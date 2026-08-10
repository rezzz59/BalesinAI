"""Tests for app.services.llm."""
import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.llm import AnthropicLLMClient, LLMError


def _make_mock_response(intent: str, confidence: float, is_valid_json: bool = True) -> MagicMock:
    """Create a mock response object with the given JSON content or invalid text."""
    if is_valid_json:
        text = json.dumps({"intent": intent, "confidence": confidence})
    else:
        text = "not json"
    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="text", text=text)]
    return mock_response


def test_classify_returns_intent_and_confidence():
    """Successful classification returns intent and confidence."""
    mock_response = _make_mock_response("faq", 0.85)

    with patch("anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_cls.return_value = mock_client

        client = AnthropicLLMClient(api_key="test-key")
        result = client.classify("Berapa harga kaos?")

        assert result["intent"] == "faq"
        assert result["confidence"] == 0.85


def test_classify_parses_has_complaint_signal():
    """Classification JSON must carry has_complaint_signal into the result."""
    text = json.dumps({
        "intent": "unclear",
        "confidence": 0.6,
        "has_complaint_signal": True,
        "sentiment": "negative",
    })
    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="text", text=text)]

    with patch("anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_cls.return_value = mock_client

        client = AnthropicLLMClient(api_key="test-key")
        result = client.classify("barang rusak, mau refund dong")

        assert result["has_complaint_signal"] is True
        assert result["sentiment"] == "negative"


def test_classify_defaults_complaint_signal_false():
    """Missing has_complaint_signal in JSON defaults to False."""
    mock_response = _make_mock_response("faq", 0.85)

    with patch("anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_cls.return_value = mock_client

        client = AnthropicLLMClient(api_key="test-key")
        result = client.classify("Berapa harga kaos?")

        assert result["has_complaint_signal"] is False


def test_classify_handles_invalid_json():
    """If LLM returns non-JSON, raise LLMError."""
    mock_response = _make_mock_response("", 0.0, is_valid_json=False)

    with patch("anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_cls.return_value = mock_client

        client = AnthropicLLMClient(api_key="test-key")
        with pytest.raises(LLMError):
            client.classify("test")


def test_classify_validates_intent_values():
    """Validation rejects invalid intents and out-of-range confidence."""
    mock_response = _make_mock_response("invalid_intent", 0.5)

    with patch("anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_cls.return_value = mock_client

        client = AnthropicLLMClient(api_key="test-key")
        with pytest.raises(LLMError, match="Invalid intent"):
            client.classify("test")