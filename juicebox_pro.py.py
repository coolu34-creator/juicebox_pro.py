import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
from datetime import datetime, time
import numpy as np
import pytz
from concurrent.futures import ThreadPoolExecutor

# -------------------------------------------------
# 1. PREMIUM UI & APP SETUP
# -------------------------------------------------
st.set_page_config(page_title="JuiceBox Ultra", page_icon="💎", layout="wide")

# Enhanced CSS for a "Premium" Dark/Light Mode feel
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    
    .main { background-color: #f1f5f9; }
    .stMetric { background: white; padding: 15px; border-radius: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    
    /* Premium Sentiment Bar */
    .premium-header {
        background: linear-gradient(90deg, #0f172a 0%, #334155 100%);
        color: white; padding: 20px; border-radius: 18px; margin-bottom: 25px;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
    }
    
    /* Strategy Cards */
    .card { 
        border: none; border-radius: 20px; background: white; 
        padding: 24px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05);
        border-top: 5px solid #3b82f6;
    }
    
    .juice-val { color: #059669; font-weight: 800; font-size: 32px; margin: 0; }
    .premium-badge {
        background: linear-gradient(45deg, #f59e0b, #ef4444);
        color: white; padding: 2px 8px; border-radius: 6px; font-size: 10px; font-weight: bold;
    }
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
        return "LIVE MARKET", "background-color: #22c55e;"
    return "MARKET CLOSED", "background-color: #64748b;"

def get_market_sentiment():
    try:
        data = yf.download(["^GSPC", "^VIX"], period="2d", interval="1d", progress=False)['Close']
        spy_ch = ((data["^GSPC"].iloc[-1] - data["^GSPC"].iloc[-2]) / data["^GSPC"].iloc[-2]) * 100
        vix_v = data["^VIX"].iloc[-1]
        return spy_ch, vix_v
    except: return 0.0, 0.0

spy_ch, v_vix = get_market_sentiment()
status_txt, status_style = get_market_status()

# -------------------------------------------------
# 3. PREMIUM TICKER ENGINE
# -------------------------------------------------
TICKER_MAP = {
    "Leveraged (3x/2x)": ["SOXL", "TQQQ", "BITX", "FAS", "SPXL", "SQQQ"],
    "Market ETFs": ["SPY", "QQQ", "IWM", "DIA"],
    "Tech & Semi": ["AMD", "INTC", "MU", "PLTR", "SOFI", "HOOD"],
    "Finance": ["BAC", "WFC", "NU", "SQ", "PYPL", "COIN"],
    "Premium Alpha (Subscribers Only)": ["NVDA", "TSLA", "AAPL", "MSFT", "META", "AMZN", "GOOGL"]
}

def scan_ticker(t, strategy_type, min_cushion, max_days, target_val, max_price, income_goal):
    try:
        stock = yf.Ticker(t)
        price = stock.fast_info['last_price']
        if price > max_price: return None

        # Fetch chains
        exps = stock.options[:5]
        for exp in exps:
            dte = (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days
            if 4 <= dte <= max_days:
                chain = stock.option_chain(exp)
                
                # Logic for Strategy Selection
                if "Put" in strategy_type:
                    df = chain.puts
                    match = df[df['strike'] < price * (1 - min_cushion/100)].iloc[-1]
                else:
                    df = chain.calls
                    # ATM/ITM/OTM logic simplified for speed
                    match = df.iloc[(df['strike'] - (price * 0.95)).abs().argsort()[:1]].iloc[0]

                premium = float(match['lastPrice'])
                strike = float(match['strike'])
                
                # Calculations
                juice_per_contract = premium * 100
                roi = (premium / (price if "Call" in strategy_type else strike)) * 100
                contracts_needed = int(np.ceil(income_goal / juice_per_contract)) if juice_per_contract > 0 else 0
                
                if juice_per_contract < target_val: continue

                return {
                    "Ticker": t, "Price": round(price, 2), "Strike": strike, 
                    "Juice": round(juice_per_contract, 2), "ROI": round(roi, 2), 
                    "DTE": dte, "Required": contracts_needed, "Expiry": exp
                }
    except: return None

# -------------------------------------------------
# 4. SIDEBAR & AUTH SIMULATION
# -------------------------------------------------
with st.sidebar:
    st.title("🧃 JuiceBox Ultra")
    is_premium = st.toggle("Unlock Premium Tier", value=False)
    
    if not is_premium:
        st.info("💡 Upgrade to access 'Premium Alpha' tickers like NVDA and TSLA.")
    
    st.divider()
    income_goal = st.number_input("Monthly Income Goal ($)", value=2000, step=500)
    
    st.subheader("Config")
    strategy = st.selectbox("Strategy", ["Standard Covered Call", "Cash Secured Put", "Premium Wheel"])
    max_stock_price = st.slider("Max Stock Price", 10, 500, 150)
    min_cushion = st.slider("Safety Cushion %", 0, 15, 5)
    
    selected_sectors = st.multiselect("Sectors", 
                                      options=[k for k in TICKER_MAP.keys() if "Premium" not in k or is_premium],
                                      default=["Market ETFs"])

# -------------------------------------------------
# 5. MAIN INTERFACE
# -------------------------------------------------
# Premium Header
st.markdown(f"""
<div class="premium-header">
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
            <span style="font-size: 12px; opacity: 0.8; letter-spacing: 1px;">MARKET SENTIMENT</span>
            <h2 style="margin:0;">{spy_ch:+.2f}% <span style="font-size:15px; font-weight:normal;">(S&P 500)</span></h2>
        </div>
        <div style="text-align: right;">
            <span style="{status_style} padding: 5px 12px; border-radius: 50px; font-size: 10px; font-weight: bold;">{status_txt}</span>
            <p style="margin: 5px 0 0 0; font-size: 14px;">VIX: {v_vix:.2f}</p>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)
col1.metric("Global Volatility", f"{v_vix:.1f}", "-2.4%" if v_vix < 20 else "+5.1%")
col2.metric("Income Goal", f"${income_goal:,}")
col3.metric("Premium Access", "ULTRA" if is_premium else "BASIC")

if st.button("RUN DEEP SCAN ⚡", use_container_width=True):
    univ = []
    for s in selected_sectors: univ.extend(TICKER_MAP[s])
    
    with st.spinner("Analyzing Option Chains..."):
        with ThreadPoolExecutor(max_workers=20) as ex:
            results = [r for r in ex.map(lambda t: scan_ticker(t, strategy, min_cushion, 30, 50, max_stock_price, income_goal), univ) if r]
        st.session_state.pro_results = sorted(results, key=lambda x: x['ROI'], reverse=True)

# -------------------------------------------------
# 6. RESULTS & TRADINGVIEW
# -------------------------------------------------
if "pro_results" in st.session_state and st.session_state.pro_results:
    df = pd.DataFrame(st.session_state.pro_results)
    
    # Modern Data Grid
    st.subheader("🔥 Top Harvest Opportunities")
    selected_row = st.dataframe(
        df, 
        use_container_width=True, 
        hide_index=True, 
        selection_mode="single-row", 
        on_select="rerun"
    )

    if selected_row.selection.rows:
        data = df.iloc[selected_row.selection.rows[0]]
        
        st.divider()
        c1, c2 = st.columns([2, 1])
        
        with c1:
            # High-end Charting
            st.markdown(f"### {data['Ticker']} Technical Analysis")
            cid = f"tv_{data['Ticker']}"
            components.html(f"""
                <div id="{cid}" style="height:450px;"></div>
                <script src="https://s3.tradingview.com/tv.js"></script>
                <script>
                new TradingView.widget({{
                  "autosize": true, "symbol": "{data['Ticker']}", "interval": "60",
                  "theme": "light", "style": "1", "container_id": "{cid}",
                  "hide_side_toolbar": false, "allow_symbol_change": true
                }});
                </script>
            """, height=460)
            
        with c2:
            progress = min(100, int((data['Juice'] / income_goal) * 100))
            st.markdown(f"""
            <div class="card">
                <div style="display:flex; justify-content:space-between;">
                    <span style="font-weight:bold; color:#64748b;">EXECUTION CARD</span>
                    <span class="premium-badge">PRO</span>
                </div>
                <h1 style="margin: 10px 0;">{data['Ticker']}</h1>
                <p class="juice-val">${data['Juice']}</p>
                <p style="color:#64748b; font-size:14px; margin-bottom:20px;">Premium per contract</p>
                
                <p><b>Strike Price:</b> ${data['Strike']}</p>
                <p><b>Expiring:</b> {data['Expiry']} ({data['DTE']} days)</p>
                <p><b>ROI:</b> {data['ROI']}%</p>
                <hr>
                <p style="font-size: 13px;">This trade covers <b>{progress}%</b> of your monthly goal.</p>
                <div style="background:#e2e8f0; border-radius:10px; height:8px;">
                    <div style="background:#059669; width:{progress}%; height:8px; border-radius:10px;"></div>
                </div>
                <br>
                <button style="width:100%; padding:12px; background:#0f172a; color:white; border:none; border-radius:10px; cursor:pointer;">
                    Copy Trade Details
                </button>
            </div>
            """, unsafe_allow_html=True)
else:
    st.write("Click 'Run Deep Scan' to find premium income plays.")