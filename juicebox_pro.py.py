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
# 2. HELPERS
# -------------------------------------------------
@st.cache_data(ttl=3600)
def is_healthy(t):
    try:
        tk = yf.Ticker(t)
        return tk.info.get("netIncomeToCommon", 0) > 0
    except: return True

@st.cache_data(ttl=300)
def get_price(t):
    try:
        tk = yf.Ticker(t)
        fi = getattr(tk, "fast_info", None)
        if fi and "last_price" in fi: return float(fi["last_price"])
        hist = tk.history(period="1d")
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
    acct = st.number_input("Account Value ($)", 1000, 1000000, 10000, step=500)
    goal = st.number_input("Weekly Goal ($)", 10, 50000, 150, step=10)
    price_range = st.slider("Stock Price Range ($)", 1, 500, (2, 100))
    
    strategy = st.selectbox("Strategy", [
        "Standard OTM Covered Call", 
        "Deep ITM Covered Call", 
        "ATM Covered Call", 
        "Cash Secured Put"
    ])
    
    funda_filter = st.toggle("Positive Fundamentals Only", value=False)
    cushion_req = st.slider("Min ITM Cushion %", 0, 30, 10) if "Deep ITM" in strategy else 0

    st.divider()
    default_ticks = "SOFI, PLUG, LUMN, OPEN, BBAI, CLOV, MVIS, MPW, PLTR, AAL, F, SNAP, PFE, NIO, HOOD, RKT, BAC, T, VZ, AAPL, AMD, TSLA, PYPL, KO, O, TQQQ, SOXL, C, GM, DAL, UBER, MARA, RIOT, COIN, DKNG, LCID, AI, GME, AMC, BB, PATH, U, SQ, SHOP, NU, RIVN, GRAB, SE, CCL, NCLH, RCL, SAVE, JBLU, UAL, LUV, MAR, HLT, MGM, WYNN, TLRY, CGC, CRON, MSOS, HUT, HIVE, CLSK, BTBT, WULF, IREN, BITF, PDD, BABA, JD, LI, XPEV, BIDU, NET, CRWD, OKTA, ZS, DDOG, SNOW, MDB, TEAM, ASAN, MOND, SMAR, ESTC, NTNX, BOX, DBX, DOCU, ZM, PINS, ETSY, EBAY, DASH, ROKU, W, CHWY, CVNA, BYND, EXPE, BKNG, ABNB, LYFT, ARM, AVGO, MU, INTC, TXN, ADI, ON, NXPI, QRVO, SWKS, TER, LRCX, AMAT, KLAC, ASML, TSM, GFS, WDC, STX, MP, ALB, SQM, CHPT, BLNK, EVGO, BE, FCEL, RUN, NOVA, ENPH, SEDG, FSLR, CSIQ, JKS, DQ, PLD, AMT, CCI, EQIX, DLR, WY, PSA, EXR, CUBE, IRM, VICI, STAG, EPR, AGNC, NLY, CMCSA, DIS, NFLX, PARA, WBD, SIRI, FUBO, SPOT, BOIL, UNG"
    text = st.text_area("Ticker Watchlist", value=default_ticks, height=180)
    tickers = sorted({t.upper() for t in text.replace(",", " ").split() if t.strip()})

# -------------------------------------------------
# 4. SCANNER LOGIC
# -------------------------------------------------
def scan(t):
    try:
        if funda_filter and not is_healthy(t): return None, (t, ["bad_funda"])
        price = get_price(t)
        if not price or not (price_range[0] <= price <= price_range[1]): return None, (t, ["range"])
        
        tk = yf.Ticker(t)
        if not tk.options: return None, (t, ["no_opt"])

        best = None
        for exp in tk.options[:2]:
            chain = tk.option_chain(exp)
            is_put = strategy == "Cash Secured Put"
            df = chain.puts if is_put else chain.calls
            if df.empty: continue

            # Strategy Strike Selection
            if strategy == "Standard OTM Covered Call":
                df = df[df["strike"] > price] # Forces OTM
                if df.empty: continue
                pick = df.sort_values("strike").iloc[0]
            elif strategy == "Deep ITM Covered Call":
                df = df[df["strike"] <= price * (1 - cushion_req/100)]
                if df.empty: continue
                pick = df.sort_values("strike", ascending=False).iloc[0]
            else: # ATM or CSP
                df["d"] = abs(df["strike"] - price)
                pick = df.sort_values("d").iloc[0]

            strike, prem = float(pick["strike"]), mid_price(pick)
            if prem <= 0: continue

            # Component Calculations
            collateral = strike * 100 if is_put else price * 100
            
            if is_put:
                juice = prem * 100
                upside_pct = 0
                yield_pct = (juice / collateral) * 100
                cushion = max(0, (price - strike) / price * 100)
            else:
                intrinsic = max(0, price - strike)
                extrinsic = max(0, prem - intrinsic)
                juice = extrinsic * 100
                yield_pct = (juice / collateral) * 100
                upside_pct = ((strike - price) / price * 100)
                cushion = ((price - strike) / price * 100) if strike < price else 0

            total_ret = yield_pct + upside_pct
            contracts = max(1, int(np.ceil(goal / (prem * 100))))
            if contracts * collateral > acct: continue

            row = {
                "Ticker": t, "Grade": "🟢 A" if total_ret > 5 else "🟡 B",
                "Price": round(price, 2), "Strike": round(strike, 2), "Expiration": exp,
                "Juice/Con": round(prem * 100, 2), "Contracts": contracts,
                "Total Juice": round((prem * 100) * contracts, 2),
                "Yield %": round(yield_pct, 2), "Upside %": round(upside_pct, 2),
                "Total Return %": round(total_ret, 2), "Cushion %": round(cushion, 2),
                "Collateral": round(contracts * collateral, 0)
            }
            if not best or total_ret > best["Total Return %"]: best = row
        return (best, (t, [])) if best else (None, (t, ["no_match"]))
    except: return None, (t, ["err"])

