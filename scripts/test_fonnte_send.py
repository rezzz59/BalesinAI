#!/usr/bin/env python3
"""
Test script to send a test message via Fonnte Gateway.

Usage:
    python scripts/test_fonnte_send.py

WARNING: This will send a REAL WhatsApp message to the target number.
Make sure you intend to do this and that you have sufficient balance.
"""

import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from app.services.fonnte import FonnteGateway

def main():
    # Load environment variables
    load_dotenv()

    api_key = os.getenv("FONNTE_API_KEY")
    if not api_key or api_key == "isi_di_sini_mandiri" or api_key == "YOUR_FONTE_API_KEY":
        print("❌ ERROR: FONNTE_API_KEY is not properly configured!")
        print("   Please edit .env file and set:")
        print("   FONNTE_API_KEY=your_actual_api_key_here")
        sys.exit(1)

    print("✓ FONTE_API_KEY configured successfully")

    # Target phone number (without + prefix - Fonnte expects pure digits)
    # Original: +62 882-4628-3086 → Cleaned: 6288246283086
    target_phone = "6288246283086"

    # Create gateway instance (using same setup as your app)
    gateway = FonnteGateway(api_key=api_key, max_retries=1)  # Reduced retries for test

    async def test_send():
        try:
            print(f"\n📤 Mengirim pesan ke {target_phone}...")
            result = await gateway.send_message(
                phone=target_phone,
                message="[TEST] Pesan uji dari Fonnte Gateway - {datetime.now().strftime('%H:%M')}"
            )
            print(f"✅ Pesan berhasil dikirim!")
            print(f"   Response: {result}")
            return True
        except Exception as e:
            print(f"❌ Gagal mengirim pesan: {type(e).__name__}: {e}")
            return False

    success = asyncio.run(test_send())
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())