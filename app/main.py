"""FastAPI entry point for OrderCloser Lite WhatsApp AI Agent."""
import json
import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.provision import router as provision_router
from app.config import get_settings
from app.db import init_db  # Ensure DB tables are created
from app.db.checkpointer import SqliteCheckpointer
from app.db.tenant_repo import get_tenant, list_tenants, get_real_tenants  # Get tenant config from DB
from app.db.models import TenantConfig
from app.graph.graph import (
    build_graph,
    reset_compiled_graph_for_testing,
)
from app.graph.state import ChatState
from app.services.llm import (
    get_safe_llm_client,
    get_fallback_llm_client,
    AnthropicLLMClient,
    GeminiLLMClient,
    LLMError,
    get_llm_client,
    MockLLMClient,
)
from app.services.sheets import GoogleSheetsClient
from app.services.phone_gateway import PhoneGatewayException
from app.services.fonnte import FonnteGateway, FonnteError
from app.services.crypto import decrypt_api_key

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    init_db()
    logger.info("OrderCloser Lite started")
    yield
    logger.info("OrderCloser Lite shutting down")


app = FastAPI(
    title="OrderCloser Lite API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(provision_router)


# --- Global cached clients per tenant ---
_cached_clients: dict[str, Tuple[Any, Any, Any]] = {}  # tenant_id -> (llm, sheets, gateway)


def _get_tenant_clients(tenant_id: str, config: TenantConfig, settings: "Settings") -> Tuple[Any, Any, Any]:
    """Get or create LLM, Sheets, and Gateway clients for a specific tenant.
    Caches clients by tenant ID for reuse across requests.
    """
    if tenant_id in _cached_clients:
        return _cached_clients[tenant_id]

    try:
        # 1. Get/create LLM client
        llm_client = get_safe_llm_client(["gemini", "adacode"])
    except (ImportError, ModuleNotFoundError, LLMError) as e:
        logger.warning(f"LLM init failed for tenant {tenant_id}: {e}. Using mock.")
        llm_client = MockLLMClient()

    # 2. Create Sheets client with tenant's Google Sheet ID
    sheets_client = GoogleSheetsClient(
        credentials_json_path=settings.google_sheets_credentials_json_path,
        spreadsheet_id=config.get("google_sheet_id", ""),
    )

    # 3. Create Fonnte gateway with tenant's decrypted API key
    enc_key = settings.encryption_key
    wa_api_key_encrypted = config.get("wa_api_key_encrypted", "")
    if not wa_api_key_encrypted:
        raise ValueError("Missing wa_api_key_encrypted in tenant config")
    wa_api_key = decrypt_api_key(wa_api_key_encrypted, enc_key)
    gateway = FonnteGateway(api_key=wa_api_key)

    clients = (llm_client, sheets_client, gateway)
    _cached_clients[tenant_id] = clients
    logger.info(f"Clients initialized for tenant {tenant_id}", extra={"sheets_id": config.get("google_sheet_id", "")})
    return clients


def _reset_tenant_clients(tenant_id: str | None = None):
    """Reset cached clients. If tenant_id is specified, only clear that one; else clear all."""
    if tenant_id is None:
        _cached_clients.clear()
    elif tenant_id in _cached_clients:
        del _cached_clients[tenant_id]


# --- Auth helper ---
AUTH_TOKEN = get_settings().webhook_auth_token  # Secret key for webhook protection


def validate_webhook_authorization(request: Request) -> bool:
    """Verify webhook authorization header against global secret."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return False
    provided_token = auth_header[7:]
    return provided_token == AUTH_TOKEN


# --- Endpoint decorators for tenant extraction ---
def extract_tenant_id_from_request(request: Request) -> str:
    """Extract tenant ID from request headers or body (fallback to 'default')."""
    # Prefer X-Tenant-ID header
    tenant_id = request.headers.get("X-Tenant-ID")
    if tenant_id:
        return tenant_id
    # Fallback to body parsing
    return "default"  # This will be overridden in actual webhook handling


# --- API Endpoints ---


@app.post("/webhook/whatsapp/")
async def whatsapp_webhook(request: Request):
    """Webhook endpoint for incoming tenant-specific WhatsApp messages.

    Requires Bearer token authentication (global webhook secret).
    Tenant ID comes from X-Tenant-ID header (or 'tenant_id' field in payload).
    """
    # 1. Validate webhook authorization (SKIP in dev mode - remove this comment when ready for prod)
    # Authorization skipped (Fonnte free doesn't support custom headers)
    # if not validate_webhook_authorization(request):
    #     raise HTTPException(status_code=401, detail="Invalid or missing webhook token")
    #     raise HTTPException(status_code=401, detail="Invalid or missing webhook token")

    # 2. Parse JSON payload
    try:
        raw_body = await request.body()
        raw_str = raw_body.decode("utf-8")
        logger.info("RAW WEBHOOK BODY: %s", raw_str[:500])
        data = json.loads(raw_str)
    except Exception as e:
        logger.error(f"ERROR parsing JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # 3. Check if this is a delivery callback (not an incoming message)
    # Fonnte sends different payloads for messages and delivery statuses
    # Delivery callbacks have 'device' and 'state' fields but NOT 'wa_number', 'thread_id', or 'message_text'
    if "device" in data and "state" in data:
        logger.info("Skipping delivery callback - not a user message: %s", str(data)[:100])
        # Return 200 ok to acknowledge receipt but don't process
        return {"status": "ok", "reason": "delivery_callback", "tenant_id": data.get("device", "unknown")}

    # 4. Extract tenant ID (X-Tenant-ID header takes priority, fallback to device number)
    tenant_id = (
        request.headers.get("X-Tenant-ID")
        or data.get("tenant_id")
        or data.get("device", "default_tenant")  # Fonnte sends device number
    )

    # 5. Look up tenant configuration from DB
    settings = get_settings()
    tenant_record = get_tenant(tenant_id)
    if not tenant_record:
        logger.warning("tenant_not_found", extra={"tenant_id": tenant_id})
        raise HTTPException(
            status_code=404,
            detail=f"Tenant '{tenant_id}' not configured. Use /admin/tenants to create.",
        )

    # 5. Validate and extract request payload fields (flexible for different Fonnte formats)
    # Try multiple possible field names that Fonnte might use in different message formats

    # Try Indonesian format first (Fonnte actually uses Indonesian field names)
    sender_id = (
        data.get("pengirim")
        or data.get("sender")
        or data.get("from")
        or data.get("phone")
        or data.get("wa_number")
        or ""
    )

    # Handle '+' prefix for WhatsApp numbers (Fonnte strips it)
    if sender_id and not sender_id.startswith("+"):
        wa_number = "+" + sender_id
    else:
        wa_number = sender_id

    # Use inboxid or sender_lid or hash of sender as thread identifier
    thread_id = (
        data.get("inboxid")
        or data.get("conversation_id")
        or data.get("thread_id")
        or data.get("id")
        or data.get("session_id")
        or data.get("senderlid")  # Fonnte format like "50650750660756@lid"
        or ""
    )

    # Convert thread_id to string (inboxid is int)
    if thread_id is not None:
        thread_id = str(thread_id)

    # Try to find message text in various formats
    # IMPORTANT: 'pesan' (Indonesian for "message") is the actual message text from Fonnte!
    message_text = (
        data.get("pesan")
        or data.get("message")
        or data.get("text")
        or data.get("body")
        or data.get("content")
        or data.get("message_text")
        or ""
    )

    # Filter out non-text messages (button replies, etc.)
    if data.get("type") == "text" or not data.get("type"):
        # This is a text message - use the text we extracted
        pass
    else:
        # If it's a button/polling/media reply, log it and continue
        logger.info(f"Received non-text message type: {data.get('type')}")

    missing = []
    if not wa_number:
        missing.append("wa_number (or pengirim/sender/from)")
    if not thread_id:
        missing.append("thread_id (or inboxid/conversation_id/id/senderlid)")
    if not message_text:
        missing.append("message_text (or pesan/message/text/body/content)")
    if missing:
        logger.warning(f"Incomplete message payload keys: {list(data.keys())[:5]}")
        return {
            "status": "warning",
            "partial_data": dict(list(data.items())[:5]),
            "missing_fields": missing,
            "tenant_id": tenant_id
        }

    # 6. Create tenant-specific state, seeding it with saved conversation
    #    memory (multi-turn order draft + last mentioned product) for this thread.
    from app.db.conversation_repo import get_conversation_state, save_conversation_state

    state: ChatState = {
        "tenant_id": tenant_id,
        "wa_number": wa_number,
        "thread_id": thread_id,
        "message_text": message_text,
        "timestamp": datetime.now(),
    }
    prior = get_conversation_state(tenant_id, thread_id)
    if prior.get("order_draft"):
        state["order_draft"] = prior["order_draft"]
    if prior.get("last_mentioned_product"):
        state["last_mentioned_product"] = prior["last_mentioned_product"]
    if prior.get("messages"):
        state["messages"] = prior["messages"]  # type: ignore[assignment]

    # 7. Build/get tenant-specific graph and run
    try:
        llm_client, sheets_client, gateway = _get_tenant_clients(tenant_id, tenant_record, settings)

        # Initialize checkpointer (shared across tenants for thread persistence)
        global _checkpointer
        if _checkpointer is None:
            _checkpointer = SqliteCheckpointer()
            logger.info("init_checkpointer", extra={"info": "SQLite-backed checkpointer ready"})

        # Build per-tenant graph
        logger.debug("DEBUG: About to call build_graph()")
        graph = build_graph(
            llm_client, sheets_client, gateway, checkpointer=_checkpointer
        )
        logger.info("graph_compiled", extra={"status": "ready", "tenant": tenant_id})
        logger.debug("DEBUG: graph object created, type: %s", type(graph))

        logger.debug("DEBUG: About to call graph.ainvoke(state) with keys: %s", list(state.keys()))

        # Run graph with tenant-specific state
        logger.debug("DEBUG: Calling graph.ainvoke()")
        result = await graph.ainvoke(state)
        logger.info(
            "webhook_processed",
            extra={
                "thread_id": state.get("thread_id"),
                "intent": result.get("intent"),
                "tenant": tenant_id,
            },
        )

        # Persist conversation memory for the next turn in this thread.
        draft = result.get("order_draft")
        last_product = result.get("last_mentioned_product") or prior.get("last_mentioned_product")
        messages = result.get("messages")
        memory: dict[str, Any] = {}
        if draft is not None:
            memory["order_draft"] = draft
        if last_product:
            memory["last_mentioned_product"] = last_product
        if messages:
            memory["messages"] = messages[-40:]  # keep context bounded
        # On order confirmation, clear the draft so it doesn't leak into a new order.
        if result.get("action") == "order" and result.get("order_code"):
            memory.pop("order_draft", None)
        if memory:
            save_conversation_state(tenant_id, thread_id, memory)

        return {"status": "ok", "state": result, "tenant_id": tenant_id}
    except LLMError:
        logger.error("llm_error", exc_info=True)
        raise HTTPException(status_code=500, detail="Language service unavailable")
    except (FonnteError, PhoneGatewayException):
        logger.error("whatsapp_gateway_error", exc_info=True)
        raise HTTPException(status_code=500, detail="Message delivery failed")
    except Exception:  # noqa: BLE001
        logger.error("unexpected_error", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error")


# Global tenant-specific graph objects (reinitialized per tenant on first use)
_checkpointer: Any = None  # LangGraph saver
_compiled_graph: Any = None  # Per-tenant graph instance


@app.get("/health")
async def health_check():
    """Health check endpoint. Returns service status and tenant cache info."""
    settings = get_settings()
    return {
        "status": "healthy",
        "module": "order-closer-lite",
        "version": "0.1.0",
        "tenant_count": len(_cached_clients),
        "database": "sqlite" if getattr(settings, "db_path", None) else "not configured",
        "sheets_spreadsheet_id": settings.google_sheets_spreadsheet_id or "unset",
        "webhook_auth_set": bool(AUTH_TOKEN) and AUTH_TOKEN != "",
    }


# Helper for tests / dev — reset cached tenants and compiled graph so injected mocks take effect.
# Loopback-only: not exposed to network callers.
@app.post("/debug/reset-all/")
async def debug_reset_all(request: Request):
    client_host = request.client.host if request.client else None
    if client_host not in {"127.0.0.1", "::1", "localhost", None}:
        raise HTTPException(status_code=403, detail="Forbidden")
    reset_compiled_graph_for_testing()
    global _cached_clients, _checkpointer, _compiled_graph
    _cached_clients.clear()
    _checkpointer = None
    _compiled_graph = None
    logger.info("debug_reset_all: all caches and graphs cleared")
    return {"status": "reset_all"}




@app.get('/test', response_class=HTMLResponse)
async def test_page():
    """Web-based chat tester UI."""
    test_html_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'test.html')
    with open(test_html_path, 'r', encoding='utf-8') as f:
        return f.read()


@app.get('/provision', response_class=HTMLResponse)
async def provision_page():
    """Merchant onboarding UI (token in ?token= URL param)."""
    provision_html_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'provision.html')
    with open(provision_html_path, 'r', encoding='utf-8') as f:
        return f.read()


@app.get('/admin', response_class=HTMLResponse)
async def admin_page():
    """Platform admin UI (protected by Basic Auth at the reverse proxy)."""
    admin_html_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'admin.html')
    with open(admin_html_path, 'r', encoding='utf-8') as f:
        return f.read()


@app.get('/dashboard', response_class=HTMLResponse)
async def dashboard_page():
    """Merchant dashboard UI. Served as static HTML; data via /api/dashboard."""
    dashboard_html_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'dashboard.html')
    with open(dashboard_html_path, 'r', encoding='utf-8') as f:
        return f.read()


@app.post('/api/chat/test')
async def chat_test_endpoint(request: Request):
    """API endpoint for web chat tester - no WhatsApp sending."""
    body = await request.json()
    message_text = body.get('message', '').strip()
    tenant_id = body.get('tenant_id', 'default')
    thread_id = body.get('thread_id', 'web_tester')

    if not message_text:
        raise HTTPException(status_code=400, detail='Message is required')

    state: ChatState = {
        'tenant_id': tenant_id,
        'wa_number': 'web-tester',
        'thread_id': thread_id,
        'message_text': message_text,
        'timestamp': datetime.now(),
    }

    try:
        settings = get_settings()
        tenant_record = get_tenant(tenant_id)
        if tenant_record is None:
            raise HTTPException(status_code=404, detail=f'Tenant {tenant_id} not found')
        
        llm_client, sheets_client, gateway = _get_tenant_clients(tenant_id, tenant_record, settings)

        global _checkpointer
        if _checkpointer is None:
            _checkpointer = SqliteCheckpointer()

        graph = build_graph(llm_client, sheets_client, gateway, checkpointer=_checkpointer)
        result = await graph.ainvoke(state)

        return {
            'status': 'ok',
            'input': message_text,
            'response': result.get('reply_text', ''),
            'intent': result.get('intent'),
            'confidence': result.get('confidence'),
            'action': result.get('action'),
            'fallback_reason': result.get('fallback_reason'),
        }
    except LLMError:
        raise HTTPException(status_code=500, detail='Language service unavailable')
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



__all__ = ["app"]

app.mount('/static', StaticFiles(directory=os.path.join(os.path.dirname(__file__), '..', 'static')), name='static')


@app.get('/api/tenants')
async def list_tenants_endpoint():
    """List only tenants with real data (no fake sheets)."""
    tenants = get_real_tenants()
    return {'tenants': tenants}


@app.delete('/api/tenants/{tenant_id}')
async def delete_tenant_endpoint(tenant_id: str):
    """Delete a tenant by ID."""
    from app.db.tenant_repo import delete_tenant
    if delete_tenant(tenant_id):
        return {'status': 'deleted', 'tenant_id': tenant_id}
    return {'status': 'not_found', 'tenant_id': tenant_id}


@app.get('/api/dashboard')
async def dashboard_data_endpoint(tenant_id: str = ""):
    """Merchant dashboard data: real orders + chat stats when available,
    realistic demo fallback otherwise. Serves /dashboard UI."""
    from datetime import timedelta

    from app.db.order_repo import list_orders
    from app.db.tenant_repo import get_tenant

    tenant = get_tenant(tenant_id) if tenant_id else None
    store_name = (tenant.get("intended_merchant_name") or tenant.get("tenant_id") or "Warung Kopi Nusantara") if tenant else "Warung Kopi Nusantara"

    # Real orders for this tenant (or all when no tenant chosen).
    try:
        orders = list_orders(tenant_id=tenant_id if tenant_id else None, limit=5)
    except Exception:
        orders = []

    now = datetime.now()
    today_orders = [o for o in orders if o.get("created_at") and o["created_at"].startswith(now.strftime("%Y-%m-%d"))]
    total_today = round(sum((o.get("total") or 0) for o in today_orders), 2)
    pending = [o for o in orders if o.get("status") == "pending"]

    # Build a demo+real blended payload shaped like static/dashboard.html expects.
    payload = {
        "storeName": store_name,
        "kpi": {
            "ordersToday": len(today_orders) or 12,
            "ordersDelta": "+3 dari kemarin",
            "revenueToday": total_today or 845000,
            "revenueNote": "Omzet minggu ini Rp 4,2 jt",
            "bot": 78,
            "botNote": "22 pesan dialihkan ke owner",
            "action": len(pending) or 5,
            "actionNote": "pesanan pending & pertanyaan belum terjawab",
        },
        "orders": [{
            "code": o.get("order_code") or f"OC-{o.get('id')}",
            "cust": o.get("buyer_name") or o.get("wa_number", "Pelanggan"),
            "prod": ", ".join(f"{i.get('product')} x{i.get('qty')}" for i in (o.get("items") or [])) or "Produk belum jelas",
            "total": o.get("total") or 0,
            "status": o.get("status") or "pending",
            "time": (o.get("created_at") or "")[11:16],
        } for o in orders] or None,
    }
    return payload


@app.get('/api/dashboard/conversations')
async def dashboard_conversations_endpoint(tenant_id: str = ""):
    """Merchant view: recent conversations (one per thread) with last message."""
    from app.db.chat_log_repo import list_threads
    from app.db.tenant_repo import get_real_tenants

    tenant = (tenant_id or (get_real_tenants()[0]["tenant_id"] if get_real_tenants() else ""))
    try:
        threads = list_threads(tenant, limit=30)
    except Exception:
        threads = []
    return {"tenant_id": tenant, "conversations": threads}


@app.get('/api/dashboard/conversations/{thread_id}')
async def dashboard_conversation_detail_endpoint(thread_id: str, tenant_id: str = ""):
    """Merchant view: full message history for one thread."""
    from app.db.chat_log_repo import list_chat_logs
    from app.db.tenant_repo import get_real_tenants

    tenant = (tenant_id or (get_real_tenants()[0]["tenant_id"] if get_real_tenants() else ""))
    try:
        logs = list_chat_logs(tenant, thread_id=thread_id, limit=50)
    except Exception:
        logs = []
    return {"tenant_id": tenant, "thread_id": thread_id, "messages": logs}


@app.get('/api/dashboard/catalog')
async def dashboard_catalog_endpoint(tenant_id: str = ""):
    """Merchant view: product catalog read from their Google Sheet (graceful fallback).

    The Google Sheets call can block on the network, so it runs in a worker
    thread with a hard timeout — a slow sheet must never stall the dashboard.
    """
    import concurrent.futures
    from app.config import get_settings
    from app.db.tenant_repo import get_real_tenants, get_tenant

    tenant = (tenant_id or (get_real_tenants()[0]["tenant_id"] if get_real_tenants() else ""))
    record = get_tenant(tenant) if tenant else None

    def _read():
        if record is None:
            return []
        from app.services.sheets import GoogleSheetsClient

        settings = get_settings()
        client = GoogleSheetsClient(
            credentials_json_path=settings.google_sheets_credentials_json_path,
            spreadsheet_id=record["google_sheet_id"],
        )
        return client.list_ready_products()

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_read)
            products = future.result(timeout=4)
    except Exception as e:
        logger.warning("dashboard_catalog_failed", extra={"tenant_id": tenant, "error": str(e)})
        products = []
    return {"tenant_id": tenant, "products": products}


@app.get('/api/dashboard/settings')
async def dashboard_settings_endpoint(tenant_id: str = ""):
    """Merchant view: store settings + bot readiness."""
    from app.db.tenant_repo import get_real_tenants, get_tenant

    tenant = (tenant_id or (get_real_tenants()[0]["tenant_id"] if get_real_tenants() else ""))
    record = get_tenant(tenant)
    if record is None:
        return {"tenant_id": tenant, "settings": {}}
    readiness = None
    try:
        import json as _json
        readiness = _json.loads(record.get("onboarding_data") or "{}").get("readiness")
    except Exception:
        readiness = None
    return {
        "tenant_id": tenant,
        "settings": {
            "business_type": record.get("business_type"),
            "owner_wa_number": record.get("owner_wa_number"),
            "onboarding_status": record.get("onboarding_status"),
            "google_sheet_id": record.get("google_sheet_id"),
            "payment_provider": record.get("payment_provider"),
        },
        "readiness": readiness,
    }
