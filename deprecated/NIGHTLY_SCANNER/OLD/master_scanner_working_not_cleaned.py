import yfinance as yf
import stumpy
import pandas as pd
import numpy as np
from scipy.signal import find_peaks
from scipy.stats import percentileofscore
import os
import logging
import argparse
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import warnings
from colorama import init, Fore, Style

# --- INITIALIZE COLORAMA ---
init(autoreset=True)

# --- CONFIGURATION ---
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
LIBRARY_PATH = os.path.join(BASE_PATH, "..", "ARCHETYPE_LIBRARY") # Corrected Path
CANDIDATE_PATH = os.path.join(BASE_PATH, "..", "CANDIDATE_LIBRARY")
LOG_PATH = os.path.join(BASE_PATH, "LOGS")
TARGETS_FILE = os.path.join(BASE_PATH, "targets.txt")

os.makedirs(CANDIDATE_PATH, exist_ok=True)
os.makedirs(LOG_PATH, exist_ok=True)

# --- STRATEGY PARAMETERS (FROM OG SCRIPT) ---
M_VALUES_TO_SCAN = [15, 30, 60, 90, 120]
MIN_PERCENTAGE_GROWTH = 10.0
DNA_STRICT_THRESHOLD = 2.75
DNA_LOOSE_THRESHOLD = 4.75
DNA_WINDOW = 30
ATR_PERIOD = 14
ATR_MULTIPLIER = 3.0
MIN_PROFIT_FOR_LEARNING = 50.0
MIN_GROWTH_PERCENTILE_FOR_LEARNING = 98.0
DUPLICATE_ARCHETYPE_THRESHOLD = 0.5 # New duplicate check

# --- SETUP & HELPER FUNCTIONS (FROM OG SCRIPT) ---
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
    if not os.path.exists(library_path):
        logging.warning(f"Archetype library not found.")
        return archetypes_db
    for file in os.listdir(library_path):
        if file.endswith(".npy"):
            name = os.path.splitext(file)[0]
            path = os.path.join(library_path, file)
            archetypes_db[name] = np.load(path)
    logging.info(f"Loaded {len(archetypes_db)} archetypes from {library_path}.")
    return archetypes_db

def calculate_percentage_growth(series):
    values = series if isinstance(series, np.ndarray) else series.to_numpy()
    if len(values) < 2: return 0.0
    start_price, end_price = values[0], values[-1]
    if start_price == 0: return np.inf
    return float(((end_price - start_price) / start_price) * 100.0)

def run_entry_filters(current_ts_window, archetypes_db):
    growth = calculate_percentage_growth(current_ts_window)
    logging.info(f"  [Filter 2] 30-Day Growth Check: {growth:.2f}%")
    if growth < MIN_PERCENTAGE_GROWTH:
        logging.info(Fore.RED + f"  [Filter 2] FAILED. Growth < {MIN_PERCENTAGE_GROWTH}%.")
        return None
    logging.info(Fore.GREEN + f"  [Filter 2] PASSED.")
    
    normalized_ramp = z_normalize(current_ts_window)
    best_match_name, best_match_distance = None, np.inf
    for name, archetype in archetypes_db.items():
        try:
            if len(normalized_ramp) > len(archetype): continue
            distance_profile = stumpy.mass(archetype, normalized_ramp)
            min_distance = np.min(distance_profile)
            if min_distance < best_match_distance:
                best_match_distance, best_match_name = min_distance, name
        except Exception: continue
    
    logging.info(f"  [Filter 3] DNA Test Best Match: '{best_match_name}' (Distance: {best_match_distance:.4f})")
    if best_match_distance <= DNA_LOOSE_THRESHOLD:
        match_type = "Strict" if best_match_distance <= DNA_STRICT_THRESHOLD else "Loose"
        logging.info(Fore.GREEN + f"  [Filter 3] PASSED ({match_type} Match).")
        return {'growth': growth, 'distance': best_match_distance, 'match_name': best_match_name, 'match_type': match_type}
    
    logging.info(Fore.RED + f"  [Filter 3] FAILED. Distance > {DNA_LOOSE_THRESHOLD}.")
    return None

