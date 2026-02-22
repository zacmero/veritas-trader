import os
import subprocess
from datetime import datetime
from colorama import init, Fore, Style

# --- INITIALIZE COLORAMA ---
init(autoreset=True)

# --- CONFIGURATION ---
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
MASTER_SCANNER_PATH = os.path.join(BASE_PATH, "master_scanner.py")
TARGETS_FILE = os.path.join(BASE_PATH, "targets.txt")
LOG_DIR = os.path.join(BASE_PATH, "LOGS")

# The detectors we want to run in our live scan
M_VALUES_TO_RUN = [15, 30, 60, 90, 120]

def check_log_for_status(log_path):
    """Reads the log file to find the Verdict and Live Status."""
    verdict = "UNKNOWN"
    live_status = False
    entry_price = "N/A"
    
    if not os.path.exists(log_path):
        return "ERROR", False, "N/A"

    with open(log_path, 'r') as f:
        content = f.read()
        
        # Check Verdict
        if "STRATEGY VERDICT: PROFITABLE" in content:
            verdict = "PROFITABLE"
        elif "STRATEGY VERDICT: BLACK SHEEP" in content:
            verdict = "BLACK SHEEP"
        elif "STRATEGY VERDICT: PASSIVE" in content:
            verdict = "PASSIVE"
            
        # Check Live Status
        if "This is a potential LIVE BUY SIGNAL" in content:
            live_status = True
            try:
                price_line = [line for line in content.split('\n') if "Entry Price:" in line]
                if price_line:
                    entry_price = price_line[-1].split(": ")[1]
            except:
                pass

    return verdict, live_status, entry_price

# --- MAIN EXECUTION ---
def main():
    print(f"{Fore.CYAN}--- [Elephant Hunter Live Orchestrator Started] ---")
    
    if not os.path.exists(TARGETS_FILE):
        print(f"{Fore.RED}ERROR: Targets file not found at {TARGETS_FILE}")
        return
        
    with open(TARGETS_FILE, 'r') as f:
        targets = [line.strip().upper() for line in f if line.strip()]
        
    if not targets:
        print(f"{Fore.RED}ERROR: No targets found in targets.txt")
        return

    print(f"{Fore.CYAN}Found {len(targets)} targets to scan.")
    
    # Use a single timestamp for all logs in this run
    run_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    for ticker in targets:
        print(f"\n{Fore.WHITE}{'='*60}")
        print(f"{Fore.WHITE} Scanning: {Style.BRIGHT}{ticker}")
        print(f"{Fore.WHITE}{'='*60}")
        
        # Print Table Header
        print(f"{'M-Value':<8} | {'Verdict':<15} | {'Status':<15} | {'Price'}")
        print("-" * 60)

        for m_value in M_VALUES_TO_RUN:
            # Define dates (Elephant Hunter benefits from deep history)
            start_date = "1990-01-01" 
            end_date = datetime.now().strftime('%Y-%m-%d')
            
            log_filename = f"live_scan_{ticker}_m{m_value}_{run_timestamp}.log"
            log_path = os.path.join(LOG_DIR, log_filename)
            
            command = [
                "python3",
                MASTER_SCANNER_PATH,
                "--ticker", ticker,
                "--start", start_date,
                "--end", end_date,
                "--m", str(m_value),
                "--logfile", log_filename
            ]
            
            try:
                # Run silently so we can print our own table row
                subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                # Check results immediately
                verdict, live_status, price = check_log_for_status(log_path)
                
                # Color coding
                v_color = Fore.WHITE
                if verdict == "PROFITABLE": v_color = Fore.GREEN
                elif verdict == "BLACK SHEEP": v_color = Fore.RED
                elif verdict == "PASSIVE": v_color = Fore.BLUE
                
                s_color = Fore.WHITE
                if live_status: s_color = Fore.MAGENTA + Style.BRIGHT + "LIVE TRADE!"
                else: s_color = "Scanning"

                print(f"m={m_value:<6} | {v_color}{verdict:<15}{Style.RESET_ALL} | {s_color:<15}{Style.RESET_ALL} | {price}")

            except subprocess.CalledProcessError:
                print(f"m={m_value:<6} | {Fore.RED}ERROR EXECUTION FAILED")
            except KeyboardInterrupt:
                print(f"\n{Fore.RED}Scan interrupted by user.")
                return

    print(f"\n{Fore.CYAN}--- [Live Scan Finished] ---")

if __name__ == "__main__":
    main()