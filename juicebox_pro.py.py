import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor

# -------------------------------------------------
# 1) APP SETUP & STYLING
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
# 2) HELPERS
# -------------------------------------------------
@st.cache_data(ttl=300)
def get_price(ticker: str) -> float | None:
    """Robust price fetch."""
    try:
        tk = yf.Ticker(ticker)
        fi = getattr(tk, "fast_info", None)
        if fi and fi.get("last_price"):
            p = float(fi["last_price"])
            return p if p > 0 else None
    except Exception:
        pass

    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period="5d", interval="1d")
        if hist is not None and not hist.empty:
            p = float(hist["Close"].dropna().iloc[-1])
            return p if p > 0 else None
    except Exception:
        pass

    return None


def mid_price(row: pd.Series) -> float:
    """Use mid (bid/ask) if available; else lastPrice."""
    bid = row.get("bid", np.nan)
    ask = row.get("ask", np.nan)
    lastp = row.get("lastPrice", np.nan)

    if pd.notna(bid) and pd.notna(ask) and float(ask) > 0:
        m = (float(bid) + float(ask)) / 2.0
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


def explain_qualifies(strategy_type: str, price: float, strike: float, prem: float, cushion_pct: float) -> str:
    if strategy_type == "Cash Secured Put":
        return f"Put strike is below/near price and you collect premium. Cushion is {cushion_pct:.2f}% to strike."
    if strategy_type == "Deep ITM Covered Call":
        return f"Call strike is deep ITM (below price), adding downside cushion of {cushion_pct:.2f}% to strike."
    return f"Call strike is closest to current price, aiming for max premium with cushion of {cushion_pct:.2f}% to strike."


# -------------------------------------------------
# 3) SIDEBAR
# -------------------------------------------------
with st.sidebar:
    st.header("🧃 Juice Settings")

    total_acc = st.number_input("Account Value ($)", value=10000, min_value=0, step=500)
    weekly_goal = st.number_input("Weekly Goal ($)", value=150, min_value=0, step=10)

    max_safe = total_acc * 0.03
    if total_acc > 0 and weekly_goal > max_safe:
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
# 4) SCANNER ENGINE
# -------------------------------------------------
def scan_ticker(ticker: str, strategy_type: str, target_goal: float, cushion_limit: float, account_total: float):
    """
    Returns: (best_candidate_dict_or_None, (ticker, diag_list))
    Calls: juice = EXTRINSIC only (premium - intrinsic)
    CSP:  juice = premium
    """
    diag: list[str] = []

    try:
        price = get_price(ticker)
        if price is None:
            diag.append("no_price")
            return None, (ticker, diag)

        tk = yf.Ticker(ticker)
        opts = getattr(tk, "options", None)
        if not opts:
            diag.append("no_options_chain")
            return None, (ticker, diag)

        expirations = opts[:2]  # nearest 2 expirations
        best = None

        for exp in expirations:
            try:
                chain = tk.option_chain(exp)
            except Exception as e:
                diag.append(f"bad_chain:{exp}")
                diag.append(str(e))
                continue

            is_put = (strategy_type == "Cash Secured Put")
            df = (chain.puts.copy() if is_put else chain.calls.copy())
            if df is None or df.empty:
                diag.append(f"empty_chain:{exp}")
                continue

            # pick a strike
            if strategy_type == "Deep ITM Covered Call":
                cutoff = price * (1 - cushion_limit / 100.0)
                matches = df[df["strike"] <= cutoff]
                if matches.empty:
                    diag.append(f"no_deep_itm:{exp}")
                    continue
                pick = matches.sort_values("strike", ascending=False).iloc[0]

            elif strategy_type == "ATM Covered Call":
                temp = df.copy()
                temp["diff"] = (temp["strike"] - price).abs()
                pick = temp.sort_values("diff", ascending=True).iloc[0]

            else:
                # CSP: prefer strike <= price (slightly OTM)
                otm = df[df["strike"] <= price].copy()
                if otm.empty:
                    temp = df.copy()
                    temp["diff"] = (temp["strike"] - price).abs()
                    pick = temp.sort_values("diff", ascending=True).iloc[0]
                else:
                    otm["diff"] = (otm["strike"] - price).abs()
                    pick = otm.sort_values("diff", ascending=True).iloc[0]

            strike = float(pick["strike"])
            prem = float(mid_price(pick))

            if prem <= 0:
                diag.append(f"no_premium:{exp}")
                continue

            # income math
            if not is_put:
                intrinsic = max(price - strike, 0.0)
                extrinsic = max(prem - intrinsic, 0.0)
                juice_per_contract = extrinsic * 100.0
                collateral_per_contract = price * 100.0
                cushion_pct = max((price - strike) / price * 100.0, 0.0)
            else:
                juice_per_contract = prem * 100.0
                collateral_per_contract = strike * 100.0
                cushion_pct = max((price - strike) / price * 100.0, 0.0)

            if juice_per_contract <= 0:
                diag.append(f"zero_juice:{exp}")
                continue

            # sizing
            contracts = int(np.ceil(target_goal / juice_per_contract)) if target_goal > 0 else 1
            contracts = max(1, contracts)

            total_collateral = collateral_per_contract * contracts
            if account_total > 0 and total_collateral > account_total:
                diag.append(f"too_expensive:{exp}")
                continue

            roi_pct = (juice_per_contract / collateral_per_contract) * 100.0 if collateral_per_contract > 0 else 0.0
            grade = grade_from_cushion(cushion_pct)

            candidate = {
                "Ticker": ticker,
                "Strategy": strategy_type,
                "Expiration": exp,
                "Grade": grade,
                "Price": round(price, 2),
                "Strike": round(strike, 2),
                "Prem (mid)": round(prem, 2),
                "Juice/Con ($)": round(juice_per_contract, 2),
                "Contracts": int(contracts),
                "Total Juice ($)": round(juice_per_contract * contracts, 2),
                "Cushion %": round(cushion_pct, 2),
                "ROI %": round(roi_pct, 2),
                "Collateral ($)": round(total_collateral, 2),
                "Why qualifies": explain_qualifies(strategy_type, price, strike, prem, cushion_pct),
            }

            # choose best: higher ROI, tie-breaker higher cushion
            if best is None:
                best = candidate
            else:
                if (candidate["ROI %"] > best["ROI %"]) or (
                    candidate["ROI %"] == best["ROI %"] and candidate["Cushion %"] > best["Cushion %"]
                ):
                    best = candidate

        if best is None:
            return None, (ticker, diag)

        return best, (ticker, diag)

    except Exception as e:
        diag.append("exception")
        diag.append(str(e))
        return None, (ticker, diag)


