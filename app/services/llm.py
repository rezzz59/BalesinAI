"""Abstract LLM client interface and provider implementations."""
import abc
import json
import logging
import re
import httpx
from typing import Any, TypeAlias

from app.graph.prompts import (
    COMPOSE_NOMATCH_SYSTEM,
    COMPOSE_PARTIAL_SYSTEM,
    COMPOSE_STRICT_SYSTEM,
    COMPOSE_USER_TEMPLATE,
    INTENT_CLASSIFICATION_SYSTEM,
    INTENT_CLASSIFICATION_USER,
)

logger = logging.getLogger(__name__)

VALID_INTENTS = {"faq", "check_product", "confirm_order", "unclear"}
VALID_SENTIMENTS = {"positive", "neutral", "negative"}
ClassificationResult: TypeAlias = dict[str, Any]
# Keys: intent (str), confidence (float), has_complaint_signal (bool), sentiment (str)


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

    @abc.abstractmethod
    def classify_with_history(self, messages: list[dict[str, str]]) -> ClassificationResult:
        """Classify user message intent using full conversation history.

        Supports multi-turn context by providing role-based message history.

        Args:
          messages: list of {"role": "user"|"assistant", "content": str}

        Raises LLMError if API fails or response is invalid.
        """
        pass

    @abc.abstractmethod
    def compose_reply(
        self,
        message: str,
        retrieved_row: dict | None,
        match_kind: str,
        customer_context: dict | None = None,
    ) -> str:
        """Compose natural Indonesian reply grounded in retrieved_row (if any).

        Args:
          message: the buyer's WhatsApp message.
          retrieved_row: matched FAQ or product row, or None.
          match_kind: 'high' | 'medium' | 'none'.
          customer_context: optional dict from analyze_customer_context with
            mapped_conditions, issue_type, primary_intent, confidence, reasoning.

        Returns the composed reply text. May raise LLMError.
        """
        pass

    @abc.abstractmethod
    def compose_reply_with_history(
        self,
        messages: list[dict[str, str]],
        message: str,
        retrieved_row: dict | None,
        match_kind: str,
        customer_context: dict | None = None,
    ) -> str:
        """Compose reply with full conversation history.

        Supports multi-turn context so assistant replies can reference prior
        exchange. The messages list includes all previous turns; the latest
        `message` is the current user input to be answered.

        Args:
          messages: full conversation history [{"role": "...", "content": "..."}, ...]
          message: current buyer message being processed
          retrieved_row: matched FAQ or product row, or None
          match_kind: 'high' | 'medium' | 'none' — contextual quality hint
          customer_context: optional dict from analyze_customer_context with
            mapped_conditions, issue_type, primary_intent, confidence, reasoning

        Returns the composed reply text. May raise LLMError.
        """
        pass


