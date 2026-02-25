import os
from colorama import init, Fore, Style
from .deribit_executor import DeribitExecutor
from .utils import load_env_file

init(autoreset=True)

def nuke_portfolio():
    load_env_file()
    print(f"{Fore.RED}{'='*80}")
    print(f"!!! INITIATING EMERGENCY LIQUIDATION !!!")
    print(f"{'='*80}{Style.RESET_ALL}")
    
    bot = DeribitExecutor()
    try:
        bot.connect()
    except Exception as e:
        print(f"Connection failed: {e}")
        return

    # Fetch BOTH BTC and ETH positions
    print("Fetching all active positions...")
    positions = bot.get_all_positions(currency='BTC') + bot.get_all_positions(currency='ETH')
    
    if not positions:
        print(f"{Fore.GREEN}No open positions found. Portfolio is clean.{Style.RESET_ALL}")
    
    for pos in positions:
        instrument = pos.get('instrument_name')
        size = pos.get('size', 0)
        kind = pos.get('kind')
        
        if size == 0:
            continue
            
        # Format size correctly (Futures need Integers, Options need Floats)
        if kind == 'future':
            trade_size = int(abs(size))
        else:
            trade_size = float(abs(size))
            
        print(f"Liquidating {instrument} (Current Size: {size})")
        
        try:
            # If size is positive (Long), we Sell. If negative (Short), we Buy.
            if size > 0:
                bot.place_market_sell(instrument, trade_size)
            elif size < 0:
                bot.place_market_buy(instrument, trade_size)
            print(f"{Fore.GREEN}>>> Successfully closed {instrument}.{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.YELLOW}>>> Failed to close {instrument}: {e}{Style.RESET_ALL}")

    # Delete the corrupted state files
    print("\nCleaning state files...")
    base_dir = os.path.dirname(__file__)
    files_to_delete =[
        os.path.join(base_dir, "crypto_state.json"),
        os.path.join(base_dir, "eth_state.json")
    ]
    
    for file_path in files_to_delete:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"Deleted: {file_path}")
            
    print(f"\n{Fore.GREEN}LIQUIDATION COMPLETE. ALL SYSTEMS RESET AND READY FOR FRESH START.{Style.RESET_ALL}")

if __name__ == "__main__":
    nuke_portfolio()
