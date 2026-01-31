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
        vix_v = data["^VIX"].iloc[-1] if not np.isnan(data["^VIX"].iloc[-1]) else 0.0
        return spy_ch, vix_v, ("#22c55e" if spy_ch >= 0 else "#ef4444")
    except: return 0.0, 0.0, "#fff"

status_text, status_class = get_market_status()
spy_ch, v_vix, s_c = get_market_sentiment()

# -------------------------------------------------
# 3. SCANNER ENGINE (ATM Strategy Added)
# -------------------------------------------------
TICKER_MAP = {
    "Leveraged (3x/2x)": ["SOXL", "TQQQ", "TNA", "BOIL", "KOLD", "BITX", "FAS", "SPXL", "SQQQ", "UNG", "UVXY"],
    "Market ETFs": ["SPY", "QQQ", "IWM", "DIA", "VOO", "SCHD", "ARKK", "BITO"],
    "Tech & Semi": ["AMD", "INTC", "MU", "PLTR", "SOFI", "HOOD", "AFRM", "UPST", "ROKU", "NET", "AI", "GME"],
    "Finance": ["BAC", "WFC", "C", "PNC", "COF", "NU", "SQ", "PYPL", "COIN"],
    "Energy & Materials": ["OXY", "DVN", "HAL", "SLB", "FCX", "CLF", "NEM", "GOLD"],
    "Retail & Misc": ["F", "GM", "CL", "PFE", "BMY", "NKE", "SBUX", "TGT", "DIS", "WBD", "MARA", "RIOT", "AMC"]
}

