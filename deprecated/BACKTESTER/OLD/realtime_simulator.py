import yfinance as yf
import stumpy
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
import os
import logging
from datetime import datetime, timedelta

# --- CONFIGURATION ---

# 1. FOCUSED TEST PARAMETERS
TICKER = "PTON"
M_WINDOW_SIZE = 15 # The 'm' that worked for PTON
SIMULATION_START_DATE = "2019-09-26" # PTON IPO Date
SIMULATION_END_DATE = "2021-01-01"   # Cover the 2020 bubble

# 2. Project Folders
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
LIBRARY_PATH = os.path.join(BASE_PATH, "..", "ARCHETYPE_LIBRARY")
LOG_PATH = os.path.join(BASE_PATH, "LOGS")

# 3. Filter Parameters
# How many days to use for the initial "baseline" MP calculation
INITIALIZATION_DAYS = 150 # (m * 10)
# Trigger if "newness" score is in the top 5% of historical newness
DISCORD_TRIGGER_PERCENTILE = 95.0 
DNA_QUALIFICATION_WINDOW = 30
SLOPE_QUALIFICATION_WINDOWS = [30, 60, 90]
MIN_POSITIVE_SLOPE_THRESHOLD = 0.001
DNA_STRICT_THRESHOLD = 2.75
DNA_LOOSE_THRESHOLD = 4.75
ALERT_COOLDOWN_DAYS = 90

# --- SETUP: LOGGING ---
def setup_logging():
    os.makedirs(LOG_PATH, exist_ok=True)
    log_file = os.path.join(LOG_PATH, f"realtime_sim_PTON_m{M_WINDOW_SIZE}.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-7s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, mode='w'), # Overwrite
            logging.StreamHandler()
        ]
    )
    logging.getLogger("yfinance").setLevel(logging.ERROR)
    logging.getLogger("stumpy").setLevel(logging.ERROR)

# --- SETUP: LOAD ARCHETYPES ---
def load_archetypes(library_path):
    archetypes_db = {}
    if not os.path.exists(library_path):
        logging.warning(f"Archetype library not found: {library_path}.")
        return archetypes_db
    for file in os.listdir(library_path):
        if file.endswith(".npy"):
            name = os.path.splitext(file)[0]
            path = os.path.join(library_path, file)
            archetypes_db[name] = np.load(path)
    logging.info(f"Loaded {len(archetypes_db)} archetypes from library.")
    return archetypes_db

# --- FILTER 2 (SLOPE) & 3 (DNA) ---
# These functions are PROVEN. We reuse them directly.
def run_filter_2_slope(full_ts, trigger_index, ticker):
    if trigger_index + DNA_QUALIFICATION_WINDOW >= len(full_ts):
        logging.info(f"[{ticker}] F2 FAILED: Trigger too close to end of data.")
        return None
    ramp_pattern_30_day = full_ts[trigger_index : trigger_index + DNA_QUALIFICATION_WINDOW]
    if np.isnan(ramp_pattern_30_day).any(): return None

    has_positive_slope, best_slope = False, -np.inf
    for window in SLOPE_QUALIFICATION_WINDOWS:
        if trigger_index + window >= len(full_ts): continue
        pattern = full_ts[trigger_index : trigger_index + window]
        if np.isnan(pattern).any(): continue
        X = np.arange(window).reshape(-1, 1); y = pattern
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
        logging.info(f"[{ticker}] F3 DNA Test vs '{name}': Distance = {min_distance:.4f}")
        if min_distance < best_match_distance:
            best_match_distance, best_match_name = min_distance, name
    return {'distance': best_match_distance, 'match_name': best_match_name}

