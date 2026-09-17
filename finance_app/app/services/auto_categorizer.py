"""
services/auto_categorizer.py — Pakistani-Tuned Transaction Auto-Categorizer
───────────────────────────────────────────────────────────────────────────────
Fast keyword matcher for transaction descriptions common in Pakistani banking.
Maps merchants, payment descriptions, and services to user categories.

Used for:
  - CSV import auto-classification
  - Manual transaction entry suggestions
"""

from typing import Optional, Dict, List

# Keyword → category mapping (case-insensitive matching)
# Ordered by specificity — more specific patterns first
KEYWORD_MAP: List[Dict] = [
    # Food & Dining
    {"keywords": ["kfc", "mcdonald", "pizza hut", "domino", "subway", "hardees",
                  "broadway pizza", "student biryani", "nandos", "optp",
                  "foodpanda", "cheetay", "eat mubarak", "howdy", "desi meals",
                  "ice cream", "cafe", "coffee", "restaurant", "hotel food",
                  "imtiaz", "metro cash", "carrefour", "grocery", "bakery",
                  "saylani", "ehsaas rashan", "utility store", "kiryana"],
     "category": "Food & Dining"},

    # Transport
    {"keywords": ["uber", "careem", "indrive", "in drive", "bykea", "airlift",
                  "metro bus", "metrobus", "brt", "daewoo", "faisal movers",
                  "patroleum", "petrol", "cng", "filling station", "pso",
                  "shell", "total parco", "attock", "hascol", "parking"],
     "category": "Transport"},

    # Utilities
    {"keywords": ["kesc", "k-electric", "wapda", "fesco", "iesco", "mepco",
                  "sui gas", "sngpl", "ssgc", "ptcl", "nayatel", "stormfiber",
                  "jazz", "zong", "telenor", "ufone", "wateen", "internet",
                  "gas bill", "electricity", "water bill", "sewerage"],
     "category": "Utilities"},

    # Entertainment
    {"keywords": ["netflix", "spotify", "youtube premium", "amazon prime",
                  "hbo", "apple tv", "disney", "tapmad", "vidly",
                  "cinema", "cinepax", "nueplex", "atrium", "movies",
                  "gaming", "steam", "playstation", "xbox", "pubg"],
     "category": "Entertainment"},

    # Shopping
    {"keywords": ["daraz", "olx", "amazon", "aliexpress", "alibaba",
                  "khaadi", "sapphire", "limelight", "junaid jamshed", "j.",
                  "gul ahmed", "bonanza", "outfitters", "breakout",
                  "mall", "hyperstar", "lucky one", "dolmen", "centaurus",
                  "packages mall", "emporium"],
     "category": "Shopping"},

    # Healthcare
    {"keywords": ["pharmacy", "dawaai", "sehat", "dvago", "fazal din",
                  "shaheen chemist", "hospital", "clinic", "doctor", "lab",
                  "aga khan", "shifa", "south city", "jinnah hospital",
                  "chughtai lab", "excel lab", "essa lab", "panadol",
                  "medicine", "medical", "dental", "optical"],
     "category": "Healthcare"},

    # Education
    {"keywords": ["school", "college", "university", "tuition", "academy",
                  "course", "udemy", "coursera", "skillshare", "books",
                  "stationery", "library", "lums", "nust", "fast", "iba"],
     "category": "Education"},

    # Rent
    {"keywords": ["rent", "kiraya", "lease", "property", "zameen"],
     "category": "Rent"},

    # Savings / Transfers
    {"keywords": ["nsc", "national savings", "meezan", "saving", "deposit",
                  "investment", "mutual fund", "stock", "psx"],
     "category": "Savings"},
]


def auto_categorize(description: str) -> Optional[str]:
    """Match a transaction description to a category.

    Args:
        description: Transaction description text (e.g., "KFC DHA Phase 6")

    Returns:
        Matched category name string, or None if no match found.
    """
    if not description:
        return None

    desc_lower = description.lower().strip()

    for entry in KEYWORD_MAP:
        for keyword in entry["keywords"]:
            if keyword in desc_lower:
                return entry["category"]

    return None


def suggest_categories(description: str, top_n: int = 3) -> List[str]:
    """Return ranked category suggestions for a transaction description.

    Returns up to top_n category names, best match first.
    Falls back to ["Miscellaneous"] if nothing matches.
    """
    if not description:
        return ["Miscellaneous"]

    desc_lower = description.lower().strip()
    matches = []

    for entry in KEYWORD_MAP:
        score = sum(1 for kw in entry["keywords"] if kw in desc_lower)
        if score > 0:
            matches.append((entry["category"], score))

    if not matches:
        return ["Miscellaneous"]

    matches.sort(key=lambda x: -x[1])
    return [m[0] for m in matches[:top_n]]
