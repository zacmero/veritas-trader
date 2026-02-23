"""
Veritas Trader - Crypto Investment Reporter
-------------------------------------------
Generates a clean, human-readable terminal report of Gamma Scalping performance
on the Deribit Testnet.
"""

import os
import json
from colorama import init, Fore, Style
from tabulate import tabulate
from .deribit_executor import DeribitExecutor
from .utils import load_env_file

init(autoreset=True)

STATE_FILE = os.path.join(os.path.dirname(__file__), "crypto_state.json")

def format_usd(value: float) -> str:
    """Formats a float as a USD string with correct coloring for P/L."""
    if value >= 0:
        return f"{Fore.GREEN}+${value:,.2f}{Style.RESET_ALL}"
    else:
        return f"{Fore.RED}-${abs(value):,.2f}{Style.RESET_ALL}"

def main():
    load_env_file()
    
    bot = DeribitExecutor()
    try:
        bot.connect()
    except Exception as e:
        print(f"{Fore.RED}Connection Failed: {e}{Style.RESET_ALL}")
        return

    # 1. Fetch Account Summary and Spot Price
    account = bot.get_account_summary(currency="BTC")
    spot_price = bot.get_current_price("BTC-PERPETUAL")
    
    if not account or spot_price == 0:
        print(f"{Fore.RED}Failed to fetch account or spot price data.{Style.RESET_ALL}")
        return

    equity_btc = account.get("equity", 0.0)
    equity_usd = equity_btc * spot_price

    # 2. Fetch Positions
    positions = bot.get_all_positions()
    
    options_positions = []
    perp_position = None
    
    for pos in positions:
        if pos.get("kind") == "option":
            options_positions.append(pos)
        elif pos.get("instrument_name") == "BTC-PERPETUAL":
            perp_position = pos

    # 3. Process Option Data
    opt_table = []
    total_opt_unrealized_usd = 0.0
    
    for opt in options_positions:
        symbol = opt["instrument_name"]
        size = float(opt.get("size", 0.0))
        
        # Prices in BTC, convert to USD
        avg_price_btc = float(opt.get("average_price", 0.0))
        mark_price_btc = float(opt.get("mark_price", 0.0))
        unrealized_btc = float(opt.get("floating_profit_loss", 0.0))
        
        entry_price_usd = avg_price_btc * spot_price
        curr_price_usd = mark_price_btc * spot_price
        unrealized_usd = unrealized_btc * spot_price
        
        total_opt_unrealized_usd += unrealized_usd
        
        opt_table.append([
            symbol,
            f"{size} BTC",
            f"${entry_price_usd:.2f}",
            f"${curr_price_usd:.2f}",
            format_usd(unrealized_usd)
        ])

    # 4. Process Hedge (BTC-PERPETUAL) Data
    hedge_table = []
    total_hedge_realized_usd = 0.0
    total_hedge_unrealized_usd = 0.0
    
    if perp_position:
        size_usd = float(perp_position.get("size", 0.0))
        
        realized_btc = float(perp_position.get("realized_profit_loss", 0.0))
        unrealized_btc = float(perp_position.get("floating_profit_loss", 0.0))
        
        realized_usd = realized_btc * spot_price
        unrealized_usd = unrealized_btc * spot_price
        
        total_hedge_realized_usd += realized_usd
        total_hedge_unrealized_usd += unrealized_usd
        
        hedge_table.append([
            "BTC-PERPETUAL",
            f"{size_usd:,.0f} USD",
            format_usd(realized_usd),
            format_usd(unrealized_usd)
        ])

    # 5. Calculate Total Strategy P/L
    net_strategy_pl = total_opt_unrealized_usd + total_hedge_realized_usd + total_hedge_unrealized_usd

    # 6. Print Report
    print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}!!! VERITAS TRADER: CRYPTO PERFORMANCE REPORT !!!{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
    print(f"Account Equity: ${equity_usd:,.2f} USD\n")
    
    print(f"{Fore.YELLOW}[ ACTIVE CASINO OPTION ]{Style.RESET_ALL}")
    if opt_table:
        print(tabulate(opt_table, headers=["Instrument", "Size", "Entry Price", "Current Price", "Unrealized P/L"], tablefmt="simple"))
    else:
        print("No active options.")
        
    print(f"\n{Fore.YELLOW}[ DYNAMIC HEDGE (GAMMA SCALPING) ]{Style.RESET_ALL}")
    if hedge_table:
        print(tabulate(hedge_table, headers=["Instrument", "Net Size", "Realized P/L (Cash Harvested)", "Unrealized P/L"], tablefmt="simple"))
    else:
        print("No active hedges.")
        
    print(f"\n{Fore.WHITE}NET STRATEGY P/L: {format_usd(net_strategy_pl)}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

if __name__ == "__main__":
    main()