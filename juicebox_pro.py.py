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
import textwrap
from datetime import datetime, timedelta
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
    .disclaimer {font-size: 11px; color: #9ca3af; line-height: 1.4; margin-top: 30px; padding: 20px; border-top: 1px solid #eee;}
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# 2. DATA HELPERS
# -------------------------------------------------
@st.cache_data(ttl=3600)
def get_earnings_info(t):
    try:
        tk = yf.Ticker(t)
        calendar = tk.calendar
        if calendar is not None and not calendar.empty:
            e_date = calendar.iloc[0, 0] 
            if isinstance(e_date, datetime):
                # Returns True if earnings are within 45 days
                if e_date < (datetime.now() + timedelta(days=45)):
                    return True, e_date.strftime('%Y-%m-%d')
    except: pass
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
# 3. SIDEBAR (Unique Keys to fix crashes)
# -------------------------------------------------
with st.sidebar:
    st.header("🧃 Configuration")
    
    acct = st.number_input("Account Value ($)", 1000, 1000000, 10000, step=500, key="sb_acct_input")
    goal = st.number_input("Weekly Goal ($)", 10, 50000, 150, step=10, key="sb_goal_input")
    price_range = st.slider("Stock Price Range ($)", 1, 500, (2, 100), key="sb_price_slider")
    dte_range = st.slider("Days to Expiration (DTE)", 0, 45, (0, 30), key="sb_dte_slider")
    
    strategy = st.selectbox("Strategy", ["Standard OTM Covered Call", "Deep ITM Covered Call", "ATM Covered Call", "Cash Secured Put"], key="sb_strat_select")
    
    # --- DYNAMIC SLIDERS ---
    delta_val = (0.15, 0.45) 
    if strategy == "Standard OTM Covered Call":
        delta_val = st.slider("Delta Filter (Probability)", 0.10, 0.90, (0.15, 0.45), key="sb_delta_slider")
    
    cushion_val = 10 
    if strategy == "Deep ITM Covered Call":
        cushion_val = st.slider("Min ITM Cushion %", 0, 30, 10, key="sb_cushion_slider")

    # --- LEGEND ---
    st.markdown("### 📚 Strategy Legend")
    if strategy == "Standard OTM Covered Call":
        st.info("**Standard OTM:** Targets growth + premium. Selects strikes ABOVE market price.")
    elif strategy == "Deep ITM Covered Call":
        st.success("**Deep ITM:** Maximizes safety ('Cushion'). Targets strikes BELOW market price.")
    elif strategy == "ATM Covered Call":
        st.warning("**ATM:** High premium. Automatically picks the strike closest to the current stock price.")
    else:
        st.info("**Cash Secured Put:** OTM Puts. You are paid to wait to buy the stock at a discount.")

    st.divider()
    text = st.text_area("Ticker Watchlist", value="SOFI, PLUG, LUMN, OPEN, BBAI, CLOV, MVIS, MPW, PLTR, AAL, F, NIO, BAC, T, VZ, AAPL, AMD, TSLA, PYPL, KO, O, TQQQ, SOXL, C, MARA, RIOT, COIN, DKNG, LCID, AI, GME, AMC, SQ, SHOP, NU, RIVN, GRAB, CCL, NCLH, RCL, SAVE, JBLU, UAL, NET, CRWD, SNOW, DASH, ROKU, CHWY, CVNA, BKNG, ABNB, ARM, AVGO, MU, INTC, TSM, GFS, PLD, AMT, CMCSA, DIS, NFLX, PARA, SPOT, BOIL, UNG", height=150, key="sb_ticker_input")
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

            # --- CRITICAL FIX: STRATEGY STRIKE SELECTION ---
            if strategy == "Standard OTM Covered Call":
                df = df[df["strike"] > price] # Must be OTM
            elif strategy == "Deep ITM Covered Call":
                df = df[df["strike"] <= price * (1 - cushion_val / 100)] # Must be Deep ITM
            elif strategy == "ATM Covered Call":
                # STRICTLY FIND CLOSEST STRIKE. Do not iterate whole chain.
                # Sort by distance to price and take the top 1
                df["dist"] = abs(df["strike"] - price)
                df = df.sort_values("dist").head(1)
            elif strategy == "Cash Secured Put":
                df = df[df["strike"] < price] # Puts should be OTM (Strike < Price)

            for _, row in df.iterrows():
                strike, prem = row["strike"], mid_price(row)
                if prem <= 0: continue

                # Delta Prob check (only for Standard)
                approx_delta = 1.0 - abs(strike - price) / price
                if strategy == "Standard OTM Covered Call":
                    if not (delta_val[0] <= approx_delta <= delta_val[1]): continue

                coll_con = strike * 100 if is_put else price * 100
                juice_con = prem * 100
                needed = max(1, int(np.ceil(goal / juice_con)))
                if (needed * coll_con) > acct: continue

                total_ret = ((juice_con / coll_con) * 100) + (((strike - price) / price * 100) if not is_put and strike > price else 0)

                res = {
                    "Ticker": disp_ticker, "RawT": t, "Grade": "🟢 A" if total_ret > 5 else "🟡 B",
                    "Price": round(price, 2), "Strike": round(strike, 2), "Expiration": exp, "DTE": exp_dte,
                    "Delta": round(approx_delta, 2), "Juice/Con": round(juice_con, 2), "Contracts": needed,
                    "Total Juice": round(juice_con * needed, 2), "Total Return %": round(total_ret, 2),
                    "Collateral": round(needed * coll_con, 0), "HasE": has_e, "EDate": e_date
                }
                if not best or total_ret > best["Total Return %"]: best = res
        return best
    except: return None

# -------------------------------------------------
# 5. RUNNER & DISPLAY
# -------------------------------------------------
st.title("🧃 JuiceBox Pro")

if st.button("RUN LIVE SCAN ⚡", use_container_width=True, key="btn_run_main"):
    with st.spinner("Analyzing market data..."):
        with ThreadPoolExecutor(max_workers=10) as ex:
            out = list(ex.map(scan, tickers))
    # Filter out None values to prevent "Ambiguous Truth" error
    st.session_state.results = [r for r in out if r is not None]

if "results" in st.session_state:
    df = pd.DataFrame(st.session_state.results)
    if not df.empty:
        df = df.sort_values("Total Return %", ascending=False)
        cols = ["Ticker", "Grade", "Price", "Strike", "Expiration", "DTE", "Juice/Con", "Total Juice", "Total Return %"]
        
        sel = st.dataframe(df[cols], use_container_width=True, hide_index=True, selection_mode="single-row", on_select="rerun", key="df_results")
        
        if sel.selection.rows:
            r = df.iloc[sel.selection.rows[0]]
            st.divider()
            c1, c2 = st.columns([2, 1])
            with c1:
                components.html(f"""<div id="tv" style="height:500px"></div><script src="https://s3.tradingview.com/tv.js"></script><script>new TradingView.widget({{"autosize": true, "symbol": "{r['RawT']}", "interval": "D", "theme": "light", "container_id": "tv", "studies": ["BB@tv-basicstudies"]}});</script>""", height=510)
            with c2:
                g = r["Grade"][-1].lower()
                e_html = f'<div class="earnings-alert">⚠️ EARNINGS: {r["EDate"]}</div>' if r['HasE'] else ""
                
                # HTML RENDERING FIX: Removed indentation and used textwrap
                card_html = textwrap.dedent(f"""
                <div class="card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <h2 style="margin:0;">{r['Ticker']}</h2>
                        <span class="grade-{g}">{r['Grade']}</span>
                    </div>
                    {e_html}
                    <p style="margin:0; font-size:14px; color:#6b7280; margin-top:10px;">Potential Total Return</p>
                    <div class="juice-val">{r['Total Return %']}%</div>
                    <hr>
                    <b>Contracts:</b> {r['Contracts']}<br>
                    <b>Total Juice:</b> ${r['Total Juice']}<br>
                    <hr>
                    <b>Price:</b> ${r['Price']} | <b>Strike:</b> ${r['Strike']}<br>
                    <b>Exp:</b> {r['Expiration']} ({r['DTE']} Days)
                </div>
                """)
                st.markdown(card_html, unsafe_allow_html=True)

st.markdown("""<div class="disclaimer"><b>LEGAL NOTICE:</b> JuiceBox Pro™ owned by <b>Bucforty LLC</b>. Tickers with <b>(E)</b> have earnings scheduled within 45 days.</div>""", unsafe_allow_html=True)