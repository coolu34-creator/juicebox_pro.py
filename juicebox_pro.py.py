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

st.markdown("""
<style>
    .main { background-color: #f8fafc; }
    .sentiment-bar { 
        background: #1e293b; color: white; padding: 12px; 
        border-radius: 12px; margin-bottom: 20px; 
        display: flex; justify-content: space-around; font-weight: 700; 
        box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); align-items: center;
    }
    .status-tag { padding: 4px 12px; border-radius: 20px; font-size: 12px; text-transform: uppercase; }
    .status-open { background-color: #16a34a; color: white; }
    .status-closed { background-color: #dc2626; color: white; }
    .card { 
        border: 1px solid #e2e8f0; border-radius: 12px; background: white; 
        padding: 20px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); margin-bottom: 15px; 
    }
    .juice-val { color: #16a34a; font-weight: 800; font-size: 26px; margin: 0; }
    .premium-val { color: #3b82f6; font-weight: 700; font-size: 20px; margin: 0; }
    .dot { height: 12px; width: 12px; border-radius: 50%; display: inline-block; margin-right: 8px; }
    .dot-green { background-color: #16a34a; box-shadow: 0 0 10px #16a34a; }
    .dot-yellow { background-color: #facc15; box-shadow: 0 0 10px #facc15; }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# 2. MARKET DATA UTILITIES
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
        if data.empty or len(data) < 2: return 0.0, 0.0, "#fff", "#fff"
        spy_now, spy_prev = data["^GSPC"].iloc[-1], data["^GSPC"].iloc[-2]
        spy_ch = 0.0 if np.isnan(spy_now) or spy_prev == 0 else ((spy_now - spy_prev) / spy_prev) * 100
        vix_v = data["^VIX"].iloc[-1] if not np.isnan(data["^VIX"].iloc[-1]) else 0.0
        return spy_ch, vix_v, ("#22c55e" if spy_ch >= 0 else "#ef4444"), ("#ef4444" if vix_v > 22 else "#22c55e")
    except: return 0.0, 0.0, "#fff", "#fff"

status_text, status_class = get_market_status()
spy_ch, vix_v, s_c, v_c = get_market_sentiment()

# -------------------------------------------------
# 3. SCANNER ENGINE (PREMIUM & JUICE LOGIC)
# -------------------------------------------------
TICKER_MAP = {
    "Leveraged (3x/2x)": ["SOXL", "TQQQ", "TNA", "BOIL", "KOLD", "BITX", "FAS", "SPXL", "SQQQ", "UNG", "UVXY"],
    "Market ETFs": ["SPY", "QQQ", "IWM", "DIA", "VOO", "SCHD", "ARKK"],
    "Tech & Semi": ["AMD", "INTC", "MU", "PLTR", "SOFI", "HOOD", "AFRM", "UPST", "ROKU", "NET", "AI"],
    "Finance": ["BAC", "WFC", "C", "PNC", "COF", "NU", "SQ", "PYPL", "COIN"],
    "Energy & Materials": ["OXY", "DVN", "HAL", "SLB", "FCX", "CLF", "NEM", "GOLD"],
    "Retail & Misc": ["F", "GM", "CL", "PFE", "BMY", "NKE", "SBUX", "TGT", "DIS", "WBD", "MARA", "RIOT"]
}

def scan_ticker(t, strategy_type, min_cushion, max_days, target_type, target_val):
    try:
        stock = yf.Ticker(t)
        hist = stock.history(period="5d")
        if hist.empty: return None
        price = float(hist["Close"].iloc[-1])
        
        for exp in stock.options[:3]:
            days = (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days
            if 4 <= days <= max_days:
                chain = stock.option_chain(exp)
                match, premium, juice = None, 0, 0
                intrinsic = 0
                
                if strategy_type == "Deep ITM Covered Call":
                    df = chain.calls[(chain.calls["strike"] < price * (1 - min_cushion/100))]
                    if not df.empty:
                        match = df.sort_values("strike", ascending=False).iloc[0]
                        strike = float(match["strike"])
                        opt_price = float(match["lastPrice"])
                        premium = opt_price
                        intrinsic = max(0, price - strike)
                        juice = max(0, opt_price - intrinsic)
                
                elif strategy_type == "Standard OTM Covered Call":
                    df = chain.calls[(chain.calls["strike"] > price * 1.01)]
                    if not df.empty:
                        match = df.sort_values("strike", ascending=True).iloc[0]
                        premium = float(match["lastPrice"])
                        juice = premium # OTM has no intrinsic value
                
                elif strategy_type == "Cash Secured Put":
                    df = chain.puts[(chain.puts["strike"] < price * (1 - min_cushion/100))]
                    if not df.empty:
                        match = df.sort_values("strike", ascending=False).iloc[0]
                        premium = float(match["lastPrice"])
                        juice = premium

                if match is not None:
                    net_basis = price - premium if strategy_type != "Cash Secured Put" else float(match["strike"]) - premium
                    if net_basis <= 0: return None
                    
                    roi = (juice / net_basis) * 100
                    if target_type == "Dollar ($)" and (juice * 100) < target_val: continue
                    if target_type == "Percentage (%)" and roi < target_val: continue

                    return {
                        "Status": "🟢" if roi > 1.2 else "🟡", "Ticker": t, "Price": round(price, 2),
                        "Strike": float(match["strike"]), "Premium ($)": round(premium * 100, 2),
                        "Intrinsic": round(intrinsic * 100, 2), "Juice ($)": round(juice * 100, 2),
                        "ROI %": round(roi, 2), "Expiry": exp, "Net Basis": round(net_basis, 2)
                    }
    except: return None

# -------------------------------------------------
# 4. UI & SIDEBAR
# -------------------------------------------------
st.markdown(f"""
<div class="sentiment-bar">
    <span class="status-tag {status_class}">{status_text}</span>
    <span>S&P 500: <span style="color:{s_c}">{spy_ch:+.2f}%</span></span>
    <span>VIX: <span style="color:{v_c}">{vix_v:.2f}</span></span>
</div>
""", unsafe_allow_html=True)

st.title("🧃 JuiceBox Pro")

with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/box.png", width=60)
    st.subheader("💰 Monthly Tracker")
    monthly_goal = st.number_input("Goal ($)", value=2000)
    earned = st.number_input("Earned ($)", value=0)
    
    st.divider()
    target_type = st.radio("Minimum Juice Goal:", ["Dollar ($)", "Percentage (%)"], horizontal=True)
    target_val = st.number_input("Value", value=50.0 if target_type == "Dollar ($)" else 1.0)
    
    st.divider()
    all_s = list(TICKER_MAP.keys())
    sectors = st.multiselect("Sectors", options=all_s, default=all_s)
    strategy = st.selectbox("Strategy", ["Deep ITM Covered Call", "Standard OTM Covered Call", "Cash Secured Put"])
    max_days = st.slider("Days Away", 7, 45, 21)
    min_cushion = st.slider("Safety %", 0, 15, 5)

# -------------------------------------------------
# 5. RESULTS & BREAKDOWN
# -------------------------------------------------
remaining = monthly_goal - earned
st.progress(max(0, min(100, int((earned / monthly_goal) * 100))) / 100 if monthly_goal > 0 else 0)

if st.button("RUN GLOBAL SCAN ⚡", use_container_width=True):
    univ = []
    for s in sectors: univ.extend(TICKER_MAP[s])
    univ = list(set(univ))
    with st.spinner("Calculating Premiums..."):
        with ThreadPoolExecutor(max_workers=25) as ex:
            results = [r for r in ex.map(lambda t: scan_ticker(t, strategy, min_cushion, max_days, target_type, target_val), univ) if r]
        st.session_state.results = sorted(results, key=lambda x: x['ROI %'], reverse=True)

if "results" in st.session_state and st.session_state.results:
    df = pd.DataFrame(st.session_state.results)
    st.dataframe(df[["Status", "Ticker", "Price", "Strike", "Premium ($)", "Juice ($)", "ROI %", "Expiry"]], 
                 use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")

    if st.session_state.get("selection") and st.session_state.selection.rows:
        row = df.iloc[st.session_state.selection.rows[0]]
        st.divider()
        c1, c2 = st.columns([2, 1])
        with c1:
            st.write("Chart View Active")
        with c2:
            st.markdown(f"""
            <div class="card">
                <b>{row['Ticker']} PREMIUM BREAKDOWN</b>
                <p class="premium-val">Total Premium: ${row['Premium ($)']}</p>
                <hr>
                <p style="color: grey; font-size: 14px;">Intrinsic (Stock Value): ${row['Intrinsic']}</p>
                <p class="juice-val">Extrinsic (The Juice): ${row['Juice ($)']}</p>
                <hr>
                <p><b>Total Return: {row['ROI %']}%</b></p>
                <p><b>Net Cost Basis: ${row['Net Basis']}</b></p>
            </div>
            """, unsafe_allow_html=True)