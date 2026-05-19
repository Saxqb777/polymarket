import sqlite3
import pathlib
from datetime import datetime
from typing import Optional

import config


def _connect(db_path: str = config.DB_PATH) -> sqlite3.Connection:
    pathlib.Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = config.DB_PATH) -> None:
    """Create all tables if they don't exist. Safe to call on every startup."""
    with _connect(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date            TEXT NOT NULL,
                run_timestamp       TEXT NOT NULL,
                candidates_scanned  INTEGER,
                candidates_passed   INTEGER,
                decision            TEXT,
                symbol              TEXT,
                entry_price         REAL,
                stop_loss           REAL,
                target_price        REAL,
                risk_reward         REAL,
                shares              INTEGER,
                position_value      REAL,
                risk_amount         REAL,
                confidence          TEXT,
                rationale           TEXT,
                no_trade_reason     TEXT,
                is_paper            INTEGER DEFAULT 1,
                telegram_sent       INTEGER DEFAULT 0,
                created_at          TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS trade_outcomes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id      INTEGER REFERENCES runs(id),
                symbol      TEXT,
                entry_date  TEXT,
                exit_date   TEXT,
                entry_price REAL,
                exit_price  REAL,
                shares      INTEGER,
                pnl_dollars REAL,
                pnl_pct     REAL,
                outcome     TEXT,
                notes       TEXT,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS monthly_stats (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                month             TEXT UNIQUE,
                total_trades      INTEGER DEFAULT 0,
                wins              INTEGER DEFAULT 0,
                losses            INTEGER DEFAULT 0,
                total_pnl         REAL DEFAULT 0.0,
                drawdown_pct      REAL DEFAULT 0.0,
                starting_capital  REAL,
                ending_capital    REAL,
                drawdown_breach   INTEGER DEFAULT 0,
                created_at        TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)


def log_run(run_data: dict, db_path: str = config.DB_PATH) -> int:
    """Insert a weekly run record. Returns the new row id."""
    fields = [
        "run_date", "run_timestamp", "candidates_scanned", "candidates_passed",
        "decision", "symbol", "entry_price", "stop_loss", "target_price",
        "risk_reward", "shares", "position_value", "risk_amount",
        "confidence", "rationale", "no_trade_reason",
        "quality_tier", "target_move_pct", "is_premium", "meets_quality_bar",
        "is_paper",
    ]
    values = [run_data.get(f) for f in fields]
    placeholders = ", ".join("?" * len(fields))
    columns = ", ".join(fields)

    with _connect(db_path) as conn:
        cursor = conn.execute(
            f"INSERT INTO runs ({columns}) VALUES ({placeholders})", values
        )
        return cursor.lastrowid


def update_telegram_status(run_id: int, success: bool, db_path: str = config.DB_PATH) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE runs SET telegram_sent = ? WHERE id = ?",
            (1 if success else 0, run_id),
        )


def check_monthly_drawdown(month: Optional[str] = None, db_path: str = config.DB_PATH) -> bool:
    """Return True if this month's realised losses have hit the -8% drawdown cap."""
    if month is None:
        month = datetime.now(config.GULF_TZ).strftime("%Y-%m")

    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(pnl_dollars), 0) AS total_pnl
            FROM trade_outcomes
            WHERE strftime('%Y-%m', exit_date) = ?
            """,
            (month,),
        ).fetchone()

    monthly_pnl = row["total_pnl"] if row else 0.0
    drawdown = abs(monthly_pnl) / config.ACCOUNT_CAPITAL if monthly_pnl < 0 else 0.0
    return drawdown >= config.MONTHLY_DRAWDOWN_CAP_PCT


def get_run_history(limit: int = 20, db_path: str = config.DB_PATH) -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
