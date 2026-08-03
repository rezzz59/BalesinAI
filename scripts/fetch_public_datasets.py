"""Fetch public datasets for Indonesian customer service conversations.

Sources:
1. KAGGLE - Indonesian conversational datasets
2. Hugging Face Datasets
3. GitHub repos with Indonesian chat data
4. Scraping approaches (with caution)
"""
import os
import subprocess
import json


# Dataset sources to explore
DATASET_SOURCES = {
    "kaggle": [
        {
            "name": "indonesian-conversational-dataset",
            "url": "https://www.kaggle.com/datasets",
            "description": "Dataset percakapan Indonesia dari berbagai domain",
            "keywords": ["indonesian chatbot dataset", "indonesian conversational dataset", "indonesian qa dataset"]
        },
        {
            "name": "indonesian-customer-service",
            "url": "https://www.kaggle.com/datasets",
            "description": "Dataset customer service Indonesia",
            "keywords": ["indonesian customer service chat", "whatsapp business indonesia dataset"]
        },
        {
            "name": "indonesian-faq-dataset",
            "url": "https://www.kaggle.com/datasets",
            "description": "Dataset FAQ Indonesia",
            "keywords": ["indonesian faq dataset", "indonesian question answer dataset"]
        }
    ],
    "huggingface": [
        {
            "name": "indonesian-chatbot-conversation",
            "url": "https://huggingface.co/datasets",
            "description": "Dataset percakapan chatbot Indonesia",
            "keywords": ["indonesian chatbot conversation", "indonesian dialogue dataset"]
        },
        {
            "name": "indo-dialogue",
            "url": "https://huggingface.co/datasets",
            "description": "Dataset dialogue Indonesia",
            "keywords": ["indo dialogue", "indonesian multi-turn dialogue"]
        },
        {
            "name": "indonesian-qas",
            "url": "https://huggingface.co/datasets",
            "description": "Dataset Q&A Indonesia",
            "keywords": ["indonesian qa", "indonesian question answering"]
        }
    ],
    "github": [
        {
            "name": "indonesian-chatbot-datasets",
            "url": "https://github.com/topics/indonesian-chatbot",
            "description": "GitHub repos dengan dataset chatbot Indonesia",
            "search_terms": ["indonesian chatbot dataset", "indonesian conversational data"]
        },
        {
            "name": "indo-nlp-datasets",
            "url": "https://github.com/topics/indo-nlp",
            "description": "GitHub repos NLP Indonesia",
            "search_terms": ["indonesian dialogue", "indonesian conversation"]
        }
    ]
}


def search_kaggle_datasets():
    """Search for Indonesian datasets on Kaggle."""
    print("=" * 60)
    print("KAGGLE DATASET SEARCH")
    print("=" * 60)
    print()
    
    search_terms = [
        "indonesian chatbot dataset",
        "indonesian conversational dataset", 
        "indonesian customer service",
        "indonesian whatsapp dataset",
        "indonesian faq dataset",
        "indonesian dialogue dataset",
    ]
    
    for term in search_terms:
        print(f"Search: {term}")
        print(f"  URL: https://www.kaggle.com/datasets?q={term.replace(' ', '+')}")
        print()


def search_huggingface_datasets():
    """Search for Indonesian datasets on Hugging Face."""
    print("=" * 60)
    print("HUGGING FACE DATASET SEARCH")
    print("=" * 60)
    print()
    
    search_terms = [
        "indonesian chatbot",
        "indonesian conversation",
        "indonesian dialogue",
        "indo qa",
        "indonesian customer service",
    ]
    
    for term in search_terms:
        print(f"Search: {term}")
        print(f"  URL: https://huggingface.co/datasets?search={term.replace(' ', '+')}")
        print()


def search_github_repos():
    """Search for Indonesian datasets on GitHub."""
    print("=" * 60)
    print("GITHUB REPO SEARCH")
    print("=" * 60)
    print()
    
    search_terms = [
        "indonesian chatbot dataset",
        "indonesian conversational data",
        "indo dialogue dataset",
        "indonesian whatsapp conversation",
    ]
    
    for term in search_terms:
        print(f"Search: {term}")
        print(f"  URL: https://github.com/search?q={term.replace(' ', '+')}&type=repositories")
        print()


