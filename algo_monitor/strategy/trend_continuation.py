"""
Firsty-Style Trend Continuation Strategy Module (Document 2 Requirement).

Implements deterministic rules for moving-average trend continuation:
1. Moving Average Separation:
   - Fast EMA (e.g. 20) and Slow EMA (e.g. 50).
   - Trend defined by EMA alignment (Fast > Slow for Uptrend, Fast < Slow for Downtrend)
     and directional slope over a lookback window.
   - Minimum separation between EMAs (in instrument-aware ATR multiples, not fixed forex pips)
     to filter out sluggish or consolidating markets.

2. Value Area Pullback:
   - Price pulls back into the dynamic value zone between/around Fast and Slow EMAs.

3. S/R Confluence:
   - The pullback location coincides with an established Support Zone (for long)
     or Resistance Zone (for short), or a freshly flipped polarity zone.

4. Directional Trigger Candle:
   - Price rejects the EMA / S/R zone with a decisive wick in the direction of support/resistance
     (wick ratio >= min_rejection_wick_ratio) and closes in the continuation direction.

5. Risk Validation:
   - Stop-Loss placed beyond the rejection candle's extreme or S/R zone boundary.
   - Target projected to the next opposing S/R zone or fixed RR multiple (>= min_reward_risk).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from algo_monitor.data.models import Candle
from algo_monitor.strategy.levels import Zone, ZoneType, calculate_atr
from algo_monitor.strategy.signals import Direction, SetupType, Signal
from algo_monitor.utils.logging import get_logger

if TYPE_CHECKING:
    from algo_monitor.config.settings import StrategyConfig

logger = get_logger("strategy.trend_continuation")


def calculate_ema(values: list[float], period: int) -> list[float]:
    """
    Calculate Exponential Moving Average for a series of values.
    Returns a list of the same length as values.
    """
    n = len(values)
    if n == 0:
        return []
    if period <= 1 or n < period:
        # Fallback to cumulative average or raw values
        return list(values)

    multiplier = 2.0 / (period + 1.0)
    ema: list[float] = [0.0] * n

    # Seed with SMA of first `period` bars
    sma = sum(values[:period]) / period
    for i in range(period):
        ema[i] = sma

    for i in range(period, n):
        ema[i] = (values[i] - ema[i - 1]) * multiplier + ema[i - 1]

    return ema


@dataclass
class FirstyContinuationDetector:
    """
    Detector for Firsty-style EMA Trend Continuation setups with S/R confluence.
    """

    config: StrategyConfig

    @property
    def tc_cfg(self):
        return self.config.firsty_continuation

    def detect_signals(
        self,
        symbol: str,
        exchange: str,
        candles: list[Candle],
        zones: list[Zone],
        timeframe: str = "5m",
    ) -> list[Signal]:
        """
        Scan candles for Firsty-style trend-continuation signals.
        """
        if not self.tc_cfg.enabled:
            return []

        completed = [c for c in candles if c.is_complete]
        min_required = max(self.tc_cfg.slow_ema_period + 5, 15)
        if len(completed) < min_required:
            return []

        closes = [c.close for c in completed]
        fast_ema = calculate_ema(closes, self.tc_cfg.fast_ema_period)
        slow_ema = calculate_ema(closes, self.tc_cfg.slow_ema_period)
        atr_val = calculate_atr(completed, period=14)

        if atr_val <= 0:
            return []

        curr_idx = len(completed) - 1
        current = completed[curr_idx]
        prev = completed[curr_idx - 1]

        fast_curr = fast_ema[curr_idx]
        slow_curr = slow_ema[curr_idx]
        ema_diff = fast_curr - slow_curr

        # Minimum EMA separation check
        min_sep = self.tc_cfg.min_separation_atr_mult * atr_val
        if abs(ema_diff) < min_sep:
            return []

        # Trend slope check
        slope_bars = min(self.tc_cfg.trend_slope_lookback, curr_idx)
        fast_slope = fast_curr - fast_ema[curr_idx - slope_bars]

        signals: list[Signal] = []

        # -------------------------------------------------------------
        # 1. Bullish Trend Continuation (Fast > Slow, Positive Slope)
        # -------------------------------------------------------------
        if ema_diff > 0 and fast_slope > 0:
            bull_signal = self._evaluate_bullish_continuation(
                symbol=symbol,
                exchange=exchange,
                completed=completed,
                curr_idx=curr_idx,
                fast_ema=fast_curr,
                slow_ema=slow_curr,
                atr_val=atr_val,
                zones=zones,
                timeframe=timeframe,
            )
            if bull_signal:
                signals.append(bull_signal)

        # -------------------------------------------------------------
        # 2. Bearish Trend Continuation (Fast < Slow, Negative Slope)
        # -------------------------------------------------------------
        elif ema_diff < 0 and fast_slope < 0:
            bear_signal = self._evaluate_bearish_continuation(
                symbol=symbol,
                exchange=exchange,
                completed=completed,
                curr_idx=curr_idx,
                fast_ema=fast_curr,
                slow_ema=slow_curr,
                atr_val=atr_val,
                zones=zones,
                timeframe=timeframe,
            )
            if bear_signal:
                signals.append(bear_signal)

        return signals

    def _evaluate_bullish_continuation(
        self,
        symbol: str,
        exchange: str,
        completed: list[Candle],
        curr_idx: int,
        fast_ema: float,
        slow_ema: float,
        atr_val: float,
        zones: list[Zone],
        timeframe: str,
    ) -> Signal | None:
        current = completed[curr_idx]
        prev = completed[curr_idx - 1]

        # Pullback check: low of current or prev candle reached near fast EMA or into EMA zone
        pullback_tol = self.tc_cfg.pullback_tolerance_atr_mult * atr_val
        lowest_low = min(current.low, prev.low)
        highest_low = max(current.low, prev.low)

        # Bullish pullback should touch fast_ema + tolerance, but not collapse far below slow_ema
        tested_value_area = (
            lowest_low <= fast_ema + pullback_tol and
            lowest_low >= slow_ema - pullback_tol
        )
        if not tested_value_area:
            return None

        # S/R Confluence check
        confluent_zone: Zone | None = None
        if self.tc_cfg.require_sr_confluence:
            # Look for active Support zone (or flipped Resistance-to-Support)
            for z in zones:
                if z.is_broken:
                    continue
                if z.zone_type == ZoneType.SUPPORT:
                    # Check if lowest_low interacted with this zone
                    tol = z.price_high * (self.tc_cfg.sr_confluence_tolerance_pct / 100.0)
                    if (lowest_low <= z.price_high + tol) and (highest_low >= z.price_low - tol):
                        confluent_zone = z
                        break
            if confluent_zone is None:
                return None

        # Trigger candle evaluation
        candle_range = current.high - current.low
        if candle_range <= 0:
            return None

        # Lower rejection wick
        lower_wick = min(current.open, current.close) - current.low
        wick_ratio = lower_wick / candle_range

        if wick_ratio < self.tc_cfg.min_rejection_wick_ratio:
            return None

        # Candle should close bullish or close above fast EMA
        if current.close <= current.open and current.close < fast_ema:
            return None

        entry_price = current.close
        buffer = 0.15 * atr_val
        stop_loss = lowest_low - buffer

        if stop_loss >= entry_price:
            return None

        risk = entry_price - stop_loss

        # Find Target: Nearest overhead Resistance Zone or fixed RR
        overhead_targets = [
            z.price_low for z in zones
            if not z.is_broken and z.zone_type == ZoneType.RESISTANCE and z.price_low > entry_price + risk
        ]

        if overhead_targets:
            target = min(overhead_targets)
        else:
            target = entry_price + (risk * max(self.tc_cfg.min_reward_risk, 2.0))

        reward = target - entry_price
        rr = reward / risk if risk > 0 else 0.0

        if rr < self.tc_cfg.min_reward_risk:
            return None

        confidence = 0.70
        if confluent_zone:
            if confluent_zone.freshness_score > 0.8:
                confidence += 0.08
            if confluent_zone.rejection_count >= 2:
                confidence += 0.07
        confidence = min(round(confidence, 2), 0.95)

        logger.info(
            "Found Firsty Bullish Continuation on %s: entry=%.4f, SL=%.4f, TP=%.4f, RR=%.2f",
            symbol, entry_price, stop_loss, target, rr
        )

        return Signal(
            symbol=symbol,
            exchange=exchange,
            direction=Direction.LONG,
            setup_type=SetupType.FIRSTY_CONTINUATION,
            timeframe=timeframe,
            zone=confluent_zone,
            entry_ref=entry_price,
            stop_loss=stop_loss,
            target=target,
            risk_reward=round(rr, 2),
            strength=confidence,
            reason=f"Bullish Firsty Continuation at EMA/Support. RR={rr:.2f}",
            invalidation="Loss of pullback low invalidates setup.",
            created_at=current.timestamp if current.timestamp else datetime.now(timezone.utc),
            strategy_module="firsty_continuation",
            metadata={
                "fast_ema": round(fast_ema, 4),
                "slow_ema": round(slow_ema, 4),
                "atr": round(atr_val, 4),
                "rejection_wick_ratio": round(wick_ratio, 3),
                "confluent_zone_type": confluent_zone.zone_type.value if confluent_zone else "none",
                "confluent_zone_flipped": confluent_zone.is_flipped if confluent_zone else False,
            },
        )

    def _evaluate_bearish_continuation(
        self,
        symbol: str,
        exchange: str,
        completed: list[Candle],
        curr_idx: int,
        fast_ema: float,
        slow_ema: float,
        atr_val: float,
        zones: list[Zone],
        timeframe: str,
    ) -> Signal | None:
        current = completed[curr_idx]
        prev = completed[curr_idx - 1]

        pullback_tol = self.tc_cfg.pullback_tolerance_atr_mult * atr_val
        highest_high = max(current.high, prev.high)
        lowest_high = min(current.high, prev.high)

        # Bearish pullback should touch fast_ema - tolerance, but not burst way above slow_ema
        tested_value_area = (
            highest_high >= fast_ema - pullback_tol and
            highest_high <= slow_ema + pullback_tol
        )
        if not tested_value_area:
            return None

        # S/R Confluence check
        confluent_zone: Zone | None = None
        if self.tc_cfg.require_sr_confluence:
            for z in zones:
                if z.is_broken:
                    continue
                if z.zone_type == ZoneType.RESISTANCE:
                    tol = z.price_low * (self.tc_cfg.sr_confluence_tolerance_pct / 100.0)
                    if (highest_high >= z.price_low - tol) and (lowest_high <= z.price_high + tol):
                        confluent_zone = z
                        break
            if confluent_zone is None:
                return None

        # Trigger candle evaluation
        candle_range = current.high - current.low
        if candle_range <= 0:
            return None

        # Upper rejection wick
        upper_wick = current.high - max(current.open, current.close)
        wick_ratio = upper_wick / candle_range

        if wick_ratio < self.tc_cfg.min_rejection_wick_ratio:
            return None

        # Candle should close bearish or close below fast EMA
        if current.close >= current.open and current.close > fast_ema:
            return None

        entry_price = current.close
        buffer = 0.15 * atr_val
        stop_loss = highest_high + buffer

        if stop_loss <= entry_price:
            return None

        risk = stop_loss - entry_price

        # Find Target: Nearest underlying Support Zone or fixed RR
        underlying_targets = [
            z.price_high for z in zones
            if not z.is_broken and z.zone_type == ZoneType.SUPPORT and z.price_high < entry_price - risk
        ]

        if underlying_targets:
            target = max(underlying_targets)
        else:
            target = entry_price - (risk * max(self.tc_cfg.min_reward_risk, 2.0))

        reward = entry_price - target
        rr = reward / risk if risk > 0 else 0.0

        if rr < self.tc_cfg.min_reward_risk:
            return None

        confidence = 0.70
        if confluent_zone:
            if confluent_zone.freshness_score > 0.8:
                confidence += 0.08
            if confluent_zone.rejection_count >= 2:
                confidence += 0.07
        confidence = min(round(confidence, 2), 0.95)

        logger.info(
            "Found Firsty Bearish Continuation on %s: entry=%.4f, SL=%.4f, TP=%.4f, RR=%.2f",
            symbol, entry_price, stop_loss, target, rr
        )

        return Signal(
            symbol=symbol,
            exchange=exchange,
            direction=Direction.SHORT,
            setup_type=SetupType.FIRSTY_CONTINUATION,
            timeframe=timeframe,
            zone=confluent_zone,
            entry_ref=entry_price,
            stop_loss=stop_loss,
            target=target,
            risk_reward=round(rr, 2),
            strength=confidence,
            reason=f"Bearish Firsty Continuation at EMA/Resistance. RR={rr:.2f}",
            invalidation="Loss of pullback high invalidates setup.",
            created_at=current.timestamp if current.timestamp else datetime.now(timezone.utc),
            strategy_module="firsty_continuation",
            metadata={
                "fast_ema": round(fast_ema, 4),
                "slow_ema": round(slow_ema, 4),
                "atr": round(atr_val, 4),
                "rejection_wick_ratio": round(wick_ratio, 3),
                "confluent_zone_type": confluent_zone.zone_type.value if confluent_zone else "none",
                "confluent_zone_flipped": confluent_zone.is_flipped if confluent_zone else False,
            },
        )
