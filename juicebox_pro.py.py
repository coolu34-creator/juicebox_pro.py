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
    .juice-val {color:#16a34a;font-size:32px;font-weight:800;margin:5px 0;}
    .stButton>button {border-radius:12px;font-weight:700;height:3em;background-color:#16a34a !important; color: white !important;}
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# 2. HELPERS
# -------------------------------------------------
@st.cache_data(ttl=300)
def get_price(t):
    try:
        tk = yf.Ticker(t)
        # Fast info check
        fi = getattr(tk, "fast_info", None)
        if fi and "last_price" in fi: return float(fi["last_price"])
    except: pass
    try:
        hist = yf.Ticker(t).history(period="1d")
        if not hist.empty: return float(hist["Close"].iloc[-1])
    except: pass
    return None

def mid_price(row):
    bid, ask, lastp = row.get("bid"), row.get("ask"), row.get("lastPrice")
    if pd.notna(bid) and pd.notna(ask) and ask > 0: return (bid + ask) / 2
    return float(lastp) if pd.notna(lastp) else 0

def get_grade(total_ret):
    if total_ret >= 6: return "🟢 A"
    if total_ret >= 3: return "🟡 B"
    return "🔴 C"

# -------------------------------------------------
# 3. SIDEBAR & SETTINGS
# -------------------------------------------------
with st.sidebar:
    st.header("🧃 Configuration")
    acct = st.number_input("Account Value ($)", 1000, 1000000, 10000, step=500)
    goal = st.number_input("Weekly Goal ($)", 10, 50000, 150, step=10)
    price_range = st.slider("Stock Price Range ($)", 1, 500, (5, 150))
    
    st.divider()
    default_ticks = "SOFI, PLUG, LUMN, OPEN, BBAI, CLOV, MVIS, MPW, PLTR, AAL, F, SNAP, PFE, NIO, HOOD, RKT, BAC, KVUE, T, VZ, AAPL, AMD, TSLA, PYPL, KO, O, TQQQ, SOXL, BITO, C, GM, DAL, UBER, MARA, RIOT, COIN, DKNG, LCID, AI, GME, AMC, BB, PATH, U, SQ, SHOP, NU, RIVN, GRAB, SE, CCL, NCLH, RCL, SAVE, JBLU, UAL, LUV, MAR, HLT, MGM, WYNN, PENN, TLRY, CGC, CRON, ACB, MSOS, CAN, HUT, HIVE, CLSK, BTBT, WULF, SDIG, IREN, CIFR, BITF, GCT, PDD, BABA, JD, LI, XPEV, BIDU, FUTU, TME, VIPS, IQ, EDU, TAL, GOTU, NET, CRWD, OKTA, ZS, DDOG, SNOW, MDB, TEAM, ASAN, MOND, SMAR, ESTC, SPLK, NTNX, BOX, DBX, DOCU, ZM, PINS, ETSY, EBAY, DASH, ROKU, W, CHWY, CVNA, BYND, EXPE, BKNG, ABNB, LYFT, ARM, AVGO, MU, INTC, TXN, ADI, MCHP, ON, NXPI, QRVO, SWKS, TER, LRCX, AMAT, KLAC, ASML, TSM, GFS, WDC, STX, MP, ALB, SQM, LAC, CHPT, BLNK, EVGO, BE, FCEL, RUN, NOVA, ENPH, SEDG, FSLR, CSIQ, JKS, DQ, PLD, AMT, CCI, EQIX, DLR, WY, PSA, EXR, CUBE, IRM, VICI, GLPI, STAG, EPR, AGNC, NLY, CMCSA, DIS, NFLX, PARA, WBD, FOXA, SIRI, FUBO, SPOT, BOIL, UNG"
    text = st.text_area("Ticker Watchlist", value=default_ticks, height=200)
    tickers = sorted({t.upper() for t in text.replace(",", " ").split() if t.strip()})

# -------------------------------------------------
# 4. SCANNER LOGIC (STANDARD COVERED CALL)
# -------------------------------------------------
def scan(t):
    try:
        price = get_price(t)
        if not price or not (price_range[0] <= price <= price_range[1]): return None, (t, ["Range Out"])
        
        tk = yf.Ticker(t)
        if not tk.options: return None, (t, ["No Options"])

        best = None
        # Focus on the nearest expiration (usually 7-35 days)
        for exp in tk.options[:2]:
            chain = tk.option_chain(exp)
            df = chain.calls
            if df.empty: continue

            # Filter for OTM strikes (Above Current Price)
            otm_df = df[df["strike"] > price].copy()
            if otm_df.empty: continue
            
            # Pick the nearest OTM strike
            pick = otm_df.sort_values("strike", ascending=True).iloc[0]
            strike = float(pick["strike"])
            prem = mid_price(pick)
            
            if prem <= 0: continue

            # ROI CALCULATIONS
            juice_per_con = prem * 100
            collateral_per_con = price * 100
            
            yield_pct = (juice_per_con / collateral_per_con) * 100
            upside_pct = ((strike - price) / price) * 100
            total_return = yield_pct + upside_pct

            # Goal Logic
            contracts = max(1, int(np.ceil(goal / juice_per_con)))
            if (contracts * collateral_per_con) > acct:
                # If too expensive, scale down to max possible contracts
                contracts = int(acct // collateral_per_con)
            
            if contracts < 1: continue

            row = {
                "Ticker": t, 
                "Grade": get_grade(total_return), 
                "Price": round(price, 2), 
                "Strike": round(strike, 2), 
                "Expiration": exp, 
                "Juice/Con": round(juice_per_con, 2), 
                "Contracts": contracts, 
                "Total Juice": round(juice_per_con * contracts, 2), 
                "Yield %": round(yield_pct, 2), 
                "Upside %": round(upside_pct, 2), 
                "Total Return %": round(total_return, 2),
                "Collateral": round(contracts * collateral_per_con, 0)
            }
            if not best or total_return > best["Total Return %"]: 
                best = row
                
        return (best, (t, [])) if best else (None, (t, ["No Match"]))
    except Exception as e: return None, (t, [str(e)])

# -------------------------------------------------
# 5. UI & SCAN RUNNER
# -------------------------------------------------
st.title("🧃 JuiceBox Pro")
st.caption("Standard Covered Call Strategy: Yield + Appreciation")

if st.button("RUN SCAN ⚡", use_container_width=True):
    results, diags = [], {}
    with st.spinner(f"Scanning {len(tickers)} tickers..."):
        with ThreadPoolExecutor(max_workers=10) as ex:
            out = list(ex.map(scan, tickers))
    for r, (t, d) in out:
        diags[t] = d
        if r: results.append(r)
    st.session_state.results = results
    st.session_state.diags = diags

# -------------------------------------------------
# 6. DISPLAY
# -------------------------------------------------
if "results" in st.session_state:
    df = pd.DataFrame(st.session_state.results)
    if df.empty: 
        st.warning("No matches. Try expanding your price range or account value.")
    else:
        # Show Summary Table
        df = df.sort_values("Total Return %", ascending=False)
        sel = st.dataframe(
            df[["Ticker", "Grade", "Price", "Strike", "Yield %", "Total Return %", "Total Juice"]], 
            use_container_width=True, 
            hide_index=True, 
            selection_mode="single-row", 
            on_select="rerun"
        )
        
        # Detailed Breakdown
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
                g_char = r["Grade"][-1].lower()
                st.markdown(f"""
                <div class="card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <h2 style="margin:0;">{r['Ticker']}</h2>
                        <span class="grade-{g_char}">{r['Grade']}</span>
                    </div>
                    <p style="margin:10px 0 0 0; font-size:14px; color:#6b7280;">Potential Total Return</p>
                    <div class="juice-val">{r['Total Return %']}%</div>
                    <hr>
                    <div style="display:flex; justify-content:space-between;">
                        <span><b>Yield (Cash):</b></span>
                        <span style="color:#16a34a; font-weight:700;">{r['Yield %']}%</span>
                    </div>
                    <div style="display:flex; justify-content:space-between;">
                        <span><b>Max Upside:</b></span>
                        <span style="color:#16a34a; font-weight:700;">{r['Upside %']}%</span>
                    </div>
                    <hr>
                    <b>Stock Price:</b> ${r['Price']}<br>
                    <b>Sell Strike:</b> ${r['Strike']}<br>
                    <b>Exp Date:</b> {r['Expiration']}<br>
                    <hr>
                    <b>Contracts:</b> {r['Contracts']}<br>
                    <b>Total Premium:</b> ${r['Total Juice']:,.2f}<br>
                    <b>Req. Collateral:</b> ${r['Collateral']:,.0f}
                </div>
                """, unsafe_allow_html=True)