
import yfinance as yf
import stumpy
import pandas as pd
import numpy as np
from scipy.signal import find_peaks
from sklearn.linear_model import LinearRegression
import matplotlib.pyplot as plt
import os
import warnings

# Suppress specific warnings from yfinance and stumpy
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning, module='stumpy')

def generate_archetype_from_history(ticker_id, history_start, history_end, m_window_size, qualification_window, num_candidates, library_path):
    """
    Analyzes a historical asset to identify, qualify, and save a bubble archetype pattern.
    """
    print(f"\n--- Processing Archetype for: {ticker_id} (m={m_window_size}) ---")

    # --- 0.0: SETUP: CREATE LIBRARY DIRECTORY ---
    os.makedirs(library_path, exist_ok=True)

    # --- [FILTER 1]: REGIME CHANGE CANDIDATE DETECTION ---
    # 1.1. Acquire Data
    try:
        data = yf.download(ticker_id, start=history_start, end=history_end, progress=False, auto_adjust=True)
        if data.empty:
            print(f"Error: No data found for {ticker_id} in the given date range.")
            return
        ts = data['Close'].values
        dates = data.index
        if len(ts) < m_window_size * 10:
            print(f"Error: Not enough data for {ticker_id}. Required: {m_window_size * 10}, Found: {len(ts)}")
            return
    except Exception as e:
        print(f"Error downloading data for {ticker_id}: {e}")
        return

    # 1.2. Compute Matrix Profile
    mp_output = stumpy.stump(ts, m=m_window_size)
    I = mp_output[:, 1]

    # 1.3. Compute Regime Change (CAC) Curve
    # Using stumpy.fluss to get the CAC for the best single split, as it's robust for finding valleys.
    cac, _ = stumpy.fluss(I, m=m_window_size, n_regimes=2)

    # 1.4. Find Candidate Valleys (Regime Changes)
    negative_cac = -cac
    peaks, _ = find_peaks(negative_cac, distance=m_window_size)
    if len(peaks) == 0:
        print(f"Error: No regime change candidates found for {ticker_id}.")
        return
    peak_heights = negative_cac[peaks]
    # Ensure we don't request more candidates than available
    k = min(num_candidates, len(peaks))
    top_peak_indices = np.argsort(peak_heights)[-k:]
    candidate_indices = sorted(peaks[top_peak_indices])

    # --- [FILTER 2]: REGIME QUALIFICATION (SLOPE TEST) ---
    results = []
    for idx in candidate_indices:
        if idx + qualification_window >= len(ts):
            continue
        ramp_subsequence = ts[idx : idx + qualification_window]
        X = np.arange(qualification_window).reshape(-1, 1)
        y = ramp_subsequence
        model = LinearRegression().fit(X, y)
        slope = model.coef_[0]
        results.append({'index': idx, 'date': dates[idx], 'slope': slope})

    if not results:
        print(f"Error: No valid candidates found for {ticker_id} after slope test.")
        return
    bubble_candidate = max(results, key=lambda x: x['slope'])
    if bubble_candidate['slope'] <= 0:
        print(f"Error: No positive slope candidates found for {ticker_id}.")
        return

    # --- [FILTER 3]: ARCHETYPE EXTRACTION & SAVING ---
    start_idx = bubble_candidate['index']
    end_idx = start_idx + qualification_window
    archetype_pattern = ts[start_idx:end_idx]
    archetype_date = bubble_candidate['date'].strftime('%Y-%m-%d')

    # 3.2. Generate & Save Visualization
    plt.figure(figsize=(10, 6))
    plt.plot(archetype_pattern)
    plt.title(f"Archetype: {ticker_id} (m={m_window_size})\nStart: {archetype_date} | Slope: {bubble_candidate['slope']:.4f}")
    plt.ylabel("Price")
    plt.xlabel(f"Days (from start date)")
    img_filename = f"{ticker_id}_m{m_window_size}_ramp.png"
    plt.savefig(os.path.join(library_path, img_filename))
    plt.close()

    # 3.3. Normalize & Save Data
    normalized_archetype = (archetype_pattern - np.mean(archetype_pattern)) / np.std(archetype_pattern)
    data_filename = f"{ticker_id}_m{m_window_size}_ramp.npy"
    np.save(os.path.join(library_path, data_filename), normalized_archetype)

    # 3.4. Report & Log
    print(f"--- SUCCESS: New Archetype Created ---")
    print(f"  Source: {ticker_id}")
    print(f"  Start Date: {archetype_date}")
    print(f"  Chart saved to: {os.path.join(library_path, img_filename)}")
    print(f"  Data saved to: {os.path.join(library_path, data_filename)}")


if __name__ == "__main__":
    archetype_params = [
        {
            "ticker_id": "GME", "history_start": "2017-01-01", "history_end": "2023-01-01",
            "m_window_size": 90, "qualification_window": 30, "num_candidates": 5, "library_path": "ARCHETYPE_LIBRARY"
        },
        {
            "ticker_id": "BTC-USD", "history_start": "2015-01-01", "history_end": "2019-01-01",
            "m_window_size": 90, "qualification_window": 30, "num_candidates": 5, "library_path": "ARCHETYPE_LIBRARY"
        },
        {
            "ticker_id": "CSCO", "history_start": "1995-01-01", "history_end": "2002-01-01",
            "m_window_size": 90, "qualification_window": 30, "num_candidates": 5, "library_path": "ARCHETYPE_LIBRARY"
        },
        {
            "ticker_id": "SHIB-USD", "history_start": "2020-08-01", "history_end": "2023-01-01",
            "m_window_size": 30, "qualification_window": 30, "num_candidates": 5, "library_path": "ARCHETYPE_LIBRARY"
        },
        {
            "ticker_id": "VWAGY", "history_start": "2006-01-01", "history_end": "2010-01-01",
            "m_window_size": 15, "qualification_window": 30, "num_candidates": 5, "library_path": "ARCHETYPE_LIBRARY"
        },
        {
            "ticker_id": "IYR", "history_start": "2002-01-01", "history_end": "2010-01-01",
            "m_window_size": 120, "qualification_window": 30, "num_candidates": 5, "library_path": "ARCHETYPE_LIBRARY"
        },
        {
            "ticker_id": "USO", "history_start": "2006-04-10", "history_end": "2010-01-01",
            "m_window_size": 90, "qualification_window": 30, "num_candidates": 5, "library_path": "ARCHETYPE_LIBRARY"
        }
    ]

    for params in archetype_params:
        generate_archetype_from_history(**params)

    print("\n--- Archetype Generation Complete ---")
