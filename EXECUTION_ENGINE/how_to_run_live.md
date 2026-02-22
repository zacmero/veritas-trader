Phase 1: The Clean Slate (Tonight)
  Goal: Ensure no "ghosts" from previous tests interfere.

   1. Flush Orders: Cancel all open orders on Alpaca Paper (use the Web UI or run python3
      EXECUTION_ENGINE/debug_state.py then cancel).
   2. Close Positions: Manually close all positions (including shorts) on Alpaca Paper.
   3. Reset Memory: Delete the old portfolio file.
       rm EXECUTION_ENGINE/portfolio.csv
   4. Reset Account (Optional): If your Paper equity is messy, hit "Reset" on the Alpaca Dashboard to start
      fresh with $100k.
   5. **IMPORTANT** Delete all the old entries in portfolio.csv, actionable_signals.csv and trade_history.txt. 

  ---

  Phase 2: The Setup (Monday Morning - Before 9:30 AM ET)
  Goal: Prepare the targets and start the engine.

   1. Generate Signals: (Run this after your nightly scan finishes).
       python3 -m EXECUTION_ENGINE.rank_live_signals
       * Check: Ensure it says "Found X actionable signals" and saves the CSV.

   2. Start the Master Brain: (Run this in a separate terminal or screen session. Keep it running all day).
       while true; do python3 -m EXECUTION_ENGINE.portfolio_manager_master; sleep 1; done
       * Check: It should say "Managing 0 positions" initially.

  ---

  Phase 3: The Strike (Monday - 9:35 AM ET)
  Goal: Enter the market safely.

   1. Wait: Do not run at 9:30 sharp. Wait 5 minutes for the spread to settle.
   2. Execute:
       python3 -m EXECUTION_ENGINE.auto_trader
   3. Verify:
       * Watch the Master Brain terminal. It should immediately detect the new positions and switch from
         "Managing 0" to "Managing X positions".
       * It will start printing HOLD ticker | P/L: ....

  ---

  Phase 4: The Grind (Intraday)
  Goal: Let the machine work.

   1. Do Nothing. The portfolio_manager_master is handling everything (Stops, Moons, Trails).
   2. Audit (Optional): If you want to check P/L without disturbing the engine:
       python3 -m EXECUTION_ENGINE.investment_reporter

  Phase 5: The Debrief (Monday - 4:05 PM ET)
  Goal: Analyze performance.

   1. Run Report:
       python3 -m EXECUTION_ENGINE.investment_reporter
   2. Review: Check "DAY P/L" and "CLOSED POSITIONS".


