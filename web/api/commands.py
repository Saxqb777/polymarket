"""Write-side commands."""
import json
from datetime import date, datetime
from typing import Optional
from fastapi import HTTPException
from .db import get_db


def _audit(conn, action: str, run_id: Optional[int] = None, payload: Optional[dict] = None):
    conn.execute(
        "INSERT INTO audit_log (action, run_id, payload, created_at) VALUES (?,?,?,CURRENT_TIMESTAMP)",
        [action, run_id, json.dumps(payload) if payload else None]
    )


def take_pick(run_id: int, actual_entry: float, actual_shares: float) -> dict:
    with get_db() as conn:
        row = conn.execute("SELECT id, decision, taken FROM runs WHERE id=?", [run_id]).fetchone()
        if not row:
            raise HTTPException(404, "Pick not found")
        if row["decision"] != "TRADE":
            raise HTTPException(400, "Not a TRADE pick")
        conn.execute(
            "UPDATE runs SET taken=1, actual_entry=?, actual_shares=? WHERE id=?",
            [actual_entry, actual_shares, run_id]
        )
        _audit(conn, "take_pick", run_id, {"actual_entry": actual_entry, "actual_shares": actual_shares})
    return {"ok": True}


def skip_pick(run_id: int, reason: Optional[str] = None) -> dict:
    with get_db() as conn:
        row = conn.execute("SELECT id FROM runs WHERE id=?", [run_id]).fetchone()
        if not row:
            raise HTTPException(404, "Pick not found")
        conn.execute(
            "UPDATE runs SET skip_reason=? WHERE id=?",
            [reason or "skipped", run_id]
        )
        _audit(conn, "skip_pick", run_id, {"reason": reason})
    return {"ok": True}


def close_trade(run_id: int, exit_price: float, exit_date: Optional[str] = None,
                notes: Optional[str] = None) -> dict:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, actual_entry, actual_shares, symbol, run_date FROM runs WHERE id=?",
            [run_id]
        ).fetchone()
        if not row:
            raise HTTPException(404, "Trade not found")

        # Check already closed
        existing = conn.execute(
            "SELECT id FROM trade_outcomes WHERE run_id=?", [run_id]
        ).fetchone()
        if existing:
            raise HTTPException(400, "Trade already closed — use reopen first")

        entry = row["actual_entry"]
        shares = row["actual_shares"]
        if not entry or not shares:
            raise HTTPException(400, "Trade has no entry or shares")

        # Account for already-trimmed shares
        partial = conn.execute(
            "SELECT COALESCE(SUM(shares_sold),0) as s, COALESCE(SUM(pnl_dollars),0) as p FROM partial_exits WHERE run_id=?",
            [run_id]
        ).fetchone()
        trimmed_shares = partial["s"]
        partial_pnl = partial["p"]
        remaining = shares - trimmed_shares

        pnl_dollars = round((exit_price - entry) * remaining, 2)
        pnl_pct = round((exit_price - entry) / entry * 100, 2) if entry else 0
        outcome = "WIN" if pnl_dollars >= 0 else "LOSS"

        conn.execute("""
            INSERT INTO trade_outcomes
            (run_id, symbol, entry_date, exit_date, entry_price, exit_price, shares, pnl_dollars, pnl_pct, outcome, notes, closed_method)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,'manual')
        """, [
            run_id, row["symbol"], row["run_date"],
            exit_date or date.today().isoformat(),
            entry, exit_price, remaining,
            pnl_dollars, pnl_pct, outcome, notes
        ])
        _audit(conn, "close_trade", run_id, {"exit_price": exit_price})
    return {"ok": True, "pnl_dollars": pnl_dollars, "outcome": outcome}


def trim_trade(run_id: int, shares_sold: float, exit_price: float, reason: Optional[str] = None) -> dict:
    with get_db() as conn:
        row = conn.execute(
            "SELECT actual_entry, actual_shares FROM runs WHERE id=? AND taken=1",
            [run_id]
        ).fetchone()
        if not row:
            raise HTTPException(404, "Open trade not found")

        partial = conn.execute(
            "SELECT COALESCE(SUM(shares_sold),0) as s FROM partial_exits WHERE run_id=?",
            [run_id]
        ).fetchone()
        trimmed = partial["s"]
        remaining = (row["actual_shares"] or 0) - trimmed

        if shares_sold > remaining:
            raise HTTPException(400, f"Cannot sell {shares_sold} — only {remaining:.4f} remaining")

        entry = row["actual_entry"]
        pnl_dollars = round((exit_price - entry) * shares_sold, 2)
        pnl_pct = round((exit_price - entry) / entry * 100, 2) if entry else 0

        conn.execute("""
            INSERT INTO partial_exits (run_id, exit_date, shares_sold, exit_price, pnl_dollars, pnl_pct, reason, created_at)
            VALUES (?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
        """, [run_id, date.today().isoformat(), shares_sold, exit_price, pnl_dollars, pnl_pct, reason])
        _audit(conn, "trim_trade", run_id, {"shares_sold": shares_sold, "exit_price": exit_price})
    return {"ok": True, "pnl_dollars": pnl_dollars}


def reopen_trade(run_id: int) -> dict:
    with get_db() as conn:
        conn.execute("DELETE FROM trade_outcomes WHERE run_id=?", [run_id])
        _audit(conn, "reopen_trade", run_id)
    return {"ok": True}


def edit_trade(run_id: int, actual_entry: Optional[float], actual_shares: Optional[float],
               my_notes: Optional[str]) -> dict:
    with get_db() as conn:
        updates = []
        params = []
        if actual_entry is not None:
            updates.append("actual_entry=?"); params.append(actual_entry)
        if actual_shares is not None:
            updates.append("actual_shares=?"); params.append(actual_shares)
        if my_notes is not None:
            updates.append("my_notes=?"); params.append(my_notes)
        if not updates:
            return {"ok": True}
        params.append(run_id)
        conn.execute(f"UPDATE runs SET {', '.join(updates)} WHERE id=?", params)
        _audit(conn, "edit_trade", run_id)
    return {"ok": True}


def update_settings(starting_capital: Optional[float] = None, accent_color: Optional[str] = None) -> dict:
    with get_db() as conn:
        if starting_capital is not None:
            conn.execute(
                "UPDATE settings SET starting_capital=?, updated_at=CURRENT_TIMESTAMP WHERE id=1",
                [starting_capital]
            )
            # Also sync to bot's user_settings table if it exists
            try:
                conn.execute(
                    "UPDATE user_settings SET starting_capital=?, updated_at=CURRENT_TIMESTAMP WHERE id=1",
                    [starting_capital]
                )
            except Exception:
                pass
        if accent_color is not None:
            conn.execute("UPDATE settings SET accent_color=? WHERE id=1", [accent_color])
    return {"ok": True}
