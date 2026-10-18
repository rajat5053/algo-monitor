"""
Historical candle ingestion service.

Fetches, validates, and stores OHLCV candles from supported exchanges.
Supports incremental updates and handles API pagination, rate limits, and errors.

Upstox API interval support (v2 historical-candle endpoint):
    1minute, 5minute, 15minute, 30minute, 60minute, 1day, 1week, 1month
    Note: "4hour" is NOT a valid Upstox interval. Use "1d" for daily zones.
    Note: Intraday intervals (< 1day) have a 100-day maximum lookback window.

Delta Exchange interval support:
    1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 1d, 1w
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from algo_monitor.config.instruments import Exchange, Instrument
from algo_monitor.data.models import Candle
from algo_monitor.utils.logging import get_logger

if TYPE_CHECKING:
    from algo_monitor.data.candle_store import CandleStore
    from algo_monitor.data.delta_exchange import DeltaExchangeClient
    from algo_monitor.data.upstox import UpstoxClient

logger = get_logger("data.ingestion")

# ---------------------------------------------------------------------------
# Interval mapping tables
# ---------------------------------------------------------------------------

# Map our standard interval labels to Delta Exchange resolution strings.
_DELTA_INTERVALS: dict[str, str] = {
    "1m":  "1m",
    "5m":  "5m",
    "15m": "15m",
    "30m": "30m",
    "1h":  "1h",
    "4h":  "4h",
    "1d":  "1d",
}

# Map our standard interval labels to Upstox v2 historical-candle interval strings.
#
# CORRECTION (P0-A): The previous mapping was:
#   "5m" → "30minute"  (WRONG — fetched 30-minute bars, stored as "5m")
#   "1h" → "30minute"  (WRONG — fetched 30-minute bars, stored as "1h")
#   "4h" → "day"       (WRONG — fetched daily bars, stored as "4h")
#
# Upstox valid values: 1minute, 5minute, 15minute, 30minute, 60minute,
#                      1day, 1week, 1month
# "4h" does not exist in the Upstox API. Indian market strategy must use "1d".
_UPSTOX_INTERVALS: dict[str, str] = {
    "1m":  "1minute",
    "5m":  "5minute",
    "15m": "15minute",
    "30m": "30minute",
    "1h":  "60minute",
    "1d":  "1day",
    "1w":  "1week",
    "1M":  "1month",
}

# Maximum lookback in calendar days for Upstox intraday endpoints.
# Upstox restricts intraday historical data to the most recent ~100 days.
_UPSTOX_INTRADAY_MAX_DAYS = 100

# Intervals that Upstox treats as "intraday" (subject to the 100-day limit).
_UPSTOX_INTRADAY_INTERVALS = {"1m", "5m", "15m", "30m", "1h"}

# Expected candle duration in seconds for each standard interval label.
# Used to validate that returned candles actually cover the correct duration.
# A "5m" candle stored with 1800-second gaps is a 30-minute candle mislabelled.
CANDLE_DURATION_SECONDS: dict[str, int] = {
    "1m":   60,
    "5m":   300,
    "15m":  900,
    "30m":  1800,
    "1h":   3600,
    "4h":   14400,
    "1d":   86400,
    "1w":   604800,
    "1M":   2592000,   # ~30 days; approximate
}

# Tolerance factor for candle duration validation (allow ±20% for gaps/holidays).
_DURATION_TOLERANCE = 0.20


def check_candle_duration(
    candles: list[Candle],
    expected_interval: str,
    sample_size: int = 10,
) -> list[str]:
    """
    Spot-check that consecutive candle timestamps reflect the expected interval.

    Returns a list of warning strings (empty = no problems found).
    This is a sanity check, not a hard rejection filter, because:
    - Weekend/holiday gaps produce larger-than-expected gaps for daily candles.
    - Market microstructure may cause occasional missing bars.

    Uses the median gap from the first `sample_size` consecutive pairs.
    """
    warnings: list[str] = []
    if len(candles) < 2 or expected_interval not in CANDLE_DURATION_SECONDS:
        return warnings

    expected_secs = CANDLE_DURATION_SECONDS[expected_interval]
    # Use a sample near the beginning (older data, more complete)
    sample = candles[:min(len(candles), sample_size + 1)]
    gaps = []
    for i in range(1, len(sample)):
        gap = (sample[i].timestamp - sample[i - 1].timestamp).total_seconds()
        if gap > 0:
            gaps.append(gap)

    if not gaps:
        return warnings

    gaps.sort()
    median_gap = gaps[len(gaps) // 2]
    lower = expected_secs * (1 - _DURATION_TOLERANCE)
    upper = expected_secs * (1 + _DURATION_TOLERANCE)

    if not (lower <= median_gap <= upper):
        warnings.append(
            f"Duration mismatch: interval='{expected_interval}' expects "
            f"~{expected_secs}s between candles, but median gap is "
            f"{median_gap:.0f}s. "
            f"Possible mislabelled timeframe data."
        )

    return warnings


class IngestionService:
    """
    Orchestrates historical candle fetching and storage.

    Usage:
        svc = IngestionService(candle_store, delta_client, upstox_client)
        result = svc.ingest(instrument, intervals=['1d', '5m'], lookback_days=365)
    """

    def __init__(
        self,
        store: "CandleStore",
        delta_client: "DeltaExchangeClient | None" = None,
        upstox_client: "UpstoxClient | None" = None,
    ):
        self.store = store
        self.delta = delta_client
        self.upstox = upstox_client

    def ingest(
        self,
        instrument: Instrument,
        intervals: list[str] | None = None,
        lookback_days: int = 90,
        force_full: bool = False,
    ) -> dict[str, int]:
        """
        Fetch and store historical candles for an instrument.

        Args:
            instrument: Instrument to fetch data for.
            intervals: List of intervals. Defaults based on market category:
                       Indian → ['1d', '5m']  (daily zones + 5-min entries)
                       Crypto → ['1h', '5m']  (hourly context + 5-min entries)
            lookback_days: How far back to fetch.
            force_full: If True, ignore cached data and refetch everything.

        Returns:
            Dict mapping interval → number of candles stored.
        """
        if intervals is None:
            from algo_monitor.config.instruments import MarketCategory
            if instrument.market_category == MarketCategory.INDIAN:
                intervals = ["1d", "5m"]
            else:
                intervals = ["1h", "5m"]

        results = {}
        for interval in intervals:
            try:
                count = self._ingest_interval(
                    instrument, interval, lookback_days, force_full
                )
                results[interval] = count
            except Exception as exc:
                logger.error(
                    "Ingestion failed for %s/%s/%s: %s",
                    instrument.symbol,
                    instrument.exchange.value,
                    interval,
                    exc,
                )
                results[interval] = 0

        return results

    def ingest_all(
        self,
        instruments: list[Instrument],
        intervals: list[str] | None = None,
        lookback_days: int = 90,
    ) -> dict[str, dict[str, int]]:
        """Ingest candles for multiple instruments."""
        all_results = {}
        for inst in instruments:
            logger.info("Ingesting %s (%s)...", inst.symbol, inst.exchange.value)
            all_results[inst.symbol] = self.ingest(inst, intervals, lookback_days)
            time.sleep(0.5)  # Be nice to APIs
        return all_results

    def _ingest_interval(
        self,
        instrument: Instrument,
        interval: str,
        lookback_days: int,
        force_full: bool,
    ) -> int:
        """Fetch and store candles for a single instrument/interval."""
        now = datetime.now(timezone.utc)

        # Determine start time (incremental or full)
        if not force_full:
            latest = self.store.get_latest_timestamp(
                instrument.symbol, instrument.exchange.value, interval
            )
            if latest:
                start = latest  # Fetch from last known candle
            else:
                start = now - timedelta(days=lookback_days)
        else:
            start = now - timedelta(days=lookback_days)

        end = now

        # Fetch from the right exchange
        if instrument.exchange == Exchange.DELTA:
            candles = self._fetch_delta(instrument.symbol, interval, start, end)
        elif instrument.exchange == Exchange.UPSTOX:
            candles = self._fetch_upstox(instrument, interval, start, end)
        else:
            logger.warning("Unsupported exchange: %s", instrument.exchange)
            return 0

        if not candles:
            logger.info(
                "No new candles for %s/%s", instrument.symbol, interval
            )
            return 0

        # Validate candle duration consistency (P0-A sanity check)
        duration_warnings = check_candle_duration(candles, interval)
        for warn in duration_warnings:
            logger.warning(
                "INTERVAL MISMATCH for %s/%s: %s",
                instrument.symbol, interval, warn,
            )

        # Validate individual candle OHLCV integrity
        valid_candles = []
        for c in candles:
            errors = c.validate()
            if errors:
                logger.warning("Skipping invalid candle: %s", errors)
                continue
            valid_candles.append(c)

        # Remove incomplete current candle (prevent look-ahead)
        if valid_candles and not valid_candles[-1].is_complete:
            valid_candles.pop()

        count = self.store.upsert_candles(valid_candles)
        logger.info(
            "Stored %d candles for %s/%s/%s",
            count,
            instrument.symbol,
            instrument.exchange.value,
            interval,
        )
        return count

    def _fetch_delta(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        """Fetch candles from Delta Exchange."""
        if not self.delta:
            logger.warning("Delta client not configured")
            return []

        resolution = _DELTA_INTERVALS.get(interval, interval)
        return self.delta.get_candles_paginated(
            symbol=symbol,
            resolution=resolution,
            start=start,
            end=end,
        )

    def _fetch_upstox(
        self,
        instrument: Instrument,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        """
        Fetch candles from Upstox.

        Enforces the Upstox intraday 100-day history limit.
        If the requested interval is not in the Upstox mapping, reports the
        limitation and returns an empty list rather than substituting a
        different timeframe.
        """
        if not self.upstox:
            logger.warning("Upstox client not configured")
            return []

        if not instrument.instrument_key:
            logger.warning(
                "No instrument_key for %s; cannot fetch Upstox data",
                instrument.symbol,
            )
            return []

        upstox_interval = _UPSTOX_INTERVALS.get(interval)
        if upstox_interval is None:
            logger.error(
                "Interval '%s' is not supported by Upstox API. "
                "Upstox supports: %s. "
                "Returning empty — no substitute timeframe will be used.",
                interval,
                list(_UPSTOX_INTERVALS.keys()),
            )
            return []

        # Enforce Upstox intraday lookback limit
        if interval in _UPSTOX_INTRADAY_INTERVALS:
            max_start = end - timedelta(days=_UPSTOX_INTRADAY_MAX_DAYS)
            if start < max_start:
                logger.info(
                    "Upstox intraday limit: capping start from %s to %s "
                    "(100-day maximum for %s)",
                    start.date(), max_start.date(), interval,
                )
                start = max_start

        return self.upstox.get_candles(
            instrument_key=instrument.instrument_key,
            interval=upstox_interval,
            from_date=start.strftime("%Y-%m-%d"),
            to_date=end.strftime("%Y-%m-%d"),
            symbol=instrument.symbol,
            storage_interval=interval,
        )
