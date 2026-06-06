"""
Fetches OHLCV data for NSE stocks.

Primary  : Upstox Analytics API (instrument_key from search API)
Fallback : Yahoo Finance
"""

import os
import time
import logging
import requests
import pandas as pd
from datetime import date, timedelta, datetime
from typing import Optional

logger = logging.getLogger(__name__)

UPSTOX_TOKEN    = os.environ.get("UPSTOX_TOKEN", "")
UPSTOX_HIST_URL = "https://api.upstox.com/v2/historical-candle/{key}/day/{to}/{frm}"

# In-memory symbol -> instrument_key cache (shared across threads)
_INST_MAP: dict = {}
_MAP_LOADED = False


def _upstox_headers() -> dict:
    return {"Authorization": f"Bearer {UPSTOX_TOKEN}", "Accept": "application/json"}


def preload_instrument_map(symbols: list) -> None:
    """
    Pre-load instrument keys for all symbols BEFORE parallel scanning.
    Call this once from the main thread to avoid duplicate downloads.
    """
    global _INST_MAP, _MAP_LOADED
    if _MAP_LOADED or not UPSTOX_TOKEN:
        return

    logger.info(f"Pre-loading instrument keys for {len(symbols)} symbols...")
    missing = [s for s in symbols if s not in _INST_MAP]

    # Batch search in groups of 10 to be fast
    for i in range(0, len(missing), 10):
        batch = missing[i:i+10]
        for sym in batch:
            if sym in _INST_MAP:
                continue
            try:
                resp = requests.get(
                    "https://api.upstox.com/v2/instruments/search",
                    params={"query": sym, "segment": "NSE_EQ"},
                    headers=_upstox_headers(),
                    timeout=8,
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    for item in data:
                        if (item.get("trading_symbol") == sym and
                                item.get("segment") == "NSE_EQ"):
                            _INST_MAP[sym] = item["instrument_key"]
                            break
            except Exception as e:
                logger.debug(f"Search failed for {sym}: {e}")

    _MAP_LOADED = True
    found = sum(1 for s in symbols if s in _INST_MAP)
    logger.info(f"Instrument keys loaded: {found}/{len(symbols)} symbols mapped")


def _get_instrument_key(symbol: str) -> Optional[str]:
    """Get instrument key from cache or search API."""
    if symbol in _INST_MAP:
        return _INST_MAP[symbol]

    if not UPSTOX_TOKEN:
        return None

    try:
        resp = requests.get(
            "https://api.upstox.com/v2/instruments/search",
            params={"query": symbol, "segment": "NSE_EQ"},
            headers=_upstox_headers(),
            timeout=8,
        )
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            for item in data:
                if (item.get("trading_symbol") == symbol and
                        item.get("segment") == "NSE_EQ"):
                    _INST_MAP[symbol] = item["instrument_key"]
                    return item["instrument_key"]
    except Exception as e:
        logger.debug(f"Instrument search failed for {symbol}: {e}")

    return None


def _fetch_upstox(symbol: str, days: int = 90) -> Optional[pd.DataFrame]:
    """Fetch historical daily OHLCV from Upstox API."""
    if not UPSTOX_TOKEN:
        return None

    instrument_key = _get_instrument_key(symbol)
    if not instrument_key:
        return None

    to_dt   = date.today()
    from_dt = to_dt - timedelta(days=days)

    # URL-encode the pipe character
    encoded_key = instrument_key.replace("|", "%7C")
    url = UPSTOX_HIST_URL.format(
        key = encoded_key,
        to  = to_dt.strftime("%Y-%m-%d"),
        frm = from_dt.strftime("%Y-%m-%d"),
    )

    try:
        resp = requests.get(url, headers=_upstox_headers(), timeout=10)

        if resp.status_code == 401:
            logger.error("Upstox token expired. Update UPSTOX_TOKEN.")
            return None

        if resp.status_code != 200:
            logger.debug(f"Upstox {symbol}: HTTP {resp.status_code}")
            return None

        candles = resp.json().get("data", {}).get("candles", [])
        if not candles or len(candles) < 22:
            return None

        # [timestamp, open, high, low, close, volume, oi]
        df = pd.DataFrame(candles, columns=["ts","open","high","low","close","volume","oi"])
        df = df[["open","high","low","close","volume"]].copy()

        for col in ["open","high","low","close","volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna().iloc[::-1].reset_index(drop=True)  # oldest first
        return df if len(df) >= 22 else None

    except Exception as e:
        logger.debug(f"Upstox error for {symbol}: {e}")
        return None


# ── Yahoo Finance fallback ──────────────────────────────────────────────────────

_YF_SESSION = None


def _get_yf_session():
    global _YF_SESSION
    if _YF_SESSION is not None:
        return _YF_SESSION
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://finance.yahoo.com/",
    })
    try:
        session.get("https://finance.yahoo.com", timeout=10)
        time.sleep(1)
    except Exception:
        pass
    _YF_SESSION = session
    return _YF_SESSION


def _fetch_yfinance(symbol: str, days: int = 90) -> Optional[pd.DataFrame]:
    """Fallback: fetch via Yahoo Finance."""
    try:
        import yfinance as yf
        import warnings
        warnings.filterwarnings("ignore")

        period  = "1mo" if days <= 30 else "2mo" if days <= 60 else "3mo" if days <= 90 else "6mo"
        session = _get_yf_session()
        ticker  = yf.Ticker(f"{symbol}.NS", session=session)
        df      = ticker.history(period=period, interval="1d",
                                 auto_adjust=True, raise_errors=False)

        if df is None or df.empty or len(df) < 22:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower().strip() for c in df.columns]
        if "adj close" in df.columns and "close" not in df.columns:
            df = df.rename(columns={"adj close": "close"})

        required = {"open","high","low","close","volume"}
        if not required.issubset(set(df.columns)):
            return None

        return df[list(required)].dropna().reset_index(drop=True)

    except Exception as e:
        logger.debug(f"Yahoo Finance failed for {symbol}: {e}")
        return None


# ── Public API ──────────────────────────────────────────────────────────────────

def fetch_stock_data(symbol: str, days: int = 90) -> Optional[pd.DataFrame]:
    """
    Fetch daily OHLCV for NSE stock.
    Tries Upstox first (fast), falls back to Yahoo Finance.
    """
    df = _fetch_upstox(symbol, days)
    if df is not None:
        return df

    logger.debug(f"{symbol}: Upstox failed, trying Yahoo Finance...")
    return _fetch_yfinance(symbol, days)
