"""Abstract LLM client interface and provider implementations."""
import abc
import json
import logging
import re
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

    @abc.abstractmethod
    def compose_reply(self, message: str, retrieved_row: dict | None, match_kind: str) -> str:
        """Compose natural Indonesian reply grounded in retrieved_row (if any).

        Args:
          message: the buyer's WhatsApp message.
          retrieved_row: matched FAQ or product row, or None.
          match_kind: 'high' | 'medium' | 'none'.

        Returns the composed reply text. May raise LLMError.
        """
        pass


class MockLLMClient(LLMClient):
    """Deterministic classifier for local dev / testing / when SDK missing.

    Uses simple keyword heuristics — no external API call. Never raises.
    """

    def classify(self, message: str) -> ClassificationResult:
        msg = (message or "").lower()
        if any(kw in msg for kw in ("stok", "ready", "ada ga", "ada nggak", "ready stock", "tersedia")):
            return {"intent": "check_product", "confidence": 0.95}
        if any(kw in msg for kw in ("order", "pesan", "beli", "booking", "checkout")):
            return {"intent": "confirm_order", "confidence": 0.92}
        if any(kw in msg for kw in ("?", "apa", "bagaimana", "kapan", "dimana", "gimana")):
            return {"intent": "faq", "confidence": 0.8}
        return {"intent": "unclear", "confidence": 0.4}

    def compose_reply(self, message: str, retrieved_row: dict | None, match_kind: str) -> str:
        if retrieved_row:
            return str(retrieved_row.get("name") or retrieved_row.get("nama_produk") or "produk")
        return "Mohon maaf, produk belum tersedia."


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

    def compose_reply(
        self,
        message: str,
        retrieved_row: dict | None,
        match_kind: str,
    ) -> str:
        """See base class. Anthropic implementation."""
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
            logger.exception("gemini_call_failed: %s", e)
            raise LLMError(f"Gemini API error: {e}") from e

    def compose_reply(
        self,
        message: str,
        retrieved_row: dict | None,
        match_kind: str,
    ) -> str:
        """See base class. Gemini implementation."""
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
