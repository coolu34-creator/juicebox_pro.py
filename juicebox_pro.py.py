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
from datetime import datetime
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
    .card {border:1px solid #e5e7eb;border-radius:16px;padding:18px;background:white;box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);}
    .juice-val {color:#16a34a;font-size:26px;font-weight:800;margin:10px 0;}
    .stButton>button {border-radius:12px;font-weight:700;height:3em;background-color:#16a34a !important; color: white !important;}
    .disclaimer {font-size: 11px; color: #9ca3af; line-height: 1.4; margin-top: 30px; padding: 20px; border-top: 1px solid #eee;}
    .guide-box {background: #f0fdf4; padding: 20px; border-radius: 12px; border: 1px solid #bbf7d0; margin-bottom: 25px;}
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# 2. REAL-TIME HELPERS
# -------------------------------------------------
@st.cache_data(ttl=60)
def get_live_price(t):
    try:
        tk = yf.Ticker(t)
        fi = getattr(tk, "fast_info", None)
        if fi and "last_price" in fi: return float(fi["last_price"])
        hist = tk.history(period="1d", interval="1m")
        if not hist.empty: return float(hist["Close"].iloc[-1])
    except: pass
    return None

@st.cache_data(ttl=3600)
def is_healthy(t):
    try:
        tk = yf.Ticker(t)
        return tk.info.get("netIncomeToCommon", 0) > 0
    except: return True

def mid_price(row):
    bid, ask, lastp = row.get("bid"), row.get("ask"), row.get("lastPrice")
    if pd.notna(bid) and pd.notna(ask) and ask > 0: return (bid + ask) / 2
    return float(lastp) if pd.notna(lastp) else 0

# -------------------------------------------------
# 3. SIDEBAR & STRATEGY LEGEND
# -------------------------------------------------
with st.sidebar:
    st.header("🧃 Configuration")
    acct = st.number_input("Account Value ($)", 1000, 1000000, 10000, step=500, key="cfg_acct")
    goal = st.number_input("Weekly Goal ($)", 10, 50000, 150, step=10, key="cfg_goal")
    price_range = st.slider("Stock Price Range ($)", 1, 500, (2, 100))
    dte_range = st.slider("Days to Expiration (DTE)", 0, 45, (0, 30))
    
    strategy = st.selectbox("Strategy", [
        "Standard OTM Covered Call", 
        "Deep ITM Covered Call", 
        "ATM Covered Call", 
        "Cash Secured Put"
    ])
    
    st.markdown("### 📚 Strategy Legend")
    if strategy == "Standard OTM Covered Call":
        st.info("**Standard OTM:** Targets growth + premium. Selects strikes above current price.")
    elif strategy == "Deep ITM Covered Call":
        st.success("**Deep ITM:** Maximizes downside protection ('Cushion'). Targets income over growth.")
    elif strategy == "ATM Covered Call":
        st.warning("**ATM:** High premium but zero room for stock growth before assignment.")
    else:
        st.info("**Cash Secured Put:** Paid to wait. Collects rent while waiting to buy at a discount.")

    funda_filter = st.toggle("Positive Fundamentals Only", value=False)
    cush_req = st.slider("Min ITM Cushion %", 0, 30, 10) if "Deep ITM" in strategy else 0
    
    st.divider()
    text = st.text_area("Ticker Watchlist", value="SOFI, PLUG, LUMN, OPEN, BBAI, CLOV, MVIS, MPW, PLTR, AAL, F, NIO, BAC, T, VZ, AAPL, AMD, TSLA, PYPL, KO, O, TQQQ, SOXL, C, MARA, RIOT, COIN, DKNG, LCID, AI, GME, AMC, SQ, SHOP, NU, RIVN, GRAB, CCL, NCLH, RCL, SAVE, JBLU, UAL, NET, CRWD, SNOW, DASH, ROKU, CHWY, CVNA, BKNG, ABNB, ARM, AVGO, MU, INTC, TSM, GFS, PLD, AMT, CMCSA, DIS, NFLX, PARA, SPOT, BOIL, UNG", height=180)
    tickers = sorted({t.upper() for t in text.replace(",", " ").split() if t.strip()})

# -------------------------------------------------
# 4. SCANNER LOGIC
# -------------------------------------------------
def scan(t):
    try:
        if funda_filter and not is_healthy(t): return None
        price = get_live_price(t)
        if not price or not (price_range[0] <= price <= price_range[1]): return None
        
        tk = yf.Ticker(t)
        if not tk.options: return None

        valid_exps = []
        today = datetime.now()
        for exp in tk.options:
            exp_dte = (datetime.strptime(exp, "%Y-%m-%d") - today).days
            if dte_range[0] <= exp_dte <= dte_range[1]: valid_exps.append((exp, exp_dte))
            if exp_dte > dte_range[1]: break 

        if not valid_exps: return None

        best = None
        for exp, dte in valid_exps:
            chain = tk.option_chain(exp)
            is_put = strategy == "Cash Secured Put"
            df = chain.puts if is_put else chain.calls
            if df.empty: continue

            if strategy == "Standard OTM Covered Call":
                df = df[df["strike"] > price]
                if df.empty: continue
                pick = df.sort_values("strike").iloc[0]
            elif strategy == "Deep ITM Covered Call":
                df = df[df["strike"] <= price * (1 - cush_req/100)]
                if df.empty: continue
                pick = df.sort_values("strike", ascending=False).iloc[0]
            else:
                df["d"] = abs(df["strike"] - price)
                pick = df.sort_values("d").iloc[0]

            strike, prem = float(pick["strike"]), mid_price(pick)
            if prem <= 0: continue

            collateral_con = strike * 100 if is_put else price * 100
            juice_con = prem * 100
            needed = max(1, int(np.ceil(goal / juice_con)))
            total_collateral = needed * collateral_con
            if total_collateral > acct: continue

            yield_pct = (juice_con / collateral_con) * 100
            upside_pct = ((strike - price) / price * 100) if not is_put and strike > price else 0
            total_ret = yield_pct + upside_pct

            row = {
                "Ticker": t, "Grade": "🟢 A" if total_ret > 5 else "🟡 B",
                "Price": round(price, 2), "Strike": round(strike, 2), "Expiration": exp, "DTE": dte,
                "Juice/Con": round(juice_con, 2), "Contracts": needed,
                "Total Juice": round(juice_con * needed, 2), "Total Return %": round(total_ret, 2),
                "Yield %": round(yield_pct, 2), "Collateral": round(total_collateral, 0)
            }
            if not best or total_ret > best["Total Return %"]: best = row
        return best
    except: return None

# -------------------------------------------------
# 5. UI DISPLAY & RUNNER
# -------------------------------------------------
st.title("🧃 JuiceBox Pro")

with st.expander("📖 OPERATING DIRECTIONS", expanded=False):
    st.markdown("""<div class="guide-box">1. Set capital and DTE. 2. Choose strategy using Legend. 3. Run Live Scan. 4. Analyze detailed Side-Card.</div>""", unsafe_allow_html=True)

if st.button("RUN LIVE SCAN ⚡", use_container_width=True):
    with st.spinner("Streaming real-time data..."):
        with ThreadPoolExecutor(max_workers=10) as ex:
            out = list(ex.map(scan, tickers))
    st.session_state.results = [r for r in out if r]

if "results" in st.session_state:
    df = pd.DataFrame(st.session_state.results)
    if not df.empty:
        df = df.sort_values("Total Return %", ascending=False)
        cols = ["Ticker", "Grade", "Price", "Strike", "Expiration", "DTE", "Juice/Con", "Contracts", "Total Juice", "Total Return %"]
        sel = st.dataframe(df[cols], use_container_width=True, hide_index=True, selection_mode="single-row", on_select="rerun")
        
        if sel.selection.rows:
            r = df.iloc[sel.selection.rows[0]]
            st.divider()
            c1, c2 = st.columns([2, 1])
            with c1:
                components.html(f"""<div id="tv" style="height:500px"></div><script src="https://s3.tradingview.com/tv.js"></script><script>new TradingView.widget({{"autosize": true, "symbol": "{r['Ticker']}", "interval": "D", "theme": "light", "container_id": "tv", "studies": ["BB@tv-basicstudies"]}});</script>""", height=510)
            with c2:
                g = r["Grade"][-1].lower()
                st.markdown(f"""<div class="card"><div style="display:flex; justify-content:space-between; align-items:center;"><h2>{r['Ticker']}</h2><span class="grade-{g}">{r['Grade']}</span></div><p style="margin:0; font-size:14px; color:#6b7280;">Potential Total Return</p><div class="juice-val">{r['Total Return %']}%</div><hr><b>Contracts Needed:</b> {r['Contracts']}<br><b>Juice/Con:</b> ${r['Juice/Con']}<br><b>Total Juice:</b> ${r['Total Juice']}<hr><b>Price:</b> ${r['Price']} | <b>Strike:</b> ${r['Strike']}<br><b>Exp:</b> {r['Expiration']} ({r['DTE']} Days)<br><b>Total Collateral:</b> ${r['Collateral']:,.0f}</div>""", unsafe_allow_html=True)

st.markdown("""<div class="disclaimer"><b>LEGAL NOTICE:</b> JuiceBox Pro™ owned by <b>Bucforty LLC</b>. All data is for educational use only. Trading options involves risk.</div>""", unsafe_allow_html=True)