# --- REAL-TIME SIMULATION MAIN ---
def main():
    setup_logging()
    logging.info(f"--- [Real-Time Simulator Started] ---")
    logging.info(f"TICKER: {TICKER}, M_WINDOW: {M_WINDOW_SIZE}, START: {SIMULATION_START_DATE}")

    archetypes_db = load_archetypes(LIBRARY_PATH)
    if not archetypes_db:
        logging.critical("No archetypes loaded. Exiting.")
        return

    # 1. Fetch ALL data for the simulation period
    try:
        data_series = yf.download(TICKER, start=SIMULATION_START_DATE, end=SIMULATION_END_DATE, interval="1d", progress=False)['Close']
        if data_series.empty or len(data_series) < INITIALIZATION_DAYS:
            logging.critical(f"Not enough data for PTON. Need > {INITIALIZATION_DAYS} days.")
            return
        full_ts = data_series.values.astype(np.float64).flatten() # Ensure 1D array
        full_dates = data_series.index
    except Exception as e:
        logging.critical(f"Failed to fetch data: {e}")
        return

    # 2. Initialize the Incremental Matrix Profile (stumpy.stumpi)
    try:
        logging.info(f"Initializing STUMPI with first {INITIALIZATION_DAYS} days...")
        ts_init = full_ts[:INITIALIZATION_DAYS]
        
        # This is the "online" object that will process new data points
        stumpi_obj = stumpy.stumpi(T=ts_init, m=M_WINDOW_SIZE)
        
        logging.info("STUMPI initialization and priming complete.")
    except Exception as e:
        logging.critical(f"STUMPI initialization failed: {e}. Exiting.")
        return
        
    alert_cooldown_date = pd.Timestamp(0)
    total_alerts_fired = 0

    # 3. Start the day-by-day simulation loop
    # We start *after* the initialization period
    for i in range(INITIALIZATION_DAYS, len(full_ts)):
        current_sim_date = full_dates[i]
        today_str = current_sim_date.strftime('%Y-%m-%d')
        new_data_point = full_ts[i]
        
        # Check for cooldown
        if current_sim_date < alert_cooldown_date:
            if current_sim_date.weekday() == 0: # Log once a week
                 logging.info(f"--- Simulating Day (In Cooldown): {today_str} ---")
            continue

        logging.info(f"--- Simulating Day: {today_str} ---")

        try:
            # --- FILTER 1: REAL-TIME ANOMALY DETECTION ---
            # This is the core of the new logic. We update the MP with ONE new point.
            stumpi_obj.update(new_data_point)
            
            # The "anomaly score" is the Matrix Profile value for the *newest* window
            current_anomaly_score = stumpi_obj.P_[-1]
            
            # The historical threshold is the 95th percentile of *all anomaly scores seen so far*
            historical_mp = stumpi_obj.P_[:-1] # Exclude the current point
            trigger_threshold = np.percentile(historical_mp, DISCORD_TRIGGER_PERCENTILE)

            logging.info(f"[{TICKER} m={M_WINDOW_SIZE}] F1 Anomaly Check:")
            logging.info(f"  - Current Anomaly Score: {current_anomaly_score:.4f}")
            logging.info(f"  - Hist. Threshold ({DISCORD_TRIGGER_PERCENTILE:.1f}%ile): {trigger_threshold:.4f}")

            # The Trigger: Is today's "newness" score higher than the historical threshold?
            if current_anomaly_score > trigger_threshold:
                logging.warning(f"[SIM F1] {TICKER}: TRIGGER! New anomaly score > threshold.")
                trigger_index = i # Today is the trigger

                # --- FILTER 2: SLOPE TEST ---
                # We use the *full* data to "look ahead" and see if this ramp continues
                slope_result = run_filter_2_slope(full_ts, trigger_index, TICKER)
                
                if slope_result:
                    logging.warning(f"[SIM F2] {TICKER}: QUALIFIED. Positive slope found.")
                    
                    # --- FILTER 3: DNA TEST ---
                    dna_result = run_filter_3_dna_test(slope_result['ramp_pattern_30_day'], archetypes_db, TICKER)
                    
                    if dna_result:
                        distance, match_name = dna_result['distance'], dna_result['match_name']
                        alert_level, alert_type = None, None

                        if distance <= DNA_STRICT_THRESHOLD:
                            alert_level, alert_type = logging.CRITICAL, "High Confidence (Strict Match)"
                        elif distance <= DNA_LOOSE_THRESHOLD:
                            alert_level, alert_type = logging.WARNING, "Medium Confidence (Loose Match)"

                        if alert_level:
                            log_message = (f"\n{'!' * 62}\n!!!{'REALTIME SIMULATION ALERT TRIGGERED':^56}!!!\n{'!' * 62}\n"
                                         f"  Ticker       : {TICKER}\n"
                                         f"  ALERT DATE   : {today_str}\n"
                                         f"  Detector     : AnomalyDetector (m={M_WINDOW_SIZE})\n"
                                         f"  Anomaly Score: {current_anomaly_score:.4f} (Threshold: {trigger_threshold:.4f})\n"
                                         f"  Best Slope   : {slope_result['best_slope']:.4f}\n"
                                         f"  DNA Match    : {match_name}\n"
                                         f"  Distance     : {distance:.4f}\n{'!' * 62}\n")
                            logging.log(alert_level, log_message)
                            total_alerts_fired += 1
                            alert_cooldown_date = current_sim_date + timedelta(days=ALERT_COOLDOWN_DAYS)
                        else:
                            logging.info(f"[SIM F3] {TICKER}: Uncategorized. Best match '{match_name}' (Dist: {distance:.4f}) > Loose Threshold.")
                    else:
                        logging.info(f"[SIM F3] {TICKER}: Event ON {today_str} is uncategorized. No DNA match.")
                else:
                    logging.info(f"[SIM F2] {TICKER}: DISQUALIFIED ON {today_str}. No positive slope.")
            else:
                logging.info(f"  - Not Triggered (Score is <= threshold)")

        except Exception as e:
            logging.error(f"Error during simulation on {today_str}: {e}", exc_info=True)
            # Continue simulation
            pass

    logging.info(f"--- [Real-Time Simulation Finished] ---")
    logging.info(f"Total Alerts Fired: {total_alerts_fired}")

if __name__ == "__main__":
    main()
