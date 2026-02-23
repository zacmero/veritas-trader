"""
Veritas Trader - Casino Entry (Gamma Scalp Initiator)
-----------------------------------------------------
This script initiates the strategy. It scans the options chain for a highly liquid 
ETF (e.g., SPY, SPLG), finds an At-The-Money (ATM) Call option expiring in ~30 days, 
and purchases it. 

Once purchased, the `dynamic_hedger.py` daemon will automatically detect it 
and begin shorting the underlying stock to Delta-Hedge the position.
"""

import time
from datetime import datetime, timedelta
from colorama import init, Fore, Style
from .alpaca_executor import AlpacaExecutor
from .utils import load_env_file
from .risk_manager import get_eastern_time
from alpaca.trading.requests import GetOptionContractsRequest
from alpaca.trading.enums import ContractType

init(autoreset=True)

# --- CONFIGURATION ---
# The system will attempt to enter the first available, liquid ETF in this list.
# RSP is equal-weight S&P 500 (~$170), XLF is Financials (~$40), IWM is Russell 2000 (~$220).
TARGET_ETFS = ["XLF", "QQQ", "IWM", "DIA", "RSP", "SPY"]
TARGET_DAYS_TO_EXPIRY = 30
CONTRACTS_TO_BUY = 1

def main():
    load_env_file()
    print(f"{Fore.CYAN}{'='*80}")
    print(f"!!! VERITAS TRADER: CASINO ENTRY ONLINE !!!")
    print(f"{Style.RESET_ALL}{'='*80}")

    # --- WAIT FOR MARKET HOURS (9:35 AM - 3:55 PM ET) ---
    while True:
        et_now = get_eastern_time()
        # 0 = Monday, 4 = Friday
        if et_now.weekday() < 5:
            # 9:35 AM = 9*60 + 35 = 575
            # 3:55 PM = 15*60 + 55 = 955
            current_minutes = et_now.hour * 60 + et_now.minute
            if 575 <= current_minutes <= 955:
                print(f"{Fore.GREEN}Market is within stable hours ({et_now.strftime('%H:%M:%S')} ET). Proceeding with entry...{Style.RESET_ALL}")
                break
        
        print(f"{Fore.YELLOW}Waiting for stable market hours (9:35 AM - 3:55 PM ET). Current: {et_now.strftime('%H:%M:%S')} ET. Sleeping 60s...{Style.RESET_ALL}")
        time.sleep(60)
    
    bot = AlpacaExecutor(paper_trading=True)
    try:
        bot.connect()
    except Exception as e:
        print(f"{Fore.RED}Connection Failed: {e}{Style.RESET_ALL}")
        return

    # Loop through our target list, stopping as soon as one purchase succeeds.
    for target_etf in TARGET_ETFS:
        print(f"\n{Fore.CYAN}--- Evaluating Target Asset: {target_etf} ---{Style.RESET_ALL}")
        
        # 1. Get Current Stock Price
        try:
            current_price = float(bot.get_current_price(target_etf))
            print(f"Current {target_etf} Price: ${current_price:.2f}")
        except Exception as e:
            print(f"{Fore.YELLOW}Failed to fetch underlying price for {target_etf}: {e}. Skipping...{Style.RESET_ALL}")
            continue

        # 2. Calculate Target Expiration Date
        target_date = datetime.now() + timedelta(days=TARGET_DAYS_TO_EXPIRY)
        
        # 3. Fetch Option Chain from Alpaca
        print(f"Fetching Option Chain for {target_etf}...")
        req = GetOptionContractsRequest(
            underlying_symbols=[target_etf],
            status="active",
            type=ContractType.CALL
        )
        
        try:
            contracts = bot.trading_client.get_option_contracts(req)
            if not contracts.option_contracts:
                print(f"{Fore.YELLOW}No active option contracts found for {target_etf}. Skipping...{Style.RESET_ALL}")
                continue
        except Exception as e:
            # Catch "invalid underlying symbols" (like SPLG) without crashing
            print(f"{Fore.YELLOW}Alpaca rejected option query for {target_etf}: {e}. Skipping...{Style.RESET_ALL}")
            continue

        # 4. Filter for the closest ATM (At-The-Money) strike and closest Expiry
        # First, find the minimum date difference across all contracts
        try:
            min_date_diff = min(abs((c.expiration_date - target_date.date()).days) for c in contracts.option_contracts)
        except ValueError:
            print(f"{Fore.YELLOW}Error calculating expiration dates for {target_etf}. Skipping...{Style.RESET_ALL}")
            continue
        
        # Filter contracts that are within 2 days of this optimal date
        valid_contracts = [c for c in contracts.option_contracts if abs((c.expiration_date - target_date.date()).days) <= min_date_diff + 2]
        
        # Out of these, find the one with the strike price closest to current price
        best_contract = None
        smallest_price_diff = float('inf')

        for contract in valid_contracts:
            strike = float(contract.strike_price)
            price_diff = abs(strike - current_price)
            
            if price_diff < smallest_price_diff:
                smallest_price_diff = price_diff
                best_contract = contract

        if not best_contract:
            print(f"{Fore.YELLOW}Could not find a suitable ATM contract for {target_etf}. Skipping...{Style.RESET_ALL}")
            continue

        print(f"\n{Fore.GREEN}>>> TARGET ACQUIRED <<<{Style.RESET_ALL}")
        print(f"Symbol: {best_contract.symbol}")
        print(f"Strike: ${best_contract.strike_price}")
        print(f"Expiry: {best_contract.expiration_date}")
        
        # 5. Execute the Purchase
        print(f"\nInitiating Gamma Scalp. Buying {CONTRACTS_TO_BUY} contract(s)...")
        
        success, filled_price = bot.place_market_buy(best_contract.symbol, CONTRACTS_TO_BUY)
        
        if success:
            print(f"{Fore.GREEN}SUCCESS! Option purchased at ~${filled_price}.{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}The Dynamic Hedger will now detect this position and begin shorting {target_etf} to neutralize Delta.{Style.RESET_ALL}")
            return # EXIT THE SCRIPT - WE ONLY WANT ONE CASINO ENTRY AT A TIME
        else:
            print(f"{Fore.RED}Failed to execute option purchase for {target_etf}. Will try next target...{Style.RESET_ALL}")

    print(f"\n{Fore.RED}Exhausted all targets in TARGET_ETFS list. No entry made.{Style.RESET_ALL}")

if __name__ == "__main__":
    main()