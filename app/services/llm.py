"""Abstract LLM client interface and provider implementations."""
import abc
import json
import logging
from typing import Any, TypeAlias

from app.graph.prompts import INTENT_CLASSIFICATION_SYSTEM, INTENT_CLASSIFICATION_USER

logger = logging.getLogger(__name__)

VALID_INTENTS = {"faq", "check_product", "confirm_order", "unclear"}
ClassificationResult: TypeAlias = dict[str, Any]  # {"intent": str, "confidence": float}


class LLMError(Exception):
    """Raised when LLM call fails or returns invalid output."""


class LLMClient(metaclass=abc.ABCMeta):
    """Abstract base class for intent classification clients."""

    @abc.abstractmethod
    def classify(self, message: str) -> ClassificationResult:
        """Classify user message intent. Returns {intent, confidence}.

        Raises LLMError if API fails or response is invalid.
        """
        pass


# Attempt to import Anthropic SDK; optional - required only if using Anthropic backend
try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment,misc]


class AnthropicLLMClient(LLMClient):
    """Wraps Anthropic SDK for Claude Haiku intent classification."""

    MODEL = "claude-haiku-4-5"

    def __init__(self, api_key: str):
        if anthropic is None:
            raise LLMError("Anthropic SDK is not installed. Install 'anthropic' package to use this backend.")
        self._client = anthropic.Anthropic(api_key=api_key)

    def classify(self, message: str) -> ClassificationResult:
        """Classify user message intent."""
        try:
            response = self._client.messages.create(
                model=self.MODEL,
                max_tokens=128,
                system=INTENT_CLASSIFICATION_SYSTEM,
                messages=[
                    {
                        "role": "user",
                        "content": INTENT_CLASSIFICATION_USER.format(message=message),
                    }
                ],
            )

            text_block = next(
                (b for b in response.content if b.type == "text"),
                None,
            )
            if text_block is None:
                raise LLMError("No text block in response")

            result = json.loads(text_block.text)

            intent = result.get("intent")
            confidence = result.get("confidence")

            if intent not in VALID_INTENTS:
                raise LLMError(f"Invalid intent from LLM: {intent}")
            if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
                raise LLMError(f"Invalid confidence from LLM: {confidence}")

            return {"intent": intent, "confidence": float(confidence)}

        except json.JSONDecodeError as e:
            raise LLMError(f"Invalid JSON from LLM: {e}") from e


class GeminiLLMClient(LLMClient):
    """Wraps the new google-genai SDK for Gemini intent classification.

    Uses the free-tier friendly model `gemini-2.0-flash-lite` by default.
    """

    MODEL = "gemini-2.0-flash-lite"

    def __init__(self, api_key: str):
        import google.genai as genai  # noqa: E402 (lazy import; only needed when used)

        self._client = genai.Client(api_key=api_key)

    def classify(self, message: str) -> ClassificationResult:
        """Classify user message intent using Gemini API."""
        try:
            from google.genai import types as genai_types

            response = self._client.models.generate_content(
                model=self.MODEL,
                contents=[
                    INTENT_CLASSIFICATION_SYSTEM
                    + "\n\n"
                    + INTENT_CLASSIFICATION_USER.format(message=message)
                ],
                config=genai_types.GenerateContentConfig(
                    temperature=0,
                    max_output_tokens=128,
                    response_mime_type="application/json",
                    response_schema={
                        "type": "OBJECT",
                        "properties": {
                            "intent": {
                                "type": "STRING",
                                "enum": ["faq", "check_product", "confirm_order", "unclear"],
                            },
                            "confidence": {"type": "NUMBER"},
                        },
                        "required": ["intent", "confidence"],
                    },
                ),
            )

            text = (response.text or "").strip()
            if not text:
                raise LLMError("Empty response from Gemini")

            result = json.loads(text)
            intent = result.get("intent")
            confidence = result.get("confidence")

            if intent not in VALID_INTENTS:
                raise LLMError(f"Invalid intent from LLM: {intent}")
            if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
                raise LLMError(f"Invalid confidence from LLM: {confidence}")

            return {"intent": intent, "confidence": float(confidence)}

        except json.JSONDecodeError as e:
            raise LLMError(f"Invalid JSON from Gemini: {e}") from e
        except Exception as e:  # noqa: BLE001
            logger.error("gemini_call_failed", error=str(e))
            raise LLMError(f"Gemini API error: {e}") from e


def get_llm_client() -> LLMClient:
    """Factory function that creates the appropriate LLM client based on LLM_BACKEND env var.

    Supported backends: "anthropic", "gemini". Default: "gemini".

    Raises LLMError if backend unknown or missing credentials.
    """
    from app.config import get_settings

    settings = get_settings()
    backend = settings.llm_backend.lower() if settings.llm_backend else "gemini"

    if backend == "anthropic":
        if not settings.anthropic_api_key:
            raise LLMError("ANTHROPIC_API_KEY not set for anthropic backend")
        return AnthropicLLMClient(api_key=settings.anthropic_api_key)

    elif backend == "gemini":
        if not settings.gemini_api_key:
            raise LLMError("GEMINI_API_KEY not set for gemini backend")
        return GeminiLLMClient(api_key=settings.gemini_api_key)

    else:
        raise LLMError(
            f"unknown LLM backend: {backend}. Choose 'anthropic' or 'gemini'"
        )


__all__ = [
    "LLMError",
    "LLMClient",
    "AnthropicLLMClient",
    "GeminiLLMClient",
    "get_llm_client",
]
