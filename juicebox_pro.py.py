import yfinance as yf
import pandas as pd

def run_juice_scanner(ticker_symbol):
    """
    A scanner for 'In-the-Money' (ITM) covered calls.
    It calculates the 'Safety Net' and 'Allowance Score' for a student.
    """
    print(f"--- 🕵️ Scanning {ticker_symbol} for the Best ITM Deals ---")
    
    # 1. Get Stock Data
    stock = yf.Ticker(ticker_symbol)
    try:
        # Grabbing the most recent price
        current_price = stock.fast_info['last_price']
    except Exception:
        return "Error: Could not find that stock. Check the symbol!"

    # 2. Get Expiration Dates (Looking for deals about 30 days away)
    expiry_dates = stock.options
    if not expiry_dates:
        return "No options found for this stock."
    
    # We'll use the first available expiration date
    target_expiry = expiry_dates[0]
    chain = stock.option_chain(target_expiry)
    calls = chain.calls

    # 3. Filter for 'In-the-Money' (Strike Price < Current Price)
    # This means the deal has a 'Safety Net' built in.
    itm_deals = calls[calls['strike'] < current_price].copy()

    # --- THE 'JUICE' CALCULATIONS ---
    
    # How much cash the friend gives you upfront (the Premium)
    # We use 'bid' because that is the price you can sell it for right now.
    
    # Break-Even: What you actually paid for the stock after the fee
    itm_deals['break_even'] = current_price - itm_deals['bid']
    
    # Safety Net: How many dollars the stock can drop before you lose money
    itm_deals['safety_net_$'] = current_price - itm_deals['break_even']
    
    # Max Profit: If the stock is sold at the strike price
    itm_deals['max_profit_$'] = (itm_deals['strike'] + itm_deals['bid']) - current_price
    
    # Allowance %: Your reward for the month!
    itm_deals['allowance_%'] = (itm_deals['max_profit_$'] / current_price) * 100

    # 4. THE GRADING SYSTEM
    def assign_grade(row):
        if row['allowance_%'] > 2.5: return "💎 A+ (High Reward)"
        if row['allowance_%'] > 1.0: return "✅ B (Solid Deal)"
        if row['allowance_%'] > 0:   return "⚠️ C (Low Reward)"
        return "❌ F (Bad Deal)"

    itm_deals['Grade'] = itm_deals.apply(assign_grade, axis=1)

    # 5. Clean up the view for the user
    final_list = itm_deals[['strike', 'bid', 'safety_net_$', 'allowance_%', 'Grade']]
    
    # Sorting so the best grades are at the top
    return final_list.sort_values(by='allowance_%', ascending=False)

# --- HOW TO RUN ---
# You can change 'AAPL' to 'XOM' (Exxon) or 'COST' (Costco) 
# since you have tracked those before!
print(run_juice_scanner("AAPL").head(10))