# --- CORE ANALYSIS ENGINES ---
def run_backtest_mode(args, archetypes_db):
    logging.info(f"--- [Master Scanner: BACKTEST MODE Started for {args.ticker}] ---")
    
    full_data = yf.download(args.ticker, start=args.start, end=args.end, progress=False, auto_adjust=True)
    if full_data.empty or len(full_data) < args.m * 2:
        logging.critical("Not enough data for backtest. Exiting.")
        return
        
    high_low = full_data['High'] - full_data['Low']
    high_close = np.abs(full_data['High'] - full_data['Close'].shift())
    low_close = np.abs(full_data['Low'] - full_data['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    full_data['atr'] = true_range.rolling(ATR_PERIOD).mean()

    ts = full_data['Close'].values.flatten()
    dates = full_data.index
    logging.info(f"Loaded {len(ts)} data points and pre-calculated ATR.")

    logging.info("Pre-calculating historical growth distribution for learning system...")
    series_for_learning = pd.Series(ts)
    historical_growths = series_for_learning.rolling(window=DNA_WINDOW).apply(calculate_percentage_growth, raw=True).dropna()

    logging.info(f"Pre-calculating all CAC valleys with m={args.m}...")
    mp_output = stumpy.stump(ts, m=args.m)
    I = mp_output[:, 1].astype(np.int64)
    cac, _ = stumpy.fluss(I, L=args.m, n_regimes=10)
    valleys, _ = find_peaks(-cac, distance=args.m)
    valley_dates = set(dates[valleys].strftime('%Y-%m-%d'))
    logging.info(f"Found {len(valley_dates)} potential entry dates.")

    trades = []
    in_trade = False
    current_trade = {}
    cooldown_until = pd.Timestamp(0)
    trailing_stop_price = 0.0

    for i in range(args.m, len(full_data)):
        current_date = dates[i]
        current_price = ts[i]
        current_atr = full_data['atr'].iloc[i]

        if current_date < cooldown_until: continue

        if in_trade:
            if np.isnan(current_atr): continue
            new_stop_price = current_price - (current_atr * ATR_MULTIPLIER)
            trailing_stop_price = max(trailing_stop_price, new_stop_price)
            if current_price < trailing_stop_price:
                current_trade['exit_date'] = current_date
                current_trade['exit_price'] = current_price
                current_trade['exit_reason'] = f"ATR Trailing Stop"
                profit = ((current_trade['exit_price'] - current_trade['entry_price']) / current_trade['entry_price']) * 100
                current_trade['profit_pct'] = profit
                trades.append(current_trade)
                logging.info(Fore.YELLOW + f"\n!!! SELL SIGNAL on {current_date.strftime('%Y-%m-%d')} at ${current_price:.2f}. Profit: {profit:.2f}% !!!\n")
                
                if profit >= MIN_PROFIT_FOR_LEARNING:
                    ramp_growth = calculate_percentage_growth(current_trade['trigger_pattern'])
                    growth_percentile = percentileofscore(historical_growths, ramp_growth)
                    logging.info(f"--- [LEARNING CHECK] Profitable trade. Ramp growth was {ramp_growth:.2f}% ({growth_percentile:.2f}th percentile). ---")
                    if growth_percentile >= MIN_GROWTH_PERCENTILE_FOR_LEARNING:
                        is_duplicate = False
                        candidate_pattern_norm = z_normalize(current_trade['trigger_pattern'])
                        for name, archetype in archetypes_db.items():
                            distance = np.linalg.norm(candidate_pattern_norm - archetype)
                            if distance < DUPLICATE_ARCHETYPE_THRESHOLD:
                                logging.info(Fore.YELLOW + f"--- [LEARNING] REJECTED. Candidate is a duplicate of '{name}'. ---")
                                is_duplicate = True
                                break
                        if not is_duplicate:
                            logging.info(Fore.GREEN + f"--- [LEARNING] PASSED. Saving candidate archetype. ---")
                            pattern = current_trade['trigger_pattern']
                            date_str = current_trade['entry_date'].strftime('%Y%m%d')
                            filename = f"candidate_{args.ticker}_{date_str}_m{args.m}"
                            np.save(os.path.join(CANDIDATE_PATH, f"{filename}.npy"), candidate_pattern_norm)
                            plt.figure(); plt.plot(pattern); plt.title(f"Candidate: {args.ticker} {date_str}");
                            plt.savefig(os.path.join(CANDIDATE_PATH, f"{filename}.png")); plt.close()
                    else:
                        logging.info(Fore.RED + f"--- [LEARNING] FAILED. Growth percentile < {MIN_GROWTH_PERCENTILE_FOR_LEARNING}%. ---")

                in_trade = False
                current_trade = {}
                cooldown_until = current_date + timedelta(days=90)
                continue
        else:
            if current_date.strftime('%Y-%m-%d') in valley_dates:
                logging.info(f"\n--- [F1 TRIGGER] Pre-calculated CAC Valley detected on {current_date.strftime('%Y-%m-%d')} ---")
                if i < DNA_WINDOW: continue
                past_30_day_pattern = ts[i - DNA_WINDOW + 1 : i + 1]
                entry_signal = run_entry_filters(past_30_day_pattern, archetypes_db)
                if entry_signal:
                    in_trade = True
                    current_trade = { 'entry_date': current_date, 'entry_price': current_price, 'trigger_pattern': past_30_day_pattern, 'details': entry_signal }
                    if np.isnan(current_atr):
                        trailing_stop_price = current_price * 0.8
                    else:
                        trailing_stop_price = current_price - (current_atr * ATR_MULTIPLIER)
                    logging.info(Fore.GREEN + f"\n!!! BUY SIGNAL on {current_date.strftime('%Y-%m-%d')} at ${current_price:.2f}. Match: {entry_signal['match_name']} ({entry_signal['match_type']}) !!!\n")

    logging.info("\n\n" + "="*60)
    logging.info("--- [TRADING SIMULATION REPORT] ---")
    logging.info("="*60)
    if not trades:
        logging.info("No trades were executed during the simulation period.")
    else:
        num_trades = len(trades)
        num_wins = sum(1 for t in trades if t['profit_pct'] > 0)
        report_data = []
        for t in trades:
            report_data.append({
                'Entry Date': t['entry_date'].strftime('%Y-%m-%d'),
                'Entry Price': f"${t['entry_price']:.2f}",
                'Exit Date': t['exit_date'].strftime('%Y-%m-%d'),
                'Exit Price': f"${t['exit_price']:.2f}",
                'Exit Reason': t['exit_reason'],
                'Profit %': f"{t['profit_pct']:.2f}%"
            })
        report_df = pd.DataFrame(report_data)
        logging.info("\n--- [Trade Log] ---")
        logging.info("\n" + report_df.to_markdown(index=False))
        total_profit_sum = sum(t['profit_pct'] for t in trades)
        logging.info(f"\nTotal Trades: {num_trades} | Win Rate: {(num_wins/num_trades)*100:.2f}%")
        logging.info(f"Average Profit/Loss per Trade: {total_profit_sum/num_trades:.2f}%")
    logging.info("="*60)
    logging.info("--- [Backtest Finished] ---")

def run_audit_mode(targets, archetypes_db):
    logging.info("--- [Master Scanner: AUDIT MODE Started] ---")
    # ... (This function can be implemented later if needed, focusing on the core backtester first)
    logging.warning("Audit mode is not the primary focus. Please use backtest mode.")
    pass

def main():
    parser = argparse.ArgumentParser(description="Master Scanner v2.0 (Based on Trading Simulator v4.1)")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--m", type=int, required=True)
    parser.add_argument("--logfile", required=True)
    args = parser.parse_args()

    setup_logging(args.logfile)
    archetypes_db = load_archetypes(LIBRARY_PATH)
    if not archetypes_db:
        logging.critical("No archetypes loaded. Exiting.")
        return
    
    # For now, this script IS the backtester. The mode logic is simplified.
    run_backtest_mode(args, archetypes_db)

if __name__ == "__main__":
    main()