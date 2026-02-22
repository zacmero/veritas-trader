# Algorithmic Trading Automation System (Alpaca Edition)

## 1. System Architecture

This system implements a modular **"Factory Line"** architecture for automated trading, designed using the **Adapter Pattern** to ensure future flexibility (e.g., switching brokers).

### The Four Pillars
1.  **Discovery (Scanner):** Identifies profitable opportunities.
2.  **Filtration (Ranker):** Validates and prioritizes signals based on historical edge.
3.  **Execution (Auto Trader):** Allocates capital and safely enters positions (Fractional/Whole).
4.  **Management (Manager/Stream):** Monitors positions in real-time for surgical exits (Stop Loss, Take Profit, Trailing).

---

## 2. Directory Structure (`EXECUTION_ENGINE/`)

| File | Role | Description |
| :--- | :--- | :--- |
| `executor_interface.py` | **Contract** | Defines the abstract `OrderExecutor` class. Any broker adapter MUST implement these methods. |
| `alpaca_executor.py` | **Adapter** | The concrete implementation for Alpaca. Handles API connections, price data (IEX), and order logic (Fractional Fallback). |
| `rank_live_signals.py` | **Filter** | Scans `LOGS_QUICKSTRIKE`, filters for `PROFITABLE` + `IN_TRADE` signals, and generates `actionable_signals.csv`. |
| `auto_trader.py` | **Entry** | Reads the CSV, calculates position sizing (Cash / Signals), and executes entries via the Executor. |
| `stream_manager.py` | **Brain** | Connects to Alpaca's WebSocket. Detects Entry Fills and immediately places "Manual Bracket" orders (Stop Loss + Limit Sell). |
| `portfolio_manager.py` | **Grinder** | Runs periodically (cron). Checks for "Soft Exits" (Time Stop, Break Even, Trailing) and manages the portfolio CSV. |
| `investment_reporter.py` | **Audit** | Generates a detailed P/L report of Open Positions and Account Equity. |
| `utils.py` | **Utility** | Securely loads credentials from `.env`. |

---

## 3. Operational Workflow

### Step 0: Prerequisites
*   **Environment:** A `.env` file in the project root containing:
    ```bash
    ALPACA_API_KEY=PKQQ...
    ALPACA_SECRET_KEY=ALNt...
    ALPACA_ENDPOINT=https://paper-api.alpaca.markets
    ```
*   **Daemon:** The `stream_manager.py` MUST be running in the background (Screen/Tmux) to handle protection stops.

### Step 1: Discovery (Night/Dawn)
The `master_scanner_quickstrike.py` (or Hybrid) runs on your target list. It generates logs in `NIGHTLY_SCANNER/LOGS_QUICKSTRIKE`.
*   *Signal:* `IN_TRADE_live_qs_TICKER.log`

### Step 2: Filtration (6:00 AM)
Run `rank_live_signals.py`.
*   It parses the logs.
*   It rejects "Black Sheep" strategies (unless configured otherwise).
*   It prioritizes high-win-rate signals.
*   **Output:** `actionable_signals.csv`.

### Step 3: Execution (Market Open + 5 mins)
Run `auto_trader.py`.
*   It reads the CSV.
*   It checks your Buying Power.
*   It calculates equal allocation (e.g., $200k / 5 signals = $40k each).
*   It submits **Market Buy** orders.
    *   *Feature:* If the asset supports fractionals, it buys exact dollar amounts.
    *   *Fallback:* If not, it automatically calculates and buys Max Integer Shares.

### Step 4: Protection (Instant)
The `stream_manager.py` (running in background) detects the **FILL**.
*   It immediately calculates:
    *   **Stop Loss:** -5% from Entry Price.
    *   **Moonshot Target:** +20% from Entry Price.
*   It places these as separate Sell Orders (Stop & Limit).

### Step 5: Management (Intraday - Every 5 mins)
The `portfolio_manager.py` runs via Cron.
*   It checks real-time prices (IEX Feed).
*   **Logic:**
    *   **Break Even:** If price > +1.5%, checks if price falls back to Entry.
    *   **Trailing Stop:** If price > +2.0%, trails max price by 50%.
    *   **Time Stop:** Exits if held > 7 Days.
*   If a soft exit triggers, it cancels the hard stops and sells immediately.

---

## 4. How to Run (Manual)

1.  **Start the Brain (One-time):**
    ```bash
    # Run in a separate terminal or screen session
    python3 -m EXECUTION_ENGINE.stream_manager
    ```

2.  **Generate Signals:**
    ```bash
    python3 -m EXECUTION_ENGINE.rank_live_signals
    ```

3.  **Execute Trades:**
    ```bash
    python3 -m EXECUTION_ENGINE.auto_trader
    ```

4.  **Check Status:**
    ```bash
    python3 -m EXECUTION_ENGINE.investment_reporter
    ```

---

## 5. Automation (Cron)

Use the provided `setup_cron.sh` to install these jobs automatically.

| Time | Script | Purpose |
| :--- | :--- | :--- |
| **06:00** | `rank_live_signals` | Prepare the day's target list. |
| **09:35** | `auto_trader` | Execute entries 5 mins after Open. |
| **Every 5m** | `portfolio_manager` | Monitor for trailing exits. |
| **16:05** | `investment_reporter` | End-of-day P/L report. |

---

## 6. Safety Features

*   **Fractional Fallback:** Automatically switches to whole shares if Alpaca rejects the fractional order (`"asset not fractionable"`).
*   **Orphan Order Protection:** Before selling a position, the system forces a `cancel_all_orders(ticker)` to ensure old Stop/Limit orders don't trigger accidentally.
*   **Data Redundancy:** If the real-time `Ask Price` is missing (common in Paper/Off-hours), the system seamlessly falls back to the `Last Trade Price`.
*   **Secure Config:** Credentials are never hardcoded; they are loaded securely from `.env`.
