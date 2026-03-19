import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "market_radar.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            reference  TEXT UNIQUE NOT NULL,
            name       TEXT,
            source     TEXT DEFAULT 'manual',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS scrape_sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            type        TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'running',
            total       INTEGER DEFAULT 0,
            done        INTEGER DEFAULT 0,
            started_at  TEXT DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT
        );

        CREATE TABLE IF NOT EXISTS scrape_results (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id   INTEGER REFERENCES products(id) ON DELETE CASCADE,
            session_id   INTEGER REFERENCES scrape_sessions(id),
            site         TEXT NOT NULL,
            url          TEXT,
            price_raw    TEXT,
            price        REAL,
            availability TEXT,
            scraped_at   TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_results_product_site
            ON scrape_results(product_id, site, scraped_at DESC);
    """)
    conn.commit()

    # Safe migration: add category column if it doesn't exist yet
    try:
        conn.execute("ALTER TABLE products ADD COLUMN category TEXT")
        conn.commit()
    except Exception:
        pass  # Column already exists

    conn.close()
