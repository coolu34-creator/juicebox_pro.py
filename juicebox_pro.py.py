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
import time
from datetime import datetime, time as dtime, timedelta
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
    market_open = dtime(9, 30)
    market_close = dtime(16, 0)
    is_open = is_weekday and (market_open <= current_time <= market_close)
    return is_open, now_et

@st.cache_data(ttl=60)
def get_live_price(t):
    try:
        # Rate limit breather
        time.sleep(0.05)
        tk = yf.Ticker(t)
        live_val = tk.info.get('regularMarketPrice')
        if live_val: return float(live_val)
        hist = tk.history(period="1d")
        if not hist.empty: return float(hist["Close"].iloc[-1])
    except: pass
    return None

def mid_price(row):
    bid, ask, lastp = row.get("bid"), row.get("ask"), row.get("lastPrice")
    if pd.notna(bid) and pd.notna(ask) and ask > 0: return (bid + ask) / 2
    return float(lastp) if pd.notna(lastp) else 0

# -------------------------------------------------
# 3. SIDEBAR (CONFIG & WATCHLIST)
# -------------------------------------------------
with st.sidebar:
    st.header("🧃 Configuration")
    acct = st.number_input("Account Value ($)", 1000, 1000000, 10000, step=500, key="cfg_acct_v30")
    goal_amt = st.number_input("Goal ($)", 1.0, 100000.0, 150.0, step=10.0, key="cfg_goal_v30")
    
    price_range = st.slider("Price Range ($)", 1, 500, (2, 100), key="cfg_pr_v30")
    dte_range = st.slider("DTE", 0, 45, (0, 30), key="cfg_dte_v30")
    strategy = st.selectbox("Strategy", ["Deep ITM Covered Call", "Standard OTM Covered Call", "ATM Covered Call", "Cash Secured Put"], key="cfg_strat_v30")
    
    put_mode = "OTM"
    if strategy == "Cash Secured Put":
        put_mode = st.radio("Put Mode", ["OTM", "ITM"], horizontal=True, key="cfg_pm_v30")
    
    is_itm = strategy == "Deep ITM Covered Call" or (strategy == "Cash Secured Put" and put_mode == "ITM")
    cushion_val = st.slider("Min ITM Cushion %", 0, 50, 10, key="cfg_cush_v30") if is_itm else 0

    st.divider()
    etf_only = st.toggle("ETF Only Mode", value=False, key="cfg_etf_v30")
    
    st.divider()
    # 200 TICKER WATCHLIST LOADED
    watchlist_200 = "TQQQ, SOXL, UPRO, SQQQ, LABU, FNGU, TECL, BULZ, TNA, FAS, SOXS, BOIL, UNG, SPY, QQQ, IWM, DIA, VOO, VTI, QLD, SSO, USD, DIG, ERX, DRN, PILL, CURE, WANT, WEBL, UBT, TMF, TYD, SOFI, PLTR, RIVN, DKNG, AAL, LCID, PYPL, AMD, TSLA, NVDA, AAPL, MSFT, AMZN, GOOGL, META, NFLX, BABA, NIO, GME, AMC, HOOD, MARA, RIOT, COIN, MSTR, SQ, SHOP, U, SNOW, CRWD, NET, AI, PLUG, CLOV, OPEN, BBAI, MVIS, MPW, BAC, T, VZ, KO, O, C, NU, GRAB, CCL, NCLH, RCL, SAVE, JBLU, UAL, DASH, ROKU, CHWY, CVNA, BKNG, ABNB, ARM, AVGO, MU, INTC, TSM, GFS, PLD, AMT, CMCSA, DIS, PARA, SPOT, XOM, CVX, SLB, HAL, OXY, MPC, VLO, RIG, PBR, VALE, FCX, NEM, GOLD, GDX, GDXJ, SIL, SLV, GLD, TLT, HYG, JNK, LQD, BND, KRE, KBE, XLF, XLK, XLV, XLI, XLE, XLU, XLB, XLP, XLY, XRT, SMH, TAN, FAN, LIT, ARKK, ARKG, ARKF, BITO, COLD, MP, ALB, QS, RUN, ENPH, SEDG, FSLR, SE, MELI, PDD, JD, LI, XPEV, BILI, FUTU, CPNG, PATH, DDOG, TEAM, ZS, OKTA, MDB, PANW, FTNT, BILL, AFRM, UPST, LC, V, MA, GS, JPM, WFC, MS, SCHW, TDOC, RBLX, NKLA, F, GM, TM, STLA, HMC, RACE, BYDDF"
    text = st.text_area("Watchlist (200 Symbols)", value=watchlist_200, height=150, key="cfg_wl_v30")
    tickers = sorted({t.upper() for t in text.replace(",", " ").split() if t.strip()})

