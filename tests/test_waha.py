"""Tests for WAHA WhatsApp gateway: send, retry 5xx, @c.us append, typing, send_attachment."""
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch, ANY

from app.services.waha import WahaGateway, WahaError
from app.services.phone_gateway import PhoneGateway


@pytest.fixture
def waha_gateway():
    return WahaGateway(base_url="http://localhost:3000", session_name="test-session")


def test_waha_implements_phone_gateway():
    assert issubclass(WahaGateway, PhoneGateway)


@pytest.mark.asyncio
async def test_waha_send_message_success(waha_gateway):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "sent", "id": "msg_123"}

    with patch("app.services.waha.httpx.AsyncClient") as mock_client:
        mock_post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.post = mock_post
        result = await waha_gateway.send_message(phone="6281234567890", message="Halo")

    assert result["status"] == "sent"


@pytest.mark.asyncio
async def test_waha_appends_suffix_at_sign_c_us(waha_gateway):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "sent"}

    with patch("app.services.waha.httpx.AsyncClient") as mock_client:
        mock_post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.post = mock_post
        await waha_gateway.send_message(phone="6281234567890", message="Test")

    send_call = [c for c in mock_post.call_args_list if "/api/sendText" in str(c)]
    assert len(send_call) > 0
    payload = send_call[0].kwargs.get("json")
    assert payload["chatId"] == "6281234567890@c.us"


@pytest.mark.asyncio
async def test_waha_strips_plus_prefix(waha_gateway):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "sent"}

    with patch("app.services.waha.httpx.AsyncClient") as mock_client:
        mock_post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.post = mock_post
        await waha_gateway.send_message(phone="+6281234567890", message="Test")

    send_calls = [c for c in mock_post.call_args_list if "/api/sendText" in str(c)]
    assert len(send_calls) > 0
    payload = send_calls[0].kwargs.get("json")
    assert payload["chatId"] == "6281234567890@c.us"


@pytest.mark.asyncio
async def test_waha_retries_on_5xx(waha_gateway):
    mock_5xx = MagicMock()
    mock_5xx.status_code = 500
    mock_5xx.text = "Server Error"

    mock_ok = MagicMock()
    mock_ok.status_code = 200
    mock_ok.json.return_value = {"status": "sent", "id": "retry_ok"}

    with patch("app.services.waha.httpx.AsyncClient") as mock_client:
        # startTyping ok, sendText 5xx (retry), sendText ok, stopTyping ok
        mock_post = AsyncMock(side_effect=[mock_ok, mock_5xx, mock_ok, mock_ok])
        mock_client.return_value.__aenter__.return_value.post = mock_post
        waha_gateway.max_retries = 3
        result = await waha_gateway.send_message(phone="6281234567890", message="Test")

    assert result["status"] == "sent"
    assert mock_post.call_count >= 3


@pytest.mark.asyncio
async def test_waha_raises_after_max_retries(waha_gateway):
    mock_5xx = MagicMock()
    mock_5xx.status_code = 503
    mock_5xx.text = "Service Unavailable"

    with patch("app.services.waha.httpx.AsyncClient") as mock_client:
        mock_post = AsyncMock(return_value=mock_5xx)
        mock_client.return_value.__aenter__.return_value.post = mock_post
        waha_gateway.max_retries = 2
        with pytest.raises(WahaError):
            await waha_gateway.send_message(phone="6281234567890", message="Test")


@pytest.mark.asyncio
async def test_waha_send_attachment_success(waha_gateway):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "sent"}

    with patch("app.services.waha.httpx.AsyncClient") as mock_client:
        mock_post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.post = mock_post
        result = await waha_gateway.send_attachment(
            phone="6281234567890", image_url="https://example.com/img.jpg", caption="Lihat"
        )

    assert result["status"] == "sent"
    file_calls = [c for c in mock_post.call_args_list if "/api/sendFile" in str(c)]
    assert len(file_calls) > 0
    payload = file_calls[0].kwargs.get("json")
    assert payload["file"]["url"] == "https://example.com/img.jpg"
    assert payload["caption"] == "Lihat"
    assert payload["chatId"] == "6281234567890@c.us"


@pytest.mark.asyncio
async def test_waha_attachment_appends_c_us_suffix(waha_gateway):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "sent"}

    with patch("app.services.waha.httpx.AsyncClient") as mock_client:
        mock_post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.post = mock_post
        await waha_gateway.send_attachment(phone="628999", image_url="https://x.com/p.jpg")

    file_calls = [c for c in mock_post.call_args_list if "/api/sendFile" in str(c)]
    assert len(file_calls) > 0
    payload = file_calls[0].kwargs.get("json")
    assert payload["chatId"] == "628999@c.us"


def test_waha_error_is_phone_gateway_exception():
    from app.services.phone_gateway import PhoneGatewayException
    assert issubclass(WahaError, PhoneGatewayException)