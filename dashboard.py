"""
BB + EMA Scanner Dashboard
Run: streamlit run dashboard.py
"""

import os
import json
import glob
import subprocess
import sys
import streamlit as st
import pandas as pd

st.set_page_config(page_title="BB+EMA Scanner", page_icon="📈", layout="wide")

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Syne:wght@400;600;800&display=swap');
  html, body, [class*="css"] { font-family: 'Syne', sans-serif; background:#0a0e1a; color:#e2e8f0; }
  .stApp { background:#0a0e1a; }
  section[data-testid="stSidebar"] { background:#0f1628; border-right:1px solid #1e2d4a; }
  div[data-testid="metric-container"] { background:linear-gradient(135deg,#111827,#1a2540); border:1px solid #1e3a5f; border-radius:12px; padding:1rem; }
  div[data-testid="metric-container"] label { color:#64748b!important; font-size:.72rem!important; text-transform:uppercase; }
  div[data-testid="metric-container"] div[data-testid="stMetricValue"] { color:#38bdf8!important; font-family:'JetBrains Mono',monospace; font-size:1.8rem!important; }
  .stButton>button { background:linear-gradient(135deg,#1d4ed8,#0ea5e9)!important; color:white!important; border:none!important; border-radius:8px!important; font-weight:600!important; }
  hr { border-color:#1e3a5f!important; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## BB+EMA Scanner")
    st.markdown("---")

    universe = st.selectbox(
        "Stock Universe",
        ["NIFTY_50","NIFTY_100","NIFTY_200","NSE_500","NSE_1000","NSE_ALL"],
        index=0,
    )

    st.markdown("### Price Filter (optional)")
    st.caption("Leave at 0 / 999999 to scan all prices")
    min_price = st.number_input("Min Price (Rs)", min_value=0, max_value=50000, value=0, step=10)
    max_price = st.number_input("Max Price (Rs)", min_value=0, max_value=200000, value=999999, step=100)

    st.markdown("---")

    if st.button("Run Scanner Now", use_container_width=True):
        cmd = [sys.executable, "run_scanner.py", "--universe", universe]
        if min_price > 0:
            cmd += ["--min-price", str(min_price)]
        if max_price < 999999:
            cmd += ["--max-price", str(max_price)]
        subprocess.Popen(cmd, cwd=os.getcwd())
        st.success(
            f"Scanner started!\n"
            f"Universe: {universe}\n"
            f"Refresh in a few minutes."
        )

    st.markdown("---")
    st.markdown(
        "<div style='color:#475569;font-size:.75rem'>"
        "Signal: BB Lower Touch + 9 EMA Bounce<br>"
        "Data: Upstox API (Yahoo Finance fallback)<br>"
        "Run after 3:30 PM IST"
        "</div>",
        unsafe_allow_html=True,
    )

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="background:linear-gradient(90deg,#0f1f3d,#0a2550);border:1px solid #1e3a5f;
     border-radius:16px;padding:1.5rem 2rem;margin-bottom:1.5rem;">
  <p style="font-family:Syne,sans-serif;font-weight:800;font-size:1.6rem;color:#38bdf8;margin:0">
    📈 BB + EMA Buy Signal Scanner
  </p>
  <p style="color:#64748b;font-size:.85rem;margin:.3rem 0 0">
    Bollinger Band Lower Touch + 9 EMA Bounce | NSE Daily
  </p>
</div>
""", unsafe_allow_html=True)

# ── Load results ──────────────────────────────────────────────────────────────
files = sorted(glob.glob("data/signals_*.json"), reverse=True)

if not files:
    st.warning("No results yet.")
    st.info(
        "**How to use:**\n\n"
        "1. Select universe in the sidebar\n"
        "2. Click **Run Scanner Now**\n"
        "3. Refresh after a few minutes\n\n"
        "Or results will appear automatically after the daily GitHub Actions run."
    )
    st.stop()

dates  = [os.path.basename(f).replace("signals_","").replace(".json","") for f in files]
labels = [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in dates]
sel    = st.selectbox("Scan Date", labels, index=0)
data   = json.load(open(files[labels.index(sel)]))
sigs   = data.get("signals", [])
rng    = data.get("price_range", [0, 999999])

st.caption(
    f"Universe: {data.get('universe','')} | "
    f"Scanned: {data.get('total_scanned',0)} stocks | "
    f"Range: Rs{rng[0]}-Rs{rng[1]} | "
    f"Date: {data.get('date','')}"
)

# ── Metrics ───────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
with c1: st.metric("Stocks Scanned", data.get("total_scanned", 0))
with c2: st.metric("Buy Signals",    len(sigs))
with c3:
    rate = round(len(sigs) / max(data.get("total_scanned",1),1) * 100, 1)
    st.metric("Signal Rate", f"{rate}%")
with c4: st.metric("Errors", data.get("errors", 0))

st.markdown("---")

if not sigs:
    st.info("No buy signals for this scan. This is normal — strategy is selective.")
    st.stop()

# ── Results table ─────────────────────────────────────────────────────────────
rows = []
for s in sigs:
    chg = round(((s["close"] - s.get("prev_close", s["close"])) /
                  max(s.get("prev_close", s["close"]), 1)) * 100, 2)
    rows.append({
        "Symbol":     s["symbol"],
        "Close (Rs)": s["close"],
        "Change %":   chg,
        "EMA 9":      s.get("ema9", ""),
        "BB Lower":   s.get("bb_lower", ""),
        "BB Upper":   s.get("bb_upper", ""),
        "Avg Volume": s.get("avg_volume", 0),
    })
df = pd.DataFrame(rows)

left, right = st.columns([3, 2])

with left:
    st.markdown(f"### Buy Signals &nbsp; `{len(df)}`")
    styled = (
        df.style
        .applymap(
            lambda v: "color:#4ade80" if isinstance(v,(int,float)) and v > 0
                      else "color:#f87171" if isinstance(v,(int,float)) and v < 0 else "",
            subset=["Change %"]
        )
        .format({
            "Close (Rs)": "Rs {:.2f}", "Change %": "{:+.2f}%",
            "EMA 9":      "Rs {:.2f}", "BB Lower": "Rs {:.2f}",
            "BB Upper":   "Rs {:.2f}", "Avg Volume": "{:,.0f}",
        }, na_rep="—")
    )
    st.dataframe(styled, use_container_width=True, height=460)
    st.download_button(
        "Download CSV", df.to_csv(index=False),
        file_name=f"signals_{sel}.csv", mime="text/csv"
    )

with right:
    st.markdown("### Price Distribution")
    import plotly.graph_objects as go
    fig = go.Figure(go.Histogram(
        x=df["Close (Rs)"], nbinsx=20,
        marker_color="#0ea5e9", opacity=0.8
    ))
    fig.update_layout(
        paper_bgcolor="#0a0e1a", plot_bgcolor="#0f1628",
        font_color="#94a3b8", margin=dict(l=10,r=10,t=20,b=10),
        height=240, showlegend=False,
        xaxis=dict(title="Price (Rs)", gridcolor="#1e3a5f"),
        yaxis=dict(title="Count", gridcolor="#1e3a5f"),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Top Movers")
    for _, row in df.nlargest(5, "Change %").iterrows():
        c = "#4ade80" if row["Change %"] >= 0 else "#f87171"
        s = "+" if row["Change %"] >= 0 else ""
        st.markdown(
            f"""<div style="background:#0f1628;border:1px solid #1e2d4a;
                border-radius:10px;padding:.7rem 1rem;margin-bottom:.35rem;
                display:flex;align-items:center;justify-content:space-between;">
              <span style="font-family:'JetBrains Mono',monospace;font-weight:600">{row['Symbol']}</span>
              <div style="text-align:right">
                <div style="font-family:'JetBrains Mono',monospace;color:#4ade80;font-weight:600">
                  Rs {row['Close (Rs)']:.2f}
                </div>
                <div style="color:{c};font-size:.8rem">{s}{row['Change %']:.2f}%</div>
              </div>
            </div>""",
            unsafe_allow_html=True,
        )

# ── History ───────────────────────────────────────────────────────────────────
if len(files) > 1:
    st.markdown("---")
    st.markdown("### Scan History")
    hist = []
    for f in files[:10]:
        d = json.load(open(f))
        r = d.get("price_range", [0, 999999])
        hist.append({
            "Date":      d.get("date",""),
            "Universe":  d.get("universe",""),
            "Price Range": f"Rs{r[0]}-Rs{r[1]}",
            "Scanned":   d.get("total_scanned", 0),
            "Signals":   d.get("total_signals", 0),
            "Errors":    d.get("errors", 0),
        })
    st.dataframe(pd.DataFrame(hist), use_container_width=True, hide_index=True)
