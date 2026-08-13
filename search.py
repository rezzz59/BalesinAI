import urllib.request
import urllib.parse
import json
import re

def search(query):
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    req = urllib.request.Request(
        url, 
        data=None, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    try:
        response = urllib.request.urlopen(req)
        html = response.read().decode('utf-8')
        
        # Simple regex to find result snippets and links
        snippets = re.findall(r'<a class="result__url" href="([^"]+)">(.*?)</a>.*?<a class="result__snippet[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL)
        
        print(f"Results for: {query}")
        for idx, (link, disp, snippet) in enumerate(snippets[:5]):
            print(f"{idx+1}. Link: {link}\n   Snippet: {snippet.strip()}\n")
            
    except Exception as e:
        print(f"Error: {e}")

search("Cekat AI WhatsApp chatbot architecture")
search("Cekat AI engineering blog RAG agent")
search("Cekat AI startup Indonesia technical stack")
