"""
Tests for adaptive initial target planning (P0-E / P2-A).
"""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from algo_monitor.config.settings import StrategyConfig
from algo_monitor.strategy.adaptive_target import AdaptiveTargetPlanner
from algo_monitor.strategy.levels import Zone, ZoneType


class TestAdaptiveTargetPlanner:
    """Validate structure-based target placement and fallbacks."""

    @pytest.fixture
    def config(self):
        return StrategyConfig(
            target_mode="adaptive",
            target_fixed_rr_multiple=1.5,
            min_reward_risk=1.5,
            zone_clearance_buffer_pct=0.2,
        )

    def test_adaptive_target_opposing_resistance_for_long(self, config):
        """For a long trade, target should be just below the nearest resistance zone."""
        planner = AdaptiveTargetPlanner(config)
        entry = 100.0
        stop = 95.0  # Risk = 5.0. Min RR 1.5 -> target >= 107.5
        now = datetime.now(timezone.utc)

        # Resistance zone from 110.0 to 112.0
        resistance_zone = Zone(
            zone_type=ZoneType.RESISTANCE,
            price_low=110.0,
            price_high=112.0,
            first_seen=now,
            last_seen=now,
            touches=3,
        )

        res = planner.compute_initial_target(
            entry=entry,
            stop=stop,
            direction="long",
            all_zones=[resistance_zone],
        )

        assert res.target is not None
        # Target should be placed just before 110.0 (e.g. 110.0 - 0.2% buffer = 109.78)
        assert res.target < 110.0
        assert res.target > 107.5  # Meets min RR 1.5
        assert res.opposing_zone == resistance_zone
        assert "structure_zone" in res.method

    def test_adaptive_target_opposing_support_for_short(self, config):
        """For a short trade, target should be just above the nearest support zone."""
        planner = AdaptiveTargetPlanner(config)
        entry = 100.0
        stop = 105.0  # Risk = 5.0. Min RR 1.5 -> target <= 92.5
        now = datetime.now(timezone.utc)

        # Support zone from 88.0 to 90.0
        support_zone = Zone(
            zone_type=ZoneType.SUPPORT,
            price_low=88.0,
            price_high=90.0,
            first_seen=now,
            last_seen=now,
            touches=3,
        )

        res = planner.compute_initial_target(
            entry=entry,
            stop=stop,
            direction="short",
            all_zones=[support_zone],
        )

        assert res.target is not None
        # Target should be placed just above 90.0 (90.0 + 0.2% buffer = 90.18)
        assert res.target > 90.0
        assert res.target < 92.5  # Meets min RR
        assert res.opposing_zone == support_zone

    def test_adaptive_target_no_opposing_zone_fallback(self, config):
        """If no opposing zone exists, fall back to target_fixed_rr_multiple (1.5R)."""
        planner = AdaptiveTargetPlanner(config)
        entry = 100.0
        stop = 95.0  # Risk = 5.0

        res = planner.compute_initial_target(
            entry=entry,
            stop=stop,
            direction="long",
            all_zones=[],  # No zones
        )

        assert res.target is not None
        assert res.target == pytest.approx(100.0 + 5.0 * 1.5)  # 107.5
        assert res.opposing_zone is None
        assert "fixed_rr" in res.method

    def test_adaptive_target_opposing_zone_too_close_rejects(self, config):
        """If opposing zone gives RR < min_reward_risk (1.5), target is rejected."""
        planner = AdaptiveTargetPlanner(config)
        entry = 100.0
        stop = 95.0  # Risk = 5.0. Min target is 107.5
        now = datetime.now(timezone.utc)

        # Resistance at 104.0 (RR would only be ~0.8)
        close_resistance = Zone(
            zone_type=ZoneType.RESISTANCE,
            price_low=104.0,
            price_high=105.0,
            first_seen=now,
            last_seen=now,
            touches=3,
        )

        res = planner.compute_initial_target(
            entry=entry,
            stop=stop,
            direction="long",
            all_zones=[close_resistance],
        )

        # Since opposing resistance is blocking at 104, placing target before 104 gives RR < 1.5
        # The planner should flag insufficient RR or reject
        assert res.target is None or res.rr_ratio < 1.5 or res.rejected_reason != ""

    def test_source_zone_excluded_from_opposing_zones(self, config):
        """The source zone that triggered the bounce/breakout must not be used as opposing target."""
        planner = AdaptiveTargetPlanner(config)
        entry = 100.0
        stop = 95.0
        now = datetime.now(timezone.utc)

        source_support = Zone(
            zone_type=ZoneType.SUPPORT,
            price_low=98.0,
            price_high=100.5,
            first_seen=now,
            last_seen=now,
            touches=3,
        )

        res = planner.compute_initial_target(
            entry=entry,
            stop=stop,
            direction="long",
            all_zones=[source_support],
            source_zone=source_support,
        )

        # Source zone excluded, no other zone -> fallback to fixed RR
        assert res.opposing_zone is None
        assert res.target == pytest.approx(107.5)
