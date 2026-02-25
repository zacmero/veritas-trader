import os

with open('CRYPTO_EXECUTION_ENGINE/deribit_executor.py', 'r') as f:
    content = f.read()

new_methods = """
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
"""

content = content + new_methods

with open('CRYPTO_EXECUTION_ENGINE/deribit_executor.py', 'w') as f:
    f.write(content)
print("Updated deribit_executor.py")
