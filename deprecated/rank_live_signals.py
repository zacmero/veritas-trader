import os
import re
import pandas as pd
from colorama import init, Fore, Style

init(autoreset=True)

# --- CONFIGURATION ---
BASE_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# NOTE: User is placing Elephant Hunter logs here for testing
LOG_DIR = os.path.join(BASE_PATH, "NIGHTLY_SCANNER", "LOGS_QUICKSTRIKE") 
OUTPUT_FILE = os.path.join(BASE_PATH, "EXECUTION_ENGINE", "actionable_signals.csv")

# FILTER SETTINGS
ALLOW_BLACK_SHEEP = False 

def parse_log_stats(filepath):
    """
    Universal parser for both QuickStrike (qs) and Elephant Hunter (scan) logs.
    """
    filename = os.path.basename(filepath)
    
    with open(filepath, 'r', errors='ignore') as f:
        content = f.read()
    
    # 1. Check for Live Signal - This is the most reliable flag
    if "This is a potential LIVE BUY SIGNAL" not in content:
        # print(f"DEBUG: Skipping {filename}: No LIVE BUY SIGNAL")
        return None

    # 2. Check Verdict (Must be Profitable)
    if not ALLOW_BLACK_SHEEP:
        if "PROFITABLE" not in content and "PROVEN WINNER" not in content:
            # print(f"DEBUG: Skipping {filename}: Not PROFITABLE or PROVEN")
            return None
        if "BLACK SHEEP" in content: # Explicitly reject black sheep
            # print(f"DEBUG: Skipping {filename}: Is BLACK SHEEP")
            return None

    # 3. Universal Regex for Ticker/M
    match = re.search(r"live_(?:qs|scan)_(.+)_m(\d+)", filename)
    if not match: 
        print(f"DEBUG: Skipping {filename}: Filename regex mismatch")
        return None
    
    ticker = match.group(1)
    m_value = int(match.group(2))
    
    # 4. Universal Stats Parsing
    pl_match = re.search(r"Avg P/L:\s*([\d\.\-]+)%", content)
    if not pl_match:
        # Fallback for other potential formats
        pl_match = re.search(r"Average Profit/Loss per Trade:\s*([\d\.\-]+)%", content)
    
    if not pl_match: 
        print(f"DEBUG: Skipping {filename}: No Avg P/L found")
        return None # If we can't find P/L, we can't rank it.
    
    # Extract other stats if available, otherwise use defaults
    win_rate = 0.0
    trades = 0
    stats_match = re.search(r"Total Trades:\s*(\d+)\s*\|\s*Win Rate:\s*([\d\.]+)%", content)
    if stats_match:
        trades = int(stats_match.group(1))
        win_rate = float(stats_match.group(2))
        
    price_match = re.search(r"Entry Price:\s*\$?([\d\.]+)", content)
    entry_price = float(price_match.group(1)) if price_match else 0.0
    
    return {
        "Ticker": ticker,
        "M": m_value,
        "Price": entry_price,
        "Trades": trades,
        "WinRate": win_rate,
        "AvgPL": float(pl_match.group(1))
    }

def main():
    print(f"{Fore.CYAN}--- [LIVE SIGNAL RANKER (Universal)] ---")
    
    if not os.path.exists(LOG_DIR):
        print(f"{Fore.RED}Error: {LOG_DIR} not found.")
        return

    files = [f for f in os.listdir(LOG_DIR) if f.endswith(".log")]
    data = []
    
    print(f"Scanning {len(files)} logs in {LOG_DIR}...")
    
    for f in files:
        stats = parse_log_stats(os.path.join(LOG_DIR, f))
        if stats:
            data.append(stats)

    if not data:
        print(f"{Fore.YELLOW}No actionable profitable signals found.")
        pd.DataFrame(columns=['Ticker', 'M_List', 'Price', 'WinRate', 'AvgPL']).to_csv(OUTPUT_FILE, index=False)
        return

    # --- DEDUPLICATION LOGIC ---
    df_raw = pd.DataFrame(data)
    unique_tickers = []
    
    grouped = df_raw.groupby('Ticker')
    
    for ticker, group in grouped:
        best_signal = group.loc[group['AvgPL'].idxmax()].to_dict()
        m_list = sorted(group['M'].unique().tolist())
        best_signal['M_List'] = ",".join(map(str, m_list))
        del best_signal['M']
        unique_tickers.append(best_signal)
        
    df = pd.DataFrame(unique_tickers)
    df = df.sort_values(by=['AvgPL'], ascending=False)
    
    df.to_csv(OUTPUT_FILE, index=False)

    print(f"\n{Fore.GREEN}Found {len(df)} unique actionable signals (deduplicated).")
    print(f"Saved to: {OUTPUT_FILE}")
    print("-" * 65)
    print(df[['Ticker', 'M_List', 'Price', 'WinRate', 'AvgPL']].head(10).to_string(index=False))

if __name__ == "__main__":
    main()