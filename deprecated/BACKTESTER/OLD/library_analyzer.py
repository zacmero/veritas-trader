import numpy as np
import os
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from colorama import init, Fore, Style

# --- INITIALIZE COLORAMA ---
init(autoreset=True)

# --- CONFIGURATION ---
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
# --- IMPORTANT: Point to the TWO libraries we want to analyze ---
LEGACY_LIB_PATH = os.path.join(BASE_PATH, "..", "ARCHETYPE_LIBRARY_LEGACY")
LEARNED_LIB_PATH = os.path.join(BASE_PATH, "..", "ARCHETYPE_LIBRARY")
OUTPUT_PATH = os.path.join(BASE_PATH, "library_analysis.png")

# --- HELPER: Z-Normalization (The Correct, Robust Version) ---
def z_normalize(series):
    std_dev = np.std(series)
    if std_dev < 1e-6:
        # Return None for flat-line patterns, we'll handle them as corrupted
        return None
    return (series - np.mean(series)) / std_dev

# --- MAIN ANALYSIS LOGIC ---
def main():
    print(Fore.CYAN + "--- [Archetype Library Analyzer Started] ---")
    
    all_archetypes = {}
    
    # 1. Load all archetypes from both libraries
    print("Loading archetypes from LEGACY library...")
    for file in os.listdir(LEGACY_LIB_PATH):
        if file.endswith(".npy"):
            path = os.path.join(LEGACY_LIB_PATH, file)
            pattern = np.load(path)
            normalized_pattern = z_normalize(pattern)
            if normalized_pattern is not None:
                all_archetypes[f"L_{file[:-4]}"] = normalized_pattern # "L" for Legacy
            else:
                print(Fore.RED + f"  - WARNING: Corrupted or flat-line pattern detected and skipped: {file}")

    print("Loading archetypes from LEARNED (Candidate) library...")
    for file in os.listdir(LEARNED_LIB_PATH):
        if file.endswith(".npy"):
            path = os.path.join(LEARNED_LIB_PATH, file)
            pattern = np.load(path)
            normalized_pattern = z_normalize(pattern)
            if normalized_pattern is not None:
                all_archetypes[f"C_{file[:-4]}"] = normalized_pattern # "C" for Candidate/Learned
            else:
                print(Fore.RED + f"  - WARNING: Corrupted or flat-line pattern detected and skipped: {file}")

    if not all_archetypes:
        print(Fore.RED + "No valid archetypes found to analyze.")
        return

    print(f"\nLoaded a total of {len(all_archetypes)} unique archetypes for analysis.")

    # 2. Calculate the similarity matrix
    archetype_names = list(all_archetypes.keys())
    num_archetypes = len(archetype_names)
    similarity_matrix = np.zeros((num_archetypes, num_archetypes))

    print("Calculating pairwise distances...")
    for i in range(num_archetypes):
        for j in range(i, num_archetypes):
            name_i = archetype_names[i]
            name_j = archetype_names[j]
            
            pattern_i = all_archetypes[name_i]
            pattern_j = all_archetypes[name_j]
            
            # Using simple Euclidean distance as they are all normalized and same length
            distance = np.linalg.norm(pattern_i - pattern_j)
            
            similarity_matrix[i, j] = distance
            similarity_matrix[j, i] = distance # Matrix is symmetric

    # 3. Generate and save the heatmap
    print("Generating heatmap...")
    plt.figure(figsize=(20, 18))
    sns.heatmap(
        similarity_matrix,
        xticklabels=archetype_names,
        yticklabels=archetype_names,
        annot=True,
        fmt=".2f",
        cmap="viridis_r", # Use a reversed colormap so low distances (good) are bright
        linewidths=.5
    )
    plt.title("Archetype Similarity Matrix (Euclidean Distance)", fontsize=20)
    plt.xticks(rotation=90)
    plt.yticks(rotation=0)
    plt.tight_layout()
    
    plt.savefig(OUTPUT_PATH)
    print(Fore.GREEN + f"\n--- SUCCESS: Analysis complete. ---")
    print(Fore.GREEN + f"Heatmap saved to: {OUTPUT_PATH}")

    # 4. Print out the most similar pairs for easy analysis
    print("\n--- [Top 10 Most Similar Archetype Pairs] ---")
    pairs = []
    for i in range(num_archetypes):
        for j in range(i + 1, num_archetypes):
            pairs.append((archetype_names[i], archetype_names[j], similarity_matrix[i, j]))
            
    # Sort by distance (ascending)
    sorted_pairs = sorted(pairs, key=lambda x: x[2])
    
    for name_i, name_j, dist in sorted_pairs[:10]:
        verdict = ""
        if dist < 2.75: verdict = Fore.GREEN + "(Strict Match - Redundant)"
        elif dist < 4.75: verdict = Fore.YELLOW + "(Loose Match - Related)"
        print(f"- {name_i:<40} vs. {name_j:<40} | Distance: {dist:.4f} {verdict}")


if __name__ == "__main__":
    main()