import yfinance as yf
import stumpy
import pandas as pd
import numpy as np
from scipy.signal import find_peaks
from scipy.stats import percentileofscore
import os
import logging
import argparse
import re
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import warnings
from colorama import init, Fore, Style

# --- IMPORTS ---
# from parser12 import fetch_news_for_symbols (deprecated)

init(autoreset=True)

# --- CONFIGURATION ---
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
LIBRARY_PATH = os.path.join(BASE_PATH, "..", "ARCHETYPE_LIBRARY_FINAL")
LOG_PATH = os.path.join(BASE_PATH, "LOGS_QUICKSTRIKE")
TARGETS_FILE = os.path.join(BASE_PATH, "TARGETS", "elite_targets.txt")

os.makedirs(LOG_PATH, exist_ok=True)

# --- QUICK STRIKE PARAMETERS ---
STOP_LOSS_PCT = 5.0          
BREAK_EVEN_TRIGGER_PCT = 1.5 
MIN_PROFIT_TO_TRAIL = 2.0    
TRAILING_RETRACEMENT = 0.50  
MAX_HOLD_DAYS = 7            

# --- STRATEGY PARAMETERS ---
FIXED_START_DATE = "2020-01-01"
MIN_PERCENTAGE_GROWTH = 10.0
DNA_STRICT_THRESHOLD = 2.75
DNA_LOOSE_THRESHOLD = 4.75
DNA_WINDOW = 30
VOLATILITY_LOWER_PERCENTILE = 25.0
VOLATILITY_UPPER_PERCENTILE = 90.0
NEWS_ANALYSIS_START_DATE = "2099-12-31" # <-- Far future date for disabling -- Normal Config: NEWS_ANALYSIS_START_DATE = (datetime.now() - timedelta(days=1*1)).strftime('%Y-%m-%d') # 1x1 practically disabled.

# --- VERDICT THRESHOLDS ---
MIN_WIN_RATE_THRESHOLD = 50.0
MIN_AVG_PROFIT_THRESHOLD = 0.0

# --- SETUP & HELPER FUNCTIONS ---
def setup_logging(log_filename):
    os.makedirs(LOG_PATH, exist_ok=True)
    log_file = os.path.join(LOG_PATH, log_filename)
    for handler in logging.root.handlers[:]: logging.root.removeHandler(handler)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)-7s] %(message)s", handlers=[logging.FileHandler(log_file, mode='w'), logging.StreamHandler()])
    logging.getLogger("yfinance").setLevel(logging.ERROR)
    logging.getLogger("stumpy").setLevel(logging.ERROR)
    warnings.filterwarnings("ignore", message="`Q` must be 1-dimensional and was automatically flattened")

def z_normalize(series):
    std_dev = np.std(series)
    if std_dev < 1e-6: return np.zeros_like(series)
    return (series - np.mean(series)) / std_dev

def load_archetypes(library_path):
    archetypes_db = {}
    if not os.path.exists(library_path): return archetypes_db
    for file in os.listdir(library_path):
        if file.endswith(".npy"):
            name = os.path.splitext(file)[0]
            path = os.path.join(library_path, file)
            archetypes_db[name] = np.load(path)
    return archetypes_db

def calculate_percentage_growth(series):
    values = series if isinstance(series, np.ndarray) else series.to_numpy()
    if len(values) < 2: return 0.0
    start_price, end_price = values[0], values[-1]
    if start_price == 0: return np.inf
    return float(((end_price - start_price) / start_price) * 100.0)

def run_volatility_filter(atrs, trigger_index):
    current_atr = atrs[trigger_index]
    if np.isnan(current_atr): return False
    clean_atrs = atrs[~np.isnan(atrs)]
    atr_percentile = percentileofscore(clean_atrs, current_atr)
    if atr_percentile < VOLATILITY_LOWER_PERCENTILE: return False
    if atr_percentile >= VOLATILITY_UPPER_PERCENTILE: return False
    return True

def extract_m_value(archetype_name):
    match = re.search(r'_m(\d+)', archetype_name)
    if match: return int(match.group(1))
    return 30

def is_compatible(scan_m, arch_m):
    if scan_m <= 30: return arch_m <= 60 
    elif scan_m >= 90: return arch_m >= 60 
    else: return True 

def run_entry_filters(current_ts_window, archetypes_db, scan_m):
    growth = calculate_percentage_growth(current_ts_window)
    result = {'growth': growth}
    if growth < MIN_PERCENTAGE_GROWTH:
        result['status'] = 'fail_growth'
        return result
    
    normalized_ramp = z_normalize(current_ts_window)
    best_match_name, best_match_distance = None, np.inf
    
    for name, archetype in archetypes_db.items():
        arch_m = extract_m_value(name)
        if not is_compatible(scan_m, arch_m): continue 

        try:
            if len(normalized_ramp) > len(archetype): continue
            distance_profile = stumpy.mass(archetype, normalized_ramp)
            min_distance = np.min(distance_profile)
            if min_distance < best_match_distance:
                best_match_distance, best_match_name = min_distance, name
        except Exception: continue
    
    result.update({'distance': best_match_distance, 'match_name': best_match_name})
    
    if best_match_distance <= DNA_LOOSE_THRESHOLD:
        match_type = "Strict" if best_match_distance <= DNA_STRICT_THRESHOLD else "Loose"
        result.update({'status': 'pass', 'match_type': match_type})
        return result
    
    result['status'] = 'fail_dna'
    return result

