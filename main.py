"""
SwingBot — weekly US equity swing trade recommendation engine.

Entry points:
  python main.py            — start local scheduler (fires every Sunday 20:00 Gulf)
  python main.py --now      — run immediately (used by Railway cron)
  python main.py --dry-run  — full pipeline, skip Telegram send
  python main.py --test     — send a Telegram test ping and exit
"""
import argparse
import logging
import sys
from datetime import datetime

import schedule
import structlog

import config
from src import database, scanner, earnings, technicals, telegram_bot
from src import news as news_mod
from src import analyst, trade_plan, regime as regime_mod, fundamentals, memory, monitor

# ── Logging setup ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = structlog.get_logger()


# ── Pipeline ──────────────────────────────────────────────────────────────────

def run_pipeline(dry_run: bool = False) -> None:
    """
    Full Sunday pipeline:
      1. Monthly drawdown guard
      2. Scan watchlist → top 10
      3. Filter earnings risk
      4. Compute deep technicals + news for each candidate
      5. Claude Sonnet analysis → trade decision
      6. Format + send Telegram message
      7. Log run to SQLite
    """
    now = datetime.now(config.GULF_TZ)
    run_date = now.strftime("%Y-%m-%d")
    run_timestamp = now.isoformat()

    log.info("pipeline_start", date=run_date, paper=config.PAPER_TRADING, dry_run=dry_run)

    # ── Step 1: monthly drawdown guard ───────────────────────────────────────
    if database.check_monthly_drawdown():
        msg = (
            "⛔ *Monthly drawdown cap reached*\n\n"
            "Losses this month have hit the \\-8% threshold\\.\n"
            "No trade recommendation this run\\.\n\n"
            "_Review your open positions before the next scan\\._"
        )
        log.warning("monthly_drawdown_cap_reached")
        if not dry_run:
            telegram_bot.send_message(msg)
        return

    # ── Step 2: scan watchlist ────────────────────────────────────────────────
    log.info("scanning_watchlist", total=len(config.WATCHLIST))
    candidates = scanner.scan_watchlist(config.WATCHLIST)

    if not candidates:
        log.warning("no_candidates_after_scan")
        _send_no_candidates(dry_run, run_date, run_timestamp, "Scanner returned no candidates.")
        return

    log.info("scan_complete", top_n=len(candidates),
             symbols=[c["symbol"] for c in candidates])

    # ── Step 3: earnings filter ───────────────────────────────────────────────
    symbols = [c["symbol"] for c in candidates]
    safe_symbols, blacklisted = earnings.filter_earnings_risk(symbols)

    log.info("earnings_filter", safe=len(safe_symbols), blacklisted=blacklisted)
    candidates = [c for c in candidates if c["symbol"] in safe_symbols]

    if not candidates:
        log.warning("no_candidates_after_earnings_filter")
        reason = f"All top candidates have earnings this week: {', '.join(blacklisted)}"
        _send_no_candidates(dry_run, run_date, run_timestamp, reason)
        return

    # ── Step 4: deep technicals + news ───────────────────────────────────────
    enriched = []
    for c in candidates:
        sym = c["symbol"]
        try:
            df = scanner.fetch_ohlcv(sym)
            tech = technicals.compute_all(sym, df)
            company = config.SYMBOL_TO_COMPANY.get(sym, sym)
            news_summary = news_mod.get_news_summary(sym, company)
            signals = fundamentals.get_analyst_signals(sym, tech.get("last_close"))
            enriched.append({**c, "technicals": tech, "news": news_summary,
                             "analyst_signals": signals})
            log.info("enriched_candidate", symbol=sym,
                     trend=tech.get("trend"), rsi=tech.get("rsi"),
                     news_sentiment=news_summary.get("overall_sentiment"),
                     wall_st=(signals.get("recommendation") or {}).get("consensus"))
        except Exception as e:
            log.warning("enrichment_failed", symbol=sym, error=str(e))
            # Still pass the candidate with raw scanner data; analyst degrades gracefully
            enriched.append({**c, "technicals": {}, "news": {}, "analyst_signals": {}})

    # ── Step 4a: recent-pick blackout (avoid repeating the same symbol) ─────
    recent_picks = database.get_recent_pick_symbols(limit=3)
    if recent_picks:
        last_pick = recent_picks[0]
        # Hard-filter: remove the most-recently-picked symbol from candidates
        enriched_filtered = [c for c in enriched if c["symbol"] != last_pick]
        if enriched_filtered:
            if len(enriched_filtered) < len(enriched):
                log.info("blackout_last_pick", removed=last_pick,
                         remaining=[c["symbol"] for c in enriched_filtered])
            enriched = enriched_filtered
        # Soft-warn about the 2nd and 3rd most recent picks via prompt injection
        repeat_warning = recent_picks[1:]  # symbols picked 2 and 3 runs ago
    else:
        repeat_warning = []

    # ── Step 4b: market regime ───────────────────────────────────────────────
    regime = regime_mod.get_market_regime()
    log.info("market_regime", regime=regime.get("regime"), score=regime.get("score"))

    # ── Step 4c: self-learning track record ──────────────────────────────────
    track_record = memory.build_track_record_block(limit=10)

    # ── Step 5: Claude analysis (Opus 4.8 + extended thinking) ───────────────
    log.info("calling_analyst", candidates=len(enriched), model=config.ANALYST_MODEL)
    result = analyst.analyze(enriched, regime, track_record, repeat_warning)

    decision = result["decision"]
    symbol = result.get("symbol")
    log.info("analyst_complete", decision=decision, symbol=symbol,
             rr=result.get("risk_reward_ratio"), confidence=result.get("confidence"))

    # ── Step 6: format + send Telegram ───────────────────────────────────────
    message = trade_plan.format_telegram_message(
        result,
        is_paper=config.PAPER_TRADING,
        capital=config.ACCOUNT_CAPITAL,
    )

    telegram_sent = False
    if dry_run:
        log.info("dry_run_message_preview")
        print("\n" + "=" * 60)
        print(message)
        print("=" * 60 + "\n")
    else:
        telegram_sent = telegram_bot.send_message(message)
        if not telegram_sent:
            log.error("telegram_send_failed")

    # ── Step 7: log run to DB ─────────────────────────────────────────────────
    run_data = {
        "run_date": run_date,
        "run_timestamp": run_timestamp,
        "candidates_scanned": len(config.WATCHLIST),
        "candidates_passed": len(enriched),
        "decision": decision,
        "symbol": symbol,
        "entry_price": result.get("entry_price"),
        "stop_loss": result.get("stop_loss"),
        "target_price": result.get("target_price"),
        "risk_reward": result.get("risk_reward_ratio"),
        "shares": None,        # user sets their own size
        "position_value": None,
        "risk_amount": None,
        "confidence": result.get("confidence"),
        "rationale": result.get("rationale"),
        "no_trade_reason": result.get("no_trade_reason"),
        "quality_tier": result.get("quality_tier"),
        "target_move_pct": result.get("target_move_pct"),
        "is_premium": result.get("is_premium"),
        "meets_quality_bar": result.get("meets_quality_bar"),
        "is_paper": int(config.PAPER_TRADING),
        "telegram_sent": int(telegram_sent),
    }
    try:
        run_id = database.log_run(run_data)
        if not dry_run:
            database.update_telegram_status(run_id, telegram_sent)
        log.info("run_logged", run_id=run_id)
    except Exception as e:
        log.error("db_log_failed", error=str(e))

    log.info("pipeline_complete", decision=decision, symbol=symbol, telegram_sent=telegram_sent)


