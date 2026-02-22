import os
import sys
# Fix Import
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
    
    print("Testing /v2/account/activities...")
    try:
        # Note: client.get might be expecting just the path if base_url is set
        res = client.get("/v2/account/activities")
        print("Success with /v2!")
        # print(res[0] if res else "Empty list")
        return
    except Exception as e:
        print(f"Failed with /v2: {e}")

    print("Testing /account/activities...")
    try:
        res = client.get("/account/activities")
        print("Success without /v2!")
        return
    except Exception as e:
        print(f"Failed without /v2: {e}")

if __name__ == "__main__":
    main()