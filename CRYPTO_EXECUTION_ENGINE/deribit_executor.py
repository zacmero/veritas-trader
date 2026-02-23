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

    def get_account_summary(self, currency="BTC"):
        """Returns the account summary for a specific currency."""
        if not self.access_token:
            self.connect()
            
        url = f"{self.base_url}/private/get_account_summary"
        params = {"currency": currency, "extended": "true"}
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            if "result" in data:
                return data["result"]
            return {}
        except Exception as e:
            print(f"Error fetching account summary: {e}")
            return {}

    def get_all_positions(self):
        """Returns a list of active positions."""
        if not self.access_token:
            self.connect()
            
        url = f"{self.base_url}/private/get_positions"
        params = {"currency": "BTC", "kind": "any"}
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            if "result" in data:
                # Filter out positions with 0 size
                return [p for p in data["result"] if float(p.get("size", 0)) != 0]
            return []
        except Exception as e:
            print(f"Error fetching positions: {e}")
            return []
            
    def _place_order(self, instrument: str, amount: float, side: str):
        if not self.access_token:
            self.connect()
            
        endpoint = f"/private/{side}"
        url = f"{self.base_url}{endpoint}"
        
        params = {
            "instrument_name": instrument,
            "amount": amount,
            "type": "market"
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
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
