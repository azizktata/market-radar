"""
Generic product scraper using configurable CSS selectors.
Used for all sites whose price_selector is stored in the sites DB table.
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


def _parse_price(text: str) -> float | None:
    """Parse a price string to float, return None if unparseable or zero."""
    if not text:
        return None
    cleaned = re.sub(r"[^\d,.]", "", text).replace(",", ".")
    parts = cleaned.split(".")
    if len(parts) > 2:
        cleaned = "".join(parts[:-1]) + "." + parts[-1]
    try:
        value = float(cleaned)
        return value if value > 0 else None
    except (ValueError, TypeError):
        return None


def _price_from_jsonld(soup: BeautifulSoup) -> float | None:
    """Extract price from JSON-LD structured data as fallback."""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if "@graph" in item:
                    items = item["@graph"]
                    continue
                if item.get("@type") in ("Product", "product"):
                    offers = item.get("offers") or {}
                    if isinstance(offers, list):
                        offers = offers[0]
                    price = offers.get("price") or offers.get("lowPrice")
                    if price:
                        value = _parse_price(str(price))
                        if value:
                            return value
        except Exception:
            continue
    return None


def scrape_product(url: str, price_selector: str) -> dict:
    """
    Fetch a product page and extract the price using the provided CSS selector.

    Returns:
        {
            "price_raw": str | None,
            "price": float | None,
            "availability": None,   # not scraped; status is derived from PVC comparison
            "url": str,
        }
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[GENERIC] Failed to fetch {url}: {e}")
        return {"price_raw": None, "price": None, "availability": None, "url": url}

    soup = BeautifulSoup(resp.text, "html.parser")

    price_raw: str | None = None
    price: float | None = None

    el = soup.select_one(price_selector)
    if el:
        visible_text = el.get_text(strip=True)
        # Prefer the `content` attribute (PrestaShop / Schema.org itemprop pattern)
        # which holds a clean numeric value even when the text is JS-rendered
        content_attr = el.get("content")
        if content_attr:
            price = _parse_price(str(content_attr))
            if price:
                # Use visible text if it looks valid, otherwise format the content value
                price_raw = visible_text if _parse_price(visible_text) else str(content_attr).replace(".", ",")

        if not price:
            # Fall back to visible text
            price_raw = visible_text
            price = _parse_price(price_raw)

    # Magento 2 fallback: price is JS-rendered, but data-price-amount is in static HTML
    # Walk up from the matched element looking for data-price-amount on ancestors,
    # or search the whole page for [data-price-type="finalPrice"][data-price-amount].
    if not price:
        candidate = None
        if el:
            # Try ancestors first (e.g. span.price inside span.price-wrapper[data-price-amount])
            for ancestor in el.parents:
                amt = ancestor.get("data-price-amount")
                if amt:
                    candidate = str(amt)
                    break
        if not candidate:
            # Broader search: any element with data-price-type=finalPrice
            wrapper = soup.select_one('[data-price-type="finalPrice"][data-price-amount]')
            if wrapper:
                candidate = str(wrapper.get("data-price-amount"))
        if not candidate:
            # <meta itemprop="price" content="..."> (Magento 2 schema.org)
            meta = soup.select_one('meta[itemprop="price"][content]')
            if meta:
                candidate = str(meta.get("content"))
        if candidate:
            price = _parse_price(candidate)
            if price:
                price_raw = f"{price:.3f}".replace(".", ",")
                print(f"[GENERIC] Used data-price-amount/meta fallback for {url}: {price}")

    # Last resort: JSON-LD structured data (handles JS-rendered / combination products)
    if not price:
        price = _price_from_jsonld(soup)
        if price:
            # Format as Tunisian style: 45.0 → "45,000"
            price_raw = f"{price:.3f}".replace(".", ",")
            print(f"[GENERIC] Used JSON-LD fallback for {url}: {price}")

    return {"price_raw": price_raw, "price": price, "availability": None, "url": url}
