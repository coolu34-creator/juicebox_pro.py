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
from concurrent.futures import ThreadPoolExecutor

# Python 3.9+ (preferred). Falls back safely if not available.
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

# -------------------------------------------------
# 1. APP SETUP & STYLING
# -------------------------------------------------
st.set_page_config(page_title="JuiceBox Pro", page_icon="🧃", layout="wide")

st.markdown(
    """
<style>
    .grade-a { background:#22c55e;color:white;padding:4px 10px;border-radius:18px;font-weight:700;}
    .grade-b { background:#eab308;color:white;padding:4px 10px;border-radius:18px;font-weight:700;}
    .grade-c { background:#ef4444;color:white;padding:4px 10px;border-radius:18px;font-weight:700;}
    .card {border:1px solid #e5e7eb;border-radius:16px;padding:18px;background:white;box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); color: #1f2937; margin-top: 10px;}
    .juice-val {color:#16a34a;font-size:26px;font-weight:800;margin:10px 0;}
    .stButton>button {border-radius:12px;font-weight:700;height:3em;background-color:#16a34a !important; color: white !important;}
    .market-banner {padding: 10px; border-radius: 8px; margin-bottom: 20px; font-weight: bold; text-align: center;}
    .market-open {background-color: #dcfce7; color: #166534; border: 1px solid #86efac;}
    .market-closed {background-color: #fee2e2; color: #991b1b; border: 1px solid #fca5a5;}
    .small {font-size: 12px; color: #6b7280; line-height: 1.4;}
    .mono {font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;}
    .disclaimer {font-size: 11px; color: #9ca3af; line-height: 1.4; margin-top: 30px; padding: 20px; border-top: 1px solid #eee;}
    .pill {display:inline-block;border:1px solid #e5e7eb;border-radius:999px;padding:4px 10px;margin-right:6px;background:#f9fafb;color:#111827;font-weight:600;font-size:12px;}
</style>
""",
    unsafe_allow_html=True,
)

# -------------------------------------------------
# 2. DATA HELPERS
# -------------------------------------------------
def _now_et():
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo("America/New_York"))
        except Exception:
            pass
    # fallback (DST may be off, but keeps app working)
    return datetime.utcnow() - timedelta(hours=5)

def get_market_status():
    now_et = _now_et()
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
        if hist is not None and not hist.empty:
            curr_price = float(hist["Close"].iloc[-1])
            # Try to grab previous close from history (more stable than info)
            prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else curr_price
            if prev_close != 0:
                pct_change = ((curr_price - prev_close) / prev_close) * 100.0
            else:
                pct_change = 0.0
            return curr_price, pct_change
    except Exception:
        pass
    return 0.0, 0.0

@st.cache_data(ttl=30)
def get_live_price(ticker: str):
    try:
        tk = yf.Ticker(ticker)
        # fast path
        v = tk.info.get("regularMarketPrice")
        if v is not None and v != 0:
            return float(v)
        # fallback
        hist = tk.history(period="1d", interval="1m")
        if hist is not None and not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return None

def mid_price(row):
    bid, ask, lastp = row.get("bid"), row.get("ask"), row.get("lastPrice")
    try:
        if pd.notna(bid) and pd.notna(ask) and float(ask) > 0:
            return (float(bid) + float(ask)) / 2.0
        return float(lastp) if pd.notna(lastp) else 0.0
    except Exception:
        return 0.0

def safe_int(x, default=0):
    try:
        if pd.isna(x):
            return default
        return int(x)
    except Exception:
        return default

def safe_float(x, default=0.0):
    try:
        if pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default

def grade_from_return(ret_pct: float):
    # Tune how you want; leaving simple and stable
    if ret_pct >= 3.0:
        return "🟢 A", "a"
    if ret_pct >= 1.5:
        return "🟡 B", "b"
    return "🔴 C", "c"

