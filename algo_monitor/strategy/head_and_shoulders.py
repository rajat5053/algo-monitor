"""
Head and Shoulders Pattern Recognition Module (Document 2 Requirement).

Detects both Standard (Bearish reversal) and Inverse (Bullish reversal)
Head and Shoulders chart patterns where an established Support/Resistance
zone acts as the neckline.

Deterministic rules:
1. Standard H&S:
   - Three consecutive swing highs (Left Shoulder, Head, Right Shoulder)
   - Head is higher than both Left Shoulder and Right Shoulder
   - Left and Right Shoulders have comparable heights (symmetry tolerance)
   - Intervening troughs define a neckline that aligns with a Support Zone
   - Trigger on verified breakdown below the neckline or retest of the broken neckline
   - Measured move target = Neckline - (Head - Neckline)
   - Stop-Loss = Above Right Shoulder

2. Inverse H&S:
   - Three consecutive swing lows (Left Shoulder, Head, Right Shoulder)
   - Head is lower than both shoulders
   - Shoulders symmetrical within tolerance
   - Intervening peaks define a neckline that aligns with a Resistance Zone
   - Trigger on breakout above neckline or retest
   - Measured move target = Neckline + (Neckline - Head)
   - Stop-Loss = Below Right Shoulder
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from algo_monitor.data.models import Candle
from algo_monitor.strategy.levels import LevelDetector, SwingPoint, Zone, ZoneType, calculate_atr
from algo_monitor.strategy.signals import Direction, SetupType, Signal
from algo_monitor.utils.logging import get_logger

if TYPE_CHECKING:
    from algo_monitor.config.settings import StrategyConfig

logger = get_logger("strategy.head_and_shoulders")


@dataclass
class HeadAndShouldersPattern:
    """Represents a validated Head and Shoulders geometric pattern."""
    is_inverse: bool
    left_shoulder: SwingPoint
    head: SwingPoint
    right_shoulder: SwingPoint
    neckline_points: list[SwingPoint]
    neckline_low: float
    neckline_high: float
    measured_target: float
    neckline_zone: Zone | None = None


class HeadAndShouldersDetector:
    """
    Deterministic detector for Head & Shoulders and Inverse Head & Shoulders patterns.
    """

    def __init__(self, config: StrategyConfig):
        self.config = config
        self.pattern_cfg = config.head_and_shoulders
        self.level_detector = LevelDetector(config)

    def detect_signals(
        self,
        symbol: str,
        exchange: str,
        candles: list[Candle],
        zones: list[Zone],
        timeframe: str = "5m",
    ) -> list[Signal]:
        """
        Scan candles for Head & Shoulders patterns with S/R neckline confluence.
        """
        if not self.pattern_cfg.enabled:
            return []

        if len(candles) < self.pattern_cfg.min_pattern_candles:
            return []

        completed = [c for c in candles if c.is_complete]
        if len(completed) < 3:
            return []

        current = completed[-1]
        prev = completed[-2]

        swings = self.level_detector.find_swing_points(completed)
        if len(swings) < 5:
            return []

        signals: list[Signal] = []

        # 1. Check Standard (Bearish) Head and Shoulders
        standard_pattern = self._find_standard_pattern(swings, zones)
        if standard_pattern:
            sig = self._evaluate_standard_trigger(
                symbol, exchange, timeframe, current, prev, standard_pattern, zones
            )
            if sig:
                signals.append(sig)

        # 2. Check Inverse (Bullish) Head and Shoulders
        inverse_pattern = self._find_inverse_pattern(swings, zones)
        if inverse_pattern:
            sig = self._evaluate_inverse_trigger(
                symbol, exchange, timeframe, current, prev, inverse_pattern, zones
            )
            if sig:
                signals.append(sig)

        return signals

    def _find_standard_pattern(
        self, swings: list[SwingPoint], zones: list[Zone]
    ) -> HeadAndShouldersPattern | None:
        """Find the most recent valid Standard (Bearish) H&S pattern in swing points."""
        highs = [s for s in swings if s.swing_type == ZoneType.RESISTANCE]
        lows = [s for s in swings if s.swing_type == ZoneType.SUPPORT]

        if len(highs) < 3 or len(lows) < 2:
            return None

        # Examine the last 3 swing highs
        ls, head, rs = highs[-3], highs[-2], highs[-1]

        # Chronology
        if not (ls.timestamp < head.timestamp < rs.timestamp):
            return None

        # Head must be higher than both shoulders
        if head.price <= ls.price or head.price <= rs.price:
            return None

        # Head prominence
        prominence_pct = self.pattern_cfg.min_head_prominence_pct
        head_margin = max(ls.price, rs.price) * (1 + prominence_pct / 100)
        if head.price < head_margin:
            return None

        # Shoulder symmetry
        shoulder_diff_pct = abs(ls.price - rs.price) / ((ls.price + rs.price) / 2) * 100
        if shoulder_diff_pct > self.pattern_cfg.shoulder_symmetry_pct:
            return None

        # Find intervening troughs forming the neckline
        t1_candidates = [l for l in lows if ls.timestamp < l.timestamp < head.timestamp]
        t2_candidates = [l for l in lows if head.timestamp < l.timestamp < rs.timestamp]

        if not t1_candidates or not t2_candidates:
            return None

        t1 = min(t1_candidates, key=lambda l: l.price)
        t2 = min(t2_candidates, key=lambda l: l.price)

        # Neckline slope tolerance
        neckline_diff_pct = abs(t1.price - t2.price) / ((t1.price + t2.price) / 2) * 100
        if neckline_diff_pct > (self.pattern_cfg.neckline_tolerance_pct * 3):
            return None

        nl_low = min(t1.price, t2.price)
        nl_high = max(t1.price, t2.price)

        # S/R Confluence Check: neckline must align with an active Support Zone
        matching_zone = None
        for z in zones:
            if z.zone_type == ZoneType.SUPPORT:
                # Overlap check
                if not (z.price_high < nl_low or z.price_low > nl_high):
                    matching_zone = z
                    break

        if self.pattern_cfg.require_neckline_sr_confluence and not matching_zone:
            return None

        neckline_mid = (nl_low + nl_high) / 2
        head_height = head.price - neckline_mid
        measured_target = max(0.01, neckline_mid - head_height)

        return HeadAndShouldersPattern(
            is_inverse=False,
            left_shoulder=ls,
            head=head,
            right_shoulder=rs,
            neckline_points=[t1, t2],
            neckline_low=nl_low,
            neckline_high=nl_high,
            measured_target=measured_target,
            neckline_zone=matching_zone,
        )

    def _find_inverse_pattern(
        self, swings: list[SwingPoint], zones: list[Zone]
    ) -> HeadAndShouldersPattern | None:
        """Find the most recent valid Inverse (Bullish) H&S pattern in swing points."""
        lows = [s for s in swings if s.swing_type == ZoneType.SUPPORT]
        highs = [s for s in swings if s.swing_type == ZoneType.RESISTANCE]

        if len(lows) < 3 or len(highs) < 2:
            return None

        ls, head, rs = lows[-3], lows[-2], lows[-1]

        if not (ls.timestamp < head.timestamp < rs.timestamp):
            return None

        # Head must be lower than both shoulders
        if head.price >= ls.price or head.price >= rs.price:
            return None

        # Prominence
        prominence_pct = self.pattern_cfg.min_head_prominence_pct
        head_margin = min(ls.price, rs.price) * (1 - prominence_pct / 100)
        if head.price > head_margin:
            return None

        # Shoulder symmetry
        shoulder_diff_pct = abs(ls.price - rs.price) / ((ls.price + rs.price) / 2) * 100
        if shoulder_diff_pct > self.pattern_cfg.shoulder_symmetry_pct:
            return None

        # Intervening peaks forming neckline
        p1_candidates = [h for h in highs if ls.timestamp < h.timestamp < head.timestamp]
        p2_candidates = [h for h in highs if head.timestamp < h.timestamp < rs.timestamp]

        if not p1_candidates or not p2_candidates:
            return None

        p1 = max(p1_candidates, key=lambda h: h.price)
        p2 = max(p2_candidates, key=lambda h: h.price)

        neckline_diff_pct = abs(p1.price - p2.price) / ((p1.price + p2.price) / 2) * 100
        if neckline_diff_pct > (self.pattern_cfg.neckline_tolerance_pct * 3):
            return None

        nl_low = min(p1.price, p2.price)
        nl_high = max(p1.price, p2.price)

        matching_zone = None
        for z in zones:
            if z.zone_type == ZoneType.RESISTANCE:
                if not (z.price_high < nl_low or z.price_low > nl_high):
                    matching_zone = z
                    break

        if self.pattern_cfg.require_neckline_sr_confluence and not matching_zone:
            return None

        neckline_mid = (nl_low + nl_high) / 2
        head_depth = neckline_mid - head.price
        measured_target = neckline_mid + head_depth

        return HeadAndShouldersPattern(
            is_inverse=True,
            left_shoulder=ls,
            head=head,
            right_shoulder=rs,
            neckline_points=[p1, p2],
            neckline_low=nl_low,
            neckline_high=nl_high,
            measured_target=measured_target,
            neckline_zone=matching_zone,
        )

    def _evaluate_standard_trigger(
        self,
        symbol: str,
        exchange: str,
        tf: str,
        current: Candle,
        prev: Candle,
        pattern: HeadAndShouldersPattern,
        all_zones: list[Zone],
    ) -> Signal | None:
        """Evaluate breakdown or neckline retest trigger for bearish H&S."""
        nl_low = pattern.neckline_low
        threshold = nl_low * (1 - self.config.breakout_threshold_pct / 100)

        # 1. Breakdown trigger: current closed below neckline threshold
        is_breakdown = prev.close > nl_low and current.close <= threshold and current.is_bearish

        # 2. Retest trigger: candle returned to retest neckline from below
        is_retest = (
            abs(current.high - nl_low) <= ((nl_low + pattern.neckline_high) / 2 * 0.005)
            and current.close < nl_low
            and current.is_bearish
        )

        if not (is_breakdown or is_retest):
            return None

        entry = current.close
        # Stop-loss: above Right Shoulder (conservative) or above neckline high (aggressive retest)
        stop = pattern.right_shoulder.price * 1.002
        risk = stop - entry
        if risk <= 0:
            return None

        target = pattern.measured_target
        if target >= entry:
            return None

        rr = (entry - target) / risk
        if rr < self.pattern_cfg.min_reward_risk:
            # Adjust target to min R:R if measured move is too small
            target = entry - risk * self.pattern_cfg.min_reward_risk
            rr = self.pattern_cfg.min_reward_risk

        trigger_type = "breakdown" if is_breakdown else "retest"
        return Signal(
            symbol=symbol,
            exchange=exchange,
            setup_type=SetupType.HEAD_AND_SHOULDERS,
            direction=Direction.SHORT,
            timeframe=tf,
            zone=pattern.neckline_zone,
            entry_ref=entry,
            stop_loss=stop,
            target=target,
            risk_reward=round(rr, 2),
            strength=0.85,
            reason=(
                f"Bearish Head & Shoulders {trigger_type} across neckline [{nl_low:.2f} - {pattern.neckline_high:.2f}]. "
                f"Left Shoulder: {pattern.left_shoulder.price:.2f}, Head: {pattern.head.price:.2f}, Right Shoulder: {pattern.right_shoulder.price:.2f}. "
                f"Measured target: {target:.2f} (R:R={rr:.2f})."
            ),
            invalidation=f"Close back above Right Shoulder {stop:.2f} invalidates the pattern.",
            strategy_module="head_and_shoulders",
            metadata={
                "pattern_type": "standard",
                "left_shoulder": pattern.left_shoulder.price,
                "head": pattern.head.price,
                "right_shoulder": pattern.right_shoulder.price,
                "neckline_mid": (nl_low + pattern.neckline_high) / 2,
            },
        )

    def _evaluate_inverse_trigger(
        self,
        symbol: str,
        exchange: str,
        tf: str,
        current: Candle,
        prev: Candle,
        pattern: HeadAndShouldersPattern,
        all_zones: list[Zone],
    ) -> Signal | None:
        """Evaluate breakout or neckline retest trigger for bullish inverse H&S."""
        nl_high = pattern.neckline_high
        threshold = nl_high * (1 + self.config.breakout_threshold_pct / 100)

        is_breakout = prev.close < nl_high and current.close >= threshold and current.is_bullish
        is_retest = (
            abs(current.low - nl_high) <= ((pattern.neckline_low + nl_high) / 2 * 0.005)
            and current.close > nl_high
            and current.is_bullish
        )

        if not (is_breakout or is_retest):
            return None

        entry = current.close
        stop = pattern.right_shoulder.price * 0.998
        risk = entry - stop
        if risk <= 0:
            return None

        target = pattern.measured_target
        if target <= entry:
            return None

        rr = (target - entry) / risk
        if rr < self.pattern_cfg.min_reward_risk:
            target = entry + risk * self.pattern_cfg.min_reward_risk
            rr = self.pattern_cfg.min_reward_risk

        trigger_type = "breakout" if is_breakout else "retest"
        return Signal(
            symbol=symbol,
            exchange=exchange,
            setup_type=SetupType.HEAD_AND_SHOULDERS,
            direction=Direction.LONG,
            timeframe=tf,
            zone=pattern.neckline_zone,
            entry_ref=entry,
            stop_loss=stop,
            target=target,
            risk_reward=round(rr, 2),
            strength=0.85,
            reason=(
                f"Bullish Inverse Head & Shoulders {trigger_type} above neckline [{pattern.neckline_low:.2f} - {nl_high:.2f}]. "
                f"Left Shoulder: {pattern.left_shoulder.price:.2f}, Head: {pattern.head.price:.2f}, Right Shoulder: {pattern.right_shoulder.price:.2f}. "
                f"Measured target: {target:.2f} (R:R={rr:.2f})."
            ),
            invalidation=f"Close back below Right Shoulder {stop:.2f} invalidates the pattern.",
            strategy_module="head_and_shoulders",
            metadata={
                "pattern_type": "inverse",
                "left_shoulder": pattern.left_shoulder.price,
                "head": pattern.head.price,
                "right_shoulder": pattern.right_shoulder.price,
                "neckline_mid": (pattern.neckline_low + nl_high) / 2,
            },
        )
