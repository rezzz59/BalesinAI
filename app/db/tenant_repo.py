"""Tenant config repository."""
from typing import TypedDict

from app.db.engine import get_session
from app.db.models import TenantConfig


class TenantRecord(TypedDict):
    tenant_id: str
    wa_api_key_encrypted: bytes
    google_sheet_id: str
    payment_provider: str
    owner_wa_number: str


def insert_tenant(
    tenant_id: str,
    wa_api_key_encrypted: bytes,
    google_sheet_id: str,
    owner_wa_number: str,
    payment_provider: str = "xendit",
) -> None:
    """Insert a new tenant config row."""
    with get_session() as session:
        tenant = TenantConfig(
            tenant_id=tenant_id,
            wa_api_key_encrypted=wa_api_key_encrypted,
            google_sheet_id=google_sheet_id,
            owner_wa_number=owner_wa_number,
            payment_provider=payment_provider,
        )
        session.add(tenant)
        session.commit()


def insert_or_update_tenant(
    tenant_id: str,
    wa_api_key_encrypted: bytes,
    google_sheet_id: str,
    owner_wa_number: str,
    payment_provider: str = "xendit",
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
            tenant.updated_at = __import__('datetime', fromlist=['datetime']).datetime.now()
        else:
            tenant = TenantConfig(
                tenant_id=tenant_id,
                wa_api_key_encrypted=wa_api_key_encrypted,
                google_sheet_id=google_sheet_id,
                owner_wa_number=owner_wa_number,
                payment_provider=payment_provider,
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
        )


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
