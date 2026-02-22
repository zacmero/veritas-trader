from EXECUTION_ENGINE.alpaca_executor import AlpacaExecutor
from EXECUTION_ENGINE.utils import load_env_file
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

load_env_file()
bot = AlpacaExecutor(paper_trading=True)
bot.connect()

print("Attempting to buy $10 BTC/USD (Crypto is 24/7)...")

try:
    # Use raw client to bypass our wrapper logic for a pure test
    # Crypto needs GTC
    req = MarketOrderRequest(
        symbol="BTC/USD",
        notional=10.0,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.GTC
    )
    order = bot.trading_client.submit_order(req)
    print(f"Order Sent: {order.id} status: {order.status}")
except Exception as e:
    print(f"Failed: {e}")
