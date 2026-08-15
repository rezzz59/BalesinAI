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
    STYLE_PROFILER_SYSTEM,
    STYLE_PROFILER_USER,
)

logger = logging.getLogger(__name__)

VALID_INTENTS = {"faq", "check_product", "confirm_order", "unclear"}
VALID_SENTIMENTS = {"positive", "neutral", "negative"}
VALID_STYLE_FORMALITY = {"formal", "semi-formal", "casual"}
VALID_STYLE_EMOJI = {"none", "low", "medium", "high"}
VALID_STYLE_LENGTH = {"concise", "detailed"}
VALID_STYLE_TONE = {"warm_and_enthusiastic", "professional_and_direct", "humble_and_polite"}
ClassificationResult: TypeAlias = dict[str, Any]


def _extract_sse_content(body: str) -> str:
    """Join assistant content deltas from an OpenAI-style SSE stream body."""
    parts: list[str] = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            continue
        delta = chunk.get("choices", [{}])[0].get("delta", {}) if chunk.get("choices") else {}
        if isinstance(delta, dict) and delta.get("content"):
            parts.append(delta["content"])
        elif isinstance(delta, str) and delta:
            parts.append(delta)
    return "".join(parts).strip()


def _first_json_object(text: str) -> dict:
    """Parse the first complete JSON object anywhere in *text*."""
    decoder = json.JSONDecoder()
    for m in re.finditer(r'\{', text):
        try:
            obj, _ = decoder.raw_decode(text[m.start():])
            return obj
        except json.JSONDecodeError:
            continue
    raise ValueError("no JSON object found in text")


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

    def extract_style_profile(self, text: str) -> dict:
        """Analyze raw onboarding text into {identity, style_profile,
        key_facts_and_preferences}.

        Concrete clients override this; the base default raises so clients that
        never profiled still behave deterministically when asked.
        """
        raise LLMError("Style profiling not supported by this client")

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
                       "udah lama", "komplain", "jelek", "batal")
        )
        has_objection_signal = any(
            kw in msg for kw in ("mahal", "diskon", "potongan", "negosiasi", "nggak kebeli")
        )
        sentiment = "negative" if (has_complaint_signal or has_objection_signal) else "neutral"
        if any(kw in msg for kw in ("stok", "ready", "ada ga", "ada nggak", "ready stock", "tersedia")):
            return {"intent": "check_product", "confidence": 0.95, "has_complaint_signal": has_complaint_signal, "has_objection_signal": has_objection_signal, "sentiment": sentiment}
        if any(kw in msg for kw in ("order", "pesan", "beli", "booking", "checkout")):
            return {"intent": "confirm_order", "confidence": 0.92, "has_complaint_signal": has_complaint_signal, "has_objection_signal": has_objection_signal, "sentiment": sentiment}
        if any(kw in msg for kw in ("?", "apa", "bagaimana", "kapan", "dimana", "gimana")):
            return {"intent": "faq", "confidence": 0.8, "has_complaint_signal": has_complaint_signal, "has_objection_signal": has_objection_signal, "sentiment": sentiment}
        return {"intent": "unclear", "confidence": 0.4, "has_complaint_signal": has_complaint_signal, "has_objection_signal": has_objection_signal, "sentiment": sentiment}

    def classify_with_history(self, messages: list[dict[str, str]]) -> ClassificationResult:
        """Multi-turn aware classification using latest message only."""
        last_msg = ""
        if messages and isinstance(messages[-1], dict):
            last_msg = messages[-1].get("content", "") or ""
        return self.classify(last_msg)

    def extract_style_profile(self, text: str) -> dict:
        """Deterministic heuristic style profile — no external API call."""
        text = text or ""
        emoji_count = len(re.findall(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF]", text))
        emoji_density = (
            "none" if emoji_count == 0
            else "low" if emoji_count == 1
            else "medium" if emoji_count <= 3
            else "high"
        )
        lower = text.lower()
        if any(w in lower for w in ("dengan hormat", "yang terhormat", "salam sejahtera")):
            formality = "formal"
        elif any(w in lower for w in ("kak", "siap", "noted", "oke", "hehe", "haha", "yaa")):
            formality = "casual"
        else:
            formality = "semi-formal"
        sentences = [s for s in re.split(r"[.!?\n]+", text) if s.strip()]
        avg_words = sum(len(s.split()) for s in sentences) / max(len(sentences), 1)
        sentence_length = "concise" if avg_words < 10 else "detailed"
        if any(w in lower for w in ("terima kasih", "mohon", "maaf", "silakan")):
            tone = "humble_and_polite"
        elif any(w in lower for w in ("mantap", "keren", "gas", "siap", "deals", "mari")):
            tone = "warm_and_enthusiastic"
        else:
            tone = "professional_and_direct"
        phrases = [kw for kw in ("siap kak", "noted", "mantap", "oke kak", "terima kasih") if kw in lower][:4]
        return {
            "identity": {"name": None, "role": None, "business_name": None},
            "style_profile": {
                "formality": formality,
                "emoji_density": emoji_density,
                "sentence_length": sentence_length,
                "tone": tone,
                "key_phrases": phrases,
            },
            "key_facts_and_preferences": [],
        }

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

    def _chat(self, system: str, messages: list[dict[str, str]], max_tokens: int = 512, json_mode: bool = False, _retries: int = 2) -> str:
        """POST /v1/chat/completions and return the assistant text.

        Retries when the model returns an empty content — reasoning-style
        models occasionally emit only reasoning and no final content.
        """
        payload = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}] + messages,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        resp = self._session.post(
            f"{self._base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json=payload,
            timeout=60.0,
        )
        resp.raise_for_status()
        body = resp.text.strip()
        # 9Router may return an SSE stream even when stream=false; extract the
        # assistant content from the data: chunks instead of treating it as JSON.
        if body.startswith("data:") or "\ndata:" in body:
            content = _extract_sse_content(body)
            if not content and _retries > 0:
                return self._chat(system, messages, max_tokens=max_tokens, _retries=_retries - 1)
            return content
        # Some routers (e.g. 9Router combo) append an SSE "data: [DONE]" tail to
        # otherwise-non-streaming responses; strip it before parsing.
        if body.endswith("data: [DONE]"):
            body = body[: body.rindex("data: [DONE]")].rstrip()
        data = json.loads(body)
        try:
            content = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as e:
            raise LLMValidationError(f"Invalid AdaCode chat response format: {e}") from e
        if not content and _retries > 0:
            return self._chat(system, messages, max_tokens=max_tokens, _retries=_retries - 1)
        return content

    def classify(self, message: str) -> ClassificationResult:
        """Classify user message intent via AdaCode API."""
        return self._classify_call([{"role": "user", "content": message}])

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
        return self._classify_call([{"role": "user", "content": history_text}])

    def _classify_call(self, messages: list[dict[str, str]], _retries: int = 2) -> ClassificationResult:
        """Call _chat and parse the classification JSON, retrying on failures."""
        try:
            text = self._chat(
                INTENT_CLASSIFICATION_SYSTEM,
                messages,
                max_tokens=512,
                json_mode=True,
            )
        except LLMValidationError:
            raise
        except httpx.HTTPStatusError as e:
            # 429/5xx retry — transient quota/backend hiccups.
            if _retries > 0 and e.response.status_code in (429, 500, 502, 503, 504):
                return self._classify_call(messages, _retries=_retries - 1)
            raise LLMError(f"AdaCode API error: {e.response.status_code} {e.response.text}") from e
        except httpx.HTTPError as e:
            if _retries > 0:
                return self._classify_call(messages, _retries=_retries - 1)
            raise LLMError(f"AdaCode HTTP error: {e}") from e
        except Exception as e:
            if isinstance(e, LLMError):
                raise
            raise LLMError(f"Unexpected AdaCode error: {e}") from e
        try:
            return self._parse_classification(text)
        except LLMValidationError:
            if _retries > 0:
                return self._classify_call(messages, _retries=_retries - 1)
            raise

    def _parse_classification(self, text: str) -> ClassificationResult:
        """Parse JSON classification from AdaCode output."""
        try:
            data = _first_json_object(text)
            intent = data.get("intent", "").lower()
            confidence = float(data.get("confidence", 0))
            sentiment = data.get("sentiment", "neutral").lower()
            complaint = bool(data.get("has_complaint_signal", False))
            objection = bool(data.get("has_objection_signal", False))
            if intent not in VALID_INTENTS:
                raise LLMValidationError(f"Invalid intent from AdaCode: {intent!r}")
            if not (0 <= confidence <= 1):
                raise LLMValidationError(f"Confidence out of range: {confidence}")
            if sentiment not in VALID_SENTIMENTS:
                sentiment = "neutral"
            return {"intent": intent, "confidence": confidence, "has_complaint_signal": complaint, "has_objection_signal": objection, "sentiment": sentiment}
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning("classification_parse_failed", extra={"raw_text": text[:300], "error": str(e)})
            raise LLMValidationError(f"Failed to parse AdaCode classification: {e}") from e

    def extract_style_profile(self, text: str) -> dict:
        """Analyze raw onboarding text into a style profile via AdaCode."""
        try:
            raw = self._chat(
                STYLE_PROFILER_SYSTEM,
                [{"role": "user", "content": STYLE_PROFILER_USER.format(raw_text=text)}],
                max_tokens=2048,
            )
        except LLMValidationError:
            raise
        except httpx.HTTPStatusError as e:
            raise LLMError(f"AdaCode style profile error: {e.response.status_code} {e.response.text}") from e
        except httpx.HTTPError as e:
            raise LLMError(f"AdaCode style profile HTTP error: {e}") from e
        except Exception as e:
            if isinstance(e, LLMError):
                raise
            raise LLMError(f"Unexpected AdaCode style profile error: {e}") from e
        return _parse_style_profile(raw)

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
            text = self._chat(prompt, [], max_tokens=2048)
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
        self._model = self._genai.GenerativeModel("gemini-3.1-flash-lite")

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
            complaint = bool(data.get("has_complaint_signal", False))
            objection = bool(data.get("has_objection_signal", False))
            if intent not in VALID_INTENTS:
                raise LLMValidationError(f"Invalid intent: {intent!r}")
            if not (0 <= confidence <= 1):
                raise LLMValidationError(f"Confidence out of range: {confidence}")
            if sentiment not in VALID_SENTIMENTS:
                sentiment = "neutral"
            return {"intent": intent, "confidence": confidence, "has_complaint_signal": complaint, "has_objection_signal": objection, "sentiment": sentiment}
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            raise LLMValidationError(f"Failed to parse classification: {e}") from e

    def extract_style_profile(self, text: str) -> dict:
        """Analyze raw onboarding text into a style profile via Gemini."""
        try:
            prompt = STYLE_PROFILER_SYSTEM + "\n\n" + STYLE_PROFILER_USER.format(raw_text=text)
            raw = self._model.generate_content(prompt).text
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(f"Gemini style profile error: {e}") from e
        return _parse_style_profile(raw)

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
            complaint = bool(data.get("has_complaint_signal", False))
            objection = bool(data.get("has_objection_signal", False))
            if intent not in VALID_INTENTS:
                raise LLMValidationError(f"Invalid intent: {intent!r}")
            if not (0 <= confidence <= 1):
                raise LLMValidationError(f"Confidence out of range: {confidence}")
            if sentiment not in VALID_SENTIMENTS:
                sentiment = "neutral"
            return {"intent": intent, "confidence": confidence, "has_complaint_signal": complaint, "has_objection_signal": objection, "sentiment": sentiment}
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            raise LLMValidationError(f"Failed to parse classification: {e}") from e

    def extract_style_profile(self, text: str) -> dict:
        """Analyze raw onboarding text into a style profile via Claude."""
        try:
            prompt = STYLE_PROFILER_SYSTEM + "\n\n" + STYLE_PROFILER_USER.format(raw_text=text)
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(f"Anthropic style profile error: {e}") from e
        return _parse_style_profile(raw)

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

    def extract_style_profile(self, text: str) -> dict:
        """Extract style profile using fallback chain."""
        for i, client in enumerate(self._clients):
            try:
                result = client.extract_style_profile(text)
                logger.info(f"FallingBackLLMClient: extract_style_profile succeeded with {type(client).__name__} (attempt {i+1}/{len(self._clients)})")
                return result
            except LLMValidationError:
                raise
            except LLMError as e:
                logger.warning(f"FallingBackLLMClient: extract_style_profile failed with {type(client).__name__}: {e}, trying next...")
                if i == len(self._clients) - 1:
                    raise
                continue
        raise LLMError("Unexpected error in FallingBackLLMClient.extract_style_profile")

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
    if settings.ai_router_api_key:
        return AdaCodeLLMClient(
            api_key=settings.ai_router_api_key,
            base_url=settings.ai_router_base_url,
            model=settings.ai_router_model,
        )
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

    backends = priority_backends or ["router", "adacode", "gemini", "anthropic"]

    for backend in backends:
        backend_lower = backend.lower()
        if backend_lower == "router":
            if not settings.ai_router_api_key:
                logger.warning("AI_ROUTER_API_KEY not set, skipping 9router")
                continue
            try:
                client = AdaCodeLLMClient(
                    api_key=settings.ai_router_api_key,
                    base_url=settings.ai_router_base_url,
                    model=settings.ai_router_model,
                )
                clients.append(client)
                logger.info("Added 9Router client to fallback chain")
            except Exception as e:
                logger.warning(f"Failed to init 9Router client: {e}")
        elif backend_lower == "adacode":
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
        self._priority_backends = priority_backends or ["router", "adacode", "gemini", "anthropic"]
    
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

    def extract_style_profile(self, text: str) -> dict:
        try:
            return self._wrapped.extract_style_profile(text)
        except LLMError as e:
            logger.warning(f"LLM extract_style_profile failed: {e}, trying fallback backends...")
            for backend in self._priority_backends:
                try:
                    alt_client = get_fallback_llm_client([backend])
                    return alt_client.extract_style_profile(text)
                except LLMError:
                    continue
            logger.warning(f"All backends failed, using MockLLMClient")
            return MockLLMClient().extract_style_profile(text)

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


