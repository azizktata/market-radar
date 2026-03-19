"""
DuckDuckGo search module — adapted from features-scraper/fiche-techniquev4.py
Finds the best matching product URL on a given domain for a reference + name.
"""

import re
import time
import random
import unicodedata
import traceback
from urllib.parse import urlparse

from ddgs import DDGS
from ddgs.exceptions import DDGSException

# --- Configuration ---
MAX_DDGS_RETRIES = 3
INITIAL_DDGS_SLEEP = 5
RANDOM_DDGS_DELAY = (2, 5)           # between different strategies
RANDOM_DDGS_DELAY_INTRA = (1, 2)     # between strategies on same domain
HIGH_CONFIDENCE_SCORE = 120
CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)

KNOWN_BRANDS = [
    "ASUS", "DELL", "HP", "LENOVO", "ACER", "MSI", "SAMSUNG", "LG", "SONY",
    "PHILIPS", "BEKO", "BRANDT", "ARISTON", "INDESIT", "WHIRLPOOL", "BOSCH",
    "SIEMENS", "ELECTROLUX", "CANDY", "HAIER", "HISENSE", "TCL", "PANASONIC",
    "SHARP", "TOSHIBA", "ORIENT", "CONDOR",
]

GENERIC_WORDS = {
    "de", "la", "le", "les", "du", "des", "un", "une", "avec", "pour", "et",
    "au", "aux", "en", "sur", "noir", "blanc", "gris", "silver", "tunisie",
}


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _normalize_for_url(text: str) -> list[str]:
    text = text.lower().strip()
    text = "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return [w for w in text.strip().split() if len(w) > 1]


def _weighted_word_score(product_name: str, slug: str) -> tuple[float, int]:
    name_clean = re.sub(r"\b(LED|4K|HZ|HDR|FULL|HD)\b", "", product_name, flags=re.I)
    name_words = _normalize_for_url(name_clean)
    slug_words = _normalize_for_url(slug)
    score, strong = 0.0, 0
    for w in name_words:
        if w in slug_words:
            if w in GENERIC_WORDS:
                score += 0.5
            else:
                score += 1.5
                strong += 1
    return score, strong


def _detect_conflicts(product_name: str, slug: str) -> float:
    pwords = " ".join(_normalize_for_url(product_name))
    swords = " ".join(_normalize_for_url(slug))
    conflicts = 0.0
    for kw in ["i3", "i5", "i7", "i9", "ryzen3", "ryzen5", "ryzen7", "ryzen9"]:
        if (kw in pwords) != (kw in swords):
            conflicts += 1
    for m in re.findall(r"\b\d+\s*(to|go)\b", pwords):
        if m not in swords:
            conflicts += 0.5
    return conflicts


def extract_brand(product_name: str) -> str:
    upper = product_name.upper()
    for brand in KNOWN_BRANDS:
        if re.search(r"\b" + re.escape(brand) + r"\b", upper):
            return brand
    return ""


def extract_model(product_name: str, brand: str) -> str:
    clean = product_name.upper()
    if brand:
        clean = clean.replace(brand.upper(), "")
    for pattern in [
        r"\b(\d+)\s?(INCH|POUCES|LED|IPS|VA|TN|OLED|4K|2K|HD|FHD|QHD|UHD|HDR\d*|CURVED)\b",
        r"\b(\d{2,4}\s?HZ)\b",
        r"\b(FREESYNC|GSYNC|GAMING|ULTRA|WIDE|ECRAN|MONITEUR|HD)\b",
    ]:
        clean = re.sub(pattern, " ", clean, flags=re.I)
    candidates = re.findall(r"[A-Z0-9]{2,}[A-Z0-9\-/:]*[A-Z0-9]+", clean)
    if candidates:
        best = max(candidates, key=len, default=None)
        if best and len(best) > 3:
            return re.sub(r"[^A-Z0-9]", "", best.upper())
    return ""