class MockLLMClient(LLMClient):
    """Deterministic classifier for local dev / testing / when SDK missing.

    Uses simple keyword heuristics — no external API call. Never raises.
    """

    def classify(self, message: str) -> ClassificationResult:
        msg = (message or "").lower()
        has_complaint_signal = any(
            kw in msg
            for kw in ("kecewa", "rusak", "refund", "balik", "gak sampai", "ga做起",
                       "lama", "kapan sampainya", "komplain", "jelek", "batal")
        )
        sentiment = "negative" if has_complaint_signal else "neutral"
        if any(kw in msg for kw in ("stok", "ready", "ada ga", "ada nggak", "ready stock", "tersedia")):
            return {"intent": "check_product", "confidence": 0.95, "has_complaint_signal": has_complaint_signal, "sentiment": sentiment}
        if any(kw in msg for kw in ("order", "pesan", "beli", "booking", "checkout")):
            return {"intent": "confirm_order", "confidence": 0.92, "has_complaint_signal": has_complaint_signal, "sentiment": sentiment}
        if any(kw in msg for kw in ("?", "apa", "bagaimana", "kapan", "dimana", "gimana")):
            return {"intent": "faq", "confidence": 0.8, "has_complaint_signal": has_complaint_signal, "sentiment": sentiment}
        return {"intent": "unclear", "confidence": 0.4, "has_complaint_signal": has_complaint_signal, "sentiment": sentiment}

    def classify_with_history(self, messages: list[dict[str, str]]) -> ClassificationResult:
        """Multi-turn aware classification using latest user message."""
        if not messages:
            return self.classify("")
        for m in messages:
            if m.get("role") == "user":
                return self.classify(m["content"])
        return self.classify("")

    def compose_reply(
        self,
        message: str,
        retrieved_row: dict | None,
        match_kind: str,
        customer_context: dict | None = None,
    ) -> str:
        """Compose a single-reply message using retrieved facts."""
        return self.compose_reply_with_history(
            messages=[],  # No history for direct compose call
            message=message,
            retrieved_row=retrieved_row,
            match_kind=match_kind,
            customer_context=customer_context,
        )

    def compose_reply_with_history(
        self,
        messages: list[dict[str, str]],
        message: str,
        retrieved_row: dict | None,
        match_kind: str,
        customer_context: dict | None = None,
    ) -> str:
        """Compose reply grounded in retrieved_row while preserving multi-turn history."""
        if retrieved_row:
            parts = [str(v) for v in retrieved_row.values() if v is not None]
            base_reply = " ".join(parts) if parts else "Mohon maaf, produk belum tersedia."
        else:
            base_reply = "Mohon maaf, produk belum tersedia."

        history_parts = [m["content"] for m in messages if m.get("role") == "user"]
        if history_parts:
            context = " | ".join(history_parts)
            prefix = f"{context}: "
        else:
            prefix = ""

        # Incorporate customer context for context-aware reply
        if customer_context:
            issue_type = customer_context.get("issue_type", "none")
            if issue_type != "none":
                base_reply = f"[{issue_type}] {base_reply}"

        return f"{prefix}{base_reply}"


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
            has_complaint_signal = result.get("has_complaint_signal", False)
            sentiment = result.get("sentiment", "neutral")

            if intent not in VALID_INTENTS:
                raise LLMError(f"Invalid intent from LLM: {intent}")
            if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
                raise LLMError(f"Invalid confidence from LLM: {confidence}")
            if not isinstance(has_complaint_signal, bool):
                raise LLMError(f"Invalid has_complaint_signal from LLM: {has_complaint_signal}")
            if sentiment not in VALID_SENTIMENTS:
                raise LLMError(f"Invalid sentiment from LLM: {sentiment}")

            return {
                "intent": intent,
                "confidence": float(confidence),
                "has_complaint_signal": has_complaint_signal,
                "sentiment": sentiment,
            }

        except json.JSONDecodeError as e:
            raise LLMError(f"Invalid JSON from LLM: {e}") from e
        except Exception as e:
            logger.exception("anthropic_classify failed: %s", e)
            raise LLMError(f"Anthropic API error: {e}") from e

    def classify_with_history(self, messages: list[dict[str, str]]) -> ClassificationResult:
        """Multi-turn aware classification using conversation history."""
        from app.graph.prompts import INTENT_CLASSIFICATION_SYSTEM, INTENT_CLASSIFICATION_USER
        latest_user_content = ""
        for m in messages:
            if m.get("role") == "user":
                latest_user_content = m["content"]
        if not latest_user_content:
            return self.classify("")

        system_message = INTENT_CLASSIFICATION_SYSTEM + "\n\n" + INTENT_CLASSIFICATION_USER.format(message=latest_user_content)

        try:
            response = self._client.messages.create(
                model=self.MODEL,
                max_tokens=128,
                system=system_message,
                messages=[{"role": "user", "content": latest_user_content}],
            )
            text_block = next((b for b in response.content if b.type == "text"), None)
            if text_block is None:
                raise LLMError("No text block in response")
            result = json.loads(text_block.text)

            intent = result.get("intent")
            confidence = result.get("confidence")
            has_complaint_signal = result.get("has_complaint_signal", False)
            sentiment = result.get("sentiment", "neutral")

            if intent not in VALID_INTENTS:
                raise LLMError(f"Invalid intent from LLM: {intent}")
            if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
                raise LLMError(f"Invalid confidence from LLM: {confidence}")
            if not isinstance(has_complaint_signal, bool):
                raise LLMError(f"Invalid has_complaint_signal from LLM: {has_complaint_signal}")
            if sentiment not in VALID_SENTIMENTS:
                raise LLMError(f"Invalid sentiment from LLM: {sentiment}")

            return {
                "intent": intent,
                "confidence": float(confidence),
                "has_complaint_signal": has_complaint_signal,
                "sentiment": sentiment,
            }

        except json.JSONDecodeError as e:
            raise LLMError(f"Invalid JSON from LLM: {e}") from e
        except Exception as e:
            logger.exception("anthropic_classify_with_history failed: %s", e)
            raise LLMError(f"Anthropic API error: {e}") from e

    def compose_reply(
        self,
        message: str,
        retrieved_row: dict | None,
        match_kind: str,
        customer_context: dict | None = None,
    ) -> str:
        """Compose natural Indonesian reply grounded in retrieved_row."""
        if match_kind == "none":
            system = COMPOSE_NOMATCH_SYSTEM
        elif match_kind == "medium":
            system = COMPOSE_PARTIAL_SYSTEM
        else:
            system = COMPOSE_STRICT_SYSTEM

        if retrieved_row:
            source_str = " | ".join(f"{k}: {v}" for k, v in retrieved_row.items() if v is not None)
        else:
            source_str = "(tidak ada data yang cocok di katalog)"

        user_content = COMPOSE_USER_TEMPLATE.format(message=message, source_row=source_str, match_kind=match_kind, customer_context=customer_context)

        try:
            response = self._client.messages.create(
                model=self.MODEL,
                max_tokens=512,
                system=system,
                messages=[{"role": "user", "content": user_content}],
            )
            text_block = next((b for b in response.content if b.type == "text"), None)
            if text_block is None:
                raise LLMError("No text block in compose response")
            return text_block.text.strip()
        except Exception as e:
            raise LLMError(f"Anthropic compose failed: {e}") from e

    def compose_reply_with_history(
        self,
        messages: list[dict[str, str]],
        message: str,
        retrieved_row: dict | None,
        match_kind: str,
        customer_context: dict | None = None,
    ) -> str:
        """Compose reply with full conversation history."""
        if match_kind == "none":
            system = COMPOSE_NOMATCH_SYSTEM
        elif match_kind == "medium":
            system = COMPOSE_PARTIAL_SYSTEM
        else:
            system = COMPOSE_STRICT_SYSTEM

        if retrieved_row:
            source_str = " | ".join(
                f"{k}: {v}" for k, v in retrieved_row.items() if v is not None
            )
        else:
            source_str = "(tidak ada data yang cocok di katalog)"

        user = COMPOSE_USER_TEMPLATE.format(
            message=message,
            source_row=source_str,
            match_kind=match_kind,
            customer_context=customer_context,
        )

        try:
            response = self._client.messages.create(
                model=self.MODEL,
                max_tokens=512,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            text_block = next(
                (b for b in response.content if b.type == "text"),
                None,
            )
            if text_block is None:
                raise LLMError("No text block in compose response")
            return text_block.text.strip()
        except Exception as e:  # noqa: BLE001
            raise LLMError(f"Anthropic compose failed: {e}") from e


class GeminiLLMClient(LLMClient):
    """Wraps the new google-genai SDK for Gemini intent classification.

    Uses a readily available model that works with the free tier.
    To change the model, edit the MODEL constant or pass via env var.
    """

    MODEL = "gemini-3.1-flash-lite"

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
                            "has_complaint_signal": {"type": "BOOLEAN"},
                            "sentiment": {
                                "type": "STRING",
                                "enum": ["positive", "neutral", "negative"],
                            },
                        },
                        "required": ["intent", "confidence", "has_complaint_signal", "sentiment"],
                    },
                ),
            )

            text = (response.text or "").strip()
            logger.warning(f"DEBUG_GEMINI_RESPONSE: {text!r}")  # TEMP DEBUG
            if not text:
                raise LLMError("Empty response from Gemini")

            result = json.loads(text)
            intent = result.get("intent")
            confidence = result.get("confidence")
            has_complaint_signal = result.get("has_complaint_signal", False)
            sentiment = result.get("sentiment", "neutral")

            if intent not in VALID_INTENTS:
                raise LLMError(f"Invalid intent from LLM: {intent}")
            if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
                raise LLMError(f"Invalid confidence from LLM: {confidence}")
            if not isinstance(has_complaint_signal, bool):
                raise LLMError(f"Invalid has_complaint_signal from LLM: {has_complaint_signal}")
            if sentiment not in VALID_SENTIMENTS:
                raise LLMError(f"Invalid sentiment from LLM: {sentiment}")

            return {
                "intent": intent,
                "confidence": float(confidence),
                "has_complaint_signal": has_complaint_signal,
                "sentiment": sentiment,
            }

        except json.JSONDecodeError as e:
            raise LLMError(f"Invalid JSON from Gemini: {e}") from e
        except Exception as e:  # noqa: BLE001
            logger.exception("gemini_call_failed: %s", e)
            raise LLMError(f"Gemini API error: {e}") from e

    def classify_with_history(self, messages: list[dict[str, str]]) -> ClassificationResult:
        """Multi-turn aware classification using conversation history."""
        from google.genai import types as genai_types
        latest_user_content = ""
        for m in messages:
            if m.get("role") == "user":
                latest_user_content = m["content"]
        if not latest_user_content:
            return self.classify("")

        prompt = INTENT_CLASSIFICATION_SYSTEM + "\n\n" + INTENT_CLASSIFICATION_USER.format(message=latest_user_content)

        try:
            response = self._client.models.generate_content(
                model=self.MODEL,
                contents=[prompt],
                config=genai_types.GenerateContentConfig(
                    temperature=0,
                    max_output_tokens=128,
                    response_mime_type="application/json",
                    response_schema={
                        "type": "OBJECT",
                        "properties": {
                            "intent": {"type": "STRING", "enum": ["faq", "check_product", "confirm_order", "unclear"]},
                            "confidence": {"type": "NUMBER"},
                            "has_complaint_signal": {"type": "BOOLEAN"},
                            "sentiment": {"type": "STRING", "enum": ["positive", "neutral", "negative"]},
                        },
                        "required": ["intent", "confidence", "has_complaint_signal", "sentiment"],
                    },
                ),
            )
            text = (response.text or "").strip()
            logger.warning(f"DEBUG_GEMINI_RESPONSE: {text!r}")  # TEMP DEBUG
            if not text:
                raise LLMError("Empty response from Gemini")
            result = json.loads(text)
            intent = result.get("intent")
            confidence = result.get("confidence")
            has_complaint_signal = result.get("has_complaint_signal", False)
            sentiment = result.get("sentiment", "neutral")

            if intent not in VALID_INTENTS:
                raise LLMError(f"Invalid intent from Gemini: {intent}")
            if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
                raise LLMError(f"Invalid confidence from Gemini: {confidence}")
            if not isinstance(has_complaint_signal, bool):
                raise LLMError(f"Invalid has_complaint_signal from Gemini: {has_complaint_signal}")
            if sentiment not in VALID_SENTIMENTS:
                raise LLMError(f"Invalid sentiment from Gemini: {sentiment}")

            return {
                "intent": intent,
                "confidence": float(confidence),
                "has_complaint_signal": has_complaint_signal,
                "sentiment": sentiment,
            }

        except json.JSONDecodeError as e:
            raise LLMError(f"Invalid JSON from Gemini: {e}") from e
        except Exception as e:
            logger.exception("gemini_classify_with_history failed: %s", e)
            raise LLMError(f"Gemini API error: {e}") from e

    def compose_reply(
        self,
        message: str,
        retrieved_row: dict | None,
        match_kind: str,
        customer_context: dict | None = None,
    ) -> str:
        """Compose natural Indonesian reply grounded in retrieved_row."""
        if match_kind == "none":
            system = COMPOSE_NOMATCH_SYSTEM
        elif match_kind == "medium":
            system = COMPOSE_PARTIAL_SYSTEM
        else:
            system = COMPOSE_STRICT_SYSTEM

        if retrieved_row:
            source_str = " | ".join(f"{k}: {v}" for k, v in retrieved_row.items() if v is not None)
        else:
            source_str = "(tidak ada data yang cocok di katalog)"

        user_content = COMPOSE_USER_TEMPLATE.format(message=message, source_row=source_str, match_kind=match_kind, customer_context=customer_context)

        try:
            from google.genai import types as genai_types

            response = self._client.models.generate_content(
                model=self.MODEL,
                contents=[system + "\n\n" + user_content],
                config=genai_types.GenerateContentConfig(
                    temperature=0.4,
                    max_output_tokens=512,
                ),
            )
            text = (response.text or "").strip()
            if not text:
                raise LLMError("Empty compose response from Gemini")
            return text
        except Exception as e:
            raise LLMError(f"Gemini compose failed: {e}") from e

    def compose_reply_with_history(
        self,
        messages: list[dict[str, str]],
        message: str,
        retrieved_row: dict | None,
        match_kind: str,
        customer_context: dict | None = None,
    ) -> str:
        """Compose reply with full conversation history."""
        if match_kind == "none":
            system = COMPOSE_NOMATCH_SYSTEM
        elif match_kind == "medium":
            system = COMPOSE_PARTIAL_SYSTEM
        else:
            system = COMPOSE_STRICT_SYSTEM

        if retrieved_row:
            source_str = " | ".join(
                f"{k}: {v}" for k, v in retrieved_row.items() if v is not None
            )
        else:
            source_str = "(tidak ada data yang cocok di katalog)"

        user = COMPOSE_USER_TEMPLATE.format(
            message=message,
            source_row=source_str,
            match_kind=match_kind,
            customer_context=customer_context,
        )

        try:
            from google.genai import types as genai_types

            response = self._client.models.generate_content(
                model=self.MODEL,
                contents=[system + "\n\n" + user],
                config=genai_types.GenerateContentConfig(
                    temperature=0.4,
                    max_output_tokens=512,
                ),
            )
            text = (response.text or "").strip()
            if not text:
                raise LLMError("Empty compose response from Gemini")
            return text
        except Exception as e:  # noqa: BLE001
            raise LLMError(f"Gemini compose failed: {e}") from e


