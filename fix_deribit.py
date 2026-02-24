import os

with open('CRYPTO_EXECUTION_ENGINE/deribit_executor.py', 'r') as f:
    lines = f.readlines()

new_methods = """
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
            if hasattr(e, 'response') and e.response is not None and e.response.status_code in [400, 401]:
                print(f"{Fore.YELLOW}Token likely expired. Reconnecting...{Style.RESET_ALL}")
                self.connect()
                response = requests.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()
            else:
                raise e
                
        return data

    def get_account_summary(self, currency="BTC"):
        \"\"\"Returns the account summary for a specific currency.\"\"\"
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
        \"\"\"Returns a list of active positions.\"\"\"
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
        \"\"\"Executes an immediate market buy for the specified amount.\"\"\"
        print(f"EXECUTING MARKET BUY: {amount} of {instrument}")
        return self._place_order(instrument, amount, "buy")

    def place_market_sell(self, instrument: str, amount: float):
        \"\"\"Executes an immediate market sell for the specified amount.\"\"\"
        print(f"EXECUTING MARKET SELL: {amount} of {instrument}")
        return self._place_order(instrument, amount, "sell")
"""

# Find where get_account_summary starts
start_idx = -1
for i, line in enumerate(lines):
    if line.startswith("    def get_account_summary"):
        start_idx = i
        break

if start_idx != -1:
    final_content = "".join(lines[:start_idx]) + new_methods
    with open('CRYPTO_EXECUTION_ENGINE/deribit_executor.py', 'w') as f:
        f.write(final_content)
    print("Updated successfully")
else:
    print("Could not find get_account_summary")

