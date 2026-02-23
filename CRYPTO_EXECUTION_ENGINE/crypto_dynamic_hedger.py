"""
Veritas Trader - Crypto Dynamic Hedger
--------------------------------------
This daemon continuously monitors the Deribit Testnet portfolio. It identifies active 
BTC Option positions, calculates their real-time Delta, and automatically buys 
or short-sells BTC-PERPETUAL futures contracts to maintain Delta Neutrality.

Implements strict Crypto Risk Management (Time Stop and Hard Equity Stop).
"""

import time
import re
import json
import os
from datetime import datetime
import pytz
from colorama import init, Fore, Style
from .deribit_executor import DeribitExecutor
from .utils import load_env_file
from .crypto_risk_manager import is_expiration_danger, check_equity_stop
from . import prime_math

init(autoreset=True)

# --- CONFIGURATION ---
SLEEP_INTERVAL = 5               # Reduced from 60s to 5s for high-frequency crypto monitoring
HEDGE_THRESHOLD_USD = 150.0      # Minimum USD imbalance required to trigger a rebalance trade
RISK_FREE_RATE = 0.045           # 4.5% Risk-Free Rate
STATE_FILE = os.path.join(os.path.dirname(__file__), "crypto_state.json")

def parse_deribit_symbol(symbol: str) -> dict:
    """
    Parses a standard Deribit option symbol into its components.
    Example: BTC-27FEB26-60000-C
    """
    match = re.match(r'^([A-Z]+)-(\d{1,2}[A-Z]{3}\d{2})-(\d+)-([CP])$', symbol)
    if not match:
        raise ValueError(f"Invalid Deribit symbol format: {symbol}")
        
    underlying = match.group(1)
    date_str = match.group(2)
    strike_str = match.group(3)
    opt_type_str = match.group(4)
    
    # Format Expiry Date
    # Deribit standard is %d%b%y (e.g., 27FEB26)
    # Options expire at 08:00:00 UTC
    expiry_date = datetime.strptime(date_str, "%d%b%y").replace(hour=8, minute=0, tzinfo=pytz.utc)
    
    # Format Option Type
    opt_type = "call" if opt_type_str == 'C' else "put"
    
    strike_price = float(strike_str)
    
    return {
        "underlying": underlying,
        "expiry": expiry_date,
        "type": opt_type,
        "strike": strike_price
    }