# -------------------------------------------------
# 5) UI
# -------------------------------------------------
st.title("🧃 JuiceBox Pro")

run = st.button("RUN GENERATIONAL SCAN ⚡", use_container_width=True)

if run:
    results = []
    diags = {}

    with ThreadPoolExecutor(max_workers=10) as ex:
        out = list(ex.map(lambda t: scan_ticker(t, strategy, weekly_goal, user_cushion, total_acc), tickers))

    for best, (t, diag) in out:
        diags[t] = diag
        if best:
            results.append(best)

    st.session_state.results = results
    st.session_state.diags = diags

if "results" in st.session_state:
    results = st.session_state.results
    df = pd.DataFrame(results)

    if df.empty:
        st.warning("No qualifying trades found with your settings.")
    else:
        cols = [
            "Ticker",
            "Grade",
            "Strategy",
            "Price",
            "Strike",
            "Expiration",
            "Prem (mid)",
            "Juice/Con ($)",
            "Contracts",
            "Total Juice ($)",
            "Cushion %",
            "ROI %",
            "Collateral ($)",
            "Why qualifies",
        ]
        df = df[cols].sort_values(["Grade", "ROI %"], ascending=[True, False])

        st.caption("Click a row to load the chart + trade card.")
        event = st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            selection_mode="single-row",
            on_select="rerun",
        )

        selected_row = None
        try:
            if event and hasattr(event, "selection") and event.selection.rows:
                selected_row = df.iloc[event.selection.rows[0]]
        except Exception:
            selected_row = None

        if selected_row is not None:
            st.divider()
            col1, col2 = st.columns([2, 1])

            with col1:
                components.html(
                    f"""
                    <div id="tradingview_chart" style="height:450px;"></div>
                    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
                    <script type="text/javascript">
                    new TradingView.widget({{
                      "autosize": true,
                      "symbol": "{selected_row['Ticker']}",
                      "interval": "D",
                      "timezone": "Etc/UTC",
                      "theme": "light",
                      "style": "1",
                      "locale": "en",
                      "toolbar_bg": "#f1f3f6",
                      "enable_publishing": false,
                      "hide_side_toolbar": false,
                      "allow_symbol_change": true,
                      "container_id": "tradingview_chart",
                      "studies": ["BB@tv-basicstudies"]
                    }});
                    </script>
                    """,
                    height=460,
                )

            grade_letter = str(selected_row["Grade"])[-1].lower()

            with col2:
                st.markdown(
                    f"""
                    <div class="card">
                        <h3>{selected_row['Ticker']} <span class="grade-{grade_letter}">{selected_row['Grade']}</span></h3>
                        <p class="juice-val">${float(selected_row['Total Juice ($)']):,.2f} Total Juice</p>
                        <hr>
                        <b>Strategy:</b> {selected_row['Strategy']}<br>
                        <b>Expiration:</b> {selected_row['Expiration']}<br>
                        <b>Contracts:</b> {int(selected_row['Contracts'])}<br>
                        <b>Strike:</b> ${selected_row['Strike']}<br>
                        <b>Premium (mid):</b> ${selected_row['Prem (mid)']}<br>
                        <b>Juice / contract:</b> ${float(selected_row['Juice/Con ($)']):,.2f}<br>
                        <b>Cushion:</b> {selected_row['Cushion %']}%<br>
                        <b>ROI:</b> {selected_row['ROI %']}%<br>
                        <b>Collateral est.:</b> ${float(selected_row['Collateral ($)']):,.0f}<br>
                        <hr>
                        <b>Why this qualifies</b><br>
                        <span class="muted">{selected_row['Why qualifies']}</span>
                        <p class="muted" style="margin-top:10px;">
                          Calls: “juice” = extrinsic only (true income). Intrinsic is not counted as income.
                        </p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    if show_diagnostics and "diags" in st.session_state:
        st.divider()
        st.subheader("Diagnostics (why tickers failed)")
        diag_rows = [{"Ticker": t, "Notes": ", ".join(st.session_state.diags.get(t, []))} for t in tickers]
        st.dataframe(pd.DataFrame(diag_rows), use_container_width=True, hide_index=True)
