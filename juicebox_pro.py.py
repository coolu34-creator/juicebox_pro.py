import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
from datetime import datetime
import numpy as np
from concurrent.futures import ThreadPoolExecutor

# -------------------------------------------------
# 1. APP SETUP & BRANDING
# -------------------------------------------------
st.set_page_config(page_title="JuiceBox Pro", page_icon="🧃", layout="wide")

st.markdown("""
<style>
    .main { background-color: #f8fafc; }
    .sentiment-bar { 
        background: #000000; color: white; padding: 15px; 
        border-radius: 15px; margin-bottom: 20px; 
        display: flex; flex-direction: column; align-items: center; gap: 8px;
    }
    .card { 
        border: 1px solid #e2e8f0; border-radius: 15px; background: white; 
        padding: 20px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); margin-bottom: 15px; 
    }
    .juice-val { color: #16a34a; font-weight: 800; font-size: 26px; margin:0; }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# 2. MARKET DATA UTILITIES
# -------------------------------------------------
def get_market_sentiment():
    try:
        data = yf.download(["^GSPC", "^VIX"], period="2d", interval="1d", progress=False)['Close']
        spy_ch = ((data["^GSPC"].iloc[-1] - data["^GSPC"].iloc[-2]) / data["^GSPC"].iloc[-2]) * 100
        vix_val = data["^VIX"].iloc[-1]
        return spy_ch, vix_val, ("#ef4444" if spy_ch < 0 else "#22c55e")
    except: return 0.0, 0.0, "#fff"

spy_ch, v_vix, s_c = get_market_sentiment()

# -------------------------------------------------
# 3. SIDEBAR: SECTORS & PRECISION FILTERS
# -------------------------------------------------
TICKER_MAP = {
    "Market ETFs": ["SPY", "QQQ", "IWM", "DIA", "SCHD", "ARKK"],
    "Tech & Semi": ["AMD", "NVDA", "AAPL", "MSFT", "PLTR", "SOFI", "AFRM", "AI"],
    "Leveraged": ["SOXL", "TQQQ", "BITX", "FAS", "SQQQ", "UVXY"],
    "Finance & Bank": ["BAC", "WFC", "C", "GS", "JPM", "COF", "PYPL", "SQ"],
    "Energy & Retail": ["OXY", "DVN", "XLE", "F", "TSLA", "MARA", "RIOT", "AMC"]
}

with st.sidebar:
    try: st.image("couple.png", use_container_width=True)
    except: st.info("Generational Wealth Mode")
    
    st.subheader("🗓️ Weekly Account Engine")
    total_acc = st.number_input("Account Value ($)", value=10000, step=1000)
    
    st.divider()
    # SECTOR FILTER
    all_sectors = list(TICKER_MAP.keys())
    selected_sectors = st.multiselect("Sectors", options=all_sectors, default=all_sectors)
    
    # Range & Safety
    price_range = st.slider("Share Price Range ($)", 0, 500, (10, 150))
    min_p, max_p = price_range
    user_cushion = st.slider("Min ITM Cushion %", 2, 25, 8) 
    max_dte = st.slider("Max DTE (Days)", 4, 15, 10)
    
    st.divider()
    risk_mode = st.select_slider("Risk Profile", options=["Conservative", "Middle Road", "Aggressive"], value="Middle Road")
    yield_map = {"Conservative": 0.0025, "Middle Road": 0.006, "Aggressive": 0.0125}
    weekly_goal = total_acc * yield_map[risk_mode]
    st.metric("Weekly Income Goal", f"${weekly_goal:,.2f}")

    strategy = st.selectbox("Strategy", ["Deep ITM Covered Call", "ATM", "Standard OTM", "Cash Secured Put"])

# -------------------------------------------------
# 4. SCANNER ENGINE
# -------------------------------------------------
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
                    "ROI %": round((juice/basis)*100, 2), "Cushion %": round(((price - basis) / price) * 100, 2), 
                    "DTE": dte, "Contracts": contracts, "Capital Req": round(price * 100 * contracts, 2)
                }
    except: return None

# -------------------------------------------------
# 5. UI DISPLAY & RESULTS
# -------------------------------------------------
st.markdown(f"""
<div class="sentiment-bar">
    <div><b>S&P 500:</b> <span style="color:{s_c}">{spy_ch:+.2f}%</span> | <b>VIX:</b> {v_vix:.2f}</div>
</div>
""", unsafe_allow_html=True)

if st.button("RUN GLOBAL SCAN ⚡", use_container_width=True):
    univ = []
    for s in selected_sectors: univ.extend(TICKER_MAP[s])
    with ThreadPoolExecutor(max_workers=15) as ex:
        results = [r for r in ex.map(lambda t: scan_ticker(t, strategy, weekly_goal, user_cushion, max_dte, min_p, max_p), list(set(univ))) if r]
    st.session_state.results = sorted(results, key=lambda x: x['ROI %'], reverse=True)

if "results" in st.session_state and st.session_state.results:
    df = pd.DataFrame(st.session_state.results)
    display_cols = ["Ticker", "Price", "Strike", "Premium ($)", "Juice ($)", "ROI %", "Cushion %", "DTE", "Contracts"]
    
    sel = st.dataframe(df[display_cols], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")

    if sel.selection.rows:
        row = df.iloc[sel.selection.rows[0]]
        st.divider()
        c1, c2 = st.columns([2, 1])
        with c1:
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
                <b>{row['Ticker']} Summary</b><br>
                <p style="color:#2563eb; font-weight:700;">Premium: ${row['Premium ($)']}</p>
                <p class="juice-val">Juice: ${row['Juice ($)']}</p>
                <hr>
                <b>Strike:</b> ${row['Strike']}<br>
                <b>Cushion:</b> {row['Cushion %']}%<br>
                <b>Time:</b> {row['DTE']} Days
            </div>
            """, unsafe_allow_html=True)