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

**Backend**: Python FastAPI (`backend/`) with SQLite (`market_radar.db`). Background tasks handle long-running scrape jobs. Progress is polled via `GET /api/sessions/{id}`.

```
market-radar/
├── app/page.tsx                      # Main dashboard (client component)
├── components/
│   ├── product-table.tsx             # @tanstack/react-table data grid
│   ├── add-product-dialog.tsx        # Single product entry modal
│   ├── import-excel-dialog.tsx       # Excel bulk import modal
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
        ├── generic.py                # Generic scraper using configurable CSS selectors
        ├── detector.py               # Auto-detects price CSS selector from a product URL
        ├── search.py                 # DuckDuckGo multi-strategy search with rate limiting
        ├── export.py                 # pandas + openpyxl Excel export
        └── _category_utils.py        # Shared breadcrumb → canonical category normalization
```

> The legacy site-specific scrapers (`tunisianet.py`, `spacenet.py`, `mytek.py`) still exist but are no longer used. All scraping goes through `generic.py`.

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/products` | All products with latest scrape results per enabled site |
| POST | `/api/products` | Add single product `{reference, name?, category?, sous_categorie?, marque?, pvc?}` |
| POST | `/api/products/import` | Upload Excel file (`multipart/form-data`) → `{added, skipped}` |
| DELETE | `/api/products` | Delete all products |
| DELETE | `/api/products/{id}` | Delete one product |
| GET | `/api/products/categories` | Distinct category values from products |
| GET | `/api/sites` | List all sites |
| POST | `/api/sites` | Add site `{name, domain, sample_url?, price_selector?, scraper_key?, threshold?, enabled?}` → auto-detects selector if `sample_url` provided |
| PATCH | `/api/sites/{id}` | Update site fields (partial); `sample_url` re-triggers detection |
| DELETE | `/api/sites/{id}` | Delete site |
| POST | `/api/sites/detect` | Test selector auto-detection `{url}` → `{selector, price_sample}` |
| GET | `/api/sessions/{id}` | Poll session progress |
| GET | `/api/sessions/latest` | Most recent scrape session |
| POST | `/api/scrape` | Start scrape `{product_ids?: int[], resume_from_session?: int, categories?: string[]}` → `{session_id}` |
| POST | `/api/scrape/stop` | Signal running scrape to stop (graceful, finishes in-flight workers) |
| GET | `/api/export` | Download Excel file |

Only one job runs at a time (mutex). Scrape uses `ThreadPoolExecutor(max_workers=5)`. A stopped session can be resumed by passing its `id` as `resume_from_session`.

## Database schema (SQLite)

Four tables:

- `products` — `(reference UNIQUE, name, source, category, sous_categorie, marque, pvc, created_at)`
- `scrape_sessions` — `(type, status, total, done, started_at, finished_at)`
- `scrape_results` — `(product_id→products, session_id→scrape_sessions, site, url, price_raw, price, availability, scraped_at)` — rows accumulate; `GET /api/products` joins on the latest row per `(product_id, site)`
- `sites` — `(name, domain UNIQUE, scraper_key UNIQUE, price_selector, threshold, enabled, created_at)` — seeded with Tunisianet, Mytek, Spacenet on first run

`price_raw` is the raw string scraped from the page; `price` is a parsed float. `threshold` on a site is used to flag products whose scraped price exceeds PVC by that margin. Schema migrations are applied safely via `ALTER TABLE ... ADD COLUMN` in `database.py`.

## Dynamic site system

Sites are managed via the `sites` table rather than per-site Python files. `scraper_key` (auto-derived from domain, e.g. `tunisianet.com.tn` → `tunisianet`) becomes the column key for that site's data in `GET /api/products` responses.

**To add a new site**: use `POST /api/sites` with a `sample_url` pointing to any product page. The `detector.py` module will auto-detect the price CSS selector by:
1. Parsing JSON-LD structured data to get a known price value
2. Trying a prioritized list of candidate selectors (`CANDIDATE_SELECTORS` in `detector.py`)

`generic.py` scrapes all sites: it applies the stored `price_selector`, then falls back to `data-price-amount` attributes (Magento 2) and JSON-LD if the selector yields no parseable price.

## DuckDuckGo search (`scrapers/search.py`)

Adapted from `C:\Users\user\Desktop\projects\features-scraper\fiche-techniquev4.py` (lines 531–630). Uses three query strategies (ref-only → ref+name → name+tunisie), early exit on high-confidence score (≥120), exponential backoff retries, and region locked to `tn`. Once a URL is found for a `(product, site)` pair, it is reused on subsequent scrapes without re-querying DDGS.

## UI language

The UI is in French (labels, error messages, button text). Keep new UI text in French.

## UI component system

Add new shadcn components with:
```bash
npx shadcn add <component>
```
Path alias `@/` maps to the project root.
