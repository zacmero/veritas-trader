### **4. Commands to Build the "Sell" Library Today**

Let's build our initial `SELL_ARCHETYPE_LIBRARY` using the historical data from our most famous bubble successes. We will use the `m` value that was most successful in the original backtests for each.

**Instructions:**
1.  Create the `generate_sell_archetypes.py` script.
2.  Run these commands from your `BACKTESTER/` directory.

```bash
# Activate your environment
source ../venv/bin/activate

# --- Generate SELL Archetypes from our Greatest Hits ---

# GME (The King)
python3 generate_sell_archetypes.py --ticker "GME" --start "2018-01-01" --end "2023-01-01" --m 90

# NVAX (The Biotech Bubble)
python3 generate_sell_archetypes.py --ticker "NVAX" --start "2018-01-01" --end "2023-01-01" --m 15

# PTON (The COVID Darling)
python3 generate_sell_archetypes.py --ticker "PTON" --start "2019-09-26" --end "2023-01-01" --m 15

# MRNA (The Other Vaccine Bubble)
python3 generate_sell_archetypes.py --ticker "MRNA" --start "2019-01-01" --end "2023-01-01" --m 30

# BB (The Meme Stock)
python3 generate_sell_archetypes.py --ticker "BB" --start "2018-01-01" --end "2023-01-01" --m 60

# TSLA (The Classic Bubble)
python3 generate_sell_archetypes.py --ticker "TSLA" --start "2018-01-01" --end "2023-01-01" --m 15
```

