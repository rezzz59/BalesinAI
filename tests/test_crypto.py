"""Tests for app.services.crypto."""
import base64

import pytest

from app.services.crypto import CryptoError, decrypt_api_key, encrypt_api_key


def _key_b64() -> str:
    # 32 bytes = AES-256 key
    return base64.b64encode(b"x" * 32).decode()


def test_encrypt_decrypt_round_trip():
    key_b64 = _key_b64()
    plaintext = "fonnte-api-key-abc123"

    ciphertext = encrypt_api_key(plaintext, key_b64)
    assert ciphertext != plaintext.encode()
    assert isinstance(ciphertext, bytes)

    decrypted = decrypt_api_key(ciphertext, key_b64)
    assert decrypted == plaintext


def test_decrypt_with_wrong_key_fails():
    key_b64 = _key_b64()
    other_key_b64 = base64.b64encode(b"y" * 32).decode()

    ciphertext = encrypt_api_key("secret", key_b64)

    with pytest.raises(CryptoError):
        decrypt_api_key(ciphertext, other_key_b64)


def test_decrypt_tampered_ciphertext_fails():
    key_b64 = _key_b64()
    ciphertext = encrypt_api_key("secret", key_b64)
    tampered = ciphertext[:-1] + bytes([(ciphertext[-1] ^ 0xFF)])

    with pytest.raises(CryptoError):
        decrypt_api_key(tampered, key_b64)


def test_encrypt_invalid_key_length():
    with pytest.raises(CryptoError):
        encrypt_api_key("text", base64.b64encode(b"short").decode())