import yfinance as yf
import stumpy
import pandas as pd
import numpy as np
from scipy.signal import find_peaks
from sklearn.linear_model import LinearRegression
import os
import logging
from datetime import datetime

# --- CONFIGURATION ---

# 1. Project Folders
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
LIBRARY_PATH = os.path.join(BASE_PATH, "..", "ARCHETYPE_LIBRARY")
TARGET_FILE_PATH = os.path.join(BASE_PATH, "targets.txt")
LOG_PATH = os.path.join(BASE_PATH, "LOGS")

# 2. Scanner Parameters
SCANNER_CONFIGS = [
    {'m': 180, 'name': 'SlowBuildDetector (m=180)'},
    {'m': 120, 'name': 'SlowBuildDetector (m=120)'},
    {'m': 90,  'name': 'RegimeDetector (m=90)'},
    {'m': 30,  'name': 'ShockDetector (m=30)'},
    {'m': 15,  'name': 'FlashPumpDetector (m=15)'}
]

# 3. Filter Parameters
# *** NEW v1.1 LOGIC ***
# Filter 2 will check all these windows for a positive slope.
SLOPE_QUALIFICATION_WINDOWS = [30, 60, 90]
# Filter 3 will *always* use this window for the "apples-to-apples" DNA test.
DNA_QUALIFICATION_WINDOW = 30
MIN_POSITIVE_SLOPE_THRESHOLD = 0.001 # Small positive num to confirm it's not a downtrend
# *** END NEW LOGIC ***

DNA_MATCH_THRESHOLD = 2.75 
CAC_LOOKBACK_DAYS = 15     
CAC_TRIGGER_PERCENTILE = 95.0 

# --- SETUP: LOGGING ---
def setup_logging():
    """Configures the logging system to log to both file and console."""
    os.makedirs(LOG_PATH, exist_ok=True)
    log_file = os.path.join(LOG_PATH, "scanner.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-7s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, mode='a'), 
            logging.StreamHandler()                 
        ]
    )
    
    logging.getLogger("yfinance").setLevel(logging.ERROR)
    logging.getLogger("stumpy").setLevel(logging.ERROR)

# --- SETUP: LOAD ASSETS & ARCHETYPES ---
def load_archetypes(library_path):
    """Loads all .npy archetype patterns from the library into memory."""
    archetypes_db = {}
    if not os.path.exists(library_path):
        logging.warning(f"Archetype library not found at: {library_path}. No DNA tests will be run.")
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
        logging.warning(f"No .npy archetypes found in {library_path}. Filter 3 will be skipped.")
        
    return archetypes_db

def load_targets(target_file):
    """Loads the list of tickers to scan from a simple text file."""
    if not os.path.exists(target_file):
        logging.error(f"Target file not found: {target_file}. No assets to scan.")
        return []
    
    with open(target_file, 'r') as f:
        targets = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    
    logging.info(f"Loaded {len(targets)} tickers to scan from {target_file}.")
    return targets

# --- DATA ACQUISITION ---
def fetch_data(ticker):
    """Downloads 5 years of daily data for a single ticker."""
    try:
        data = yf.download(ticker, period="5y", interval="1d", progress=False)
        if data.empty:
            logging.warning(f"No data returned for {ticker}.")
            return None
        
        ts = data['Close'].values
        dates = data.index
        return ts, dates
    except Exception as e:
        logging.error(f"Failed to download data for {ticker}: {e}")
        return None