# -------------------------------------------------
# 5. UI DISPLAY & RUNNER
# -------------------------------------------------
st.title("🧃 JuiceBox Pro")

with st.expander("📖 OPERATING DIRECTIONS", expanded=False):
    st.markdown("""
    <div class="guide-box">
    <b>1. Set Capital:</b> Define your trading budget in the sidebar.<br>
    <b>2. Set Goal:</b> Set your weekly cash flow target.<br>
    <b>3. Filter Fundamentals:</b> Toggle 'Positive Fundamentals' to skip companies with negative net income.<br>
    <b>4. Choose Strategy:</b> Use 'Standard OTM' for capital gains + premium; 'Deep ITM' for conservative income.<br>
    <b>5. Analyze:</b> The 'Grade' is based on the Total Potential Return (Premium + Stock Gain).
    </div>
    """, unsafe_allow_html=True)

if st.button("RUN SCAN ⚡", use_container_width=True):
    results = []
    with st.spinner("Squeezing..."):
        with ThreadPoolExecutor(max_workers=10) as ex:
            out = list(ex.map(scan, tickers))
    st.session_state.results = [r for r, d in out if r]

if "results" in st.session_state:
    df = pd.DataFrame(st.session_state.results)
    if not df.empty:
        df = df.sort_values("Total Return %", ascending=False)
        sel = st.dataframe(df, use_container_width=True, hide_index=True, selection_mode="single-row", on_select="rerun")
        if sel.selection.rows:
            r = df.iloc[sel.selection.rows[0]]
            st.divider()
            c1, c2 = st.columns([2, 1])
            with c1:
                components.html(f"""<div id="tv" style="height:500px"></div><script src="https://s3.tradingview.com/tv.js"></script><script>new TradingView.widget({{"autosize": true, "symbol": "{r['Ticker']}", "interval": "D", "theme": "light", "style": "1", "container_id": "tv", "studies": ["BB@tv-basicstudies", "RSI@tv-basicstudies"]}});</script>""", height=510)
            with c2:
                g = r["Grade"][-1].lower()
                st.markdown(f"""<div class="card"><div style="display:flex; justify-content:space-between; align-items:center;"><h2>{r['Ticker']}</h2><span class="grade-{g}">{r['Grade']}</span></div><p style="margin:0; font-size:14px; color:#6b7280;">Potential Total Return</p><div class="juice-val">{r['Total Return %']}%</div><hr><b>Yield:</b> {r['Yield %']}% | <b>Upside:</b> {r['Upside %']}%<br><b>Strike:</b> ${r['Strike']} | <b>Exp:</b> {r['Expiration']}<br><b>Collateral:</b> ${r['Collateral']:,.0f}</div>""", unsafe_allow_html=True)

st.markdown("""
<div class="disclaimer">
<b>LEGAL NOTICE & DISCLAIMER:</b> JuiceBox Pro™ is a software tool owned by <b>Bucforty LLC</b> and provided for informational and educational purposes only. It is NOT financial advice. 
The creator and Bucforty LLC are not registered investment advisors. Options trading involves substantial risk of loss. 
Data is provided "as-is" via third-party APIs and may be delayed. By using this tool, you agree that you are solely responsible for your 
own trading decisions and hold Bucforty LLC harmless from any losses incurred.
</div>
""", unsafe_allow_html=True)