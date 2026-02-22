"""
Veritas Trader - Dynamic Hedger (The Execution Loop)
----------------------------------------------------
This daemon continuously monitors the portfolio. It identifies active Option positions,
calculates their real-time Delta using the Prime Math Engine, and automatically buys 
or short-sells the underlying stock to maintain a perfectly Delta-Neutral portfolio.
"""

import time
import re
from datetime import datetime
from colorama import init, Fore, Style
from alpaca_executor import AlpacaExecutor
from utils import load_env_file
import prime_math
import risk_manager

init(autoreset=True)

# --- CONFIGURATION ---
HEDGE_THRESHOLD = 5          # Minimum share difference required to trigger a rebalance trade
RISK_FREE_RATE = 0.045       # 4.5% Risk-Free Rate (Approximate US Treasury Yield)
SLEEP_INTERVAL = 60          # Seconds to wait between portfolio scans

def parse_occ_symbol(occ_symbol: str) -> dict:
    """
    Parses a standard OCC option symbol into its components.
    Example: SPY241220C00510000 -> SPY, 2024-12-20, Call, 510.00
    """
    # Regex to match: Ticker (up to 6 chars), Date (6 digits), Type (1 char), Strike (8 digits)
    match = re.match(r'^([A-Z]{1,6})(\d{6})([CP])(\d{8})$', occ_symbol)
    if not match:
        raise ValueError(f"Invalid OCC symbol format: {occ_symbol}")
        
    ticker = match.group(1)
    date_str = match.group(2)
    opt_type_str = match.group(3)
    strike_str = match.group(4)
    
    # Format Expiry Date
    expiry_date = datetime.strptime(date_str, "%y%m%d")
    
    # Format Option Type
    opt_type = "call" if opt_type_str == 'C' else "put"
    
    # Format Strike Price (last 3 digits are decimals in OCC standard)
    strike_price = float(strike_str) / 1000.0
    
    return {
        "underlying": ticker,
        "expiry": expiry_date,
        "type": opt_type,
        "strike": strike_price
    }

