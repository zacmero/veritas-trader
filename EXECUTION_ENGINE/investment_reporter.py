"""
Veritas Trader - Investment Reporter (The Accountant)
-----------------------------------------------------
Reconstructs Trade History using FIFO matching, supporting both
Long and Short positions, and handles Options Multipliers (x100).
Aggregates daily hedging trades to keep the report clean.
Outputs a formatted report using tabulate and colorama.
"""

import os
import re
import pandas as pd
from datetime import datetime
from alpaca.trading.client import TradingClient
from tabulate import tabulate
from colorama import init, Fore, Style

from .utils import load_env_file

init(autoreset=True)

BASE_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_FILE = os.path.join(BASE_PATH, "EXECUTION_ENGINE", "investment_report.txt")
HISTORY_FILE = os.path.join(BASE_PATH, "EXECUTION_ENGINE", "trade_history.csv")

def parse_occ_symbol(occ_symbol: str) -> dict:
    """Parses a standard OCC option symbol into its components."""
    match = re.match(r'^([A-Z]{1,6})(\d{6})([CP])(\d{8})$', occ_symbol)
    if not match:
        return None
        
    ticker = match.group(1)
    date_str = match.group(2)
    opt_type_str = match.group(3)
    strike_str = match.group(4)
    
    expiry_date = datetime.strptime(date_str, "%y%m%d")
    opt_type = "Call" if opt_type_str == 'C' else "Put"
    strike_price = float(strike_str) / 1000.0
    
    return {
        "underlying": ticker,
        "expiry": expiry_date,
        "type": opt_type,
        "strike": strike_price
    }

def format_symbol(symbol: str) -> str:
    """Converts OCC symbol to human readable format, or returns stock ticker."""
    occ_data = parse_occ_symbol(symbol)
    if occ_data:
        date_fmt = occ_data["expiry"].strftime("%m/%d")
        return f"{occ_data['underlying']} ${occ_data['strike']:g} {occ_data['type']} ({date_fmt})"
    return symbol

