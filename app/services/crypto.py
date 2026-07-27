"""AES-GCM encryption for tenant API keys at rest."""
import base64
import os

from Crypto.Cipher import AES


class CryptoError(Exception):
    """Raised when encryption/decryption fails."""


def _decode_key(key_b64: str) -> bytes:
    try:
        key = base64.b64decode(key_b64)
    except Exception as e:
        raise CryptoError(f"Invalid base64 encryption key: {e}") from e

    if len(key) != 32:
        raise CryptoError(f"Encryption key must be 32 bytes, got {len(key)}")

    return key


def encrypt_api_key(plaintext: str, key_b64: str) -> bytes:
    """Encrypt plaintext API key. Returns nonce || ciphertext."""
    try:
        key = _decode_key(key_b64)
        nonce = os.urandom(12)
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode())
        # Append GCM tag to ensure integrity on decryption
        return nonce + ciphertext + tag
    except ValueError as e:
        raise CryptoError(f"Encryption failed: {e}") from e
    except Exception as e:
        raise CryptoError(f"Encryption failed: {e}") from e


def decrypt_api_key(ciphertext: bytes, key_b64: str) -> str:
    """Decrypt ciphertext from encrypt_api_key. Returns plaintext."""
    try:
        key = _decode_key(key_b64)
        if len(ciphertext) < 12 + 16:  # 12 nonce + 16 tag minimum
            raise CryptoError("Ciphertext too short")

        nonce = ciphertext[:12]
        tagged_data = ciphertext[12:-16]
        tag = ciphertext[-16:]

        key = _decode_key(key_b64)
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        plaintext = cipher.decrypt_and_verify(tagged_data, tag)
        return plaintext.decode()
    except ValueError as e:
        raise CryptoError(f"Decryption failed - authentication check: {e}") from e
    except CryptoError:
        raise
    except Exception as e:
        raise CryptoError(f"Decryption failed: {e}") from e