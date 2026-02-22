import pandas as pd
import yfinance as yf
import os
from datetime import datetime, timedelta
from colorama import init, Fore, Style
import logging

init(autoreset=True)

# --- CONFIGURATION ---
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
PORTFOLIO_FILE = os.path.join(BASE_PATH, "portfolio.csv")

# --- QUICK STRIKE EXIT LOGIC (Must match master_scanner_quickstrike.py) ---
STOP_LOSS_PCT = 5.0          
BREAK_EVEN_TRIGGER_PCT = 1.5 
MIN_PROFIT_TO_TRAIL = 2.0    
TRAILING_RETRACEMENT = 0.50  
MAX_HOLD_DAYS = 7            

def get_live_data(ticker):
    # Suppress yfinance noise
    logging.getLogger('yfinance').setLevel(logging.CRITICAL)
    try:
        # Get last 1 month of data to cover the 7-day hold period easily
        df = yf.download(ticker, period="1mo", progress=False, auto_adjust=True)
        if df.empty: return None
        return df
    except: return None

def analyze_position(row):
    ticker = row['Ticker']
    try:
        entry_date = pd.to_datetime(row['EntryDate'])
        entry_price = float(row['EntryPrice'])
    except ValueError:
        return f"{Fore.RED}ERROR: Invalid Date/Price format in CSV{Style.RESET_ALL}"
    
    df = get_live_data(ticker)
    if df is None:
        return f"{Fore.RED}ERROR: No Data Fetch{Style.RESET_ALL}"

    # Filter data to only show days AFTER entry to calculate High Water Mark
    mask = df.index > entry_date
    data_since_entry = df.loc[mask]
    
    # Get Current Price (Handle Series/Scalar ambiguity)
    try:
        current_close = df.iloc[-1]['Close']
        current_price = float(current_close.iloc[0]) if isinstance(current_close, pd.Series) else float(current_close)
    except:
        return f"{Fore.RED}ERROR: Price Parse{Style.RESET_ALL}"

    # If no data since entry (e.g. bought today), use current price as max
    if data_since_entry.empty:
        max_price_reached = current_price
    else:
        # Get Max High since entry
        max_high = data_since_entry['High'].max()
        max_price_reached = float(max_high.iloc[0]) if isinstance(max_high, pd.Series) else float(max_high)
        # Ensure max price is at least the current price (in case today is a new high)
        max_price_reached = max(max_price_reached, current_price)

    # --- CALCULATIONS ---
    max_profit_pct = ((max_price_reached - entry_price) / entry_price) * 100.0
    current_profit_pct = ((current_price - entry_price) / entry_price) * 100.0
    days_held = (datetime.now() - entry_date).days
    
    # --- EXIT LOGIC ENGINE ---
    
    # A. Hard Stop / Break Even Floor
    floor_price = entry_price * (1 - STOP_LOSS_PCT/100)
    stop_type = f"Hard Stop -{STOP_LOSS_PCT}%"
    
    if max_profit_pct >= BREAK_EVEN_TRIGGER_PCT:
        floor_price = entry_price
        stop_type = "Break Even"

    # B. Retracement Ceiling
    ceiling_price = 0.0
    if max_profit_pct >= MIN_PROFIT_TO_TRAIL:
        ceiling_price = entry_price * (1 + (max_profit_pct/100) * (1 - TRAILING_RETRACEMENT))

    # --- DECISION MATRIX ---
    
    # Priority 1: Retracement Hit?
    if ceiling_price > 0 and current_price <= ceiling_price:
        return f"{Fore.GREEN}SELL NOW (Retracement){Style.RESET_ALL} | Max Up: {max_profit_pct:.2f}% | Lock Profit: {current_profit_pct:.2f}%"

    # Priority 2: Floor Hit?
    if current_price <= floor_price:
        color = Fore.RED if floor_price < entry_price else Fore.YELLOW
        return f"{color}SELL NOW ({stop_type}){Style.RESET_ALL} | Current: {current_profit_pct:.2f}%"

    # Priority 3: Time Stop?
    if days_held >= MAX_HOLD_DAYS:
        return f"{Fore.YELLOW}SELL NOW (Time Stop 7 Days){Style.RESET_ALL} | Current: {current_profit_pct:.2f}%"

    # Priority 4: HOLD
    return f"{Fore.CYAN}HOLD{Style.RESET_ALL} | Current: {current_profit_pct:.2f}% | Max Up: {max_profit_pct:.2f}% | Days: {days_held}"

def main():
    print(f"{Fore.WHITE}{'='*80}")
    print(f"PORTFOLIO MANAGER - QUICK STRIKE LOGIC")
    print(f"{'='*80}")
    
    if not os.path.exists(PORTFOLIO_FILE):
        print(f"{Fore.RED}Error: {PORTFOLIO_FILE} not found.")
        print("Create 'portfolio.csv' with columns: Ticker,EntryDate,EntryPrice,Shares")
        return

    try:
        portfolio = pd.read_csv(PORTFOLIO_FILE)
    except Exception as e:
        print(f"{Fore.RED}Error reading CSV: {e}")
        return
    
    if portfolio.empty:
        print("Portfolio is empty.")
        return

    print(f"{'Ticker':<8} | {'Entry':<12} | {'Price':<8} | {'Action / Status'}")
    print("-" * 80)

    for index, row in portfolio.iterrows():
        status = analyze_position(row)
        print(f"{row['Ticker']:<8} | {row['EntryDate']:<12} | {row['EntryPrice']:<8.2f} | {status}")

    print("-" * 80)

if __name__ == "__main__":
    main()