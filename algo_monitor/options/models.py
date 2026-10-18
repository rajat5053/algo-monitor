"""
Options data models and structures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class OptionType(str, Enum):
    CE = "CE"  # Call European
    PE = "PE"  # Put European


@dataclass
class OptionGreeks:
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0


@dataclass
class OptionContract:
    """An options contract representation."""

    symbol: str               # e.g., "NIFTY50-25000-CE" or "BTC-65000-CE"
    underlying: str           # e.g., "NIFTY50" or "BTCUSD"
    exchange: str             # "upstox" or "delta"
    option_type: OptionType   # CE or PE
    strike: float             # Strike price
    expiry_date: str          # YYYY-MM-DD
    lot_size: int             # e.g. 25 for NIFTY, 15 for BANKNIFTY, 1 for crypto
    days_to_expiry: float     # Days remaining to expiry
    implied_volatility: float # Annualised IV (e.g. 0.14 for 14%)
    spot_price: float         # Underlying spot price at contract generation
    premium: float            # Current theoretical / market premium
    greeks: OptionGreeks = field(default_factory=OptionGreeks)


@dataclass
class OptionTradeSetup:
    """A prepared options trade setup ready for execution."""

    contract: OptionContract
    entry_premium: float
    stop_loss_premium: float
    target_premium: float
    lots: int
    quantity: float
    capital_required: float       # Total premium outlay in quote currency
    capital_required_inr: float   # Converted to INR if USD underlying
    max_risk_inr: float           # Max loss in INR if SL is hit
    risk_reward: float
