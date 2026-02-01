import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
from datetime import datetime, time
import numpy as np
import pytz
from concurrent.futures import ThreadPoolExecutor

# -------------------------------------------------
# 1. APP SETUP & BRANDING
# -------------------------------------------------
st.set_page_config(page_title="JuiceBox Pro", page_icon="🧃", layout="wide")

# Persistent Trade Log for tracking wealth over time
if 'wealth_log' not in st.session_state:
    st.session_state.wealth_log = []

# High-quality static icon
LOGO_URL = "https://img.icons8.com/fluency/150/family-save.png"

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
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# 2. MARKET DATA UTILITIES (Fixes NameError)
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
# 3. SIDEBAR: ACCOUNT & CUSTOM CUSHION
# -------------------------------------------------
with st.sidebar:
    st.image(LOGO_URL, width=100)
    st.subheader("🗓️ Weekly Account Engine")
    total_account = st.number_input("Account Value ($)", value=10000, step=1000)
    
    # MANUAL CUSHION SELECTOR
    st.divider()
    st.subheader("🛡️ Safety Settings")
    user_cushion = st.slider("Min ITM Cushion %", 2, 20, 8) 
    min_oi = st.number_input("Min Open Interest", value=500)
    
    st.divider()
    risk_mode = st.select_slider("Risk Profile", options=["Conservative", "Middle Road", "Aggressive"], value="Conservative")
    yield_map = {"Conservative": 0.0025, "Middle Road": 0.006, "Aggressive": 0.0125}
    weekly_goal = total_account * yield_map[risk_mode]
    st.metric("Weekly Income Goal", f"${weekly_goal:,.2f}")

    st.divider()
    strategy = st.selectbox("Strategy", ["Deep ITM Covered Call", "ATM (At-the-Money)", "Standard OTM Covered Call", "Cash Secured Put"])

# -------------------------------------------------
# 4. SCANNER ENGINE (Fixes KeyError)
# -------------------------------------------------
def scan_ticker(t, strategy_type, week_goal, cushion_limit, oi_limit):
    try:
        stock = yf.Ticker(t)
        price = stock.fast_info['last_price']
        if not price: return None

        for exp in stock.options[:2]:
            dte = (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days
            if 4 <= dte <= 12: 
                chain = stock.option_chain(exp)
                df = chain.calls if strategy_type != "Cash Secured Put" else chain.puts
                df = df[df["openInterest"] >= oi_limit]
                if df.empty: continue
                
                # Apply user-defined cushion for ITM
                if strategy_type == "Deep ITM Covered Call":
                    match_df = df[df["strike"] < price * (1 - (cushion_limit / 100))]
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

                return {
                    "Ticker": t, "Juice ($)": round(juice * 100, 2), "ROI %": round((juice/basis)*100, 2),
                    "Cushion %": round(((price - basis) / price) * 100, 2), "Strike": float(match["strike"]),
                    "Contracts": contracts, "Capital Req ($)": round(capital_req, 2), "OI": int(match["openInterest"])
                }
    except: return None

# -------------------------------------------------
# 5. UI DISPLAY & WEALTH TRACKER
# -------------------------------------------------
st.markdown(f"""
<div class="sentiment-bar">
    <span class="status-tag {status_class}">{status_text}</span>
    <div><b>S&P 500:</b> <span style="color:{s_c}">{spy_ch:+.2f}%</span> | <b>VIX:</b> {v_vix:.2f}</div>
</div>
""", unsafe_allow_html=True)

if st.button("RUN GENERATIONAL SCAN ⚡", use_container_width=True):
    univ = ["SPY", "QQQ", "IWM", "AMD", "NVDA", "AAPL", "TSLA", "PLTR", "SOFI", "AFRM", "MARA", "RIOT", "F", "BAC"]
    with ThreadPoolExecutor(max_workers=20) as ex:
        results = [r for r in ex.map(lambda t: scan_ticker(t, strategy, weekly_goal, user_cushion, min_oi), list(set(univ))) if r]
    st.session_state.results = sorted(results, key=lambda x: x['ROI %'], reverse=True)

if "results" in st.session_state and st.session_state.results:
    df = pd.DataFrame(st.session_state.results)
    display_cols = ["Ticker", "Juice ($)", "ROI %", "Cushion %", "Contracts", "Capital Req ($)"]
    sel = st.dataframe(df[display_cols], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")

    if sel.selection.rows:
        row = df.iloc[sel.selection.rows[0]]
        st.divider()
        c1, c2 = st.columns([2, 1])
        with c1:
            components.html(f"""
                <div id="tv-chart" style="height:400px;"></div>
                <script src="https://s3.tradingview.com/tv.js"></script>
                <script>new TradingView.widget({{"autosize": true, "symbol": "{row['Ticker']}", "interval": "D", "theme": "light", "style": "1", "container_id": "tv-chart"}});</script>
            """, height=420)
        with c2:
            st.markdown(f"""
            <div class="card">
                <h3>{row['Ticker']} Log</h3>
                <p class="juice-val">${row['Juice ($)']} Juice</p>
                <p><b>Strike:</b> ${row['Strike']}</p>
                <hr>
                <b>Budget:</b> ${row['Capital Req ($)']:,}<br>
                <b>Safety:</b> {row['Cushion %']}%
            </div>
            """, unsafe_allow_html=True)
            if st.button("📈 LOG THIS TRADE"):
                st.session_state.wealth_log.append({
                    "Date": datetime.now().strftime("%Y-%m-%d"),
                    "Ticker": row['Ticker'],
                    "Juice Earned": row['Juice ($)'] * row['Contracts']
                })
                st.toast(f"Trade Logged! Wealth Building in progress.")

# -------------------------------------------------
# 6. GENERATIONAL WEALTH LOG
# -------------------------------------------------
if st.session_state.wealth_log:
    st.divider()
    st.subheader("📜 Your Generational Wealth Log")
    log_df = pd.DataFrame(st.session_state.wealth_log)
    st.table(log_df)
    total_harvest = log_df["Juice Earned"].sum()
    st.success(f"Total Wealth Harvested to Date: **${total_harvest:,.2f}**")