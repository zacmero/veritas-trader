"""
Veritas Trader - Casino Entry (Gamma Scalp Initiator)
-----------------------------------------------------
This script initiates the strategy. It scans the options chain for a highly liquid 
ETF (e.g., SPY), finds an At-The-Money (ATM) Call option expiring in ~30 days, 
and purchases it. 

Once purchased, the `dynamic_hedger.py` daemon will automatically detect it 
and begin shorting the underlying stock to Delta-Hedge the position.
"""

import time
from datetime import datetime, timedelta
from colorama import init, Fore, Style
from alpaca_executor import AlpacaExecutor
from utils import load_env_file
from alpaca.trading.requests import GetOptionContractsRequest
from alpaca.trading.enums import ContractType

init(autoreset=True)

# --- CONFIGURATION ---
TARGET_ETF = "SPY"
TARGET_DAYS_TO_EXPIRY = 30
CONTRACTS_TO_BUY = 1

def main():
    load_env_file()
    print(f"{Fore.CYAN}{'='*80}")
    print(f"!!! VERITAS TRADER: CASINO ENTRY ONLINE !!!")
    print(f"{Style.RESET_ALL}{'='*80}")
    
    bot = AlpacaExecutor(paper_trading=True)
    try:
        bot.connect()
    except Exception as e:
        print(f"{Fore.RED}Connection Failed: {e}{Style.RESET_ALL}")
        return

    print(f"Targeting Asset: {TARGET_ETF}")
    
    # 1. Get Current Stock Price
    try:
        current_price = float(bot.get_current_price(TARGET_ETF))
        print(f"Current {TARGET_ETF} Price: ${current_price:.2f}")
    except Exception as e:
        print(f"{Fore.RED}Failed to fetch underlying price: {e}{Style.RESET_ALL}")
        return

    # 2. Calculate Target Expiration Date
    target_date = datetime.now() + timedelta(days=TARGET_DAYS_TO_EXPIRY)
    
    # 3. Fetch Option Chain from Alpaca
    print(f"Fetching Option Chain for {TARGET_ETF}...")
    req = GetOptionContractsRequest(
        underlying_symbols=[TARGET_ETF],
        status="active",
        type=ContractType.CALL
    )
    
    try:
        contracts = bot.trading_client.get_option_contracts(req)
        if not contracts.option_contracts:
            print(f"{Fore.RED}No contracts found for {TARGET_ETF}.{Style.RESET_ALL}")
            return
    except Exception as e:
        print(f"{Fore.RED}Failed to fetch option contracts: {e}{Style.RESET_ALL}")
        return

    # 4. Filter for the closest ATM (At-The-Money) strike and closest Expiry
    best_contract = None
    smallest_price_diff = float('inf')
    smallest_date_diff = float('inf')

    for contract in contracts.option_contracts:
        # Alpaca returns expiration_date as string 'YYYY-MM-DD'
        exp_date = datetime.strptime(contract.expiration_date, "%Y-%m-%d")
        date_diff = abs((exp_date - target_date).days)
        
        strike = float(contract.strike_price)
        price_diff = abs(strike - current_price)
        
        # We want the date to be as close to 30 days as possible, 
        # and the strike to be as close to the current price as possible.
        if date_diff <= smallest_date_diff + 2: # Allow a 2-day variance for expiry
            if price_diff < smallest_price_diff:
                smallest_price_diff = price_diff
                smallest_date_diff = date_diff
                best_contract = contract

    if not best_contract:
        print(f"{Fore.RED}Could not find a suitable ATM contract.{Style.RESET_ALL}")
        return

    print(f"\n{Fore.GREEN}>>> TARGET ACQUIRED <<<{Style.RESET_ALL}")
    print(f"Symbol: {best_contract.symbol}")
    print(f"Strike: ${best_contract.strike_price}")
    print(f"Expiry: {best_contract.expiration_date}")
    
    # 5. Execute the Purchase
    print(f"\nInitiating Gamma Scalp. Buying {CONTRACTS_TO_BUY} contract(s)...")
    
    # Note: Assuming AlpacaExecutor has a method to place option orders. 
    # If not, using standard market buy logic.
    success, filled_price = bot.place_market_buy(best_contract.symbol, CONTRACTS_TO_BUY)
    
    if success:
        print(f"{Fore.GREEN}SUCCESS! Option purchased at ~${filled_price}.{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}The Dynamic Hedger will now detect this position and begin shorting {TARGET_ETF} to neutralize Delta.{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}Failed to execute option purchase.{Style.RESET_ALL}")

if __name__ == "__main__":
    main()