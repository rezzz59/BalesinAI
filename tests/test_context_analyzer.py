"""Tests for analyze_customer_context node (B1)."""
import json
from unittest.mock import MagicMock

from app.graph.context_analyzer import analyze_customer_context


class FakeLLM:
    def __init__(self, response_text):
        self.response_text = response_text

    def classify_with_history(self, messages):
        return {"text": self.response_text}


def test_analyzer_maps_description_to_conditions():
    """Basic mapping from policy description to customer conditions."""
    state = {
        "tenant_id": "default",
        "message_text": "produk saya ada lubang di leher padahal baru sampe",
        "intent": "faq",
        "policy_rows": [
            {"rule_key": "return_eligible",
             "description": "Bisa return kalau rusak dan belum dicuci",
             "conditions": ["rusak", "belum_dicuci"]}
        ],
    }
    response_json = json.dumps({
        "mapped_conditions": ["rusak", "belum_dicuci"],
        "issue_type": "product_damage",
        "primary_intent": "return_query",
        "confidence": 0.85,
        "reasoning": "lubang di leher = rusak, baru sampe = belum dicusi"
    })
    llm = FakeLLM(response_json)
    result = analyze_customer_context(state, llm)
    assert result["customer_context"]["mapped_conditions"] == ["rusak", "belum_dicuci"]
    assert result["customer_context"]["issue_type"] == "product_damage"


def test_analyzer_handles_no_policy_gracefully():
    """When no policies, returns sensible defaults."""
    state = {
        "tenant_id": "default",
        "message_text": "halo",
        "intent": "unclear",
        "policy_rows": [],
    }
    response_json = json.dumps({
        "mapped_conditions": [],
        "issue_type": "none",
        "primary_intent": "greeting",
        "confidence": 0.6,
        "reasoning": "Generic greeting, no policy mapping needed"
    })
    llm = FakeLLM(response_json)
    result = analyze_customer_context(state, llm)
    assert result["customer_context"]["confidence"] >= 0.5


def test_analyzer_with_catalog_answer():
    """Catalog info is included in context."""
    state = {
        "tenant_id": "default",
        "message_text": "saya mau hoodie yang hangat",
        "intent": "check_product",
        "catalog_answer": [{"name": "Hoodie Fleece", "desc": "Bahan bulu tebal untuk cuaca dingin"}],
        "policy_rows": [],
    }
    response_json = json.dumps({
        "mapped_conditions": ["hangat"],
        "issue_type": "none",
        "primary_intent": "check_product",
        "confidence": 0.7,
        "reasoning": "Pelanggan mencari produk hangat"
    })
    llm = FakeLLM(response_json)
    result = analyze_customer_context(state, llm)
    assert result["customer_context"]["primary_intent"] == "check_product"


def test_analyzer_returns_default_on_empty_mapping():
    """When JSON missing required fields, fallback to safe defaults."""
    state = {
        "tenant_id": "default",
        "message_text": "masalah apa pun",
        "intent": "complaint",
        "policy_rows": [],
    }
    # Return incomplete JSON
    response_json = '{"some": "invalid"}'
    llm = FakeLLM(response_json)
    result = analyze_customer_context(state, llm)
    # Should have fallback defaults
    assert "mapped_conditions" in result["customer_context"]
    assert result["customer_context"]["confidence"] == 0.5


def test_analyzer_on_llm_error():
    """LLMError is caught and handled gracefully."""
    from app.services.llm import LLMError
    state = {
        "tenant_id": "default",
        "message_text": "error testing",
        "intent": "faq",
        "policy_rows": [],
    }
    class ErrorLLM:
        def classify_with_history(self, messages):
            raise LLMError("Service unavailable")
    llm = ErrorLLM()
    result = analyze_customer_context(state, llm)
    assert result["customer_context"]["issue_type"] == "none"
    assert result["customer_context"]["confidence"] == 0.3