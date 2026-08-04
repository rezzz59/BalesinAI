"""Tests for FallingBackLLMClient and get_fallback_llm_client factory."""
import pytest

from app.services.llm import (
    FallingBackLLMClient,
    LLMClient,
    LLMError,
    LLMValidationError,
    get_fallback_llm_client,
)


class _OkLLM(LLMClient):
    """Stub that always returns a fixed classification/reply."""

    def __init__(self, label: str = "ok"):
        self._label = label
        self.classify_call_count = 0
        self.compose_call_count = 0

    def classify(self, message):
        self.classify_call_count += 1
        return {
            "intent": "faq",
            "confidence": 0.9,
            "has_complaint_signal": False,
            "sentiment": "neutral",
            "label": self._label,
        }

    def classify_with_history(self, messages):
        self.classify_call_count += 1
        return self.classify(messages[-1]["content"] if messages else "")

    def compose_reply(self, message, retrieved_row, match_kind, customer_context=None, persona=None):
        self.compose_call_count += 1
        return f"reply-from-{self._label}"

    def compose_reply_with_history(self, messages, message, retrieved_row, match_kind, customer_context=None, persona=None):
        self.compose_call_count += 1
        return self.compose_reply(message, retrieved_row, match_kind)


class _FailingLLM(LLMClient):
    """Stub that always raises LLMError."""

    def __init__(self, msg: str = "primary down"):
        self._msg = msg
        self.classify_call_count = 0
        self.compose_call_count = 0

    def classify(self, message):
        self.classify_call_count += 1
        raise LLMError(self._msg)

    def classify_with_history(self, messages):
        self.classify_call_count += 1
        raise LLMError(self._msg)

    def compose_reply(self, message, retrieved_row, match_kind, customer_context=None, persona=None):
        self.compose_call_count += 1
        raise LLMError(self._msg)

    def compose_reply_with_history(self, messages, message, retrieved_row, match_kind, customer_context=None, persona=None):
        self.compose_call_count += 1
        raise LLMError(self._msg)


class _ValidationLLM(LLMClient):
    """Stub that raises LLMValidationError.

    Used to verify that validation errors DO NOT trigger fallback
    (because callers expect to handle them via retry, not failover).
    """

    def __init__(self):
        self.classify_call_count = 0
        self.compose_call_count = 0

    def classify(self, message):
        self.classify_call_count += 1
        raise LLMValidationError("invalid")

    def classify_with_history(self, messages):
        self.classify_call_count += 1
        raise LLMValidationError("invalid")

    def compose_reply(self, message, retrieved_row, match_kind, customer_context=None, persona=None):
        self.compose_call_count += 1
        raise LLMValidationError("invalid")

    def compose_reply_with_history(self, messages, message, retrieved_row, match_kind, customer_context=None, persona=None):
        self.compose_call_count += 1
        raise LLMValidationError("invalid")


def test_classify_first_client_succeeds_no_fallback():
    """When the primary succeeds, no fallback clients should be called."""
    primary = _OkLLM("primary")
    secondary = _OkLLM("secondary")
    chain = FallingBackLLMClient([primary, secondary])

    result = chain.classify("halo")

    assert result["label"] == "primary"
    assert primary.classify_call_count == 1
    assert secondary.classify_call_count == 0


def test_classify_falls_back_when_primary_fails():
    """When primary raises LLMError, the next client is tried."""
    primary = _FailingLLM("primary down")
    secondary = _OkLLM("secondary")
    chain = FallingBackLLMClient([primary, secondary])

    result = chain.classify("halo")

    assert result["label"] == "secondary"
    assert primary.classify_call_count == 1
    assert secondary.classify_call_count == 1


def test_classify_all_clients_fail_raises_last_error():
    """If all clients fail, the last LLMError is re-raised."""
    primary = _FailingLLM("primary down")
    secondary = _FailingLLM("secondary down")
    chain = FallingBackLLMClient([primary, secondary])

    with pytest.raises(LLMError, match="secondary down"):
        chain.classify("halo")

    assert primary.classify_call_count == 1
    assert secondary.classify_call_count == 1


