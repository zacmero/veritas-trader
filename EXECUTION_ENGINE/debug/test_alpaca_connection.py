import os
from alpaca.trading.client import TradingClient
from colorama import init, Fore
from .utils import load_env_file

init(autoreset=True)

def main():
    load_env_file()
    print(f"{Fore.CYAN}--- [ALPACA CONNECTION TEST] ---")
    
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    
    if not api_key or not secret_key:
        print(f"{Fore.RED}Error: ALPACA credentials not found in .env")
        return

    print(f"Connecting with Key: {api_key[:5]}...")
    
    try:
        # 1. Trading Client (Account Info)
        trading_client = TradingClient(api_key, secret_key, paper=True)
        account = trading_client.get_account()
        
        print(f"{Fore.GREEN}SUCCESS! Connected to Alpaca Trading API.")
        print(f"Status: {account.status}")
        print(f"Buying Power: ${account.buying_power}")
        print(f"Cash: ${account.cash}")
        
    except Exception as e:
        print(f"{Fore.RED}CONNECTION FAILED.")
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
