"""
Fetches OHLCV data for NSE stocks.

Primary  : Upstox Analytics API
Fallback : Yahoo Finance

Instrument key map is built from Upstox complete.json.gz (one download,
all 135k instruments). Filtered to NSE_EQ and cached for 7 days.
"""

import os
import gzip
import json
import time
import logging
import requests
import pandas as pd
from datetime import date, timedelta, datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Suppress connection pool warnings from parallel Yahoo Finance requests
import urllib3
urllib3.disable_warnings()
logging.getLogger("urllib3").setLevel(logging.ERROR)

# Increase connection pool size for parallel requests
from requests.adapters import HTTPAdapter
_ADAPTER = HTTPAdapter(pool_connections=50, pool_maxsize=50)

UPSTOX_TOKEN     = os.environ.get("UPSTOX_TOKEN", "")
UPSTOX_HIST_URL  = "https://api.upstox.com/v2/historical-candle/{key}/day/{to}/{frm}"
UPSTOX_INST_URL  = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
INST_CACHE_FILE  = os.path.join(os.path.dirname(__file__), ".upstox_inst_map.csv")
INST_CACHE_DAYS  = 7

_INST_MAP: dict = {}


def _upstox_headers() -> dict:
    return {"Authorization": f"Bearer {UPSTOX_TOKEN}", "Accept": "application/json"}


def _build_instrument_map() -> dict:
    logger.info("Downloading Upstox instrument list (one-time, ~3.5MB)...")
    try:
        r = requests.get(UPSTOX_INST_URL, timeout=30)
        r.raise_for_status()
        data = json.loads(gzip.decompress(r.content))
        logger.info(f"Downloaded {len(data)} total instruments")
        nse_eq = [
            item for item in data
            if item.get("segment") == "NSE_EQ"
            and item.get("instrument_type") == "EQ"
        ]
        logger.info(f"Filtered to {len(nse_eq)} NSE EQ instruments")
        inst_map = {
            item["trading_symbol"]: item["instrument_key"]
            for item in nse_eq
            if "trading_symbol" in item and "instrument_key" in item
        }
        return inst_map
    except Exception as e:
        logger.error(f"Failed to download instrument list: {e}")
        return {}


def _load_inst_cache() -> dict:
    if not os.path.exists(INST_CACHE_FILE):
        return {}
    mtime = datetime.fromtimestamp(os.path.getmtime(INST_CACHE_FILE))
    if datetime.now() - mtime > timedelta(days=INST_CACHE_DAYS):
        logger.info("Instrument cache expired, will refresh.")
        return {}
    df = pd.read_csv(INST_CACHE_FILE)
    result = dict(zip(df["symbol"], df["instrument_key"]))
    logger.info(f"Loaded {len(result)} instrument keys from cache (instant)")
    return result


def _save_inst_cache(inst_map: dict):
    df = pd.DataFrame([{"symbol": k, "instrument_key": v} for k, v in inst_map.items()])
    df.to_csv(INST_CACHE_FILE, index=False)
    logger.info(f"Saved {len(inst_map)} instrument keys to cache")


def preload_instrument_map(symbols: list) -> None:
    global _INST_MAP
    if _INST_MAP:
        logger.info(f"Instrument map already in memory ({len(_INST_MAP)} keys)")
        return
    _INST_MAP = _load_inst_cache()
    if _INST_MAP:
        return
    _INST_MAP = _build_instrument_map()
    if _INST_MAP:
        _save_inst_cache(_INST_MAP)
    found = sum(1 for s in symbols if s in _INST_MAP)
    logger.info(f"Instrument keys ready: {found}/{len(symbols)} symbols mapped")


def _get_instrument_key(symbol: str):
    return _INST_MAP.get(symbol)


def _fetch_upstox(symbol: str, days: int = 90):
    if not UPSTOX_TOKEN:
        return None
    instrument_key = _get_instrument_key(symbol)
    if not instrument_key:
        return None
    to_dt   = date.today()
    from_dt = to_dt - timedelta(days=days)
    encoded_key = instrument_key.replace("|", "%7C")
    url = UPSTOX_HIST_URL.format(
        key=encoded_key,
        to=to_dt.strftime("%Y-%m-%d"),
        frm=from_dt.strftime("%Y-%m-%d"),
    )
    try:
        resp = requests.get(url, headers=_upstox_headers(), timeout=10)
        if resp.status_code == 401:
            logger.error("Upstox token expired. Update UPSTOX_TOKEN secret.")
            return None
        if resp.status_code != 200:
            logger.debug(f"Upstox {symbol}: HTTP {resp.status_code}")
            return None
        candles = resp.json().get("data", {}).get("candles", [])
        if not candles or len(candles) < 22:
            return None
        df = pd.DataFrame(candles, columns=["ts","open","high","low","close","volume","oi"])
        df = df[["open","high","low","close","volume"]].copy()
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna().iloc[::-1].reset_index(drop=True)
        return df if len(df) >= 22 else None
    except Exception as e:
        logger.debug(f"Upstox error for {symbol}: {e}")
        return None


_YF_SESSION = None

def _get_yf_session():
    global _YF_SESSION
    if _YF_SESSION is not None:
        return _YF_SESSION
    session = requests.Session()
    session.mount("https://", _ADAPTER)
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


def _fetch_yfinance(symbol: str, days: int = 90):
    try:
        import yfinance as yf
        import warnings
        warnings.filterwarnings("ignore")
        period  = "1mo" if days <= 30 else "2mo" if days <= 60 else "3mo" if days <= 90 else "6mo"
        session = _get_yf_session()
        ticker  = yf.Ticker(f"{symbol}.NS", session=session)
        df      = ticker.history(period=period, interval="1d", auto_adjust=True, raise_errors=False)
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


def fetch_stock_data(symbol: str, days: int = 90):
    df = _fetch_upstox(symbol, days)
    if df is not None:
        return df
    logger.debug(f"{symbol}: Upstox failed, trying Yahoo Finance...")
    return _fetch_yfinance(symbol, days)
