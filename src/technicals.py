import logging
from typing import Optional

import pandas as pd
import numpy as np

import config

logger = logging.getLogger(__name__)


# ── Individual indicator functions ────────────────────────────────────────────

def _sma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(period).mean()


def _ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI using Wilder's smoothing (exponential, alpha=1/period)."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range — measures recent volatility in dollar terms."""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    true_range = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def _adx(df: pd.DataFrame, period: int = 14) -> tuple[float, float, float]:
    """
    Average Directional Index — measures TREND STRENGTH (not direction).
      ADX > 25  → strong trend (good for swing entries)
      ADX < 20  → choppy / rangebound (avoid)
    Returns (adx, plus_di, minus_di) as floats for the latest bar.
    """
    high, low, close = df["high"], df["low"], df["close"]
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = ((up_move > down_move) & (up_move > 0)) * up_move
    minus_dm = ((down_move > up_move) & (down_move > 0)) * down_move

    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, min_periods=period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, min_periods=period, adjust=False).mean() / atr

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    def _last(s: pd.Series) -> float:
        v = s.iloc[-1]
        return float(v) if pd.notna(v) else 0.0

    return _last(adx), _last(plus_di), _last(minus_di)


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Returns (macd_line, signal_line, histogram)."""
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _bollinger(close: pd.Series, period: int = 20, std_dev: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Returns (upper_band, mid_band, lower_band)."""
    mid = _sma(close, period)
    std = close.rolling(period).std()
    return mid + std_dev * std, mid, mid - std_dev * std


# ── Support / Resistance ──────────────────────────────────────────────────────

def _find_support_resistance(
    df: pd.DataFrame,
    lookback: int = 60,
    window: int = 3,
    n_levels: int = 3,
    cluster_pct: float = 0.005,
) -> dict:
    """
    Detect pivot highs and lows over the last `lookback` bars.
    Pivots are local extremes where high[i] == max (or low[i] == min)
    over a window of `window` bars on each side.
    Nearby levels within `cluster_pct` of each other are averaged together.
    Returns the `n_levels` nearest support levels (below price) and
    `n_levels` nearest resistance levels (above price).
    """
    recent = df.tail(lookback).copy()
    high = recent["high"].values
    low = recent["low"].values
    last_close = float(df["close"].iloc[-1])

    pivot_highs = []
    pivot_lows = []

    for i in range(window, len(recent) - window):
        if high[i] == max(high[i - window: i + window + 1]):
            pivot_highs.append(float(high[i]))
        if low[i] == min(low[i - window: i + window + 1]):
            pivot_lows.append(float(low[i]))

    def cluster(levels: list[float]) -> list[float]:
        if not levels:
            return []
        levels = sorted(levels)
        clustered = []
        group = [levels[0]]
        for lvl in levels[1:]:
            if abs(lvl - group[0]) / group[0] <= cluster_pct:
                group.append(lvl)
            else:
                clustered.append(round(sum(group) / len(group), 2))
                group = [lvl]
        clustered.append(round(sum(group) / len(group), 2))
        return clustered

    all_highs = cluster(pivot_highs)
    all_lows = cluster(pivot_lows)

    resistance = sorted([r for r in all_highs if r > last_close])[:n_levels]
    support = sorted([s for s in all_lows if s < last_close], reverse=True)[:n_levels]

    return {"support_levels": support, "resistance_levels": resistance}


# ── Trend classification ───────────────────────────────────────────────────────

