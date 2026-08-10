"""Local data client — serves FAQ/catalog from rows uploaded via XLSX.

Implements the same duck-typed interface the graph, bot_tester and
embedding_seeder expect from GoogleSheetsClient, so a tenant with
data_source='upload' can run the identical pipeline without touching the
graph. FAQ matching reuses the shared scoring in app.services.sheets.
"""
import logging

from app.db import local_data_repo
from app.services.sheets import FAQ_MATCH_THRESHOLD, READY_TRUE_VALUES, _score_faq_row

logger = logging.getLogger(__name__)


class LocalDataClient:
    """Reads FAQ + catalog from the local DB (uploaded XLSX)."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    def read_faq(self) -> list[dict]:
        return local_data_repo.session_faq(self.tenant_id)

    def read_catalog(self) -> list[dict]:
        return local_data_repo.session_catalog(self.tenant_id)

    def read_ongkir(self) -> list[dict]:
        return local_data_repo.session_ongkir(self.tenant_id)

    def list_ready_products(self) -> list[dict]:
        return [
            r for r in self.read_catalog()
            if (r.get("ready") or "").strip().lower() in READY_TRUE_VALUES
        ]

    def lookup_faq(self, message: str) -> dict | None:
        """Best FAQ row above threshold (same logic as GoogleSheetsClient)."""
        if not message or not message.strip():
            return None
        best_row: dict | None = None
        best_score = 0.0
        for row in reversed(self.read_faq()):
            score = _score_faq_row(message, row)
            if score > best_score:
                best_score = score
                best_row = row
        if best_score < FAQ_MATCH_THRESHOLD:
            return None
        return best_row

    def clear_cache(self) -> None:
        pass