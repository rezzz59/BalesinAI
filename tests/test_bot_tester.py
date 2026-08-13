"""Tests for app/services/bot_tester — dry-run reply + readiness scoring."""
import os
import tempfile

import pytest

from app.config import get_settings
from app.services.bot_tester import (
    GOLDEN_QUESTIONS,
    DryRunGateway,
    _compute_readiness,
    dry_run_reply,
    score_tenant,
)


@pytest.fixture(autouse=True)
def reset_db():
    """File-based temp SQLite so graph nodes that touch the DB work."""
    from sqlalchemy import create_engine

    import app.db.engine as engine_mod
    from app.db.models import Base

    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="test_bot_")
    os.close(fd)
    eng = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    engine_mod.reset_engine_for_testing(eng)
    yield
    eng.dispose()
    engine_mod.reset_engine_for_testing(None)
    try:
        os.unlink(db_path)
    except OSError:
        pass


def _setup_tenant(tenant_id: str = "test-merchant", business_type: str = "jualan") -> str:
    from app.db.tenant_repo import insert_or_update_tenant
    from app.services.crypto import encrypt_api_key

    settings = get_settings()
    enc = encrypt_api_key("fonnte-test", settings.encryption_key)
    insert_or_update_tenant(
        tenant_id=tenant_id,
        wa_api_key_encrypted=enc,
        google_sheet_id="sheet-abc",
        owner_wa_number="+628111111",
        business_type=business_type,
        onboarding_status="seeding",
    )
    return tenant_id


class FakeSheets:
    def __init__(self, faq_rows=None, catalog_rows=None, lookup=None):
        self.faq_rows = faq_rows or []
        self.catalog_rows = catalog_rows or []
        self._lookup = lookup

    def lookup_faq(self, message):
        if self._lookup is not None:
            return self._lookup(message)
        if self.faq_rows:
            return self.faq_rows[0]
        return None

    def read_faq(self):
        return self.faq_rows

    def read_catalog(self):
        return self.catalog_rows

    def list_ready_products(self):
        return [
            r for r in self.catalog_rows
            if (r.get("ready") or "").lower() in ("y", "yes", "ya", "ready", "tersedia", "1", "true", "t")
        ]


class FakeSemantic:
    def search(self, *args, **kwargs):
        return []


class FakeLLM:
    def __init__(self, intent="faq", confidence=0.9, reply="Terima kasih sudah bertanya, Kak! Kami bantu segera 🙏", has_complaint_signal=False):
        self.intent = intent
        self.confidence = confidence
        self.reply = reply
        self.has_complaint_signal = has_complaint_signal
        self.compose_calls = 0

    def classify_with_history(self, messages):
        return {"intent": self.intent, "confidence": self.confidence,
                "has_complaint_signal": self.has_complaint_signal, "sentiment": "neutral"}

    def classify(self, message):
        return self.classify_with_history([{"role": "user", "content": message}])

    def compose_reply_with_history(self, messages, message, retrieved_row, match_kind,
                                   customer_context=None, persona=None):
        self.compose_calls += 1
        return self.reply

    def compose_reply(self, message, retrieved_row, match_kind,
                      customer_context=None, persona=None):
        self.compose_calls += 1
        return self.reply


class TestDryRunGateway:
    def test_send_message_records_instead_of_transmitting(self):
        import asyncio

        gw = DryRunGateway()
        result = asyncio.run(gw.send_message("+6281", "halo"))
        assert result["dry_run"] is True
        assert gw.calls == [("+6281", "halo")]

    def test_send_message_is_async(self):
        import asyncio

        gw = DryRunGateway()
        r = asyncio.run(gw.send_message("+6281", "halo"))
        assert r["status"] == "ok"


class TestDryRunReply:
    def test_returns_diagnostics_and_no_transmission(self, reset_db):
        tenant_id = _setup_tenant()
        llm = FakeLLM(intent="faq", confidence=0.95)
        sheets = FakeSheets(faq_rows=[{"pertanyaan": "jam buka apa?", "jawaban": "Kami buka jam 8 pagi."}])
        out = dry_run_reply(tenant_id, "jam buka apa?", llm_client=llm, sheets_client=sheets,
                            semantic_search_client=FakeSemantic())
        assert out["action"] == "reply"
        assert out["intent"] == "faq"
        assert out["reply_text"]
        assert out["match_kind"] == "high"
        # One recorded call to the fake number — recorded, never transmitted.
        assert len(out["gateway_calls"]) == 1

    def test_fallback_path_runs_headless(self, reset_db):
        tenant_id = _setup_tenant()
        llm = FakeLLM(intent="unclear", confidence=0.3, has_complaint_signal=True)
        sheets = FakeSheets(faq_rows=[], catalog_rows=[])
        out = dry_run_reply(tenant_id, "random", llm_client=llm, sheets_client=sheets,
                            semantic_search_client=FakeSemantic())
        assert out["action"] == "fallback"
        assert out["fallback_reason"]
        # Owner + buyer ack are recorded on the DryRunGateway, not transmitted.
        assert isinstance(out["gateway_calls"], list)
        assert len(out["gateway_calls"]) == 2


