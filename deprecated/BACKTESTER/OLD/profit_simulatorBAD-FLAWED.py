import yfinance as yf
import stumpy
import pandas as pd
import numpy as np
from scipy.signal import find_peaks
from sklearn.linear_model import LinearRegression
import os
import logging
from datetime import datetime, timedelta
import time

# --- CONFIGURATION ---

# 1. Project Folders
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
LIBRARY_PATH = os.path.join(BASE_PATH, "..", "ARCHETYPE_LIBRARY")
TARGET_FILE_PATH = os.path.join(BASE_PATH, "targets.txt")
LOG_PATH = os.path.join(BASE_PATH, "LOGS")

# 2. Scanner Parameters
# We run 7 scanners in parallel for our 7 unique 'm' windows.
SCANNER_CONFIGS = [
    {'m': 15,  'name': 'FlashPumpDetector (m=15)'},
    {'m': 10,  'name': 'UltraFlashDetector (m=10)'}
]

# 3. Filter Parameters
SLOPE_QUALIFICATION_WINDOWS = [30, 60, 90] # Check all 3 slopes
DNA_QUALIFICATION_WINDOW = 30         # Standardized 30-day pattern for DNA test
MIN_POSITIVE_SLOPE_THRESHOLD = 0.001  # Must be slightly positive
DNA_STRICT_THRESHOLD = 2.75           # Tier 1 Alert
DNA_LOOSE_THRESHOLD = 4.75            # Tier 2 Alert

ALERT_COOLDOWN_DAYS = 90              # Wait 90 days after an alert for a ticker

# 4. Simulation Parameters
SIMULATION_START_DATE = "2019-09-01"
SIMULATION_END_DATE = "2022-01-01"
# 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
# We run the expensive calculations only on Fridays (weekday() == 4)
ANALYSIS_WEEKDAY = 4

# 5. Real-Time Trigger Logic Parameters
CAC_LOOKBACK_DAYS = 15     # Check for new valleys in the last 15 days
CAC_TRIGGER_PERCENTILE = 90.0 # Trigger if new valley is in the deepest 10% of history

# --- SETUP: LOGGING ---
def setup_logging():
    """Configures logging for the profit simulator."""
    os.makedirs(LOG_PATH, exist_ok=True)
    log_file = os.path.join(LOG_PATH, "profit_sim_FINAL_IPO_FIX.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-7s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, mode='w'), # Overwrite log each run
            logging.StreamHandler()
        ]
    )
    logging.getLogger("yfinance").setLevel(logging.ERROR)
    logging.getLogger("stumpy").setLevel(logging.ERROR)

# --- SETUP: LOAD ASSETS & ARCHETYPES ---
def load_archetypes(library_path):
    """Loads all 8 of our .npy archetype patterns from the library."""
    archetypes_db = {}
    if not os.path.exists(library_path):
        logging.warning(f"Archetype library not found: {library_path}. No DNA tests.")
        return archetypes_db
    for file in os.listdir(library_path):
        if file.endswith(".npy"):
            name = os.path.splitext(file)[0]
            path = os.path.join(library_path, file)
            try:
                archetypes_db[name] = np.load(path)
                logging.info(f"Loaded Archetype: {name}")
            except Exception as e:
                logging.error(f"Failed to load archetype {file}: {e}")
    if not archetypes_db:
        logging.warning(f"No .npy archetypes found. Filter 3 skipped.")
    return archetypes_db

def load_targets(target_file):
    """Loads the list of tickers to scan."""
    if not os.path.exists(target_file):
        logging.error(f"Target file not found: {target_file}. Exiting.")
        return []
    with open(target_file, 'r') as f:
        targets = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    logging.info(f"Loaded {len(targets)} tickers from {target_file}.")
    return targets

# --- DATA ACQUISITION ---
def fetch_all_data(targets, start_date, end_date):
    """Downloads the *full* historical data for *all* targets at once."""
    logging.info(f"Fetching full historical data for {len(targets)} tickers...")
    all_data = {}
    # Download buffer for initial calculations
    buffer_start = "2015-01-01"
    
    for ticker in targets:
        try:
            data = yf.download(ticker, start=buffer_start, end=end_date, interval="1d", progress=False)
            if not data.empty and len(data) > 150:
                all_data[ticker] = data['Close'] # Store only the 'Close' Series
                logging.info(f"Successfully fetched data for {ticker} ({len(data)} points)")
            else:
                 logging.warning(f"Skipping {ticker}: Not enough data ({len(data)} points)")
        except Exception as e:
            logging.error(f"Failed to download data for {ticker}: {e}")
    logging.info(f"Finished fetching data for {len(all_data)} tickers.")
    return all_data

