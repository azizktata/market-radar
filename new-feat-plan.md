
# Plan: Auth + Multi-company + MySQL + Docker Compose

## Context

The app is currently a single-tenant, unauthenticated tool. We need to add JWT authentication, multi-company tenancy (each company owns its own products, sites, and scrape data), a super admin who manages users and companies, and a production Docker Compose deployment. SQLite is replaced with MySQL (user has a fresh MySQL Docker container at localhost:3306, root, no password — no existing schema, no data migration needed).

 **MySQL bootstrap** : The local MySQL container has no database yet. `init_db()` will first create the `market_radar` database if it doesn't exist (connecting without a database), then create all tables. This is handled entirely in code — no manual SQL setup required.

---

## Key Decisions

* **Auth** : Custom JWT (python-jose + passlib[bcrypt]). No NextAuth.
* **Token storage** : HttpOnly cookie set by the backend on login. JavaScript cannot read it (XSS-safe). The browser sends it automatically on every request. Next.js middleware reads it natively via `request.cookies.get('auth_token')`.
* **Multi-tenancy** : `company_id` FK added to `products`, `sites`, `scrape_sessions`. All data endpoints require `?company_id=N`.
* **User roles** : `superadmin` (manages users/companies globally) or `user` (full access within assigned companies).
* **Company fields** : `id`, `name`, `created_at` only.
* **Users ↔ Companies** : Many-to-many — a user can belong to multiple companies.
* **Super admin bootstrap** : Seed script `backend/create_superadmin.py` reads env vars. Idempotent via `ON DUPLICATE KEY UPDATE name=VALUES(name)` — password hash is never overwritten on re-run.
* **Production** : Single VPS, Docker Compose (mysql + backend + frontend + nginx).

---

## Auth Flow: HttpOnly Cookie

### Why HttpOnly cookies over localStorage

|                    | localStorage              | HttpOnly Cookie                    |
| ------------------ | ------------------------- | ---------------------------------- |
| XSS vulnerability  | ❌ JS can steal token     | ✅ JS cannot read it               |
| CSRF risk          | ✅ Not sent automatically | ⚠️ Mitigated by `SameSite=Lax` |
| Next.js middleware | Needs extra plumbing      | ✅ Native `request.cookies`      |
| Mobile app support | ✅ Easy                   | ⚠️ Requires extra work           |

Since this is a web-only tool, HttpOnly cookies are strictly better.

### Login flow

1. `POST /api/auth/login` with `{email, password}` JSON body
2. Backend validates credentials, creates JWT, responds with:

   ```
   Set-Cookie: auth_token=<jwt>; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=259200
   ```

   Response body: `{user: {id, email, name, role, companies[]}}` — no raw token in body
3. Frontend stores `user` object in React context (company switcher, role checks)
4. Every subsequent fetch is `credentials: "include"` — browser sends the cookie automatically
5. Logout: `POST /api/auth/logout` → backend sets `auth_token=; Max-Age=0`

### Dev vs Production CORS

In dev (frontend `:3000`, backend `:8000` — different origins), cookies require:

```python
# FastAPI CORS — must be explicit origin, never "*" with credentials
allow_credentials=True
allow_origins=["http://localhost:3000"]
```

And every fetch call: `credentials: "include"`.

In production, nginx puts everything on the same origin — no CORS needed, cookies flow normally.

### `get_current_user` reads from cookie (not Authorization header)

```python
def get_current_user(request: Request) -> dict:
    token = request.cookies.get("auth_token")
    if not token:
        raise HTTPException(status_code=401, detail="Non authentifié")
    try:
        payload = decode_access_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalide")
    # fetch user row from DB, check is_active
    ...
```

---

## Critical PyMySQL Migration Gotchas

1. **No `conn.execute()`** — PyMySQL requires a cursor. Add a helper wrapper in `database.py`:

   ```python
   def execute(conn, sql, params=None):
       cur = conn.cursor()
       cur.execute(sql, params or ())
       return cur
   ```

   Then update ALL `conn.execute(...)` call sites throughout `main.py` to use this.
2. **No `executescript()`** — `init_db()` must call each `CREATE TABLE` statement individually.
3. **Placeholders** : `?` → `%s` everywhere.
4. **Syntax** : `INSERT OR IGNORE INTO` → `INSERT IGNORE INTO`.
5. **Remove PRAGMAs** (`journal_mode=WAL`, `foreign_keys=ON`) — MySQL doesn't use these.
6. **Charset** : All tables must use `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci`. PyMySQL connection must set `charset="utf8mb4"`.
7. **Thread safety** : PyMySQL connections are not thread-safe. The existing pattern of `get_conn()` per function call is correct — keep it.

