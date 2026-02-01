import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
from datetime import datetime
import numpy as np
from concurrent.futures import ThreadPoolExecutor

# -------------------------------------------------
# 1. APP SETUP & PERSISTENCE
# -------------------------------------------------
st.set_page_config(page_title="JuiceBox Pro", page_icon="🧃", layout="wide")

if 'wealth_history' not in st.session_state:
    st.session_state.wealth_history = pd.DataFrame(columns=[
        "Date", "Ticker", "Grade", "Juice ($)", "Contracts", "Total Juice", "Cushion %"
    ])

# -------------------------------------------------
# 2. MARKET DATA & BOLLINGER CALCULATION
# -------------------------------------------------
def get_bollinger_status(ticker):
    try:
        data = yf.download(ticker, period="30d", interval="1d", progress=False)
        if data.empty: return "N/A"
        
        # Calculate Bollinger Bands (20-day SMA, 2 Std Dev)
        sma = data['Close'].rolling(window=20).mean()
        std = data['Close'].rolling(window=20).std()
        upper_bb = sma + (std * 2)
        lower_bb = sma - (std * 2)
        
        curr_price = data['Close'].iloc[-1]
        
        if curr_price <= lower_bb.iloc[-1]: return "🔵 Oversold (Bottom)"
        if curr_price >= upper_bb.iloc[-1]: return "🟠 Overbought (Top)"
        return "⚪ Neutral"
    except: return "N/A"

def get_market_sentiment():
    try:
        data = yf.download(["^GSPC", "^VIX"], period="2d", interval="1d", progress=False)['Close']
        spy_ch = ((data["^GSPC"].iloc[-1] - data["^GSPC"].iloc[-2]) / data["^GSPC"].iloc[-2]) * 100
        vix_val = data["^VIX"].iloc[-1]
        return spy_ch, vix_val, ("#ef4444" if spy_ch < 0 else "#22c55e")
    except: return 0.0, 0.0, "#fff"

spy_ch, v_vix, s_c = get_market_sentiment()

# -------------------------------------------------
# 3. SIDEBAR: STRATEGY & FILTERS
# -------------------------------------------------
TICKER_MAP = {
    "Leveraged (3x/2x)": ["SOXL", "TQQQ", "BOIL", "BITX", "TNA", "FAS", "SPXL", "SQQQ", "UVXY"],
    "Tech & Semi": ["AMD", "NVDA", "AAPL", "MSFT", "PLTR", "SOFI", "AFRM", "TSLA", "INTC"],
    "Market/Finance": ["SPY", "QQQ", "IWM", "BAC", "WFC", "C", "GS", "JPM", "SCHD"],
    "Energy & Retail": ["OXY", "DVN", "XLE", "HAL", "F", "GM", "PFE", "NKE", "MARA", "RIOT"]
}

with st.sidebar:
    try: st.image("couple.png", use_container_width=True)
    except: st.info("Generational Wealth Mode")
    
    st.subheader("🗓️ Weekly Account Engine")
    total_acc = st.number_input("Account Value ($)", value=10000, step=1000)
    
    st.divider()
    selected_sectors = st.multiselect("Sectors", options=list(TICKER_MAP.keys()), default=list(TICKER_MAP.keys()))
    price_range = st.slider("Price Range ($)", 0, 500, (5, 200))
    
    strategy = st.selectbox("Strategy", ["Deep ITM Covered Call", "ATM Covered Call", "Cash Secured Put"])
    user_cushion = st.slider("Min ITM Cushion %", 2, 25, 8) if "Deep ITM" in strategy else 0
    max_dte = st.slider("Max DTE (Days)", 4, 15, 10)
    
    st.divider()
    risk_mode = st.select_slider("Risk Profile", options=["Conservative", "Middle Road", "Aggressive"], value="Middle Road")
    yield_map = {"Conservative": 0.0025, "Middle Road": 0.006, "Aggressive": 0.0125}
    weekly_goal = total_acc * yield_map[risk_mode]
    st.metric("Weekly Income Goal", f"${weekly_goal:,.2f}")

