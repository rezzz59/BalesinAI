"""Tests for device onboarding: QR, connection status, number mismatch rejection."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch, AsyncMock

from app.config import get_settings


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("FONNTE_ACCOUNT_TOKEN", "test-account-token")
    monkeypatch.setenv("GATEWAY_PROVIDER", "fonnte")  # this file tests the Fonnte path
    monkeypatch.setenv("ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_JSON_PATH", "dummy")
    get_settings.cache_clear()
    from app.main import app
    return TestClient(app)


@pytest.fixture
def mock_auth(monkeypatch):
    from app.db.models import User
    user = User(id=1, email="test@balesin.ai", tenant_id="t-123")
    monkeypatch.setattr("app.api.onboard.current_user", lambda req: user)
    return user


@pytest.fixture
def mock_tenant(monkeypatch):
    tenant = {
        "tenant_id": "t-123",
        "wa_api_key_encrypted": b"",
        "owner_wa_number": "6281",
        "business_type": "jualan",
        "onboarding_status": "pending",
        "data_source": "sheet",
        "fonnte_device_id": "",
        "device_status": "fresh"
    }
    monkeypatch.setattr("app.api.onboard._user_tenant", lambda user: tenant)
    monkeypatch.setattr("app.api.onboard.insert_or_update_tenant", lambda **kw: None)
    monkeypatch.setattr("app.api.onboard.update_device_status", lambda t, s: None)
    return tenant


def test_device_provision_creates_device_and_qr(client, mock_auth, mock_tenant, monkeypatch):
    mock_acct_gw = MagicMock()
    mock_acct_gw.add_device = AsyncMock(return_value={"token": "dev-token-123"})
    
    mock_dev_gw = MagicMock()
    mock_dev_gw.get_qr = AsyncMock(return_value={"url": "base64qrdata"})
    
    def _mock_gw(api_key, **kw):
        if api_key == "test-account-token":
            return mock_acct_gw
        return mock_dev_gw
        
    monkeypatch.setattr("app.services.fonnte.FonnteGateway", _mock_gw)
    
    res = client.post("/api/onboard/device", json={"device_wa": "08123456789"})
    
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["qr"] == "base64qrdata"
    assert data["device"] == "628123456789"
    assert data["device_status"] == "pending"
    
    assert mock_acct_gw.add_device.call_count == 1
    assert mock_dev_gw.get_qr.call_count == 1


def test_device_provision_handles_already_connect(client, mock_auth, mock_tenant, monkeypatch):
    from app.services.fonnte import FonnteError
    
    mock_dev_gw = MagicMock()
    mock_dev_gw.get_qr = AsyncMock(side_effect=FonnteError("device already connect"))
    
    monkeypatch.setattr("app.services.fonnte.FonnteGateway", lambda api_key, **kw: mock_dev_gw)
    # Give it an encrypted key to bypass add_device
    from app.services.crypto import encrypt_api_key
    mock_tenant["wa_api_key_encrypted"] = encrypt_api_key("dev-token", get_settings().encryption_key)
    
    res = client.post("/api/onboard/device", json={"device_wa": "08123456789"})
    
    assert res.status_code == 200
    data = res.json()
    assert data["device_status"] == "connected"


def test_device_status_validates_real_number_and_rejects_mismatch(client, mock_auth, mock_tenant, monkeypatch):
    mock_tenant["device_status"] = "pending"
    mock_tenant["fonnte_device_id"] = "628123456789" # INTENDED
    
    from app.services.crypto import encrypt_api_key
    mock_tenant["wa_api_key_encrypted"] = encrypt_api_key("dev-token", get_settings().encryption_key)
    
    mock_acct_gw = MagicMock()
    mock_acct_gw.get_devices = AsyncMock(return_value={
        "data": [{"device": "628123456789", "status": "connect"}]
    })
    
    mock_dev_gw = MagicMock()
    # RETURN A DIFFERENT REAL NUMBER!
    mock_dev_gw.device_profile = AsyncMock(return_value={"device": "628999999999"})
    mock_dev_gw.disconnect = AsyncMock()
    
    def _mock_gw(api_key, **kw):
        if api_key == "test-account-token":
            return mock_acct_gw
        return mock_dev_gw
        
    monkeypatch.setattr("app.services.fonnte.FonnteGateway", _mock_gw)
    
    updated_status = []
    monkeypatch.setattr("app.api.onboard.update_device_status", lambda t, s: updated_status.append(s))
    
    res = client.get("/api/onboard/device/status")
    
    assert res.status_code == 200
    data = res.json()
    
    # Assert mismatch is detected and rejected
    assert data["device_status"] == "rejected"
    assert data["device_match"] is False
    assert data["device"] == "628999999999" # Reports the real scanned number
    
    assert mock_dev_gw.disconnect.call_count == 1
    assert "rejected" in updated_status


def test_device_status_validates_real_number_success(client, mock_auth, mock_tenant, monkeypatch):
    mock_tenant["device_status"] = "pending"
    mock_tenant["fonnte_device_id"] = "628123456789" # INTENDED
    
    from app.services.crypto import encrypt_api_key
    mock_tenant["wa_api_key_encrypted"] = encrypt_api_key("dev-token", get_settings().encryption_key)
    
    mock_acct_gw = MagicMock()
    mock_acct_gw.get_devices = AsyncMock(return_value={
        "data": [{"device": "628123456789", "status": "connect"}]
    })
    
    mock_dev_gw = MagicMock()
    # MATCHES intended
    mock_dev_gw.device_profile = AsyncMock(return_value={"device": "628123456789"})
    mock_dev_gw.disconnect = AsyncMock()
    
    def _mock_gw(api_key, **kw):
        if api_key == "test-account-token":
            return mock_acct_gw
        return mock_dev_gw
        
    monkeypatch.setattr("app.services.fonnte.FonnteGateway", _mock_gw)
    
    updated_status = []
    monkeypatch.setattr("app.api.onboard.update_device_status", lambda t, s: updated_status.append(s))
    
    res = client.get("/api/onboard/device/status")
    
    assert res.status_code == 200
    data = res.json()
    
    assert data["device_status"] == "connected"
    assert data["device_match"] is True
    assert mock_dev_gw.disconnect.call_count == 0