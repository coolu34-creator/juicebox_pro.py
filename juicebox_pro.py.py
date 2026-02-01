import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
from datetime import datetime
import numpy as np
from concurrent.futures import ThreadPoolExecutor

# -------------------------------------------------
# 1. APP SETUP
# -------------------------------------------------
st.set_page_config(page_title="JuiceBox Pro", page_icon="🧃", layout="wide")

if 'wealth_history' not in st.session_state:
    st.session_state.wealth_history = pd.DataFrame(columns=[
        "Date", "Ticker", "Grade", "Juice ($)", "Contracts", "Total Juice", "Cushion %"
    ])

# -------------------------------------------------
# 2. SIDEBAR: GOALS & COLLATERAL GUARD
# -------------------------------------------------
with st.sidebar:
    try: st.image("couple.png", use_container_width=True)
    except: st.info("Generational Wealth Mode")
    
    st.subheader("🗓️ Wealth Engine")
    total_acc = st.number_input("Total Account Value ($)", value=10000, step=1000)
    
    # MANUAL WEEKLY GOAL INPUT
    weekly_goal = st.number_input("Weekly Income Goal ($)", value=100, step=50)
    
    # COLLATERAL GUARD LOGIC
    # Standard ITM strategies usually require 100% collateral (Cash or Stock)
    # We estimate a safe 'Yield' is 0.5% - 2% per week. 
    max_safe_goal = total_acc * 0.03 # 3% is a very aggressive ceiling
    
    is_overleveraged = False
    if weekly_goal > max_safe_goal:
        st.error(f"⚠️ **GOAL TOO HIGH**")
        st.warning(f"Based on your ${total_acc:,.0f} account, a ${weekly_goal} goal is unrealistic. You don't have enough collateral to back these trades safely.")
        is_overleveraged = True
    else:
        st.success("✅ Goal is within collateral limits.")

    st.divider()
    strategy = st.selectbox("Strategy", ["Deep ITM Covered Call", "ATM Covered Call", "Cash Secured Put"])
    user_cushion = st.slider("Min ITM Cushion %", 2, 25, 10) if "Deep ITM" in strategy else 0
    selected_sectors = st.multiselect("Sectors", options=["Tech", "Leveraged", "Finance", "Energy"], default=["Tech", "Finance"])

# -------------------------------------------------
# 3. SCANNER ENGINE (With Collateral Validation)
# -------------------------------------------------
def scan_ticker(t, strategy_type, target_goal, cushion_limit, account_total):
    try:
        stock = yf.Ticker(t)
        price = stock.fast_info['last_price']
        
        for exp in stock.options[:3]:
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
            
            # CALCULATE CONTRACTS
            contracts_needed = int(np.ceil(target_goal / juice_per_contract)) if juice_per_contract > 0 else 0
            
            # CALCULATE REQUIRED COLLATERAL
            collateral_req = (price * 100 * contracts_needed) if "Call" in strategy_type else (strike * 100 * contracts_needed)
            
            if collateral_req > account_total:
                return None # Skip tickers that require too much collateral

            return {
                "Ticker": t, "Strike": strike, "Juice/Contract": round(juice_per_contract, 2),
                "Contracts": contracts_needed, "Collateral Req": round(collateral_req, 2),
                "Cushion %": round(((price - (price-prem))/price)*100, 2)
            }
    except: return None

# -------------------------------------------------
# 4. EXECUTION
# -------------------------------------------------
if not is_overleveraged:
    if st.button("RUN GLOBAL SCAN ⚡", use_container_width=True):
        univ = ["AAPL", "AMD", "NVDA", "TSLA", "MSFT", "PLTR", "BAC", "SPY", "QQQ", "SOXL", "TQQQ"]
        with ThreadPoolExecutor(max_workers=10) as ex:
            results = [r for r in ex.map(lambda t: scan_ticker(t, strategy, weekly_goal, user_cushion, total_acc), univ) if r]
        st.session_state.results = results

if "results" in st.session_state:
    st.dataframe(pd.DataFrame(st.session_state.results), use_container_width=True)