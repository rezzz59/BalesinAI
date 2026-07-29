"""LangGraph state graph assembly & routing functions."""
import asyncio
import concurrent.futures
import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.config import get_settings
from app.graph.nodes import (
    classify_intent,
    compose_reply,
    fallback_human,
    lookup_catalog,
    send_whatsapp,
    write_chat_log,
)
from app.graph.state import ChatState

logger = logging.getLogger(__name__)


def _run_async_from_sync(coro):
    """Run a coroutine from a sync context, even if an event loop is running.

    Uses a worker thread to spin up a private event loop. This avoids
    'event loop already running' errors when graph nodes (sync) are
    called from inside an async FastAPI request handler.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    # Loop already running — execute in dedicated thread
    def _runner():
        return asyncio.run(coro)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_runner)
        return future.result()


def should_fallback(state: ChatState, threshold: float | None = None) -> bool:
    """Decide whether to route to fallback based on confidence & intent."""
    if threshold is None:
        threshold = get_settings().intent_confidence_threshold

    if state.get("intent") == "unclear":
        return True
    if state.get("confidence", 0.0) < threshold:
        return True
    return False


def route_after_classify(state: ChatState) -> str:
    """Route after classify_intent node."""
    return "fallback_human" if should_fallback(state) else "lookup_catalog"


def route_after_lookup(state: ChatState) -> str:
    """Route after lookup_catalog node. Fallback if lookup returned nothing for faq/product."""
    intent = state.get("intent")
    if intent == "faq" and not state.get("catalog_answer"):
        return "compose_reply_fallback"
    if intent == "check_product" and not state.get("product_match") and not state.get("reply_text"):
        return "compose_reply_fallback"
    return "compose_reply"


def _classify_node_sync(state, llm_client):
    """Sync wrapper for classify_intent (which is sync)."""
    return classify_intent(state, llm_client=llm_client)


def _lookup_node_sync(state, sheets_client):
    """Sync wrapper for lookup_catalog."""
    return lookup_catalog(state, sheets_client=sheets_client)


def _compose_sync(state, llm_client):
    return compose_reply(state, llm_client=llm_client)


def _send_sync(state, gateway_client):
    result = _run_async_from_sync(send_whatsapp(state, gateway_client=gateway_client))
    state.update(result)
    return {}


def _fallback_sync(state, gateway_client):
    result = _run_async_from_sync(fallback_human(state, gateway_client=gateway_client))
    state.update(result)
    return {}


def _compose_fallback_node(state):
    """Compose fallback message (called when lookup returns nothing).

    Sync to match the rest of the graph — langgraph's invoke() rejects async
    nodes unless every node is async.
    """
    return {
        "reply_text": "Sedang kami cek, owner akan follow up ya 🙏",
        "action": "fallback",
        "fallback_reason": (
            "no_faq_match" if state.get("intent") == "faq"
            else "no_product_match" if state.get("intent") == "check_product"
            else "no_match"
        ),
    }


def build_graph(llm_client, sheets_client, gateway_client, checkpointer: Any = None):
    """Construct and compile the StateGraph.

    Args:
        llm_client: LLM client for classification.
        sheets_client: Sheets client for catalog/FAQ lookups.
        gateway_client: Fonnte gateway client for sending WhatsApp messages.
        checkpointer: Optional LangGraph saver for persisting checkpoints (e.g., SqliteCheckpointer).

    Flow:
      START -> classify -> (lookup OR fallback)
             lookup -> (compose OR compose_fallback)
             fallback -> END
             compose -> send -> log -> END
    """
    g = StateGraph(ChatState, checkpointer=checkpointer)

    # Add nodes (all sync — async operations bridge via _run_async_from_sync)
    g.add_node("classify_intent", lambda s: _classify_node_sync(s, llm_client))
    g.add_node("lookup_catalog", lambda s: _lookup_node_sync(s, sheets_client))
    g.add_node("compose_reply", lambda s: _compose_sync(s, llm_client))
    g.add_node("compose_reply_fallback", _compose_fallback_node)
    g.add_node("send_whatsapp", lambda s: _send_sync(s, gateway_client))
    g.add_node("fallback_human", lambda s: _fallback_sync(s, gateway_client))
    g.add_node("write_chat_log", write_chat_log)

    # Edges
    g.add_edge(START, "classify_intent")
    g.add_conditional_edges(
        "classify_intent",
        route_after_classify,
        {"lookup_catalog": "lookup_catalog", "fallback_human": "fallback_human"},
    )
    g.add_conditional_edges(
        "lookup_catalog",
        route_after_lookup,
        {
            "compose_reply": "compose_reply",
            "compose_reply_fallback": "compose_reply_fallback",
        },
    )
    g.add_edge("compose_reply", "send_whatsapp")
    g.add_edge("compose_reply_fallback", "fallback_human")
    g.add_edge("send_whatsapp", "write_chat_log")
    g.add_edge("fallback_human", "write_chat_log")
    g.add_edge("write_chat_log", END)

    return g.compile()


# Create compiled graph at module level for easy injection
_compiled_graph = None


def get_compiled_graph(llm_client=None, sheets_client=None, gateway_client=None):
    """Get the compiled graph (lazy-init). Tests must inject clients."""
    global _compiled_graph
    if _compiled_graph is None:
        if llm_client is None or sheets_client is None or gateway_client is None:
            raise RuntimeError("Clients not injected — call build_graph() explicitly first")
        _compiled_graph = build_graph(llm_client, sheets_client, gateway_client)
    return _compiled_graph


def reset_compiled_graph_for_testing() -> None:
    """Test helper: reset cached compiled graph."""
    global _compiled_graph
    _compiled_graph = None