# -------------------------------------------------
# 3. SIDEBAR
# -------------------------------------------------
with st.sidebar:
    st.header("🧃 Configuration")

    acct = st.number_input("Account Value ($)", 1000, 1000000, 10000, step=500, key="cfg_acct_master")

    goal_type = st.radio("Goal Setting Mode", ["Dollar ($)", "Percentage (%)"], horizontal=True, key="cfg_goal_type_master")

    if goal_type == "Percentage (%)":
        goal_pct = st.number_input("Weekly Goal (%)", 0.1, 10.0, 1.5, step=0.1, key="cfg_goal_pct_master")
        goal_amt = acct * (goal_pct / 100.0)
    else:
        goal_amt = st.number_input("Weekly Goal ($)", 1.0, 100000.0, 150.0, step=10.0, key="cfg_goal_amt_master")
        goal_pct = (goal_amt / acct) * 100.0 if acct else 0.0

    st.divider()

    mode = st.selectbox(
        "Mode",
        [
            "Covered Call (Standard OTM)",
            "Covered Call (Deep ITM)",
            "Covered Call (Closest OTM / 'ATM')",
            "Cash Secured Put (OTM/ATM)",
            "Cash Secured Put (ITM)",
        ],
        key="cfg_mode_master",
    )

    price_range = st.slider("Stock Price Range ($)", 1, 500, (2, 100), key="cfg_price_rng_master")
    dte_range = st.slider("Days to Expiration (DTE)", 0, 45, (0, 30), key="cfg_dte_rng_master")

    cushion_val = 0
    if mode in ["Covered Call (Deep ITM)", "Cash Secured Put (ITM)"]:
        cushion_val = st.slider("Min ITM Cushion %", 0, 50, 10, key="cfg_cushion_master")

    st.divider()
    f_sound = st.toggle("Fundamental Sound Stocks", value=False, key="cfg_fsound_master")
    etf_only = st.toggle("ETF Only Mode", value=False, key="cfg_etf_master")

    st.divider()
    auto_detect = st.toggle("Auto-detect Shares vs Cash", value=True, key="cfg_autodetect_master")
    shares_owned = st.number_input("Shares Owned (if CC)", 0, 100000, 0, step=100, key="cfg_shares_owned_master")
    cash_avail = st.number_input("Cash Available (if CSP)", 0, 10000000, int(acct), step=500, key="cfg_cash_avail_master")

    st.divider()
    st.caption("Min Open Interest (OI)")
    min_oi = st.number_input("OI Threshold", 0, 50000, 500, step=50, key="cfg_min_oi_master")

    st.info(f"Goal: ${goal_amt:,.2f} ({goal_pct:.1f}%)  |  OI ≥ {min_oi}")

    st.divider()
    text = st.text_area(
        "Watchlist",
        value="TQQQ, SOXL, UPRO, SQQQ, LABU, FNGU, TECL, BULZ, TNA, FAS, SOXS, BOIL, UNG, SPY, QQQ, SOFI, PLTR, RIVN, DKNG, AAL, LCID, PYPL, AMD, TSLA, NVDA",
        height=150,
        key="cfg_watchlist_master",
    )
    tickers = sorted({t.upper() for t in text.replace(",", " ").split() if t.strip()})

# -------------------------------------------------
# 4. SCANNER LOGIC
# -------------------------------------------------
def _mode_flags():
    is_put = mode.startswith("Cash Secured Put")
    is_deep_itm_call = mode == "Covered Call (Deep ITM)"
    is_standard_cc = mode == "Covered Call (Standard OTM)"
    is_closest_otm = mode == "Covered Call (Closest OTM / 'ATM')"
    is_itm_put = mode == "Cash Secured Put (ITM)"
    return is_put, is_deep_itm_call, is_standard_cc, is_closest_otm, is_itm_put

def _qualify_text(is_put, is_itm, exp, dte, strike, price, oi, total_prem, intrinsic, extrinsic, needed, collateral):
    parts = []
    parts.append(f"Expiration {exp} (DTE {dte}) is within your range.")
    if is_put:
        parts.append(f"Put OI {oi} meets threshold (≥ {min_oi}).")
        if is_itm:
            parts.append(f"ITM put: strike {strike:.2f} is at least {cushion_val}% above price {price:.2f}.")
        else:
            parts.append(f"OTM/ATM put: strike {strike:.2f} is at or below price {price:.2f}.")
    else:
        parts.append(f"Call OI {oi} meets threshold (≥ {min_oi}).")
        if is_itm:
            parts.append(f"ITM call: strike {strike:.2f} is at least {cushion_val}% below price {price:.2f}.")
        else:
            parts.append(f"OTM call: strike {strike:.2f} is above price {price:.2f}.")
    parts.append(f"Premium ${total_prem*100:.2f} per contract; intrinsic ${intrinsic*100:.2f}, extrinsic ${extrinsic*100:.2f}.")
    parts.append(f"Contracts needed: {needed} (collateral ~ ${collateral:,.0f}).")
    return " ".join(parts)

