"""Local uploaded-data repo (FAQ + catalog rows from XLSX upload)."""
import logging

from app.db.engine import get_session
from app.db.models import CatalogRow, FaqRow, OngkirRow

logger = logging.getLogger(__name__)


def replace_faq(tenant_id: str, rows: list[dict]) -> int:
    """Replace all FAQ rows for a tenant. rows: [{pertanyaan, jawaban}]."""
    with get_session() as session:
        session.query(FaqRow).filter_by(tenant_id=tenant_id).delete()
        added = 0
        for i, r in enumerate(rows, start=1):
            q = (r.get("pertanyaan") or "").strip()
            a = (r.get("jawaban") or "").strip()
            if not q or not a:
                continue
            session.add(FaqRow(tenant_id=tenant_id, pertanyaan=q, jawaban=a, row_no=i))
            added += 1
        session.commit()
        return added


def replace_catalog(tenant_id: str, rows: list[dict]) -> int:
    """Replace all catalog rows for a tenant. rows: [{nama_produk, harga, ready, deskripsi}]."""
    with get_session() as session:
        session.query(CatalogRow).filter_by(tenant_id=tenant_id).delete()
        added = 0
        for r in rows:
            name = (r.get("nama_produk") or "").strip()
            if not name:
                continue
            session.add(CatalogRow(
                tenant_id=tenant_id,
                nama_produk=name,
                harga=str(r.get("harga") or "").strip(),
                ready=str(r.get("ready") or "").strip(),
                deskripsi=str(r.get("deskripsi") or "").strip(),
                min_order=str(r.get("min_order") or "").strip(),
            ))
            added += 1
        session.commit()
        return added


def replace_ongkir(tenant_id: str, rows: list[dict]) -> int:
    """Replace all ongkir rows for a tenant. rows: [{wilayah, ongkir, min_order}]."""
    with get_session() as session:
        session.query(OngkirRow).filter_by(tenant_id=tenant_id).delete()
        added = 0
        for r in rows:
            wilayah = (r.get("wilayah") or "").strip()
            if not wilayah:
                continue
            session.add(OngkirRow(
                tenant_id=tenant_id,
                wilayah=wilayah,
                ongkir=str(r.get("ongkir") or "").strip(),
                min_order=str(r.get("min_order") or "").strip(),
            ))
            added += 1
        session.commit()
        return added


def session_faq(tenant_id: str) -> list[dict]:
    with get_session() as session:
        rows = session.query(FaqRow).filter_by(tenant_id=tenant_id).order_by(FaqRow.row_no).all()
        return [{"pertanyaan": r.pertanyaan, "jawaban": r.jawaban} for r in rows]


def session_catalog(tenant_id: str) -> list[dict]:
    with get_session() as session:
        rows = session.query(CatalogRow).filter_by(tenant_id=tenant_id).all()
        return [
            {
                "nama_produk": r.nama_produk,
                "harga": r.harga,
                "ready": r.ready,
                "deskripsi": r.deskripsi,
                "min_order": r.min_order,
            }
            for r in rows
        ]


def session_ongkir(tenant_id: str) -> list[dict]:
    with get_session() as session:
        rows = session.query(OngkirRow).filter_by(tenant_id=tenant_id).all()
        return [
            {"wilayah": r.wilayah, "ongkir": r.ongkir, "min_order": r.min_order}
            for r in rows
        ]


def has_local_data(tenant_id: str) -> bool:
    with get_session() as session:
        return (
            session.query(FaqRow.id).filter_by(tenant_id=tenant_id).first() is not None
            or session.query(CatalogRow.id).filter_by(tenant_id=tenant_id).first() is not None
        )