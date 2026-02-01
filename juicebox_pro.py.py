import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
from datetime import datetime
import numpy as np
from concurrent.futures import ThreadPoolExecutor

# -------------------------------------------------
# 1. APP SETUP & STYLING
# -------------------------------------------------
st.set_page_config(page_title="JuiceBox Pro", page_icon="🧃", layout="wide")

st.markdown("""
<style>
    .market-bar { 
        background-color: #000000; color: white; padding: 10px; 
        border-radius: 10px; margin-bottom: 20px; text-align: center;
        display: flex; justify-content: space-around; font-weight: bold;
    }
    .grade-a { background-color: #22c55e; color: white; padding: 2px 8px; border-radius: 12px; }
    .grade-b { background-color: #eab308; color: white; padding: 2px 8px; border-radius: 12px; }
    .grade-c { background-color: #ef4444; color: white; padding: 2px 8px; border-radius: 12px; }
    .card { border: 1px solid #e2e8f0; border-radius: 15px; padding: 20px; background: white; }
    .juice-val { color: #16a34a; font-size: 26px; font-weight: 800; }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# 2. TOP BAR: MARKET WATCH & VIX (Fixes NameError)
# -------------------------------------------------
def get_market_data():
    try:
        # Fetch SPY and VIX
        tickers = yf.download(["SPY", "^VIX"], period="2d", interval="1d", progress=False)['Close']
        spy_prev, spy_now = tickers["SPY"].iloc[-2], tickers["SPY"].iloc[-1]
        vix_now = tickers["^VIX"].iloc[-1]
        
        spy_chg = ((spy_now - spy_prev) / spy_prev) * 100
        spy_color = "#22c55e" if spy_chg >= 0 else "#ef4444"
        
        # Market Sentiment Logic
        sentiment = "🧘 Calm" if vix_now < 20 else "⚠️ Volatile" if vix_now < 30 else "😱 Extreme Fear"
        
        return spy_chg, spy_color, vix_now, sentiment
    except:
        return 0.0, "#fff", 0.0, "Data Offline"

spy_chg, spy_color, vix_now, sentiment = get_market_data()

# Render Top Bar
st.markdown(f"""
<div class="market-bar">
    <span>S&P 500: <span style="color:{spy_color}">{spy_chg:+.2f}%</span></span>