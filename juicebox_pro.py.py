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

st.markdown(
    """
<style>
    .grade-a { background-color: #22c55e; color: white; padding: 4px 10px; border-radius: 20px; font-weight: 700; }
    .grade-b { background-color: #eab308; color: white; padding: 4px 10px; border-radius: 20px; font-weight: 700; }
    .grade-c { background-color: #ef4444; color: white; padding: 4px 10px; border-radius: 20px; font-weight: 700; }

    .card { border: 1px solid #e2e8f0; border-radius: 15px; padding: 20px; background: white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.06); }

    .juice-val { color: #16a34a; font-size: 28px; font-weight: 800; margin: 0; }
    .muted { color: #64748b; font-size: 12px; }
</style>
""",
    unsafe_allow_html=True,
)

# -------------------------------------------------
# 2. HELPERS
# -------------------------------------------------
@st.cache_data(ttl=300)
def get_price(ticker: str) -> float | None:
    """Robust last price fetch."""
    try:
        tk = yf.Ticker(ticker)
        # fast_info is fast but sometimes missing/None
        fi = getattr(tk, "fast_info", None)
        if fi and fi.get("last_price"):
            return float(fi["last_price"])
    except Exception:
        pass

    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period="5d", interval="1d")
        if hist is not None and not hist.empty:
            return float(hist["Close"].dropna().iloc[-1])
    except Exception:
        pass

    return None


def mid_price(row) -> float:
    """Use mid if bid/ask exist, else fallback to lastPrice."""
    bid = row.get("bid", np.nan)
    ask = row.get("ask", np.nan)
    lastp = row.get("lastPrice", np.nan)

    if pd.notna(bid) and pd.notna(ask) and ask > 0:
        m = (float(bid) + float(ask)) / 2.0
        # if spread is insane, fallback
        if m > 0:
            return m

    if pd.notna(lastp) and float(lastp) > 0:
        return float(lastp)

    return 0.0


def grade_from_cushion(cushion_pct: float) -> str:
    if cushion_pct >= 12:
        return "🟢 A"
    if cushion_pct >= 7:
        return "🟡 B"
    return "🔴 C"


# -------------------------------------------------
# 3. SIDEBAR
# -------------------------------------------------
with st.sidebar:
    st.header("🧃 Juice Settings")

    total_acc = st.number_input("Account Value ($)", value=10000, min_value=0, step=500)
    weekly_goal = st.number_input("Weekly Goal ($)", value=150, min_value=0, step=10)

    max_safe = total_acc * 0.03
    if weekly_goal > max_safe and total_acc > 0:
        st.warning(f"⚠️ High Risk: Goal exceeds 3% of account (${max_safe:,.0f}).")

    st.divider()

    strategy = st.selectbox(
        "Strategy",
        ["Deep ITM Covered Call", "ATM Covered Call", "Cash Secured Put"],
    )

    user_cushion = 0
    if strategy == "Deep ITM Covered Call":
        user_cushion = st.slider("Min ITM Cushion % (strike below price)", 5, 25, 10)

    st.divider()

    show_diagnostics = st.checkbox("Show scan diagnostics", value=False)

    tickers = ["AAPL", "NVDA", "AMD", "TSLA", "PLTR", "SOXL", "TQQQ", "SPY", "QQQ", "BITX"]


# -------------------------------------------------
# 4. SCANNER ENGINE
# -------------------------------------------------
def scan_ticker(ticker: str, strategy_type: str, target_goal: float, cushion_limit: float, account_total: float):
    """
    Returns best option candidate dict for this ticker, else None.
    - Calls: juice = EXTRINSIC only (premium - intrinsic)
    - CSP: juice = premium
    """
    diag = []

    try:
        price = get_price(ticker)
        if price is None or price <= 0:
            diag.append("no_price")
            return (None, (ticker, diag))

        tk = yf.Ticker(ticker)
        opts = getattr(tk, "options", None)

        if not opts:
            diag.append("no_options_chain")
            return (None, (ticker, diag))

        expirations = opts[:2]  # nearest 2 expirations
        best = None

        for exp in expirations:
            try:
                chain = tk.option_chain(exp)
            except Exception:
                diag.append(f"bad_chain:{exp}")
                continue

            is_put = (strategy_type == "Cash Secured Put")
            df = chain.puts.copy() if is_put else chain.calls.copy()
            if df.empty:
                diag.append(f"empty_chain:{exp}")
                continue

            # Pick strike candidate
            if strategy_type == "Deep ITM Covered Call":
                # strike must be BELOW price by at least cushion_limit%
                cutoff = price * (1 - cushion_limit / 100.0)
                matches = df[df["strike"] <= cutoff].copy()
                if matches.empty:
                    diag.append(f"no_deep_itm:{exp}")
                    continue
                # choose the highest strike under cutoff (closest to price while still deep ITM)
                matches = matches.sort_values_
