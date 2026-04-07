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

Bootstrap the first superadmin (required on a fresh DB):
```bash
cd backend
SUPERADMIN_EMAIL=admin@example.com SUPERADMIN_PASSWORD=secret python create_superadmin.py
```

Docker (full stack with nginx proxy on port 80):
```bash
docker-compose up --build
```

No test framework is configured yet.

## Architecture

**Frontend**: Next.js 16 App Router, React 19, TypeScript, Tailwind CSS v4, shadcn/ui (base-vega style backed by `@base-ui/react`), `@tanstack/react-table`.

**Backend**: Python FastAPI (`backend/`) with SQLite (`market_radar.db`). Background tasks handle long-running scrape jobs. Progress is polled via `GET /api/sessions/{id}`.

```
market-radar/
├── app/
│   ├── page.tsx                      # Main dashboard (client component)
│   ├── sites/page.tsx                # Sites management page
│   ├── login/page.tsx                # Login page
│   └── admin/page.tsx                # Superadmin panel (users/companies/assignments)
├── contexts/
│   └── company-context.tsx           # CompanyProvider + useCompany hook (user, currentCompany)
├── components/
│   ├── product-table.tsx             # @tanstack/react-table data grid
│   ├── add-product-dialog.tsx        # Single product entry modal
│   ├── import-excel-dialog.tsx       # Excel bulk import modal
│   ├── progress-bar.tsx              # Session progress display
│   ├── stats-cards.tsx               # Summary metric cards
│   └── ui/                           # shadcn primitives (Button, Table)
├── lib/
│   ├── api.ts                        # Fetch wrapper → NEXT_PUBLIC_API_URL (default http://localhost:8000)
│   ├── auth.ts                       # Thin client-side auth helpers (cookie is HttpOnly, cleared server-side)
│   └── utils.ts                      # cn() helper
├── middleware.ts                      # Next.js middleware (currently passthrough; matcher excludes /login)
└── backend/
    ├── main.py                       # FastAPI app, all routes, background tasks
    ├── database.py                   # SQLite init + get_conn()
    ├── auth.py                       # JWT creation/validation, cookie helpers, get_current_user dependency
    ├── create_superadmin.py          # One-shot script to seed the first superadmin + company
    └── scrapers/
        ├── generic.py                # Generic scraper using configurable CSS selectors
        ├── detector.py               # Auto-detects price CSS selector from a product URL
        ├── search.py                 # DuckDuckGo multi-strategy search with rate limiting
        ├── export.py                 # pandas + openpyxl Excel export
        └── _category_utils.py        # Shared breadcrumb → canonical category normalization
```

> The legacy site-specific scrapers (`tunisianet.py`, `spacenet.py`, `mytek.py`) still exist but are no longer used. All scraping goes through `generic.py`.

## Authentication & multi-tenancy

Auth uses **JWT stored in an HTTP-only cookie** (`auth_token`, 72 h by default). All protected endpoints use the `get_current_user` FastAPI dependency which reads and validates the cookie.

Two roles: `superadmin` (full access via `require_superadmin` dependency) and `user` (scoped to assigned companies via `check_company_access`).

Every data endpoint (products, sites, sessions, scrape, export) requires a `?company_id=<int>` query parameter. The backend verifies the caller has access to that company. Superadmins can access all companies; regular users only those in their `user_companies` rows.

Frontend state flows through `CompanyProvider` (`contexts/company-context.tsx`): it calls `GET /api/auth/me` on mount to hydrate `user`, `companies`, and `currentCompany`. All pages use `useCompany()` to get the current company ID.

## API endpoints

