import yfinance as yf
import pandas as pd

def scan_for_itm_deals(ticker_symbol):
    print(f"--- 🕵️ Scanning {ticker_symbol} for the Best Deals ---")
    
    # 1. Get Stock Info
    stock = yf.Ticker(ticker_symbol)
    try:
        current_price = stock.fast_info['last_price']
    except:
        return "Error: Could not find that stock. Check the symbol!"

    # 2. Pick an Expiration Date (Looking ~30 days out is usually best)
    expiry_dates = stock.options
    if not expiry_dates:
        return "No options found."
    
    # We'll use the first available date for this example
    target_expiry = expiry_dates[0]
    chain = stock.option_chain(target_expiry)
    calls = chain.calls

    # 3. Filter for 'In-the-Money' (Strike Price < Current Price)
    # This means the deal is already "started"
    itm_deals = calls[calls['strike'] < current_price].copy()

    # --- THE BRAINS OF THE STRATEGY ---
    
    # Break-Even: Price of stock - Cash friend gives you
    itm_deals['break_even'] = current_price - itm_deals['bid']
    
    # Safety Net: How much can the stock drop before we lose money?
    itm_deals['safety_net_$'] = current_price - itm_deals['break_even']
    
    # The Profit: If the stock stays above the strike price
    itm_deals['max_profit_$'] = (itm_deals['strike'] + itm_deals['bid']) - current_price
    
    # Allowance Score: What is our profit % for this month?
    itm_deals['allowance_%'] = (itm_deals['max_profit_$'] / current_price) * 100

    # 4. THE GRADING SYSTEM (Middle School Edition)
    def assign_grade(row):
        if row['allowance_%'] > 3: return "💎 A+ (High Reward)"
        if row['allowance_%'] > 1.5: return "✅ B (Solid Deal)"
        if row['allowance_%'] > 0: return "⚠️ C (Low Reward)"
        return "❌ F (Bad Deal)"

    itm_deals['Grade'] = itm_deals.apply(assign_grade, axis=1)

    # 5. Clean up the view
    final_list = itm_deals[['strike', 'bid', 'safety_net_$', 'allowance_%', 'Grade']]
    
    # Sort to show the best grades at the top
    return final_list.sort_values(by='allowance_%', ascending=False)

# --- EXECUTE SCAN ---
# Let's try it with a popular stock!
print(scan_for_itm_deals("AAPL").head(10))