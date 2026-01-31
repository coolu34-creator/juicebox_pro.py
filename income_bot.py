import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
from datetime import datetime
import numpy as np
from scipy.stats import norm

# -------------------------------------------------
# 1. APP SETUP & LIGHT THEME STYLING
# -------------------------------------------------
st.set_page_config(page_title="Income Bot Pro 2026 (Kid-Simple Bands)", page_icon="📈", layout="wide")

st.markdown("""
<style>
    .main { background-color: #f6f7fb; }
    section[data-testid="stSidebar"] { background-color: #ffffff; border-right: 1px solid #e5e7eb; }

    div[data-testid="metric-container"] {
        background-color: #ffffff;
        border: 1px solid #d0d7de;
        padding: 18px;
        border-radius: 12px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.06);
    }
    div[data-testid="metric-container"] label {
        color: #111827 !important;
        font-size: 1.05rem !important;
        font-weight: 650 !important;
    }
    div[data-testid="metric-container"] [data-testid="stMetricValue"] {
        color: #0f172a !important;
        font-size: 2.0rem !important;
        font-weight: 750 !important;
    }

    .stDataFrame { border: 1px solid #d0d7de; border-radius: 10px; background: white; }

    .card {
        border: 1px solid #d0d7de;
        border-radius: 12px;
        background: white;
        padding: 14px 16px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.06);
    }
    .big {
        font-size: 28px;
        font-weight: 800;
        margin: 0;
    }
    .small {
        color: #334155;
        margin-top: 6px;
        margin-bottom: 0;
        font-size: 14px;
    }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# 2. TRADINGVIEW EMBED (OPTIONAL VISUAL)
# -------------------------------------------------
def guess_exchange_prefix(ticker: str) -> str:
    """
    Best-effort exchange prefix for TradingView.
    If we can't detect, default to NASDAQ.
    """
    try:
        exch = (yf.Ticker(ticker).fast_info.get("exchange") or "").upper()
        if "NYQ" in exch or "NYSE" in exch:
            return "NYSE"
        if "NMS" in exch or "NASDAQ" in exch:
            return "NASDAQ"
        if "ASE" in exch or "AMEX" in exch:
            return "AMEX"
        return "NASDAQ"
    except:
        return "NASDAQ"

def tradingview_chart(symbol: str, interval: str = "D", height: int = 650, theme: str = "light", style: str = "8"):
    """
    TradingView Advanced Chart widget.
    style:
      0 Bars, 1 Candles, 3 Line, 8 Heikin Ashi, 9 Area
    """
    container_id = f"tv_{abs(hash(symbol + interval + style))}"

    html = f"""
    <div style="border:1px solid #d0d7de;border-radius:12px;overflow:hidden;background:#fff;box-shadow:0 2px 10px rgba(0,0,0,0.06);">
      <div id="{container_id}" style="height:{height}px; width:100%;"></div>
    </div>
    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
    <script type="text/javascript">
      new TradingView.widget({{
        "autosize": true,
        "symbol": "{symbol}",
        "interval": "{interval}",
        "timezone": "America/New_York",
        "theme": "{theme}",
        "style": "{style}",
        "locale": "en",
        "enable_publishing": false,
        "withdateranges": true,
        "hide_side_toolbar": false,
        "allow_symbol_change": true,
        "container_id": "{container_id}"
      }});
    </script>
    """
    components.html(html, height=height + 30, scrolling=False)

# -------------------------------------------------
# 3. DATA + POP CALC
# -------------------------------------------------
EARNINGS_DB = {
    "AAPL": "2026-01-29", "TSLA": "2026-01-28", "PLTR": "2026-02-02",
    "AMD": "2026-02-03", "NVDA": "2026-02-25", "COIN": "2026-02-12",
    "MSFT": "2026-01-27", "GOOGL": "2026-01-30", "AMZN": "2026-02-01"
}

def calculate_pop(price, strike, days, iv, strategy):
    """Estimated Probability of Profit using N(d2)."""
    if iv <= 0 or days <= 0:
        return 0.5
    t = max(days, 1) / 365
    d2 = (np.log(price / strike) + (-0.5 * iv**2) * t) / (iv * np.sqrt(t))
    prob_itm = norm.cdf(d2)
    return (1 - prob_itm) if strategy == "Cash-Secured Put" else prob_itm

@st.cache_data(ttl=3600)
def get_liquid_universe():
    return ["AAPL", "TSLA", "NVDA", "AMD", "PLTR", "SOFI", "MARA", "F", "BAC", "T",
            "CCL", "IREN", "COIN", "RIVN", "GOOGL", "MSFT", "AMZN"]

def check_earnings(ticker, exp_date):
    """
    Returns:
      "✅ Clear" if expiry is before earnings date
      "⚠️ YYYY-MM-DD" if earnings is on/before expiry
      "Clear" if not in DB
    """
    if ticker not in EARNINGS_DB:
        return "Clear"
    earn_dt = datetime.strptime(EARNINGS_DB[ticker], "%Y-%m-%d")
    exp_dt = datetime.strptime(exp_date, "%Y-%m-%d")
    return f"⚠️ {EARNINGS_DB[ticker]}" if exp_dt >= earn_dt else "✅ Clear"

def earnings_risk_flag(earnings_str: str) -> bool:
    return isinstance(earnings_str, str) and earnings_str.startswith("⚠️")

# -------------------------------------------------
# 4. SIDEBAR
# -------------------------------------------------
with st.sidebar:
    st.title("💸 Trading Terminal")
    page = st.radio("Navigation", ["🔍 Deep Scanner", "📊 Wealth Tracker"])
    st.divider()

    capital = st.number_input("Trading Capital ($)", value=5000, step=500)
    strategy_type = st.selectbox("Strategy", ["Cash-Secured Put", "Covered Call"])
    aggressive = st.toggle("🔥 Aggressive Mode", value=False)

    goal_mode = st.radio("Goal Type", ["$ Goal", "% Goal"])
    target_val = st.number_input("Target", value=150.0 if goal_mode == "$ Goal" else 2.5)
    weekly_target = target_val if goal_mode == "$ Goal" else (target_val / 100) * capital
    st.success(f"Goal: ${weekly_target:,.2f} / Week")

    max_days_slider = st.slider("Max Search (Days)", 7, 45, 45)

    st.divider()
    st.caption("Chart Settings")
    tv_interval = st.selectbox("TradingView Interval", ["D", "60", "30", "15", "5"], index=0)
    tv_theme = st.selectbox("TradingView Theme", ["light", "dark"], index=0)

    chart_type = st.selectbox(
        "Chart Type",
        ["Heikin Ashi (smooth)", "Line (simple)", "Bars", "Candles", "Area"],
        index=0
    )
    style_map = {
        "Bars": "0",
        "Candles": "1",
        "Line (simple)": "3",
        "Heikin Ashi (smooth)": "8",
        "Area": "9",
    }
    tv_style = style_map[chart_type]

# -------------------------------------------------
# 5. SCANNER PAGE
# -------------------------------------------------
if page == "🔍 Deep Scanner":
    st.title(f"🔍 Deep Income Scanner (7 - {max_days_slider} Days)")

    if st.button("Start Global Deep Scan 🌐", use_container_width=True):
        universe = get_liquid_universe()
        results = []
        prog = st.progress(0)

        for i, t in enumerate(universe):
            prog.progress((i + 1) / len(universe))
            try:
                stock = yf.Ticker(t)
                price = float(stock.fast_info["lastPrice"])
                if not (2 <= price <= 100):
                    continue

                for exp in stock.options:
                    days_to_exp = (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days
                    if 7 <= days_to_exp <= max_days_slider:
                        chain = stock.option_chain(exp)

                        buffer = 0.98 if aggressive else 0.92
                        data = chain.puts if strategy_type == "Cash-Secured Put" else chain.calls

                        if strategy_type == "Cash-Secured Put":
                            df_f = data[(data["strike"] * 100 <= capital) & (data["strike"] < price * buffer)]
                            match = df_f.iloc[-1] if not df_f.empty else None
                        else:
                            df_f = data[(data["strike"] * 100 <= capital) & (data["strike"] > price * (1 / buffer))]
                            match = df_f.iloc[0] if not df_f.empty else None

                        if match is not None and float(match["bid"]) > 0.05:
                            bid = float(match["bid"])
                            qty = int(np.ceil(weekly_target / (bid * 100)))

                            if (qty * float(match["strike"]) * 100) <= capital:
                                pop = calculate_pop(
                                    price,
                                    float(match["strike"]),
                                    days_to_exp,
                                    float(match.get("impliedVolatility", 0.5)),
                                    strategy_type
                                )
                                income_val = bid * 100 * qty
                                return_pct = (income_val / capital) * 100

                                results.append({
                                    "Ticker": t,
                                    "Price": round(price, 2),
                                    "Strike": float(match["strike"]),
                                    "Expiry": exp,
                                    "Win Prob": f"{pop * 100:.1f}%",
                                    "Contracts": qty,
                                    "Earnings": check_earnings(t, exp),
                                    "Income": f"${income_val:.2f}",
                                    "Return %": f"{return_pct:.2f}%"
                                })
            except:
                continue

        st.session_state.deep_scan = results
        prog.empty()

    if "deep_scan" in st.session_state and st.session_state.deep_scan:
        df = pd.DataFrame(st.session_state.deep_scan)

        df["_ReturnNum"] = df["Return %"].str.replace("%", "", regex=False).astype(float)
        df = df.sort_values("_ReturnNum", ascending=False).drop(columns=["_ReturnNum"]).reset_index(drop=True)

        selection = st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row"
        )

        if selection.selection.rows:
            row = df.iloc[selection.selection.rows[0]]

            # -------------------------------------------------
            # CALC BOLLINGER + KID-SIMPLE SIGNAL (SAFE)
            # -------------------------------------------------
            hist = yf.download(row["Ticker"], period="6mo", interval="1d", auto_adjust=False)

            band_label = "🟡 WAIT"
            band_reason = "not enough data"
            band_action = "wait"
            last_close = lower = upper = mid = None

            if not hist.empty and "Close" in hist.columns:
                hist["MA20"] = hist["Close"].rolling(20).mean()
                hist["STD20"] = hist["Close"].rolling(20).std()
                hist["Upper"] = hist["MA20"] + (hist["STD20"] * 2)
                hist["Lower"] = hist["MA20"] - (hist["STD20"] * 2)

                required_cols = ["Close", "MA20", "Upper", "Lower"]
                if all(col in hist.columns for col in required_cols):
                    valid = hist.dropna(subset=required_cols)

                    if not valid.empty:
                        last = valid.iloc[-1]
                        last_close = float(last["Close"])
                        lower = float(last["Lower"])
                        upper = float(last["Upper"])
                        mid = float(last["MA20"])

                        if last_close <= lower * 1.01:
                            band_label = "🟢 GOOD time to sell a cash-secured put"
                            band_reason = "price is near the bottom band"
                            band_action = "sell a put below the current price"
                        elif last_close < upper * 0.99:
                            band_label = "🟡 WAIT"
                            band_reason = "price is in the middle"
                            band_action = "wait for price to move lower"
                        else:
                            band_label = "🔴 NOT a good time"
                            band_reason = "price is near the top band"
                            band_action = "wait (or use covered calls)"

                        # extra safety: not enough history
                        if len(valid) < 30:
                            band_label = "🟡 WAIT"
                            band_reason = "not enough history yet"
                            band_action = "wait for more data"

            # earnings override for CSP
            earnings_text = row["Earnings"]
            if strategy_type == "Cash-Secured Put" and earnings_risk_flag(earnings_text):
                band_label = "🟡 WAIT (earnings soon)"
                band_reason = f"earnings is coming up: {earnings_text.replace('⚠️ ','')}"
                band_action = "wait until earnings passes"

            st.divider()

            left, right = st.columns([2.2, 1])

            with left:
                st.subheader("📊 Chart")
                exch = guess_exchange_prefix(row["Ticker"])
                tv_symbol = f"{exch}:{row['Ticker']}"
                tradingview_chart(
                    symbol=tv_symbol,
                    interval=tv_interval,
                    theme=tv_theme,
                    style=tv_style,
                    height=650
                )

            with right:
                st.subheader("🟦 Simple Signal")

                st.markdown(f"""
                <div class="card">
                    <p class="big">{band_label}</p>
                    <p class="small">{band_reason}</p>
                    <p class="small"><b>what to do:</b> {band_action}</p>
                </div>
                """, unsafe_allow_html=True)

                st.divider()
                st.subheader("📌 Trade Summary")
                st.write(f"**Ticker:** {row['Ticker']}")
                st.write(f"**Strategy:** {strategy_type}")
                st.write(f"**Price:** ${row['Price']}")
                st.write(f"**Strike:** {row['Strike']}")
                st.write(f"**Expiry:** {row['Expiry']}")
                st.write(f"**Income:** {row['Income']}")
                st.write(f"**Return %:** {row['Return %']}")
                st.write(f"**Earnings:** {row['Earnings']}")

                if last_close is not None:
                    st.divider()
                    st.subheader("📏 Band Numbers")
                    st.write(f"**Close:** ${last_close:,.2f}")
                    st.write(f"**Lower Band:** ${lower:,.2f}")
                    st.write(f"**Middle (SMA20):** ${mid:,.2f}")
                    st.write(f"**Upper Band:** ${upper:,.2f}")

                st.divider()
                c1, c2 = st.columns(2)
                c1.metric("Win Prob", row["Win Prob"])
                c2.metric("Contracts", row["Contracts"])
                st.metric("Earnings Watch", row["Earnings"])

                if st.button("📝 Log This Trade", use_container_width=True):
                    st.session_state.setdefault("history", []).append({
                        "Date": datetime.now().strftime("%Y-%m-%d"),
                        "Ticker": row["Ticker"],
                        "Strategy": strategy_type,
                        "Strike": float(row["Strike"]),
                        "Expiry": row["Expiry"],
                        "Income": float(row["Income"].replace("$", "")),
                        "Band Signal": band_label
                    })
                    st.toast("Trade saved to Tracker!")

# -------------------------------------------------
# 6. TRACKER PAGE
# -------------------------------------------------
elif page == "📊 Wealth Tracker":
    st.title("📊 The Snowball Effect")

    if "history" in st.session_state and st.session_state.history:
        h_df = pd.DataFrame(st.session_state.history)

        st.metric("Total Income Collected", f"${h_df['Income'].sum():,.2f}")

        st.subheader("Income Growth")
        h_df["Date"] = pd.to_datetime(h_df["Date"])
        h_df = h_df.sort_values("Date")
        st.line_chart(h_df.set_index("Date")["Income"].cumsum())

        st.subheader("Trade Log")
        st.dataframe(h_df, use_container_width=True, hide_index=True)
    else:
        st.info("Log a trade from the scanner to see your wealth growth here.")