# -------------------------------------------------
# 4. SCANNER LOGIC (PARALLEL CONNECTION GUARD)
# -------------------------------------------------
def scan(t):
    try:
        time.sleep(0.1) # Connection Guard
        tk = yf.Ticker(t)
        q_type = tk.info.get('quoteType', 'EQUITY')
        if etf_only and q_type != 'ETF': return None

        price = get_live_price(t)
        if not price or not (price_range[0] <= price <= price_range[1]): return None
        if not tk.options: return None

        today = datetime.now()
        best = None
        for exp in tk.options[:5]: # Search nearest 5 expirations for speed
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
                df = df[df["strike"] > price].sort_values("strike").head(1)
            elif strategy == "Cash Secured Put":
                if put_mode == "OTM":
                    df = df[df["strike"] <= price]
                else: 
                    df = df[df["strike"] >= price * (1 + cushion_val / 100)]

            for _, row in df.iterrows():
                strike, total_prem = row["strike"], mid_price(row)
                if row.get("openInterest", 0) < 500 or total_prem <= 0: continue

                intrinsic = max(0, price - strike) if not is_put else max(0, strike - price)
                extrinsic = max(0, total_prem - intrinsic)

                juice_val = total_prem if strategy == "ATM Covered Call" else (extrinsic if intrinsic > 0 else total_prem)
                juice_con = juice_val * 100
                coll_con = strike * 100 if is_put else price * 100
                total_ret = (juice_con / coll_con) * 100
                
                needed = max(1, int(np.ceil(goal_amt / juice_con)))
                if (needed * coll_con) > acct: continue
                goal_met_icon = " 🎯" if juice_con >= goal_amt else ""

                res = {
                    "Ticker": f"{t}{goal_met_icon}", "RawT": t, "Grade": "🟢 A" if total_ret > 5 else "🟡 B",
                    "Price": round(price, 2), "Strike": round(strike, 2), "Expiration": exp, "OI": int(row.get("openInterest", 0)),
                    "Extrinsic": round(extrinsic * 100, 2), "Intrinsic": round(intrinsic * 100, 2),
                    "Total Prem": round(total_prem * 100, 2), "Total Return %": round(total_ret, 2), 
                    "Contracts": needed, "Total Juice": round(juice_con * needed, 2), "Collateral": round(needed * coll_con, 0)
                }
                if not best or total_ret > best["Total Return %"]: best = res
        return best
    except: return None

# -------------------------------------------------
# 5. UI DISPLAY
# -------------------------------------------------
st.title("🧃 JuiceBox Pro")

is_open, et_time = get_market_status()
st.markdown(f"<div class='market-banner' style='background-color: {'#dcfce7' if is_open else '#fee2e2'}'>{'MARKET OPEN 🟢' if is_open else 'MARKET CLOSED 🔴'} | ET: {et_time.strftime('%I:%M %p')}</div>", unsafe_allow_html=True)

if st.button("RUN LIVE SCAN ⚡"):
    with st.spinner(f"Scanning 200 symbols... this takes ~45 seconds."):
        with ThreadPoolExecutor(max_workers=4) as ex: # Throttled for safety
            out = list(ex.map(scan, tickers))
        st.session_state.results = [r for r in out if r is not None]

if "results" in st.session_state:
    df = pd.DataFrame(st.session_state.results)
    if not df.empty:
        df = df.sort_values("Total Return %", ascending=False)
        cols = ["Ticker", "Grade", "Price", "Strike", "Expiration", "OI", "Extrinsic", "Intrinsic", "Total Prem", "Total Return %"]
        sel = st.dataframe(df[cols], use_container_width=True, hide_index=True, selection_mode="single-row", on_select="rerun", key="df_v30")
        
        if sel.selection.rows:
            r = df.iloc[sel.selection.rows[0]]
            st.divider()
            c1, c2 = st.columns([2, 1])
            with c1:
                tv_html = f"""<div id="tv" style="height:500px"></div><script src="https://s3.tradingview.com/tv.js"></script><script>new TradingView.widget({{"autosize": true, "symbol": "{r['RawT']}", "interval": "D", "theme": "light", "container_id": "tv", "studies": ["BB@tv-basicstudies"]}});</script>"""
                components.html(tv_html, height=510)
            with c2:
                g = r["Grade"][-1].lower()
                card_html = f"""<div class="card">
                <div style="display:flex; justify-content:space-between;"><h2>{r['Ticker']}</h2><span class="grade-{g}">{r['Grade']}</span></div>
                <div class="juice-val">{r['Total Return %']}%</div>
                <hr>
                <b>Goal Progress:</b> {round((r['Total Juice']/goal_amt)*100, 1)}% of goal<br>
                <b>Breakdown:</b> Extrinsic: ${r['Extrinsic']} | Intrinsic: ${r['Intrinsic']}<br>
                <hr>
                <b>Contracts:</b> {r['Contracts']} | <b>Total Juice:</b> ${r['Total Juice']}<br>
                <b>Collateral:</b> ${r['Collateral']:,.0f}
                </div>"""
                st.markdown(card_html, unsafe_allow_html=True)

st.markdown("""<div class="disclaimer"><b>LEGAL NOTICE:</b> JuiceBox Pro™ owned by <b>Bucforty LLC</b>. Scan may be slower due to Yahoo Rate Limits.</div>""", unsafe_allow_html=True)