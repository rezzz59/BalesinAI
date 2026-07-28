# OrderCloser Lite

AI agent berbasis LangGraph untuk auto-reply WhatsApp + fallback ke owner.

## Quick Start

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Configure
cp .env.example .env
# Edit .env — at minimum:
#   ANTHROPIC_API_KEY
#   ENCRYPTION_KEY (generate via: python scripts/gen_encryption_key.py)
#   GOOGLE_SHEETS_CREDENTIALS_JSON_PATH (setup guide: docs/setup.md)

# Seed tenant
python scripts/gen_encryption_key.py
python scripts/seed_tenant.py \
    --tenant demo \
    --sheet-id YOUR_GOOGLE_SHEET_ID \
    --wa-number +6281234567890 \
    --api-key YOUR_WABLAS_API_KEY

# Run
uvicorn app.main:app --reload --port 8000
```

## Testing

```bash 
pytest -v
```

## Architecture

See [design spec](../specs/2026-07-27-ordercloser-lite-fase1-design.md).
