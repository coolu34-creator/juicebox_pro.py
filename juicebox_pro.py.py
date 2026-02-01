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
                    return True, e_date.strftime('%Y-%m-%d')
    except: return False, None
    return False, None

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

def mid_price(row):
    bid, ask, lastp = row.get("bid"), row.get("ask"), row.get("lastPrice")
    if pd.notna(bid) and pd.notna(ask) and ask > 0: return (bid + ask) / 2
    return float(lastp) if pd.notna(lastp) else 0

# -------------------------------------------------
# 3. SIDEBAR
# -------------------------------------------------
with st.sidebar:
    st.header("🧃 Configuration")
    acct = st.number_input("Account Value ($)", 1000, 1000000, 10000, step=500, key="sb_acct_v11")
    goal = st.number_input("Weekly Goal ($)", 10, 50000, 150, step=10, key="sb_goal_v11")
    price_range = st.slider("Stock Price Range ($)", 1, 500, (2, 100), key="sb_price_v11")
    dte_range = st.slider("Days to Expiration (DTE)", 0, 45, (0, 30), key="sb_dte_v11")
    strategy = st.selectbox("Strategy", ["Deep ITM Covered Call", "Standard OTM Covered Call", "ATM Covered Call", "Cash Secured Put"], key="sb_strat_v11")
    
    delta_val = (0.15, 0.45) 
    if strategy == "Standard OTM Covered Call":
        delta_val = st.slider("Delta Filter (Probability)", 0.10, 0.90, (0.15, 0.45), key="sb_delta_v11")
    
    cushion_val = 10 
    if strategy == "Deep ITM Covered Call":
        cushion_val = st.slider("Min ITM Cushion %", 0, 30, 10, key="sb_cushion_v11")

    st.markdown("### 📚 Strategy Legend")
    if strategy == "Standard OTM Covered Call":
        st.info("**Standard OTM:** Targets growth + premium. Selects strikes ABOVE market price.")
    elif strategy == "Deep ITM Covered Call":
        st.success("**Deep ITM:** Safety Play. Juice is **Extrinsic Value** only.")
    elif strategy == "ATM Covered Call":
        st.warning("**ATM:** High premium. Picks strike closest to current price.")
    else:
        st.info("**Cash Secured Put:** Paid to wait. Buy stock at a discount.")

    st.divider()
    text = st.text_area("Ticker Watchlist", value="SOFI, PLUG, LUMN, OPEN, BBAI, CLOV, MVIS, MPW, PLTR, AAL, F, NIO, BAC, T, VZ, AAPL, AMD, TSLA, PYPL, KO, O, TQQQ, SOXL, C, MARA, RIOT, COIN, DKNG, LCID, AI, GME, AMC, SQ, SHOP, NU, RIVN, GRAB, CCL, NCLH, RCL, SAVE, JBLU, UAL, NET, CRWD, SNOW, DASH, ROKU, CHWY, CVNA, BKNG, ABNB, ARM, AVGO, MU, INTC, TSM, GFS, PLD, AMT, CMCSA, DIS, NFLX, PARA, SPOT, BOIL, UNG", height=150, key="sb_ticks_v11")
    tickers = sorted({t.upper() for t in text.replace(",", " ").split() if t.strip()})

