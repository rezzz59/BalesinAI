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
    fallback_reason_for,
    lookup_catalog,
    send_whatsapp,
    write_chat_log,
)
from app.graph.context_analyzer import analyze_customer_context
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
    """Decide whether to route to fallback based on confidence, intent & complaint signal."""
    if threshold is None:
        threshold = get_settings().intent_confidence_threshold

    if state.get("has_complaint_signal"):
        return True
    if state.get("intent") == "unclear":
        return True
    if state.get("confidence", 0.0) < threshold:
        return True
    return False


def route_after_classify(state: ChatState) -> str:
    """Route after classify_intent node. Sets fallback_reason if routing to fallback."""
    if should_fallback(state):
        # Populate fallback_reason so fallback_human sees it.
        # We mutate state via a no-op return — langgraph's conditional edge
        # can't update state, so fallback_human computes it itself.
        return "fallback_human"
    return "lookup_catalog"


def route_after_lookup(state: ChatState) -> str:
    """Route after lookup_catalog node. Fallback if lookup returned nothing for faq/product."""
    intent = state.get("intent")
    if intent == "faq" and not state.get("catalog_answer"):
        return "compose_reply_fallback"
    if intent == "check_product" and not state.get("product_match") and not state.get("reply_text"):
        return "compose_reply_fallback"
    return "analyze_customer_context"


def _classify_node_sync(state, llm_client):
    """Sync wrapper for classify_intent (which is sync)."""
    return classify_intent(state, llm_client=llm_client)


def _lookup_node_sync(state, sheets_client):
    """Sync wrapper for lookup_catalog."""
    from app.services.semantic_search import SemanticSearchClient
    semantic_client = SemanticSearchClient.from_defaults()
    return lookup_catalog(
        state, sheets_client=sheets_client, semantic_search_client=semantic_client
    )


def _compose_sync(state, llm_client):
    return compose_reply(state, llm_client=llm_client)


def _send_sync(state, gateway_client):
    """Sync wrapper for send_whatsapp. Returns update dict so LangGraph merges it."""
    return _run_async_from_sync(send_whatsapp(state, gateway_client=gateway_client))


def _fallback_sync(state, gateway_client):
    """Sync wrapper for fallback_human. Returns the update dict so LangGraph merges it."""
    return _run_async_from_sync(fallback_human(state, gateway_client=gateway_client))


def _analyze_customer_context_sync(state, llm_client):
    """Sync wrapper for analyze_customer_context."""
    from app.graph.context_analyzer import analyze_customer_context
    return analyze_customer_context(state, llm_client=llm_client)


def _compose_fallback_node(state):
    """Compose fallback message (called when lookup returns nothing).

    Sync to match the rest of the graph — langgraph's invoke() rejects async
    nodes unless every node is async.
    """
    reason = fallback_reason_for(state) or "no_match"
    return {
        "reply_text": "Sedang kami cek, owner akan follow up ya 🙏",
        "action": "fallback",
        "fallback_reason": reason,
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
             lookup -> analyze_context -> compose
             fallback -> END (with write_log)
             compose -> send -> log -> END
    """
    g = StateGraph(ChatState, checkpointer=checkpointer)

    # Add nodes (all sync — async operations bridge via _run_async_from_sync)
    g.add_node("classify_intent", lambda s: _classify_node_sync(s, llm_client))
    g.add_node("lookup_catalog", lambda s: _lookup_node_sync(s, sheets_client))
    g.add_node("analyze_customer_context", lambda s: _analyze_customer_context_sync(s, llm_client))
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
            "analyze_customer_context": "analyze_customer_context",
            "compose_reply_fallback": "compose_reply_fallback",
        },
    )
    g.add_edge("analyze_customer_context", "compose_reply")
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