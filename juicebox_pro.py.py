import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
from datetime import datetime
import numpy as np
from concurrent.futures import ThreadPoolExecutor

# 1. APP SETUP
st.set_page_config(page_title="JuiceBox Pro", page_icon="🧃", layout="wide")

# 2. MARKET SENTIMENT (Top Bar)
def get_market_sentiment():
    try:
        data = yf.download(["^GSPC", "^VIX"], period="2d", interval="1d", progress=False)['Close']
        spy_ch = ((data["^GSPC"].iloc[-1] - data["^GSPC"].iloc[-2]) / data["^GSPC"].iloc[-2]) * 100
        vix_val = data["^VIX"].iloc[-1]
        return spy_ch, vix_val, ("#22c55e" if spy_ch >= 0 else "#ef4444")
    except: return 0.0, 0.0, "#fff"

spy_ch, v_vix, s_c = get_market_sentiment()

# 3. SIDEBAR: GOALS & FILTERS
with st.sidebar:
    try:
        st.image("couple.png", use_container_width=True)
    except:
        st.warning("Upload 'couple.png' to this folder to see your branding.")
    
    st.subheader("🗓️ Weekly Account Engine")
    total_acc = st.number_input("Account Value ($)", value=10000, step=1000)
    
    st.divider()
    # Share Price Range
    price_range = st.slider("Share Price Range ($)", 0, 500, (10, 150))
    min_p, max_p = price_range
    
    # Safety & DTE
    user_cushion = st.slider("Min ITM Cushion %", 2, 25, 8) 
    max_dte = st.slider("Max DTE (Days)", 4, 15, 10)
    
    st.divider()
    risk_mode = st.select_slider("Risk Profile", options=["Conservative", "Middle Road", "Aggressive"], value="Middle Road")
    yield_map = {"Conservative": 0.0025, "Middle Road": 0.006, "Aggressive": 0.0125}
    weekly_goal = total_acc * yield_map[risk_mode]
    st.metric("Weekly Income Goal", f"${weekly_goal:,.2f}")

    strategy = st.selectbox("Strategy", ["Deep ITM Covered Call", "ATM", "Standard OTM", "Cash Secured Put"])

# 4. SCANNER LOGIC
def scan_ticker(t, strategy_type, week_goal, cushion_limit, dte_limit, min_price, max_price):
    try:
        stock = yf.Ticker(t)
        price = stock.fast_info['last_price']
        if not price or not (min_price <= price <= max_price): return None

        for exp in stock.options[:3]:
            dte = (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days
            if 4 <= dte <= dte_limit:
                chain = stock.option_chain(exp)
                df = chain.calls if strategy_type != "Cash Secured Put" else chain.puts
                df = df[df["openInterest"] >= 300]
                if df.empty: continue
                
                # Strike selection based on cushion
                if "ITM" in strategy_type:
                    match_df = df[df["strike"] < price * (1 - (cushion_limit / 100))]
                    if match_df.empty: continue
                    match = match_df.sort_values("strike", ascending=False).iloc[0]
                else:
                    df["diff"] = abs(df["strike"] - price)
                    match = df.sort_values("diff").iloc[0]

                prem = float(match["lastPrice"])
                strike = float(match["strike"])
                juice = (prem - max(0, price - strike)) if strike < price else prem
                basis = price - prem
                contracts = int(np.ceil(week_goal / (juice * 100))) if juice > 0 else 0

                return {
                    "Ticker": t, "Price": round(price, 2), "Strike": strike,
                    "Premium ($)": round(prem * 100, 2), "Juice ($)": round(juice * 100, 2), 
                    "Cushion %": round(((price - basis) / price) * 100, 2), 
                    "DTE": dte, "Contracts": contracts, "Capital Req": round(price * 100 * contracts, 2)
                }
    except: return None

# 5. UI RESULTS
st.markdown(f'<div style="background:#000; color:#fff; padding:15px; border-radius:15px; text-align:center;">'
            f'<b>S&P 500:</b> <span style="color:{s_c}">{spy_ch:+.2f}%</span> | <b>VIX:</b> {v_vix:.2f}</div>', unsafe_allow_html=True)

if st.button("RUN GENERATIONAL SCAN ⚡", use_container_width=True):
    univ = ["SPY", "QQQ", "IWM", "AMD", "NVDA", "AAPL", "TSLA", "PLTR", "SOFI", "AFRM", "MARA", "RIOT", "F", "BAC"]
    with ThreadPoolExecutor(max_workers=15) as ex:
        results = [r for r in ex.map(lambda t: scan_ticker(t, strategy, weekly_goal, user_cushion, max_dte, min_p, max_p), univ) if r]
    st.session_state.results = results

if "results" in st.session_state:
    df = pd.DataFrame(st.session_state.results)
    st.dataframe(df, use_container_width=True, hide_index=True)