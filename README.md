# NSE BB+EMA Buy Signal Scanner

Scans NSE stocks daily for **Bollinger Band Lower Touch + 9 EMA Bounce** buy signal.

- **Data**: Upstox Analytics API (fast) with Yahoo Finance fallback
- **Automation**: GitHub Actions runs at 10 PM IST every weekday
- **Notification**: Telegram bot sends signal list automatically

---

## Setup

### 1. Clone repo
```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO
pip install -r requirements.txt
```

### 2. Set Upstox token (local)
```bash
# Windows
set UPSTOX_TOKEN=your_token_here

# Mac/Linux
export UPSTOX_TOKEN=your_token_here
```

### 3. Test data pipeline
```bash
python test_signal.py
```

### 4. Run scanner
```bash
python run_scanner.py --universe NIFTY_50
python run_scanner.py --universe NSE_1000
python run_scanner.py --universe NSE_ALL
python run_scanner.py --universe NSE_1000 --min-price 20 --max-price 500
```

### 5. Launch dashboard
```bash
streamlit run dashboard.py
```

---

## GitHub Actions Setup

Add these secrets to your repo (Settings → Secrets → Actions):

| Secret | Value |
|---|---|
| `UPSTOX_TOKEN` | Your Upstox Analytics token (valid 1 year) |
| `TELEGRAM_TOKEN` | Your Telegram bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID from @userinfobot |

Workflow runs automatically every weekday at **10 PM IST**.
You can also trigger it manually from the Actions tab.

---

## Universe Options

| Universe | Stocks | Est. Time (Upstox) |
|---|---|---|
| NIFTY_50 | 50 | ~15 sec |
| NIFTY_100 | 100 | ~30 sec |
| NIFTY_200 | 200 | ~1 min |
| NSE_500 | 500 | ~2 min |
| NSE_1000 | 1000 | ~4 min |
| NSE_ALL | ~2000 | ~8 min |

---

## Signal Logic

```
1. Stock LOW touches/crosses below BB Lower Band (20,2)
   → afterLowerTouch = True

2. On any future candle: CLOSE > 9 EMA
   → BUY SIGNAL fires
```

---

## Notes
- Run after 3:30 PM IST (NSE market close)
- 0 signals some days is normal — strategy is selective
- Always verify on TradingView before trading
- Not financial advice
