"""
Market Radar — FastAPI backend
Run: uvicorn main:app --reload --port 8000
"""

import io
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pandas as pd
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from database import get_conn, init_db
from scrapers.export import build_excel
from scrapers.generic import scrape_product as generic_scrape
from scrapers.search import search_product

# Mutex so only one scrape job runs at a time
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
# Helpers
# ---------------------------------------------------------------------------

def _get_enabled_sites(conn) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT id, name, domain, scraper_key, price_selector, threshold FROM sites WHERE enabled = 1 ORDER BY id"
        ).fetchall()
    ]


def _fetch_products_with_results() -> list[dict]:
    conn = get_conn()
    try:
        products = conn.execute(
            "SELECT id, reference, name, source, category, sous_categorie, marque, pvc, created_at FROM products ORDER BY created_at DESC"
        ).fetchall()
        enabled_keys = [s["scraper_key"] for s in _get_enabled_sites(conn)]

        result = []
        for p in products:
            row = dict(p)
            for site_key in enabled_keys:
                latest = conn.execute(
                    """
                    SELECT price, price_raw, availability, url, scraped_at
                    FROM scrape_results
                    WHERE product_id = ? AND site = ?
                    ORDER BY scraped_at DESC LIMIT 1
                    """,
                    (p["id"], site_key),
                ).fetchone()
                row[site_key] = dict(latest) if latest else None
            result.append(row)
        return result
    finally:
        conn.close()


def _domain_to_key(domain: str) -> str:
    """Generate a scraper_key from a domain. tunisianet.com.tn → tunisianet"""
    d = re.sub(r"^www\.", "", domain.lower().strip())
    first = d.split(".")[0]
    return re.sub(r"[^a-z0-9]", "_", first)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ProductIn(BaseModel):
    reference: str
    name: str | None = None
    category: str | None = None
    sous_categorie: str | None = None
    marque: str | None = None
    pvc: float | None = None


class SiteIn(BaseModel):
    name: str
    domain: str
    sample_url: str | None = None      # used for auto-detection
    price_selector: str | None = None  # override; auto-detected if None + sample_url given
    scraper_key: str | None = None     # auto-generated from domain if None
    threshold: float = 0
    enabled: bool = True


class SiteUpdate(BaseModel):
    name: str | None = None
    domain: str | None = None
    scraper_key: str | None = None
    price_selector: str | None = None
    sample_url: str | None = None      # re-triggers detection on update
    threshold: float | None = None
    enabled: bool | None = None


class DetectIn(BaseModel):
    url: str


class ScrapeIn(BaseModel):
    product_ids: list[int] | None = None
    resume_from_session: int | None = None
    categories: list[str] | None = None


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
            "INSERT OR IGNORE INTO products (reference, name, category, sous_categorie, marque, pvc, source) VALUES (?, ?, ?, ?, ?, ?, 'manual')",
            (body.reference.strip(), body.name, body.category, body.sous_categorie, body.marque, body.pvc),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, reference, name, source, category, sous_categorie, marque, pvc, created_at FROM products WHERE reference = ?",
            (body.reference.strip(),),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


@app.delete("/api/products", status_code=200)
def clear_all_products():
    conn = get_conn()
    try:
        cur = conn.execute("DELETE FROM products")
        conn.commit()
        return {"deleted": cur.rowcount}
    finally:
        conn.close()


