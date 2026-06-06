"""
BB+EMA Signal Dashboard — Quant Analyst View
Tracks signal frequency, position sizing, and historical patterns.
Run: streamlit run dashboard.py
"""

import os
import json
import glob
import subprocess
import sys
from datetime import datetime, timedelta, date
from collections import defaultdict

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

st.set_page_config(
    page_title="BB+EMA Signal Tracker",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Syne:wght@400;600;800&display=swap');
  html, body, [class*="css"] { font-family: 'Syne', sans-serif; background:#0a0e1a; color:#e2e8f0; }
  .stApp { background:#0a0e1a; }
  section[data-testid="stSidebar"] { background:#0f1628; border-right:1px solid #1e2d4a; }
  div[data-testid="metric-container"] {
    background:linear-gradient(135deg,#111827,#1a2540);
    border:1px solid #1e3a5f; border-radius:12px; padding:1rem;
  }
  div[data-testid="metric-container"] label {
    color:#64748b!important; font-size:.72rem!important;
    text-transform:uppercase; letter-spacing:.08em;
  }
  div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
    color:#38bdf8!important; font-family:'JetBrains Mono',monospace; font-size:1.6rem!important;
  }
  .stButton>button {
    background:linear-gradient(135deg,#1d4ed8,#0ea5e9)!important;
    color:white!important; border:none!important; border-radius:8px!important; font-weight:600!important;
  }
  hr { border-color:#1e3a5f!important; }
  .signal-tag {
    display:inline-block; padding:2px 8px; border-radius:4px;
    font-family:'JetBrains Mono',monospace; font-size:.7rem; font-weight:600;
  }
  .tag-hot { background:#7f1d1d; color:#fca5a5; border:1px solid #991b1b; }
  .tag-warm { background:#78350f; color:#fcd34d; border:1px solid #92400e; }
  .tag-new { background:#052e16; color:#4ade80; border:1px solid #166534; }
  .stock-card {
    background:#0f1628; border:1px solid #1e2d4a; border-radius:10px;
    padding:1rem; margin-bottom:.5rem;
  }
</style>
""", unsafe_allow_html=True)


# ── Data Loading ───────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_all_signals() -> pd.DataFrame:
    """
    Load all historical signal files and build a unified DataFrame.
    Each row = one signal occurrence for one stock on one date.
    """
    files = sorted(glob.glob("data/signals_*.json"))
    rows  = []

    for f in files:
        try:
            with open(f) as fp:
                data = json.load(fp)
            scan_date = data.get("date", "")
            for s in data.get("signals", []):
                rows.append({
                    "date":       scan_date,
                    "symbol":     s["symbol"],
                    "close":      s.get("close", 0),
                    "ema9":       s.get("ema9", 0),
                    "bb_lower":   s.get("bb_lower", 0),
                    "bb_upper":   s.get("bb_upper", 0),
                    "prev_close": s.get("prev_close", s.get("close", 0)),
                    "avg_volume": s.get("avg_volume", 0),
                })
        except Exception:
            continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


def build_frequency_table(df: pd.DataFrame, capital: float) -> pd.DataFrame:
    """
    Build per-symbol frequency table with signal counts across time windows.
    """
    if df.empty:
        return pd.DataFrame()

    today     = df["date"].max()
    d7        = today - timedelta(days=7)
    d30       = today - timedelta(days=30)
    d90       = today - timedelta(days=90)
    today_str = today.date()

    symbols = df["symbol"].unique()
    rows    = []

    for sym in symbols:
        sym_df = df[df["symbol"] == sym].sort_values("date")
        latest = sym_df.iloc[-1]

        # Signal counts
        cnt_today = len(sym_df[sym_df["date"].dt.date == today_str])
        cnt_7d    = len(sym_df[sym_df["date"] >= d7])
        cnt_30d   = len(sym_df[sym_df["date"] >= d30])
        cnt_90d   = len(sym_df[sym_df["date"] >= d90])

        # Streak — consecutive days with signal (working backwards)
        all_dates = sorted(sym_df["date"].dt.date.unique(), reverse=True)
        streak    = 0
        check     = today_str
        for d in all_dates:
            if d == check:
                streak += 1
                check   = check - timedelta(days=1)
                # Skip weekends
                while check.weekday() >= 5:
                    check -= timedelta(days=1)
            else:
                break

        # Score: weighted frequency (recent signals matter more)
        score = cnt_7d * 4 + cnt_30d * 2 + cnt_90d * 1

        # Latest price
        price = float(latest["close"])

        # Change %
        prev  = float(latest["prev_close"]) if latest["prev_close"] else price
        chg   = round(((price - prev) / max(prev, 1)) * 100, 2)

        # Position sizing
        qty   = int(capital / price) if price > 0 else 0
        value = round(qty * price, 2)

        # Last seen
        last_seen = latest["date"].date()
        days_ago  = (today_str - last_seen).days

        rows.append({
            "Symbol":       sym,
            "Last Price":   price,
            "Change %":     chg,
            "Today":        "✓" if cnt_today > 0 else "",
            "7d Count":     cnt_7d,
            "30d Count":    cnt_30d,
            "90d Count":    cnt_90d,
            "Streak":       streak,
            "Score":        score,
            "Qty":          qty,
            "Deploy (Rs)":  value,
            "Last Seen":    str(last_seen),
            "Days Ago":     days_ago,
            "EMA9":         round(float(latest["ema9"]), 2),
            "BB Lower":     round(float(latest["bb_lower"]), 2),
            "Avg Vol":      int(latest["avg_volume"]),
        })

    result = pd.DataFrame(rows)
    result = result.sort_values("Score", ascending=False).reset_index(drop=True)
    return result


def build_heatmap_data(df: pd.DataFrame, top_n: int = 30, days: int = 30) -> pd.DataFrame:
    """Build symbol × date pivot for heatmap."""
    if df.empty:
        return pd.DataFrame()

    cutoff    = df["date"].max() - timedelta(days=days)
    recent    = df[df["date"] >= cutoff].copy()
    recent["date_str"] = recent["date"].dt.strftime("%m/%d")

    # Top symbols by frequency
    top_syms  = recent["symbol"].value_counts().head(top_n).index.tolist()
    recent    = recent[recent["symbol"].isin(top_syms)]

    pivot = recent.pivot_table(
        index="symbol", columns="date_str",
        values="close", aggfunc="count", fill_value=0
    )
    return pivot


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## BB+EMA Signal Tracker")
    st.markdown("---")

    st.markdown("### Position Sizing")
    capital = st.number_input(
        "Capital per trade (Rs)",
        min_value=1000, max_value=10_000_000,
        value=20_000, step=1000,
        help="How much you want to invest per stock"
    )

    st.markdown("### Filters")
    min_score  = st.slider("Min Score", 0, 50, 0,
                            help="Score = 7d×4 + 30d×2 + 90d×1. Higher = more consistent signal")
    min_30d    = st.slider("Min 30d signals", 0, 20, 0)
    today_only = st.checkbox("Show today's signals only", value=False)
    max_price  = st.number_input("Max Price (Rs)", 0, 200000, 5000, 100)
    min_volume = st.number_input("Min Avg Volume", 0, 10_000_000, 0, 10000,
                                  format="%d")

    st.markdown("---")

    universe = st.selectbox("Universe", ["NSE_ALL","NSE_1000","NSE_500","NIFTY_200","NIFTY_50"])

    if st.button("Run Scanner Now", use_container_width=True):
        cmd = [sys.executable, "run_scanner.py", "--universe", universe]
        subprocess.Popen(cmd, cwd=os.getcwd())
        st.success(f"Scanner started ({universe})\nRefresh in ~10 minutes.")

    st.markdown("---")
    st.markdown(
        "<div style='color:#475569;font-size:.72rem'>"
        "Signal: BB Lower Touch + 9 EMA Bounce<br>"
        "Score = 7d×4 + 30d×2 + 90d×1<br>"
        "Qty = Capital ÷ Price<br>"
        "Run after 3:30 PM IST daily"
        "</div>",
        unsafe_allow_html=True,
    )


# ── Load data ─────────────────────────────────────────────────────────────────

df = load_all_signals()

if df.empty:
    st.warning("No scan data found. Run the scanner first.")
    st.info("Run: `python run_scanner.py --universe NSE_ALL`")
    st.stop()

freq_df = build_frequency_table(df, capital)

# Apply filters
mask = (
    (freq_df["Score"]      >= min_score) &
    (freq_df["30d Count"]  >= min_30d) &
    (freq_df["Last Price"] <= max_price if max_price > 0 else True) &
    (freq_df["Avg Vol"]    >= min_volume)
)
if today_only:
    mask &= (freq_df["Today"] == "✓")

filtered = freq_df[mask].copy()


# ── Header ────────────────────────────────────────────────────────────────────

latest_date = df["date"].max().strftime("%d %B %Y")
today_sigs  = len(df[df["date"] == df["date"].max()])
total_days  = df["date"].dt.date.nunique()
total_syms  = df["symbol"].nunique()

st.markdown(f"""
<div style="background:linear-gradient(90deg,#0f1f3d,#0a2550);border:1px solid #1e3a5f;
     border-radius:16px;padding:1.2rem 2rem;margin-bottom:1.5rem;
     display:flex;align-items:center;justify-content:space-between">
  <div>
    <p style="font-family:Syne,sans-serif;font-weight:800;font-size:1.5rem;color:#38bdf8;margin:0">
      📈 BB+EMA Signal Tracker
    </p>
    <p style="color:#64748b;font-size:.82rem;margin:.2rem 0 0">
      Last scan: {latest_date} &nbsp;|&nbsp; {total_days} trading days tracked
    </p>
  </div>
  <div style="text-align:right;font-family:'JetBrains Mono',monospace;font-size:.8rem;color:#64748b">
    Capital/trade: <span style="color:#38bdf8">Rs {capital:,}</span>
  </div>
</div>
""", unsafe_allow_html=True)


# ── Top metrics ───────────────────────────────────────────────────────────────

c1, c2, c3, c4, c5 = st.columns(5)
with c1: st.metric("Today's Signals",   today_sigs)
with c2: st.metric("Unique Stocks",     total_syms)
with c3: st.metric("Days Tracked",      total_days)
with c4:
    repeat = len(freq_df[freq_df["30d Count"] >= 3])
    st.metric("High Freq (3+ in 30d)", repeat)
with c5:
    streak_stocks = len(freq_df[freq_df["Streak"] >= 2])
    st.metric("On Streak (2+ days)", streak_stocks)

st.markdown("---")


# ── Main tabs ─────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Signal Frequency",
    "🔥 Heatmap",
    "📅 History",
    "🔍 Stock Detail",
])


# ── Tab 1: Signal Frequency Table ─────────────────────────────────────────────

with tab1:
    st.markdown(f"### Signal Frequency Table &nbsp; `{len(filtered)} stocks`")
    st.caption(
        "Score = 7d×4 + 30d×2 + 90d×1 | "
        "Streak = consecutive days with signal | "
        f"Qty = Rs{capital:,} ÷ Last Price"
    )

    if filtered.empty:
        st.info("No stocks match current filters. Try reducing the filters.")
    else:
        # Style the table
        def style_cell(val, col):
            if col == "Change %" and isinstance(val, float):
                return "color:#4ade80" if val > 0 else "color:#f87171"
            if col == "Score" and isinstance(val, (int, float)):
                if val >= 20: return "color:#f97316;font-weight:700"
                if val >= 10: return "color:#fbbf24"
            if col == "Streak" and isinstance(val, (int, float)) and val >= 2:
                return "color:#a78bfa;font-weight:700"
            if col == "Today" and val == "✓":
                return "color:#4ade80;font-weight:700"
            return ""

        display_cols = [
            "Symbol", "Last Price", "Change %", "Today",
            "7d Count", "30d Count", "90d Count", "Streak",
            "Score", "Qty", "Deploy (Rs)", "Last Seen", "EMA9", "BB Lower"
        ]

        styled = (
            filtered[display_cols].style
            .applymap(lambda v: style_cell(v, "Change %"),  subset=["Change %"])
            .applymap(lambda v: style_cell(v, "Score"),     subset=["Score"])
            .applymap(lambda v: style_cell(v, "Streak"),    subset=["Streak"])
            .applymap(lambda v: style_cell(v, "Today"),     subset=["Today"])
            .format({
                "Last Price":  "Rs {:.2f}",
                "Change %":    "{:+.2f}%",
                "Deploy (Rs)": "Rs {:,.0f}",
                "EMA9":        "Rs {:.2f}",
                "BB Lower":    "Rs {:.2f}",
            }, na_rep="—")
        )
        st.dataframe(styled, use_container_width=True, height=500)

        st.download_button(
            "Download CSV",
            filtered[display_cols].to_csv(index=False),
            file_name=f"signals_freq_{date.today()}.csv",
            mime="text/csv",
        )

    # Top consistent stocks highlight
    st.markdown("---")
    st.markdown("### 🏆 Most Consistent Signals (Top 10 by Score)")

    top10 = freq_df.head(10)
    cols  = st.columns(5)
    for idx, (_, row) in enumerate(top10.iterrows()):
        col = cols[idx % 5]
        with col:
            score  = row["Score"]
            streak = row["Streak"]
            tag    = "hot" if score >= 20 else "warm" if score >= 10 else "new"
            tag_label = f"{score} pts"

            if streak >= 2:
                streak_badge = f'<span class="signal-tag" style="background:#1e1b4b;color:#a78bfa;border:1px solid #4c1d95;margin-left:4px">{streak}d streak</span>'
            else:
                streak_badge = ""

            st.markdown(f"""
            <div class="stock-card">
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:.4rem">
                <span style="font-family:'JetBrains Mono',monospace;font-weight:700;font-size:.95rem">{row['Symbol']}</span>
                <span class="signal-tag tag-{tag}">{tag_label}</span>
              </div>
              {streak_badge}
              <div style="margin-top:.5rem;font-family:'JetBrains Mono',monospace;font-size:.8rem;color:#4ade80">
                Rs {row['Last Price']:.2f}
              </div>
              <div style="font-size:.72rem;color:#64748b;margin-top:.2rem">
                30d: {row['30d Count']}x &nbsp;|&nbsp; Qty: {row['Qty']}
              </div>
            </div>
            """, unsafe_allow_html=True)


# ── Tab 2: Heatmap ────────────────────────────────────────────────────────────

with tab2:
    st.markdown("### Signal Heatmap — Top 30 stocks × Last 30 days")
    st.caption("Each cell = 1 if signal fired on that date, 0 if not. Darker = more consistent.")

    days_window = st.select_slider("Time window", [7, 14, 30, 60, 90], value=30)
    top_n_heat  = st.slider("Top N stocks", 10, 50, 30)

    pivot = build_heatmap_data(df, top_n=top_n_heat, days=days_window)

    if pivot.empty:
        st.info("Not enough data for heatmap yet. Run scanner for more days.")
    else:
        fig = go.Figure(go.Heatmap(
            z          = pivot.values,
            x          = pivot.columns.tolist(),
            y          = pivot.index.tolist(),
            colorscale = [[0,"#0a0e1a"],[0.5,"#1e3a5f"],[1,"#0ea5e9"]],
            showscale  = False,
            hovertemplate = "%{y} on %{x}<extra></extra>",
        ))
        fig.update_layout(
            paper_bgcolor = "#0a0e1a",
            plot_bgcolor  = "#0a0e1a",
            font_color    = "#94a3b8",
            height        = max(400, top_n_heat * 22),
            margin        = dict(l=10, r=10, t=20, b=10),
            xaxis         = dict(tickfont=dict(size=9), color="#64748b"),
            yaxis         = dict(tickfont=dict(size=10), color="#e2e8f0"),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Blue = signal fired | Black = no signal")


# ── Tab 3: History ────────────────────────────────────────────────────────────

with tab3:
    st.markdown("### Daily Scan History")

    # Summary per scan date
    hist_df = df.groupby(df["date"].dt.date).agg(
        signals     = ("symbol", "count"),
        unique_syms = ("symbol", "nunique"),
    ).reset_index()
    hist_df.columns = ["Date", "Total Signals", "Unique Stocks"]
    hist_df = hist_df.sort_values("Date", ascending=False)

    # Bar chart
    fig = go.Figure(go.Bar(
        x              = hist_df["Date"].astype(str),
        y              = hist_df["Total Signals"],
        marker_color   = "#0ea5e9",
        opacity        = 0.85,
        hovertemplate  = "%{x}: %{y} signals<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor = "#0a0e1a",
        plot_bgcolor  = "#0f1628",
        font_color    = "#94a3b8",
        height        = 250,
        margin        = dict(l=10, r=10, t=20, b=10),
        showlegend    = False,
        xaxis         = dict(gridcolor="#1e3a5f", tickangle=-45),
        yaxis         = dict(gridcolor="#1e3a5f", title="Signals"),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(hist_df, use_container_width=True, hide_index=True, height=300)

    st.markdown("---")
    st.markdown("### Stocks Seen Most Often (All Time)")
    top_freq = df["symbol"].value_counts().reset_index()
    top_freq.columns = ["Symbol", "Total Appearances"]
    top_freq["Last Price"] = top_freq["Symbol"].map(
        df.groupby("symbol")["close"].last()
    ).round(2)
    top_freq["Last Seen"] = top_freq["Symbol"].map(
        df.groupby("symbol")["date"].max().dt.date.astype(str)
    )

    fig2 = px.bar(
        top_freq.head(20),
        x="Symbol", y="Total Appearances",
        color="Total Appearances",
        color_continuous_scale=["#1e3a5f","#0ea5e9"],
    )
    fig2.update_layout(
        paper_bgcolor="#0a0e1a", plot_bgcolor="#0f1628",
        font_color="#94a3b8", height=300,
        margin=dict(l=10,r=10,t=20,b=10),
        showlegend=False, coloraxis_showscale=False,
        xaxis=dict(gridcolor="#1e3a5f"),
        yaxis=dict(gridcolor="#1e3a5f"),
    )
    st.plotly_chart(fig2, use_container_width=True)


# ── Tab 4: Stock Detail ───────────────────────────────────────────────────────

with tab4:
    st.markdown("### Stock Detail — Signal History")

    all_syms = sorted(df["symbol"].unique().tolist())
    sel_sym  = st.selectbox("Select Stock", all_syms)

    if sel_sym:
        sym_df = df[df["symbol"] == sel_sym].sort_values("date")

        # Stats
        total_app  = len(sym_df)
        first_seen = sym_df["date"].min().strftime("%Y-%m-%d")
        last_seen  = sym_df["date"].max().strftime("%Y-%m-%d")
        last_price = sym_df["close"].iloc[-1]
        qty        = int(capital / last_price) if last_price > 0 else 0
        deploy     = qty * last_price

        c1, c2, c3, c4, c5 = st.columns(5)
        with c1: st.metric("Total Appearances", total_app)
        with c2: st.metric("First Seen",        first_seen)
        with c3: st.metric("Last Seen",         last_seen)
        with c4: st.metric("Last Price",        f"Rs {last_price:.2f}")
        with c5: st.metric("Qty to Buy",        f"{qty} shares (Rs {deploy:,.0f})")

        # Price chart over signal dates
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x    = sym_df["date"],
            y    = sym_df["close"],
            mode = "lines+markers",
            name = "Close Price",
            line = dict(color="#0ea5e9", width=2),
            marker = dict(color="#4ade80", size=8, symbol="triangle-up"),
            hovertemplate = "%{x|%Y-%m-%d}: Rs%{y:.2f}<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x    = sym_df["date"],
            y    = sym_df["ema9"],
            mode = "lines",
            name = "EMA9",
            line = dict(color="#f97316", width=1.5, dash="dot"),
        ))
        fig.add_trace(go.Scatter(
            x    = sym_df["date"],
            y    = sym_df["bb_lower"],
            mode = "lines",
            name = "BB Lower",
            line = dict(color="#a78bfa", width=1.5, dash="dash"),
        ))
        fig.update_layout(
            paper_bgcolor = "#0a0e1a",
            plot_bgcolor  = "#0f1628",
            font_color    = "#94a3b8",
            height        = 320,
            margin        = dict(l=10, r=10, t=30, b=10),
            legend        = dict(orientation="h", y=1.12, font_size=11),
            xaxis         = dict(gridcolor="#1e3a5f", title="Signal Date"),
            yaxis         = dict(gridcolor="#1e3a5f", title="Price (Rs)"),
            title         = dict(
                text=f"{sel_sym} — All Signal Dates",
                font=dict(size=14, color="#e2e8f0"), x=0
            ),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Frequency by month
        sym_df["month"] = sym_df["date"].dt.to_period("M").astype(str)
        monthly = sym_df.groupby("month").size().reset_index(name="count")

        fig3 = go.Figure(go.Bar(
            x=monthly["month"], y=monthly["count"],
            marker_color="#0ea5e9", opacity=0.85,
        ))
        fig3.update_layout(
            paper_bgcolor="#0a0e1a", plot_bgcolor="#0f1628",
            font_color="#94a3b8", height=200,
            margin=dict(l=10,r=10,t=30,b=10),
            title=dict(text="Monthly Signal Frequency", font=dict(size=13, color="#e2e8f0"), x=0),
            xaxis=dict(gridcolor="#1e3a5f"),
            yaxis=dict(gridcolor="#1e3a5f", title="Count"),
        )
        st.plotly_chart(fig3, use_container_width=True)

        # Full history table
        st.markdown("#### All Signal Dates")
        hist_tbl = sym_df[["date","close","ema9","bb_lower","bb_upper","avg_volume"]].copy()
        hist_tbl["date"] = hist_tbl["date"].dt.strftime("%Y-%m-%d")
        hist_tbl.columns = ["Date","Close","EMA9","BB Lower","BB Upper","Avg Volume"]
        hist_tbl = hist_tbl.sort_values("Date", ascending=False)
        st.dataframe(
            hist_tbl.style.format({
                "Close":      "Rs {:.2f}",
                "EMA9":       "Rs {:.2f}",
                "BB Lower":   "Rs {:.2f}",
                "BB Upper":   "Rs {:.2f}",
                "Avg Volume": "{:,.0f}",
            }),
            use_container_width=True, hide_index=True,
        )
