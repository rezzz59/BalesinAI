import asyncio
import logging
from typing import Any
import httpx

from app.services.phone_gateway import PhoneGateway, PhoneGatewayException

logger = logging.getLogger(__name__)

class WahaError(PhoneGatewayException):
    """Raised when WAHA API call fails."""

class WahaGateway(PhoneGateway):
    """Async client for WAHA (WhatsApp HTTP API) Gateway.
    
    WAHA is a self-hosted engine based on Baileys. It provides a more robust
    and safe alternative to shared-IP providers like Fonnte.
    
    Endpoint: POST {base_url}/api/sendText
    Body: {"chatId": "62xxx@c.us", "text": "message", "session": "default"}
    """
    
    def __init__(self, base_url: str, session_name: str = "default", api_key: str = "", max_retries: int = 3):
        self.base_url = base_url.rstrip("/")
        self.session_name = session_name
        self.api_key = api_key
        self.max_retries = max_retries
        
    async def _request(self, method: str, path: str, payload: dict | None = None) -> Any:
        """Raw HTTP call to WAHA; returns parsed JSON or the raw response body."""
        url = f"{self.base_url}{path}"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["X-Api-Key"] = self.api_key

        async with httpx.AsyncClient(timeout=15.0) as client:
            if method == "GET":
                response = await client.get(url, headers=headers)
            elif method == "DELETE":
                response = await client.delete(url, headers=headers)
            else:
                response = await client.post(url, headers=headers, json=payload or {})

        if response.status_code >= 500:
            raise WahaError(f"WAHA Gateway Error {response.status_code}: {response.text}")
        try:
            return response.json()
        except ValueError:
            return {"status": False, "reason": "invalid json", "body": response.text}

    async def _post(self, path: str, payload: dict) -> dict[str, Any]:
        return await self._request("POST", path, payload)

    async def start_session(self, webhook_url: str = "") -> dict[str, Any]:
        """Create (or ensure) this tenant's session. Returns the WAHA session object.

        The session's webhook is pointed at our inbound endpoint so messages
        arrive as soon as the number is paired.
        """
        payload: dict[str, Any] = {"name": self.session_name}
        if webhook_url:
            payload["config"] = {
                "webhooks": [
                    {"url": webhook_url, "events": ["message"]},
                ],
            }
        try:
            return await self._post("/api/sessions", payload)
        except WahaError:
            # Session already exists (WAHA 409) — treat as idempotent.
            logger.info("waha_session_exists", extra={"session": self.session_name})
            return {"name": self.session_name, "status": "exists"}

    async def get_qr(self) -> str | None:
        """Return the QR code as a base64 data URI, or None when not scannable."""
        res = await self._request("GET", f"/api/sessions/{self.session_name}/qr")
        if isinstance(res, str) and res:
            return res
        if isinstance(res, dict):
            return res.get("qr") or res.get("data") or res.get("image") or None
        return None

    async def session_status(self) -> str:
        """Return WAHA session status: WORKING | SCAN_QR_CODE | STOPPED | ..."""
        res = await self._request("GET", f"/api/sessions/{self.session_name}")
        if isinstance(res, dict):
            status = res.get("status")
            if status:
                return str(status)
            # Some WAHA versions only expose the paired identity (no status).
            return "WORKING" if res.get("me") else "SCAN_QR_CODE"
        return "STOPPED"

    async def device_profile(self) -> dict[str, Any]:
        """Return the paired device's profile (scanned number)."""
        res = await self._request("GET", f"/api/sessions/{self.session_name}/me")
        if isinstance(res, dict):
            return res
        return {}

    async def logout(self) -> dict[str, Any]:
        """Disconnect/delete the session (used to reject a mismatched number)."""
        return await self._request("DELETE", f"/api/sessions/{self.session_name}")

    async def send_message(self, phone: str, message: str) -> dict[str, Any]:
        """Send a text message via WAHA."""
        # 1. Anti-Ban Human Delay Simulator
        await self.simulate_human_delay(message)
        
        # WAHA requires chat IDs to be appended with '@c.us'
        target = phone.lstrip("+")
        if not target.endswith("@c.us"):
            target = f"{target}@c.us"
            
        payload = {
            "chatId": target,
            "text": message,
            "session": self.session_name
        }
        
        # 2. Trigger typing indicator for extra safety
        try:
            typing_payload = {"chatId": target, "session": self.session_name}
            await self._post("/api/startTyping", typing_payload)
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.debug(f"WAHA startTyping failed (ignoring): {e}")
            
        # 3. Send message with retry logic
        for attempt in range(self.max_retries):
            try:
                res = await self._post("/api/sendText", payload)
                
                # Stop typing indicator
                try:
                    await self._post("/api/stopTyping", typing_payload)
                except Exception:
                    pass
                    
                return res
            except httpx.RequestError as e:
                logger.warning(f"WAHA HTTP error (attempt {attempt+1}): {e}")
                if attempt == self.max_retries - 1:
                    raise WahaError(f"WAHA HTTP Error after {self.max_retries} retries: {e}") from e
                await asyncio.sleep(2 ** attempt)
            except WahaError as e:
                logger.warning(f"WAHA server error (attempt {attempt+1}): {e}")
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)
                
        raise WahaError("Max retries exceeded")

    async def send_attachment(self, phone: str, image_url: str, caption: str = "") -> dict[str, Any]:
        """Send an image via WAHA."""
        target = phone.lstrip("+")
        if not target.endswith("@c.us"):
            target = f"{target}@c.us"
            
        payload = {
            "chatId": target,
            "session": self.session_name,
            "file": {"url": image_url},
            "caption": caption
        }
        
        for attempt in range(self.max_retries):
            try:
                return await self._post("/api/sendFile", payload)
            except (httpx.RequestError, WahaError) as e:
                if attempt == self.max_retries - 1:
                    raise WahaError(f"WAHA Attachment Error: {e}") from e
                await asyncio.sleep(2 ** attempt)
                
        raise WahaError("Max retries exceeded")
