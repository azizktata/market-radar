"""
Market Radar — FastAPI backend
Run: uvicorn main:app --reload --port 8000
"""

import io
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pandas as pd
from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel

from auth import (
    check_company_access,
    clear_auth_cookie,
    create_access_token,
    get_current_user,
    get_user_companies,
    require_superadmin,
    set_auth_cookie,
    verify_password,
)
from database import get_conn, init_db
from scrapers.export import build_excel
from scrapers.generic import scrape_product as generic_scrape
from scrapers.search import search_product

_job_locks: dict[int, threading.Lock] = {}
_job_locks_mutex = threading.Lock()
_cancel_events: dict[int, threading.Event] = {}


def _get_company_lock(company_id: int) -> tuple[threading.Lock, threading.Event]:
    with _job_locks_mutex:
        if company_id not in _job_locks:
            _job_locks[company_id] = threading.Lock()
            _cancel_events[company_id] = threading.Event()
        return _job_locks[company_id], _cancel_events[company_id]


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Market Radar API", lifespan=lifespan)

_cors_origin = os.environ.get("CORS_ORIGIN", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_cors_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_enabled_sites(conn, company_id: int) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT id, name, domain, scraper_key, price_selector, threshold FROM sites WHERE enabled = 1 AND company_id = ? ORDER BY id",
            (company_id,),
        ).fetchall()
    ]


def _fetch_products_with_results(company_id: int) -> list[dict]:
    conn = get_conn()
    try:
        products = conn.execute(
            "SELECT id, reference, name, source, category, sous_categorie, marque, pvc, created_at FROM products WHERE company_id = ? ORDER BY created_at DESC",
            (company_id,),
        ).fetchall()
        enabled_keys = [s["scraper_key"] for s in _get_enabled_sites(conn, company_id)]

        result = []
        for p in products:
            row = dict(p)
            for site_key in enabled_keys:
                latest = conn.execute(
                    """
                    SELECT price, price_raw, availability, url, scraped_at
                    FROM scrape_results pr
                    JOIN products p ON p.id = pr.product_id
                    WHERE p.company_id = ? AND pr.product_id = ? AND pr.site = ?
                    ORDER BY pr.scraped_at DESC LIMIT 1
                    """,
                    (company_id, p["id"], site_key),
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

class LoginIn(BaseModel):
    email: str
    password: str


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
    sample_url: str | None = None
    price_selector: str | None = None
    scraper_key: str | None = None
    threshold: float = 0
    enabled: bool = True


class SiteUpdate(BaseModel):
    name: str | None = None
    domain: str | None = None
    scraper_key: str | None = None
    price_selector: str | None = None
    sample_url: str | None = None
    threshold: float | None = None
    enabled: bool | None = None


class DetectIn(BaseModel):
    url: str


class ScrapeIn(BaseModel):
    product_ids: list[int] | None = None
    resume_from_session: int | None = None
    categories: list[str] | None = None


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@app.post("/api/auth/login")
def login(body: LoginIn, request: Request):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = ?", (body.email,))
        user = cur.fetchone()
        if not user or not verify_password(body.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Email ou mot de passe invalide")
        if not user["is_active"]:
            raise HTTPException(status_code=401, detail="Compte désactivé")

        token = create_access_token(user["id"], user["email"], user["role"])
        companies = get_user_companies(user["id"])

        response = JSONResponse({
            "user": {
                "id": user["id"],
                "email": user["email"],
                "name": user["name"],
                "role": user["role"],
                "companies": companies,
            }
        })
        set_auth_cookie(response, token)
        return response
    finally:
        conn.close()


@app.post("/api/auth/logout")
def logout():
    response = JSONResponse({"ok": True})
    clear_auth_cookie(response)
    return response


@app.get("/api/auth/me")
def get_me(user: dict = Depends(get_current_user)):
    companies = get_user_companies(user["id"])
    return {
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "role": user["role"],
            "companies": companies,
        }
    }


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

@app.get("/api/products")
def list_products(company_id: int = Query(...), user: dict = Depends(get_current_user)):
    check_company_access(user, company_id)
    return _fetch_products_with_results(company_id)


@app.get("/api/products/categories")
def list_categories(company_id: int = Query(...), user: dict = Depends(get_current_user)):
    check_company_access(user, company_id)
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT category FROM products WHERE company_id = ? AND category IS NOT NULL ORDER BY category ASC",
            (company_id,),
        ).fetchall()
        return [row["category"] for row in rows]
    finally:
        conn.close()


