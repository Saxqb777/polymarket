"""Read-side queries: adapts the bot's schema to clean API responses."""
import json
from datetime import date, datetime, timedelta
from typing import Optional
from .db import get_db


def _row_to_dict(row) -> dict:
    return dict(row) if row else {}


def get_overview() -> dict:
    with get_db() as conn:
        # Starting capital
        cap_row = conn.execute("SELECT starting_capital FROM settings WHERE id=1").fetchone()
        starting = cap_row["starting_capital"] if cap_row else 10000.0

        # Closed P&L from trade_outcomes
        closed = conn.execute("""
            SELECT COALESCE(SUM(to2.pnl_dollars), 0) as closed_pnl
            FROM trade_outcomes to2
        """).fetchone()
        closed_pnl = closed["closed_pnl"] if closed else 0.0

        # Partial exits P&L
        partial = conn.execute("SELECT COALESCE(SUM(pnl_dollars),0) as p FROM partial_exits").fetchone()
        partial_pnl = partial["p"] if partial else 0.0

        total_pnl = closed_pnl + partial_pnl
        account_value = starting + total_pnl
        pnl_pct = (total_pnl / starting * 100) if starting else 0.0

        # Open positions (taken but no trade_outcome)
        open_rows = conn.execute("""
            SELECT r.id, r.symbol, r.actual_entry, r.actual_shares, r.stop_loss, r.target_price,
                   r.entry_price, r.confidence, r.quality_tier, r.run_date,
                   COALESCE(pe_agg.trimmed_shares, 0) as trimmed_shares,
                   COALESCE(pe_agg.trimmed_pnl, 0) as trimmed_pnl
            FROM runs r
            LEFT JOIN (
                SELECT run_id,
                       SUM(shares_sold) as trimmed_shares,
                       SUM(pnl_dollars) as trimmed_pnl
                FROM partial_exits GROUP BY run_id
            ) pe_agg ON pe_agg.run_id = r.id
            LEFT JOIN trade_outcomes to2 ON to2.run_id = r.id
            WHERE r.taken = 1 AND to2.id IS NULL AND r.decision = 'TRADE'
        """).fetchall()

        open_positions = []
        for row in open_rows:
            d = _row_to_dict(row)
            remaining = (d.get("actual_shares") or 0) - d["trimmed_shares"]
            open_positions.append({
                **d,
                "shares_remaining": round(remaining, 8),
            })

        # Next daily watch (next weekday at 16:00 Gulf = 12:00 UTC)
        now = datetime.utcnow()
        next_watch = _next_weekday_watch(now)

        # Market open: Mon-Fri 13:30-20:00 UTC
        market_open = _is_market_open(now)

        return {
            "account_value": round(account_value, 2),
            "starting_capital": round(starting, 2),
            "total_pnl": round(total_pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "closed_pnl": round(closed_pnl, 2),
            "partial_pnl": round(partial_pnl, 2),
            "open_positions": open_positions,
            "next_daily_watch": next_watch.isoformat(),
            "market_open": market_open,
        }


def _next_weekday_watch(now: datetime) -> datetime:
    """Next weekday at 12:00 UTC (16:00 Gulf)."""
    candidate = now.replace(hour=12, minute=0, second=0, microsecond=0)
    if now >= candidate or now.weekday() >= 5:
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def _is_market_open(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    open_t = now.replace(hour=13, minute=30, second=0, microsecond=0)
    close_t = now.replace(hour=20, minute=0, second=0, microsecond=0)
    return open_t <= now <= close_t


def get_picks(status: Optional[str] = None) -> list:
    """List picks from runs table. status: pending|taken|skipped|all"""
    with get_db() as conn:
        where = ""
        params = []
        if status == "pending":
            where = "WHERE r.decision='TRADE' AND r.taken IS NULL AND r.skip_reason IS NULL"
        elif status == "taken":
            where = "WHERE r.taken = 1"
        elif status == "skipped":
            where = "WHERE r.skip_reason IS NOT NULL"
        else:
            where = "WHERE r.decision='TRADE'"

        rows = conn.execute(f"""
            SELECT r.*,
                   to2.outcome, to2.exit_price AS closed_exit_price, to2.exit_date AS closed_exit_date,
                   to2.pnl_dollars AS close_pnl,
                   COALESCE(pe_agg.partial_pnl, 0) as partial_pnl
            FROM runs r
            LEFT JOIN trade_outcomes to2 ON to2.run_id = r.id
            LEFT JOIN (
                SELECT run_id, SUM(pnl_dollars) as partial_pnl FROM partial_exits GROUP BY run_id
            ) pe_agg ON pe_agg.run_id = r.id
            {where}
            ORDER BY r.id DESC
        """, params).fetchall()

        result = []
        for row in rows:
            d = _row_to_dict(row)
            d["trade_state"] = _derive_state(d)
            d["total_pnl"] = round((d.get("close_pnl") or 0) + (d.get("partial_pnl") or 0), 2)
            result.append(d)
        return result


def get_pick_by_id(run_id: int) -> Optional[dict]:
    with get_db() as conn:
        row = conn.execute("""
            SELECT r.*,
                   to2.outcome, to2.exit_price AS closed_exit_price, to2.exit_date AS closed_exit_date,
                   to2.pnl_dollars AS close_pnl, to2.notes AS close_notes, to2.closed_method,
                   COALESCE(pe_agg.partial_pnl, 0) as partial_pnl
            FROM runs r
            LEFT JOIN trade_outcomes to2 ON to2.run_id = r.id
            LEFT JOIN (
                SELECT run_id, SUM(pnl_dollars) as partial_pnl FROM partial_exits GROUP BY run_id
            ) pe_agg ON pe_agg.run_id = r.id
            WHERE r.id = ?
        """, [run_id]).fetchone()
        if not row:
            return None
        d = _row_to_dict(row)
        d["trade_state"] = _derive_state(d)
        d["total_pnl"] = round((d.get("close_pnl") or 0) + (d.get("partial_pnl") or 0), 2)

        # Partial exits
        pe_rows = conn.execute(
            "SELECT * FROM partial_exits WHERE run_id=? ORDER BY created_at", [run_id]
        ).fetchall()
        d["partial_exits"] = [_row_to_dict(r) for r in pe_rows]

        # Watch history
        watch_rows = conn.execute(
            "SELECT * FROM daily_watch WHERE run_id=? ORDER BY created_at DESC", [run_id]
        ).fetchall()
        d["watch_history"] = [_row_to_dict(r) for r in watch_rows]

        return d


def _derive_state(d: dict) -> str:
    if d.get("skip_reason"):
        return "skipped"
    if d.get("taken") == 1:
        if d.get("closed_exit_price") is not None:
            return "closed"
        return "open"
    return "pending"


def get_trades(status: Optional[str] = None, tier: Optional[str] = None,
               days: Optional[int] = None) -> list:
    """List taken trades with optional filters."""
    with get_db() as conn:
        clauses = ["r.taken = 1"]
        params = []
        if status == "open":
            clauses.append("to2.id IS NULL")
        elif status == "closed":
            clauses.append("to2.id IS NOT NULL")
        if tier:
            clauses.append("r.quality_tier = ?")
            params.append(tier)
        if days:
            cutoff = (date.today() - timedelta(days=days)).isoformat()
            clauses.append("r.run_date >= ?")
            params.append(cutoff)

        where = "WHERE " + " AND ".join(clauses)
        rows = conn.execute(f"""
            SELECT r.*,
                   to2.outcome, to2.exit_price AS closed_exit_price, to2.exit_date AS closed_exit_date,
                   to2.pnl_dollars AS close_pnl, to2.closed_method,
                   COALESCE(pe_agg.partial_pnl, 0) as partial_pnl,
                   COALESCE(pe_agg.trimmed_shares, 0) as trimmed_shares
            FROM runs r
            LEFT JOIN trade_outcomes to2 ON to2.run_id = r.id
            LEFT JOIN (
                SELECT run_id, SUM(pnl_dollars) as partial_pnl, SUM(shares_sold) as trimmed_shares
                FROM partial_exits GROUP BY run_id
            ) pe_agg ON pe_agg.run_id = r.id
            {where}
            ORDER BY r.id DESC
        """, params).fetchall()

        result = []
        for row in rows:
            d = _row_to_dict(row)
            d["trade_state"] = _derive_state(d)
            d["total_pnl"] = round((d.get("close_pnl") or 0) + (d.get("partial_pnl") or 0), 2)
            result.append(d)
        return result


def get_trade_detail(run_id: int) -> Optional[dict]:
    """Full trade detail including partial exits and watch history."""
    return get_pick_by_id(run_id)


def get_equity_curve() -> list:
    """Daily equity curve combining closed trade P&L and partial exits."""
    with get_db() as conn:
        cap_row = conn.execute("SELECT starting_capital FROM settings WHERE id=1").fetchone()
        starting = cap_row["starting_capital"] if cap_row else 10000.0

        # Closed P&L by date
        closed_rows = conn.execute("""
            SELECT exit_date, SUM(pnl_dollars) as pnl
            FROM trade_outcomes
            WHERE exit_date IS NOT NULL
            GROUP BY exit_date
            ORDER BY exit_date
        """).fetchall()

        # Partial P&L by date
        partial_rows = conn.execute("""
            SELECT exit_date, SUM(pnl_dollars) as pnl
            FROM partial_exits
            WHERE exit_date IS NOT NULL
            GROUP BY exit_date
            ORDER BY exit_date
        """).fetchall()

        pnl_by_date: dict = {}
        for r in closed_rows:
            pnl_by_date[r["exit_date"]] = pnl_by_date.get(r["exit_date"], 0) + r["pnl"]
        for r in partial_rows:
            pnl_by_date[r["exit_date"]] = pnl_by_date.get(r["exit_date"], 0) + r["pnl"]

        if not pnl_by_date:
            return []

        curve = []
        running = starting
        for d in sorted(pnl_by_date):
            running += pnl_by_date[d]
            curve.append({"date": d, "equity": round(running, 2), "pnl": round(pnl_by_date[d], 2)})
        return curve


def get_insights() -> dict:
    with get_db() as conn:
        # Win rate by tier
        tier_rows = conn.execute("""
            SELECT r.quality_tier,
                   COUNT(*) as total,
                   SUM(CASE WHEN to2.outcome='WIN' THEN 1 ELSE 0 END) as wins
            FROM runs r
            JOIN trade_outcomes to2 ON to2.run_id = r.id
            WHERE r.quality_tier IS NOT NULL
            GROUP BY r.quality_tier
        """).fetchall()
        win_rate_by_tier = {r["quality_tier"]: {
            "total": r["total"], "wins": r["wins"],
            "win_rate": round(r["wins"]/r["total"]*100, 1) if r["total"] else 0
        } for r in tier_rows}

        # Win rate by confidence
        conf_rows = conn.execute("""
            SELECT r.confidence,
                   COUNT(*) as total,
                   SUM(CASE WHEN to2.outcome='WIN' THEN 1 ELSE 0 END) as wins
            FROM runs r
            JOIN trade_outcomes to2 ON to2.run_id = r.id
            WHERE r.confidence IS NOT NULL
            GROUP BY r.confidence
        """).fetchall()
        win_rate_by_confidence = {r["confidence"]: {
            "total": r["total"], "wins": r["wins"],
            "win_rate": round(r["wins"]/r["total"]*100, 1) if r["total"] else 0
        } for r in conf_rows}

        # R:R scatter
        scatter_rows = conn.execute("""
            SELECT r.risk_reward, to2.pnl_pct, to2.outcome, r.symbol
            FROM runs r
            JOIN trade_outcomes to2 ON to2.run_id = r.id
            WHERE r.risk_reward IS NOT NULL
        """).fetchall()
        rr_scatter = [_row_to_dict(r) for r in scatter_rows]

        # Calendar heatmap (84 days)
        calendar_rows = conn.execute("""
            SELECT exit_date, SUM(pnl_dollars) as pnl
            FROM trade_outcomes
            WHERE exit_date >= date('now', '-84 days')
            GROUP BY exit_date
        """).fetchall()
        calendar_data = {r["exit_date"]: round(r["pnl"], 2) for r in calendar_rows}

        # Total closed
        total_closed = conn.execute("SELECT COUNT(*) as c FROM trade_outcomes").fetchone()["c"]

        return {
            "total_closed": total_closed,
            "win_rate_by_tier": win_rate_by_tier,
            "win_rate_by_confidence": win_rate_by_confidence,
            "rr_scatter": rr_scatter,
            "calendar_data": calendar_data,
        }


def get_bot_status() -> dict:
    with get_db() as conn:
        last = conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        now = datetime.utcnow()
        next_sunday = now
        while next_sunday.weekday() != 6:
            next_sunday += timedelta(days=1)
        next_sunday = next_sunday.replace(hour=16, minute=0, second=0, microsecond=0)
        if now >= next_sunday:
            next_sunday += timedelta(weeks=1)

        return {
            "last_run": _row_to_dict(last) if last else None,
            "next_scan_utc": next_sunday.isoformat(),
            "next_scan_gulf": "Sunday 20:00 Gulf",
        }


def get_daily_watch_today() -> list:
    """All open trades with latest daily watch verdict."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT r.id, r.symbol, r.actual_entry, r.actual_shares, r.stop_loss, r.target_price,
                   r.quality_tier, r.confidence, r.run_date,
                   dw.verdict, dw.confidence as watch_confidence,
                   dw.reasoning, dw.suggested_stop, dw.thesis_intact,
                   dw.price_at_watch, dw.watch_date
            FROM runs r
            LEFT JOIN trade_outcomes to2 ON to2.run_id = r.id
            LEFT JOIN daily_watch dw ON dw.run_id = r.id
                AND dw.id = (
                    SELECT id FROM daily_watch WHERE run_id = r.id ORDER BY created_at DESC LIMIT 1
                )
            WHERE r.taken = 1 AND to2.id IS NULL AND r.decision = 'TRADE'
        """).fetchall()
        return [_row_to_dict(r) for r in rows]


def get_settings() -> dict:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM settings WHERE id=1").fetchone()
        return _row_to_dict(row) if row else {"starting_capital": 10000.0}
