"""
Unit tests for Document 1 S/R Enhancements:
- Prominence filtering of swing points
- Price zones with minimum thickness
- Rejection wick detection and freshness scoring
- Verified polarity flips after breakout/breakdown
- Merging overlapping zones to prevent chart clutter
"""

from datetime import datetime, timedelta, timezone
import pytest

from algo_monitor.config.settings import StrategyConfig
from algo_monitor.data.models import Candle
from algo_monitor.strategy.levels import LevelDetector, SwingPoint, Zone, ZoneType


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


class TestEnhancedSupportResistance:

    def test_prominence_filtering(self):
        """Verify minor noise swings are filtered out while prominent swings are retained."""
        config = StrategyConfig(swing_lookback=2, min_prominence_pct=1.0)
        detector = LevelDetector(config)

        base_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        # Sequence with a very minor bump (0.2%) and a major peak (5%)
        # Bars: 100 -> 100.1 -> 100.2 (tiny peak) -> 100.1 -> 100 -> 110 (major peak) -> 100
        prices = [
            (100, 100.5, 99.5, 100),
            (100, 100.8, 99.8, 100.2),
            (100.2, 100.9, 100.1, 100.3),  # Tiny peak high 100.9, prominence ~0.4%
            (100.3, 100.5, 99.9, 100.1),
            (100.1, 101.0, 99.5, 100.0),
            (100.0, 105.0, 99.8, 104.0),
            (104.0, 110.0, 103.5, 108.0),  # Major peak high 110.0, prominence > 5%
            (108.0, 108.5, 101.0, 102.0),
            (102.0, 103.0, 98.0, 99.0),
        ]

        candles = [
            _make_candle(base_time + timedelta(minutes=5 * i), o, h, l, c)
            for i, (o, h, l, c) in enumerate(prices)
        ]

        swings = detector.find_swing_points(candles)
        res_swings = [s for s in swings if s.swing_type == ZoneType.RESISTANCE]

        # The tiny peak should be filtered out by min_prominence_pct=1.0
        assert any(s.price == 110.0 for s in res_swings)
        assert not any(s.price == 100.9 for s in res_swings)

    def test_zone_thickness_and_minimum_width(self):
        """Verify zones are price bands with minimum percentage width, not single prices."""
        config = StrategyConfig(zone_tolerance_pct=0.5, min_zone_width_pct=0.4)
        detector = LevelDetector(config)

        # Cluster points very close together: 100.0, 100.05
        swings = [
            SwingPoint(100.0, datetime.now(timezone.utc), ZoneType.SUPPORT, 0),
            SwingPoint(100.05, datetime.now(timezone.utc), ZoneType.SUPPORT, 5),
        ]

        zones = detector._cluster_levels(swings, ZoneType.SUPPORT)
        assert len(zones) == 1
        zone = zones[0]

        # Even though raw span is 0.05 (0.05%), min_zone_width_pct=0.4 enforces width >= 0.4%
        width = zone.price_high - zone.price_low
        width_pct = (width / zone.mid_price) * 100.0
        assert width_pct >= 0.39

    def test_rejection_count_and_freshness_score(self):
        """Verify rejection wicks are counted and freshness decays when over-tested."""
        config = StrategyConfig()
        detector = LevelDetector(config)
        base_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)

        # Support zone at 100 - 101
        zone = Zone(
            zone_type=ZoneType.SUPPORT,
            price_low=100.0,
            price_high=101.0,
            touches=1,
        )

        # Candle tests zone with lower wick: Low=99.8, Open=102, Close=103, High=103.5
        # Lower wick = 102 - 99.8 = 2.2; Range = 103.5 - 99.8 = 3.7; Wick ratio > 0.40 -> Rejection!
        rejection_candle = _make_candle(base_time, 102.0, 103.5, 99.8, 103.0)
        normal_candle = _make_candle(base_time + timedelta(minutes=5), 101.0, 102.0, 100.5, 101.5)

        detector._count_touches(zone, [rejection_candle, normal_candle])

        assert zone.rejection_count >= 1
        assert zone.freshness_score == 1.0  # touches <= 3 has full freshness

        # Now simulate an over-tested zone (e.g. 7 touches)
        many_candles = [
            _make_candle(base_time + timedelta(minutes=5 * i), 101.0, 102.0, 100.5, 101.2)
            for i in range(8)
        ]
        detector._count_touches(zone, many_candles)
        assert zone.freshness_score < 1.0  # Decays as zone is over-tested

    def test_verified_polarity_flip(self):
        """Verify broken Resistance flips to verified Support after successful retest."""
        config = StrategyConfig(zone_invalidation_threshold_pct=0.3, retest_tolerance_pct=0.5)
        detector = LevelDetector(config)
        base_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)

        # Resistance zone at 100 - 101
        res_zone = Zone(
            zone_type=ZoneType.RESISTANCE,
            price_low=100.0,
            price_high=101.0,
        )

        # 1. Breakout bar closing well above resistance at 103.0
        breakout_bar = _make_candle(base_time, 100.5, 103.5, 100.2, 103.0)
        # 2. Pullback bar retesting 101.2 (holding above broken level) and closing at 102.5
        retest_bar = _make_candle(base_time + timedelta(minutes=5), 102.8, 103.0, 101.1, 102.5)

        detector.update_polarity_flips([res_zone], [breakout_bar, retest_bar])

        assert res_zone.is_flipped is True
        assert res_zone.zone_type == ZoneType.SUPPORT
        assert res_zone.original_type == ZoneType.RESISTANCE

    def test_merge_overlapping_zones(self):
        """Verify overlapping zones of the same type are merged to eliminate chart clutter."""
        detector = LevelDetector(StrategyConfig())

        # Two overlapping support zones: [100, 102] and [101.5, 103.5]
        z1 = Zone(zone_type=ZoneType.SUPPORT, price_low=100.0, price_high=102.0, touches=2)
        z2 = Zone(zone_type=ZoneType.SUPPORT, price_low=101.5, price_high=103.5, touches=3)
        # One separate resistance zone: [110, 112]
        z3 = Zone(zone_type=ZoneType.RESISTANCE, price_low=110.0, price_high=112.0, touches=2)

        merged = detector.merge_overlapping_zones([z1, z2, z3])
        assert len(merged) == 2

        support_merged = [z for z in merged if z.zone_type == ZoneType.SUPPORT][0]
        assert support_merged.price_low == 100.0
        assert support_merged.price_high == 103.5
        assert support_merged.touches == 5