def scan_ticker(t, strategy_type, min_cushion, max_days, target_type, target_val, max_price, only_positive, min_oi, income_goal):
    try:
        stock = yf.Ticker(t)
        info = stock.info
        price = info.get('currentPrice') or info.get('regularMarketPrice')
        if not price or price > max_price: return None
        
        if only_positive:
            eps, margin = info.get('forwardEps', 0), info.get('profitMargins', 0)
            if (eps is not None and eps < 0) or (margin is not None and margin < 0): return None

        for exp in stock.options[:3]:
            dte = (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days
            if 4 <= dte <= max_days:
                chain = stock.option_chain(exp)
                match = None
                
                if strategy_type == "Deep ITM Covered Call":
                    df = chain.calls[(chain.calls["strike"] < price * (1 - min_cushion/100)) & (chain.calls["openInterest"] >= min_oi)]
                    if not df.empty: match = df.sort_values("strike", ascending=False).iloc[0]
                
                elif strategy_type == "ATM (At-the-Money)":
                    # Targets the strike closest to current price
                    df = chain.calls[chain.calls["openInterest"] >= min_oi]
                    if not df.empty:
                        df["diff"] = abs(df["strike"] - price)
                        match = df.sort_values("diff").iloc[0]

                elif strategy_type == "Standard OTM Covered Call":
                    df = chain.calls[(chain.calls["strike"] > price * 1.01) & (chain.calls["openInterest"] >= min_oi)]
                    if not df.empty: match = df.sort_values("strike", ascending=True).iloc[0]
                
                elif strategy_type == "Cash Secured Put":
                    df = chain.puts[(chain.puts["strike"] < price * (1 - min_cushion/100)) & (chain.puts["openInterest"] >= min_oi)]
                    if not df.empty: match = df.sort_values("strike", ascending=False).iloc[0]

                if match is not None:
                    premium = float(match["lastPrice"])
                    intrinsic = max(0, price - float(match["strike"])) if float(match["strike"]) < price else 0
                    juice = (premium - intrinsic)
                    basis = price - premium if strategy_type != "Cash Secured Put" else float(match["strike"]) - premium
                    roi = (juice / basis) * 100
                    
                    cushion_pct = ((price - basis) / price) * 100
                    juice_per_contract = juice * 100
                    contracts_needed = int(np.ceil(income_goal / juice_per_contract)) if juice_per_contract > 0 else 0
                    
                    if target_type == "Dollar ($)" and juice_per_contract < target_val: continue
                    if target_type == "Percentage (%)" and roi < target_val: continue

                    return {
                        "Status": "🟢" if roi > 1.2 else "🟡", "Ticker": t, "Price": round(price, 2),
                        "Strike": float(match["strike"]), "Juice ($)": round(juice_per_contract, 2),
                        "ROI %": round(roi, 2), "Cushion %": round(cushion_pct, 2), "DTE": dte,
                        "Contracts": contracts_needed, "Expiry": exp, "Basis": round(basis, 2)
                    }
    except: return None

# -------------------------------------------------
# 4. INTERFACE & UI
# -------------------------------------------------
st.markdown(f"""
<div class="sentiment-bar">
    <span class="status-tag {status_class}">{status_text}</span>
    <div><b>S&P 500:</b> <span style="color:{s_c}">{spy_ch:+.2f}%</span> | <b>VIX:</b> {v_vix:.2f}</div>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.subheader("💰 Progress Tracker")
    income_goal = st.number_input("Target Goal ($)", value=2000)
    
    st.divider()
    st.subheader("🛡️ Safety Filters")
    min_cushion = st.slider("Min Cushion %", 0, 20, 5)
    max_days = st.slider("Max DTE (Days)", 7, 60, 30)
    max_stock_price = st.slider("Max Price ($)", 10, 100, 100)
    min_oi = st.number_input("Min Open Interest", value=500)
    
    st.divider()
    target_type = st.radio("Pay Goal:", ["Dollar ($)", "Percentage (%)"], horizontal=True)
    target_val = st.number_input("Value", value=50.0 if target_type == "Dollar ($)" else 1.0)
    
    sectors = st.multiselect("Sectors", options=list(TICKER_MAP.keys()), default=list(TICKER_MAP.keys()))
    strategy = st.selectbox("Strategy", ["Deep ITM Covered Call", "ATM (At-the-Money)", "Standard OTM Covered Call", "Cash Secured Put"])

# -------------------------------------------------
# 5. EXECUTION & DISPLAY
# -------------------------------------------------
if st.button("RUN GLOBAL SCAN ⚡", use_container_width=True):
    univ = []
    for s in sectors: univ.extend(TICKER_MAP[s])
    univ = list(set(univ))
    with st.spinner("Harvesting strategies..."):
        with ThreadPoolExecutor(max_workers=25) as ex:
            results = [r for r in ex.map(lambda t: scan_ticker(t, strategy, min_cushion, max_days, target_type, target_val, max_stock_price, True, min_oi, income_goal), univ) if r]
        st.session_state.results = sorted(results, key=lambda x: x['ROI %'], reverse=True)

if "results" in st.session_state and st.session_state.results:
    df = pd.DataFrame(st.session_state.results)
    display_cols = ["Status", "Ticker", "Price", "Strike", "Juice ($)", "ROI %", "Cushion %", "DTE", "Contracts"]
    sel = st.dataframe(df[display_cols], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")

    if sel.selection.rows:
        row = df.iloc[sel.selection.rows[0]]
        st.divider()
        c1, c2 = st.columns([2, 1])
        with c1:
            cid = f"tv_{row['Ticker']}"
            components.html(f'<div id="{cid}" style="height:400px; width:100%;"></div><script src="https://s3.tradingview.com/tv.js"></script><script>new TradingView.widget({{"autosize": true, "symbol": "{row["Ticker"]}", "interval": "D", "theme": "light", "style": "1", "container_id": "{cid}"}});</script>', height=420)
        with c2:
            st.markdown(f"""
            <div class="card">
                <b>{row['Ticker']} Strategy Card</b>
                <p class="juice-val">${row['Juice ($)']} Juice</p>
                <hr>
                <p><b>Cushion:</b> {row['Cushion %']}%</p>
                <p><b>DTE:</b> {row['DTE']} days</p>
                <p><b>Required:</b> {row['Contracts']} Contracts</p>
            </div>
            """, unsafe_allow_html=True)