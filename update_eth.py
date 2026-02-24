import os

# --- Update deribit_executor.py ---
with open('CRYPTO_EXECUTION_ENGINE/deribit_executor.py', 'r') as f:
    executor_content = f.read()

executor_content = executor_content.replace(
    'def get_all_positions(self):',
    'def get_all_positions(self, currency="BTC"):'
).replace(
    'params = {"currency": "BTC", "kind": "any"}',
    'params = {"currency": currency, "kind": "any"}'
)

with open('CRYPTO_EXECUTION_ENGINE/deribit_executor.py', 'w') as f:
    f.write(executor_content)


# --- 1. crypto_casino_entry_ETH.py ---
with open('CRYPTO_EXECUTION_ENGINE/crypto_casino_entry.py', 'r') as f:
    content = f.read()

content = content.replace('"BTC"', '"ETH"')
content = content.replace("'BTC'", "'ETH'")
content = content.replace("BTC-PERPETUAL", "ETH-PERPETUAL")
content = content.replace("BTC contracts", "ETH contracts")
content = content.replace("BTC Options", "ETH Options")
content = content.replace("0.1 # BTC", "1.0 # ETH")
content = content.replace("CONTRACTS_TO_BUY = 0.1", "CONTRACTS_TO_BUY = 1.0")
content = content.replace("crypto_state.json", "eth_state.json")
content = content.replace("CRYPTO CASINO ENTRY", "ETH CASINO ENTRY")

with open('CRYPTO_EXECUTION_ENGINE/crypto_casino_entry_ETH.py', 'w') as f:
    f.write(content)


# --- 2. crypto_dynamic_hedger_ETH.py ---
with open('CRYPTO_EXECUTION_ENGINE/crypto_dynamic_hedger.py', 'r') as f:
    content = f.read()

content = content.replace("BTC-PERPETUAL", "ETH-PERPETUAL")
content = content.replace("BTC Option", "ETH Option")
content = content.replace("BTC Delta", "ETH Delta")
content = content.replace("Delta (BTC)", "Delta (ETH)")
content = content.replace("Net Delta (BTC)", "Net Delta (ETH)")
content = content.replace("total_position_delta_btc", "total_position_delta_eth")
content = content.replace("delta_per_btc", "delta_per_eth")
content = content.replace("opt_mark_btc", "opt_mark_eth")
content = content.replace("pnl_btc", "pnl_eth")
content = content.replace("crypto_state.json", "eth_state.json")
content = content.replace("CRYPTO DYNAMIC HEDGER", "ETH DYNAMIC HEDGER")
content = content.replace("HEDGE_THRESHOLD_USD = 150.0", "HEDGE_THRESHOLD_USD = 50.0")

# Adjust rounding logic
content = content.replace("target_usd = round(target_usd / 10.0) * 10.0", "target_usd = round(target_usd / 1.0) * 1.0")
content = content.replace("multiples of 10.", "multiples of 1.")
content = content.replace("increments of $10 USD.", "increments of $1 USD.")
content = content.replace("bot.get_all_positions()", "bot.get_all_positions(currency='ETH')")

# Other 'BTC' replacements
content = content.replace('"BTC"', '"ETH"')
content = content.replace("'BTC'", "'ETH'")

with open('CRYPTO_EXECUTION_ENGINE/crypto_dynamic_hedger_ETH.py', 'w') as f:
    f.write(content)


# --- 3. crypto_investment_reporter_ETH.py ---
with open('CRYPTO_EXECUTION_ENGINE/crypto_investment_reporter.py', 'r') as f:
    content = f.read()

content = content.replace("BTC-PERPETUAL", "ETH-PERPETUAL")
content = content.replace('"BTC"', '"ETH"')
content = content.replace(" BTC", " ETH")
content = content.replace("avg_price_btc", "avg_price_eth")
content = content.replace("mark_price_btc", "mark_price_eth")
content = content.replace("unrealized_btc", "unrealized_eth")
content = content.replace("equity_btc", "equity_eth")
content = content.replace("realized_btc", "realized_eth")
content = content.replace("CRYPTO PERFORMANCE REPORT", "ETH PERFORMANCE REPORT")
content = content.replace("bot.get_all_positions()", "bot.get_all_positions(currency='ETH')")

with open('CRYPTO_EXECUTION_ENGINE/crypto_investment_reporter_ETH.py', 'w') as f:
    f.write(content)

