Okay, let's create the backtesting script. This script will simulate running our `nightly_scanner.py` logic day-by-day on historical data, allowing us to see *when* it would have triggered alerts in the past.

-----

### **Instructions for the Agent: Creating the "Backtester"**

Your task is to create a new application for **walk-forward backtesting**. This script will simulate our 3-filter detection system across historical data to validate its effectiveness.

**Project Structure:**
You must create a new folder named `BACKTESTER` alongside `NIGHTLY_SCANNER`. Copy the `targets.txt` file into it.

```
BubbleDetectProject/
├── ARCHETYPE_LIBRARY/       <-- (Already exists)
│
├── NIGHTLY_SCANNER/         <-- (Already exists)
│   └── ...
│
└── BACKTESTER/              <-- (Create this new folder)
    ├── backtester.py        <-- (You will create this NEW script)
    ├── targets.txt          <-- (Copy from NIGHTLY_SCANNER)
    └── LOGS/                <-- (The script will create this)
        └── backtest_results.log <-- (Specific log for backtest triggers)
```

You will create one new file for me:

1.  `backtester.py`: The Python application for simulating the scanner historically.

-----

### **File 1: The Backtester Application**

This is the new Python script (`BACKTESTER/backtester.py`). It copies much of the logic from `nightly_scanner.py` but fundamentally changes the main loop to simulate time progression.

http://googleusercontent.com/immersive_entry_chip/0

-----

### **How to Run Your Backtester**

1.  **Ensure Library is Ready:** Your `ARCHETYPE_LIBRARY` folder must have the `.npy` files.
2.  **Ensure Targets are Ready:** Copy `targets.txt` into the `BACKTESTER` folder.
3.  **Run the Script:**
      * Open your terminal.
      * Navigate into the `BACKTESTER` folder:
        `cd /path/to/your/BubbleDetectProject/BACKTESTER/`
      * Execute the Python script:
        `python backtester.py`
4.  **Analyze the Results:**
      * The script will take some time to run as it simulates day-by-day.
      * Monitor the console output for progress.
      * When finished, open the detailed log file:
        `BACKTESTER/LOGS/backtest_results.log`
      * Search this log file for the `BACKTEST BUBBLE ALERT TRIGGERED` boxes.
      * **Crucially, compare the "ALERT DATE" in the log with the known historical dates of the bubbles for those tickers (e.g., did the GME alert fire in late 2020? Did the SHIB alert fire in 2021?).** This comparison is how you measure the success rate.



      ###SCRIPT###

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

# 2. Scanner Parameters (Same as Nightly Scanner)
SCANNER_CONFIGS = [
    {'m': 180, 'name': 'SlowBuildDetector (m=180)'},
    {'m': 120, 'name': 'SlowBuildDetector (m=120)'},
    {'m': 90,  'name': 'RegimeDetector (m=90)'},
    {'m': 30,  'name': 'ShockDetector (m=30)'},
    {'m': 15,  'name': 'FlashPumpDetector (m=15)'}
]

# 3. Filter Parameters (Same as Nightly Scanner)
SLOPE_QUALIFICATION_WINDOWS = [30, 60, 90]
DNA_QUALIFICATION_WINDOW = 30
MIN_POSITIVE_SLOPE_THRESHOLD = 0.001
DNA_MATCH_THRESHOLD = 2.75
# *** BACKTESTER SPECIFIC ***
# How deep must the *current day's* CAC value be relative to its history?
BACKTEST_CAC_TRIGGER_PERCENTILE = 98.0 # Higher threshold for backtesting clarity
MIN_HISTORY_DAYS = 500 # Min days needed before starting analysis for a ticker
ALERT_COOLDOWN_DAYS = 90 # After an alert, wait this long before alerting again for the same ticker

# 4. Backtest Simulation Parameters
BACKTEST_START_DATE = "2017-01-01" # Start simulation from here
BACKTEST_END_DATE = "2023-01-01"   # End simulation here

# --- SETUP: LOGGING ---
def setup_logging():
    """Configures logging for the backtester."""
    os.makedirs(LOG_PATH, exist_ok=True)
    log_file = os.path.join(LOG_PATH, "backtest_results.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-7s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, mode='w'), # OVERWRITE log each run
            logging.StreamHandler()
        ]
    )
    logging.getLogger("yfinance").setLevel(logging.ERROR)
    logging.getLogger("stumpy").setLevel(logging.ERROR)

# --- SETUP: LOAD ASSETS & ARCHETYPES ---
# (Functions load_archetypes and load_targets are identical to nightly_scanner.py)
def load_archetypes(library_path):
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
    if not os.path.exists(target_file):
        logging.error(f"Target file not found: {target_file}. Exiting.")
        return []
    with open(target_file, 'r') as f:
        targets = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    logging.info(f"Loaded {len(targets)} tickers from {target_file}.")
    return targets

