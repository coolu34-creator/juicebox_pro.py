#=================================================================
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
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

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
    except:
        pass
    return 0, 0

@st.cache_data(ttl=30)
def get_live_price(t):
    try:
        tk = yf.Ticker(t)
        live_val = tk.info.get('regularMarketPrice')
        if live_val:
            return float(live_val)
        hist = tk.history(period="1d", interval="1m")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except:
        pass
    return None

def mid_price(row):
    bid, ask, lastp = row.get("bid"), row.get("ask"), row.get("lastPrice")
    if pd.notna(bid) and pd.notna(ask) and ask > 0:
        return (bid + ask) / 2
    return float(lastp) if pd.notna(lastp) else 0

# --- batch prices for big watchlists (200+ tickers) ---
@st.cache_data(ttl=30)
def get_live_prices_batch(tickers_list):
    try:
        df = yf.download(
            tickers=" ".join(tickers_list),
            period="1d",
            interval="1m",
            group_by="ticker",
            threads=True,
            progress=False
        )
        out = {t: None for t in tickers_list}
        if df is None or df.empty:
            return out

        if isinstance(df.columns, pd.MultiIndex):
            for t in tickers_list:
                try:
                    s = df[t]["Close"].dropna()
                    out[t] = float(s.iloc[-1]) if len(s) else None
                except:
                    out[t] = None
        else:
            s = df["Close"].dropna()
            out[tickers_list[0]] = float(s.iloc[-1]) if len(s) else None

        return out
    except:
        return {t: None for t in tickers_list}

# --- cache info and only load when needed ---
@st.cache_data(ttl=1800)
def get_info_cached(t):
    try:
        return yf.Ticker(t).info
    except:
        return {}

# -------------------------------------------------
# 3. SIDEBAR
# -------------------------------------------------
with st.sidebar:
    st.header("🧃 Configuration")
    acct = st.number_input("Account Value ($)", 1000, 1000000, 10000, step=500, key="cfg_acct_v26")

    goal_type = st.radio("Goal Setting Mode", ["Dollar ($)", "Percentage (%)"], horizontal=True, key="cfg_goal_type_v26")

    if goal_type == "Percentage (%)":
        goal_pct = st.number_input("Weekly Goal (%)", 0.1, 10.0, 1.5, step=0.1, key="cfg_goal_pct_v26")
        goal_amt = acct * (goal_pct / 100)
    else:
        goal_amt = st.number_input("Weekly Goal ($)", 1.0, 100000.0, 150.0, step=10.0, key="cfg_goal_amt_v26")
        goal_pct = (goal_amt / acct) * 100

    price_range = st.slider("Stock Price Range ($)", 1, 500, (2, 100), key="cfg_price_rng_v26")
    dte_range = st.slider("Days to Expiration (DTE)", 0, 45, (0, 14), key="cfg_dte_rng_v26")
    strategy = st.selectbox("Strategy", ["Deep ITM Covered Call", "Standard OTM Covered Call", "ATM Covered Call", "Cash Secured Put"], key="cfg_strat_v26")

    put_mode = "OTM"
    if strategy == "Cash Secured Put":
        put_mode = st.radio("Put Mode", ["OTM", "ITM"], horizontal=True, key="cfg_put_mode_v26")

    is_itm_call = strategy == "Deep ITM Covered Call"
    is_itm_put = strategy == "Cash Secured Put" and put_mode == "ITM"
    cushion_val = 0
    if is_itm_call or is_itm_put:
        cushion_val = st.slider("Min ITM Cushion %", 0, 50, 10, key="cfg_cushion_v26")

    st.divider()
    f_sound = st.toggle("Fundamental Sound Stocks", value=False, key="cfg_fsound_v26")
    etf_only = st.toggle("ETF Only Mode", value=False, key="cfg_etf_v26")

    # --- NEW: hide advanced perf knobs behind toggle ---
    advanced_perf = st.toggle("Advanced performance settings", value=False, key="cfg_adv_perf_v26")

    if advanced_perf:
        max_expirations = st.slider("Max expirations per ticker", 1, 8, 2, key="cfg_max_exp_v26")
        workers = st.slider("Workers", 5, 30, 20, key="cfg_workers_v26")
    else:
        max_expirations = 2
        workers = 20

    # timeout stays visible (important)
    scan_timeout_sec = st.slider("Per-ticker timeout (sec)", 2, 25, 8, key="cfg_timeout_v26")

    st.info(f"💡 **OI 500+ Active** | Goal: ${goal_amt:,.2f} ({goal_pct:.1f}%)")

    st.divider()
    text = st.text_area(
        "Watchlist",
        value="TQQQ, SOXL, UPRO, SQQQ, LABU, FNGU, TECL, BULZ, TNA, FAS, SOXS, BOIL, UNG, SPY, QQQ, SOFI, PLTR, RIVN, DKNG, AAL, LCID, PYPL, AMD, TSLA, NVDA",
        height=150,
        key="cfg_watchlist_v26"
    )
    tickers = sorted({t.upper() for t in text.replace(",", " ").split() if t.strip()})

