"""
Mytek scraper — Magento 2-based site.
- Category discovery: paginates ?p=N, collects product page URLs from a.product-item-link,
  then visits each product page to extract the reference from the specs table.
- Product page: price (span.price), availability (.stock), reference from specs table.
"""

import re
import time
import random
import requests
from bs4 import BeautifulSoup
from scrapers._category_utils import extract_category

SITE = "mytek"
DOMAIN = "mytek.tn"
CATEGORY_URL = "https://www.mytek.tn/electromenager.html"
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


def _get_product_urls_from_page(soup: BeautifulSoup) -> list[str]:
    """Extract all product page URLs from a listing page."""
    urls = []
    for a in soup.select("a.product-item-link"):
        href = a.get("href", "").strip()
        if href and href.startswith("http"):
            urls.append(href)
    return list(dict.fromkeys(urls))  # deduplicate preserving order


def discover_products(progress_cb=None) -> list[dict]:
    """
    Crawl all paginated category pages, then visit each product page to extract the reference.
    Returns a list of {"reference": str, "name": str, "url": str, "site": SITE}

    NOTE: Mytek has ~thousands of products. This does two passes:
    Pass 1 — collect (name, url) from listing pages
    Pass 2 — visit each product page to get reference (uses ThreadPoolExecutor internally)
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Pass 1: collect product URLs + names from listing pages
    product_stubs = []  # [{"name": str, "url": str}]
    page = 1

    while True:
        url = CATEGORY_URL if page == 1 else f"{CATEGORY_URL}?p={page}"
        print(f"[{SITE}] Fetching listing page {page}: {url}")
        resp = _get(url)
        if not resp:
            break

        soup = BeautifulSoup(resp.content, "html.parser")
        product_links = soup.select("a.product-item-link")
        if not product_links:
            print(f"[{SITE}] No products on page {page}, stopping.")
            break

        for a in product_links:
            href = a.get("href", "").strip()
            name = a.get_text(strip=True)
            if href and href.startswith("http"):
                product_stubs.append({"name": name, "url": href})

        if progress_cb:
            progress_cb(len(product_stubs))

        # Check for next page
        next_page_link = soup.select_one("a.action.next") or \
                         soup.find("a", attrs={"title": re.compile(r"next|suivant", re.I)})
        if not next_page_link:
            break

        page += 1
        time.sleep(random.uniform(1.5, 3.0))

    print(f"[{SITE}] Pass 1 done. Found {len(product_stubs)} product URLs.")

    # Pass 2: visit each product page to get reference
    products = []

    def _fetch_ref(stub: dict) -> dict | None:
        time.sleep(random.uniform(0.8, 2.0))
        resp = _get(stub["url"])
        if not resp:
            return None
        soup = BeautifulSoup(resp.content, "html.parser")
        ref = _extract_reference(soup)
        if ref:
            return {"reference": ref, "name": stub["name"], "url": stub["url"], "site": SITE}
        return None

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_fetch_ref, stub): stub for stub in product_stubs}
        for future in as_completed(futures):
            result = future.result()
            if result:
                products.append(result)
                if progress_cb:
                    progress_cb(len(products))

    print(f"[{SITE}] Discovery done. Found {len(products)} products with references.")
    return products


def scrape_product(url: str) -> dict:
    """
    Scrape price and availability from a single Mytek product page.
    Price and stock are JS-rendered — we extract the product ID from raw HTML,
    then call the opensearch_api JSON endpoint to get the actual data.
    """
    time.sleep(random.uniform(1.0, 2.5))
    resp = _get(url)
    result = {"price_raw": None, "price": None, "availability": None, "url": url}

    if not resp:
        return result

    soup = BeautifulSoup(resp.content, "html.parser")

    # Extract product ID from the stock placeholder or price box
    product_id = None
    stock_el = soup.select_one("[data-role='stockStatus']")
    if stock_el:
        product_id = stock_el.get("data-product-id")
    if not product_id:
        price_box = soup.select_one("[data-price-box]")
        if price_box:
            product_id = price_box.get("data-product-id")

    if product_id:
        api_url = f"https://www.mytek.tn/opensearch_api/api/productData?ids={product_id}&productPage=1"
        api_resp = _get(api_url)
        if api_resp:
            try:
                data = api_resp.json().get(str(product_id), {})
                price = data.get("final_price") or data.get("price")
                if price is not None:
                    result["price_raw"] = f"{price} DT"
                    result["price"] = float(price)
                erpstock = data.get("erpstock", {})
                label = erpstock.get("label")
                if label:
                    result["availability"] = _normalize_availability(label)
            except Exception as e:
                print(f"[{SITE}] API parse error for product {product_id}: {e}")
    else:
        print(f"[{SITE}] Could not extract product_id from {url}")

    # Category from breadcrumb (Mytek breadcrumb is inverted: specific before general)
    crumb_items = soup.select(".breadcrumbs li")
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


def _extract_reference(soup: BeautifulSoup) -> str | None:
    """
    Extract the product reference from a Mytek product page.
    Tries the specs table first, then the SKU meta element.
    """
    # From specs table (existing pattern from features-scraper v4)
    product_table = soup.find("table", id="product-attribute-specs-table")
    if product_table:
        for row in product_table.find_all("tr"):
            label_cell = row.find("th", class_="col label")
            data_cell = row.find("td", class_="col data")
            if label_cell and data_cell:
                label = label_cell.get_text(strip=True).lower()
                if "référence" in label or "reference" in label or "réf" in label:
                    return data_cell.get_text(strip=True)

    # Fallback: .product.attribute.sku or meta[itemprop=sku]
    sku_el = soup.select_one(".product.attribute.sku .value") or \
             soup.select_one("[itemprop='sku']")
    if sku_el:
        return sku_el.get_text(strip=True)

    return None


def _parse_price(raw: str) -> float | None:
    try:
        cleaned = re.sub(r"[^\d,\s]", "", raw).replace("\xa0", " ").strip()
        cleaned = re.sub(r"\s+", "", cleaned).replace(",", ".")
        return float(cleaned)
    except Exception:
        return None
