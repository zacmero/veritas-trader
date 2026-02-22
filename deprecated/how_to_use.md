### **The Master System: Complete Documentation (v1.0)**

This document provides a complete overview of the Bubble Detection System, from its core components to a practical user guide for running simulations.

### **Part 1: System Overview (The "Simple Explanation")**

Imagine our system is a team of expert earthquake detectors watching the stock market for speculative bubbles.

*   **The Detectors (The `m` value "Lenses"):** Each of our detectors is a specialist. A **small `m` value (like `m=15`)** is a local sensor, designed to spot **fast, violent tremors** (meme stock squeezes). A **large `m` value (like `m=90`)** is a deep-earth sensor that ignores minor noise and only triggers on **massive, slow-building tectonic shifts** (like the dot-com bubble).

*   **The Entry Checklist (The 3 Filters):** When a detector senses a tremor, it runs a 3-step checklist before sounding the "BUY" alarm:
    1.  **Filter 1 (The Tremor):** The algorithm finds a major change in the stock's "personality" (a "valley" in the CAC curve).
    2.  **Filter 2 (The Intensity):** It confirms the tremor is causing the ground to move *upward* with force, checking if the stock has jumped at least **10%** in the past 30 days.
    3.  **Filter 3 (The Fingerprint):** It compares the 30-day "fingerprint" of this tremor to our library of famous historical bubbles (like GameStop).

*   **The Exit Signal (The "Safety Net"):** Once we're in a trade, we deploy a smart "safety net" (an ATR Trailing Stop) that follows the price up. When the stock is volatile, the net stays far away; when it's calm, the net moves closer. The "SELL" alarm sounds the moment the price falls and breaks this net, protecting our profits.

---

### **Part 2: The Tools of the Trade**

The project consists of two primary, active scripts in the `BACKTESTER/` folder.

#### **1. `generate_new_archetypes.py` (The Master Forger)**

*   **Purpose:** This script is our tool for **manually creating the foundational archetypes** that form the "brain" of our system. It is used when we identify a new, major historical bubble that we want to add to our library.
*   **How it Works:**
    1.  A human provides a known bubble to analyze (e.g., "GME from 2017-2023").
    2.  The script finds all significant regime changes ("valleys") within that period.
    3.  It identifies the single valley that was followed by the **most explosive upward ramp** (the highest positive slope).
    4.  It saves the 30-day price pattern of that specific ramp as two files in the `ARCHETYPE_LIBRARY/`:
        *   A `.png` image for human verification.
        *   A `.npy` data file (the "fingerprint") for the trading simulator to use.

#### **2. `trading_simulator.py` (The Master System / The Hunter)**

*   **Purpose:** This is the core engine of the project. It backtests our complete, end-to-end trading strategy on any asset, providing a detailed report of its profitability.
*   **How it Works:**
    1.  **Setup:** It loads the full historical data for a stock and our entire Archetype Library.
    2.  **Pre-computation (The Map):** To be fast, it calculates the CAC curve **once** for the entire history and identifies all potential trigger dates ("valleys") ahead of time.
    3.  **Daily Simulation:** It then loops through the timeline day-by-day.
        *   **If NOT in a trade:** It checks if the current date is one of the pre-calculated trigger dates. If it is, it runs the 3-step **Entry Funnel** on the data *leading up to that day*. If all filters pass, it logs a **"BUY" signal** and enters a trade.
        *   **If IN a trade:** It checks the **ATR Trailing Stop** exit condition every day. If the price breaks the "safety net," it logs a **"SELL" signal**, exits the trade, and calculates the profit.
    4.  **The Learning System:** After a profitable "SELL" (`>50%` profit), the system performs a final check. It verifies that the initial 30-day ramp was a truly explosive event (in the top 2% of the stock's own history). If it was, the system automatically saves that ramp's fingerprint to the `CANDIDATE_LIBRARY/` folder for future analysis.

### **Part 3: How to Use the System (User Guide)**

This guide explains how to run a simulation and interpret the results.

#### **1. Setting Up the Environment**

All commands must be run from a terminal that is inside a Python virtual environment (`venv`).

1.  **Open your terminal.**
2.  **Navigate to the project's root directory:**
    ```bash
    cd path/to/your/bubble-detector
    ```
3.  **Activate the virtual environment:**
    ```bash
    source venv/bin/activate
    ```
    Your terminal prompt should now start with `(venv)`.

    Make sure all packages are installed: 
    
    ```bash
    pip install -r requirements.txt
    ```

#### **2. Running a Simulation**

You will use the `trading_simulator.py` script. The command has a clear and consistent structure.

**Command Structure:**
```bash
python3 BACKTESTER/trading_simulator.py --ticker "{TICKER}" --start "{YYYY-MM-DD}" --end "{YYYY-MM-DD}" --m {M_VALUE} --logfile "{LOG_FILENAME}.log"
```

**Argument Breakdown:**
*   `--ticker`: The stock symbol you want to test (e.g., "TSLA", "BTC-USD").
*   `--start`: The beginning of the historical period to analyze.
*   `--end`: The end of the historical period.
*   `--m`: The "lens" you want to use for the detector (`15`, `30`, `60`, `90`, or `120`).
*   `--logfile`: The name of the file where the detailed results will be saved.

**Example Command:**
To run a simulation on Tesla (`TSLA`) from 2018 to 2023 using the `m=30` detector, you would run:
```bash
python3 BACKTESTER/trading_simulator.py --ticker "TSLA" --start "2018-01-01" --end "2023-01-01" --m 30 --logfile "sim_TSLA_m30.log"
```

#### **3. Where to Find the Results**

The results are generated in two places:

1.  **The Terminal:** The full, detailed log will be printed to your screen as the script runs.
2.  **The Log File:** A complete copy of that log is saved permanently in the `BACKTESTER/LOGS/` folder with the filename you specified (e.g., `sim_TSLA_m30.log`).

#### **4. How to Read the Logs**

The log is designed to be read from top to bottom, but the most important information is at the end.

*   **`[F1 TRIGGER]`:** This indicates the system has found a potential entry point.
*   **`[Filter 2]` & `[Filter 3]`:** These lines show the results of the entry checklist. You can see the exact growth percentage and DNA distance for each candidate.
*   **`!!! BUY SIGNAL !!!`:** This confirms a trade has been entered. It shows the date, price, and which archetype it matched.
*   **`!!! SELL SIGNAL !!!`:** This confirms a trade has been closed. It shows the date, price, exit reason, and the final profit or loss.
*   **`--- [TRADING SIMULATION REPORT] ---`:** This is the most important section at the very end of the file. It provides a clean, final summary of all trades executed, the win rate, and the average profit per trade. This is the definitive measure of the system's performance for that run.

---

### **Extra OBS: The Role of `slope_calibrator.py`**

You asked about the `slope_calibrator.py` script.

*   **Its Purpose:** This was a **temporary, diagnostic tool.** We used it during our research phase to discover that "raw slope" was a flawed metric and that "percentage growth" was the correct one.
*   **Is it still relevant?** No. Its findings have been permanently integrated into the main `trading_simulator.py` (the `MIN_PERCENTAGE_GROWTH = 10.0` filter).
*   **Action:** The script can be safely **deleted or archived.** It is no longer needed for the operation of the Master System.