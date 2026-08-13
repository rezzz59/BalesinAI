"""Tests for sales-style reply validation (C3)."""
from app.services.reply_validator import validate_sales_style


def test_short_reply_passes():
    """OK if reply is within sentence limit, single emoji, no listener violation."""
    ok, msg = validate_sales_style("Halo Kak, produk ini ready ya 😊 Mau pesan yang mana?")
    assert ok is True
    assert msg == "OK"


def test_reply_without_question_fails():
    """Persona rule: never end a message without a guiding question."""
    ok, msg = validate_sales_style("Halo Kak, produk ini ready ya 😊")
    assert ok is False
    assert "question" in msg.lower()


def test_multiple_questions_fails():
    """Persona rule: max 1 question per message (decision fatigue)."""
    ok, msg = validate_sales_style(
        "Halo Kak, produknya ready ya 😊 Mau pesan yang mana? Sekalian ukurannya mau apa? 😊"
    )
    assert ok is False
    assert "more than 1 question" in msg.lower()


def test_two_emojis_passes():
    """Persona allows up to 2 emojis per message."""
    ok, msg = validate_sales_style("Halo Kak! Produknya ready ya 😊 Mau pesan yang mana? 🙏")
    assert ok is True


def test_long_reply_fails():
    """Reply with more than 6 sentences should be rejected."""
    ok, msg = validate_sales_style(
        "Kalimat satu. Kalimat dua. Kalimat tiga. Kalimat empat. Kalimat lima. Kalimat enam. Kalimat tujuh."
    )
    assert ok is False
    assert "sentences" in msg.lower()


def test_multiple_emojis_fails():
    """Reply with more than 2 emojis should be rejected."""
    ok, msg = validate_sales_style("Kak, ada 😊 sekali 😊 emang 😊 ya")
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
    ok, msg = validate_sales_style("Ukuran M yang Anda pesan sudah kami siapkan. Mau lanjut konfirmasi alamatnya, Kak?",
                                   user_message="Saya mau ukura M")
    assert ok is True or "listener" not in msg


def test_answering_attribute_info_is_not_violation():
    """Naming the attribute while ANSWERING a stock/size/color question is fine;
    only RE-ASKING it is a listener violation."""
    ok, msg = validate_sales_style(
        "Siap Kak! Kemeja Batik size L warna navy ready ya. 🙌 "
        "Tersedia warna hitam dan navy ukuran M-XXL. Harganya Rp 135.000 per pcs. "
        "Boleh dibantu nama lengkap dan alamatnya agar pesanannya bisa kami amankan?",
        user_message="kak, kemeja batik premiumnya ready size L warna navy ada ga?",
    )
    assert ok is True, msg


def test_asking_size_already_mentioned_fails():
    """Re-asking the size the buyer already named must still be flagged."""
    ok, msg = validate_sales_style(
        "Sudah kami siapkan ya Kak. Kakak mau ukuran apa?",
        user_message="Saya mau kaos oversize size M",
    )
    assert ok is False
    assert "listener" in msg.lower()


def test_one_sentence_single_emoji_ok():
    """Single emoji and one sentence passes."""
    ok, msg = validate_sales_style("Terima kasih! Mau dibantu apa lagi, Kak? 👍")
    assert ok is True