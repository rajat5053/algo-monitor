"""
Multi-instrument scanner.

Orchestrates level detection and signal generation across all
enabled instruments.  Designed to be called periodically by the
scheduler or on new candle arrival.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from algo_monitor.config.instruments import Instrument, MarketCategory, get_enabled_instruments
from algo_monitor.data.candle_store import CandleStore
from algo_monitor.strategy.levels import LevelDetector, Zone
from algo_monitor.strategy.signals import Signal, SignalGenerator
from algo_monitor.utils.logging import get_logger

if TYPE_CHECKING:
    from algo_monitor.config.settings import StrategyConfig
    from algo_monitor.database import Database

logger = get_logger("strategy.scanner")


def is_indian_market_hours(dt: datetime | None = None) -> bool:
    """
    Check if current time is within Indian NSE trading hours (Mon-Fri 09:15 - 15:30 IST).
    IST is UTC+05:30.
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    ist = dt.astimezone(timezone(timedelta(hours=5, minutes=30)))
    if ist.weekday() >= 5:  # Saturday or Sunday
        return False
    market_open = ist.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = ist.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= ist <= market_close


class Scanner:
    """
    Scans all enabled instruments for trading setups.

    Workflow per instrument:
    1. Load 4h candles → detect HTF support/resistance zones
    2. Load 5m candles → generate LTF signals against HTF zones
    3. Return consolidated signals and zones
    """

    def __init__(self, config: StrategyConfig, db: Database):
        self.config = config
        self.db = db
        self.store = CandleStore(db)
        self.level_detector = LevelDetector(config)
        self.signal_generator = SignalGenerator(config)

    def scan_instrument(self, instrument: Instrument) -> dict:
        """
        Scan a single instrument for setups.

        Returns:
            {
                'symbol': str,
                'exchange': str,
                'htf_zones': list[Zone],
                'ltf_zones': list[Zone],
                'signals': list[Signal],
                'last_price': float | None,
                'scan_time': datetime,
            }
        """
        symbol = instrument.symbol
        exchange = instrument.exchange.value
        is_indian = (
            exchange == "upstox"
            or getattr(instrument, "market_category", None) == MarketCategory.INDIAN
        )

        # Per-market intervals and thresholds (P1-A, P1-B)
        if is_indian:
            htf_interval = getattr(self.config, "indian_htf_interval", "1d")
            ltf_interval = getattr(self.config, "indian_ltf_interval", "5m")
            lookback_days = getattr(self.config, "indian_lookback_days", 365)
            min_htf = 30
            min_ltf = 30
        else:
            htf_interval = getattr(self.config, "crypto_htf_interval", "1h")
            ltf_interval = getattr(self.config, "crypto_ltf_interval", "5m")
            rolling_hours = getattr(self.config, "crypto_rolling_window_hours", 72)
            min_htf = min(24, rolling_hours // 3)
            min_ltf = 30

        # Load HTF candles for zone detection
        if is_indian:
            htf_candles = self.store.get_candles(
                symbol, exchange, htf_interval,
                limit=lookback_days,
            )
            if not htf_candles:
                # P1-C: Fallback only to exact alias for same interval
                alias = "day" if htf_interval == "1d" else ("1d" if htf_interval == "day" else None)
                if alias:
                    htf_candles = self.store.get_candles(symbol, exchange, alias, limit=lookback_days)
        else:
            # P1-A: Crypto rolling window enforcement
            active_htf = htf_interval
            latest_ts = self.store.get_latest_timestamp(symbol, exchange, active_htf)
            if not latest_ts:
                # If configured 1h interval not yet ingested, fall back to 4h
                for alt in ("4h", "1d"):
                    if alt != active_htf:
                        latest_ts = self.store.get_latest_timestamp(symbol, exchange, alt)
                        if latest_ts:
                            active_htf = alt
                            min_htf = min(12, rolling_hours // 4)
                            break

            if latest_ts:
                cutoff = latest_ts - timedelta(hours=rolling_hours)
            else:
                cutoff = datetime.now(timezone.utc) - timedelta(hours=rolling_hours)

            htf_candles = self.store.get_candles(
                symbol, exchange, active_htf,
                start=cutoff,
                limit=100,
            )
            htf_candles = [c for c in htf_candles if c.timestamp >= cutoff]

        # Load LTF candles (5m) for signal confirmation
        ltf_candles = self.store.get_candles(
            symbol, exchange, ltf_interval,
            limit=300,
        )
        if not ltf_candles and is_indian:
            # P1-C: Fallback only to exact alias for same interval
            alias = "5minute" if ltf_interval == "5m" else ("5m" if ltf_interval == "5minute" else None)
            if alias:
                ltf_candles = self.store.get_candles(symbol, exchange, alias, limit=300)

        result = {
            "symbol": symbol,
            "exchange": exchange,
            "htf_zones": [],
            "ltf_zones": [],
            "signals": [],
            "last_price": None,
            "scan_time": datetime.now(timezone.utc),
        }

        latest_candle = ltf_candles[-1] if ltf_candles else (htf_candles[-1] if htf_candles else None)
        if latest_candle:
            result["last_price"] = latest_candle.close

        if ltf_candles:
            latest = ltf_candles[-1]
            candle_age = (datetime.now(timezone.utc) - latest.timestamp).total_seconds()
            market_open = is_indian_market_hours() if is_indian else True

            # During market hours, candles from today's session (up to 6h old) are active
            freshness_threshold = 21600 if (is_indian and market_open) else 7200
            if candle_age > freshness_threshold:
                logger.info(
                    "Candles for %s are historical (%.1f h old, market_open=%s). Zones detected, but signals suppressed to prevent outdated alerts.",
                    symbol, candle_age / 3600, market_open,
                )
                if len(htf_candles) >= min_htf:
                    result["htf_zones"] = self.level_detector.detect_zones(
                        htf_candles, reference_price=latest.close
                    )
                if len(ltf_candles) >= min_ltf:
                    result["ltf_zones"] = self.level_detector.detect_zones(
                        ltf_candles, reference_price=latest.close
                    )
                return result

        # Detect HTF zones
        if len(htf_candles) >= min_htf:
            ref_price = latest_candle.close if latest_candle else 0
            result["htf_zones"] = self.level_detector.detect_zones(
                htf_candles, reference_price=ref_price
            )
        else:
            logger.info(
                "Insufficient HTF candles for %s (%d < %d)",
                symbol, len(htf_candles), min_htf,
            )

        # Detect LTF zones (for additional context)
        if len(ltf_candles) >= min_ltf:
            ref_price = latest_candle.close if latest_candle else 0
            result["ltf_zones"] = self.level_detector.detect_zones(
                ltf_candles, reference_price=ref_price
            )

        # Generate signals using LTF candles against HTF zones
        if ltf_candles and result["htf_zones"]:
            result["signals"] = self.signal_generator.generate_signals(
                symbol=symbol,
                exchange=exchange,
                candles=ltf_candles,
                zones=result["ltf_zones"],
                htf_zones=result["htf_zones"],
            )

        return result

    def scan_all(
        self, instruments: list[Instrument] | None = None
    ) -> list[dict]:
        """Scan all enabled instruments and return results."""
        if instruments is None:
            instruments = get_enabled_instruments()

        # Filter by market toggle
        indian_enabled = self.db.get_state("market_toggle_indian", "true") == "true"
        crypto_enabled = self.db.get_state("market_toggle_crypto", "true") == "true"

        filtered_instruments = []
        for inst in instruments:
            cat = getattr(inst, "market_category", None)
            if cat == MarketCategory.INDIAN and not indian_enabled:
                continue
            if cat == MarketCategory.CRYPTO and not crypto_enabled:
                continue
            filtered_instruments.append(inst)

        results = []
        for inst in filtered_instruments:
            try:
                result = self.scan_instrument(inst)
                results.append(result)
                if result["signals"]:
                    logger.info(
                        "%s: %d signals, %d zones",
                        inst.symbol,
                        len(result["signals"]),
                        len(result["htf_zones"]),
                    )
            except Exception as exc:
                logger.error("Scan failed for %s: %s", inst.symbol, exc)
                results.append({
                    "symbol": inst.symbol,
                    "exchange": inst.exchange.value,
                    "htf_zones": [],
                    "ltf_zones": [],
                    "signals": [],
                    "last_price": None,
                    "scan_time": datetime.now(timezone.utc),
                    "error": str(exc),
                })

        total_signals = sum(len(r.get("signals", [])) for r in results)
        logger.info(
            "Scan complete: %d instruments, %d total signals",
            len(results), total_signals,
        )
        return results
