
import yfinance as yf
import stumpy
import pandas as pd
import numpy as np
from scipy.signal import find_peaks
from sklearn.linear_model import LinearRegression
import matplotlib.pyplot as plt
import os

def generate_archetype_from_history_v1_2(ticker_id, history_start, history_end, m_window_size, qualification_window, library_path):
    """
    Analyzes a historical asset to identify and save a bubble archetype using v1.2 protocol.
    """
    print(f"\n--- Processing Archetype v1.2 for: {ticker_id} (m={m_window_size}) ---")

    # --- 0.0: SETUP ---
    os.makedirs(library_path, exist_ok=True)

    # --- [FILTER 1]: REGIME CHANGE CANDIDATE DETECTION ---
    data = yf.download(ticker_id, start=history_start, end=history_end, progress=False)
    if data.empty:
        print(f"Error: No data downloaded for {ticker_id}. Skipping.")
        return
        
    ts = data['Close'].values
    dates = data.index
    if len(ts) < m_window_size * 10:
        print(f"Error: Not enough data for {ticker_id}. Required: {m_window_size * 10}, Found: {len(ts)}")
        return

    mp_output = stumpy.stump(ts.flatten(), m=m_window_size)
    I = mp_output[:, 1]
    cac, _ = stumpy.fluss(I, L=m_window_size, n_regimes=2)

    # Find ALL significant valleys
    negative_cac = -cac
    # Use a small prominence threshold and the window size as the minimum distance
    candidate_indices, _ = find_peaks(negative_cac, prominence=0.01, distance=m_window_size)
    
    if len(candidate_indices) == 0:
        print(f"Error: No significant regime change candidates found for {ticker_id}.")
        return

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
        print(f"Error: No valid candidates found for {ticker_id} after qualification.")
        return

    # Filter for positive slopes first
    positive_slope_results = [res for res in results if res['slope'] > 0]

    if not positive_slope_results:
        print(f"Error: No positive slope candidates found for {ticker_id}.")
        return

    # Find the best candidate from the positive-only list
    bubble_candidate = max(positive_slope_results, key=lambda x: x['slope'])

    # --- [FILTER 3]: ARCHETYPE EXTRACTION & SAVING ---
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

    print(f"--- SUCCESS: New Archetype Created ---")
    print(f"  Source: {ticker_id}")
    print(f"  Start Date: {archetype_date}")
    print(f"  Chart saved to: {os.path.join(library_path, img_filename)}")
    print(f"  Data saved to: {os.path.join(library_path, data_filename)}")


if __name__ == "__main__":
    main_library_path = "ARCHETYPE_LIBRARY"
    
    # Default qualification window
    QUALIFICATION_WINDOW = 30

    # --- Re-Generate Archetypes with v1.2 Protocol ---
    
    # 1. 'New Asset Class' (BTC)
    generate_archetype_from_history_v1_2("BTC-USD", "2015-01-01", "2019-01-01", 90, QUALIFICATION_WINDOW, main_library_path)

    # 2. 'Classic Short Squeeze' (VW)
    generate_archetype_from_history_v1_2("VWAGY", "2006-01-01", "2010-01-01", 15, QUALIFICATION_WINDOW, main_library_path)

    # 3. 'Commodity Super-Spike' (USO)
    generate_archetype_from_history_v1_2("USO", "2006-04-10", "2010-01-01", 90, QUALIFICATION_WINDOW, main_library_path)

    print("\n--- Archetype Re-Generation Complete ---")
