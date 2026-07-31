#!/usr/bin/env python3
"""Test script for AdaCode LLM client integration with the chatbot project."""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings
from app.services.llm import get_llm_client, AdaCodeLLMClient

def test_basic():
    """Basic sanity tests."""
    settings = get_settings()
    print(f"[TEST] LLM_BACKEND: {settings.llm_backend}")
    print(f"[TEST] ADACODE_API_KEY set: {bool(settings.adacode_api_key)}")

    client = get_llm_client()
    assert isinstance(client, AdaCodeLLMClient), f"Expected AdaCodeLLMClient, got {type(client).__name__}"
    print("[PASS] get_llm_client returns AdaCodeLLMClient")

    # Test classify with complaint message
    result = client.classify("pokoknya aku kecewa banget produknya rusak!")
    assert result["intent"] == "unclear", f"Expected unclear, got {result['intent']}"
    assert result["has_complaint_signal"], "Expected has_complaint_signal=True"
    assert result["sentiment"] == "negative", f"Expected negative sentiment, got {result['sentiment']}"
    print("[PASS] classify detects complaint signal")

    # Test classify with product question
    result = client.classify("apakah ada hoodie hitam ready?")
    assert result["intent"] == "check_product", f"Expected check_product, got {result['intent']}"
    assert result["confidence"] > 0.5, f"Confidence too low: {result['confidence']}"
    print("[PASS] classify intent detection works")

    # Test compose_reply with retrieved row
    test_row = {
        "nama_produk": "Hoodie Fleece Tebal - Hitam - Size L",
        "harga": "150000",
        "ready": "Y",
        "deskripsi": "Bahan fleece 380gsm, ready stock hitam dan abu."
    }
    reply = client.compose_reply("apakah ada hoodie hitam?", test_row, match_kind="high")
    assert "Hoodie Fleece" in reply or "hitam" in reply, f"Reply should contain product info: {reply}"
    assert "Rp" in reply or "150000" in reply, f"Reply should contain price info: {reply}"
    print("[PASS] compose_reply grounded in retrieved row works")

    return True

if __name__ == "__main__":
    try:
        if test_basic():
            print("\n=== ALL TESTS PASSED ===")
            sys.exit(0)
    except Exception as e:
        print(f"\n=== TEST FAILED: {e} ===")
        import traceback
        traceback.print_exc()
        sys.exit(1)