# --- FILTER 1: REGIME CHANGE (CAC) ---
def run_filter_1_cac(ts, m_window_size):
    """
    Runs the CAC algorithm and checks the *last few days* for a new,
    significant regime change.
    """
    if len(ts) < m_window_size * 10: 
        logging.warning(f"Not enough data for m={m_window_size} (Need {m_window_size*10}, got {len(ts)}). Skipping.")
        return None
        
    try:
        mp_output = stumpy.stump(ts.flatten(), m=m_window_size)
        mp = mp_output[:, 0]
        I = mp_output[:, 1]
        cac, _ = stumpy.fluss(I, L=m_window_size, n_regimes=2)
        
        recent_cac = cac[-CAC_LOOKBACK_DAYS:]
        
        recent_valleys_idx, _ = find_peaks(-recent_cac)
        
        if not recent_valleys_idx.any():
            return None 
            
        deepest_recent_valley_local_idx = recent_valleys_idx[np.argmin(recent_cac[recent_valleys_idx])]
        
        historical_threshold = np.percentile(-cac, CAC_TRIGGER_PERCENTILE)
        valley_depth = -recent_cac[deepest_recent_valley_local_idx]
        
        if valley_depth > historical_threshold:
            trigger_index = len(ts) - CAC_LOOKBACK_DAYS + deepest_recent_valley_local_idx
            return trigger_index
        else:
            return None 
            
    except Exception as e:
        if "STUMPY_ERROR" in str(e):
            logging.warning(f"STUMPY failed for m={m_window_size} (likely constant data). Skipping.")
        else:
            logging.error(f"Filter 1 failed for m={m_window_size}: {e}")
        return None

# --- *** NEW v1.1 *** ---
# --- FILTER 2: "SMART" REGIME QUALIFICATION (SLOPE) ---
def run_filter_2_slope(ts, trigger_index):
    """
    Checks if the period *after* the trigger has a positive slope
    over *multiple horizons* (e.g., 30, 60, 90 days).
    If *any* are positive, it qualifies.
    It returns the 30-day pattern for the DNA test.
    """
    
    # First, check if we have enough data for the standardized DNA test pattern
    if trigger_index + DNA_QUALIFICATION_WINDOW >= len(ts):
        logging.info("Trigger is too recent, not enough data for 30-day DNA test pattern. Waiting.")
        return None
        
    # Get the 30-day pattern for Filter 3 (DNA Test)
    ramp_pattern_30_day = ts[trigger_index : trigger_index + DNA_QUALIFICATION_WINDOW]
    
    if np.isnan(ramp_pattern_30_day).any():
        logging.warning(f"NaNs in 30-day ramp pattern at {trigger_index}. Disqualifying.")
        return None

    has_positive_slope = False
    best_slope = -np.inf

    # Now, check all our qualification windows (30, 60, 90 days)
    for window in SLOPE_QUALIFICATION_WINDOWS:
        if trigger_index + window >= len(ts):
            continue # Not enough data for this specific window
        
        pattern = ts[trigger_index : trigger_index + window]
        
        if np.isnan(pattern).any():
            continue # Skip if data is bad

        X = np.arange(window).reshape(-1, 1)
        y = pattern
        
        try:
            model = LinearRegression().fit(X, y)
            slope = model.coef_[0]
        except ValueError:
            continue

        if slope > best_slope:
            best_slope = slope
        
        if slope > MIN_POSITIVE_SLOPE_THRESHOLD:
            has_positive_slope = True
    
    if has_positive_slope:
        logging.info(f"Multi-slope test PASSED. Best slope (up to {SLOPE_QUALIFICATION_WINDOWS[-1]}d): {best_slope:.4f}")
        # Return the 30-DAY pattern for a fair "apples-to-apples" DNA test
        return {'best_slope': best_slope, 'ramp_pattern_30_day': ramp_pattern_30_day, 'start_index': trigger_index}
    else:
        logging.info(f"Multi-slope test FAILED. Best slope: {best_slope:.4f}. Disqualifying.")
        return None

