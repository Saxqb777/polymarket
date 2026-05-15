"""
Run this on your Mac after git pull to confirm every new ticker returns
live yfinance data and is roughly in the $20-$100 price band.

Usage:
    python scripts/verify_watchlist.py
"""
import sys, time
sys.path.insert(0, ".")
import yfinance as yf
import config

passed, out_of_range, no_data = [], [], []

print(f"Checking {len(config.WATCHLIST)} tickers...\n")

for ticker in sorted(config.WATCHLIST):
    try:
        time.sleep(0.3)
        info = yf.Ticker(ticker).fast_info
        price = getattr(info, "last_price", None)
        if price is None:
            no_data.append(ticker)
            print(f"  NO DATA  : {ticker}")
        elif 20 <= price <= 100:
            passed.append((ticker, round(price, 2)))
            print(f"  OK       : {ticker:6s}  ${price:.2f}")
        else:
            out_of_range.append((ticker, round(price, 2)))
            flag = "HIGH" if price > 100 else "LOW"
            print(f"  {flag:8s} : {ticker:6s}  ${price:.2f}")
    except Exception as e:
        no_data.append(ticker)
        print(f"  ERROR    : {ticker}  {e}")

print(f"""
=== SUMMARY ===
In $20-$100 range : {len(passed)}
Out of range      : {len(out_of_range)}  {[t for t,_ in out_of_range]}
No data / error   : {len(no_data)}  {no_data}

The scanner's own hard filters (price $10-$1000, volume > 1M/day) will
automatically exclude any tickers that fall outside the live price band
or are too illiquid at runtime.
""")
