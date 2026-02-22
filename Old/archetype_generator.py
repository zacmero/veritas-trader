
import yfinance as yf
import stumpy
import pandas as pd
import numpy as np
from scipy.signal import find_peaks
from sklearn.linear_model import LinearRegression
import matplotlib.pyplot as plt
import os

def generate_archetype_from_history(ticker_id, history_start, history_end, m_window_size, qualification_window, num_candidates, library_path):
    """
    Analyzes a historical asset to identify and save a bubble archetype.
    """
    print(f"\n--- Processing Archetype for: {ticker_id} (m={m_window_size}) ---")

    # --- 0.0: SETUP: CREATE LIBRARY DIRECTORY ---
    os.makedirs(library_path, exist_ok=True)

    # --- [FILTER 1]: REGIME CHANGE CANDIDATE DETECTION ---
    # 1.1. Acquire Data
    data = yf.download(ticker_id, start=history_start, end=history_end, progress=False)
    ts = data['Close'].values
    dates = data.index
    if len(ts) < m_window_size * 10:
        print(f"Error: Not enough data for {ticker_id}. Required: {m_window_size * 10}, Found: {len(ts)}")
        return

    # 1.2. Compute Matrix Profile
    mp_output = stumpy.stump(ts.flatten(), m=m_window_size)
    I = mp_output[:, 1]

    # 1.3. Compute Regime Change (CAC) Curve
    cac, _ = stumpy.fluss(I, L=m_window_size, n_regimes=2)

    # 1.4. Find Candidate Valleys (Regime Changes)
    negative_cac = -cac
    peaks, _ = find_peaks(negative_cac, distance=m_window_size)
    peak_heights = negative_cac[peaks]
    # Ensure we don't request more candidates than available
    k = min(num_candidates, len(peak_heights))
    if k == 0:
        print(f"Error: No regime change candidates found for {ticker_id}.")
        return
        
    top_peak_indices = np.argsort(peak_heights)[-k:]
    candidate_indices = peaks[top_peak_indices]

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
    plt.title(f"Archetype: {ticker_id} (m={m_window_size})\nStart: {archetype_date} | Slope: {float(bubble_candidate['slope']):.4f}")
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
    # Create the main library folder
    main_library_path = "ARCHETYPE_LIBRARY"
    os.makedirs(main_library_path, exist_ok=True)

    # --- Generate Archetypes ---
    
    # 1. The 'Meme Squeeze'
    generate_archetype_from_history("GME", "2017-01-01", "2023-01-01", 90, 30, 5, main_library_path)

    # 2. The 'New Asset Class'
    generate_archetype_from_history("BTC-USD", "2015-01-01", "2019-01-01", 90, 30, 5, main_library_path)

    # 3. The 'Dot-Com'
    generate_archetype_from_history("CSCO", "1995-01-01", "2002-01-01", 90, 30, 5, main_library_path)

    # 4. The 'Meme Coin'
    generate_archetype_from_history("SHIB-USD", "2020-08-01", "2023-01-01", 30, 30, 5, main_library_path)

    # 5. The 'Classic Short Squeeze'
    generate_archetype_from_history("VWAGY", "2006-01-01", "2010-01-01", 15, 30, 5, main_library_path)

    # 6. The 'Real Estate Bubble'
    generate_archetype_from_history("IYR", "2002-01-01", "2010-01-01", 120, 30, 5, main_library_path)

    # 7. The 'Commodity Super-Spike'
    generate_archetype_from_history("USO", "2006-04-10", "2010-01-01", 90, 30, 5, main_library_path)

    print("\n--- Archetype Generation Complete ---")
