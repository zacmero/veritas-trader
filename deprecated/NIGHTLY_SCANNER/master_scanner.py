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
import pickle
from colorama import init, Fore, Style

# --- IMPORTS ---
# from parser12 import fetch_news_for_symbols (deprecated)

# --- INITIALIZE COLORAMA ---
init(autoreset=True)

# --- CONFIGURATION ---
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
TARGETS_FILE = os.path.join(BASE_PATH, "TARGETS", "elite_targets.txt")
CACHE_PATH = os.path.join(BASE_PATH, "SCANNER_CACHE")
LOG_PATH = os.path.join(BASE_PATH, "LOGS")
LIBRARY_PATH = os.path.normpath(os.path.join(BASE_PATH, "..", "ARCHETYPE_LIBRARY_FINAL"))
CANDIDATE_PATH = os.path.normpath(os.path.join(BASE_PATH, "..", "CANDIDATE_LIBRARY"))

os.makedirs(CACHE_PATH, exist_ok=True)
os.makedirs(LOG_PATH, exist_ok=True)
os.makedirs(CANDIDATE_PATH, exist_ok=True)

# --- STRATEGY PARAMETERS ---
M_VALUES_TO_SCAN = [15, 30, 60, 90, 120]
HISTORY_YEARS = 5
MIN_PERCENTAGE_GROWTH = 10.0
DNA_STRICT_THRESHOLD = 2.75
DNA_LOOSE_THRESHOLD = 4.75
DNA_WINDOW = 30
ATR_PERIOD = 14
ATR_MULTIPLIER = 3.0
MIN_PROFIT_FOR_LEARNING = 50.0
MIN_GROWTH_PERCENTILE_FOR_LEARNING = 98.0
DUPLICATE_ARCHETYPE_THRESHOLD = 0.5

# --- VOLATILITY FILTER PARAMETERS ---
VOLATILITY_LOWER_PERCENTILE = 25.0
VOLATILITY_UPPER_PERCENTILE = 90.0

# --- NEWS SYSTEM CONFIGURATION ---
NEWS_ANALYSIS_START_DATE = "2099-12-31" # <-- Far future date for disabling -- Normal Config: NEWS_ANALYSIS_START_DATE = (datetime.now() - timedelta(days=1*1)).strftime('%Y-%m-%d') # 1x1 practically disabled.

# --- BLACK SHEEP THRESHOLDS ---
MIN_WIN_RATE_THRESHOLD = 50.0
MIN_AVG_PROFIT_THRESHOLD = 0.0

# --- SETUP: LOGGING ---
def setup_logging(log_filename):
    os.makedirs(LOG_PATH, exist_ok=True)
    log_file = os.path.join(LOG_PATH, log_filename)
    for handler in logging.root.handlers[:]: logging.root.removeHandler(handler)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)-7s] %(message)s", handlers=[logging.FileHandler(log_file, mode='w'), logging.StreamHandler()])
    logging.getLogger("yfinance").setLevel(logging.ERROR)
    logging.getLogger("stumpy").setLevel(logging.ERROR)
    warnings.filterwarnings("ignore", message="`Q` must be 1-dimensional and was automatically flattened")

# --- HELPER & FILTER FUNCTIONS ---
def z_normalize(series):
    std_dev = np.std(series)
    if std_dev < 1e-6: return np.zeros_like(series)
    return (series - np.mean(series)) / std_dev

def load_archetypes(library_path):
    archetypes_db = {}
    if not os.path.exists(library_path):
        logging.warning(f"Archetype library not found at {library_path}")
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

def run_volatility_filter(full_data, trigger_index):
    historical_atr = full_data['atr'].dropna()
    current_atr = full_data['atr'].iloc[trigger_index]
    
    if pd.isna(current_atr):
        logging.info(Fore.RED + "  [Filter 1.5] VOLATILITY FAILED. ATR data not available.")
        return False

    atr_percentile = percentileofscore(historical_atr, current_atr)
    
    logging.info(f"  [Filter 1.5] Volatility Check: Current ATR is at the {atr_percentile:.2f}th percentile of its history.")
    
    if atr_percentile < VOLATILITY_LOWER_PERCENTILE:
        logging.info(Fore.RED + f"  [Filter 1.5] VOLATILITY FAILED. Too low (less than {VOLATILITY_LOWER_PERCENTILE}th percentile). Stock is 'dead'.")
        return False
        
    if atr_percentile >= VOLATILITY_UPPER_PERCENTILE:
        logging.info(Fore.RED + f"  [Filter 1.5] VOLATILITY FAILED. Too high (greater than {VOLATILITY_UPPER_PERCENTILE}th percentile). Too chaotic for a clean entry.")
        return False
        
    logging.info(Fore.GREEN + "  [Filter 1.5] VOLATILITY PASSED. Environment is suitable for entry.")
    return True

