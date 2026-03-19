"""
Auto-detects the price CSS selector for a product page.
Used when adding a new site so the user doesn't have to enter selectors manually.
"""

import json
import re
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    )
}

# Ordered list of candidate selectors to try (most specific first)
CANDIDATE_SELECTORS = [
    "span.current-price-value",         # PrestaShop (Tunisianet, Spacenet)
    ".product-info-price span.price",   # Magento 2 (Mytek)
    ".price-final_price span.price",    # Magento 2 alt
    "[itemprop='price']",               # Schema.org attribute
    ".woocommerce-Price-amount bdi",    # WooCommerce
    ".woocommerce-Price-amount",        # WooCommerce alt
    "span.price",                       # Generic
    "p.price",                          # Generic
    "#price-new",                       # OpenCart
    ".price-new",                       # OpenCart alt
    ".product-price",                   # Generic
    ".current-price",                   # Generic
    ".price",                           # Broad fallback
]


def _is_valid_price(text: str) -> bool:
    """Return True if text looks like a parseable positive price."""
    if not text:
        return False
    cleaned = re.sub(r"[^\d,.]", "", text).replace(",", ".")
    # Handle multiple dots (e.g. "1.299.000")
    parts = cleaned.split(".")
    if len(parts) > 2:
        cleaned = "".join(parts[:-1]) + "." + parts[-1]
    try:
        return float(cleaned) > 0
    except (ValueError, TypeError):
        return False


def detect_price_selector(url: str) -> tuple[str | None, str | None]:
    """
    Fetch a product page and attempt to detect the CSS selector for the price element.

    Returns:
        (selector, price_raw_sample) — first working selector and the price text found
        (None, None) — if no selector could be determined
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[DETECTOR] Failed to fetch {url}: {e}")
        return None, None

    soup = BeautifulSoup(resp.text, "html.parser")

    # 1. Try JSON-LD structured data first to get a known price value
    known_price_str: str | None = None
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            raw = script.string or ""
            data = json.loads(raw)
            items = data if isinstance(data, list) else [data]
            for item in items:
                # Handle @graph arrays
                if "@graph" in item:
                    items = item["@graph"]
                    continue
                if item.get("@type") in ("Product", "product"):
                    offers = item.get("offers") or {}
                    if isinstance(offers, list):
                        offers = offers[0]
                    price = offers.get("price") or offers.get("lowPrice")
                    if price:
                        known_price_str = str(price)
                        break
            if known_price_str:
                break
        except Exception:
            continue

    # 2. Try candidate CSS selectors
    for selector in CANDIDATE_SELECTORS:
        try:
            el = soup.select_one(selector)
            if not el:
                continue
            text = el.get_text(strip=True)
            # If we have a known price from JSON-LD, verify this element matches it
            if known_price_str:
                cleaned_known = re.sub(r"[^\d]", "", known_price_str)
                cleaned_found = re.sub(r"[^\d]", "", text)
                if cleaned_known and cleaned_found and cleaned_known[:4] in cleaned_found:
                    print(f"[DETECTOR] Matched JSON-LD price with selector: {selector} → {text}")
                    return selector, text
                # If no match, fall through to validity check
            if _is_valid_price(text):
                print(f"[DETECTOR] Found price selector: {selector} → {text}")
                return selector, text
        except Exception:
            continue

    print(f"[DETECTOR] No price selector found for {url}")
    return None, None
