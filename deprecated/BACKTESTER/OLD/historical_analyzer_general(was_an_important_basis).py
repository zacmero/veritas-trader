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

# --- FILTER THRESHOLDS ---
MIN_PERCENTAGE_GROWTH = 10.0
DNA_STRICT_THRESHOLD = 2.75
DNA_LOOSE_THRESHOLD = 4.75
DNA_QUALIFICATION_WINDOW = 30

# --- SETUP: LOGGING ---
def setup_logging(log_filename):
    os.makedirs(LOG_PATH, exist_ok=True)
    log_file = os.path.join(LOG_PATH, log_filename)
    for handler in logging.root.handlers[:]: logging.root.removeHandler(handler)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)-7s] %(message)s", handlers=[logging.FileHandler(log_file, mode='w'), logging.StreamHandler()])
    logging.getLogger("yfinance").setLevel(logging.ERROR)
    logging.getLogger("stumpy").setLevel(logging.ERROR)

# --- HELPER FUNCTIONS (No Changes) ---
def load_archetypes(library_path):
    archetypes_db = {}
    if not os.path.exists(library_path):
        logging.warning("Archetype library not found.")
        return archetypes_db
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

# --- FILTER FUNCTIONS (No Changes) ---
def run_filter_2_qualification(full_ts, trigger_index):
    if trigger_index + DNA_QUALIFICATION_WINDOW > len(full_ts): return None
    ramp_pattern_30_day = full_ts[trigger_index : trigger_index + DNA_QUALIFICATION_WINDOW]
    if np.isnan(ramp_pattern_30_day).any(): return None
    growth_percent = calculate_percentage_growth(ramp_pattern_30_day)
    logging.info(f"  [Filter 2] 30-Day Growth Check: {growth_percent:.2f}%")
    if growth_percent >= MIN_PERCENTAGE_GROWTH:
        logging.info(f"  [Filter 2] PASSED. Growth of {growth_percent:.2f}% >= {MIN_PERCENTAGE_GROWTH}% threshold.")
        return {'ramp_pattern_30_day': ramp_pattern_30_day, 'growth_percent': growth_percent}
    else:
        logging.info(f"  [Filter 2] FAILED. Growth of {growth_percent:.2f}% < {MIN_PERCENTAGE_GROWTH}% threshold.")
        return None

def run_filter_3_dna_test(ramp_pattern_30_day, archetypes_db):
    if not archetypes_db: return None
    try:
        ramp_pattern_1d = ramp_pattern_30_day.astype(np.float64).flatten()
        if np.std(ramp_pattern_1d) < 1e-6:
            logging.warning("    [Filter 3] Skipping DNA test: Ramp pattern is a flat line.")
            return None
    except Exception as e:
        logging.error(f"    [Filter 3] CRITICAL ERROR during data preparation.", exc_info=True)
        return None
    best_match_name, best_match_distance = None, np.inf
    for name, archetype in archetypes_db.items():
        try:
            archetype_1d = archetype.astype(np.float64).flatten()
            if len(ramp_pattern_1d) > len(archetype_1d): continue
            distance_profile = stumpy.mass(archetype_1d, ramp_pattern_1d)
            min_distance = np.min(distance_profile)
            logging.info(f"    [Filter 3] DNA Test vs '{name}': Distance = {min_distance:.4f}")
            if min_distance < best_match_distance:
                best_match_distance, best_match_name = min_distance, name
        except Exception as e:
            logging.error(f"    [Filter 3] Error comparing with archetype {name}.", exc_info=True)
            continue
    return {'distance': best_match_distance, 'match_name': best_match_name}

# --- MAIN ANALYSIS ---
def main(args):
    setup_logging(args.logfile)
    logging.info(f"--- [Historical Analyzer Started for {args.ticker}] ---")
    ts_full_series = yf.download(args.ticker, start=args.start, end=args.end, progress=False)['Close']
    ts = ts_full_series.values.flatten()
    dates = ts_full_series.index
    logging.info(f"Loaded {len(ts)} data points for {args.ticker}.")
    archetypes_db = load_archetypes(LIBRARY_PATH)

    logging.info(f"Computing full CAC curve with m={args.m}...")
    mp_output = stumpy.stump(ts, m=args.m)
    I = mp_output[:, 1].astype(np.int64)
    cac, _ = stumpy.fluss(I, L=args.m, n_regimes=10)
    valleys, _ = find_peaks(-cac, distance=args.m)
    logging.info(f"Found {len(valleys)} candidate valleys in the CAC curve.")

    passed_filter2 = 0
    final_alerts = [] # Store alerts for the final report

    for valley_idx in valleys:
        valley_date = dates[valley_idx]
        logging.info(f"\n--- Analyzing Valley at {valley_date.strftime('%Y-%m-%d')} ---")
        qualification_result = run_filter_2_qualification(ts, valley_idx)
        if qualification_result:
            passed_filter2 += 1
            dna_result = run_filter_3_dna_test(qualification_result['ramp_pattern_30_day'], archetypes_db)
            if dna_result and dna_result['distance'] < np.inf:
                distance = dna_result['distance']
                match_type = "None"
                
                if distance <= DNA_STRICT_THRESHOLD:
                    match_type = "Strict"
                    logging.info(f"    [Filter 3] PASSED. Best Match: '{dna_result['match_name']}' (Strict Match) (Distance: {distance:.4f})")
                elif distance <= DNA_LOOSE_THRESHOLD:
                    match_type = "Loose"
                    logging.info(f"    [Filter 3] PASSED. Best Match: '{dna_result['match_name']}' (Loose Match) (Distance: {distance:.4f})")
                else:
                    logging.info(f"    [Filter 3] FAILED. Best Match '{dna_result['match_name']}' (Distance: {distance:.4f}) > Loose Threshold.")

                # If a match was found (Strict or Loose), store it for the final report
                if match_type in ["Strict", "Loose"]:
                    final_alerts.append({
                        'date': valley_date.strftime('%Y-%m-%d'),
                        'm_value': args.m,
                        'growth_pct': qualification_result['growth_percent'],
                        'best_match': dna_result['match_name'],
                        'distance': distance,
                        'match_type': match_type
                    })
            else:
                logging.warning(f"    [Filter 3] DNA test could not be performed.")
    
    # --- THE NEW, DETAILED FINAL REPORT ---
    logging.info("\n\n" + "="*60)
    logging.info("--- [FINAL ANALYSIS REPORT] ---")
    logging.info("="*60)
    
    num_strict = sum(1 for alert in final_alerts if alert['match_type'] == 'Strict')
    num_loose = sum(1 for alert in final_alerts if alert['match_type'] == 'Loose')

    logging.info(f"Total Valleys Found: {len(valleys)}")
    logging.info(f"Valleys Passing Filter 2 (Growth > {MIN_PERCENTAGE_GROWTH}%): {passed_filter2}")
    logging.info(f"Total Alerts Generated (Passing Filter 3): {len(final_alerts)}")
    logging.info(f"  - Strict Matches: {num_strict}")
    logging.info(f"  - Loose Matches: {num_loose}")
    
    if final_alerts:
        logging.info("\n--- [ALERT DETAILS FOR NEWS SYSTEM] ---")
        alerts_df = pd.DataFrame(final_alerts)
        logging.info("\n" + alerts_df.to_markdown(index=False))
    else:
        logging.info("\n--- No alerts passed the DNA match filter. ---")
        
    logging.info("="*60)
    logging.info("--- [Historical Analyzer Finished] ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Historical Archetype Analyzer")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--m", type=int, required=True)
    parser.add_argument("--logfile", required=True)
    args = parser.parse_args()
    main(args)