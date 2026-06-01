"""
Wall Street analyst signals via Finnhub.

We already pay nothing for Finnhub (used for the earnings calendar). It also
exposes two signals that are genuinely useful for swing trades:

  1. Recommendation trends — how many sell-side analysts rate the stock
     strongBuy / buy / hold / sell / strongSell (latest month).
  2. Price target — mean / high / low analyst price target vs current price,
     which tells us how much implied upside the Street sees.

Both are wrapped in try/except with graceful degradation: if an endpoint is
unavailable on the current plan, the bot just skips that signal — it never
crashes the pipeline. Results are cached per run.
"""
import logging
from typing import Optional

import finnhub

import config

logger = logging.getLogger(__name__)

# Per-run caches
_rec_cache: dict[str, dict] = {}
_pt_cache: dict[str, dict] = {}


def _client() -> Optional["finnhub.Client"]:
    if not config.FINNHUB_API_KEY:
        return None
    return finnhub.Client(api_key=config.FINNHUB_API_KEY)


def get_recommendation(symbol: str) -> Optional[dict]:
    """
    Latest analyst recommendation trend for a symbol.
    Returns {strongBuy, buy, hold, sell, strongSell, consensus, bullish_pct} or None.
    """
    if symbol in _rec_cache:
        return _rec_cache[symbol]

    client = _client()
    if client is None:
        return None

    try:
        data = client.recommendation_trends(symbol)
        if not data:
            _rec_cache[symbol] = None
            return None
        latest = data[0]  # most recent period first
        sb = latest.get("strongBuy", 0) or 0
        b = latest.get("buy", 0) or 0
        h = latest.get("hold", 0) or 0
        s = latest.get("sell", 0) or 0
        ss = latest.get("strongSell", 0) or 0
        total = sb + b + h + s + ss
        bullish = sb + b
        bearish = s + ss
        bullish_pct = round(100 * bullish / total, 0) if total else 0

        if total == 0:
            consensus = "NONE"
        elif bullish > (h + bearish):
            consensus = "BUY"
        elif bearish > (h + bullish):
            consensus = "SELL"
        else:
            consensus = "HOLD"

        result = {
            "strongBuy": sb, "buy": b, "hold": h, "sell": s, "strongSell": ss,
            "total": total, "consensus": consensus, "bullish_pct": bullish_pct,
            "period": latest.get("period", ""),
        }
        _rec_cache[symbol] = result
        return result
    except Exception as e:
        logger.debug("recommendation_trends unavailable for %s: %s", symbol, e)
        _rec_cache[symbol] = None
        return None


def get_price_target(symbol: str, last_close: Optional[float] = None) -> Optional[dict]:
    """
    Analyst price target for a symbol. Returns {mean, high, low, upside_pct} or None.
    Price-target endpoint may be premium-only — degrades gracefully if so.
    """
    if symbol in _pt_cache:
        return _pt_cache[symbol]

    client = _client()
    if client is None:
        return None

    try:
        data = client.price_target(symbol)
        mean = data.get("targetMean") or 0
        if not mean:
            _pt_cache[symbol] = None
            return None
        upside = None
        if last_close and last_close > 0:
            upside = round(100 * (mean - last_close) / last_close, 1)
        result = {
            "mean": round(mean, 2),
            "high": round(data.get("targetHigh", 0) or 0, 2),
            "low": round(data.get("targetLow", 0) or 0, 2),
            "upside_pct": upside,
        }
        _pt_cache[symbol] = result
        return result
    except Exception as e:
        logger.debug("price_target unavailable for %s: %s", symbol, e)
        _pt_cache[symbol] = None
        return None


def get_analyst_signals(symbol: str, last_close: Optional[float] = None) -> dict:
    """Bundle recommendation + price target into one dict for the analyst prompt."""
    return {
        "recommendation": get_recommendation(symbol),
        "price_target": get_price_target(symbol, last_close),
    }


def reset_cache() -> None:
    _rec_cache.clear()
    _pt_cache.clear()