# -------------------------------------------------
# 4. SCANNER LOGIC
# -------------------------------------------------
def scan(t):
    try:
        price = get_live_price(t)
        if not price or not (price_range[0] <= price <= price_range[1]): return None
        has_e, e_date = get_earnings_info(t)
        disp_ticker = f"{t} (E)" if has_e else t
        tk = yf.Ticker(t)
        if not tk.options: return None

        today = datetime.now()
        best = None
        for exp in tk.options:
            exp_dte = (datetime.strptime(exp, "%Y-%m-%d") - today).days
            if not (dte_range[0] <= exp_dte <= dte_range[1]): 
                if exp_dte > dte_range[1]: break
                continue

            chain = tk.option_chain(exp)
            is_put = strategy == "Cash Secured Put"
            df = chain.puts if is_put else chain.calls
            if df.empty: continue

            if strategy == "Standard OTM Covered Call":
                df = df[df["strike"] > price] 
            elif strategy == "Deep ITM Covered Call":
                df = df[df["strike"] <= price * (1 - cushion_val / 100)] 
            elif strategy == "ATM Covered Call":
                df["dist"] = abs(df["strike"] - price)
                df = df.sort_values("dist").head(1)
            elif strategy == "Cash Secured Put":
                df = df[df["strike"] < price] 

            for _, row in df.iterrows():
                strike, prem = row["strike"], mid_price(row)
                if prem <= 0: continue

                # --- EXTRINSIC EXTRACTION ---
                intrinsic = max(0, price - strike) if not is_put else max(0, strike - price)
                extrinsic = max(0, prem - intrinsic)

                # Filter: Only show ITM if there is time value left
                if strategy == "Deep ITM Covered Call" and extrinsic <= 0.05: continue

                # Determine Juice: Use Extrinsic only for ITM, Full Premium for others
                juice_con = extrinsic * 100 if strategy == "Deep ITM Covered Call" else prem * 100
                coll_con = strike * 100 if is_put else price * 100

                if juice_con <= 1: continue 

                needed = max(1, int(np.ceil(goal / juice_con)))
                if (needed * coll_con) > acct: continue

                # Return calculation
                upside = ((strike - price) / price * 100) if not is_put and strike > price else 0
                total_ret = ((juice_con / coll_con) * 100) + upside

                res = {
                    "Ticker": disp_ticker, "RawT": t, "Grade": "🟢 A" if total_ret > 5 else "🟡 B",
                    "Price": round(price, 2), "Strike": round(strike, 2), "Expiration": exp, "DTE": exp_dte,
                    "Juice/Con": round(juice_con, 2), "Contracts": needed,
                    "Total Juice": round(juice_con * needed, 2), "Total Return %": round(total_ret, 2),
                    "Collateral": round(needed * coll_con, 0), "HasE": has_e, "EDate": e_date,
                    "Extrinsic": round(extrinsic * 100, 2)
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
status_text = "MARKET OPEN 🟢" if is_open else "MARKET CLOSED 🔴"
status_class = "market-open" if is_open else "market-closed"
spy_color = "🟢" if spy_pct >= 0 else "🔴"

st.markdown(f"""
<div class="market-banner {status_class}">
    {status_text} | Current Time (ET): {et_time.strftime('%I:%M %p')}<br>
    SPY S&P 500: ${spy_price:.2f} ({spy_color} {spy_pct:+.2f}%)
</div>
""", unsafe_allow_html=True)

if st.button("RUN LIVE SCAN ⚡", use_container_width=True, key="btn_run_v11"):
    with st.spinner("Scanning for juice..."):
        with ThreadPoolExecutor(max_workers=10) as ex:
            out = list(ex.map(scan, tickers))
    st.session_state.results = [r for r in out if r is not None]

if "results" in st.session_state:
    df = pd.DataFrame(st.session_state.results)
    if not df.empty:
        df = df.sort_values("Total Return %", ascending=False)
        cols = ["Ticker", "Grade", "Price", "Strike", "Expiration", "DTE", "Juice/Con", "Total Juice", "Total Return %"]
        sel = st.dataframe(df[cols], use_container_width=True, hide_index=True, selection_mode="single-row", on_select="rerun", key="df_v11")
        
        if sel.selection.rows:
            r = df.iloc[sel.selection.rows[0]]
            st.divider()
            c1, c2 = st.columns([2, 1])
            with c1:
                tv_html = f"""<div id="tv" style="height:500px"></div><script src="https://s3.tradingview.com/tv.js"></script><script>new TradingView.widget({{"autosize": true,"symbol": "{r['RawT']}","interval": "D","theme": "light","container_id": "tv","studies": ["BB@tv-basicstudies"]}});</script>"""
                components.html(tv_html, height=510)
            with c2:
                g = r["Grade"][-1].lower()
                ext_html = f'<div class="extrinsic-highlight">Time Value (Extrinsic): ${r["Extrinsic"]}</div><br>' if strategy == "Deep ITM Covered Call" else ""
                card_html = f"""<div class="card"><div style="display:flex; justify-content:space-between; align-items:center;"><h2 style="margin:0;">{r['Ticker']}</h2><span class="grade-{g}">{r['Grade']}</span></div><p style="margin:0; font-size:14px; color:#6b7280; margin-top:10px;">Total Return on Cap</p><div class="juice-val">{r['Total Return %']}%</div><hr>{ext_html}<b>Contracts:</b> {r['Contracts']}<br><b>Total Juice:</b> ${r['Total Juice']}<br><hr><b>Price:</b> ${r['Price']} | <b>Strike:</b> ${r['Strike']}<br><b>Exp:</b> {r['Expiration']} ({r['DTE']} Days)</div>"""
                st.markdown(card_html, unsafe_allow_html=True)

st.markdown("""<div class="disclaimer"><b>LEGAL NOTICE:</b> JuiceBox Pro™ owned by <b>Bucforty LLC</b>. Tickers with <b>(E)</b> have earnings scheduled within 45 days.</div>""", unsafe_allow_html=True)