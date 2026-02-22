import pandas as pd
import os

def get_nasdaq_symbols():
    print("Fetching NASDAQ symbols...")
    try:
        url = "http://www.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt"
        df = pd.read_csv(url, sep="|")
        
        # 1. Remove Test Issues (Test Issue == 'N')
        # 2. Remove ETFs (ETF == 'N') - Optional, but keeps it to companies
        df = df[(df['Test Issue'] == 'N') & (df['ETF'] == 'N')]
        
        # 3. Remove Warrants, Units, Preferreds, Rights, Notes
        # We look at the 'Security Name' column for keywords to ban
        junk_keywords = ['Warrant', 'Unit', 'Preferred', 'Right', 'Note', 'Debenture']
        pattern = '|'.join(junk_keywords)
        
        # Keep only rows where Security Name does NOT contain the junk keywords
        df_clean = df[~df['Security Name'].str.contains(pattern, case=False, na=False)]
        
        symbols = df_clean['Symbol'].tolist()
        print(f"Raw count: {len(df)}. Cleaned Common Stock count: {len(symbols)}")
        return symbols
    except Exception as e:
        print(f"Error fetching symbols: {e}")
        return []

def main():
    symbols = get_nasdaq_symbols()
    
    if not symbols:
        return

    # Save to quickstrike_targets.txt
    # Ensure the directory exists
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, "quickstrike_targets.txt")
    
    with open(file_path, "w") as f:
        for sym in symbols:
            f.write(f"{sym}\n")
            
    print(f"Saved {len(symbols)} targets to {file_path}")

if __name__ == "__main__":
    main()