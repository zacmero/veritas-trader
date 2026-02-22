import os
import pandas as pd
from .alpaca_executor import AlpacaExecutor
from .utils import load_env_file
from colorama import init, Fore, Style

init(autoreset=True)

# --- CONFIGURATION ---
BASE_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIGNALS_FILE = os.path.join(BASE_PATH, "EXECUTION_ENGINE", "actionable_signals.csv")
PORTFOLIO_FILE = os.path.join(BASE_PATH, "EXECUTION_ENGINE", "portfolio.csv")

# Alpaca Min Order is usually $1, but let's keep $5 for safety
MIN_ORDER_SIZE = 5.0 

def main():
    load_env_file()
    print(f"{Fore.YELLOW}--- [AUTO TRADER: ENTRY ENGINE (ALPACA)] ---")
    
    if not os.path.exists(SIGNALS_FILE):
        print("No signals file found. Run rank_live_signals.py first.")
        return

    signals = pd.read_csv(SIGNALS_FILE)
    if signals.empty:
        print("No signals to trade.")
        return

    # 1. Connect
    try:
        bot = AlpacaExecutor(paper_trading=True)
        bot.connect()
    except Exception as e:
        print(f"{Fore.RED}Connection failed. Check .env")
        return

    # 2. Calculate Allocation
    cash = bot.get_account_balance()
    print(f"{Fore.GREEN}Buying Power: ${cash:.2f}")
    
    num_signals = len(signals)
    if num_signals == 0: return

    allocation_per_trade = cash / num_signals
    
    print(f"Initial Calc: ${cash:.2f} / {num_signals} signals = ${allocation_per_trade:.2f}/trade")

    # If allocation is too small, drop the lowest ranked signals until it fits
    dropped = 0
    while allocation_per_trade < MIN_ORDER_SIZE and num_signals > 0:
        num_signals -= 1
        dropped += 1
        if num_signals > 0:
            allocation_per_trade = cash / num_signals
    
    if dropped > 0:
        print(f"{Fore.YELLOW}Dropped {dropped} signals due to Min Order Size (${MIN_ORDER_SIZE}).")

    if num_signals == 0:
        print(f"{Fore.RED}Insufficient funds to trade even 1 signal at ${MIN_ORDER_SIZE}.")
        return

    print(f"Trading Top {num_signals} signals at ${allocation_per_trade:.2f} each.")
    
    # 3. Execute
    new_positions = []
    
    # Iterate through the top N signals
    for i, row in signals.head(num_signals).iterrows():
        ticker = row['Ticker']
        
        # Check for existing position to prevent stacking if logic fails elsewhere
        # (Though Ranker deduplicates, we might have positions from yesterday)
        # For a simple Auto Trader, we trust the Ranker.
        
        # Execute Fractional Entry
        order_id = bot.place_fractional_entry(ticker, allocation_per_trade)
        
        if order_id:
            new_positions.append({
                'Ticker': ticker,
                'EntryPrice': 0.0, # Pending Fill
                'Shares': 0.0, # Pending Fill
                'EntryDate': pd.Timestamp.now().strftime('%Y-%m-%d'),
                'MaxPriceReached': 0.0,
                'M_List': row.get('M_List', 'N/A')
            })
            print(f"Entry Sent. Portfolio Manager Master will handle Exits.")
        else:
            print(f"{Fore.RED}Failed to place order for {ticker}")

    # 4. Update Portfolio
    if new_positions:
        if not os.path.exists(PORTFOLIO_FILE):
            pd.DataFrame(new_positions).to_csv(PORTFOLIO_FILE, index=False)
        else:
            df = pd.read_csv(PORTFOLIO_FILE)
            new_df = pd.DataFrame(new_positions)
            combined = pd.concat([df, new_df], ignore_index=True)
            combined.to_csv(PORTFOLIO_FILE, index=False)
        print(f"{Fore.GREEN}Portfolio Updated. Added {len(new_positions)} positions.")

if __name__ == "__main__":
    main()