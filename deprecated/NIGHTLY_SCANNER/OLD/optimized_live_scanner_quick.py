import subprocess
import os
import time
import sys
import argparse
from datetime import datetime
from colorama import init, Fore, Style
from concurrent.futures import ThreadPoolExecutor, as_completed

init(autoreset=True)

# --- CONFIGURATION ---
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
SCANNER_SCRIPT = os.path.join(BASE_PATH, "master_scanner_quickstrike.py")
# Default target file if none provided
DEFAULT_TARGETS_FILE = "quickstrike_targets.txt" 
LOG_DIR = os.path.join(BASE_PATH, "LOGS_QUICKSTRIKE")

# --- PERFORMANCE TUNING ---
# Set this to match your CPU cores.
# For a 4-core machine, keeping this at 4 is optimal.
MAX_CONCURRENT_PROCESSES = 4 

M_VALUES = [15, 30, 60, 90, 120]

def check_log_for_status(log_path):
    verdict = "UNKNOWN"
    live_status = False
    entry_price = "N/A"
    stats = "N/A"
    equity = "N/A"
    
    # Check for renamed file
    if not os.path.exists(log_path):
        directory, filename = os.path.split(log_path)
        renamed_path = os.path.join(directory, f"IN_TRADE_{filename}")
        if os.path.exists(renamed_path):
            log_path = renamed_path
        else:
            return "ERROR", False, "N/A", "N/A", "N/A"

    with open(log_path, 'r') as f:
        content = f.read()
        
        if "STRATEGY VERDICT: PROFITABLE" in content: verdict = "PROFITABLE"
        elif "STRATEGY VERDICT: BLACK SHEEP" in content: verdict = "BLACK SHEEP"
        elif "STRATEGY VERDICT: PASSIVE" in content: verdict = "PASSIVE"
            
        if "This is a potential LIVE BUY SIGNAL" in content:
            live_status = True
            try:
                price_line = [line for line in content.split('\n') if "Entry Price:" in line]
                if price_line: entry_price = price_line[-1].split(": ")[1]
            except: pass

        try:
            stats_line = [line for line in content.split('\n') if "Total Trades:" in line and "Win Rate:" in line]
            if stats_line: stats = stats_line[-1].strip()
            equity_line = [line for line in content.split('\n') if "Simulated Account" in line]
            if equity_line: equity = equity_line[-1].split(": ")[1].split(" (")[0]
        except: pass

    return verdict, live_status, entry_price, stats, equity

def run_single_scan_task(task_args):
    """Runs a single m-value scan for a ticker."""
    ticker, m = task_args
    log_filename = f"live_qs_{ticker}_m{m}.log"
    log_path = os.path.join(LOG_DIR, log_filename)
    
    os.makedirs(LOG_DIR, exist_ok=True)

    command = [
        "python3", SCANNER_SCRIPT,
        "--ticker", ticker,
        "--m", str(m),
        "--logfile", log_filename
    ]
    
    try:
        # Run blocking inside the thread
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return (ticker, m, log_path, True)
    except subprocess.CalledProcessError:
        return (ticker, m, log_path, False)

def print_report(ticker, results):
    """Prints the summary table for a ticker."""
    print(f"\n{Fore.WHITE}--- REPORT FOR {ticker} ---")
    print(f"{'M-Value':<8} | {'Verdict':<12} | {'Status':<12} | {'Equity':<12} | {'Stats'}")
    print("-" * 90)

    results.sort(key=lambda x: x[0])

    for m, log_path, success in results:
        if not success:
            print(f"m={m:<6} | {Fore.RED}EXECUTION FAILED")
            continue

        verdict, live_status, price, stats, equity = check_log_for_status(log_path)
        
        v_color = Fore.WHITE
        if verdict == "PROFITABLE": v_color = Fore.GREEN
        elif verdict == "BLACK SHEEP": v_color = Fore.RED
        elif verdict == "PASSIVE": v_color = Fore.BLUE
        
        s_color = Fore.WHITE
        if live_status: s_color = Fore.MAGENTA + Style.BRIGHT + "LIVE!"
        else: s_color = "Scanning"

        short_stats = stats.replace("Total Trades", "Trds").replace("Win Rate", "WR").replace("Avg P/L", "Avg")
        print(f"m={m:<6} | {v_color}{verdict:<12}{Style.RESET_ALL} | {s_color:<12}{Style.RESET_ALL} | {Fore.YELLOW}{equity:<12}{Style.RESET_ALL} | {short_stats}")

def main():
    parser = argparse.ArgumentParser(description="Optimized Live Scanner")
    parser.add_argument("--targets", default=DEFAULT_TARGETS_FILE, help="Path to targets file")
    args = parser.parse_args()

    targets_file_path = os.path.join(BASE_PATH, args.targets)

    if not os.path.exists(targets_file_path):
        print(f"{Fore.RED}Error: {targets_file_path} not found.")
        return

    with open(targets_file_path, 'r') as f:
        targets = [line.strip().upper() for line in f if line.strip()]

    print(f"{Fore.GREEN}Loaded {len(targets)} targets from {args.targets}.")
    print(f"{Fore.CYAN}Performance Mode: {MAX_CONCURRENT_PROCESSES} concurrent workers.")
    
    total_start = time.time()
    
    for i, ticker in enumerate(targets):
        print(f"\n{Fore.CYAN}[{i+1}/{len(targets)}] Scanning {ticker}...")
        
        tasks = [(ticker, m) for m in M_VALUES]
        ticker_results = []

        # The ThreadPool ensures we never exceed MAX_CONCURRENT_PROCESSES
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_PROCESSES) as executor:
            future_to_m = {executor.submit(run_single_scan_task, task): task[1] for task in tasks}
            
            for future in as_completed(future_to_m):
                m = future_to_m[future]
                try:
                    t, m_val, path, success = future.result()
                    ticker_results.append((m_val, path, success))
                except Exception as e:
                    print(f"{Fore.RED}Error in thread: {e}")

        print_report(ticker, ticker_results)

    total_time = time.time() - total_start
    print(f"\n{Fore.GREEN}{'='*60}")
    print(f"{Fore.GREEN}FULL SCAN COMPLETED in {total_time:.2f} seconds.")
    print(f"{Fore.GREEN}{'='*60}")

if __name__ == "__main__":
    main()