@app.post("/api/products/import", status_code=201)
async def import_products_excel(file: UploadFile = File(...)):
    content = await file.read()
    try:
        df = pd.read_excel(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Impossible de lire le fichier Excel: {e}")

    # Normalize column names: strip whitespace, lowercase for matching
    col_map: dict[str, str] = {}
    for col in df.columns:
        normalized = str(col).strip().lower()
        col_map[normalized] = col

    def find_col(*candidates: str) -> str | None:
        for c in candidates:
            if c.lower() in col_map:
                return col_map[c.lower()]
        return None

    ref_col = find_col("référence", "reference", "ref", "réf")
    if ref_col is None:
        raise HTTPException(status_code=400, detail="Colonne 'Référence' introuvable dans le fichier.")

    name_col = find_col("nom", "name")
    cat_col = find_col("catégorie", "categorie", "category")
    sous_cat_col = find_col("sous-catégorie", "sous catégorie", "sous_categorie", "sous-categorie")
    marque_col = find_col("marque", "brand")
    pvc_col = find_col("pvc")

    added = 0
    skipped = 0
    conn = get_conn()
    try:
        for _, row in df.iterrows():
            ref = str(row[ref_col]).strip() if row[ref_col] is not None else ""
            if not ref or ref.lower() == "nan":
                continue
            def _str_col(col):
                return str(row[col]).strip() if col and row[col] is not None and str(row[col]).lower() != "nan" else None

            name = _str_col(name_col)
            category = _str_col(cat_col)
            sous_categorie = _str_col(sous_cat_col)
            marque = _str_col(marque_col)
            pvc: float | None = None
            if pvc_col and row[pvc_col] is not None:
                try:
                    pvc = float(row[pvc_col])
                except (ValueError, TypeError):
                    pass

            cur = conn.execute(
                "INSERT OR IGNORE INTO products (reference, name, category, sous_categorie, marque, pvc, source) VALUES (?, ?, ?, ?, ?, ?, 'manual')",
                (ref, name, category, sous_categorie, marque, pvc),
            )
            if cur.rowcount > 0:
                added += 1
            else:
                skipped += 1
        conn.commit()
    finally:
        conn.close()

    return {"added": added, "skipped": skipped}


@app.delete("/api/products/{product_id}", status_code=204)
def delete_product(product_id: int):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Sites
# ---------------------------------------------------------------------------

@app.get("/api/sites")
def list_sites():
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, name, domain, scraper_key, price_selector, threshold, enabled, created_at FROM sites ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.post("/api/sites/detect")
def detect_site_selector(body: DetectIn):
    """Test auto-detection of price selector for a given product URL."""
    from scrapers.detector import detect_price_selector
    sel, sample = detect_price_selector(body.url)
    return {"selector": sel, "price_sample": sample}


@app.post("/api/sites", status_code=201)
def add_site(body: SiteIn):
    # Auto-generate scraper_key from domain if not provided
    scraper_key = body.scraper_key or _domain_to_key(body.domain)

    # Auto-detect price_selector from sample_url if not manually provided
    price_selector = body.price_selector or ""
    detected = False
    price_sample: str | None = None
    if body.sample_url and not body.price_selector:
        from scrapers.detector import detect_price_selector
        sel, sample = detect_price_selector(body.sample_url)
        if sel:
            price_selector = sel
            detected = True
            price_sample = sample

    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO sites (name, domain, scraper_key, price_selector, threshold, enabled) VALUES (?, ?, ?, ?, ?, ?)",
            (body.name, body.domain, scraper_key, price_selector, body.threshold, int(body.enabled)),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM sites WHERE id = ?", (cur.lastrowid,)).fetchone()
        result = dict(row)
        result["detected"] = detected
        result["price_sample"] = price_sample
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@app.patch("/api/sites/{site_id}", status_code=200)
def update_site(site_id: int, body: SiteUpdate):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Site introuvable.")

        updates = body.model_dump(exclude_none=True)
        # Remove sample_url from DB updates (it's not a column)
        sample_url = updates.pop("sample_url", None)

        # Re-detect selector if sample_url provided and price_selector not explicitly set
        if sample_url and "price_selector" not in updates:
            from scrapers.detector import detect_price_selector
            sel, _ = detect_price_selector(sample_url)
            if sel:
                updates["price_selector"] = sel

        if not updates:
            return dict(existing)
        if "enabled" in updates:
            updates["enabled"] = int(updates["enabled"])
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE sites SET {set_clause} WHERE id = ?",
            (*updates.values(), site_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@app.delete("/api/sites/{site_id}", status_code=204)
def delete_site(site_id: int):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM sites WHERE id = ?", (site_id,))
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
# Scrape — find URLs + scrape prices
# ---------------------------------------------------------------------------

def _scrape_one(product_id: int, reference: str, name: str | None, site_row: dict, session_id: int):
    """Worker: scrape price for one product on one site."""
    if _cancel_event.is_set():
        return False

    site_key = site_row["scraper_key"]
    domain = site_row["domain"]
    price_selector = site_row["price_selector"]

    # Reuse an already-known URL to avoid unnecessary DDGS traffic
    conn_check = get_conn()
    try:
        existing = conn_check.execute(
            """SELECT url FROM scrape_results
               WHERE product_id = ? AND site = ? AND url IS NOT NULL
               ORDER BY scraped_at DESC LIMIT 1""",
            (product_id, site_key),
        ).fetchone()
    finally:
        conn_check.close()

    if existing and existing["url"]:
        url = existing["url"]
        print(f"[SCRAPE] {reference} @ {site_key}: reusing known URL")
    else:
        url, _ = search_product(name or reference, reference, domain)

    conn = get_conn()
    try:
        if url:
            result = generic_scrape(url, price_selector)
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
                site_key,
                result.get("url"),
                result.get("price_raw"),
                result.get("price"),
                None,
            ),
        )
        conn.commit()
        print(f"[SCRAPE] {reference} @ {site_key}: {result.get('price_raw')}")
        return True
    except Exception as e:
        print(f"[SCRAPE] Error {reference} @ {site_key}: {e}")
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

        enabled_sites = _get_enabled_sites(conn)
        site_map = {s["scraper_key"]: s for s in enabled_sites}

        all_tasks = [(dict(r), site_key) for r in rows for site_key in site_map]

        # Resume: skip (product_id, site) pairs already completed in the resumed session
        if resume_from_session:
            done_pairs = {
                (row["product_id"], row["site"])
                for row in conn.execute(
                    "SELECT product_id, site FROM scrape_results WHERE session_id = ?",
                    (resume_from_session,),
                ).fetchall()
            }
            tasks = [(r, sk) for r, sk in all_tasks if (r["id"], sk) not in done_pairs]
            print(f"[SCRAPE] Resuming session {resume_from_session}: {len(all_tasks) - len(tasks)} already done, {len(tasks)} remaining.")
        else:
            tasks = all_tasks

        # Track total as number of unique products, not tasks
        total_products = len(rows)

        # Per-product remaining-task counter (used to detect when a product is fully done)
        product_remaining: dict[int, int] = {}
        for r, sk in tasks:
            pid = r["id"]
            product_remaining[pid] = product_remaining.get(pid, 0) + 1

        # Products with no remaining tasks are already done (resume scenario)
        already_done = total_products - len(product_remaining)

        conn.execute(
            "UPDATE scrape_sessions SET total = ?, done = ? WHERE id = ?",
            (total_products, already_done, session_id),
        )
        conn.commit()
    finally:
        conn.close()

    done_products = already_done
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(_scrape_one, r["id"], r["reference"], r.get("name"), site_map[site_key], session_id): (r, site_key)
            for r, site_key in tasks
        }
        for future in as_completed(futures):
            r, site_key = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"[SCRAPE] Worker error: {e}")
            finally:
                with lock:
                    product_remaining[r["id"]] -= 1
                    if product_remaining[r["id"]] == 0:
                        done_products += 1
                        _update_session_done(session_id, done_products)

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
    if not _job_lock.locked():
        raise HTTPException(status_code=400, detail="No scrape job is currently running.")
    _cancel_event.set()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@app.get("/api/export")
def export_excel():
    conn = get_conn()
    try:
        sites = _get_enabled_sites(conn)
    finally:
        conn.close()
    products = _fetch_products_with_results()
    xlsx_bytes = build_excel(products, sites)
    filename = f"market_radar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
