import yfinance as yf
import stumpy
import pandas as pd
import numpy as np
from scipy.signal import find_peaks
from sklearn.linear_model import LinearRegression
import os
import logging
from datetime import datetime, timedelta
import time # For simulating delays if needed

# --- CONFIGURATION ---

# 1. Project Folders
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
LIBRARY_PATH = os.path.join(BASE_PATH, "..", "ARCHETYPE_LIBRARY")
TARGET_FILE_PATH = os.path.join(BASE_PATH, "targets.txt")
LOG_PATH = os.path.join(BASE_PATH, "LOGS")

# 2. Scanner Parameters
SCANNER_CONFIGS = [
    {'m': 90,  'name': 'RegimeDetector (m=90)'}
]

# 3. Filter Parameters
SLOPE_QUALIFICATION_WINDOWS = [30, 60, 90]
DNA_QUALIFICATION_WINDOW = 30
MIN_POSITIVE_SLOPE_THRESHOLD = 0.001
DNA_MATCH_THRESHOLD = 2.75
BACKTEST_CAC_TRIGGER_PERCENTILE = 90.0
MIN_HISTORY_DAYS = 900 # Min days needed before starting analysis for a ticker
ALERT_COOLDOWN_DAYS = 90

# 4. Backtest Simulation Parameters
BACKTEST_START_DATE = "2020-10-01"
BACKTEST_END_DATE = "2022-01-01"

# --- SETUP: LOGGING ---
def setup_logging():
    """Configures logging for the backtester."""
    os.makedirs(LOG_PATH, exist_ok=True)
    log_file = os.path.join(LOG_PATH, "backtest_GME_only_m90_CorrectIndex.log")

    logging.basicConfig(
        level=logging.INFO, # Changed to DEBUG
        format="%(asctime)s [%(levelname)-7s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, mode='w'),
            logging.StreamHandler()
        ]
    )
    logging.getLogger("yfinance").setLevel(logging.ERROR)
    logging.getLogger("stumpy").setLevel(logging.ERROR)

# --- SETUP: LOAD ASSETS & ARCHETYPES ---
def load_archetypes(library_path):
    archetypes_db = {}
    if not os.path.exists(library_path):
        logging.warning(f"Archetype library not found: {library_path}. No DNA tests.")
        return archetypes_db
    for file in os.listdir(library_path):
        if file.endswith(".npy"):
            name = os.path.splitext(file)[0]
            path = os.path.join(library_path, file)
            archetypes_db[name] = np.load(path)
    return archetypes_db

def load_targets(target_file):
    logging.info("--- RUNNING FOCUSED BACKTEST FOR GME ONLY ---")
    return ["GME"]

# --- DATA ACQUISITION ---
def fetch_all_data(targets, start_date, end_date):
    logging.info(f"Fetching full historical data for {len(targets)} tickers...")
    all_data = {}
    for ticker in targets:
        buffer_start = (pd.to_datetime(start_date) - timedelta(days=MIN_HISTORY_DAYS*2)).strftime('%Y-%m-%d')
        data = yf.download(ticker, start=buffer_start, end=end_date, interval="1d", progress=False)
        if not data.empty and len(data) > MIN_HISTORY_DAYS:
            all_data[ticker] = data['Close']
    return all_data

# --- CORE ALGORITHMS (WITH DEBUG LOGGING) ---

