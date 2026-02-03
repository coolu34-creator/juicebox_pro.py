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
    .card {border:1px solid #e5e7eb;border-radius:16px;padding:18px;background:white;box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); color: #1f2937; margin-top: 10px;}
    .juice-val {color:#16a34a;font-size:26px;font-weight:800;margin:10px 0;}
    .stButton>button {border-radius:12px;font-weight:700;height:3em;background-color:#16a34a !important; color: white !important;}
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
        hist = spy.history(period="1d")
        if not hist.empty:
            curr_price = hist["Close"].iloc[-1]
            prev_close = spy.info.get('previousClose', curr_price)
            pct_change = ((curr_price - prev_close) / prev_close) * 100
            return curr_price, pct_change
    except: pass
    return 0, 0

@st.cache_data(ttl=30)
def get_live_price(t):
    try:
        tk = yf.Ticker(t)
        live_val = tk.info.get('regularMarketPrice')
        if live_val: return float(live_val)
        hist = tk.history(period="1d", interval="1m")
        if not hist.empty: return float(hist["Close"].iloc[-1])
    except: pass
    return None

def mid_price(row):
    bid, ask, lastp = row.get("bid"), row.get("ask"), row.get("lastPrice")
    if pd.notna(bid) and pd.notna(ask) and ask > 0: return (bid + ask) / 2
    return float(lastp) if pd.notna(lastp) else 0

# -------------------------------------------------
# 3. SIDEBAR
# -------------------------------------------------
with st.sidebar:
    st.header("🧃 Configuration")
    acct = st.number_input("Account Value ($)", 1000, 1000000, 10000, step=500, key="cfg_acct_v25")
    
    goal_type = st.radio("Goal Setting Mode", ["Dollar ($)", "Percentage (%)"], horizontal=True, key="cfg_goal_type_v25")
    
    if goal_type == "Percentage (%)":
        goal_pct = st.number_input("Weekly Goal (%)", 0.1, 10.0, 1.5, step=0.1, key="cfg_goal_pct_v25")
        goal_amt = acct * (goal_pct / 100)
    else:
        goal_amt = st.number_input("Weekly Goal ($)", 1.0, 100000.0, 150.0, step=10.0, key="cfg_goal_amt_v25")
        goal_pct = (goal_amt / acct) * 100
    
    price_range = st.slider("Stock Price Range ($)", 1, 500, (2, 100), key="cfg_price_rng_v25")
    dte_range = st.slider("Days to Expiration (DTE)", 0, 45, (0, 30), key="cfg_dte_rng_v25")
    strategy = st.selectbox("Strategy", ["Deep ITM Covered Call", "Standard OTM Covered Call", "ATM Covered Call", "Cash Secured Put"], key="cfg_strat_v25")
    
    put_mode = "OTM"
    if strategy == "Cash Secured Put":
        put_mode = st.radio("Put Mode", ["OTM", "ITM"], horizontal=True, key="cfg_put_mode_v25")
    
    is_itm_call = strategy == "Deep ITM Covered Call"
    is_itm_put = strategy == "Cash Secured Put" and put_mode == "ITM"
    cushion_val = 0
    if is_itm_call or is_itm_put:
        cushion_val = st.slider("Min ITM Cushion %", 0, 50, 10, key="cfg_cushion_v25")

    st.divider()
    f_sound = st.toggle("Fundamental Sound Stocks", value=False, key="cfg_fsound_v25")
    etf_only = st.toggle("ETF Only Mode", value=False, key="cfg_etf_v25")
    
    st.info(f"💡 **OI 500+ Active** | Goal: ${goal_amt:,.2f} ({goal_pct:.1f}%)")

    st.divider()
    text = st.text_area("Watchlist", value="TQQQ, SOXL, UPRO, SQQQ, LABU, FNGU, TECL, BULZ, TNA, FAS, SOXS, BOIL, UNG, SPY, QQQ, SOFI, PLTR, RIVN, DKNG, AAL, LCID, PYPL, AMD, TSLA, NVDA", height=150, key="cfg_watchlist_v25")
    tickers = sorted({t.upper() for t in text.replace(",", " ").split() if t.strip()})

# -------------------------------------------------
# 4. SCANNER LOGIC
# -------------------------------------------------
def scan(t):
    try:
        tk = yf.Ticker(t)
        q_type = tk.info.get('quoteType', 'EQUITY')
        
        # ETF Filter Logic
        if etf_only and q_type != 'ETF': return None
        
        if f_sound:
            info = tk.info
            if info.get('trailingEps', -1) <= 0: return None
            if info.get('recommendationKey') not in ['buy', 'strong_buy', 'hold']: return None

        price = get_live_price(t)
        if not price or not (price_range[0] <= price <= price_range[1]): return None
        if not tk.options: return None

        today = datetime.now()
        best = None
        for exp in tk.options:
            exp_dte = (datetime.strptime(exp, "%Y-%m-%d") - today).days
            if not (dte_range[0] <= exp_dte <= dte_range[1]): continue

            chain = tk.option_chain(exp)
            is_put = strategy == "Cash Secured Put"
            df = chain.puts if is_put else chain.calls
            
            if strategy == "Deep ITM Covered Call":
                df = df[df["strike"] <= price * (1 - cushion_val / 100)]
            elif strategy == "Standard OTM Covered Call":
                df = df[df["strike"] > price]
            elif strategy == "ATM Covered Call":
                df["dist"] = abs(df["strike"] - price)
                df = df.sort_values("dist").head(1)
            elif strategy == "Cash Secured Put":
                if put_mode == "OTM":
                    df = df[df["strike"] <= price]
                else: 
                    df = df[df["strike"] >= price * (1 + cushion_val / 100)]

            for _, row in df.iterrows():
                strike, total_prem = row["strike"], mid_price(row)
                open_int = row.get("openInterest", 0)
                if open_int < 500 or total_prem <= 0: continue

                intrinsic = max(0, price - strike) if not is_put else max(0, strike - price)
                extrinsic = max(0, total_prem - intrinsic)

                if strategy == "ATM Covered Call":
                    juice_val = total_prem
                else:
                    if intrinsic > 0 and extrinsic <= 0.05: continue
                    juice_val = extrinsic if intrinsic > 0 else total_prem

                juice_con = juice_val * 100
                coll_con = strike * 100 if is_put else price * 100
                total_ret = (juice_con / coll_con) * 100
                
                needed = max(1, int(np.ceil(goal_amt / juice_con)))
                if (needed * coll_con) > acct: continue

                goal_met_icon = " 🎯" if juice_con >= goal_amt else ""

                res = {
                    "Ticker": f"{t}{goal_met_icon}", "RawT": t, "Grade": "🟢 A" if total_ret > 5 else "🟡 B",
                    "Price": round(price, 2), "Strike": round(strike, 2), "Expiration": exp, "OI": int(open_int),
                    "Type": q_type, # Identifying asset type
                    "Extrinsic": round(extrinsic * 100, 2), "Intrinsic": round(intrinsic * 100, 2),
                    "Total Prem": round(total_prem * 100, 2), "Total Return %": round(total_ret, 2), 
                    "Contracts": needed, "Total Juice": round(juice_con * needed, 2), 
                    "Collateral": round(needed * coll_con, 0)
                }
                if not best or total_ret > best["Total Return %"]: best = res
        return best
    except: return None

# -------------------------------------------------
# 5. UI DISPLAY
# -------------------------------------------------
st.title("🧃 JuiceBox Pro")

is_open, et_time = get_market_status()
spy_price, spy_pct = get_spy_condition()
st.markdown(f"""<div class="market-banner {'market-open' if is_open else 'market-closed'}">
{'MARKET OPEN 🟢' if is_open else 'MARKET CLOSED 🔴'} | ET: {et_time.strftime('%I:%M %p')} | SPY: ${spy_price:.2f} ({spy_pct:+.2f}%)</div>""", unsafe_allow_html=True)

if st.button("RUN LIVE SCAN ⚡", use_container_width=True, key="main_scan_btn_v25"):
    with st.spinner(f"Scanning for opportunities..."):
        with ThreadPoolExecutor(max_workers=10) as ex:
            out = list(ex.map(scan, tickers))
        st.session_state.results = [r for r in out if r is not None]

if "results" in st.session_state:
    df = pd.DataFrame(st.session_state.results)
    if not df.empty:
        df = df.sort_values("Total Return %", ascending=False)
        # Added 'Type' to table columns
        cols = ["Ticker", "Type", "Grade", "Price", "Strike", "Expiration", "OI", "Extrinsic", "Intrinsic", "Total Prem", "Total Return %"]
        sel = st.dataframe(df[cols], use_container_width=True, hide_index=True, selection_mode="single-row", on_select="rerun", key="main_results_df_v25")
        
        if sel.selection.rows:
            r = df.iloc[sel.selection.rows[0]]
            st.divider()
            c1, c2 = st.columns([2, 1])
            with c1:
                tv_html = f"""
                <div id="tv" style="height:500px"></div>
                <script src="https://s3.tradingview.com/tv.js"></script>
                <script>
                new TradingView.widget({{
                    "autosize": true, "symbol": "{r['RawT']}", "interval": "D", "theme": "light", "container_id": "tv", "studies": ["BB@tv-basicstudies"]
                }});
                </script>
                """
                components.html(tv_html, height=510)
            with c2:
                g = r["Grade"][-1].lower()
                card_html = f"""<div class="card">
                <div style="display:flex; justify-content:space-between;"><h2>{r['Ticker']}</h2><span class="grade-{g}">{r['Grade']}</span></div>
                <div class="juice-val">{r['Total Return %']}%</div>
                <hr>
                <b>Asset Type:</b> {r['Type']}<br>
                <b>Goal Progress:</b> {round((r['Total Juice']/goal_amt)*100, 1)}% of goal<br>
                <b>Breakdown:</b> Extrinsic: ${r['Extrinsic']} | Intrinsic: ${r['Intrinsic']}<br>
                <hr>
                <b>Contracts:</b> {r['Contracts']} | <b>Total Juice:</b> ${r['Total Juice']}<br>
                <b>Collateral:</b> ${r['Collateral']:,.0f}
                </div>"""
                st.markdown(card_html, unsafe_allow_html=True)

st.markdown("""<div class="disclaimer"><b>LEGAL NOTICE:</b> JuiceBox Pro™ owned by <b>Bucforty LLC</b>. Information is for educational purposes only.</div>""", unsafe_allow_html=True)