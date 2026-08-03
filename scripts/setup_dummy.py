#!/usr/bin/env python3
"""
Setup dummy tenant untuk testing webhook WhatsApp.
Jalankan script ini sekali untuk membuat database dan tenant dummy.
"""
import os
import sys
import sqlite3

# Set up env before imports
os.environ.setdefault("ENCRYPTION_KEY", "ZI4Y9avr30SJ1MiDrF2ooaiDNM6HQrGqVl0I8Wegf44=")
os.environ.setdefault("GOOGLE_SHEETS_CREDENTIALS_JSON_PATH", "./secrets/test-sa.json")

def setup_database():
    """Initialize database and create dummy tenant."""
    # Import after setting env
    from app.db import init_db
    from app.db.tenant_repo import insert_or_update_tenant
    from app.services.crypto import encrypt_api_key
    from app.config import get_settings

    print("=" * 60)
    print("🔧 Setup Dummy Tenant untuk Testing")
    print("=" * 60)

    # 1. Init database
    print("\n[1/3] Initializing database...")
    init_db()
    print("      ✅ Database initialized (data/.chatbot.db)")

    # 2. Get settings
    settings = get_settings()
    enc_key = settings.encryption_key

    # 3. Create dummy tenant
    print("\n[2/3] Creating dummy tenant...")

    # Use dummy encrypted key (same pattern as tests)
    dummy_encrypted_key = b"\x00" * 32

    insert_or_update_tenant(
        tenant_id="default",
        owner_wa_number="+6281234567890",
        google_sheet_id="1bf1bg1s8bjc53v092pZVkGtbCsRLv9DPhhvpeUCjpqA",
        wa_api_key_encrypted=dummy_encrypted_key,
        payment_provider="dummy"
    )
    print("      ✅ Tenant created: default")
    print("         - Owner WA: +6281234567890")
    print("         - Sheets ID: 1bf1bg1s8bjc53v092pZVkGtbCsRLv9DPhhvpeUCjpqA")
    print("         - Fonnte Key: [dummy encrypted]")

    # 4. Verify
    print("\n[3/3] Verifying database...")
    conn = sqlite3.connect("data/.chatbot.db")
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cur.fetchall()
    conn.close()

    print("      ✅ Tables created:", [t[0] for t in tables])

    print("\n" + "=" * 60)
    print("✅ SETUP SELESAI!")
    print("=" * 60)
    print("\nSekarang kamu bisa test webhook dengan curl:")
    print()
    print("  # Test FAQ response:")
    print('  curl -X POST http://localhost:8000/webhook/wa ' \
          '-H "Authorization: Bearer S4bfYPjfqWCZMm7j2dUAfAbiJB-Kb2b74Bat1T8UyYM" ' \
          '-H "Content-Type: application/json" ' \
          '-d \'{"tenant": "default", "phone": "+628999888777", "message": "Garansi berapa bulan?"}\'')
    print()
    print("  # Test Product inquiry:")
    print('  curl -X POST http://localhost:8000/webhook/wa ' \
          '-H "Authorization: Bearer S4bfYPjfqWCZMm7j2dUAfAbiJB-Kb2b74Bat1T8UyYM" ' \
          '-H "Content-Type: application/json" ' \
          '-d \'{"tenant": "default", "phone": "+628999888777", "message": "Kaos hitam ada ga?"}\'')
    print()
    print("  # Test Fallback (complaint/unclear):")
    print('  curl -X POST http://localhost:8000/webhook/wa ' \
          '-H "Authorization: Bearer S4bfYPjfqWCZMm7j2dUAfAbiJB-Kb2b74Bat1T8UyYM" ' \
          '-H "Content-Type: application/json" ' \
          '-d \'{"tenant": "default", "phone": "+628999888777", "message": "Barang saya rusak!"}\'')
    print()
    print("=" * 60)

if __name__ == "__main__":
    setup_database()
