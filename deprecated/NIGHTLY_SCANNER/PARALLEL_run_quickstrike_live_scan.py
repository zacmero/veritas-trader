import subprocess
import os
import time
import sys
import argparse
from datetime import datetime
from colorama import init, Fore, Style

init(autoreset=True)

# --- CONFIGURATION ---
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
SCANNER_SCRIPT = os.path.join(BASE_PATH, "master_scanner_quickstrike.py")
# Default log dir (Must match what is in master_scanner_quickstrike.py)
LOG_DIR = os.path.join(BASE_PATH, "LOGS_QUICKSTRIKE") 

M_VALUES = [15, 30, 60, 90, 120]

def check_log_for_status(log_path):
    verdict = "UNKNOWN"
    live_status = False
    entry_price = "N/A"
    stats = "N/A"
    equity = "N/A"
    
    # Check for Renamed "IN_TRADE" file
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

def run_parallel_scan(ticker, current_idx, total_targets):
    # Start Timer
    start_time = time.time()

    print(f"\n{Fore.CYAN}{'='*80}")
    print(f"{Fore.CYAN}--- [{current_idx}/{total_targets}] LAUNCHING PARALLEL SCAN FOR: {Style.BRIGHT}{ticker} {Style.NORMAL}---")
    print(f"{Fore.CYAN}{'='*80}")

    processes = []
    log_files = {}

    # 1. SPAWN PROCESSES (Parallel Execution)
    for m in M_VALUES:
        log_filename = f"live_qs_{ticker}_m{m}.log"
        log_path = os.path.join(LOG_DIR, log_filename)
        log_files[m] = log_path
        
        print(f"   > Launching m={m:<3} detector...", end="", flush=True)
        
        command = [
            "python3", SCANNER_SCRIPT,
            "--ticker", ticker,
            "--m", str(m),
            "--logfile", log_filename
        ]
        
        try:
            p = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            processes.append(p)
            print(f" {Fore.GREEN}[STARTED]")
        except Exception as e:
            print(f" {Fore.RED}[FAILED: {e}]")

    # 2. WAIT FOR COMPLETION
    print(f"\n{Fore.YELLOW}   ... detectors running in parallel ... please wait ...")
    
    for p in processes:
        p.wait()

    # Stop Timer
    elapsed = time.time() - start_time
    print(f"{Fore.GREEN}   > All detectors finished. (Took: {elapsed:.2f}s)\n")

    # 3. Audit Results
    print(f"{Fore.WHITE}--- REPORT FOR {ticker} (Fixed Start: 2020-01-01) ---")
    print(f"{'M-Value':<8} | {'Verdict':<12} | {'Status':<12} | {'Equity':<12} | {'Stats'}")
    print("-" * 90)

    for m in M_VALUES:
        verdict, live_status, price, stats, equity = check_log_for_status(log_files[m])
        
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
    parser = argparse.ArgumentParser(description="Parallel Quick Strike Live Orchestrator")
    parser.add_argument("--targets", default="TARGETS/elite_targets.txt", help="Path to targets file")
    args = parser.parse_args()

    targets_file_path = os.path.join(BASE_PATH, args.targets)

    if not os.path.exists(targets_file_path):
        print(f"{Fore.RED}Error: {targets_file_path} not found.")
        return

    with open(targets_file_path, 'r') as f:
        targets = [line.strip().upper() for line in f if line.strip()]

    print(f"{Fore.GREEN}Loaded {len(targets)} targets from {args.targets}.")
    total_start = time.time()
    
    # Added enumerate to track index
    for i, ticker in enumerate(targets, 1):
        try:
            run_parallel_scan(ticker, i, len(targets))
        except KeyboardInterrupt: sys.exit()
        except Exception as e: print(f"{Fore.RED}Error scanning {ticker}: {e}")

    total_time = time.time() - total_start
    print(f"\n{Fore.GREEN}{'='*60}")
    print(f"{Fore.GREEN}FULL SCAN COMPLETED in {total_time:.2f} seconds.")
    print(f"{Fore.GREEN}{'='*60}")

if __name__ == "__main__":
    main()