def _classify_trend(close: pd.Series) -> str:
    """
    Classify trend using price position relative to 20/50/200 MAs and
    the 5-day slope of the 20-day MA.

      STRONG_UPTREND:   price > ma20 > ma50 > ma200, slope positive
      UPTREND:          price > ma50, above ma200
      SIDEWAYS:         price within 2% of ma50, slope near flat
      DOWNTREND:        price < ma50, below ma200
      STRONG_DOWNTREND: price < ma20 < ma50 < ma200, slope negative
    """
    last = float(close.iloc[-1])
    ma20 = float(_sma(close, 20).iloc[-1])
    ma50 = float(_sma(close, 50).iloc[-1])
    ma200 = float(_sma(close, 200).iloc[-1])
    ma20_5d_ago = float(_sma(close, 20).iloc[-5])
    slope = (ma20 - ma20_5d_ago) / ma20_5d_ago if ma20_5d_ago > 0 else 0.0

    if last > ma20 > ma50 > ma200 and slope > 0.001:
        return "STRONG_UPTREND"
    if last > ma50 and last > ma200:
        return "UPTREND"
    if last < ma20 < ma50 < ma200 and slope < -0.001:
        return "STRONG_DOWNTREND"
    if last < ma50 and last < ma200:
        return "DOWNTREND"
    return "SIDEWAYS"


# ── Master function ───────────────────────────────────────────────────────────

def compute_all(symbol: str, df: pd.DataFrame) -> dict:
    """
    Compute the full technical picture for one stock.
    Returns a structured dict consumed by analyst.py.
    """
    try:
        close = df["close"]
        volume = df["volume"]
        last_close = float(close.iloc[-1])

        # Moving averages
        ma20 = float(_sma(close, config.MA_SHORT).iloc[-1])
        ma50 = float(_sma(close, config.MA_LONG).iloc[-1])
        ma200 = float(_sma(close, config.MA_TREND).iloc[-1])

        # RSI
        rsi = float(_rsi(close, config.RSI_PERIOD).iloc[-1])

        # ATR
        atr_val = float(_atr(df, config.ATR_PERIOD).iloc[-1])
        atr_pct = round((atr_val / last_close) * 100, 2) if last_close > 0 else 0.0

        # ADX — trend strength
        adx_val, plus_di, minus_di = _adx(df, config.ATR_PERIOD)

        # MACD
        macd_line, signal_line, histogram = _macd(close)
        macd_line_val = float(macd_line.iloc[-1])
        macd_histogram_val = float(histogram.iloc[-1])

        # Bollinger Bands
        bb_upper, bb_mid, bb_lower = _bollinger(close)
        bb_upper_val = float(bb_upper.iloc[-1])
        bb_lower_val = float(bb_lower.iloc[-1])

        # Trend
        trend = _classify_trend(close)

        # Support / Resistance
        sr = _find_support_resistance(df)

        # Volume
        vol_20d_avg = float(volume.iloc[-20:].mean())
        last_volume = float(volume.iloc[-1])
        vol_ratio = round(last_volume / vol_20d_avg, 2) if vol_20d_avg > 0 else 1.0

        # Last 10 candles for Claude's pattern review
        recent_candles = []
        for _, row in df.tail(10).iterrows():
            recent_candles.append({
                "date": str(row.name.date()) if hasattr(row.name, "date") else str(row.name),
                "open": round(float(row["open"]), 2),
                "high": round(float(row["high"]), 2),
                "low": round(float(row["low"]), 2),
                "close": round(float(row["close"]), 2),
                "volume": int(row["volume"]),
            })

        return {
            "symbol": symbol,
            "last_close": round(last_close, 2),
            "trend": trend,
            "rsi": round(rsi, 1),
            "ma20": round(ma20, 2),
            "ma50": round(ma50, 2),
            "ma200": round(ma200, 2),
            "atr": round(atr_val, 2),
            "atr_pct": atr_pct,
            "adx": round(adx_val, 1),
            "plus_di": round(plus_di, 1),
            "minus_di": round(minus_di, 1),
            "macd_line": round(macd_line_val, 3),
            "macd_histogram": round(macd_histogram_val, 3),
            "bb_upper": round(bb_upper_val, 2),
            "bb_lower": round(bb_lower_val, 2),
            "support_levels": sr["support_levels"],
            "resistance_levels": sr["resistance_levels"],
            "recent_candles": recent_candles,
            "vol_20d_avg": int(vol_20d_avg),
            "last_volume": int(last_volume),
            "vol_ratio": vol_ratio,
        }

    except Exception as e:
        logger.error("compute_all failed for %s: %s", symbol, e)
        raise
