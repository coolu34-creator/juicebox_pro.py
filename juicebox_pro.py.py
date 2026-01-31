import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
from datetime import datetime, time
import numpy as np
import pytz
from concurrent.futures import ThreadPoolExecutor

# -------------------------------------------------
# 1. MOBILE APP SETUP
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
</style>
""", unsafe_allow_html=True)

if 'total_earned' not in st.session_state: st.session_state.total_earned = 0.0

# -------------------------------------------------
# 2. DATA UTILITIES
# -------------------------------------------------
def get_market_sentiment():
    try:
        data = yf.download(["^GSPC", "^VIX"], period="5d", interval="1d", progress=False)['Close']
        if data.empty: return 0.0, 0.0, "#fff"
        spy_ch = ((data["^GSPC"].iloc[-1] - data["^GSPC"].iloc[-2]) / data["^GSPC"].iloc[-2]) * 100
        v_vix = data["^VIX"].iloc[-1]
        return spy_ch, v_vix, ("#22c55e" if spy_ch >= 0 else "#ef4444")
    except: return 0.0, 0.0, "#fff"

spy_ch, v_vix, s_c = get_market_sentiment()
status_text, status_class = ("Market Open", "status-open") if 9 <= datetime.now().hour < 16 else ("Market Closed", "status-closed")

# -------------------------------------------------
# 3. SIDEBAR & FEASIBILITY CHECK
# -------------------------------------------------
with st.sidebar:
    st.subheader("💰 Feasibility Tracker")
    total_capital = st.number_input("Total Trading Capital ($)", value=10000)
    income_goal = st.number_input("Monthly Income Goal ($)", value=200)
    
    # Feasibility Logic
    yield_req = (income_goal / total_capital) * 100 if total_capital > 0 else 0
    if yield_req <= 2.0:
        st.success(f"Feasible: Targets {yield_req:.1f}% monthly yield.")
    elif yield_req <= 5.0:
        st.warning(f"Aggressive: Targets {yield_req:.1f}% monthly yield.")
    else:
        st.error(f"High Risk: Targets {yield_req:.1f}% monthly yield.")

    st.divider()
    max_price = st.slider("Max Stock Price", 10, 100, 100)
    min_oi = st.number_input("Min Open Interest", value=500)
    strategy = st.selectbox("Strategy", ["Deep ITM Covered Call", "ATM (At-the-Money)", "Standard OTM Covered Call", "Cash Secured Put"])

# -------------------------------------------------
# 4. SCANNER LOGIC
# -------------------------------------------------
TICKER_MAP = {
    "Leveraged (3x/2x)": ["SOXL", "TQQQ", "TNA", "BITX", "FAS", "SPXL", "SQQQ", "UVXY"],
    "Market ETFs": ["SPY", "QQQ", "IWM", "DIA", "VOO", "SCHD", "BITO"],
    "Tech & Semi": ["AMD", "INTC", "MU", "PLTR", "SOFI", "HOOD", "AFRM", "UPST", "ROKU", "NET", "AI", "GME"],
    "Finance": ["BAC", "WFC", "C", "NU", "SQ", "PYPL", "COIN"],
    "Energy & Materials": ["OXY", "DVN", "HAL", "SLB", "FCX", "CLF", "NEM", "GOLD"],
    "Retail & Misc": ["F", "GM", "CL", "PFE", "BMY", "NKE", "SBUX", "TGT", "DIS", "WBD", "MARA", "RIOT", "AMC"]
}

def scan_ticker(t, strategy_type, income_goal, max_p, oi_limit):
    try:
        stock = yf.Ticker(t)
        info = stock.info
        price = info.get('currentPrice') or info.get('regularMarketPrice')
        if not price or price > max_p: return None
        
        # Fundamental Filter: Must have positive profit margin
        if info.get('profitMargins', 0) <= 0: return None

        for exp in stock.options[:2]:
            dte = (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days
            if 4 <= dte <= 45:
                chain = stock.option_chain(exp)
                df = chain.calls if strategy_type != "Cash Secured Put" else chain.puts
                df = df[df["openInterest"] >= oi_limit]
                
                if df.empty: continue
                
                # Selection Logic
                if strategy_type == "Deep ITM Covered Call":
                    match = df[df["strike"] < price * 0.90].sort_values("strike", ascending=False).iloc[0]
                elif strategy_type == "ATM (At-the-Money)":
                    df["diff"] = abs(df["strike"] - price)
                    match = df.sort_values("diff").iloc[0]
                else:
                    match = df.iloc[0] # Default placeholder for OTM/Put logic
                
                premium = float(match["lastPrice"])
                intrinsic = max(0, price - float(match["strike"])) if float(match["strike"]) < price else 0
                juice = (premium - intrinsic)
                basis = price - premium
                roi = (juice / basis) * 100
                
                juice_total = juice * 100
                contracts = int(np.ceil(income_goal / juice_total)) if juice_total > 0 else 0
                
                return {
                    "Ticker": t, "Price": round(price, 2), "Strike": match["strike"],
                    "Juice ($)": round(juice_total, 2), "ROI %": round(roi, 2),
                    "Contracts": contracts, "DTE": dte, "Status": "🟢" if roi > 1 else "🟡"
                }
    except: return None

# -------------------------------------------------
# 5. UI DISPLAY
# -------------------------------------------------
st.markdown(f"""
<div class="sentiment-bar">
    <span class="status-tag {status_class}">{status_text}</span>
    <div><b>S&P 500:</b> <span style="color:{s_c}">{spy_ch:+.2f}%</span> | <b>VIX:</b> {v_vix:.2f}</div>
</div>
""", unsafe_allow_html=True)

if st.button("RUN SCAN ⚡", use_container_width=True):
    univ = []
    for s in TICKER_MAP.values(): univ.extend(s)
    with ThreadPoolExecutor(max_workers=20) as ex:
        results = [r for r in ex.map(lambda t: scan_ticker(t, strategy, income_goal, max_price, min_oi), list(set(univ))) if r]
    st.session_state.results = sorted(results, key=lambda x: x['ROI %'], reverse=True)

if "results" in st.session_state and st.session_state.results:
    df = pd.DataFrame(st.session_state.results)
    st.dataframe(df, use_container_width=True, hide_index=True)