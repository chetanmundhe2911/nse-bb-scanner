"""
Stock universe lists for NSE scanning.
Fetches live list from NSE archives and caches for 7 days.
"""

import os
import time
import logging
import requests
import pandas as pd
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ── Hardcoded curated lists ────────────────────────────────────────────────────

NIFTY_50 = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BPCL", "BHARTIARTL",
    "BRITANNIA", "CIPLA", "COALINDIA", "DIVISLAB", "DRREDDY",
    "EICHERMOT", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE",
    "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "ITC",
    "INDUSINDBK", "INFY", "JSWSTEEL", "KOTAKBANK", "LT",
    "LTIM", "M&M", "MARUTI", "NESTLEIND", "NTPC",
    "ONGC", "POWERGRID", "RELIANCE", "SBILIFE", "SBIN",
    "SUNPHARMA", "TCS", "TATACONSUM", "TATAMOTORS", "TATASTEEL",
    "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO",
]

NIFTY_NEXT_50 = [
    "ABB", "ADANIGREEN", "AMBUJACEM", "AUROPHARMA", "BANDHANBNK",
    "BANKBARODA", "BERGEPAINT", "BOSCHLTD", "CANBK", "CHOLAFIN",
    "COLPAL", "DLF", "DABUR", "DMART", "FEDERALBNK",
    "GAIL", "GODREJCP", "GODREJPROP", "HAL", "HAVELLS",
    "ICICIGI", "ICICIPRULI", "INDIGO", "IOC", "IRCTC",
    "JINDALSTEL", "LICI", "LUPIN", "MUTHOOTFIN", "NAUKRI",
    "NMDC", "OFSS", "PAGEIND", "PIDILITIND", "PNB",
    "RECLTD", "SAIL", "SIEMENS", "TORNTPHARM", "UPL",
    "VBL", "VEDL", "ZOMATO", "MARICO", "MFSL",
    "MOTHERSON", "PETRONET", "PIIND", "TATACOMM", "TATAELXSI",
]

NIFTY_MIDCAP = [
    "ABCAPITAL", "ABFRL", "ASTRAL", "AUBANK", "APLAPOLLO",
    "BATAINDIA", "BSE", "CAMS", "CANFINHOME", "COFORGE",
    "CROMPTON", "CUMMINSIND", "DEEPAKNTR", "DIXON", "ESCORTS",
    "EXIDEIND", "GLENMARK", "IDFCFIRSTB", "INDIAMART", "INDHOTEL",
    "JKCEMENT", "JUBLFOOD", "KAJARIACER", "KPITTECH", "LALPATHLAB",
    "LAURUSLABS", "LICHSGFIN", "MAXHEALTH", "MCX", "MPHASIS",
    "NATCOPHARM", "OBEROIRLTY", "PERSISTENT", "RADICO", "SCHAEFFLER",
    "SONACOMS", "SUNTV", "TIINDIA", "TIMKEN", "TTKPRESTIG",
    "BIRLACORPN", "CARBORUNIV", "CENTRALBK", "ELGIEQUIP", "EMAMILTD",
    "ENGINERSIN", "FACT", "FLUOROCHEM", "GNFC", "GRINDWELL",
]

# ── NSE Live equity list ───────────────────────────────────────────────────────

NSE_EQUITY_CSV = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
CACHE_FILE     = os.path.join(os.path.dirname(__file__), ".nse_equity_cache.csv")
CACHE_DAYS     = 7


def _fetch_nse_list() -> pd.DataFrame:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer":    "https://www.nseindia.com/",
    })
    try:
        session.get("https://www.nseindia.com", timeout=10)
        time.sleep(1)
    except Exception:
        pass

    resp = session.get(NSE_EQUITY_CSV, timeout=15)
    resp.raise_for_status()

    from io import StringIO
    return pd.read_csv(StringIO(resp.text))


def _load_nse_all() -> list:
    if os.path.exists(CACHE_FILE):
        mtime = datetime.fromtimestamp(os.path.getmtime(CACHE_FILE))
        if datetime.now() - mtime < timedelta(days=CACHE_DAYS):
            df = pd.read_csv(CACHE_FILE)
            df.columns = [c.strip().upper() for c in df.columns]
            return df["SYMBOL"].str.strip().dropna().tolist()

    logger.info("Fetching fresh NSE equity list from NSE archives...")
    try:
        df = _fetch_nse_list()
        df.to_csv(CACHE_FILE, index=False)
        df.columns = [c.strip().upper() for c in df.columns]
        logger.info(f"Cached {len(df)} stocks to {CACHE_FILE}")
        return df["SYMBOL"].str.strip().dropna().tolist()
    except Exception as e:
        logger.warning(f"Could not fetch NSE list: {e}")
        if os.path.exists(CACHE_FILE):
            df = pd.read_csv(CACHE_FILE)
            df.columns = [c.strip().upper() for c in df.columns]
            return df["SYMBOL"].str.strip().dropna().tolist()
        # Fallback to hardcoded
        return list(dict.fromkeys(NIFTY_50 + NIFTY_NEXT_50 + NIFTY_MIDCAP))


# ── Public API ──────────────────────────────────────────────────────────────────

NIFTY_100 = list(dict.fromkeys(NIFTY_50 + NIFTY_NEXT_50))
NIFTY_200 = list(dict.fromkeys(NIFTY_100 + NIFTY_MIDCAP))


def get_universe(name: str) -> list:
    universes = {
        "NIFTY_50":  NIFTY_50,
        "NIFTY_100": NIFTY_100,
        "NIFTY_200": NIFTY_200,
        "NSE_500":   lambda: _load_nse_all()[:500],
        "NSE_1000":  lambda: _load_nse_all()[:1000],
        "NSE_ALL":   lambda: _load_nse_all(),
    }
    val = universes.get(name, NIFTY_50)
    return val() if callable(val) else val
