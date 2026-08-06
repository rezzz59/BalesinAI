"""Auto-seed FAQ & catalog embeddings for a tenant during provisioning.

Encodes each FAQ row (pertanyaan + jawaban) and catalog row (nama_produk +
deskripsi) into 384-d vectors and upserts them into the embedding cache so
semantic search works immediately after onboarding.
"""
import logging

from app.db.embeddings_repo import get_embedding_repo
from app.services.embeddings import get_embedding_service
from app.services.sheets import GoogleSheetsClient

logger = logging.getLogger(__name__)


def _faq_text(row: dict) -> str:
    parts = []
    if row.get("pertanyaan"):
        parts.append(str(row["pertanyaan"]))
    if row.get("jawaban"):
        parts.append(str(row["jawaban"]))
    return " ".join(parts).strip()


def _catalog_text(row: dict) -> str:
    parts = []
    if row.get("nama_produk"):
        parts.append(str(row["nama_produk"]))
    if row.get("deskripsi"):
        parts.append(str(row["deskripsi"]))
    return " ".join(parts).strip()


def seed_tenant_embeddings(
    tenant_id: str,
    sheets_client: GoogleSheetsClient,
    repo=None,
    embedding_service=None,
) -> dict:
    """Embed all FAQ + catalog rows for a tenant into the cache.

    Returns {'faq': int, 'catalog': int} counts of rows embedded.
    row_id for FAQ is the row index (position); for catalog it's nama_produk.
    """
    repo = repo or get_embedding_repo()
    embedding_service = embedding_service or get_embedding_service()

    faq_rows = sheets_client.read_faq()
    catalog_rows = sheets_client.read_catalog()

    faq_count = 0
    for idx, row in enumerate(faq_rows):
        text = _faq_text(row)
        if not text:
            continue
        try:
            vec = embedding_service.encode(text)
            repo.save(tenant_id, "faq", str(idx), text, vec)
            faq_count += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("embed_faq_failed", extra={"tenant_id": tenant_id, "idx": idx, "error": str(e)})

    catalog_count = 0
    for row in catalog_rows:
        text = _catalog_text(row)
        row_id = (row.get("nama_produk") or "").strip()
        if not text or not row_id:
            continue
        try:
            vec = embedding_service.encode(text)
            repo.save(tenant_id, "catalog", row_id, text, vec)
            catalog_count += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("embed_catalog_failed", extra={"tenant_id": tenant_id, "product": row_id, "error": str(e)})

    logger.info(
        "embeddings_seeded",
        extra={"tenant_id": tenant_id, "faq": faq_count, "catalog": catalog_count},
    )
    return {"faq": faq_count, "catalog": catalog_count}


def seed_local_tenant_embeddings(
    tenant_id: str,
    repo=None,
    embedding_service=None,
) -> dict:
    """Seed embeddings from locally-uploaded FAQ/catalog rows (no Sheets).

    Mirrors seed_tenant_embeddings but reads from the local DB tables, so a
    tenant with data_source='upload' gets the same semantic search without
    touching Google Sheets.
    """
    from app.db import local_data_repo

    repo = repo or get_embedding_repo()
    embedding_service = embedding_service or get_embedding_service()

    faq_rows = local_data_repo.session_faq(tenant_id)
    catalog_rows = local_data_repo.session_catalog(tenant_id)

    faq_count = 0
    for idx, row in enumerate(faq_rows):
        text = _faq_text(row)
        if not text:
            continue
        try:
            vec = embedding_service.encode(text)
            repo.save(tenant_id, "faq", str(idx), text, vec)
            faq_count += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("embed_faq_failed", extra={"tenant_id": tenant_id, "idx": idx, "error": str(e)})

    catalog_count = 0
    for row in catalog_rows:
        text = _catalog_text(row)
        row_id = (row.get("nama_produk") or "").strip()
        if not text or not row_id:
            continue
        try:
            vec = embedding_service.encode(text)
            repo.save(tenant_id, "catalog", row_id, text, vec)
            catalog_count += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("embed_catalog_failed", extra={"tenant_id": tenant_id, "product": row_id, "error": str(e)})

    logger.info(
        "embeddings_seeded_local",
        extra={"tenant_id": tenant_id, "faq": faq_count, "catalog": catalog_count},
    )
    return {"faq": faq_count, "catalog": catalog_count}
