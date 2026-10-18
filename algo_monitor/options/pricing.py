"""
Quantitative Black-Scholes-Merton pricing and Greeks engine.

Provides analytical closed-form pricing for European Call & Put options,
first and second-order Greeks (Delta, Gamma, Theta, Vega), and option
premium translation from underlying spot setups.
"""

from __future__ import annotations

import math
from algo_monitor.options.models import OptionGreeks


def norm_cdf(x: float) -> float:
    """Cumulative distribution function for standard normal distribution."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_pdf(x: float) -> float:
    """Probability density function for standard normal distribution."""
    return (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * x * x)


def black_scholes_price(
    spot: float,
    strike: float,
    t_years: float,
    r: float,
    iv: float,
    is_call: bool,
) -> float:
    """
    Compute theoretical European option price via Black-Scholes formula.

    Args:
        spot: Underlying asset price (> 0)
        strike: Option strike price (> 0)
        t_years: Time to expiry in years (> 0)
        r: Risk-free interest rate (e.g. 0.065 for 6.5%)
        iv: Implied volatility (e.g. 0.14 for 14%)
        is_call: True for Call (CE), False for Put (PE)

    Returns:
        Theoretical option premium.
    """
    if spot <= 0 or strike <= 0:
        return 0.0

    # Near expiry edge-case (intrinsic value only)
    if t_years <= 1e-5 or iv <= 1e-5:
        if is_call:
            return max(0.0, spot - strike)
        else:
            return max(0.0, strike - spot)

    sqrt_t = math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (r + 0.5 * iv * iv) * t_years) / (iv * sqrt_t)
    d2 = d1 - iv * sqrt_t

    discount = math.exp(-r * t_years)

    if is_call:
        price = spot * norm_cdf(d1) - strike * discount * norm_cdf(d2)
    else:
        price = strike * discount * norm_cdf(-d2) - spot * norm_cdf(-d1)

    return max(0.05, round(price, 2))


def calculate_greeks(
    spot: float,
    strike: float,
    t_years: float,
    r: float,
    iv: float,
    is_call: bool,
) -> OptionGreeks:
    """
    Compute Delta, Gamma, Theta, and Vega for the option contract.
    """
    if spot <= 0 or strike <= 0 or t_years <= 1e-5 or iv <= 1e-5:
        delta = 1.0 if (is_call and spot > strike) else (-1.0 if (not is_call and spot < strike) else 0.0)
        return OptionGreeks(delta=delta, gamma=0.0, theta=0.0, vega=0.0)

    sqrt_t = math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (r + 0.5 * iv * iv) * t_years) / (iv * sqrt_t)
    d2 = d1 - iv * sqrt_t
    discount = math.exp(-r * t_years)
    pdf_d1 = norm_pdf(d1)

    # Delta
    if is_call:
        delta = norm_cdf(d1)
    else:
        delta = norm_cdf(d1) - 1.0

    # Gamma (identical for Call and Put)
    gamma = pdf_d1 / (spot * iv * sqrt_t)

    # Vega (1% change in IV convention)
    vega = (spot * sqrt_t * pdf_d1) / 100.0

    # Theta (annual theta divided by 365 for 1-day decay)
    if is_call:
        theta_annual = -(spot * pdf_d1 * iv) / (2.0 * sqrt_t) - r * strike * discount * norm_cdf(d2)
    else:
        theta_annual = -(spot * pdf_d1 * iv) / (2.0 * sqrt_t) + r * strike * discount * norm_cdf(-d2)
    theta_daily = theta_annual / 365.0

    return OptionGreeks(
        delta=round(delta, 4),
        gamma=round(gamma, 6),
        theta=round(theta_daily, 4),
        vega=round(vega, 4),
    )


def derive_option_setup_from_spot(
    spot_entry: float,
    spot_sl: float,
    spot_target: float,
    strike: float,
    t_years: float,
    r: float,
    iv: float,
    is_call: bool,
    max_sl_premium_pct: float = 0.40,
) -> tuple[float, float, float]:
    """
    Given underlying spot entry, stop-loss, and target levels,
    derive the corresponding Option entry premium, stop-loss premium, and target premium.

    Guarantees:
    - SL premium < Entry premium < Target premium
    - Risk is strictly positive and capped.
    """
    entry_prem = black_scholes_price(spot_entry, strike, t_years, r, iv, is_call)
    sl_prem = black_scholes_price(spot_sl, strike, t_years, r, iv, is_call)
    tp_prem = black_scholes_price(spot_target, strike, t_years, r, iv, is_call)

    # Ensure realistic minimum premium for execution
    entry_prem = max(entry_prem, 1.0)

    # Quantitative protection:
    # 1. Stop loss premium must be strictly less than entry premium
    if sl_prem >= entry_prem:
        # Fall back to percentage-based stop loss on option premium
        sl_prem = entry_prem * (1.0 - max_sl_premium_pct)
    else:
        # Also cap maximum loss on the option premium (e.g. max 40% loss of premium)
        min_allowed_sl = entry_prem * (1.0 - max_sl_premium_pct)
        sl_prem = max(sl_prem, min_allowed_sl)

    sl_prem = max(0.10, round(sl_prem, 2))

    # 2. Target premium must be strictly greater than entry premium
    if tp_prem <= entry_prem:
        risk_pts = entry_prem - sl_prem
        # Ensure at least 1.5x reward-to-risk
        tp_prem = entry_prem + 1.5 * risk_pts

    tp_prem = round(tp_prem, 2)

    return entry_prem, sl_prem, tp_prem
