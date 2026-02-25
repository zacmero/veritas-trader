"""
Veritas Trader - Crypto Dynamic Hedger
--------------------------------------
This daemon continuously monitors the Deribit Testnet portfolio. It identifies active 
ETH Option positions, calculates their real-time Delta, and automatically buys 
or short-sells ETH-PERPETUAL futures contracts to maintain Delta Neutrality.

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
SLEEP_INTERVAL = 5
DELTA_BAND = 0.02  # Rebalance if Net Delta strays beyond +/- 0.02
RISK_FREE_RATE = 0.045
STATE_FILE = os.path.join(os.path.dirname(__file__), "eth_state.json")

def parse_deribit_symbol(symbol: str) -> dict:
    """
    Parses a standard Deribit option symbol into its components.
    Example: ETH-27FEB26-60000-C
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
    print(f"!!! VERITAS TRADER: ETH DYNAMIC HEDGER ONLINE !!!")
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
            
            positions = bot.get_all_positions(currency='ETH')
            
            options_positions = []
            perp_positions = {}
            
            # Categorize Positions
            for pos in positions:
                if pos.get("kind") == "option":
                    options_positions.append(pos)
                elif pos.get("instrument_name") == "ETH-PERPETUAL":
                    perp_positions["ETH-PERPETUAL"] = float(pos.get("size", 0))
                    
            if not options_positions:
                print(f"{Fore.YELLOW}No active options found. Waiting for ETH Casino entry...{Style.RESET_ALL}")
                time.sleep(SLEEP_INTERVAL)
                continue
                
            # Dictionary to aggregate target perp contracts (amount in USD)
            target_perp_hedges = {"ETH-PERPETUAL": 0.0}
            
            # Risk Management Tracking
            total_current_value_usd = 0.0
            
            portfolio_delta_coin = 0.0  # Accumulator for all options

            # Process Options & Calculate Required Hedges
            for opt in options_positions:
                try:
                    symbol = opt["instrument_name"]
                    occ_data = parse_deribit_symbol(symbol)
                    
                    # Live Prices
                    # Deribit options are priced in ETH. Get ETH-PERPETUAL as spot proxy.
                    spot_price = bot.get_current_price("ETH-PERPETUAL")
                    opt_mark_eth = float(opt.get("mark_price", 0))
                    opt_qty = float(opt.get("size", 0)) # In ETH
                    
                    if spot_price == 0:
                        raise ValueError(f"Spot price is 0 for {symbol}")

                    opt_value_usd = opt_mark_eth * spot_price * opt_qty
                    total_current_value_usd += opt_value_usd

                    # --- RISK MANAGEMENT: EXPIRATION CHECK ---
                    if is_expiration_danger(occ_data["expiry"]):
                        print(f"{Fore.RED}>>> TIME STOP DANGER: {symbol} is within 48 hours of expiration! Gamma Risk too high.{Style.RESET_ALL}")
                        print(f"{Fore.RED}>>> LIQUIDATING OPTION AND HEDGE.{Style.RESET_ALL}")
                        
                        # 1. Sell Option
                        bot.place_market_sell(symbol, opt_qty)
                        
                        # 2. Liquidate Hedge
                        current_perp = int(perp_positions.get("ETH-PERPETUAL", 0.0))
                        if current_perp > 0:
                            bot.place_market_sell("ETH-PERPETUAL", int(abs(current_perp)))
                        elif current_perp < 0:
                            bot.place_market_buy("ETH-PERPETUAL", int(abs(current_perp)))
                            
                        # Delete state file to reset
                        if os.path.exists(STATE_FILE):
                            os.remove(STATE_FILE)
                            
                        print(f"{Fore.RED}>>> LIQUIDATION COMPLETE. SHUTTING DOWN.{Style.RESET_ALL}")
                        return 
                    
                    # Calculate Time to Expiry (T) accurately using seconds
                    seconds_to_expiry = (occ_data["expiry"] - datetime.now(pytz.utc)).total_seconds()
                    days_to_expiry = seconds_to_expiry / (24 * 3600)
                    T = max(1.0 / 3650.0, seconds_to_expiry / (365.0 * 24 * 3600)) # Prevent zero
                    
                    # Use Deribit's native Greeks if available, otherwise fallback to prime_math
                    greeks = opt.get("greeks", {})
                    if "delta" in greeks and "mark_iv" in opt:
                        delta_per_coin = float(greeks["delta"])
                        iv = float(opt["mark_iv"]) / 100.0
                    else:
                        iv = prime_math.get_implied_volatility(
                            market_price=opt_mark_eth * spot_price,
                            S=spot_price, K=occ_data["strike"], T=T, r=RISK_FREE_RATE, option_type=occ_data["type"]
                        )
                        delta_per_coin = prime_math.calculate_delta(
                            S=spot_price, K=occ_data["strike"], T=T, r=RISK_FREE_RATE, sigma=iv, option_type=occ_data["type"]
                        )
                    
                    # Add to Portfolio Delta
                    position_delta = delta_per_coin * opt_qty
                    portfolio_delta_coin += position_delta
                    
                    # Visual Countdown
                    time_color = Fore.GREEN if days_to_expiry > 10 else (Fore.YELLOW if days_to_expiry > 3 else Fore.RED)
                    expiry_str = f"{time_color}[T-Minus: {days_to_expiry:.2f} Days]{Style.RESET_ALL}"
                    print(f"OPT: {symbol} {expiry_str} | S: ${spot_price:.2f} | IV: {iv*100:.1f}% | Pos Delta: {position_delta:.3f}")

                except Exception as e:
                    print(f"{Fore.RED}Error processing option {opt.get('instrument_name', 'Unknown')}: {e}{Style.RESET_ALL}")

            # Calculate Hedge PnL for Equity Stop
            for pos in positions:
                if pos.get("instrument_name") == "ETH-PERPETUAL":
                    # For inverse contracts, PnL is in ETH. We convert to USD
                    pnl_eth = float(pos.get("floating_profit_loss", 0))
                    total_current_value_usd += (pnl_eth * spot_price)
            
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
                            current_perp = int(perp_positions.get("ETH-PERPETUAL", 0.0))
                            if current_perp > 0:
                                bot.place_market_sell("ETH-PERPETUAL", int(abs(current_perp)))
                            elif current_perp < 0:
                                bot.place_market_buy("ETH-PERPETUAL", int(abs(current_perp)))
                                
                            os.remove(STATE_FILE)
                            print(f"{Fore.RED}>>> LIQUIDATION COMPLETE. SHUTTING DOWN.{Style.RESET_ALL}")
                            return
                        else:
                            drawdown = ((total_current_value_usd - initial_cost) / initial_cost) * 100
                            print(f"Total Portfolio Value: ${total_current_value_usd:.2f} | Initial Cost: ${initial_cost:.2f} | Drawdown: {drawdown:.2f}%")
                except Exception as e:
                    print(f"Error checking Equity Stop: {e}")

            # --- CALCULATE TRUE NET DELTA ---
            # Get current hedge delta
            perp_symbol = "ETH-PERPETUAL"
            current_hedge_usd = float(perp_positions.get(perp_symbol, 0.0))
            hedge_delta_coin = current_hedge_usd / spot_price
            
            true_net_delta = portfolio_delta_coin + hedge_delta_coin
            print(f"\n{Fore.CYAN}=== PORTFOLIO STATE ==={Style.RESET_ALL}")
            print(f"Options Delta: {portfolio_delta_coin:.4f} | Hedge Delta: {hedge_delta_coin:.4f} | TRUE NET DELTA: {true_net_delta:.4f}")
            
            # --- EXECUTE REBALANCING (DELTA BAND) ---
            if abs(true_net_delta) >= DELTA_BAND:
                # 1. Cancel any hanging unfilled orders from the last cycle
                bot.cancel_all_orders(perp_symbol)
                
                # We need to trade enough USD to bring true_net_delta back to 0
                # If net delta is +0.05, we need to short 0.05 coins.
                coin_to_trade = -true_net_delta
                usd_to_trade = coin_to_trade * spot_price
                
                # Round to nearest contract size ($1.0 for ETH)
                contract_size = 1.0
                trade_amount_usd = int(round(usd_to_trade / contract_size) * contract_size)
                
                if trade_amount_usd != 0:
                    # Use Limit Orders at the current spot_price to capture Maker fees (0.00%)
                    # Deribit ETH tick size is $0.05
                    limit_price = round(spot_price * 20) / 20.0
                    
                    if trade_amount_usd > 0:
                        print(f"{Fore.MAGENTA}>>> REBALANCING: LIMIT BUY {trade_amount_usd} USD of {perp_symbol} @ ${limit_price}{Style.RESET_ALL}")
                        bot.place_limit_buy(perp_symbol, trade_amount_usd, limit_price)
                    else:
                        print(f"{Fore.MAGENTA}>>> REBALANCING: LIMIT SELL {abs(trade_amount_usd)} USD of {perp_symbol} @ ${limit_price}{Style.RESET_ALL}")
                        bot.place_limit_sell(perp_symbol, abs(trade_amount_usd), limit_price)
                        
                    # --- POST-TRADE CONFIRMATION LOG ---
                    # Calculate projected state after order fills
                    new_hedge_usd = current_hedge_usd + trade_amount_usd
                    projected_hedge_delta = new_hedge_usd / spot_price
                    projected_net_delta = portfolio_delta_coin + projected_hedge_delta
                    print(f"{Fore.CYAN}>>> POST-TRADE PROJECTION | Hedge Delta: {projected_hedge_delta:.3f} | TRUE NET DELTA: {projected_net_delta:.3f}{Style.RESET_ALL}")
            else:
                print(f"{Fore.GREEN}>>> Delta Neutral (Net Delta {abs(true_net_delta):.4f} is within {DELTA_BAND} band). No action required.{Style.RESET_ALL}")

            print(f"Cycle Complete. Sleeping {SLEEP_INTERVAL}s...")
            time.sleep(SLEEP_INTERVAL)

        except Exception as e:
            print(f"{Fore.RED}HEDGER ERROR: {e}{Style.RESET_ALL}")
            time.sleep(10)

if __name__ == "__main__":
    main()