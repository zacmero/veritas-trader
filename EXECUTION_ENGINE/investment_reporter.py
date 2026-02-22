import os
import pandas as pd
import re
from datetime import datetime, timedelta
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide
from .utils import load_env_file
from colorama import init, Fore, Style

init(autoreset=True)

BASE_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_FILE = os.path.join(BASE_PATH, "EXECUTION_ENGINE", "investment_report.txt")
PORTFOLIO_FILE = os.path.join(BASE_PATH, "EXECUTION_ENGINE", "portfolio.csv")
HISTORY_FILE = os.path.join(BASE_PATH, "EXECUTION_ENGINE", "trade_history.csv")

def main():
    load_env_file()
    print(f"{Fore.CYAN}--- [INVESTMENT REPORT GENERATOR (Grand Auditor)] ---")
    
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    
    try:
        client = TradingClient(api_key, secret_key, paper=True)
        account = client.get_account()
        
        # --- 1. REBUILD/RECONCILE TRADE HISTORY FROM ALPACA --- 
        print(f"{Fore.YELLOW}Reconciling trade history from Alpaca...{Style.RESET_ALL}")
        
        # Fetch ALL FILLS
        all_activities = []
        page_token = None
        while True:
            params = {
                "activity_types": "FILL",
                "direction": "asc", 
                "page_size": 100 
            }
            if page_token: params['page_token'] = page_token
            
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
            time = act.get('transaction_time', '').split('.')[0].replace('T', ' ')
            
            if symbol not in inventory: inventory[symbol] = []
            
            if side == 'buy':
                inventory[symbol].append({'qty': qty, 'price': price})
            elif side == 'sell':
                shares_to_sell = qty
                cost_basis = 0.0
                matched_qty = 0.0
                
                while shares_to_sell > 0.0001 and inventory[symbol]:
                    buy_batch = inventory[symbol][0]
                    if buy_batch['qty'] <= shares_to_sell:
                        cost_basis += buy_batch['qty'] * buy_batch['price']
                        matched_qty += buy_batch['qty']
                        shares_to_sell -= buy_batch['qty']
                        inventory[symbol].pop(0)
                    else:
                        cost_basis += shares_to_sell * buy_batch['price']
                        matched_qty += shares_to_sell
                        buy_batch['qty'] -= shares_to_sell
                        shares_to_sell = 0
                
                if matched_qty > 0:
                    avg_entry = cost_basis / matched_qty
                    pl_dollars = (price - avg_entry) * matched_qty
                    pl_percent = ((price - avg_entry) / avg_entry) * 100
                    ledger.append({
                        'Ticker': symbol,
                        'ExitDate': time,
                        'EntryPrice': round(avg_entry, 2),
                        'ExitPrice': round(price, 2),
                        'Qty': matched_qty,
                        'PL_Dollars': round(pl_dollars, 2),
                        'PL_Percent': round(pl_percent, 2),
                        'ExitReason': "Alpaca Fill",
                        'M_List': "N/A"
                    })
                
                if shares_to_sell > 0.0001:
                    ledger.append({
                        'Ticker': symbol,
                        'ExitDate': time,
                        'EntryPrice': "N/A",
                        'ExitPrice': round(price, 2),
                        'Qty': shares_to_sell,
                        'PL_Dollars': round(shares_to_sell * price, 2), # Gross Proceeds
                        'PL_Percent': "N/A",
                        'ExitReason': "Alpaca Fill (Unmatched)",
                        'M_List': "N/A"
                    })

        df_ledger = pd.DataFrame(ledger)
        
        # 3. AGGREGATION LOGIC
        if not df_ledger.empty:
            df_ledger['ExitDateObj'] = pd.to_datetime(df_ledger['ExitDate'])
            df_ledger['Day'] = df_ledger['ExitDateObj'].dt.floor('D') 
            df_ledger['IsUnmatched'] = df_ledger['EntryPrice'] == "N/A"
            
            def aggregate_trades(x):
                total_qty = x['Qty'].sum()
                avg_exit = (x['ExitPrice'] * x['Qty']).sum() / total_qty
                
                is_unmatched = x.name[2]
                
                if is_unmatched:
                    avg_entry = "N/A"
                    total_pl = x['PL_Dollars'].sum()
                    pl_pct = "N/A"
                else:
                    avg_entry = (x['EntryPrice'] * x['Qty']).sum() / total_qty
                    total_pl = x['PL_Dollars'].sum()
                    pl_pct = ((avg_exit - avg_entry) / avg_entry) * 100
                
                return pd.Series({
                    'EntryPrice': round(avg_entry, 2) if avg_entry != "N/A" else "N/A",
                    'ExitPrice': round(avg_exit, 2),
                    'Qty': total_qty,
                    'PL_Dollars': round(total_pl, 2),
                    'PL_Percent': round(pl_pct, 2) if pl_pct != "N/A" else "N/A",
                    'ExitDate': x['ExitDate'].max(),
                    'ExitReason': x['ExitReason'].iloc[0],
                    'Ticker': x.name[0] # Retrieve from grouping key
                })

            df_agg = df_ledger.groupby(['Ticker', 'Day', 'IsUnmatched']).apply(aggregate_trades).reset_index(drop=True)
            
            df_agg.sort_values(by='ExitDate', ascending=False, inplace=True)
            df_agg.to_csv(HISTORY_FILE, index=False)
            print(f"Ledger aggregated: {len(df_agg)} trades (condensed from {len(df_ledger)} fills).")
            full_ledger = df_agg
        else:
            full_ledger = pd.DataFrame()

        # --- REPORTING ---
        positions = client.get_all_positions()
        portfolio_map = {}
        if os.path.exists(PORTFOLIO_FILE):
            try:
                pf_df = pd.read_csv(PORTFOLIO_FILE)
                for _, row in pf_df.iterrows():
                    portfolio_map[row['Ticker']] = row.get('M_List', 'N/A')
            except: pass

        start_equity = float(account.last_equity)
        current_equity = float(account.equity)
        day_pl = current_equity - start_equity
        day_pl_pct = (day_pl / start_equity) * 100.0 if start_equity > 0 else 0.0
        
        lifetime_pl = 0.0
        win_rate = 0.0
        total_trades = 0
        
        if not full_ledger.empty:
            valid_trades = full_ledger[full_ledger['PL_Percent'] != 'N/A']
            if not valid_trades.empty:
                lifetime_pl = valid_trades['PL_Dollars'].sum()
                wins = len(valid_trades[valid_trades['PL_Dollars'] > 0])
                total_trades = len(valid_trades)
                win_rate = (wins / total_trades) * 100.0

        report = f"""
============================================================
              ALGORITHMIC TRADING REPORT
============================================================
Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Account ID:     {account.account_number}
Status:         {account.status}
Buying Power:   ${float(account.buying_power):,.2f}
Equity:         ${current_equity:,.2f}
------------------------------------------------------------
DAY P/L:        ${day_pl:,.2f} ({day_pl_pct:+.2f}%)
LIFETIME P/L:   ${lifetime_pl:,.2f} (Realized - Verified)
WIN RATE:       {win_rate:.1f}% ({total_trades} Verified Trades)
============================================================

--- [OPEN POSITIONS (Active)] ---
{'Symbol':<6} | {'M':<8} | {'Qty':<8} | {'Entry':<8} | {'Current':<8} | {'P/L %'}
{'--'*40}
"""
        if not positions: report += "No open positions.\n"
        else:
            for p in positions:
                pl_pct = float(p.unrealized_plpc) * 100
                c = Fore.GREEN if pl_pct > 0 else Fore.RED
                m_val = str(portfolio_map.get(p.symbol, "?"))
                report += f"{p.symbol:<6} | {m_val:<8} | {float(p.qty):<8} | ${float(p.avg_entry_price):<7.2f} | ${float(p.current_price):<7.2f} | {c}{pl_pct:+.2f}%{Style.RESET_ALL}\n"

        report += "\n--- [CLOSED TRADES (FIFO - Daily Aggregated)] ---\n"
        report += f"{'Symbol':<6} | {'Entry':<8} | {'Exit':<8} | {'Qty':<8} | {'P/L $':<10} | {'P/L %':<8} | {'Time'}\n"
        report += f"{'--'*42}\n"
        
        if not full_ledger.empty:
            full_ledger_sorted = full_ledger.sort_values(by='Ticker')
            for _, row in full_ledger_sorted.iterrows():
                pl_d = row['PL_Dollars']
                pl_pct_val = row['PL_Percent']
                exit_time = str(row['ExitDate'])
                
                is_gross = (pl_pct_val == 'N/A')
                
                try:
                    pl_dol_f = float(pl_d)
                    if is_gross:
                        c = Fore.BLUE 
                        pl_str = f"${pl_dol_f:.2f} (Val)"
                        pct_str = "N/A"
                    else:
                        c = Fore.GREEN if pl_dol_f > 0 else Fore.RED
                        pl_str = f"${pl_dol_f:.2f}"
                        pct_str = f"{float(pl_pct_val):+.2f}%"
                except:
                    c = Fore.WHITE
                    pl_str = str(pl_d)
                    pct_str = str(pl_pct_val)

                report += f"{row['Ticker']:<6} | {str(row['EntryPrice']):<8} | ${row['ExitPrice']:<8} | {float(row['Qty']):<8.2f} | {c}{pl_str:<10}{Style.RESET_ALL} | {c}{pct_str:<8}{Style.RESET_ALL} | {exit_time}\n"
        else:
            report += "No closed trades.\n"

        print(report)
        
        clean = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])').sub('', report)
        with open(REPORT_FILE, "w") as f: f.write(clean)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
