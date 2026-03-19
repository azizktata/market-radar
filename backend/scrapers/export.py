"""
Excel export — generates a .xlsx file matching the spec column layout.
Lowest price per row is highlighted in green.
"""

import io
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter

SITES = ["tunisianet", "mytek", "spacenet"]

GREEN_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
RED_FILL   = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
HEADER_FILL = PatternFill(start_color="2D6A4F", end_color="2D6A4F", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF")

SITE_LABELS = {
    "tunisianet": "Tunisianet",
    "mytek":      "Mytek",
    "spacenet":   "Spacenet",
}

COLUMNS = ["Référence", "Nom"]
for site in SITES:
    label = SITE_LABELS[site]
    COLUMNS += [f"Prix {label}", f"Statut {label}", f"URL {label}"]
COLUMNS.append("Dernière mise à jour")


def build_excel(products: list[dict]) -> bytes:
    """
    products: list of dicts returned by GET /api/products
    Each dict has shape:
    {
      "id": int,
      "reference": str,
      "name": str | None,
      "tunisianet": {"price": float|None, "price_raw": str|None, "availability": str|None, "url": str|None, "scraped_at": str|None},
      "mytek":      { ... },
      "spacenet":   { ... },
    }
    Returns raw bytes of the .xlsx file.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Market Radar"

    # Header row
    for col_idx, col_name in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center")

    # Freeze header
    ws.freeze_panes = "A2"

    # Data rows
    for row_idx, product in enumerate(products, start=2):
        prices: list[tuple[float, int]] = []  # (price, col_index) for highlighting

        ws.cell(row=row_idx, column=1, value=product.get("reference", ""))
        ws.cell(row=row_idx, column=2, value=product.get("name") or "")

        col = 3
        last_scraped = None
        for site in SITES:
            data = product.get(site) or {}
            price = data.get("price")
            price_raw = data.get("price_raw") or ""
            avail = data.get("availability") or ""
            url = data.get("url") or ""
            scraped_at = data.get("scraped_at")

            ws.cell(row=row_idx, column=col,     value=price_raw)
            ws.cell(row=row_idx, column=col + 1, value=avail)
            link_cell = ws.cell(row=row_idx, column=col + 2, value=url)
            if url:
                link_cell.hyperlink = url
                link_cell.style = "Hyperlink"

            if price is not None:
                prices.append((price, col))

            if scraped_at and (last_scraped is None or scraped_at > last_scraped):
                last_scraped = scraped_at

            col += 3

        ws.cell(row=row_idx, column=len(COLUMNS), value=last_scraped or "")

        # Highlight cheapest / most expensive price in each row
        if prices:
            min_price = min(p for p, _ in prices)
            max_price = max(p for p, _ in prices)
            for price, col_idx in prices:
                cell = ws.cell(row=row_idx, column=col_idx)
                if price == min_price and len(prices) > 1:
                    cell.fill = GREEN_FILL
                elif price == max_price and len(prices) > 1:
                    cell.fill = RED_FILL

    # Auto-size columns (approximate)
    for col_idx, col_name in enumerate(COLUMNS, start=1):
        max_len = len(col_name) + 2
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = min(max_len, 40)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()
