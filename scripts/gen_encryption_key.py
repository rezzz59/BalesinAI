#!/usr/bin/env python3
"""
Generate a secure 32-byte URL-safe encryption key.

Usage:
    python scripts/gen_encryption_key.py
"""

import secrets


def main() -> None:
    key = secrets.token_urlsafe(32)
    print("=" * 60)
    print("🔐 Encryption Key Generated")
    print("=" * 60)
    print(f"\n{key}\n")
    print("=" * 60)
    print("Copy this key into your .env file as ENCRYPTION_KEY=<key>")
    print("=" * 60)
    print("⚠️  Keep this secret! Do NOT commit to version control.")


if __name__ == "__main__":
    main()
