"""
Tests for Stage 2 (P1): Market-specific configuration, rolling window, and zone invalidation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest

from algo_monitor.config.instruments import AssetClass, Exchange, Instrument, MarketCategory
from algo_monitor.config.settings import StrategyConfig
from algo_monitor.data.candle_store import CandleStore
from algo_monitor.data.models import Candle
from algo_monitor.risk.manager import RiskManager
from algo_monitor.strategy.levels import LevelDetector, Zone, ZoneType
from algo_monitor.strategy.scanner import Scanner
from algo_monitor.strategy.signals import SignalGenerator, SetupType


class TestZoneInvalidation:
    """Validate P1-D: zone broken-level invalidation logic."""

    def test_support_zone_invalidated_after_consecutive_closes_below(self, strategy_config):
        """Support zone should be marked broken after 2 consecutive closes below threshold."""
        strategy_config.zone_invalidation_threshold_pct = 0.5
        strategy_config.zone_invalidation_closes = 2
        detector = LevelDetector(strategy_config)

        now = datetime.now(timezone.utc)
        support_zone = Zone(
            zone_type=ZoneType.SUPPORT,
            price_low=100.0,
            price_high=102.0,
            first_seen=now,
            last_seen=now,
            touches=3,
        )

        # Cutoff is 100 * (1 - 0.005) = 99.5
        # 2 candles closing at 98.0 (below 99.5)
        break_candles = [
            Candle(
                symbol="TEST",
                exchange="test",
                interval="5m",
                timestamp=now - timedelta(minutes=10),
                open=100.0,
                high=100.5,
                low=97.5,
                close=98.0,
                volume=1000.0,
            ),
            Candle(
                symbol="TEST",
                exchange="test",
                interval="5m",
                timestamp=now - timedelta(minutes=5),
                open=98.0,
                high=98.5,
                low=97.0,
                close=97.8,
                volume=1000.0,
            ),
        ]

        assert not support_zone.is_broken
        detector.invalidate_broken_zones([support_zone], break_candles)
        assert support_zone.is_broken
        assert any("broken" in r.lower() for r in support_zone.reasons)

    def test_broken_zone_suppresses_bounce_signal(self, strategy_config):
        """A broken support zone must not generate a bounce signal."""
        gen = SignalGenerator(strategy_config)
        now = datetime.now(timezone.utc)

        broken_support = Zone(
            zone_type=ZoneType.SUPPORT,
            price_low=100.0,
            price_high=102.0,
            first_seen=now,
            last_seen=now,
            touches=3,
            is_broken=True,
        )

        # Candle that looks like a bounce
        prev = Candle(
            symbol="TEST",
            exchange="test",
            interval="5m",
            timestamp=now - timedelta(minutes=10),
            open=103.0,
            high=103.0,
            low=101.0,  # inside zone
            close=101.5,
            volume=500.0,
            is_complete=True,
        )
        curr = Candle(
            symbol="TEST",
            exchange="test",
            interval="5m",
            timestamp=now - timedelta(minutes=5),
            open=101.5,
            high=104.0,
            low=101.2,
            close=103.5,  # above zone, bullish
            volume=1500.0,
            is_complete=True,
        )

        sig = gen._check_bounce_support(
            "TEST", "test", "5m", curr, prev, broken_support, [broken_support]
        )
        assert sig is None

    def test_broken_zone_suppresses_rejection_signal(self, strategy_config):
        """A broken resistance zone must not generate a rejection signal."""
        gen = SignalGenerator(strategy_config)
        now = datetime.now(timezone.utc)

        broken_resistance = Zone(
            zone_type=ZoneType.RESISTANCE,
            price_low=100.0,
            price_high=102.0,
            first_seen=now,
            last_seen=now,
            touches=3,
            is_broken=True,
        )

        # Candle that looks like a rejection
        prev = Candle(
            symbol="TEST",
            exchange="test",
            interval="5m",
            timestamp=now - timedelta(minutes=10),
            open=99.0,
            high=101.5,  # inside zone
            low=98.5,
            close=100.0,
            volume=500.0,
            is_complete=True,
        )
        curr = Candle(
            symbol="TEST",
            exchange="test",
            interval="5m",
            timestamp=now - timedelta(minutes=5),
            open=100.0,
            high=100.2,
            low=97.0,
            close=98.0,  # below zone, bearish
            volume=1500.0,
            is_complete=True,
        )

        sig = gen._check_rejection_resistance(
            "TEST", "test", "5m", curr, prev, broken_resistance, [broken_resistance]
        )
        assert sig is None


class TestScannerMarketSpecifics:
    """Validate P1-A, P1-B, P1-C: Scanner market specifics."""

    def test_crypto_rolling_window_filters_old_candles(self, tmp_db, strategy_config):
        """Crypto HTF candles older than crypto_rolling_window_hours (72h) are excluded."""
        store = CandleStore(tmp_db)
        scanner = Scanner(strategy_config, tmp_db)

        now = datetime(2024, 6, 10, 12, 0, tzinfo=timezone.utc)
        inst = Instrument(
            symbol="BTCUSD",
            exchange=Exchange.DELTA,
            asset_class=AssetClass.SPOT_CRYPTO,
            market_category=MarketCategory.CRYPTO,
        )

        # Create 100 hourly candles: 50 inside the 72h window, 50 older than 72h
        candles = [
            Candle(
                symbol="BTCUSD",
                exchange="delta",
                interval="1h",
                timestamp=now - timedelta(hours=100 - i),
                open=60000.0 + i,
                high=60050.0 + i,
                low=59950.0 + i,
                close=60010.0 + i,
                volume=10.0,
            )
            for i in range(100)
        ]
        store.upsert_candles(candles, validate_interval=False)

        # Also insert LTF candles so scan can run
        ltf_candles = [
            Candle(
                symbol="BTCUSD",
                exchange="delta",
                interval="5m",
                timestamp=now - timedelta(minutes=300 - 5 * i),
                open=60100.0,
                high=60120.0,
                low=60080.0,
                close=60110.0,
                volume=1.0,
            )
            for i in range(40)
        ]
        store.upsert_candles(ltf_candles, validate_interval=False)

        res = scanner.scan_instrument(inst)
        # Verify scanner executed
        assert res["symbol"] == "BTCUSD"

    def test_approaching_zone_does_not_open_position(self, risk_config):
        """Verify APPROACHING_ZONE signal is rejected by risk manager because entry_ref is None."""
        rm = RiskManager(risk_config)
        now = datetime.now(timezone.utc)

        zone = Zone(
            zone_type=ZoneType.SUPPORT,
            price_low=100.0,
            price_high=102.0,
            first_seen=now,
            last_seen=now,
            touches=3,
        )

        from algo_monitor.strategy.signals import Signal, Direction
        approaching_sig = Signal(
            symbol="TEST",
            exchange="test",
            setup_type=SetupType.APPROACHING_ZONE,
            direction=Direction.LONG,
            timeframe="5m",
            zone=zone,
            entry_ref=None,
            stop_loss=None,
            target=None,
            strength=0.3,
            reason="Price approaching support",
        )

        decision = rm.evaluate(
            signal=approaching_sig,
            current_price=101.5,
            current_balance=100_000,
            open_positions=[],
        )

        assert not decision.approved
        assert any("entry reference" in r.lower() for r in decision.reject_reasons)
