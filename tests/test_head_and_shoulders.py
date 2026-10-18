"""
Unit tests for Document 2: Head and Shoulders Pattern Recognition Module.
Tests:
- Standard H&S (Bearish reversal) with S/R neckline confluence
- Inverse H&S (Bullish reversal) with S/R neckline confluence
- Neckline breakout and retest signal triggering
- Measured move target and stop-loss placement
"""

from datetime import datetime, timedelta, timezone
import pytest

from algo_monitor.config.settings import HeadAndShouldersConfig, StrategyConfig
from algo_monitor.data.models import Candle
from algo_monitor.strategy.head_and_shoulders import HeadAndShouldersDetector
from algo_monitor.strategy.levels import Zone, ZoneType
from algo_monitor.strategy.signals import Direction, SetupType


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


class TestHeadAndShouldersDetector:

    def test_standard_head_and_shoulders_breakdown(self):
        """
        Verify detection of standard bearish Head & Shoulders pattern
        with neckline at support zone and breakdown trigger.
        """
        cfg = StrategyConfig(
            swing_lookback=2,
            min_prominence_pct=0.1,
            head_and_shoulders=HeadAndShouldersConfig(
                enabled=True,
                min_head_prominence_pct=0.3,
                shoulder_symmetry_pct=30.0,
                min_pattern_candles=10,
                require_neckline_sr_confluence=True,
                min_reward_risk=1.5,
            ),
        )
        detector = HeadAndShouldersDetector(cfg)

        base = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)

        # Build a synthetic H&S:
        # Left shoulder peak at 105
        # Trough 1 at 100
        # Head peak at 110
        # Trough 2 at 100
        # Right shoulder peak at 105
        # Breakdown bar closing below 100 (e.g. at 98.5)
        pattern_data = [
            # Up to Left Shoulder
            (99, 101, 98, 100),
            (100, 103, 99, 102),
            (102, 105.0, 101, 104),  # LS peak at 105 (idx 2)
            (104, 104.5, 101, 102),
            (102, 102.5, 99.8, 100.5), # Trough 1 around 100 (idx 4)
            # Up to Head
            (100.5, 104, 100, 103),
            (103, 107, 102, 106),
            (106, 110.0, 105, 108),  # Head peak at 110 (idx 7)
            (108, 108.5, 104, 105),
            (105, 101.5, 99.9, 100.4), # Trough 2 around 100 (idx 9, high 101.5)
            # Up to Right Shoulder
            (100.4, 103, 100, 102),
            (102, 105.2, 101, 104),  # RS peak at 105.2 (idx 11)
            (104, 104.5, 101, 102),
            (102, 102.5, 99.5, 100.2),
            # Breakdown bar
            (100.2, 100.5, 97.5, 98.0), # Closes below 100 at 98.0
        ]

        candles = [
            _make_candle(base + timedelta(minutes=5 * i), o, h, l, c)
            for i, (o, h, l, c) in enumerate(pattern_data)
        ]

        # Established Support Zone around 99.5 - 100.5 (Neckline confluence)
        zones = [
            Zone(zone_type=ZoneType.SUPPORT, price_low=99.5, price_high=100.5, touches=3)
        ]

        signals = detector.detect_signals("BTCUSD", "delta", candles, zones)
        assert len(signals) == 1
        sig = signals[0]

        assert sig.direction == Direction.SELL
        assert sig.setup_type == SetupType.HEAD_AND_SHOULDERS
        assert sig.strategy_module == "head_and_shoulders"
        # Stop loss above right shoulder (~105.2)
        assert sig.stop_loss > 105.0
        # Measured target: neckline (~100) - (Head - Neckline) = 100 - (110 - 100) = ~90
        assert sig.target_price < 95.0
        assert sig.reward_risk_ratio >= 1.5

    def test_inverse_head_and_shoulders_breakout(self):
        """
        Verify detection of inverse bullish Head & Shoulders pattern
        with neckline at resistance zone and breakout trigger.
        """
        cfg = StrategyConfig(
            swing_lookback=2,
            min_prominence_pct=0.1,
            head_and_shoulders=HeadAndShouldersConfig(
                enabled=True,
                min_head_prominence_pct=0.3,
                shoulder_symmetry_pct=30.0,
                min_pattern_candles=10,
                require_neckline_sr_confluence=True,
                min_reward_risk=1.5,
            ),
        )
        detector = HeadAndShouldersDetector(cfg)

        base = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)

        # Inverse H&S:
        # Left shoulder trough at 95
        # Peak 1 at 100
        # Head trough at 90
        # Peak 2 at 100
        # Right shoulder trough at 94.8
        # Breakout bar closing above 100 (e.g. at 101.8)
        pattern_data = [
            # Down to Left Shoulder
            (101, 102, 99, 100),
            (100, 101, 97, 98),
            (98, 99, 95.0, 96),       # LS trough at 95 (idx 2)
            (96, 98, 95.5, 97.5),
            (97.5, 100.2, 97, 99.8),  # Peak 1 around 100 (idx 4)
            # Down to Head
            (99.8, 100, 96, 97),
            (97, 98, 93, 94),
            (94, 95, 90.0, 92),       # Head trough at 90 (idx 7)
            (92, 95, 91.5, 94),
            (94, 100.1, 98.5, 99.9),  # Peak 2 around 100 (idx 9, low 98.5)
            # Down to Right Shoulder
            (99.9, 100, 96.5, 97),
            (97, 98, 94.8, 96.5),     # RS trough at 94.8 (idx 11)
            (96.5, 99, 96, 98.5),
            (98.5, 100.1, 98, 99.8),
            # Breakout bar
            (99.8, 102.5, 99.5, 102.0), # Closes above 100 at 102.0
        ]

        candles = [
            _make_candle(base + timedelta(minutes=5 * i), o, h, l, c)
            for i, (o, h, l, c) in enumerate(pattern_data)
        ]

        # Established Resistance Zone around 99.5 - 100.5 (Neckline confluence)
        zones = [
            Zone(zone_type=ZoneType.RESISTANCE, price_low=99.5, price_high=100.5, touches=3)
        ]

        signals = detector.detect_signals("BTCUSD", "delta", candles, zones)
        assert len(signals) == 1
        sig = signals[0]

        assert sig.direction == Direction.BUY
        assert sig.setup_type == SetupType.HEAD_AND_SHOULDERS
        assert sig.strategy_module == "head_and_shoulders"
        # Stop loss below right shoulder (~94.8)
        assert sig.stop_loss < 95.0
        # Measured target: neckline (~100) + (Neckline - Head) = 100 + (100 - 90) = ~110
        assert sig.target_price > 105.0
        assert sig.reward_risk_ratio >= 1.5

    def test_disabled_by_default(self):
        """Verify H&S detector yields 0 signals when disabled in config."""
        cfg = StrategyConfig()
        assert cfg.head_and_shoulders.enabled is False
        detector = HeadAndShouldersDetector(cfg)
        signals = detector.detect_signals("BTCUSD", "delta", [], [])
        assert signals == []
