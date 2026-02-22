import os
import asyncio
import threading
import json
from datetime import datetime, timedelta
from alpaca.trading.stream import TradingStream
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import OrderStatus, QueryOrderStatus, OrderSide
from .alpaca_executor import AlpacaExecutor
from .utils import load_env_file
from colorama import init, Fore

init(autoreset=True)

executor = None

async def trade_update_handler(data):
    """WebSocket Event Handler"""
    event = data.event
    order = data.order
    symbol = order.symbol
    
    if event != 'fill':
        return

    qty = float(order.filled_qty or 0)
    price = float(order.filled_avg_price or 0)
    
    print(f"\n[{event.upper()}] {symbol}: {order.side} {qty} @ ${price:.2f}")

    if event == 'fill':
        if qty <= 0: return

        if order.side == 'buy':
            print(f"{Fore.GREEN}Entry Filled! Placing Bracket for {symbol}...\n")
            executor.cancel_all_orders(symbol)
            executor.place_fractional_exits(symbol, qty, price)
            
        elif order.side == 'sell':
            print(f"{Fore.YELLOW}Exit Filled! Cancelling remaining orders for {symbol}...\n")
            executor.cancel_all_orders(symbol)

def reconciliation_worker():
    """
    Background thread that polls for unprotected positions.
    """
    print("Reconciliation Worker Started...")
    
    # Create a new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def loop_logic():
        while True:
            await asyncio.sleep(60)
            try:
                # Check for active positions that might be missing exits
                positions = executor.trading_client.get_all_positions()
                
                for pos in positions:
                    symbol = pos.symbol
                    qty = float(pos.qty)
                    # available_qty tells us if shares are free to trade or locked in orders
                    # Fix: SDK uses 'qty_available' usually, checking both or defaulting
                    try:
                        qty_avail = float(pos.qty_available)
                    except AttributeError:
                        # Fallback for older SDK versions or different field names
                        qty_avail = float(getattr(pos, 'available_qty', 0))
                    
                    if qty > 0:
                        # If Available < Total, it means we have open orders (Stops/Limits)
                        if qty_avail < qty:
                            # print(f"{Fore.CYAN}[RECON] Position {symbol} is protected (Shares Held).")
                            continue

                        # If we are here, we have Naked Shares
                        print(f"{Fore.RED}[RECON] Found UNPROTECTED Position: {symbol}. Placing Bracket...")
                        try:
                            # CRITICAL: Cancel any hidden/stale orders that might be holding shares
                            # (Though available_qty check implies none are held, this clears partials)
                            executor.cancel_all_orders(symbol)
                            
                            entry_price = float(pos.avg_entry_price)
                            res = executor.place_fractional_exits(symbol, qty, entry_price)
                            if not res:
                                print(f"{Fore.YELLOW}[RECON] Rescue failed (API rejected). Position likely closing.")
                        except Exception as e:
                            if "held_for_orders" in str(e) or "insufficient qty" in str(e):
                                print(f"{Fore.YELLOW}[RECON] Rescue Skipped: Position is being closed/held.")
                            else:
                                print(f"[RECON ERROR] {e}")
                            
            except Exception as e:
                print(f"[RECON ERROR] {e}")

    loop.run_until_complete(loop_logic())

def main():
    load_env_file()
    print(f"{Fore.CYAN}--- [STREAM MANAGER: MANUAL BRACKET ENGINE + RECONCILER] ---")
    
    global executor
    executor = AlpacaExecutor(paper_trading=True)
    executor.connect()
    
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    
    # 1. Start Reconciliation in Background Thread
    recon_thread = threading.Thread(target=reconciliation_worker, daemon=True)
    recon_thread.start()

    # 2. Start WebSocket Stream (Main Thread Blocking)
    stream = TradingStream(api_key, secret_key, paper=True)
    stream.subscribe_trade_updates(trade_update_handler)

    print(f"{Fore.GREEN}Listening for fills... (Press Ctrl+C to stop)")
    try:
        stream.run()
    except KeyboardInterrupt:
        print("Stopping stream...")
    except Exception as e:
        print(f"Stream Error: {e}")

if __name__ == "__main__":
    main()
