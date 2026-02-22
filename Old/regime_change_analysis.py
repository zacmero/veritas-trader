import yfinance as yf
import pandas as pd
import numpy as np
import stumpy
import matplotlib.pyplot as plt

# Task 1: Load and Prepare Data
gme_df = yf.download('GME', start='2017-01-01', end='2023-01-01')
gme_close = gme_df['Close'].dropna()

# Task 2: Compute the Regime Change (CAC) Curve
m = 30
mp_output = stumpy.stump(gme_close.values.flatten(), m)
I = mp_output[:, 1] # Profile Indices

# Use stumpy.fluss for Corrected Arc Curve calculation, specifying 2 regimes
cac, _ = stumpy.fluss(I, m, n_regimes=2)

# Task 3: Find the Top Regime Change Point
change_point_idx = np.argmin(cac)
change_point_date = gme_df.index[change_point_idx]

# Task 4: Report and Visualize

# Report
print(f"The most significant regime change was detected on: {change_point_date.strftime('%Y-%m-%d')}")

# Visualize
plt.figure(figsize=(15, 10))

# Panel 1: GME Close Price
ax1 = plt.subplot(2, 1, 1)
ax1.plot(gme_df.index, gme_close.values, label='GME Close')
ax1.set_title('GME Close Price with Detected Regime Change')
ax1.axvline(x=change_point_date, color='red', linestyle='--', label=f'Regime Change: {change_point_date.strftime("%Y-%m-%d")}')
ax1.legend()

# Panel 2: Corrected Arc Curve (CAC)
ax2 = plt.subplot(2, 1, 2, sharex=ax1)
ax2.plot(gme_df.index[:len(cac)], cac, label='Corrected Arc Curve (CAC)')
ax2.set_title('Regime Change Detection using CAC')
ax2.plot(change_point_date, cac[change_point_idx], 'X', ms=10, color='red', label=f'Minimum CAC at {change_point_date.strftime("%Y-%m-%d")}')
ax2.legend()

plt.tight_layout()
plt.savefig('gme_regime_change.png')

print("\ngme_regime_change.png has been created.")