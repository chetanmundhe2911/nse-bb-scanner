"""
BB Lower Touch + 9 EMA Bounce Signal
Exact translation of Pine Script strategy to Python.
"""

import pandas as pd


def compute_signal(df: pd.DataFrame) -> dict:
    """
    df: OHLCV DataFrame with columns open, high, low, close, volume (oldest first)
    Returns dict with signal=True/False and all indicator values.
    """
    df = df.copy().reset_index(drop=True)

    if len(df) < 22:
        return {"signal": False, "reason": "Not enough data"}

    latest_close = float(df["close"].iloc[-1])
    avg_volume   = float(df["volume"].tail(20).mean())

    # Bollinger Bands (20, 2)
    df["sma20"]    = df["close"].rolling(20).mean()
    df["std20"]    = df["close"].rolling(20).std()
    df["bb_upper"] = df["sma20"] + 2.0 * df["std20"]
    df["bb_lower"] = df["sma20"] - 2.0 * df["std20"]

    # 9 EMA
    df["ema9"] = df["close"].ewm(span=9, adjust=False).mean()

    # Pine Script stateful logic: var bool afterLowerTouch = false
    after_lower = False
    signals     = []
    for _, row in df.iterrows():
        if row["low"] <= row["bb_lower"]:
            after_lower = True
        bounce = after_lower and (row["close"] > row["ema9"])
        if bounce:
            after_lower = False
        signals.append(bounce)

    df["signal"] = signals
    latest = df.iloc[-1]
    prev   = df.iloc[-2] if len(df) > 1 else latest

    return {
        "signal":     bool(df["signal"].iloc[-1]),
        "close":      round(float(latest["close"]),    2),
        "bb_lower":   round(float(latest["bb_lower"]), 2),
        "bb_upper":   round(float(latest["bb_upper"]), 2),
        "ema9":       round(float(latest["ema9"]),     2),
        "sma20":      round(float(latest["sma20"]),    2),
        "low":        round(float(latest["low"]),      2),
        "high":       round(float(latest["high"]),     2),
        "open":       round(float(latest["open"]),     2),
        "prev_close": round(float(prev["close"]),      2),
        "avg_volume": int(avg_volume),
    }
