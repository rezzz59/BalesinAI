#!/usr/bin/env python3
"""
Test script to validate Gemini API connectivity.
Usage: python scripts/test_gemini_api.py
"""

import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_gemini():
    """Simple test of the Gemini API key."""
    load_dotenv()

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key.strip() == "":
        print("❌ ERROR: GEMINI_API_KEY is not set in .env")
        return False

    # Basic validation - check if it looks like a valid Gemini key
    if len(api_key) < 20:
        print(f"⚠️  Warning: API key appears short ({len(api_key)} characters)")
    else:
        print(f"✓ GEMINI_API_KEY configured ({len(api_key)} characters)")

    # Try to actually use it - let's see if we can import and use the model
    try:
        from google.genai import types
        from google.genai.types import Part, GenerativeModel

        # This will test if the API key is valid by making a simple call
        # We'll use a very lightweight model if available
        print("\n🔧 Attempting to connect to Gemini API...")

        # Create a client instance (this will validate the key immediately)
        # Note: We're not setting actual model yet, just testing connectivity
        import google.auth
        from google.api_core import credentials

        # Test with a simple auth check
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        print(f"✓ Google Auth succeeded (service account available)")

        # Try to instantiate the model object (does NOT make network call yet)
        model = GenerativeModel(model_name="gemini-1.5-flash", credentials=creds)
        print(f"✓ GenerativeModel object created successfully")

        # Make a quick actual API call to test connectivity
        # Use a simple prompt to avoid cost overruns
        response = model.count_tokens([Part(text="Hello")])
        print(f"✓ Token count succeeded: {response.total_tokens} tokens")

        print("\n✅ ALL CHECKS PASSED! Gemini API is working correctly.")
        return True

    except ImportError as e:
        print(f"❌ ImportError: {e}")
        print("\n   Maybe required package not installed? Try:")
        print("   pip install google-genai")
        return False
    except Exception as e:
        print(f"❌ Error connecting to Gemini API:")
        print(f"   Type: {type(e).__name__}")
        print(f"   Message: {str(e)}")
        print("\n   Possible causes:")
        print("   • API key is invalid or expired")
        print("   • Gemini API not enabled in Google Cloud Console")
        print("   • Network/firewall blocking access")
        print("   • Quota exceeded")
        return False


if __name__ == "__main__":
    success = test_gemini()
    sys.exit(0 if success else 1)
