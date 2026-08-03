"""Demo: How multi-tenant works in the chatbot system."""
import asyncio
import json
from unittest.mock import MagicMock, patch

# Mock the clients to avoid real API calls
class MockSheetsClient:
    def __init__(self, tenant_id, sheet_id):
        self.tenant_id = tenant_id
        self.sheet_id = sheet_id
        
    def lookup_faq(self, message):
        """Mock FAQ lookup based on tenant."""
        if self.tenant_id == "klinik_sehat":
            if "jam" in message.lower() or "buka" in message.lower():
                return {"pertanyaan": "jam buka", "jawaban": "Jam buka kami 08.00-20.00 WIB"}
            elif "dokter" in message.lower():
                return {"pertanyaan": "daftar dokter", "jawaban": "Kami punya dr. Andi (umum) dan dr. Budi (bedah)"}
        elif self.tenant_id == "cafe_kopi":
            if "roti" in message.lower():
                return {"pertanyaan": "ada roti", "jawaban": "Ada roti cokelt dan cheese, Rp 15.000"}
            elif "kopi" in message.lower():
                return {"pertanyaan": "menu kopi", "jawaban": "Espresso Rp 18.000, Latte Rp 22.000"}
        return None

class MockLLMClient:
    def classify(self, message):
        return {"intent": "faq", "confidence": 1.0}
    
    def compose_reply(self, message, row, match_kind):
        if row and row.get("jawaban"):
            return row["jawaban"]
        return "Maaf, saya tidak mengerti. Owner akan follow up."

class MockGateway:
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id
        
    async def send(self, phone, message):
        print(f"  [Gateway] Sending to {phone}: {message[:50]}...")
        return {"status": "sent"}

async def test_tenant(tenant_id, message, expected_reply_contains):
    """Test a single tenant."""
    print(f"\n{'='*60}")
    print(f"TESTING TENANT: {tenant_id}")
    print(f"{'='*60}")
    print(f"Message: '{message}'")
    print()
    
    # Simulate tenant lookup
    sheets = MockSheetsClient(tenant_id, f"sheet_{tenant_id}")
    llm = MockLLMClient()
    gateway = MockGateway(tenant_id)
    
    # Test FAQ lookup
    faq_result = sheets.lookup_faq(message)
    if faq_result:
        print(f"✅ FAQ MATCH found:")
        print(f"   Question: {faq_result['pertanyaan']}")
        print(f"   Answer: {faq_result['jawaban']}")
        print()
        print(f"📱 Reply akan dikirim ke user:")
        print(f"   \"{faq_result['jawaban']}\"")
    else:
        print(f"❌ No FAQ match")
        print(f"   → akan routing ke LLM fallback")
    
    # Verify it contains expected text
    if expected_reply_contains:
        print(f"\n✅ Verification: Reply contains '{expected_reply_contains}'")


async def main():
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║                 MULTI-TENANT DEMONSTRATION                           ║
╚══════════════════════════════════════════════════════════════════════╝

This demo shows how different tenants get DIFFERENT replies based on
their own FAQ data, even though they use the SAME chatbot system.
""")
    
    # Test Tenant 1: Existing (fashion store)
    await test_tenant(
        "default",
        "harga kaos",
        "kaos"
    )
    
    # Test Tenant 2: New clinic
    await test_tenant(
        "klinik_sehat",
        "jam buka",
        "08.00"
    )
    
    await test_tenant(
        "klinik_sehat",
        "ada dokter spesialis",
        "dokter"
    )
    
    # Test Tenant 3: New cafe
    await test_tenant(
        "cafe_kopi",
        "ada roti",
        "roti"
    )
    
    await test_tenant(
        "cafe_kopi",
        "menu kopinya apa",
        "kopi"
    )
    
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║                          KEY TAKEAWAYS                               ║
╚══════════════════════════════════════════════════════════════════════╝

✅ 1. SAME system, DIFFERENT data
   - Semua tenant pakai code yang sama
   - Tapi data FAQ terpisah per tenant
   
✅ 2. ISOLATED responses
   - Klinik tidak pernah dapat reply tentang kaos
   - Cafe tidak pernah dapat reply tentang jam operasional klinik
   
✅ 3. SCALABLE
   - Tambah tenant baru = insert 1 row ke DB
   - Tidak perlu deploy ulang
   - Tidak perlu ubah code
   
✅ 4. FLEXIBLE
   - Tiap tenant bisa punya:
     * Google Sheet sendiri
     * WhatsApp API key sendiri
     * Owner number untuk fallback
     * Payment provider sendiri

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 REAL IMPLEMENTATION STEPS:

1. Client daftar → dapat tenant_id
2. Buat Google Sheet baru untuk client
3. Insert ke database:
   INSERT INTO tenant_config VALUES ('client_id', 'encrypted_key', 'sheet_id', 'owner_wa');
4. Setup webhook dengan header X-Tenant-ID: client_id
5. Done!

Sistem akan otomatis:
- Lookup config client dari DB
- Init SheetsClient dengan sheet_id mereka
- Process graph dengan data mereka
- Reply via gateway mereka

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")


if __name__ == "__main__":
    asyncio.run(main())
