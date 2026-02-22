import sys
import os
import inspect

# Fix Import Error
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from EXECUTION_ENGINE.utils import load_env_file
from alpaca.trading.client import TradingClient

def main():
    load_env_file()
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    
    client = TradingClient(api_key, secret_key, paper=True)
    
    print("--- AVAILABLE METHODS ---")
    print(dir(client))

if __name__ == "__main__":
    main()