---

## New MySQL Schema

```sql
-- New tables (create first — others FK to companies)
CREATE TABLE IF NOT EXISTS companies (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    name       VARCHAR(255) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS users (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    email         VARCHAR(255) NOT NULL UNIQUE,
    name          VARCHAR(255),
    password_hash VARCHAR(255) NOT NULL,
    role          ENUM('superadmin','user') NOT NULL DEFAULT 'user',
    is_active     TINYINT(1) NOT NULL DEFAULT 1,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_companies (
    user_id    INT NOT NULL,
    company_id INT NOT NULL,
    PRIMARY KEY (user_id, company_id),
    FOREIGN KEY (user_id)    REFERENCES users(id)     ON DELETE CASCADE,
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

Add `company_id INT` to existing tables via safe migrations in `init_db()`:

```sql
ALTER TABLE products        ADD COLUMN company_id INT;
ALTER TABLE sites           ADD COLUMN company_id INT;
ALTER TABLE scrape_sessions ADD COLUMN company_id INT;
```

Add indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_products_company        ON products(company_id);
CREATE INDEX IF NOT EXISTS idx_sites_company           ON sites(company_id);
CREATE INDEX IF NOT EXISTS idx_scrape_sessions_company ON scrape_sessions(company_id);
```

---

## New Files to Create

| File                             | Purpose                                                                                                                                                                        |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `backend/auth.py`              | JWT encode/decode,`hash_password`,`verify_password`,`get_current_user`dependency (reads HttpOnly cookie),`require_superadmin`dependency,`check_company_access`helper |
| `backend/create_superadmin.py` | Seed script — reads `SUPERADMIN_EMAIL/PASSWORD/NAME`from env, upserts superadmin user. Uses `ON DUPLICATE KEY UPDATE name=VALUES(name)`only — never overwrites password  |
| `backend/Dockerfile`           | `python:3.12-slim`, runs seed script then uvicorn                                                                                                                            |
| `lib/auth.ts`                  | `getUser()`,`setUser()`,`clearAuth()`— manages user object in memory/context only. No token handling (cookie is HttpOnly)                                               |
| `middleware.ts`                | Next.js edge middleware — checks `auth_token`cookie via `request.cookies.get('auth_token')`, redirects to `/login`if absent                                             |
| `contexts/company-context.tsx` | React Context holding `user`,`companies[]`,`currentCompany`,`setCurrentCompany`— populated from login response body                                                   |
| `app/login/page.tsx`           | Login form (email + password), calls `api.login()`with `credentials: "include"`, stores user in context, redirects to `/`                                                |
| `app/admin/page.tsx`           | Super admin panel — tabs: Utilisateurs / Entreprises / Affectations                                                                                                           |
| `Dockerfile.frontend`          | Multi-stage Node build using `output: 'standalone'`                                                                                                                          |
| `docker-compose.yml`           | 4 services: mysql (health check), backend, frontend, nginx                                                                                                                     |
| `nginx/nginx.conf`             | `/api/*`→`backend:8000`,`/`→`frontend:3000`                                                                                                                          |
| `.env.example`                 | Documents all env vars                                                                                                                                                         |

---

## Files to Modify

### `backend/requirements.txt`

Add: `PyMySQL>=1.1.0`, `python-jose[cryptography]>=3.3.0`, `passlib[bcrypt]>=1.7.4`, `python-dotenv>=1.0.0`

### `backend/database.py` (full rewrite)

