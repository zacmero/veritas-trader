import os
import subprocess
import time
import sys
from datetime import datetime
from colorama import init, Fore, Style

# --- INITIALIZE COLORAMA ---
init(autoreset=True)

# --- CONFIGURATION ---
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
MASTER_SCANNER_PATH = os.path.join(BASE_PATH, "master_scanner.py")
TARGETS_FILE = os.path.join(BASE_PATH, "TARGETS", "elite_targets.txt")
LOG_DIR = os.path.join(BASE_PATH, "LOGS")

# The detectors we want to run
M_VALUES_TO_RUN = [15, 30, 60, 90, 120]

def check_log_for_status(log_path):
    """Reads the log file to find the Verdict, Live Status, and Stats."""
    verdict = "UNKNOWN"
    live_status = False
    entry_price = "N/A"
    stats = "N/A"
    equity = "N/A"
    
    if not os.path.exists(log_path):
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

        # --- ADDED STATS PARSING ---
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
    
    run_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    start_date = "2020-01-01" 
    end_date = datetime.now().strftime('%Y-%m-%d')

    # 1. SPAWN PROCESSES
    for m in M_VALUES_TO_RUN:
        log_filename = f"live_scan_{ticker}_m{m}_{run_timestamp}.log"
        log_path = os.path.join(LOG_DIR, log_filename)
        log_files[m] = log_path
        
        command = [
            "python3",
            MASTER_SCANNER_PATH,
            "--ticker", ticker,
            "--start", start_date,
            "--end", end_date,
            "--m", str(m),
            "--logfile", log_filename
        ]
        
        print(f"   > Launching m={m:<3} detector...", end="", flush=True)
        
        try:
            p = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            processes.append(p)
            print(f" {Fore.GREEN}[STARTED]")
        except Exception as e:
            print(f" {Fore.RED}[FAILED: {e}]")

    # 2. WAIT FOR COMPLETION
    print(f"\n{Fore.YELLOW}   ... detectors running ... please wait ...")
    for p in processes:
        p.wait()

    # Stop Timer
    elapsed = time.time() - start_time
    print(f"{Fore.GREEN}   > All detectors finished. (Took: {elapsed:.2f}s)\n")

    # 3. REPORT RESULTS
    print(f"{Fore.WHITE}--- REPORT FOR {ticker} ---")
    print(f"{'M-Value':<8} | {'Verdict':<12} | {'Status':<12} | {'Equity':<12} | {'Stats'}")
    print("-" * 90)

    for m in M_VALUES_TO_RUN:
        verdict, live_status, price, stats, equity = check_log_for_status(log_files[m])
        
        v_color = Fore.WHITE
        if verdict == "PROFITABLE": v_color = Fore.GREEN
        elif verdict == "BLACK SHEEP": v_color = Fore.RED
        elif verdict == "PASSIVE": v_color = Fore.BLUE
        
        s_color = Fore.WHITE
        if live_status: s_color = Fore.MAGENTA + Style.BRIGHT + "LIVE TRADE!"
        else: s_color = "Scanning"

        # Clean up stats string for table
        short_stats = stats.replace("Total Trades", "Trds").replace("Win Rate", "WR").replace("Avg P/L", "Avg")

        print(f"m={m:<6} | {v_color}{verdict:<12}{Style.RESET_ALL} | {s_color:<12}{Style.RESET_ALL} | {Fore.YELLOW}{equity:<12}{Style.RESET_ALL} | {short_stats}")

# --- MAIN EXECUTION ---
def main():
    if not os.path.exists(TARGETS_FILE):
        print(f"{Fore.RED}ERROR: Targets file not found at {TARGETS_FILE}")
        return
        
    with open(TARGETS_FILE, 'r') as f:
        targets = [line.strip().upper() for line in f if line.strip()]
        
    if not targets:
        print(f"{Fore.RED}ERROR: No targets found in targets.txt")
        return

    print(f"{Fore.GREEN}Loaded {len(targets)} targets from file.")
    total_start = time.time()

    # Added enumerate to track index
    for i, ticker in enumerate(targets, 1):
        try:
            run_parallel_scan(ticker, i, len(targets))
        except KeyboardInterrupt:
            print(f"\n{Fore.RED}Scan interrupted by user.")
            sys.exit()
        except Exception as e:
            print(f"{Fore.RED}Error scanning {ticker}: {e}")

    total_time = time.time() - total_start
    print(f"\n{Fore.GREEN}{'='*60}")
    print(f"{Fore.GREEN}FULL SCAN COMPLETED in {total_time:.2f} seconds.")
    print(f"{Fore.GREEN}{'='*60}")

if __name__ == "__main__":
    main()