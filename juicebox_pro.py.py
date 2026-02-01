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

st.markdown("""
<style>
    .main { background-color: #f8fafc; }
    .sentiment-bar { 
        background: #000; color: #fff; padding: 15px; 
        border-radius: 15px; margin-bottom: 20px; text-align: center;
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
# 3. SIDEBAR: CONDITIONAL UI & GOALS
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
    st.subheader("💎 Fundamental Guards")
    min_margin = st.slider("Min Profit Margin (%)", -5, 50, 5)
    max_pe = st.slider("Max P/E Ratio", 5, 100, 40)
    
    st.divider()
    selected_sectors = st.multiselect("Sectors", options=list(TICKER_MAP.keys()), default=list(TICKER_MAP.keys()))
    price_range = st.slider("Price Range ($)", 0, 500, (5, 200))
    
    strategy = st.selectbox("Strategy", ["Deep ITM Covered Call", "ATM Covered Call", "Cash Secured Put"])
    
    user_cushion = 0
    if "Deep ITM" in strategy:
        user_cushion = st.slider("Min ITM Cushion %", 2, 25, 8)
    
    max_dte = st.slider("Max DTE (Days)", 4, 15, 10)
    
    st.divider()
    risk_mode = st.select_slider("Risk Profile", options=["Conservative", "Middle Road", "Aggressive"], value="Middle Road")
    yield_map = {"Conservative": 0.0025, "Middle Road": 0.006, "Aggressive": 0.0125}
    weekly_goal = total_acc * yield_map[risk_mode]
    st.metric("Weekly Income Goal", f"${weekly_goal:,.2f}")

# -------------------------------------------------
# 4. SCANNER ENGINE
# -------------------------------------------------
def scan_ticker(t, strategy_type, week_goal, cushion_limit, dte_limit, min_p, max_p, f_margin, f_pe):
    try:
        stock = yf.Ticker(t)
        info = stock.info
        
        if "ETF" not in info.get('quoteType', ''):
            margin = info.get('profitMargins', 0) * 100
            pe = info.get('trailingPE', 0)
            if margin < f_margin or (pe > f_pe and f_pe != 100): return None
        else: margin, pe = 0, 0

        price = info.get('currentPrice') or info.get('regularMarketPrice')
        if not price or not (min_p <= price <= max_p): return None

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
                    "Ticker": t, "Grade": grade, "Price": round(price, 2), "Strike": strike,
                    "Strike Date": exp, "Premium ($)": round(prem * 100, 2), 
                    "Juice ($)": round(juice * 100, 2), "ROI %": round((juice/basis)*100, 2), 
                    "Cushion %": round(cushion, 2), "DTE": dte, "Contracts": contracts
                }
    except: return None

# -------------------------------------------------
# 5. UI DISPLAY & BOLLINGER CHART
# -------------------------------------------------
st.markdown(f'<div class="sentiment-bar"><b>S&P 500:</b> <span style="color:{s_c}">{spy_ch:+.2f}%</span> | <b>VIX:</b> {v_vix:.2f}</div>', unsafe_allow_html=True)

if st.button("RUN GENERATIONAL SCAN ⚡", use_container_width=True):
    univ = []
    for s in selected_sectors: univ.extend(TICKER_MAP[s])
    with ThreadPoolExecutor(max_workers=20) as ex:
        results = [r for r in ex.map(lambda t: scan_ticker(t, strategy, weekly_goal, user_cushion, max_dte, price_range[0], price_range[1], min_margin, max_pe), list(set(univ))) if r]
    st.session_state.results = sorted(results, key=lambda x: x['ROI %'], reverse=True)

if "results" in st.session_state and st.session_state.results:
    df_res = pd.DataFrame(st.session_state.results)
    cols = ["Ticker", "Grade", "Strike Date", "Strike", "Premium ($)", "Juice ($)", "ROI %", "Cushion %", "DTE"]
    sel = st.dataframe(df_res[cols], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")

    if sel.selection.rows:
        row = df_res.iloc[sel.selection.rows[0]]
        st.divider()
        c1, c2 = st.columns([2, 1])
        with c1:
            # UPDATED: Chart with Bollinger Bands default
            components.html(f"""
                <div id="tv-chart" style="height:400px;"></div>
                <script src="https://s3.tradingview.com/tv.js"></script>
                <script>
                new TradingView.widget({{
                    "autosize": true,
                    "symbol": "{row["Ticker"]}",
                    "interval": "D",
                    "theme": "light",
                    "style": "1",
                    "container_id": "tv-chart",
                    "studies": ["BB@tv-basicstudies"]
                }});
                </script>
            """, height=420)
        with c2:
            st.markdown(f'<div class="card"><h3>{row["Ticker"]}</h3><p class="juice-val">${row["Juice ($)"]} Juice</p><hr><b>Contracts:</b> {row["Contracts"]}<br><b>Cushion:</b> {row["Cushion %"]}%</div>', unsafe_allow_html=True)
            if st.button("💾 SAVE TO WEALTH LOG"):
                st.session_state.wealth_history = pd.concat([st.session_state.wealth_history, pd.DataFrame([row])], ignore_index=True)
                st.toast("Saved!")

# -------------------------------------------------
# 6. EXPORT
# -------------------------------------------------
if not st.session_state.wealth_history.empty:
    st.divider()
    st.subheader("📜 Saved Progress")
    st.dataframe(st.session_state.wealth_history, use_container_width=True)
    st.download_button("📥 Download History CSV", st.session_state.wealth_history.to_csv(index=False).encode('utf-8'), "wealth_history.csv", "text/csv")