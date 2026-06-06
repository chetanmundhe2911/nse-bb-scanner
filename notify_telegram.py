"""
Sends today's scan results to Telegram.
Called by GitHub Actions after run_scanner.py completes.
Can also run manually: python notify_telegram.py
"""

import os
import json
import glob
import requests
from datetime import datetime

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def send_message(text: str):
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    resp = requests.post(url, data=data, timeout=10)
    if resp.status_code == 200:
        print("Telegram message sent successfully")
    else:
        print(f"Telegram error: {resp.status_code} {resp.text}")


def load_todays_signals() -> dict:
    date_str  = datetime.today().strftime("%Y%m%d")
    file_path = f"data/signals_{date_str}.json"
    if not os.path.exists(file_path):
        files = sorted(glob.glob("data/signals_*.json"), reverse=True)
        if not files:
            return {}
        file_path = files[0]
    with open(file_path) as f:
        return json.load(f)


def format_message(data: dict) -> str:
    scan_date   = data.get("date", datetime.today().strftime("%Y-%m-%d"))
    total       = data.get("total_scanned", 0)
    signals     = data.get("signals", [])
    price_range = data.get("price_range", [0, 999999])
    universe    = data.get("universe", "NSE")

    lines = [
        f"<b>BB+EMA Scanner - {scan_date}</b>",
        f"Universe : {universe}",
        f"Scanned  : {total} stocks",
        f"Range    : Rs{price_range[0]} - Rs{price_range[1]}",
        f"Signals  : {len(signals)}",
        "",
    ]

    if not signals:
        lines.append("No buy signals found today.")
        lines.append("Strategy: BB Lower Touch + 9 EMA Bounce")
    else:
        lines.append("<b>Buy Signals:</b>")
        lines.append("")
        for i, s in enumerate(signals, 1):
            sym   = s["symbol"]
            close = s.get("close", 0)
            prev  = s.get("prev_close", close)
            chg   = round(((close - prev) / max(prev, 1)) * 100, 2)
            arrow = "+" if chg >= 0 else ""
            lines.append(
                f"{i}. <b>{sym}</b>  Rs{close:.2f} ({arrow}{chg:.2f}%)\n"
                f"   EMA9: Rs{s.get('ema9',0):.2f} | BB Lower: Rs{s.get('bb_lower',0):.2f}"
            )

    lines += ["", "Not financial advice. Do your own research."]
    return "\n".join(lines)


def main():
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: Set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID as environment variables.")
        return

    data = load_todays_signals()
    if not data:
        send_message("Scanner ran but no results file found.")
        return

    message = format_message(data)
    send_message(message)
    print(f"Sent: {data.get('total_signals', 0)} signals")


if __name__ == "__main__":
    main()
