import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

def run_juice_scanner(ticker_symbol):
    print(f"--- 🕵️ Scanning {ticker_symbol} for ITM Deals ---")
    
    # 1. Get Stock Data
    stock = yf.Ticker(ticker_symbol)
    try:
        # Get the very latest price
        current_price = stock.fast_info['last_price']
    except:
        return "Error: Could not find that stock symbol!"

    # 2. Get Expiration Dates
    expiry_dates = stock.options
    if not expiry_dates:
        return "No options found."
    
    # We'll scan the closest expiration (usually ~30 days)
    chain = stock.option_chain(expiry_dates[0])
    calls = chain.calls

    # 3. Filter for 'In-the-Money' (Strike is BELOW current price)
    itm_deals = calls[calls['strike'] < current_price].copy()

    # --- CALCULATE THE "JUICE" ---
    # Break-Even: Price you effectively paid (Stock Price - Premium)
    itm_deals['break_even'] = current_price - itm_deals['bid']
    
    # Safety Net: How many dollars the stock can drop before you lose money
    itm_deals['safety_net_$'] = current_price - itm_deals['break_even']
    
    # Profit: (Strike Price + Premium Received) - Current Stock Price
    itm_deals['max_profit_$'] = (itm_deals['strike'] + itm_deals['bid']) - current_price
    
    # Allowance %: Your "Reward Score" for this trade
    itm_deals['allowance_%'] = (itm_deals['max_profit_$'] / current_price) * 100

    # 4. THE GRADING SYSTEM (Middle School Friendly)
    def assign_grade(row):
        if row['allowance_%'] > 2.5: return "💎 A+ (High Reward)"
        if row['allowance_%'] > 1.0: return "✅ B (Solid Deal)"
        if row['allowance_%'] > 0:   return "⚠️ C (Low Reward)"
        return "❌ F (Bad Deal)"

    itm_deals['Grade'] = itm_deals.apply(assign_grade, axis=1)

    # 5. Clean & Display
    final_results = itm_deals[['strike', 'bid', 'safety_net_$', 'allowance_%', 'Grade']]
    return final_results.sort_values(by='allowance_%', ascending=False)

# --- EXAMPLE EXECUTION ---
# You can change 'AAPL' to 'XOM' or 'COST' which you've tracked before!
print(run_juice_scanner("AAPL").head(10))