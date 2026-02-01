import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
from datetime import datetime
import numpy as np
from concurrent.futures import ThreadPoolExecutor

# -------------------------------------------------
# 1. APP SETUP & DATA PERSISTENCE
# -------------------------------------------------
st.set_page_config(page_title="JuiceBox Pro", page_icon="🧃", layout="wide")

# Initialize the Wealth Log in session state
if 'wealth_history' not in st.session_state:
    st.session_state.wealth_history = pd.DataFrame(columns=[
        "Date", "Ticker", "Grade", "Juice per Contract", "Contracts", "Total Juice", "Margin %", "P/E"
    ])

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
# 3. SIDEBAR: FUNDAMENTALS & WEEKLY GOALS
# -------------------------------------------------
TICKER_MAP = {
    "Leveraged": ["SOXL", "TQQQ", "BOIL", "BITX", "TNA", "FAS", "SPXL", "SQQQ", "UVXY"],
    "Tech & Semi": ["AMD", "NVDA", "AAPL", "MSFT", "PLTR", "SOFI", "AFRM", "TSLA"],
    "Market/Finance": ["SPY", "QQQ", "IWM", "BAC", "WFC", "C", "GS", "JPM", "SCHD"],
    "Energy & Retail": ["OXY", "DVN", "XLE", "HAL", "F", "GM", "PFE", "NKE", "MARA", "RIOT"]
}

with st.sidebar:
    try: st.image("couple.png", use_container_width=True)
    except: st.info("Generational Wealth Mode")
    
    st.subheader("🗓️ Weekly Account Engine")
    total_acc = st.number_input("Account Value ($)", value=10000, step=1000)
    
    st.divider()
    st.subheader("💎 Fundamental Guards")
    min_margin = st.slider("Min Profit Margin (%)", -5, 50, 5)
    max_pe = st.slider("Max P/E Ratio", 5, 100, 40)
    
    st.divider()
    selected_sectors = st.multiselect("Sectors", options=list(TICKER_MAP.keys()), default=list(TICKER_MAP.keys()))
    price_range = st.slider("Price Range ($)", 0, 500, (5, 200))
    user_cushion = st.slider("Min ITM Cushion %", 2, 25, 8) 
    
    risk_mode = st.select_slider("Risk Profile", options=["Conservative", "Middle Road", "Aggressive"], value="Middle Road")
    yield_map = {"Conservative": 0.0025, "Middle Road": 0.006, "Aggressive": 0.0125}
    weekly_goal = total_acc * yield_map[risk_mode]
    st.metric("Weekly Income Goal", f"${weekly_goal:,.2f}")

