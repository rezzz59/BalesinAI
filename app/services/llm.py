"""Abstract LLM client interface and provider implementations."""
import abc
import httpx
import json
import logging
import os
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
VALID_SENTIMENTS = {"positive", "neutral", "negative"}
ClassificationResult: TypeAlias = dict[str, Any]


class LLMError(Exception):
    """Raised when LLM call fails or returns invalid output."""


class LLMValidationError(LLMError):
    """Raised when LLM-composed reply contains facts not in source row."""


class LLMClient(metaclass=abc.ABCMeta):
    """Abstract base class for intent classification clients."""

    @abc.abstractmethod
    def classify(self, message: str) -> ClassificationResult:
        """Classify user message intent. Returns {intent, confidence}.

        Raises LLMError if API fails or response is invalid.
        """
        raise LLMError("Empty fallback chain - no clients available")

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
        persona: str | None = None,
    ) -> str:
        """Compose natural Indonesian reply grounded in retrieved_row (if any).

        Args:
          message: the buyer's WhatsApp message.
          retrieved_row: matched FAQ or product row, or None.
          match_kind: 'high' | 'medium' | 'none'.
          customer_context: optional dict from analyze_customer_context with
            mapped_conditions, issue_type, primary_intent, confidence, reasoning.
          persona: optional store-persona instruction text prepended to the
            compose system prompt (per business_type).

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
        persona: str | None = None,
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
          persona: optional store-persona instruction text prepended to the
            compose system prompt (per business_type).

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
            for kw in ("kecewa", "rusak", "refund", "balik", "gak sampai", "belum sampai",
                       "udah lama", "kapan sampainya", "komplain", "jelek", "batal")
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
        """Multi-turn aware classification using latest message only."""
        last_msg = ""
        if messages and isinstance(messages[-1], dict):
            last_msg = messages[-1].get("content", "") or ""
        return self.classify(last_msg)

    def compose_reply(
        self,
        message: str,
        retrieved_row: dict | None,
        match_kind: str,
        customer_context: dict | None = None,
        persona: str | None = None,
    ) -> str:
        """Provide a deterministic dummy reply that mirrors source-row facts."""
        if not retrieved_row:
            return "Terima kasih! Kami akan membantu Anda segera. Boleh kami bantu cari produk yang lainnya, Kak?"
        if isinstance(retrieved_row, str):
            return f"Terima kasih telah menghubungi kami. {retrieved_row} Boleh dibantu cari yang lainnya, Kak?"
        answer = (
            retrieved_row.get("jawaban")
            or retrieved_row.get("answer")
            or retrieved_row.get("stok")
            or retrieved_row.get("deskripsi")
            or retrieved_row.get("harga")
            or retrieved_row.get("price")
            or ""
        )
        if answer:
            return f"Terima kasih telah menghubungi kami. {answer} Boleh dibantu cari yang lainnya, Kak?"
        return "Terima kasih telah menghubungi kami. Boleh dibantu cari yang lainnya, Kak?"

    def compose_reply_with_history(
        self,
        messages: list[dict[str, str]],
        message: str,
        retrieved_row: dict | None,
        match_kind: str,
        customer_context: dict | None = None,
        persona: str | None = None,
    ) -> str:
        """Multi-turn aware dummy reply."""
        return self.compose_reply(message, retrieved_row, match_kind, customer_context, persona)


class AdaCodeLLMClient(LLMClient):
    """Wraps AdaCODE's OpenAI-compatible chat completions API.

    AdaCODE exposes POST {base_url}/v1/chat/completions (same shape as the
    OpenAI API). Intent classification and reply composition are done by
    prompting a chat model, mirroring the Gemini/Anthropic clients.
    """

    def __init__(self, api_key: str, base_url: str = "https://api.adacode.ai", model: str = "claude-sonnet-4-6"):
        self._api_key = api_key
        self._base_url = (base_url or "https://api.adacode.ai").rstrip("/")
        self._model = model
        self._session = httpx.Client(timeout=60.0)

    def _chat(self, system: str, messages: list[dict[str, str]], max_tokens: int = 512) -> str:
        """POST /v1/chat/completions and return the assistant text."""
        resp = self._session.post(
            f"{self._base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self._model,
                "messages": [{"role": "system", "content": system}] + messages,
                "max_tokens": max_tokens,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as e:
            raise LLMValidationError(f"Invalid AdaCode chat response format: {e}") from e

    def classify(self, message: str) -> ClassificationResult:
        """Classify user message intent via AdaCode API."""
        try:
            text = self._chat(
                INTENT_CLASSIFICATION_SYSTEM,
                [{"role": "user", "content": message}],
                max_tokens=256,
            )
        except LLMValidationError:
            raise
        except httpx.HTTPStatusError as e:
            raise LLMError(f"AdaCode API error: {e.response.status_code} {e.response.text}") from e
        except httpx.HTTPError as e:
            raise LLMError(f"AdaCode HTTP error: {e}") from e
        except Exception as e:
            if isinstance(e, LLMError):
                raise
            raise LLMError(f"Unexpected AdaCode error: {e}") from e
        return self._parse_classification(text)

    def classify_with_history(self, messages: list[dict[str, str]]) -> ClassificationResult:
        """Classify with history — folds the conversation into one user message."""
        history = [
            m.get("content", "")
            for m in messages
            if isinstance(m, dict) and m.get("content")
        ]
        last_msg = history[-1] if history else ""
        if not last_msg:
            return self.classify("")
        history_text = "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages if isinstance(m, dict))
        try:
            text = self._chat(
                INTENT_CLASSIFICATION_SYSTEM,
                [{"role": "user", "content": history_text}],
                max_tokens=256,
            )
        except LLMValidationError:
            raise
        except httpx.HTTPStatusError as e:
            raise LLMError(f"AdaCode API error: {e.response.status_code} {e.response.text}") from e
        except httpx.HTTPError as e:
            raise LLMError(f"AdaCode HTTP error: {e}") from e
        except Exception as e:
            if isinstance(e, LLMError):
                raise
            raise LLMError(f"Unexpected AdaCode error: {e}") from e
        return self._parse_classification(text)

    def _parse_classification(self, text: str) -> ClassificationResult:
        """Parse JSON classification from AdaCode output."""
        try:
            match = re.search(r'\{[^}]+\}', text)
            if match:
                data = json.loads(match.group())
            else:
                data = json.loads(text)
            intent = data.get("intent", "").lower()
            confidence = float(data.get("confidence", 0))
            sentiment = data.get("sentiment", "neutral").lower()
            if intent not in VALID_INTENTS:
                raise LLMValidationError(f"Invalid intent from AdaCode: {intent!r}")
            if not (0 <= confidence <= 1):
                raise LLMValidationError(f"Confidence out of range: {confidence}")
            if sentiment not in VALID_SENTIMENTS:
                sentiment = "neutral"
            return {"intent": intent, "confidence": confidence, "sentiment": sentiment}
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            raise LLMValidationError(f"Failed to parse AdaCode classification: {e}") from e

    def compose_reply(
        self,
        message: str,
        retrieved_row: dict | None,
        match_kind: str,
        customer_context: dict | None = None,
        persona: str | None = None,
    ) -> str:
        """Compose reply grounded in retrieved row via AdaCode."""
        return self._compose(message, retrieved_row, match_kind, customer_context, persona, with_history=False)

    def compose_reply_with_history(
        self,
        messages: list[dict[str, str]],
        message: str,
        retrieved_row: dict | None,
        match_kind: str,
        customer_context: dict | None = None,
        persona: str | None = None,
    ) -> str:
        """Compose reply with history via AdaCode."""
        return self._compose(message, retrieved_row, match_kind, customer_context, persona, with_history=True, messages=messages)

    def _compose(self, message, retrieved_row, match_kind, customer_context, persona=None, with_history=False, messages=None):
        """Internal compose via chat completions."""
        prompt = self._build_compose_prompt(message, retrieved_row, match_kind, customer_context, persona, with_history=with_history, messages=messages)
        try:
            text = self._chat(prompt, [], max_tokens=1024)
        except LLMValidationError:
            raise
        except httpx.HTTPStatusError as e:
            raise LLMError(f"AdaCode compose error: {e.response.status_code} {e.response.text}") from e
        except httpx.HTTPError as e:
            raise LLMError(f"AdaCode compose HTTP error: {e}") from e
        except Exception as e:
            if isinstance(e, LLMError):
                raise
            raise LLMError(f"Unexpected AdaCode compose error: {e}") from e
        return self._parse_reply(text)

    def _build_compose_prompt(self, message, retrieved_row, match_kind, customer_context, persona=None, with_history=False, messages=None):
        """Build compose prompt for AdaCode."""
        if match_kind == "none":
            system = COMPOSE_NOMATCH_SYSTEM
        elif match_kind == "medium":
            system = COMPOSE_PARTIAL_SYSTEM
        else:
            system = COMPOSE_STRICT_SYSTEM

        prompt = system + "\n\n"
        if persona:
            prompt += f"{persona}\n\n"
        if with_history and messages:
            history = "\n".join(
                f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages
            )
            prompt += f"Conversation history:\n{history}\n\n"
        prompt += f"User message: {message}\n"
        if retrieved_row:
            prompt += f"Retrieved row: {retrieved_row}\n"
        if customer_context:
            prompt += f"Customer context: {customer_context}\n"
        return prompt

    def _parse_reply(self, text: str) -> str:
        """Parse and validate reply from AdaCode."""
        reply = text.strip()
        if not reply:
            raise LLMValidationError("Empty reply from AdaCode")
        return reply


class GeminiLLMClient(LLMClient):
    """Google Gemini-based LLM client for intent classification and reply composition."""

    def __init__(self, api_key: str):
        import google.generativeai as genai
        self._genai = genai
        self._api_key = api_key
        self._genai.configure(api_key=api_key)
        self._model = self._genai.GenerativeModel("gemini-2.0-flash")

    def classify(self, message: str) -> ClassificationResult:
        """Classify user message intent via Gemini."""
        try:
            prompt = INTENT_CLASSIFICATION_SYSTEM + "\n\nUser message: " + message
            text = self._model.generate_content(prompt).text
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(f"Gemini classify error: {e}") from e
        return self._parse_classification(text)

    def classify_with_history(self, messages: list[dict[str, str]]) -> ClassificationResult:
        """Classify with history via Gemini."""
        try:
            history_text = "\n".join(
                f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages
            )
            prompt = INTENT_CLASSIFICATION_SYSTEM + "\n\nConversation history:\n" + history_text
            text = self._model.generate_content(prompt).text
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(f"Gemini classify_with_history error: {e}") from e
        return self._parse_classification(text)

    def _parse_classification(self, text: str) -> ClassificationResult:
        """Parse JSON classification from Gemini output."""
        try:
            match = re.search(r'\{[^}]+\}', text)
            if match:
                data = json.loads(match.group())
            else:
                data = json.loads(text)
            intent = data.get("intent", "").lower()
            confidence = float(data.get("confidence", 0))
            sentiment = data.get("sentiment", "neutral").lower()
            if intent not in VALID_INTENTS:
                raise LLMValidationError(f"Invalid intent: {intent!r}")
            if not (0 <= confidence <= 1):
                raise LLMValidationError(f"Confidence out of range: {confidence}")
            if sentiment not in VALID_SENTIMENTS:
                sentiment = "neutral"
            return {"intent": intent, "confidence": confidence, "sentiment": sentiment}
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            raise LLMValidationError(f"Failed to parse classification: {e}") from e

    def compose_reply(
        self,
        message: str,
        retrieved_row: dict | None,
        match_kind: str,
        customer_context: dict | None = None,
        persona: str | None = None,
    ) -> str:
        """Compose reply via Gemini."""
        try:
            prompt = self._build_compose_prompt(message, retrieved_row, match_kind, customer_context, persona, with_history=False)
            text = self._model.generate_content(prompt).text
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(f"Gemini compose_reply error: {e}") from e
        return self._parse_reply(text)

    def compose_reply_with_history(
        self,
        messages: list[dict[str, str]],
        message: str,
        retrieved_row: dict | None,
        match_kind: str,
        customer_context: dict | None = None,
        persona: str | None = None,
    ) -> str:
        """Compose reply with history via Gemini."""
        try:
            prompt = self._build_compose_prompt(message, retrieved_row, match_kind, customer_context, persona, with_history=True, messages=messages)
            text = self._model.generate_content(prompt).text
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(f"Gemini compose_reply_with_history error: {e}") from e
        return self._parse_reply(text)

    def _build_compose_prompt(self, message, retrieved_row, match_kind, customer_context, persona=None, with_history=False, messages=None):
        """Build compose prompt for Gemini."""
        if match_kind == "none":
            system = COMPOSE_NOMATCH_SYSTEM
        elif match_kind == "medium":
            system = COMPOSE_PARTIAL_SYSTEM
        else:
            system = COMPOSE_STRICT_SYSTEM

        prompt = system + "\n\n"
        if persona:
            prompt += f"{persona}\n\n"
        if with_history and messages:
            history = "\n".join(
                f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages
            )
            prompt += f"Conversation history:\n{history}\n\n"
        prompt += f"User message: {message}\n"
        if retrieved_row:
            prompt += f"Retrieved row: {retrieved_row}\n"
        if customer_context:
            prompt += f"Customer context: {customer_context}\n"
        return prompt

    def _parse_reply(self, text: str) -> str:
        """Parse and validate reply from Gemini."""
        reply = text.strip()
        if not reply:
            raise LLMValidationError("Empty reply from Gemini")
        return reply


class AnthropicLLMClient(LLMClient):
    """Anthropic Claude-based LLM client."""

    def __init__(self, api_key: str):
        import anthropic
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = "claude-3-5-haiku-20241022"

    def classify(self, message: str) -> ClassificationResult:
        """Classify user message intent via Anthropic Claude."""
        try:
            prompt = INTENT_CLASSIFICATION_SYSTEM + "\n\nUser message: " + message
            response = self._client.messages.create(
                model=self._model,
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(f"Anthropic classify error: {e}") from e
        return self._parse_classification(text)

    def classify_with_history(self, messages: list[dict[str, str]]) -> ClassificationResult:
        """Classify with history via Anthropic Claude."""
        try:
            anthropic_messages = []
            for m in messages:
                role = m.get("role", "user")
                if role == "user":
                    anthropic_messages.append({"role": "user", "content": m.get("content", "")})
                elif role == "assistant":
                    anthropic_messages.append({"role": "assistant", "content": m.get("content", "")})
            prompt = INTENT_CLASSIFICATION_SYSTEM + "\n\nConversation history:\n"
            for am in anthropic_messages:
                prompt += f"{am['role']}: {am['content']}\n"
            response = self._client.messages.create(
                model=self._model,
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(f"Anthropic classify_with_history error: {e}") from e
        return self._parse_classification(text)

    def _parse_classification(self, text: str) -> ClassificationResult:
        """Parse JSON classification from Anthropic output."""
        try:
            match = re.search(r'\{[^}]+\}', text)
            if match:
                data = json.loads(match.group())
            else:
                data = json.loads(text)
            intent = data.get("intent", "").lower()
            confidence = float(data.get("confidence", 0))
            sentiment = data.get("sentiment", "neutral").lower()
            if intent not in VALID_INTENTS:
                raise LLMValidationError(f"Invalid intent: {intent!r}")
            if not (0 <= confidence <= 1):
                raise LLMValidationError(f"Confidence out of range: {confidence}")
            if sentiment not in VALID_SENTIMENTS:
                sentiment = "neutral"
            return {"intent": intent, "confidence": confidence, "sentiment": sentiment}
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            raise LLMValidationError(f"Failed to parse classification: {e}") from e

    def compose_reply(
        self,
        message: str,
        retrieved_row: dict | None,
        match_kind: str,
        customer_context: dict | None = None,
        persona: str | None = None,
    ) -> str:
        """Compose reply via Anthropic Claude."""
        try:
            prompt = self._build_compose_prompt(message, retrieved_row, match_kind, customer_context, persona, with_history=False)
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(f"Anthropic compose_reply error: {e}") from e
        return self._parse_reply(text)

    def compose_reply_with_history(
        self,
        messages: list[dict[str, str]],
        message: str,
        retrieved_row: dict | None,
        match_kind: str,
        customer_context: dict | None = None,
        persona: str | None = None,
    ) -> str:
        """Compose reply with history via Anthropic Claude."""
        try:
            prompt = self._build_compose_prompt(message, retrieved_row, match_kind, customer_context, persona, with_history=True, messages=messages)
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(f"Anthropic compose_reply_with_history error: {e}") from e
        return self._parse_reply(text)

    def _build_compose_prompt(self, message, retrieved_row, match_kind, customer_context, persona=None, with_history=False, messages=None):
        """Build compose prompt for Anthropic."""
        if match_kind == "none":
            system = COMPOSE_NOMATCH_SYSTEM
        elif match_kind == "medium":
            system = COMPOSE_PARTIAL_SYSTEM
        else:
            system = COMPOSE_STRICT_SYSTEM

        prompt = system + "\n\n"
        if persona:
            prompt += f"{persona}\n\n"
        if with_history and messages:
            history = "\n".join(
                f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages
            )
            prompt += f"Conversation history:\n{history}\n\n"
        prompt += f"User message: {message}\n"
        if retrieved_row:
            prompt += f"Retrieved row: {retrieved_row}\n"
        if customer_context:
            prompt += f"Customer context: {customer_context}\n"
        return prompt

    def _parse_reply(self, text: str) -> str:
        """Parse and validate reply from Anthropic."""
        reply = text.strip()
        if not reply:
            raise LLMValidationError("Empty reply from Anthropic")
        return reply


class FallingBackLLMClient(LLMClient):
    """Client that falls back through a chain of clients."""

    def __init__(self, clients: list[LLMClient]):
        if not clients:
            raise LLMError("At least one client must be provided")
        self._clients = clients

    def classify(self, message: str) -> ClassificationResult:
        """Classify message intent using fallback chain."""
        for i, client in enumerate(self._clients):
            try:
                result = client.classify(message)
                logger.info(f"FallingBackLLMClient: classify succeeded with {type(client).__name__} (attempt {i+1}/{len(self._clients)})")
                return result
            except LLMValidationError:
                raise
            except LLMError as e:
                logger.warning(f"FallingBackLLMClient: classify failed with {type(client).__name__}: {e}, trying next...")
                if i == len(self._clients) - 1:
                    raise
                continue
        raise LLMError("Unexpected error in FallingBackLLMClient.classify")

    def classify_with_history(self, messages: list[dict[str, str]]) -> ClassificationResult:
        """Classify with history using fallback chain."""
        for i, client in enumerate(self._clients):
            try:
                result = client.classify_with_history(messages)
                logger.info(f"FallingBackLLMClient: classify_with_history succeeded with {type(client).__name__} (attempt {i+1}/{len(self._clients)})")
                return result
            except LLMValidationError:
                raise
            except LLMError as e:
                logger.warning(f"FallingBackLLMClient: classify_with_history failed with {type(client).__name__}: {e}, trying next...")
                if i == len(self._clients) - 1:
                    raise
                continue
        raise LLMError("Unexpected error in FallingBackLLMClient.classify_with_history")

    def compose_reply(
        self,
        message: str,
        retrieved_row: dict | None,
        match_kind: str,
        customer_context: dict | None = None,
        persona: str | None = None,
    ) -> str:
        """Compose reply using fallback chain."""
        for i, client in enumerate(self._clients):
            try:
                result = client.compose_reply(message, retrieved_row, match_kind, customer_context, persona)
                logger.info(f"FallingBackLLMClient: compose_reply succeeded with {type(client).__name__} (attempt {i+1}/{len(self._clients)})")
                return result
            except LLMValidationError:
                raise
            except LLMError as e:
                logger.warning(f"FallingBackLLMClient: compose_reply failed with {type(client).__name__}: {e}, trying next...")
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
        persona: str | None = None,
    ) -> str:
        """Compose reply with history and fallback."""
        for i, client in enumerate(self._clients):
            try:
                result = client.compose_reply_with_history(messages, message, retrieved_row, match_kind, customer_context, persona)
                logger.info(f"FallingBackLLMClient: compose_reply_with_history succeeded with {type(client).__name__} (attempt {i+1}/{len(self._clients)})")
                return result
            except LLMValidationError:
                raise
            except LLMError as e:
                logger.warning(f"FallingBackLLMClient: compose_reply_with_history failed with {type(client).__name__}: {e}, trying next...")
                if i == len(self._clients) - 1:
                    raise
                continue
        raise LLMError("Unexpected error in FallingBackLLMClient.compose_reply_with_history")


def get_llm_client() -> LLMClient:
    """Get the primary LLM client based on configuration."""
    from app.config import get_settings
    settings = get_settings()
    if settings.adacode_api_key:
        return AdaCodeLLMClient(
            api_key=settings.adacode_api_key,
            base_url=settings.adacode_base_url,
            model=settings.adacode_model,
        )
    if settings.gemini_api_key:
        return GeminiLLMClient(api_key=settings.gemini_api_key)
    if settings.anthropic_api_key:
        return AnthropicLLMClient(api_key=settings.anthropic_api_key)
    logger.warning("No LLM API key configured, falling back to MockLLMClient")
    return MockLLMClient()


def get_fallback_llm_client(priority_backends: list[str] | None = None) -> LLMClient:
    """Get a fallback-capable LLM client with the configured clients in order.
    """
    from app.config import get_settings

    settings = get_settings()
    clients: list[LLMClient] = []

    backends = priority_backends or ["adacode", "gemini", "anthropic"]

    for backend in backends:
        backend_lower = backend.lower()
        if backend_lower == "adacode":
            if not settings.adacode_api_key:
                logger.warning("ADACODE_API_KEY not set, skipping adacode")
                continue
            try:
                client = AdaCodeLLMClient(
                    api_key=settings.adacode_api_key,
                    base_url=settings.adacode_base_url,
                    model=settings.adacode_model,
                )
                clients.append(client)
                logger.info(f"Added AdaCode client to fallback chain")
            except Exception as e:
                logger.warning(f"Failed to init AdaCode client: {e}")
        elif backend_lower == "gemini":
            if not settings.gemini_api_key:
                logger.warning("GEMINI_API_KEY not set, skipping gemini")
                continue
            try:
                import google.generativeai as genai  # type: ignore
                client = GeminiLLMClient(api_key=settings.gemini_api_key)
                clients.append(client)
                logger.info(f"Added Gemini client to fallback chain")
            except (ImportError, ModuleNotFoundError):
                logger.warning("google.generativeai not installed, skipping gemini")
            except Exception as e:
                logger.warning(f"Failed to init Gemini client: {e}")
        elif backend_lower == "anthropic":
            if not settings.anthropic_api_key:
                logger.warning("ANTHROPIC_API_KEY not set, skipping anthropic")
                continue
            try:
                client = AnthropicLLMClient(api_key=settings.anthropic_api_key)
                clients.append(client)
                logger.info(f"Added Anthropic client to fallback chain")
            except Exception as e:
                logger.warning(f"Failed to init Anthropic client: {e}")
        else:
            logger.warning(f"Unknown backend '{backend}' in fallback chain; choose adacode/gemini/anthropic")

    if not clients:
        logger.warning("No LLM backends available, using MockLLMClient as fallback")
        return MockLLMClient()

    return FallingBackLLMClient(clients)


def get_safe_llm_client(priority_backends: list[str] | None = None) -> LLMClient:
    """Get LLM client with safe fallback to MockLLMClient on any error.
    
    This wraps get_fallback_llm_client and falls back to MockLLMClient if:
    1. No clients could be initialized (returns MockLLMClient)
    2. All backends fail at runtime (falls back to MockLLMClient)
    """
    try:
        client = get_fallback_llm_client(priority_backends)
    except LLMError as e:
        logger.warning(f"Failed to create fallback LLM client: {e}, using MockLLMClient")
        return MockLLMClient()
    
    # Wrap the client to catch runtime errors and fallback to MockLLMClient
    return _SafeLLMClientWrapper(client, priority_backends)


class _SafeLLMClientWrapper(LLMClient):
    """Wrapper that falls back to MockLLMClient on any runtime error."""
    
    def __init__(self, wrapped: LLMClient, priority_backends: list[str] | None = None):
        self._wrapped = wrapped
        self._priority_backends = priority_backends or ["adacode", "gemini", "anthropic"]
    
    def classify(self, message: str) -> ClassificationResult:
        try:
            return self._wrapped.classify(message)
        except LLMError as e:
            logger.warning(f"LLM classify failed: {e}, trying fallback backends...")
            # Try next backend in chain
            for backend in self._priority_backends:
                try:
                    alt_client = get_fallback_llm_client([backend])
                    return alt_client.classify(message)
                except LLMError:
                    continue
            # All backends failed, fallback to mock
            logger.warning(f"All backends failed, using MockLLMClient")
            return MockLLMClient().classify(message)
    
    def classify_with_history(self, messages: list[dict[str, str]]) -> ClassificationResult:
        try:
            return self._wrapped.classify_with_history(messages)
        except LLMError as e:
            logger.warning(f"LLM classify_with_history failed: {e}, trying fallback backends...")
            for backend in self._priority_backends:
                try:
                    alt_client = get_fallback_llm_client([backend])
                    return alt_client.classify_with_history(messages)
                except LLMError:
                    continue
            logger.warning(f"All backends failed, using MockLLMClient")
            return MockLLMClient().classify_with_history(messages)
    
    def compose_reply(self, message: str, retrieved_row: dict | None, match_kind: str, customer_context: dict | None = None, persona: str | None = None) -> str:
        try:
            return self._wrapped.compose_reply(message, retrieved_row, match_kind, customer_context, persona)
        except LLMError as e:
            logger.warning(f"LLM compose_reply failed: {e}, using MockLLMClient")
            return MockLLMClient().compose_reply(message, retrieved_row, match_kind, customer_context, persona)

    def compose_reply_with_history(self, messages: list[dict[str, str]], message: str, retrieved_row: dict | None, match_kind: str, customer_context: dict | None = None, persona: str | None = None) -> str:
        try:
            return self._wrapped.compose_reply_with_history(messages, message, retrieved_row, match_kind, customer_context, persona)
        except LLMError as e:
            logger.warning(f"LLM compose_reply_with_history failed: {e}, using MockLLMClient")
            return MockLLMClient().compose_reply_with_history(messages, message, retrieved_row, match_kind, customer_context, persona)


__all__ = [
    "LLMError",
    "LLMClient",
    "AnthropicLLMClient",
    "GeminiLLMClient",
    "AdaCodeLLMClient",
    "FallingBackLLMClient",  # new: wraps multiple backends with automatic failover
    "get_llm_client",
    "get_fallback_llm_client",  # convenience factory for fall-back chains
    "get_safe_llm_client",  # safe factory with mock fallback
    "LLMValidationError",
    "validate_reply",
]


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
