"""SQLite connection helper and schema migrations."""
import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", "data/trades.db")

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def ensure_tables():
    """Idempotent migrations — add new tables and columns without touching existing bot schema."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS daily_watch (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id      INTEGER NOT NULL REFERENCES runs(id),
                watch_date  TEXT    NOT NULL,
                verdict     TEXT    NOT NULL,
                confidence  TEXT,
                reasoning   TEXT,
                catalysts   TEXT,
                suggested_stop REAL,
                thesis_intact  INTEGER DEFAULT 1,
                price_at_watch REAL,
                created_at  TEXT    DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS news_archive (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol      TEXT    NOT NULL,
                run_id      INTEGER,
                url_hash    TEXT    NOT NULL,
                title       TEXT,
                source      TEXT,
                published_at TEXT,
                sentiment   TEXT,
                created_at  TEXT    DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(url_hash)
            );
            CREATE TABLE IF NOT EXISTS settings (
                id              INTEGER PRIMARY KEY CHECK (id = 1),
                starting_capital REAL    NOT NULL DEFAULT 10000.0,
                password_hash   TEXT,
                accent_color    TEXT    DEFAULT 'mint',
                updated_at      TEXT    DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                action      TEXT    NOT NULL,
                run_id      INTEGER,
                payload     TEXT,
                created_at  TEXT    DEFAULT CURRENT_TIMESTAMP
            );
        """)
        # Seed settings row if missing
        conn.execute("""
            INSERT OR IGNORE INTO settings (id, starting_capital, updated_at)
            SELECT 1, COALESCE(
                (SELECT starting_capital FROM user_settings WHERE id=1), 10000.0
            ), CURRENT_TIMESTAMP
        """)

def ensure_indexes():
    with get_db() as conn:
        conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_runs_decision ON runs(decision);
            CREATE INDEX IF NOT EXISTS idx_runs_taken ON runs(taken);
            CREATE INDEX IF NOT EXISTS idx_daily_watch_run_id ON daily_watch(run_id);
            CREATE INDEX IF NOT EXISTS idx_daily_watch_date ON daily_watch(watch_date);
            CREATE INDEX IF NOT EXISTS idx_partial_exits_run_id ON partial_exits(run_id);
        """)