def _collateral_ok(is_put, needed, strike, price):
    # Covered Calls assume shares are needed; CSP assumes cash collateral.
    if is_put:
        # cash collateral
        coll_per = strike * 100.0
        total = needed * coll_per
        cash = cash_avail if cash_avail is not None else 0
        return total <= cash, coll_per, total
    else:
        # shares collateral
        # If auto-detect is ON and shares_owned is set, enforce contracts <= shares/100
        # Else enforce account value check vs buying shares (fallback)
        coll_per = price * 100.0
        total = needed * coll_per

        if auto_detect and shares_owned > 0:
            max_contracts = shares_owned // 100
            return needed <= max_contracts, coll_per, total

        return total <= acct, coll_per, total

def scan(t):
    diag = {"Ticker": t, "KilledBy": "", "Detail": ""}

    try:
        tk = yf.Ticker(t)

        # Quote type
        info = {}
        try:
            info = tk.info or {}
        except Exception:
            info = {}

        q_type = info.get("quoteType", "EQUITY")
        if etf_only and q_type != "ETF":
            diag["KilledBy"] = "ETF Only"
            diag["Detail"] = f"quoteType={q_type}"
            return None, diag

        if f_sound:
            eps = safe_float(info.get("trailingEps"), default=-1.0)
            rec = info.get("recommendationKey")
            if eps <= 0:
                diag["KilledBy"] = "Fundamentals"
                diag["Detail"] = f"trailingEps={eps}"
                return None, diag
            if rec not in ["buy", "strong_buy", "hold"]:
                diag["KilledBy"] = "Fundamentals"
                diag["Detail"] = f"recommendationKey={rec}"
                return None, diag

        price = get_live_price(t)
        if price is None or price == 0:
            diag["KilledBy"] = "No Price"
            diag["Detail"] = "live price unavailable"
            return None, diag
        if not (price_range[0] <= price <= price_range[1]):
            diag["KilledBy"] = "Price Range"
            diag["Detail"] = f"price={price:.2f}"
            return None, diag

        opts = []
        try:
            opts = list(tk.options) if tk.options else []
        except Exception:
            opts = []
        if not opts:
            diag["KilledBy"] = "No Options"
            diag["Detail"] = "tk.options empty"
            return None, diag

        is_put, is_deep_itm_call, is_standard_cc, is_closest_otm, is_itm_put = _mode_flags()
        is_itm = (not is_put and is_deep_itm_call) or (is_put and is_itm_put)

        today = datetime.now()
        best = None
        best_diag = None

        for exp in opts:
            try:
                exp_dte = (datetime.strptime(exp, "%Y-%m-%d") - today).days
            except Exception:
                continue

            if not (dte_range[0] <= exp_dte <= dte_range[1]):
                continue

            try:
                chain = tk.option_chain(exp)
            except Exception:
                continue

            df = chain.puts if is_put else chain.calls
            if df is None or df.empty:
                continue

            # Strategy filters
            if not is_put:
                if is_deep_itm_call:
                    df = df[df["strike"] <= price * (1.0 - cushion_val / 100.0)]
                elif is_standard_cc:
                    df = df[df["strike"] > price]
                elif is_closest_otm:
                    df = df[df["strike"] > price].sort_values("strike").head(1)
            else:
                if is_itm_put:
                    df = df[df["strike"] >= price * (1.0 + cushion_val / 100.0)]
                else:
                    df = df[df["strike"] <= price]

            if df is None or df.empty:
                continue

            # Evaluate contracts in filtered chain
            for _, row in df.iterrows():
                strike = safe_float(row.get("strike"), 0.0)
                if strike <= 0:
                    continue

                total_prem = mid_price(row)  # per share
                oi = safe_int(row.get("openInterest"), 0)

                if oi < min_oi:
                    continue
                if total_prem <= 0:
                    continue

                # intrinsic/extrinsic per share
                intrinsic = max(0.0, price - strike) if not is_put else max(0.0, strike - price)
                extrinsic = max(0.0, total_prem - intrinsic)

                # Juice logic:
                # - Closest OTM uses Total Premium
                # - ITM uses Extrinsic only (and requires some real extrinsic)
                # - OTM uses Total Premium
                if is_closest_otm:
                    juice_val = total_prem
                else:
                    if intrinsic > 0 and extrinsic <= 0.05:
                        # avoid near-zero extrinsic ITM traps
                        continue
                    juice_val = extrinsic if intrinsic > 0 else total_prem

                juice_con = juice_val * 100.0
                if juice_con <= 0:
                    continue

                # Collateral base for return %
                coll_base = (strike * 100.0) if is_put else (price * 100.0)
                if coll_base <= 0:
                    continue

                total_ret = (juice_con / coll_base) * 100.0

                # contracts needed to hit goal_amt
                needed = max(1, int(np.ceil(goal_amt / juice_con))) if goal_amt > 0 else 1

                ok, coll_per, coll_total = _collateral_ok(is_put, needed, strike, price)
                if not ok:
                    continue

                grade_txt, grade_key = grade_from_return(total_ret)

                goal_met_icon = " 🎯" if juice_con >= goal_amt else ""
                why = _qualify_text(
                    is_put=is_put,
                    is_itm=is_itm,
                    exp=exp,
                    dte=exp_dte,
                    strike=strike,
                    price=price,
                    oi=oi,
                    total_prem=total_prem,
                    intrinsic=intrinsic,
                    extrinsic=extrinsic,
                    needed=needed,
                    collateral=coll_total,
                )

                res = {
                    "Ticker": f"{t}{goal_met_icon}",
                    "RawT": t,
                    "Mode": mode,
                    "Grade": grade_txt,
                    "GradeKey": grade_key,
                    "Price": round(price, 2),
                    "Strike": round(strike, 2),
                    "Expiration": exp,
                    "DTE": int(exp_dte),
                    "OI": int(oi),
                    "Type": q_type,
                    "Extrinsic": round(extrinsic * 100.0, 2),
                    "Intrinsic": round(intrinsic * 100.0, 2),
                    "Total Prem": round(total_prem * 100.0, 2),
                    "Total Return %": round(total_ret, 2),
                    "Contracts": int(needed),
                    "Total Juice": round(juice_con * needed, 2),
                    "Collateral": round(coll_total, 0),
                    "Why": why,
                }

                if (best is None) or (res["Total Return %"] > best["Total Return %"]):
                    best = res
                    best_diag = {"Ticker": t, "KilledBy": "", "Detail": ""}

        if best is None:
            diag["KilledBy"] = "No Match"
            diag["Detail"] = "No contract passed filters"
            return None, diag

        return best, best_diag

    except Exception as e:
        diag["KilledBy"] = "Exception"
        diag["Detail"] = str(e)[:180]
        return None, diag

