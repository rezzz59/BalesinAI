"""Fonnte WhatsApp gateway implementation."""
import asyncio
import logging
import random
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

    async def _post(self, path: str, payload: dict) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {"Authorization": self.api_key}
        last_err: httpx.RequestError | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.post(url, headers=headers, data=payload)
                break
            except httpx.RequestError as e:
                last_err = e
                logger.warning("fonnte_post_retry", extra={"path": path, "attempt": attempt, "error": str(e)})
                if attempt < self.max_retries:
                    await asyncio.sleep(0.1 * (2 ** (attempt - 1)))
        else:
            raise FonnteError(f"Fonnte connection error: {last_err}") from last_err
        if response.status_code >= 500:
            raise FonnteError(f"Fonnte {response.status_code}")
        if 400 <= response.status_code < 500:
            raise FonnteError(f"Fonnte client error: {response.status_code}")
        result = response.json()
        if result.get("status") is not True:
            reason = result.get("reason") or result.get("detail") or "Unknown Fonnte error"
            raise FonnteError(f"Fonnte API error: {reason}")
        return result

    async def add_device(self, name: str, device: str) -> dict[str, Any]:
        """Create a new device via API (needs the ACCOUNT token).

        Returns the device token plus metadata. Raises FonnteError on failure
        (e.g. device already exist, too much free device).
        """
        payload = {"name": name, "device": device, "autoread": "true"}
        return await self._post("/add-device", payload)

    async def get_qr(self, whatsapp: str, type_: str = "qr") -> dict[str, Any]:
        """Fetch the pairing QR for a device number. Returns base64 in 'url'."""
        payload = {"type": type_, "whatsapp": whatsapp}
        return await self._post("/qr", payload)

    async def typing(self, target: str, duration: int = 3, stop: bool = False) -> dict[str, Any]:
        """Simulate typing indicator on a conversation."""
        payload = {"target": target.lstrip("+"), "countryCode": "62", "duration": duration, "stop": str(stop).lower()}
        return await self._post("/typing", payload)

    async def device_profile(self) -> dict[str, Any]:
        """Return the actual device number + status for the current token.

        Uses the DEVICE token. 'device' in the response is the REAL WhatsApp
        number linked to the device (what the user scanned), not the label used
        at add-device time.
        """
        return await self._post("/device", {})

    async def get_devices(self) -> dict[str, Any]:
        """List all devices on the account (ACCOUNT token).

        Returns {'devices': int, 'connected': int, 'data': [...]}. Each item's
        'status' is 'connect'/'disconnect' — the real link state of the device,
        usable to validate that a QR scan actually connected.
        """
        return await self._post("/get-devices", {})

    async def disconnect(self) -> dict[str, Any]:
        """Disconnect the linked WhatsApp number from this device (DEVICE token).

        Unlinks whatever number is currently paired. The device itself stays so
        a new QR can be shown for re-scan.
        """
        return await self._post("/disconnect", {})

    async def send_message(
        self,
        phone: str,
        message: str,
        url: str | None = None,
        filename: str | None = None,
        typing: bool = False,
        delay: str | None = None,
        sequence: bool = False,
    ) -> dict[str, Any]:
        """Send a text (and optionally an attachment) via Fonnte.

        Retries 3x on 5xx with exponential backoff. Raises FonnteError after exhaustion.

        Args:
            phone: Phone number (with or without + prefix).
            message: Message text to send.
            url: Public URL of an attachment (image/file/pdf). Only available on
                Fonnte Super plan — used for the Pro tier (photo catalog, brosur).
            filename: Custom filename for non-image/video attachments.
            typing: Show a typing indicator before delivering.
            delay: Random send delay range, e.g. "2-5" seconds (human-like pacing).
            sequence: Send parts in strict order (no delays applied).
        """
        
        # Anti-Ban: Apply human delay before sending 
        # BalesinAI ensures that responses aren't blasted instantaneously.
        await self.simulate_human_delay(message)
        
        target = phone.lstrip("+")
        payload: dict[str, Any] = {"target": target, "message": message}
        if url:
            payload["url"] = url
        if filename:
            payload["filename"] = filename
        if typing:
            payload["typing"] = "true"
        if delay:
            payload["delay"] = str(delay)
        if sequence:
            payload["sequence"] = "true"

        last_exception: Exception | None = None

        async with httpx.AsyncClient(timeout=15.0) as client:
            for attempt in range(1, self.max_retries + 1):
                try:
                    response = await client.post(f"{self.base_url}/send", headers={"Authorization": self.api_key}, data=payload)
                    if response.status_code >= 500:
                        raise FonnteError(f"Fonnte {response.status_code}")
                    if 400 <= response.status_code < 500:
                        raise FonnteError(f"Fonnte client error: {response.status_code}")
                    response.raise_for_status()
                    result = response.json()
                    if result.get("status") is not True:
                        error_msg = result.get("reason") or result.get("detail") or "Unknown Fonnte error"
                        raise FonnteError(f"Fonnte API error: {error_msg}")
                    return result
                except FonnteError as e:
                    if "client error" in str(e) or (e.__cause__ is None and "4" in str(e)[:20]):
                        raise
                    last_exception = e
                    logger.warning("fonnte_send_attempt_failed", extra={"attempt": attempt, "phone": phone[-4:], "error": str(e)})
                    if attempt < self.max_retries:
                        await asyncio.sleep(0.1 * (2 ** (attempt - 1)))
                except httpx.HTTPStatusError as e:
                    if e.response and 400 <= e.response.status_code < 500:
                        raise FonnteError(f"Fonnte client error: {e.response.status_code}") from e
                    last_exception = e
                    if attempt < self.max_retries:
                        await asyncio.sleep(0.1 * (2 ** (attempt - 1)))
                except httpx.RequestError as e:
                    last_exception = e
                    if attempt < self.max_retries:
                        await asyncio.sleep(0.1 * (2 ** (attempt - 1)))

        raise FonnteError(f"Failed after {self.max_retries} retries: {last_exception}")

    async def send_attachment(self, phone: str, image_url: str, caption: str = "", typing: bool = True) -> dict[str, Any]:
        """Send a photo attachment as an actual image (not a link)."""
        return await self.send_message(phone=phone, message=caption, url=image_url, typing=typing)
