import logging
import concurrent.futures
import time
from typing import Optional

import pandas as pd
import numpy as np
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log

import config

logger = logging.getLogger(__name__)


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Compute RSI using Wilder's smoothing (standard definition)."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def fetch_ohlcv(symbol: str, days: int = config.LOOKBACK_DAYS) -> pd.DataFrame:
    """Download daily OHLCV data via yfinance. Retries up to 3x on failure."""
    time.sleep(0.5)
    df = yf.download(symbol, period=f"{days}d", interval="1d", auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"No data returned for {symbol}")
    # Flatten MultiIndex columns yfinance sometimes returns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [c.lower() for c in df.columns]
    return df


def _period_return(close: pd.Series, period: int) -> Optional[float]:
    """Percentage return over `period` trading days, or None if not enough data."""
    if len(close) <= period:
        return None
    past = float(close.iloc[-period - 1])
    now = float(close.iloc[-1])
    if past <= 0:
        return None
    return (now - past) / past * 100.0


def compute_score(symbol: str, df: pd.DataFrame,
                  benchmark_return: Optional[float] = None) -> Optional[dict]:
    """
    Score a stock for swing trade candidacy. Returns None if any hard filter fails.

    Scoring weights:
      Volume ratio (last day / 20d avg): 25 pts
      Above 50-day MA:                  20 pts
      RSI in sweet spot (45–65):        20 pts
      Price within 3% of 20-day MA:     20 pts
      20-day MA slope (5-day gradient): 15 pts
      Relative strength vs SPY (bonus): up to 20 pts
    """
    try:
        if len(df) < config.MA_TREND:
            return None

        close = df["close"]
        volume = df["volume"]
        last_close = float(close.iloc[-1])

        # ── Hard filters ──────────────────────────────────────────────────────
        if not (config.SCANNER_MIN_PRICE <= last_close <= config.SCANNER_MAX_PRICE):
            return None

        # Tag price zone — analyst enforces PREMIUM-only for BUFFER picks
        price_zone = (
            "BUFFER"
            if last_close < config.PRICE_GREEN_MIN or last_close > config.PRICE_GREEN_MAX
            else "GREEN"
        )

        vol_20d_avg = float(volume.iloc[-20:].mean())
        if vol_20d_avg < config.SCANNER_MIN_VOLUME_20D_AVG:
            return None

        last_volume = float(volume.iloc[-1])
        if last_volume == 0:
            return None

        rsi_series = _rsi(close, config.RSI_PERIOD)
        rsi = float(rsi_series.iloc[-1])
        if pd.isna(rsi) or not (config.SCANNER_RSI_MIN <= rsi <= config.SCANNER_RSI_MAX):
            return None

        ma20 = float(close.rolling(config.MA_SHORT).mean().iloc[-1])
        ma50 = float(close.rolling(config.MA_LONG).mean().iloc[-1])

        # ── Soft scoring ──────────────────────────────────────────────────────
        score = 0.0

        vol_ratio = last_volume / vol_20d_avg
        score += min(vol_ratio / 2.0, 1.0) * 25

        score += 20 if last_close > ma50 else 0

        rsi_distance = abs(rsi - 55.0) / 10.0
        score += max(0.0, 1.0 - rsi_distance) * 20

        ma20_distance = abs(last_close - ma20) / ma20
        score += max(0.0, 1.0 - (ma20_distance / 0.03)) * 20

        ma20_series = close.rolling(config.MA_SHORT).mean()
        ma20_5d_ago = float(ma20_series.iloc[-5])
        ma20_slope = (ma20 - ma20_5d_ago) / ma20_5d_ago if ma20_5d_ago > 0 else 0.0
        score += min(max(ma20_slope / 0.01, 0.0), 1.0) * 15

        # ── Relative strength vs benchmark (SPY) ──────────────────────────────
        stock_return = _period_return(close, config.RS_PERIOD)
        rel_strength = None
        if stock_return is not None and benchmark_return is not None:
            rel_strength = round(stock_return - benchmark_return, 2)
            # +10pp outperformance → full 20 pts; clamp at 0 below RS_MIN_PCT
            if rel_strength > config.RS_MIN_PCT:
                score += min(max(rel_strength / 10.0, 0.0), 1.0) * 20

        return {
            "symbol": symbol,
            "score": round(score, 2),
            "last_close": round(last_close, 2),
            "volume_ratio": round(vol_ratio, 2),
            "vol_20d_avg": int(vol_20d_avg),
            "rsi": round(rsi, 1),
            "above_50ma": last_close > ma50,
            "ma20": round(ma20, 2),
            "ma20_slope": round(ma20_slope, 4),
            "rel_strength": rel_strength,
            "stock_return_60d": round(stock_return, 2) if stock_return is not None else None,
            "price_zone": price_zone,
        }

    except Exception as e:
        logger.warning("compute_score failed for %s: %s", symbol, e)
        return None


def _score_symbol(symbol: str, benchmark_return: Optional[float] = None) -> Optional[dict]:
    try:
        df = fetch_ohlcv(symbol)
        return compute_score(symbol, df, benchmark_return)
    except Exception as e:
        logger.warning("Skipping %s — %s", symbol, e)
        return None


def _benchmark_return() -> Optional[float]:
    """Fetch SPY and compute its RS_PERIOD return — the bar each stock must beat."""
    try:
        df = fetch_ohlcv(config.RS_BENCHMARK)
        ret = _period_return(df["close"], config.RS_PERIOD)
        logger.info("Benchmark %s %d-day return: %s%%", config.RS_BENCHMARK, config.RS_PERIOD, ret)
        return ret
    except Exception as e:
        logger.warning("Benchmark fetch failed (%s) — relative strength disabled this run", e)
        return None


def scan_watchlist(watchlist: list[str]) -> list[dict]:
    """Score all watchlist symbols in parallel, return top SCANNER_TOP_N by score."""
    results = []

    benchmark_return = _benchmark_return()

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_score_symbol, sym, benchmark_return): sym for sym in watchlist}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result is not None:
                results.append(result)

    results.sort(key=lambda x: x["score"], reverse=True)
    top = results[: config.SCANNER_TOP_N]

    logger.info(
        "Scan complete — %d/%d passed filters, returning top %d",
        len(results), len(watchlist), len(top),
    )
    return top
