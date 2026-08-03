"""Download and process Indonesian public datasets for chatbot training.

Datasets:
1. IndoDialogue - Multi-turn dialogues
2. INDOQA - Question answering
3. IndoChat - Chatbot conversations
"""
import os
import csv
import json
from pathlib import Path


# Dataset download URLs
DATASETS = {
    "indodialogue": {
        "name": "IndoDialogue",
        "url": "https://huggingface.co/datasets/indonlp/indodialogue",
        "description": "Indonesian multi-turn dialogue dataset",
        "huggingface_id": "indonlp/indodialogue",
    },
    "indoqa": {
        "name": "INDOQA",
        "url": "https://huggingface.co/datasets/indonlp/indoqa",
        "description": "Indonesian question answering dataset",
        "huggingface_id": "indonlp/indoqa",
    },
    "indo_chat": {
        "name": "IndoChat",
        "url": "https://huggingface.co/datasets/indonlp/indo_chat",
        "description": "Indonesian chatbot conversations",
        "huggingface_id": "indonlp/indo_chat",
    },
}


def check_huggingface_cli():
    """Check if huggingface-cli is installed."""
    try:
        import subprocess
        result = subprocess.run(
            ["huggingface-cli", "--version"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except:
        return False


def download_dataset_hf(dataset_id: str, output_dir: str = "/tmp/datasets"):
    """Download dataset using huggingface_hub."""
    try:
        from huggingface_hub import snapshot_download
        
        print(f"Downloading {dataset_id}...")
        path = snapshot_download(
            repo_id=dataset_id,
            repo_type="dataset",
            local_dir=os.path.join(output_dir, dataset_id),
            local_dir_use_symlinks=False
        )
        print(f"  Saved to: {path}")
        return path
    except ImportError:
        print("  huggingface_hub not installed. Install with: pip install huggingface_hub")
        return None
    except Exception as e:
        print(f"  Error: {e}")
        return None


def download_dataset_cli(dataset_id: str, output_dir: str = "/tmp/datasets"):
    """Download dataset using huggingface-cli."""
    try:
        import subprocess
        os.makedirs(output_dir, exist_ok=True)
        cmd = [
            "huggingface-cli", "download",
            dataset_id,
            "--repo-type", "dataset",
            "--local-dir", os.path.join(output_dir, dataset_id),
            "--local-dir-use-symlinks", "False"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"  Downloaded to: {os.path.join(output_dir, dataset_id)}")
            return os.path.join(output_dir, dataset_id)
        else:
            print(f"  Error: {result.stderr}")
            return None
    except Exception as e:
        print(f"  Error: {e}")
        return None


def process_indodialogue(dataset_path: str, output_csv: str = "/tmp/indodialogue.csv"):
    """Process IndoDialogue dataset to CSV format."""
    conversations = []
    
    # Try to load from JSON files
    json_files = list(Path(dataset_path).glob("*.json"))
    if not json_files:
        json_files = list(Path(dataset_path).glob("**/*.json"))
    
    for json_file in json_files[:5]:  # Limit to first 5 files
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        # Extract conversation turns
                        if 'dialogue' in item or 'conversatio
