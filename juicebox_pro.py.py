# =================================================================
# SOFTWARE LICENSE AGREEMENT
# Property of: Bucforty LLC
# Project: JuiceBox Pro™
# Copyright (c) 2026. All Rights Reserved.
# NOTICE: This code is proprietary. Reproduction or 
# redistribution of this material is strictly forbidden.
# =================================================================

import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta
from concurrent.futures import ThreadPoolExecutor

# -------------------------------------------------
# 1. APP SETUP & STYLING
# -------------------------------------------------
st.set_page_config(page_title="JuiceBox Pro", page_icon="🧃", layout="wide")

st.markdown("""
<style>
    .grade-a { background:#22c55e;color:white;padding:4px 10px;border-radius:18px;font-weight:700;}
    .grade-b { background:#eab308;color:white;padding:4px 10px;border-radius:18px;font-weight:700;}
    .grade-c { background:#ef4444;color:white;padding:4px 10px;border-radius:18px;font-weight:700;}
    .card {border:1px solid #e5e7eb;border-radius:16px;padding:18px;background:white;box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); color: #1f2937; margin-top: 10px;}
    .juice-val {color:#16a34a;font-size:26px;font-weight:800;margin:10px 0;}
    .stButton>button {border-radius:12px;font-weight:700;height:3em;background-color:#16a34a !important; color: white !important;}
    .earnings-alert {color: #f97316; font-weight: bold; font-size: 14px; margin-bottom: 5px; background: #fff7ed; padding: 5px; border-radius: 6px;}
    .extrinsic-highlight {color: #2563eb; font-weight: bold; font-size: 13px;}
    .market-banner {padding: 10px; border-radius: 8px; margin-bottom: 20px; font-weight: bold; text-align: center;}
    .market-open {background-color: #dcfce7; color: #166534; border: 1px solid #86efac;}
    .market-closed {background-color: #fee2e2; color: #991b1b; border: 1px solid #fca5a5;}
    .disclaimer {font-size: 11px; color: #9ca3af; line-height: 1.4; margin-top: 30px; padding: 20px; border-top: 1px solid #eee;}
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# 2. DATA HELPERS
# -------------------------------------------------
def get_market_status():
    """Checks if NYSE is currently open (9:30-4:00 ET Mon-Fri)."""
    now_utc = datetime.utcnow()
    now_et = now_utc - timedelta(hours=5) 
    is_weekday = 0 <= now_et.weekday() <= 4
    current_time = now_et.time()
    market_open = time(9, 30)
    market_close = time(16, 0)
    is_open = is_weekday and (market_open <= current_time <= market_close)
    return is_open, now_et

@st.cache_data(ttl=300)
def get_spy_condition():
    try:
        spy = yf.Ticker("SPY")
        hist = spy.history(period="2d")
        if len(hist) >= 2:
            prev_close = hist["Close"].iloc[-2]
            curr_price = hist["Close"].iloc[-1]
            pct_change = ((curr_price - prev_close) / prev_close) * 100
            return curr_price, pct_change
    except: pass
    return 0, 0

@st.cache_data(ttl=3600)
def get_earnings_info(t):
    try:
        tk = yf.Ticker(t)
        calendar = tk.calendar
        if calendar is not None and not calendar.empty:
            e_date = calendar.iloc[0, 0] 
            if isinstance(e_date, datetime):
                if e_date < (datetime.now() + timedelta(days=45)):
                    return True, e_date