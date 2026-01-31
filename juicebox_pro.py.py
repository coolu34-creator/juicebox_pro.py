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
    .dot { height: 12px; width: 12px; border-radius: 50%; display: inline-block; margin-right: 8px; }
    .dot-green { background-color: #16a34a; box-shadow: 0 0 10px #16a34a; }
    .dot-yellow { background-color: #facc15; box-shadow: 0 0 10px #facc15; }
    .dot-red { background-color: #dc2626; box-shadow: 0 0 10px #dc2626; }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# 2. MARKET DATA (AFTER-HOURS READY)
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
# 3. UI RENDERING
# -------------------------------------------------
st.markdown(f"""
<div class="sentiment-bar">
    <span class="status-tag {status_class}">{status_text}</span>
    <span>S&P 500: <span style="color:{s_c}">{spy_ch:+.2f}%</span></span>
    <span>VIX: <span style="color:{v_c}">{vix_v:.2f}</span></span>
</div>
""", unsafe_allow_html=True)

st.title("🧃 JuiceBox Pro")

# SIMPLE EXPLANATION (LEGEND)
with st.expander("📖 How This Works"):
    st.write("Think of this like renting out a house you own.")
    st.markdown("""
    * **Juice:** This is the 'Rent Money' you collect. You get to keep this as profit.
    * **Cushion:** This is your 'Safety Net.' It shows how much the price can fall before you lose money.
    * **Status Dots:** 🟢 means a great deal, 🟡 means a fair deal, and 🔴 means a small deal.
    * **Earnings:** This is like 'Report Card Day' for the stock. The price might move up or down very fast!
    """)

# -------------------------------------------------
# 4. UNIVERSE & ENGINE
# -------------------------------------------------
TICKER_MAP = {
    "Leveraged (3x/2x)": ["SOXL", "TQQQ", "TNA", "BOIL", "KOLD", "BITX", "FAS", "SPXL", "SQQQ", "UNG", "UVXY"],
    "Market ETFs": ["SPY", "QQQ", "IWM", "DIA", "VOO", "SCHD", "ARKK", "BITO"],
    "Tech & Semi": ["AMD", "INTC", "MU", "PLTR", "SOFI", "HOOD", "AFRM", "UPST", "ROKU", "PINS", "SNAP", "NET", "OKTA", "AI", "GME"],
    "Finance": ["BAC", "WFC", "C", "USB", "TFC", "PNC", "COF", "DFS", "NU", "SE", "SQ", "PYPL", "COIN"],
    "Energy & Materials": ["OXY", "DVN", "HAL", "SLB", "KMI", "WMB", "FCX", "CLF", "NEM", "GOLD", "RIG", "XOP"],
    "Retail & Misc": ["F", "GM", "CL", "K", "GIS", "PFE", "BMY", "KVUE", "NKE", "SBUX", "TGT", "DIS", "WBD", "MARA", "RIOT", "AMC"]
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
                match, juice, net_basis = None, 0, 0
                
                if strategy_type == "Deep ITM Covered Call":
                    df = chain.calls[(chain.calls["strike"] < price * (1 - min_cushion/100))]
                    if not df.empty:
                        match = df.sort_values("strike", ascending=False).iloc[0]
                        juice = max(0, float(match["lastPrice"]) - (price - float(match["strike"])))
                        net_basis = price - float(match["lastPrice"])
                elif strategy_type == "Standard OTM Covered Call":
                    df = chain.calls[(chain.calls["strike"] > price * 1.01)]
                    if not df.empty:
                        match = df.sort_values("strike", ascending=True).iloc[0]
                        juice = float(match["lastPrice"])
                        net_basis = price - juice
                elif strategy_type == "Cash Secured Put":
                    df = chain.puts[(chain.puts["strike"] < price * (1 - min_cushion/100))]
                    if not df.empty:
                        match = df.sort_values("strike", ascending=False).iloc[0]
                        juice = float(match["lastPrice"])
                        net_basis = float(match["strike"]) - juice

                if match is not None and net_basis > 0:
                    juice_dollars = juice * 100
                    roi = (juice / net_basis) * 100
                    if target_type == "Dollar ($)" and juice_dollars < target_val: continue
                    if target_type == "Percentage (%)" and roi < target_val: continue

                    dot_style = "dot-green" if roi > 1.2 else "dot-yellow" if roi > 0.5 else "dot-red"
                    return {
                        "Status": "🟢" if roi > 1.2 else "🟡" if roi > 0.5 else "🔴",
                        "Dot": dot_style, "Ticker": t, "Price": round(price, 2), 
                        "Strike": match["strike"], "Juice ($)": round(juice_dollars, 2), 
                        "ROI %": round(roi, 2), "Expiry": exp, "Net Basis": round(net_basis, 2)
                    }
    except: return None

# -------------------------------------------------
# 5. CONTROL PANEL & LEGAL
# -------------------------------------------------
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/box.png", width=60)
    st.subheader("Your Target")
    target_type = st.radio("Minimum Goal:", ["Dollar ($)", "Percentage (%)"], horizontal=True)
    target_val = st.number_input(f"Value", value=50.0 if target_type == "Dollar ($)" else 1.0)
    
    st.subheader("Settings")
    strategy = st.selectbox("Pick a Strategy", ["Deep ITM Covered Call", "Standard OTM Covered Call", "Cash Secured Put"])
    all_s = list(TICKER_MAP.keys())
    sectors = st.multiselect("Sectors", options=all_s, default=all_s)
    max_days = st.slider("Days Away", 7, 45, 21)
    min_cushion = st.slider("Safety %", 0, 15, 5)
    
    # PROFESSIONAL LEGAL TERMINOLOGY
    st.divider()
    st.error("⚖️ LEGAL DISCLAIMER")
    st.caption("""
    This application is for informational and educational purposes only. 
    It does not constitute financial, investment, or legal advice. 
    Options trading involves substantial risk of loss and is not suitable for every investor. 
    The data provided is sourced from public APIs and is not guaranteed to be accurate, 
    complete, or real-time. By using this tool, you acknowledge that you are 
    solely responsible for your own trading decisions and financial outcomes.
    """)

if st.button("RUN GLOBAL SCAN ⚡", use_container_width=True):
    univ = []
    for s in sectors: univ.extend(TICKER_MAP[s])
    univ = list(set(univ))
    with st.spinner("Finding the best deals..."):
        with ThreadPoolExecutor(max_workers=25) as ex:
            results = [r for r in ex.map(lambda t: scan_ticker(t, strategy, min_cushion, max_days, target_type, target_val), univ) if r]
        st.session_state.results = sorted(results, key=lambda x: x['ROI %'], reverse=True)

if "results" in st.session_state and st.session_state.results:
    df = pd.DataFrame(st.session_state.results)
    st.download_button("📥 Save Results (CSV)", df.to_csv(index=False).encode('utf-8'), f"Juice_{datetime.now().date()}.csv", "text/csv", use_container_width=True)
    st.dataframe(df[["Status", "Ticker", "Price", "Strike", "Juice ($)", "ROI %", "Expiry"]], use_container_width=True, hide_index=True)