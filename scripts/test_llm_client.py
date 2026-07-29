#!/usr/bin/env python3
"""
Test script to validate LLM client connectivity.
Tests both Anthropic and Gemmini backends based on configuration.
"""

import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from app.config import get_settings
from app.services.llm import get_llm_client, LLMError

def main():
    print("=" * 60)
    print("🤖 LLM Client Connection Test")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Load environment variables from .env
    load_dotenv()

    # Get settings
    try:
        settings = get_settings()
    except Exception as e:
        print(f"❌ Error loading settings: {e}")
        return 1

    # Show current configuration
    print(f"LLM Backend: {settings.llm_backend}")
    print(f"Anthropic API Key set: {'✓' if settings.anthropic_api_key else '✗'}")
    print(f"Gemini API Key set: {'✓' if settings.gemini_api_key else '✗'}")
    print()

    # Try to get the LLM client
    try:
        llm_client = get_llm_client()
        print(f"✓ LLM client instantiated successfully")
        print(f"  Type: {type(llm_client).__name__}")
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("\n   Missing Python package. Try installing:")
        if "anthropic" in str(e):
            print("   pip install anthropic langchain-anthropic")
        elif "google.genai" in str(e):
            print("   pip install google.genai")
        return 1
    except LLMError as e:
        print(f"❌ LLM configuration error: {e}")
        # Provide specific guidance
        if "not set" in str(e) or "empty" in str(e).lower():
            if settings.llm_backend == "anthropic":
                print("\n   Please set ANTHROPIC_API_KEY in your .env file")
            elif settings.llm_backend == "gemini":
                print("\n   Please set GEMINI_API_KEY in your .env file")
                print("   AND install: pip install google.genai")
        return 1
    except Exception as e:
        print(f"❌ Unexpected error creating LLM client: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Test classification with a sample message
    print("\n" + "-" * 40)
    print("📝 Testing intent classification...")
    print("-" * 40)

    test_messages = [
        "Stok produk X tersedia?",
        "Saya mau beli 2 buah smartphone",
        "Bagaimana cara memesan?",
        "Terima kasih!",
    ]

    for msg in test_messages:
        try:
            result = llm_client.classify(msg)
            print(f"  Input: '{msg[:40]}{'...' if len(msg) > 40 else ''}'")
            print(f"  → Intent: {result['intent']} (confidence: {result['confidence']:.2%})")
        except LLMError as e:
            print(f"  ❌ Error classifying '{msg[:40]}...': {e}")
        except Exception as e:
            print(f"  ⚠️ Unexpected error: {e}")

    print()
    print("=" * 60)
    print("✅ LLM CLIENT TEST COMPLETE")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    exit(main())
