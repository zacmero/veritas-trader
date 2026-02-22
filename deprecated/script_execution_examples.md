source venv/bin/activate

# --- Test 1: NVAX (The Biotech Bubble) ---
python3 BACKTESTER/trading_simulator.py --ticker "NVAX" --start "2018-01-01" --end "2023-01-01" --m 15 --logfile "final_suite_NVAX_m15.log"
python3 BACKTESTER/trading_simulator.py --ticker "NVAX" --start "2018-01-01" --end "2023-01-01" --m 30 --logfile "final_suite_NVAX_m30.log"
python3 BACKTESTER/trading_simulator.py --ticker "NVAX" --start "2018-01-01" --end "2023-01-01" --m 60 --logfile "final_suite_NVAX_m60.log"

# --- Test 2: RIVN (The Post-IPO Bubble) ---
python3 BACKTESTER/trading_simulator.py --ticker "RIVN" --start "2021-11-10" --end "2023-01-01" --m 15 --logfile "final_suite_RIVN_m15.log"
python3 BACKTESTER/trading_simulator.py --ticker "RIVN" --start "2021-11-10" --end "2023-01-01" --m 30 --logfile "final_suite_RIVN_m30.log"

# --- Test 3: XOM (The Cyclical Non-Bubble) ---
python3 BACKTESTER/trading_simulator.py --ticker "XOM" --start "2018-01-01" --end "2023-01-01" --m 30 --logfile "final_suite_XOM_m30.log"
python3 BACKTESTER/trading_simulator.py --ticker "XOM" --start "2018-01-01" --end "2023-01-01" --m 60 --logfile "final_suite_XOM_m60.log"
python3 BACKTESTER/trading_simulator.py --ticker "XOM" --start "2018-01-01" --end "2023-01-01" --m 90 --logfile "final_suite_XOM_m90.log"

# --- Test 4: WM (The "Boring" Non-Bubble) ---
python3 BACKTESTER/trading_simulator.py --ticker "WM" --start "2018-01-01" --end "2023-01-01" --m 30 --logfile "final_suite_WM_m30.log"
python3 BACKTESTER/trading_simulator.py --ticker "WM" --start "2018-01-01" --end "2023-01-01" --m 60 --logfile "final_suite_WM_m60.log"
python3 BACKTESTER/trading_simulator.py --ticker "WM" --start "2018-01-01" --end "2023-01-01" --m 90 --logfile "final_suite_WM_m90.log"