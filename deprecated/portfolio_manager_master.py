import pandas as pd
import os
import time
from datetime import datetime
from colorama import init, Fore, Style
from .alpaca_executor import AlpacaExecutor
from .utils import load_env_file
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus, OrderSide

init(autoreset=True)

# --- CONFIGURATION ---
BASE_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTFOLIO_FILE = os.path.join(BASE_PATH, "EXECUTION_ENGINE", "portfolio.csv")

# --- TRADING LOGIC (SOFT EXITS) ---
STOP_LOSS_PCT = -5.0          # Sell if drops 5%
MOONSHOT_PCT = 20.0           # Sell if jumps 20%
BREAK_EVEN_TRIGGER_PCT = 1.5  # Lock entry price if up 1.5%
MIN_PROFIT_TO_TRAIL = 2.0     # Start trailing if up 2.0%
TRAILING_RETRACEMENT = 0.50   # 50% retracement of gains
MAX_HOLD_DAYS = 7             # Time stop

def main():
    load_env_file()
    print(f"{Fore.CYAN}{'='*80}")
    print(f"!!! PORTFOLIO MANAGER MASTER - ONLINE !!!")
    print(f"{Style.RESET_ALL}{'='*80}")
    
    # 1. Connect to Alpaca
    bot = AlpacaExecutor(paper_trading=True)
    try:
        bot.connect()
    except Exception as e:
        print(f"{Fore.RED}Connection Failed: {e}")
        return

    while True:
        try:
            print(f"\n--- [Cycle Start: {datetime.now().strftime('%H:%M:%S')}] ---")
            
            # 2. Load High Water Mark (HWM) Memory from CSV
            hwm_memory = {}
            if os.path.exists(PORTFOLIO_FILE):
                try:
                    df_pf = pd.read_csv(PORTFOLIO_FILE)
                    for _, row in df_pf.iterrows():
                        hwm_memory[row['Ticker']] = {
                            'max_price': float(row.get('MaxPriceReached', 0.0)),
                            'm_list': row.get('M_List', 'N/A'),
                            'entry_date': row.get('EntryDate', 'N/A')
                        }
                except Exception as e:
                    print(f"HWM Load Warning: {e}")

            # 3. Get Real Positions from Alpaca (The Source of Truth)
            positions = bot.trading_client.get_all_positions()
            print(f"Managing {len(positions)} positions...")
            
            new_hwm_data = []

            for pos in positions:
                symbol = pos.symbol
                qty = float(pos.qty)
                entry_price = float(pos.avg_entry_price)
                current_price = float(pos.current_price)
                
                if qty < 0:
                    print(f"{Fore.RED}ALERT: Short position detected in {symbol}. Skipping.")
                    continue

                # Get existing memory or init
                mem = hwm_memory.get(symbol, {
                    'max_price': current_price,
                    'm_list': 'N/A',
                    'entry_date': datetime.now().strftime('%Y-%m-%d')
                })
                
                # Update Max Price (High Water Mark)
                max_price = max(float(mem['max_price']), current_price)
                
                # --- CALCULATE PROFITS ---
                cur_profit_pct = float(pos.unrealized_plpc) * 100
                max_profit_pct = ((max_price - entry_price) / entry_price) * 100.0 if entry_price > 0 else 0.0
                
                # --- EXIT LOGIC ---
                sell_signal = False
                reason = ""

                # 1. Hard Moonshot (+20%)
                if cur_profit_pct >= MOONSHOT_PCT:
                    sell_signal = True
                    reason = f"MOONSHOT (+{cur_profit_pct:.1f}%)"

                # 2. Hard Stop Loss (-5%)
                elif cur_profit_pct <= STOP_LOSS_PCT:
                    sell_signal = True
                    reason = f"STOP LOSS ({cur_profit_pct:.1f}%)"

                # 3. Trailing Stop
                elif max_profit_pct >= MIN_PROFIT_TO_TRAIL:
                    trail_floor = entry_price * (1 + (max_profit_pct/100) * (1 - TRAILING_RETRACEMENT))
                    if current_price <= trail_floor:
                        sell_signal = True
                        reason = f"TRAILING ({max_profit_pct:.1f}% peak -> {cur_profit_pct:.1f}%)"

                # 4. Break Even
                elif max_profit_pct >= BREAK_EVEN_TRIGGER_PCT:
                    if current_price <= entry_price:
                        sell_signal = True
                        reason = f"BREAK EVEN (Dipped after +{max_profit_pct:.1f}%)"

                # 5. Time Stop
                else:
                    try:
                        entry_dt = datetime.strptime(str(mem['entry_date']), '%Y-%m-%d')
                        days_held = (datetime.now() - entry_dt).days
                        if days_held >= MAX_HOLD_DAYS:
                            sell_signal = True
                            reason = f"TIME STOP ({days_held} Days)"
                    except:
                        days_held = 0

                # --- EXECUTE SELL ---
                if sell_signal:
                    # SPAM PREVENTION: Check if we already have a pending sell
                    try:
                        req_open = GetOrdersRequest(
                            status=QueryOrderStatus.OPEN,
                            symbols=[symbol],
                            side=OrderSide.SELL
                        )
                        existing_sells = bot.trading_client.get_orders(req_open)
                        if existing_sells:
                            # ACTIVE MANAGEMENT: Check if we should cancel the sell
                            c = Fore.GREEN if cur_profit_pct > 0 else Fore.RED
                            print(f"{Fore.YELLOW}PENDING SELL {symbol:<6}{Style.RESET_ALL} | Cur: ${current_price:.2f} ({c}{cur_profit_pct:+.2f}%{Style.RESET_ALL})")
                            
                            # RECOVERY CHECK: If price recovered above -3.0% (Safe Zone), Cancel Sell
                            if cur_profit_pct > -3.0 and cur_profit_pct < MOONSHOT_PCT:
                                print(f"{Fore.GREEN}>>> RECOVERY DETECTED ({cur_profit_pct:.2f}%). Cancelling Sell to resume HOLD.{Style.RESET_ALL}")
                                bot.cancel_all_orders(symbol)
                            
                            continue
                    except Exception: pass

                    print(f"{Fore.GREEN}>>> SELLING {symbol}: {reason}{Style.RESET_ALL}")
                    # Clear any manual orders before dumping
                    bot.cancel_all_orders(symbol)
                    success, sell_price = bot.place_market_sell(symbol, qty)
                    
                    if not success:
                        print(f"{Fore.YELLOW}Sell Order failed (will retry).{Style.RESET_ALL}")
                else:
                    # Keep Position
                    c = Fore.GREEN if cur_profit_pct > 0 else Fore.RED
                    print(f"HOLD {symbol:<6} | P/L: {c}{cur_profit_pct:>6.2f}%{Style.RESET_ALL} | Max: {max_profit_pct:>6.2f}%")
                    
                    new_hwm_data.append({
                        'Ticker': symbol,
                        'EntryPrice': entry_price,
                        'Shares': qty,
                        'EntryDate': mem['entry_date'],
                        'MaxPriceReached': max_price,
                        'M_List': mem['m_list']
                    })

            # 4. Sync Memory to CSV
            if new_hwm_data:
                pd.DataFrame(new_hwm_data).to_csv(PORTFOLIO_FILE, index=False)
            else:
                if not positions:
                    print("No active positions to manage.")
                else:
                    print("Sync skipped (positions exist but pending update).")

            print(f"Cycle Complete. Sleeping 5s...")
            time.sleep(5)

        except Exception as e:
            print(f"{Fore.RED}MASTER ERROR: {e}")
            time.sleep(10) # Cooling off before retry

if __name__ == "__main__":
    main()