# --- CORE ALGORITHMS ---

# --- FILTER 1: REAL-TIME TRIGGER LOGIC ---
def run_filter_1_trigger(ts_up_to_today, m_window_size, ticker, current_sim_date):
    """
    This is the REAL-TIME trigger logic. It detects a *newly formed*
    valley in the CAC curve and compares it to the historical threshold.
    """
    if len(ts_up_to_today) < m_window_size * 10:
        logging.info(f"[{ticker} m={m_window_size}] Not enough history ({len(ts_up_to_today)} < {m_window_size*10} days). Skipping.")
        return None # Not enough history yet

    try:
        mp_output = stumpy.stump(ts_up_to_today.flatten(), m=m_window_size)
        mp = mp_output[:, 0]
        I = mp_output[:, 1].astype(np.int64)
        cac, _ = stumpy.fluss(I, L=m_window_size, n_regimes=2)

        # We must have enough historical data to calculate a stable threshold
        historical_cac_for_threshold = cac[:-CAC_LOOKBACK_DAYS]
        if len(historical_cac_for_threshold) < 100:
            return None # Not enough history for a stable percentile

        # Calculate the historical threshold (e.g., 90th percentile of *negative* CAC)
        trigger_threshold = np.percentile(-historical_cac_for_threshold, CAC_TRIGGER_PERCENTILE)

        # Now, look for NEW valleys *only in the most recent data*
        recent_cac = cac[-CAC_LOOKBACK_DAYS:]
        recent_valleys_idx, _ = find_peaks(-recent_cac) # Find peaks in negative CAC

        if not recent_valleys_idx.any():
            return None # No new valley has appeared in the last 15 days

        # Find the deepest *new* valley that just appeared
        deepest_recent_valley_local_idx = recent_valleys_idx[np.argmin(recent_cac[recent_valleys_idx])]
        valley_depth_negative_cac = -recent_cac[deepest_recent_valley_local_idx]

        # Log the check
        logging.info(f"[{ticker} m={m_window_size}] F1 Check on {current_sim_date.strftime('%Y-%m-%d')}:")
        logging.info(f"  - New Valley Depth: {valley_depth_negative_cac:.4f}")
        logging.info(f"  - Hist. Threshold ({CAC_TRIGGER_PERCENTILE:.1f}%ile): {trigger_threshold:.4f}")

        # This is the trigger: Is the new valley significant?
        if valley_depth_negative_cac > trigger_threshold:
            # Calculate the index of the trigger relative to the full ts
            trigger_index = len(ts_up_to_today) - CAC_LOOKBACK_DAYS + deepest_recent_valley_local_idx
            logging.info(f"  - *** TRIGGERED *** (New valley is deeper than threshold)")
            return trigger_index
        else:
            logging.info(f"  - Not Triggered (New valley is not deep enough)")
            return None

    except Exception as e:
        if "STUMPY_ERROR" in str(e) or "zero variance" in str(e):
            pass # Suppress common, expected errors on flat data
        else:
            logging.error(f"ProfitSim Filter 1 failed for {ticker} m={m_window_size}: {e}")
        return None