def analyze_news_context(ticker, trade_date):
    try:
        df_news = fetch_news_for_symbols([ticker], save=False, target_date=trade_date)
        if df_news.empty: return "No news found.", 0.0, []
        return f"{len(df_news)} articles", df_news['Score'].mean(), df_news.nlargest(3, 'Score')['Title'].tolist()
    except: return "Error", 0.0, []

# --- MAIN ENGINE ---
def main(args):
    setup_logging(args.logfile)
    logging.info(f"--- [Quick Strike Scanner v5.1 Started for {args.ticker}] ---")
    
    archetypes_db = load_archetypes(LIBRARY_PATH)
    
    # --- DATA LOADING (Fixed Baseline) ---
    # We use a fixed start date to ensure the CAC algorithm always has the same
    # historical context (including the 2020 volatility baseline).
    full_data = yf.download(args.ticker, start=FIXED_START_DATE, end=None, progress=False, auto_adjust=True)
    
    if full_data.empty or len(full_data) < args.m * 2: 
        logging.critical(f"Not enough data since {FIXED_START_DATE} to run scan.")
        return

    logging.info(f"Data loaded from fixed start date: {FIXED_START_DATE}")

    high_low = full_data['High'] - full_data['Low']
    high_close = np.abs(full_data['High'] - full_data['Close'].shift())
    low_close = np.abs(full_data['Low'] - full_data['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    full_data['atr'] = true_range.rolling(14).mean()

    ts = full_data['Close'].values.flatten()
    highs = full_data['High'].values.flatten()
    lows = full_data['Low'].values.flatten()
    atrs = full_data['atr'].values.flatten()
    dates = full_data.index
    
    # CAC Calculation
    mp_output = stumpy.stump(ts, m=args.m)
    I = mp_output[:, 1].astype(np.int64)
    cac, _ = stumpy.fluss(I, L=args.m, n_regimes=10)
    valleys, _ = find_peaks(-cac, distance=args.m)
    valley_dates = set(dates[valleys].strftime('%Y-%m-%d'))

    # --- CRITICAL FIX: EDGE VALLEY DETECTOR ---
    # find_peaks cannot find a valley at the very end of the data (today)
    # because it needs a right neighbor. We manually check if the current CAC
    # is critically low (indicating a regime change is active NOW).
    
    # Calculate the 10th percentile of the CAC (Low values = Regime Change)
    cac_threshold = np.percentile(cac, 10)
    
    # Check the last 3 days. If CAC is below threshold, add to valley_dates.
    # This allows the system to trigger on "Today".
    for i in range(1, 4):
        if len(cac) >= i:
            if cac[-i] <= cac_threshold:
                date_str = dates[-i].strftime('%Y-%m-%d')
                valley_dates.add(date_str)
                # We don't log here to avoid spam, but the date is now valid for the loop.
    # ------------------------------------------

    trades = []
    in_trade = False
    current_trade = {}
    days_held = 0
    max_profit_reached = 0.0 
    max_loss_reached = 0.0

    for i in range(args.m, len(full_data)):
        current_date = dates[i]
        current_price = ts[i]
        
        if in_trade:
            days_held += 1
            entry_price = current_trade['entry_price']
            daily_high = highs[i]
            daily_low = lows[i]
            
            day_max_profit = ((daily_high - entry_price) / entry_price) * 100.0
            day_max_loss = ((daily_low - entry_price) / entry_price) * 100.0
            max_profit_reached = max(max_profit_reached, day_max_profit)
            max_loss_reached = min(max_loss_reached, day_max_loss)

            floor_price = entry_price * (1 - STOP_LOSS_PCT/100)
            if max_profit_reached >= BREAK_EVEN_TRIGGER_PCT:
                floor_price = entry_price 
            
            ceiling_price = 0.0
            if max_profit_reached >= MIN_PROFIT_TO_TRAIL:
                ceiling_price = entry_price * (1 + (max_profit_reached/100) * (1 - TRAILING_RETRACEMENT))

            exit_reason = None
            exit_price = current_price

            if ceiling_price > 0 and daily_low <= ceiling_price:
                exit_reason = f"Retracement Stop (Max Up: {max_profit_reached:.2f}%)"
                exit_price = ceiling_price
            elif floor_price > 0 and daily_low <= floor_price:
                if floor_price == entry_price: exit_reason = "Break Even Stop"
                else: exit_reason = f"Stop Loss (-{STOP_LOSS_PCT}%)"
                exit_price = floor_price
            elif days_held >= MAX_HOLD_DAYS:
                exit_reason = f"Time Stop ({MAX_HOLD_DAYS} days)"
                exit_price = current_price

            if exit_reason:
                profit = ((exit_price - entry_price) / entry_price) * 100.0
                current_trade.update({
                    'exit_date': current_date, 
                    'exit_price': exit_price, 
                    'exit_reason': exit_reason, 
                    'profit_pct': profit,
                    'max_profit_reached': max_profit_reached
                })
                trades.append(current_trade)
                color = Fore.GREEN if profit >= 0 else Fore.RED
                logging.info(color + f"!!! SELL: {exit_reason} | Profit: {profit:.2f}% !!!")
                in_trade = False
                days_held = 0
                max_profit_reached = 0.0
                max_loss_reached = 0.0
                continue

        else:
            if current_date.strftime('%Y-%m-%d') in valley_dates:
                if run_volatility_filter(atrs, i):
                    if i < DNA_WINDOW: continue
                    past_30_day_pattern = ts[i - DNA_WINDOW + 1 : i + 1]
                    entry_signal = run_entry_filters(past_30_day_pattern, archetypes_db, args.m)
                    
                    if entry_signal and entry_signal['status'] == 'pass':
                        in_trade = True
                        current_trade = { 
                            'entry_date': current_date, 
                            'entry_price': current_price,
                            'match_name': entry_signal['match_name'], 
                            'match_type': entry_signal['match_type']
                        }
                        logging.info(Fore.GREEN + f"!!! BUY SIGNAL on {current_date.strftime('%Y-%m-%d')} at ${current_price:.2f} !!!")

    # --- REPORT ---
    logging.info("\n" + "="*60)
    if trades:
        num_wins = sum(1 for t in trades if t['profit_pct'] > 0)
        win_rate = (num_wins / len(trades)) * 100
        avg_profit = sum(t['profit_pct'] for t in trades) / len(trades)
        
        # --- NEW: EQUITY SIMULATION ---
        start_equity = 10000.0
        current_equity = start_equity
        for t in trades:
            current_equity = current_equity * (1 + t['profit_pct'] / 100.0)
        
        total_return = ((current_equity - start_equity) / start_equity) * 100.0

        logging.info(f"Total Trades: {len(trades)} | Win Rate: {win_rate:.2f}% | Avg P/L: {avg_profit:.2f}%")
        logging.info(Fore.CYAN + f"Simulated Account ($10k start): ${current_equity:,.2f} (Total Return: {total_return:.2f}%)")
        
        df = pd.DataFrame(trades)[['entry_date', 'exit_date', 'match_name', 'exit_reason', 'profit_pct']]
        logging.info("\n" + df.to_markdown(index=False))

        is_profitable = (win_rate >= MIN_WIN_RATE_THRESHOLD) and (avg_profit > MIN_AVG_PROFIT_THRESHOLD)
        logging.info("\n" + "="*60)
        if is_profitable:
            logging.info(Fore.GREEN + Style.BRIGHT + "--- [STRATEGY VERDICT: PROFITABLE] ---")
        else:
            logging.info(Fore.RED + Style.BRIGHT + "--- [STRATEGY VERDICT: BLACK SHEEP] ---")
        logging.info("="*60)

    else:
        logging.info("No trades were executed during the simulation period.")
        logging.info("\n" + "="*60)
        logging.info(Fore.BLUE + "--- [STRATEGY VERDICT: PASSIVE] ---")
        logging.info("="*60)

    if in_trade:
        logging.info(Style.BRIGHT + Fore.GREEN + "\n--- [LIVE STATUS] ---")
        logging.info(f"The simulation finished while IN A TRADE.")
        logging.info(f"Entry Date: {current_trade['entry_date'].strftime('%Y-%m-%d')}")
        logging.info(f"Entry Price: ${current_trade['entry_price']:.2f}")
        logging.info(f"This is a potential LIVE BUY SIGNAL.")
        
        # --- RENAME LOG FILE ---
        # We must shut down logging to release the file handle before renaming
        logging.info("Renaming log file to indicate active trade...")
        logging.shutdown()
        
        try:
            old_path = os.path.join(LOG_PATH, args.logfile)
            new_filename = f"IN_TRADE_{args.logfile}"
            new_path = os.path.join(LOG_PATH, new_filename)
            
            if os.path.exists(new_path):
                os.remove(new_path) # Overwrite if exists
                
            os.rename(old_path, new_path)
            print(Fore.MAGENTA + f"Log renamed to: {new_filename}")
        except Exception as e:
            print(Fore.RED + f"Error renaming log file: {e}")
        
    else:
        logging.info("--- [Quick Strike Scanner Finished] ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--start", required=False) # Made optional, script handles it
    parser.add_argument("--end", required=False)   # Made optional
    parser.add_argument("--m", type=int, required=True)
    parser.add_argument("--logfile", required=True)
    args = parser.parse_args()
    main(args)