class AdaCodeLLMClient(LLMClient):
    """Wraps OpenAI-compatible API (adaCODE platform) for intent classification and reply composition.

    Uses the /v1/chat/completions endpoint with Bearer token authentication.
    """

    def __init__(self, api_key: str, base_url: str | None = None, model: str | None = None):
        self.api_key = api_key
        self.base_url = base_url or "https://api.adacode.ai"
        self.model = model or "claude-sonnet-4-6"

    def _call_completion(self, messages: list[dict[str, str]], max_tokens: int = 128) -> dict:
        """Make a chat completion request to AdaCode API."""
        try:
            import httpx
            response = httpx.post(
                f"{self.base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": 0,
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return data
        except httpx.RequestError as e:
            raise LLMError(f"AdaCode network error: {e}") from e
        except httpx.HTTPStatusError as e:
            raise LLMError(f"AdaCode HTTP error: {e.response.status_code} - {e.response.text[:200]}") from e
        except Exception as e:
            raise LLMError(f"AdaCode API error: {e}") from e

    def classify(self, message: str) -> ClassificationResult:
        """Classify user message intent using AdaCode API."""
        from app.graph.prompts import INTENT_CLASSIFICATION_SYSTEM, INTENT_CLASSIFICATION_USER

        system_message = INTENT_CLASSIFICATION_SYSTEM + "\n\n" + INTENT_CLASSIFICATION_USER.format(message=message)

        try:
            data = self._call_completion([
                {"role": "system", "content": system_message},
                {"role": "user", "content": message},
            ], max_tokens=128)

            # Extract the choice content
            choices = data.get("choices", [])
            if not choices:
                raise LLMError("No choices in AdaCode response")

            content = choices[0].get("message", {}).get("content", "")
            if not content:
                raise LLMError("No content in message from AdaCode response")

            result = json.loads(content.strip())
            intent = result.get("intent")
            confidence = result.get("confidence")
            has_complaint_signal = result.get("has_complaint_signal", False)
            sentiment = result.get("sentiment", "neutral")

            if intent not in VALID_INTENTS:
                raise LLMError(f"Invalid intent from AdaCode: {intent}")
            if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
                raise LLMError(f"Invalid confidence from AdaCode: {confidence}")
            if not isinstance(has_complaint_signal, bool):
                raise LLMError(f"Invalid has_complaint_signal from AdaCode: {has_complaint_signal}")
            if sentiment not in VALID_SENTIMENTS:
                raise LLMError(f"Invalid sentiment from AdaCode: {sentiment}")

            return {
                "intent": intent,
                "confidence": float(confidence),
                "has_complaint_signal": has_complaint_signal,
                "sentiment": sentiment,
            }

        except json.JSONDecodeError as e:
            raise LLMError(f"Invalid JSON from AdaCode: {e}") from e
        except Exception as e:
            logger.exception("adacode_classify failed: %s", e)
            raise LLMError(f"AdaCode API error: {e}") from e

    def classify_with_history(self, messages: list[dict[str, str]]) -> ClassificationResult:
        """Multi-turn aware classification using conversation history."""
        from app.graph.prompts import INTENT_CLASSIFICATION_SYSTEM, INTENT_CLASSIFICATION_USER
        latest_user_content = ""
        for m in messages:
            if m.get("role") == "user":
                latest_user_content = m["content"]
        if not latest_user_content:
            return self.classify("")

        system_message = INTENT_CLASSIFICATION_SYSTEM + "\n\n" + INTENT_CLASSIFICATION_USER.format(message=latest_user_content)

        try:
            data = self._call_completion([
                {"role": "system", "content": system_message},
                {"role": "user", "content": latest_user_content},
            ], max_tokens=128)

            choices = data.get("choices", [])
            if not choices:
                raise LLMError("No choices in AdaCode response")

            content = choices[0].get("message", {}).get("content", "")
            if not content:
                raise LLMError("No content in message from AdaCode response")

            result = json.loads(content.strip())
            intent = result.get("intent")
            confidence = result.get("confidence")
            has_complaint_signal = result.get("has_complaint_signal", False)
            sentiment = result.get("sentiment", "neutral")

            if intent not in VALID_INTENTS:
                raise LLMError(f"Invalid intent from AdaCode: {intent}")
            if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
                raise LLMError(f"Invalid confidence from AdaCode: {confidence}")
            if not isinstance(has_complaint_signal, bool):
                raise LLMError(f"Invalid has_complaint_signal from AdaCode: {has_complaint_signal}")
            if sentiment not in VALID_SENTIMENTS:
                raise LLMError(f"Invalid sentiment from AdaCode: {sentiment}")

            return {
                "intent": intent,
                "confidence": float(confidence),
                "has_complaint_signal": has_complaint_signal,
                "sentiment": sentiment,
            }

        except json.JSONDecodeError as e:
            raise LLMError(f"Invalid JSON from AdaCode: {e}") from e
        except Exception as e:
            logger.exception("adacode_classify_with_history failed: %s", e)
            raise LLMError(f"AdaCode API error: {e}") from e

    def compose_reply(self, message: str, retrieved_row: dict | None, match_kind: str, customer_context: dict | None = None) -> str:
        """Compose natural Indonesian reply grounded in retrieved_row via AdaCode API."""
        from app.graph.prompts import COMPOSE_NOMATCH_SYSTEM, COMPOSE_PARTIAL_SYSTEM, COMPOSE_STRICT_SYSTEM, COMPOSE_USER_TEMPLATE

        # Select system prompt based on match kind
        if match_kind == "none":
            system = COMPOSE_NOMATCH_SYSTEM
        elif match_kind == "medium":
            system = COMPOSE_PARTIAL_SYSTEM
        else:
            system = COMPOSE_STRICT_SYSTEM

        if retrieved_row:
            source_str = " | ".join(f"{k}: {v}" for k, v in retrieved_row.items() if v is not None)
        else:
            source_str = "(tidak ada data yang cocok di katalog)"

        user_content = COMPOSE_USER_TEMPLATE.format(message=message, source_row=source_str, match_kind=match_kind, customer_context=customer_context)

        try:
            data = self._call_completion([
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ], max_tokens=512)

            choices = data.get("choices", [])
            if not choices:
                raise LLMError("No choices in AdaCode response for compose_reply")

            return choices[0].get("message", {}).get("content", "").strip()

        except json.JSONDecodeError as e:
            raise LLMError(f"Invalid JSON from AdaCode compose: {e}") from e
        except Exception as e:
            raise LLMError(f"AdaCode compose failed: {e}") from e

    def compose_reply_with_history(
        self,
        messages: list[dict[str, str]],
        message: str,
        retrieved_row: dict | None,
        match_kind: str,
        customer_context: dict | None = None,
    ) -> str:
        """Compose reply with full conversation history."""
        from app.graph.prompts import COMPOSE_NOMATCH_SYSTEM, COMPOSE_PARTIAL_SYSTEM, COMPOSE_STRICT_SYSTEM, COMPOSE_USER_TEMPLATE
        if match_kind == "none":
            system = COMPOSE_NOMATCH_SYSTEM
        elif match_kind == "medium":
            system = COMPOSE_PARTIAL_SYSTEM
        else:
            system = COMPOSE_STRICT_SYSTEM

        if retrieved_row:
            source_str = " | ".join(f"{k}: {v}" for k, v in retrieved_row.items() if v is not None)
        else:
            source_str = "(tidak ada data yang cocok di katalog)"

        user_content = COMPOSE_USER_TEMPLATE.format(message=message, source_row=source_str, match_kind=match_kind, customer_context=customer_context)

        try:
            data = self._call_completion([
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ], max_tokens=512)

            choices = data.get("choices", [])
            if not choices:
                raise LLMError("No choices in AdaCode response for compose_reply")

            return choices[0].get("message", {}).get("content", "").strip()

        except json.JSONDecodeError as e:
            raise LLMError(f"Invalid JSON from AdaCode compose: {e}") from e
        except Exception as e:
            raise LLMError(f"AdaCode compose failed: {e}") from e


def get_llm_client() -> LLMClient:
    """Factory function that creates the appropriate LLM client based on LLM_BACKEND env var.

    Supported backends: "anthropic", "gemini", "adacode". Default: "gemini".

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

    elif backend == "adacode":
        if not settings.adacode_api_key:
            raise LLMError("ADACODE_API_KEY not set for adacode backend")
        return AdaCodeLLMClient(
            api_key=settings.adacode_api_key,
            base_url=settings.adacode_base_url,
            model=settings.adacode_model,
        )

    else:
        raise LLMError(
            f"unknown LLM backend: {backend}. Choose 'anthropic', 'gemini', or 'adacode'"
        )


class FallingBackLLMClient(LLMClient):
    """Wrapper that tries multiple LLM clients in priority order.

    If one client raises an LLMError, the next client in the chain is tried.
    If all fail, the last LLMError is re-raised.

    NOTE: This catches only LLMError (network/API errors). LLMValidationError is NOT caught
    because it indicates invalid output - the caller should handle it via its own fallback path.
    """

    def __init__(self, clients: list[LLMClient]):
        self._clients = clients
        self._fallback_chain = ", ".join(type(c).__name__ for c in clients)

    def classify(self, message: str) -> ClassificationResult:
        """Classify with fallback across all registered clients."""
        for i, client in enumerate(self._clients):
            try:
                result = client.classify(message)
                logger.info(
                    f"FallingBackLLMClient: classify succeeded with {type(client).__name__} "
                    f"(attempt {i+1}/{len(self._clients)})"
                )
                return result
            except LLMError as e:
                logger.warning(
                    f"FallingBackLLMClient: classify failed with {type(client).__name__}: {e}, "
                    f"trying next..."
                )
                # If this was the last client, re-raise the error
                if i == len(self._clients) - 1:
                    raise
                continue
        # Unreachable, but needed to satisfy type checker
        raise LLMError("Unexpected error in FallingBackLLMClient.classify")

    def classify_with_history(self, messages: list[dict[str, str]]) -> ClassificationResult:
        """Multi-turn classification with fallback."""
        for i, client in enumerate(self._clients):
            try:
                result = client.classify_with_history(messages)
                logger.info(
                    f"FallingBackLLMClient: classify_with_history succeeded with {type(client).__name__} "
                    f"(attempt {i+1}/{len(self._clients)})"
                )
                return result
            except LLMError as e:
                logger.warning(
                    f"FallingBackLLMClient: classify_with_history failed with {type(client).__name__}: {e}, "
                    f"trying next..."
                )
                if i == len(self._clients) - 1:
                    raise
                continue
        raise LLMError("Unexpected error in FallingBackLLMClient.classify_with_history")

    def compose_reply(self, message: str, retrieved_row: dict | None, match_kind: str, customer_context: dict | None = None) -> str:
        """Compose reply with fallback."""
        for i, client in enumerate(self._clients):
            try:
                result = client.compose_reply(message, retrieved_row, match_kind, customer_context)
                logger.info(
                    f"FallingBackLLMClient: compose_reply succeeded with {type(client).__name__} "
                    f"(attempt {i+1}/{len(self._clients)})"
                )
                return result
            except LLMError as e:
                logger.warning(
                    f"FallingBackLLMClient: compose_reply failed with {type(client).__name__}: {e}, "
                    f"trying next..."
                )
                if i == len(self._clients) - 1:
                    raise
                continue
        raise LLMError("Unexpected error in FallingBackLLMClient.compose_reply")

    def compose_reply_with_history(
        self,
        messages: list[dict[str, str]],
        message: str,
        retrieved_row: dict | None,
        match_kind: str,
        customer_context: dict | None = None,
    ) -> str:
        """Compose reply with history and fallback."""
        for i, client in enumerate(self._clients):
            try:
                result = client.compose_reply_with_history(messages, message, retrieved_row, match_kind, customer_context)
                logger.info(
                    f"FallingBackLLMClient: compose_reply_with_history succeeded with {type(client).__name__} "
                    f"(attempt {i+1}/{len(self._clients)})"
                )
                return result
            except LLMError as e:
                logger.warning(
                    f"FallingBackLLMClient: compose_reply_with_history failed with {type(client).__name__}: {e}, "
                    f"trying next..."
                )
                if i == len(self._clients) - 1:
                    raise
                continue
        raise LLMError("Unexpected error in FallingBackLLMClient.compose_reply_with_history")


def get_fallback_llm_client(priority_backends: list[str]) -> LLMClient:
    """Create a FallingBackLLMClient by instantiating clients from backend names.

    Args:
        priority_backends: List of backend names in priority order, e.g. ["adacode", "gemini"].
                           Each must be one of: "adacode", "gemini", "anthropic".

    Returns:
        A FallingBackLLMClient wrapping the configured clients in order.
    """
    from app.config import get_settings

    settings = get_settings()
    clients: list[LLMClient] = []

    for backend in priority_backends:
        backend_lower = backend.lower()
        if backend_lower == "adacode":
            if not settings.adacode_api_key:
                raise LLMError(f"ADACODE_API_KEY not set for adacode backend in fallback chain")
            client = AdaCodeLLMClient(
                api_key=settings.adacode_api_key,
                base_url=settings.adacode_base_url,
                model=settings.adacode_model,
            )
            clients.append(client)
        elif backend_lower == "gemini":
            if not settings.gemini_api_key:
                raise LLMError(f"GEMINI_API_KEY not set for gemini backend in fallback chain")
            clients.append(GeminiLLMClient(api_key=settings.gemini_api_key))
        elif backend_lower == "anthropic":
            if not settings.anthropic_api_key:
                raise LLMError(f"ANTHROPIC_API_KEY not set for anthropic backend in fallback chain")
            clients.append(AnthropicLLMClient(api_key=settings.anthropic_api_key))
        else:
            raise LLMError(f"Unknown backend '{backend}' in fallback chain; choose adacode/gemini/anthropic")

    if not clients:
        raise LLMError("At least one backend must be specified in priority_backends")

    return FallingBackLLMClient(clients)


__all__ = [
    "LLMError",
    "LLMClient",
    "AnthropicLLMClient",
    "GeminiLLMClient",
    "AdaCodeLLMClient",
    "FallingBackLLMClient",  # new: wraps multiple backends with automatic failover
    "get_llm_client",
    "get_fallback_llm_client",  # convenience factory for fall-back chains
    "LLMValidationError",
    "validate_reply",
]


class LLMValidationError(Exception):
    """Raised when LLM-composed reply contains facts not in source row."""


def validate_reply(reply: str, source_row: dict | str | None) -> None:
    """Enforce no-hallucination rule on a composed reply.

    Raises LLMValidationError if reply contains numbers, sizes, or stock
    indicators not present in source_row.

    Args:
      reply: the composed reply text from the LLM.
      source_row: matched FAQ or product row as dict, or stringified row,
                  or None when no row matched (validation is a no-op then).
    """
    if source_row is None:
        return

    # Extract source text — either from a dict's stringified values, or a raw string.
    if isinstance(source_row, dict):
        source_text = " ".join(str(v) for v in source_row.values() if v is not None)
    elif isinstance(source_row, str):
        source_text = source_row
    else:
        return

    # 1. Numeric tokens — must all appear in source.
    reply_nums = set(re.findall(r"\d+(?:\.\d+)?", reply))
    source_nums = set(re.findall(r"\d+(?:\.\d+)?", source_text))
    invented_nums = reply_nums - source_nums
    if invented_nums:
        raise LLMValidationError(
            f"Reply contains numbers not in source: {sorted(invented_nums)}"
        )

    # 2. Sizes — S, M, L, XL, XXL, XXXL.
    size_pattern = r"\b(?:XXXL|XXL|XL|L|M|S)\b"
    reply_sizes = set(re.findall(size_pattern, reply))
    source_sizes = set(re.findall(size_pattern, source_text))
    # Only enforce if source actually mentions sizes (otherwise L may be common word).
    if source_sizes and (reply_sizes - source_sizes):
        raise LLMValidationError(
            f"Reply contains sizes not in source: {sorted(reply_sizes - source_sizes)}"
        )

    # 3. Stock indicators — ready / habis / Y / N.
    stock_pattern = r"\b(?:ready|habis)\b"
    reply_stock = set(re.findall(stock_pattern, reply, flags=re.IGNORECASE))
    source_stock = set(re.findall(stock_pattern, source_text, flags=re.IGNORECASE))
    if source_stock and (reply_stock - source_stock):
        raise LLMValidationError(
            f"Reply contains stock status not in source: {sorted(reply_stock - source_stock)}"
        )

    # 4. Strict price-format check — the reply must contain the source price verbatim
    #    if it mentions a price. Look for "Rp" anywhere in reply and ensure
    #    a matching "Rp <digits>" pattern from source appears character-for-character.
    reply_prices = re.findall(r"Rp\s*[\d.,]+", reply)
    if reply_prices:
        # Normalize: any Rp <num> in reply must match at least one Rp <num> in source.
        source_prices = re.findall(r"Rp\s*[\d.,]+", source_text)
        if not source_prices:
            raise LLMValidationError(
                f"Reply mentions price but source has no price: {reply_prices}"
            )
        for rp in reply_prices:
            # Normalize whitespace and check substring match against each source price.
            rp_norm = re.sub(r"\s+", " ", rp).strip()
            if not any(rp_norm == re.sub(r"\s+", " ", sp).strip() for sp in source_prices):
                raise LLMValidationError(
                    f"Reply price '{rp}' does not exactly match any source price"
                )