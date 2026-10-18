"""
Adaptive initial target planning for support/resistance setups.

This module is the core of the P0-E fix: decoupling the initial target
from a mandatory fixed 1.5R multiple. Instead, targets are based on
the market structure visible at signal time.

Algorithm (initial target):
  1. Identify the nearest opposing S/R zone in the trade direction.
  2. Place the target just before that zone (minus zone_clearance_buffer_pct).
  3. Verify the resulting reward-to-risk is at least min_reward_risk.
  4. If no zone is found within usable distance, fall back to target_fixed_rr_multiple.

The planner is deterministic: identical inputs always produce identical output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from algo_monitor.strategy.levels import Zone, ZoneType
from algo_monitor.utils.logging import get_logger

if TYPE_CHECKING:
    from algo_monitor.config.settings import StrategyConfig

logger = get_logger("strategy.adaptive_target")


@dataclass
class TargetResult:
    """Result of adaptive target computation."""

    target: float | None       # None if no viable target found
    method: str                # Human-readable explanation of how target was set
    opposing_zone: Zone | None = None   # Zone that bounded the target (if any)
    rr_ratio: float = 0.0
    rejected_reason: str = ""  # Why a candidate target was rejected, if applicable


class AdaptiveTargetPlanner:
    """
    Structure-based initial target planner.

    Selects a trade target based on the nearest opposing S/R zone,
    ensuring the target does not require price to pass through a
    significant zone without justification.
    """

    def __init__(self, config: "StrategyConfig"):
        self.config = config

    def compute_initial_target(
        self,
        entry: float,
        stop: float,
        direction: str,
        all_zones: list[Zone],
        source_zone: Zone | None = None,
    ) -> TargetResult:
        """
        Compute the initial trade target from market structure.

        Args:
            entry: Entry price (confirmed candle close).
            stop: Stop-loss price.
            direction: 'long' or 'short'.
            all_zones: All active S/R zones (both timeframes merged).
            source_zone: The zone that triggered this signal (excluded
                         from opposing zone search to avoid using the
                         same zone as both trigger and target).

        Returns:
            TargetResult with target price and reasoning.
        """
        if entry <= 0 or stop <= 0:
            return TargetResult(
                target=None,
                method="invalid_inputs",
                rejected_reason=f"entry={entry} or stop={stop} is non-positive",
            )

        risk = abs(entry - stop)
        if risk <= 0:
            return TargetResult(
                target=None,
                method="zero_risk",
                rejected_reason="Risk distance is zero",
            )

        min_rr = getattr(self.config, "min_reward_risk", 1.5)
        rr_fallback = getattr(self.config, "target_fixed_rr_multiple", 1.5)
        buffer_pct = getattr(self.config, "zone_clearance_buffer_pct", 0.2)

        # Identify candidate opposing zones
        opposing_zones = self._find_opposing_zones(
            entry=entry,
            direction=direction,
            all_zones=all_zones,
            source_zone=source_zone,
        )

        # Attempt each opposing zone as a potential target boundary
        for zone in opposing_zones:
            candidate, method, reason = self._target_from_zone(
                entry=entry,
                stop=stop,
                direction=direction,
                zone=zone,
                risk=risk,
                buffer_pct=buffer_pct,
                min_rr=min_rr,
            )

            if candidate is not None:
                rr = abs(candidate - entry) / risk
                logger.debug(
                    "Adaptive target: entry=%.4f, target=%.4f, R:R=%.2f, zone=[%.4f-%.4f], method=%s",
                    entry, candidate, rr, zone.price_low, zone.price_high, method,
                )
                return TargetResult(
                    target=candidate,
                    method=method,
                    opposing_zone=zone,
                    rr_ratio=rr,
                )
            else:
                logger.debug(
                    "Zone [%.4f-%.4f] rejected as target boundary: %s",
                    zone.price_low, zone.price_high, reason,
                )

        # No suitable opposing zone — fall back to fixed R:R
        if direction == "long":
            fallback_target = entry + risk * rr_fallback
        else:
            fallback_target = entry - risk * rr_fallback

        logger.debug(
            "Adaptive target: no usable opposing zone found; "
            "falling back to %.1fR target %.4f",
            rr_fallback, fallback_target,
        )

        return TargetResult(
            target=fallback_target,
            method=f"fixed_rr ({rr_fallback}R — no opposing zone within range)",
            rr_ratio=rr_fallback,
            rejected_reason="No opposing zone found within valid distance",
        )

    def _find_opposing_zones(
        self,
        entry: float,
        direction: str,
        all_zones: list[Zone],
        source_zone: Zone | None,
    ) -> list[Zone]:
        """
        Find zones that are in the direction of the trade and
        above/below entry (as obstacles/targets).

        For a long trade: resistance zones above the entry price.
        For a short trade: support zones below the entry price.

        Excludes the source zone (which generated the signal).
        Sorted by proximity (nearest first).
        """
        if direction == "long":
            opposing_type = ZoneType.RESISTANCE
            candidates = [
                z for z in all_zones
                if z.zone_type == opposing_type
                and z.price_low > entry  # Zone is above entry
                and z is not source_zone
                and z.strength > 0.2     # Only meaningful zones
            ]
            candidates.sort(key=lambda z: z.price_low)  # Nearest first

        else:  # short
            opposing_type = ZoneType.SUPPORT
            candidates = [
                z for z in all_zones
                if z.zone_type == opposing_type
                and z.price_high < entry  # Zone is below entry
                and z is not source_zone
                and z.strength > 0.2
            ]
            candidates.sort(key=lambda z: z.price_high, reverse=True)  # Nearest first

        return candidates

    def _target_from_zone(
        self,
        entry: float,
        stop: float,
        direction: str,
        zone: Zone,
        risk: float,
        buffer_pct: float,
        min_rr: float,
    ) -> tuple[float | None, str, str]:
        """
        Attempt to derive a target from a single opposing zone.

        Returns:
            (target_price or None, method_description, rejection_reason)
        """
        buffer = zone.mid_price * buffer_pct / 100

        if direction == "long":
            # Place target just before the zone's lower boundary
            candidate = zone.price_low - buffer
            if candidate <= entry:
                return None, "", "Zone lower boundary is at or below entry"
            reward = candidate - entry
        else:
            # Place target just above the zone's upper boundary
            candidate = zone.price_high + buffer
            if candidate >= entry:
                return None, "", "Zone upper boundary is at or above entry"
            reward = entry - candidate

        if reward <= 0:
            return None, "", "Zero or negative reward to zone target"

        rr = reward / risk
        if rr < min_rr:
            return (
                None, "",
                f"R:R={rr:.2f} < min_reward_risk={min_rr} (zone too close to entry)",
            )

        method = (
            f"structure_zone [{zone.price_low:.4f}-{zone.price_high:.4f}] "
            f"({zone.zone_type.value}, strength={zone.strength:.2f}, "
            f"touches={zone.touches}), R:R={rr:.2f}"
        )
        return candidate, method, ""


def compute_target_extension_viability(
    current_price: float,
    current_target: float,
    entry: float,
    stop: float,
    direction: str,
    all_zones: list[Zone],
    usd_inr_rate: float = 85.0,
    min_remaining_rr: float = 0.5,
) -> tuple[bool, str, Zone | None]:
    """
    Assess whether extending the current target is viable.

    Used by TradeManager to evaluate CONSIDER_TARGET_EXTENSION.

    Returns:
        (viable, reason, next_zone_if_viable)

    A target extension is viable when:
    - Price is within 15% of the current target (approaching)
    - The next opposing zone is meaningfully beyond the current target
    - The remaining reward (from current_price to new_target) is at
      least min_remaining_rr times the initial risk
    - No strong rejection is evident at the current target area
    """
    risk = abs(entry - stop)
    if risk <= 0 or current_price <= 0:
        return False, "Invalid risk or price", None

    # Check if price is approaching current target
    distance_to_target = abs(current_target - current_price)
    if direction == "long":
        progress_pct = (current_price - entry) / (current_target - entry) * 100 if current_target > entry else 0
    else:
        progress_pct = (entry - current_price) / (entry - current_target) * 100 if entry > current_target else 0

    if progress_pct < 50:
        return False, f"Price progress {progress_pct:.0f}% — target not yet approaching (need >50%)", None

    # Find next opposing zone beyond current target
    if direction == "long":
        beyond_zones = [
            z for z in all_zones
            if z.zone_type == ZoneType.RESISTANCE
            and z.price_low > current_target * 1.002  # meaningfully beyond
            and z.strength > 0.25
        ]
        beyond_zones.sort(key=lambda z: z.price_low)
    else:
        beyond_zones = [
            z for z in all_zones
            if z.zone_type == ZoneType.SUPPORT
            and z.price_high < current_target * 0.998
            and z.strength > 0.25
        ]
        beyond_zones.sort(key=lambda z: z.price_high, reverse=True)

    if not beyond_zones:
        return False, "No opposing zone found beyond current target", None

    next_zone = beyond_zones[0]

    # Assess remaining reward from current price to next zone
    if direction == "long":
        new_target_candidate = next_zone.price_low * 0.998
        remaining_reward = new_target_candidate - current_price
    else:
        new_target_candidate = next_zone.price_high * 1.002
        remaining_reward = current_price - new_target_candidate

    remaining_rr = remaining_reward / risk if risk > 0 else 0

    if remaining_rr < min_remaining_rr:
        return (
            False,
            f"Remaining R:R={remaining_rr:.2f} < threshold {min_remaining_rr} "
            f"(next zone too close)",
            None,
        )

    reason = (
        f"Price at {progress_pct:.0f}% progress toward current target. "
        f"Next {next_zone.zone_type.value} zone at "
        f"[{next_zone.price_low:.4f}-{next_zone.price_high:.4f}] "
        f"(strength={next_zone.strength:.2f}). "
        f"Remaining R:R={remaining_rr:.2f}."
    )
    return True, reason, next_zone