def run_entry_filters(current_ts_window, archetypes_db):
    growth = calculate_percentage_growth(current_ts_window)
    # Return dictionary for detailed logging
    result = {'growth': growth}
    
    logging.info(f"  [Filter 2] 30-Day Growth Check: {growth:.2f}%")
    if growth < MIN_PERCENTAGE_GROWTH:
        logging.info(Fore.RED + f"  [Filter 2] FAILED. Growth < {MIN_PERCENTAGE_GROWTH}%.")
        result['status'] = 'fail_growth'
        return result
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
    
    result.update({'distance': best_match_distance, 'match_name': best_match_name})
    
    logging.info(f"  [Filter 3] DNA Test Best Match: '{best_match_name}' (Distance: {best_match_distance:.4f})")
    if best_match_distance <= DNA_LOOSE_THRESHOLD:
        match_type = "Strict" if best_match_distance <= DNA_STRICT_THRESHOLD else "Loose"
        logging.info(Fore.GREEN + f"  [Filter 3] PASSED ({match_type} Match).")
        result.update({'status': 'pass', 'match_type': match_type})
        return result
    
    logging.info(Fore.RED + f"  [Filter 3] FAILED. Distance > {DNA_LOOSE_THRESHOLD}.")
    result['status'] = 'fail_dna'
    return result

def analyze_news_context(ticker, trade_date):
    logging.info(Fore.CYAN + f"--- [News System] Fetching news context for {ticker} around {trade_date.strftime('%Y-%m-%d')}... ---")
    try:
        df_news = fetch_news_for_symbols([ticker], save=False, target_date=trade_date)
        if df_news.empty:
            return "No news found in the 30 days prior.", 0.0, []
        avg_sentiment = df_news['Score'].mean()
        news_volume = len(df_news)
        top_headlines = df_news.nlargest(3, 'Score')['Title'].tolist()
        volume_desc = f"High ({news_volume} articles)" if news_volume > 10 else f"Normal ({news_volume} articles)"
        return volume_desc, avg_sentiment, top_headlines
    except Exception as e:
        logging.error(f"--- [News System] Failed to fetch news for {ticker}. ---", exc_info=True)
        return "Error", 0.0, []

def get_investment_tier(m_value):
    if m_value >= 90: return "Tier 1: Elephant Hunter", "25%"
    if m_value == 60: return "Tier 2: Workhorse", "20%"
    if m_value == 15: return "Tier 2: Lottery Ticket", "20%"
    if m_value == 30: return "Tier 3: Standard", "15%"
    return "N/A", "N/A"

