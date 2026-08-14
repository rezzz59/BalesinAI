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
    data_source: str
    tier: str
    device_status: str
    gateway_plan: str


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
    data_source: str = "sheet",
    tier: str | None = None,
    device_status: str | None = None,
    gateway_plan: str | None = None,
) -> None:
    """Insert or update tenant config. None for tier/device_status/gateway_plan
    leaves the stored value untouched (on update) or uses the default."""
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
            if onboarding_data:
                try:
                    existing = json.loads(tenant.onboarding_data or "{}")
                except Exception:
                    existing = {}
                existing.update(onboarding_data)
                tenant.onboarding_data = json.dumps(existing)
            tenant.fonnte_device_id = fonnte_device_id
            tenant.data_source = data_source
            if tier is not None:
                tenant.tier = tier
            if device_status is not None:
                tenant.device_status = device_status
            if gateway_plan is not None:
                tenant.gateway_plan = gateway_plan
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
                data_source=data_source,
                tier=tier or "basic",
                device_status=device_status or "fresh",
                gateway_plan=gateway_plan or "lite",
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
            data_source=tenant.data_source,
            tier=tenant.tier,
            device_status=tenant.device_status,
            gateway_plan=tenant.gateway_plan,
        )


def _norm_digits(value: str) -> str:
    """Normalize a WA/device number to the international digit form.

    '083135333166' and '6283135333166' both become '6283135333166'.
    """
    digits = "".join(ch for ch in value if ch.isdigit())
    if digits.startswith("0"):
        return "62" + digits[1:]
    return digits


def get_tenant_by_device(device_id: str) -> TenantRecord | None:
    """Fetch the tenant whose fonnte_device_id matches a device number.

    Normalizes both sides (08... vs 62...) before comparing, so the webhook can
    map a Fonnte `device` field ('6283135333166') to a tenant stored with
    '083135333166'. Returns None if no tenant owns that device.
    """
    target = _norm_digits(device_id)
    if not target:
        return None
    with get_session() as session:
        tenants = session.query(TenantConfig).all()
        for tenant in tenants:
            if _norm_digits(tenant.fonnte_device_id or "") == target:
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
                    data_source=tenant.data_source,
                    tier=tenant.tier,
                    device_status=tenant.device_status,
                    gateway_plan=tenant.gateway_plan,
                )
        return None


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


def update_device_status(tenant_id: str, status: str) -> None:
    """Update only the device_status for a tenant (fresh/pending/connected/disconnected)."""
    with get_session() as session:
        tenant = session.get(TenantConfig, tenant_id)
        if tenant:
            tenant.device_status = status
            tenant.updated_at = _now()
            session.commit()


def update_tier(tenant_id: str, tier: str, gateway_plan: str | None = None) -> None:
    """Update the tier (basic/pro/enterprise) and optionally gateway plan."""
    with get_session() as session:
        tenant = session.get(TenantConfig, tenant_id)
        if tenant:
            tenant.tier = tier
            if gateway_plan:
                tenant.gateway_plan = gateway_plan
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
                "data_source": t.data_source,
                "tier": t.tier,
                "device_status": t.device_status,
                "gateway_plan": t.gateway_plan,
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
