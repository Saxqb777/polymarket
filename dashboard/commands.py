"""
Write-only mutations for the dashboard.

All functions return the updated trade row so callers don't need
a second query. Reads live in dashboard/queries.py.
"""
import sqlite3
import pathlib
import sys
from datetime import date
from typing import Optional

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import config


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _get_trade(run_id: int) -> Optional[dict]:
    with _conn() as conn:
        row = conn.execute("""
            SELECT r.*,
                   to2.outcome, to2.exit_date, to2.exit_price,
                   to2.pnl_dollars, to2.pnl_pct,
                   to2.notes AS outcome_notes, to2.closed_method
            FROM runs r
            LEFT JOIN trade_outcomes to2 ON r.id = to2.run_id
            WHERE r.id = ?
        """, (run_id,)).fetchone()
    return dict(row) if row else None


def mark_taken(run_id: int, actual_entry: float,
               actual_shares: float, notes: Optional[str] = None) -> Optional[dict]:
    with _conn() as conn:
        conn.execute("""
            UPDATE runs
            SET taken = 1, actual_entry = ?, actual_shares = ?, my_notes = ?
            WHERE id = ?
        """, (actual_entry, actual_shares, notes or None, run_id))
    return _get_trade(run_id)


def mark_skipped(run_id: int, skip_reason: Optional[str] = None) -> Optional[dict]:
    with _conn() as conn:
        conn.execute(
            "UPDATE runs SET taken = 0, skip_reason = ? WHERE id = ?",
            (skip_reason or None, run_id),
        )
    return _get_trade(run_id)


def log_outcome(run_id: int, exit_price: float, outcome: str,
                closed_method: str, notes: Optional[str] = None) -> Optional[dict]:
    trade = _get_trade(run_id)
    if not trade:
        return None

    entry  = trade.get("actual_entry")  or trade.get("entry_price")  or 0.0
    shares = trade.get("actual_shares") or 0.0

    pnl_dollars = round((exit_price - entry) * shares, 2)
    pnl_pct     = round((exit_price - entry) / entry * 100, 2) if entry else 0.0

    with _conn() as conn:
        conn.execute("""
            INSERT INTO trade_outcomes
              (run_id, symbol, entry_date, exit_date,
               entry_price, exit_price, shares,
               pnl_dollars, pnl_pct, outcome, notes, closed_method)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id, trade.get("symbol"),
            trade.get("run_date"), date.today().isoformat(),
            entry, exit_price, shares,
            pnl_dollars, pnl_pct,
            outcome, notes or None, closed_method,
        ))
    return _get_trade(run_id)


def reopen_trade(run_id: int) -> Optional[dict]:
    """Delete the outcome row so the trade is treated as open again."""
    with _conn() as conn:
        conn.execute("DELETE FROM trade_outcomes WHERE run_id = ?", (run_id,))
    return _get_trade(run_id)


def unskip_trade(run_id: int) -> Optional[dict]:
    """Reset taken/skip_reason so the trade is back to pending."""
    with _conn() as conn:
        conn.execute(
            "UPDATE runs SET taken = NULL, skip_reason = NULL WHERE id = ?",
            (run_id,),
        )
    return _get_trade(run_id)


def trim_position(run_id: int, shares_sold: float,
                  exit_price: float, reason: Optional[str] = None) -> Optional[dict]:
    """Sell a portion of shares, log the realized P&L, update remaining share count."""
    trade = _get_trade(run_id)
    if not trade:
        return None

    entry     = trade.get("actual_entry") or trade.get("entry_price") or 0.0
    remaining = trade.get("actual_shares") or 0.0

    if shares_sold <= 0 or shares_sold > remaining:
        return None

    pnl_dollars = round((exit_price - entry) * shares_sold, 2)
    pnl_pct     = round((exit_price - entry) / entry * 100, 2) if entry else 0.0

    with _conn() as conn:
        conn.execute("""
            INSERT INTO partial_exits
              (run_id, exit_date, shares_sold, exit_price, pnl_dollars, pnl_pct, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            run_id, date.today().isoformat(),
            shares_sold, exit_price,
            pnl_dollars, pnl_pct,
            reason or None,
        ))
        conn.execute(
            "UPDATE runs SET actual_shares = ? WHERE id = ?",
            (round(remaining - shares_sold, 8), run_id),
        )
    return _get_trade(run_id)


def edit_outcome(run_id: int, exit_price: float, pnl_dollars: float,
                 outcome: str, notes: Optional[str] = None) -> Optional[dict]:
    """Correct an already-closed trade's exit price and P&L."""
    trade = _get_trade(run_id)
    if not trade:
        return None

    entry  = trade.get("actual_entry") or trade.get("entry_price") or 0.0
    shares = trade.get("actual_shares") or 0.0
    pnl_pct = round(pnl_dollars / (entry * shares) * 100, 2) if entry and shares else 0.0

    with _conn() as conn:
        conn.execute("""
            UPDATE trade_outcomes
            SET exit_price = ?, pnl_dollars = ?, pnl_pct = ?, outcome = ?, notes = ?
            WHERE run_id = ?
        """, (exit_price, round(pnl_dollars, 2), pnl_pct, outcome, notes or None, run_id))
    return _get_trade(run_id)


def update_settings(starting_capital: float) -> None:
    """Upsert the single user_settings row."""
    with _conn() as conn:
        conn.execute("""
            INSERT INTO user_settings (id, starting_capital, updated_at)
            VALUES (1, ?, datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                starting_capital = excluded.starting_capital,
                updated_at       = excluded.updated_at
        """, (starting_capital,))
