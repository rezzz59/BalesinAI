#!/usr/bin/env python3
"""Setup default tenant for testing."""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.engine import get_engine, reset_engine_for_testing
from app.db.models import Base
from app.db.tenant_repo import insert_tenant
from app.services.crypto import encrypt_api_key
from app.config import get_settings

# Reset engine to use the DB file from .env (not :memory:)
get_engine.cache_clear()

# Create tables if not exists
Base.metadata.create_all(get_engine())

# Read encryption key from .env
with open('.env', 'r') as f:
    for line in f:
        if line.startswith('ENCRYPTION_KEY='):
            enc_key = line.strip().split('=', 1)[1]
            break

# Insert default tenant
insert_tenant(
    tenant_id='default_tenant',
    wa_api_key_encrypted=encrypt_api_key('fonnete-token', enc_key),
    google_sheet_id='1bf1bg1s8bjc53v092pZVkGtbCsRLv9DPhhvpeUCjpqA',
    owner_wa_number='+6283142298645'  # owner = owner's number
)

print("✅ Default tenant set up successfully!")
print(f"   Tenant ID: default_tenant")
print(f"   Owner WA: +6283142298645")