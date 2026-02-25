"""
Veritas Trader - Prime Math Engine
----------------------------------
This module contains the pure mathematical functions required for Options Pricing,
Implied Volatility calculation (Newton-Raphson method), and Delta Hedging.

It is strictly decoupled from any broker or data feed. 
All inputs must be standard Python floats or integers.

Nomenclature:
    S = Current Spot Price of the underlying asset
    K = Strike Price of the option contract
    T = Time to expiration (expressed in years. e.g., 6 months = 0.5)
    r = Risk-free interest rate (e.g., 0.045 for 4.5%)
    sigma = Volatility of the underlying asset (expressed as a decimal, e.g., 0.20 for 20%)
"""

import numpy as np
from scipy.stats import norm

def _calculate_d1_d2(S: float, K: float, T: float, r: float, sigma: float) -> tuple:
    """
    Internal helper function to calculate d1 and d2 components of the Black-Scholes formula.
    Includes fail-safes for expired options or zero volatility.
    """
    # Fail-safe: If option is expired or volatility is zero, return extreme values
    if T <= 0.0 or sigma <= 0.0:
        return (0.0, 0.0)

    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    return d1, d2

def calculate_black_scholes_price(S: float, K: float, T: float, r: float, sigma: float, option_type: str = "call") -> float:
    """
    Calculates the theoretical fair value of a European option using Black-Scholes.
    """
    if T <= 0.0:
        # Intrinsic value at expiration
        return max(0.0, S - K) if option_type.lower() == "call" else max(0.0, K - S)

    d1, d2 = _calculate_d1_d2(S, K, T, r, sigma)
    
    if option_type.lower() == "call":
        price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    elif option_type.lower() == "put":
        price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    else:
        raise ValueError("option_type must be 'call' or 'put'")
        
    return price

def calculate_vega(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """
    Calculates Vega: The sensitivity of the option price to changes in volatility.
    Crucial for the Newton-Raphson Root Finding algorithm.
    """
    if T <= 0.0 or sigma <= 0.0:
        return 0.0

    d1, _ = _calculate_d1_d2(S, K, T, r, sigma)
    vega = S * norm.pdf(d1) * np.sqrt(T)
    
    return vega

def calculate_delta(S: float, K: float, T: float, r: float, sigma: float, option_type: str = "call") -> float:
    """
    Calculates Delta: The sensitivity of the option price to changes in the underlying asset.
    This is the core metric used for Dynamic Hedging.
    
    Returns:
        float: Delta value (0 to 1 for calls, -1 to 0 for puts)
    """
    if T <= 0.0:
        # At expiration, Delta is binary (1 or 0 for calls, -1 or 0 for puts)
        if option_type.lower() == "call":
            return 1.0 if S > K else 0.0
        else:
            return -1.0 if S < K else 0.0

    d1, _ = _calculate_d1_d2(S, K, T, r, sigma)
    
    if option_type.lower() == "call":
        return norm.cdf(d1)
    elif option_type.lower() == "put":
        return norm.cdf(d1) - 1.0
    else:
        raise ValueError("option_type must be 'call' or 'put'")

def get_implied_volatility(market_price: float, S: float, K: float, T: float, r: float, option_type: str = "call") -> float:
    """
    Reverse-engineers the Implied Volatility (IV) from the live market price using 
    the Newton-Raphson Root Finding method.
    
    This saves us from requiring an expensive Level 3 Options Data subscription.
    """
    # Edge case: Option is essentially worthless or expired
    if market_price <= 0 or T <= 0:
        return 0.001 # Return near-zero volatility

    MAX_ITERATIONS = 100
    PRECISION = 1.0e-5
    
    # Initial guess for Volatility (50%)
    sigma = 0.50 
    
    for i in range(MAX_ITERATIONS):
        # 1. Calculate theoretical price with current guess
        theoretical_price = calculate_black_scholes_price(S, K, T, r, sigma, option_type)
        
        # 2. Calculate the difference from reality
        diff = theoretical_price - market_price 
        
        # 3. If the difference is within our precision threshold, we found the IV
        if abs(diff) < PRECISION:
            return sigma
            
        # 4. Calculate Vega to determine how much to adjust our next guess
        vega = calculate_vega(S, K, T, r, sigma)
        
        # Fail-safe: If Vega is too small, Newton-Raphson will fail (divide by zero). 
        # Break and return best guess.
        if vega < 1.0e-8:
            break 
            
        # 5. Adjust the guess
        sigma = sigma - (diff / vega)
        
        # Fail-safe: Volatility cannot be negative. If it drops below 0, reset to a small positive number.
        if sigma <= 0.0:
            sigma = 0.001
            
    return sigma

def calculate_realized_volatility(daily_closes: list) -> float:
    """
    Calculates annualized Realized Volatility (RV) from a list of daily closing prices.
    Requires at least 2 days of data. Usually calculated over 20-30 days.
    """
    if len(daily_closes) < 2:
        return 0.0
    
    closes = np.array(daily_closes)
    # Calculate daily logarithmic returns
    log_returns = np.log(closes[1:] / closes[:-1])
    
    # Standard deviation of daily returns
    daily_vol = np.std(log_returns, ddof=1)
    
    # Annualize it (Crypto trades 365 days a year)
    annualized_vol = daily_vol * np.sqrt(365)
    return annualized_vol