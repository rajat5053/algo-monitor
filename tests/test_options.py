"""
Comprehensive quantitative tests for Options pricing, strike selection,
risk sizing, and trading engine options execution.
"""

from __future__ import annotations

import math
import pytest
from datetime import datetime, timezone

from algo_monitor.config.settings import OptionsConfig, RiskConfig
from algo_monitor.database import Database
from algo_monitor.options.engine import OptionsEngine
from algo_monitor.options.models import OptionType
from algo_monitor.options.pricing import (
    black_scholes_price,
    calculate_greeks,
    derive_option_setup_from_spot,
    norm_cdf,
)
from algo_monitor.strategy.signals import Direction, SetupType, Signal
from algo_monitor.trading.engine import PaperTradingEngine


@pytest.fixture
def fresh_db(tmp_path, request):
    db_path = str(tmp_path / f"test_{request.node.name}.db")
    db = Database(db_path)
    db.initialise()
    return db


@pytest.fixture
def options_engine():
    return OptionsEngine()


# ===========================================================================
# 1. Quant Pricing & Greeks Tests
# ===========================================================================

class TestOptionsPricing:
    """Quantitative verification of Black-Scholes formulas and Greeks."""

    def test_put_call_parity(self):
        """Verify Put-Call Parity: C - P = S - K * exp(-r * T)."""
        S = 25000.0
        K = 25000.0
        T = 7.0 / 365.0
        r = 0.065
        iv = 0.14

        call = black_scholes_price(S, K, T, r, iv, is_call=True)
        put = black_scholes_price(S, K, T, r, iv, is_call=False)

        discounted_k = K * math.exp(-r * T)
        parity_diff = (call - put) - (S - discounted_k)
        assert abs(parity_diff) < 1.0  # Within rounding tolerance

    def test_atm_call_and_put_pricing(self):
        """ATM options should have realistic positive premiums."""
        call = black_scholes_price(25000, 25000, 5 / 365, 0.065, 0.14, is_call=True)
        put = black_scholes_price(25000, 25000, 5 / 365, 0.065, 0.14, is_call=False)
        assert 100.0 < call < 250.0
        assert 100.0 < put < 250.0

    def test_intrinsic_value_at_near_expiry(self):
        """At expiry, option prices equal intrinsic value."""
        # Deep ITM Call
        call_itm = black_scholes_price(25200, 25000, 0.000001, 0.065, 0.14, is_call=True)
        assert abs(call_itm - 200.0) < 0.1

        # OTM Call at expiry
        call_otm = black_scholes_price(24800, 25000, 0.000001, 0.065, 0.14, is_call=True)
        assert call_otm <= 0.05

        # ITM Put at expiry
        put_itm = black_scholes_price(24800, 25000, 0.000001, 0.065, 0.14, is_call=False)
        assert abs(put_itm - 200.0) < 0.1

    def test_greeks_properties(self):
        """Verify Delta, Gamma, Vega, Theta behaviour."""
        S, K, T, r, iv = 25000.0, 25000.0, 5 / 365.0, 0.065, 0.14

        call_greeks = calculate_greeks(S, K, T, r, iv, is_call=True)
        put_greeks = calculate_greeks(S, K, T, r, iv, is_call=False)

        # ATM Call Delta ~ 0.50, ATM Put Delta ~ -0.50
        assert 0.45 < call_greeks.delta < 0.60
        assert -0.60 < put_greeks.delta < -0.45

        # Gamma is positive for long options
        assert call_greeks.gamma > 0
        assert put_greeks.gamma > 0

        # Theta is negative (decay)
        assert call_greeks.theta < 0
        assert put_greeks.theta < 0

        # Vega is positive
        assert call_greeks.vega > 0


# ===========================================================================
# 2. Strike Selection & Setup Derivation
# ===========================================================================

class TestStrikeSelectionAndSetup:
    """Test ATM strike rounding and spot setup translation."""

    def test_strike_selection(self, options_engine):
        # NIFTY 50 strike step = 50
        assert options_engine.select_strike("NIFTY50", 25024) == 25000.0
        assert options_engine.select_strike("NIFTY50", 25048) == 25050.0

        # BANKNIFTY strike step = 100
        assert options_engine.select_strike("BANKNIFTY", 51240) == 51200.0
        assert options_engine.select_strike("BANKNIFTY", 51260) == 51300.0

    def test_contract_generation_direction(self, options_engine):
        # LONG -> CE
        ce_contract = options_engine.build_contract("NIFTY50", 25000, Direction.LONG)
        assert ce_contract.option_type == OptionType.CE
        assert ce_contract.symbol == "NIFTY50-25000-CE"
        assert ce_contract.lot_size == 25

        # SHORT -> PE
        pe_contract = options_engine.build_contract("NIFTY50", 25000, Direction.SHORT)
        assert pe_contract.option_type == OptionType.PE
        assert pe_contract.symbol == "NIFTY50-25000-PE"

    def test_derive_setup_from_spot(self):
        """Spot LONG setup (entry 25000, sl 24900, target 25200) -> Option premiums."""
        entry_prem, sl_prem, tp_prem = derive_option_setup_from_spot(
            spot_entry=25000,
            spot_sl=24900,
            spot_target=25200,
            strike=25000,
            t_years=5 / 365,
            r=0.065,
            iv=0.14,
            is_call=True,
        )

        assert sl_prem < entry_prem < tp_prem
        assert tp_prem - entry_prem > entry_prem - sl_prem  # Positive R:R


# ===========================================================================
# 3. Position Sizing for ₹15,000 Capital
# ===========================================================================

