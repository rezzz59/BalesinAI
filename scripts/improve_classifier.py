"""Improve MockLLMClient with Indonesian buyer patterns.

Adds:
1. Small talk detection
2. Complaint-specific handling
3. Better keyword matching
4. Typo tolerance
"""
import re


def normalize_text(text: str) -> str:
    """Normalize Indonesian text for matching."""
    if not text:
        return ""
    # Lowercase
    text = text.lower()
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Remove punctuation except question marks
    text = re.sub(r'[^\w\s?]', '', text)
    return text


# Expanded keyword lists based on Indonesian buyer patterns
KEYWORDS = {
    "faq": {
        "harga": ["harga", "brp", "berapa", "mahal", "murah", "termurah", "spesial", "grosir", "nego"],
        "ongkir": ["ongkir", "kirim", "pengiriman", "ekspedisi", "jne", "jnt", "sicepat", "pos", "kirimin", "sampai"],
        "garansi": ["garansi", "jaminan", "ganti", "tukar", "return", "exchange"],
        "order": ["order", "pesan", "beli", "belanja", "checkout", "min order", "paling sedikit"],
        "cara": ["cara", "gimana", "dimana", "tempat", "link", "website"],
        "waktu": ["kapan", "estimasi", "lama", "hari", "besok", "tadi"],
    },
    "check_product": {
        "ready": ["ready", "stok", "tersedia", "ada", "baru", "restock"],
        "size": ["size", "ukuran", "s ", "m ", "l ", "xl", "xxl", "30", "32", "34", "36"],
        "warna": ["warna", "color", "hitam", "putih", "merah", "biru", "coklat", "olive"],
    },
    "confirm_order": {
        "order": ["order", "pesan", "beli", "ambil", "booking", "saya mau", "saya pesan", 
                  "oke", "ya", "iya", "lanjut", "checkout", "syarat"],
    },
    "small_talk": {
        "sapaan": ["halo", "hai", "hello", "hi", "pagi", "siang", "sore", "malam", "kak", "min", "admin"],
        "ucapan": ["terima kasih", "makasih", "thanks", "thank", "syukran"],
        "emoji": ["👋", "🙏", "👍", "👌", "💯", "😍", "🔥", "❤️", "👀", "😊", "🤔"],
    },
    "complaint": {
        "negative": ["kecewa", "marah", "rusak", "cacat", "jelek", "buruk", "tidak sesuai", "beda", 
                     "penipuan", "bohong", "tipu", "batal", "ga jadi", "mau komplain", "komplain"],
        "delivery": ["ga sampai", "belum sampai", "lama", "tunggu", "nunggu", "sampe", "sampai"],
        "refund": ["refund", "kembalikan", "uangs kembali", "uang kembali", "cucur"],
    },
}


