import numpy as np
import matplotlib.pyplot as plt
import os

# --- CONFIGURATION ---
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
# --- WE ARE NOW COMPARING THE TWO "BUY" ARCHETYPES ---
ARCHETYPE_1_PATH = os.path.join(BASE_PATH, "..", "ARCHETYPE_LIBRARY", "GME_m90_ramp.npy")
ARCHETYPE_2_PATH = os.path.join(BASE_PATH, "..", "CANDIDATE_LIBRARY", "candidate_GME_20201109_m90.npy")

# --- HELPER: Z-Normalization (The Correct One) ---
def z_normalize(series):
    std_dev = np.std(series)
    if std_dev < 1e-6:
        return np.zeros_like(series)
    return (series - np.mean(series)) / std_dev

# --- MAIN DISSECTION LOGIC ---
def main():
    print("--- [Dissector v2.0 Started: Comparing the Two GME 'BUY' Archetypes] ---")

    if not os.path.exists(ARCHETYPE_1_PATH) or not os.path.exists(ARCHETYPE_2_PATH):
        print("ERROR: One or both GME archetype files not found.")
        return

    pattern_1 = np.load(ARCHETYPE_1_PATH)
    pattern_2 = np.load(ARCHETYPE_2_PATH)
    
    # Ensure both are correctly normalized for a fair comparison
    pattern_1_norm = z_normalize(pattern_1)
    pattern_2_norm = z_normalize(pattern_2)

    # Calculate the distance
    distance = np.linalg.norm(pattern_1_norm - pattern_2_norm)
    
    print(f"\n--- [ANALYSIS] ---")
    print(f"Calculated Euclidean Distance between the two 'BUY' archetypes: {distance:.4f}")
    
    if distance < 2.75:
        print("VERDICT: The patterns are a STRICT MATCH. They are capturing the same event.")
    elif distance < 4.75:
        print("VERDICT: The patterns are a LOOSE MATCH. They are related.")
    else:
        print("VERDICT: The patterns are DISSIMILAR.")

    # Visualize the comparison
    plt.figure(figsize=(12, 7))
    plt.title("Dissection: GME 'Legacy' Ramp vs. GME 'Learned' Ramp (Normalized)", fontsize=16)
    
    plt.plot(pattern_1_norm, label=f"Legacy (GME_m90_ramp)", color='blue', linewidth=2)
    plt.plot(pattern_2_norm, label=f"Learned (candidate_GME_20201109_m90)", color='orange', linewidth=2, linestyle='--')
    
    plt.xlabel("Days (0-29)")
    plt.ylabel("Z-Normalized Price")
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.legend()
    
    output_path = os.path.join(BASE_PATH, "dissection_buy_vs_buy.png")
    plt.savefig(output_path)
    print(f"\nVisual comparison saved to: {output_path}")
    print("--- [Dissector v2.0 Finished] ---")

if __name__ == "__main__":
    main()