class TestOptionsSizing:
    """Verify position sizing conforms strictly to ₹15,000 starting capital."""

    def test_nifty_option_fits_15k_capital(self, options_engine):
        signal = Signal(
            symbol="NIFTY50",
            exchange="upstox",
            setup_type=SetupType.BOUNCE_SUPPORT,
            direction=Direction.LONG,
            timeframe="5m",
            entry_ref=25000.0,
            stop_loss=24920.0,
            target=25160.0,
            risk_reward=2.0,
            strength=0.8,
            reason="Test Nifty Long",
        )

        setup = options_engine.prepare_trade_setup(
            signal=signal,
            spot_price=25000.0,
            balance_inr=15000.0,
            max_capital_pct=0.45,
        )

        assert setup is not None
        assert setup.lots >= 1
        assert setup.quantity == setup.lots * 25
        # Total capital outlay must not exceed balance
        assert setup.capital_required_inr <= 15000.0
        # Risk amount must be strictly defined and bounded
        assert 0 < setup.max_risk_inr < 5000.0

    def test_insufficient_capital_rejected(self, options_engine):
        """If capital is too small to afford even 1 lot, setup should return None."""
        signal = Signal(
            symbol="NIFTY50",
            exchange="upstox",
            setup_type=SetupType.BOUNCE_SUPPORT,
            direction=Direction.LONG,
            timeframe="5m",
            entry_ref=25000.0,
            stop_loss=24920.0,
            target=25160.0,
            risk_reward=2.0,
            strength=0.8,
            reason="Test Nifty Long",
        )

        # ₹500 balance cannot afford 1 lot of NIFTY options (~₹3,000-₹4,000)
        setup = options_engine.prepare_trade_setup(
            signal=signal,
            spot_price=25000.0,
            balance_inr=500.0,
            max_capital_pct=0.45,
        )
        assert setup is None


# ===========================================================================
# 4. End-to-End Trading Engine Execution
# ===========================================================================

class TestTradingEngineOptionsExecution:
    """Test full cycle: Signal -> Option Trade -> Mark-to-Market -> Exit."""

    def test_nifty_signal_routes_to_options_and_executes(self, fresh_db):
        risk_cfg = RiskConfig(starting_balance=15000.0)
        opt_cfg = OptionsConfig(enabled=True, auto_route_indices=True)
        engine = PaperTradingEngine(risk_cfg, fresh_db, opt_cfg)

        signal = Signal(
            symbol="NIFTY50",
            exchange="upstox",
            setup_type=SetupType.BOUNCE_SUPPORT,
            direction=Direction.LONG,
            timeframe="5m",
            entry_ref=25000.0,
            stop_loss=24920.0,
            target=25160.0,
            risk_reward=2.0,
            strength=0.8,
            reason="Nifty Bounce Support",
        )

        trade = engine.process_signal(signal, current_price=25000.0)

        assert trade is not None
        assert "NIFTY50-25000-CE" in trade["symbol"]
        assert trade["status"] == "open"
        assert trade["direction"] == "long"
        assert trade["quantity"] >= 25

        # Check DB persistence
        open_trades = engine.get_open_positions()
        assert len(open_trades) == 1
        assert open_trades[0]["symbol"] == trade["symbol"]

    def test_option_position_target_hit(self, fresh_db):
        """When underlying rallies, option premium increases and hits target."""
        risk_cfg = RiskConfig(starting_balance=15000.0)
        opt_cfg = OptionsConfig(enabled=True, auto_route_indices=True)
        engine = PaperTradingEngine(risk_cfg, fresh_db, opt_cfg)

        signal = Signal(
            symbol="NIFTY50",
            exchange="upstox",
            setup_type=SetupType.BOUNCE_SUPPORT,
            direction=Direction.LONG,
            timeframe="5m",
            entry_ref=25000.0,
            stop_loss=24920.0,
            target=25160.0,
            risk_reward=2.0,
            strength=0.8,
            reason="Nifty Setup",
        )

        trade = engine.process_signal(signal, current_price=25000.0)
        initial_balance = engine.balance

        # Underlying jumps to target (25,160)
        # Pass updated NIFTY50 spot price
        closed = engine.update_positions({"NIFTY50": 25250.0})

        assert len(closed) == 1
        assert closed[0]["exit_reason"] == "target_hit"
        assert closed[0]["net_pnl"] > 0
        assert engine.balance > initial_balance

    def test_option_position_stop_loss_hit(self, fresh_db):
        """When underlying breaks support, option hits stop loss and caps risk."""
        risk_cfg = RiskConfig(starting_balance=15000.0)
        opt_cfg = OptionsConfig(enabled=True, auto_route_indices=True)
        engine = PaperTradingEngine(risk_cfg, fresh_db, opt_cfg)

        signal = Signal(
            symbol="NIFTY50",
            exchange="upstox",
            setup_type=SetupType.BOUNCE_SUPPORT,
            direction=Direction.LONG,
            timeframe="5m",
            entry_ref=25000.0,
            stop_loss=24920.0,
            target=25160.0,
            risk_reward=2.0,
            strength=0.8,
            reason="Nifty Setup",
        )

        trade = engine.process_signal(signal, current_price=25000.0)
        initial_balance = engine.balance

        # Underlying drops through SL (24,800)
        closed = engine.update_positions({"NIFTY50": 24800.0})

        assert len(closed) == 1
        assert closed[0]["exit_reason"] == "stop_loss"
        assert closed[0]["net_pnl"] < 0
        # Loss must be capped and balance remains healthy
        assert engine.balance > 10000.0
