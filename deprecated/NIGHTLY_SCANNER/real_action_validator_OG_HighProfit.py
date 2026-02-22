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
    first_line = lines[0]
    run_date_match = re.search(r"^(\d{4}-\d{2}-\d{2})", first_line)
    if not run_date_match: return None
    run_date_str = run_date_match.group(1)
    
    # Extract Simulated Signal Date for Gap Calculation
    entry_date_matches = re.findall(r"Entry Date:\s*(\d{4}-\d{2}-\d{2})", content)
    signal_date_str = entry_date_matches[-1] if entry_date_matches else run_date_str

    return {'ticker': ticker, 'm': m_value, 'run_date': run_date_str, 'signal_date': signal_date_str}

def simulate_real_trade(trade_data):
    ticker = trade_data['ticker']
    run_date_str = trade_data['run_date']
    signal_date_str = trade_data['signal_date']
    
    # Download extra history to find Signal Price (Friday Close)
    start_dt = datetime.strptime(signal_date_str, "%Y-%m-%d")
    end_dt = datetime.now()
    logging.getLogger('yfinance').setLevel(logging.CRITICAL)
    
    try:
        df = yf.download(ticker, start=start_dt, end=end_dt, progress=False, auto_adjust=True)
    except: return "ERROR_DOWNLOAD", 0.0, "N/A", 0.0, "N/A", 0.0
    if df.empty: return "ERROR_NO_DATA", 0.0, "N/A", 0.0, "N/A", 0.0
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

    # 1. Get Signal Price (Close of Signal Day)
    try:
        signal_row = df.loc[signal_date_str]
        signal_price = safe_float(signal_row['Close'])
    except KeyError:
        if len(df) > 0: signal_price = safe_float(df.iloc[0]['Close'])
        else: signal_price = 0.0

    # 2. Find Action Day (Next Open >= Run Date)
    action_mask = df.index >= run_date_str
    action_df = df.loc[action_mask]
    
    # Handle Nightly Run: If Run Date is in data, we assume we missed it (post-close), take NEXT row.
    start_idx = 0
    if not action_df.empty:
        first_date_str = action_df.index[0].strftime('%Y-%m-%d')
        if first_date_str == run_date_str:
            if len(action_df) > 1: start_idx = 1
            else: return "PENDING_NEXT", 0.0, "N/A", 0.0, "N/A", 0.0
    else:
        return "PENDING", 0.0, "N/A", 0.0, "N/A", 0.0

    row_entry = action_df.iloc[start_idx]
    entry_price = safe_float(row_entry['Open'])
    real_entry_date = action_df.index[start_idx].strftime('%Y-%m-%d')
    
    # 3. Calculate GAP % (Overnight change)
    gap_pct = 0.0
    if signal_price > 0:
        gap_pct = ((entry_price - signal_price) / signal_price) * 100.0

    # 4. Simulation Loop (Fresh Trade Logic)
    days_held = 0
    max_profit_reached = 0.0
    
    for i in range(start_idx, len(action_df)):
        row = action_df.iloc[i]
        date = action_df.index[i]
        days_held += 1
        daily_high = safe_float(row['High'])
        daily_low = safe_float(row['Low'])
        close_price = safe_float(row['Close'])
        
        day_max_profit = ((daily_high - entry_price) / entry_price) * 100.0
        max_profit_reached = max(max_profit_reached, day_max_profit)
        
        floor_price = entry_price * (1 - STOP_LOSS_PCT/100)
        if max_profit_reached >= BREAK_EVEN_TRIGGER_PCT: floor_price = entry_price 
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
            else: reason = "Stop Loss"
        elif days_held >= MAX_HOLD_DAYS:
            exit_price = close_price
            reason = "Time"
            
        if reason:
            profit_pct = ((exit_price - entry_price) / entry_price) * 100.0
            return reason, profit_pct, date.strftime('%Y-%m-%d'), entry_price, real_entry_date, gap_pct

    last_price = safe_float(action_df.iloc[-1]['Close'])
    current_profit = ((last_price - entry_price) / entry_price) * 100.0
    return "OPEN", current_profit, action_df.index[-1].strftime('%Y-%m-%d'), entry_price, real_entry_date, gap_pct

def main():
    print(f"{Fore.CYAN}--- [OG HIGH PROFIT VALIDATOR (with Gap Analysis)] ---")
    if not os.path.exists(LOG_DIR): return
    files = [f for f in os.listdir(LOG_DIR) if f.endswith(".log")]
    files.sort()
    results = []
    
    print(f"{ 'Ticker':<6} | {'Entry Date':<10} | {'Gap %':<8} | {'Entry $':<8} | {'Exit Date':<10} | {'Status':<15} | {'Profit %'}")
    print("-" * 95)
    
    for filename in files:
        filepath = os.path.join(LOG_DIR, filename)
        trade_data = parse_log_file(filepath)
        if not trade_data: continue
        
        reason, profit, exit_date, entry_price, real_entry_date, gap_pct = simulate_real_trade(trade_data)
        
        c = Fore.GREEN if profit > 0 else Fore.RED
        gap_c = Fore.RED if gap_pct < -2.0 else Fore.WHITE
        
        print(f"{trade_data['ticker']:<6} | {real_entry_date:<10} | {gap_c}{gap_pct:>6.2f}%{Style.RESET_ALL} | ${entry_price:<7.2f} | {exit_date:<10} | {reason:<15} | {c}{profit:.2f}%{Style.RESET_ALL}")
        results.append(profit)
        
    if results:
        avg_pl = sum(results) / len(results)
        total_pl = sum(results)
        win_rate = len([p for p in results if p > 0]) / len(results) * 100
        print("\n" + "="*40)
        print(f"TOTAL TRADES: {len(results)}")
        print(f"WIN RATE: {win_rate:.2f}%")
        print(f"AVG P/L: {Fore.YELLOW}{avg_pl:.2f}%{Style.RESET_ALL}")
        print(f"TOTAL P/L SUM: {Fore.YELLOW}{total_pl:.2f}%{Style.RESET_ALL}")
        print("="*40)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=os.path.expanduser("~/IN_TRADE/profitable"))
    args = parser.parse_args()
    LOG_DIR = args.dir
    main()