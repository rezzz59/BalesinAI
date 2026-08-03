"""Capture user messages for dataset creation."""
import csv
import json
from sqlalchemy import text, inspect
from app.db.engine import get_engine
from app.db.models import ChatLog, Base

def add_message_column():
    """Add user_message column to chat_log table."""
    engine = get_engine()
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns('chat_log')]
    
    if 'user_message' not in columns:
        with engine.connect() as conn:
            conn.execute(text('ALTER TABLE chat_log ADD COLUMN user_message TEXT'))
            conn.commit()
        print("Added user_message column to chat_log")
    else:
        print("user_message column already exists")

def export_dataset(limit=500):
    """Export chat log dataset to CSV."""
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text(f'''
            SELECT id, thread_id, tenant_id, wa_number, intent, 
                   confidence, response, fallback_reason, status, timestamp,
                   user_message
            FROM chat_log
            ORDER BY timestamp DESC
            LIMIT {limit}
        '''))
        rows = result.fetchall()
        
        with open('/tmp/chat_dataset.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'thread_id', 'tenant_id', 'wa_number', 'intent', 
                             'confidence', 'response', 'fallback_reason', 'status', 
                             'timestamp', 'user_message', 'ground_truth_intent', 
                             'ground_truth_response', 'quality_rating'])
            for row in rows:
                writer.writerow(row)
        
        print(f"Exported {len(rows)} rows to /tmp/chat_dataset.csv")
        return len(rows)

if __name__ == "__main__":
    add_message_column()
    export_dataset()
