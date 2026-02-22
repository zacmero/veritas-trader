import yfinance as yf
import stumpy
import pandas as pd
import numpy as np
from scipy.signal import find_peaks
import os
import logging
import matplotlib.pyplot as plt

# --- CONFIGURATION ---
# We are hard-coding the exact parameters of the failed PTON test.
TICKER = "PTON"
M_WINDOW_SIZE = 15
SIMULATED_DATE = "2020-09-18" # The Friday *after* the known 2020-09-15 ramp
CAC_LOOKBACK_DAYS = 15
CAC_TRIGGER_PERCENTILE = 90.0
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "LOGS")
CHART_FILENAME = os.path.join(LOG_PATH, f"debug_plot_{TICKER}_m{M_WINDOW_SIZE}_on_{SIMULATED_DATE}.png")

# --- SETUP LOGGING ---
def setup_logging():
    os.makedirs(LOG_PATH, exist_ok=True)
    log_file = os.path.join(LOG_PATH, "debug_trigger.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-7s] %(message)s",
        handlers=[logging.FileHandler(log_file, mode='w'), logging.StreamHandler()]
    )
    logging.getLogger("yfinance").setLevel(logging.ERROR)
    logging.getLogger("stumpy").setLevel(logging.ERROR)

# --- THE DEBUG FUNCTION ---
def debug_filter_1_trigger(ts_up_to_today, m, ticker, sim_date_str):
    """
    Runs the Filter 1 logic for a single day and saves a detailed debug plot.
    """
    logging.info(f"--- Running White Box Diagnostic for {ticker} (m={m}) on {sim_date_str} ---")
    
    if len(ts_up_to_today) < m * 10:
        logging.error(f"Not enough history. Need {m*10}, Got {len(ts_up_to_today)}")
        return

    try:
        # 1. Calculate Full CAC (as the script does)
        mp_output = stumpy.stump(ts_up_to_today.flatten(), m=m)
        I = mp_output[:, 1].astype(np.int64)
        cac, _ = stumpy.fluss(I, L=m, n_regimes=2)
        
        # Invert for peak finding (deeper valleys = higher peaks)
        negative_cac = -cac

        # 2. Calculate Historical Threshold
        historical_cac_for_threshold = negative_cac[:-CAC_LOOKBACK_DAYS]
        if len(historical_cac_for_threshold) < 100:
            logging.error("Not enough historical CAC data for a stable threshold.")
            return

        trigger_threshold = np.percentile(historical_cac_for_threshold, CAC_TRIGGER_PERCENTILE)

        # 3. Analyze Recent Window (The Failing Part)
        recent_cac_negative = negative_cac[-CAC_LOOKBACK_DAYS:]
        recent_peaks_idx, _ = find_peaks(recent_cac_negative)

        logging.info(f"Historical Threshold ({CAC_TRIGGER_PERCENTILE}%ile) calculated: {trigger_threshold:.4f}")
        logging.info(f"Recent CAC (last {CAC_LOOKBACK_DAYS} days) values: {np.round(recent_cac_negative, 4)}")
        logging.info(f"Peaks found in recent window (local indices): {recent_peaks_idx}")

        trigger_found = False
        if recent_peaks_idx.any():
            deepest_recent_valley_local_idx = recent_peaks_idx[np.argmax(recent_cac_negative[recent_peaks_idx])]
            valley_depth = recent_cac_negative[deepest_recent_valley_local_idx]
            
            logging.info(f"Deepest *new* valley found at local index {deepest_recent_valley_local_idx} with depth: {valley_depth:.4f}")
            
            if valley_depth > trigger_threshold:
                logging.critical("*** TRIGGER WOULD HAVE FIRED ***")
                trigger_found = True
            else:
                logging.warning(f"Trigger FAILED: New valley depth ({valley_depth:.4f}) is NOT > threshold ({trigger_threshold:.4f})")
        else:
            logging.warning("Trigger FAILED: No peaks found in the recent window.")

        # 4. Generate the Diagnostic Plot
        plt.figure(figsize=(15, 8))
        plt.title(f"Debug Probe for {ticker} (m={m}) on {sim_date_str}")
        
        # Plot full historical CAC (this is what historical_analyzer saw)
        plt.plot(negative_cac, label="Historical Negative CAC (Full)", color='gray', alpha=0.7)
        
        # Plot the threshold line
        plt.axhline(y=trigger_threshold, color='red', linestyle='--', label=f"Trigger Threshold ({trigger_threshold:.4f})")
        
        # Highlight the "recent" window the script is checking
        recent_indices = np.arange(len(negative_cac) - CAC_LOOKBACK_DAYS, len(negative_cac))
        plt.plot(recent_indices, recent_cac_negative, label="Recent Negative CAC (Being Checked)", color='blue', linewidth=2.5)

        # Mark the peaks found *in the recent window*
        if recent_peaks_idx.any():
            global_peak_indices = recent_indices[recent_peaks_idx]
            plt.plot(global_peak_indices, negative_cac[global_peak_indices], "x", color='orange', markersize=10, label="Recent Peaks Found")

        plt.legend()
        plt.ylabel("Negative CAC Value (Valley Depth)")
        plt.xlabel("CAC Index (Days)")
        plt.savefig(CHART_FILENAME)
        plt.close()
        
        logging.info(f"Diagnostic plot saved to: {CHART_FILENAME}")

    except Exception as e:
        logging.error(f"CRITICAL FAILURE in debug function: {e}", exc_info=True)

# --- MAIN EXECUTION ---
def main():
    setup_logging()
    
    # 1. Fetch data up to the simulated date
    try:
        data = yf.download(TICKER, start="2019-01-01", end=SIMULATED_DATE, interval="1d", progress=False)
        if data.empty:
            logging.error("No data fetched.")
            return
        ts = data['Close'].values
    except Exception as e:
        logging.error(f"Failed to fetch data: {e}")
        return

    # 2. Run the single diagnostic
    debug_filter_1_trigger(ts, M_WINDOW_SIZE, TICKER, SIMULATED_DATE)

if __name__ == "__main__":
    main()
