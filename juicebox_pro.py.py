import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
from datetime import datetime, time
import numpy as np
import pytz
from concurrent.futures import ThreadPoolExecutor

# -------------------------------------------------
# 1. MOBILE-FIRST APP SETUP
# -------------------------------------------------
st.set_page_config(page_title="JuiceBox Pro", page_icon="🧃", layout="wide")

st.markdown("""
<style>
    .main { background-color: #f8fafc; padding: 10px; }
    .sentiment-bar { 
        background: #1e293b; color: white; padding: 15px; 
        border-radius: 15px; margin-bottom: 20px; 
        display: flex; flex-direction: column; align-items: center; gap: 8px;
    }
    .status-tag { padding: 4px 12px; border-radius: 20px; font-size: 12px; text-transform: uppercase; }
    .status-open { background-color: #16a34a; color: white; }
    .status-closed { background-color: #dc2626; color: white; }
    .card { 
        border: 1px solid #e2e8f0; border-radius: 15px; background: white; 
        padding: 20px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); margin-bottom: 15px; 
    }
    .juice-val { color: #16a34a; font-weight: 800; font-size: 26px; margin:0; }
    .prem-val { color: #3b82f6; font-weight: 700; font-size: 18px; margin:0; }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# 2. MARKET DATA UTILITIES
# -------------------------------------------------
def get_market_sentiment():
    try:
        data = yf.download(["^GSPC", "^VIX"], period="5d", interval="1d", progress=False)['Close']
        if data.empty or len(data) < 2: return 0.0, 0.0, "#fff"
        spy_now, spy_prev = data["^GSPC"].iloc[-1], data["^GSPC"].iloc[-2]
        spy_ch = 0.0 if np.isnan(spy_now) or spy_prev == 0 else ((spy_now - spy_prev) / spy_prev) * 100
        vix_val = data["^VIX"].iloc[-1] if not np.isnan(data["^VIX"].iloc[-1]) else 0.0
        return spy_ch, vix_val, ("#22c55e" if spy_ch >= 0 else "#ef4444")
    except: return 0.0, 0.0, "#fff"

spy_ch, v_vix, s_c = get_market_sentiment()
status_text, status_class = ("Market Open", "status-open") if 9 <= datetime.now().hour < 16 else ("Market Closed", "status-closed")

# -------------------------------------------------
# 3. SIDEBAR: WEEKLY GOAL & ACCOUNT ENGINE
# -------------------------------------------------
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/box.png", width=60)
    st.subheader("🗓️ Weekly Account Engine")
    
    total_capital = st.number_input("Account Value ($)", value=10000, step=1000)
    risk_mode = st.select_slider("Risk Profile", options=["Conservative", "Middle Road", "Aggressive"], value="Conservative")
    
    yield_map = {"Conservative": 0.0025, "Middle Road": 0.006, "Aggressive": 0.0125}
    weekly_goal = total_capital * yield_map[risk_mode]
    st.metric("Weekly Income Goal", f"${weekly_goal:,.2f}")

    st.divider()
    st.subheader("🛡️ Safety & Liquidity")
    min_oi = st.number_input("Min Open Interest", value=500)
    min_cushion_req = st.slider("Min Cushion %", 0, 20, 5)
    max_price = st.slider("Max Share Price ($)", 10, 100, 100)
    
    st.divider()
    strategy = st.selectbox("Strategy", ["Deep ITM Covered Call", "ATM (At-the-Money)", "Standard OTM Covered Call", "Cash Secured Put"])

# -------------------------------------------------
# 4. SCANNER LOGIC (Premium & Share Price Added)
# -------------------------------------------------
def scan_ticker(t, strategy_type, week_goal, max_p, oi_limit, min_cushion):
    try:
        stock = yf.Ticker(t)
        info = stock.info
        share_price = info.get('currentPrice') or info.get('regularMarketPrice')
        if not share_price or share_price > max_p: return None

        for exp in stock.options[:2]:
            dte = (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days
            if 4 <= dte <= 12: 
                chain = stock.option_chain(exp)
                df = chain.calls if strategy_type != "Cash Secured Put" else chain.puts
                df = df[df["openInterest"] >= oi_limit]
                if df.empty: continue
                
                if strategy_type == "Deep ITM Covered Call":
                    match_df = df[df["strike"] < share_price * (1 - min_cushion/100)]
                    if match_df.empty: continue
                    match = match_df.sort_values("strike", ascending=False).iloc[0]
                elif strategy_type == "ATM (At-the-Money)":
                    df["diff"] = abs(df["strike"] - share_price)
                    match = df.sort_values("diff").iloc[0]
                else: match = df.iloc[0]

                opt_premium = float(match["lastPrice"])
                intrinsic = max(0, share_price - float(match["strike"])) if float(match["strike"]) < share_price else 0
                juice = (opt_premium - intrinsic)
                basis = share_price - opt_premium
                roi = (juice / basis) * 100
                
                cushion_pct = ((share_price - basis) / share_price) * 100
                contracts = int(np.ceil(week_goal / (juice * 100))) if juice > 0 else 0

                return {
                    "Ticker": t, "Share Price": round(share_price, 2), "Strike": float(match["strike"]),
                    "Total Prem ($)": round(opt_premium * 100, 2), "Juice ($)": round(juice * 100, 2),
                    "ROI %": round(roi, 2), "Cushion %": round(cushion_pct, 2), "OI": int(match["openInterest"]),
                    "Contracts": contracts, "DTE": dte, "Expiry": exp
                }
    except: return None

# -------------------------------------------------
# 5. UI DISPLAY & RESULTS
# -------------------------------------------------
st.markdown(f"""
<div class="sentiment-bar">
    <span class="status-tag {status_class}">{status_text}</span>
    <div><b>S&P 500:</b> <span style="color:{s_c}">{spy_ch:+.2f}%</span> | <b>VIX:</b> {v_vix:.2f}</div>
</div>
""", unsafe_allow_html=True)

if st.button("RUN WEEKLY SCAN ⚡", use_container_width=True):
    univ = ["SPY", "QQQ", "IWM", "AMD", "NVDA", "AAPL", "TSLA", "PLTR", "SOFI", "AFRM", "MARA", "RIOT", "F", "BAC"]
    with ThreadPoolExecutor(max_workers=20) as ex:
        results = [r for r in ex.map(lambda t: scan_ticker(t, strategy, weekly_goal, max_price, min_oi, min_cushion_req), list(set(univ))) if r]
    st.session_state.results = sorted(results, key=lambda x: x['ROI %'], reverse=True)

if "results" in st.session_state and st.session_state.results:
    df = pd.DataFrame(st.session_state.results)
    
    # Selection Table with Premium and Share Price
    sel = st.dataframe(df[["Ticker", "Share Price", "Strike", "Total Prem ($)", "Juice ($)", "Cushion %", "Contracts"]], 
                       use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")

    if sel.selection.rows:
        row = df.iloc[sel.selection.rows[0]]
        st.divider