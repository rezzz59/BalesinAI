"""Check what's already available locally and try alternative dataset sources."""
import os
from pathlib import Path


def check_local_files():
    """Check if any datasets exist locally."""
    print("=" * 60)
    print("CHECKING LOCAL FILESYSTEM")
    print("=" * 60)
    print()
    
    search_dirs = [
        '/tmp',
        '/data',
        '/datasets',
        '/root/datasets',
        '/home/datasets',
        Path.home() / 'datasets',
        Path.cwd() / 'datasets',
        Path.cwd() / 'data',
    ]
    
    for d in search_dirs:
        if os.path.exists(d):
            print(f"✅ {d}")
            try:
                files = os.listdir(d)
                for f in files[:10]:
                    full = os.path.join(d, f)
                    if os.path.isdir(full):
                        print(f"   📁 {f}/")
                    elif f.endswith(('.csv', '.json', '.jsonl', '.txt', '.tsv')):
                        size = os.path.getsize(full)
                        print(f"   📄 {f} ({size:,} bytes)")
            except PermissionError:
                print(f"   ⚠️ Permission denied")
        else:
            print(f"❌ {d} (not found)")


def check_huggingface_cache():
    """Check Hugging Face cache directory."""
    print()
    print("=" * 60)
    print("CHECKING HUGGINGFACE CACHE")
    print("=" * 60)
    print()
    
    cache_dirs = [
        Path.home() / '.cache' / 'huggingface',
        Path('/root/.cache/huggingface'),
        Path.home() / '.cache' / 'huggingface' / 'hub',
    ]
    
    for cache in cache_dirs:
        if cache.exists():
            print(f"✅ {cache}")
            for item in cache.iterdir():
                print(f"   📁 {item.name}/")
        else:
            print(f"❌ {cache}")


def check_dataset_files():
    """Check our current /tmp datasets."""
    print()
    print("=" * 60)
    print("CHECKING /tmp/datasets* FILES")
    print("=" * 60)
    print()
    
    import glob
    files = glob.glob('/tmp/*dataset*')
    for f in files:
        size = os.path.getsize(f)
        print(f"📄 {f} ({size:,} bytes)")
        
        # Try to read first few lines
        try:
            if f.endswith('.csv'):
                with open(f, 'r', encoding='utf-8', errors='ignore') as file:
                    lines = file.readlines()[:3]
                    for line in lines:
                        print(f"   | {line.rstrip()}")
            elif f.endswith('.json'):
                with open(f, 'r', encoding='utf-8', errors='ignore') as file:
                    content = file.read()[:500]
                    print(f"   | {content[:200]}")
            print()
        except Exception as e:
            print(f"   ⚠️ Could not read: {e}")


def try_loading_with_huggingface_hub():
    """Try to load using huggingface_hub library."""
    print()
    print("=" * 60)
    print("TRYING HUGGINGFACE_HUB")
    print("=" * 60)
    print()
    
    try:
        from huggingface_hub import HfApi
        api = HfApi()
        
        # List Indonesian datasets
        print("Searching for Indonesian datasets...")
        try:
            datasets = list(api.list_datasets(search="indonesian", limit=20))
            print(f"Found {len(datasets)} datasets")
            for ds in datasets[:10]:
                print(f"  - {ds.id} (downloads: {getattr(ds, 'downloads', 0)})")
        except Exception as e:
            print(f"Error searching: {e}")
        
    except Exception as e:
        print(f"Error: {e}")


def check_for_csv_json_in_repo():
    """Check if there are CSV/JSON files anywhere in the chatbot repo."""
    print()
    print("=" * 60)
    print("SEARCHING REPO FOR DATA FILES")
    print("=" * 60)
    print()
    
    repo_root = Path('/media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot')
    
    for ext in ['*.csv', '*.json', '*.jsonl', '*.txt']:
        files = list(repo_root.rglob(ext))
        for f in files:
            if 'node_modules' not in str(f) and '.venv' not in str(f) and '__pycache__' not in str(f):
                size = f.stat().st_size
                if size > 100:  # Skip tiny files
                    print(f"�� {f.relative_to(repo_root)} ({size:,} bytes)")


if __name__ == "__main__":
    check_local_files()
    check_huggingface_cache()
    check_dataset_files()
    check_for_csv_json_in_repo()
    try_loading_with_huggingface_hub()