class TestReadinessScoring:
    def test_all_reply_scores_100(self):
        breakdown = [
            {"kind": "faq", "query": "q1", "action": "reply", "confidence": 0.9},
            {"kind": "catalog", "query": "q2", "action": "reply", "confidence": 0.9},
        ]
        r = _compute_readiness(breakdown, threshold=70)
        assert r["score"] == 100
        assert r["status"] == "ready"
        assert r["containment_rate"] == 1.0

    def test_high_score_ready(self):
        breakdown = [
            {"kind": "faq", "query": "q1", "action": "reply", "confidence": 0.9},
            {"kind": "catalog", "query": "q2", "action": "reply", "confidence": 0.9},
            {"kind": "golden", "query": "g1", "action": "reply", "confidence": 0.9},
        ]
        r = _compute_readiness(breakdown, threshold=70)
        assert r["score"] >= 70
        assert r["status"] == "ready"
        assert r["golden_hits"] == 1

    def test_low_score_needs_review(self):
        breakdown = [
            {"kind": "faq", "query": "q1", "action": "fallback", "confidence": 0.3},
            {"kind": "catalog", "query": "q2", "action": "fallback", "confidence": 0.3},
            {"kind": "golden", "query": "g1", "action": "fallback", "confidence": 0.3},
        ]
        r = _compute_readiness(breakdown, threshold=70)
        assert r["score"] < 70
        assert r["status"] == "needs_review"
        assert r["warnings"]  # golden misses become warnings

    def test_threshold_boundary_ready(self):
        breakdown = [{"kind": "faq", "query": "q", "action": "reply", "confidence": 0.9}]
        r = _compute_readiness(breakdown, threshold=60)
        assert r["score"] >= 60
        assert r["status"] == "ready"

    def test_empty_breakdown_error(self):
        r = _compute_readiness([], threshold=70)
        assert r["score"] == 0
        assert r["status"] == "error"

    def test_errors_penalize_quality(self):
        breakdown = [
            {"kind": "faq", "query": "q1", "action": "reply", "confidence": 0.9},
            {"kind": "faq", "query": "q2", "action": "error", "confidence": 0.0},
        ]
        r = _compute_readiness(breakdown, threshold=70)
        assert r["errors"] == 1
        assert r["score"] < 100

    def test_score_tenant_end_to_end_ready(self, reset_db):
        tenant_id = _setup_tenant()
        llm = FakeLLM(intent="faq", confidence=0.95)
        sheets = FakeSheets(
            faq_rows=[{"pertanyaan": "jam buka apa?", "jawaban": "Kami buka jam 8 pagi."}],
            catalog_rows=[{"nama_produk": "Kopi Susu", "harga": "15000", "ready": "Y"}],
        )
        r = score_tenant(tenant_id, llm_client=llm, sheets_client=sheets,
                         semantic_search_client=FakeSemantic(), threshold=70)
        assert r["status"] == "ready"
        assert r["score"] >= 70
        assert "breakdown" in r
        assert r["containment_rate"] > 0

    def test_score_tenant_needs_review_when_all_fallback(self, reset_db):
        tenant_id = _setup_tenant()
        llm = FakeLLM(intent="unclear", confidence=0.3)
        sheets = FakeSheets(faq_rows=[{"pertanyaan": "jam buka", "jawaban": "8 pagi"}],
                            catalog_rows=[])
        r = score_tenant(tenant_id, llm_client=llm, sheets_client=sheets,
                         semantic_search_client=FakeSemantic(), threshold=70)
        assert r["status"] == "needs_review"
        assert r["score"] < 70

    def test_score_tenant_missing_tenant_raises(self, reset_db):
        with pytest.raises(ValueError):
            score_tenant("nope-nonexistent")


class TestGoldenQuestions:
    def test_every_business_type_has_golden_questions(self):
        for bt in ("jualan", "klinik", "kuliner", "fashion"):
            assert GOLDEN_QUESTIONS[bt], f"golden empty for {bt}"
