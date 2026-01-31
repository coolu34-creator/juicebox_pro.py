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
        background: #1e293b; color: white; padding: 12px; 
        border-radius: 12px; margin-bottom: 20px; 
        display: flex; justify-content: space-around; font-weight: 700; 
        box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
    }
    .card { 
        border: 1px solid #e2e8f0; border-radius: 12px; background: white; 
        padding: 20px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); margin-bottom: 15px; 
    }
    .big-title { font-size: 34px; font-weight: 800; color: #0f172a; margin-bottom: 5px; }
    .juice-val { color: #16a34a; font-weight: 800; font-size: 26px; margin: 0; }
    .dot { height: 12px; width: 12px; border-radius: 50%; display: inline-block; margin-right: 8px; }
    .dot-green { background-color: #16a34a; box-shadow: 0 0 10px #16a34a; }
    .dot-yellow { background-color: #facc15; box-shadow: 0 0 10px #facc15; }
    .dot-red { background-color: #dc2626; box-shadow: 0 0 10px #dc2626; }
    .guide-step { 
        background: #f1f5f9; padding: 12px; border-radius: 8px; 
        margin-bottom: 10px; border-left: 5px solid #3b82f6; font-size: 14px;
    }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# 2. MARKET SENTIMENT FETCH (Defined First)
# -------------------------------------------------
def get_market_sentiment():
    try:
        data = yf.download(["^GSPC", "^VIX"], period="2d", interval="1h", progress=False)['Close']
        if data.empty or len(data) < 2:
            return 0.0, 0.0, "#ffffff", "#ffffff"
        
        spy_now = data["^GSPC"].iloc[-1]
        spy_prev = data["^GSPC"].iloc[-2]
        # Use isnan check to avoid +nan% display
        if np.isnan(spy_now) or np.isnan(spy_prev):
             return 0.0, 0.0, "#ffffff", "#ffffff"
             
        spy_ch = ((spy_now - spy_prev) / spy_prev) * 100
        vix_v = data["^VIX"].iloc[-1]
        s_c = "#22c55e" if spy_ch >= 0 else "#ef4444"
        v_c = "#ef4444" if vix_v > 22 else "#22c55e" 
        return spy_ch, vix_v, s_c, v_c
    except:
        return 0.0, 0.0, "#ffffff", "#ffffff"

# CRITICAL: Fetch data BEFORE displaying it
spy_ch, vix_v, s_c, v_c = get_market_sentiment()

# -------------------------------------------------
# 3. UI RENDERING
# -------------------------------------------------
st.markdown(f"""
<div class="sentiment-bar">
    <span>S&P 500: <span style="color:{s_c}">{spy_ch:+.2f}%</span></span>
    <span>VIX (Fear Index): <span style="color:{v_c}">{vix_v:.2f}</span></span>
</div>
""", unsafe_allow_html=True)

st.markdown('<p class="big-title">🧃 JuiceBox Pro</p>', unsafe_allow_html=True)

TICKER_MAP = {
    "Leveraged (3x/2x)": ["SOXL", "TQQQ", "TNA", "BOIL", "KOLD", "BITX", "FAS", "SPXL", "SQQQ", "UNG", "UVXY"],
    "Market ETFs": ["SPY", "QQQ", "IWM", "DIA", "VOO", "SCHD", "ARKK", "BITO"],
    "Tech & Semi": ["AMD", "INTC", "MU", "PLTR", "SOFI", "HOOD", "AFRM", "UPST", "ROKU", "PINS", "SNAP", "NET", "OKTA", "AI", "GME"],
    "Finance": ["BAC", "WFC", "C", "USB", "TFC", "PNC", "COF", "DFS", "NU", "SE", "SQ", "PYPL", "COIN"],
    "Energy & Materials": ["OXY", "DVN", "HAL", "SLB", "KMI", "WMB", "FCX", "CLF", "NEM", "GOLD", "RIG", "XOP"],
    "Retail & Misc": ["F", "GM", "CL", "K", "GIS", "PFE", "BMY", "KVUE", "NKE", "SBUX", "TGT", "DIS", "WBD", "MARA", "RIOT", "AMC"]
}

# -------------------------------------------------
# 4. SCANNER LOGIC
# -------------------------------------------------
def scan_ticker(t, strategy_type, min_cushion, max_days, capital):
    try:
        stock = yf.Ticker(t)
        price = float(stock.fast_info["lastPrice"])
        if not (2.0 <= price <= 100.0): return None
        
        next_e, e_alert = "N/A", ""
        cal = stock.calendar
        if cal is not None and 'Earnings Date' in cal:
            e_date = cal['Earnings Date'][0]
            next_e = e_date.strftime('%Y-%m-%d')
            days_to_e = (e_date.replace(tzinfo=None) - datetime.now()).days
            if 0 <= days_to_e <= 45: e_alert = "📅 ALERT"

        for exp in stock.options[:3]:
            days = (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days
            if 4 <= days <= max_days:
                chain = stock.option_chain(exp)
                match, juice, net_basis = None, 0, 0
                
                if strategy_type == "Deep ITM Covered Call":
                    df = chain.calls[(chain.calls["strike"] < price * (1 - min_cushion/100)) & (chain.calls["volume"] > 0)]
                    if not df.empty:
                        match = df.sort_values("strike", ascending=False).iloc[0]
                        juice = max(0, float(match["bid"]) - (price - float(match["strike"])))
                        net_basis = price - float(match["bid"])
                elif strategy_type == "Standard OTM Covered Call":
                    df = chain.calls[(chain.calls["strike"] > price * 1.01) & (chain.calls["volume"] > 0)]
                    if not df.empty:
                        match = df.sort_values("strike", ascending=True).iloc[0]
                        juice = float(match["bid"])
                        net_basis = price - juice
                elif strategy_type == "Cash Secured Put":
                    df = chain.puts[(chain.puts["strike"] < price * (1 - min_cushion/100)) & (chain.puts["volume"] > 0)]
                    if not df.empty:
                        match = df.sort_values("strike", ascending=False).iloc[0]
                        juice = float(match["bid"])
                        net_basis = float(match["strike"]) - juice

                if match is not None and net_basis > 0:
                    roi = (juice / net_basis) * 100
                    dot_style = "dot-green" if roi > 1.2 else "dot-yellow" if roi > 0.5 else "dot-red"
                    return {
                        "Status": "🟢" if roi > 1.2 else "🟡" if roi > 0.5 else "🔴",
                        "Dot": dot_style, "Ticker": t, "Earnings": e_alert, "E-Date": next_e,
                        "Price": round(price, 2), "Strike