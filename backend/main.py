"""
Market Radar — FastAPI backend
Run: uvicorn main:app --reload --port 8000
"""

import random
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from database import get_conn, init_db
from scrapers import mytek, spacenet, tunisianet
from scrapers.export import build_excel
from scrapers.search import search_product

SITES = ["tunisianet", "mytek", "spacenet"]
SITE_DOMAINS = {
    "tunisianet": "tunisianet.com.tn",
    "mytek": "mytek.tn",
    "spacenet": "spacenet.tn",
}
SITE_SCRAPERS = {
    "tunisianet": tunisianet.scrape_product,
    "mytek": mytek.scrape_product,
    "spacenet": spacenet.scrape_product,
}

# Mutex so only one scrape/discover job runs at a time
_job_lock = threading.Lock()
# Set to request cancellation of the running scrape job
_cancel_event = threading.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Market Radar API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ProductIn(BaseModel):
    reference: str
    name: str | None = None


class BulkProductIn(BaseModel):
    references: list[str]


# ---------------------------------------------------------------------------
# Helper: build product list with latest results
# ---------------------------------------------------------------------------

def _fetch_products_with_results() -> list[dict]:
    conn = get_conn()
    try:
        products = conn.execute(
            "SELECT id, reference, name, source, category, created_at FROM products ORDER BY created_at DESC"
        ).fetchall()

        result = []
        for p in products:
            row = dict(p)
            for site in SITES:
                latest = conn.execute(
                    """
                    SELECT price, price_raw, availability, url, scraped_at
                    FROM scrape_results
                    WHERE product_id = ? AND site = ?
                    ORDER BY scraped_at DESC LIMIT 1
                    """,
                    (p["id"], site),
                ).fetchone()
                row[site] = dict(latest) if latest else None
            result.append(row)
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

@app.get("/api/products")
def list_products():
    return _fetch_products_with_results()


@app.get("/api/products/categories")
def list_categories():
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT category FROM products WHERE category IS NOT NULL ORDER BY category ASC"
        ).fetchall()
        return [row["category"] for row in rows]
    finally:
        conn.close()


@app.post("/api/products", status_code=201)
def add_product(body: ProductIn):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO products (reference, name, source) VALUES (?, ?, 'manual')",
            (body.reference.strip(), body.name),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, reference, name, source, created_at FROM products WHERE reference = ?",
            (body.reference.strip(),),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


@app.post("/api/products/bulk", status_code=201)
def add_products_bulk(body: BulkProductIn):
    conn = get_conn()
    added = 0
    try:
        for ref in body.references:
            ref = ref.strip()
            if not ref:
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO products (reference, source) VALUES (?, 'manual')",
                (ref,),
            )
            added += cur.rowcount
        conn.commit()
        return {"added": added}
    finally:
        conn.close()


@app.delete("/api/products/{product_id}", status_code=204)
def delete_product(product_id: int):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Sessions (progress polling)
# ---------------------------------------------------------------------------

@app.get("/api/sessions/{session_id}")
def get_session(session_id: int):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id, type, status, total, done, started_at, finished_at FROM scrape_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        return dict(row)
    finally:
        conn.close()


