"""
Shared test fixtures and mock data.

All tests use in-memory SQLite and synthetic candle data
so they can run without live API access.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from algo_monitor.config.settings import RiskConfig, StrategyConfig
from algo_monitor.data.models import Candle
from algo_monitor.database import Database


@pytest.fixture
def tmp_db(tmp_path):
    """Provide a fresh SQLite database for each test."""
    db_path = str(tmp_path / "test.db")
    db = Database(db_path)
    db.initialise()
    return db


@pytest.fixture
def fresh_db(tmp_db):
    """Alias for tmp_db."""
    return tmp_db



@pytest.fixture
def strategy_config():
    """Default strategy config for tests."""
    return StrategyConfig(
        swing_lookback=3,
        zone_tolerance_pct=0.5,
        min_touches=2,
        max_zones=20,
        signal_expiry_candles=12,
        approach_distance_pct=1.0,
        breakout_threshold_pct=0.3,
        retest_tolerance_pct=0.5,
        min_history_candles=20,  # Lower for tests
    )


@pytest.fixture
def risk_config():
    """Default risk config for tests."""
    return RiskConfig(
        starting_balance=1_000_000,
        # Generic fallback (overridden by per-market fields)
        risk_per_trade=0.02,
        # Per-market risk percentages
        indian_cash_risk_per_trade=0.02,
        indian_futures_risk_per_trade=0.02,
        crypto_risk_per_trade=0.02,
        gold_risk_per_trade=0.02,
        max_positions=5,
        max_daily_loss=0.05,
        max_weekly_loss=0.04,
        max_peak_drawdown=0.08,
        max_aggregate_open_risk=0.10,  # High for tests; tests that need it lower set it explicitly
        min_reward_risk=1.5,
        max_leverage=1.0,
        max_capital_per_trade_pct=0.5,
        fee_rate=0.0005,
        slippage_rate=0.0003,
        intraday_expiry_minutes=375,
        swing_max_days=14,
    )



def make_candle(
    price: float,
    idx: int = 0,
    symbol: str = "TEST",
    exchange: str = "test",
    interval: str = "4h",
    base_time: datetime | None = None,
    body_pct: float = 0.3,
    range_pct: float = 1.0,
    bullish: bool = True,
    volume: float = 1000,
) -> Candle:
    """
    Create a synthetic candle at a given price level.

    Args:
        price: Mid-price for the candle
        idx: Candle index (determines timestamp offset)
        body_pct: Body size as % of range
        range_pct: Range size as % of price
        bullish: True for green candle, False for red
    """
    if base_time is None:
        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)

    # Determine interval offset
    if interval == "4h":
        delta = timedelta(hours=4 * idx)
    elif interval == "5m":
        delta = timedelta(minutes=5 * idx)
    elif interval == "1h":
        delta = timedelta(hours=idx)
    else:
        delta = timedelta(hours=4 * idx)

    half_range = price * range_pct / 200
    half_body = price * body_pct / 200

    high = price + half_range
    low = price - half_range

    if bullish:
        open_price = price - half_body
        close_price = price + half_body
    else:
        open_price = price + half_body
        close_price = price - half_body

    return Candle(
        symbol=symbol,
        exchange=exchange,
        interval=interval,
        timestamp=base_time + delta,
        open=round(open_price, 2),
        high=round(high, 2),
        low=round(low, 2),
        close=round(close_price, 2),
        volume=volume,
        is_complete=True,
    )


def make_candle_series(
    base_price: float = 100,
    count: int = 50,
    trend: float = 0,
    volatility: float = 1.0,
    symbol: str = "TEST",
    exchange: str = "test",
    interval: str = "4h",
) -> list[Candle]:
    """
    Generate a series of synthetic candles with optional trend.

    Args:
        base_price: Starting price
        count: Number of candles
        trend: Price change per candle (positive = uptrend)
        volatility: Range multiplier
    """
    import math

    candles = []
    for i in range(count):
        # Sine wave for some realistic price action
        price = base_price + trend * i + math.sin(i * 0.5) * volatility * 2
        bullish = math.sin(i * 0.7) > 0  # Alternate

        candles.append(make_candle(
            price=max(price, 1),
            idx=i,
            symbol=symbol,
            exchange=exchange,
            interval=interval,
            body_pct=0.3 * volatility,
            range_pct=1.0 * volatility,
            bullish=bullish,
        ))

    return candles


def make_swing_candles(
    support_price: float = 95,
    resistance_price: float = 105,
    count: int = 60,
    symbol: str = "TEST",
    exchange: str = "test",
    interval: str = "4h",
) -> list[Candle]:
    """
    Generate candles that oscillate between support and resistance levels,
    creating clear swing highs and lows suitable for S/R detection testing.
    """
    import math

    candles = []
    mid = (support_price + resistance_price) / 2
    amplitude = (resistance_price - support_price) / 2

    for i in range(count):
        # Oscillate between support and resistance
        cycle = math.sin(i * 2 * math.pi / 20)  # ~20 candles per cycle
        price = mid + cycle * amplitude * 0.9

        # Make some candles touch the extremes
        if i % 10 == 5:  # Touch resistance
            price = resistance_price - 0.5
        elif i % 10 == 0:  # Touch support
            price = support_price + 0.5

        bullish = cycle > 0 or (i % 3 == 0)

        candles.append(make_candle(
            price=max(price, 1),
            idx=i,
            symbol=symbol,
            exchange=exchange,
            interval=interval,
            body_pct=0.4,
            range_pct=1.5,
            bullish=bullish,
        ))

    return candles
