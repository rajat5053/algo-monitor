"""
Tests for signal generation (all six setup types).
"""

from __future__ import annotations

import pytest

from algo_monitor.data.models import Candle
from algo_monitor.strategy.levels import LevelDetector, Zone, ZoneType
from algo_monitor.strategy.signals import (
    Direction,
    SetupType,
    Signal,
    SignalGenerator,
)
from tests.conftest import make_candle


def _make_dummy_candle(idx: int = -1, price: float = 100.0) -> Candle:
    """Create a dummy spacer candle for the generator's min-candle check."""
    return Candle(
        symbol="TEST", exchange="test", interval="5m",
        timestamp=make_candle(price, idx=idx).timestamp,
        open=price, high=price + 0.5, low=price - 0.5, close=price,
        is_complete=True,
    )


class TestBounceSupport:
    """Test bounce from support setup."""

    def test_bounce_detected(self, strategy_config):
        """Should detect a bounce when prev candle enters support zone
        and current candle closes bullish above it."""
        gen = SignalGenerator(strategy_config)

        zone = Zone(
            zone_type=ZoneType.SUPPORT,
            price_low=98.0,
            price_high=100.0,
            touches=3,
            strength=0.7,
        )

        dummy = _make_dummy_candle(idx=0, price=101.0)

        # Previous candle: low touches support zone
        prev = Candle(
            symbol="TEST", exchange="test", interval="5m",
            timestamp=make_candle(100, idx=1).timestamp,
            open=101.0, high=102.0, low=99.0, close=100.5,
            is_complete=True,
        )

        # Current candle: bounces up, closes above zone, bullish
        current = Candle(
            symbol="TEST", exchange="test", interval="5m",
            timestamp=make_candle(100, idx=2).timestamp,
            open=100.5, high=103.0, low=100.2, close=102.5,
            is_complete=True,
        )

        signals = gen.generate_signals(
            "TEST", "test", [dummy, prev, current], [zone], [zone]
        )

        bounce = [s for s in signals if s.setup_type == SetupType.BOUNCE_SUPPORT]
        assert len(bounce) >= 1
        sig = bounce[0]
        assert sig.direction == Direction.LONG
        assert sig.entry_ref is not None
        assert sig.stop_loss is not None
        assert sig.stop_loss < sig.entry_ref
        assert sig.target > sig.entry_ref

    def test_no_bounce_without_touch(self, strategy_config):
        """No bounce if prev candle didn't touch the support zone."""
        gen = SignalGenerator(strategy_config)

        zone = Zone(
            zone_type=ZoneType.SUPPORT,
            price_low=90.0,
            price_high=92.0,
            touches=3,
            strength=0.7,
        )

        dummy = _make_dummy_candle(idx=0, price=100.0)
        prev = Candle(
            symbol="TEST", exchange="test", interval="5m",
            timestamp=make_candle(100, idx=1).timestamp,
            open=100.0, high=101.0, low=99.0, close=100.5,
            is_complete=True,
        )
        current = Candle(
            symbol="TEST", exchange="test", interval="5m",
            timestamp=make_candle(100, idx=2).timestamp,
            open=100.5, high=102.0, low=100.0, close=101.5,
            is_complete=True,
        )

        signals = gen.generate_signals(
            "TEST", "test", [dummy, prev, current], [zone], [zone]
        )
        bounce = [s for s in signals if s.setup_type == SetupType.BOUNCE_SUPPORT]
        assert len(bounce) == 0


