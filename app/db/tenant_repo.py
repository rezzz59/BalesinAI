"""Tenant config repository."""
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import TypedDict

from app.db.engine import get_session
from app.db.models import ProvisioningToken, TenantConfig


class TenantRecord(TypedDict):
    tenant_id: str
    wa_api_key_encrypted: bytes
    google_sheet_id: str
    payment_provider: str
    owner_wa_number: str
    business_type: str
    onboarding_status: str
    onboarding_data: str
    fonnte_device_id: str


PROVISION_TOKEN_TTL_HOURS = 48


def _now() -> datetime:
    return datetime.now(timezone.utc)


def insert_tenant(
    tenant_id: str,
    wa_api_key_encrypted: bytes,
    google_sheet_id: str,
    owner_wa_number: str,
    payment_provider: str = "xendit",
    business_type: str = "jualan",
    onboarding_status: str = "ready",
    onboarding_data: dict | None = None,
    fonnte_device_id: str = "",
) -> None:
    """Insert a new tenant config row."""
    with get_session() as session:
        tenant = TenantConfig(
            tenant_id=tenant_id,
            wa_api_key_encrypted=wa_api_key_encrypted,
            google_sheet_id=google_sheet_id,
            owner_wa_number=owner_wa_number,
            payment_provider=payment_provider,
            business_type=business_type,
            onboarding_status=onboarding_status,
            onboarding_data=json.dumps(onboarding_data or {}),
            fonnte_device_id=fonnte_device_id,
        )
        session.add(tenant)
        session.commit()


def insert_or_update_tenant(
    tenant_id: str,
    wa_api_key_encrypted: bytes,
    google_sheet_id: str,
    owner_wa_number: str,
    payment_provider: str = "xendit",
    business_type: str = "jualan",
    onboarding_status: str = "ready",
    onboarding_data: dict | None = None,
    fonnte_device_id: str = "",
) -> None:
    """Insert or update tenant config."""
    with get_session() as session:
        from app.db.models import TenantConfig
        tenant = session.get(TenantConfig, tenant_id)
        if tenant:
            tenant.wa_api_key_encrypted = wa_api_key_encrypted
            tenant.google_sheet_id = google_sheet_id
            tenant.owner_wa_number = owner_wa_number
            tenant.payment_provider = payment_provider
            tenant.business_type = business_type
            tenant.onboarding_status = onboarding_status
            tenant.onboarding_data = json.dumps(onboarding_data or {})
            tenant.fonnte_device_id = fonnte_device_id
            tenant.updated_at = _now()
        else:
            tenant = TenantConfig(
                tenant_id=tenant_id,
                wa_api_key_encrypted=wa_api_key_encrypted,
                google_sheet_id=google_sheet_id,
                owner_wa_number=owner_wa_number,
                payment_provider=payment_provider,
                business_type=business_type,
                onboarding_status=onboarding_status,
                onboarding_data=json.dumps(onboarding_data or {}),
                fonnte_device_id=fonnte_device_id,
            )
            session.add(tenant)
        session.commit()


def get_tenant(tenant_id: str) -> TenantRecord | None:
    """Fetch tenant config. Returns None if not found."""
    with get_session() as session:
        tenant: TenantConfig | None = (
            session.query(TenantConfig).filter_by(tenant_id=tenant_id).first()
        )
        if tenant is None:
            return None
        return TenantRecord(
            tenant_id=tenant.tenant_id,
            wa_api_key_encrypted=tenant.wa_api_key_encrypted,
            google_sheet_id=tenant.google_sheet_id,
            payment_provider=tenant.payment_provider,
            owner_wa_number=tenant.owner_wa_number,
            business_type=tenant.business_type,
            onboarding_status=tenant.onboarding_status,
            onboarding_data=tenant.onboarding_data,
            fonnte_device_id=tenant.fonnte_device_id,
        )


def update_onboarding_status(tenant_id: str, status: str) -> None:
    """Update only the onboarding status for a tenant."""
    with get_session() as session:
        tenant = session.get(TenantConfig, tenant_id)
        if tenant:
            tenant.onboarding_status = status
            tenant.updated_at = _now()
            session.commit()


def update_onboarding_data(tenant_id: str, onboarding_data: dict) -> None:
    """Update only the onboarding_data JSON payload for a tenant."""
    with get_session() as session:
        tenant = session.get(TenantConfig, tenant_id)
        if tenant:
            tenant.onboarding_data = json.dumps(onboarding_data or {})
            tenant.updated_at = _now()
            session.commit()


def list_tenants() -> list[dict]:
    """List all tenants (without encrypted keys for API safety)."""
    with get_session() as session:
        tenants = session.query(TenantConfig).all()
        return [
            {
                "tenant_id": t.tenant_id,
                "google_sheet_id": t.google_sheet_id,
                "payment_provider": t.payment_provider,
                "owner_wa_number": t.owner_wa_number,
                "business_type": t.business_type,
                "onboarding_status": t.onboarding_status,
                "fonnte_device_id": t.fonnte_device_id,
                "readiness": (json.loads(t.onboarding_data or "{}") or {}).get("readiness"),
            }
            for t in tenants
        ]


def delete_tenant(tenant_id: str) -> bool:
    """Delete a tenant by ID. Returns True if deleted."""
    with get_session() as session:
        tenant = session.query(TenantConfig).filter_by(tenant_id=tenant_id).first()
        if tenant is None:
            return False
        session.delete(tenant)
        session.commit()
        return True


def get_real_tenants() -> list[dict]:
    """List only tenants with real (non-fake) Google Sheet IDs."""
    tenants = list_tenants()
    return [t for t in tenants if not t['google_sheet_id'].startswith('FAKE_')]


# --- Provisioning tokens ---


def create_provisioning_token(
    intended_merchant_name: str = "",
    ttl_hours: int = PROVISION_TOKEN_TTL_HOURS,
) -> dict:
    """Generate a single-use provisioning token. Returns dict with token + url."""
    token = secrets.token_urlsafe(24)
    now = _now()
    with get_session() as session:
        session.add(ProvisioningToken(
            token=token,
            status="pending",
            intended_merchant_name=intended_merchant_name,
            created_at=now,
            expires_at=now + timedelta(hours=ttl_hours),
        ))
        session.commit()
    return {
        "token": token,
        "intended_merchant_name": intended_merchant_name,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=ttl_hours)).isoformat(),
    }


def get_provisioning_token(token: str) -> dict | None:
    """Fetch token metadata. Returns None if missing."""
    with get_session() as session:
        row = session.get(ProvisioningToken, token)
        if row is None:
            return None
        return {
            "token": row.token,
            "status": row.status,
            "intended_merchant_name": row.intended_merchant_name,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "used_at": row.used_at.isoformat() if row.used_at else None,
            "created_tenant_id": row.created_tenant_id,
        }


def consume_provisioning_token(token: str, tenant_id: str) -> bool:
    """Mark a token as used, binding it to the created tenant.

    Returns True if the token existed and was still pending.
    """
    with get_session() as session:
        row = session.get(ProvisioningToken, token)
        if row is None or row.status != "pending":
            return False
        row.status = "used"
        row.used_at = _now()
        row.created_tenant_id = tenant_id
        session.commit()
        return True
