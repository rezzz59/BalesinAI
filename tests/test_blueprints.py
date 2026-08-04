"""Tests for industry blueprints (Fase 4)."""
from unittest.mock import patch

from app.data.blueprints import (
    BLUEPRINT_FAQS,
    available_business_types,
    get_blueprint,
)
from app.graph.nodes import _lookup_blueprint_faq


def _tenant(business_type="jualan"):
    return {
        "tenant_id": "bt",
        "business_type": business_type,
        "owner_wa_number": "+628",
        "google_sheet_id": "sheet",
        "onboarding_status": "ready",
        "onboarding_data": "{}",
        "payment_provider": "xendit",
    }


class TestBlueprintData:
    def test_covers_all_business_types(self):
        for bt in ("jualan", "kuliner", "klinik", "fashion"):
            assert bt in BLUEPRINT_FAQS, f"missing {bt}"

    def test_available_types(self):
        assert set(available_business_types()) == {"jualan", "kuliner", "klinik", "fashion"}

    def test_get_blueprint_returns_faqs_and_examples(self):
        bp = get_blueprint("kuliner")
        assert bp["business_type"] == "kuliner"
        assert len(bp["faqs"]) >= 3
        assert len(bp["catalog_examples"]) >= 1

    def test_unknown_type_falls_back_to_jualan(self):
        bp = get_blueprint("nonsense")
        assert bp["business_type"] == "jualan"

    def test_faqs_have_expected_keys(self):
        for faq in BLUEPRINT_FAQS["jualan"]:
            assert "pertanyaan" in faq and "jawaban" in faq


class TestBlueprintLookup:
    def test_matches_generic_order_question(self):
        with patch("app.db.tenant_repo.get_tenant", return_value=_tenant("jualan")):
            row = _lookup_blueprint_faq("cara ordernya gimana?", "bt")
        assert row is not None
        assert "pertanyaan" in row and "jawaban" in row

    def test_matches_kuliner_question(self):
        with patch("app.db.tenant_repo.get_tenant", return_value=_tenant("kuliner")):
            row = _lookup_blueprint_faq("bisa delivery tidak?", "bt")
        assert row is not None

    def test_returns_none_for_no_match(self):
        with patch("app.db.tenant_repo.get_tenant", return_value=_tenant("jualan")):
            row = _lookup_blueprint_faq("berapakah quark gluon plasma?", "bt")
        assert row is None

    def test_handles_missing_tenant(self):
        with patch("app.db.tenant_repo.get_tenant", return_value=None):
            assert _lookup_blueprint_faq("cara ordernya gimana?", "bt") is None