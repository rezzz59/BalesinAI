"""
Upload FAQ spreadsheet ke Google Sheets.
Cara pakai:
1. Install google-auth dan google-api-python-client
2. Setup service account atau gunakan OAuth
3. Jalankan: python upload_to_sheets.py <sheet_id>
"""
import sys
import openpyxl

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False
    print("WARNING: google-auth dan google-api-python-client belum terinstall")
    print("Install dengan: pip install google-auth google-api-python-client")

def upload_faq_to_sheets(sheet_id: str, filepath: str = "data/klinik_faq_100.xlsx"):
    """Upload FAQ data ke Google Sheet."""
    if not GOOGLE_AVAILABLE:
        print("Google API tidak tersedia. Menggunakan file lokal.")
        return
    
    # Load workbook
    wb = openpyxl.load_workbook(filepath)
    ws = wb.active
    
    # Prepare data
    data = []
    for row in ws.iter_rows(values_only=True):
        data.append(row)
    
    # Connect to Google Sheets
    credentials = service_account.Credentials.from_service_account_file(
        'credentials.json',
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    service = build('sheets', 'v4', credentials=credentials)
    
    # Update sheet
    body = {
        'values': data
    }
    
    result = service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range='FAQ!A1:D131',
        valueInputOption='USER_ENTERED',
        body=body
    ).execute()
    
    print(f"✅ Uploaded {result.get('updatedRows')} rows to Sheet ID: {sheet_id}")
    return result

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python upload_to_sheets.py <sheet_id>")
        print("Example: python upload_to_sheets.py 1abc123...")
        sys.exit(1)
    
    sheet_id = sys.argv[1]
    upload_faq_to_sheets(sheet_id)
