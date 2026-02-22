import sys
import os
import inspect

# Fix Import Error: Add project root to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from EXECUTION_ENGINE.utils import load_env_file
from alpaca.trading.client import TradingClient
import alpaca.trading.requests as requests_module # Import the module to inspect it

def main():
    load_env_file()
    
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    
    print("--- DEBUGGING ALPACA ACTIVITIES ---")

    # 1. Inspect available Request classes
    print("\nChecking available Request classes in 'alpaca.trading.requests':")
    available_classes = [name for name, obj in inspect.getmembers(requests_module) if inspect.isclass(obj)]
    
    print(f"All Classes: {available_classes}")

    # 2. Try to connect and fetch
    client = TradingClient(api_key, secret_key, paper=True)
    
    # Try to dynamically use the correct class if found
    RequestClass = None
    if 'GetAccountActivitiesRequest' in available_classes:
        RequestClass = requests_module.GetAccountActivitiesRequest
        print("\nUsing 'GetAccountActivitiesRequest'")
    elif 'GetActivitiesRequest' in available_classes:
        RequestClass = requests_module.GetActivitiesRequest
        print("\nUsing 'GetActivitiesRequest'")
    
    if RequestClass:
        try:
            from alpaca.trading.enums import ActivityType
            # Basic request for fills
            req = RequestClass(activity_types=[ActivityType.FILL])
            activities = client.get_account_activities(req)
            print(f"\nSuccessfully fetched {len(activities)} activities.")
            if activities:
                print(f"Sample: {activities[0]}")
        except Exception as e:
            print(f"Error fetching activities: {e}")
    else:
        print("\nCould not find a suitable Request class for Activities.")

if __name__ == "__main__":
    main()