# --- FILTER 3: BUBBLE DNA TEST (MASS) ---
# This function is now simpler, as it only gets the 30-day pattern
def run_filter_3_dna_test(ramp_pattern_30_day, archetypes_db):
    """Compares the standardized 30-day ramp pattern to all loaded archetypes."""
    if not archetypes_db:
        return None # No archetypes to test against
        
    try:
        # Normalize the new pattern for shape-based comparison
        normalized_ramp = (ramp_pattern_30_day - np.mean(ramp_pattern_30_day)) / np.std(ramp_pattern_30_day)
    except ZeroDivisionError:
        logging.warning(f"Cannot normalize ramp (std is zero). Skipping DNA test.")
        return None
        
    best_match_name = None
    best_match_distance = np.inf
    
    for name, archetype in archetypes_db.items():
        # Ensure archetype is at least as long as ramp pattern
        if len(archetype) < len(normalized_ramp):
            logging.warning(f"Skipping archetype {name}: length {len(archetype)} < ramp length {len(normalized_ramp)}")
            continue
            
        # Run MASS (Fast Subsequence Search)
        # We search for our 30-day ramp *within* the (potentially longer) archetype
        # Note: Swapped order for stumpy.mass(query, timeseries)
        distance_profile = stumpy.mass(normalized_ramp, archetype)
        min_distance = np.min(distance_profile)
        
        if min_distance < best_match_distance:
            best_match_distance = min_distance
            best_match_name = name
            
    if best_match_distance <= DNA_MATCH_THRESHOLD:
        return {'distance': best_match_distance, 'match_name': best_match_name}
    else:
        return None # No match was close enough

# --- MAIN EXECUTION ---
def main():
    """Main function to run the nightly scanner."""
    setup_logging()
    logging.info("--- [Nightly Scanner Started (v1.1 - Smart Slope)] ---")
    
    # --- Load Assets ---
    targets = load_targets(TARGET_FILE_PATH)
    archetypes_db = load_archetypes(LIBRARY_PATH)
    scanner_configs = SCANNER_CONFIGS
    
    if not targets:
        logging.critical("No targets loaded. Exiting.")
        return
        
    total_alerts = 0

    # --- Main Loop ---
    for ticker in targets:
        logging.info(f"--- Scanning Ticker: {ticker} ---")
        data = fetch_data(ticker)
        
        if data is None:
            continue
            
        ts, dates = data
        
        # Run all parallel scanners
        for config in scanner_configs:
            m = config['m']
            scanner_name = config['name']
            
            logging.info(f"Running Detector: {scanner_name} (m={m})")
            
            # --- FILTER 1 ---
            trigger_index = run_filter_1_cac(ts, m)
            
            if trigger_index:
                trigger_date = dates[trigger_index].strftime('%Y-%m-%d')
                logging.warning(f"[FILTER 1] {ticker}: Potential regime change detected by {scanner_name} at {trigger_date}!")
                
                # --- FILTER 2 (Smart Slope) ---
                slope_result = run_filter_2_slope(ts, trigger_index)
                
                if slope_result:
                    slope = slope_result['best_slope']
                    logging.warning(f"[FILTER 2] {ticker}: Trigger QUALIFIED. Positive multi-horizon slope found (best: {slope:.4f})")
                    
                    # --- FILTER 3 ---
                    dna_result = run_filter_3_dna_test(slope_result['ramp_pattern_30_day'], archetypes_db)
                    
                    if dna_result:
                        # --- !ALERT! ---
                        distance = dna_result['distance']
                        match_name = dna_result['match_name']
                        
                        log_message = (
                            f"\n"
                            f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
                            f"!!!               ARCHETYPE BUBBLE ALERT                 !!!\n"
                            f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
                            f"  Ticker       : {ticker}\n"
                            f"  Trigger Date : {trigger_date}\n"
                            f"  Detector     : {scanner_name}\n"
                            f"  Best Slope   : {slope:.4f}\n"
                            f"  DNA Match    : {match_name}\n"
                            f"  Distance     : {distance:.4f} (Threshold: {DNA_MATCH_THRESHOLD})\n"
                            f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
                        )
                        logging.critical(log_message)
                        total_alerts += 1
                    else:
                        logging.info(f"[FILTER 3] {ticker}: Event is uncategorized. No DNA match found.")
                else:
                    logging.info(f"[FILTER 2] {ticker}: Trigger DISQUALIFIED. No positive multi-horizon slope.")
            else:
                logging.info(f"No recent trigger found for {scanner_name}.")
                
    logging.info(f"--- [Nightly Scanner Finished] ---")
    logging.info(f"Total Alerts Fired: {total_alerts}")

if __name__ == "__main__":
    main()