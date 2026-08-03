"""Export chat log dataset for evaluation.

Usage:
    python scripts/export_dataset.py [--limit 500] [--output /tmp/dataset.csv]
"""
import argparse
import csv
from sqlalchemy import text

from app.db.engine import get_engine


def export_dataset(limit: int = 500, output: str = "/tmp/chat_dataset.csv"):
    """Export chat log dataset to CSV with user_message column."""
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT id, thread_id, tenant_id, wa_number, intent, 
                       confidence, response, fallback_reason, status, timestamp,
                       COALESCE(user_message, '') as user_message
                FROM chat_log
                ORDER BY timestamp DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
        rows = result.fetchall()

        with open(output, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "id",
                    "thread_id",
                    "tenant_id",
                    "wa_number",
                    "predicted_intent",
                    "confidence",
                    "predicted_response",
                    "fallback_reason",
                    "status",
                    "timestamp",
                    "user_message",
                    "ground_truth_intent",
                    "ground_truth_response",
                    "quality_rating",
                    "notes",
                ]
            )
            for row in rows:
                writer.writerow(list(row) + ["", "", "", ""])

        print(f"Exported {len(rows)} rows to {output}")

        # Show stats
        with_user_msg = sum(1 for r in rows if r[10])
        print(f"  Rows with user_message: {with_user_msg}/{len(rows)}")
        print(f"  Rows without user_message: {len(rows) - with_user_msg}")

        return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export chat log dataset")
    parser.add_argument("--limit", type=int, default=500, help="Max rows to export")
    parser.add_argument("--output", default="/tmp/chat_dataset.csv", help="Output CSV path")
    args = parser.parse_args()

    export_dataset(limit=args.limit, output=args.output)
