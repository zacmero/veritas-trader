import os
import sys
import json
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
    
    print("--- FETCHING RAW ACTIVITIES ---")
    
    # Try different param combinations to see what sticks
    params = {
        "activity_types": "FILL",
        "direction": "desc",
        "page_size": 10
    }
    
    try:
        # 1. Try generic endpoint
        print("Requesting /account/activities...")
        data = client.get("/account/activities", params)
        print(f"Count: {len(data)}")
        if data:
            print("Sample Item Keys:", list(data[0].keys()))
            print("Sample Item:", json.dumps(data[0], indent=2))
        else:
            print("Result is EMPTY list.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
