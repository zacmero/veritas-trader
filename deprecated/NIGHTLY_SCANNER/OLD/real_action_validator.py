import os
import re
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from colorama import init, Fore, Style
import logging

init(autoreset=True)

# --- CONFIGURATION ---
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
# Default dir, can be overridden by args
LOG_DIR = os.path.expanduser("~/IN_TRADE/profitable") 
OUTPUT_DIR = os.path.join(BASE_PATH, "VALIDATION_REAL_ACTION")

# --- QUICK STRIKE EXIT LOGIC ---
STOP_LOSS_PCT = 5.0          
BREAK_EVEN_TRIGGER_PCT = 1.5 
MIN_PROFIT_TO_TRAIL = 2.0    
TRAILING_RETRACEMENT = 0.50  
MAX_HOLD_DAYS = 7            

os.makedirs(OUTPUT_DIR, exist_ok=True)

def safe_float(value):
    try:
        if isinstance(value, pd.Series): return float(value.iloc[0])
        return float(value)
    except: return 0.0

def parse_log_file(filepath):
    with open(filepath, 'r', errors='ignore') as f:
        lines = f.readlines()
    
    if not lines: return None
    content = "".join(lines)
    
    filename = os.path.basename(filepath)
    ticker = None
    m_value = 0
    
    qs_match = re.search(r"live_qs_(.+)_m(\d+)", filename)
    og_match = re.search(r"live_scan_(.+)_m(\d+)", filename)
    
    if qs_match:
        ticker = qs_match.group(1)
        m_value = int(qs_match.group(2))
    elif og_match:
        ticker = og_match.group(1)
        m_value = int(og_match.group(2))
    
    if not ticker: return None

    # Extract Run Date from First Line
    first_line = lines[0]
    run_date_match = re.search(r"^(\d{4}-\d{2}-\d{2})", first_line)
    if not run_date_match: return None
    run_date_str = run_date_match.group(1)

    # Extract Signal Date from [LIVE STATUS] block
    entry_date_matches = re.findall(r"Entry Date:\s*(\d{4}-\d{2}-\d{2})", content)
    if not entry_date_matches: return None 
    signal_date_str = entry_date_matches[-1]

    return {
        'ticker': ticker,
        'm': m_value,
        'run_date': run_date_str,
        'signal_date': signal_date_str
    }

def simulate_real_trade(trade_data):
    ticker = trade_data['ticker']
    run_date_str = trade_data['run_date']
    signal_date_str = trade_data['signal_date']
    
    # Download data covering Signal Date to Now
    start_dt = datetime.strptime(signal_date_str, "%Y-%m-%d")
    end_dt = datetime.now()
    
    logging.getLogger('yfinance').setLevel(logging.CRITICAL)
    
    try:
        df = yf.download(ticker, start=start_dt, end=end_dt, progress=False, auto_adjust=True)
    except: return "ERROR_DOWNLOAD", 0.0, "N/A", 0.0, "N/A"
    
    if df.empty: return "ERROR_NO_DATA", 0.0, "N/A", 0.0, "N/A"
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # --- 1. GAP ANALYSIS (Signal Date -> Run Date) ---
    # Check if trade died before we could enter (Gap Protection)
    
    # Identify Signal Price (Close of Signal Date)
    try:
        signal_row = df.loc[signal_date_str]
        signal_price = safe_float(signal_row['Close'])
    except KeyError:
        # If signal date missing (weekend?), take first available
        if len(df) > 0:
            signal_price = safe_float(df.iloc[0]['Close'])
        else:
            return "ERROR_DATA_GAP", 0.0, "N/A", 0.0, "N/A"
    
    gap_stop_price = signal_price * (1 - STOP_LOSS_PCT/100)

    # --- 2. REAL ENTRY (On/After Run Date) ---
    # We enter on the OPEN of the first bar >= Run Date
    action_mask = df.index >= run_date_str
    action_df = df.loc[action_mask]
    
    if action_df.empty:
        return "PENDING", 0.0, "N/A", 0.0, "N/A"
        
    row_entry = action_df.iloc[0]
    entry_price = safe_float(row_entry['Open'])
    real_entry_date = action_df.index[0].strftime('%Y-%m-%d')

    # GAP RULE: Only skip if we are OPENING below the hard stop level relative to the Signal.
    # This prevents entering trades that have completely collapsed, but allows "dipped and recovered" trades.
    if entry_price <= gap_stop_price:
         return "SKIPPED (Gap >5%)", 0.0, real_entry_date, 0.0, "N/A"

    # --- 3. SIMULATION LOOP (FRESH TRADE LOGIC) ---
    # We treat this as a NEW trade starting from entry_price.
    # We use standard Quick Strike logic relative to THIS entry.
    
    days_held = 0
    max_profit_reached = 0.0
    
    for i in range(0, len(action_df)):
        row = action_df.iloc[i]
        current_date_str = action_df.index[i].strftime('%Y-%m-%d')
        
        daily_high = safe_float(row['High'])
        daily_low = safe_float(row['Low'])
        close_price = safe_float(row['Close'])
        
        days_held += 1
        
        # Calculate Max Profit based on OUR Entry
        day_max_profit = ((daily_high - entry_price) / entry_price) * 100.0
        max_profit_reached = max(max_profit_reached, day_max_profit)
        
        # --- EXIT LOGIC (Standard QS) ---
        floor_price = entry_price * (1 - STOP_LOSS_PCT/100)
        
        if max_profit_reached >= BREAK_EVEN_TRIGGER_PCT: 
            floor_price = entry_price 
        
        ceiling_price = 0.0
        if max_profit_reached >= MIN_PROFIT_TO_TRAIL:
            ceiling_price = entry_price * (1 + (max_profit_reached/100) * (1 - TRAILING_RETRACEMENT))
            
        exit_price = 0.0
        reason = ""
        
        if ceiling_price > 0 and daily_low <= ceiling_price:
            exit_price = ceiling_price
            reason = f"Trail (Max {max_profit_reached:.1f}%)"
        elif daily_low <= floor_price:
            exit_price = floor_price
            if floor_price == entry_price: reason = "Break Even"
            else: reason = "Stop Loss (-5%)"
        elif days_held >= MAX_HOLD_DAYS:
            exit_price = close_price
            reason = f"Time ({MAX_HOLD_DAYS}d)"
            
        if reason:
            profit_pct = ((exit_price - entry_price) / entry_price) * 100.0
            return reason, profit_pct, current_date_str, entry_price, real_entry_date

    # Still Open
    last_price = safe_float(action_df.iloc[-1]['Close'])
    current_profit = ((last_price - entry_price) / entry_price) * 100.0
    return "OPEN", current_profit, action_df.index[-1].strftime('%Y-%m-%d'), entry_price, real_entry_date

