import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from datetime import datetime, timedelta

# --- CONFIGURATION ---
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
FINAL_LIBRARY_PATH = os.path.join(BASE_PATH, "..", "ARCHETYPE_LIBRARY_FINAL")
DNA_WINDOW = 30

os.makedirs(FINAL_LIBRARY_PATH, exist_ok=True)

# --- THE CORRECT, ROBUST Z-NORMALIZE FUNCTION ---
def z_normalize(series):
    std_dev = np.std(series)
    if std_dev < 1e-6:
        return np.zeros_like(series)
    return (series - np.mean(series)) / std_dev

# --- THE COMPLETE LIST OF ALL 15 VALUABLE ARCHETYPES ---
ALL_ARCHETYPES_DATA = [
    # --- The Legacy Eight ---
    {'name': 'L_VWAGY_m15_ramp', 'ticker': 'VWAGY', 'start_date': '2008-09-17'},
    {'name': 'L_AMC_m30_ramp', 'ticker': 'AMC', 'start_date': '2021-02-09'},
    {'name': 'L_CSCO_m90_ramp', 'ticker': 'CSCO', 'start_date': '1999-11-04'},
    {'name': 'L_DOGE-USD_m30_ramp', 'ticker': 'DOGE-USD', 'start_date': '2022-03-15'},
    {'name': 'L_GME_m90_ramp', 'ticker': 'GME', 'start_date': '2020-11-09'},
    {'name': 'L_IYR_m120_ramp', 'ticker': 'IYR', 'start_date': '2006-12-26'},
    {'name': 'L_SHIB-USD_m30_ramp', 'ticker': 'SHIB-USD', 'start_date': '2021-10-09'},
    {'name': 'L_SSYS_m90_ramp', 'ticker': 'SSYS', 'start_date': '2013-10-31'},
    # --- The Battle-Tested Seven (Learned) ---
    {'name': 'C_GME_20201109_m90', 'ticker': 'GME', 'start_date': '2020-11-09'},
    {'name': 'C_SOL_20210204_m60', 'ticker': 'SOL-USD', 'start_date': '2021-02-04'},
    {'name': 'C_SOL_20210823_m10', 'ticker': 'SOL-USD', 'start_date': '2021-08-23'},
    {'name': 'C_AMC_20210209_m30', 'ticker': 'AMC', 'start_date': '2021-02-09'},
    {'name': 'C_PTON_20200529_m15', 'ticker': 'PTON', 'start_date': '2020-05-29'},
    {'name': 'C_ETH_20201209_m10', 'ticker': 'ETH-USD', 'start_date': '2020-12-09'},
    {'name': 'C_NVAX_20200427_m15', 'ticker': 'NVAX', 'start_date': '2020-04-27'},
]

# --- MAIN REFINERY LOGIC ---
def main():
    print("--- [Archetype Refinery v2.0 Started] ---")
    
    for archetype_info in ALL_ARCHETYPES_DATA:
        name = archetype_info['name']
        ticker = archetype_info['ticker']
        start_date_str = archetype_info['start_date']
        
        print(f"\n--- Refining: {name} ---")
        
        try:
            start_date_dt = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date_dt = start_date_dt + timedelta(days=DNA_WINDOW + 30)
            
            data = yf.download(ticker, start=start_date_dt, end=end_date_dt, progress=False, auto_adjust=True)
            
            ramp_data = data.head(DNA_WINDOW)
            if len(ramp_data) < DNA_WINDOW:
                print(f"  ERROR: Not enough data found for {name}. Found {len(ramp_data)} days.")
                continue

            raw_pattern = ramp_data['Close'].values
            normalized_pattern = z_normalize(raw_pattern)
            
            npy_filename = f"{name}.npy"
            np.save(os.path.join(FINAL_LIBRARY_PATH, npy_filename), normalized_pattern)
            
            plt.figure(figsize=(10, 6))
            plt.plot(raw_pattern)
            plt.title(f"REFINED Archetype: {name}\nStart: {start_date_str}")
            plt.ylabel("Price")
            plt.xlabel("Days (from start date)")
            img_filename = f"{name}.png"
            plt.savefig(os.path.join(FINAL_LIBRARY_PATH, img_filename))
            plt.close()
            
            print(f"  SUCCESS: Refined archetype saved to {FINAL_LIBRARY_PATH}")

        except Exception as e:
            print(f"  CRITICAL ERROR refining {name}: {e}")

    print("\n--- [Archetype Refinery Finished] ---")

if __name__ == "__main__":
    main()