def scan_all(tickers_list):
    results = []
    diags = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        outs = list(ex.map(scan, tickers_list))
    for r, d in outs:
        if r is not None:
            results.append(r)
        if d is not None and d.get("KilledBy"):
            diags.append(d)
    return results, diags

# -------------------------------------------------
# 5. UI DISPLAY
# -------------------------------------------------
st.title("🧃 JuiceBox Pro (Master)")

is_open, et_time = get_market_status()
spy_price, spy_pct = get_spy_condition()

st.markdown(
    f"""
<div class="market-banner {'market-open' if is_open else 'market-closed'}">
{'MARKET OPEN 🟢' if is_open else 'MARKET CLOSED 🔴'} |
ET: {et_time.strftime('%I:%M %p')} |
SPY: ${spy_price:.2f} ({spy_pct:+.2f}%)
</div>
""",
    unsafe_allow_html=True,
)

cA, cB, cC = st.columns([1, 1, 1])
with cA:
    st.markdown(f"<span class='pill'>Mode: {mode}</span>", unsafe_allow_html=True)
with cB:
    st.markdown(f"<span class='pill'>Goal: ${goal_amt:,.2f}</span>", unsafe_allow_html=True)
with cC:
    if mode.startswith("Cash Secured Put"):
        st.markdown(f"<span class='pill'>Cash: ${cash_avail:,.0f}</span>", unsafe_allow_html=True)
    else:
        if auto_detect and shares_owned > 0:
            st.markdown(f"<span class='pill'>Shares: {shares_owned}</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span class='pill'>Acct: ${acct:,.0f}</span>", unsafe_allow_html=True)

run = st.button("RUN LIVE SCAN ⚡", use_container_width=True, key="main_scan_btn_master")

if run:
    with st.spinner("Scanning for opportunities..."):
        results, diags = scan_all(tickers)
        st.session_state.results_master = results
        st.session_state.diags_master = diags