# --- FILTER 2: "SMART" SLOPE ---
def run_filter_2_slope(full_ts, trigger_index, ticker):
    """Checks slopes over multiple horizons. Returns 30d pattern if qualified."""
    if trigger_index + DNA_QUALIFICATION_WINDOW >= len(full_ts):
        logging.info(f"[{ticker}] F2 FAILED: Trigger too close to end of data.")
        return None # Not enough *future* data to check slope

    ramp_pattern_30_day = full_ts[trigger_index : trigger_index + DNA_QUALIFICATION_WINDOW]
    if np.isnan(ramp_pattern_30_day).any():
        return None

    has_positive_slope = False
    best_slope = -np.inf
    for window in SLOPE_QUALIFICATION_WINDOWS:
        if trigger_index + window >= len(full_ts):
            continue # Not enough data for this specific window
        
        pattern = full_ts[trigger_index : trigger_index + window]
        if np.isnan(pattern).any(): continue

        X = np.arange(window).reshape(-1, 1)
        y = pattern
        try:
            model = LinearRegression().fit(X, y)
            slope = model.coef_[0]
            logging.info(f"[{ticker}] F2 Slope Check ({window}d): {slope:.4f}")
            if slope > best_slope: best_slope = slope
            if slope > MIN_POSITIVE_SLOPE_THRESHOLD: has_positive_slope = True
        except ValueError: continue

    if has_positive_slope:
        logging.info(f"[{ticker}] F2 PASSED. Best positive slope: {best_slope:.4f}")
        return {'best_slope': best_slope, 'ramp_pattern_30_day': ramp_pattern_30_day}
    else:
        logging.info(f"[{ticker}] F2 FAILED. No positive slope found.")
        return None

# --- FILTER 3: DNA TEST ---
def run_filter_3_dna_test(ramp_pattern_30_day, archetypes_db, ticker):
    """Compares the 30-day ramp pattern to all 8 loaded archetypes."""
    if not archetypes_db: return None
    try:
        normalized_ramp = (ramp_pattern_30_day - np.mean(ramp_pattern_30_day)) / np.std(ramp_pattern_30_day)
    except ZeroDivisionError: return None

    best_match_name, best_match_distance = None, np.inf

    for name, archetype in archetypes_db.items():
        if len(archetype) < len(normalized_ramp): continue
        
        distance_profile = stumpy.mass(normalized_ramp, archetype)
        min_distance = np.min(distance_profile)
        logging.info(f"[{ticker}] F3 DNA Test vs '{name}': Distance = {min_distance:.4f}")
        
        if min_distance < best_match_distance:
            best_match_distance, best_match_name = min_distance, name

    if best_match_distance <= DNA_STRICT_THRESHOLD:
        match_type = "Strict Match"
        logging.info(f"[{ticker}] F3 PASSED. Best Match: '{best_match_name}' (Distance: {best_match_distance:.4f}) <= Strict Threshold ({DNA_STRICT_THRESHOLD})")
        return {'distance': best_match_distance, 'match_name': best_match_name, 'match_type': match_type}
    elif best_match_distance <= DNA_LOOSE_THRESHOLD:
        match_type = "Loose Match"
        logging.info(f"[{ticker}] F3 PASSED. Best Match: '{best_match_name}' (Distance: {best_match_distance:.4f}) <= Loose Threshold ({DNA_LOOSE_THRESHOLD})")
        return {'distance': best_match_distance, 'match_name': best_match_name, 'match_type': match_type}
    else:
        logging.info(f"[{ticker}] F3 FAILED. Best Match Distance ({best_match_distance:.4f}) > Loose Threshold ({DNA_LOOSE_THRESHOLD})")
        return None

