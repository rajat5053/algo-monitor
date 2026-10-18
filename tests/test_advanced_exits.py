"""
Unit tests for Document 2: Advanced Exit Management Module.
Tests:
- ATR trailing stop ratcheting
- Swing-based trailing stop ratcheting
- Partial profit taking at 1.0R target
- Moving stop loss to breakeven after partial profit
- Runner continuation until stop-loss or final target
"""

from datetime import datetime, timedelta, timezone
import pytest

from algo_monitor.config.settings import ExitConfig
from algo_monitor.data.models import Candle
from algo_monitor.strategy.exits import AdvancedExitManager, PositionExitState


def _make_candle(timestamp: datetime, o: float, h: float, l: float, c: float) -> Candle:
    return Candle(
        symbol="BTCUSD",
        exchange="delta",
        interval="5m",
        timestamp=timestamp,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=100.0,
        is_complete=True,
    )


class TestAdvancedExits:

    def test_atr_trailing_stop_ratchet(self):
        """Verify ATR trailing stop ratchets upward on long trade and never loosens."""
        cfg = ExitConfig(trailing_stop_mode="atr", trailing_atr_mult=2.0)
        mgr = AdvancedExitManager(cfg)

        state = mgr.create_position_state(
            trade_id=1,
            symbol="BTCUSD",
            direction="long",
            entry_price=100.0,
            stop_loss=90.0,
            target=130.0,
            quantity=1.0,
        )

        base = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        atr = 2.0  # Trailing distance = 2.0 * 2 = 4.0

        # Bar 1: Price rises to 105. SL = max(90, 105 - 4) = 101
        c1 = _make_candle(base, 100.0, 105.0, 99.0, 104.0)
        res1 = mgr.evaluate_bar(state, c1, atr_val=atr)
        assert state.current_sl == 101.0
        assert not res1.is_closed

        # Bar 2: Price pushes to 110. SL = max(101, 110 - 4) = 106
        c2 = _make_candle(base + timedelta(minutes=5), 104.0, 110.0, 103.0, 109.0)
        res2 = mgr.evaluate_bar(state, c2, atr_val=atr)
        assert state.current_sl == 106.0
        assert not res2.is_closed

        # Bar 3: Price pulls back to 107 (High 108). SL must remain 106 (never loosen!)
        c3 = _make_candle(base + timedelta(minutes=10), 109.0, 108.0, 106.5, 107.0)
        res3 = mgr.evaluate_bar(state, c3, atr_val=atr)
        assert state.current_sl == 106.0
        assert not res3.is_closed

        # Bar 4: Price dips to 105.8, hitting the trailing stop of 106!
        c4 = _make_candle(base + timedelta(minutes=15), 107.0, 107.5, 105.5, 105.8)
        res4 = mgr.evaluate_bar(state, c4, atr_val=atr)
        assert res4.is_closed is True
        assert res4.exit_reason == "stop_loss"
        assert res4.exit_price == 106.0

    def test_partial_profit_plus_breakeven_plus_trail(self):
        """
        Verify partial profit taking:
        - 50% liquidated at 1.0R (+10)
        - Stop-loss moved to breakeven (100.0)
        - Remaining 50% trails via ATR until stopped out or final target.
        """
        cfg = ExitConfig(
            trailing_stop_mode="partial_plus_atr",
            trailing_atr_mult=2.0,
            partial_profit_pct=0.5,
            partial_profit_r_mult=1.0,
            move_to_breakeven_on_partial=True,
        )
        mgr = AdvancedExitManager(cfg)

        state = mgr.create_position_state(
            trade_id=2,
            symbol="BTCUSD",
            direction="long",
            entry_price=100.0,
            stop_loss=90.0,   # Risk = 10.0 -> 1.0R Target = 110.0
            target=140.0,
            quantity=10.0,
        )

        base = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        atr = 2.0

        # Bar 1: Price touches 111.0 (hitting 1.0R target 110.0)
        c1 = _make_candle(base, 100.0, 111.0, 100.0, 109.0)
        res1 = mgr.evaluate_bar(state, c1, atr_val=atr)

        assert res1.partial_filled is True
        assert res1.partial_qty == 5.0
        assert state.remaining_qty == 5.0
        assert state.current_sl == 100.0  # Moved to breakeven!

        # Bar 2: Runner continues up to 120.0
        # Trailing stop now kicks in on remaining position: 120 - 4 = 116.0
        c2 = _make_candle(base + timedelta(minutes=5), 109.0, 120.0, 108.0, 119.0)
        res2 = mgr.evaluate_bar(state, c2, atr_val=atr)
        assert state.current_sl == 116.0
        assert not res2.is_closed

        # Bar 3: Price drops to 115.0, exiting runner at 116.0
        c3 = _make_candle(base + timedelta(minutes=10), 119.0, 119.0, 115.0, 115.5)
        res3 = mgr.evaluate_bar(state, c3, atr_val=atr)
        assert res3.is_closed is True
        assert res3.exit_reason == "stop_loss"
        assert res3.exit_price == 116.0

    def test_swing_trailing_stop(self):
        """Verify swing-based trailing stop ratchets to confirmed pivot low."""
        cfg = ExitConfig(trailing_stop_mode="swing", swing_lookback=1)
        mgr = AdvancedExitManager(cfg)

        state = mgr.create_position_state(
            trade_id=3,
            symbol="BTCUSD",
            direction="long",
            entry_price=100.0,
            stop_loss=90.0,
            target=150.0,
            quantity=1.0,
        )

        base = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)

        # Create recent candles with a confirmed swing low at 102.0
        candles = [
            _make_candle(base, 105.0, 106.0, 104.0, 104.5),
            _make_candle(base + timedelta(minutes=5), 103.0, 105.0, 102.0, 104.0),  # Pivot low 102.0
            _make_candle(base + timedelta(minutes=10), 104.0, 108.0, 103.5, 107.0),
            _make_candle(base + timedelta(minutes=15), 107.0, 110.0, 106.0, 109.0),
        ]

        res = mgr.evaluate_bar(state, candles[-1], recent_candles=candles)
        assert state.current_sl == 102.0  # Trailed to swing pivot low