@app.post("/api/products", status_code=201)
def add_product(body: ProductIn, company_id: int = Query(...), user: dict = Depends(get_current_user)):
    check_company_access(user, company_id)
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO products (reference, name, category, sous_categorie, marque, pvc, company_id, source) VALUES (?, ?, ?, ?, ?, ?, ?, 'manual')",
            (body.reference.strip(), body.name, body.category, body.sous_categorie, body.marque, body.pvc, company_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, reference, name, source, category, sous_categorie, marque, pvc, created_at FROM products WHERE reference = ? AND company_id = ?",
            (body.reference.strip(), company_id),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


@app.delete("/api/products", status_code=200)
def clear_all_products(company_id: int = Query(...), user: dict = Depends(get_current_user)):
    check_company_access(user, company_id)
    conn = get_conn()
    try:
        cur = conn.execute("DELETE FROM products WHERE company_id = ?", (company_id,))
        conn.commit()
        return {"deleted": cur.rowcount}
    finally:
        conn.close()


@app.post("/api/products/import", status_code=201)
async def import_products_excel(file: UploadFile = File(...), company_id: int = Query(...), user: dict = Depends(get_current_user)):
    check_company_access(user, company_id)
    content = await file.read()
    try:
        df = pd.read_excel(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Impossible de lire le fichier Excel: {e}")

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
                "INSERT INTO products (reference, name, category, sous_categorie, marque, pvc, company_id, source) VALUES (?, ?, ?, ?, ?, ?, ?, 'manual')",
                (ref, name, category, sous_categorie, marque, pvc, company_id),
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
def delete_product(product_id: int, company_id: int = Query(...), user: dict = Depends(get_current_user)):
    check_company_access(user, company_id)
    conn = get_conn()
    try:
        conn.execute("DELETE FROM products WHERE id = ? AND company_id = ?", (product_id, company_id))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Sites
# ---------------------------------------------------------------------------

@app.get("/api/sites")
def list_sites(company_id: int = Query(...), user: dict = Depends(get_current_user)):
    check_company_access(user, company_id)
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, name, domain, scraper_key, price_selector, threshold, enabled, created_at FROM sites WHERE company_id = ? ORDER BY id",
            (company_id,),
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
def add_site(body: SiteIn, company_id: int = Query(...), user: dict = Depends(get_current_user)):
    check_company_access(user, company_id)
    scraper_key = body.scraper_key or _domain_to_key(body.domain)

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
            "INSERT INTO sites (name, domain, scraper_key, price_selector, threshold, enabled, company_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (body.name, body.domain, scraper_key, price_selector, body.threshold, int(body.enabled), company_id),
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
def update_site(site_id: int, body: SiteUpdate, company_id: int = Query(...), user: dict = Depends(get_current_user)):
    check_company_access(user, company_id)
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM sites WHERE id = ? AND company_id = ?", (site_id, company_id)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Site introuvable.")

        updates = body.model_dump(exclude_none=True)
        sample_url = updates.pop("sample_url", None)

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
def delete_site(site_id: int, company_id: int = Query(...), user: dict = Depends(get_current_user)):
    check_company_access(user, company_id)
    conn = get_conn()
    try:
        conn.execute("DELETE FROM sites WHERE id = ? AND company_id = ?", (site_id, company_id))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

@app.get("/api/sessions/latest")
def get_latest_session(company_id: int = Query(...), user: dict = Depends(get_current_user)):
    check_company_access(user, company_id)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id, type, status, total, done, started_at, finished_at FROM scrape_sessions"
            " WHERE type = 'scrape' AND company_id = ? ORDER BY started_at DESC LIMIT 1",
            (company_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


@app.get("/api/sessions/{session_id}")
def get_session(session_id: int, company_id: int = Query(...), user: dict = Depends(get_current_user)):
    check_company_access(user, company_id)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id, type, status, total, done, started_at, finished_at FROM scrape_sessions WHERE id = ? AND company_id = ?",
            (session_id, company_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        return dict(row)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Scrape
# ---------------------------------------------------------------------------

def _scrape_one(product_id: int, reference: str, name: str | None, site_row: dict, session_id: int, cancel_event: threading.Event):
    if cancel_event.is_set():
        return False

    site_key = site_row["scraper_key"]
    domain = site_row["domain"]
    price_selector = site_row["price_selector"]

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
            (product_id, session_id, site_key, result.get("url"), result.get("price_raw"), result.get("price"), None),
        )
        conn.commit()
        print(f"[SCRAPE] {reference} @ {site_key}: {result.get('price_raw')}")
        return True
    except Exception as e:
        print(f"[SCRAPE] Error {reference} @ {site_key}: {e}")
        return False
    finally:
        conn.close()


def _run_scrape(session_id: int, company_id: int, product_ids: list[int] | None, resume_from_session: int | None = None, categories: list[str] | None = None):
    lock, cancel_event = _get_company_lock(company_id)
    cancel_event.clear()

    conn = get_conn()
    try:
        if product_ids:
            placeholders = ",".join("?" for _ in product_ids)
            rows = conn.execute(
                f"SELECT id, reference, name FROM products WHERE company_id = ? AND id IN ({placeholders})",
                (company_id, *product_ids),
            ).fetchall()
        elif categories:
            placeholders = ",".join("?" for _ in categories)
            rows = conn.execute(
                f"SELECT id, reference, name FROM products WHERE company_id = ? AND category IN ({placeholders})",
                (company_id, *categories),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, reference, name FROM products WHERE company_id = ?",
                (company_id,),
            ).fetchall()

        enabled_sites = _get_enabled_sites(conn, company_id)
        site_map = {s["scraper_key"]: s for s in enabled_sites}

        all_tasks = [(dict(r), site_key) for r in rows for site_key in site_map]

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

        total_products = len(rows)
        product_remaining: dict[int, int] = {}
        for r, sk in tasks:
            pid = r["id"]
            product_remaining[pid] = product_remaining.get(pid, 0) + 1

        already_done = total_products - len(product_remaining)

        conn.execute(
            "UPDATE scrape_sessions SET total = ?, done = ? WHERE id = ?",
            (total_products, already_done, session_id),
        )
        conn.commit()
    finally:
        conn.close()

    done_products = already_done
    inner_lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(_scrape_one, r["id"], r["reference"], r.get("name"), site_map[site_key], session_id, cancel_event): (r, site_key)
            for r, site_key in tasks
        }
        for future in as_completed(futures):
            r, site_key = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"[SCRAPE] Worker error: {e}")
            finally:
                with inner_lock:
                    product_remaining[r["id"]] -= 1
                    if product_remaining[r["id"]] == 0:
                        done_products += 1
                        _update_session_done(session_id, done_products)

    final_status = "stopped" if cancel_event.is_set() else "done"
    cancel_event.clear()
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
    lock.release()


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
def start_scrape(body: ScrapeIn, background_tasks: BackgroundTasks, company_id: int = Query(...), user: dict = Depends(get_current_user)):
    check_company_access(user, company_id)
    lock, _ = _get_company_lock(company_id)
    if not lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Un scraping est déjà en cours pour cette entreprise.")

    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO scrape_sessions (type, status, total, done, company_id) VALUES ('scrape', 'running', 0, 0, ?)",
            (company_id,),
        )
        session_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    background_tasks.add_task(_run_scrape, session_id, company_id, body.product_ids, body.resume_from_session or None, body.categories)
    return {"session_id": session_id}


