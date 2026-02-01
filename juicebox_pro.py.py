import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import urllib.request
import numpy as np
from scipy.stats import norm
import plotly.graph_objects as go

# --- 1. SETUP ---
st.set_page_config(page_title="Income Bot Pro", page_icon="📈", layout="wide")

@st.cache_data
def get_sp500_tickers():
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        table = pd.read_html(response.read())
    return table[0]['Symbol'].str.replace('.', '-', regex=False).tolist()

PENNY_WATCHLIST = ['SOFI', 'IREN', 'AAL', 'F', 'T', 'BBAI', 'LUNR', 'ACHR', 'JOBY', 'PLUG']
LEVERAGED_ETFS = ['TQQQ', 'SQQQ', 'SOXL', 'SOXS', 'UPRO', 'TNA', 'FNGU', 'LABU']

if 'trade_history' not in st.session_state:
    st.session_state.trade_history = []
if 'last_results' not in st.session_state:
    st.session_state.last_results = None

# --- 2. SIDEBAR ---
with st.sidebar:
    st.title("Institutional Settings")
    page = st.radio("Navigation", ["🔍 Income Scanner", "📊 My Earnings Tracker"])
    st.divider()
    capital = st.number_input("Trading Capital ($)", value=4500, step=500)
    strategy_type = st.selectbox("Strategy Type", ["Cash-Secured Put", "Covered Call"])
    aggressive_mode = st.toggle("🔥 Aggressive Mode", value=False)
    penny_mode = st.toggle("💰 Penny Stock Mode ($2-$20)", value=True)
    leveraged_mode = st.toggle("🚀 Include 2x/3x ETFs", value=True)
    target_weekly = st.number_input("Weekly Income Goal ($)", value=100, step=25)
    max_days = st.slider("Max Days to Expiration", 7, 45, 14)

# --- 3. MATH ---
def calculate_pop(price, strike, days, iv, strategy):
    if iv == 0 or days == 0: return 0.5
    t = max(days, 1) / 365
    d2 = (np.log(price / strike) + (-0.5 * iv**2) * t) / (iv * np.sqrt(t))
    prob_itm = norm.cdf(d2)
    return (1 - prob_itm) if strategy == "Cash-Secured Put" else prob_itm