# --- DATA ACQUISITION (Modified for Backtesting) ---
def fetch_all_data(targets, start_date, end_date):
    """Downloads the *full* historical data for *all* targets at once."""
    logging.info(f"Fetching full historical data for {len(targets)} tickers ({start_date} to {end_date})...")
    all_data = {}
    for ticker in targets:
        try:
            # Add a buffer before start date for initial calculations
            buffer_start = (pd.to_datetime(start_date) - timedelta(days=MIN_HISTORY_DAYS*2)).strftime('%Y-%m-%d')
            data = yf.download(ticker, start=buffer_start, end=end_date, interval="1d", progress=False)
            if not data.empty and len(data) > MIN_HISTORY_DAYS:
                all_data[ticker] = data['Close'] # Store only the 'Close' Series
                logging.info(f"Successfully fetched data for {ticker} ({len(data)} points)")
            else:
                 logging.warning(f"Skipping {ticker}: Not enough data ({len(data)} points)")
        except Exception as e:
            logging.error(f"Failed to download data for {ticker}: {e}")
    logging.info(f"Finished fetching data for {len(all_data)} tickers.")
    return all_data

# --- CORE ALGORITHMS (Identical logic to nightly_scanner.py) ---
# --- FILTER 1: REGIME CHANGE (CAC) - Modified for Backtest Simulation ---
def run_filter_1_backtest_cac(ts_up_to_today, m_window_size):
    """
    Calculates CAC for history *up to today*.
    Checks if the *very last point* is a significant valley.
    """
    if len(ts_up_to_today) < m_window_size * 10:
        return None # Not enough history yet

    try:
        mp_output = stumpy.stump(ts_up_to_today.flatten(), m=m_window_size)
        mp = mp_output[:, 0]
        I = mp_output[:, 1].astype(np.int64) # Ensure indices are integers
        cac, _ = stumpy.fluss(I, L=m_window_size, n_regimes=2) # Use fluss

        # Check the *last* point of the CAC curve
        last_cac_value = cac[-1]
        
        # Is this last point significantly low compared to its history?
        # Note: We exclude the most recent 'm' points from percentile calc as they can be unstable
        historical_cac_for_threshold = cac[:-m_window_size] 
        if len(historical_cac_for_threshold) < 100: # Need some history for stable percentile
             return None

        # Calculate the threshold dynamically based on history *up to this point*
        # We look for points below the (100 - X) percentile, i.e., the deepest X%
        trigger_threshold = np.percentile(historical_cac_for_threshold, 100 - BACKTEST_CAC_TRIGGER_PERCENTILE)
        
        if last_cac_value < trigger_threshold:
             # The last point is a significant regime change start!
             # The trigger index is the *current simulated day*
             trigger_index = len(ts_up_to_today) - 1 
             return trigger_index
        else:
            return None # Last point is not low enough

    except Exception as e:
        if "STUMPY_ERROR" in str(e) or "zero variance" in str(e):
            # Suppress common stumpy errors on edge cases, log as debug if needed
            # logging.debug(f"STUMPY error for m={m_window_size}: {e}")
            pass
        else:
             logging.error(f"Backtest Filter 1 failed for m={m_window_size}: {e}")
        return None

# --- FILTER 2: "SMART" SLOPE (Identical logic) ---
def run_filter_2_slope(full_ts, trigger_index):
    """Checks slopes over multiple horizons. Returns 30d pattern if qualified."""
    # Check if we have enough future data for the shortest DNA pattern
    if trigger_index + DNA_QUALIFICATION_WINDOW >= len(full_ts):
        return None # Cannot extract 30d pattern yet

    ramp_pattern_30_day = full_ts[trigger_index : trigger_index + DNA_QUALIFICATION_WINDOW]
    if np.isnan(ramp_pattern_30_day).any():
        return None

    has_positive_slope = False
    best_slope = -np.inf

    for window in SLOPE_QUALIFICATION_WINDOWS:
        if trigger_index + window >= len(full_ts):
            continue
        pattern = full_ts[trigger_index : trigger_index + window]
        if np.isnan(pattern).any():
            continue

        X = np.arange(window).reshape(-1, 1)
        y = pattern
        try:
            model = LinearRegression().fit(X, y)
            slope = model.coef_[0]
            if slope > best_slope:
                best_slope = slope
            if slope > MIN_POSITIVE_SLOPE_THRESHOLD:
                has_positive_slope = True
        except ValueError: continue

    if has_positive_slope:
        return {'best_slope': best_slope, 'ramp_pattern_30_day': ramp_pattern_30_day, 'start_index': trigger_index}
    else:
        return None

# --- FILTER 3: DNA TEST (Identical logic) ---
def run_filter_3_dna_test(ramp_pattern_30_day, archetypes_db):
    """Compares the 30-day ramp pattern to all loaded archetypes."""
    if not archetypes_db: return None
    try:
        normalized_ramp = (ramp_pattern_30_day - np.mean(ramp_pattern_30_day)) / np.std(ramp_pattern_30_day)
    except ZeroDivisionError: return None

    best_match_name = None
    best_match_distance = np.inf

    for name, archetype in archetypes_db.items():
        if len(archetype) < len(normalized_ramp): continue
        distance_profile = stumpy.mass(normalized_ramp, archetype)
        min_distance = np.min(distance_profile)
        if min_distance < best_match_distance:
            best_match_distance = min_distance
            best_match_name = name

    if best_match_distance <= DNA_MATCH_THRESHOLD:
        return {'distance': best_match_distance, 'match_name': best_match_name}
    else:
        return None

