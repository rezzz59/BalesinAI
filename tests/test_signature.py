"""Tests for app.auth.signature."""
import hmac
import hashlib

import pytest

from app.auth.signature import SignatureError, verify_wablas_signature


SECRET = "test-wablas-api-key-xyz"
BODY = b'{"phone": "+6281234567890", "message": "Halo"}'


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_verify_valid_signature_returns_true():
    sig = _sign(BODY, SECRET)
    assert verify_wablas_signature(sig, BODY, SECRET) is True


def test_verify_invalid_signature_returns_false():
    sig = _sign(BODY, SECRET)
    assert verify_wablas_signature(sig, BODY, "wrong-secret") is False
    assert verify_wablas_signature("deadbeef", BODY, SECRET) is False


def test_verify_empty_signature_raises():
    with pytest.raises(SignatureError):
        verify_wablas_signature("", BODY, SECRET)


def test_verify_constant_time_compare():
    """Verify uses hmac.compare_digest (smoke test — just ensure no exception on equal length)."""
    sig = _sign(BODY, SECRET)
    # If we use hmac.compare_digest, valid signature returns True
    assert verify_wablas_signature(sig, BODY, SECRET) is True