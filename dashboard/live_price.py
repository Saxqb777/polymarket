"""
Live price fetcher for open positions.

Primary:  Polygon.io /v2/snapshot/locale/us/markets/stocks/tickers/{symbol}
Fallback: yfinance fast_info

30-second in-memory cache per symbol. Never raises externally — use
get_price_or_none() for a guaranteed-safe call.
"""
import os
import time
from datetime import datetime, timezone
from typing import Optional

import requests

_CACHE: dict[str, dict] = {}
_CACHE_TTL = 30  # seconds

_POLYGON_KEY = os.getenv("POLYGON_API_KEY", "")

# NYSE regular session: 09:30–16:00 ET = 13:30–20:00 UTC
_OPEN_UTC_MINS  = 13 * 60 + 30   # 810
_CLOSE_UTC_MINS = 20 * 60         # 1200


def is_market_open() -> bool:
    """True during NYSE regular session (Mon–Fri 13:30–20:00 UTC)."""
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:
        return False
    current_mins = now.hour * 60 + now.minute
    return _OPEN_UTC_MINS <= current_mins < _CLOSE_UTC_MINS


def _fetch_polygon(symbol: str) -> Optional[dict]:
    if not _POLYGON_KEY:
        return None
    try:
        url = (
            f"https://api.polygon.io/v2/snapshot/locale/us"
            f"/markets/stocks/tickers/{symbol}"
        )
        r = requests.get(url, params={"apiKey": _POLYGON_KEY}, timeout=5)
        if r.status_code != 200:
            return None
        body = r.json()
        t = body.get("ticker") or body.get("results", {})
        if not t:
            return None
        # Try lastTrade price first, fall back to day close
        last_trade = t.get("lastTrade") or {}
        day        = t.get("day") or {}
        price = last_trade.get("p") or day.get("c")
        if not price:
            return None
        return {
            "price":          round(float(price), 4),
            "change_pct":     round(float(t.get("todaysChangePerc", 0)), 2),
            "change_dollars": round(float(t.get("todaysChange", 0)), 2),
            "source":         "polygon",
        }
    except Exception:
        return None


def _fetch_yfinance(symbol: str) -> Optional[dict]:
    try:
        import yfinance as yf
        fi    = yf.Ticker(symbol).fast_info
        price = fi.last_price
        prev  = fi.previous_close
        if not price:
            return None
        chg_d = round(float(price) - float(prev), 2) if prev else 0.0
        chg_p = round(chg_d / float(prev) * 100, 2)  if prev else 0.0
        return {
            "price":          round(float(price), 4),
            "change_pct":     chg_p,
            "change_dollars": chg_d,
            "source":         "yfinance",
        }
    except Exception:
        return None


def fetch_price(symbol: str) -> Optional[dict]:
    """Fetch live price with 30-second cache. Returns None if both sources fail."""
    now    = time.time()
    cached = _CACHE.get(symbol)
    if cached and (now - cached["fetched_at"]) < _CACHE_TTL:
        return {**cached["data"], "stale": False}

    result = _fetch_polygon(symbol) or _fetch_yfinance(symbol)
    if result:
        result["timestamp"] = datetime.now(timezone.utc).isoformat()
        result["symbol"]    = symbol
        _CACHE[symbol] = {"data": result, "fetched_at": now}
        return {**result, "stale": False}

    # Return stale data rather than nothing, if we have something cached
    if cached:
        age = int(now - cached["fetched_at"])
        return {**cached["data"], "stale": True, "stale_secs": age}
    return None


def get_price_or_none(symbol: str) -> Optional[dict]:
    """Guaranteed no-exception wrapper around fetch_price."""
    try:
        return fetch_price(symbol)
    except Exception:
        return None
