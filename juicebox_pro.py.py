# =================================================================
# SOFTWARE LICENSE AGREEMENT
# Property of: Bucforty LLC
# Project: JuiceBox Pro™
# Copyright (c) 2026. All Rights Reserved.
# NOTICE: This code is proprietary. Reproduction or 
# redistribution of this material is strictly forbidden.
# =================================================================

import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta
from concurrent.futures import ThreadPoolExecutor

# -------------------------------------------------
# 1. APP SETUP & STYLING
# -------------------------------------------------
st.set_page_config(page_title="JuiceBox Pro", page_icon="🧃", layout="wide")

st.markdown("""
<style>
    .grade-a { background:#22c55e;color:white;padding:4px 10px;border-radius:18px;font-weight:700;}
    .grade-b { background:#eab308;color:white;padding:4px 10px;border-radius:18px;font-weight:700;}
    .card {border:1px solid #e5e7eb;border-radius:16px;padding:18px;background:white;box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); color: #1f2937; margin-top: 10px;}
    .juice-val {color:#16a34a;font-size:26px;font-weight:800;margin:10px 0;}
    .stButton>button {border-radius:12px;font-weight:700;height:3em;background-color:#16a34a !important; color: white !important;}
    .market-banner {padding: 10px; border-radius: 8px; margin-bottom: 20px; font-weight: bold; text-align: center;}
    .market-open {background-color: #dcfce7; color: #166534; border: 1px solid #86efac;}
    .market-closed {background-color: #fee2e2; color: #991b1b; border: 1px solid #fca5a5;}
    .disclaimer {font-size: 11px; color: #9ca3af; line-height: 1.4; margin-top: 30px; padding: 20px; border-top: 1px solid #eee;}
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# 2. DATA HELPERS
# -------------------------------------------------
def get_market_status():
    now_utc = datetime.utcnow()
    now_et = now_utc - timedelta(hours=5) 
    is_weekday = 0 <= now_et.weekday() <= 4
    current_time = now_et.time()
    market_open = time(9, 30)
    market_close = time(16, 0)
    is_open = is_weekday and (market_open <= current_time <= market_close)
    return is_open, now_et

@st.cache_data(ttl=300)
def get_spy_condition():
    try:
        spy = yf.Ticker("SPY")
        hist = spy.history(period="2d")
        if len(hist) >= 2:
            prev_close = hist["Close"].iloc[-2]
            curr_price = hist["Close"].iloc[-1]
            pct_change = ((curr_price - prev_close) / prev_close) * 100
            return curr_price, pct_change
    except: pass
    return 0, 0

@st.cache_data(ttl=60)
def get_live_price(t):
    try:
        tk = yf.Ticker(t)
        hist = tk.history(period="1d", interval="1m")
        if not hist.empty: return float(hist["Close"].iloc[-1])
    except: pass
    return None

def mid_price(row):
    bid, ask, lastp = row.get("bid"), row.get("ask"), row.get("lastPrice")
    if pd.notna(bid) and pd.notna(ask) and ask > 0: return (bid + ask) / 2
    return float(lastp) if pd.notna(lastp) else 0

# -------------------------------------------------
# 3. SIDEBAR
# -------------------------------------------------
with st.sidebar:
    st.header("🧃 Configuration")
    acct = st.number_input("Account Value ($)", 1000, 1000000, 10000, step=500)
    
    # --- PERCENTAGE & MONEY GOAL ---
    c1, c2 = st.columns(2)
    with c1:
        goal_pct = st.number_input("Weekly Goal (%)", 0.1, 10.0, 1.5, step=0.1)
    with c2:
        # Auto-calculate dollar goal based on percentage
        calc_goal = acct * (goal_pct / 100)
        goal_amt = st.number_input("Weekly Goal ($)", 1.0, 100000.0, calc_goal, step=10.0)
    
    price_range = st.slider("Stock Price Range ($)", 1, 500, (2, 100))
    dte_range = st.slider("Days to Expiration (DTE)", 0, 45, (0, 30))
    strategy = st.selectbox("Strategy", ["Deep ITM Covered Call", "Standard OTM Covered Call", "ATM Covered Call", "Cash Secured Put"])
    
    put_mode = "OTM"
    if strategy == "Cash Secured Put":
        put_mode = st.radio("Put Strategy Mode", ["OTM (Safe)", "ITM (Extrinsic Focus)"], horizontal=True)
    
    cushion_val = st.slider("Min Cushion %", 0, 50, 10) if strategy != "ATM Covered Call" else 0
    st.info(f"💡 **OI 500+ Active** | Targeting ${goal_amt:,.2f} ({goal_pct}%)")

    st.divider()
    text = st.text_area("Ticker Watchlist", value="SOFI, PLUG, LUMN, OPEN, BBAI, CLOV, MVIS, MPW, PLTR, AAL, F, NIO, BAC, T, VZ, AAPL, AMD, TSLA, PYPL, KO, O, TQQQ, SOXL, C, MARA, RIOT, COIN, DKNG, LCID, AI, GME, AMC, SQ, SHOP, NU, RIVN, GRAB, CCL, NCLH, RCL, SAVE, JBLU, UAL, NET, CRWD, SNOW, DASH, ROKU, CHWY, CVNA, BKNG, ABNB, ARM, AVGO, MU, INTC, TSM, GFS, PLD, AMT, CMCSA, DIS, NFLX, PARA, SPOT, BOIL, UNG", height=150)
    tickers = sorted({t.upper() for t in text.replace(",", " ").split() if t.strip()})

# -------------------------------------------------
# 4. SCANNER LOGIC
# -------------------------------------------------
def scan(t):
    try:
        price = get_live_price(t)
        if not price or not (price_range[0] <= price <= price_range[1]): return None
        tk = yf.Ticker(t)
        if not tk.options: return None

        today = datetime.now()
        best = None
        for exp in tk.options:
            exp_dte = (datetime.strptime(exp, "%Y-%m-%d") - today).days
            if not (dte_range[0] <= exp_dte <= dte_range[1]): continue

            chain = tk.option_chain(exp)
            is_put = strategy == "Cash Secured Put"
            df = chain.puts if is_put else chain.calls
            
            if strategy == "Deep ITM Covered Call":
                df = df[df["strike"] <= price * (1 - cushion_val / 100)]
            elif strategy == "Standard OTM Covered Call":
                df = df[df["strike"] > price]
            elif strategy == "Cash Secured Put":
                if "OTM" in put_mode:
                    df = df[df["strike"] <= price * (1 - cushion_val / 100)]
                else:
                    df = df[df["strike"] >= price * (1 + cushion_val / 100)]

            for _, row in df.iterrows():
                strike, total_prem = row["strike"], mid_price(row)
                open_int = row.get("openInterest", 0)
                if open_int < 500 or total_prem <= 0: continue

                intrinsic = max(0, price - strike) if not is_put else max(0, strike - price)
                extrinsic = max(0, total_prem - intrinsic)

                if intrinsic > 0 and extrinsic <= 0.05: continue

                juice_con = extrinsic * 100 if intrinsic > 0 else total_prem * 100
                coll_con = strike * 100 if is_put else price * 100

                upside = ((strike - price) / price * 100) if not is_put and strike > price else 0
                total_ret = ((juice_con / coll_con) * 100) + upside
                
                # USE DYNAMIC GOAL AMOUNT
                needed = max(1, int(np.ceil(goal_amt / (juice_con if juice_con > 0 else 1))))
                if (needed * coll_con) > acct: continue

                res = {
                    "Ticker": t, "Grade": "🟢 A" if total_ret > 5 else "🟡 B",
                    "Price": round(price, 2), "Strike": round(strike, 2), "Expiration": exp, "DTE": exp_dte,
                    "Extrinsic": round(extrinsic * 100, 2), "Intrinsic": round(intrinsic * 100, 2),
                    "Total Prem": round(total_prem * 100, 2), "OI": int(open_int),
                    "Juice/Con": round(juice_con, 2), "Total Return %": round(total_ret, 2), 
                    "Contracts": needed, "Total Juice": round(juice_con * needed, 2), 
                    "Collateral": round(needed * coll_con, 0)
                }
                if not best or total_ret > best["Total Return %"]: best = res
        return best
    except: return None

# -------------------------------------------------
# 5. UI DISPLAY
# -------------------------------------------------
st.title("🧃 JuiceBox Pro")
is_open, et_time = get_market_status()
spy_price, spy_pct = get_spy_condition()
st.markdown(f"""<div class="market-banner {'market-open' if is_open else 'market-closed'}">
{'MARKET OPEN 🟢' if is_open else 'MARKET CLOSED 🔴'} | ET: {et_time.strftime('%I:%M %p')} | SPY: ${spy_price:.2f} ({spy_pct:+.2f}%)</div>""", unsafe_allow_html=True)

if st.button("RUN LIVE SCAN ⚡", use_container_width=True):
    with st.spinner(f"Scanning for {goal_pct}% yield opportunities..."):