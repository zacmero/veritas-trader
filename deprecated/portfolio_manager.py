import pandas as pd
import os
from datetime import datetime
from colorama import init, Fore, Style
from .alpaca_executor import AlpacaExecutor
from .utils import load_env_file
import time

init(autoreset=True)

# --- CONFIGURATION ---
BASE_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTFOLIO_FILE = os.path.join(BASE_PATH, "EXECUTION_ENGINE", "portfolio.csv")

# --- QUICK STRIKE EXIT LOGIC ---
BREAK_EVEN_TRIGGER_PCT = 1.5 
MIN_PROFIT_TO_TRAIL = 2.0    
TRAILING_RETRACEMENT = 0.50  
MAX_HOLD_DAYS = 7            

def main():
    load_env_file()
    print(f"{Fore.WHITE}{'='*80}")
    print(f"PORTFOLIO MANAGER - QUICK STRIKE LOGIC (ALPACA SOURCE OF TRUTH)")
    print(f"{'='*80}")
    
    # Load Portfolio CSV for High Water Marks (Memory)
    portfolio_mem = {}
    if os.path.exists(PORTFOLIO_FILE):
        try:
            df = pd.read_csv(PORTFOLIO_FILE)
            # Create a dict mapping Ticker -> MaxPrice
            for _, row in df.iterrows():
                portfolio_mem[row['Ticker']] = float(row.get('MaxPriceReached', 0.0))
        except: pass

    # Connect
    print("Authenticating...")
    try:
        bot = AlpacaExecutor(paper_trading=True)
        bot.connect()
    except:
        return

    # 1. Fetch ALL Actual Positions from Alpaca
    real_positions = bot.trading_client.get_all_positions()
    print(f"Found {len(real_positions)} active positions on Alpaca.")

    indices_to_drop = []
    
    # We will rebuild the CSV data based on reality
    new_csv_data = []

    for pos in real_positions:
        ticker = pos.symbol
        qty = float(pos.qty)
        entry_price = float(pos.avg_entry_price)
        current_price = float(pos.current_price)
        
        # Skip Shorts (Negative Qty) - Manual intervention needed
        if qty < 0:
            print(f"{Fore.RED}SKIPPING SHORT POSITION: {ticker} ({qty}) - CLOSE MANUALLY")
            continue

        # Get High Water Mark from memory, or init with Entry
        max_price_reached = portfolio_mem.get(ticker, entry_price)
        
        # Update HWM
        if current_price > max_price_reached:
            max_price_reached = current_price
        
        current_profit_pct = float(pos.unrealized_plpc) * 100
        # Recalculate max profit pct based on HWM
        max_profit_pct = ((max_price_reached - entry_price) / entry_price) * 100.0
        
        # --- EXIT LOGIC ---
        sell_signal = False
        reason = ""

        # 1. Retracement Ceiling
        ceiling_price = 0.0
        if max_profit_pct >= MIN_PROFIT_TO_TRAIL:
            ceiling_price = entry_price * (1 + (max_profit_pct/100) * (1 - TRAILING_RETRACEMENT))
            if current_price <= ceiling_price:
                sell_signal = True
                reason = f"Retracement (Max {max_profit_pct:.2f}%)"

        # 2. Break Even Floor
        if not sell_signal and max_profit_pct >= BREAK_EVEN_TRIGGER_PCT:
            if current_price <= entry_price:
                sell_signal = True
                reason = "Break Even"

        # 3. Emergency Stop (Hard -5% on equity)
        if not sell_signal and current_profit_pct <= -5.0:
            sell_signal = True
            reason = f"Emergency Stop (P/L {current_profit_pct:.2f}%)"

        # --- EXECUTION ---
        if sell_signal:
            print(f"{Fore.GREEN}SELLING {ticker} ({reason}){Style.RESET_ALL}")
            bot.place_market_sell(ticker, qty)
            # Do not add to new_csv_data
        else:
            # Color coding
            c = Fore.GREEN if current_profit_pct > 0 else Fore.RED
            print(f"HOLD {ticker:<6} | Cur: ${current_price:.2f} ({c}{current_profit_pct:+.2f}%{Style.RESET_ALL}) | Max: {max_profit_pct:.2f}%")
            
            # Keep in memory
            new_csv_data.append({
                'Ticker': ticker,
                'EntryPrice': entry_price,
                'Shares': qty,
                'EntryDate': pd.Timestamp.now().strftime('%Y-%m-%d'), # Approx if missing
                'MaxPriceReached': max_price_reached
            })

    # Rewrite CSV with the True State
    if new_csv_data:
        pd.DataFrame(new_csv_data).to_csv(PORTFOLIO_FILE, index=False)
        print("Portfolio Memory Synced with Reality.")
    else:
        # If no positions, empty the file
        if os.path.exists(PORTFOLIO_FILE):
            os.remove(PORTFOLIO_FILE)
            print("Portfolio Cleared (No positions).")

if __name__ == "__main__":
    main()
