How the algorithms work:


portfolio_manager_master.py( // TODO:missing many core concepts)

The Logic Upgrade
  Inside the loop, when we detect a pending sell order:
   1. Log Status: Print PENDING SELL {symbol} | Cur: $X (Y%).
   2. Recovery Check:
       * If the pending order was a Stop Loss (we infer this if P/L was bad), check if current_pl > -2.0% (safe
         zone).
       * If yes -> CANCEL ORDER. "Price recovered. Resuming hold."
   3. Optimization: If the order has been pending for too long (e.g., > 30 mins) and price has moved away, we
      might want to cancel/replace, but for now, the "Recovery Cancel" is the most critical feature.


Now, if GDS(or any asset) dumps to -6% (triggering a sell) and then rallies to -2% while the market is closed, the Manager
  will:
   1. See the pending sell.
   2. See the new price (-2%).
   3. Cancel the Sell.
   4. Resume holding.

  This effectively gives you a Dynamic Trailing Stop that works even when the market is closed.

  Command to run:

   while true; do python3 -m EXECUTION_ENGINE.portfolio_manager_master; sleep 1; done

