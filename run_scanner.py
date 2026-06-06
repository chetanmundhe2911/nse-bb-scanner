"""
BB + EMA Buy Signal Scanner with Upstox API

Usage:
    python run_scanner.py --universe NIFTY_50
    python run_scanner.py --universe NSE_1000
    python run_scanner.py --universe NSE_ALL
    python run_scanner.py --universe NSE_1000 --min-price 20 --max-price 500
"""

import os
import sys
import json
import time
import logging
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from scanner.stocks import get_universe
from scanner.fetcher import fetch_stock_data, preload_instrument_map, UPSTOX_TOKEN
from scanner.signal import compute_signal

# Logging setup
os.makedirs("logs", exist_ok=True)
_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
_fh  = logging.FileHandler(
    f"logs/scanner_{datetime.today().strftime('%Y%m%d')}.log", encoding="utf-8"
)
_fh.setFormatter(_fmt)
_ch  = logging.StreamHandler(
    open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)
)
_ch.setFormatter(_fmt)
logging.basicConfig(level=logging.INFO, handlers=[_fh, _ch])
logger = logging.getLogger(__name__)


def scan_stock(symbol: str) -> dict | None:
    df = fetch_stock_data(symbol)
    if df is None:
        return None
    result = compute_signal(df)
    if result.get("signal"):
        logger.info(f"  SIGNAL: {symbol} @ Rs{result['close']}")
        return {"symbol": symbol, **result}
    return None


def run_scan(symbols: list, label: str,
             min_price: float = 0, max_price: float = 999999,
             max_workers: int = 20):

    today = datetime.today().strftime("%Y-%m-%d")
    data_source = "Upstox API" if UPSTOX_TOKEN else "Yahoo Finance"

    logger.info("----------------------------------------")
    logger.info(f"  BB + EMA Scanner  |  {today}")
    logger.info(f"  Universe : {label} ({len(symbols)} stocks)")
    logger.info(f"  Source   : {data_source}")
    if min_price > 0 or max_price < 999999:
        logger.info(f"  Price    : Rs{min_price} - Rs{max_price}")
    logger.info(f"  Workers  : {max_workers}")
    logger.info("----------------------------------------")

    # Pre-load instrument keys ONCE before parallel scan
    if UPSTOX_TOKEN:
        preload_instrument_map(symbols)

    total   = len(symbols)
    signals = []
    errors  = 0
    done    = 0

    logger.info(f"Scanning {total} stocks in parallel...")
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(scan_stock, sym): sym for sym in symbols}
        for future in as_completed(futures):
            done += 1
            try:
                result = future.result()
                if result:
                    signals.append(result)
            except Exception:
                errors += 1

            if done % 100 == 0 or done == total:
                elapsed = int(time.time() - start_time)
                logger.info(
                    f"  Progress: {done}/{total} | "
                    f"Signals: {len(signals)} | "
                    f"Time: {elapsed}s"
                )

    elapsed = int(time.time() - start_time)
    logger.info(f"Scan completed in {elapsed}s ({elapsed//60}m {elapsed%60}s)")

    # Save results
    os.makedirs("data", exist_ok=True)
    date_str = datetime.today().strftime("%Y%m%d")
    out_path = f"data/signals_{date_str}.json"

    output = {
        "date":          today,
        "universe":      label,
        "data_source":   data_source,
        "price_range":   [min_price, max_price],
        "total_scanned": total,
        "total_signals": len(signals),
        "errors":        errors,
        "scan_time_sec": elapsed,
        "signals":       sorted(signals, key=lambda x: x["close"]),
    }

    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    logger.info("----------------------------------------")
    logger.info(f"  Signals found : {len(signals)}")
    logger.info(f"  Saved to      : {out_path}")
    logger.info("----------------------------------------")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BB + EMA Buy Signal Scanner")
    parser.add_argument(
        "--universe", default="NIFTY_50",
        choices=["NIFTY_50","NIFTY_100","NIFTY_200","NSE_500","NSE_1000","NSE_ALL"],
    )
    parser.add_argument("--min-price", type=float, default=0)
    parser.add_argument("--max-price", type=float, default=999999)
    parser.add_argument("--workers",   type=int,   default=20)
    args = parser.parse_args()

    symbols = get_universe(args.universe)
    run_scan(
        symbols,
        label       = args.universe,
        min_price   = args.min_price,
        max_price   = args.max_price,
        max_workers = args.workers,
    )
