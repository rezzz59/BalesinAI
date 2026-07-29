"""FastAPI entry point for OrderCloser Lite WhatsApp AI Agent."""
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db import init_db  # Ensure DB tables are created
from app.db.checkpointer import SqliteCheckpointer
from app.auth.signature import verify_wablas_signature, SignatureError
from app.graph.graph import (
    build_graph,
    reset_compiled_graph_for_testing,
)
from app.graph.state import ChatState
from app.services.llm import (
    AnthropicLLMClient,
    GeminiLLMClient,
    LLMError,
)
from app.services.sheets import GoogleSheetsClient
from app.services.phone_gateway import PhoneGateway, PhoneGatewayException
from app.services.fonnte import FonnteGateway, FonnteError
from app.services.wablas import WablasClient, WablasError

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


# --- Client Initialization ---
_llm_client: Optional[Any] = None
_sheets_client: Optional[Any] = None
_phone_gateway: Optional[Any] = None
_checkpointer: Any = None  # LangGraph saver (e.g., SqliteCheckpointer)
_compiled_graph: Any = None


def _create_llm_client():
    """Create LLM client, falling back to MockLLMClient if real SDK is unavailable."""
    from app.services.llm import get_llm_client, MockLLMClient, LLMError

    settings = get_settings()
    backend = (settings.llm_backend or "gemini").lower()

    try:
        return get_llm_client()
    except (ImportError, ModuleNotFoundError, LLMError) as e:
        logger.warning(f"Real LLM client initialization failed: {e}. Using MockLLMClient for testing.")
        return MockLLMClient()


def _create_sheets_client():
    settings = get_settings()
    if not settings.google_sheets_credentials_json_path:
        raise RuntimeError("GOOGLE_SHEETS_CREDENTIALS_JSON_PATH not set")
    if not settings.google_sheets_spreadsheet_id:
        # In a real deployment, this would be per-tenant from DB; for default usage take from env or warn
        logger.warning("GOOGLE_SHEETS_SPREADSHEET_ID not set - using placeholder ID only for testing")
    return GoogleSheetsClient(
        credentials_json_path=settings.google_sheets_credentials_json_path,
        spreadsheet_id=settings.google_sheets_spreadsheet_id or "placeholder-sheet-id",
    )


def _create_phone_gateway():
    """Create phone gateway client based on WHATSAPP_GATEWAY config.

    Returns:
        - FonnteGateway if whatsapp_gateway == "fonnte"
        - WablasClient if whatsapp_gateway == "wablas"

    Raises:
        RuntimeError if required env vars are missing for the chosen gateway.
    """
    settings = get_settings()
    gateway = (settings.whatsapp_gateway or "wablas").lower()

    if gateway == "fonnte":
        if not settings.fonnte_api_key:
            raise RuntimeError("FONNTE_API_KEY not configured")
        return FonnteGateway(api_key=settings.fonnte_api_key)

    elif gateway == "wablas":
        if not settings.wablas_base_url:
            raise RuntimeError("WABLAS_BASE_URL must be set")
        api_key = settings.wablas_api_key or ""
        return WablasClient(base_url=settings.wablas_base_url, api_key=api_key)

    else:
        raise RuntimeError(f"Unknown WHATSAPP_GATEWAY: {gateway}. Use 'wablas' or 'fonnte'.")


def _ensure_clients():
    global _llm_client, _sheets_client, _phone_gateway, _checkpointer, _compiled_graph
    try:
        if _llm_client is None:
            _llm_client = _create_llm_client()
            logger.info(
                "llm_client_initialized",
                extra={"backend": getattr(_llm_client, "backend", "unknown")},
            )
    except Exception as e:
        logger.error("llm_client_init_failed", exc_info=True)
        _llm_client = None  # Menandai failure
    try:
        if _sheets_client is None:
            _sheets_client = _create_sheets_client()
            logger.info("sheets_client_initialized")
    except Exception as e:
        logger.error("sheets_client_init_failed", exc_info=True)
        _sheets_client = None
    try:
        if _phone_gateway is None:
            _phone_gateway = _create_phone_gateway()
            gateway_type = type(_phone_gateway).__name__
            logger.info(f"{gateway_type}_client_initialized")
    except Exception as e:
        logger.error("phone_gateway_init_failed", exc_info=True)
        _phone_gateway = None
    if _checkpointer is None:
        _checkpointer = SqliteCheckpointer()
        logger.info("init_checkpointer", extra={"info": "SQLite-backed checkpointer ready"})
    if _compiled_graph is None:
        try:
            _compiled_graph = build_graph(
                _llm_client, _sheets_client, _phone_gateway, checkpointer=_checkpointer
            )
            logger.info("graph_compiled", extra={"status": "ready"})
        except Exception as e:
            logger.error("graph_build_failed", exc_info=True)
            raise RuntimeError(f"Failed to compile graph: {e}") from e