# -------------------------------------------------
# 4. SCANNER ENGINE (With Bollinger Logic)
# -------------------------------------------------
def scan_ticker(t, strategy_type, week_goal, cushion_limit, dte_limit, min_p, max_p):
    try:
        stock = yf.Ticker(t)
        price = stock.fast_info['last_price']
        if not price or not (min_p <= price <= max_p): return None

        # Technical Alert
        bb_status = get_bollinger_status(t)

        for exp in stock.options[:3]:
            dte = (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days
            if 4 <= dte <= dte_limit:
                chain = stock.option_chain(exp)
                df = chain.puts if "Put" in strategy_type else chain.calls
                df = df[df["openInterest"] >= 200]
                if df.empty: continue
                
                if "Deep ITM" in strategy_type:
                    match_df = df[df["strike"] < price * (1 - (cushion_limit / 100))]
                    if match_df.empty: continue
                    match = match_df.sort_values("strike", ascending=False).iloc[0]
                elif "ATM" in strategy_type:
                    df["diff"] = abs(df["strike"] - price)
                    match = df.sort_values("diff").iloc[0]
                else: 
                    match_df = df[df["strike"] < price]
                    if match_df.empty: continue
                    match = match_df.sort_values("strike", ascending=False).iloc[0]

                prem = float(match["lastPrice"])
                strike = float(match["strike"])
                juice = (prem - max(0, price - strike)) if "Call" in strategy_type else prem
                basis = price - prem
                cushion = ((price - basis) / price) * 100 if "Call" in strategy_type else ((price - strike) / price) * 100
                contracts = int(np.ceil(week_goal / (juice * 100))) if juice > 0 else 0

                grade = "🟢 A" if cushion > 12 else "🟡 B" if cushion > 7 else "🔴 C"

                return {
                    "Ticker": t, "BB Alert": bb_status, "Grade": grade, "Price": round(price, 2), 
                    "Strike": strike, "Strike Date": exp, "Juice ($)": round(juice * 100, 2), 
                    "ROI %": round((juice/basis)*100, 2), "Cushion %": round(cushion, 2), 
                    "DTE": dte, "Contracts": contracts
                }
    except: return None

# -------------------------------------------------
# 5. UI DISPLAY
# -------------------------------------------------
st.markdown(f'<div style="background:#000; color:#fff; padding:15px; border-radius:15px; text-align:center;">'
            f'<b>S&P 500:</b> <span style="color:{s_c}">{spy_ch:+.2f}%</span> | <b>VIX:</b> {v_vix:.2f}</div>', unsafe_allow_html=True)

if st.button("RUN TECHNICAL SCAN ⚡", use_container_width=True):
    univ = []
    for s in selected_sectors: univ.extend(TICKER_MAP[s])
    with ThreadPoolExecutor(max_workers=20) as ex:
        results = [r for r in ex.map(lambda t: scan_ticker(t, strategy, weekly_goal, user_cushion, max_dte, price_range[0], price_range[1]), list(set(univ))) if r]
    st.session_state.results = sorted(results, key=lambda x: x['ROI %'], reverse=True)

if "results" in st.session_state and st.session_state.results:
    df_res = pd.DataFrame(st.session_state.results)
    cols = ["Ticker", "BB Alert", "Grade", "Strike Date", "Strike", "Juice ($)", "ROI %", "Cushion %", "DTE"]
    sel = st.dataframe(df_res[cols], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")

    if sel.selection.rows:
        row = df_res.iloc[sel.selection.rows[0]]
        st.divider()
        c1, c2 = st.columns([2, 1])
        with c1:
            components.html(f"""
                <div id="tv-chart" style="height:400px;"></div>
                <script src="https://s3.tradingview.com/tv.js"></script>
                <script>
                new TradingView.widget({{
                    "autosize": true, "symbol": "{row["Ticker"]}", "interval": "D", "theme": "light", "style": "1", 
                    "container_id": "tv-chart", "studies": ["BB@tv-basicstudies"]
                }});
                </script>
            """, height=420)
        with c2:
            st.markdown(f'<div style="border: 1px solid #e2e8f0; border-radius: 15px; padding: 20px;">'
                        f'<h3>{row["Ticker"]}</h3><h4>{row["BB Alert"]}</h4><hr>'
                        f'<p style="color:#16a34a; font-size:24px; font-weight:800;">Juice: ${row["Juice ($)"]}</p>'
                        f'<b>Cushion:</b> {row["Cushion %"]}%</div>', unsafe_allow_html=True)