All endpoints except `/api/auth/*` and `/api/sites/detect` require authentication (HTTP-only cookie).

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/auth/login` | — | `{email, password}` → sets cookie, returns user + companies |
| POST | `/api/auth/logout` | — | Clears cookie |
| GET | `/api/auth/me` | user | Returns current user + companies |
| GET | `/api/products` | user | All products with latest scrape results (`?company_id=`) |
| POST | `/api/products` | user | Add single product (`?company_id=`) |
| POST | `/api/products/import` | user | Upload Excel (`?company_id=`) → `{added, skipped}` |
| DELETE | `/api/products` | user | Delete all products (`?company_id=`) |
| DELETE | `/api/products/{id}` | user | Delete one product (`?company_id=`) |
| GET | `/api/products/categories` | user | Distinct categories (`?company_id=`) |
| GET | `/api/sites` | user | List sites (`?company_id=`) |
| POST | `/api/sites` | user | Add site — auto-detects selector if `sample_url` provided (`?company_id=`) |
| PATCH | `/api/sites/{id}` | user | Update site fields (`?company_id=`); `sample_url` re-triggers detection |
| DELETE | `/api/sites/{id}` | user | Delete site (`?company_id=`) |
| POST | `/api/sites/detect` | — | Test selector auto-detection `{url}` → `{selector, price_sample}` |
| GET | `/api/sessions/{id}` | user | Poll session progress (`?company_id=`) |
| GET | `/api/sessions/latest` | user | Most recent scrape session (`?company_id=`) |
| POST | `/api/scrape` | user | Start scrape (`?company_id=`) → `{session_id}` |
| POST | `/api/scrape/stop` | user | Stop running scrape (`?company_id=`) |
| GET | `/api/export` | user | Download Excel (`?company_id=`) |
| GET | `/api/admin/users` | superadmin | List all users |
| POST | `/api/admin/users` | superadmin | Create user |
| PATCH | `/api/admin/users/{id}` | superadmin | Update user |
| DELETE | `/api/admin/users/{id}` | superadmin | Delete user |
| GET | `/api/admin/companies` | superadmin | List all companies |
| POST | `/api/admin/companies` | superadmin | Create company |
| PATCH | `/api/admin/companies/{id}` | superadmin | Update company |
| DELETE | `/api/admin/companies/{id}` | superadmin | Delete company |
| GET | `/api/admin/companies/{id}/users` | superadmin | List users in company |
| POST | `/api/admin/companies/{id}/users` | superadmin | Assign user to company `{user_id}` |
| DELETE | `/api/admin/companies/{id}/users/{uid}` | superadmin | Remove user from company |

Only one scrape job runs at a time **per company** (per-company mutex). Scrape uses `ThreadPoolExecutor(max_workers=5)`. A stopped session can be resumed by passing its `id` as `resume_from_session`.

## Database schema (SQLite)

Six tables:

- `companies` — `(name, created_at)`
- `users` — `(email UNIQUE, name, password_hash, role IN ('superadmin','user'), is_active, created_at)`
- `user_companies` — `(user_id→users, company_id→companies)` PK on both columns
- `products` — `(company_id→companies, reference, name, source, category, sous_categorie, marque, pvc, created_at)` UNIQUE on `(reference, company_id)`
- `scrape_sessions` — `(company_id→companies, type, status, total, done, started_at, finished_at)`
- `scrape_results` — `(product_id→products, session_id→scrape_sessions, site, url, price_raw, price, availability, scraped_at)` — rows accumulate; `GET /api/products` joins on the latest row per `(product_id, site)`
- `sites` — `(company_id→companies, name, domain, scraper_key, price_selector, threshold, enabled, created_at)` UNIQUE on `(domain, company_id)` and `(scraper_key, company_id)`

`price_raw` is the raw scraped string; `price` is a parsed float. `threshold` flags products whose scraped price exceeds PVC by that margin. Schema migrations are applied via `ALTER TABLE ... ADD COLUMN` in `database.py`.

## Dynamic site system

Sites are managed via the `sites` table rather than per-site Python files. `scraper_key` (auto-derived from domain, e.g. `tunisianet.com.tn` → `tunisianet`) becomes the column key for that site's data in `GET /api/products` responses.

**To add a new site**: use `POST /api/sites` with a `sample_url` pointing to any product page. The `detector.py` module will auto-detect the price CSS selector by:
1. Parsing JSON-LD structured data to get a known price value
2. Trying a prioritized list of candidate selectors (`CANDIDATE_SELECTORS` in `detector.py`)

`generic.py` scrapes all sites: it applies the stored `price_selector`, then falls back to `data-price-amount` attributes (Magento 2) and JSON-LD if the selector yields no parseable price.

## DuckDuckGo search (`scrapers/search.py`)

Uses three query strategies (ref-only → ref+name → name+tunisie), early exit on high-confidence score (≥120), exponential backoff retries, and region locked to `tn`. Once a URL is found for a `(product, site)` pair, it is reused on subsequent scrapes without re-querying DDGS.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET` | `dev-secret-change-in-production` | JWT signing key — change in production |
| `JWT_EXPIRE_HOURS` | `72` | Token lifetime |
| `SECURE_COOKIES` | `false` | Set `true` in production (HTTPS) |
| `CORS_ORIGIN` | `http://localhost:3000` | Allowed CORS origin |
| `SQLITE_DB` | `market_radar.db` | Path to SQLite file |
| `SUPERADMIN_EMAIL` | — | Used by `create_superadmin.py` |
| `SUPERADMIN_PASSWORD` | — | Used by `create_superadmin.py` |
| `SUPERADMIN_NAME` | `Super Admin` | Used by `create_superadmin.py` |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend URL used by frontend |

## UI language

The UI is in French (labels, error messages, button text). Keep new UI text in French.

## UI component system

Add new shadcn components with:
```bash
npx shadcn add <component>
```
Path alias `@/` maps to the project root.
