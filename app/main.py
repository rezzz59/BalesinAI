"""FastAPI entry point for OrderCloser Lite WhatsApp AI Agent."""
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
_wablas_client: Optional[Any] = None
_checkpointer: Any = None  # LangGraph saver (e.g., SqliteCheckpointer)
_compiled_graph: Any = None


def _create_llm_client():
    settings = get_settings()
    backend = (settings.llm_backend or "gemini").lower()
    if backend == "anthropic":
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        return AnthropicLLMClient(api_key=settings.anthropic_api_key)
    elif backend == "gemini":
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        return GeminiLLMClient(api_key=settings.gemini_api_key)
    else:
        raise RuntimeError(f"unknown LLM backend: {backend}")


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


def _create_wablas_client():
    settings = get_settings()
    if not settings.wablas_base_url:
        raise RuntimeError("WABLAS_BASE_URL must be set")
    api_key = settings.wablas_api_key or ""  # may be empty for some deployments that rely on per-tenant auth
    return WablasClient(base_url=settings.wablas_base_url, api_key=api_key)


def _ensure_clients():
    global _llm_client, _sheets_client, _wablas_client, _checkpointer, _compiled_graph
    if _llm_client is None:
        _llm_client = _create_llm_client()
    if _sheets_client is None:
        _sheets_client = _create_sheets_client()
    if _wablas_client is None:
        _wablas_client = _create_wablas_client()
    if _checkpointer is None:
        _checkpointer = SqliteCheckpointer()
        logger.info("init_checkpointer", extra="SQLite-backed checkpointer ready")
    if _compiled_graph is None:
        _compiled_graph = build_graph(
            _llm_client, _sheets_client, _wablas_client, checkpointer=_checkpointer
        )


# --- API Endpoints ---


@app.post("/webhook/whatsapp/")
async def whatsapp_webhook(request: Request):
    """Webhook endpoint for incoming WhatsApp messages."""
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    _ensure_clients()

    state: ChatState = {
        "tenant_id": data.get("tenant_id", "default"),
        "wa_number": data.get("wa_number", ""),
        "thread_id": data.get("thread_id", ""),
        "message_text": data.get("message_text", ""),
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
    except WablasError as e:
        logger.error("wablas_error", exc_info=True)
        raise HTTPException(status_code=500, detail=f"WhatsApp error: {e}")
    except Exception as e:  # noqa: BLE001
        logger.error("unexpected_error", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error")


@app.get("/health")
async def health_check():
    _ensure_clients()
    return {
        "status": "healthy",
        "clients_ready": all([_llm_client, _sheets_client, _wablas_client]),
        "graph_compiled": _compiled_graph is not None,
    }


# Helper for tests / dev — reset compiled graph so injected mocks take effect
@app.post("/debug/reset-graph/")
async def debug_reset_graph():
    reset_compiled_graph_for_testing()
    global _llm_client, _sheets_client, _wablas_client, _checkpointer, _compiled_graph
    _llm_client = None
    _sheets_client = None
    _wablas_client = None
    _checkpointer = None
    _compiled_graph = None
    return {"status": "graph reset"}


__all__ = ["app"]