
import stumpy
import numpy as np

# This is a minimal script to isolate the stumpy.floss issue.

try:
    # 1. Create a simple, non-trivial time series.
    m = 30
    ts_len = 300
    ts = np.random.rand(ts_len)
    print(f"Created a sample time series of length {ts_len}.")

    # 2. Compute the matrix profile and profile indices, which is a prerequisite for floss.
    mp_output = stumpy.stump(ts, m=m)
    I = mp_output[:, 1].astype(np.int64)
    print(f"Successfully computed matrix profile indices. Shape: {I.shape}")

    # 3. Call stumpy.floss with the arguments that were causing the error.
    print(f"Attempting to call stumpy.floss(I, m={m})...")
    
    # The error was "missing 2 required positional arguments: 'm' and 'L'வுகளை".
    # This indicates the function signature is likely floss(I, L, m) or similar,
    # not what I was using. Let's try the most likely correct signature based on the error.
    # The documentation (and common sense I should have used) shows L is the window size.
    
    L = m # In the floss algorithm, L is the window size, which is our 'm'.
    cac = stumpy.floss(I, L)
    
    print("--- SUCCESS ---")
    print(f"stumpy.floss executed correctly.")
    print(f"Output CAC length: {len(cac)}")
    print(f"First 5 CAC values: {np.round(cac[:5], 4)}")

except Exception as e:
    print("\n--- FAILURE ---")
    print(f"The minimal test failed with the following error:")
    print(e)
