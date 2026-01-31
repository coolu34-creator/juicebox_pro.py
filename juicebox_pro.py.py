import yfinance as yf
import pandas as pd

def find_best_deals(ticker_symbol):
    print(f"\n--- 🕵️ SCANNING: {ticker_symbol.upper()} ---")
    
    # 1. Get the Stock Info
    try:
        stock = yf.Ticker(ticker_symbol)
        current_price = stock.fast_info['last_price']
        print(f"Current Stock Price: ${current_price:.2f}")
    except:
        print("❌ Error: Could not find that stock. Check the spelling!")
        return

    # 2. Get Option Dates (We look at the soonest one)
    options_dates = stock.options
    if not options_dates:
        print("❌ No options found for this stock.")
        return

    # Grab the first available date (usually about 30 days out)
    target_date = options_dates[0] 
    print(f"Looking at deals expiring on: {target_date}")
    
    # Get the 'Call' options
    calls = stock.option_chain(target_date).calls

    # 3. Filter for 'In-the-Money' (The 'Safety Net' Strategy)
    # We only want Strike Prices that are LOWER than the current stock price.
    itm_deals = calls[calls['strike'] < current_price].copy()

    # --- THE MATH (Simplified) ---
    
    # A. The Instant Cash (Premium)
    # We use 'bid' because that's what you can sell it for right now.
    premium = itm_deals['bid']
    strike = itm_deals['strike']

    # B. The Break-Even Price (Your new 'Cost')
    # If you buy the stock and sell the option, this is your actual cost.
    break_even = current_price - premium
    
    # C. The Safety Net ($)
    # How much can the stock drop before you lose a penny?
    itm_deals['Safety_Net_$'] = current_price - break_even
    
    # D. The Profit ($)
    # If the stock stays flat or goes up, you make this much.
    itm_deals['Profit_$'] = (strike - break_even)
    
    # E. The Score (%)
    # This acts like an interest rate. 
    itm_deals['Score_%'] = (itm_deals['Profit_$'] / break_even) * 100

    # 4. THE GRADING SYSTEM
    # This assigns a letter grade so you can spot good deals instantly.
    def give_grade(score):
        if score > 2.5: return "💎 A+ (Great)"
        if score > 1.5: return "✅ B (Good)"
        if score > 0.5: return "⚠️ C (Okay)"
        return "❌ F (Skip)"

    itm_deals['Grade'] = itm_deals['Score_%'].apply(give_grade)

    # 5. Clean Up and Show Results
    # We select only the columns we care about.
    results = itm_deals[['strike', 'bid', 'Safety_Net_$', 'Score_%', 'Grade']]
    
    # Sort: Put the highest 'Score' at the top
    top_deals = results.sort_values(by='Score_%', ascending=False).head(10)
    
    return top_deals

# --- RUN THE SCANNER HERE ---
# Change "F" to any stock symbol you want (like 'AAPL', 'TSLA', 'AMD')
print(find_best_deals("F"))