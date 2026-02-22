import yfinance as yf
import pandas as pd
import numpy as np
import stumpy
from scipy.signal import find_peaks

def z_normalize(series):
    return (series - np.mean(series)) / np.std(series)

# --- Task 1 (New Filter 1): Find All Candidate Regimes ---
print("--- Filter 1: Finding All Candidate Regimes ---")
gme_df = yf.download('GME', start='2017-01-01', end='2023-01-01')
gme_close = gme_df['Close'].dropna()

m = 30
mp_output = stumpy.stump(gme_close.values.flatten(), m)
I = mp_output[:, 1]
cac, _ = stumpy.fluss(I, m, n_regimes=5) # Find 5 regimes

# Find top 5 valleys in the CAC
peaks, properties = find_peaks(-cac, prominence=0.01)
peak_prominences = properties['prominences']
# Sort peaks by prominence and take top 5
top_peak_indices = peaks[np.argsort(peak_prominences)[-5:]]
top_peak_indices = sorted(top_peak_indices)

candidate_dates = [gme_df.index[i] for i in top_peak_indices]

print("Top 5 Candidate Regime Change Dates:")
for i, date in enumerate(candidate_dates):
    print(f"Candidate {i+1}: {date.strftime('%Y-%m-%d')}")

# --- Task 2 (New Filter 2): Characterize & Qualify Regimes ---
print("\n--- Filter 2: Characterizing & Qualifying Regimes ---")
slopes = []
for date in candidate_dates:
    start_idx = gme_df.index.get_loc(date)
    subsequence = gme_close.iloc[start_idx : start_idx + m]
    # Calculate slope with linear regression
    x = np.arange(len(subsequence))
    coeffs = np.polyfit(x, subsequence.values, 1)
    slopes.append(float(coeffs[0]))

print("Candidate Dates and Slopes:")
for i, (date, slope) in enumerate(zip(candidate_dates, slopes)):
    print(f"Candidate {i+1}: {date.strftime('%Y-%m-%d')}, 30-Day Slope: {slope:.4f}")

# Identify the best candidate
best_candidate_idx = np.argmax(slopes)
bubble_candidate_date = candidate_dates[best_candidate_idx]
bubble_candidate_slope = slopes[best_candidate_idx]

print(f"\nBubble Candidate Identified:")
print(f"Start Date: {bubble_candidate_date.strftime('%Y-%m-%d')}")
print(f"30-Day Slope: {bubble_candidate_slope:.4f}")

# --- Task 3 (New Filter 3): Re-Run the "Bubble DNA Test" ---
print("\n--- Filter 3: Re-Running the Bubble DNA Test ---")

# 1. Prepare Query
query_start_idx = gme_df.index.get_loc(bubble_candidate_date)
query_raw = gme_close.iloc[query_start_idx : query_start_idx + m]
query_normalized = z_normalize(query_raw.values)

# 2. Load DNA Library
# GME Bubble
gme_squeeze_df = yf.download('GME', start='2020-09-01', end='2021-03-01', progress=False)
peak_iloc_gme = np.argmax(gme_squeeze_df['Close'].values)
lib1_gme_raw = gme_squeeze_df['Close'].iloc[peak_iloc_gme - 90 + 1 : peak_iloc_gme + 1]
lib1_gme_normalized = z_normalize(lib1_gme_raw.values)

# BTC Bubble
btc_bubble_df = yf.download('BTC-USD', start='2017-01-01', end='2018-03-01', progress=False)
peak_iloc_btc = np.argmax(btc_bubble_df['Close'].values)
lib2_btc_raw = btc_bubble_df['Close'].iloc[peak_iloc_btc - 90 + 1 : peak_iloc_btc + 1]
lib2_btc_normalized = z_normalize(lib2_btc_raw.values)

# AAPL Control
aapl_growth_df = yf.download('AAPL', start='2019-01-01', end='2019-12-31', progress=False)
lib3_aapl_raw = aapl_growth_df['Close'].loc['2019-10-01':'2019-12-31']
lib3_aapl_normalized = z_normalize(lib3_aapl_raw.values)

# 3. Execute MASS
dist_gme = np.min(stumpy.mass(query_normalized, lib1_gme_normalized))
dist_btc = np.min(stumpy.mass(query_normalized, lib2_btc_normalized))
dist_aapl = np.min(stumpy.mass(query_normalized, lib3_aapl_normalized))

# 4. Final Report
print("\nFinal Report: DNA Test Results for the Bubble Candidate")
print(f"GME Query vs. GME 2021 Squeeze Distance: {dist_gme:.4f}")
print(f"GME Query vs. BTC 2017 Bubble Distance:  {dist_btc:.4f}")
print(f"GME Query vs. AAPL 2019 Control Distance: {dist_aapl:.4f}")