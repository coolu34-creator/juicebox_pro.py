import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor

# -------------------------------------------------
# 1. APP SETUP
# -------------------------------------------------
st.set_page_config(page_title="JuiceBox Pro", page_icon="🧃", layout="wide")

st.markdown("""
<style>
.grade-a { background:#22c55e;color:white;padding:4px 10px;border-radius:18px;font-weight:700;}
.grade-b { background:#eab308;color:white;padding:4px 10px;border-radius:18px;font-weight:700;}
.grade-c { background:#ef4444;color:white;padding:4px 10px;border-radius:18px;font-weight:700;}
.card {border:1px solid #e5e7eb;border-radius:16px;padding:18px;background:white;}
.juice-val {color:#16a34a;font-size:26px;font-weight:800;}
.muted {color:#6b7280;font-size:12px;}
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# 2. HELPERS
# -------------------------------------------------
@st.cache_data(ttl=300)
def get_price(t):
    try:
        tk = yf.Ticker(t)
        fi = getattr(tk, "fast_info", None)
        if fi and fi.get("last_price"):
            return float(fi["last_price"])
    except:
        pass
    try:
        hist = yf.Ticker(t).history(period="5d")
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

def grade(c):
    return "🟢 A" if c >= 12 else "🟡 B" if c >= 7 else "🔴 C"

# -------------------------------------------------
# 3. SIDEBAR
# -------------------------------------------------
with st.sidebar:
    st.header("🧃 Settings")

    acct = st.number_input("Account Value ($)", 10000, step=500)
    goal = st.number_input("Weekly Goal ($)", 150, step=10)

    if acct > 0 and goal > acct * 0.03:
        st.warning("⚠️ Goal > 3% of account")

    strategy = st.selectbox(
        "Strategy",
        ["Deep ITM Covered Call", "ATM Covered Call", "Cash Secured Put"]
    )

    cushion_req = st.slider("Min ITM Cushion %", 5, 25, 10) if "Deep ITM" in strategy else 0
    show_diag = st.checkbox("Show diagnostics")

    # MASTER TICKER LIST
    default_tickers = [
        "AAPL","MSFT","AMZN","GOOGL","META","NVDA","AMD","TSLA","PLTR",
        "SPY","QQQ","IWM","DIA",
        "JEPI","JEPQ","SCHD","VYM",
        "XLK","XLF","XLE","XLV","XLI",
        "UNG","BOIL","UGA",
        "SOXL","SOXS","TQQQ","SQQQ",
        "TSLL","TNA","ROBN","NFLU"
    ]

    text = st.text_area(
        "Tickers (editable)",
        value=", ".join(default_tickers),
        height=200
    )

    tickers = sorted({t.upper() for t in text.replace(",", " ").split() if t.strip()})

# -------------------------------------------------
# 4. SCANNER
# -------------------------------------------------
def scan(t):
    diag = []
    try:
        price = get_price(t)
        if not price:
            return None, (t, ["no_price"])

        tk = yf.Ticker(t)
        if not tk.options:
            return None, (t, ["no_options"])

        best = None

        for exp in tk.options[:2]:
            chain = tk.option_chain(exp)
            is_put = strategy == "Cash Secured Put"
            df = chain.puts if is_put else chain.calls
            if df.empty:
                continue

            if strategy == "Deep ITM Covered Call":
                cutoff = price * (1 - cushion_req / 100)
                df = df[df["strike"] <= cutoff]
                if df.empty:
                    continue
                pick = df.sort_values("strike", ascending=False).iloc[0]

            elif strategy == "ATM Covered Call":
                df["d"] = abs(df["strike"] - price)
                pick = df.sort_values("d").iloc[0]

            else:
                df = df[df["strike"] <= price]
                if df.empty:
                    continue
                df["d"] = abs(df["strike"] - price)
                pick = df.sort_values("d").iloc[0]

            strike = float(pick["strike"])
            prem = mid_price(pick)
            if prem <= 0:
                continue

            if is_put:
                juice = prem * 100
                collateral = strike * 100
                cushion = (price - strike) / price * 100
            else:
                intrinsic = max(price - strike, 0)
                extrinsic = max(prem - intrinsic, 0)
                juice = extrinsic * 100
                collateral = price * 100
                cushion = (price - strike) / price * 100

            if juice <= 0:
                continue

            contracts = max(1, int(np.ceil(goal / juice)))
            if contracts * collateral > acct:
                continue

            roi = juice / collateral * 100

            row = {
                "Ticker": t,
                "Grade": grade(cushion),
                "Price": round(price, 2),
                "Strike": round(strike, 2),
                "Expiration": exp,
                "Juice/Con": round(juice, 2),
                "Contracts": contracts,
                "Total Juice": round(juice * contracts, 2),
                "Cushion %": round(cushion, 2),
                "ROI %": round(roi, 2),
                "Collateral": round(contracts * collateral, 0)
            }

            if not best or roi > best["ROI %"]:
                best = row

        return (best, (t, diag)) if best else (None, (t, ["no_match"]))

    except Exception as e:
        return None, (t, [str(e)])

# -------------------------------------------------
# 5. RUN
# -------------------------------------------------
st.title("🧃 JuiceBox Pro")

if st.button("RUN SCAN ⚡", use_container_width=True):
    results, diags = [], {}

    with ThreadPoolExecutor(max_workers=10) as ex:
        out = list(ex.map(scan, tickers))

    for r, (t, d) in out:
        diags[t] = d
        if r:
            results.append(r)

    st.session_state.results = results
    st.session_state.diags = diags

# -------------------------------------------------
# 6. DISPLAY
# -------------------------------------------------
if "results" in st.session_state:
    df = pd.DataFrame(st.session_state.results)

    if df.empty:
        st.warning("No qualifying trades.")
    else:
        sel = st.dataframe(df, use_container_width=True, hide_index=True,
                           selection_mode="single-row", on_select="rerun")

        if sel.selection.rows:
            r = df.iloc[sel.selection.rows[0]]
            st.divider()
            c1, c2 = st.columns([2, 1])

            with c1:
                components.html(f"""
                <div id="tv" style="height:450px"></div>
                <script src="https://s3.tradingview.com/tv.js"></script>
                <script>
                new TradingView.widget({{
                  "autosize": true,
                  "symbol": "{r['Ticker']}",
                  "interval": "D",
                  "theme": "light",
                  "container_id": "tv",
                  "studies": ["BB@tv-basicstudies"]
                }});
                </script>
                """, height=460)

            with c2:
                g = r["Grade"][-1].lower()
                st.markdown(f"""
                <div class="card">
                <h3>{r['Ticker']} <span class="grade-{g}">{r['Grade']}</span></h3>
                <p class="juice-val">${r['Total Juice']:,.2f}</p>
                <b>Strike:</b> ${r['Strike']}<br>
                <b>Expiration:</b> {r['Expiration']}<br>
                <b>Contracts:</b> {r['Contracts']}<br>
                <b>Cushion:</b> {r['Cushion %']}%<br>
                <b>ROI:</b> {r['ROI %']}%<br>
                <b>Collateral:</b> ${r['Collateral']:,.0f}
                <p class="muted">Calls use extrinsic only. Leveraged ETFs are short-term tools.</p>
                </div>
                """, unsafe_allow_html=True)

    if show_diag:
        st.subheader("Diagnostics")
        st.dataframe(
            pd.DataFrame(
                [{"Ticker": k, "Notes": ", ".join(v)} for k, v in st.session_state.diags.items()]
            ),
            use_container_width=True,
            hide_index=True
        )