def _parse_style_profile(text: str) -> dict:
    """Parse + coerce the profiler LLM output into a valid style profile dict.

    Coerces out-of-enum values to a safe default instead of rejecting the
    whole result, so a sloppy LLM answer still yields a usable profile.
    """
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        data = json.loads(match.group() if match else text)
    except (json.JSONDecodeError, AttributeError) as e:
        raise LLMValidationError(f"Failed to parse style profile: {e}") from e

    identity = data.get("identity") if isinstance(data.get("identity"), dict) else {}
    sp = data.get("style_profile") if isinstance(data.get("style_profile"), dict) else {}
    facts = data.get("key_facts_and_preferences") or []

    def _enum(value, allowed, default):
        return value if isinstance(value, str) and value in allowed else default

    return {
        "identity": {
            "name": identity.get("name") or None,
            "role": identity.get("role") or None,
            "business_name": identity.get("business_name") or None,
        },
        "style_profile": {
            "formality": _enum(sp.get("formality"), VALID_STYLE_FORMALITY, "semi-formal"),
            "emoji_density": _enum(sp.get("emoji_density"), VALID_STYLE_EMOJI, "low"),
            "sentence_length": _enum(sp.get("sentence_length"), VALID_STYLE_LENGTH, "concise"),
            "tone": _enum(sp.get("tone"), VALID_STYLE_TONE, "professional_and_direct"),
            "key_phrases": [
                p for p in (sp.get("key_phrases") or [])
                if isinstance(p, str) and p.strip()
            ][:4],
        },
        "key_facts_and_preferences": [f for f in facts if isinstance(f, str) and f.strip()],
    }


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

    # 1. Numeric tokens — must all appear in source. Normalize thousand
    #    separators ("Rp 150.000" == "150000") so formatting never trips the
    #    hallucination check.
    def _norm_nums(text: str) -> set[str]:
        nums = set()
        for tok in re.findall(r"\d[\d.,]*", text):
            digits = re.sub(r"[.,]", "", tok)
            if digits:
                nums.add(digits)
        return nums

    reply_nums = _norm_nums(reply)
    source_nums = _norm_nums(source_text)
    invented_nums = reply_nums - source_nums
    if invented_nums:
        raise LLMValidationError(
            f"Reply contains numbers not in source: {sorted(invented_nums)}"
        )

    # 2. Sizes — S, M, L, XL, XXL, XXXL. A span like "M-XXL" expands to every
    #    size between its endpoints, so a reply naming "size L" when the source
    #    says "M-XXL" is accepted (L is in range, not a hallucination).
    size_pattern = r"\b(?:XXXL|XXL|XL|L|M|S|XS)\b"
    _SIZE_ORDER = ("XXXL", "XXL", "XL", "L", "M", "S", "XS")

    def _all_sizes(text: str) -> set:
        sizes = set(re.findall(size_pattern, text, flags=re.IGNORECASE))
        for lo, hi in re.findall(
            r"\b(XXXL|XXL|XL|L|M|S|XS)\s*[-–]\s*(XXXL|XXL|XL|L|M|S|XS)\b",
            text,
            flags=re.IGNORECASE,
        ):
            if lo.upper() in _SIZE_ORDER and hi.upper() in _SIZE_ORDER:
                i, j = _SIZE_ORDER.index(lo.upper()), _SIZE_ORDER.index(hi.upper())
                sizes |= set(_SIZE_ORDER[min(i, j): max(i, j) + 1])
        return sizes

    reply_sizes = _all_sizes(reply)
    source_sizes = _all_sizes(source_text)
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

    # 4. Price check — if the reply mentions a price, its VALUE must match a
    #    source price (thousand separators/whitespace ignored: "Rp 50.000" ==
    #    "Rp50000"). Different value → reject; same value → allow.
    def _price_value(tok: str) -> str:
        return re.sub(r"[^0-9]", "", tok)

    reply_prices = re.findall(r"Rp\s*[\d.,]+", reply)
    if reply_prices:
        source_prices = re.findall(r"Rp\s*[\d.,]+", source_text)
        if not source_prices:
            raise LLMValidationError(
                f"Reply mentions price but source has no price: {reply_prices}"
            )
        source_values = {_price_value(sp) for sp in source_prices}
        for rp in reply_prices:
            if _price_value(rp) not in source_values:
                raise LLMValidationError(
                    f"Reply price '{rp}' does not match any source price"
                )
