"""
Tests for market data ingestion and candle validation (P0-A).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest

from algo_monitor.data.candle_store import CandleStore
from algo_monitor.data.ingestion import (
    _UPSTOX_INTERVALS,
    CANDLE_DURATION_SECONDS,
    check_candle_duration,
)
from algo_monitor.data.models import Candle


class TestIngestionIntervalMapping:
    """Validate interval definitions and mappings."""

    def test_upstox_interval_mapping_correctness(self):
        """Verify Upstox intervals map to exact API strings, not wrong approximations."""
        assert _UPSTOX_INTERVALS["5m"] == "5minute"
        assert _UPSTOX_INTERVALS["15m"] == "15minute"
        assert _UPSTOX_INTERVALS["30m"] == "30minute"
        assert _UPSTOX_INTERVALS["1h"] == "60minute"
        assert _UPSTOX_INTERVALS["1d"] == "1day"
        assert "4h" not in _UPSTOX_INTERVALS  # Upstox doesn't support 4h directly

    def test_candle_duration_detection_warning(self):
        """Spot check warns when 30m gaps are labelled as 5m."""
        base_time = datetime(2024, 1, 1, 9, 15, tzinfo=timezone.utc)
        # Create candles spaced 30 minutes apart
        candles = [
            Candle(
                symbol="NIFTY",
                exchange="upstox",
                interval="5m",
                timestamp=base_time + timedelta(minutes=30 * i),
                open=20000.0,
                high=20050.0,
                low=19980.0,
                close=20020.0,
                volume=1000.0,
            )
            for i in range(5)
        ]

        warnings = check_candle_duration(candles, "5m")
        assert len(warnings) > 0
        assert "Duration mismatch" in warnings[0]

    def test_candle_duration_detection_valid(self):
        """No warning when 5m candles have 5m spacing."""
        base_time = datetime(2024, 1, 1, 9, 15, tzinfo=timezone.utc)
        candles = [
            Candle(
                symbol="NIFTY",
                exchange="upstox",
                interval="5m",
                timestamp=base_time + timedelta(minutes=5 * i),
                open=20000.0,
                high=20050.0,
                low=19980.0,
                close=20020.0,
                volume=1000.0,
            )
            for i in range(5)
        ]

        warnings = check_candle_duration(candles, "5m")
        assert len(warnings) == 0


class TestCandleStoreDurationValidation:
    """Validate CandleStore guard against mislabelled candles."""

    def test_candle_store_rejects_mislabelled(self, tmp_db):
        """CandleStore should raise ValueError when 30m spaced candles are stored under 5m."""
        store = CandleStore(tmp_db)
        base_time = datetime(2024, 1, 1, 9, 15, tzinfo=timezone.utc)
        mislabelled_candles = [
            Candle(
                symbol="NIFTY",
                exchange="upstox",
                interval="5m",
                timestamp=base_time + timedelta(minutes=30 * i),
                open=20000.0,
                high=20050.0,
                low=19980.0,
                close=20020.0,
                volume=1000.0,
            )
            for i in range(5)
        ]

        with pytest.raises(ValueError, match="Candle duration mismatch"):
            store.upsert_candles(mislabelled_candles, validate_interval=True)

    def test_candle_store_accepts_valid_interval(self, tmp_db):
        """CandleStore accepts correctly spaced candles."""
        store = CandleStore(tmp_db)
        base_time = datetime(2024, 1, 1, 9, 15, tzinfo=timezone.utc)
        valid_candles = [
            Candle(
                symbol="NIFTY",
                exchange="upstox",
                interval="5m",
                timestamp=base_time + timedelta(minutes=5 * i),
                open=20000.0,
                high=20050.0,
                low=19980.0,
                close=20020.0,
                volume=1000.0,
            )
            for i in range(5)
        ]

        count = store.upsert_candles(valid_candles, validate_interval=True)
        assert count == 5