* Replace `sqlite3` import with `pymysql` + `python-dotenv`
* Local dev defaults: `host=localhost`, `port=3306`, `user=root`, `password=""`, `db=market_radar`
* `get_conn()` returns `pymysql.connect(..., charset="utf8mb4", cursorclass=DictCursor)`
* `init_db()` two-step bootstrap:
  1. Connect **without** `database=` arg → `CREATE DATABASE IF NOT EXISTS \`market_radar`` → close
  2. Connect with `database=` → execute each `CREATE TABLE` individually (no `executescript`)
* Schema order: `companies` → `users` → `user_companies` → `products` (with `company_id`) → `sites` (with `company_id`) → `scrape_sessions` (with `company_id`) → `scrape_results`
* Safe migration block: `ALTER TABLE` for `company_id` on the three tables + existing column migrations
* Site seed uses `INSERT IGNORE INTO` (was `INSERT OR IGNORE`)

### `backend/main.py`

* Import `get_current_user`, `require_superadmin`, `check_company_access` from `auth`
* CORS:

  ```python
  allow_origins=[os.environ.get("CORS_ORIGIN", "http://localhost:3000")],
  allow_credentials=True,   # Required for HttpOnly cookie cross-origin in dev
  ```
* Replace global `_job_lock` / `_cancel_event` with per-company dicts:

  ```python
  _job_locks: dict[int, threading.Lock] = {}
  _job_locks_mutex = threading.Lock()
  _cancel_events: dict[int, threading.Event] = {}

  def _get_company_lock(company_id: int) -> threading.Lock:
      with _job_locks_mutex:
          if company_id not in _job_locks:
              _job_locks[company_id] = threading.Lock()
              _cancel_events[company_id] = threading.Event()
          return _job_locks[company_id]
  ```

  > ⚠️  **Important** : reset `_cancel_events[company_id]` at the **start** of each new scrape job, not just in `finally`. Otherwise a previously cancelled company can never scrape again in that process lifecycle.
  >
* All data endpoints: add `company_id: int` query param + `Depends(get_current_user)` + call `check_company_access(user, company_id)`
* All SQL queries: add `WHERE company_id = %s` / `AND company_id = %s`
* All `INSERT` for products/sites/sessions: include `company_id`
* `_run_scrape` / `_scrape_one`: accept and propagate `company_id`; release `_job_locks[company_id]` in `finally`

**New auth endpoints in `main.py`:**

```
POST   /api/auth/login     → sets HttpOnly cookie + returns {user {id, email, name, role, companies[]}}
POST   /api/auth/logout    → clears cookie (Max-Age=0)
GET    /api/auth/me        → returns {user} from current cookie session
```

**New admin endpoints in `main.py`:**

```
GET    /api/admin/users                          → list users (superadmin)
POST   /api/admin/users                          → create user {email, name, password} (superadmin)
PATCH  /api/admin/users/{id}                     → update user (superadmin)
DELETE /api/admin/users/{id}                     → delete user (superadmin)
GET    /api/admin/companies                      → list companies (superadmin)
POST   /api/admin/companies                      → create company {name} (superadmin)
PATCH  /api/admin/companies/{id}                 → rename company (superadmin)
DELETE /api/admin/companies/{id}                 → delete company (superadmin)
GET    /api/admin/companies/{id}/users           → list users of company (superadmin)
POST   /api/admin/companies/{id}/users           → assign user {user_id} (superadmin)
DELETE /api/admin/companies/{id}/users/{user_id} → remove assignment (superadmin)
```

### `lib/api.ts`

* `BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"`
* `req()` always passes `credentials: "include"` so the HttpOnly cookie is sent cross-origin in dev. No `Authorization` header logic needed.
* On 401 response → `clearAuth()` + redirect to `/login`
* All data methods (`getProducts`, `getSites`, `startScrape`, etc.) add `companyId: number` param → append `?company_id=${companyId}`
* Add `login(email, password)` — returns `{user}` from response body (no token handling), `logout()` — calls `POST /api/auth/logout`, `getMe()`
* New types: `User { id, email, name, role, companies[] }`, `Company { id, name, created_at }`, `LoginResponse { user: User }`

### `lib/auth.ts`

Simplified vs original plan — no token storage needed:

```typescript
// User object stored in React context only (from login response body)
// Cookie is HttpOnly — frontend never touches it

export function clearAuth() {
  // Just clear any local user state; cookie cleared server-side via /api/auth/logout
}
```

### `middleware.ts`

```typescript
import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export function middleware(request: NextRequest) {
  const token = request.cookies.get('auth_token')
  if (!token) {
    return NextResponse.redirect(new URL('/login', request.url))
  }
}

export const config = {
  matcher: ['/((?!login|_next/static|_next/image|favicon.ico).*)'],
}
```

### `app/layout.tsx`

Wrap `<body>` content in `<CompanyProvider>` (client component). Layout file itself stays as a server component.

### `components/nav-bar.tsx`

* Import `useCompany()` from context
* Render company tabs (one per company in `companies[]`; active = `currentCompany`)
* Clicking a tab calls `setCurrentCompany(c)` and navigates to `/`
* Add "Admin" link visible only when `user?.role === 'superadmin'`
* Add logout button: calls `api.logout()` (hits `/api/auth/logout` to clear cookie), then clears context, redirects to `/login`

### `app/page.tsx` and `app/sites/page.tsx`

* Import `useCompany()`
* All `api.*` calls receive `currentCompany.id` as first arg
* Show loading state while `isLoading || !currentCompany`

### `next.config.ts`

Add `output: 'standalone'` for Docker standalone build.