# --- FILTER 1: SIMPLIFIED TRIGGER LOGIC ---
def run_filter_1_backtest_cac(ts_up_to_today, m_window_size, ticker, current_sim_date):
    if len(ts_up_to_today) < m_window_size * 10:
        return None

    try:
        mp_output = stumpy.stump(ts_up_to_today.flatten(), m=m_window_size)
        I = mp_output[:, 1].astype(np.int64)
        cac, _ = stumpy.fluss(I, L=m_window_size, n_regimes=2) # CORRECTED TO FLUSS

        # --- CAC DIAGNOSTIC ---
        last_5_cac_values = cac[-5:] if len(cac) >= 5 else cac
        logging.info(f"[{ticker} m={m_window_size}] CAC calculated. Len={len(cac)}. Last 5 values: {np.round(last_5_cac_values, 4)}")
        if len(cac) > 0:
            logging.info(f"[{ticker} m={m_window_size}] Min CAC: {np.min(cac):.4f}, Max CAC: {np.max(cac):.4f}, Mean CAC: {np.mean(cac):.4f}")
        # --- END DIAGNOSTIC ---

        historical_cac_for_threshold = cac[:-m_window_size]
        if len(historical_cac_for_threshold) < 100:
            logging.info(f"[{ticker} m={m_window_size}] Not enough historical CAC points ({len(historical_cac_for_threshold)}) for threshold calc.")
            return None

        trigger_threshold = np.percentile(historical_cac_for_threshold, 100 - BACKTEST_CAC_TRIGGER_PERCENTILE)
        
        # Check the CAC value corresponding to the START of the last window
        check_index = -m_window_size -1 # Index m+1 from the end relates to change point m from end
        if abs(check_index) >= len(cac):
             logging.warning(f"[{ticker} m={m_window_size}] CAC array too short ({len(cac)}) to check index {check_index}. Skipping.")
             return None
        relevant_cac_value = cac[check_index]

        # Log the value we are ACTUALLY checking now
        logging.info(f"[{ticker} m={m_window_size}] Filter 1 Check on {current_sim_date.strftime('%Y-%m-%d')}:")
        # Log the value at the check_index, not necessarily the absolute last value
        logging.info(f"  - Relevant CAC Value (at index {check_index}): {relevant_cac_value:.4f}") 
        logging.info(f"  - Hist. Threshold ({100 - BACKTEST_CAC_TRIGGER_PERCENTILE:.1f}%ile): {trigger_threshold:.4f}")

        # The Trigger Condition (using the relevant value)
        if relevant_cac_value < trigger_threshold:
            logging.info(f"  - *** TRIGGERED *** (Value at index {check_index} is below threshold)")
            # The trigger index is still TODAY in the simulation time series
            trigger_index = len(ts_up_to_today) - 1 
            return trigger_index
        else:
            logging.info(f"  - Not Triggered (Value at index {check_index} is >= threshold)")
            return None

    except Exception as e:
        if "STUMPY_ERROR" in str(e) or "zero variance" in str(e): pass
        else: logging.error(f"Backtest Filter 1 failed for m={m_window_size}: {e}")
        return None

# --- FILTER 2: SLOPE TEST WITH LOGGING ---
def run_filter_2_slope(full_ts, trigger_index, ticker):
    if trigger_index + DNA_QUALIFICATION_WINDOW >= len(full_ts): return None
    ramp_pattern_30_day = full_ts[trigger_index : trigger_index + DNA_QUALIFICATION_WINDOW]
    if np.isnan(ramp_pattern_30_day).any(): return None

    has_positive_slope = False
    best_slope = -np.inf
    for window in SLOPE_QUALIFICATION_WINDOWS:
        if trigger_index + window >= len(full_ts): continue
        pattern = full_ts[trigger_index : trigger_index + window]
        if np.isnan(pattern).any(): continue
        X = np.arange(window).reshape(-1, 1)
        try:
            model = LinearRegression().fit(X, pattern)
            slope = model.coef_[0]
            logging.info(f"[{ticker}] Filter 2 Slope Check ({window}d): {slope:.4f}")
            if slope > best_slope: best_slope = slope
            if slope > MIN_POSITIVE_SLOPE_THRESHOLD: has_positive_slope = True
        except ValueError: continue

    if has_positive_slope:
        logging.info(f"[{ticker}] Filter 2 PASSED on Multi-Horizon Slope Test.")
        return {'best_slope': best_slope, 'ramp_pattern_30_day': ramp_pattern_30_day}
    else:
        logging.info(f"[{ticker}] Filter 2 FAILED on Multi-Horizon Slope Test.")
        return None

