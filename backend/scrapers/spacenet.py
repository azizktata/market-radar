"""
Spacenet scraper — PrestaShop-based site (same engine as Tunisianet, different selectors).
- Category discovery: paginates ?page=N, extracts reference from div.product-reference span
- Product page: same price/availability selectors as Tunisianet
"""

import re
import time
import random
import requests
from bs4 import BeautifulSoup
from scrapers._category_utils import extract_category

SITE = "spacenet"
DOMAIN = "spacenet.tn"
CATEGORY_URL = "https://spacenet.tn/159-electromenager-tunisie"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    )
}


def _get(url: str, timeout: int = 15) -> requests.Response | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp
    except Exception as e:
        print(f"[{SITE}] GET {url} failed: {e}")
        return None


def discover_products(progress_cb=None) -> list[dict]:
    """
    Crawl all paginated category pages and return a list of:
      {"reference": str, "name": str, "url": str, "site": SITE}
    """
    products = []
    page = 1

    while True:
        url = CATEGORY_URL if page == 1 else f"{CATEGORY_URL}?page={page}"
        print(f"[{SITE}] Fetching page {page}: {url}")
        resp = _get(url)
        if not resp:
            break

        soup = BeautifulSoup(resp.content, "html.parser")
        cards = soup.select("div.js-product-miniature, div.product-miniature")
        if not cards:
            print(f"[{SITE}] No products on page {page}, stopping.")
            break

        for card in cards:
            # Reference: <div class="product-reference"><label>Réf :</label><span>SKU</span></div>
            ref_el = card.select_one("div.product-reference span")
            name_el = card.select_one("h2.product_name a") or card.select_one(".product-title a")
            link_el = card.select_one("a.thumbnail.product-thumbnail")

            ref = ref_el.get_text(strip=True) if ref_el else None
            name = name_el.get_text(strip=True) if name_el else None
            href = link_el["href"] if link_el and link_el.get("href") else None

            if ref and href:
                products.append({"reference": ref, "name": name, "url": href, "site": SITE})

        if progress_cb:
            progress_cb(len(products))

        next_link = soup.select_one("a.js-search-link[rel='next']") or \
                    soup.select_one(".pagination .next a")
        if not next_link:
            has_next = soup.find("a", href=re.compile(rf"\?page={page + 1}"))
            if not has_next:
                break

        page += 1
        time.sleep(random.uniform(1.5, 3.0))

    print(f"[{SITE}] Discovery done. Found {len(products)} products.")
    return products


def scrape_product(url: str) -> dict:
    """
    Scrape price and availability from a single product page.
    """
    time.sleep(random.uniform(1.0, 2.5))
    resp = _get(url)
    result = {"price_raw": None, "price": None, "availability": None, "url": url}

    if not resp:
        return result

    soup = BeautifulSoup(resp.content, "html.parser")

    # Price
    price_el = (
        soup.select_one("span.current-price-value")
        or soup.select_one("span.current-price")
        or soup.select_one(".product-price span")
    )
    if price_el:
        raw = price_el.get_text(strip=True)
        result["price_raw"] = raw
        result["price"] = _parse_price(raw)

    # Availability
    avail_el = (
        soup.select_one("#product-availability span")
        or soup.select_one(".product-availability span")
        or soup.select_one("[id*='availability']")
    )
    if avail_el:
        result["availability"] = _normalize_availability(avail_el.get_text(strip=True))

    # Category from breadcrumb
    crumb_items = soup.select("nav.breadcrumb li")
    cat = extract_category(crumb_items)
    if cat:
        result["category"] = cat

    return result


def _normalize_availability(text: str) -> str:
    """Collapse multi-location availability text to a single canonical value."""
    t = text.lower()
    if any(x in t for x in ["disponible", "en stock", "in stock"]):
        return "Disponible"
    if "commande" in t:
        return "Sur commande"
    if any(x in t for x in ["épuisé", "epuise", "indisponible", "out of stock"]):
        return "Indisponible"
    return text.strip()


def _parse_price(raw: str) -> float | None:
    try:
        cleaned = re.sub(r"[^\d,\s]", "", raw).replace("\xa0", " ").strip()
        cleaned = re.sub(r"\s+", "", cleaned).replace(",", ".")
        return float(cleaned)
    except Exception:
        return None