---

## `backend/auth.py` Structure

```python
JWT_SECRET       = os.environ.get("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALG          = "HS256"
JWT_EXPIRE_HOURS = int(os.environ.get("JWT_EXPIRE_HOURS", "72"))
COOKIE_NAME      = "auth_token"
pwd_context      = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(plain: str) -> str
def verify_password(plain: str, hashed: str) -> bool
def create_access_token(user_id, email, role) -> str   # encodes sub/email/role/exp
def decode_access_token(token: str) -> dict             # raises JWTError on failure

def set_auth_cookie(response: Response, token: str) -> None:
    # response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax",
    #                     secure=True, max_age=JWT_EXPIRE_HOURS*3600, path="/")

def clear_auth_cookie(response: Response) -> None:
    # response.delete_cookie(COOKIE_NAME, path="/")

def get_current_user(request: Request) -> dict:
    # reads request.cookies.get(COOKIE_NAME) → decodes → fetches user row
    # raises 401 if missing/invalid/inactive

def require_superadmin(user = Depends(get_current_user)) -> dict:
    # raises 403 if user["role"] != "superadmin"

def check_company_access(user: dict, company_id: int) -> None:
    # no-op for superadmin
    # queries user_companies for regular users; raises 403 if no match
```

---

## Docker Compose Overview

```
nginx:80 ──► frontend:3000  (Next.js standalone)
         └─► /api/* backend:8000   (FastAPI)
backend  ──► mysql:3306
```

`NEXT_PUBLIC_API_URL=""` — browser calls go to same origin `/api/...`, nginx routes them to backend. No CORS needed in production (same origin = no preflight).

`backend/Dockerfile` CMD:

```bash
sh -c "python create_superadmin.py && uvicorn main:app --host 0.0.0.0 --port 8000"
```

Seeds superadmin on every container start — idempotent, never overwrites password.

Nginx config notes:

* `proxy_read_timeout 300s` — scrape jobs can take several minutes
* Pass `Host` and real IP headers to backend
* Cookie `Secure` flag requires HTTPS in production — set up TLS termination at nginx

---

## Implementation Order

1. **`backend/requirements.txt`** — add new deps
2. **`backend/database.py`** — MySQL migration (blocks everything backend)
3. **`backend/auth.py`** + **`backend/create_superadmin.py`**
4. **`backend/main.py`** — auth (HttpOnly cookie) + company_id scoping + admin endpoints
5. **`lib/auth.ts`** + **`middleware.ts`** + **`lib/api.ts`** updates
6. **`contexts/company-context.tsx`** + **`app/layout.tsx`** update
7. **`app/login/page.tsx`**
8. **`components/nav-bar.tsx`** update
9. **`app/page.tsx`** + **`app/sites/page.tsx`** updates
10. **`app/admin/page.tsx`**
11. **Docker** files (`Dockerfile.frontend`, `backend/Dockerfile`, `docker-compose.yml`, `nginx/nginx.conf`, `.env.example`)
12. **`next.config.ts`** — add `output: 'standalone'`

---

## Verification

1. `pip install -r requirements.txt` — no errors
2. `python backend/create_superadmin.py` with env vars set — prints "Superadmin ready"
3. `uvicorn main:app --reload --port 8000` — starts without error; `GET /api/sites` returns 401
4. `POST /api/auth/login` with superadmin creds → response sets `auth_token` HttpOnly cookie; body returns `{user, companies[]}`
5. `GET /api/auth/me` with cookie present → returns user + companies
6. `POST /api/auth/logout` → cookie is cleared; subsequent `GET /api/auth/me` returns 401
7. Frontend: `npm run dev` → redirects unauthenticated requests to `/login`
8. Login as superadmin → reaches dashboard; company tabs visible
9. Create a company and user via `/admin` → assign user → log in as that user → sees only their company's data
10. Verify cancelled scrape job can be restarted (cancel event reset correctly)
11. `docker compose up --build` → all services start; `http://localhost` reaches login page; cookie works same-origin (no CORS)

---

## Environment Variables Reference (`.env.example`)

```bash
# MySQL
MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=changeme
MYSQL_DB=market_radar

# JWT
JWT_SECRET=change-this-to-a-long-random-string
JWT_EXPIRE_HOURS=72

# Superadmin seed
SUPERADMIN_EMAIL=admin@example.com
SUPERADMIN_PASSWORD=changeme
SUPERADMIN_NAME=Super Admin

# CORS (dev only — not needed in production with nginx same-origin)
CORS_ORIGIN=http://localhost:3000

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
```
