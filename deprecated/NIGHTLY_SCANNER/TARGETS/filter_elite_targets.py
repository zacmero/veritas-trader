import yfinance as yf
import os

def filter_targets():
    base_path = os.path.dirname(os.path.abspath(__file__))
    input_file = os.path.join(base_path, "quickstrike_targets.txt")
    output_file = os.path.join(base_path, "elite_targets.txt")
    
    with open(input_file, 'r') as f:
        targets = [line.strip() for line in f if line.strip()]
        
    print(f"Filtering {len(targets)} targets (Price > $2, Vol > 500k)...")
    
    elite = []
    # Process in chunks to be safe, or just let it run
    # This is slow, run it once!
    for i, ticker in enumerate(targets):
        try:
            # Get just the last day of data
            df = yf.download(ticker, period="1d", progress=False, auto_adjust=True)
            if not df.empty:
                price = float(df['Close'].iloc[0])
                vol = float(df['Volume'].iloc[0])
                
                if price > 2.0 and vol > 500000:
                    elite.append(ticker)
                    print(f"[{i}/{len(targets)}] {ticker}: KEEP (${price:.2f})")
                else:
                    print(f"[{i}/{len(targets)}] {ticker}: DROP")
        except:
            pass
            
    with open(output_file, 'w') as f:
        for t in elite:
            f.write(f"{t}\n")
            
    print(f"Saved {len(elite)} elite targets to {output_file}")

if __name__ == "__main__":
    filter_targets()