# -------------------------------------------------
# 4. SCANNER LOGIC
# -------------------------------------------------
def scan(t):
    try:
        tk = yf.Ticker(t)

        # price first (batch map), before any info/options work
        price = st.session_state.get("price_map", {}).get(t) or get_live_price(t)
        if not price or not (price_range[0] <= price <= price_range[1]):
            return None

        # only pull info if needed (ETF-only or fundamentals)
        q_type = 'EQUITY'
        info = None
        if etf_only or f_sound:
            info = get_info_cached(t)
            q_type = info.get('quoteType', 'EQUITY')
            if etf_only and q_type != 'ETF':
                return None

        if f_sound:
            if info is None:
                info = get_info_cached(t)
            if info.get('trailingEps', -1) <= 0:
                return None
            if info.get('recommendationKey') not in ['buy', 'strong_buy', 'hold']:
                return None

        if not tk.options:
            return None

        today = datetime.now()

        # filter expirations by DTE then cap how many we scan
        valid_exps = []
        for exp in tk.options:
            try:
                exp_dte = (datetime.strptime(exp, "%Y-%m-%d") - today).days
            except:
                continue
            if dte_range[0] <= exp_dte <= dte_range[1]:
                valid_exps.append((exp_dte, exp))

        if not valid_exps:
            return None

        valid_exps.sort(key=lambda x: x[0])
        valid_exps = valid_exps[:max_expirations]

        best = None
        for exp_dte, exp in valid_exps:
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
                open_int = row.get("openInterest", 0)
                if open_int < 500 or total_prem <= 0:
                    continue

                intrinsic = max(0, price - strike) if not is_put else max(0, strike - price)
                extrinsic = max(0, total_prem - intrinsic)

                if strategy == "ATM Covered Call":
                    juice_val = total_prem
                else:
                    if intrinsic > 0 and extrinsic <= 0.05:
                        continue
                    juice_val = extrinsic if intrinsic > 0 else total_prem

                juice_con = juice_val * 100
                coll_con = strike * 100 if is_put else price * 100
                total_ret = (juice_con / coll_con) * 100

                needed = max(1, int(np.ceil(goal_amt / juice_con)))
                if (needed * coll_con) > acct:
                    continue

                goal_met_icon = " 🎯" if juice_con >= goal_amt else ""

                res = {
                    "Ticker": f"{t}{goal_met_icon}", "RawT": t, "Grade": "🟢 A" if total_ret > 5 else "🟡 B",
                    "Price": round(price, 2), "Strike": round(strike, 2), "Expiration": exp, "OI": int(open_int),
                    "Type": q_type, "Extrinsic": round(extrinsic * 100, 2), "Intrinsic": round(intrinsic * 100, 2),
                    "Total Prem": round(total_prem * 100, 2), "Total Return %": round(total_ret, 2),
                    "Contracts": needed, "Total Juice": round(juice_con * needed, 2),
                    "Collateral": round(needed * coll_con, 0)
                }
                if not best or total_ret > best["Total Return %"]:
                    best = res

        return best
    except:
        return None

# -------------------------------------------------
# 5. UI DISPLAY
# -------------------------------------------------
st.title("🧃 JuiceBox Pro")

is_open, et_time = get_market_status()
spy_price, spy_pct = get_spy_condition()
st.markdown(f"""<div class="market-banner {'market-open' if is_open else 'market-closed'}">
{'MARKET OPEN 🟢' if is_open else 'MARKET CLOSED 🔴'} | ET: {et_time.strftime('%I:%M %p')} | SPY: ${spy_price:.2f} ({spy_pct:+.2f}%)</div>""", unsafe_allow_html=True)

if st.button("RUN LIVE SCAN ⚡", use_container_width=True, key="main_scan_btn_v26"):
    with st.spinner("Scanning for opportunities..."):

        # batch prices first
        st.session_state.price_map = get_live_prices_batch(tickers)

        # only scan tickers with valid price in range
        eligible = [
            t for t in tickers
            if (st.session_state.price_map.get(t) is not None)
            and (price_range[0] <= st.session_state.price_map.get(t) <= price_range[1])
        ]
        st.write(f"Eligible tickers by price: {len(eligible)} / {len(tickers)}")

        progress = st.progress(0)
        results = []
        timed_out = 0
        total = len(eligible)

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(scan, t): t for t in eligible}

            done_count = 0
            for fut in as_completed(futures):
                try:
                    r = fut.result(timeout=scan_timeout_sec)
                    if r is not None:
                        results.append(r)
                except TimeoutError:
                    timed_out += 1
                except Exception:
                    pass

                done_count += 1
                if total > 0 and (done_count % 5 == 0 or done_count == total):
                    progress.progress(done_count / total)

        st.session_state.results = results
        st.session_state.timed_out = timed_out

if "results" in st.session_state:
    df = pd.DataFrame(st.session_state.results)
    if not df.empty:
        df = df.sort_values("Total Return %", ascending=False)
        cols = ["Ticker", "Type", "Grade", "Price", "Strike", "Expiration", "OI", "Extrinsic", "Intrinsic", "Total Prem", "Total Return %"]
        sel = st.dataframe(df[cols], use_container_width=True, hide_index=True, selection_mode="single-row", on_select="rerun", key="main_results_df_v26")

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
    else:
        st.warning("Scan finished. No results met your filters.")

    if "timed_out" in st.session_state and st.session_state.timed_out:
        st.caption(f"Timed out tickers (skipped): {st.session_state.timed_out}")

st.markdown("""<div class="disclaimer"><b>LEGAL NOTICE:</b> JuiceBox Pro™ owned by <b>Bucforty LLC</b>. Information is for educational purposes only.</div>""", unsafe_allow_html=True)
