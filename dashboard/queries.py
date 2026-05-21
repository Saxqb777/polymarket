"""
Read-only query helpers for the SwingBot dashboard.

All functions return plain dicts or lists of dicts — easy to pass
directly to Jinja2 templates. No writes happen here; mutations live
in dashboard/commands.py (Step 6).
"""
import sqlite3
import pathlib
import sys
from datetime import date, timedelta
from typing import Optional

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import config

_TIER_BADGE = {
    "PREMIUM":    "★ PREM",
    "STANDARD":   "STAND",
    "ACCEPTABLE": "ACCEPT",
    "BELOW_BAR":  "BELOW",
}


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _fmt_tier(tier: Optional[str]) -> str:
    return _TIER_BADGE.get(tier or "", "—")


# ── Account-level stats ───────────────────────────────────────────────────────

def get_user_settings() -> dict:
    """Returns the single user_settings row, falling back to config defaults."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT starting_capital, updated_at FROM user_settings WHERE id = 1"
        ).fetchone()
    if row:
        return {"starting_capital": row["starting_capital"], "updated_at": row["updated_at"]}
    return {"starting_capital": config.ACCOUNT_CAPITAL, "updated_at": None}


def get_account_stats() -> dict:
    """
    Everything the hero section and stats grid need.
    Returns sensible defaults (zeros, None) when the DB is empty.
    """
    settings = get_user_settings()
    starting = settings["starting_capital"]

    with _conn() as conn:
        # Completed outcomes
        outcomes = conn.execute(
            "SELECT outcome, pnl_dollars FROM trade_outcomes"
        ).fetchall()
        wins   = sum(1 for r in outcomes if r["outcome"] == "WIN")
        losses = sum(1 for r in outcomes if r["outcome"] == "LOSS")
        completed = wins + losses
        closed_pnl = sum((r["pnl_dollars"] or 0) for r in outcomes
                         if r["outcome"] in ("WIN", "LOSS"))

        # Partial exit P&L (realized even while trade still open)
        partial_total = conn.execute(
            "SELECT COALESCE(SUM(pnl_dollars), 0) FROM partial_exits"
        ).fetchone()[0] or 0
        total_pnl = closed_pnl + partial_total

        # Month-to-date P&L (closed trades + partial exits this month)
        first_of_month = date.today().replace(day=1).isoformat()
        mtd_rows = conn.execute("""
            SELECT to2.pnl_dollars
            FROM trade_outcomes to2
            JOIN runs r ON to2.run_id = r.id
            WHERE r.run_date >= ? AND to2.outcome IN ('WIN', 'LOSS')
        """, (first_of_month,)).fetchall()
        partial_mtd = conn.execute("""
            SELECT COALESCE(SUM(pnl_dollars), 0) FROM partial_exits WHERE exit_date >= ?
        """, (first_of_month,)).fetchone()[0] or 0
        mtd_pnl = sum((r["pnl_dollars"] or 0) for r in mtd_rows) + partial_mtd

        # Total TRADE decisions
        total_trades = conn.execute(
            "SELECT COUNT(*) FROM runs WHERE decision = 'TRADE'"
        ).fetchone()[0]

        # Average bot-recommended R:R
        rr_row = conn.execute(
            "SELECT AVG(risk_reward) FROM runs "
            "WHERE decision = 'TRADE' AND risk_reward IS NOT NULL"
        ).fetchone()[0]

        # Best week
        best_week = conn.execute("""
            SELECT
                strftime('%Y-%W', r.run_date) AS week,
                SUM(to2.pnl_dollars)          AS week_pnl,
                MIN(r.run_date)               AS week_start,
                r.symbol
            FROM trade_outcomes to2
            JOIN runs r ON to2.run_id = r.id
            WHERE to2.outcome IN ('WIN', 'LOSS')
            GROUP BY week
            ORDER BY week_pnl DESC
            LIMIT 1
        """).fetchone()

        # "You vs bot" — trades taken vs all recommendations
        taken_pnl_row = conn.execute("""
            SELECT COALESCE(SUM(to2.pnl_dollars), 0)
            FROM trade_outcomes to2
            JOIN runs r ON to2.run_id = r.id
            WHERE r.taken = 1 AND to2.outcome IN ('WIN', 'LOSS')
        """).fetchone()[0]

        skipped_winners = conn.execute("""
            SELECT COUNT(*)
            FROM trade_outcomes to2
            JOIN runs r ON to2.run_id = r.id
            WHERE r.taken = 0 AND to2.outcome = 'WIN'
        """).fetchone()[0]

        # Days since inception
        first_run = conn.execute(
            "SELECT MIN(run_date) FROM runs"
        ).fetchone()[0]
        days_since = 0
        if first_run:
            try:
                days_since = (date.today() - date.fromisoformat(first_run)).days
            except ValueError:
                pass

        # Open position cost basis (actual_entry × actual_shares, no outcome yet)
        open_rows = conn.execute("""
            SELECT r.actual_entry, r.actual_shares, r.symbol
            FROM runs r
            LEFT JOIN trade_outcomes to2 ON r.id = to2.run_id
            WHERE r.decision = 'TRADE'
              AND r.taken = 1
              AND to2.id IS NULL
              AND r.actual_entry IS NOT NULL
              AND r.actual_shares IS NOT NULL
            ORDER BY r.id DESC
        """).fetchall()

    open_cost   = sum((r["actual_entry"] * r["actual_shares"]) for r in open_rows)
    open_symbol = open_rows[0]["symbol"] if open_rows else None

    account_value   = starting + total_pnl
    cash_position   = account_value - open_cost
    win_rate        = (wins / completed * 100) if completed > 0 else None
    mtd_pct         = (mtd_pnl / starting * 100) if starting > 0 else 0
    pnl_pct         = (total_pnl / starting * 100) if starting > 0 else 0
    you_vs_bot_delta = (taken_pnl_row - total_pnl) if completed > 0 else None

    return {
        "account_value":        round(account_value, 2),
        "starting_capital":     starting,
        "total_pnl":            round(total_pnl, 2),
        "pnl_pct":              round(pnl_pct, 2),
        "mtd_pnl":              round(mtd_pnl, 2),
        "mtd_pct":              round(mtd_pct, 2),
        "cash_position":        round(cash_position, 2),
        "open_position_value":  round(open_cost, 2),
        "open_position_symbol": open_symbol,
        "total_trades":         total_trades,
        "wins":                 wins,
        "losses":               losses,
        "completed":            completed,
        "win_rate":             round(win_rate, 1) if win_rate is not None else None,
        "avg_rr_recommended":   round(rr_row, 2) if rr_row else None,
        "best_week_pnl":        round(best_week["week_pnl"], 2) if best_week else None,
        "best_week_symbol":     best_week["symbol"] if best_week else None,
        "best_week_date":       best_week["week_start"] if best_week else None,
        "you_vs_bot_delta":     round(you_vs_bot_delta, 2) if you_vs_bot_delta is not None else None,
        "skipped_winners":      skipped_winners,
        "days_since_inception": days_since,
    }


# ── Active position ───────────────────────────────────────────────────────────

def get_active_position() -> Optional[dict]:
    """
    The currently-open trade, or None.
    A trade is 'open' if it has a TRADE decision and no trade_outcomes row.
    Returns the most recent open trade.
    """
    with _conn() as conn:
        row = conn.execute("""
            SELECT r.*
            FROM runs r
            LEFT JOIN trade_outcomes to2 ON r.id = to2.run_id
            WHERE r.decision = 'TRADE'
              AND to2.id IS NULL
            ORDER BY r.id DESC
            LIMIT 1
        """).fetchone()

        if not row:
            return None

        trim_agg = conn.execute("""
            SELECT COALESCE(SUM(shares_sold), 0) AS total_sold,
                   COALESCE(SUM(pnl_dollars),  0) AS total_pnl
            FROM partial_exits WHERE run_id = ?
        """, (row["id"],)).fetchone()

    r = dict(row)
    r["tier_badge"]     = _fmt_tier(r.get("quality_tier"))
    r["trimmed_shares"] = round(trim_agg["total_sold"] or 0, 4)
    r["trimmed_pnl"]    = round(trim_agg["total_pnl"]  or 0, 2)

    # Days held (from run_date to today)
    try:
        opened = date.fromisoformat(r["run_date"])
        r["days_held"] = (date.today() - opened).days
    except (ValueError, TypeError):
        r["days_held"] = 0

    return r


# ── Equity curve ──────────────────────────────────────────────────────────────

def get_equity_curve(days: int = 30) -> list[dict]:
    """
    Returns [{date, value}] for the last N days, starting from ACCOUNT_CAPITAL.
    Days with no closed trades carry the previous day's value forward.
    """
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    with _conn() as conn:
        rows = conn.execute("""
            SELECT to2.exit_date, SUM(to2.pnl_dollars) AS day_pnl
            FROM trade_outcomes to2
            WHERE to2.outcome IN ('WIN', 'LOSS')
              AND to2.exit_date >= ?
            GROUP BY to2.exit_date
            ORDER BY to2.exit_date
        """, (cutoff,)).fetchall()
        partial_rows = conn.execute("""
            SELECT exit_date, SUM(pnl_dollars) AS day_pnl
            FROM partial_exits WHERE exit_date >= ?
            GROUP BY exit_date
        """, (cutoff,)).fetchall()

    # Merge both sources into daily P&L dict
    pnl_by_date = {r["exit_date"]: (r["day_pnl"] or 0) for r in rows}
    for r in partial_rows:
        pnl_by_date[r["exit_date"]] = pnl_by_date.get(r["exit_date"], 0) + (r["day_pnl"] or 0)

    # P&L before the window (both sources)
    with _conn() as conn:
        pre_closed = conn.execute("""
            SELECT COALESCE(SUM(pnl_dollars), 0)
            FROM trade_outcomes
            WHERE outcome IN ('WIN', 'LOSS') AND exit_date < ?
        """, (cutoff,)).fetchone()[0] or 0
        pre_partial = conn.execute("""
            SELECT COALESCE(SUM(pnl_dollars), 0)
            FROM partial_exits WHERE exit_date < ?
        """, (cutoff,)).fetchone()[0] or 0

    running = get_user_settings()["starting_capital"] + pre_closed + pre_partial
    curve = []
    for i in range(days + 1):
        d = (date.today() - timedelta(days=days - i)).isoformat()
        running += pnl_by_date.get(d, 0)
        curve.append({"date": d, "value": round(running, 2)})

    return curve


# ── Trade list ────────────────────────────────────────────────────────────────

def get_recent_trades(limit: int = 10) -> list[dict]:
    """
    Most recent trades with everything the table needs.
    Includes outcome from trade_outcomes (LEFT JOIN — open trades show outcome=None).
    """
    with _conn() as conn:
        rows = conn.execute("""
            SELECT
                r.id, r.run_date, r.symbol,
                r.entry_price, r.stop_loss, r.target_price, r.risk_reward,
                r.confidence, r.quality_tier, r.target_move_pct, r.is_premium,
                r.decision, r.no_trade_reason,
                r.taken, r.skip_reason,
                to2.outcome, to2.exit_price,
                to2.pnl_dollars AS close_pnl, to2.pnl_pct,
                COALESCE(pe_agg.partial_pnl, 0) AS partial_pnl
            FROM runs r
            LEFT JOIN trade_outcomes to2 ON r.id = to2.run_id
            LEFT JOIN (
                SELECT run_id, SUM(pnl_dollars) AS partial_pnl
                FROM partial_exits GROUP BY run_id
            ) pe_agg ON r.id = pe_agg.run_id
            ORDER BY r.id DESC
            LIMIT ?
        """, (limit,)).fetchall()

    trades = []
    for row in rows:
        t = dict(row)
        t["pnl_dollars"] = round((t.get("close_pnl") or 0) + (t.get("partial_pnl") or 0), 2) or None
        t["tier_badge"]  = _fmt_tier(t.get("quality_tier"))
        t["status"]      = _derive_status(t)
        trades.append(t)
    return trades


# ── Trade detail ──────────────────────────────────────────────────────────────

def get_trade_by_id(run_id: int) -> Optional[dict]:
    """Full detail for one trade, including outcome, partial exits, and user notes."""
    with _conn() as conn:
        row = conn.execute("""
            SELECT
                r.*,
                to2.outcome, to2.exit_date, to2.exit_price,
                to2.pnl_dollars, to2.pnl_pct, to2.notes AS outcome_notes,
                to2.closed_method
            FROM runs r
            LEFT JOIN trade_outcomes to2 ON r.id = to2.run_id
            WHERE r.id = ?
        """, (run_id,)).fetchone()

        if not row:
            return None

        pe_rows = conn.execute("""
            SELECT id, exit_date, shares_sold, exit_price, pnl_dollars, pnl_pct, reason
            FROM partial_exits WHERE run_id = ? ORDER BY exit_date, id
        """, (run_id,)).fetchall()

    t = dict(row)
    t["tier_badge"]        = _fmt_tier(t.get("quality_tier"))
    t["status"]            = _derive_status(t)
    t["partial_exits"]     = [dict(p) for p in pe_rows]
    t["partial_exits_pnl"] = round(sum(p["pnl_dollars"] for p in t["partial_exits"]), 2)
    t["total_pnl"]         = round((t.get("pnl_dollars") or 0) + t["partial_exits_pnl"], 2)
    return t


# ── Insights ──────────────────────────────────────────────────────────────────

def get_insights() -> dict:
    """Aggregate stats for the insights page."""
    with _conn() as conn:
        # Win rate by quality tier
        tier_stats = conn.execute("""
            SELECT r.quality_tier,
                   COUNT(*) AS total,
                   SUM(CASE WHEN to2.outcome = 'WIN' THEN 1 ELSE 0 END) AS wins,
                   SUM(CASE WHEN to2.outcome = 'LOSS' THEN 1 ELSE 0 END) AS losses,
                   AVG(to2.pnl_dollars) AS avg_pnl
            FROM runs r
            JOIN trade_outcomes to2 ON r.id = to2.run_id
            WHERE r.decision = 'TRADE'
              AND to2.outcome IN ('WIN', 'LOSS')
            GROUP BY r.quality_tier
        """).fetchall()

        # Win rate by confidence level
        conf_stats = conn.execute("""
            SELECT r.confidence,
                   COUNT(*) AS total,
                   SUM(CASE WHEN to2.outcome = 'WIN' THEN 1 ELSE 0 END) AS wins,
                   AVG(to2.pnl_dollars) AS avg_pnl
            FROM runs r
            JOIN trade_outcomes to2 ON r.id = to2.run_id
            WHERE r.decision = 'TRADE'
              AND to2.outcome IN ('WIN', 'LOSS')
            GROUP BY r.confidence
        """).fetchall()

        # Monthly P&L for drawdown chart
        monthly_pnl = conn.execute("""
            SELECT strftime('%Y-%m', to2.exit_date) AS month,
                   SUM(to2.pnl_dollars) AS pnl
            FROM trade_outcomes to2
            WHERE to2.outcome IN ('WIN', 'LOSS')
            GROUP BY month
            ORDER BY month
        """).fetchall()

    return {
        "tier_stats":   [dict(r) for r in tier_stats],
        "conf_stats":   [dict(r) for r in conf_stats],
        "monthly_pnl":  [dict(r) for r in monthly_pnl],
    }


def get_insights_data() -> dict:
    """Comprehensive analytics for the insights page."""
    starting = get_user_settings()["starting_capital"]

    with _conn() as conn:
        total_closed = conn.execute(
            "SELECT COUNT(*) FROM trade_outcomes WHERE outcome IN ('WIN','LOSS')"
        ).fetchone()[0]

        # Win rate by quality tier
        tier_rows = conn.execute("""
            SELECT r.quality_tier AS tier,
                   COUNT(*) AS total,
                   SUM(CASE WHEN to2.outcome='WIN' THEN 1 ELSE 0 END) AS wins,
                   SUM(CASE WHEN to2.outcome='LOSS' THEN 1 ELSE 0 END) AS losses
            FROM trade_outcomes to2
            JOIN runs r ON to2.run_id = r.id
            WHERE to2.outcome IN ('WIN','LOSS')
            GROUP BY r.quality_tier
        """).fetchall()

        # Win rate by confidence
        conf_rows = conn.execute("""
            SELECT r.confidence AS conf,
                   COUNT(*) AS total,
                   SUM(CASE WHEN to2.outcome='WIN' THEN 1 ELSE 0 END) AS wins,
                   SUM(CASE WHEN to2.outcome='LOSS' THEN 1 ELSE 0 END) AS losses
            FROM trade_outcomes to2
            JOIN runs r ON to2.run_id = r.id
            WHERE to2.outcome IN ('WIN','LOSS')
            GROUP BY r.confidence
        """).fetchall()

        # R:R scatter: promised vs realized
        scatter_rows = conn.execute("""
            SELECT r.id AS trade_id, r.symbol, r.run_date,
                   r.risk_reward AS promised_rr,
                   r.entry_price, r.stop_loss,
                   to2.exit_price, to2.outcome
            FROM trade_outcomes to2
            JOIN runs r ON to2.run_id = r.id
            WHERE to2.outcome IN ('WIN','LOSS')
              AND r.risk_reward IS NOT NULL
              AND r.entry_price IS NOT NULL AND r.stop_loss IS NOT NULL
              AND to2.exit_price IS NOT NULL
        """).fetchall()

        # Skipped winners
        skipped_winners = conn.execute("""
            SELECT COUNT(*), COALESCE(SUM(to2.pnl_dollars), 0)
            FROM trade_outcomes to2
            JOIN runs r ON to2.run_id = r.id
            WHERE r.taken = 0 AND to2.outcome = 'WIN'
        """).fetchone()

        # Daily P&L for calendar (last 84 days)
        cutoff_84 = (date.today() - timedelta(days=83)).isoformat()
        cal_rows = conn.execute("""
            SELECT to2.exit_date, SUM(to2.pnl_dollars) AS day_pnl
            FROM trade_outcomes to2
            WHERE to2.outcome IN ('WIN','LOSS') AND to2.exit_date >= ?
            GROUP BY to2.exit_date
        """, (cutoff_84,)).fetchall()

        # All closed daily P&L for equity + drawdown curve (30 days)
        cutoff_30 = (date.today() - timedelta(days=30)).isoformat()
        pre_30_pnl = conn.execute("""
            SELECT COALESCE(SUM(pnl_dollars), 0)
            FROM trade_outcomes
            WHERE outcome IN ('WIN','LOSS') AND exit_date < ?
        """, (cutoff_30,)).fetchone()[0] or 0
        eq_rows = conn.execute("""
            SELECT exit_date, SUM(pnl_dollars) AS day_pnl
            FROM trade_outcomes
            WHERE outcome IN ('WIN','LOSS') AND exit_date >= ?
            GROUP BY exit_date ORDER BY exit_date
        """, (cutoff_30,)).fetchall()

    # Build tier dict (ordered)
    tier_order = ["PREMIUM", "STANDARD", "ACCEPTABLE", "BELOW_BAR"]
    tier_map   = {}
    for r in tier_rows:
        rate = round(r["wins"] / r["total"] * 100, 1) if r["total"] else 0
        tier_map[r["tier"] or ""] = {
            "wins": r["wins"], "losses": r["losses"],
            "total": r["total"], "rate": rate,
        }
    win_rate_by_tier = {t: tier_map.get(t, {"wins": 0, "losses": 0, "total": 0, "rate": 0})
                        for t in tier_order}

    # Confidence dict
    conf_order = ["HIGH", "MEDIUM", "LOW"]
    conf_map   = {}
    for r in conf_rows:
        rate = round(r["wins"] / r["total"] * 100, 1) if r["total"] else 0
        conf_map[r["conf"] or ""] = {
            "wins": r["wins"], "losses": r["losses"],
            "total": r["total"], "rate": rate,
        }
    win_rate_by_confidence = {c: conf_map.get(c, {"wins": 0, "losses": 0, "total": 0, "rate": 0})
                               for c in conf_order}

    # R:R scatter points
    rr_scatter = []
    for r in scatter_rows:
        entry = r["entry_price"] or 0
        stop  = r["stop_loss"]   or 0
        exit_ = r["exit_price"]  or 0
        if entry and stop and entry != stop:
            realized = round(abs(exit_ - entry) / abs(entry - stop), 2)
        else:
            realized = None
        if realized is not None:
            rr_scatter.append({
                "trade_id":    r["trade_id"],
                "symbol":      r["symbol"],
                "run_date":    r["run_date"],
                "promised_rr": round(r["promised_rr"], 2),
                "realized_rr": realized,
                "outcome":     r["outcome"],
            })

    # Calendar data
    calendar_data = {r["exit_date"]: round(r["day_pnl"], 2) for r in cal_rows}
    calendar_days = [(date.today() - timedelta(days=83 - i)).isoformat()
                     for i in range(84)]

    # Equity + drawdown (30-day window)
    pnl_by_date = {r["exit_date"]: (r["day_pnl"] or 0) for r in eq_rows}
    running  = starting + pre_30_pnl
    peak     = running
    dd_curve = []
    for i in range(31):
        d = (date.today() - timedelta(days=30 - i)).isoformat()
        running += pnl_by_date.get(d, 0)
        peak     = max(peak, running)
        dd_pct   = round((running - peak) / peak * 100, 2) if peak else 0
        dd_curve.append({"date": d, "equity": round(running, 2), "drawdown_pct": dd_pct})

    max_dd = min((p["drawdown_pct"] for p in dd_curve), default=0)

    return {
        "total_closed":          total_closed,
        "win_rate_by_tier":      win_rate_by_tier,
        "win_rate_by_confidence": win_rate_by_confidence,
        "rr_scatter":            rr_scatter,
        "calendar_data":         calendar_data,
        "calendar_days":         calendar_days,
        "drawdown_curve":        dd_curve,
        "max_drawdown":          abs(max_dd),
        "skipped_winners":       skipped_winners[0],
        "total_value_missed":    round(skipped_winners[1], 2),
    }


def get_bot_status() -> dict:
    """Last run info + next scheduled scan timing."""
    import sys
    import os
    from datetime import datetime as dt, timezone, timedelta as td

    with _conn() as conn:
        last = conn.execute("""
            SELECT run_timestamp, run_date, candidates_scanned, candidates_passed,
                   decision, symbol, no_trade_reason
            FROM runs ORDER BY id DESC LIMIT 1
        """).fetchone()
        total_runs = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]

    now_utc = dt.now(timezone.utc)
    # Next Sunday at 16:00 UTC
    days_ahead = (6 - now_utc.weekday()) % 7  # 6 = Sunday in Python (Mon=0)
    if days_ahead == 0 and (now_utc.hour > 16 or (now_utc.hour == 16 and now_utc.minute > 0)):
        days_ahead = 7
    next_scan = (now_utc + td(days=days_ahead)).replace(
        hour=16, minute=0, second=0, microsecond=0
    )
    delta      = next_scan - now_utc
    total_secs = max(0, int(delta.total_seconds()))
    days_left  = total_secs // 86400
    hours_left = (total_secs % 86400) // 3600
    mins_left  = (total_secs % 3600) // 60

    if days_left > 0:
        time_until = f"{days_left}d {hours_left:02d}h {mins_left:02d}m"
    elif hours_left > 0:
        time_until = f"{hours_left}h {mins_left:02d}m"
    else:
        time_until = f"{mins_left}m"

    return {
        "last_run_timestamp":         last["run_timestamp"]         if last else None,
        "last_run_date":              last["run_date"]              if last else None,
        "last_run_candidates_scanned": last["candidates_scanned"]   if last else None,
        "last_run_candidates_passed": last["candidates_passed"]     if last else None,
        "last_run_decision":          last["decision"]              if last else None,
        "last_run_symbol":            last["symbol"]                if last else None,
        "last_run_reason":            last["no_trade_reason"]       if last else None,
        "next_scan_iso":              next_scan.isoformat(),
        "next_scan_display":          next_scan.strftime("%A · %H:%M UTC"),
        "time_until_next":            time_until,
        "total_runs_lifetime":        total_runs,
        "python_version":             f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "runtime_environment":        os.getenv("RAILWAY_ENVIRONMENT", "local dev"),
        "bot_version":                "v1.2",
    }


def get_all_trades_filtered(
    tier: Optional[str] = None,
    status: Optional[str] = None,
    days: Optional[int] = None,
) -> list[dict]:
    """Full trade history with optional server-side filters."""
    conditions = []
    params: list = []

    if tier:
        conditions.append("r.quality_tier = ?")
        params.append(tier)

    if days:
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        conditions.append("r.run_date >= ?")
        params.append(cutoff)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    with _conn() as conn:
        rows = conn.execute(f"""
            SELECT
                r.id, r.run_date, r.symbol,
                r.entry_price, r.stop_loss, r.target_price, r.risk_reward,
                r.confidence, r.quality_tier, r.target_move_pct,
                r.decision, r.no_trade_reason,
                r.taken, r.skip_reason,
                to2.outcome, to2.exit_price,
                to2.pnl_dollars AS close_pnl, to2.pnl_pct,
                COALESCE(pe_agg.partial_pnl, 0) AS partial_pnl
            FROM runs r
            LEFT JOIN trade_outcomes to2 ON r.id = to2.run_id
            LEFT JOIN (
                SELECT run_id, SUM(pnl_dollars) AS partial_pnl
                FROM partial_exits GROUP BY run_id
            ) pe_agg ON r.id = pe_agg.run_id
            {where}
            ORDER BY r.id DESC
        """, params).fetchall()

    trades = []
    for row in rows:
        t = dict(row)
        t["pnl_dollars"] = round((t.get("close_pnl") or 0) + (t.get("partial_pnl") or 0), 2) or None
        t["tier_badge"]  = _fmt_tier(t.get("quality_tier"))
        t["status"]      = _derive_status(t)
        if status and t["status"] != status:
            continue
        trades.append(t)
    return trades


# ── Helpers ───────────────────────────────────────────────────────────────────

def _derive_status(t: dict) -> str:
    """
    Compute a display status string from a trade row.
    Priorities: NO_TRADE → Skipped (by user) → Open → Target/Loss/Closed
    """
    if t.get("decision") == "NO_TRADE":
        return "no_trade"
    if t.get("taken") == 0:
        return "skipped"
    outcome = t.get("outcome")
    if outcome == "WIN":
        return "target"
    if outcome == "LOSS":
        return "stopped"
    if outcome:
        return "closed"
    return "open"  # TRADE decision, no outcome yet
