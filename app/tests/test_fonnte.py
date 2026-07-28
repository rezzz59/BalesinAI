"""Tests for Fonnte WhatsApp gateway implementation."""
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.fonnte import FonnteGateway, FonnteError
from app.services.phone_gateway import PhoneGateway


@pytest.fixture
def fonnte_gateway():
    return FonnteGateway(api_key="test_fonnte_key_abc123")


def test_fonnte_implements_phone_gateway():
    """Fonnte should implement the PhoneGateway interface."""
    g = FonnteGateway(api_key="test_key")
    assert isinstance(g, PhoneGateway)


@pytest.mark.asyncio
async def test_fonnte_send_message_success(fonnte_gateway):
    """Test successful message send."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": True,
        "id": "msg_123",
        "detail": "Message sent"
    }

    with patch("app.services.fonnte.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )

        result = await fonnte_gateway.send_message(
            phone="+6281234567890",
            message="Hello from Fonnte"
        )

        assert result["status"] is True
        assert result["id"] == "msg_123"


@pytest.mark.asyncio
async def test_fonnte_strips_plus_in_request(fonnte_gateway):
    """Verify + prefix is stripped before sending to Fonnte."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": True, "id": "msg_999"}

    with patch("app.services.fonnte.httpx.AsyncClient") as mock_client:
        mock_post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.post = mock_post

        await fonnte_gateway.send_message(
            phone="+6281234567890",
            message="Test"
        )

        call_args = mock_post.call_args
        payload = call_args.kwargs.get("data")
        assert payload["target"] == "6281234567890"  # No + prefix


@pytest.mark.asyncio
async def test_fonnte_uses_authorization_header(fonnte_gateway):
    """Fonnte requires Authorization header with raw token (no Bearer prefix)."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": True, "id": "msg_888"}

    with patch("app.services.fonnte.httpx.AsyncClient") as mock_client:
        mock_post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.post = mock_post

        await fonnte_gateway.send_message(
            phone="6281234567890",
            message="Test auth"
        )

        call_args = mock_post.call_args
        headers = call_args.kwargs.get("headers")
        assert headers["Authorization"] == "test_fonnte_key_abc123"
        # Verify no Bearer prefix
        assert not headers["Authorization"].startswith("Bearer ")


@pytest.mark.asyncio
async def test_fonnte_retries_on_5xx(fonnte_gateway):
    """Should retry up to 3 times on 5xx errors."""
    mock_response_5xx = MagicMock()
    mock_response_5xx.status_code = 500

    mock_response_ok = MagicMock()
    mock_response_ok.status_code = 200
    mock_response_ok.json.return_value = {"status": True, "id": "msg_retry"}

    with patch("app.services.fonnte.httpx.AsyncClient") as mock_client:
        # First 2 calls fail, 3rd succeeds
        mock_post = AsyncMock(side_effect=[
            mock_response_5xx,
            mock_response_5xx,
            mock_response_ok,
        ])
        mock_client.return_value.__aenter__.return_value.post = mock_post

        result = await fonnte_gateway.send_message(
            phone="6281234567890",
            message="Test retry"
        )

        assert result["status"] is True
        assert mock_post.call_count == 3


@pytest.mark.asyncio
async def test_fonnte_raises_after_max_retries(fonnte_gateway):
    """Should raise FonnteError after 3 failed attempts."""
    mock_response_5xx = MagicMock()
    mock_response_5xx.status_code = 503

    with patch("app.services.fonnte.httpx.AsyncClient") as mock_client:
        mock_post = AsyncMock(return_value=mock_response_5xx)
        mock_client.return_value.__aenter__.return_value.post = mock_post

        with pytest.raises(FonnteError):
            await fonnte_gateway.send_message(
                phone="6281234567890",
                message="Test failure"
            )

        assert mock_post.call_count == 3


@pytest.mark.asyncio
async def test_fonnte_raises_on_4xx(fonnte_gateway):
    """Should not retry on 4xx errors (client error)."""
    mock_response_4xx = MagicMock()
    mock_response_4xx.status_code = 400
    # Mock raise_for_status to raise HTTPStatusError like httpx does for 4xx responses
    def raise_for_status():
        raise httpx.HTTPStatusError(
            "Client error", request=None, response=mock_response_4xx
        )
    mock_response_4xx.raise_for_status = raise_for_status

    with patch("app.services.fonnte.httpx.AsyncClient") as mock_client:
        mock_post = AsyncMock(return_value=mock_response_4xx)
        mock_client.return_value.__aenter__.return_value.post = mock_post

        with pytest.raises(FonnteError):
            await fonnte_gateway.send_message(
                phone="6281234567890",
                message="Test bad request"
            )

        # 4xx should fail fast (no retry)
        assert mock_post.call_count == 1


@pytest.mark.asyncio
async def test_fonnte_raises_on_api_status_false(fonnte_gateway):
    """Should raise if Fonnte returns status=False."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": False,
        "detail": "Invalid phone number"
    }

    with patch("app.services.fonnte.httpx.AsyncClient") as mock_client:
        mock_post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.post = mock_post

        with pytest.raises(FonnteError, match="Invalid phone number"):
            await fonnte_gateway.send_message(
                phone="628invalid",
                message="Test"
            )


def test_fonnte_error_is_phone_gateway_exception():
    """FonnteError should be a subclass of PhoneGatewayException."""
    from app.services.phone_gateway import PhoneGatewayException
    assert issubclass(FonnteError, PhoneGatewayException)
