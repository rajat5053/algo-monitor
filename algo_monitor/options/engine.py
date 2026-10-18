"""
Options Trading & Contract Selection Engine.

Translates spot / underlying signals into actionable options trade setups:
- Selects ATM / near-money strikes based on underlying spot prices
- Automatically selects Call (CE) for LONG and Put (PE) for SHORT
- Calculates Greeks and theoretical entry, SL, and target premiums
- Sizes positions appropriately for a ₹15,000 account (strictly defined risk)
- Marks open options to market based on spot movement
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from algo_monitor.options.models import (
    OptionContract,
    OptionGreeks,
    OptionTradeSetup,
    OptionType,
)
from algo_monitor.options.pricing import (
    black_scholes_price,
    calculate_greeks,
    derive_option_setup_from_spot,
)
from algo_monitor.strategy.signals import Direction, Signal
from algo_monitor.utils.logging import get_logger

if TYPE_CHECKING:
    from algo_monitor.config.settings import RiskConfig

logger = get_logger("options.engine")


class OptionsEngine:
    """
    Quant options execution and strike selection engine.
    """

    # Underlying specifications: strike step, lot size, IV, risk-free rate, currency
    SPECS: dict[str, dict] = {
        "NIFTY50": {
            "strike_step": 50.0,
            "lot_size": 25,
            "typical_iv": 0.14,
            "r": 0.065,
            "currency": "INR",
            "exchange": "upstox",
            "expiry_weekday": 3,  # Thursday (NSE index weekly expiry)
        },
        "BANKNIFTY": {
            "strike_step": 100.0,
            "lot_size": 15,
            "typical_iv": 0.16,
            "r": 0.065,
            "currency": "INR",
            "exchange": "upstox",
            "expiry_weekday": 3,  # Thursday
        },
        "NIFTYAUTO": {
            "strike_step": 100.0,
            "lot_size": 25,
            "typical_iv": 0.18,
            "r": 0.065,
            "currency": "INR",
            "exchange": "upstox",
            "expiry_weekday": 3,  # Thursday
        },
        "NIFTYMIDCAPSELECT": {
            "strike_step": 25.0,
            "lot_size": 75,
            "typical_iv": 0.16,
            "r": 0.065,
            "currency": "INR",
            "exchange": "upstox",
            "expiry_weekday": 0,  # Monday (NSE Midcap Select expiry)
        },
        "BTCUSD": {
            "strike_step": 500.0,
            "lot_size": 1,
            "typical_iv": 0.55,
            "r": 0.045,
            "currency": "USD",
            "exchange": "delta",
            "expiry_weekday": 4,  # Friday
        },
        "ETHUSD": {
            "strike_step": 25.0,
            "lot_size": 1,
            "typical_iv": 0.60,
            "r": 0.045,
            "currency": "USD",
            "exchange": "delta",
            "expiry_weekday": 4,  # Friday
        },
        "SOLUSD": {
            "strike_step": 2.5,
            "lot_size": 1,
            "typical_iv": 0.65,
            "r": 0.045,
            "currency": "USD",
            "exchange": "delta",
            "expiry_weekday": 4,  # Friday
        },
        "ETHUSD": {
            "strike_step": 25.0,
            "lot_size": 1,
            "typical_iv": 0.60,
            "r": 0.045,
            "currency": "USD",
            "exchange": "delta",
            "expiry_weekday": 4,  # Friday
        },
    }

    def __init__(self, risk_config: RiskConfig | None = None):
        self.risk_config = risk_config

    def get_spec(self, symbol: str) -> dict:
        """Find matching specification for symbol."""
        sym = symbol.upper()
        for key, spec in self.SPECS.items():
            if key in sym:
                return spec
        # Sensible generic default
        return {
            "strike_step": 50.0,
            "lot_size": 1,
            "typical_iv": 0.20,
            "r": 0.065,
            "currency": "INR" if "USD" not in sym else "USD",
            "exchange": "delta" if ("BTC" in sym or "ETH" in sym) else "upstox",
            "expiry_weekday": 3,
        }

    def is_option_eligible(self, symbol: str) -> bool:
        """Return True if symbol has an active options market."""
        sym = symbol.upper()
        return any(k in sym for k in ("NIFTY", "BANKNIFTY", "BTC", "ETH"))

    def select_strike(self, underlying: str, spot_price: float) -> float:
        """Calculate ATM strike rounded to nearest strike step."""
        spec = self.get_spec(underlying)
        step = spec["strike_step"]
        return round(spot_price / step) * step

    def get_next_expiry(self, weekday: int = 3) -> tuple[str, float]:
        """
        Calculate next weekly expiry date and remaining days.
        weekday: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, etc.
        """
        now = datetime.now(timezone.utc)
        days_ahead = (weekday - now.weekday()) % 7
        if days_ahead == 0 and now.hour >= 10:  # Expired or midday today -> next week
            days_ahead = 7
        elif days_ahead == 0:
            days_ahead = 0.5  # Expiry today morning

        expiry_date = (now + timedelta(days=days_ahead)).date()
        days_to_expiry = max(0.5, float(days_ahead))
        return expiry_date.isoformat(), days_to_expiry

    def build_contract(
        self,
        underlying: str,
        spot_price: float,
        direction: Direction,
    ) -> OptionContract:
        """
        Create a calibrated OptionContract for the underlying spot setup.
        """
        spec = self.get_spec(underlying)
        strike = self.select_strike(underlying, spot_price)
        option_type = OptionType.CE if direction == Direction.LONG else OptionType.PE
        is_call = option_type == OptionType.CE

        expiry_str, days_to_expiry = self.get_next_expiry(spec["expiry_weekday"])
        t_years = days_to_expiry / 365.0
        r = spec["r"]
        iv = spec["typical_iv"]

        premium = black_scholes_price(
            spot=spot_price,
            strike=strike,
            t_years=t_years,
            r=r,
            iv=iv,
            is_call=is_call,
        )

        greeks = calculate_greeks(
            spot=spot_price,
            strike=strike,
            t_years=t_years,
            r=r,
            iv=iv,
            is_call=is_call,
        )

        symbol = f"{underlying}-{int(strike)}-{option_type.value}"

        return OptionContract(
            symbol=symbol,
            underlying=underlying,
            exchange=spec["exchange"],
            option_type=option_type,
            strike=strike,
            expiry_date=expiry_str,
            lot_size=spec["lot_size"],
            days_to_expiry=days_to_expiry,
            implied_volatility=iv,
            spot_price=spot_price,
            premium=premium,
            greeks=greeks,
        )

    def prepare_trade_setup(
        self,
        signal: Signal,
        spot_price: float,
        balance_inr: float,
        max_capital_pct: float = 0.45,
        usd_inr_rate: float = 85.0,
    ) -> OptionTradeSetup | None:
        """
        Build an executable OptionTradeSetup with defined risk and sizing.
        Returns None if trade cannot be accommodated within capital rules.
        """
        if spot_price <= 0 or balance_inr <= 0:
            return None

        contract = self.build_contract(signal.symbol, spot_price, signal.direction)
        spec = self.get_spec(signal.symbol)
        is_usd = spec["currency"] == "USD"
        fx_rate = usd_inr_rate if is_usd else 1.0

        is_call = contract.option_type == OptionType.CE
        t_years = contract.days_to_expiry / 365.0

        # Derive Option Entry, SL, and Target premiums from spot setup
        spot_entry = signal.entry_ref or spot_price
        spot_sl = signal.stop_loss
        spot_target = signal.target

        entry_prem, sl_prem, tp_prem = derive_option_setup_from_spot(
            spot_entry=spot_entry,
            spot_sl=spot_sl,
            spot_target=spot_target,
            strike=contract.strike,
            t_years=t_years,
            r=spec["r"],
            iv=contract.implied_volatility,
            is_call=is_call,
        )

        # Risk and sizing calculations
        # Max capital to risk on this trade:
        max_capital_allowed_inr = balance_inr * max_capital_pct
        lot_size = contract.lot_size
        cost_per_lot_inr = entry_prem * lot_size * fx_rate

        # If cost of even 1 lot exceeds allowed capital
        if cost_per_lot_inr > max_capital_allowed_inr:
            # If 1 lot slightly exceeds max_capital_pct but is strictly <= available balance,
            # allow 1 lot for small-capital trading (e.g. ₹15,000 buying 1 lot of NIFTY @ ₹4,000)
            if cost_per_lot_inr <= balance_inr * 0.70:
                lots = 1
            else:
                logger.info(
                    "Options setup rejected: 1 lot cost (INR %.1f) exceeds capital limit (INR %.1f)",
                    cost_per_lot_inr,
                    max_capital_allowed_inr,
                )
                return None
        else:
            # Sizing: determine number of lots within capital limit
            max_lots = int(max_capital_allowed_inr // cost_per_lot_inr)
            lots = max(1, min(max_lots, 3))  # Cap at max 3 lots for ₹15k capital

        quantity = float(lots * lot_size)
        capital_required = entry_prem * quantity
        capital_required_inr = capital_required * fx_rate
        risk_per_unit = entry_prem - sl_prem
        max_risk_inr = quantity * risk_per_unit * fx_rate
        reward_per_unit = tp_prem - entry_prem
        risk_reward = round(reward_per_unit / risk_per_unit, 2) if risk_per_unit > 0 else 1.5

        return OptionTradeSetup(
            contract=contract,
            entry_premium=entry_prem,
            stop_loss_premium=sl_prem,
            target_premium=tp_prem,
            lots=lots,
            quantity=quantity,
            capital_required=capital_required,
            capital_required_inr=round(capital_required_inr, 2),
            max_risk_inr=round(max_risk_inr, 2),
            risk_reward=risk_reward,
        )

    def mark_to_market(
        self,
        contract_symbol: str,
        current_spot: float,
        entry_spot: float,
        entry_premium: float,
        days_to_expiry: float | None = None,
    ) -> float:
        """
        Calculate current mark-to-market option premium given underlying spot price.
        """
        # Parse symbol: e.g. "NIFTY50-25000-CE"
        parts = contract_symbol.split("-")
        if len(parts) >= 3:
            underlying = parts[0]
            strike = float(parts[1])
            is_call = parts[2].upper() == "CE"
            spec = self.get_spec(underlying)
            if days_to_expiry is None:
                _, dte = self.get_next_expiry(spec.get("expiry_weekday", 3))
            else:
                dte = days_to_expiry
            t_years = max(0.1, dte) / 365.0
            return black_scholes_price(
                spot=current_spot,
                strike=strike,
                t_years=t_years,
                r=spec["r"],
                iv=spec["typical_iv"],
                is_call=is_call,
            )

        # Fallback to Delta approximation
        delta = 0.50
        spot_diff = current_spot - entry_spot
        return max(0.10, round(entry_premium + delta * spot_diff, 2))
