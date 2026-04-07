import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.environ.get("SQLITE_DB", "market_radar.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    try:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                password_hash TEXT NOT NULL,
                role TEXT CHECK(role IN ('superadmin','user')) DEFAULT 'user',
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_companies (
                user_id INTEGER,
                company_id INTEGER,
                PRIMARY KEY (user_id, company_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE RESTRICT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER,
                reference TEXT NOT NULL,
                name TEXT,
                source TEXT DEFAULT 'manual',
                category TEXT,
                sous_categorie TEXT,
                marque TEXT,
                pvc REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
                UNIQUE (reference, company_id)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS sites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER,
                name TEXT NOT NULL,
                domain TEXT NOT NULL,
                scraper_key TEXT NOT NULL,
                price_selector TEXT DEFAULT '',
                threshold REAL DEFAULT 0,
                enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
                UNIQUE (domain, company_id),
                UNIQUE (scraper_key, company_id)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS scrape_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER,
                type TEXT NOT NULL,
                status TEXT DEFAULT 'running',
                total INTEGER DEFAULT 0,
                done INTEGER DEFAULT 0,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                finished_at TIMESTAMP,
                FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS scrape_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                session_id INTEGER,
                site TEXT NOT NULL,
                url TEXT,
                price_raw TEXT,
                price REAL,
                availability TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
                FOREIGN KEY (session_id) REFERENCES scrape_sessions(id)
            )
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_results_product_site ON scrape_results(product_id, site, scraped_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_products_company ON products(company_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sites_company ON sites(company_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_company ON scrape_sessions(company_id)")

        conn.commit()
    finally:
        conn.close()
