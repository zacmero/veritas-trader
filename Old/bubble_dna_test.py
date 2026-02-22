import yfinance as yf
import pandas as pd
import numpy as np
import stumpy

def z_normalize(series):
    return (series - np.mean(series)) / np.std(series)

# --- Task 1: Isolate the "Suspect" Pattern (The Query) ---
gme_full_df = yf.download('GME', start='2017-01-01', end='2023-01-01')
query_start_date = '2021-04-06'
m = 30

query_start_index = gme_full_df.index.get_loc(query_start_date)
gme_query_raw = gme_full_df['Close'].iloc[query_start_index : query_start_index + m]
gme_query_normalized = z_normalize(gme_query_raw.values)

# --- Task 2: Build the "Bubble DNA Library" ---

# 2.1. DNA Library 1: GME 2021 Squeeze
gme_squeeze_df = yf.download('GME', start='2020-09-01', end='2021-03-01')
peak_iloc_gme = np.argmax(gme_squeeze_df['Close'].values)
lib1_start_index = peak_iloc_gme - 90 + 1
lib1_end_index = peak_iloc_gme + 1
lib1_gme_raw = gme_squeeze_df['Close'].iloc[lib1_start_index:lib1_end_index]
lib1_gme_normalized = z_normalize(lib1_gme_raw.values)
lib1_start_date = lib1_gme_raw.index[0]

# 2.2. DNA Library 2: BTC 2017 Bubble
btc_bubble_df = yf.download('BTC-USD', start='2017-01-01', end='2018-03-01')
peak_iloc_btc = np.argmax(btc_bubble_df['Close'].values)
lib2_start_index = peak_iloc_btc - 90 + 1
lib2_end_index = peak_iloc_btc + 1
lib2_btc_raw = btc_bubble_df['Close'].iloc[lib2_start_index:lib2_end_index]
lib2_btc_normalized = z_normalize(lib2_btc_raw.values)
lib2_start_date = lib2_btc_raw.index[0]

# 2.3. DNA Library 3: AAPL 2019 Control Group
aapl_growth_df = yf.download('AAPL', start='2019-01-01', end='2019-12-31')
lib3_aapl_raw = aapl_growth_df['Close'].loc['2019-10-01':'2019-12-31']
lib3_aapl_normalized = z_normalize(lib3_aapl_raw.values)
lib3_start_date = lib3_aapl_raw.index[0]

# --- Task 3: Execute the "DNA Test" ---

# Test 1: GME vs GME
dist_profile_gme = stumpy.mass(gme_query_normalized, lib1_gme_normalized)
best_dist_gme = np.min(dist_profile_gme)
best_idx_gme = np.argmin(dist_profile_gme)
best_match_date_gme = lib1_start_date + pd.to_timedelta(best_idx_gme, unit='D')

# Test 2: GME vs BTC
dist_profile_btc = stumpy.mass(gme_query_normalized, lib2_btc_normalized)
best_dist_btc = np.min(dist_profile_btc)
best_idx_btc = np.argmin(dist_profile_btc)
best_match_date_btc = lib2_start_date + pd.to_timedelta(best_idx_btc, unit='D')

# Test 3: GME vs AAPL
dist_profile_aapl = stumpy.mass(gme_query_normalized, lib3_aapl_normalized)
best_dist_aapl = np.min(dist_profile_aapl)
best_idx_aapl = np.argmin(dist_profile_aapl)
best_match_date_aapl = lib3_start_date + pd.to_timedelta(best_idx_aapl, unit='D')

# --- Task 4: Final Report ---

print("--- Bubble DNA Test Report ---")
print("\nTest 1: GME Query vs. GME 2021 Squeeze")
print(f"Best Match Distance: {best_dist_gme:.4f}")
print(f"Best Match Start Date: {best_match_date_gme.strftime('%Y-%m-%d')}")

print("\nTest 2: GME Query vs. BTC 2017 Bubble")
print(f"Best Match Distance: {best_dist_btc:.4f}")
print(f"Best Match Start Date: {best_match_date_btc.strftime('%Y-%m-%d')}")

print("\nTest 3: GME Query vs. AAPL 2019 Control Group")
print(f"Best Match Distance: {best_dist_aapl:.4f}")
print(f"Best Match Start Date: {best_match_date_aapl.strftime('%Y-%m-%d')}")