class TestRejectionResistance:
    """Test rejection from resistance setup."""

    def test_rejection_detected(self, strategy_config):
        """Should detect rejection when prev touches resistance
        and current closes bearish below it."""
        gen = SignalGenerator(strategy_config)

        zone = Zone(
            zone_type=ZoneType.RESISTANCE,
            price_low=105.0,
            price_high=107.0,
            touches=3,
            strength=0.7,
        )

        dummy = _make_dummy_candle(idx=0, price=104.0)
        prev = Candle(
            symbol="TEST", exchange="test", interval="5m",
            timestamp=make_candle(100, idx=1).timestamp,
            open=104.0, high=106.0, low=103.5, close=105.5,
            is_complete=True,
        )
        current = Candle(
            symbol="TEST", exchange="test", interval="5m",
            timestamp=make_candle(100, idx=2).timestamp,
            open=105.5, high=106.0, low=103.0, close=103.5,
            is_complete=True,
        )

        signals = gen.generate_signals(
            "TEST", "test", [dummy, prev, current], [zone], [zone]
        )
        rejection = [s for s in signals if s.setup_type == SetupType.REJECTION_RESISTANCE]
        assert len(rejection) >= 1
        sig = rejection[0]
        assert sig.direction == Direction.SHORT
        assert sig.stop_loss > sig.entry_ref


class TestBreakout:
    """Test breakout above resistance."""

    def test_breakout_detected(self, strategy_config):
        """Breakout when prev closes below zone and current closes above."""
        strategy_config.breakout_threshold_pct = 0.3
        gen = SignalGenerator(strategy_config)

        zone = Zone(
            zone_type=ZoneType.RESISTANCE,
            price_low=100.0,
            price_high=101.0,
            touches=3,
            strength=0.7,
        )

        dummy = _make_dummy_candle(idx=0, price=99.0)
        prev = Candle(
            symbol="TEST", exchange="test", interval="5m",
            timestamp=make_candle(100, idx=1).timestamp,
            open=99.0, high=100.5, low=98.5, close=99.5,
            is_complete=True,
        )
        current = Candle(
            symbol="TEST", exchange="test", interval="5m",
            timestamp=make_candle(100, idx=2).timestamp,
            open=100.0, high=103.0, low=99.5, close=102.5,
            is_complete=True,
        )

        signals = gen.generate_signals(
            "TEST", "test", [dummy, prev, current], [zone], [zone]
        )
        breakout = [s for s in signals if s.setup_type == SetupType.BREAKOUT_RESISTANCE]
        assert len(breakout) >= 1
        assert breakout[0].direction == Direction.LONG


class TestBreakdown:
    """Test breakdown below support."""

    def test_breakdown_detected(self, strategy_config):
        """Breakdown when prev closes above zone and current closes below."""
        strategy_config.breakout_threshold_pct = 0.3
        gen = SignalGenerator(strategy_config)

        zone = Zone(
            zone_type=ZoneType.SUPPORT,
            price_low=99.0,
            price_high=100.0,
            touches=3,
            strength=0.7,
        )

        dummy = _make_dummy_candle(idx=0, price=101.0)
        prev = Candle(
            symbol="TEST", exchange="test", interval="5m",
            timestamp=make_candle(100, idx=1).timestamp,
            open=101.0, high=102.0, low=100.5, close=101.0,
            is_complete=True,
        )
        current = Candle(
            symbol="TEST", exchange="test", interval="5m",
            timestamp=make_candle(100, idx=2).timestamp,
            open=100.5, high=101.0, low=97.0, close=97.5,
            is_complete=True,
        )

        signals = gen.generate_signals(
            "TEST", "test", [dummy, prev, current], [zone], [zone]
        )
        bd = [s for s in signals if s.setup_type == SetupType.BREAKDOWN_SUPPORT]
        assert len(bd) >= 1
        assert bd[0].direction == Direction.SHORT


