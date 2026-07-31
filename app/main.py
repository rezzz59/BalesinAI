"""FastAPI entry point for OrderCloser Lite WhatsApp AI Agent."""
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db import init_db  # Ensure DB tables are created
from app.db.checkpointer import SqliteCheckpointer
from app.db.tenant_repo import get_tenant  # Get tenant config from DB
from app.db.models import TenantConfig
from app.graph.graph import (
    build_graph,
    reset_compiled_graph_for_testing,
)
from app.graph.state import ChatState
from app.services.llm import (
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
        llm_client = get_llm_client()
    except (ImportError, ModuleNotFoundError, LLMError) as e:
        logger.warning(f"LLM init failed for tenant {tenant_id}: {e}. Using mock.")
        llm_client = MockLLMClient()

    # 2. Create Sheets client with tenant's Google Sheet ID
    sheets_client = GoogleSheetsClient(
        credentials_json_path=settings.google_sheets_credentials_json_path,
        spreadsheet_id=config.google_sheet_id,
    )

    # 3. Create Fonnte gateway with tenant's decrypted API key
    enc_key = settings.encryption_key
    wa_api_key = decrypt_api_key(config.wa_api_key_encrypted, enc_key)
    gateway = FonnteGateway(api_key=wa_api_key)

    clients = (llm_client, sheets_client, gateway)
    _cached_clients[tenant_id] = clients
    logger.info(f"Clients initialized for tenant {tenant_id}", extra={"sheets_id": config.google_sheet_id})
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
    # 1. Validate webhook authorization
    if not validate_webhook_authorization(request):
        raise HTTPException(status_code=401, detail="Invalid or missing webhook token")

    # 2. Parse JSON payload
    try:
        raw_body = await request.body()
        data = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # 3. Extract tenant ID (X-Tenant-ID header takes priority)
    tenant_id = (
        request.headers.get("X-Tenant-ID")
        or data.get("tenant_id")
        or "default"
    )

    # 4. Look up tenant configuration from DB
    settings = get_settings()
    tenant_record = get_tenant(tenant_id)
    if not tenant_record:
        logger.warning("tenant_not_found", extra={"tenant_id": tenant_id})
        raise HTTPException(
            status_code=404,
            detail=f"Tenant '{tenant_id}' not configured. Use /admin/tenants to create.",
        )

    # 5. Validate request payload fields
    wa_number = data.get("wa_number", "")
    thread_id = data.get("thread_id", "")
    message_text = data.get("message_text", "")

    missing = []
    if not wa_number:
        missing.append("wa_number")
    if not thread_id:
        missing.append("thread_id")
    if not message_text:
        missing.append("message_text")
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required fields: {', '.join(missing)}",
        )

    # 6. Create tenant-specific state
    state: ChatState = {
        "tenant_id": tenant_id,
        "wa_number": wa_number,
        "thread_id": thread_id,
        "message_text": message_text,
        "timestamp": datetime.now(),
    }

    # 7. Build/get tenant-specific graph and run
    try:
        llm_client, sheets_client, gateway = _get_tenant_clients(tenant_id, tenant_record, settings)

        # Initialize checkpointer (shared across tenants for thread persistence)
        global _checkpointer
        if _checkpointer is None:
            _checkpointer = SqliteCheckpointer()
            logger.info("init_checkpointer", extra={"info": "SQLite-backed checkpointer ready"})

        # Build per-tenant graph
        graph = build_graph(
            llm_client, sheets_client, gateway, checkpointer=_checkpointer
        )
        logger.info("graph_compiled", extra={"status": "ready", "tenant": tenant_id})

        # Run graph with tenant-specific state
        result = await graph.ainvoke(state)
        logger.info(
            "webhook_processed",
            extra={
                "thread_id": state.get("thread_id"),
                "intent": result.get("intent"),
                "tenant": tenant_id,
            },
        )
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


__all__ = ["app"]