#!/usr/bin/env python3
"""One-time SQLite migration for the provisioning feature.

Adds new columns to tenant_config (business_type, onboarding_status,
onboarding_data, fonnte_device_id) and creates the provisioning_tokens table.

Idempotent — safe to run multiple times.

Usage:
    python scripts/migrate_add_provisioning.py [--db PATH]
"""

import argparse
import sys
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings  # noqa: E402


NEW_COLUMNS = {
    "tenant_config": {
        "business_type": "VARCHAR NOT NULL DEFAULT 'jualan'",
        "onboarding_status": "VARCHAR NOT NULL DEFAULT 'pending'",
        "onboarding_data": "TEXT NOT NULL DEFAULT '{}'",
        "fonnte_device_id": "VARCHAR NOT NULL DEFAULT ''",
    },
}

CREATE_TOKENS_TABLE = """
CREATE TABLE IF NOT EXISTS provisioning_tokens (
    token VARCHAR(64) PRIMARY KEY,
    status VARCHAR NOT NULL DEFAULT 'pending',
    intended_merchant_name VARCHAR NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL,
    expires_at DATETIME NOT NULL,
    used_at DATETIME,
    created_tenant_id VARCHAR
)
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate DB for provisioning feature.")
    parser.add_argument("--db", default=None, help="Path to SQLite DB (default: from settings)")
    args = parser.parse_args()

    db_path = args.db or get_settings().checkpointer_db_path
    if db_path == ":memory:":
        print("Skipping in-memory DB.")
        return
    print(f"Migrating {db_path} ...")

    conn = sqlite3.connect(db_path)
    try:
        for table, cols in NEW_COLUMNS.items():
            existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            for name, ddl in cols.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
                    print(f"  + {table}.{name}")
                else:
                    print(f"  = {table}.{name} (already exists)")

        conn.execute(CREATE_TOKENS_TABLE)
        print("  + provisioning_tokens table")
        conn.commit()
    finally:
        conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    main()