# --- MAIN SIMULATION ---
def main():
    setup_logging()
    logging.info("--- [Profit Simulator Started (v1.0 - Weekly Calc)] ---")

    targets = load_targets(TARGET_FILE_PATH)
    archetypes_db = load_archetypes(LIBRARY_PATH)
    scanner_configs = SCANNER_CONFIGS # The 7 m-value scanners

    if not targets or not archetypes_db:
        logging.critical("Missing targets or archetypes. Exiting.")
        return

    # Fetch *all* data first
    all_historical_data = fetch_all_data(targets, SIMULATION_START_DATE, SIMULATION_END_DATE)
    if not all_historical_data:
        logging.critical("No historical data fetched. Exiting.")
        return

    # Generate the full date range for simulation
    simulation_dates = pd.date_range(start=SIMULATION_START_DATE, end=SIMULATION_END_DATE, freq='B') # Business days

    alert_cooldowns = {ticker: pd.Timestamp(0) for ticker in all_historical_data}
    total_alerts_fired = 0

    # --- Time Simulation Loop ---
    for current_sim_date in simulation_dates:
        
        # --- SPEED OPTIMIZATION: ONLY RUN ONCE PER WEEK ---
        if current_sim_date.weekday() != ANALYSIS_WEEKDAY:
            # Log progress without running expensive calcs
            if current_sim_date.weekday() == 0: # Log on Mondays
                 logging.info(f"--- Simulating Week of: {current_sim_date.strftime('%Y-%m-%d')} ---")
            continue 
        
        today_str = current_sim_date.strftime('%Y-%m-%d')
        logging.info(f"--- === Running Weekly Analysis for: {today_str} === ---")

        # --- Ticker Loop (for this simulated Friday) ---
        for ticker, full_ts_series in all_historical_data.items():
            
            if current_sim_date < alert_cooldowns[ticker]:
                continue # In cooldown

            # Get data *only up to the current simulated day*
            ts_up_to_today_series = full_ts_series[:current_sim_date]


            ts_up_to_today_values = ts_up_to_today_series.values
            dates_up_to_today = ts_up_to_today_series.index
            
            logging.info(f"--- Analyzing Ticker: {ticker} on {today_str} ---")
            alert_fired_for_ticker_today = False

            # --- Run Parallel Scanners (for this ticker, for this day) ---
            for config in scanner_configs:
                if alert_fired_for_ticker_today: break # Only one alert per ticker per week max

                m = config['m']
                scanner_name = config['name']

                # --- FILTER 1 (Real-Time Trigger) ---
                trigger_index = run_filter_1_trigger(ts_up_to_today_values, m, ticker, current_sim_date)

                if trigger_index is not None:
                    trigger_date = dates_up_to_today[trigger_index].strftime('%Y-%m-%d')
                    logging.warning(f"[SIM F1] {ticker}: TRIGGER by {scanner_name} on {today_str} (Signal Date: {trigger_date})!")

                    # --- FILTER 2 (Using full timeseries for lookahead) ---
                    full_ts_values = full_ts_series.values
                    
                    slope_result = run_filter_2_slope(full_ts_values, trigger_index, ticker)

                    if slope_result:
                        slope = slope_result['best_slope']
                        logging.warning(f"[SIM F2] {ticker}: QUALIFIED ON {today_str}. Slope: {slope:.4f}")

                        # --- FILTER 3 ---
                        dna_result = run_filter_3_dna_test(slope_result['ramp_pattern_30_day'], archetypes_db, ticker)

                        if dna_result:
                            distance = dna_result['distance']
                            match_name = dna_result['match_name']
                            alert_level, alert_type = None, None

                            if distance <= DNA_STRICT_THRESHOLD:
                                alert_level = logging.CRITICAL
                                alert_type = "High Confidence Bubble Alert (Strict Match)"
                            elif distance <= DNA_LOOSE_THRESHOLD:
                                alert_level = logging.WARNING
                                alert_type = "Medium Confidence Bubble Alert (Loose Match)"

                            if alert_level:
                                log_message = (f"\n{'!':*62}\n!!!{'PROFIT SIMULATION ALERT TRIGGERED':^56}!!!\n{'!':*62}\n"
                                             f"  Ticker       : {ticker}\n"
                                             f"  ALERT DATE   : {today_str}\n"
                                             f"  Signal Date  : {trigger_date}\n"
                                             f"  Detector     : {scanner_name}\n"
                                             f"  Best Slope   : {slope:.4f}\n"
                                             f"  DNA Match    : {match_name}\n"
                                             f"  Distance     : {distance:.4f} (Strict < {DNA_STRICT_THRESHOLD}, Loose < {DNA_LOOSE_THRESHOLD})\n{'!':*62}\n")
                                logging.log(alert_level, log_message)
                                total_alerts_fired += 1
                                alert_fired_for_ticker_today = True
                                alert_cooldowns[ticker] = current_sim_date + timedelta(days=ALERT_COOLDOWN_DAYS)
                            else:
                                logging.info(f"[SIM F3] {ticker}: Uncategorized. Best match '{match_name}' (Dist: {distance:.4f}) > Loose Threshold.")
                        else:
                            logging.info(f"[SIM F3] {ticker}: Event ON {today_str} is uncategorized. No DNA match.")
                    else:
                        logging.info(f"[SIM F2] {ticker}: DISQUALIFIED ON {today_s_tr}. No positive slope.")

    logging.info(f"--- [Profit Simulation Finished] ---")
    logging.info(f"Total Alerts Fired: {total_alerts_fired}")

if __name__ == "__main__":
    main()