import yfinance as yf
import stumpy
import pandas as pd
import numpy as np
from scipy.signal import find_peaks
import matplotlib.pyplot as plt
import os
import logging
import argparse

# --- CONFIGURATION ---
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
SELL_LIBRARY_PATH = os.path.join(BASE_PATH, "..", "SELL_ARCHETYPE_LIBRARY_FINAL")
LOG_PATH = os.path.join(BASE_PATH, "LOGS")
DNA_WINDOW = 30

# --- SETUP: LOGGING ---
def setup_logging(log_filename):
    os.makedirs(LOG_PATH, exist_ok=True)
    log_file = os.path.join(LOG_PATH, log_filename)
    for handler in logging.root.handlers[:]: logging.root.removeHandler(handler)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)-7s] %(message)s", handlers=[logging.FileHandler(log_file, mode='w'), logging.StreamHandler()])
    logging.getLogger("yfinance").setLevel(logging.ERROR)
    logging.getLogger("stumpy").setLevel(logging.ERROR)

# --- THE CORRECT, ROBUST Z-NORMALIZE FUNCTION (From Refinery) ---
def z_normalize(series):
    std_dev = np.std(series)
    if std_dev < 1e-6:
        return np.zeros_like(series)
    return (series - np.mean(series)) / std_dev

# --- GENERATION PROTOCOL ---
def generate_ramp_down_archetype(ticker_id, history_start, history_end, m_window_size):
    log_filename = f"sell_gen_{ticker_id}_m{m_window_size}.log"
    setup_logging(log_filename)
    
    logging.info(f"--- Generating SELL (Ramp Down) Archetype for: {ticker_id} ---")
    os.makedirs(SELL_LIBRARY_PATH, exist_ok=True)

    # 1. Fetch Data
    data = yf.download(ticker_id, start=history_start, end=history_end, progress=False, auto_adjust=True)
    if data.empty:
        logging.error("No data downloaded.")
        return

    ts = data['Close'].values
    dates = data.index

    # 2. Find the Bubble Context (The Valley)
    logging.info("Finding regime change to locate bubble context...")
    mp_output = stumpy.stump(ts.flatten(), m=m_window_size)
    I = mp_output[:, 1].astype(np.int64)
    cac, _ = stumpy.fluss(I, L=m_window_size, n_regimes=10)
    candidate_indices, _ = find_peaks(-cac, distance=m_window_size)

    if len(candidate_indices) == 0:
        logging.error("No regime changes found.")
        return

    # 3. Find the PEAK that follows the regime change
    best_peak_price = -1
    best_peak_idx = -1
    
    # We look at the window AFTER the trigger to find the highest high
    for idx in candidate_indices:
        # Search window: from trigger up to 180 days later (approx 6 months)
        search_end = min(len(ts), idx + 180)
        if idx >= search_end: continue
        
        window = ts[idx : search_end]
        peak_idx_relative = np.argmax(window)
        peak_price = window[peak_idx_relative]
        
        if peak_price > best_peak_price:
            best_peak_price = peak_price
            best_peak_idx = idx + peak_idx_relative

    if best_peak_idx == -1:
        logging.error("Could not identify a valid peak.")
        return

    # 4. Extract the "Ramp Down" (Peak + 30 days)
    start_idx = best_peak_idx
    end_idx = start_idx + DNA_WINDOW
    
    if end_idx > len(ts):
        logging.error("Not enough data after the peak to create archetype.")
        return

    raw_pattern = ts[start_idx:end_idx]
    peak_date = dates[best_peak_idx].strftime('%Y-%m-%d')

    # 5. Normalize (Refinery Logic)
    normalized_pattern = z_normalize(raw_pattern)
    
    # 6. Save
    name = f"sell_{ticker_id}_m{m_window_size}_down"
    
    # Save .npy
    data_filename = f"{name}.npy"
    np.save(os.path.join(SELL_LIBRARY_PATH, data_filename), normalized_pattern)
    
    # Save .png (Visual Confirmation)
    plt.figure(figsize=(10, 6))
    plt.plot(raw_pattern, color='red')
    plt.title(f"SELL Archetype (Ramp Down): {ticker_id}\nPeak Date: {peak_date}")
    plt.ylabel("Price")
    plt.xlabel("Days (0 = Peak)")
    img_filename = f"{name}.png"
    plt.savefig(os.path.join(SELL_LIBRARY_PATH, img_filename))
    plt.close()

    logging.info(f"--- SUCCESS: New SELL Archetype Created ---")
    logging.info(f"  Peak Date: {peak_date}")
    logging.info(f"  Saved to: {SELL_LIBRARY_PATH}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SELL Archetype Generation Script v3")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--m", type=int, required=True)
    args = parser.parse_args()

    generate_ramp_down_archetype(
        ticker_id=args.ticker,
        history_start=args.start,
        history_end=args.end,
        m_window_size=args.m
    )