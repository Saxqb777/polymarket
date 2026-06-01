"""
Auto-monitor open positions.

Runs on its own schedule (daily). For every trade you marked as TAKEN that isn't
closed yet, it pulls recent price bars and checks — chronologically since entry —
whether the stop-loss or the target was hit. If so it auto-logs the outcome
(closed_method = 'auto-stop' / 'auto-target') and pings you on Telegram. This
turns the track record into something real and honest instead of relying on you
to remember to close every trade by hand.

Assumes long (BUY) positions, which is what the bot recommends. Read-mostly:
the only write is inserting a trade_outcomes row when a level is hit.
"""
import logging
import sqlite3
from datetime import date
from typing import Optional

import config
from src import scanner, telegram_bot, trade_plan

logger = logging.getLogger(__name__)


def _conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_open_positions(db_path: str = config.DB_PATH) -> list[dict]:
    """Trades marked taken=1 with a real TRADE decision and no outcome logged yet."""
    try:
        with _conn(db_path) as conn:
            rows = conn.execute(
                """
                SELECT r.id, r.symbol, r.run_date, r.entry_price, r.actual_entry,
                       r.stop_loss, r.target_price, r.actual_shares
                FROM runs r
                WHERE r.taken = 1
                  AND r.decision = 'TRADE'
                  AND r.id NOT IN (SELECT run_id FROM trade_outcomes WHERE run_id IS NOT NULL)
                ORDER BY r.id ASC
                """
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("monitor: could not read open positions (%s)", e)
        return []


def _log_outcome(db_path: str, pos: dict, exit_price: float,
                 outcome: str, method: str) -> None:
    entry = pos.get("actual_entry") or pos.get("entry_price") or 0.0
    shares = pos.get("actual_shares") or 0.0
    pnl_dollars = round((exit_price - entry) * shares, 2)
    pnl_pct = round((exit_price - entry) / entry * 100, 2) if entry else 0.0
    with _conn(db_path) as conn:
        conn.execute(
            """
            INSERT INTO trade_outcomes
              (run_id, symbol, entry_date, exit_date,
               entry_price, exit_price, shares,
               pnl_dollars, pnl_pct, outcome, notes, closed_method)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pos["id"], pos["symbol"], pos.get("run_date"), date.today().isoformat(),
                entry, round(exit_price, 2), shares,
                pnl_dollars, pnl_pct, outcome,
                "Auto-closed by position monitor", method,
            ),
        )
    logger.info("monitor: auto-closed %s via %s — P&L %s%%", pos["symbol"], method, pnl_pct)


def _detect_hit(pos: dict) -> Optional[dict]:
    """
    Pull recent bars and decide if stop or target was hit since entry.
    Returns {kind, exit_price, outcome, method} or None if still open.
    """
    entry = pos.get("actual_entry") or pos.get("entry_price")
    stop = pos.get("stop_loss")
    target = pos.get("target_price")
    if not (entry and stop and target):
        return None

    try:
        df = scanner.fetch_ohlcv(pos["symbol"], days=60)
    except Exception as e:
        logger.warning("monitor: price fetch failed for %s (%s)", pos["symbol"], e)
        return None

    run_date = pos.get("run_date")
    # Walk bars in chronological order; only consider bars on/after the pick date.
    for ts, row in df.iterrows():
        bar_date = str(ts.date()) if hasattr(ts, "date") else str(ts)[:10]
        if run_date and bar_date < run_date:
            continue
        low = float(row["low"])
        high = float(row["high"])
        # If both hit in the same bar we can't know order intraday — assume the
        # stop first (conservative / honest about risk).
        if low <= stop:
            return {"kind": "STOP", "exit_price": float(stop),
                    "outcome": "LOSS", "method": "auto-stop", "date": bar_date}
        if high >= target:
            return {"kind": "TARGET", "exit_price": float(target),
                    "outcome": "WIN", "method": "auto-target", "date": bar_date}
    return None


def _alert(pos: dict, hit: dict, is_paper: bool) -> str:
    sym = trade_plan._esc(pos["symbol"])
    entry = pos.get("actual_entry") or pos.get("entry_price") or 0.0
    exit_price = hit["exit_price"]
    pnl_pct = round((exit_price - entry) / entry * 100, 2) if entry else 0.0
    mode = "📋 Paper" if is_paper else "💵 Live"
    if hit["kind"] == "TARGET":
        head = "🎯 *TARGET HIT* — auto\\-closed"
        emoji = "✅"
    else:
        head = "🛑 *STOP HIT* — auto\\-closed"
        emoji = "❌"
    return (
        f"{head}\n"
        f"_{mode}_\n"
        f"\n"
        f"{emoji} *\\${sym}*\n"
        f"Entry \\${trade_plan._fmt_price(entry)} → Exit \\${trade_plan._fmt_price(exit_price)}\n"
        f"P&L: {trade_plan._esc(f'{pnl_pct:+.2f}%')}\n"
        f"\n"
        f"_Logged to your record\\. Next scan {trade_plan._esc(config.CADENCE_LABEL)}\\._"
    )


def check_positions(dry_run: bool = False, db_path: str = config.DB_PATH) -> list[dict]:
    """
    Check every open position for a stop/target hit. Logs outcomes and sends a
    Telegram alert per hit. Returns the list of hits found.
    """
    positions = get_open_positions(db_path)
    logger.info("monitor: %d open position(s) to check", len(positions))
    hits = []

    for pos in positions:
        hit = _detect_hit(pos)
        if not hit:
            continue
        hits.append({**pos, **hit})
        if not dry_run:
            _log_outcome(db_path, pos, hit["exit_price"], hit["outcome"], hit["method"])
            try:
                telegram_bot.send_message(_alert(pos, hit, config.PAPER_TRADING))
            except Exception as e:
                logger.warning("monitor: telegram alert failed for %s (%s)", pos["symbol"], e)
        else:
            print(_alert(pos, hit, config.PAPER_TRADING))

    if not hits:
        logger.info("monitor: no stop/target hits this run")
    return hits
