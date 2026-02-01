# =================================================================
# SOFTWARE LICENSE AGREEMENT
# Property of: Bucforty LLC | Project: JuiceBox Pro™
# Copyright (c) 2026. All Rights Reserved.
# =================================================================

import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta
from concurrent.futures import ThreadPoolExecutor

# 1. APP SETUP
st.set_page_config(page_title="JuiceBox Pro", page_icon="🧃", layout="wide")

st.markdown("""
<style>
    .grade-a { background:#22c55e;color:white;padding:4px 10px;border-radius:18px;font-weight:700;}
    .grade-b { background:#eab308;color:white;padding:4px 10px;border-radius:18px;font-weight:700;}
    .card {border:1px solid #e5e7eb;border-radius:16px;padding:18px;background:white;box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); color: #1f2937; margin-top: 10px;}
    .juice-val {color:#16a34a;font-size:26px;font-weight:800;margin:10px 0;}
    .market-banner {padding: 10px; border-radius: 8px; margin-bottom: 20px; font-weight: bold; text-align: center;}
    .market-open {background-color: #dcfce7; color: #166534; border: 1px solid #86efac;}
    .market-closed {background-color: #fee2e2; color: #991b1b; border: 1px solid #fca5a5;}
</style>
""", unsafe_allow_html=True)

# 2. DATA HELPERS
def get_market_status():
    now_et = datetime.utcnow() - timedelta(hours=5) 
    is_open = (0 <= now_et.weekday() <= 4) and (time(9, 30) <= now_et.time() <= time(16, 0))
    return is_open, now_et

@st.cache_data(ttl=300)
def get_spy_condition():
    try:
        spy = yf.Ticker("SPY").history(period="2d")
        curr, prev = spy["Close"].iloc[-1], spy["Close"].iloc[-2]
        return curr, ((curr - prev) / prev) * 100
    except: return 0, 0

def get_live_price(t):
    try:
        tk = yf.Ticker(t)
        hist = tk.history(period="1d", interval="1m")
        return float(hist["Close"].iloc[-1]) if not hist.empty else None
    except: return None

# 3. SIDEBAR
with st.sidebar:
    st.header("🧃 Configuration")
    acct = st.number_input("Account Value ($)", 1000, 1000000, 10000, step=500)
    goal = st.number_input("Weekly Goal ($)", 10, 50000, 150, step=10)
    price_range = st.slider("Stock Price Range ($)", 1, 500, (2, 100))
    dte_range = st.slider("Days to Expiration (DTE)", 0, 45, (0, 30))
    strategy = st.selectbox("Strategy", ["Deep ITM Covered Call", "Standard OTM Covered Call", "ATM Covered Call", "Cash Secured Put"])
    cushion = st.slider("Min ITM Cushion %", 0, 50, 10) if "Deep ITM" in strategy else 0
    
    text = st.text_area("Watchlist", value="SOFI, PLUG, RIVN, DKNG, AAL, PYPL, AI, F, LCID, ROKU, BOIL, RIOT", height=150)
    tickers = sorted({t.upper() for t in text.replace(",", " ").split() if t.strip()})

# 4. SCANNER LOGIC
def scan(t):
    try:
        price = get_live_price(t)
        if not price or not (price_range[0] <= price <= price_range[1]): return None
        
        tk = yf.Ticker(t)
        today = datetime.now()
        best = None

        for exp in tk.options:
            dte = (datetime.strptime(exp, "%Y-%m-%d") - today).days
            if not (dte_range[0] <= dte <= dte_range[1]): continue

            chain = tk.option_chain(exp)
            df = chain.puts if strategy == "Cash Secured Put" else chain.calls
            
            # Strategy Filtering
            if "Deep ITM" in strategy:
                df = df[df["strike"] <= price * (1 - cushion / 100)]
            elif "OTM" in strategy:
                df = df[df["strike"] > price]

            for _, row in df.iterrows():
                strike = row["strike"]
                prem = (row["bid"] + row["ask"]) / 2 if row["ask"] > 0 else row["lastPrice"]
                
                # --- EXTRINSIC MATH (THE FIX) ---
                intrinsic = max(0, price - strike) if strategy != "Cash Secured Put" else max(0, strike - price)
                extrinsic = max(0, prem - intrinsic)
                
                # Only stocks with time value left
                if extrinsic <= 0.05: continue 

                # Collateral = Stock Price - Premium (Net Debit)
                collateral = (price - prem) * 100
                juice_con = extrinsic * 100 if "Deep ITM" in strategy else prem * 100
                
                # Return on Capital (ROC)
                ret_pct = (extrinsic / (price - prem)) * 100 if (price - prem) > 0 else 0
                
                needed = max(1, int(np.ceil(goal / (juice_con if juice_con > 0 else 1))))
                if (needed * collateral) > acct: continue

                res = {
                    "Ticker": t, "Grade": "🟢 A" if ret_pct > 1.5 else "🟡 B",
                    "Price": round(price, 2), "Strike": round(strike, 2), "Expiration": exp, 
                    "DTE": dte, "Juice/Con": round(juice_con, 2), "Total Return %": round(ret_pct, 2),
                    "Collateral": round(needed * collateral, 0), "Extrinsic": round(extrinsic * 100, 2)
                }
                if not best or ret_pct > best["Total Return %"]: best = res
        return best
    except: return None

# 5. UI DISPLAY
st.title("🧃 JuiceBox Pro")
is_open, et_time = get_market_status()
spy_p, spy_c = get_spy_condition()

st.markdown(f'<div class="market-banner {"market-open" if is_open else "market-closed"}">'
            f'{"MARKET OPEN" if is_open else "MARKET CLOSED"} | {et_time.strftime("%I:%M %p")} ET | '
            f'SPY: ${spy_p:.2f} ({spy_c:+.2f}%)</div>', unsafe_allow_html=True)

if st.button("RUN LIVE SCAN ⚡", use_container_width=True):
    with ThreadPoolExecutor(max_workers=10) as ex:
        results = [r for r in list(ex.map(scan, tickers)) if r]
    st.session_state.results = results

if "results" in st.session_state:
    df_res = pd.DataFrame(st.session_state.results).sort_values("Total Return %", ascending=False)
    st.dataframe(df_res[["Ticker", "Grade", "Price", "Strike", "Expiration", "DTE", "Juice/Con", "Total Return %"]], use_container_width=True, hide_index=True)