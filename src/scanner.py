import logging
import concurrent.futures
from typing import Optional

import pandas as pd
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log

import config

logger = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def fetch_ohlcv(symbol: str, days: int = config.LOOKBACK_DAYS) -> pd.DataFrame:
    """Download daily OHLCV data via yfinance. Retries up to 3x on failure."""
    period = f"{days}d"
    df = yf.download(symbol, period=period, interval="1d", auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"No data returned for {symbol}")
    df.columns = [c.lower() for c in df.columns]
    return df


def compute_score(symbol: str, df: pd.DataFrame) -> Optional[dict]:
    """
    Score a stock for swing trade candidacy. Returns None if it fails any hard filter.

    Scoring weights:
      - Volume ratio (last day / 20d avg): 25%
      - Above 50-day MA:                  20%
      - RSI in sweet spot (45-65):        20%
      - Price within 3% of 20-day MA:     20%
      - 20-day MA slope positive:         15%
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

        vol_20d_avg = float(volume.iloc[-20:].mean())
        if vol_20d_avg < config.SCANNER_MIN_VOLUME_20D_AVG:
            return None

        last_volume = float(volume.iloc[-1])
        if last_volume == 0:
            return None

        # ── Indicators ────────────────────────────────────────────────────────
        # pandas-ta may return a DataFrame with a single column; flatten to Series
        rsi_result = df.ta.rsi(length=config.RSI_PERIOD)
        if isinstance(rsi_result, pd.DataFrame):
            rsi_series = rsi_result.iloc[:, 0]
        else:
            rsi_series = rsi_result

        rsi = float(rsi_series.iloc[-1]) if rsi_series is not None and not rsi_series.empty else 50.0
        if pd.isna(rsi):
            rsi = 50.0

        if not (config.SCANNER_RSI_MIN <= rsi <= config.SCANNER_RSI_MAX):
            return None

        ma20 = float(close.rolling(config.MA_SHORT).mean().iloc[-1])
        ma50 = float(close.rolling(config.MA_LONG).mean().iloc[-1])

        # ── Soft scoring ──────────────────────────────────────────────────────
        score = 0.0

        # Volume ratio (last day vs 20d avg) — rewards unusual activity
        vol_ratio = last_volume / vol_20d_avg if vol_20d_avg > 0 else 1.0
        score += min(vol_ratio / 2.0, 1.0) * 25

        # Above 50-day MA — confirms uptrend
        score += 20 if last_close > ma50 else 0

        # RSI sweet spot 45-65 — not extended, not weak
        rsi_mid = 55.0
        rsi_distance = abs(rsi - rsi_mid) / 10.0
        score += max(0.0, 1.0 - rsi_distance) * 20

        # Price within 3% of 20d MA — potential pullback entry
        ma20_distance = abs(last_close - ma20) / ma20
        score += max(0.0, 1.0 - (ma20_distance / 0.03)) * 20

        # 20d MA slope — rewards stocks trending upward
        ma20_5d_ago = float(close.rolling(config.MA_SHORT).mean().iloc[-5])
        ma20_slope = (ma20 - ma20_5d_ago) / ma20_5d_ago if ma20_5d_ago > 0 else 0.0
        score += min(max(ma20_slope / 0.01, 0.0), 1.0) * 15

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
        }

    except Exception as e:
        logger.warning("compute_score failed for %s: %s", symbol, e)
        return None


def _score_symbol(symbol: str) -> Optional[dict]:
    """Fetch + score a single symbol. Returns None on any failure."""
    try:
        df = fetch_ohlcv(symbol)
        return compute_score(symbol, df)
    except Exception as e:
        logger.warning("Skipping %s — %s", symbol, e)
        return None


def scan_watchlist(watchlist: list[str]) -> list[dict]:
    """
    Score all watchlist symbols in parallel, return top SCANNER_TOP_N by score.
    Uses ThreadPoolExecutor because yfinance is I/O-bound.
    """
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_score_symbol, sym): sym for sym in watchlist}
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
