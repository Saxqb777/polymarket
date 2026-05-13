import logging
from datetime import date, timedelta
from typing import Optional

import finnhub
import yfinance as yf

import config

logger = logging.getLogger(__name__)

# Module-level cache so Finnhub is only called once per pipeline run
_earnings_cache: Optional[set[str]] = None


def _date_str(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _get_via_finnhub(symbols: list[str], days_ahead: int) -> set[str]:
    """
    Pull the earnings calendar from Finnhub for the next `days_ahead` days
    and return the set of symbols that have an announcement in that window.
    """
    today = date.today()
    to_date = today + timedelta(days=days_ahead)

    client = finnhub.Client(api_key=config.FINNHUB_API_KEY)
    data = client.earnings_calendar(
        _from=_date_str(today),
        to=_date_str(to_date),
        symbol="",          # empty = all symbols
        international=False,
    )

    upcoming = set()
    for entry in data.get("earningsCalendar", []):
        ticker = entry.get("symbol", "").upper()
        if ticker in symbols:
            upcoming.add(ticker)
            logger.debug("Earnings blacklist (Finnhub): %s on %s", ticker, entry.get("date"))

    return upcoming


def _get_via_yfinance(symbol: str, days_ahead: int) -> bool:
    """
    Per-symbol fallback using yfinance. Returns True if the stock has
    earnings within the next `days_ahead` days.
    """
    try:
        cal = yf.Ticker(symbol).calendar
        if cal is None or cal.empty:
            return False

        today = date.today()
        cutoff = today + timedelta(days=days_ahead)

        # yfinance returns a DataFrame; earnings date is in the columns
        if "Earnings Date" in cal.columns:
            for val in cal["Earnings Date"]:
                try:
                    earnings_date = val.date() if hasattr(val, "date") else date.fromisoformat(str(val)[:10])
                    if today <= earnings_date <= cutoff:
                        return True
                except Exception:
                    continue
    except Exception as e:
        logger.debug("yfinance calendar fallback failed for %s: %s", symbol, e)

    return False


def get_upcoming_earnings(
    symbols: list[str],
    days_ahead: int = config.EARNINGS_BLACKOUT_DAYS,
) -> set[str]:
    """
    Return the set of symbols (from the provided list) that have earnings
    within the next `days_ahead` days. Results are cached for the session.

    Primary source: Finnhub earnings calendar (one API call for all symbols).
    Fallback: yfinance per-symbol calendar if Finnhub is unavailable.
    """
    global _earnings_cache
    if _earnings_cache is not None:
        return _earnings_cache

    symbol_set = {s.upper() for s in symbols}

    # Try Finnhub first
    if config.FINNHUB_API_KEY:
        try:
            result = _get_via_finnhub(list(symbol_set), days_ahead)
            _earnings_cache = result
            logger.info("Earnings calendar loaded via Finnhub — %d symbols flagged", len(result))
            return _earnings_cache
        except Exception as e:
            logger.warning("Finnhub earnings failed (%s) — falling back to yfinance", e)

    # Per-symbol yfinance fallback
    logger.info("Using yfinance earnings fallback for %d symbols", len(symbol_set))
    result = set()
    for sym in symbol_set:
        if _get_via_yfinance(sym, days_ahead):
            result.add(sym)
            logger.debug("Earnings blacklist (yfinance): %s", sym)

    _earnings_cache = result
    logger.info("Earnings fallback complete — %d symbols flagged", len(result))
    return _earnings_cache


def filter_earnings_risk(
    symbols: list[str],
    days_ahead: int = config.EARNINGS_BLACKOUT_DAYS,
) -> tuple[list[str], list[str]]:
    """
    Split `symbols` into safe (no earnings this week) and blacklisted.
    Returns (safe_symbols, blacklisted_symbols).
    Logs each blacklisted ticker and why.
    """
    blacklisted_set = get_upcoming_earnings(symbols, days_ahead)

    safe = []
    blacklisted = []
    for sym in symbols:
        if sym.upper() in blacklisted_set:
            logger.info("Skipping %s — earnings within %d days", sym, days_ahead)
            blacklisted.append(sym)
        else:
            safe.append(sym)

    return safe, blacklisted


def reset_cache() -> None:
    """Clear the session cache — used in tests."""
    global _earnings_cache
    _earnings_cache = None
