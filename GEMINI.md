# Veritas Trader (v1.0) - The Casino Engine

## 0. ORCHESTRATOR PROTOCOL (YOU ARE THE LEAD AGENT)
You are the **Lead Orchestrator** for this quantitative system. You do not write boilerplate code yourself. Your job is to plan, create isolated environments, and delegate tasks to specialized `codex` sub-agents via the `pal` MCP server.

**Your Strict Workflow:**
1. **Analyze:** Break user requests into distinct components (e.g., "Refactor execution engine", "QA live paper trades").
2. **Isolate:** Use terminal commands to create a `git worktree` for the task (e.g., `git worktree add ../temp-task-name`).
3. **Delegate:** Use `pal clink` to spawn a Codex sub-agent inside that worktree. 
   * Example: `pal clink "cd ../temp-task-name && codex --agent refactorer 'Refactor the prime_math.py logic'"`
   * Example: `pal clink "cd ../temp-task-name && cp ../main-repo/.env.paper .env && codex --agent qa 'Run dynamic_hedger.py and monitor for 5 mins'"`
4. **Review & Merge:** When a sub-agent pushes a branch, review the diff. If it passes your standards, merge it into `main` and clean up the worktree (`git worktree remove ../temp-task-name`).

---

## 0.1 General Observations: Serena (MCP) is the primary code navigation + editing tool

When working in this repo, always prefer Serena MCP tools over manual file reading or text-based search:
- Use `find_symbol`, `get_symbols_overview`, `find_referencing_symbols` to locate code.
- Use symbol-targeted edits (`replace_symbol_body`, `replace_content`, `insert_before_symbol/after_symbol`) instead of editing whole files.
- Only read full files when symbol-level retrieval is insufficient.
- Use at most ~5 Serena calls to locate and understand something; if still unclear, ask for a full-file read of the single best candidate.
- If Serena can’t find it, switch to search_for_pattern or a targeted file read.
- If Serena calls exceed ~8 steps without resolving the question, stop and switch strategy:
(1) pick the single most relevant file, (2) read only that file/section, (3) proceed with a plan. Avoid long tool-call loops.
Goal: minimize token usage and avoid brittle search/replace; keep changes precise and reviewable via `git diff`.

## 1. System Philosophy & Edge
Veritas Trader is a quantitative, market-neutral algorithmic trading system. It does not predict stock direction. Instead, it trades **Volatility** using the Black-Scholes-Merton options pricing model.

* **Strategy:** Gamma Scalping / Delta-Neutral Hedging.
* **The Edge:** We buy Options (Long Volatility) and continuously buy/sell the underlying stock to maintain a Delta of Zero. As the stock price fluctuates, the continuous rebalancing (buying dips, shorting rips) generates cash flow to offset the option's time decay (Theta).
* **Risk Management:** Market Neutrality. We are immune to standard market crashes or rallies, provided we hedge fast enough.
* **Target Assets:** High-liquidity, low-gap-risk ETFs (SPY, QQQ).

---

## 2. Architecture Overview

The system is a continuous feedback loop. It calculates the theoretical mathematical requirements of our options and forces our stock portfolio to match it.

[ STOCK MARKET DATA ] -> [ PRIME MATH ENGINE ] -> [ DYNAMIC HEDGER ] -> [ ALPACA BROKER ]

---

## 3. Core Components (`EXECUTION_ENGINE/`)

### **A. The Math Engine: `prime_math.py`**
This is the brain of the operation. It contains the pure quantitative finance formulas.
* **Black-Scholes Pricer:** Calculates theoretical option prices.
* **IV Root Finder (Newton-Raphson):** Reverse-engineers Implied Volatility (IV) from live Alpaca option prices (saving us from expensive data subscriptions).
* **Delta Calculator:** Calculates the exact $\Delta$ (Delta) of our option contracts to determine our required stock hedge.

### **B. The Execution Loop: `dynamic_hedger.py`**
Replaces the old portfolio manager. This daemon runs continuously during market and extended hours.
* **Logic:**
    1. Identifies active Option positions in the portfolio.
    2. Fetches live underlying stock price and option price.
    3. Calls `prime_math.py` to calculate current IV and Target Delta.
    4. Calculates `Required Shares = Target Delta * 100 * Contract Qty`.
    5. Compares `Required Shares` to `Current Held Shares`.
    6. **Action:** If the difference exceeds the `HEDGE_THRESHOLD` (e.g., > 5 shares), it executes a Market Buy or Short Sell to rebalance to Delta Neutral.
* **Gap Protection:** Operates in After-Hours trading to hedge against late-breaking news.

### **C. The Adapter: `executor_interface.py` & `alpaca_executor.py`**
* Retained from v2.0. Handles API rate limits, order execution, and position querying.
* **Crucial Update:** Must support `asset_class='us_option'` and robust Short Selling of equities.

### **D. The Accountant: `investment_reporter.py`**
* Reconciles realized P/L from the thousands of micro-hedging trades and the final option closure.

---

## 4. Operational Protocol

### **Phase 1: Initialization**
1.  **Manual/Bot Entry:** A Long Option position (Call or Put) is opened on a highly liquid ETF (e.g., SPY).
2.  **Start the Hedger:**
    ```bash
    while true; do python3 -m EXECUTION_ENGINE.dynamic_hedger; sleep 60; done
    ```
    *Note: The loop sleeps for 60 seconds to prevent API rate limiting and over-trading minor noise.*

### **Phase 2: The Grind (Intraday & After-Hours)**
* The `dynamic_hedger` continuously buys and shorts the underlying stock. 
* No directional "Stop Losses" or "Moonshots" are used on the stock. The stock is merely a mathematical counterweight to the option.

### **Phase 3: Exit**
* The position is closed when the Option reaches a target profit (Implied Volatility spikes) or is closed manually before expiration to avoid assignment risk.

---

## 5. Developer Notes & Safety Constraints
* **No Naked Selling:** Due to broker API tier limits, we primarily execute **Long Options + Short/Long Stock** (Gamma Scalping) rather than Short Options, avoiding "Covered Call" 100-share lockup rejections.
* **Earnings/Dividends:** Do NOT hold individual stocks over earnings. Stick to ETFs (SPY, QQQ) to avoid mathematical breakdown via massive overnight price gaps.
* **Data:** We use standard Alpaca SIP/IEX feeds. IV is calculated locally via `prime_math.py` to avoid premium data costs.