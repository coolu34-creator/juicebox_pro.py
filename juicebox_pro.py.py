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
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# 2. MARKET DATA UTILITIES (Fixes NameError & nan%)
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
        # Fetch data for Sentiment Bar
        data = yf.download(["^GSPC", "^VIX"], period="5d", interval="1d", progress=False)['Close']
        if data.empty or len(data) < 2:
            return 0.0, 0.0, "#fff", "#fff"
        
        spy_now = data["^GSPC"].iloc[-1]
        spy_prev = data["^GSPC"].iloc[-2]
        
        # Clean calculation to avoid nan
        if np.isnan(spy_now) or np.isnan(spy_prev) or spy_prev == 0:
            spy_ch = 0.0
        else:
            spy_ch = ((spy_now - spy_prev) / spy_prev) * 100
            
        vix_v = data["^VIX"].iloc[-1] if not np.isnan(data["^VIX"].iloc[-1]) else 0.0
        s_c = "#22c55e" if spy_ch >= 0 else "#ef4444"
        v_c = "#ef4444" if vix_v > 22 else "#22c55e" 
        return spy_ch, vix_v, s_c, v_c
    except:
        return 0.0, 0.0, "#fff", "#fff"

status_text, status_class = get_market_status()
spy_ch, vix_v, s_c, v_c = get_market_sentiment()

# -------------------------------------------------
# 3. UNIVERSE & ENGINE (Fixes SyntaxError)
# -------------------------------------------------
TICKER_MAP = {
    "Leveraged (3x/2x)": ["SOXL", "TQQQ", "TNA", "BOIL", "KOLD", "BITX", "FAS", "SPXL", "SQQQ", "UNG", "UVXY"],
    "Market ETFs": ["SPY", "QQQ", "IWM", "DIA", "VOO", "SCHD", "ARKK", "BITO"],
    "Tech & Semi": ["AMD", "INTC", "MU", "PLTR", "SOFI", "HOOD", "AFRM", "UPST", "ROKU", "NET", "AI", "GME"],
    "Finance": ["BAC", "WFC", "C", "PNC", "COF", "NU", "SQ", "PYPL", "COIN"],
    "Energy & Materials": ["OXY", "DVN", "HAL", "SLB", "FCX", "CLF", "NEM", "GOLD"],
    "Retail & Misc": ["F", "GM", "CL", "PFE", "BMY", "NKE", "SBUX", "TGT", "DIS", "WBD", "MARA", "RIOT", "AMC"]
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
                intrinsic, extrinsic = 0, 0
                
                if strategy_type == "Deep ITM Covered Call":
                    df = chain.calls[(chain.calls["strike"] < price * (1 - min_cushion/100))]
                    if not df.empty:
                        match = df.sort_values("strike", ascending=False).iloc[0]
                        strike = float(match["strike"])
                        opt_price = float(match["lastPrice"])
                        intrinsic = max(0, price - strike)
                        extrinsic = max(0, opt_price - intrinsic)
                        juice = extrinsic
                        net_basis = price - opt_price
                
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

                    dot_style = "dot-green" if roi > 1.2 else "dot-yellow"
                    return {
                        "Status": "🟢" if roi > 1.2 else "🟡", "Dot": dot_style,
                        "Ticker": t, "Price": round(price, 2), "Strike": match["strike"],
                        "Intrinsic": round(intrinsic * 100, 2), "Juice ($)": round(juice_dollars, 2),
                        "ROI %": round(roi, 2), "Expiry": exp, "Net Basis": round(net_basis, 2)
                    }
    except: return None

# -------------------------------------------------
# 4. INTERFACE & SIDEBAR
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
    
    st.subheader("💰 Monthly Goal")
    monthly_goal = st.number_input("Goal ($)", value=2000)
    earned = st.number_input("Earned ($)", value=0)
    
    st.divider()
    st.subheader("🎯 Pay Goal")
    target_type = st.radio("Minimum Target:", ["Dollar ($)", "Percentage (%)"], horizontal=True)
    target_val = st.number_input("Value", value=50.0 if target_type == "Dollar ($)" else 1.0)
    
    st.divider()
    all_s = list(TICKER_MAP.keys())
    sectors = st.multiselect("Sectors", options=all_s, default=all_s)
    strategy = st.selectbox("Strategy", ["Deep ITM Covered Call", "Standard OTM Covered Call", "Cash Secured Put"])
    max_days = st.slider("Days Away", 7, 45, 21)
    min_cushion = st.slider("Safety %", 0, 15, 5)
    
    st.divider()
    st.error("⚖️ LEGAL DISCLAIMER")
    st.caption("JuiceBox Pro is an educational tool. Options trading involves risk. You are responsible for your own financial decisions.")

# -------------------------------------------------
# 5. EXECUTION & PROGRESS (Fixes KeyError)
# -------------------------------------------------
remaining = monthly_goal - earned
st.progress(max(0, min(100, int((earned / monthly_goal) * 100))) / 100 if monthly_goal > 0 else 0)

if st.button("RUN GLOBAL SCAN ⚡", use_container_width=True):
    univ = []
    for s in sectors: univ.extend(TICKER_MAP[s])
    univ = list(set(univ))
    with st.spinner("Harvesting data..."):
        with ThreadPoolExecutor(max_workers=25) as ex:
            results = [r for r in ex.map(lambda t: scan_ticker(t, strategy, min_cushion, max_days, target_type, target_val), univ) if r]
        st.session_state.results = sorted(results, key=lambda x: x['ROI %'], reverse=True)

if "results" in st.session_state and st.session_state.results:
    df = pd.DataFrame(st.session_state.results)
    
    avg_juice = df["Juice ($)"].mean()
    needed = int(np.ceil(remaining / avg_juice)) if avg_juice > 0 else 0
    st.write(f"**Path to Goal:** Average trade pays **${avg_juice:.2f}**. You need roughly **{needed}** more trades.")

    # Dataframe display with specific columns
    sel = st.dataframe(df[["Status", "Ticker", "Price", "Strike", "Juice ($)", "ROI %", "Expiry"]], 
                       use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")

    if sel.selection.rows:
        row = df.iloc[sel.selection.rows[0]]
        st.divider()
        c1, c2 = st.columns([2, 1])
        with c1:
            cid = f"tv_{row['Ticker']}"
            components.html(f'<div id="{cid}" style="height:500px; width:100%;"></div><script src="https://s3.tradingview.com/tv.js"></script><script>new TradingView.widget({{"autosize": true, "symbol": "{row["Ticker"]}", "interval": "D", "theme": "light", "style": "1", "container_id": "{cid}"}});</script>', height=520)
        with c2:
            st.markdown(f"""
            <div class="card">
                <div style="display: flex; align-items: center; margin-bottom: 8px;">
                    <span class="dot {row['Dot']}"></span>
                    <b>{row['Ticker']} ITM BREAKDOWN</b>
                </div>
                <p>Stock Price: ${row['Price']}</p>
                <p>Strike Price: ${row['Strike']}</p>
                <hr>
                <p style="color: grey; font-size: 14px;">Intrinsic Value: ${row['Intrinsic']}</p>
                <p class="juice-val">+ Juice (Extrinsic): ${row['Juice ($)']}</p>
                <hr>
                <p><b>Net Basis: ${row['Net Basis']}</b></p>
                <p><b>Total ROI: {row['ROI %']}%</b></p>
            </div>
            """, unsafe_allow_html=True)
else:
    st.info("Select your sectors and click 'RUN GLOBAL SCAN' to harvest juice.")