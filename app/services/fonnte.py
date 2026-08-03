"""Fonnte WhatsApp gateway implementation."""
import asyncio
import logging
from typing import Any

import httpx

from app.services.phone_gateway import PhoneGateway, PhoneGatewayException

logger = logging.getLogger(__name__)


class FonnteError(PhoneGatewayException):
    """Raised when Fonnete API call fails after retries."""


class FonnteGateway(PhoneGateway):
    """Async client for Fonnte WhatsApp Gateway.

    Endpoint: POST https://api.fonnte.com/send
    Auth: Authorization header with token (no Bearer prefix)
    Body: {"target": "62xxx", "message": "text"}
    """

    base_url = "https://api.fonnte.com"

    def __init__(self, api_key: str, max_retries: int = 3):
        self.api_key = api_key
        self.max_retries = max_retries

    async def send_message(self, phone: str, message: str) -> dict[str, Any]:
        """Send text message to a WhatsApp number via Fonnte.

        Retries 3x on 5xx with exponential backoff. Raises FonnteError after exhaustion.

        Args:
            phone: Phone number (with or without + prefix, e.g., "+6281234567890" or "6281234567890")
            message: Message text to send

        Returns:
            API response dict with status, message id, etc.
        """
        # Strip + prefix if present (Fonnte expects pure digits)
        target = phone.lstrip("+")

        url = f"{self.base_url}/send"
        headers = {
            "Authorization": self.api_key,  # Fonnte uses raw token, no Bearer prefix
        }
        payload = {
            "target": target,
            "message": message,
        }

        last_exception: Exception | None = None

        async with httpx.AsyncClient(timeout=10.0) as client:
            for attempt in range(1, self.max_retries + 1):
                try:
                    response = await client.post(url, headers=headers, data=payload)
                    if response.status_code >= 500:
                        raise FonnteError(f"Fonnte {response.status_code}")

                    # Don't retry on client errors (4xx) - raise immediately
                    if 400 <= response.status_code < 500:
                        raise FonnteError(f"Fonnte client error: {response.status_code}")

                    response.raise_for_status()
                    result = response.json()
                    # LOG FULL RESPONSE FOR DEBUGGING
                    logger.debug(
                        "FONNTE_RAW_RESPONSE",
                        extra={
                            "phone": phone,
                            "raw_result": result,
                            "all_keys": sorted(result.keys()),
                            "status_value": repr(result.get("status")),
                            "reason_value": repr(result.get("reason")),
                            "detail_value": repr(result.get("detail")),
                        },
                    )
                    logger.info(
                        "fonnte_api_response",
                        extra={
                            "phone": phone[-4:],
                            "response": result,
                            "status_field": result.get("status"),
                        },
                    )
                    # DEBUG: Check what status field actually exists
                    if result.get("status") is not True:
                        logger.debug(
                            "FONNTE_STATUS_CHECK",
                            extra={
                                "status": result.get("status"),
                                "all_keys": list(result.keys()),
                                "has_true_status": result.get("status") is True,
                                "reason_raw": result.get("reason"),
                                "detail_raw": result.get("detail"),
                            },
                        )
                        error_msg = result.get("reason") or result.get("detail") or "Unknown Fonnte error"
                        raise FonnteError(f"Fonnte API error: {error_msg}")
                    return result

                except FonnteError as e:
                    # Re-raise immediately for client errors (4xx), retry for server errors (5xx)
                    if "client error" in str(e) or (e.__cause__ is None and "4" in str(e)[:20]):
                        logger.error("FONNTE_CLIENT_ERROR", exc_info=True)
                        raise
                    last_exception = e
                    logger.warning(
                        "fonnte_send_attempt_failed",
                        extra={"attempt": attempt, "phone": phone[-4:], "error": str(e)},
                    )
                    logger.error("fonnte_exception_occurred", exc_info=True)
                    if attempt < self.max_retries:
                        await asyncio.sleep(0.1 * (2 ** (attempt - 1)))
                except httpx.HTTPStatusError as e:
                    # Don't retry on 4xx client errors
                    if e.response and 400 <= e.response.status_code < 500:
                        raise FonnteError(f"Fonnte client error: {e.response.status_code}") from e
                    last_exception = e
                    logger.warning(
                        "fonnte_send_attempt_failed",
                        extra={"attempt": attempt, "phone": phone[-4:], "error": str(e)},
                    )
                    if attempt < self.max_retries:
                        await asyncio.sleep(0.1 * (2 ** (attempt - 1)))
                except httpx.RequestError as e:
                    last_exception = e
                    logger.warning(
                        "fonnte_send_attempt_failed",
                        extra={"attempt": attempt, "phone": phone[-4:], "error": str(e)},
                    )
                    if attempt < self.max_retries:
                        await asyncio.sleep(0.1 * (2 ** (attempt - 1)))

        raise FonnteError(f"Failed after {self.max_retries} retries: {last_exception}")
