"""
Backtest harness — validate the SELECTION + RISK rules on historical data.

╔══════════════════════════════════════════════════════════════════════════════╗
║  HONEST CAVEAT — READ THIS                                                     ║
║                                                                                ║
║  This backtests the *mechanical* part of the strategy: the scanner's          ║
║  candidate selection (volume, trend, RSI, relative strength) plus an          ║
║  ATR-based stop/target with the same R:R floor the live bot uses.             ║
║                                                                                ║
║  It does NOT backtest Claude's judgement — the live bot's final pick is made  ║
║  by an LLM reading news, candles, and analyst signals, which we can't faithf- ║
║  ully replay on history. So treat these numbers as a sanity check on the      ║
║  PLUMBING (does the universe + filters + risk model produce non-garbage?),    ║
║  NOT as proof of the live bot's edge. Do not over-trust it. Paper trading the ║
║  real bot remains the real test.                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

Run:  python scripts/backtest.py --years 2 --hold 7 --top 1
"""
import argparse
import sys
import pathlib
from datetime import datetime

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import config
from src import scanner

# ── Strategy parameters (mirror the live risk model) ───────────────────────────
ATR_STOP_MULT = 1.5                  # stop = entry - 1.5 * ATR
RR_TARGET = config.MIN_RISK_REWARD   # target gives this reward:risk


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def load_history(symbols: list[str], years: int) -> dict[str, pd.DataFrame]:
    """Download full daily history once per symbol."""
    days = years * 365 + 300  # padding for indicator warmup
    data = {}
    for i, sym in enumerate(symbols, 1):
        try:
            df = scanner.fetch_ohlcv(sym, days=days)
            if len(df) > config.MA_TREND + 20:
                data[sym] = df
            print(f"  [{i}/{len(symbols)}] {sym}: {len(df)} bars")
        except Exception as e:
            print(f"  [{i}/{len(symbols)}] {sym}: FAILED ({e})")
    return data


def simulate_trade(df: pd.DataFrame, signal_idx: int, hold_days: int) -> dict | None:
    """
    Enter at the open of the bar after the signal. Exit on stop, target, or after
    hold_days. Returns a result dict with R-multiple, or None if not enough data.
    """
    if signal_idx + 1 >= len(df):
        return None
    atr = _atr(df).iloc[signal_idx]
    if pd.isna(atr) or atr <= 0:
        return None

    entry = float(df["open"].iloc[signal_idx + 1])
    stop = entry - ATR_STOP_MULT * float(atr)
    risk = entry - stop
    target = entry + RR_TARGET * risk
    if risk <= 0:
        return None

    window = df.iloc[signal_idx + 1: signal_idx + 1 + hold_days]
    for _, bar in window.iterrows():
        if float(bar["low"]) <= stop:
            return {"r": -1.0, "outcome": "STOP", "entry": entry, "exit": stop}
        if float(bar["high"]) >= target:
            return {"r": RR_TARGET, "outcome": "TARGET", "entry": entry, "exit": target}
    # Timed out — mark to last close
    last_close = float(window["close"].iloc[-1])
    r = (last_close - entry) / risk
    return {"r": round(r, 2), "outcome": "TIMEOUT", "entry": entry, "exit": last_close}


def run_backtest(years: int, hold_days: int, top_n: int) -> None:
    symbols = [s for s in config.WATCHLIST]
    print(f"Loading {years}y history for {len(symbols)} symbols + benchmark...")
    data = load_history(symbols + [config.RS_BENCHMARK], years)
    spy = data.get(config.RS_BENCHMARK)
    if spy is None:
        print("Benchmark data unavailable — aborting.")
        return

    # Build the set of trading dates from SPY, step by cadence.
    all_dates = list(spy.index)
    start_idx = config.MA_TREND + config.RS_PERIOD
    step = config.RUN_CADENCE_DAYS

    trades = []
    for di in range(start_idx, len(all_dates) - hold_days - 1, step):
        as_of = all_dates[di]

        # Benchmark return as of this date
        spy_close = spy["close"]
        if di <= config.RS_PERIOD:
            continue
        bench_ret = (float(spy_close.iloc[di]) / float(spy_close.iloc[di - config.RS_PERIOD]) - 1) * 100

        # Score every symbol using only data up to as_of
        scored = []
        for sym, df in data.items():
            if sym == config.RS_BENCHMARK or as_of not in df.index:
                continue
            pos = df.index.get_loc(as_of)
            sub = df.iloc[: pos + 1]
            res = scanner.compute_score(sym, sub, bench_ret)
            if res:
                res["_idx"] = pos
                res["_df"] = sym
                scored.append(res)

        if not scored:
            continue
        scored.sort(key=lambda x: x["score"], reverse=True)

        for pick in scored[:top_n]:
            sim = simulate_trade(data[pick["_df"]], pick["_idx"], hold_days)
            if sim:
                trades.append({"date": str(as_of.date()), "symbol": pick["_df"], **sim})

    _report(trades, years, hold_days, top_n)


def _report(trades: list[dict], years: int, hold_days: int, top_n: int) -> None:
    print("\n" + "=" * 70)
    print(f"BACKTEST RESULTS — {years}y, hold {hold_days}d, top {top_n}/run, cadence {config.CADENCE_LABEL}")
    print("=" * 70)
    if not trades:
        print("No trades generated.")
        return

    n = len(trades)
    wins = [t for t in trades if t["r"] > 0]
    total_r = sum(t["r"] for t in trades)
    win_rate = 100 * len(wins) / n
    avg_r = total_r / n
    targets = sum(1 for t in trades if t["outcome"] == "TARGET")
    stops = sum(1 for t in trades if t["outcome"] == "STOP")
    timeouts = sum(1 for t in trades if t["outcome"] == "TIMEOUT")

    print(f"Trades:        {n}")
    print(f"Win rate:      {win_rate:.1f}%  ({len(wins)} winners)")
    print(f"Total R:       {total_r:+.1f}R")
    print(f"Avg R/trade:   {avg_r:+.2f}R   (expectancy)")
    print(f"Exits:         {targets} target / {stops} stop / {timeouts} timeout")
    print("=" * 70)
    print("⚠️  Mechanical-rules backtest only — does NOT include Claude's judgement,")
    print("    news, or analyst signals. Sanity check, not proof of edge.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="SwingBot mechanical backtest")
    p.add_argument("--years", type=int, default=2, help="Years of history")
    p.add_argument("--hold", type=int, default=7, help="Max holding days per trade")
    p.add_argument("--top", type=int, default=1, help="Picks taken per run")
    args = p.parse_args()
    print(f"Started {datetime.now().isoformat(timespec='seconds')}")
    run_backtest(args.years, args.hold, args.top)
