"""
Idempotent schema migrations for the dashboard.

Called at dashboard startup. Uses PRAGMA table_info to check whether
each column already exists before issuing ALTER TABLE — safe to run
on every restart.
"""
import sqlite3
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import config


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def run(db_path: str = config.DB_PATH) -> None:
    """Apply all pending migrations. Safe to call repeatedly."""
    pathlib.Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)

    try:
        # ── runs table additions ──────────────────────────────────────────────
        existing_runs = _columns(conn, "runs")

        runs_additions = {
            # Dashboard tracking (user-filled)
            "taken":          "BOOLEAN DEFAULT NULL",
            "actual_entry":   "REAL DEFAULT NULL",
            "actual_shares":  "REAL DEFAULT NULL",
            "skip_reason":    "TEXT DEFAULT NULL",
            "my_notes":       "TEXT DEFAULT NULL",
            # Analyst quality fields (bot-filled from analyst result)
            "quality_tier":     "TEXT DEFAULT NULL",
            "target_move_pct":  "REAL DEFAULT NULL",
            "is_premium":       "INTEGER DEFAULT NULL",
            "meets_quality_bar":"INTEGER DEFAULT NULL",
        }

        for col, definition in runs_additions.items():
            if col not in existing_runs:
                conn.execute(f"ALTER TABLE runs ADD COLUMN {col} {definition}")
                print(f"  migration: runs.{col} added")

        # ── trade_outcomes table additions ────────────────────────────────────
        existing_outcomes = _columns(conn, "trade_outcomes")

        outcomes_additions = {
            "closed_method": "TEXT DEFAULT 'manual'",
        }

        for col, definition in outcomes_additions.items():
            if col not in existing_outcomes:
                conn.execute(f"ALTER TABLE trade_outcomes ADD COLUMN {col} {definition}")
                print(f"  migration: trade_outcomes.{col} added")

        # ── user_settings table ───────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                id               INTEGER PRIMARY KEY CHECK (id = 1),
                starting_capital REAL    NOT NULL DEFAULT 250.0,
                updated_at       TEXT    NOT NULL
            )
        """)
        conn.execute("""
            INSERT OR IGNORE INTO user_settings (id, starting_capital, updated_at)
            VALUES (1, ?, datetime('now'))
        """, (config.ACCOUNT_CAPITAL,))

        # ── partial_exits table ───────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS partial_exits (
                id          INTEGER PRIMARY KEY,
                run_id      INTEGER NOT NULL,
                exit_date   TEXT    NOT NULL,
                shares_sold REAL    NOT NULL,
                exit_price  REAL    NOT NULL,
                pnl_dollars REAL    NOT NULL,
                pnl_pct     REAL    NOT NULL,
                reason      TEXT,
                created_at  TEXT    NOT NULL,
                FOREIGN KEY (run_id) REFERENCES runs(id)
            )
        """)

        conn.commit()

    finally:
        conn.close()
