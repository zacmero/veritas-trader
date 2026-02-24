"""
Veritas Trader - Crypto Risk Manager
------------------------------------
Handles the 3 core Stop Losses for Gamma Scalping:
1. Time Stop (Gamma Risk)
2. Volatility Stop (IV Crush Risk)
3. Hard Equity Stop (Flash Crash / Slippage Risk)
"""
from datetime import datetime
import pytz

MIN_DAYS_TO_EXPIRY = 2
MAX_ENTRY_IV = 0.90  # Increased to 90% to accommodate ETH's higher natural volatility
MAX_DRAWDOWN_PCT = -0.15 # Liquidate if portfolio drops 15% (Hard Equity Stop)

def is_expiration_danger(expiry_date: datetime) -> bool:
    """TIME STOP: Checks if an option is within 48 hours of expiration."""
    if expiry_date.tzinfo is None:
        expiry_date = pytz.utc.localize(expiry_date)
    days_left = (expiry_date - datetime.now(pytz.utc)).days
    return days_left <= MIN_DAYS_TO_EXPIRY

def is_iv_too_high(current_iv: float) -> bool:
    """VOLATILITY STOP: Prevents buying options when insurance is overpriced."""
    return current_iv > MAX_ENTRY_IV

def check_equity_stop(initial_cost: float, current_value: float) -> bool:
    """HARD EQUITY STOP: Triggers if the combined Option + Hedge value drops too far."""
    if initial_cost <= 0: return False
    drawdown = (current_value - initial_cost) / initial_cost
    return drawdown <= MAX_DRAWDOWN_PCT