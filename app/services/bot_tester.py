"""Bot readiness tester — dry-run the conversation graph without sending WhatsApp.

Used by the provisioning flow to auto-validate a newly created tenant before
declaring it live, and by the merchant's "Test Bot" wizard step to preview
replies without side effects.

Two entry points:
  - DryRunGateway         : a no-op PhoneGateway that records calls instead of sending.
  - dry_run_reply(...)    : run one message through the full graph, return the reply.
  - score_tenant(...)     : run a battery of sheet-derived + golden queries and
                            compute a 0-100 readiness score.
"""
import logging
from datetime import datetime, timezone
from statistics import fmean
from typing import Any

from app.config import get_settings
from app.graph.graph import build_graph
from app.graph.state import ChatState

logger = logging.getLogger(__name__)

# Response weight for each breakdown "kind" when computing the readiness score.
_SHEET_WEIGHT = 0.6
_GOLDEN_WEIGHT = 0.2
_QUALITY_WEIGHT = 0.2

# Hard cap on how many sheet-derived queries we run during a score. Sheet can be
# large; scoring must stay cheap. We sample evenly from FAQ and catalog.
MAX_SHEET_QUERIES = 20

# Golden questions per business_type. These exercise generic buyer phrasing that
# a merchant sheet might not literally contain — a miss here is a warning, not a
# hard failure (the merchant simply may not have that FAQ yet).
GOLDEN_QUESTIONS: dict[str, list[str]] = {
    "jualan": [
        "cara ordernya gimana?",
        "berapa ongkirnya?",
        "pembayarannya bisa apa aja?",
    ],
    "klinik": [
        "jam buka kliniknya jam berapa?",
        "di mana lokasi kliniknya?",
        "berapa biaya konsultasinya?",
    ],
    "kuliner": [
        "menu apa saja yang tersedia?",
        "bisa delivery tidak?",
        "jam bukanya kapan?",
    ],
    "fashion": [
        "ada size L tidak?",
        "bisa retur kalau salah ukuran?",
        "bahannya terbuat dari apa?",
    ],
}


