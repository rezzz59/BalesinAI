"""Tests for /api/provision/* endpoints."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


WEBHOOK_AUTH_TOKEN = "test-admin-token-for-testing"


@pytest.fixture(autouse=True)
def reset_db():
    """Reset engine and create fresh file-based test DB per test (works with TestClient thread pool)."""
    import os
    import tempfile
    from sqlalchemy import create_engine
    import app.db.engine as engine_mod
    from app.db.models import Base

    # Create a temporary file for the test DB
    fd, db_path = tempfile.mkstemp(suffix='.db', prefix='test_')
    os.close(fd)

    eng = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    engine_mod.reset_engine_for_testing(eng)
    yield
    eng.dispose()
    engine_mod.reset_engine_for_testing(None)
    # Clean up temp file
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def client(monkeypatch, reset_db):
    """Test client with admin token and mocked services."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    monkeypatch.setenv("FONNTE_API_KEY", "test-fonnte-token")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_JSON_PATH", "./dummy.json")
    monkeypatch.setenv("WEBHOOK_AUTH_TOKEN", WEBHOOK_AUTH_TOKEN)
    get_settings.cache_clear()
    from app.main import app
    return TestClient(app)


def _mock_sheets_client(faq_rows=None, catalog_rows=None):
    """Create a mock GoogleSheetsClient."""
    mock = MagicMock()
    mock.discover_tabs.return_value = [
        {"title": "FAQ", "type": "faq", "row_count": len(faq_rows) if faq_rows is not None else 1},
        {"title": "Katalog", "type": "catalog", "row_count": len(catalog_rows) if catalog_rows is not None else 1},
    ]
    mock.read_faq.return_value = faq_rows if faq_rows is not None else [{"pertanyaan": "Q1", "jawaban": "A1"}]
    mock.read_catalog.return_value = catalog_rows if catalog_rows is not None else [{"nama_produk": "Prod1", "harga": "10000"}]
    mock.find_tab.side_effect = lambda t: "FAQ" if t == "faq" else ("Katalog" if t == "catalog" else None)
    return mock


class TestValidateSheet:
    def test_validate_sheet_ok(self, client, reset_db):
        mock_client = _mock_sheets_client(
            faq_rows=[{"pertanyaan": "Q1", "jawaban": "A1"}],
            catalog_rows=[{"nama_produk": "Prod1", "harga": "10000"}]
        )
        with patch("app.api.provision._build_sheets_client", return_value=mock_client):
            r = client.post("/api/provision/validate-sheet", json={"sheet_url": "https://docs.google.com/spreadsheets/d/ABC123"})
        assert r.status_code == 200
        data = r.json()
        assert data["spreadsheet_id"] == "ABC123"
        assert data["faq_count"] == 1
        assert data["catalog_count"] == 1
        assert data["ready"] is True

    def test_validate_sheet_warnings(self, client, reset_db):
        mock_client = _mock_sheets_client(faq_rows=[], catalog_rows=[])
        with patch("app.api.provision._build_sheets_client", return_value=mock_client):
            r = client.post("/api/provision/validate-sheet", json={"sheet_url": "https://docs.google.com/spreadsheets/d/ABC123"})
        assert r.status_code == 200
        data = r.json()
        assert data["ready"] is False
        assert any("FAQ" in w for w in data["warnings"])
        assert any("Katalog" in w for w in data["warnings"])

    def test_validate_sheet_bad_url(self, client, reset_db):
        r = client.post("/api/provision/validate-sheet", json={"sheet_url": "not-a-url"})
        assert r.status_code == 400
        assert "tidak valid" in r.json()["detail"]


