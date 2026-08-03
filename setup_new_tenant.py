"""Setup new tenant with real Google Sheet."""
import asyncio
import sys
sys.path.insert(0, '/media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot')

from app.db.tenant_repo import insert_tenant, get_tenant
from app.services.crypto import encrypt_api_key
from app.config import get_settings
from app.db.engine import get_engine
from sqlalchemy import text


def create_klinik_sheet_content():
    """Content for clinic FAQ sheet."""
    return """pertanyaan,jawaban,col_2,col_3,col_4,col_5
Jam buka?,Jam buka Klinik Sehat: Senin-Sabtu 08.00-20.00 WIB, Minggu 09.00-15.00 WIB,,,
Ada dokter spesialis?,Kami punya dr. Andi (Umum) dan dr. Budi (Bedah Umum),,,
Biaya konsultasi?,Konsultasi umum Rp 50.000, Konsultasi spesialis Rp 100.000,,,
Bisa bayar pakai BPJS?,Ya, kami menerima BPJS Nyata dan Non-Nyata,,,
Lokasinya dimana?,Jl. Sehat No. 123, Jakarta Selatan,,,
Reservation?,Bisa WhatsApp ke owner untuk janji temu,,,
"""


def main():
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║              SETUP TENANT BARU - KLINIK SEHAT                        ║
╚══════════════════════════════════════════════════════════════════════╝
""")
    
    # Step 1: Show what to do
    print("📋 STEP 1: Buat Google Sheet Baru")
    print("-" * 60)
    print("""
1. Buka https://sheets.google.com/create
2. Buat sheet baru dengan nama: "Klinik Sehat FAQ"
3. Copy isi berikut ke sheet (baris 1 = header):
""")
    print(create_klinik_sheet_content())
    print("""
4. Share sheet ke email service account (cek di secrets/sheets-sa.json)
5. Copy Sheet ID dari URL (bagian antara /d/ dan /edit)
   Contoh: https://docs.google.com/spreadsheets/d/1abc123XYZ/edit
   Sheet ID-nya: 1abc123XYZ
""")
    
    # Step 2: Ask for input
    print("\n📋 STEP 2: Input Data Tenant")
    print("-" * 60)
    
    tenant_id = input("Masukkan tenant_id (contoh: klinik_sehat): ").strip() or "klinik_sehat"
    sheet_id = input("Masukkan Sheet ID dari Google Sheets: ").strip()
    
    if not sheet_id:
        print("❌ Sheet ID diperlukan!")
        return
    
    # Generate encrypted key (mock for demo)
    settings = get_settings()
    mock_api_key = "sk_fonnte_klinik_test_2024"
    encrypted_key = encrypt_api_key(mock_api_key, settings.encryption_key)
    
    # Insert tenant
    print(f"\n📋 STEP 3: Insert Tenant ke Database")
    print("-" * 60)
    print(f"Tenant ID: {tenant_id}")
    print(f"Sheet ID: {sheet_id}")
    print(f"API Key: {mock_api_key[:20]}... (encrypted)")
    
    insert_tenant(
        tenant_id=tenant_id,
        wa_api_key_encrypted=encrypted_key,
        google_sheet_id=sheet_id,
        owner_wa_number="+6281234567890",
        payment_provider="xendit",
    )
    print("✅ Tenant inserted ke database!")
    
    # Verify
    print(f"\n📋 STEP 4: Verify")
    print("-" * 60)
    tenant = get_tenant(tenant_id)
    if tenant:
        print(f"✅ Tenant found:")
        print(f"   - tenant_id: {tenant['tenant_id']}")
        print(f"   - sheet_id: {tenant['google_sheet_id'][:30]}...")
        print(f"   - owner_wa: {tenant['owner_wa_number']}")
    else:
        print("❌ Tenant not found!")
    
    # Step 3: Test instructions
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║              NEXT: TEST WEBHOOK                                      ║
╚══════════════════════════════════════════════════════════════════════╝

Untuk test, jalankan server dulu:
  cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot
  ./start.sh

Kemudian test webhook:
  curl -X POST http://localhost:8000/webhook/whatsapp/ \\
    -H "X-Tenant-ID: """ + tenant_id + """\\" \\
    -H "Content-Type: application/json" \\
    -d '{"wa_number": "6281234567890", "message_text": "jam buka"}'

Harusnya reply dari FAQ klinik (bukan FAQ kaos)!
""")


if __name__ == "__main__":
    main()