def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"real_action_report_{timestamp}.txt"
    log_path = os.path.join(OUTPUT_DIR, log_filename)

    def log_print(message):
        print(message)
        with open(log_path, "a") as f:
            clean_msg = re.sub(r'\x1b\[[0-9;]*m', '', message)
            f.write(clean_msg + "\n")

    log_print(f"{Fore.CYAN}--- [REAL ACTION VALIDATOR v7.0 - FRESH TRADE LOGIC] ---")
    log_print(f"{Fore.CYAN}Logic: Skip if Gap > 5%. Else, treat as fresh trade (Stop -5% from Open).")
    log_print(f"Target Directory: {LOG_DIR}\n")
    
    if not os.path.exists(LOG_DIR):
        print("Log dir not found")
        return

    files = [f for f in os.listdir(LOG_DIR) if f.endswith(".log")]
    files.sort()
    
    valid_profits = []
    skipped_count = 0

    # Columns: Signal Date | Run Date | Real Entry Date | Exit Date | Entry Price | Status | Profit
    log_print(f"{ 'Ticker':<6} | {'Sig Date':<10} | {'Run Date':<10} | {'Entry Date':<10} | {'Exit Date':<10} | {'Entry $':<8} | {'Status':<18} | {'Profit %'}")
    log_print("-" * 115)

    for filename in files:
        filepath = os.path.join(LOG_DIR, filename)
        trade_data = parse_log_file(filepath)
        if not trade_data: continue
        
        reason, profit, exit_date, entry_price, real_entry_date = simulate_real_trade(trade_data)
        
        # Format Entry Date
        re_date = real_entry_date if real_entry_date != "N/A" else "-" 
        
        if "SKIPPED" in reason:
            c = Fore.BLUE
            skipped_count += 1
        elif profit > 0: 
            c = Fore.GREEN
            valid_profits.append(profit)
        else: 
            c = Fore.RED
            valid_profits.append(profit)
        
        log_print(f"{trade_data['ticker']:<6} | {trade_data['signal_date']:<10} | {trade_data['run_date']:<10} | {re_date:<10} | {exit_date:<10} | ${entry_price:<7.2f} | {reason:<18} | {c}{profit:.2f}%{Style.RESET_ALL}")

    if valid_profits:
        avg_pl = sum(valid_profits) / len(valid_profits)
        total_pl = sum(valid_profits)
        win_rate = len([p for p in valid_profits if p > 0]) / len(valid_profits) * 100
        
        log_print("\n" + "="*40)
        log_print(f"TOTAL TRADES ANALYZED: {len(valid_profits) + skipped_count}")
        log_print(f"TRADES TAKEN:        {len(valid_profits)}")
        log_print(f"TRADES SKIPPED:      {skipped_count}")
        log_print("-" * 40)
        log_print(f"REAL WORLD WIN RATE: {win_rate:.2f}%")
        log_print(f"REAL WORLD AVG P/L:  {Fore.YELLOW}{avg_pl:.2f}%{Style.RESET_ALL}")
        log_print(f"TOTAL P/L SUM:       {Fore.YELLOW}{total_pl:.2f}%{Style.RESET_ALL}")
        log_print("="*40)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=os.path.expanduser("~/IN_TRADE/profitable"))
    args = parser.parse_args()
    LOG_DIR = args.dir
    main()