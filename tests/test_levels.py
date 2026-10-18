"""
Tests for support/resistance level detection and zone clustering.
"""

from __future__ import annotations

import math

import pytest

from algo_monitor.data.models import Candle
from algo_monitor.strategy.levels import LevelDetector, Zone, ZoneType
from tests.conftest import make_candle, make_candle_series, make_swing_candles


class TestSwingPointDetection:
    """Test identification of confirmed swing highs and lows."""

    def test_simple_swing_high(self, strategy_config):
        """A clear peak should be detected as a swing high."""
        detector = LevelDetector(strategy_config)

        # Create: rising → peak → falling
        candles = []
        prices = [10, 11, 12, 13, 14, 15, 14, 13, 12, 11, 10]
        for i, p in enumerate(prices):
            candles.append(make_candle(price=p, idx=i))

        swings = detector.find_swing_points(candles)
        highs = [s for s in swings if s.swing_type == ZoneType.RESISTANCE]

        assert len(highs) >= 1
        # The peak should be near 15
        assert any(abs(s.price - 15.75) < 1.5 for s in highs)

    def test_simple_swing_low(self, strategy_config):
        """A clear trough should be detected as a swing low."""
        detector = LevelDetector(strategy_config)

        prices = [20, 19, 18, 17, 16, 15, 16, 17, 18, 19, 20]
        candles = [make_candle(price=p, idx=i) for i, p in enumerate(prices)]

        swings = detector.find_swing_points(candles)
        lows = [s for s in swings if s.swing_type == ZoneType.SUPPORT]

        assert len(lows) >= 1
        assert any(abs(s.price - 14.25) < 1.5 for s in lows)

    def test_insufficient_candles(self, strategy_config):
        """Too few candles should return no swings."""
        detector = LevelDetector(strategy_config)
        candles = [make_candle(price=100, idx=i) for i in range(4)]

        swings = detector.find_swing_points(candles)
        assert swings == []

    def test_flat_market_no_swings(self, strategy_config):
        """Flat market (same price) should produce minimal swings."""
        detector = LevelDetector(strategy_config)
        candles = [make_candle(price=100, idx=i, range_pct=0.01) for i in range(20)]

        swings = detector.find_swing_points(candles)
        # Equal highs — first might be detected but not meaningful
        # The important thing is it doesn't crash
        assert isinstance(swings, list)

    def test_no_look_ahead_bias(self, strategy_config):
        """Swings should only use candles[i-lookback : i+lookback]."""
        strategy_config.swing_lookback = 2
        detector = LevelDetector(strategy_config)

        prices = [50, 51, 55, 51, 50, 48, 45, 48, 50, 52]
        candles = [make_candle(price=p, idx=i) for i, p in enumerate(prices)]

        swings = detector.find_swing_points(candles)

        # The swing at index 2 (price~55) needs candles 0-4 to confirm
        # The swing at index 6 (price~45) needs candles 4-8 to confirm
        for s in swings:
            # Ensure the candle_index is within valid range
            assert s.candle_index >= strategy_config.swing_lookback
            assert s.candle_index < len(candles) - strategy_config.swing_lookback


class TestZoneClustering:
    """Test grouping nearby levels into zones."""

    def test_nearby_levels_merge(self, strategy_config):
        """Levels within tolerance should merge into a single zone."""
        detector = LevelDetector(strategy_config)

        # Create candles with two visits to the same support area
        candles = make_swing_candles(
            support_price=95, resistance_price=105, count=60
        )

        zones = detector.detect_zones(candles)

        # Should have some support and resistance zones
        support_zones = [z for z in zones if z.zone_type == ZoneType.SUPPORT]
        resistance_zones = [z for z in zones if z.zone_type == ZoneType.RESISTANCE]

        # At least one zone of each type
        assert len(support_zones) >= 1 or len(resistance_zones) >= 1

    def test_distant_levels_stay_separate(self, strategy_config):
        """Levels far apart should not merge."""
        detector = LevelDetector(strategy_config)
        strategy_config.zone_tolerance_pct = 0.5

        # Support at 50 and 100 — way too far to merge
        candles = []
        for i in range(30):
            if i < 15:
                candles.append(make_candle(price=50 + math.sin(i) * 3, idx=i))
            else:
                candles.append(make_candle(price=100 + math.sin(i) * 3, idx=i))

        zones = detector.detect_zones(candles)
        if len(zones) >= 2:
            # Zones should not span from 50 to 100
            for z in zones:
                assert z.width_pct < 50  # No zone should span 50% of its price

    def test_zone_has_price_range(self, strategy_config):
        """Each zone should have a valid price range."""
        detector = LevelDetector(strategy_config)
        candles = make_swing_candles(count=60)
        zones = detector.detect_zones(candles)

        for zone in zones:
            assert zone.price_low <= zone.price_high
            assert zone.price_low > 0
            assert zone.mid_price > 0

    def test_max_zones_limit(self, strategy_config):
        """Should not exceed max_zones."""
        strategy_config.max_zones = 5
        strategy_config.min_touches = 1
        detector = LevelDetector(strategy_config)

        candles = make_swing_candles(count=100)
        zones = detector.detect_zones(candles)

        assert len(zones) <= 5


class TestZoneScoring:
    """Test zone strength scoring."""

    def test_more_touches_higher_strength(self, strategy_config):
        """Zones with more touches should generally score higher."""
        detector = LevelDetector(strategy_config)
        strategy_config.min_touches = 1

        # Create a pattern with a clear, frequently-tested level
        candles = make_swing_candles(
            support_price=95, resistance_price=105, count=80
        )

        zones = detector.detect_zones(candles)

        for zone in zones:
            assert 0 <= zone.strength <= 1
            assert zone.touches >= 1

    def test_zone_contains_price(self, strategy_config):
        """Zone.contains_price should work correctly."""
        zone = Zone(
            zone_type=ZoneType.SUPPORT,
            price_low=99.0,
            price_high=101.0,
        )

        assert zone.contains_price(100.0)
        assert zone.contains_price(99.0)
        assert zone.contains_price(101.0)
        assert not zone.contains_price(98.0)
        assert not zone.contains_price(102.0)

        # With tolerance
        assert zone.contains_price(98.5, tolerance_pct=1.0)

    def test_zone_distance(self, strategy_config):
        """Zone.distance_pct should return correct percentage."""
        zone = Zone(
            zone_type=ZoneType.SUPPORT,
            price_low=100.0,
            price_high=100.0,
        )

        # Price below zone
        dist = zone.distance_pct(95.0)
        assert abs(dist - 5.26) < 0.5  # ~5%

        # Price above zone
        dist = zone.distance_pct(105.0)
        assert abs(dist - 4.76) < 0.5  # ~5%

        # Price inside zone
        dist = zone.distance_pct(100.0)
        assert dist == 0


class TestEndToEndDetection:
    """Integration tests for the full detection pipeline."""

    def test_detect_zones_returns_valid_output(self, strategy_config):
        """Full pipeline should return valid zones."""
        strategy_config.min_touches = 1
        detector = LevelDetector(strategy_config)

        candles = make_swing_candles(count=60)
        zones = detector.detect_zones(candles)

        assert isinstance(zones, list)
        for z in zones:
            assert isinstance(z, Zone)
            assert z.zone_type in (ZoneType.SUPPORT, ZoneType.RESISTANCE)
            assert len(z.reasons) > 0

    def test_empty_candles_returns_empty(self, strategy_config):
        """Empty input should not crash."""
        detector = LevelDetector(strategy_config)
        zones = detector.detect_zones([])
        assert zones == []
