"""
Data models used across the data layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


@dataclass
class Candle:
    """A single OHLCV candle."""

    symbol: str
    exchange: str
    interval: str
    timestamp: datetime        # UTC, start of the candle
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    is_complete: bool = True

    def validate(self) -> list[str]:
        """Return a list of validation errors, empty if valid."""
        errors = []
        if self.high < self.low:
            errors.append(f"high ({self.high}) < low ({self.low})")
        if self.open < self.low or self.open > self.high:
            errors.append(f"open ({self.open}) outside high-low range")
        if self.close < self.low or self.close > self.high:
            errors.append(f"close ({self.close}) outside high-low range")
        if self.volume < 0:
            errors.append(f"negative volume ({self.volume})")
        if any(v <= 0 for v in (self.open, self.high, self.low, self.close)):
            errors.append("non-positive price value")
        return errors

    @property
    def body_size(self) -> float:
        return abs(self.close - self.open)

    @property
    def range_size(self) -> float:
        return self.high - self.low

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open

    @property
    def mid_price(self) -> float:
        return (self.high + self.low) / 2


class TickerUpdate:
    """Real-time ticker data from a WebSocket feed."""

    def __init__(
        self,
        symbol: str,
        exchange: str,
        last_price: float,
        mark_price: float | None = None,
        bid: float | None = None,
        ask: float | None = None,
        volume_24h: float | None = None,
        high_24h: float | None = None,
        low_24h: float | None = None,
        timestamp: datetime | None = None,
    ):
        self.symbol = symbol
        self.exchange = exchange
        self.last_price = last_price
        self.mark_price = mark_price
        self.bid = bid
        self.ask = ask
        self.volume_24h = volume_24h
        self.high_24h = high_24h
        self.low_24h = low_24h
        self.timestamp = timestamp or datetime.utcnow()

    @property
    def spread(self) -> float | None:
        if self.bid is not None and self.ask is not None and self.bid > 0:
            return (self.ask - self.bid) / self.bid
        return None


class ConnectionStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    ERROR = "error"
