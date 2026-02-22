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
    
    print("--- DEBUG RAW ACTIVITY ---")
    try:
        client = TradingClient(api_key, secret_key, paper=True)
        
        params = {
            "activity_types": "FILL", 
            "page_size": 1
        }
        
        activities = client.get("/account/activities", params)
        
        if activities:
            print("Found Activity!")
            first = activities[0]
            print(json.dumps(first, indent=4))
            
            print("\n--- DIAGNOSIS ---")
            keys = list(first.keys())
            print(f"Keys: {keys}")
        else:
            print("No activities found in response.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()