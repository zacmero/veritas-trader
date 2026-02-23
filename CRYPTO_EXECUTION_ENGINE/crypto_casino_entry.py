"""
Veritas Trader - Crypto Casino Entry
------------------------------------
Initiates a Gamma Scalping campaign on the Deribit Testnet using BTC Options.
Finds an ATM Call expiring in ~30 days, checks the Volatility Stop (IV Crush Risk),
buys 0.1 BTC contracts, and saves the initial cost state for the Hard Equity Stop.
"""

import time
import json
import os
import requests
from datetime import datetime, timedelta
import pytz
from colorama import init, Fore, Style
from .deribit_executor import DeribitExecutor
from .utils import load_env_file
from .crypto_risk_manager import is_iv_too_high
from . import prime_math

init(autoreset=True)

# --- CONFIGURATION ---
TARGET_DAYS_TO_EXPIRY = 30
CONTRACTS_TO_BUY = 0.1 # BTC
RISK_FREE_RATE = 0.045
STATE_FILE = os.path.join(os.path.dirname(__file__), "crypto_state.json")

def main():
    load_env_file()
    print(f"{Fore.CYAN}{'='*80}")
    print(f"!!! VERITAS TRADER: CRYPTO CASINO ENTRY ONLINE !!!")
    print(f"{Style.RESET_ALL}{'='*80}")

    bot = DeribitExecutor()
    try:
        bot.connect()
    except Exception as e:
        print(f"{Fore.RED}Connection Failed: {e}{Style.RESET_ALL}")
        return

    # 1. Get Current Spot Price (We use BTC-PERPETUAL or index price as spot proxy)
    try:
        # Fetching index price for BTC
        current_price = bot.get_current_price("BTC-PERPETUAL")
        if current_price == 0:
            raise Exception("Failed to get BTC-PERPETUAL price.")
        print(f"Current BTC Spot Proxy (BTC-PERPETUAL) Price: ${current_price:.2f}")
    except Exception as e:
        print(f"{Fore.RED}Failed to fetch underlying price: {e}{Style.RESET_ALL}")
        return

    # 2. Fetch Option Chain from Deribit
    print("Fetching BTC Option Chain...")
    try:
        # Deribit public API for active options
        url = f"{bot.base_url}/public/get_instruments"
        params = {"currency": "BTC", "kind": "option", "expired": "false"}
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if "result" not in data:
            print(f"{Fore.RED}No options found.{Style.RESET_ALL}")
            return
        instruments = data["result"]
    except Exception as e:
        print(f"{Fore.RED}Failed to fetch option contracts: {e}{Style.RESET_ALL}")
        return

    target_date = datetime.now(pytz.utc) + timedelta(days=TARGET_DAYS_TO_EXPIRY)

    best_contract = None
    smallest_price_diff = float('inf')
    
    # 3. Filter for Call options and finding the best match
    call_options = [inst for inst in instruments if inst["option_type"] == "call"]
    
    # Calculate min date diff
    try:
        min_date_diff = min(abs((datetime.fromtimestamp(c["creation_timestamp"]/1000 + c["expiration_timestamp"]/1000 - c["creation_timestamp"]/1000, pytz.utc) - target_date).days) for c in call_options)
        # Actually Deribit has expiration_timestamp in milliseconds
        min_date_diff = min(abs((datetime.fromtimestamp(c["expiration_timestamp"]/1000, pytz.utc) - target_date).days) for c in call_options)
    except Exception as e:
        print(f"Error calculating dates: {e}")
        return

    valid_contracts = [c for c in call_options if abs((datetime.fromtimestamp(c["expiration_timestamp"]/1000, pytz.utc) - target_date).days) <= min_date_diff + 2]

    for contract in valid_contracts:
        strike = float(contract["strike"])
        price_diff = abs(strike - current_price)
        
        if price_diff < smallest_price_diff:
            smallest_price_diff = price_diff
            best_contract = contract

    if not best_contract:
        print(f"{Fore.RED}Could not find a suitable ATM contract.{Style.RESET_ALL}")
        return

    print(f"\n{Fore.GREEN}>>> TARGET ACQUIRED <<<{Style.RESET_ALL}")
    print(f"Instrument: {best_contract['instrument_name']}")
    print(f"Strike: ${best_contract['strike']}")
    expiry = datetime.fromtimestamp(best_contract["expiration_timestamp"]/1000, pytz.utc)
    print(f"Expiry: {expiry.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    # 4. Volatility Stop Check
    opt_price_btc = bot.get_current_price(best_contract["instrument_name"])
    # Deribit prices options in BTC, so multiply by current_price for USD value
    opt_market_price_usd = opt_price_btc * current_price 
    
    T = max(0.001, (expiry - datetime.now(pytz.utc)).days / 365.0)

    iv = prime_math.get_implied_volatility(
        market_price=opt_market_price_usd,
        S=current_price,
        K=float(best_contract["strike"]),
        T=T,
        r=RISK_FREE_RATE,
        option_type="call"
    )

    print(f"Calculated IV: {iv*100:.2f}%")
    
    if is_iv_too_high(iv):
        print(f"{Fore.RED}VOLATILITY STOP ACTIVATED: IV ({iv*100:.2f}%) exceeds maximum allowed ({MAX_ENTRY_IV*100:.2f}%). Aborting entry to avoid IV Crush.{Style.RESET_ALL}")
        return
        
    print(f"{Fore.GREEN}IV is acceptable. Proceeding...{Style.RESET_ALL}")

    # 5. Execute the Purchase
    print(f"\nInitiating Gamma Scalp. Buying {CONTRACTS_TO_BUY} BTC contracts of {best_contract['instrument_name']}...")
    success, filled_price_btc = bot.place_market_buy(best_contract['instrument_name'], CONTRACTS_TO_BUY)
    
    if success:
        initial_cost_usd = filled_price_btc * current_price * CONTRACTS_TO_BUY
        print(f"{Fore.GREEN}SUCCESS! Option purchased at ~{filled_price_btc} BTC (${initial_cost_usd:.2f} USD).{Style.RESET_ALL}")
        
        # 6. Save State
        state = {
            "instrument": best_contract["instrument_name"],
            "entry_time": datetime.now(pytz.utc).isoformat(),
            "initial_cost_usd": initial_cost_usd,
            "contracts": CONTRACTS_TO_BUY
        }
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=4)
            
        print(f"{Fore.YELLOW}Saved initial cost state for Hard Equity Stop tracking.{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}The Crypto Dynamic Hedger will now detect this position and begin shorting BTC-PERPETUAL to neutralize Delta.{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}Failed to execute option purchase.{Style.RESET_ALL}")

if __name__ == "__main__":
    main()