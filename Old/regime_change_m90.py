
import yfinance as yf
import pandas as pd
import numpy as np
import stumpy
import matplotlib.pyplot as plt

# Task 1: Load and Prepare Data
print("Loading GME data...")
gme_df = yf.download('GME', start='2017-01-01', end='2023-01-01', progress=False)
gme_close = gme_df['Close'].dropna()

# Task 2: Compute the Regime Change (CAC) Curve with m=90
m = 90
print(f"Computing Matrix Profile and CAC with window size m={m}...")
mp_output = stumpy.stump(gme_close.values.flatten(), m)
I = mp_output[:, 1]  # Profile Indices

# Note: Using stumpy.fluss as it's the correct implementation for CAC-based segmentation.
# We find the single best split by setting n_regimes=2.
cac, _ = stumpy.fluss(I, m, n_regimes=2)

# Task 3: Find the Top Regime Change Point
print("Finding the most significant regime change point...")
change_point_idx = np.argmin(cac)
change_point_date = gme_df.index[change_point_idx]

# Task 4: Report and Visualize

# Report
print(f"\nCritical Test Result:")
print(f"The most significant regime change with m=90 was detected on: {change_point_date.strftime('%Y-%m-%d')}")

# Visualize
print("Generating visualization...")
plt.figure(figsize=(15, 10))

# Panel 1: GME Close Price
ax1 = plt.subplot(2, 1, 1)
ax1.plot(gme_df.index, gme_close.values, label='GME Close')
ax1.set_title(f'GME Close Price with Detected Regime Change (m={m})')
ax1.axvline(x=change_point_date, color='red', linestyle='--', label=f'Regime Change: {change_point_date.strftime("%Y-%m-%d")}')
ax1.legend()

# Panel 2: Corrected Arc Curve (CAC)
ax2 = plt.subplot(2, 1, 2, sharex=ax1)
# The CAC is shorter than the time series, so we align it with the start.
cac_dates = gme_df.index[:len(cac)]
ax2.plot(cac_dates, cac, label='Corrected Arc Curve (CAC)')
ax2.set_title(f'Regime Change Detection using CAC (m={m})')
ax2.plot(change_point_date, cac[change_point_idx], 'X', ms=12, color='red', label=f'Minimum CAC')
ax2.legend()

plt.tight_layout()
plt.savefig('gme_regime_change_m90.png')

print("\nPlot saved as gme_regime_change_m90.png.")