# --- FILTER 3: DNA TEST WITH LOGGING ---
def run_filter_3_dna_test(ramp_pattern_30_day, archetypes_db, ticker):
    if not archetypes_db: return None
    try:
        normalized_ramp = (ramp_pattern_30_day - np.mean(ramp_pattern_30_day)) / np.std(ramp_pattern_30_day)
    except ZeroDivisionError: return None

    best_match_name, best_match_distance = None, np.inf
    for name, archetype in archetypes_db.items():
        if len(archetype) < len(normalized_ramp): continue
        distance_profile = stumpy.mass(normalized_ramp, archetype)
        min_distance = np.min(distance_profile)
        logging.info(f"[{ticker}] Filter 3 DNA Test vs '{name}': Distance = {min_distance:.4f}")
        if min_distance < best_match_distance:
            best_match_distance, best_match_name = min_distance, name

    if best_match_distance <= DNA_MATCH_THRESHOLD:
        logging.info(f"[{ticker}] Filter 3 PASSED. Best Match: '{best_match_name}' (Dist: {best_match_distance:.4f}) <= Threshold ({DNA_MATCH_THRESHOLD})")
        return {'distance': best_match_distance, 'match_name': best_match_name}
    else:
        logging.info(f"[{ticker}] Filter 3 FAILED. Best Match Distance ({best_match_distance:.4f}) > Threshold ({DNA_MATCH_THRESHOLD})")
        return None

# --- MAIN BACKTEST SIMULATION ---
def main():
    setup_logging()
    logging.info("--- [Walk-Forward Backtester Started with Final Trigger Logic] ---")
    targets, archetypes_db = load_targets(TARGET_FILE_PATH), load_archetypes(LIBRARY_PATH)
    all_historical_data = fetch_all_data(targets, BACKTEST_START_DATE, BACKTEST_END_DATE)
    if not all_historical_data: return

    simulation_dates = pd.date_range(start=BACKTEST_START_DATE, end=BACKTEST_END_DATE, freq='B')
    alert_cooldowns = {ticker: pd.Timestamp(0) for ticker in all_historical_data}
    total_alerts_fired = 0

    for current_sim_date in simulation_dates:
        today_str = current_sim_date.strftime('%Y-%m-%d')
        logging.info(f"--- Simulating Day: {today_str} ---")
        for ticker, full_ts_series in all_historical_data.items():
            if current_sim_date < alert_cooldowns[ticker]: continue
            ts_up_to_today_series = full_ts_series[:current_sim_date]
            if len(ts_up_to_today_series) < MIN_HISTORY_DAYS:
                continue # Not enough history yet for this ticker

            alert_fired_for_ticker_today = False
            for config in SCANNER_CONFIGS:
                if alert_fired_for_ticker_today: break
                m, scanner_name = config['m'], config['name']
                if len(ts_up_to_today_series) < m * 10: continue
                
                trigger_index = run_filter_1_backtest_cac(ts_up_to_today_series.values, m, ticker, current_sim_date)
                if trigger_index is not None:
                    logging.warning(f"[BACKTEST F1] {ticker}: TRIGGER by {scanner_name} ON {today_str}!")
                    slope_result = run_filter_2_slope(full_ts_series.values, trigger_index, ticker)
                    if slope_result:
                        logging.warning(f"[BACKTEST F2] {ticker}: QUALIFIED ON {today_str}. Slope: {slope_result['best_slope']:.4f}")
                        dna_result = run_filter_3_dna_test(slope_result['ramp_pattern_30_day'], archetypes_db, ticker)
                        if dna_result:
                            log_message = (f"\n{'!':*62}\n!!!{'BACKTEST BUBBLE ALERT TRIGGERED':^56}!!!\n{'!':*62}\n"
                                         f"  Ticker       : {ticker}\n  ALERT DATE   : {today_str}\n  Detector     : {scanner_name}\n"
                                         f"  Best Slope   : {slope_result['best_slope']:.4f}\n  DNA Match    : {dna_result['match_name']}\n"
                                         f"  Distance     : {dna_result['distance']:.4f} (Threshold: {DNA_MATCH_THRESHOLD})\n{'!':*62}\n")
                            logging.critical(log_message)
                            total_alerts_fired += 1
                            alert_fired_for_ticker_today = True
                            alert_cooldowns[ticker] = current_sim_date + timedelta(days=ALERT_COOLDOWN_DAYS)
                        else: logging.info(f"[BACKTEST F3] {ticker}: Uncategorized event on {today_str}.")
                    else: logging.info(f"[BACKTEST F2] {ticker}: DISQUALIFIED on {today_str}.")

    logging.info(f"--- [Backtest Finished] ---")
    logging.info(f"Total Alerts Fired: {total_alerts_fired}")

if __name__ == "__main__":
    main()