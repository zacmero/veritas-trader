"""
Veritas Trader - Deribit Adapter
--------------------------------
Adapter for Deribit Testnet REST API. Handles authentication, pricing, and execution
for BTC Options and Perpetual Futures (Gamma Scalping).
"""

import os
import requests
from colorama import init, Fore, Style

init(autoreset=True)

class DeribitExecutor:
    def __init__(self):
        self.client_id = os.getenv("DERIBIT_CLIENT_ID")
        self.client_secret = os.getenv("DERIBIT_CLIENT_SECRET")
        self.is_testnet = str(os.getenv("DERIBIT_TESTNET", "False")).lower() == "true"
        
        if not self.client_id or not self.client_secret:
            raise ValueError("Deribit Credentials missing from .env")
            
        self.base_url = "https://test.deribit.com/api/v2" if self.is_testnet else "https://www.deribit.com/api/v2"
        self.access_token = None
        self.headers = {}

    def connect(self):
        print(f"--- Connecting to Deribit ({'TESTNET' if self.is_testnet else 'MAINNET'})... ---")
        url = f"{self.base_url}/public/auth"
        params = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            if "result" in data and "access_token" in data["result"]:
                self.access_token = data["result"]["access_token"]
                self.headers = {"Authorization": f"Bearer {self.access_token}"}
                print(f"{Fore.GREEN}Deribit Connection Established.{Style.RESET_ALL}")
            else:
                raise Exception(f"Auth failed: {data}")
        except Exception as e:
            print(f"{Fore.RED}Deribit Connection Failed: {e}{Style.RESET_ALL}")
            raise e

    def get_current_price(self, instrument_name: str) -> float:
        """Fetches the mark price for a given instrument."""
        url = f"{self.base_url}/public/ticker"
        params = {"instrument_name": instrument_name}
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            if "result" in data and "mark_price" in data["result"]:
                return float(data["result"]["mark_price"])
            return 0.0
        except Exception as e:
            # print(f"Error fetching price for {instrument_name}: {e}")
            return 0.0


    def _send_private_request(self, endpoint: str, params: dict):
        if not self.access_token:
            self.connect()
            
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                raise requests.exceptions.HTTPError(f"API Error: {data['error']}")
        except requests.exceptions.HTTPError as e:
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 401:
                print(f"{Fore.YELLOW}Token likely expired. Reconnecting...{Style.RESET_ALL}")
                self.connect()
                response = requests.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()
            else:
                raise e
                
        return data

    def get_account_summary(self, currency="BTC"):
        """Returns the account summary for a specific currency."""
        params = {"currency": currency, "extended": "true"}
        try:
            data = self._send_private_request("/private/get_account_summary", params)
            if "result" in data:
                return data["result"]
            return {}
        except Exception as e:
            print(f"Error fetching account summary: {e}")
            return {}

    def get_all_positions(self, currency="BTC"):
        """Returns a list of active positions."""
        params = {"currency": currency, "kind": "any"}
        try:
            data = self._send_private_request("/private/get_positions", params)
            if "result" in data:
                return [p for p in data["result"] if float(p.get("size", 0)) != 0]
            return []
        except Exception as e:
            print(f"Error fetching positions: {e}")
            return []
            
    def _place_order(self, instrument: str, amount: float, side: str):
        params = {
            "instrument_name": instrument,
            "amount": amount,
            "type": "market"
        }
        try:
            data = self._send_private_request(f"/private/{side}", params)
            if "result" in data and "order" in data["result"]:
                order = data["result"]["order"]
                print(f"{side.capitalize()} Order Sent. ID: {order.get('order_id')}")
                avg_price = float(order.get("average_price", 0) or order.get("price", 0))
                return True, avg_price
            else:
                print(f"{side.capitalize()} Failed: {data}")
                return False, 0.0
        except Exception as e:
            print(f"{side.capitalize()} Request Failed: {e}")
            return False, 0.0

    def place_market_buy(self, instrument: str, amount: float):
        """Executes an immediate market buy for the specified amount."""
        print(f"EXECUTING MARKET BUY: {amount} of {instrument}")
        return self._place_order(instrument, amount, "buy")

    def place_market_sell(self, instrument: str, amount: float):
        """Executes an immediate market sell for the specified amount."""
        print(f"EXECUTING MARKET SELL: {amount} of {instrument}")
        return self._place_order(instrument, amount, "sell")

    def get_historical_closes(self, instrument_name: str, days: int = 30) -> list:
        import time
        end_timestamp = int(time.time() * 1000)
        start_timestamp = end_timestamp - (days * 24 * 3600 * 1000)
        url = f"{self.base_url}/public/get_tradingview_chart_data"
        params = {
            "instrument_name": instrument_name,
            "start_timestamp": start_timestamp,
            "end_timestamp": end_timestamp,
            "resolution": "1D"
        }
        try:
            import requests
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            if "result" in data and "close" in data["result"]:
                return data["result"]["close"]
            return []
        except Exception as e:
            print(f"Error fetching historical closes: {e}")
            return []

    def cancel_all_orders(self, instrument_name: str):
        params = {"instrument_name": instrument_name}
        try:
            data = self._send_private_request("/private/cancel_all_by_instrument", params)
            if "result" in data:
                return data["result"]
            return 0
        except Exception as e:
            print(f"Error cancelling orders: {e}")
            return 0

    def _place_limit_order(self, instrument: str, amount: float, price: float, side: str):
        params = {
            "instrument_name": instrument,
            "amount": amount,
            "type": "limit",
            "price": price,
            "post_only": "true" # Ensure Maker
        }
        try:
            data = self._send_private_request(f"/private/{side}", params)
            if "result" in data and "order" in data["result"]:
                order = data["result"]["order"]
                print(f"Limit {side.capitalize()} Order Sent. ID: {order.get('order_id')} @ ${price}")
                return True, price
            else:
                print(f"Limit {side.capitalize()} Failed: {data}")
                return False, 0.0
        except Exception as e:
            print(f"Limit {side.capitalize()} Request Failed: {e}")
            return False, 0.0

    def place_limit_buy(self, instrument: str, amount: float, price: float):
        return self._place_limit_order(instrument, amount, price, "buy")

    def place_limit_sell(self, instrument: str, amount: float, price: float):
        return self._place_limit_order(instrument, amount, price, "sell")