# --- MAIN SIMULATION ENGINE ---
def main(args):
    setup_logging(args.logfile)
    logging.info(f"--- [Master Simulator vFinal Started for {args.ticker}] ---")
    
    archetypes_db = load_archetypes(LIBRARY_PATH)
    if not archetypes_db:
        logging.critical("No archetypes loaded. Exiting.")
        return

    full_data = yf.download(args.ticker, start=args.start, end=args.end, progress=False, auto_adjust=True)
    if full_data.empty or len(full_data) < args.m * 2:
        logging.critical("Not enough data. Exiting.")
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

    # --- CRITICAL FIX: EDGE VALLEY DETECTOR ---
    # find_peaks cannot find a valley at the very end of the data (today).
    # We manually check if the current CAC is critically low (Regime Change active NOW).
    
    cac_threshold = np.percentile(cac, 10) # Bottom 10% indicates regime change
    
    # Check the last 3 days
    for i in range(1, 4):
        if len(cac) >= i:
            if cac[-i] <= cac_threshold:
                date_str = dates[-i].strftime('%Y-%m-%d')
                valley_dates.add(date_str)
                # We add it silently to the set so the loop catches it
    # ------------------------------------------

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
            # --- EXIT: ATR TRAILING STOP ---
            if np.isnan(current_atr): continue
            new_stop_price = current_price - (current_atr * ATR_MULTIPLIER)
            trailing_stop_price = max(trailing_stop_price, new_stop_price)
            
            if current_price < trailing_stop_price:
                current_trade['exit_date'] = current_date
                current_trade['exit_price'] = current_price
                current_trade['exit_reason'] = "ATR Trailing Stop"
                profit = ((current_trade['exit_price'] - current_trade['entry_price']) / current_trade['entry_price']) * 100
                current_trade['profit_pct'] = profit
                trades.append(current_trade)
                logging.info(Fore.YELLOW + f"\n!!! SELL SIGNAL on {current_date.strftime('%Y-%m-%d')} at ${current_price:.2f}. Reason: {current_trade['exit_reason']}. Profit: {profit:.2f}% !!!\n")
                
                # --- SMART LEARNING SYSTEM ---
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
            # --- ENTRY LOGIC ---
            if current_date.strftime('%Y-%m-%d') in valley_dates:
                logging.info(f"\n--- [F1 TRIGGER] Pre-calculated CAC Valley detected on {current_date.strftime('%Y-%m-%d')} ---")
                
                # Filter 1.5: Volatility
                if run_volatility_filter(full_data, i):
                    if i < DNA_WINDOW: continue
                    past_30_day_pattern = ts[i - DNA_WINDOW + 1 : i + 1]
                    
                    # Filters 2 & 3: Growth & DNA
                    entry_signal = run_entry_filters(past_30_day_pattern, archetypes_db)
                    
                    if entry_signal and entry_signal['status'] == 'pass':
                        # News Companion
                        if current_date.strftime('%Y-%m-%d') >= NEWS_ANALYSIS_START_DATE:
                            news_volume, avg_sentiment, top_headlines = analyze_news_context(args.ticker, current_date)
                            tier_name, allocation = get_investment_tier(args.m)
                            news_log = f"""
{Fore.CYAN}--- NEWS CONTEXT (Past 30 Days) ---
- News Volume:    {news_volume}
- Avg. Sentiment: {avg_sentiment:+.2f}
- Investment Tier: {tier_name} (Alloc: {allocation})
- Top Headlines:
"""
                            for idx, headline in enumerate(top_headlines, 1):
                                news_log += f"  {idx}. {headline}\n"
                            logging.info(news_log)

                        # Execute Buy
                        in_trade = True
                        current_trade = { 
                            'entry_date': current_date, 
                            'entry_price': current_price, 
                            'trigger_pattern': past_30_day_pattern, 
                            'details': entry_signal
                        }
                        if np.isnan(current_atr):
                            trailing_stop_price = current_price * 0.8
                        else:
                            trailing_stop_price = current_price - (current_atr * ATR_MULTIPLIER)
                        logging.info(Fore.GREEN + f"\n!!! BUY SIGNAL on {current_date.strftime('%Y-%m-%d')} at ${current_price:.2f}. Match: {entry_signal['match_name']} ({entry_signal['match_type']}) !!!\n")

    # --- FINAL REPORT ---
    logging.info("\n\n" + "="*60)
    logging.info("--- [TRADING SIMULATION REPORT] ---")
    logging.info("="*60)
    
    if not trades:
        logging.info("No trades were executed during the simulation period.")
        logging.info("\n" + "="*60)
        logging.info(Fore.BLUE + "--- [STRATEGY VERDICT: PASSIVE] ---")
        logging.info(Fore.BLUE + "This detector is highly selective and found no valid entry signals.")
        logging.info("="*60)
    else:
        num_trades = len(trades)
        num_wins = sum(1 for t in trades if t['profit_pct'] > 0)
        win_rate = (num_wins / num_trades) * 100.0
        total_profit_sum = sum(t['profit_pct'] for t in trades)
        avg_profit = total_profit_sum / num_trades
        
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
        
        logging.info(f"\nTotal Trades: {num_trades} | Win Rate: {win_rate:.2f}%")
        logging.info(f"Average Profit/Loss per Trade: {avg_profit:.2f}%")

        # --- BLACK SHEEP VERDICT ---
        is_profitable = (win_rate >= MIN_WIN_RATE_THRESHOLD) and (avg_profit > MIN_AVG_PROFIT_THRESHOLD)
        logging.info("\n" + "="*60)
        if is_profitable:
            logging.info(Fore.GREEN + Style.BRIGHT + "--- [STRATEGY VERDICT: PROFITABLE] ---")
            logging.info(Fore.GREEN + "This is a historically high-quality, tradable strategy.")
        else:
            logging.info(Fore.RED + Style.BRIGHT + "--- [STRATEGY VERDICT: BLACK SHEEP] ---")
            logging.info(Fore.RED + "This is a historically unprofitable strategy. Human discretion is required.")
        logging.info("="*60)

    # --- LIVE STATUS CHECK ---
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
        logging.info("="*60)
        logging.info("--- [Master Scanner Finished] ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Master Simulator v5.2 (Final)")
    parser.add_argument("--ticker", required=True, help="Stock ticker symbol.")
    parser.add_argument("--start", required=True, help="Start date for historical analysis (YYYY-MM-DD).")
    parser.add_argument("--end", required=True, help="End date for historical analysis (YYYY-MM-DD).")
    parser.add_argument("--m", type=int, required=True, help="The 'm' value (subsequence length) for the detector.")
    parser.add_argument("--logfile", required=True, help="Filename for the log output.")
    args = parser.parse_args()
    main(args)