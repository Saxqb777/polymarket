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

def get_account_stats() -> dict:
    """
    Everything the hero section and stats grid need.
    Returns sensible defaults (zeros, None) when the DB is empty.
    """
    starting = config.ACCOUNT_CAPITAL

    with _conn() as conn:
        # Completed outcomes
        outcomes = conn.execute(
            "SELECT outcome, pnl_dollars FROM trade_outcomes"
        ).fetchall()
        wins   = sum(1 for r in outcomes if r["outcome"] == "WIN")
        losses = sum(1 for r in outcomes if r["outcome"] == "LOSS")
        completed = wins + losses
        total_pnl = sum((r["pnl_dollars"] or 0) for r in outcomes
                        if r["outcome"] in ("WIN", "LOSS"))

        # Month-to-date P&L
        first_of_month = date.today().replace(day=1).isoformat()
        mtd_rows = conn.execute("""
            SELECT to2.pnl_dollars
            FROM trade_outcomes to2
            JOIN runs r ON to2.run_id = r.id
            WHERE r.run_date >= ? AND to2.outcome IN ('WIN', 'LOSS')
        """, (first_of_month,)).fetchall()
        mtd_pnl = sum((r["pnl_dollars"] or 0) for r in mtd_rows)

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

    account_value = starting + total_pnl
    win_rate = (wins / completed * 100) if completed > 0 else None
    mtd_pct  = (mtd_pnl / starting * 100) if starting > 0 else 0
    pnl_pct  = (total_pnl / starting * 100) if starting > 0 else 0
    you_vs_bot_delta = (taken_pnl_row - total_pnl) if completed > 0 else None

    return {
        "account_value":      round(account_value, 2),
        "starting_capital":   starting,
        "total_pnl":          round(total_pnl, 2),
        "pnl_pct":            round(pnl_pct, 2),
        "mtd_pnl":            round(mtd_pnl, 2),
        "mtd_pct":            round(mtd_pct, 2),
        "total_trades":       total_trades,
        "wins":               wins,
        "losses":             losses,
        "completed":          completed,
        "win_rate":           round(win_rate, 1) if win_rate is not None else None,
        "avg_rr_recommended": round(rr_row, 2) if rr_row else None,
        "best_week_pnl":      round(best_week["week_pnl"], 2) if best_week else None,
        "best_week_symbol":   best_week["symbol"] if best_week else None,
        "best_week_date":     best_week["week_start"] if best_week else None,
        "you_vs_bot_delta":   round(you_vs_bot_delta, 2) if you_vs_bot_delta is not None else None,
        "skipped_winners":    skipped_winners,
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

    r = dict(row)
    r["tier_badge"] = _fmt_tier(r.get("quality_tier"))

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

    # Build a daily dict from the DB rows
    pnl_by_date = {r["exit_date"]: (r["day_pnl"] or 0) for r in rows}

    # Also get total P&L before the window to establish correct starting value
    with _conn() as conn:
        pre_pnl_row = conn.execute("""
            SELECT COALESCE(SUM(pnl_dollars), 0)
            FROM trade_outcomes
            WHERE outcome IN ('WIN', 'LOSS') AND exit_date < ?
        """, (cutoff,)).fetchone()[0]

    running = config.ACCOUNT_CAPITAL + (pre_pnl_row or 0)
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
                to2.outcome, to2.exit_price, to2.pnl_dollars, to2.pnl_pct
            FROM runs r
            LEFT JOIN trade_outcomes to2 ON r.id = to2.run_id
            ORDER BY r.id DESC
            LIMIT ?
        """, (limit,)).fetchall()

    trades = []
    for row in rows:
        t = dict(row)
        t["tier_badge"] = _fmt_tier(t.get("quality_tier"))
        t["status"] = _derive_status(t)
        trades.append(t)
    return trades


def get_all_trades(offset: int = 0, limit: int = 50,
                   decision_filter: Optional[str] = None) -> list[dict]:
    """Paginated, optionally filtered trade list for the history page."""
    where = "WHERE r.decision = ?" if decision_filter else ""
    params: list = ([decision_filter] if decision_filter else []) + [limit, offset]

    with _conn() as conn:
        rows = conn.execute(f"""
            SELECT
                r.id, r.run_date, r.symbol,
                r.entry_price, r.stop_loss, r.target_price, r.risk_reward,
                r.confidence, r.quality_tier, r.target_move_pct,
                r.decision, r.no_trade_reason,
                r.taken, r.skip_reason,
                to2.outcome, to2.pnl_dollars
            FROM runs r
            LEFT JOIN trade_outcomes to2 ON r.id = to2.run_id
            {where}
            ORDER BY r.id DESC
            LIMIT ? OFFSET ?
        """, params).fetchall()

    trades = []
    for row in rows:
        t = dict(row)
        t["tier_badge"] = _fmt_tier(t.get("quality_tier"))
        t["status"] = _derive_status(t)
        trades.append(t)
    return trades


# ── Trade detail ──────────────────────────────────────────────────────────────

def get_trade_by_id(run_id: int) -> Optional[dict]:
    """Full detail for one trade, including outcome and user notes."""
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

    t = dict(row)
    t["tier_badge"] = _fmt_tier(t.get("quality_tier"))
    t["status"] = _derive_status(t)
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
