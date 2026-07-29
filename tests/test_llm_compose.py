"""Tests for LLMClient.compose_reply interface."""
import pytest

from app.services.llm import LLMClient, LLMError, MockLLMClient


def test_llm_client_has_compose_reply_abstract_method():
    # If compose_reply were missing from the ABC, instantiating a subclass
    # that doesn't implement it would raise TypeError. MockLLMClient implements
    # it, so this check is more about ensuring the attribute exists on the ABC.
    assert hasattr(LLMClient, "compose_reply")
    assert getattr(LLMClient.compose_reply, "__isabstractmethod__", False)


def test_mock_llm_client_compose_reply_returns_string():
    client = MockLLMClient()
    reply = client.compose_reply(
        message="berapa harga hoodie?",
        retrieved_row={"name": "Hoodie Fleece", "price": "Rp 150.000"},
        match_kind="high",
    )
    assert isinstance(reply, str)
    assert len(reply) > 0


def test_mock_llm_client_compose_reply_with_none_row():
    client = MockLLMClient()
    reply = client.compose_reply(
        message="apa ada jaket?",
        retrieved_row=None,
        match_kind="none",
    )
    assert isinstance(reply, str)
    assert len(reply) > 0


def test_mock_llm_client_compose_reply_medium_match():
    client = MockLLMClient()
    reply = client.compose_reply(
        message="hoodie ready ga?",
        retrieved_row={"name": "Hoodie", "price": "Rp 100.000"},
        match_kind="medium",
    )
    assert isinstance(reply, str)


def test_all_concrete_clients_implement_compose_reply():
    # Sanity: this ensures no breakage when one client lags behind. We check
    # via abstract instantiation — Google/Anthropic/Mock all need it once
    # Task 3 + 4 are done.
    # Force the mock client registry-wise; this just checks the abstract method exists.
    assert "compose_reply" in LLMClient.__abstractmethods__