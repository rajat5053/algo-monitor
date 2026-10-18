"""
Unit tests for Document 2: Firsty Trend Continuation Strategy Module.
Tests:
- EMA separation and slope validation
- Value area pullback into EMA and S/R zone confluence
- Rejection trigger candle detection
- Bullish and Bearish signal generation
- Independence and toggling via config
"""

from datetime import datetime, timedelta, timezone
import pytest

from algo_monitor.config.settings import FirstyContinuationConfig, StrategyConfig
from algo_monitor.data.models import Candle
from algo_monitor.strategy.levels import Zone, ZoneType
from algo_monitor.strategy.signals import Direction, SetupType
from algo_monitor.strategy.trend_continuation import FirstyContinuationDetector, calculate_ema


def _make_candle(timestamp: datetime, o: float, h: float, l: float, c: float) -> Candle:
    return Candle(
        symbol="ETHUSD",
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


class TestFirstyTrendContinuation:

    def test_ema_calculation(self):
        """Verify EMA calculation matches exponential smoothing formula."""
        prices = [10.0] * 20 + [20.0] * 10
        ema = calculate_ema(prices, 10)
        assert len(ema) == len(prices)
        assert ema[9] == 10.0  # Initial SMA seed
        assert ema[-1] > 15.0  # Transitioning upwards towards 20

    def test_bullish_continuation_setup(self):
        """
        Verify bullish continuation:
        Fast EMA > Slow EMA, pullback to 20 EMA + Support zone, hammer-like rejection candle.
        """
        cfg = StrategyConfig(
            firsty_continuation=FirstyContinuationConfig(
                enabled=True,
                fast_ema_period=5,
                slow_ema_period=15,
                trend_slope_lookback=3,
                min_separation_atr_mult=0.1,
                pullback_tolerance_atr_mult=0.8,
                require_sr_confluence=True,
                min_rejection_wick_ratio=0.25,
                min_reward_risk=1.5,
            )
        )
        detector = FirstyContinuationDetector(cfg)
        base = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)

        # 30 bars in steady uptrend, then a pullback to EMA with lower wick rejection
        candles = []
        price = 100.0
        for i in range(25):
            o = price
            c = price + 1.0
            h = c + 0.5
            l = o - 0.2
            candles.append(_make_candle(base + timedelta(minutes=5 * i), o, h, l, c))
            price = c

        # Bar 25: Pullback bar dipping towards EMA
        candles.append(_make_candle(base + timedelta(minutes=5 * 25), 125.0, 126.0, 120.0, 121.0))

        # Bar 26: Trigger candle: opens at 121, dips to 118 (tests support zone at 118-120),
        # but strongly rejects upwards to close at 124 (High 124.5).
        # Lower wick = min(121, 124) - 118 = 3.0. Range = 124.5 - 118 = 6.5. Wick ratio ~ 46%!
        trigger_candle = _make_candle(base + timedelta(minutes=5 * 26), 121.0, 124.5, 118.0, 124.0)
        candles.append(trigger_candle)

        # Active Support Zone at 118-120 (S/R confluence)
        zones = [
            Zone(zone_type=ZoneType.SUPPORT, price_low=118.0, price_high=120.0, touches=3),
            Zone(zone_type=ZoneType.RESISTANCE, price_low=135.0, price_high=137.0, touches=2),
        ]

        signals = detector.detect_signals("ETHUSD", "delta", candles, zones)
        assert len(signals) == 1
        sig = signals[0]

        assert sig.direction == Direction.BUY
        assert sig.setup_type == SetupType.FIRSTY_CONTINUATION
        assert sig.strategy_module == "firsty_continuation"
        assert sig.entry_price == 124.0
        assert sig.stop_loss < 118.0
        assert sig.target_price >= 135.0
        assert sig.reward_risk_ratio >= 1.5

    def test_bearish_continuation_setup(self):
        """
        Verify bearish continuation:
        Fast EMA < Slow EMA, pullback to 20 EMA + Resistance zone, shooting-star rejection candle.
        """
        cfg = StrategyConfig(
            firsty_continuation=FirstyContinuationConfig(
                enabled=True,
                fast_ema_period=5,
                slow_ema_period=15,
                trend_slope_lookback=3,
                min_separation_atr_mult=0.1,
                pullback_tolerance_atr_mult=0.8,
                require_sr_confluence=True,
                min_rejection_wick_ratio=0.25,
                min_reward_risk=1.5,
            )
        )
        detector = FirstyContinuationDetector(cfg)
        base = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)

        # 25 bars in downtrend
        candles = []
        price = 150.0
        for i in range(25):
            o = price
            c = price - 1.0
            h = o + 0.2
            l = c - 0.5
            candles.append(_make_candle(base + timedelta(minutes=5 * i), o, h, l, c))
            price = c

        # Bar 25: Pullback bar rising towards EMA
        candles.append(_make_candle(base + timedelta(minutes=5 * 25), 125.0, 129.0, 124.0, 128.0))

        # Bar 26: Trigger candle: opens at 128, spikes to 132 (tests resistance zone at 130-132),
        # but gets rejected back down to close at 126 (Low 125.5).
        # Upper wick = 132 - max(128, 126) = 4.0. Range = 132 - 125.5 = 6.5. Wick ratio > 50%!
        trigger_candle = _make_candle(base + timedelta(minutes=5 * 26), 128.0, 132.0, 125.5, 126.0)
        candles.append(trigger_candle)

        # Active Resistance Zone at 130-132 (S/R confluence)
        zones = [
            Zone(zone_type=ZoneType.RESISTANCE, price_low=130.0, price_high=132.0, touches=3),
            Zone(zone_type=ZoneType.SUPPORT, price_low=110.0, price_high=112.0, touches=2),
        ]

        signals = detector.detect_signals("ETHUSD", "delta", candles, zones)
        assert len(signals) == 1
        sig = signals[0]

        assert sig.direction == Direction.SELL
        assert sig.setup_type == SetupType.FIRSTY_CONTINUATION
        assert sig.strategy_module == "firsty_continuation"
        assert sig.entry_price == 126.0
        assert sig.stop_loss > 132.0
        assert sig.target_price <= 112.0
        assert sig.reward_risk_ratio >= 1.5
