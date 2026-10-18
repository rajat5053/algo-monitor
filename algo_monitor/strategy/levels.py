"""
Support and resistance level detection.

Identifies swing highs/lows from OHLCV candles, clusters nearby levels
into zones, and tracks zone strength based on repeated price reactions.

Key design decisions:
- A swing high/low requires `lookback` candles on EACH side to be confirmed.
  This prevents look-ahead bias — a swing is never confirmed until enough
  future candles have closed.
- Nearby levels within `zone_tolerance_pct` of each other are merged into
  a single zone.  The zone spans from the lowest to highest constituent level.
- Each zone records the number of "touches" (price reactions), recency,
  and a composite strength score.
- Zones are capped per instrument to prevent clutter.

All parameters are configurable via StrategyConfig.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

from algo_monitor.data.models import Candle
from algo_monitor.utils.logging import get_logger

if TYPE_CHECKING:
    from algo_monitor.config.settings import StrategyConfig

logger = get_logger("strategy.levels")


class ZoneType(str, Enum):
    SUPPORT = "support"
    RESISTANCE = "resistance"


@dataclass
class SwingPoint:
    """A confirmed swing high or low."""

    price: float
    timestamp: datetime
    swing_type: ZoneType   # SUPPORT for swing lows, RESISTANCE for swing highs
    candle_index: int      # Position in the candle array (for debugging)
    prominence: float = 0.0 # ATR or % distance by which the swing stands out


@dataclass
class Zone:
    """A support or resistance zone (cluster of nearby levels)."""

    zone_type: ZoneType
    price_low: float
    price_high: float
    touches: int = 1
    first_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    strength: float = 1.0
    constituent_prices: list[float] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    is_broken: bool = False
    is_flipped: bool = False                    # True if flipped (e.g. Broken Resistance -> Support)
    original_type: ZoneType | None = None       # Polarity prior to flipping
    rejection_count: int = 0                    # Count of pronounced wick rejections
    freshness_score: float = 1.0                # 1.0 for 1-3 touches, decays if over-tested

    @property
    def mid_price(self) -> float:
        return (self.price_low + self.price_high) / 2

    @property
    def width_pct(self) -> float:
        """Zone width as % of mid price."""
        mid = self.mid_price
        if mid <= 0:
            return 0
        return ((self.price_high - self.price_low) / mid) * 100

    def contains_price(self, price: float, tolerance_pct: float = 0.0) -> bool:
        """Check if a price is within the zone (with optional extra tolerance)."""
        margin = self.mid_price * tolerance_pct / 100
        return (self.price_low - margin) <= price <= (self.price_high + margin)

    def distance_pct(self, price: float) -> float:
        """Percentage distance from price to nearest zone edge."""
        if price <= 0:
            return float("inf")
        if price < self.price_low:
            return ((self.price_low - price) / price) * 100
        elif price > self.price_high:
            return ((price - self.price_high) / price) * 100
        return 0  # Inside the zone


def calculate_atr(candles: list[Candle], period: int = 14) -> float:
    """Calculate Average True Range from historical candles."""
    if len(candles) < 2:
        return 0.0
    true_ranges = []
    for i in range(1, len(candles)):
        c = candles[i]
        prev = candles[i - 1]
        tr = max(
            c.high - c.low,
            abs(c.high - prev.close),
            abs(c.low - prev.close),
        )
        true_ranges.append(tr)
    if not true_ranges:
        return 0.0
    recent = true_ranges[-period:] if len(true_ranges) >= period else true_ranges
    return sum(recent) / len(recent)


class LevelDetector:
    """
    Detects clean, pronounced support and resistance zones from OHLCV candle data.

    Features:
    - Meaningful swing detection via prominence filtering (Document 1)
    - Volatility-aware minimum zone width
    - Rejection behavior evaluation (pin bar / wick reactions)
    - Freshness scoring (early tests preferred; over-tested penalized)
    - Verified polarity changes after clean breakouts/breakdowns
    - Anti-clutter merging of overlapping zones
    """

    def __init__(self, config: StrategyConfig):
        self.config = config
        self.lookback = config.swing_lookback
        self.zone_tolerance_pct = config.zone_tolerance_pct
        self.min_touches = config.min_touches
        self.max_zones = config.max_zones
        self.min_prominence_pct = getattr(config, "min_prominence_pct", 0.25)
        self.min_zone_width_pct = getattr(config, "min_zone_width_pct", 0.20)
        self.enable_polarity_flips = getattr(config, "enable_polarity_flips", True)
        self.enable_zone_merging = getattr(config, "enable_zone_merging", True)
        self.zone_invalidation_threshold_pct = getattr(config, "zone_invalidation_threshold_pct", 0.5)
        self.zone_invalidation_closes = getattr(config, "zone_invalidation_closes", 2)
        self.max_fresh_touches = getattr(config, "max_fresh_touches", 5)

    def find_swing_points(self, candles: list[Candle]) -> list[SwingPoint]:
        """
        Identify confirmed, prominent swing highs and lows.

        Filters out insignificant noise bars by requiring minimum swing prominence.
        """
        swings = []
        n = len(candles)

        if n < 2 * self.lookback + 1:
            logger.debug(
                "Insufficient candles (%d) for swing detection (need %d)",
                n, 2 * self.lookback + 1,
            )
            return swings

        atr = calculate_atr(candles, period=14)

        for i in range(self.lookback, n - self.lookback):
            candle = candles[i]

            # --- Swing HIGH ---
            is_swing_high = True
            for j in range(i - self.lookback, i + self.lookback + 1):
                if j == i:
                    continue
                if candles[j].high > candle.high:
                    is_swing_high = False
                    break

            if is_swing_high:
                # Prominence check: swing high must stand out from neighboring lows
                left_lows = [candles[j].low for j in range(i - self.lookback, i)]
                right_lows = [candles[j].low for j in range(i + 1, i + self.lookback + 1)]
                depth_left = candle.high - min(left_lows) if left_lows else 0
                depth_right = candle.high - min(right_lows) if right_lows else 0
                prominence = min(depth_left, depth_right)

                min_required = max(
                    candle.high * (self.min_prominence_pct / 100),
                    atr * 0.3 if atr > 0 else 0,
                )

                if prominence >= min_required or self.min_prominence_pct <= 0:
                    swings.append(SwingPoint(
                        price=candle.high,
                        timestamp=candle.timestamp,
                        swing_type=ZoneType.RESISTANCE,
                        candle_index=i,
                        prominence=prominence,
                    ))

            # --- Swing LOW ---
            is_swing_low = True
            for j in range(i - self.lookback, i + self.lookback + 1):
                if j == i:
                    continue
                if candles[j].low < candle.low:
                    is_swing_low = False
                    break

            if is_swing_low:
                left_highs = [candles[j].high for j in range(i - self.lookback, i)]
                right_highs = [candles[j].high for j in range(i + 1, i + self.lookback + 1)]
                depth_left = max(left_highs) - candle.low if left_highs else 0
                depth_right = max(right_highs) - candle.low if right_highs else 0
                prominence = min(depth_left, depth_right)

                min_required = max(
                    candle.low * (self.min_prominence_pct / 100),
                    atr * 0.3 if atr > 0 else 0,
                )

                if prominence >= min_required or self.min_prominence_pct <= 0:
                    swings.append(SwingPoint(
                        price=candle.low,
                        timestamp=candle.timestamp,
                        swing_type=ZoneType.SUPPORT,
                        candle_index=i,
                        prominence=prominence,
                    ))

        logger.debug("Found %d prominent swing points in %d candles", len(swings), n)
        return swings

    def cluster_into_zones(
        self, swings: list[SwingPoint], reference_price: float = 0, atr: float = 0.0
    ) -> list[Zone]:
        """
        Group nearby swing points into zones using configurable tolerance.
        """
        if not swings:
            return []

        support_swings = [s for s in swings if s.swing_type == ZoneType.SUPPORT]
        resistance_swings = [s for s in swings if s.swing_type == ZoneType.RESISTANCE]

        zones = []
        zones.extend(self._cluster_one_type(support_swings, ZoneType.SUPPORT, atr))
        zones.extend(self._cluster_one_type(resistance_swings, ZoneType.RESISTANCE, atr))

        return zones

    def detect_zones(
        self, candles: list[Candle], reference_price: float = 0
    ) -> list[Zone]:
        """
        Full pipeline:
        1. Meaningful swings with prominence filtering
        2. Volatility-aware clustering with minimum width bands
        3. Touch count, rejection evaluation & freshness scoring
        4. Verified polarity flips (broken resistance -> support)
        5. Anti-clutter merging of overlapping zones
        6. Ranking by composite strength score
        """
        if not candles:
            return []

        if reference_price <= 0:
            reference_price = candles[-1].close

        atr = calculate_atr(candles, period=14)

        swings = self.find_swing_points(candles)
        zones = self.cluster_into_zones(swings, reference_price, atr)

        # Count additional touches and analyze rejection behaviour
        self._count_touches(zones, candles)

        # Update polarity changes for cleanly broken zones
        if self.enable_polarity_flips:
            self.update_polarity_flips(zones, candles)
        else:
            self.invalidate_broken_zones(zones, candles)

        # Re-count touches for any newly flipped zones
        self._count_touches(zones, candles)

        # Merge overlapping zones of same polarity to eliminate clutter
        if self.enable_zone_merging:
            zones = self.merge_overlapping_zones(zones)

        # Filter by minimum touches
        zones = [z for z in zones if z.touches >= self.min_touches and not z.is_broken]

        # Score and rank
        self._score_zones(zones, reference_price)
        zones.sort(key=lambda z: z.strength, reverse=True)

        if len(zones) > self.max_zones:
            zones = zones[: self.max_zones]

        logger.info(
            "Detected %d clean zones (%d support, %d resistance) from %d candles",
            len(zones),
            sum(1 for z in zones if z.zone_type == ZoneType.SUPPORT),
            sum(1 for z in zones if z.zone_type == ZoneType.RESISTANCE),
            len(candles),
        )
        return zones

    def update_polarity_flips(
        self, zones: list[Zone], candles: list[Candle]
    ) -> None:
        """
        Detect verified polarity changes after breakouts and breakdowns (Document 1).

        When price breaks decisively beyond a level with required consecutive closes:
        - Resistance cleanly broken -> flips to Support
        - Support cleanly broken -> flips to Resistance
        """
        if not zones or not candles:
            return

        threshold_pct = self.zone_invalidation_threshold_pct
        req_closes = self.zone_invalidation_closes

        for zone in zones:
            consecutive_broken = 0
            for c in reversed(candles):
                if zone.zone_type == ZoneType.SUPPORT:
                    cutoff = zone.price_low * (1 - threshold_pct / 100)
                    if c.close < cutoff:
                        consecutive_broken += 1
                    else:
                        break
                else:  # RESISTANCE
                    cutoff = zone.price_high * (1 + threshold_pct / 100)
                    if c.close > cutoff:
                        consecutive_broken += 1
                    else:
                        break

            if consecutive_broken >= req_closes:
                # Verified breakout/breakdown -> Flip Polarity
                old_type = zone.zone_type
                if old_type == ZoneType.RESISTANCE:
                    zone.zone_type = ZoneType.SUPPORT
                    zone.is_flipped = True
                    zone.original_type = ZoneType.RESISTANCE
                    zone.is_broken = False
                    zone.touches = 1
                    zone.reasons.append(
                        f"Polarity flipped: Resistance -> Support following verified breakout ({consecutive_broken} closes > {threshold_pct}%)"
                    )
                else:
                    zone.zone_type = ZoneType.RESISTANCE
                    zone.is_flipped = True
                    zone.original_type = ZoneType.SUPPORT
                    zone.is_broken = False
                    zone.touches = 1
                    zone.reasons.append(
                        f"Polarity flipped: Support -> Resistance following verified breakdown ({consecutive_broken} closes < -{threshold_pct}%)"
                    )

    def invalidate_broken_zones(
        self, zones: list[Zone], candles: list[Candle]
    ) -> None:
        """Fallback: Mark broken zones without flipping if polarity flips are disabled."""
        if not zones or not candles:
            return

        threshold_pct = self.zone_invalidation_threshold_pct
        req_closes = self.zone_invalidation_closes

        for zone in zones:
            consecutive_broken = 0
            for c in reversed(candles):
                if zone.zone_type == ZoneType.SUPPORT:
                    cutoff = zone.price_low * (1 - threshold_pct / 100)
                    if c.close < cutoff:
                        consecutive_broken += 1
                    else:
                        break
                else:
                    cutoff = zone.price_high * (1 + threshold_pct / 100)
                    if c.close > cutoff:
                        consecutive_broken += 1
                    else:
                        break

            if consecutive_broken >= req_closes:
                zone.is_broken = True
                zone.reasons.append(
                    f"Zone broken: {consecutive_broken} consecutive closes beyond threshold ({threshold_pct}%)"
                )

    def merge_overlapping_zones(self, zones: list[Zone]) -> list[Zone]:
        """
        Merge overlapping or duplicate zones of the same type to avoid chart clutter (Document 1).
        """
        if len(zones) <= 1:
            return zones

        # Group by type
        by_type: dict[ZoneType, list[Zone]] = {ZoneType.SUPPORT: [], ZoneType.RESISTANCE: []}
        for z in zones:
            by_type[z.zone_type].append(z)

        merged_all: list[Zone] = []

        for z_type, group in by_type.items():
            if not group:
                continue

            sorted_group = sorted(group, key=lambda z: z.price_low)
            merged: list[Zone] = [sorted_group[0]]

            for current in sorted_group[1:]:
                prev = merged[-1]
                # Check for overlap (prev.price_high >= current.price_low with small margin)
                margin = prev.mid_price * (self.zone_tolerance_pct / 100)
                if prev.price_high + margin >= current.price_low:
                    # Merge current into prev
                    prev.price_low = min(prev.price_low, current.price_low)
                    prev.price_high = max(prev.price_high, current.price_high)
                    prev.touches += current.touches
                    prev.rejection_count += current.rejection_count
                    prev.constituent_prices.extend(current.constituent_prices)
                    prev.first_seen = min(prev.first_seen, current.first_seen)
                    prev.last_seen = max(prev.last_seen, current.last_seen)
                    prev.strength = max(prev.strength, current.strength) * 1.05
                    prev.reasons.append(f"Merged with overlapping {z_type.value} zone")
                else:
                    merged.append(current)

            merged_all.extend(merged)

        return merged_all

    def _cluster_levels(
        self, swings: list[SwingPoint], zone_type: ZoneType, atr: float = 0.0
    ) -> list[Zone]:
        """Convenience alias for _cluster_one_type."""
        return self._cluster_one_type(swings, zone_type, atr)

    def _cluster_one_type(
        self, swings: list[SwingPoint], zone_type: ZoneType, atr: float = 0.0
    ) -> list[Zone]:
        """Cluster swing points of the same type by price proximity."""
        if not swings:
            return []

        sorted_swings = sorted(swings, key=lambda s: s.price)
        zones: list[Zone] = []
        current_group = [sorted_swings[0]]

        for swing in sorted_swings[1:]:
            group_avg = sum(s.price for s in current_group) / len(current_group)
            distance_pct = abs(swing.price - group_avg) / group_avg * 100

            if distance_pct <= self.zone_tolerance_pct:
                current_group.append(swing)
            else:
                zones.append(self._group_to_zone(current_group, zone_type, atr))
                current_group = [swing]

        zones.append(self._group_to_zone(current_group, zone_type, atr))
        return zones

    def _group_to_zone(
        self, group: list[SwingPoint], zone_type: ZoneType, atr: float = 0.0
    ) -> Zone:
        """Convert a group of nearby swing points into a Zone with realistic width."""
        prices = [s.price for s in group]
        timestamps = [s.timestamp for s in group]

        p_low = min(prices)
        p_high = max(prices)

        # Enforce minimum zone width so levels are price zones rather than infinitesimals
        mid = (p_low + p_high) / 2
        min_width = max(
            mid * (self.min_zone_width_pct / 100),
            atr * 0.25 if atr > 0 else 0,
        )

        if p_high - p_low < min_width:
            half = min_width / 2
            p_low = max(0.01, mid - half)
            p_high = mid + half

        reasons = []
        for s in group:
            reasons.append(
                f"Swing {'high' if zone_type == ZoneType.RESISTANCE else 'low'} "
                f"at {s.price:.2f} on {s.timestamp.strftime('%Y-%m-%d %H:%M')}"
            )

        return Zone(
            zone_type=zone_type,
            price_low=p_low,
            price_high=p_high,
            touches=len(group),
            first_seen=min(timestamps),
            last_seen=max(timestamps),
            constituent_prices=prices,
            reasons=reasons,
        )

    def _count_touches(self, zones: list[Zone] | Zone, candles: list[Candle]) -> None:
        """
        Count price reactions and evaluate rejection behaviour (Document 1).

        A touch is recognized when price enters the zone and does not close through it.
        A 'rejection' is credited when candle leaves a pronounced wick pointing into the zone.
        """
        if isinstance(zones, Zone):
            zone_list = [zones]
        else:
            zone_list = zones

        for zone in zone_list:
            extra_touches = 0
            rejections = 0

            for candle in candles:
                rng = candle.high - candle.low
                if rng <= 0:
                    continue

                if zone.zone_type == ZoneType.SUPPORT:
                    # Low entered zone and closed above
                    if (candle.low <= zone.price_high and
                            candle.low >= zone.price_low * 0.99 and
                            candle.close > zone.price_high):
                        extra_touches += 1
                        zone.last_seen = max(zone.last_seen, candle.timestamp)

                        # Check for rejection lower shadow (bullish pin / wick rejection)
                        lower_wick = min(candle.open, candle.close) - candle.low
                        if lower_wick / rng >= 0.35:
                            rejections += 1

                else:  # RESISTANCE
                    # High entered zone and closed below
                    if (candle.high >= zone.price_low and
                            candle.high <= zone.price_high * 1.01 and
                            candle.close < zone.price_low):
                        extra_touches += 1
                        zone.last_seen = max(zone.last_seen, candle.timestamp)

                        # Check for rejection upper shadow (bearish pin / wick rejection)
                        upper_wick = candle.high - max(candle.open, candle.close)
                        if upper_wick / rng >= 0.35:
                            rejections += 1

            zone.touches += extra_touches
            zone.rejection_count += rejections

            # Freshness score: 1-3 touches = highest quality; >5 tests = level getting absorbed/weakened
            total_t = zone.touches
            if total_t <= 3:
                zone.freshness_score = 1.0
            elif total_t <= self.max_fresh_touches:
                zone.freshness_score = 0.75
            else:
                zone.freshness_score = 0.40  # Over-tested level

            if extra_touches > 0:
                zone.reasons.append(
                    f"{extra_touches} price reactions ({rejections} clean rejections, freshness={zone.freshness_score:.2f})"
                )

    def _score_zones(
        self, zones: list[Zone], reference_price: float
    ) -> None:
        """
        Compute composite strength score incorporating touches, recency, proximity,
        rejection quality, and freshness (Document 1).
        """
        if not zones:
            return

        now = datetime.now(timezone.utc)
        max_touches = max(z.touches for z in zones) if zones else 1
        max_rejections = max(z.rejection_count for z in zones) if zones else 1

        for zone in zones:
            touch_score = min(zone.touches / max(max_touches, 1), 1.0)
            rejection_score = zone.rejection_count / max(max_rejections, 1)

            # Recency decay (30-day half-life)
            days_ago = (now - zone.last_seen).total_seconds() / 86400
            recency_score = 1 / (1 + days_ago / 30)

            # Proximity
            if reference_price > 0:
                dist_pct = zone.distance_pct(reference_price)
                proximity_score = 1 / (1 + dist_pct / 5)
            else:
                proximity_score = 0.5

            # Composite strength:
            # Touches (25%), Rejections (25%), Recency (25%), Proximity (25%) scaled by Freshness
            raw_strength = (
                0.25 * touch_score
                + 0.25 * rejection_score
                + 0.25 * recency_score
                + 0.25 * proximity_score
            )
            zone.strength = round(raw_strength * zone.freshness_score, 2)

            zone.reasons.append(
                f"Strength={zone.strength:.2f} "
                f"(touch={touch_score:.2f}, rejections={rejection_score:.2f}, "
                f"freshness={zone.freshness_score:.2f})"
            )

