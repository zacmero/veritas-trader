import yfinance as yf
import stumpy
import pandas as pd
import numpy as np
from scipy.signal import find_peaks
from sklearn.linear_model import LinearRegression
import matplotlib.pyplot as plt
import os
import logging
import argparse

# --- CONFIGURATION ---
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
LIBRARY_PATH = os.path.join(BASE_PATH, "..", "ARCHETYPE_LIBRARY")
LOG_PATH = os.path.join(BASE_PATH, "LOGS")

# --- SETUP: LOGGING ---
def setup_logging(log_filename):
    os.makedirs(LOG_PATH, exist_ok=True)
    log_file = os.path.join(LOG_PATH, log_filename)
    
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
        
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-7s] %(message)s",
        handlers=[logging.FileHandler(log_file, mode='w'), logging.StreamHandler()]
    )
    logging.getLogger("yfinance").setLevel(logging.ERROR)
    logging.getLogger("stumpy").setLevel(logging.ERROR)

# --- v1.2 Generation Protocol ---
def generate_archetype(ticker_id, history_start, history_end, m_window_size, qualification_window, num_candidates, library_path):
    log_filename = f"archetype_gen_{ticker_id}_m{m_window_size}.log"
    setup_logging(log_filename)
    
    logging.info(f"--- Generating Archetype for: {ticker_id} (m={m_window_size}) ---")

    os.makedirs(library_path, exist_ok=True)

    data = yf.download(ticker_id, start=history_start, end=history_end, progress=False)
    if data.empty:
        logging.error(f"No data downloaded for {ticker_id}. Skipping.")
        return False
        
    ts = data['Close'].values
    dates = data.index
    if len(ts) < m_window_size * 10:
        logging.error(f"Not enough data. Required: {m_window_size * 10}, Found: {len(ts)}")
        return False

    mp_output = stumpy.stump(ts.flatten(), m=m_window_size)
    I = mp_output[:, 1].astype(np.int64)
    cac, _ = stumpy.fluss(I, L=m_window_size, n_regimes=num_candidates)

    candidate_indices, _ = find_peaks(-cac, prominence=0.01, distance=m_window_size)
    
    if len(candidate_indices) == 0:
        logging.error("No significant regime change candidates found.")
        return False

    results = []
    for idx in candidate_indices:
        if idx + qualification_window >= len(ts): continue
        ramp_subsequence = ts[idx : idx + qualification_window]
        X = np.arange(qualification_window).reshape(-1, 1)
        y = ramp_subsequence
        model = LinearRegression().fit(X, y)
        slope = model.coef_[0]
        results.append({'index': idx, 'date': dates[idx], 'slope': slope})

    if not results:
        logging.error("No valid candidates found after slope calculation.")
        return False

    positive_slope_results = [res for res in results if res['slope'] > 0]
    if not positive_slope_results:
        logging.error("No positive slope candidates found.")
        return False

    bubble_candidate = max(positive_slope_results, key=lambda x: x['slope'])

    start_idx = bubble_candidate['index']
    end_idx = start_idx + qualification_window
    archetype_pattern = ts[start_idx:end_idx]
    archetype_date = bubble_candidate['date'].strftime('%Y-%m-%d')

    plt.figure(figsize=(10, 6))
    plt.plot(archetype_pattern)
    plt.title(f"Archetype: {ticker_id} (m={m_window_size})\nStart: {archetype_date} | Slope: {float(bubble_candidate['slope']):.4f}")
    plt.ylabel("Price")
    plt.xlabel(f"Days (from start date)")
    img_filename = f"{ticker_id}_m{m_window_size}_ramp.png"
    plt.savefig(os.path.join(library_path, img_filename))
    plt.close()

    normalized_archetype = (archetype_pattern - np.mean(archetype_pattern)) / np.std(archetype_pattern)
    data_filename = f"{ticker_id}_m{m_window_size}_ramp.npy"
    np.save(os.path.join(library_path, data_filename), normalized_archetype)

    logging.info(f"--- SUCCESS: New Archetype Created ---")
    logging.info(f"  Source: {ticker_id}")
    logging.info(f"  Start Date: {archetype_date}")
    logging.info(f"  Chart saved to: {os.path.join(library_path, img_filename)}")
    logging.info(f"  Data saved to: {os.path.join(library_path, data_filename)}")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Archetype Generation Script")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--m", type=int, required=True)
    parser.add_argument("--qual", type=int, required=True)
    parser.add_argument("--numc", type=int, required=True)
    parser.add_argument("--path", required=True)
    
    args = parser.parse_args()

    generate_archetype(
        ticker_id=args.ticker,
        history_start=args.start,
        history_end=args.end,
        m_window_size=args.m,
        qualification_window=args.qual,
        num_candidates=args.numc,
        library_path=args.path
    )