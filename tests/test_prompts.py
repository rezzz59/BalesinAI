"""Tests for prompt templates."""
from app.graph.prompts import (
    COMPOSE_STRICT_SYSTEM,
    COMPOSE_PARTIAL_SYSTEM,
    COMPOSE_NOMATCH_SYSTEM,
    COMPOSE_USER_TEMPLATE,
)


def test_compose_strict_system_has_no_hallucination_rule():
    assert "EXACTLY" in COMPOSE_STRICT_SYSTEM or "exactly" in COMPOSE_STRICT_SYSTEM
    assert "kami" in COMPOSE_STRICT_SYSTEM or "Kak" in COMPOSE_STRICT_SYSTEM


def test_compose_partial_system_acknowledges_partial_match():
    text = COMPOSE_PARTIAL_SYSTEM.lower()
    assert any(kw in text for kw in ("partial", "sebagian", "konfirmasi", "belum lengkap"))


def test_compose_nomatch_system_uses_exact_user_rules():
    assert "kami" in COMPOSE_NOMATCH_SYSTEM
    assert "Kak" in COMPOSE_NOMATCH_SYSTEM
    assert "NEVER hallucinate" in COMPOSE_NOMATCH_SYSTEM or "NEVER" in COMPOSE_NOMATCH_SYSTEM


def test_compose_user_template_interpolates_message_and_row():
    out = COMPOSE_USER_TEMPLATE.format(
        message="berapa harga hoodie?",
        source_row="Hoodie Fleece Tebal — Rp 150.000",
        match_kind="high",
    )
    assert "berapa harga hoodie?" in out
    assert "Hoodie Fleece Tebal — Rp 150.000" in out
    assert "high" in out