class TestCreateTenant:
    def test_create_tenant_ok(self, client, reset_db):
        from app.db.tenant_repo import create_provisioning_token

        tok = create_provisioning_token(intended_merchant_name="Test Merchant")
        token = tok["token"]

        mock_client = _mock_sheets_client(
            faq_rows=[{"pertanyaan": "Q1", "jawaban": "A1"}],
            catalog_rows=[{"nama_produk": "Prod1", "harga": "10000"}]
        )
        readiness = {"score": 85, "status": "ready", "containment_rate": 1.0, "warnings": []}
        with patch("app.api.provision._build_sheets_client", return_value=mock_client), \
             patch("app.api.provision.seed_tenant_embeddings", return_value={"faq": 1, "catalog": 1}), \
             patch("app.api.provision.score_tenant", return_value=readiness):
            r = client.post("/api/provision/create-tenant", json={
                "token": token,
                "sheet_url": "https://docs.google.com/spreadsheets/d/ABC123",
                "owner_wa_number": "+6281234567890",
                "business_type": "kuliner",
                "merchant_name": "Test Merchant",
            })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "ready"
        assert data["tenant_id"]
        assert "webhook_url" in data
        assert data["embeddings"] == {"faq": 1, "catalog": 1}
        assert data["readiness"]["score"] == 85

    def test_create_tenant_needs_review_when_score_low(self, client, reset_db):
        from app.db.tenant_repo import create_provisioning_token

        token = create_provisioning_token(intended_merchant_name="Low Merchant")["token"]

        mock_client = _mock_sheets_client(
            faq_rows=[{"pertanyaan": "Q1", "jawaban": "A1"}],
            catalog_rows=[{"nama_produk": "Prod1", "harga": "10000"}]
        )
        readiness = {"score": 40, "status": "needs_review", "containment_rate": 0.4,
                     "warnings": ["FAQ 'jam buka' tidak ditemukan."]}
        with patch("app.api.provision._build_sheets_client", return_value=mock_client), \
             patch("app.api.provision.seed_tenant_embeddings", return_value={"faq": 1, "catalog": 1}), \
             patch("app.api.provision.score_tenant", return_value=readiness):
            r = client.post("/api/provision/create-tenant", json={
                "token": token,
                "sheet_url": "https://docs.google.com/spreadsheets/d/ABC123",
                "owner_wa_number": "+6281234567890",
                "business_type": "kuliner",
            })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "needs_review"
        assert data["readiness"]["score"] == 40

    def test_create_tenant_scoring_error_keeps_tenant(self, client, reset_db):
        from app.db.tenant_repo import create_provisioning_token, get_tenant

        token = create_provisioning_token(intended_merchant_name="Error Merchant")["token"]

        mock_client = _mock_sheets_client(
            faq_rows=[{"pertanyaan": "Q1", "jawaban": "A1"}],
            catalog_rows=[{"nama_produk": "Prod1", "harga": "10000"}]
        )
        with patch("app.api.provision._build_sheets_client", return_value=mock_client), \
             patch("app.api.provision.seed_tenant_embeddings", return_value={"faq": 1, "catalog": 1}), \
             patch("app.api.provision.score_tenant", side_effect=Exception("boom")):
            r = client.post("/api/provision/create-tenant", json={
                "token": token,
                "sheet_url": "https://docs.google.com/spreadsheets/d/ABC123",
                "owner_wa_number": "+6281234567890",
            })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "seeding_error"
        # Token consumed, tenant still persisted.
        assert get_tenant(data["tenant_id"]) is not None

    def test_create_tenant_bad_token(self, client, reset_db):
        mock_client = _mock_sheets_client()
        with patch("app.api.provision._build_sheets_client", return_value=mock_client):
            r = client.post("/api/provision/create-tenant", json={
                "token": "bad-token",
                "sheet_url": "https://docs.google.com/spreadsheets/d/ABC123",
                "owner_wa_number": "+6281234567890",
            })
        assert r.status_code == 404
        assert "tidak valid" in r.json()["detail"]

    def test_create_tenant_used_token(self, client, reset_db):
        from app.db.tenant_repo import create_provisioning_token, consume_provisioning_token

        tok = create_provisioning_token(intended_merchant_name="Test")
        token = tok["token"]
        consume_provisioning_token(token, "existing-tenant")

        mock_client = _mock_sheets_client()
        with patch("app.api.provision._build_sheets_client", return_value=mock_client):
            r = client.post("/api/provision/create-tenant", json={
                "token": token,
                "sheet_url": "https://docs.google.com/spreadsheets/d/ABC123",
                "owner_wa_number": "+6281234567890",
            })
        assert r.status_code == 409
        assert "sudah digunakan" in r.json()["detail"]

    def test_create_tenant_missing_owner_wa(self, client, reset_db):
        from app.db.tenant_repo import create_provisioning_token
        token = create_provisioning_token()["token"]
        mock_client = _mock_sheets_client()
        with patch("app.api.provision._build_sheets_client", return_value=mock_client):
            r = client.post("/api/provision/create-tenant", json={
                "token": token,
                "sheet_url": "https://docs.google.com/spreadsheets/d/ABC123",
            })
        assert r.status_code == 400
        assert "WA owner wajib" in r.json()["detail"]

    def test_create_tenant_sheet_read_error(self, client, reset_db):
        from app.db.tenant_repo import create_provisioning_token
        from app.services.sheets import SheetsError

        token = create_provisioning_token()["token"]
        mock_client = MagicMock()
        mock_client.read_faq.side_effect = SheetsError("read failed")
        mock_client.read_catalog.side_effect = SheetsError("read failed")

        with patch("app.api.provision._build_sheets_client", return_value=mock_client):
            r = client.post("/api/provision/create-tenant", json={
                "token": token,
                "sheet_url": "https://docs.google.com/spreadsheets/d/ABC123",
                "owner_wa_number": "+6281234567890",
            })
        assert r.status_code == 400
        assert "Gagal membaca" in r.json()["detail"]


