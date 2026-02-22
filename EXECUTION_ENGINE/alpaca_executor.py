from .executor_interface import OrderExecutor
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, StopOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest, StockLatestTradeRequest
import os
import math
from datetime import datetime, time as dtime
import pytz
from colorama import init, Fore, Style

init(autoreset=True)

class AlpacaExecutor(OrderExecutor):
    def __init__(self, paper_trading=True):
        self.api_key = os.getenv("ALPACA_API_KEY")
        self.secret_key = os.getenv("ALPACA_SECRET_KEY")
        self.paper = paper_trading
        
        if not self.api_key or not self.secret_key:
            raise ValueError("Alpaca Credentials missing from .env")

        self.trading_client = None
        self.data_client = None

    def connect(self):
        print(f"--- Connecting to Alpaca ({'PAPER' if self.paper else 'LIVE'})... ---")
        try:
            self.trading_client = TradingClient(self.api_key, self.secret_key, paper=self.paper)
            self.data_client = StockHistoricalDataClient(self.api_key, self.secret_key)
            
            account = self.trading_client.get_account()
            print(f"Connected. Status: {account.status}")
        except Exception as e:
            print(f"Alpaca Connection Failed: {e}")
            raise e

    def get_account_balance(self):
        try:
            account = self.trading_client.get_account()
            # User requested Cash Only (No Margin)
            return float(account.cash)
        except:
            return 0.0

    def get_current_price(self, ticker):
        try:
            # Paper account requires feed='iex'
            req = StockLatestQuoteRequest(symbol_or_symbols=ticker, feed='iex')
            res = self.data_client.get_stock_latest_quote(req)
            price = float(res[ticker].ask_price)
            
            # Fallback if Ask is 0 (Market Closed / No Liquidity)
            if price == 0:
                req_trade = StockLatestTradeRequest(symbol_or_symbols=ticker, feed='iex')
                res_trade = self.data_client.get_stock_latest_trade(req_trade)
                price = float(res_trade[ticker].price)
                
            return price
        except Exception as e:
            # print(f"Price Fetch Error ({ticker}): {e}") # Suppress noise
            return None

    def cancel_all_orders(self, ticker):
        """Cancels open orders for a specific ticker."""
        try:
            req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[ticker])
            orders = self.trading_client.get_orders(req)
            for order in orders:
                try:
                    self.trading_client.cancel_order_by_id(order.id)
                    print(f"Cancelled Order: {order.id} ({order.type})")
                except Exception as e:
                    if "filled" in str(e) or "not found" in str(e):
                        continue # Harmless race condition
                    print(f"Error cancelling order {order.id}: {e}")
        except Exception as e:
            print(f"Error cancelling orders: {e}")

    # --- FRACTIONAL LOGIC ---

    def place_fractional_entry(self, ticker, notional_amount):
        """
        Places a simple Market Buy using NOTIONAL value.
        Handles Halt Fallback.
        """
        notional_amount = round(float(notional_amount), 2)
        print(f"EXECUTING BUY: ${notional_amount:.2f} of {ticker}")
        
        try:
            req = MarketOrderRequest(
                symbol=ticker,
                notional=notional_amount, 
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY
            )
            order = self.trading_client.submit_order(req)
            print(f"Buy Order Sent. ID: {order.id}")
            return order.id
        except Exception as e:
            # FALLBACK 1: Trading Halt (Limit Order)
            if "trading halt" in str(e).lower() or "place a limit order" in str(e).lower():
                print(f"Trading Halt detected on {ticker}. Retrying with Limit Order...")
                price = self.get_current_price(ticker)
                if not price: return None
                
                limit_price = round(price * 1.02, 2)
                
                try:
                    qty = int(notional_amount // limit_price)
                    if qty < 1: return None
                    
                    req_limit = LimitOrderRequest(
                        symbol=ticker,
                        qty=qty,
                        side=OrderSide.BUY,
                        time_in_force=TimeInForce.DAY,
                        limit_price=limit_price
                    )
                    order = self.trading_client.submit_order(req_limit)
                    print(f"Limit Buy Order Sent. ID: {order.id} (Qty: {qty} @ ${limit_price})")
                    return order.id
                except Exception as e2:
                    print(f"Limit Retry Failed: {e2}")
                    return None

            # FALLBACK 2: Integer Shares
            if "not fractionable" in str(e).lower():
                print(f"Asset {ticker} not fractionable. Attempting integer shares...")
                price = self.get_current_price(ticker)
                if not price: return None
                qty = int(notional_amount // price)
                if qty < 1: return None
                
                try:
                    req_int = MarketOrderRequest(
                        symbol=ticker,
                        qty=qty,
                        side=OrderSide.BUY,
                        time_in_force=TimeInForce.DAY
                    )
                    order = self.trading_client.submit_order(req_int)
                    print(f"Integer Buy Order Sent. ID: {order.id} (Qty: {qty})")
                    return order.id
                except Exception as e2:
                    print(f"Integer Buy Failed: {e2}")
                    return None
            
            print(f"Buy Failed: {e}")
            return None

    # --- SMART EXIT LOGIC (Extended Hours) ---

    def place_market_sell(self, ticker, quantity):
        self.cancel_all_orders(ticker)
        
        # Determine Market Session
        is_extended = False
        tz = pytz.timezone('US/Eastern')
        now = datetime.now(tz).time()
        
        market_open = dtime(9, 30)
        market_close = dtime(16, 0)
        
        if now < market_open or now >= market_close:
            is_extended = True
            print(f"Extended Hours Detected ({now}). Using Smart Limit Exit.")

        # Get Price for either Limit Order or for Ledger accuracy
        current_price = self.get_current_price(ticker)
        if not current_price:
            print(f"Error: Could not fetch price for exit of {ticker}.")
            return False, 0.0

        print(f"EXECUTING: {'SMART ' if is_extended else ''}MARKET SELL {quantity} x {ticker}")
        
        try:
            if is_extended:
                # Alpaca constraint: No fractional in extended hours
                qty_int = int(quantity)
                
                if qty_int < 1:
                    print(f"{Fore.YELLOW}TRAPPED: {ticker} ({quantity}) is fractional. Waiting for Market Open.{Style.RESET_ALL}")
                    return False, 0.0

                # Aggressive Limit: 2% below current price to force a fill
                limit_price = round(current_price * 0.98, 2)
                
                req = LimitOrderRequest(
                    symbol=ticker,
                    qty=qty_int,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                    limit_price=limit_price,
                    extended_hours=True
                )
                sell_price = limit_price
            else:
                req = MarketOrderRequest(
                    symbol=ticker,
                    qty=quantity,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY
                )
                sell_price = current_price

            self.trading_client.submit_order(req)
            print("Sell Order Sent.")
            return True, sell_price
            
        except Exception as e:
            print(f"Sell Failed: {e}")
            return False, 0.0

    def place_entry_with_bracket(self, ticker, dollar_amount, stop_loss_pct, moonshot_pct):
        return self.place_fractional_entry(ticker, dollar_amount)
    
    def place_fractional_exits(self, ticker, qty, entry_price, stop_loss_pct=0.05, moonshot_pct=0.20):
        # Deprecated by Portfolio Manager Master logic, but kept for interface compliance
        pass