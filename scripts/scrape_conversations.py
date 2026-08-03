"""Scrape conversations from existing chat logs to build evaluation dataset.

Since historical logs don't have user_message, we need to:
1. Check if there are any other sources (Fonnte logs, webhook logs, etc.)
2. Generate synthetic test messages that cover edge cases
3. Run them through the bot to get bot responses for evaluation

Usage:
    python scripts/scrape_conversations.py
"""
import csv
import json
import os
from pathlib import Path
from datetime import datetime

from app.db.engine import get_engine
from sqlalchemy import text


# Realistic test messages covering various intents and edge cases
# Based on typical WhatsApp business chat patterns in Indonesian
SYNTHETIC_TEST_MESSAGES = {
    "faq": [
        "Berapa ongkir ke Jakarta?",
        "Ada warna merah ga?",
        "Bisa COD ga?",
        "Garansinya berapa lama?",
        "Bahan apa ini?",
        "Ukurannya ada yang L ga?",
        "Bisa kirim ke Bandung hari ini?",
        "Ada diskon ga?",
        "Kalau tidak sesuai bisa return ga?",
        "Berapa lama pengiriman ke Surabaya?",
    ],
    "check_product": [
        "Stok jeans biru ukuran 30 ada?",
        "Baju hitam ready?",
        "Tas ini ready stock ga?",
        "Sepatu putih ukuran 42 ada?",
        "Kemeja motif bunga ready?",
        "Dress merah ready?",
        "Jaket denim ada?",
        "Celana pendek size M ready?",
    ],
    "confirm_order": [
        "Oke saya order",
        "Saya pesan 2",
        "Beli 1 ya",
        "OK checkout",
        "Saya booking dulu",
        "Boleh order 3",
    ],
    "unclear": [
        "Halo",
        "Selamat pagi",
        "Test",
        "Hai",
        "👍",
        "🙏",
        "Ok",
        "Terima kasih",
    ],
    "small_talk": [
        "Selamat siang kak",
        "Hai kak",
        "Halo selamat sore",
        "Pagi",
        "Thanks ya",
        "Mantap",
    ],
    "complaint": [
        "Udah 3 hari ga sampai-sampai",
        "Barang rusak, mau refund",
        "Kecewa banget sih",
        "Batal aja",
        "Ga sesuai foto",
        "Bahan jelek banget",
        "Lama banget pengirimannya",
        "Mau komplain di sosmed nih",
    ],
    "multi_intent": [
        "Baju biru ready? Kalau ready saya order",
        "Berapa harga kaos merah? Saya pesan 2 ya",
        "Ada stok M? Saya order sekarang",
        "Ongkir ke Jakarta berapa? Saya pesan 1",
    ],
    "edge_cases": [
        "",  # empty
        "   ",  # whitespace
        "!!!",  # punctuation only
        "abcdefghijklmnopqrstuvwxyz",  # gibberish
        "Bhs inggris dong",  # mixed language
        "berapa harga" * 10,  # spam
        "Baju",  # single word
        "?",  # single punctuation
        "Beli dong baju yang warna biru ukuran L yang ready stock",  # long
        "B-aru ready?",  # typo
        "bAjU mErAh",  # random caps
        "Halo, saya tertarik dengan produk Anda. Bisa info lebih lanjut? Apakah ready stock? Berapa harga dan ongkir ke Jakarta? Saya tertarik untuk beli 2 pcs.",  # formal
    ],
}


def export_synthetic_dataset(output: str = "/tmp/synthetic_dataset.csv"):
    """Export synthetic test messages as evaluation dataset."""
    rows = []
    for intent, messages in SYNTHETIC_TEST_MESSAGES.items():
        for msg in messages:
            rows.append(
                {
                    "test_id": f"{intent}_{len(rows):03d}",
                    "user_message": msg,
                    "expected_intent": intent,
                    "category": intent,
                    "notes": "",
                }
            )

    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "test_id",
                "user_message",
                "expected_intent",
                "category",
                "predicted_intent",
                "predicted_response",
                "fallback_reason",
                "passed",
                "notes",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"Exported {len(rows)} synthetic test messages to {output}")
    print(f"  Categories: {len(SYNTHETIC_TEST_MESSAGES)}")
    print()
    print("Breakdown by category:")
    for intent, messages in SYNTHETIC_TEST_MESSAGES.items():
        print(f"  {intent}: {len(messages)} messages")


def export_historical_logs_with_msg(output: str = "/tmp/historical_dataset.csv"):
    """Export historical logs (only those with user_message populated)."""
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT id, user_message, intent, confidence, response, 
                       fallback_reason, status, timestamp
                FROM chat_log
                WHERE user_message IS NOT NULL AND user_message != ''
                ORDER BY timestamp DESC
                LIMIT 500
                """
            )
        )
        rows = result.fetchall()

        with open(output, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "id",
                    "user_message",
                    "predicted_intent",
                    "confidence",
                    "predicted_response",
                    "fallback_reason",
                    "status",
                    "timestamp",
                    "ground_truth_intent",
                    "ground_truth_response",
                    "quality_rating",
                    "notes",
                ]
            )
            for row in rows:
                writer.writerow(list(row) + ["", "", "", ""])

        print(f"Exported {len(rows)} historical logs with user_message to {output}")
        return len(rows)


if __name__ == "__main__":
    export_synthetic_dataset()
    print()
    export_historical_logs_with_msg()