def list_known_datasets():
    """List known datasets that might be available."""
    print("=" * 60)
    print("KNOWN INDONESIAN DATASETS")
    print("=" * 60)
    print()
    
    datasets = [
        {
            "name": "IndoDialogue",
            "source": "Hugging Face",
            "url": "https://huggingface.co/datasets/indonlp/indodialogue",
            "description": "Multi-turn dialogue dataset in Indonesian",
            "size": "~50K dialogues",
            "license": "CC BY-SA"
        },
        {
            "name": "INDOQA",
            "source": "Hugging Face",
            "url": "https://huggingface.co/datasets/indonlp/indoqa",
            "description": "Question answering dataset in Indonesian",
            "size": "~100K QA pairs",
            "license": "MIT"
        },
        {
            "name": "IndoChat",
            "source": "GitHub",
            "url": "https://github.com/IndoNLP/indochat",
            "description": "Chatbot training data in Indonesian",
            "size": "~200K turns",
            "license": "Apache 2.0"
        },
        {
            "name": "Bahasa LEMBAH",
            "source": "Research Paper",
            "url": "https://aclanthology.org/2022.acl-demo.15/",
            "description": "Indonesian conversational dataset from forums",
            "size": "~500K turns",
            "license": "Research"
        },
        {
            "name": "OSCAR (Indonesian subset)",
            "source": "Hugging Face",
            "url": "https://huggingface.co/datasets/oscar",
            "description": "Web crawl data with Indonesian content",
            "size": "~100GB Indonesian text",
            "license": "CC-BY-SA"
        },
    ]
    
    for ds in datasets:
        print(f"📦 {ds['name']}")
        print(f"   Source: {ds['source']}")
        print(f"   URL: {ds['url']}")
        print(f"   Description: {ds['description']}")
        print(f"   Size: {ds['size']}")
        print(f"   License: {ds['license']}")
        print()


def create_scraper_script():
    """Create a script to scrape WhatsApp business conversations from public sources."""
    script_content = '''"""Scrape public WhatsApp business conversations.

Note: Only scrape from public/authorized sources.
Do not scrape private conversations.
"""
import requests
from bs4 import BeautifulSoup
import csv
import time


def scrape_forum_conversations():
    """Scrape customer service conversations from public forums."""
    # Example: scrape from Indonesian e-commerce forums
    forums = [
        "https://forum.komunitas.belajar.com",  # Contoh forum
        "https://community.tokopedia.com",
        "https://forum.shopee.co.id",
    ]
    
    conversations = []
    for forum in forums:
        try:
            response = requests.get(forum, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            # Parse conversations...
            pass
        except Exception as e:
            print(f"Error scraping {forum}: {e}")
    
    return conversations


def scrape_social_media():
    """Scrape from public social media posts."""
    # Twitter/X public posts about customer service
    # Reddit r/indonesia
    # Facebook public groups
    pass


def scrape_e-commerce_reviews():
    """Scrape product reviews (can infer customer questions)."""
    # Tokopedia, Shopee reviews
    pass


if __name__ == "__main__":
    print("This script is for reference only.")
    print("Please ensure you have permission to scrape any data.")
'''
    
    with open("scripts/scrape_public_data.py", "w") as f:
        f.write(script_content)
    
    print("Created: scripts/scrape_public_data.py")


if __name__ == "__main__":
    list_known_datasets()
    search_kaggle_datasets()
    search_huggingface_datasets()
    search_github_repos()
    create_scraper_script()
    
    print()
    print("=" * 60)
    print("RECOMMENDATIONS")
    print("=" * 60)
    print()
    print("1. Try Hugging Face datasets first (easiest to access):")
    print("   - IndoDialogue: https://huggingface.co/datasets/indonlp/indodialogue")
    print("   - INDOQA: https://huggingface.co/datasets/indonlp/indoqa")
    print()
    print("2. Check Kaggle for Indonesian chatbot datasets:")
    print("   - Search: 'indonesian chatbot dataset'")
    print()
    print("3. GitHub repos with Indonesian conversational data:")
    print("   - https://github.com/IndoNLP/indochat")
    print()
    print("4. Academic datasets:")
    print("   - Bahasa LEMBAH (forum conversations)")
    print("   - OSCAR Indonesian subset (web crawl)")
