# Project Guidelines

## Code Style
- Keep frontend code in TypeScript with React function components and explicit props/types.
- Use `"use client"` only for interactive components that need browser APIs or state.
- Prefer existing path alias imports (`@/`) over deep relative imports.
- Reuse existing UI primitives in `components/ui/` and `cn()` from `lib/utils.ts` for class composition.
- Keep backend scraper modules small and focused: site-specific selectors in their own file under `backend/scrapers/`.

## Architecture
- Frontend (`app/`, `components/`, `lib/`) is a Next.js App Router client dashboard.
- Backend (`backend/`) is a FastAPI service with SQLite (`backend/market_radar.db`) and background jobs.
- API contract is centralized in `lib/api.ts`; update shared types there when backend payloads change.
- Scrapers are pluggable modules (`discover_products`, `scrape_product`) registered/orchestrated by `backend/main.py`.

## Build and Run
- Frontend dev: `npm run dev` (port 3000)
- Frontend build: `npm run build`
- Frontend lint: `npm run lint`
- Backend install: `cd backend && pip install -r requirements.txt`
- Backend dev server: `cd backend && python -m uvicorn main:app --reload --port 8000`
- No automated test framework is configured; validate changes with manual end-to-end checks.

## Backend and Frontend Workflow
- Run frontend and backend at the same time. The UI depends on backend APIs at `http://localhost:8000`.
- Typical flow:
  1. Start FastAPI backend and ensure it logs startup on port 8000.
  2. Start Next.js frontend on port 3000.
  3. Trigger discover/scrape from UI, then poll session progress via `/api/sessions/{id}` (handled in `app/page.tsx`).
  4. Confirm results render in `components/product-table.tsx` and persisted rows exist in SQLite.
- Backend jobs are serialized with a lock and can be canceled; avoid introducing parallel task paths that bypass session/progress updates.

## Conventions
- CORS currently allows `http://localhost:3000`; update `backend/main.py` if frontend origin changes.
- Tunisianet and Spacenet use PrestaShop pagination (`?page=N`), while Mytek requires detail-page traversal to extract references.
- DuckDuckGo fallback search is region-locked to Tunisia (`tn`) and uses multi-strategy queries.
- Prefer extending current patterns instead of introducing new state/data layers unless necessary.

## Key Files
- `app/page.tsx`: frontend orchestration and polling lifecycle
- `lib/api.ts`: backend API methods and shared TS types
- `backend/main.py`: route handlers and background session workflow
- `backend/database.py`: schema and connection setup
- `backend/scrapers/tunisianet.py`: reference scraper structure
