"""Wablas webhook signature verification.

Wablas sends an HMAC SHA-256 signature in the request header (typically X-Wablas-Signature
— exact name TBD, will be confirmed during implementation).

The signature is computed over the raw request body using the tenant's Wablas API key.
"""
import hmac
import hashlib


class SignatureError(Exception):
    """Raised when signature header is missing or malformed."""


def verify_wablas_signature(
    signature_header: str,
    request_body: bytes,
    secret: str,
) -> bool:
    """Verify a Wablas webhook signature using HMAC SHA-256 with constant-time compare.

    Returns True if signature is valid, False otherwise.
    Raises SignatureError if signature_header is missing/empty.
    """
    if not signature_header:
        raise SignatureError("Missing signature header")

    expected = hmac.new(
        secret.encode("utf-8"),
        request_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature_header)