@app.get("/api/sessions/latest")
def get_latest_session():
    """Returns the most recent scrape session (any status), or null."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id, type, status, total, done, started_at, finished_at FROM scrape_sessions"
            " WHERE type = 'scrape' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Discover — crawl category pages
# ---------------------------------------------------------------------------

def _run_discover(session_id: int, sites: list[str]):
    conn = get_conn()
    new_total = 0

    try:
        discover_fns = {
            "tunisianet": tunisianet.discover_products,
            "spacenet": spacenet.discover_products,
            "mytek": mytek.discover_products,
        }
        selected = {s: discover_fns[s] for s in sites if s in discover_fns}
        conn.execute(
            "UPDATE scrape_sessions SET total = ? WHERE id = ?",
            (len(selected), session_id),
        )
        conn.commit()

        done = 0
        for site, fn in selected.items():
            print(f"[DISCOVER] Starting {site}...")
            try:
                products = fn()
            except Exception as e:
                print(f"[DISCOVER] {site} failed: {e}")
                products = []

            # Upsert discovered products and store their URLs
            for p in products:
                ref = (p.get("reference") or "").strip()
                name = p.get("name")
                url = p.get("url")
                if not ref:
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO products (reference, name, source) VALUES (?, ?, 'discovered')",
                    (ref, name),
                )
                new_total += 1
                # Save the already-known URL for this site so "Scraper" can reuse it
                if url:
                    product_row = conn.execute(
                        "SELECT id FROM products WHERE reference = ?", (ref,)
                    ).fetchone()
                    if product_row:
                        conn.execute(
                            """INSERT INTO scrape_results (product_id, session_id, site, url)
                               VALUES (?, ?, ?, ?)""",
                            (product_row["id"], session_id, site, url),
                        )
            conn.commit()

            done += 1
            conn.execute(
                "UPDATE scrape_sessions SET done = ? WHERE id = ?",
                (done, session_id),
            )
            conn.commit()

        conn.execute(
            "UPDATE scrape_sessions SET status = 'done', finished_at = ?, total = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), new_total, session_id),
        )
        conn.commit()
        print(f"[DISCOVER] Done. {new_total} products upserted.")

    except Exception as e:
        print(f"[DISCOVER] Fatal error: {e}")
        conn.execute(
            "UPDATE scrape_sessions SET status = 'error', finished_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), session_id),
        )
        conn.commit()
    finally:
        conn.close()
        _job_lock.release()


class DiscoverIn(BaseModel):
    sites: list[str] = SITES


@app.post("/api/discover", status_code=202)
def start_discover(body: DiscoverIn, background_tasks: BackgroundTasks):
    if not _job_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A job is already running.")
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO scrape_sessions (type, status, total, done) VALUES ('discover', 'running', 0, 0)"
        )
        session_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    background_tasks.add_task(_run_discover, session_id, body.sites)
    return {"session_id": session_id}


# ---------------------------------------------------------------------------
# Scrape — find URLs + scrape prices
# ---------------------------------------------------------------------------

def _scrape_one(product_id: int, reference: str, name: str | None, site: str, session_id: int):
    """Worker: scrape price/availability for one product on one site.
    Reuses a previously discovered/stored URL when available; falls back to DuckDuckGo.
    Returns False immediately if cancellation was requested.
    """
    if _cancel_event.is_set():
        return False

    scraper = SITE_SCRAPERS[site]

    # Reuse an already-known URL to avoid unnecessary DDGS traffic
    conn_check = get_conn()
    try:
        existing = conn_check.execute(
            """SELECT url FROM scrape_results
               WHERE product_id = ? AND site = ? AND url IS NOT NULL
               ORDER BY scraped_at DESC LIMIT 1""",
            (product_id, site),
        ).fetchone()
    finally:
        conn_check.close()

    if existing and existing["url"]:
        url = existing["url"]
        print(f"[SCRAPE] {reference} @ {site}: reusing known URL")
    else:
        domain = SITE_DOMAINS[site]
        url, _ = search_product(name or reference, reference, domain)

    conn = get_conn()
    try:
        if url:
            result = scraper(url)
        else:
            result = {"price_raw": None, "price": None, "availability": None, "url": None}

        conn.execute(
            """
            INSERT INTO scrape_results (product_id, session_id, site, url, price_raw, price, availability)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product_id,
                session_id,
                site,
                result.get("url"),
                result.get("price_raw"),
                result.get("price"),
                result.get("availability"),
            ),
        )
        # Populate category from scrape result if not yet set
        category = result.get("category")
        if category:
            conn.execute(
                "UPDATE products SET category = ? WHERE id = ? AND category IS NULL",
                (category, product_id),
            )
        conn.commit()
        print(f"[SCRAPE] {reference} @ {site}: {result.get('price_raw')} | {result.get('availability')}")
        return True
    except Exception as e:
        print(f"[SCRAPE] Error {reference} @ {site}: {e}")
        return False
    finally:
        conn.close()