class DryRunGateway:
    """Records send_message calls instead of transmitting.

    Used so the full graph (including fallback_human, which normally texts the
    owner) can execute headlessly during a test without any side effects.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def send_message(self, phone: str, message: str) -> dict[str, Any]:
        self.calls.append((phone, message))
        return {"status": "ok", "dry_run": True}

    async def send_attachment(self, phone: str, image_url: str, caption: str = "") -> dict[str, Any]:
        self.calls.append((phone, f"[FOTO {image_url}] {caption}"))
        return {"status": "ok", "dry_run": True}


def _tenant_record(tenant_id: str) -> dict[str, Any]:
    from app.db.tenant_repo import get_tenant

    tenant = get_tenant(tenant_id)
    if tenant is None:
        raise ValueError(f"tenant '{tenant_id}' not found")
    return dict(tenant)


def _base_state(tenant_id: str, message: str) -> ChatState:
    return {
        "tenant_id": tenant_id,
        "wa_number": "dry-run",
        "thread_id": f"dry-run:{tenant_id}",
        "message_text": message,
        "timestamp": datetime.now(timezone.utc),
    }


def dry_run_reply(
    tenant_id: str,
    message: str,
    llm_client: Any = None,
    sheets_client: Any = None,
    semantic_search_client: Any = None,
) -> dict:
    """Run one user message through the tenant's graph headlessly.

    Returns the reply dict plus the DryRunGateway calls so callers/tests can
    assert nothing was transmitted.
    """
    llm_client = llm_client or _build_llm_client()
    sheets_client = sheets_client or _build_sheets_client(tenant_id)
    gateway = DryRunGateway()

    graph = build_graph(
        llm_client=llm_client,
        sheets_client=sheets_client,
        gateway_client=gateway,
        semantic_search_client=semantic_search_client,
        include_chat_log=False,
        persist_orders=False,
    )
    result = graph.invoke(_base_state(tenant_id, message))
    return {
        "reply_text": result.get("reply_text", ""),
        "intent": result.get("intent"),
        "confidence": result.get("confidence"),
        "action": result.get("action"),
        "fallback_reason": result.get("fallback_reason"),
        "match_kind": result.get("match_kind"),
        "blueprint_fallback": result.get("blueprint_fallback"),
        "order_items": result.get("order_items"),
        "order_total": result.get("order_total"),
        "gateway_calls": list(gateway.calls),
    }


def score_tenant(
    tenant_id: str,
    llm_client: Any = None,
    sheets_client: Any = None,
    semantic_search_client: Any = None,
    threshold: float | None = None,
) -> dict:
    """Run a readiness battery for a tenant and produce a 0-100 score.

    Breakout (0-100):
      - 60% sheet-derived containment (does the bot answer the merchant's own
        FAQ/catalog questions with action=='reply').
      - 20% per-business golden questions (miss → warning, not hard fail).
      - 20% quality (avg confidence on replies, minus penalties for fallback & error).
    """
    from app.db.tenant_repo import get_tenant

    tenant = get_tenant(tenant_id)
    if tenant is None:
        raise ValueError(f"tenant '{tenant_id}' not found")

    llm_client = llm_client or _build_llm_client()
    sheets_client = sheets_client or _build_sheets_client(tenant_id)

    if threshold is None:
        threshold = get_settings().bot_readiness_threshold

    faq_rows = sheets_client.read_faq()
    catalog_rows = sheets_client.read_catalog()

    queries: list[tuple[str, str]] = []
    # FAQ questions (sheet-derived).
    faq_questions = [(r.get("pertanyaan") or "").strip() for r in faq_rows]
    faq_questions = [q for q in faq_questions if q]
    # Catalog: "ada <nama>?" intended to be answerable.
    catalog_names = [(r.get("nama_produk") or "").strip() for r in catalog_rows]
    catalog_names = [n for n in catalog_names if n]
    catalog_queries = [f"ada {n}?" for n in catalog_names]

    # Sample to stay cheap: equal split of the allowance across both sources.
    half = max(1, MAX_SHEET_QUERIES // 2)
    sampled_faq = _sample(faq_questions, half)
    sampled_cat = _sample(catalog_queries, half)
    queries.extend(("faq", q) for q in sampled_faq)
    queries.extend(("catalog", q) for q in sampled_cat)

    # Golden per business_type.
    golden = GOLDEN_QUESTIONS.get(tenant.get("business_type", "jualan"), [])
    queries.extend(("golden", q) for q in golden)

    gateway = DryRunGateway()
    graph = build_graph(
        llm_client=llm_client,
        sheets_client=sheets_client,
        gateway_client=gateway,
        semantic_search_client=semantic_search_client,
        include_chat_log=False,
        persist_orders=False,
    )

    breakdown: list[dict] = []
    for kind, query in queries:
        result = _safe_invoke(graph, tenant_id, query)
        breakdown.append(
            {
                "kind": kind,
                "query": query,
                "action": result.get("action"),
                "intent": result.get("intent"),
                "confidence": result.get("confidence"),
                "fallback_reason": result.get("fallback_reason"),
                "reply_excerpt": (result.get("reply_text", "") or "")[:120],
            }
        )

    return _compute_readiness(breakdown, threshold=threshold)


def _sample(items: list[str], n: int) -> list[str]:
    """Deterministic sample of at most n items, preserving order."""
    if len(items) <= n:
        return items
    step = max(1, len(items) // n)
    return items[::step][:n] if step else items[:n]


def _safe_invoke(graph, tenant_id: str, query: str) -> dict:
    try:
        return graph.invoke(_base_state(tenant_id, query))
    except Exception as e:  # noqa: BLE001
        logger.error(
            "bot_test_query_failed",
            extra={"tenant_id": tenant_id, "query": query, "error": str(e)},
        )
        return {"action": "error", "intent": None, "confidence": 0.0,
                "fallback_reason": "error", "reply_text": ""}


def _compute_readiness(breakdown: list[dict], threshold: float) -> dict:
    total = len(breakdown)
    if total == 0:
        return {
            "score": 0,
            "status": "error",
            "containment_rate": 0.0,
            "avg_confidence": 0.0,
            "fallbacks": 0,
            "errors": 0,
            "golden_hits": 0,
            "warnings": [],
            "breakdown": [],
        }

    sheet_items = [b for b in breakdown if b["kind"] in ("faq", "catalog")]
    golden_items = [b for b in breakdown if b["kind"] == "golden"]

    def _reply_rate(items: list[dict]) -> float:
        if not items:
            return 1.0
        return sum(1 for b in items if b.get("action") == "reply") / len(items)

    sheet_rate = _reply_rate(sheet_items)
    golden_rate = _reply_rate(golden_items)

    replies = [b for b in breakdown if b.get("action") == "reply"]
    avg_confidence = fmean([b.get("confidence") or 0.0 for b in replies]) if replies else 0.0
    fallback_count = sum(1 for b in breakdown if b.get("action") == "fallback")
    error_count = sum(1 for b in breakdown if b.get("action") == "error")

    # Quality 0..1: start perfect and subtract penalties for fallback/error.
    # (avg_confidence is reported separately — low confidence already routes to
    # fallback in the graph, so it is reflected via the fallback count.)
    quality = max(0.0, min(1.0, 1.0 - 0.15 * (fallback_count / total) - 0.4 * (error_count / total)))

    score = round(100 * (
        _SHEET_WEIGHT * sheet_rate
        + _GOLDEN_WEIGHT * golden_rate
        + _QUALITY_WEIGHT * quality
    ))

    golden_hits = sum(1 for b in golden_items if b.get("action") == "reply")
    # Warnings: golden questions the sheet can't answer (merchant hasn't added them).
    warnings = [
        f"FAQ '{b['query']}' tidak ditemukan di data Anda."
        for b in golden_items if b.get("action") != "reply"
    ]
    if error_count:
        warnings.append(f"{error_count} query gagal diproses (error).")
    if not sheet_items:
        warnings.append("Tidak ada FAQ/katalog terdeteksi untuk diuji.")

    return {
        "score": score,
        "status": "ready" if score >= threshold else "needs_review",
        "containment_rate": round(sheet_rate, 3),
        "avg_confidence": round(avg_confidence, 3),
        "fallbacks": fallback_count,
        "errors": error_count,
        "golden_hits": golden_hits,
        "warnings": warnings,
        "breakdown": breakdown,
    }


def _build_llm_client() -> Any:
    from app.services.llm import get_safe_llm_client

    settings = get_settings()
    priority = [settings.llm_backend] if settings.llm_backend else []
    for extra in ("router", "adacode", "gemini", "anthropic"):
        if extra not in priority and getattr(settings, f"{extra}_api_key", ""):
            priority.append(extra)
    return get_safe_llm_client(priority or ["gemini", "adacode"])


def _build_sheets_client(tenant_id: str) -> Any:
    tenant = _tenant_record(tenant_id)
    if tenant.get("data_source") == "upload":
        from app.services.local_data import LocalDataClient

        return LocalDataClient(tenant_id=tenant_id)

    from app.services.sheets import GoogleSheetsClient

    settings = get_settings()
    return GoogleSheetsClient(
        credentials_json_path=settings.google_sheets_credentials_json_path,
        spreadsheet_id=tenant.get("google_sheet_id", ""),
    )