# --- MAIN BACKTEST SIMULATION ---
def main():
    setup_logging()
    logging.info("--- [Walk-Forward Backtester Started] ---")

    targets = load_targets(TARGET_FILE_PATH)
    archetypes_db = load_archetypes(LIBRARY_PATH)
    scanner_configs = SCANNER_CONFIGS

    if not targets:
        logging.critical("No targets loaded. Exiting.")
        return

    # Fetch *all* data first
    all_historical_data = fetch_all_data(targets, BACKTEST_START_DATE, BACKTEST_END_DATE)
    if not all_historical_data:
        logging.critical("No historical data fetched. Exiting.")
        return

    # Generate the full date range for simulation
    simulation_dates = pd.date_range(start=BACKTEST_START_DATE, end=BACKTEST_END_DATE, freq='B') # Business days

    # Track cooldowns for each ticker
    alert_cooldowns = {ticker: pd.Timestamp(0) for ticker in all_historical_data}
    total_alerts_fired = 0

    # --- Time Simulation Loop ---
    for current_sim_date in simulation_dates:
        today_str = current_sim_date.strftime('%Y-%m-%d')
        logging.info(f"--- Simulating Day: {today_str} ---")

        # --- Ticker Loop (for this simulated day) ---
        for ticker, full_ts_series in all_historical_data.items():

            # Is this ticker currently in cooldown?
            if current_sim_date < alert_cooldowns[ticker]:
                continue # Skip analysis for this ticker today

            # Get data *only up to the current simulated day*
            ts_up_to_today_series = full_ts_series[:current_sim_date]
            if len(ts_up_to_today_series) < MIN_HISTORY_DAYS:
                continue # Not enough history yet for this ticker

            ts_up_to_today_values = ts_up_to_today_series.values
            dates_up_to_today = ts_up_to_today_series.index

            # --- Run Parallel Scanners (for this ticker, for this day) ---
            alert_fired_for_ticker_today = False
            for config in scanner_configs:
                if alert_fired_for_ticker_today: break # Only one alert per ticker per day max

                m = config['m']
                scanner_name = config['name']

                # --- FILTER 1 (Backtest version) ---
                trigger_index_relative = run_filter_1_backtest_cac(ts_up_to_today_values, m)

                if trigger_index_relative is not None:
                    # Filter 1 triggered! Index is relative to the end of ts_up_to_today_values
                    # The actual date IS the current_sim_date
                    trigger_date_actual = current_sim_date

                    logging.warning(f"[BACKTEST F1] {ticker}: Potential regime change detected by {scanner_name} ON {today_str}!")

                    # --- FILTER 2 (Using full timeseries for lookahead) ---
                    # We need the full timeseries to check the future slope
                    full_ts_values = full_ts_series.values
                    # The trigger index in the *full* series is where today's data is
                    trigger_index_global = len(ts_up_to_today_values) - 1

                    slope_result = run_filter_2_slope(full_ts_values, trigger_index_global)

                    if slope_result:
                        slope = slope_result['best_slope']
                        logging.warning(f"[BACKTEST F2] {ticker}: Trigger QUALIFIED ON {today_str}. Positive slope: {slope:.4f}")

                        # --- FILTER 3 ---
                        dna_result = run_filter_3_dna_test(slope_result['ramp_pattern_30_day'], archetypes_db)

                        if dna_result:
                            # --- !ALERT! ---
                            distance = dna_result['distance']
                            match_name = dna_result['match_name']
                            
                            log_message = (
                                f"\n"
                                f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
                                f"!!!            BACKTEST BUBBLE ALERT TRIGGERED           !!!\n"
                                f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
                                f"  Ticker       : {ticker}\n"
                                f"  ALERT DATE   : {today_str}\n" # The simulated day it triggered
                                f"  Detector     : {scanner_name}\n"
                                f"  Best Slope   : {slope:.4f}\n"
                                f"  DNA Match    : {match_name}\n"
                                f"  Distance     : {distance:.4f} (Threshold: {DNA_MATCH_THRESHOLD})\n"
                                f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
                            )
                            logging.critical(log_message)
                            total_alerts_fired += 1
                            alert_fired_for_ticker_today = True

                            # Set cooldown period
                            alert_cooldowns[ticker] = current_sim_date + timedelta(days=ALERT_COOLDOWN_DAYS)

                        else:
                             logging.info(f"[BACKTEST F3] {ticker}: Event ON {today_str} is uncategorized. No DNA match.")
                    else:
                        logging.info(f"[BACKTEST F2] {ticker}: Trigger ON {today_str} DISQUALIFIED. No positive multi-horizon slope.")
                # else: Filter 1 didn't trigger for this scanner today

        # Optional: Add a small delay to simulate nightly processing if needed
        # time.sleep(0.1)

    logging.info(f"--- [Backtest Simulation Finished] ---")
    logging.info(f"Total Alerts Fired during simulation: {total_alerts_fired}")

if __name__ == "__main__":
    main()