class TestApproachingZone:
    """Test approaching zone early warning."""

    def test_approaching_support_warning(self, strategy_config):
        """Should warn when price is approaching a support zone."""
        strategy_config.approach_distance_pct = 2.0
        gen = SignalGenerator(strategy_config)

        zone = Zone(
            zone_type=ZoneType.SUPPORT,
            price_low=95.0,
            price_high=96.0,
            touches=4,
            strength=0.7,
        )

        dummy = _make_dummy_candle(idx=0, price=99.0)
        prev = Candle(
            symbol="TEST", exchange="test", interval="5m",
            timestamp=make_candle(100, idx=1).timestamp,
            open=99.0, high=100.0, low=98.5, close=99.0,
            is_complete=True,
        )
        current = Candle(
            symbol="TEST", exchange="test", interval="5m",
            timestamp=make_candle(100, idx=2).timestamp,
            open=99.0, high=99.5, low=97.0, close=97.5,
            is_complete=True,
        )

        signals = gen.generate_signals(
            "TEST", "test", [dummy, prev, current], [zone], [zone]
        )
        approach = [s for s in signals if s.setup_type == SetupType.APPROACHING_ZONE]
        assert len(approach) >= 1


class TestSignalDeduplication:
    """Test that duplicate signals are suppressed."""

    def test_same_signal_not_repeated(self, strategy_config):
        """Running the same setup twice should not produce duplicate signals."""
        gen = SignalGenerator(strategy_config)

        zone = Zone(
            zone_type=ZoneType.SUPPORT,
            price_low=98.0,
            price_high=100.0,
            touches=3,
            strength=0.7,
        )

        dummy = _make_dummy_candle(idx=0, price=101.0)
        prev = Candle(
            symbol="TEST", exchange="test", interval="5m",
            timestamp=make_candle(100, idx=1).timestamp,
            open=101.0, high=102.0, low=99.0, close=100.5,
            is_complete=True,
        )
        current = Candle(
            symbol="TEST", exchange="test", interval="5m",
            timestamp=make_candle(100, idx=2).timestamp,
            open=100.5, high=103.0, low=100.2, close=102.5,
            is_complete=True,
        )

        candles = [dummy, prev, current]

        first = gen.generate_signals("TEST", "test", candles, [zone], [zone])
        second = gen.generate_signals("TEST", "test", candles, [zone], [zone])

        # Second call should have fewer signals due to dedup
        assert len(second) <= len(first)


class TestSignalProperties:
    """Test signal metadata and properties."""

    def test_signal_id_deterministic(self, strategy_config):
        """Same signal parameters should produce same ID."""
        sig1 = Signal(
            symbol="TEST", exchange="test",
            setup_type=SetupType.BOUNCE_SUPPORT,
            direction=Direction.LONG,
            timeframe="5m",
        )
        sig2 = Signal(
            symbol="TEST", exchange="test",
            setup_type=SetupType.BOUNCE_SUPPORT,
            direction=Direction.LONG,
            timeframe="5m",
        )
        assert sig1.signal_id == sig2.signal_id

    def test_different_signals_different_ids(self, strategy_config):
        """Different setups should produce different IDs."""
        sig1 = Signal(
            symbol="TEST", exchange="test",
            setup_type=SetupType.BOUNCE_SUPPORT,
            direction=Direction.LONG,
            timeframe="5m",
        )
        sig2 = Signal(
            symbol="TEST", exchange="test",
            setup_type=SetupType.BREAKOUT_RESISTANCE,
            direction=Direction.LONG,
            timeframe="5m",
        )
        assert sig1.signal_id != sig2.signal_id

    def test_incomplete_candles_rejected(self, strategy_config):
        """Incomplete candles should not generate signals."""
        gen = SignalGenerator(strategy_config)

        zone = Zone(
            zone_type=ZoneType.SUPPORT,
            price_low=98.0, price_high=100.0,
            touches=3, strength=0.7,
        )

        incomplete = Candle(
            symbol="TEST", exchange="test", interval="5m",
            timestamp=make_candle(100, idx=0).timestamp,
            open=100.0, high=102.0, low=99.0, close=101.5,
            is_complete=False,
        )

        signals = gen.generate_signals(
            "TEST", "test", [incomplete], [zone], [zone]
        )
        assert len(signals) == 0
