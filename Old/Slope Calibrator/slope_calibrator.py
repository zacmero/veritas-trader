import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def calculate_percentage_growth(series):
    """Calculates the total percentage growth of a time series."""
    if series.empty or len(series) < 2:
        return 0.0
    
    # Ensure we are working with raw numpy arrays to avoid pandas ambiguity
    values = series.to_numpy()
    start_price = values[0]
    end_price = values[-1]
    
    if start_price == 0:
        return np.inf
        
    return ((end_price - start_price) / start_price) * 100.0

def main():
    # --- Task 1: Calculate Growth for True Bubbles ---
    ARCHETYPE_DATA = [
        {'name': 'GME', 'ticker': 'GME', 'start_date': '2020-11-09'},
        {'name': 'AMC', 'ticker': 'AMC', 'start_date': '2021-02-09'},
        {'name': 'VWAGY', 'ticker': 'VWAGY', 'start_date': '2008-10-17'},
        {'name': 'CSCO', 'ticker': 'CSCO', 'start_date': '1999-10-25'},
        {'name': 'IYR', 'ticker': 'IYR', 'start_date': '2006-02-03'},
        {'name': 'SSYS', 'ticker': 'SSYS', 'start_date': '2013-10-31'},
        {'name': 'DOGE-USD', 'ticker': 'DOGE-USD', 'start_date': '2021-01-28'},
        {'name': 'SHIB-USD', 'ticker': 'SHIB-USD', 'start_date': '2021-10-24'},
    ]

    print("--- Calculating 30-Day % Growth for True Bubbles ---")
    true_bubble_growths = []
    for archetype in ARCHETYPE_DATA:
        start_date_dt = datetime.strptime(archetype['start_date'], '%Y-%m-%d')
        end_date_dt = start_date_dt + timedelta(days=90)
        
        data = yf.download(archetype['ticker'], start=start_date_dt, end=end_date_dt, progress=False)
        
        ramp_data = data[data.index >= start_date_dt].head(30)
        
        if not ramp_data.empty:
            growth = calculate_percentage_growth(ramp_data['Close'])
            true_bubble_growths.append({'Asset/Date': archetype['name'], '30-Day % Growth': float(growth)})
            print(f"{archetype['name']} 30-Day % Growth: {float(growth):.2f}%")
        else:
            print(f"Could not find data for {archetype['name']} at or after {archetype['start_date']}")

    # --- Task 2: Calculate Growth for False Positives ---
    FALSE_POSITIVE_DATES = [
        '2018-10-10', '2019-03-21', '2019-08-13', '2019-12-06',
        '2020-07-02', '2021-04-14', '2021-07-09', '2019-03-15',
        '2019-11-08', '2020-08-13',
    ]

    print("\n--- Calculating 30-Day % Growth for False Positives ---")
    ko_data = yf.download('KO', start='2017-01-01', end='2023-01-01', progress=False)
    false_positive_growths = []

    for date_str in FALSE_POSITIVE_DATES:
        start_date_dt = datetime.strptime(date_str, '%Y-%m-%d')
        ramp_data = ko_data[ko_data.index >= start_date_dt].head(30)

        if not ramp_data.empty:
            growth = calculate_percentage_growth(ramp_data['Close'])
            false_positive_growths.append({'Asset/Date': f"KO {date_str}", '30-Day % Growth': float(growth)})
            print(f"KO {date_str} 30-Day % Growth: {float(growth):.2f}%")
        else:
            print(f"Could not find data for KO at or after {date_str}")


    # --- Deliverable: Final Summary Table ---
    print("\n\n--- Final Summary Table ---")
    
    true_bubbles_df = pd.DataFrame(true_bubble_growths)
    true_bubbles_df['Category'] = 'True Bubbles'
    
    false_positives_df = pd.DataFrame(false_positive_growths)
    false_positives_df['Category'] = 'False Positives'
    
    summary_df = pd.concat([true_bubbles_df, false_positives_df], ignore_index=True)
    summary_df = summary_df[['Category', 'Asset/Date', '30-Day % Growth']]
    
    print(summary_df.to_markdown(index=False))

if __name__ == "__main__":
    main()