def _send_no_candidates(dry_run: bool, run_date: str, run_timestamp: str, reason: str) -> None:
    """Send a NO_TRADE message and log when the pipeline exits early."""
    no_trade = {
        "decision": "NO_TRADE",
        "symbol": None,
        "action": None,
        "entry_price": None,
        "stop_loss": None,
        "target_price": None,
        "risk_reward_ratio": None,
        "timeframe": None,
        "confidence": None,
        "rationale": None,
        "key_risks": [],
        "no_trade_reason": reason,
    }
    message = trade_plan.format_telegram_message(
        no_trade, is_paper=config.PAPER_TRADING, capital=config.ACCOUNT_CAPITAL
    )
    telegram_sent = False
    if dry_run:
        print(message)
    else:
        telegram_sent = telegram_bot.send_message(message)

    try:
        run_id = database.log_run({
            "run_date": run_date,
            "run_timestamp": run_timestamp,
            "candidates_scanned": len(config.WATCHLIST),
            "candidates_passed": 0,
            "decision": "NO_TRADE",
            "no_trade_reason": reason,
            "is_paper": int(config.PAPER_TRADING),
            "telegram_sent": int(telegram_sent),
        })
        database.update_telegram_status(run_id, telegram_sent)
    except Exception as e:
        log.error("db_log_failed_early_exit", error=str(e))


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="SwingBot — weekly trade recommendation engine")
    parser.add_argument("--now", action="store_true",
                        help="Run pipeline immediately (Railway cron mode)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run full pipeline but print message instead of sending")
    parser.add_argument("--test", action="store_true",
                        help="Send a Telegram test ping and exit")
    parser.add_argument("--monitor", action="store_true",
                        help="Check open positions for stop/target hits, log + alert, then exit")
    args = parser.parse_args()

    # Init DB on every startup
    database.init_db()
    # Ensure dashboard/tracking columns exist too (taken, actual_entry, …) so the
    # bot works even if it starts before the dashboard service has migrated.
    try:
        from dashboard import migrations as _migrations
        _migrations.run()
    except Exception as e:
        log.warning("schema_migration_skipped", error=str(e))

    if args.test:
        ok = telegram_bot.test_telegram()
        sys.exit(0 if ok else 1)

    if args.monitor:
        try:
            hits = monitor.check_positions(dry_run=args.dry_run)
            log.info("monitor_complete", hits=len(hits))
        except Exception as e:
            log.error("monitor_crashed", error=str(e), exc_info=True)
            sys.exit(1)
        return

    if args.now or args.dry_run:
        try:
            run_pipeline(dry_run=args.dry_run)
        except Exception as e:
            log.error("pipeline_crashed", error=str(e), exc_info=True)
            # Attempt to notify via Telegram even on crash
            try:
                telegram_bot.send_message(
                    f"⚠️ SwingBot crashed this Sunday\\.\n\nError: {trade_plan._esc(str(e))}\n\nCheck logs\\."
                )
            except Exception:
                pass
            sys.exit(1)
        return

    # ── Local scheduler mode (not used on Railway) ────────────────────────────
    # On Railway the real cadence is driven by the cron in railway.toml. This
    # local loop mirrors RUN_CADENCE_DAYS for convenience when testing locally.
    gulf_time = "20:00"
    log.info("scheduler_started",
             cadence=config.CADENCE_LABEL, fires_at=f"{gulf_time} Gulf time")

    # schedule library uses local system time — warn if system tz differs
    import time
    schedule.every(config.RUN_CADENCE_DAYS).days.at(gulf_time).do(run_pipeline)

    log.info("next_run", at=str(schedule.next_run()))
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
