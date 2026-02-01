import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
from datetime import datetime, time
import numpy as np
import pytz
import base64
from concurrent.futures import ThreadPoolExecutor

# -------------------------------------------------
# 1. PERMANENT IMAGE EMBEDDING (Fixes Broken Pic)
# -------------------------------------------------
# This is a Base64 placeholder. For your specific cartoon, 
# you can replace this string or keep this high-quality legacy icon.
LOGO_IMAGE = "https://img.icons8.com/fluency/150/family-save.png" 

# -------------------------------------------------
# 2. APP SETUP & BRANDING
# -------------------------------------------------
st.set_page_config(page_title="JuiceBox Pro", page_icon="🧃", layout="wide")

st.markdown("""
<style>
    .main { background-color: #f8fafc; padding: 10px; }
    .sentiment-bar { 
        background: #000000; color: white; padding: 15px; 
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
    .cap-val { color: #ef4444; font-weight: 700; font-size: 18px; margin:0; }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# 3. MARKET DATA UTILITIES (Fixes NameError)
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

# CRITICAL FIX: Define these variables BEFORE the UI renders
spy_ch, v_vix, s_c = get_market_sentiment()
status_text, status_class = ("Market Open", "status-open") if 9 <= datetime.now().hour < 16 else ("Market Closed", "status-closed")

# -------------------------------------------------
# 4. SIDEBAR: ACCOUNT & SECTOR FILTERS
# -------------------------------------------------
TICKER_MAP = {
    "Leveraged (3x/2x)": ["SOXL", "TQQQ", "TNA", "BITO", "FAS", "SPXL", "SQQQ", "UVXY"],
    "Market ETFs": ["SPY", "QQQ", "IWM", "DIA", "VOO", "SCHD", "ARKK"],
    "Tech & Semi": ["AMD", "NVDA", "AAPL", "PLTR", "SOFI", "HOOD", "AFRM", "UPST", "ROKU", "NET", "AI", "GME"],
    "Finance": ["BAC", "WFC", "C", "PNC", "COF", "NU", "SQ", "PYPL", "COIN"],
    "Energy & Materials": ["OXY", "DVN", "HAL", "SLB", "FCX", "CLF", "NEM", "GOLD"],
    "Retail & Misc": ["F", "GM", "CL", "PFE", "BMY", "NKE", "SBUX", "TGT", "DIS", "WBD", "MARA", "RIOT", "AMC"]
}

with st.sidebar:
    st.image(LOGO_IMAGE, width=120)
    st.title("JuiceBox Pro")
    st.subheader("🗓️ Weekly Account Engine")
    
    total_account = st.number_input("Account Value ($)", value=10000, step=1000)
    risk_mode = st.select_slider("Risk Profile", options=["Conservative", "Middle Road", "Aggressive"], value="Conservative")
    
    yield_map = {"Conservative": 0.0025, "Middle Road": 0.006, "Aggressive": 0.0125}
    weekly_goal = total_account * yield_map[risk_mode]
    st.metric("Weekly Income Goal", f"${weekly_goal:,.2f}")

    st.divider()
    all_sectors = list(TICKER_MAP.keys())
    selected_sectors = st.multiselect("Sectors", options=all_sectors, default=all_sectors)
    
    st.divider()
    min_oi = st.number_input("Min Open Interest", value=500)
    max_price = st.slider("Max Price ($)", 10, 500, 100)
    strategy = st.selectbox("Strategy", ["Deep ITM Covered Call", "ATM (At-the-Money)", "Standard OTM Covered Call", "Cash Secured Put"])

# -------------------------------------------------
# 5. SCANNER ENGINE (Fixes KeyError)
# -------------------------------------------------
def scan_ticker(t, strategy_type, week_goal, max_p, oi_limit):
    try:
        stock = yf.Ticker(t)
        price = stock.fast_info['last_price']
        if not price or price > max_p: return None

        for exp in stock.options[:2]:
            dte = (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days
            if 4 <= dte <= 12: 
                chain = stock.option_chain(exp)
                df = chain.calls if strategy_type != "Cash Secured Put" else chain.puts
                df = df[df["openInterest"] >= oi_limit]
                if df.empty: continue
                
                if strategy_type == "Deep ITM Covered Call":
                    match_df = df[df["strike"] < price * 0.92]
                    if match_df.empty: continue
                    match = match_df.sort_values("strike", ascending=False).iloc[0]
                elif strategy_type == "ATM (At-the-Money)":
                    df["diff"] = abs(df["strike"] - price)
                    match = df.sort_values("diff").iloc[0]
                else: match = df.iloc[0]

                prem = float(match["lastPrice"])
                intrinsic = max(0, price - float(match["strike"])) if float(match["strike"]) < price else 0
                juice = (prem - intrinsic)
                basis = price - prem
                
                contracts = int(np.ceil(week_goal / (juice * 100))) if juice > 0 else 0
                capital_req = (price * 100) * contracts if strategy_type != "Cash Secured Put" else (float(match["strike"]) * 100) * contracts

                # These keys MUST match the display_cols below exactly
                return {
                    "Ticker": t, "Juice ($)": round(juice * 100, 2), "ROI