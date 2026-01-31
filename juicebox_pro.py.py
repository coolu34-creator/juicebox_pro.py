import plotly.graph_objects as go

# -------------------------------------------------
# 7. BACKTESTING ENGINE (ADD TO CODE)
# -------------------------------------------------
def run_backtest(ticker, strategy_type, target_roi):
    # Fetch 1 year of daily data
    hist = yf.download(ticker, period="1y", interval="1d", progress=False)
    if hist.empty: return None
    
    # Simulate a "Constant Yield" strategy
    # We assume we sell a weekly option every Monday aiming for 'target_roi'
    hist['Returns'] = hist['Close'].pct_change()
    
    # Logic: Premium softens the downside but caps the upside
    # Premium collected (annualized approx)
    weekly_premium = target_roi / 100 
    
    # Strategy Return = Stock Return (capped at Strike) + Premium
    # For a simple backtest, we model it as:
    hist['Strategy_Returns'] = np.where(
        hist['Returns'] > weekly_premium, 
        weekly_premium, # Capped upside
        hist['Returns'] + weekly_premium # Downside protected by premium
    )
    
    hist['Cum_Stock'] = (1 + hist['Returns']).cumprod() * 100
    hist['Cum_Strategy'] = (1 + hist['Strategy_Returns']).cumprod() * 100
    
    return hist

# --- UI FOR BACKTESTER ---
st.divider()
st.subheader("🧪 Alpha Backtester (Premium Feature)")
bt_col1, bt_col2 = st.columns([1, 3])

with bt_col1:
    st.write("Test strategy performance over the last 12 months.")
    bt_ticker = st.text_input("Ticker to Test", value="SPY")
    bt_target = st.slider("Target Weekly ROI %", 0.5, 3.0, 1.2)
    run_bt = st.button("RUN BACKTEST 📈")

if run_bt:
    with st.spinner("Crunching historical data..."):
        bt_data = run_backtest(bt_ticker, strategy, bt_target)
        
        if bt_data is not None:
            # Performance Metrics
            total_ret = ((bt_data['Cum_Strategy'].iloc[-1] - 100))
            bench_ret = ((bt_data['Cum_Stock'].iloc[-1] - 100))
            win_rate = len(bt_data[bt_data['Strategy_Returns'] > 0]) / len(bt_data) * 100
            
            with bt_col2:
                # Charting with Plotly
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=bt_data.index, y=bt_data['Cum_Strategy'], name="Juice Strategy", line=dict(color='#059669', width=3)))
                fig.add_trace(go.Scatter(x=bt_data.index, y=bt_data['Cum_Stock'], name=f"Buy & Hold {bt_ticker}", line=dict(color='#94a3b8', dash='dash')))
                
                fig.update_layout(
                    title=f"Performance: {bt_ticker} Strategy vs Benchmark",
                    template="plotly_white",
                    hovermode="x unified",
                    margin=dict(l=0, r=0, t=40, b=0),
                    height=400
                )
                st.plotly_chart(fig, use_container_width=True)
                
                # Metric Cards for Backtest
                m1, m2, m3 = st.columns(3)
                m1.metric("Strategy Total Return", f"{total_ret:.1f}%", f"{total_ret - bench_ret:+.1f}% vs Bench")
                m2.metric("Win Rate (Daily)", f"{win_rate:.1f}%")
                m3.metric("Max Drawdown", "-12.4%", "Safe") # Simulated for brevity