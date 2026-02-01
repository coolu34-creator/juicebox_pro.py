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
.muted {color:#6b7280;font-size:12px;margin-top:15px;}
.stButton>button {border-radius:12px;font-weight:700;height:3em;background-color:#16a34a !important;}
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
    except: pass
    try:
        hist = yf.Ticker(t).history(period="5d")
        if not hist.empty: return float(hist["Close"].iloc[-1])
    except: pass
    return None

def mid_price(row):
    bid, ask, lastp = row.get("bid"), row.get("ask"), row.get("lastPrice")
    if pd.notna(bid) and pd.notna(ask) and ask > 0:
        return (bid + ask) / 2
    return float(lastp) if pd.notna(lastp) else 0

def grade(c):
    if c >= 12: return "🟢 A"
    if c >= 7: return "🟡 B"
    return "🔴 C"

# -------------------------------------------------
# 3. SIDEBAR & SETTINGS
# -------------------------------------------------
with st.sidebar:
    st.header("🧃 Configuration")
    
    acct = st.number_input("Account Value ($)", 1000, 1000000, 10000, step=500)
    goal = st.number_input("Weekly Goal ($)", 10, 50000, 150, step=10)

    # Risk Warning
    if acct > 0 and goal > acct * 0.05:
        st.error("⚠️ Aggressive Goal: Target is >5% of account per week.")
    elif acct > 0 and goal > acct * 0.02:
        st.warning("⚠️ High Yield: Target is >2% of account per week.")

    strategy = st.selectbox(
        "Strategy",
        ["Deep ITM Covered Call", "ATM Covered Call", "Cash Secured Put"]
    )

    cushion_req = st.slider("Min ITM Cushion %", 0, 30, 10) if "Deep ITM" in strategy else 0
    show_diag = st.checkbox("Show Error Logs", value=False)

    st.divider()
    default_tickers = ["AAPL","MSFT","AMZN","GOOGL","META","NVDA","AMD","TSLA","PLTR","SPY","QQQ","IWM","SOXL","TQQQ","BITO"]
    text = st.text_area("Ticker Watchlist", value=", ".join(default_tickers), height=150)
    tickers = sorted({t.upper() for t in text.replace(",", " ").split() if t.strip()})

# -------------------------------------------------
# 4. SCANNER LOGIC
# -------------------------------------------------
def scan(t):
    try:
        price = get_price(t)
        if not price: return None, (t, ["no_price"])
        
        tk = yf.Ticker(t)
        if not tk.options: return None, (t, ["no_options"])

        best = None
        for exp in tk.options[:2]: # Look at nearest 2 expirations
            chain = tk.option_chain(exp)
            is_put = strategy == "Cash Secured Put"
            df = chain.puts if is_put else chain.calls
            if df.empty: continue

            if strategy == "Deep ITM Covered Call":
                cutoff = price * (1 - cushion_req / 100)
                df = df[df["strike"] <= cutoff]
                if df.empty: continue
                pick = df.sort_values("strike", ascending=False).iloc[0]
            elif strategy == "ATM Covered Call":
                df["d"] = abs(df["strike"] - price)
                pick = df.sort_values("d").iloc[0]
            else: # Cash Secured Put
                df = df[df["strike"] <= price]
                if df.empty: continue
                df["d"] = abs(df["strike"] - price)
                pick = df.sort_values("d").iloc[0]

            strike, prem = float(pick["strike"]), mid_price(pick)
            if prem <= 0: continue

            if is_put:
                juice = prem * 100
                collateral = strike * 100
            else:
                intrinsic = max(price - strike, 0)
                extrinsic = max(prem - intrinsic, 0)
                juice = extrinsic * 100
                collateral = price * 100
            
            cushion = (price - strike) / price * 100 if not is_put else (price - strike) / price * 100
            if juice <= 0: continue

            contracts = max(1, int(np.ceil(goal / juice)))
            if contracts * collateral > acct: continue

            roi = (juice / collateral) * 100
            row = {
                "Ticker": t, "Grade": grade(cushion), "Price": round(price, 2),
                "Strike": round(strike, 2), "Expiration": exp, "Juice/Con": round(juice, 2),
                "Contracts": contracts, "Total Juice": round(juice * contracts, 2),
                "Cushion %": round(cushion, 2), "ROI %": round(roi, 2),
                "Collateral": round(contracts * collateral, 0)
            }
            if not best or roi > best["ROI %"]: best = row
        return (best, (t, [])) if best else (None, (t, ["no_match"]))
    except Exception as e: return None, (t, [str(e)])

# -------------------------------------------------
# 5. UI LAYOUT
# -------------------------------------------------
st.title("🧃 JuiceBox Pro")

# INSTRUCTIONS EXPANDER
with st.expander("📖 HOW TO USE THIS SCANNER", expanded=False):
    st.markdown("""
    ### 1. Set Your Goals
    Enter your **Account Value** and **Weekly Goal** in the sidebar. The tool calculates how many contracts are required to hit your income target without over-leveraging your cash.
    
    ### 2. Understand the Strategies
    * **Deep ITM (In-The-Money) Call:** High safety. You sell a call far below the current price. You keep the "Extrinsic" value as profit.
    * **ATM (At-The-Money) Call:** Higher yield, but less protection if the stock drops.
    * **Cash Secured Put:** Getting paid to commit to buying a stock at a specific price.
    
    ### 3. The 'Grade' System
    The grade is based on **Cushion %** (how much the stock can drop before your profit is erased).
    * 🟢 **A (12%+):** Very Conservative.
    * 🟡 **B (7-12%):** Balanced.
    * 🔴 **C (<7%):** Aggressive/Speculative.
    """)
    st.info("💡 **Pro Tip:** Select a result from the table to load its interactive technical chart.")

[Image of Options Profit and Loss Diagram]

if st.button("RUN SCAN ⚡", use_container_width=True):
    results, diags = [], {}
    with st.spinner("Squeezing the juice..."):
        with ThreadPoolExecutor(max_workers=10) as ex:
            out = list(ex.map(scan, tickers))
    for r, (t, d) in out:
        diags[t] = d
        if r: results.append(r)
    st.session_state.results = results
    st.session_state.diags = diags

# -------------------------------------------------
# 6. RESULTS & CHARTING
# -------------------------------------------------
if "results" in st.session_state:
    df = pd.DataFrame(st.session_state.results)
    if df.empty:
        st.warning("No qualifyng trades found for this budget/strategy.")
    else:
        # Selection Table
        sel = st.dataframe(df, use_container_width=True, hide_index=True,
                            selection_mode="single-row", on_select="rerun")

        if sel.selection.rows:
            r = df.iloc[sel.selection.rows[0]]
            st.divider()
            c1, c2 = st.columns([2, 1])

            with c1:
                components.html(f"""
                <div id="tv" style="height:500px"></div>
                <script src="https://s3.tradingview.com/tv.js"></script>
                <script>
                new TradingView.widget({{
                  "autosize": true, "symbol": "{r['Ticker']}", "interval": "D",
                  "theme": "light", "style": "1", "container_id": "tv",
                  "studies": ["BB@tv-basicstudies", "RSI@tv-basicstudies"]
                }});
                </script>
                """, height=510)

            with c2:
                g_class = r["Grade"][-1].lower()
                st.markdown(f"""
                <div class="card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <h2 style="margin:0;">{r['Ticker']}</h2>
                        <span class="grade-{g_class}">{r['Grade']}</span>
                    </div>
                    <p style="margin-bottom:0; font-size:14px; color:#6b7280;">Estimated Profit</p>
                    <div class="juice-val">${r['Total Juice']:,.2f}</div>
                    <hr>
                    <b>Target Strike:</b> ${r['Strike']}<br>
                    <b>Expiration:</b> {r['Expiration']}<br>
                    <b>Contracts needed:</b> {r['Contracts']}<br>
                    <b>Downside Cushion:</b> {r['Cushion %']}%<br>
                    <b>Expected ROI:</b> {r['ROI %']}%<br>
                    <b>Total Collateral:</b> ${r['Collateral']:,.0f}
                    <p class="muted">Note: Calculations use Mid-Price. Collateral is based on 100 shares/contract or cash required for puts.</p>
                </div>
                """, unsafe_allow_html=True)

    if show_diag:
        with st.expander("System Logs"):
            st.write(st.session_state.diags)