def has_minimum_matching_words(product_name: str, slug_url: str, min_matches: int = 5) -> bool:
    slug = urlparse(slug_url).path.split("/")[-1]
    slug = re.sub(r"\.html$", "", slug)
    score, strong = _weighted_word_score(product_name, slug)
    conflicts = _detect_conflicts(product_name, slug)
    word_count = len(_normalize_for_url(product_name))
    if word_count > 10 and word_count < 13:
        min_matches = 9
    elif word_count >= 13:
        min_matches = 11
    elif word_count <= 7:
        min_matches = word_count
    if strong == 0 or conflicts >= 2:
        return False
    return (score - conflicts * 2) >= min_matches


def score_url_match(product_name: str, product_reference: str, url: str) -> float:
    slug = re.sub(r"\.html$", "", urlparse(url).path.lower())
    score = 0.0
    if product_reference:
        ref_norm = re.sub(r"[^a-z0-9]", "", product_reference.lower())
        if ref_norm and len(ref_norm) > 2 and ref_norm in re.sub(r"[^a-z0-9]", "", slug):
            score += 100
    brand = extract_brand(product_name)
    model = extract_model(product_name, brand)
    if model and len(model) > 3 and model.lower() in re.sub(r"[^a-z0-9]", "", slug):
        score += 50
    if brand and brand.lower() in slug:
        score += 20
    word_score, _ = _weighted_word_score(product_name, slug)
    score += word_score
    score -= _detect_conflicts(product_name, slug) * 10
    return score


# ---------------------------------------------------------------------------
# Main search function
# ---------------------------------------------------------------------------

def search_product(product_name: str, product_reference: str, domain: str) -> tuple[str | None, float]:
    """
    Search for a product on a specific domain using DuckDuckGo.
    Returns (best_url, score) or (None, 0).
    """
    print(f"\n[DDGS] Searching '{product_name}' [{product_reference}] on {domain}...")
    custom_headers = {"User-Agent": CHROME_USER_AGENT}
    found_urls: set[str] = set()
    max_urls = 2
    site = f"site:{domain}"

    queries = []
    if product_reference and product_reference.strip():
        queries.append(f"{site} {product_reference}")
    queries.append(f"{site} {product_reference} {product_name}")

    for q_idx, query in enumerate(queries):
        if len(found_urls) >= max_urls:
            break

        if found_urls:
            best_score = max(score_url_match(product_name, product_reference, u) for u in found_urls)
            if best_score >= HIGH_CONFIDENCE_SCORE:
                print(f"[DDGS] High-confidence ({best_score:.1f}), skipping remaining strategies.")
                break

        print(f"[DDGS] Strategy {q_idx + 1}/{len(queries)}: '{query}'")

        for attempt in range(MAX_DDGS_RETRIES):
            with DDGS() as ddgs:
                try:
                    results = ddgs.text(
                        query,
                        region="tn",
                        safesearch="on",
                        headers=custom_headers,
                        max_results=2,
                    )
                    if results:
                        for r in results:
                            url = r["href"]
                            valid = (
                                has_minimum_matching_words(product_name, url, 5)
                                or has_minimum_matching_words(product_reference, url, 1)
                            )
                            if valid and url not in found_urls:
                                found_urls.add(url)
                                print(f"[DDGS] Kept: {url}")
                                if len(found_urls) >= max_urls:
                                    break
                            else:
                                print(f"[DDGS] Ignored: {url}")

                        delay = RANDOM_DDGS_DELAY_INTRA if q_idx < len(queries) - 1 else RANDOM_DDGS_DELAY
                        time.sleep(random.uniform(*delay))
                        break
                    else:
                        continue

                except DDGSException as e:
                    if attempt < MAX_DDGS_RETRIES - 1:
                        wait = INITIAL_DDGS_SLEEP * (2 ** attempt) + random.uniform(1, 3)
                        print(f"[DDGS] Error attempt {attempt + 1}: {e}. Retry in {wait:.1f}s")
                        time.sleep(wait)
                    else:
                        print(f"[DDGS] Persistent block after {MAX_DDGS_RETRIES} attempts.")
                        break

                except Exception as e:
                    print(f"[DDGS] Unexpected error: {e}")
                    traceback.print_exc()
                    break

    if found_urls:
        best = max(found_urls, key=lambda u: score_url_match(product_name, product_reference, u))
        return best, score_url_match(product_name, product_reference, best)
    return None, 0