class ImprovedMockLLMClient:
    """Improved classifier with Indonesian buyer patterns."""
    
    def classify(self, message: str) -> dict:
        """Classify message with improved logic."""
        msg = normalize_text(message or "")
        
        # Check for empty/whitespace
        if not msg or len(msg) < 2:
            return {
                "intent": "unclear",
                "confidence": 0.3,
                "has_complaint_signal": False,
                "sentiment": "neutral"
            }
        
        # Check small talk FIRST (before other intents)
        if self._is_small_talk(msg):
            return {
                "intent": "small_talk",
                "confidence": 0.9,
                "has_complaint_signal": False,
                "sentiment": "neutral"
            }
        
        # Check complaint signals
        has_complaint = self._has_complaint_signal(msg)
        
        # Check check_product (product-specific queries)
        if self._matches_keyword_group(msg, KEYWORDS["check_product"]):
            return {
                "intent": "check_product",
                "confidence": 0.95,
                "has_complaint_signal": has_complaint,
                "sentiment": "negative" if has_complaint else "neutral"
            }
        
        # Check confirm_order
        if self._matches_keyword_group(msg, KEYWORDS["confirm_order"]):
            return {
                "intent": "confirm_order",
                "confidence": 0.92,
                "has_complaint_signal": has_complaint,
                "sentiment": "negative" if has_complaint else "positive"
            }
        
        # Check faq (general questions)
        if self._matches_keyword_group(msg, KEYWORDS["faq"]):
            return {
                "intent": "faq",
                "confidence": 0.85,
                "has_complaint_signal": has_complaint,
                "sentiment": "negative" if has_complaint else "neutral"
            }
        
        # If has complaint signal, return complaint intent
        if has_complaint:
            return {
                "intent": "complaint",
                "confidence": 0.8,
                "has_complaint_signal": True,
                "sentiment": "negative"
            }
        
        # Default to unclear
        return {
            "intent": "unclear",
            "confidence": 0.4,
            "has_complaint_signal": has_complaint,
            "sentiment": "neutral"
        }
    
    def _is_small_talk(self, msg: str) -> bool:
        """Check if message is small talk."""
        # Check for greeting words
        greetings = ["halo", "hai", "hello", "hi", "pagi", "siang", "sore", "malam", 
                     "kak", "min", "admin", "terima kasih", "makasih", "thanks"]
        
        for word in greetings:
            if word in msg:
                # Exclude if it's part of a question
                if "?" not in msg and "berapa" not in msg and "ada" not in msg:
                    return True
        
        # Check for emoji-only messages
        emoji_count = sum(1 for c in msg if ord(c) > 0x1F000)
        if emoji_count >= 1 and len(msg) < 10:
            return True
        
        return False
    
    def _has_complaint_signal(self, msg: str) -> bool:
        """Check for complaint signals."""
        complaint_words = ["kecewa", "marah", "rusak", "cacat", "jelek", "tidak sesuai", 
                          "beda", "penipuan", "bohong", "batal", "ga jadi", "komplain",
                          "ga sampai", "belum sampai", "refund", "kembalikan"]
        
        for word in complaint_words:
            if word in msg:
                return True
        
        return False
    
    def _matches_keyword_group(self, msg: str, groups: dict) -> bool:
        """Check if message matches any keyword in any group."""
        for group_name, keywords in groups.items():
            for keyword in keywords:
                if keyword in msg:
                    return True
        return False


if __name__ == "__main__":
    import csv
    
    # Test with Indonesian buyer dataset
    client = ImprovedMockLLMClient()
    
    with open('/tmp/indonesian_buyer_dataset.csv', 'r') as f:
        reader = csv.DictReader(f)
        dataset = list(reader)
    
    primary = [row for row in dataset if row['is_primary'] == 'yes']
    
    results = []
    print("=== IMPROVED CLASSIFIER EVALUATION ===")
    print()
    
    for i, row in enumerate(primary, 1):
        message = row['message']
        expected = row['category']
        
        result = client.classify(message)
        predicted = result['intent']
        
        # Check pass
        passed = predicted == expected
        status = '✅' if passed else '❌'
        
        results.append({
            'message': message,
            'expected': expected,
            'predicted': predicted,
            'passed': passed,
        })
        
        print(f"{status} [{i:2}/{len(primary)}] {message[:40]}")
        if not passed:
            print(f"     Expected: {expected}, Got: {predicted}")
    
    print()
    passed_count = sum(1 for r in results if r['passed'])
    print(f"Pass rate: {passed_count}/{len(results)} ({100*passed_count/len(results):.1f}%)")
    
    # Breakdown
    print()
    print("Breakdown by category:")
    categories = {}
    for r in results:
        cat = r['expected']
        if cat not in categories:
            categories[cat] = {'total': 0, 'passed': 0}
        categories[cat]['total'] += 1
        if r['passed']:
            categories[cat]['passed'] += 1
    
    for cat, stats in sorted(categories.items()):
        rate = 100 * stats['passed'] / stats['total'] if stats['total'] > 0 else 0
        print(f"  {cat:20} {stats['passed']}/{stats['total']} ({rate:.1f}%)")
