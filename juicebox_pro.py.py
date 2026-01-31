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
</style>
""", unsafe_allow_html=True)

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
# 3. SIDEBAR: ACCOUNT MODES & FEASIBILITY
# -------------------------------------------------
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/box.png", width=60)
    st.subheader("💰 Account Engine")
    
    total_capital = st.number_input("Total Account Value ($)", value=10000, step=1000)
    
    # RISK MODE SELECTION
    risk_mode = st.select_slider(
        "Select Risk Profile",
        options=["Conservative", "Middle Road", "Aggressive"],
        value="Conservative"
    )
    
    # Calculate feasible goal based on account size
    if risk_mode == "Conservative":
        target_yield = 0.01  # 1% per month
        st.info("Goal: 1% Yield. Prioritizes Deep ITM cushion.")
    elif risk_mode == "Middle Road":
        target_yield = 0.025 # 2.5% per month
        st.warning("Goal: 2.5% Yield. Balanced safety and profit.")
    else:
        target_yield = 0.05  # 5% per month
        st.error("Goal: 5% Yield. High risk, lower safety cushion.")
    
    income_goal = total_capital * target_yield
    st.metric("Monthly Income Goal", f"${income_goal:,.2f}")

    st.divider()
    st.subheader("🛡️ Liquidity & Safety")
    min_oi = st.number_input("Min Open Interest", value=500)
    max_price = st.slider("Max Stock Price ($)", 10, 100, 100)
    
    st.divider()
    strategy = st.selectbox("Strategy", ["Deep ITM Covered Call", "ATM (At-the-Money)", "Standard OTM Covered Call", "Cash Secured Put"])

# -------------------------------------------------
# 4. SCANNER ENGINE (Contracts based on Account Goal)
# -------------------------------------------------
TICKER_MAP = {
    "Leveraged (3x/2x)": ["SOXL", "TQQQ", "TNA", "BOIL", "KOLD", "BITX", "FAS", "SPXL", "SQQQ", "UNG", "UVXY"],
    "Market ETFs": ["SPY", "QQQ", "IWM", "DIA", "VOO", "SCHD", "ARKK", "BITO"],
    "Tech & Semi": ["AMD", "INTC", "MU", "PLTR", "SOFI", "HOOD", "AFRM", "UPST", "ROKU", "NET", "AI", "GME"],
    "Finance": ["BAC", "WFC", "C", "PNC", "COF", "NU", "SQ", "PYPL", "COIN"],
    "Energy & Materials": ["OXY", "DVN", "HAL", "SLB", "FCX", "CLF", "NEM", "GOLD"],
    "Retail & Misc": ["F", "GM", "CL", "PFE", "BMY", "NKE", "SBUX", "TGT", "DIS", "WBD", "MARA", "RIOT", "AMC"]
}

def scan_ticker(t, strategy_type, income_goal, max_p, oi_limit):
    try:
        stock = yf.Ticker(t)
        info = stock.info
        price = info.get('currentPrice') or info.get('regularMarketPrice')
        if not price or price > max_p: return None
        
        # Fundamental Filter
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
                    match_df = df[df["strike"] < price * 0.90]
                    if match_df.empty: continue
                    match = match_df.sort_values("strike", ascending=False).iloc[0]
                elif strategy_type == "ATM (At-the-Money)":
                    df["diff"] = abs(df["strike"] - price)
                    match = df.sort_values("diff").iloc[0]
                else:
                    match = df.iloc[0]

                premium = float(match["lastPrice"])
                intrinsic = max(0, price - float(match["strike"])) if float(match["strike"]) < price else 0
                juice = (premium - intrinsic)
                basis = price - premium
                roi = (juice / basis) * 100
                
                # Contracts Needed Calculation
                juice_per_contract = juice * 100
                contracts_needed = int(np.ceil(income_goal / juice_per_contract)) if juice_per_contract > 0 else 0
                
                # Safety Cushion %
                cushion_pct = ((price - basis) / price) * 100

                return {
                    "Ticker": t, "Price": round(price, 2), "Strike": float(match["strike"]),
                    "Juice ($)": round(juice_per_contract, 2), "ROI %": round(roi, 2),
                    "Cushion %": round(cushion_pct, 2), "Contracts": contracts_needed, 
                    "DTE": dte, "Expiry": exp, "Basis": round(basis, 2)
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

if st.button("RUN ACCOUNT SCAN ⚡", use_container_width=True):
    univ = []
    for s in TICKER_MAP.values(): univ.extend(s)
    with ThreadPoolExecutor(max_workers=20) as ex:
        results = [r for r in ex.map(lambda t: scan_ticker(t, strategy, income_goal, max_price, min_oi), list(set(univ))) if r]
    st.session_state.results = sorted(results, key=lambda x: x['ROI %'], reverse=True)

if "results" in st.session_state and st.session_state.results:
    df = pd.DataFrame(st.session_state.results)
    st.dataframe(df[["Ticker", "Price", "Strike", "Juice ($)", "ROI %", "Cushion %", "Contracts", "DTE"]], 
                 use_container_width=True, hide_index=True)