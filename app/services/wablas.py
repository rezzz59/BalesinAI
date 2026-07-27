"""Wablas API client adapter."""
import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class WablasError(Exception):
    """Raised when Wablas API call fails after retries."""


class WablasClient:
    """Async client for Wablas WhatsApp API.

    Endpoint: POST /api/v1/send-message
    Auth: Bearer <api_key> header
    Body: {"phone": "+62xxx", "message": "text"}
    """

    def __init__(self, base_url: str, api_key: str, device_id: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.device_id = device_id
        self.max_retries = 3

    async def send_message(self, phone: str, message: str) -> dict[str, Any]:
        """Send text message to a WhatsApp number. Returns API response dict.

        Retries 3x on 5xx with exponential backoff. Raises WablasError after exhaustion.
        """
        url = f"{self.base_url}/api/v1/send-message"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"phone": phone, "message": message}
        if self.device_id:
            payload["device_id"] = self.device_id

        last_exception: Exception | None = None

        async with httpx.AsyncClient(timeout=10.0) as client:
            for attempt in range(1, self.max_retries + 1):
                try:
                    response = await client.post(url, headers=headers, json=payload)
                    if response.status_code >= 500:
                        raise WablasError(f"Wablas {response.status_code}")

                    response.raise_for_status()
                    return response.json()

                except (httpx.HTTPStatusError, WablasError, httpx.RequestError) as e:
                    last_exception = e
                    logger.warning(
                        "wablas_send_attempt_failed",
                        extra={"attempt": attempt, "phone": phone[-4:], "error": str(e)},
                    )
                    if attempt < self.max_retries:
                        await asyncio.sleep(0.1 * (2 ** (attempt - 1)))

        raise WablasError(f"Failed after {self.max_retries} retries: {last_exception}")