#!/usr/bin/env python3
"""Embedding pre-load script for catalog items.

Generates embeddings from the catalog sheet and saves them to the embedding cache.

Usage:
    python scripts/embedding_preload.py [--tenant <id>]

The script will:
1. Read the catalog from Google Sheets (cached locally during run).
2. For each product row where 'nama_produk' is non-empty, compute an embedding
   from the concatenated text "nama_produk + deskripsi".
3. Save the embedding to the SQLite cache under source='catalog', using
   nama_produk as the row_id.

Run this once after initial seeding, or whenever catalog changes significantly.
"""

import argparse
import sys
from pathlib import Path

# Ensure app package is importable
sys.path.insert(
    0,
    str(Path(__file__).parent.parent),
)

from app.services.sheets import GoogleSheetsClient
from app.services.embeddings import EmbeddingService
from app.db.embeddings_repo import get_embedding_repo
from app.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pre-load catalog items into embedding cache."
    )
    parser.add_argument(
        "--tenant",
        default="default",
        help="Tenant ID for the cached embeddings (default: 'default')",
    )
    args = parser.parse_args()

    tenant_id = args.tenant

    # Initialize clients
    settings = get_settings()
    sheets_client = GoogleSheetsClient(
        credentials_json_path=settings.google_sheets_credentials_json_path,
        spreadsheet_id=settings.google_sheets_spreadsheet_id,
    )
    embedding_service = EmbeddingService()
    repo = get_embedding_repo()

    # Read catalog
    print("Reading catalog from Google Sheets...")
    products = sheets_client.read_catalog()
    print(f"Found {len(products)} catalog entries.")

    loaded_count = 0
    updated_count = 0

    for product in products:
        row_id = product.get("nama_produk", "").strip()
        if not row_id:
            continue  # Skip rows without a product name

        combined_text = f"{row_id} {product.get('deskripsi', '')}"
        print(f"Processing '{row_id}' ({len(combined_text)} chars)...")

        try:
            embedding = embedding_service.encode(combined_text)
        except Exception as e:
            print(f"  ERROR encoding: {e}")
            continue

        # Check if entry already exists to determine new vs update
        existing = repo.find_by_id(tenant_id, "catalog", row_id)
        is_new = existing is None

        # Upsert into cache
        try:
            repo.save(
                tenant_id=tenant_id,
                source="catalog",
                row_id=row_id,
                text=combined_text,
                embedding=embedding,
            )
            if is_new:
                loaded_count += 1
                print("  New entry saved.")
            else:
                updated_count += 1
                print("  Entry updated.")
        except Exception as e:
            print(f"  ERROR saving: {e}")
            continue

    print(f"\nDone! Loaded: {loaded_count}, Updated: {updated_count}")


if __name__ == "__main__":
    main()
