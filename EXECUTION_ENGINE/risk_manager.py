"""
Veritas Trader - Risk & Time Manager
------------------------------------
Handles market hours validation and expiration risk (Gamma Risk).
Strictly operates using US Eastern Time (America/New_York).
"""

from datetime import datetime, timedelta
import pytz

# Alpaca Extended Hours: 4:00 AM to 8:00 PM ET
MARKET_OPEN_HOUR = 4
MARKET_CLOSE_HOUR = 20
MIN_DAYS_TO_EXPIRY = 2

def get_eastern_time() -> datetime:
    """Returns the current time in US Eastern Time."""
    utc_now = datetime.now(pytz.utc)
    eastern = pytz.timezone('America/New_York')
    return utc_now.astimezone(eastern)

def is_hedging_window_open() -> bool:
    """
    Checks if the current time is within the allowed trading window 
    (Monday-Friday, 4:00 AM to 8:00 PM ET).
    """
    et_now = get_eastern_time()
    
    # Check if it's the weekend (5 = Saturday, 6 = Sunday)
    if et_now.weekday() >= 5:
        return False
        
    # Check if within hours
    if MARKET_OPEN_HOUR <= et_now.hour < MARKET_CLOSE_HOUR:
        return True
        
    return False

def is_expiration_danger(expiry_date: datetime) -> bool:
    """
    Checks if an option is too close to expiration.
    Options near expiration have explosive Gamma, making Delta hedging dangerous and unprofitable.
    """
    # Ensure expiry_date is timezone aware (assume ET for OCC standard)
    if expiry_date.tzinfo is None:
        eastern = pytz.timezone('America/New_York')
        expiry_date = eastern.localize(expiry_date)
        
    et_now = get_eastern_time()
    days_left = (expiry_date - et_now).days
    
    return days_left <= MIN_DAYS_TO_EXPIRY