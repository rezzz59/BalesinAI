"""Tests for app.services.wablas."""
import pytest
from unittest.mock import AsyncMock, patch

from app.services.wablas import WablasClient, WablasError


@pytest.fixture
def client():
    return WablasClient(
        base_url="https://api.wablas.com",
        api_key="test-key-xyz",
        device_id="device-abc",
    )


def test_send_message_makes_post_request(client):
    with patch("app.services.wablas.httpx.AsyncClient") as mock_client_cls:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = lambda: {"status": "success", "message_id": "msg-123"}
        mock_response.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        import asyncio
        result = asyncio.run(
            client.send_message(phone="+6281234567890", message="Halo!")
        )

        assert result["status"] == "success"
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "v1/send-message" in call_args[0][0] or "send-message" in str(call_args)
        assert call_args[1]["headers"]["Authorization"] == "Bearer test-key-xyz"


def test_send_message_retries_on_5xx(client):
    with patch("app.services.wablas.httpx.AsyncClient") as mock_client_cls:
        mock_response_fail = AsyncMock()
        mock_response_fail.status_code = 503
        mock_response_fail.raise_for_status.side_effect = Exception("503")

        mock_response_ok = AsyncMock()
        mock_response_ok.status_code = 200
        mock_response_ok.json = lambda: {"status": "ok"}
        mock_response_ok.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=[mock_response_fail, mock_response_ok])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        import asyncio
        result = asyncio.run(
            client.send_message(phone="+628123", message="Hi")
        )

        assert result["status"] == "ok"
        assert mock_client.post.call_count == 2


def test_send_message_raises_after_max_retries(client):
    with patch("app.services.wablas.httpx.AsyncClient") as mock_client_cls:
        mock_response_fail = AsyncMock()
        mock_response_fail.status_code = 503
        mock_response_fail.raise_for_status.side_effect = Exception("503")

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response_fail)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        import asyncio
        with pytest.raises(WablasError):
            asyncio.run(client.send_message(phone="+628123", message="Hi"))