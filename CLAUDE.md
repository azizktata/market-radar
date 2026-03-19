# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the project

Two separate processes must run simultaneously:

```bash
# Python backend (FastAPI) — port 8000
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000

# Next.js frontend — port 3000
npm run dev
```

Other frontend commands:
```bash
npm run build   # production build
npm run lint    # ESLint
```

No test framework is configured yet.

## Architecture

**Frontend**: Next.js 16 App Router, React 19, TypeScript, Tailwind CSS v4, shadcn/ui (base-vega style backed by `@base-ui/react`), `@tanstack/react-table`.

**Backend**: Python FastAPI (`backend/`) with SQLite (`market_radar.db`). Background tasks handle long-running scrape/discover jobs. Progress is polled via `GET /api/sessions/{id}`.

```
market-radar/
├── app/page.tsx                      # Main dashboard (client component)
├── components/
│   ├── product-table.tsx             # @tanstack/react-table data grid
│   ├── add-product-dialog.tsx        # Bulk reference entry modal
│   ├── progress-bar.tsx              # Session progress display
│   ├── stats-cards.tsx               # Summary metric cards
│   └── ui/                           # shadcn primitives (Button, Table)
├── lib/
│   ├── api.ts                        # Fetch wrapper → http://localhost:8000
│   └── utils.ts                      # cn() helper
└── backend/
    ├── main.py                       # FastAPI app, all routes, background tasks
    ├── database.py                   # SQLite init + get_conn()
    └── scrapers/
        ├── tunisianet.py             # PrestaShop: discover (category pages) + scrape product page
        ├── spacenet.py               # PrestaShop: same pattern, different selectors
        ├── mytek.py                  # Magento 2: discover (listing → detail pages) + scrape
        ├── _category_utils.py        # Shared breadcrumb → canonical category normalization
        ├── search.py                 # DuckDuckGo multi-strategy search with rate limiting
        └── export.py                 # pandas + openpyxl Excel export
```

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/products` | All products with latest scrape results per site |
| POST | `/api/products` | Add single product `{reference, name?}` |
| POST | `/api/products/bulk` | Add multiple products `{references: string[]}` |
| DELETE | `/api/products/{id}` | Delete product |
| GET | `/api/sessions/{id}` | Poll session progress |
| GET | `/api/sessions/latest` | Most recent scrape session |
| GET | `/api/products/categories` | Distinct category values from products |
| POST | `/api/discover` | Start discover job `{sites?: string[]}` → `{session_id}` |
| POST | `/api/scrape` | Start scrape `{product_ids?: int[], resume_from_session?: int, categories?: string[]}` → `{session_id}` |
| POST | `/api/scrape/stop` | Signal running scrape to stop (graceful, finishes in-flight workers) |
| GET | `/api/export` | Download Excel file |

Only one job (discover or scrape) runs at a time (mutex). Scrape uses `ThreadPoolExecutor(max_workers=5)`. A stopped session can be resumed by passing its `id` as `resume_from_session`.

## Database schema (SQLite)

Three tables: `products` (reference, name, source, category, created_at), `scrape_sessions` (type, status, total, done, started_at, finished_at), `scrape_results` (product_id, session_id, site, url, price_raw, price, availability, scraped_at).

`price_raw` is the raw string scraped from the page; `price` is a parsed float. `category` on products is populated lazily from scrape results. `scrape_results` rows accumulate over sessions — `GET /api/products` always joins on the latest row per (product, site). The `category` column was added via safe migration (`ALTER TABLE ... ADD COLUMN`) so the schema and migration coexist in `database.py`.

## Domain-specific scraper notes

- **Tunisianet / Spacenet**: PrestaShop sites, paginate with `?page=N`. References on listing page (`span.product-reference` / `div.product-reference span`). Price: `span.current-price-value`. Availability: `#product-availability span`.
- **Mytek**: Magento 2. Listing uses `?p=N`. References are NOT on listing pages — must follow each product URL and read `table#product-attribute-specs-table`. Price: `.product-info-price span.price`. Availability: `div.stock`.

When adding a new site, add a new scraper file in `backend/scrapers/` with `discover_products()` and `scrape_product(url)` functions, then register it in `backend/main.py`. Use `extract_category()` from `_category_utils.py` to normalize breadcrumb categories — extend `CANONICAL` / `SECTION_LEVEL` there if needed rather than in the scraper itself.

## DuckDuckGo search (`scrapers/search.py`)

Adapted from `C:\Users\user\Desktop\projects\features-scraper\fiche-techniquev4.py` (lines 531–630). Uses three query strategies (ref-only → ref+name → name+tunisie), early exit on high-confidence score (≥120), exponential backoff retries, and region locked to `tn`.

## UI language

The UI is in French (labels, error messages, button text). Keep new UI text in French.

## UI component system

Add new shadcn components with:
```bash
npx shadcn add <component>
```
Path alias `@/` maps to the project root.
