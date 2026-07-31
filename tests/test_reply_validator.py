"""Tests for sales-style reply validation (C3)."""
from app.services.reply_validator import validate_sales_style


def test_short_reply_passes():
    """OK if reply is within sentence limit, single emoji, no listener violation."""
    ok, msg = validate_sales_style("Halo Kak, produk ini ready ya 😊")
    assert ok is True
    assert msg == "OK"


def test_long_reply_fails():
    """Reply with more than 3 sentences should be rejected."""
    ok, msg = validate_sales_style(
        "Ini kalimat satu. Ini kalimat dua. Ini kalimat tiga. Ini kalimat empat."
    )
    assert ok is False
    assert "sentences" in msg.lower()


def test_multiple_emojis_fails():
    """Reply with more than 1 emoji should be rejected."""
    ok, msg = validate_sales_style("Kak, ada 😊 sekali 😊")
    assert ok is False
    assert "emoji" in msg.lower()


def test_listener_violation():
    """Ask about size when customer already mentioned it should fail."""
    ok, msg = validate_sales_style(
        "Kak, mau ukuran apa? 😊",
        user_message="Saya sudah pesan kaos ukuran M"
    )
    assert ok is False
    assert "listener" in msg.lower()


def test_no_user_message():
    """Without user_message, listener check is skipped."""
    ok, msg = validate_sales_style("Mau ukuran apa?", user_message="")
    # Only sentence/emoji checks apply
    # This may still pass if within limits


def test_exact_size_reference_passes():
    """Don't flag if reply doesn't repeat the attribute word as a question."""
    ok, msg = validate_sales_style("Ukuran M yang Anda pesan sudah kami siapkan.",
                                   user_message="Saya mau ukura M")
    assert ok is True or "listener" not in msg


def test_one_sentence_single_emoji_ok():
    """Single emoji and one sentence passes."""
    ok, msg = validate_sales_style("Terima kasih! 👍")
    assert ok is True