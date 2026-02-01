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

# Static reliable icon for sidebar branding
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
    .cap-val { color: #ef4444; font-weight: 700; font-size: 18px; margin:0; }
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

# CRITICAL FIX: Variables must exist before the UI tries to render them
spy_ch, v_vix, s_c = get_market_sentiment()
status_text, status_class = ("Market Open", "status-open") if 9 <= datetime.now().hour < 16 else ("Market Closed", "status-closed")

# -------------------------------------------------
# 3. SIDEBAR: WEEKLY GOAL ENGINE
# -------------------------------------------------
TICKER_MAP = {
    "Leveraged (3x/2x)": ["SOXL", "TQQQ", "TNA", "BITX", "FAS", "SPXL", "SQQQ", "UVXY"],
    "Market ETFs": ["SPY", "QQQ", "IWM", "DIA", "VOO", "SCHD", "ARKK"],
    "Tech & Semi": ["AMD", "INTC", "MU", "PLTR", "SOFI", "HOOD", "AFRM", "UPST", "ROKU", "NET", "AI", "GME"],
    "Finance": ["BAC", "WFC", "C", "PNC", "COF", "NU", "SQ", "PYPL", "COIN"],
    "Energy & Materials": ["OXY", "DVN", "HAL", "SLB", "FCX", "CLF", "NEM", "GOLD"],
    "Retail & Misc": ["F", "GM", "CL", "PFE", "BMY", "NKE", "SBUX", "TGT", "DIS", "WBD", "MARA", "RIOT", "AMC"]
}

with st.sidebar:
    st.image(LOGO_URL, width=100)
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
# 4. SCANNER ENGINE (Fixes KeyError)
# -------------------------------------------------
def scan_ticker(t, strategy_type, week_goal, max_p, oi_limit):
    try:
        stock = yf.Ticker(t)
        info = stock.info
        price = info.get('currentPrice') or info.get('regularMarketPrice')
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
                
                # Calculation of Contracts and Capital
                contracts = int(np.ceil(week_goal / (juice * 100))) if juice > 0 else 0
                capital_req = (price * 100) * contracts if strategy_type != "Cash Secured Put" else (float(match["strike"]) * 100) * contracts

                # These dictionary keys MUST match display_cols exactly below
                return {
                    "Ticker": t, "Juice ($)": round(juice * 100, 2), "ROI %": round((juice/basis)*100, 2),
                    "Cushion %": round(((price - basis) / price) * 100, 2), 
                    "Contracts": contracts, "Capital Req ($)": round(capital_req, 2),
                    "OI": int(match["openInterest"])
                }
    except: return None

# -------------------------------------------------
# 5. UI & CHART (Fixes SyntaxError)
# -------------------------------------------------
st.markdown(f"""
<div class="sentiment-bar">
    <span class="status-tag {status_class}">{status_text}</span>
    <div><b>S&P 500:</b> <span style="color:{s_c}">{spy_ch:+.2f}%</span> | <b>VIX:</b> {v_vix:.2f}</div>
</div>
""", unsafe_allow_html=True)

if st.button("RUN GLOBAL SCAN ⚡", use_container_width=True):
    univ = []
    for s in selected_sectors: univ.extend(TICKER_MAP[s])
    with ThreadPoolExecutor(max_workers=25) as ex:
        results = [r for r in ex.map(lambda t: scan_ticker(t, strategy, weekly_goal, max_price, min_oi), list(set(univ))) if r]
    st.session_state.results = sorted(results, key=lambda x: x['ROI %'], reverse=True)

if "results" in st.session_state and st.session_state.results:
    df = pd.DataFrame(st.session_state.results)
    
    # Fix: Matching exactly with Step 4 return keys
    display_cols = ["Ticker", "Juice ($)", "ROI %", "Cushion %", "Contracts", "Capital Req ($)"]
    
    sel = st.dataframe(df[display_cols], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")

    if sel.selection.rows:
        row = df.iloc[sel.selection.rows[0]]
        st.divider()
        c1, c2 = st.columns([2, 1])
        with c1:
            # Fix: Using triple quotes to safely embed JS without unterminated string errors
            components.html(f"""
                <div id="tv-chart" style="height:400px;"></div>
                <script src="https://s3.tradingview.com/tv.js"></script>
                <script>
                new TradingView.widget({{
                    "autosize": true, "symbol": "{row['Ticker']}", 
                    "interval": "D", "theme": "light", "style": "1", "container_id": "tv-chart"
                }});
                </script>
            """, height=420)
        with c2:
            st.markdown(f"""
            <div class="card">
                <h3>{row['Ticker']} Details</h3>
                <p class="juice-val">${row['Juice ($)']} Juice</p>
                <p class="cap-val">Required: ${row['Capital Req ($)']:,}</p>
                <hr>
                <b>Weekly Contracts:</b> {row['Contracts']}<br>
                <b>Safety Cushion:</b> {row['Cushion %']}%<br>
                <b>Liquidity:</b> {row['OI']} OI
            </div>
            """, unsafe_allow_html=True)