# --- API Endpoints ---


@app.post("/webhook/whatsapp/")
async def whatsapp_webhook(request: Request):
    """Webhook endpoint for incoming WhatsApp messages with signature verification."""
    # Get raw request body for signature verification
    try:
        raw_body = await request.body()
    except Exception:
        raise HTTPException(status_code=400, detail="Unable to read request body")

    # Parse JSON data separately
    try:
        data = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Get API key for auth verification based on selected gateway
    settings = get_settings()
    gateway = (settings.whatsapp_gateway or "wablas").lower()

    if gateway == "fonnte":
        api_key = settings.fonnte_api_key or ""
        if not api_key:
            raise HTTPException(
                status_code=500, detail="FONNTE_API_KEY not configured on server"
            )
        # Fonnte uses Bearer token auth
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=401,
                detail="Missing Bearer Authorization header (Fonnte auth)",
            )
        provided_token = auth_header[7:]
        if provided_token != api_key:
            raise HTTPException(status_code=401, detail="Invalid Fonnte API key")
    else:
        # Wablas
        wablas_api_key = settings.wablas_api_key or ""
        if not wablas_api_key:
            raise HTTPException(
                status_code=500, detail="WABLAS_API_KEY not configured on server"
            )
        # Verify Wablas authentication — supports two methods:
        # 1. Authorization header: Bearer <API_KEY> (token-based)
        # 2. X-Wablas-Signature header (HMAC-SHA256 of body)
        auth_header = request.headers.get("Authorization", "")

        if auth_header.startswith("Bearer "):
            # Method 1: Token-based auth
            provided_token = auth_header[7:]  # Remove "Bearer "
            if provided_token != wablas_api_key:
                raise HTTPException(status_code=401, detail="Invalid API key")
        else:
            # Method 2: Signature-based auth
            signature_header = request.headers.get("X-Wablas-Signature")
            if not signature_header:
                raise HTTPException(
                    status_code=401,
                    detail="Missing X-Wablas-Signature or Authorization header",
                )
            try:
                verify_wablas_signature(signature_header, raw_body, wablas_api_key)
            except SignatureError as e:
                raise HTTPException(status_code=401, detail=f"Signature error: {e}")

    tenant_id = data.get("tenant_id", "default")
    wa_number = data.get("wa_number", "")
    thread_id = data.get("thread_id", "")
    message_text = data.get("message_text", "")

    # Validate required fields
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

    _ensure_clients()

    state: ChatState = {
        "tenant_id": tenant_id,
        "wa_number": wa_number,
        "thread_id": thread_id,
        "message_text": message_text,
        "timestamp": datetime.now(),
    }

    try:
        # Run graph - uses async nodes (ainvoke)
        result = await _compiled_graph.ainvoke(state)
        logger.info(
            "webhook_processed",
            extra={"thread_id": state.get("thread_id"), "intent": result.get("intent")},
        )
        return {"status": "ok", "state": result}
    except LLMError as e:
        logger.error("llm_error", exc_info=True)
        raise HTTPException(status_code=500, detail=f"LLM error: {e}")
    except (FonnteError, WablasError, PhoneGatewayException) as e:
        logger.error("whatsapp_gateway_error", exc_info=True)
        raise HTTPException(status_code=500, detail=f"WhatsApp gateway error: {e}")
    except Exception as e:  # noqa: BLE001
        logger.error("unexpected_error", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error")


@app.get("/health")
async def health_check():
    _ensure_clients()
    return {
        "status": "healthy",
        "clients_ready": all([_llm_client, _sheets_client, _phone_gateway]),
        "graph_compiled": _compiled_graph is not None,
    }


# Helper for tests / dev — reset compiled graph so injected mocks take effect
@app.post("/debug/reset-graph/")
async def debug_reset_graph():
    reset_compiled_graph_for_testing()
    global _llm_client, _sheets_client, _phone_gateway, _checkpointer, _compiled_graph
    _llm_client = None
    _sheets_client = None
    _phone_gateway = None
    _checkpointer = None
    _compiled_graph = None
    return {"status": "graph reset"}


__all__ = ["app"]