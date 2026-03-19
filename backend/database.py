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
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            reference      TEXT UNIQUE NOT NULL,
            name           TEXT,
            source         TEXT DEFAULT 'manual',
            category       TEXT,
            sous_categorie TEXT,
            marque         TEXT,
            pvc            REAL,
            created_at     TEXT DEFAULT CURRENT_TIMESTAMP
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

        CREATE TABLE IF NOT EXISTS sites (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            name           TEXT NOT NULL,
            domain         TEXT NOT NULL UNIQUE,
            scraper_key    TEXT NOT NULL UNIQUE,
            price_selector TEXT NOT NULL,
            threshold      REAL NOT NULL DEFAULT 0,
            enabled        INTEGER NOT NULL DEFAULT 1,
            created_at     TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()

    # Safe migrations for existing databases
    for migration in [
        "ALTER TABLE products ADD COLUMN category TEXT",
        "ALTER TABLE products ADD COLUMN pvc REAL",
        "ALTER TABLE products ADD COLUMN sous_categorie TEXT",
        "ALTER TABLE products ADD COLUMN marque TEXT",
        "ALTER TABLE sites ADD COLUMN price_selector TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE sites ADD COLUMN threshold REAL NOT NULL DEFAULT 0",
    ]:
        try:
            conn.execute(migration)
            conn.commit()
        except Exception:
            pass  # Column already exists

    # Seed the 3 default sites
    for name, domain, scraper_key, price_selector in [
        ("Tunisianet", "tunisianet.com.tn", "tunisianet", "span.current-price-value"),
        ("Mytek",      "mytek.tn",          "mytek",      ".product-info-price span.price"),
        ("Spacenet",   "spacenet.tn",       "spacenet",   "span.current-price-value"),
    ]:
        conn.execute(
            "INSERT OR IGNORE INTO sites (name, domain, scraper_key, price_selector) VALUES (?, ?, ?, ?)",
            (name, domain, scraper_key, price_selector),
        )
    conn.commit()

    conn.close()