def main():
    load_env_file()
    print(f"{Fore.CYAN}--- [INVESTMENT REPORT GENERATOR (Grand Auditor)] ---{Style.RESET_ALL}")
    
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    
    try:
        client = TradingClient(api_key, secret_key, paper=True)
        account = client.get_account()
        
        print(f"{Fore.YELLOW}Reconciling trade history from Alpaca...{Style.RESET_ALL}")
        
        # 1. Fetch Fills
        all_activities = []
        page_token = None
        while True:
            params = {
                "activity_types": "FILL",
                "direction": "asc", 
                "page_size": 100 
            }
            if page_token: params['page_token'] = page_token
            
            # Use raw request as SDK might lack some parameters in the helper methods
            activities = client.get("/account/activities", params)
            if not activities: break
                
            all_activities.extend(activities)
            if len(activities) < 100: break
            page_token = activities[-1]['id']
            
        print(f"Total Fills Fetched: {len(all_activities)}")
        
        # 2. FIFO Reconstruction
        inventory = {} 
        ledger = []
        
        for act in all_activities:
            if act.get('activity_type') != 'FILL': continue
            symbol = act.get('symbol')
            side = act.get('side')
            qty = float(act.get('qty'))
            price = float(act.get('price'))
            time_str = act.get('transaction_time', '').split('.')[0].replace('T', ' ')
            
            is_option = parse_occ_symbol(symbol) is not None
            multiplier = 100.0 if is_option else 1.0
            
            if symbol not in inventory:
                inventory[symbol] = []
                
            shares_to_match = qty
            cost_basis = 0.0
            matched_qty = 0.0
            
            while shares_to_match > 0.0001 and inventory[symbol] and inventory[symbol][0]['side'] != side:
                opp_batch = inventory[symbol][0]
                match_amount = min(shares_to_match, opp_batch['qty'])
                
                cost_basis += match_amount * opp_batch['price']
                matched_qty += match_amount
                
                opp_batch['qty'] -= match_amount
                shares_to_match -= match_amount
                
                if opp_batch['qty'] <= 0.0001:
                    inventory[symbol].pop(0)
                    
            if matched_qty > 0:
                avg_entry = cost_basis / matched_qty
                
                if side == 'sell': # Closing a LONG
                    pl_dollars = (price - avg_entry) * matched_qty * multiplier
                    pl_percent = ((price - avg_entry) / avg_entry) * 100 if avg_entry > 0 else 0
                    trade_type = "Long"
                else: # Closing a SHORT (side == 'buy')
                    pl_dollars = (avg_entry - price) * matched_qty * multiplier
                    pl_percent = ((avg_entry - price) / avg_entry) * 100 if avg_entry > 0 else 0
                    trade_type = "Short"
                    
                ledger.append({
                    'Ticker': symbol,
                    'ReadableSymbol': format_symbol(symbol),
                    'Type': trade_type,
                    'ExitDate': time_str,
                    'EntryPrice': avg_entry,
                    'ExitPrice': price,
                    'Qty': matched_qty,
                    'PL_Dollars': pl_dollars,
                    'PL_Percent': pl_percent,
                    'IsOption': is_option
                })
                
            if shares_to_match > 0.0001:
                inventory[symbol].append({'side': side, 'qty': shares_to_match, 'price': price})

        df_ledger = pd.DataFrame(ledger)
        
        # 3. AGGREGATION LOGIC (Aggregate by Ticker, Date, and Type)
        if not df_ledger.empty:
            df_ledger['ExitDateObj'] = pd.to_datetime(df_ledger['ExitDate'])
            df_ledger['Day'] = df_ledger['ExitDateObj'].dt.floor('D') 
            
            agg_list = []
            for name, group in df_ledger.groupby(['Ticker', 'Day', 'Type']):
                total_qty = group['Qty'].sum()
                # Weighted averages
                avg_entry = (group['EntryPrice'] * group['Qty']).sum() / total_qty
                avg_exit = (group['ExitPrice'] * group['Qty']).sum() / total_qty
                total_pl = group['PL_Dollars'].sum()
                
                if name[2] == 'Long':
                    pl_pct = ((avg_exit - avg_entry) / avg_entry) * 100 if avg_entry > 0 else 0
                else:
                    pl_pct = ((avg_entry - avg_exit) / avg_entry) * 100 if avg_entry > 0 else 0
                    
                agg_list.append({
                    'Ticker': name[0],
                    'ReadableSymbol': format_symbol(name[0]),
                    'Type': name[2],
                    'EntryPrice': avg_entry,
                    'ExitPrice': avg_exit,
                    'Qty': total_qty,
                    'PL_Dollars': total_pl,
                    'PL_Percent': pl_pct,
                    'ExitDate': group['ExitDate'].max()
                })
                
            df_agg = pd.DataFrame(agg_list)
            df_agg.sort_values(by='ExitDate', ascending=False, inplace=True)
            df_agg.to_csv(HISTORY_FILE, index=False)
            print(f"Ledger aggregated: {len(df_agg)} trades (condensed from {len(df_ledger)} fills).")
            full_ledger = df_agg
        else:
            full_ledger = pd.DataFrame()

        # --- REPORTING ---
        positions = client.get_all_positions()

        start_equity = float(account.last_equity)
        current_equity = float(account.equity)
        day_pl = current_equity - start_equity
        day_pl_pct = (day_pl / start_equity) * 100.0 if start_equity > 0 else 0.0
        
        lifetime_pl = 0.0
        win_rate = 0.0
        total_trades = 0
        
        if not full_ledger.empty:
            lifetime_pl = full_ledger['PL_Dollars'].sum()
            wins = len(full_ledger[full_ledger['PL_Dollars'] > 0])
            total_trades = len(full_ledger)
            win_rate = (wins / total_trades) * 100.0 if total_trades > 0 else 0.0

        # Header
        report = []
        report.append("============================================================")
        report.append("              VERITAS TRADER: ALGORITHMIC REPORT            ")
        report.append("============================================================")
        report.append(f"Date:           {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Account ID:     {account.account_number}")
        report.append(f"Status:         {account.status}")
        report.append(f"Buying Power:   ${float(account.buying_power):,.2f}")
        report.append(f"Equity:         ${current_equity:,.2f}")
        report.append("------------------------------------------------------------")
        
        c_day = Fore.GREEN if day_pl >= 0 else Fore.RED
        report.append(f"DAY P/L:        {c_day}${day_pl:,.2f} ({day_pl_pct:+.2f}%){Style.RESET_ALL}")
        
        c_life = Fore.GREEN if lifetime_pl >= 0 else Fore.RED
        report.append(f"LIFETIME P/L:   {c_life}${lifetime_pl:,.2f}{Style.RESET_ALL} (Realized)")
        report.append(f"WIN RATE:       {win_rate:.1f}% ({total_trades} Verified Trades)")
        report.append("============================================================\n")

        # Open Positions
        report.append("--- [OPEN POSITIONS (Active)] ---")
        pos_table = []
        if not positions:
            report.append("No open positions.\n")
        else:
            for p in positions:
                sym_fmt = format_symbol(p.symbol)
                qty = float(p.qty)
                pos_type = "Long" if qty > 0 else "Short"
                entry_p = float(p.avg_entry_price)
                curr_p = float(p.current_price)
                pl_pct = float(p.unrealized_plpc) * 100
                
                # Alpaca provides unrealized_pl which already includes multipliers for options
                pl_dollars = float(p.unrealized_pl)
                
                c = Fore.GREEN if pl_pct >= 0 else Fore.RED
                pl_str = f"{c}{pl_pct:+.2f}%{Style.RESET_ALL}"
                
                pos_table.append([
                    sym_fmt, pos_type, abs(qty), f"${entry_p:.2f}", f"${curr_p:.2f}", 
                    f"{c}${pl_dollars:.2f}{Style.RESET_ALL}", pl_str
                ])
                
            report.append(tabulate(pos_table, headers=["Symbol", "Type", "Qty", "Entry", "Current", "P/L $", "P/L %"], tablefmt="simple"))
            report.append("\n")

        # Closed Trades
        report.append("--- [CLOSED TRADES (FIFO - Daily Aggregated)] ---")
        trd_table = []
        if not full_ledger.empty:
            for _, row in full_ledger.iterrows():
                pl_d = float(row['PL_Dollars'])
                pl_p = float(row['PL_Percent'])
                
                c = Fore.GREEN if pl_d >= 0 else Fore.RED
                pl_d_str = f"{c}${pl_d:,.2f}{Style.RESET_ALL}"
                pl_p_str = f"{c}{pl_p:+.2f}%{Style.RESET_ALL}"
                
                # Truncate time to just date and hour/min for cleaner look
                trd_time = row['ExitDate'][:16] 
                
                trd_table.append([
                    row['ReadableSymbol'], row['Type'], f"${row['EntryPrice']:.2f}", f"${row['ExitPrice']:.2f}", 
                    f"{row['Qty']:.2f}", pl_d_str, pl_p_str, trd_time
                ])
                
            report.append(tabulate(trd_table, headers=["Symbol", "Type", "Entry", "Exit", "Qty", "P/L $", "P/L %", "Time"], tablefmt="simple"))
            report.append("\n")
        else:
            report.append("No closed trades.\n")

        final_output = "\n".join(report)
        print(final_output)
        
        # Save clean version without ANSI colors to file
        clean = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])').sub('', final_output)
        with open(REPORT_FILE, "w") as f:
            f.write(clean)

    except Exception as e:
        print(f"{Fore.RED}Report Error: {e}{Style.RESET_ALL}")

if __name__ == "__main__":
    main()
