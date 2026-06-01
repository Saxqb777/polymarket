"""
Market regime filter.

Before the analyst picks anything, we read the broad market (SPY + QQQ). Going
long into a falling market is a losing game even with a good-looking chart, so we
classify the environment as RISK_ON / NEUTRAL / RISK_OFF and feed that context to
the analyst. In RISK_OFF the analyst is told to demand a stronger setup or sit out.

This is intentionally simple and explainable:
  - For each index we check price vs the 50-day and 200-day moving averages and
    the 5-day slope of the 50-day MA.
  - Each index scores bullish points; we average across SPY + QQQ.
"""
import logging

import config
from src import scanner

logger = logging.getLogger(__name__)


def _index_health(symbol: str) -> dict:
    """Return a small health dict for one index, or a neutral default on failure."""
    try:
        df = scanner.fetch_ohlcv(symbol)
        close = df["close"]
        last = float(close.iloc[-1])
        ma50 = float(close.rolling(50).mean().iloc[-1])
        ma200 = float(close.rolling(200).mean().iloc[-1])
        ma50_5d_ago = float(close.rolling(50).mean().iloc[-5])
        slope = (ma50 - ma50_5d_ago) / ma50_5d_ago if ma50_5d_ago > 0 else 0.0

        above_50 = last > ma50
        above_200 = last > ma200
        rising = slope > 0

        # 0–3 bullish points
        points = int(above_50) + int(above_200) + int(rising)
        return {
            "symbol": symbol,
            "last": round(last, 2),
            "above_50ma": above_50,
            "above_200ma": above_200,
            "ma50_rising": rising,
            "points": points,
            "ok": True,
        }
    except Exception as e:
        logger.warning("Regime check failed for %s: %s", symbol, e)
        return {"symbol": symbol, "points": 2, "ok": False}  # neutral fallback


def get_market_regime() -> dict:
    """
    Classify the overall market environment.

    Returns:
      {
        "regime": "RISK_ON" | "NEUTRAL" | "RISK_OFF",
        "summary": human-readable one-liner,
        "details": [per-index health dicts],
        "score": averaged bullish points (0–3),
      }
    """
    if not config.REGIME_ENABLED:
        return {
            "regime": "NEUTRAL",
            "summary": "Regime filter disabled — treating market as neutral.",
            "details": [],
            "score": 2.0,
        }

    details = [_index_health(sym) for sym in config.REGIME_INDICES]
    avg = sum(d["points"] for d in details) / max(len(details), 1)

    if avg >= 2.5:
        regime = "RISK_ON"
    elif avg >= 1.5:
        regime = "NEUTRAL"
    else:
        regime = "RISK_OFF"

    parts = []
    for d in details:
        if not d.get("ok"):
            parts.append(f"{d['symbol']}: data unavailable")
            continue
        loc = []
        loc.append("above" if d["above_50ma"] else "below")
        loc.append("50MA;")
        loc.append("above" if d["above_200ma"] else "below")
        loc.append("200MA;")
        loc.append("50MA rising" if d["ma50_rising"] else "50MA falling")
        parts.append(f"{d['symbol']} {' '.join(loc)}")

    summary = f"{regime} — " + " | ".join(parts)
    logger.info("Market regime: %s (score=%.2f)", regime, avg)
    return {"regime": regime, "summary": summary, "details": details, "score": round(avg, 2)}