def main():
    load_env_file()
    print(f"{Fore.CYAN}{'='*80}")
    print(f"!!! VERITAS TRADER: DYNAMIC HEDGER ONLINE !!!")
    print(f"{Style.RESET_ALL}{'='*80}")
    
    # 1. Connect to Broker
    bot = AlpacaExecutor(paper_trading=True)
    try:
        bot.connect()
        print(f"{Fore.GREEN}Broker Connection Established.{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Connection Failed: {e}{Style.RESET_ALL}")
        return

    while True:
        try:
            print(f"\n--- [Hedging Cycle: {datetime.now().strftime('%H:%M:%S')}] ---")
            
            # --- RISK MANAGEMENT: TIME CHECK ---
            if not risk_manager.is_hedging_window_open():
                print(f"{Fore.YELLOW}Market Closed (Outside 4AM-8PM ET or Weekend). Hedger sleeping...{Style.RESET_ALL}")
                time.sleep(SLEEP_INTERVAL * 5) # Sleep longer when closed
                continue
            
            positions = bot.trading_client.get_all_positions()
            
            options_positions = []
            stock_positions = {}
            
            # 2. Categorize Positions
            for pos in positions:
                # Robust check for Option Asset Class (handles both Enum and String)
                if 'option' in str(pos.asset_class).lower():
                    options_positions.append(pos)
                else:
                    stock_positions[pos.symbol] = float(pos.qty)
                    
            if not options_positions:
                print(f"{Fore.YELLOW}No active options found. Waiting for Casino entry...{Style.RESET_ALL}")
                time.sleep(SLEEP_INTERVAL)
                continue
                
            # Dictionary to aggregate target stock shares per underlying ticker
            target_stock_hedges = {}

            # 3. Process Options & Calculate Required Hedges
            for opt in options_positions:
                try:
                    occ_data = parse_occ_symbol(opt.symbol)
                    underlying = occ_data["underlying"]
                    
                    # --- RISK MANAGEMENT: EXPIRATION CHECK ---
                    if risk_manager.is_expiration_danger(occ_data["expiry"]):
                        print(f"{Fore.RED}>>> DANGER: {opt.symbol} is within 48 hours of expiration! Gamma Risk too high.{Style.RESET_ALL}")
                        print(f"{Fore.RED}>>> LIQUIDATING OPTION AND HEDGE.{Style.RESET_ALL}")
                        
                        # 1. Sell the Option
                        bot.cancel_all_orders(opt.symbol)
                        bot.place_market_sell(opt.symbol, float(opt.qty))
                        
                        # 2. Liquidate the underlying stock hedge
                        bot.cancel_all_orders(underlying)
                        bot.trading_client.close_position(underlying)
                        
                        continue # Skip delta math for this option, it's dead to us
                    
                    # Get Live Prices
                    opt_market_price = float(opt.current_price)
                    
                    # We need the underlying stock price. If we hold it, we can get it from positions.
                    # Otherwise, we must fetch a quote. (Assuming AlpacaExecutor has a get_last_price method)
                    try:
                        underlying_price = float(bot.trading_client.get_position(underlying).current_price)
                    except:
                        # Fallback if we don't hold the stock yet
                        underlying_price = float(bot.get_current_price(underlying))
                        
                    # Calculate Time to Expiry (T) in years
                    days_to_expiry = (occ_data["expiry"] - datetime.now()).days
                    T = max(0.001, days_to_expiry / 365.0) # Prevent zero
                    
                    # Math Engine: Calculate IV
                    iv = prime_math.get_implied_volatility(
                        market_price=opt_market_price,
                        S=underlying_price,
                        K=occ_data["strike"],
                        T=T,
                        r=RISK_FREE_RATE,
                        option_type=occ_data["type"]
                    )
                    
                    # Math Engine: Calculate Delta
                    delta_per_share = prime_math.calculate_delta(
                        S=underlying_price,
                        K=occ_data["strike"],
                        T=T,
                        r=RISK_FREE_RATE,
                        sigma=iv,
                        option_type=occ_data["type"]
                    )
                    
                    # Calculate Position Delta
                    opt_qty = float(opt.qty) # Positive if Long, Negative if Short
                    total_position_delta = delta_per_share * 100 * opt_qty
                    
                    # Target Stock Hedge is the INVERSE of the Option Delta
                    required_stock_shares = -total_position_delta
                    
                    # Aggregate (in case we hold multiple options on the same stock)
                    target_stock_hedges[underlying] = target_stock_hedges.get(underlying, 0.0) + required_stock_shares
                    
                    print(f"OPT: {opt.symbol} | S: ${underlying_price:.2f} | IV: {iv*100:.1f}% | Delta: {delta_per_share:.3f} | Net Delta: {total_position_delta:.1f}")

                except Exception as e:
                    print(f"{Fore.RED}Error processing option {opt.symbol}: {e}{Style.RESET_ALL}")

            # 4. Execute Rebalancing Trades
            for underlying, target_qty in target_stock_hedges.items():
                target_qty = int(round(target_qty))
                current_qty = int(stock_positions.get(underlying, 0))
                
                shares_to_trade = target_qty - current_qty
                
                print(f"HEDGE [{underlying}]: Target: {target_qty} | Current: {current_qty} | Diff: {shares_to_trade}")
                
                if abs(shares_to_trade) >= HEDGE_THRESHOLD:
                    if shares_to_trade > 0:
                        print(f"{Fore.MAGENTA}>>> REBALANCING: Buying {shares_to_trade} shares of {underlying}{Style.RESET_ALL}")
                        bot.place_market_buy(underlying, shares_to_trade)
                    else:
                        print(f"{Fore.MAGENTA}>>> REBALANCING: Selling/Shorting {abs(shares_to_trade)} shares of {underlying}{Style.RESET_ALL}")
                        bot.place_market_sell(underlying, abs(shares_to_trade))
                else:
                    print(f"{Fore.GREEN}>>> {underlying} is Delta Neutral. No action required.{Style.RESET_ALL}")

            print(f"Cycle Complete. Sleeping {SLEEP_INTERVAL}s...")
            time.sleep(SLEEP_INTERVAL)

        except Exception as e:
            print(f"{Fore.RED}HEDGER ERROR: {e}{Style.RESET_ALL}")
            time.sleep(10)

if __name__ == "__main__":
    main()