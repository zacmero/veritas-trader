from EXECUTION_ENGINE.alpaca_executor import AlpacaExecutor
from EXECUTION_ENGINE.utils import load_env_file

load_env_file()
bot = AlpacaExecutor(paper_trading=True)
bot.connect()

from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus

print("\n--- POSITIONS ---")
positions = bot.trading_client.get_all_positions()
print(f"Count: {len(positions)}")
for p in positions:
    print(f"{p.symbol}: {p.qty}")

print("\n--- OPEN ORDERS ---")
req = GetOrdersRequest(status=QueryOrderStatus.OPEN)
orders = bot.trading_client.get_orders(req)
print(f"Count: {len(orders)}")
for o in orders:
    print(f"{o.symbol}: {o.side} {o.qty} ({o.status})")

