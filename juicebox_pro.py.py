import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
from datetime import datetime
import numpy as np
from concurrent.futures import ThreadPoolExecutor

# -------------------------------------------------
# 1. APP SETUP & STYLING
# -------------------------------------------------
st.set_page_config(page_title="JuiceBox Pro", page_icon="🧃", layout="wide")

# Custom CSS for Grading Bubbles and Cards
st.markdown("""
<style>
    .grade-a { background-color: #22c55e; color: white; padding: 4px 10px; border-radius: 20px; font-weight: bold; }
    .grade-b { background-color: #eab308; color: white; padding: 4px 10px; border-radius: 20px; font-weight: bold; }
    .grade-c { background-color: #ef4444; color: white; padding: 4px 10px; border-radius: 20px; font-weight: bold; }
    .card { border: 1px solid #e2e8f0; border-radius: 15px; padding: 20px; background: white; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .juice-val { color: #16a34a; font-size: 28px; font-weight: 800; margin: 0; }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# 2. SIDEBAR: GOALS & COLLATERAL GUARD
# -------------------------------------------------
with st.sidebar:
    st.header("🧃 Juice Settings")
    total_acc = st.number_input("Account Value ($)", value=10000)
    weekly_goal = st.number_input("Weekly Goal ($)", value=150)
    
    # Collateral Guard
    max_safe = total_acc * 0.03
    if weekly_goal > max_safe:
        st.warning(f"⚠️ High Risk: Goal exceeds 3% of collateral (${max_safe:,.0f}).")
    
    st.divider()
    strategy = st.selectbox("Strategy", ["Deep ITM Covered Call", "ATM Covered Call", "Cash Secured Put"])
    user_cushion = st.slider("Min ITM Cushion %", 5, 25, 10) if "Deep ITM" in strategy else 0
    
    tickers = ["AAPL", "NVDA", "AMD", "TSLA", "PLTR", "SOXL", "TQQQ", "SPY", "QQQ", "BITX"]

# -------------------------------------------------
# 3. SCANNER ENGINE
# -------------------------------------------------
def scan_ticker(t, strategy_type, target_goal, cushion_limit, account_total):
    try:
        stock = yf.Ticker(t)
        price = stock.fast_info['last_price']
        
        for exp in stock.options[:2]: # Check nearest 2 expirations
            chain = stock.option_chain(exp)
            df = chain.puts if "Put" in strategy_type else chain.calls
            
            if "Deep ITM" in strategy_type:
                match_df = df[df["strike"] < price * (1 - (cushion_limit / 100))]
                if match_df.empty: continue
                match = match_df.sort_values("strike", ascending=False).iloc[0]
            else:
                df["diff"] = abs(df["strike"] - price)
                match = df.sort_values("diff").iloc[0]

            prem = float(match["lastPrice"])
            strike = float(match["strike"])
            juice_per_contract = (prem - max(0, price - strike)) * 100 if "Call" in strategy_type else prem * 100
            contracts = int(np.ceil(target_goal / juice_per_contract)) if juice_per_contract > 0 else 0
            
            collateral = (price * 100 * contracts) if "Call" in strategy_type else (strike * 100 * contracts)
            if collateral > account_total: return None

            cushion = round(((price - (price - prem)) / price) * 100, 1)
            grade = "🟢 A" if cushion > 12 else "🟡 B" if cushion > 7 else "🔴 C"

            return {
                "Ticker": t, "Grade": grade, "Price": round(price, 2), "Strike": strike,
                "Juice/Con": round(juice_per_contract, 2), "Contracts": contracts,
                "Cushion %": cushion, "ROI %": round((juice_per_contract/collateral)*100, 2)
            }
    except: return None

# -------------------------------------------------
# 4. DASHBOARD EXECUTION
# -------------------------------------------------
if st.button("RUN GENERATIONAL SCAN ⚡", use_container_width=True):
    with ThreadPoolExecutor(max_workers=10) as ex:
        results = [r for r in ex.map(lambda t: scan_ticker(t, strategy, weekly_goal, user_cushion, total_acc), tickers) if r]
    st.session_state.results = results

if "results" in st.session_state:
    df = pd.DataFrame(st.session_state.results)
    # Display table with selection
    sel = st.dataframe(df, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")

    if sel.selection.rows:
        row = df.iloc[sel.selection.rows[0]]
        st.divider()
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # BACK: Chart with Bollinger Bands enabled
            components.html(f"""
                <div id="tradingview_chart" style="height:450px;"></div>
                <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
                <script type="text/javascript">
                new TradingView.widget({{
                  "autosize": true, "symbol": "{row['Ticker']}", "interval": "D",
                  "timezone": "Etc/UTC", "theme": "light", "style": "1",
                  "locale": "en", "toolbar_bg": "#f1f3f6", "enable_publishing": false,
                  "hide_side_toolbar": false, "allow_symbol_change": true,
                  "container_id": "tradingview_chart", "studies": ["BB@tv-basicstudies"]
                }});
                </script>
            """, height=460)
            
        with col2:
            st.markdown(f"""
                <div class="card">
                    <h3>{row['Ticker']} <span class="grade-{row['Grade'][-1].lower()}">{row['Grade']}</span></h3>
                    <p class="juice-val">${row['Juice/Con'] * row['Contracts']:,.2f} Total Juice</p>
                    <hr>
                    <b>Contracts to Sell:</b> {row['Contracts']}<br>
                    <b>Strike Price:</b> ${row['Strike']}<br>
                    <b>Cushion:</b> {row['Cushion %']}%<br>
                    <p style="font-size: 12px; color: gray; margin-top:10px;">
                    Ensure strike is below the lower Bollinger Band for maximum safety.</p>
                </div>
            """, unsafe_allow_html=True)