@app.post("/api/scrape/stop", status_code=200)
def stop_scrape(company_id: int = Query(...), user: dict = Depends(get_current_user)):
    check_company_access(user, company_id)
    lock, cancel_event = _get_company_lock(company_id)
    if not lock.locked():
        raise HTTPException(status_code=400, detail="Aucun scraping en cours.")
    cancel_event.set()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@app.get("/api/export")
def export_excel(company_id: int = Query(...), user: dict = Depends(get_current_user)):
    check_company_access(user, company_id)
    conn = get_conn()
    try:
        sites = _get_enabled_sites(conn, company_id)
    finally:
        conn.close()
    products = _fetch_products_with_results(company_id)
    xlsx_bytes = build_excel(products, sites)
    filename = f"market_radar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

@app.get("/api/admin/users")
def list_users(user: dict = Depends(require_superadmin)):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, email, name, role, is_active, created_at FROM users ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


class UserIn(BaseModel):
    email: str
    name: str | None = None
    password: str


@app.post("/api/admin/users", status_code=201)
def create_user(body: UserIn, user: dict = Depends(require_superadmin)):
    from auth import hash_password
    conn = get_conn()
    try:
        password_hash = hash_password(body.password)
        cur = conn.execute(
            "INSERT INTO users (email, name, password_hash, role, is_active) VALUES (?, ?, ?, 'user', 1)",
            (body.email, body.name, password_hash),
        )
        conn.commit()
        row = conn.execute("SELECT id, email, name, role, is_active, created_at FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


class UserUpdate(BaseModel):
    email: str | None = None
    name: str | None = None
    password: str | None = None
    role: str | None = None
    is_active: bool | None = None


@app.patch("/api/admin/users/{user_id}", status_code=200)
def update_user(user_id: int, body: UserUpdate, user: dict = Depends(require_superadmin)):
    from auth import hash_password
    conn = get_conn()
    try:
        updates = body.model_dump(exclude_none=True)
        if "password" in updates:
            updates["password_hash"] = hash_password(updates.pop("password"))
        if "is_active" in updates:
            updates["is_active"] = int(updates["is_active"])
        if not updates:
            row = conn.execute("SELECT id, email, name, role, is_active, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
            return dict(row) if row else HTTPException(status_code=404, detail="Utilisateur introuvable")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", (*updates.values(), user_id))
        conn.commit()
        row = conn.execute("SELECT id, email, name, role, is_active, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@app.delete("/api/admin/users/{user_id}", status_code=204)
def delete_user(user_id: int, user: dict = Depends(require_superadmin)):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


@app.get("/api/admin/companies")
def list_companies(user: dict = Depends(require_superadmin)):
    conn = get_conn()
    try:
        rows = conn.execute("SELECT id, name, created_at FROM companies ORDER BY id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


class CompanyIn(BaseModel):
    name: str


@app.post("/api/admin/companies", status_code=201)
def create_company(body: CompanyIn, user: dict = Depends(require_superadmin)):
    conn = get_conn()
    try:
        cur = conn.execute("INSERT INTO companies (name) VALUES (?)", (body.name,))
        conn.commit()
        row = conn.execute("SELECT id, name, created_at FROM companies WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@app.patch("/api/admin/companies/{company_id}", status_code=200)
def update_company(company_id: int, body: CompanyIn, user: dict = Depends(require_superadmin)):
    conn = get_conn()
    try:
        conn.execute("UPDATE companies SET name = ? WHERE id = ?", (body.name, company_id))
        conn.commit()
        row = conn.execute("SELECT id, name, created_at FROM companies WHERE id = ?", (company_id,)).fetchone()
        return dict(row) if row else HTTPException(status_code=404, detail="Entreprise introuvable")
    finally:
        conn.close()


@app.delete("/api/admin/companies/{company_id}", status_code=204)
def delete_company(company_id: int, user: dict = Depends(require_superadmin)):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM companies WHERE id = ?", (company_id,))
        conn.commit()
    finally:
        conn.close()


@app.get("/api/admin/companies/{company_id}/users")
def list_company_users(company_id: int, user: dict = Depends(require_superadmin)):
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT u.id, u.email, u.name, u.role, u.is_active, u.created_at
               FROM users u JOIN user_companies uc ON uc.user_id = u.id
               WHERE uc.company_id = ? ORDER BY u.email""",
            (company_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


class AssignUserIn(BaseModel):
    user_id: int


@app.post("/api/admin/companies/{company_id}/users", status_code=201)
def assign_user_to_company(company_id: int, body: AssignUserIn, user: dict = Depends(require_superadmin)):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO user_companies (user_id, company_id) VALUES (?, ?)",
            (body.user_id, company_id),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.delete("/api/admin/companies/{company_id}/users/{user_id}", status_code=204)
def remove_user_from_company(company_id: int, user_id: int, user: dict = Depends(require_superadmin)):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM user_companies WHERE user_id = ? AND company_id = ?", (user_id, company_id))
        conn.commit()
    finally:
        conn.close()
