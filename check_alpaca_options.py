from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOptionContractsRequest
from alpaca.trading.enums import ContractType
import os
from utils import load_env_file

load_env_file()
api_key = os.getenv("ALPACA_API_KEY")
secret_key = os.getenv("ALPACA_SECRET_KEY")
client = TradingClient(api_key, secret_key, paper=True)

test_tickers = ["SPLG", "RSP", "SPYG", "IWM", "QQQM", "DIA", "XLF"]

for ticker in test_tickers:
    req = GetOptionContractsRequest(underlying_symbols=[ticker], status="active", type=ContractType.CALL)
    try:
        contracts = client.get_option_contracts(req)
        if contracts.option_contracts:
            print(f"{ticker}: Supported (Found {len(contracts.option_contracts)} contracts)")
        else:
            print(f"{ticker}: No contracts returned")
    except Exception as e:
        print(f"{ticker}: Error - {e}")