def test_classify_three_clients_first_two_fail_third_succeeds():
    """Three-client chain: first two fail, third succeeds."""
    a = _FailingLLM("a down")
    b = _FailingLLM("b down")
    c = _OkLLM("c")
    chain = FallingBackLLMClient([a, b, c])

    result = chain.classify("halo")
    assert result["label"] == "c"


def test_classify_validation_error_terminates_without_fallback():
    """LLMValidationError does NOT trigger fallback even though LLMClient exists.

    Validation errors are independent from LLMError (they inherit from Exception,
    not LLMError). They are raised when the LLM output violates business rules
    (e.g., contains invented numbers). Retrying with another backend would not
    solve the data validity problem, so fallback is incorrect.

    The FallingBackLLMClient only catches LLMError (infrastructure failures),
    not LLMValidationError.
    """
    primary = _ValidationLLM()
    secondary = _OkLLM("secondary")
    chain = FallingBackLLMClient([primary, secondary])

    # Expect LLMValidationError to propagate immediately without trying secondary
    with pytest.raises(LLMValidationError, match="invalid"):
        chain.classify("halo")

    assert primary.classify_call_count == 1
    assert secondary.classify_call_count == 0  # secondary never called


def test_empty_chain_raises():
    """An empty chain should not be constructable — constructor raises immediately."""
    with pytest.raises(LLMError, match="At least one client"):
        FallingBackLLMClient([])


def test_compose_reply_falls_back_when_primary_fails():
    """compose_reply should also use the fallback chain."""
    primary = _FailingLLM("primary compose down")
    secondary = _OkLLM("secondary")
    chain = FallingBackLLMClient([primary, secondary])

    reply = chain.compose_reply("halo", None, "none")
    assert reply == "reply-from-secondary"


def test_classify_with_history_falls_back():
    primary = _FailingLLM("primary")
    secondary = _OkLLM("secondary")
    chain = FallingBackLLMClient([primary, secondary])

    msgs = [{"role": "user", "content": "halo"}]
    result = chain.classify_with_history(msgs)
    assert result["label"] == "secondary"


def test_compose_reply_with_history_falls_back():
    primary = _FailingLLM("primary")
    secondary = _OkLLM("secondary")
    chain = FallingBackLLMClient([primary, secondary])

    msgs = [{"role": "user", "content": "halo"}]
    reply = chain.compose_reply_with_history(msgs, "halo", None, "none")
    assert reply == "reply-from-secondary"


# --- get_fallback_llm_client factory tests ---


def test_get_fallback_llm_client_with_valid_backends(monkeypatch):
    """Factory should build a chain with the configured backends."""
    from app.config import get_settings

    s = get_settings()
    if not s.adacode_api_key:
        monkeypatch.setenv("ADACODE_API_KEY", "test-adacode-key")
    if not s.gemini_api_key:
        monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    chain = get_fallback_llm_client(["adacode", "gemini"])
    assert isinstance(chain, FallingBackLLMClient)
    assert len(chain._clients) == 2


def test_get_fallback_llm_client_missing_credentials_fallback():
    """Factory falls back to MockLLMClient when credentials are missing."""
    import os

    saved_keys = {}
    for key in ("ADACODE_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        saved_keys[key] = os.environ.get(key)
        os.environ[key] = ""  # empty string beats .env in pydantic-settings priority

    try:
        from app.config import get_settings
        get_settings.cache_clear()
        client = get_fallback_llm_client(["adacode"])
        from app.services.llm import MockLLMClient
        assert isinstance(client, MockLLMClient)
    finally:
        for key, val in saved_keys.items():
            if val is not None:
                os.environ[key] = val
            else:
                os.environ.pop(key, None)
        from app.config import get_settings
        get_settings.cache_clear()


def test_get_fallback_llm_client_unknown_backend_fallback():
    """Factory falls back to MockLLMClient on unknown backend name."""
    client = get_fallback_llm_client(["unknown_provider"])
    from app.services.llm import MockLLMClient
    assert isinstance(client, MockLLMClient)


def test_get_fallback_llm_client_empty_list_fallback(monkeypatch):
    """Factory falls back to MockLLMClient if no backends are provided."""
    import os
    monkeypatch.setenv("ADACODE_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    from app.config import get_settings
    get_settings.cache_clear()
    client = get_fallback_llm_client([])
    from app.services.llm import MockLLMClient
    assert isinstance(client, MockLLMClient)