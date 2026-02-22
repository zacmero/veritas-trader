import yfinance as yf
import stumpy
import pandas as pd
import numpy as np
from scipy.signal import find_peaks
from sklearn.linear_model import LinearRegression
import os
import logging
import argparse

# --- CONFIGURATION ---
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
LIBRARY_PATH = os.path.join(BASE_PATH, "..", "ARCHETYPE_LIBRARY")
LOG_PATH = os.path.join(BASE_PATH, "LOGS")

DNA_MATCH_THRESHOLD = 2.75
SLOPE_QUALIFICATION_WINDOWS = [30, 60, 90]
DNA_QUALIFICATION_WINDOW = 30
MIN_POSITIVE_SLOPE_THRESHOLD = 0.001

# --- SETUP: LOGGING ---
def setup_logging(log_filename):
    os.makedirs(LOG_PATH, exist_ok=True)
    log_file = os.path.join(LOG_PATH, log_filename)
    
    # Remove existing handlers if any
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
        
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-7s] %(message)s",
        handlers=[logging.FileHandler(log_file, mode='w'), logging.StreamHandler()]
    )
    logging.getLogger("yfinance").setLevel(logging.ERROR)
    logging.getLogger("stumpy").setLevel(logging.ERROR)

# --- HELPER FUNCTIONS ---
def load_archetypes(library_path):
    archetypes_db = {}
    if not os.path.exists(library_path):
        logging.warning(f"Archetype library not found. No DNA tests will be run.")
        return archetypes_db
    for file in os.listdir(library_path):
        if file.endswith(".npy"):
            name = os.path.splitext(file)[0]
            path = os.path.join(library_path, file)
            archetypes_db[name] = np.load(path)
    return archetypes_db

def run_filter_2_slope(full_ts, dates, trigger_index, m_window_size):
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
            slope = float(model.coef_[0])
            logging.info(f"  [Filter 2] Valley at {dates[trigger_index].strftime('%Y-%m-%d')}: Slope Check ({window}d) = {slope:.4f}")
            if slope > best_slope: best_slope = slope
            if slope > MIN_POSITIVE_SLOPE_THRESHOLD: has_positive_slope = True
        except ValueError: continue

    if has_positive_slope:
        return {'best_slope': best_slope, 'ramp_pattern_30_day': ramp_pattern_30_day}
    else:
        return None

def run_filter_3_dna_test(ramp_pattern_30_day, archetypes_db):
    if not archetypes_db: return None
    try:
        normalized_ramp = (ramp_pattern_30_day - np.mean(ramp_pattern_30_day)) / np.std(ramp_pattern_30_day)
    except ZeroDivisionError: return None

    best_match_name, best_match_distance = None, np.inf
    for name, archetype in archetypes_db.items():
        if len(archetype) < len(normalized_ramp): continue
        distance_profile = stumpy.mass(normalized_ramp, archetype)
        min_distance = np.min(distance_profile)
        logging.info(f"    [Filter 3] DNA Test vs '{name}': Distance = {min_distance:.4f}")
        if min_distance < best_match_distance:
            best_match_distance, best_match_name = min_distance, name

    if best_match_distance <= DNA_MATCH_THRESHOLD:
        return {'distance': best_match_distance, 'match_name': best_match_name}
    else:
        return None

# --- MAIN ANALYSIS ---
def main(args):
    setup_logging(args.logfile)
    logging.info(f"--- [Historical Analyzer Started for {args.ticker}] ---")

    ts_full_series = yf.download(args.ticker, start=args.start, end=args.end, progress=False)['Close']
    ts = ts_full_series.values
    dates = ts_full_series.index
    logging.info(f"Loaded {len(ts)} data points for {args.ticker}.")

    archetypes_db = load_archetypes(LIBRARY_PATH)

    logging.info(f"Computing full CAC curve with m={args.m}...")
    mp_output = stumpy.stump(ts.flatten(), m=args.m)
    I = mp_output[:, 1].astype(np.int64)
    cac, _ = stumpy.fluss(I, L=args.m, n_regimes=10)

    valleys, _ = find_peaks(-cac, distance=args.m, prominence=0.01)
    logging.info(f"Found {len(valleys)} significant valleys in the CAC curve.")

    passed_filter2 = 0
    passed_filter3 = 0
    for valley_idx in valleys:
        valley_date = dates[valley_idx]
        logging.info(f"\n--- Analyzing Valley at {valley_date.strftime('%Y-%m-%d')} (index {valley_idx}) ---")

        slope_result = run_filter_2_slope(ts, dates, valley_idx, args.m)
        
        if slope_result:
            passed_filter2 += 1
            logging.info(f"  [Filter 2] PASSED. Best positive slope: {slope_result['best_slope']:.4f}")
            
            dna_result = run_filter_3_dna_test(slope_result['ramp_pattern_30_day'], archetypes_db)
            if dna_result:
                passed_filter3 += 1
                logging.info(f"    [Filter 3] PASSED. Best Match: '{dna_result['match_name']}' (Distance: {dna_result['distance']:.4f})")
            else:
                logging.info(f"    [Filter 3] FAILED. No DNA match found below threshold {DNA_MATCH_THRESHOLD}.")
        else:
            logging.info(f"  [Filter 2] FAILED. No positive slope found.")

    logging.info("\n--- [Analysis Summary] ---")
    logging.info(f"Total Valleys Found: {len(valleys)}")
    logging.info(f"Valleys Passing Filter 2 (Slope Test): {passed_filter2}")
    logging.info(f"Valleys Passing Filter 3 (DNA Test): {passed_filter3}")
    logging.info("--- [Historical Analyzer Finished] ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Historical Archetype Analyzer")
    parser.add_argument("--ticker", required=True, help="Ticker ID (e.g., 'GME')")
    parser.add_argument("--start", required=True, help="History start date (e.g., '2017-01-01')")
    parser.add_argument("--end", required=True, help="History end date (e.g., '2023-01-01')")
    parser.add_argument("--m", type=int, required=True, help="Window size for Matrix Profile")
    parser.add_argument("--logfile", required=True, help="Name for the log file")
    args = parser.parse_args()
    main(args)