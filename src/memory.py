"""
Self-learning memory.

The bot keeps a record of every pick and its outcome. This module reads the most
recent CLOSED trades and formats them into a "track record" block that gets
injected into the analyst prompt. The point: the brain sees what actually
happened to its past picks — which setups worked, which got stopped out, and why
— so it can stop repeating mistakes. A trading bot that grades itself and learns
from its own record is the difference between a screener and an edge.

Read-only. Never raises — if the DB isn't ready, it returns an empty block.
"""
import logging
import sqlite3
from typing import Optional

import config

logger = logging.getLogger(__name__)


def _conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_recent_outcomes(limit: int = 10, db_path: str = config.DB_PATH) -> list[dict]:
    """Return the most recent closed trades joined with their original setup."""
    try:
        with _conn(db_path) as conn:
            rows = conn.execute(
                """
                SELECT r.symbol, r.run_date, r.confidence, r.quality_tier,
                       r.entry_price, r.stop_loss, r.target_price, r.risk_reward,
                       r.rationale,
                       o.exit_date, o.exit_price, o.pnl_pct, o.outcome,
                       o.closed_method, o.notes
                FROM trade_outcomes o
                JOIN runs r ON r.id = o.run_id
                ORDER BY o.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.debug("memory: could not read outcomes (%s)", e)
        return []


def _win_rate(outcomes: list[dict]) -> tuple[int, int, float]:
    wins = sum(1 for o in outcomes if (o.get("pnl_pct") or 0) > 0)
    total = len(outcomes)
    rate = round(100 * wins / total, 0) if total else 0.0
    return wins, total, rate


def build_track_record_block(limit: int = 10, db_path: str = config.DB_PATH) -> str:
    """
    Build the text block injected into the analyst prompt. Returns "" if there is
    no closed-trade history yet (e.g. early in the paper-trading period).
    """
    outcomes = get_recent_outcomes(limit, db_path)
    if not outcomes:
        return ""

    wins, total, rate = _win_rate(outcomes)
    lines = [
        "## YOUR RECENT TRACK RECORD (learn from this)",
        f"Last {total} closed trades — win rate {rate:.0f}% ({wins}W / {total - wins}L).",
        "Study what worked and what didn't. Do not blindly repeat losing setups; "
        "lean into the patterns that produced wins. Be honest with yourself.",
        "",
    ]
    for o in outcomes:
        pnl = o.get("pnl_pct")
        pnl_str = f"{pnl:+.1f}%" if pnl is not None else "n/a"
        result = "WIN " if (pnl or 0) > 0 else "LOSS"
        tier = o.get("quality_tier") or "?"
        conf = o.get("confidence") or "?"
        method = o.get("closed_method") or "manual"
        rationale = (o.get("rationale") or "").strip().replace("\n", " ")
        if len(rationale) > 160:
            rationale = rationale[:157] + "..."
        lines.append(
            f"- {result} {o.get('symbol')} ({pnl_str}, {method}) — "
            f"tier {tier}, confidence {conf}, R:R {o.get('risk_reward')}. "
            f"Thesis was: {rationale}"
        )
    lines.append("")
    block = "\n".join(lines)
    logger.info("memory: injected %d past outcomes (win rate %.0f%%)", total, rate)
    return block
