"""Test the new clinic tenant."""
import sys
sys.path.insert(0, '/media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot')

from app.db.tenant_repo import get_tenant
from app.services.sheets import GoogleSheetsClient
from app.config import get_settings


def test_tenant():
    tenant_id = "klinik_baru"
    
    print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║              TESTING TENANT: {tenant_id.upper()}                    ║
╚══════════════════════════════════════════════════════════════════════╝
""")
    
    # Get tenant config
    tenant = get_tenant(tenant_id)
    if not tenant:
        print(f"❌ Tenant '{tenant_id}' not found in database!")
        return
    
    print(f"✅ Tenant config found:")
    print(f"   - Sheet ID: {tenant['google_sheet_id']}")
    print(f"   - Owner WA: {tenant['owner_wa_number']}")
    print()
    
    # Test Google Sheets client
    settings = get_settings()
    print("📋 Testing Google Sheets connection...")
    try:
        sheets_client = GoogleSheetsClient(
            credentials_json_path=settings.google_sheets_credentials_json_path,
            spreadsheet_id=tenant['google_sheet_id'],
        )
        print("✅ Google Sheets client initialized")
    except Exception as e:
        print(f"⚠️  Note: {e}")
        print("   (This might fail if sheet is not shared with service account)")
    
    print()
    print("="*60)
    print("NEXT STEPS:")
    print("="*60)
    print("""
1. Make sure sheet is shared with service account:
   - Open: https://docs.google.com/spreadsheets/d/1RQ38rPafmE67Z3eDELYd7CnQxxUzJfcbNzAMk_LtQP8/edit
   - Click Share → Add people
   - Add email from: secrets/sheets-sa.json

2. Test the webhook:
   curl -X POST http://localhost:8000/webhook/whatsapp/ \\
     -H "X-Tenant-ID: klinik_baru" \\
     -H "Content-Type: application/json" \\
     -d '{"wa_number": "6281234567890", "message_text": "jam buka"}'

3. Expected reply: FAQ from KLINIK sheet (not kaos sheet!)
""")


if __name__ == "__main__":
    test_tenant()