# -------------------------------------------------
# 4. SCANNER ENGINE (Fundamentals & Grading)
# -------------------------------------------------
def scan_ticker(t, strategy_type, week_goal, cushion_limit, min_p, max_p, f_margin, f_pe):
    try:
        stock = yf.Ticker(t)
        info = stock.info
        
        # Fundamental Filter
        if "ETF" not in info.get('quoteType', ''):
            margin = info.get('profitMargins', 0) * 100
            pe = info.get('trailingPE', 0)
            if margin < f_margin or (pe > f_pe and f_pe != 100): return None
        else: margin, pe = 0, 0

        price = info.get('currentPrice') or info.get('regularMarketPrice')
        if not price or not (min_p <= price <= max_p): return None

        for exp in stock.options[:3]:
            dte = (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days
            if 4 <= dte <= 12:
                chain = stock.option_chain(exp)
                df = chain.calls # Defaulting to Covered Calls for Wealth Strategy
                df = df[df["openInterest"] >= 200]
                if df.empty: continue
                
                match_df = df[df["strike"] < price * (1 - (cushion_limit / 100))]
                if match_df.empty: continue
                match = match_df.sort_values("strike", ascending=False).iloc[0]

                prem = float(match["lastPrice"])
                strike = float(match["strike"])
                juice = (prem - max(0, price - strike))
                basis = price - prem
                cushion = ((price - basis) / price) * 100
                roi = (juice / basis) * 100
                contracts = int(np.ceil(week_goal / (juice * 100))) if juice > 0 else 0

                if cushion > 12 and roi > 0.4: grade = "🟢 A"
                elif cushion > 7: grade = "🟡 B"
                else: grade = "🔴 C"

                return {
                    "Ticker": t, "Grade": grade, "Margin %": round(margin, 1), "P/E": round(pe, 1),
                    "Strike Date": exp, "Strike": strike, "Juice ($)": round(juice * 100, 2), 
                    "ROI %": round(roi, 2), "Cushion %": round(cushion, 2), "DTE": dte, "Contracts": contracts
                }
    except: return None

# -------------------------------------------------
# 5. UI DISPLAY & SAVE PROCESS
# -------------------------------------------------
st.markdown(f"""
<div class="sentiment-bar">
    <div><b>S&P 500:</b> <span style="color:{s_c}">{spy_ch:+.2f}%</span> | <b>VIX:</b> {v_vix:.2f}</div>
</div>
""", unsafe_allow_html=True)

if st.button("RUN GLOBAL SCAN ⚡", use_container_width=True):
    univ = []
    for s in selected_sectors: univ.extend(TICKER_MAP[s])
    with ThreadPoolExecutor(max_workers=20) as ex:
        results = [r for r in ex.map(lambda t: scan_ticker(t, "ITM", weekly_goal, user_cushion, price_range[0], price_range[1], min_margin, max_pe), list(set(univ))) if r]
    st.session_state.results = sorted(results, key=lambda x: x['ROI %'], reverse=True)

if "results" in st.session_state and st.session_state.results:
    df_res = pd.DataFrame(st.session_state.results)
    sel = st.dataframe(df_res, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")

    if sel.selection.rows:
        row = df_res.iloc[sel.selection.rows[0]]
        st.divider()
        c1, c2 = st.columns([2, 1])
        with c1:
            components.html(f'<div id="tv" style="height:400px;"></div><script src="https://s3.tradingview.com/tv.js"></script><script>new TradingView.widget({{"autosize": true, "symbol": "{row["Ticker"]}", "interval": "D", "theme": "light", "style": "1", "container_id": "tv"}});</script>', height=420)
        with c2:
            st.markdown(f'<div class="card"><h3>{row["Ticker"]}</h3><p class="juice-val">${row["Juice ($)"]} Juice</p><hr><b>Grade:</b> {row["Grade"]}<br><b>Margin:</b> {row["Margin %"]}%</div>', unsafe_allow_html=True)
            
            # SAVE PROCESS BUTTON
            if st.button("💾 SAVE TO WEALTH LOG"):
                new_entry = pd.DataFrame([{
                    "Date": datetime.now().strftime("%Y-%m-%d"),
                    "Ticker": row["Ticker"], "Grade": row["Grade"],
                    "Juice per Contract": row["Juice ($)"], "Contracts": row["Contracts"],
                    "Total Juice": row["Juice ($)"] * row["Contracts"],
                    "Margin %": row["Margin %"], "P/E": row["P/E"]
                }])
                st.session_state.wealth_history = pd.concat([st.session_state.wealth_history, new_entry], ignore_index=True)
                st.success("Trade Saved Successfully!")

# -------------------------------------------------
# 6. THE WEALTH HISTORY (SAVEABLE PROGRESS)
# -------------------------------------------------
if not st.session_state.wealth_history.empty:
    st.divider()
    st.subheader("📜 Your Saved Progress")
    st.dataframe(st.session_state.wealth_history, use_container_width=True, hide_index=True)
    
    # DOWNLOAD PROGRESS
    csv = st.session_state.wealth_history.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download Wealth History CSV",
        data=csv,
        file_name=f"JuiceBox_Legacy_{datetime.now().strftime('%Y%m%d')}.csv",
        mime='text/csv',
    )