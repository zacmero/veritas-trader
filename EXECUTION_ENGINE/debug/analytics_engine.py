import os
import pandas as pd
import re
from colorama import init, Fore, Style
import glob

init(autoreset=True)

BASE_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_FILE = os.path.join(BASE_PATH, "EXECUTION_ENGINE", "trade_history.csv")
LOG_DIR = os.path.join(BASE_PATH, "NIGHTLY_SCANNER", "LOGS_QUICKSTRIKE")
REPORT_FILE = os.path.join(BASE_PATH, "EXECUTION_ENGINE", "analytics_report.txt")

def parse_quickstrike_log(ticker, m_list):
    """
    Finds the log file for a ticker and extracts:
    - Best Match Name (Archetype)
    - Predicted Win Rate / Avg PL
    - Last Signal Date
    """
    # Search for any log with this ticker
    # Pattern accounts for both "IN_TRADE" prefix and standard prefix
    pattern = os.path.join(LOG_DIR, f"*live_qs_{ticker}_m*.log")
    files = glob.glob(pattern)
    
    if not files:
        return None

    # Pick the best file (prefer IN_TRADE as it implies active management)
    best_file = files[0]
    for f in files:
        if "IN_TRADE" in os.path.basename(f):
            best_file = f
            break
            
    try:
        with open(best_file, 'r', errors='ignore') as f:
            content = f.read()
            
        # Extract Match Name from the last "BUY SIGNAL" block or table
        # Table format example: | 2026-01-30 | 2026-02-02 | C_GME_2020... | ...
        
        # Regex to find table rows containing dates
        table_rows = re.findall(r"\|\s*\d{4}-\d{2}-\d{2}.+\|", content)
        
        match_name = "Unknown"
        if table_rows:
            last_row = table_rows[-1]
            parts = [p.strip() for p in last_row.split('|')]
            # Expected parts: ['', 'EntryDate', 'ExitDate', 'MatchName', 'Reason', 'Profit', '']
            # So MatchName should be at index 3
            if len(parts) >= 4:
                match_name = parts[3]
        
        # Extract Verdict
        verdict = "UNKNOWN"
        if "PROVEN WINNER" in content: verdict = "PROVEN WINNER"
        elif "BLACK SHEEP" in content: verdict = "BLACK SHEEP"
        elif "PROFITABLE" in content: verdict = "PROFITABLE"
        
        return {
            "LogFile": os.path.basename(best_file),
            "MatchName": match_name,
            "Verdict": verdict
        }
        
    except Exception:
        return None

def main():
    print(f"{Fore.CYAN}--- [POST-MORTEM ANALYTICS ENGINE] ---")
    
    if not os.path.exists(HISTORY_FILE):
        print(f"{Fore.RED}No trade history found.")
        return

    # Load Real Trades
    try:
        trades = pd.read_csv(HISTORY_FILE)
    except Exception as e:
        print(f"{Fore.RED}Error reading trade history: {e}")
        return

    print(f"Analyzing {len(trades)} closed trades...")
    
    analytics_data = []
    
    for _, row in trades.iterrows():
        ticker = row['Ticker']
        m_list = str(row.get('M_List', ''))
        
        # Get Simulation Data
        sim_data = parse_quickstrike_log(ticker, m_list)
        
        entry = {
            'Ticker': ticker,
            'Real_PL_Pct': float(row['PL_Percent']),
            'Real_PL_Dol': float(row['PL_Dollars']),
            'Exit_Reason': row['ExitReason'],
            'M_List': m_list,
            'Sim_Match': sim_data['MatchName'] if sim_data else "N/A",
            'Sim_Verdict': sim_data['Verdict'] if sim_data else "N/A"
        }
        analytics_data.append(entry)
        
    df = pd.DataFrame(analytics_data)
    
    if df.empty:
        print("No data to analyze.")
        return

    # --- REPORT GENERATION ---
    output = []
    output.append("============================================================")
    output.append("              POST-MORTEM ANALYTICS REPORT")
    output.append("============================================================")
    output.append(f"Total Trades Analyzed: {len(df)}")
    output.append(f"Total Realized P/L:    ${df['Real_PL_Dol'].sum():.2f}")
    
    wins = len(df[df['Real_PL_Dol'] > 0])
    win_rate = (wins / len(df) * 100) if len(df) > 0 else 0.0
    output.append(f"Average Win Rate:      {win_rate:.1f}%")
    output.append("------------------------------------------------------------\n")
    
    # 1. Performance by Archetype (Match Name)
    output.append("--- [PERFORMANCE BY ARCHETYPE] ---")
    if 'Sim_Match' in df.columns:
        # Group by Match Name
        arch_group = df.groupby('Sim_Match').agg({
            'Real_PL_Pct': 'mean',
            'Real_PL_Dol': 'sum',
            'Ticker': 'count'
        }).sort_values(by='Real_PL_Pct', ascending=False)
        
        output.append(f"{'Archetype':<25} | {'Count':<5} | {'Avg P/L %':<10} | {'Total $':<10}")
        output.append("-" * 65)
        
        for name, row in arch_group.iterrows():
            if name == "N/A": continue
            # Truncate name for display
            disp_name = (name[:22] + '..') if len(name) > 22 else name
            
            pl_pct = row['Real_PL_Pct']
            # Only use color codes in console print, strip later for file
            c = Fore.GREEN if pl_pct > 0 else Fore.RED
            
            output.append(f"{disp_name:<25} | {int(row['Ticker']):<5} | {c}{pl_pct:>9.2f}%{Style.RESET_ALL} | ${row['Real_PL_Dol']:>9.2f}")

    output.append("\n------------------------------------------------------------\n")

    # 3. Best Winners vs Worst Losers
    output.append("--- [TOP 5 WINNERS] ---")
    winners = df.sort_values(by='Real_PL_Pct', ascending=False).head(5)
    for _, row in winners.iterrows():
        output.append(f"{row['Ticker']:<6} | {Fore.GREEN}{row['Real_PL_Pct']:+.2f}%{Style.RESET_ALL} | {row['Sim_Match']}")
        
    output.append("\n--- [TOP 5 LOSERS] ---")
    losers = df.sort_values(by='Real_PL_Pct', ascending=True).head(5)
    for _, row in losers.iterrows():
        output.append(f"{row['Ticker']:<6} | {Fore.RED}{row['Real_PL_Pct']:+.2f}%{Style.RESET_ALL} | {row['Sim_Match']}")

    # Print and Save
    full_report = "\n".join(output)
    print(full_report)
    
    # Strip codes for file save using a cleaner regex
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_report = ansi_escape.sub('', full_report)
    
    with open(REPORT_FILE, "w") as f:
        f.write(clean_report)
    
    print(f"\n{Fore.GREEN}Analytics saved to {REPORT_FILE}")

if __name__ == "__main__":
    main()