# Results table
results = st.session_state.get("results_master", [])
diags = st.session_state.get("diags_master", [])

if results:
    df = pd.DataFrame(results).sort_values("Total Return %", ascending=False)

    cols = [
        "Ticker",
        "Mode",
        "Type",
        "Grade",
        "Price",
        "Strike",
        "Expiration",
        "DTE",
        "OI",
        "Extrinsic",
        "Intrinsic",
        "Total Prem",
        "Total Return %",
        "Contracts",
        "Total Juice",
        "Collateral",
    ]

    st.subheader("Scan Results")

    # Try dataframe row selection (newer Streamlit). If it fails, fall back to selectbox.
    selected_row = None
    try:
        sel = st.dataframe(
            df[cols],
            use_container_width=True,
            hide_index=True,
            selection_mode="single-row",
            on_select="rerun",
            key="main_results_df_master",
        )
        if sel is not None and hasattr(sel, "selection") and sel.selection.rows:
            selected_row = df.iloc[sel.selection.rows[0]]
    except Exception:
        selected_row = None

    if selected_row is None:
        st.caption("Tip: if clicking rows doesn't work, your Streamlit version may not support dataframe selection.")
        pick = st.selectbox(
            "Pick a row",
            options=list(range(len(df))),
            format_func=lambda i: f"{df.iloc[i]['Ticker']} | {df.iloc[i]['Mode']} | {df.iloc[i]['Total Return %']}%",
            key="fallback_row_pick_master",
        )
        if pick is not None:
            selected_row = df.iloc[int(pick)]

    if selected_row is not None:
        r = selected_row
        st.divider()

        left, right = st.columns([2, 1])

        with left:
            tv_html = f"""
            <div id="tv" style="height:520px"></div>
            <script src="https://s3.tradingview.com/tv.js"></script>
            <script>
            new TradingView.widget({{
                "autosize": true,
                "symbol": "{r['RawT']}",
                "interval": "D",
                "theme": "light",
                "container_id": "tv",
                "studies": ["BB@tv-basicstudies"]
            }});
            </script>
            """
            components.html(tv_html, height=540)

        with right:
            g = r.get("GradeKey", "b")
            goal_progress = (float(r["Total Juice"]) / goal_amt * 100.0) if goal_amt else 0.0
            card_html = f"""
            <div class="card">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <h2 style="margin:0;">{r['Ticker']}</h2>
                    <span class="grade-{g}">{r['Grade']}</span>
                </div>
                <div class="juice-val">{r['Total Return %']}%</div>
                <div class="small">Mode: <b>{r['Mode']}</b></div>
                <hr>
                <b>Asset Type:</b> {r['Type']}<br>
                <b>Goal Progress:</b> {round(goal_progress, 1)}% of goal<br>
                <b>Breakdown:</b> Extrinsic: ${r['Extrinsic']} | Intrinsic: ${r['Intrinsic']}<br>
                <b>Total Prem:</b> ${r['Total Prem']}<br>
                <hr>
                <b>Contracts:</b> {r['Contracts']}<br>
                <b>Total Juice:</b> ${r['Total Juice']}<br>
                <b>Collateral:</b> ${float(r['Collateral']):,.0f}
            </div>
            """
            st.markdown(card_html, unsafe_allow_html=True)

        st.subheader("Why this trade qualifies")
        st.write(r.get("Why", ""))

else:
    st.caption("Run a scan to see results.")

# Diagnostics
if diags:
    st.divider()
    st.subheader("Scan Diagnostics (what killed results)")
    ddf = pd.DataFrame(diags)
    # show top reasons
    top = (
        ddf.groupby(["KilledBy"])["Ticker"]
        .count()
        .sort_values(ascending=False)
        .reset_index()
        .rename(columns={"Ticker": "Count"})
    )

    c1, c2 = st.columns([1, 2])
    with c1:
        st.write("Top kill reasons")
        st.dataframe(top, use_container_width=True, hide_index=True)
    with c2:
        st.write("Examples")
        st.dataframe(ddf.head(50), use_container_width=True, hide_index=True)

st.markdown(
    """<div class="disclaimer"><b>LEGAL NOTICE:</b> JuiceBox Pro™ owned by <b>Bucforty LLC</b>. Information is for educational purposes only.</div>""",
    unsafe_allow_html=True,
)
