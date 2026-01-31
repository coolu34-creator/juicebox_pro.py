import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, time
import pytz
from concurrent.futures import ThreadPoolExecutor

# --- APP CONFIGURATION ---
st.set_page_config(page_title="JuiceBox Ultra", page_icon="💎", layout="wide")

# Premium CSS Styling
st.markdown("""
<style>
    .premium-header {
        background: linear-gradient(90deg, #0f172a 0%, #334155 100%);
        color: white; padding: 20px; border-radius: 15px; margin-bottom: 25px;
    }
    .card { 
        border: none; border-radius: 15px; background: white; 
        padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        border-top: 5px solid #3b82f6;
    }
</style>
""", unsafe_allow_html=True)

# --- UTILITY FUNCTIONS ---
@st.cache_data(ttl=3600)
def get_market_sentiment():
    try:
        data = yf.download(["^GSPC", "^VIX"], period="2d", interval="1d", progress=False)['Close']
        spy_ch = ((data["^GSPC"].iloc[-1] - data["^GSPC"].iloc[-2]) / data["^GSPC"].iloc[-2]) * 100
        vix_v = data["^VIX"].iloc[-1]
        return spy_ch, vix_v
    except: return 0.0, 0.0

def run_backtest(ticker, target_roi):
    hist = yf.download(ticker, period="1y", interval="1d", progress=False)
    if hist.empty: return None
    weekly_premium = target_roi / 100 
    hist['Returns'] = hist['Close'].pct_change()
    hist['Strategy_Returns'] = np.where(hist['Returns'] > weekly_premium, weekly_premium, hist['Returns'] + weekly_premium)
    hist['Cum_Stock'] = (1 + hist['Returns']).cumprod() * 100
    hist['Cum_Strategy'] = (1 + hist['Strategy_Returns']).cumprod() * 100
    return hist

# --- MAIN UI ---
spy_ch, v_vix = get_market_sentiment()

st.markdown(f"""
<div class="premium-header">
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <h2 style="margin:0;">JuiceBox Ultra | S&P 500: {spy_ch:+.2f}%</h2>
        <h3 style="margin:0;">VIX: {v_vix:.2f}</h3>
    </div>
</div>
""", unsafe_allow_html=True)

# Sidebar Controls
with st.sidebar:
    st.title("🛡️ Pro Controls")
    is_premium = st.toggle("Unlock Premium Tier")
    strategy = st.selectbox("Strategy", ["Covered Call", "Cash Secured Put"])
    income_goal = st.number_input("Monthly Income Goal ($)", value=2000)

# Backtester Section
st.subheader("🧪 Alpha Backtest Engine")
col1, col2 = st.columns([1, 2])

with col1:
    st.write("Analyze historical performance vs. Buy & Hold.")
    bt_ticker = st.text_input("Ticker", value="SPY")
    bt_roi = st.slider("Target Weekly ROI %", 0.5, 3.0, 1.2)
    run_bt = st.button("RUN HISTORY TEST")

if run_bt:
    bt_data = run_backtest(bt_ticker, bt_roi)
    if bt_data is not None:
        with col2:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=bt_data.index, y=bt_data['Cum_Strategy'], name="Juice Strategy", line=