# ---------------------------------------------------------
# PAGE 1: SCANNER
# ---------------------------------------------------------
if page == "🔍 Income Scanner":
    st.title("🔍 Pro Scanner with Strike Visualization")
    
    ticker_list = PENNY_WATCHLIST if penny_mode else get_sp500_tickers()[:100]
    if leveraged_mode:
        ticker_list = list(set(ticker_list + LEVERAGED_ETFS))
    
    if st.button("Run Global Scan 🔍"):
        results = []
        prog = st.progress(0); status = st.empty()
        
        for i, t in enumerate(ticker_list):
            prog.progress((i + 1) / len(ticker_list))
            status.text(f"Analyzing {t}...")
            try:
                stock = yf.Ticker(t); price = float(stock.fast_info['lastPrice'])
                if penny_mode and (price < 2.0 or price > 20.0): continue
                
                exp = stock.options[0]; chain = stock.option_chain(exp)
                days_to_exp = (datetime.strptime(exp, '%Y-%m-%d') - datetime.now()).days
                
                if strategy_type == "Cash-Secured Put":
                    data = chain.puts; buffer = 0.99 if aggressive_mode else 0.95
                    df_f = data[(data['strike'] * 100 <= capital) & (data['strike'] < price * buffer)]
                    match = df_f.iloc[-1] if not df_f.empty else None
                else:
                    data = chain.calls; buffer = 1.01 if aggressive_mode else 1.05
                    df_f = data[(data['strike'] * 100 <= capital) & (data['strike'] > price * buffer)]
                    match = df_f.iloc[0] if not df_f.empty else None

                if match is not None:
                    bid_price = float(match['bid'])
                    prem = bid_price * 100
                    if prem > 5:
                        qty = int(np.ceil(target_weekly / prem))
                        total_cost = float(qty * match['strike'] * 100)
                        if total_cost <= capital:
                            pop = calculate_pop(price, float(match['strike']), days_to_exp, float(match.get('impliedVolatility', 0.4)), strategy_type)
                            results.append({
                                "Ticker": t, "Price": round(price, 2), "Strike": float(match['strike']),
                                "Premium/Share": f"${bid_price:.2f}", "Win Prob": f"{pop*100:.1f}%",
                                "Contracts": qty, "Total Pay": f"${prem * qty:.2f}", 
                                "Weekly Goal %": f"{(prem * qty / capital)*100:.2f}%"
                            })
            except: continue
        status.empty(); prog.empty()
        st.session_state.last_results = results

    if st.session_state.last_results:
        df = pd.DataFrame(st.session_state.last_results).sort_values("Weekly Goal %", ascending=False)
        st.success(f"Found {len(df)} setups!")
        st.dataframe(df, use_container_width=True)
        
        st.divider()
        col_chart, col_log = st.columns([2, 1])
        
        with col_chart:
            st.subheader("🕯️ Chart with Strike & Premium")
            chart_ticker = st.selectbox("View Technicals:", df['Ticker'].tolist())
            if chart_ticker:
                # Get the specific data for the selected ticker
                row = df[df['Ticker'] == chart_ticker].iloc[0]
                strike_price = row['Strike']
                premium_val = row['Premium/Share']
                
                c_data = yf.download(chart_ticker, period="3mo", interval="1d", auto_adjust=True)
                close_prices = c_data['Close'].squeeze()
                sma = close_prices.rolling(20).mean()
                std = close_prices.rolling(20).std()
                
                fig = go.Figure()
                # Candlesticks
                fig.add_trace(go.Candlestick(x=c_data.index, open=c_data['Open'].squeeze(), high=c_data['High'].squeeze(), low=c_data['Low'].squeeze(), close=c_data['Close'].squeeze(), name='Price'))
                
                # Bollinger Bands
                fig.add_trace(go.Scatter(x=c_data.index, y=sma + (2*std), name='Upper Band', line=dict(color='rgba(173,216,230,0.3)')))
                fig.add_trace(go.Scatter(x=c_data.index, y=sma - (2*std), name='Lower Band', line=dict(color='rgba(173,216,230,0.3)'), fill='tonexty'))
                
                # --- NEW: STRIKE PRICE LINE ---
                fig.add_hline(y=strike_price, line_dash="dash", line_color="green" if strategy_type == "Cash-Secured Put" else "red", 
                              annotation_text=f"STRIKE: ${strike_price} (Premium: {premium_val})", annotation_position="bottom right")

                fig.update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)

        with col_log:
            st.subheader("📝 Tracker Log")
            with st.form("log_form"):
                pick = st.selectbox("Log to Snowball:", df['Ticker'].tolist())
                if st.form_submit_button("Confirm & Save"):
                    row_to_save = df[df['Ticker'] == pick].iloc[0]
                    clean_income = float(row_to_save['Total Pay'].replace('$', ''))
                    st.session_state.trade_history.append({"Date": datetime.now().strftime("%Y-%m-%d"), "Ticker": row_to_save['Ticker'], "Income": clean_income})
                    st.toast(f"Logged ${clean_income}!")

# ---------------------------------------------------------
# PAGE 2: TRACKER
# ---------------------------------------------------------
elif page == "📊 My Earnings Tracker":
    st.title("📊 The Wealth Snowball")
    if st.session_state.trade_history:
        df_h = pd.DataFrame(st.session_state.trade_history)
        total = df_h['Income'].sum()
        st.metric("Total Income Collected", f"${total:.2f}")
        st.line_chart(df_h.set_index('Date')['Income'].cumsum())
        st.table(df_h)
    else:
        st.warning("No trades logged yet!")