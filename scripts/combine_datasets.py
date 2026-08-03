"""Combine all datasets into one training file."""
import csv


def combine_datasets():
    """Combine training_dataset and indonesian_buyer_dataset."""
    combined = []
    
    # Read training_dataset.csv
    try:
        with open('/tmp/training_dataset.json', 'r', encoding='utf-8') as f:
            import json
            data = json.load(f)
            for item in data:
                combined.append({
                    'category': item['category'],
                    'intent': item['intent'],
                    'message': item['message'],
                    'source': item.get('source', 'generated'),
                    'notes': item.get('notes', ''),
                })
    except FileNotFoundError:
        print("training_dataset.json not found")
    
    # Read indonesian_buyer_dataset.csv
    with open('/tmp/indonesian_buyer_dataset.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            combined.append({
                'category': row['category'],
                'intent': row['intent'],
                'message': row['message'],
                'source': 'buyer_patterns',
                'notes': row.get('notes', ''),
            })
    
    # Remove duplicates
    seen = set()
    unique = []
    for item in combined:
        key = (item['category'], item['intent'], item['message'])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    
    # Export
    with open('/tmp/combined_training_dataset.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['category', 'intent', 'message', 'source', 'notes'])
        writer.writeheader()
        writer.writerows(unique)
    
    print(f"Combined dataset: {len(unique)} messages")
    print()
    
    # Statistics
    print("By Category:")
    categories = {}
    for item in unique:
        cat = item['category']
        categories[cat] = categories.get(cat, 0) + 1
    
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        pct = 100 * count / len(unique)
        print(f"  {cat:20} {count:4} ({pct:5.1f}%)")
    
    print()
    print("File saved: /tmp/combined_training_dataset.csv")


if __name__ == "__main__":
    combine_datasets()
