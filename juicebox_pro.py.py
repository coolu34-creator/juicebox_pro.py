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
    .juice-val { color: #16a34a; font-weight: 800; font-size: 26px; }
    .projection-val { color: #3b82f6; font-weight: 800; font-size: 22px; }
</style>
""", unsafe_allow_html=True)

# Session State for tracking
if 'total_earned' not in st.session_state: st.session_state.total_earned = 0.0

# -------------------------------------------------
# 2. MARKET DATA UTILITIES (Fixes NameError)
# -------------------------------------------------
def get_market_status():
    tz = pytz.timezone('America/New_York')
    now = datetime.now(tz)
    is_weekday = now.weekday() < 5
    m_open, m_close = time(9, 30), time(16, 0)
    if is_weekday and m_open <= now.time() <= m_close:
        return "Market Open", "status-open"
    return "Market Closed", "status-closed"

def get_market_sentiment():
    try:
        data = yf.download(["^GSPC", "^VIX"], period="5d", interval="1d", progress=False)['Close']
        if data.empty or len(data) < 2: return 0.0, 0.0, "#fff"
        spy_now, spy_prev = data["^GSPC"].iloc[-1], data["^GSPC"].iloc[-2]
        spy_ch = 0.0 if np.isnan(spy_now) or spy_prev == 0 else ((spy_now - spy_prev) / spy_prev) * 100
        vix_val = data["^VIX"].iloc[-1] if not np.isnan(data["^VIX"].iloc[-1]) else 0.0
        return spy_ch, vix_val, ("#22c55e" if spy_ch >= 0 else "#ef4444")
    except: return 0.0, 0.0, "#fff"

status_text, status_class = get_market_status()
spy_ch, v_vix, s_c = get_market_sentiment()

# -------------------------------------------------
# 3. SCANNER ENGINE (Affordability & Projection Logic)
# -------------------------------------------------
TICKER_MAP = {
    "Leveraged (3x/2x)": ["SOXL", "TQQQ", "TNA", "BOIL", "KOLD", "BITX", "FAS", "SPXL", "SQQQ", "UNG", "UVXY"],
    "Market ETFs": ["SPY", "QQQ", "IWM", "DIA", "VOO", "SCHD", "ARKK", "BITO"],
    "Tech & Semi": ["AMD", "INTC", "MU", "PLTR", "SOFI", "HOOD", "AFRM", "UPST", "ROKU", "NET", "AI", "GME"],
    "Finance": ["BAC", "WFC", "C", "PNC", "COF", "NU", "SQ", "PYPL", "COIN"],
    "Energy & Materials": ["OXY", "DVN", "HAL", "SLB", "FCX", "CLF", "NEM", "GOLD"],
    "Retail & Misc": ["F", "GM", "CL", "PFE", "BMY", "NKE", "SBUX", "TGT", "DIS", "WBD", "MARA", "RIOT", "AMC"]
}

def scan_ticker(t, strategy_type, min_cushion, max_days, target_type, target_val, max_price, min_oi, account_balance):
    try:
        stock = yf.Ticker(t)
        price = stock.fast_info['lastPrice']
        
        # Affordability Check: Must afford at least 1 contract (100 shares)
        if (price * 100) > account_balance: return None
        if price > max_price: return None

        for exp in stock.options[:3]:
            dte = (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days
            if 4 <= dte <= max_days:
                chain = stock.option_chain(exp)
                match = None
                
                # Logic for ATM / ITM / Put
                if strategy_type == "Deep ITM Covered Call":
                    df = chain.calls[(chain.calls["strike"] < price * (1 - min_cushion/100)) & (chain.calls["openInterest"] >= min_oi)]
                    if not df.empty: match = df.sort_values("strike", ascending=False).iloc[0]
                elif strategy_type == "ATM (At-the-Money)":
                    df = chain.calls[chain.calls["openInterest"] >= min_oi]
                    if not df.empty:
                        df["diff"] = abs(df["strike"] - price)
                        match = df.sort_values("diff").iloc[0]
                elif strategy_type == "Cash Secured Put":
                    df = chain.puts[(chain.puts["strike"] < price * (1 - min_cushion/100)) & (chain.puts["openInterest"] >= min_oi)]
                    if not df.empty: match = df.sort_values("strike", ascending=False).iloc[0]

                if match is not None:
                    premium = float(match["lastPrice"])
                    intrinsic = max(0, price - float(match["strike"])) if float(match["strike"]) < price else 0
                    juice = (premium - intrinsic)
                    basis = price - premium if strategy_type != "Cash Secured Put" else float(match["strike"]) - premium
                    
                    # Purchasing Power Calculation
                    cost_per_contract = basis * 100
                    max_contracts = int(account_balance // cost_per_contract)
                    total_juice_projection = (juice * 100) * max_contracts
                    roi = (juice / basis) * 100
                    
                    if max_contracts == 0: return None
                    if target_type == "Dollar ($)" and total_juice_projection < target_val: continue
                    if target_type == "Percentage (%)" and roi < target_val: continue

                    return {
                        "Status": "🟢" if roi > 1.2 else "🟡", "Ticker": t, "Price": round(price, 2),
                        "Strike": float(match["strike"]), "Can Afford": f"{max_contracts} Contracts",
                        "Total Juice ($)": round(total_juice_projection, 2), "ROI %": round(roi, 2),
                        "Basis": round(basis, 2), "DTE": dte
                    }
    except: return None

# -------------------------------------------------
# 4. MOBILE INTERFACE
# -------------------------------------------------
st.markdown(f"""
<div class="sentiment-bar">
    <span class="status-tag {status_class}">{status_text}</span>
    <div><b>S&P 500:</b> <span style="color:{s_c}">{spy_ch:+.2f}%</span> | <b>VIX:</b> {v_vix:.2f}</div>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.subheader("🏦 Client Affordability")
    account_balance = st.number_input("Account Balance ($)", value=10000, step=1000)
    
    st.divider()
    st.subheader("🛡️ Safety Filters")
    min_cushion = st.slider("Min Safety Cushion %", 0, 20, 5)
    max_days = st.slider("Max Days (DTE)", 7, 60, 30)
    min_oi = st.number_input("Min Open Interest", value=500)
    
    st.divider()
    st.subheader("🎯 Pay Goal")
    target_type = st.radio("Minimum I must make:", ["Dollar ($)", "Percentage (%)"], horizontal=True)
    target_val = st.number_input("Value", value=100.0 if target_type == "Dollar ($)" else 1.0)
    
    sectors = st.multiselect("Sectors", options=list(TICKER_MAP.keys()), default=list(TICKER_MAP.keys()))
    strategy = st.selectbox("Strategy", ["Deep ITM Covered Call", "ATM (At-the-Money)", "Cash Secured Put"])

# -------------------------------------------------
# 5. EXECUTION & PROJECTION
# -------------------------------------------------
if st.button("RUN ADVISORY SCAN ⚡", use_container_width=True):
    univ = []
    for s in sectors: univ.extend(TICKER_MAP[s])
    univ = list(set(univ))
    with st.spinner(f"Finding what you can afford with ${account_balance}..."):
        with ThreadPoolExecutor(max_workers=25) as ex:
            results = [r for r in ex.map(lambda t: scan_ticker(t, strategy, min_cushion, max_days, target_type, target_val, 100, min_oi, account_balance), univ) if r]
        st.session_state.results = sorted(results, key=lambda x: x['Total Juice ($)'], reverse=True)

if "results" in st.session_state and st.session_state.results:
    df = pd.DataFrame(st.session_state.results)
    st.dataframe(df[["Status", "Ticker", "Can Afford", "Total Juice ($)", "ROI %", "Price", "Basis", "DTE"]], 
                 use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")

    if st.session_state.get("selection") and st.session_state.selection.rows:
        row = df.iloc[st.session_state.selection.rows[0]]
        st.markdown(f"""
        <div class="card">
            <b>{row['Ticker']} Advisory Report</b>
            <p>Based on your ${account_balance} balance:</p>
            <p class="projection-val">You can make ${row['Total Juice ($)']} Juice</p>
            <hr>
            <p><b>Quantity:</b> {row['Can Afford']}</p>
            <p><b>Cost to Open:</b> ${round(row['Basis'] * 100, 2)} per contract</p>
        </div>
        """, unsafe_allow_html=True)