def main():
    load_env_file()
    print(f"{Fore.CYAN}{'='*80}")
    print(f"!!! VERITAS TRADER: CRYPTO DYNAMIC HEDGER ONLINE !!!")
    print(f"{Style.RESET_ALL}{'='*80}")
    
    bot = DeribitExecutor()
    try:
        bot.connect()
        print(f"{Fore.GREEN}Deribit Connection Established.{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Connection Failed: {e}{Style.RESET_ALL}")
        return

    while True:
        try:
            print(f"\n--- [Hedging Cycle: {datetime.now(pytz.utc).strftime('%H:%M:%S UTC')}] ---")
            
            positions = bot.get_all_positions()
            
            options_positions = []
            perp_positions = {}
            
            # Categorize Positions
            for pos in positions:
                if pos.get("kind") == "option":
                    options_positions.append(pos)
                elif pos.get("instrument_name") == "BTC-PERPETUAL":
                    perp_positions["BTC-PERPETUAL"] = float(pos.get("size", 0))
                    
            if not options_positions:
                print(f"{Fore.YELLOW}No active options found. Waiting for Crypto Casino entry...{Style.RESET_ALL}")
                time.sleep(SLEEP_INTERVAL)
                continue
                
            # Dictionary to aggregate target perp contracts (amount in USD)
            target_perp_hedges = {"BTC-PERPETUAL": 0.0}
            
            # Risk Management Tracking
            total_current_value_usd = 0.0

            # Process Options & Calculate Required Hedges
            for opt in options_positions:
                try:
                    symbol = opt["instrument_name"]
                    occ_data = parse_deribit_symbol(symbol)
                    
                    # Live Prices
                    # Deribit options are priced in BTC. Get BTC-PERPETUAL as spot proxy.
                    spot_price = bot.get_current_price("BTC-PERPETUAL")
                    opt_mark_btc = float(opt.get("mark_price", 0))
                    opt_qty = float(opt.get("size", 0)) # In BTC
                    
                    if spot_price == 0:
                        raise ValueError(f"Spot price is 0 for {symbol}")

                    opt_value_usd = opt_mark_btc * spot_price * opt_qty
                    total_current_value_usd += opt_value_usd

                    # --- RISK MANAGEMENT: EXPIRATION CHECK ---
                    if is_expiration_danger(occ_data["expiry"]):
                        print(f"{Fore.RED}>>> TIME STOP DANGER: {symbol} is within 48 hours of expiration! Gamma Risk too high.{Style.RESET_ALL}")
                        print(f"{Fore.RED}>>> LIQUIDATING OPTION AND HEDGE.{Style.RESET_ALL}")
                        
                        # 1. Sell Option
                        bot.place_market_sell(symbol, opt_qty)
                        
                        # 2. Liquidate Hedge
                        current_perp = perp_positions.get("BTC-PERPETUAL", 0.0)
                        if current_perp > 0:
                            bot.place_market_sell("BTC-PERPETUAL", abs(current_perp))
                        elif current_perp < 0:
                            bot.place_market_buy("BTC-PERPETUAL", abs(current_perp))
                            
                        # Delete state file to reset
                        if os.path.exists(STATE_FILE):
                            os.remove(STATE_FILE)
                            
                        print(f"{Fore.RED}>>> LIQUIDATION COMPLETE. SHUTTING DOWN.{Style.RESET_ALL}")
                        return 
                    
                    # Calculate Time to Expiry (T) in years
                    days_to_expiry = (occ_data["expiry"] - datetime.now(pytz.utc)).days
                    T = max(0.001, days_to_expiry / 365.0) 
                    
                    # Math Engine
                    iv = prime_math.get_implied_volatility(
                        market_price=opt_mark_btc * spot_price, # USD representation
                        S=spot_price,
                        K=occ_data["strike"],
                        T=T,
                        r=RISK_FREE_RATE,
                        option_type=occ_data["type"]
                    )
                    
                    delta_per_btc = prime_math.calculate_delta(
                        S=spot_price,
                        K=occ_data["strike"],
                        T=T,
                        r=RISK_FREE_RATE,
                        sigma=iv,
                        option_type=occ_data["type"]
                    )
                    
                    # Total Position Delta in BTC
                    total_position_delta_btc = delta_per_btc * opt_qty
                    
                    # Target BTC-PERPETUAL Hedge: Inverse of the Option Delta
                    # Deribit BTC-PERPETUAL contracts are sized in USD (1 contract = $10 USD)
                    # We need to short `total_position_delta_btc` amount of BTC.
                    # USD Value of Delta = total_position_delta_btc * spot_price
                    # Contracts = USD Value / 10
                    # Note: Deribit API `amount` parameter for BTC-PERPETUAL is typically in USD (e.g. 100 means $100).
                    # We will request the amount in USD directly if that's what API expects.
                    # Wait, standard Deribit BTC-PERPETUAL amount is in USD: e.g. amount=100 is 10 contracts of $10 each.
                    # So the required amount to trade is the exact USD value of the delta!
                    required_usd_short = - (total_position_delta_btc * spot_price)
                    
                    target_perp_hedges["BTC-PERPETUAL"] += required_usd_short
                    
                    print(f"OPT: {symbol} | S: ${spot_price:.2f} | IV: {iv*100:.1f}% | Delta (BTC): {delta_per_btc:.3f} | Net Delta (BTC): {total_position_delta_btc:.3f}")

                except Exception as e:
                    print(f"{Fore.RED}Error processing option {opt.get('instrument_name', 'Unknown')}: {e}{Style.RESET_ALL}")

            # Calculate Hedge PnL for Equity Stop
            for pos in positions:
                if pos.get("instrument_name") == "BTC-PERPETUAL":
                    # For inverse contracts, PnL is in BTC. We convert to USD
                    pnl_btc = float(pos.get("floating_profit_loss", 0))
                    total_current_value_usd += (pnl_btc * spot_price)
            
            # --- RISK MANAGEMENT: HARD EQUITY STOP ---
            if os.path.exists(STATE_FILE):
                try:
                    with open(STATE_FILE, "r") as f:
                        state = json.load(f)
                        initial_cost = state.get("initial_cost_usd", 0)
                        
                    if initial_cost > 0:
                        if check_equity_stop(initial_cost, total_current_value_usd):
                            drawdown = ((total_current_value_usd - initial_cost) / initial_cost) * 100
                            print(f"{Fore.RED}>>> HARD EQUITY STOP TRIGGERED! Drawdown: {drawdown:.2f}% (Limit: -15%){Style.RESET_ALL}")
                            print(f"{Fore.RED}>>> LIQUIDATING PORTFOLIO.{Style.RESET_ALL}")
                            
                            # Liquidate Options
                            for opt in options_positions:
                                bot.place_market_sell(opt["instrument_name"], float(opt.get("size", 0)))
                            
                            # Liquidate Hedge
                            current_perp = perp_positions.get("BTC-PERPETUAL", 0.0)
                            if current_perp > 0:
                                bot.place_market_sell("BTC-PERPETUAL", abs(current_perp))
                            elif current_perp < 0:
                                bot.place_market_buy("BTC-PERPETUAL", abs(current_perp))
                                
                            os.remove(STATE_FILE)
                            print(f"{Fore.RED}>>> LIQUIDATION COMPLETE. SHUTTING DOWN.{Style.RESET_ALL}")
                            return
                        else:
                            drawdown = ((total_current_value_usd - initial_cost) / initial_cost) * 100
                            print(f"Total Portfolio Value: ${total_current_value_usd:.2f} | Initial Cost: ${initial_cost:.2f} | Drawdown: {drawdown:.2f}%")
                except Exception as e:
                    print(f"Error checking Equity Stop: {e}")

            # Execute Rebalancing Trades
            for underlying, target_usd in target_perp_hedges.items():
                # Deribit BTC-PERPETUAL contracts are in increments of $10 USD.
                # We round to the nearest $10.
                target_usd = round(target_usd / 10.0) * 10.0
                current_usd = float(perp_positions.get(underlying, 0.0))
                
                usd_to_trade = target_usd - current_usd
                
                print(f"HEDGE [{underlying}]: Target USD: {target_usd} | Current USD: {current_usd} | Diff: {usd_to_trade}")
                
                # Only trade if the imbalance is larger than our fee-safe threshold
                if abs(usd_to_trade) >= HEDGE_THRESHOLD_USD:
                    if usd_to_trade > 0:
                        print(f"{Fore.MAGENTA}>>> REBALANCING: Buying {usd_to_trade} USD of {underlying}{Style.RESET_ALL}")
                        bot.place_market_buy(underlying, usd_to_trade)
                    else:
                        print(f"{Fore.MAGENTA}>>> REBALANCING: Selling/Shorting {abs(usd_to_trade)} USD of {underlying}{Style.RESET_ALL}")
                        bot.place_market_sell(underlying, abs(usd_to_trade))
                else:
                    print(f"{Fore.GREEN}>>> Delta Neutral (Imbalance ${abs(usd_to_trade)} is below ${HEDGE_THRESHOLD_USD} threshold). No action required.{Style.RESET_ALL}")

            print(f"Cycle Complete. Sleeping {SLEEP_INTERVAL}s...")
            time.sleep(SLEEP_INTERVAL)

        except Exception as e:
            print(f"{Fore.RED}HEDGER ERROR: {e}{Style.RESET_ALL}")
            time.sleep(10)

if __name__ == "__main__":
    main()