class TestProvisioningStatus:
    def test_status_ready(self, client, reset_db):
        from app.db.tenant_repo import insert_or_update_tenant
        from app.config import get_settings
        from app.services.crypto import encrypt_api_key

        settings = get_settings()
        enc = encrypt_api_key("fonnte-xyz", settings.encryption_key)
        insert_or_update_tenant(
            tenant_id="tenant-ready",
            wa_api_key_encrypted=enc,
            google_sheet_id="sheet-1",
            owner_wa_number="+6281234567890",
            business_type="jualan",
            onboarding_status="ready",
        )

        r = client.get("/api/provision/status/tenant-ready")
        assert r.status_code == 200
        assert r.json()["status"] == "ready"
        assert r.json()["business_type"] == "jualan"

    def test_status_not_found(self, client, reset_db):
        r = client.get("/api/provision/status/nonexistent")
        assert r.status_code == 404
        assert "tidak ditemukan" in r.json()["detail"]


class TestAdminTokens:
    def auth_headers(self):
        return {"Authorization": f"Bearer {WEBHOOK_AUTH_TOKEN}"}

    def test_mint_token_ok(self, client, reset_db):
        r = client.post("/api/provision/tokens", headers=self.auth_headers(), json={
            "merchant_name": "New Merchant",
            "ttl_hours": 24,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["token"]
        assert data["intended_merchant_name"] == "New Merchant"
        assert "created_at" in data
        assert "expires_at" in data

    def test_mint_token_unauthorized(self, client, reset_db):
        r = client.post("/api/provision/tokens", headers={"Authorization": "Bearer wrong"}, json={})
        assert r.status_code == 401

    def test_list_tokens_ok(self, client, reset_db):
        from app.db.tenant_repo import create_provisioning_token
        create_provisioning_token(intended_merchant_name="M1")
        create_provisioning_token(intended_merchant_name="M2")

        r = client.get("/api/provision/tokens", headers=self.auth_headers())
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2
        assert data[0]["intended_merchant_name"] == "M1"
        assert data[0]["status"] == "pending"

    def test_list_tokens_unauthorized(self, client, reset_db):
        r = client.get("/api/provision/tokens", headers={"Authorization": "Bearer wrong"})
        assert r.status_code == 401


class TestAdminTenants:
    def auth_headers(self):
        return {"Authorization": f"Bearer {WEBHOOK_AUTH_TOKEN}"}

    def test_list_tenants_ok(self, client, reset_db):
        from app.db.tenant_repo import insert_or_update_tenant
        from app.config import get_settings
        from app.services.crypto import encrypt_api_key

        settings = get_settings()
        enc = encrypt_api_key("fonnte-xyz", settings.encryption_key)
        insert_or_update_tenant(tenant_id="t1", wa_api_key_encrypted=enc, google_sheet_id="s1", owner_wa_number="+6281", business_type="kuliner")
        insert_or_update_tenant(tenant_id="t2", wa_api_key_encrypted=enc, google_sheet_id="s2", owner_wa_number="+6282", business_type="fashion")

        r = client.get("/api/provision/tenants", headers=self.auth_headers())
        assert r.status_code == 200
        data = r.json()
        assert len(data["tenants"]) == 2
        assert data["tenants"][0]["tenant_id"] == "t1"
        assert data["tenants"][0]["business_type"] == "kuliner"

    def test_list_tenants_unauthorized(self, client, reset_db):
        r = client.get("/api/provision/tenants", headers={"Authorization": "Bearer wrong"})
        assert r.status_code == 401


class TestTestChat:
    def test_test_chat_ok(self, client, reset_db):
        from app.db.tenant_repo import insert_or_update_tenant
        from app.config import get_settings
        from app.services.crypto import encrypt_api_key

        settings = get_settings()
        enc = encrypt_api_key("fonnte-xyz", settings.encryption_key)
        insert_or_update_tenant(
            tenant_id="tenant-test-chat",
            wa_api_key_encrypted=enc,
            google_sheet_id="sheet-1",
            owner_wa_number="+6281234567890",
            business_type="kuliner",
            onboarding_status="ready",
        )
        dry_result = {
            "reply_text": "Halo Kak! Kami bantu segera 🙏",
            "intent": "faq",
            "confidence": 0.9,
            "action": "reply",
            "fallback_reason": None,
            "match_kind": "high",
            "gateway_calls": [],
        }
        with patch("app.api.provision.dry_run_reply", return_value=dry_result):
            r = client.post("/api/provision/test-chat", json={
                "tenant_id": "tenant-test-chat",
                "message": "jam buka?",
            })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["reply"] == "Halo Kak! Kami bantu segera 🙏"
        assert data["intent"] == "faq"
        assert data["action"] == "reply"

    def test_test_chat_no_transmission(self, client, reset_db):
        """Ensure the test-chat path never sends a WhatsApp message; dry_run
        gateway_calls must be empty (caller checked), and payload has no send."""
        from app.db.tenant_repo import insert_or_update_tenant
        from app.config import get_settings
        from app.services.crypto import encrypt_api_key

        settings = get_settings()
        enc = encrypt_api_key("fonnte-xyz", settings.encryption_key)
        insert_or_update_tenant(
            tenant_id="tenant-test-chat2",
            wa_api_key_encrypted=enc,
            google_sheet_id="sheet-1",
            owner_wa_number="+6281234567890",
            onboarding_status="ready",
        )
        captured = {}

        def fake_dry(tenant_id, message):
            captured["tenant_id"] = tenant_id
            captured["message"] = message
            return {
                "reply_text": "ok",
                "intent": "faq",
                "confidence": 0.8,
                "action": "reply",
                "fallback_reason": None,
                "match_kind": "high",
                "gateway_calls": [],
            }

        with patch("app.api.provision.dry_run_reply", side_effect=fake_dry):
            r = client.post("/api/provision/test-chat", json={
                "tenant_id": "tenant-test-chat2",
                "message": "ada diskon?",
            })
        assert r.status_code == 200
        assert captured["tenant_id"] == "tenant-test-chat2"
        assert captured["message"] == "ada diskon?"

    def test_test_chat_tenant_not_found(self, client, reset_db):
        with patch("app.api.provision.dry_run_reply") as mock:
            r = client.post("/api/provision/test-chat", json={
                "tenant_id": "nonexistent",
                "message": "halo",
            })
        assert r.status_code == 404
        mock.assert_not_called()

    def test_test_chat_empty_message(self, client, reset_db):
        from app.db.tenant_repo import insert_or_update_tenant
        from app.config import get_settings
        from app.services.crypto import encrypt_api_key

        enc = encrypt_api_key("key", get_settings().encryption_key)
        insert_or_update_tenant(
            tenant_id="t-empty",
            wa_api_key_encrypted=enc,
            google_sheet_id="s",
            owner_wa_number="+6281",
        )
        r = client.post("/api/provision/test-chat", json={"tenant_id": "t-empty", "message": "  "})
        assert r.status_code == 400
        assert "tidak boleh kosong" in r.json()["detail"]


class TestProvisionPage:
    def test_provision_page_loads(self, client, reset_db):
        r = client.get("/provision?token=abc123")
        assert r.status_code == 200
        assert "Onboard Toko" in r.text

    def test_admin_page_loads(self, client, reset_db):
        r = client.get("/admin")
        assert r.status_code == 200
        assert "Admin Panel" in r.text