def _run_scrape(session_id: int, product_ids: list[int] | None, resume_from_session: int | None = None, categories: list[str] | None = None):
    _cancel_event.clear()
    conn = get_conn()
    try:
        if product_ids:
            placeholders = ",".join("?" * len(product_ids))
            rows = conn.execute(
                f"SELECT id, reference, name FROM products WHERE id IN ({placeholders})",
                product_ids,
            ).fetchall()
        elif categories:
            placeholders = ",".join("?" * len(categories))
            rows = conn.execute(
                f"SELECT id, reference, name FROM products WHERE category IN ({placeholders})",
                categories,
            ).fetchall()
        else:
            rows = conn.execute("SELECT id, reference, name FROM products").fetchall()

        all_tasks = [(dict(r), site) for r in rows for site in SITES]

        # Resume: skip (product_id, site) pairs already completed in the resumed session
        if resume_from_session:
            done_pairs = {
                (row["product_id"], row["site"])
                for row in conn.execute(
                    "SELECT product_id, site FROM scrape_results WHERE session_id = ?",
                    (resume_from_session,),
                ).fetchall()
            }
            tasks = [(r, site) for r, site in all_tasks if (r["id"], site) not in done_pairs]
            print(f"[SCRAPE] Resuming session {resume_from_session}: {len(all_tasks) - len(tasks)} already done, {len(tasks)} remaining.")
        else:
            tasks = all_tasks

        conn.execute(
            "UPDATE scrape_sessions SET total = ? WHERE id = ?", (len(tasks), session_id)
        )
        conn.commit()
    finally:
        conn.close()

    done = 0
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(_scrape_one, r["id"], r["reference"], r.get("name"), site, session_id): (r, site)
            for r, site in tasks
        }
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"[SCRAPE] Worker error: {e}")
            finally:
                done += 1
                _update_session_done(session_id, done)

    final_status = "stopped" if _cancel_event.is_set() else "done"
    _cancel_event.clear()
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE scrape_sessions SET status = ?, finished_at = ? WHERE id = ?",
            (final_status, datetime.now(timezone.utc).isoformat(), session_id),
        )
        conn.commit()
        print(f"[SCRAPE] Session {session_id} finished with status: {final_status}")
    finally:
        conn.close()
        _job_lock.release()


def _update_session_done(session_id: int, done: int):
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE scrape_sessions SET done = ? WHERE id = ?", (done, session_id)
        )
        conn.commit()
    finally:
        conn.close()


class ScrapeIn(BaseModel):
    product_ids: list[int] | None = None       # None = all products
    resume_from_session: int | None = None     # Resume a stopped session
    categories: list[str] | None = None        # Filter by category


@app.post("/api/scrape", status_code=202)
def start_scrape(body: ScrapeIn, background_tasks: BackgroundTasks):
    if not _job_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A job is already running.")
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO scrape_sessions (type, status, total, done) VALUES ('scrape', 'running', 0, 0)"
        )
        session_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    background_tasks.add_task(_run_scrape, session_id, body.product_ids, body.resume_from_session, body.categories)
    return {"session_id": session_id}


@app.post("/api/scrape/stop", status_code=200)
def stop_scrape():
    """Signal the running scrape job to stop after current in-flight workers finish."""
    if not _job_lock.locked():
        raise HTTPException(status_code=400, detail="No scrape job is currently running.")
    _cancel_event.set()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@app.get("/api/export")
def export_excel():
    products = _fetch_products_with_results()
    xlsx_bytes = build_excel(products)
    filename = f"market_radar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
