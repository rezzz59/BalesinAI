"""Tests for WAHA (self-hosted) device onboarding: QR, session status, reject mismatch."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock

from app.config import get_settings


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GATEWAY_PROVIDER", "waha")
    monkeypatch.setenv("WAHA_BASE_URL", "http://localhost:3000")
    monkeypatch.setenv("WAHA_API_KEY", "waha-secret")
    monkeypatch.setenv("ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_JSON_PATH", "dummy")
    get_settings.cache_clear()
    from app.main import app
    return TestClient(app)


@pytest.fixture
def mock_auth(monkeypatch):
    from app.db.models import User
    user = User(id=1, email="test@balesin.ai", tenant_id="t-waha")
    monkeypatch.setattr("app.api.onboard.current_user", lambda req: user)
    return user


@pytest.fixture
def mock_tenant(monkeypatch):
    tenant = {
        "tenant_id": "t-waha",
        "wa_api_key_encrypted": b"",
        "owner_wa_number": "6281",
        "business_type": "jualan",
        "onboarding_status": "pending",
        "data_source": "sheet",
        "fonnte_device_id": "",
        "device_status": "fresh",
    }
    monkeypatch.setattr("app.api.onboard._user_tenant", lambda user: tenant)
    monkeypatch.setattr("app.api.onboard.insert_or_update_tenant", lambda **kw: None)
    monkeypatch.setattr("app.api.onboard.update_device_status", lambda t, s: None)
    return tenant


def test_waha_provision_returns_qr(client, mock_auth, mock_tenant, monkeypatch):
    gw = MagicMock()
    gw.start_session = AsyncMock(return_value={"name": "t-waha"})
    gw.get_qr = AsyncMock(return_value="data:image/png;base64,AAAA")
    monkeypatch.setattr("app.services.waha.WahaGateway", lambda **kw: gw)

    res = client.post("/api/onboard/device", json={"device_wa": "08123456789"})

    assert res.status_code == 200
    data = res.json()
    assert data["qr"].startswith("data:image/png;base64")
    assert data["device"] == "628123456789"
    assert data["device_status"] == "pending"
    gw.start_session.assert_awaited_once()


def test_waha_status_connected_matching_number(client, mock_auth, mock_tenant, monkeypatch):
    mock_tenant["fonnte_device_id"] = "628123456789"
    mock_tenant["device_status"] = "pending"

    gw = MagicMock()
    gw.session_status = AsyncMock(return_value="WORKING")
    gw.device_profile = AsyncMock(return_value={"id": "628123456789@c.us"})
    monkeypatch.setattr("app.services.waha.WahaGateway", lambda **kw: gw)

    updated = []
    monkeypatch.setattr("app.api.onboard.update_device_status", lambda t, s: updated.append(s))

    res = client.get("/api/onboard/device/status")

    assert res.status_code == 200
    data = res.json()
    assert data["device_status"] == "connected"
    assert data["device_match"] is True
    assert "connected" in updated


def test_waha_status_rejects_mismatched_number(client, mock_auth, mock_tenant, monkeypatch):
    mock_tenant["fonnte_device_id"] = "628123456789"
    mock_tenant["device_status"] = "pending"

    gw = MagicMock()
    gw.session_status = AsyncMock(return_value="WORKING")
    gw.device_profile = AsyncMock(return_value={"id": "628999999999@c.us"})
    gw.logout = AsyncMock()
    monkeypatch.setattr("app.services.waha.WahaGateway", lambda **kw: gw)

    updated = []
    monkeypatch.setattr("app.api.onboard.update_device_status", lambda t, s: updated.append(s))

    res = client.get("/api/onboard/device/status")

    assert res.status_code == 200
    data = res.json()
    assert data["device_status"] == "rejected"
    assert data["device_match"] is False
    assert data["device"] == "628999999999"
    gw.logout.assert_awaited_once()
    assert "rejected" in updated


def test_waha_status_pending_when_scanning(client, mock_auth, mock_tenant, monkeypatch):
    mock_tenant["fonnte_device_id"] = "628123456789"
    mock_tenant["device_status"] = "pending"

    gw = MagicMock()
    gw.session_status = AsyncMock(return_value="SCAN_QR_CODE")
    monkeypatch.setattr("app.services.waha.WahaGateway", lambda **kw: gw)

    res = client.get("/api/onboard/device/status")

    assert res.status_code == 200
    assert res.json()["device_status"] == "pending"
