"""
Quick test to verify the data pipeline works.
Run: python test_signal.py
"""

import os
from scanner.fetcher import fetch_stock_data, UPSTOX_TOKEN
from scanner.signal import compute_signal

TEST_SYMBOLS = ["RELIANCE", "INFY", "TCS", "HDFCBANK", "ITC"]

print("=" * 60)
print("  BB + EMA Signal Test")
print("=" * 60)

source = "Upstox API" if UPSTOX_TOKEN else "Yahoo Finance (fallback)"
print(f"  Data source: {source}")
print()

for sym in TEST_SYMBOLS:
    print(f"  Fetching {sym}...", end=" ", flush=True)
    df = fetch_stock_data(sym, days=90)
    if df is None:
        print("No data")
        continue
    result = compute_signal(df)
    signal_str = "BUY SIGNAL!" if result["signal"] else "-"
    print(f"Close: Rs{result['close']:>8.2f}  |  EMA9: Rs{result['ema9']:>8.2f}  |  {signal_str}")

print()
print("=" * 60)
print("  Test complete.")
print("=" * 60)
