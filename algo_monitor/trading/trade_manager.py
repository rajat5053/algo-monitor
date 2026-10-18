"""
Adaptive Trade Management for Open Positions (P2-B, P2-C).

Monitors open paper trades against current price action, recent candles,
and higher-timeframe support/resistance structure to generate disciplined,
context-aware trade recommendations.

Explicit Recommendation States:
1. HOLD_CURRENT_PLAN: Price progressing normally; no structural trigger.
2. CONSIDER_TARGET_EXTENSION: High continuation momentum, target approaching,
   and clean structure exists toward the next major opposing zone.
3. CONSIDER_PROFIT_TAKING: Exhaustion or strong opposing reaction near target.
4. CONSIDER_STOP_TIGHTENING: Favorable excursion (+1R) permits trailing stop to
   breakeven or recent swing pivot to protect capital.
5. EXIT_THESIS_INVALIDATED: Premise broken (origin zone lost, adverse expansion).
6. MONITORING_UNAVAILABLE: Stale market data or missing structural context.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING

from algo_monitor.strategy.levels import Zone, ZoneType
from algo_monitor.utils.logging import get_logger

if TYPE_CHECKING:
    from algo_monitor.alerts.notifier import AlertManager
    from algo_monitor.config.settings import StrategyConfig
    from algo_monitor.database import Database
    from algo_monitor.data.models import Candle

logger = get_logger("trading.trade_manager")


class TradeManagementState(str, Enum):
    HOLD_CURRENT_PLAN = "HOLD_CURRENT_PLAN"
    CONSIDER_TARGET_EXTENSION = "CONSIDER_TARGET_EXTENSION"
    CONSIDER_PROFIT_TAKING = "CONSIDER_PROFIT_TAKING"
    CONSIDER_STOP_TIGHTENING = "CONSIDER_STOP_TIGHTENING"
    EXIT_THESIS_INVALIDATED = "EXIT_THESIS_INVALIDATED"
    MONITORING_UNAVAILABLE = "MONITORING_UNAVAILABLE"


@dataclass
class TradeEvaluation:
    """Detailed evaluation result for an open trade."""

    trade_id: int
    symbol: str
    direction: str
    state: TradeManagementState
    current_price: float
    entry_price: float
    stop_loss: float
    current_target: float
    proposed_target: float | None = None
    r_achieved: float = 0.0
    progress_pct: float = 0.0
    evidence_for: list[str] = field(default_factory=list)
    evidence_against: list[str] = field(default_factory=list)
    opposing_zone_info: str = ""
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    entry_time: str = ""

    @property
    def alert_hash(self) -> str:
        """Deterministic fingerprint for duplicate suppression."""
        target_str = f"{self.proposed_target:.4f}" if self.proposed_target else "none"
        raw = f"{self.trade_id}:{self.state.value}:{target_str}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


class TradeManager:
    """
    Evaluates open paper trades against live price action and market structure.
    Suppresses duplicate recommendations and persists state across restarts.
    """

    def __init__(
        self,
        db: Database,
        config: StrategyConfig,
        alert_manager: AlertManager | None = None,
    ):
        self.db = db
        self.config = config
        self.alert_manager = alert_manager
        # Cached last alert hash per trade to suppress duplicate alerts
        self._last_alert_states: dict[int, str] = {}
        self._load_persisted_states()

    def _load_persisted_states(self) -> None:
        """Load last alerted states from DB for restart safety."""
        try:
            rows = self.db.fetchall("""
                SELECT trade_id, alert_hash
                FROM trade_management
                WHERE alert_sent = 1
                ORDER BY id ASC
            """)
            for r in rows:
                self._last_alert_states[int(r["trade_id"])] = str(r["alert_hash"])
            logger.debug(
                "Loaded %d trade-management alert states from DB",
                len(self._last_alert_states),
            )
        except Exception as exc:
            logger.warning("Could not load persisted trade management states: %s", exc)

    def evaluate_trade(
        self,
        trade: dict,
        current_price: float,
        candles: list[Candle],
        zones: list[Zone],
    ) -> TradeEvaluation:
        """
        Evaluate a single open trade against market data and S/R zones.
        """
        trade_id = trade.get("id", 0)
        symbol = trade.get("symbol", "")
        direction = str(trade.get("direction", "long")).lower()
        entry = float(trade.get("entry_price", 0.0))
        stop = float(trade.get("stop_loss", 0.0))
        target = float(trade.get("target", 0.0))

        # 1. Check data freshness (MONITORING_UNAVAILABLE)
        is_stale, stale_reason = self._is_data_stale(symbol, candles)
        if is_stale or current_price <= 0 or entry <= 0:
            return TradeEvaluation(
                trade_id=trade_id,
                symbol=symbol,
                direction=direction,
                state=TradeManagementState.MONITORING_UNAVAILABLE,
                current_price=current_price,
                entry_price=entry,
                stop_loss=stop,
                current_target=target,
                evidence_for=[],
                evidence_against=[stale_reason or "Missing valid price or candle data."],
            )

        # 2. Progress and R-multiple calculations
        risk = abs(entry - stop)
        if direction == "long":
            r_achieved = (current_price - entry) / risk if risk > 0 else 0.0
            target_distance = target - entry
            progress_pct = (
                ((current_price - entry) / target_distance * 100)
                if target_distance > 0
                else 0.0
            )
        else:
            r_achieved = (entry - current_price) / risk if risk > 0 else 0.0
            target_distance = entry - target
            progress_pct = (
                ((entry - current_price) / target_distance * 100)
                if target_distance > 0
                else 0.0
            )

        # 3. Thesis Invalidation
        if self._check_thesis_invalidated(direction, current_price, stop, candles):
            return TradeEvaluation(
                trade_id=trade_id,
                symbol=symbol,
                direction=direction,
                state=TradeManagementState.EXIT_THESIS_INVALIDATED,
                current_price=current_price,
                entry_price=entry,
                stop_loss=stop,
                current_target=target,
                r_achieved=r_achieved,
                progress_pct=progress_pct,
                evidence_for=[
                    f"Price closed beyond invalidation threshold ({current_price:.2f} vs stop {stop:.2f}).",
                    "Initial support/resistance thesis structure violated.",
                ],
                evidence_against=["Premise no longer intact."],
            )

        # Find nearest opposing zone ahead of current price
        opposing_zone = self._find_nearest_opposing_zone(
            direction, current_price, zones
        )
        opposing_info = ""
        if opposing_zone:
            opposing_info = (
                f"Opposing {opposing_zone.zone_type.value} at "
                f"[{opposing_zone.price_low:.2f} – {opposing_zone.price_high:.2f}] "
                f"(touches={opposing_zone.touches}, strength={opposing_zone.strength:.2f})"
            )

        # 4. Consider Profit Taking
        if self._check_profit_taking(
            direction, current_price, target, progress_pct, r_achieved, opposing_zone, candles
        ):
            return TradeEvaluation(
                trade_id=trade_id,
                symbol=symbol,
                direction=direction,
                state=TradeManagementState.CONSIDER_PROFIT_TAKING,
                current_price=current_price,
                entry_price=entry,
                stop_loss=stop,
                current_target=target,
                r_achieved=r_achieved,
                progress_pct=progress_pct,
                opposing_zone_info=opposing_info,
                evidence_for=[
                    f"Price reached {progress_pct:.1f}% of target ({r_achieved:.2f}R).",
                    "Opposing structural friction or rejection candle observed near target.",
                    "Favorable gain secured; protecting profits before potential mean-reversion.",
                ],
                evidence_against=[
                    "Strong broader trend might still carry price further beyond current target."
                ],
            )

        # 5. Consider Target Extension
        ext_target = self._check_target_extension(
            direction, entry, current_price, target, progress_pct, r_achieved, opposing_zone, candles
        )
        if ext_target is not None:
            return TradeEvaluation(
                trade_id=trade_id,
                symbol=symbol,
                direction=direction,
                state=TradeManagementState.CONSIDER_TARGET_EXTENSION,
                current_price=current_price,
                entry_price=entry,
                stop_loss=stop,
                current_target=target,
                proposed_target=ext_target,
                r_achieved=r_achieved,
                progress_pct=progress_pct,
                opposing_zone_info=opposing_info,
                evidence_for=[
                    f"Strong momentum reaching {progress_pct:.1f}% to target with clean air ahead.",
                    f"Nearest major structural boundary is located higher at {ext_target:.2f}.",
                    "Recent candle closes confirm continuation with minimal opposing wick.",
                ],
                evidence_against=[
                    f"Position has already run {r_achieved:.1f}R; trailing stop tightening is mandatory if extended.",
                    "Unforeseen reversal would give back unrealized gains.",
                ],
            )

        # 6. Consider Stop Tightening
        if self._check_stop_tightening(direction, entry, stop, r_achieved):
            return TradeEvaluation(
                trade_id=trade_id,
                symbol=symbol,
                direction=direction,
                state=TradeManagementState.CONSIDER_STOP_TIGHTENING,
                current_price=current_price,
                entry_price=entry,
                stop_loss=stop,
                current_target=target,
                r_achieved=r_achieved,
                progress_pct=progress_pct,
                opposing_zone_info=opposing_info,
                evidence_for=[
                    f"Trade has achieved favorable excursion of {r_achieved:.2f}R (> 1.0R).",
                    "Capital preservation rule: move stop loss to breakeven or recent swing pivot.",
                ],
                evidence_against=[
                    "Trailing stop placed too tightly could suffer premature exit on normal pullback."
                ],
            )

        # 7. Default: Hold Current Plan
        return TradeEvaluation(
            trade_id=trade_id,
            symbol=symbol,
            direction=direction,
            state=TradeManagementState.HOLD_CURRENT_PLAN,
            current_price=current_price,
            entry_price=entry,
            stop_loss=stop,
            current_target=target,
            r_achieved=r_achieved,
            progress_pct=progress_pct,
            opposing_zone_info=opposing_info,
            evidence_for=[
                f"Trade is orderly at {r_achieved:.2f}R ({progress_pct:.1f}% to target).",
                "No thesis violation or premature target extension condition met.",
            ],
            evidence_against=["Normal market variance ongoing."],
        )

    def evaluate_and_alert_trade(
        self,
        trade: dict,
        current_price: float,
        candles: list[Candle],
        zones: list[Zone],
    ) -> TradeEvaluation:
        """
        Evaluate an open trade, persist the recommendation, and dispatch Telegram alert
        if the state has changed (duplicate suppression).
        """
        evaluation = self.evaluate_trade(trade, current_price, candles, zones)
        evaluation.entry_time = str(trade.get("entry_time") or "")
        self.persist_and_notify(evaluation)
        return evaluation

    def persist_and_notify(self, eval_result: TradeEvaluation) -> bool:
        """
        Persist evaluation to database and send alert if recommendation is actionable
        and not duplicate. Returns True if alert was sent.
        """
        alert_sent = False
        trade_id = eval_result.trade_id
        current_hash = eval_result.alert_hash
        last_hash = self._last_alert_states.get(trade_id)

        # Only alert if state changed AND recommendation is an active advisory
        is_actionable = eval_result.state not in (
            TradeManagementState.HOLD_CURRENT_PLAN,
            TradeManagementState.MONITORING_UNAVAILABLE,
        )

        should_alert = is_actionable and (last_hash != current_hash)

        if should_alert and self.alert_manager:
            try:
                alert_sent = self.alert_manager.send_trade_management_alert(eval_result)
                if alert_sent:
                    self._last_alert_states[trade_id] = current_hash
            except Exception as exc:
                logger.error("Failed to send trade management alert: %s", exc)

        # Persist to SQLite
        try:
            with self.db.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO trade_management
                        (trade_id, evaluated_at, recommendation, proposed_target,
                         current_target, evidence_for, evidence_against, alert_sent, alert_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(trade_id, recommendation, proposed_target)
                    DO UPDATE SET
                        evaluated_at=excluded.evaluated_at,
                        current_target=excluded.current_target,
                        evidence_for=excluded.evidence_for,
                        evidence_against=excluded.evidence_against,
                        alert_sent=MAX(trade_management.alert_sent, excluded.alert_sent),
                        alert_hash=excluded.alert_hash
                    """,
                    (
                        trade_id,
                        eval_result.evaluated_at.isoformat(),
                        eval_result.state.value,
                        eval_result.proposed_target,
                        eval_result.current_target,
                        json.dumps(eval_result.evidence_for),
                        json.dumps(eval_result.evidence_against),
                        1 if alert_sent else 0,
                        current_hash,
                    ),
                )
        except Exception as exc:
            logger.warning("Could not persist trade management evaluation: %s", exc)

        return alert_sent

    # -------------------------------------------------------------------------
    # Helper heuristic checks
    # -------------------------------------------------------------------------

    def _is_data_stale(
        self, symbol: str, candles: list[Candle]
    ) -> tuple[bool, str]:
        """Check if candle data exceeds freshness threshold."""
        if not candles:
            return True, "No candles available for evaluation."

        latest = candles[-1]
        now = datetime.now(timezone.utc)
        age_seconds = (now - latest.timestamp).total_seconds()

        # Crypto continuous: > 2 hours is stale
        # Equity: > 6 hours is stale
        is_crypto = any(c in symbol.upper() for c in ("BTC", "ETH", "SOL", "USD"))
        threshold = 7200 if is_crypto else 21600

        if age_seconds > threshold:
            return True, f"Data age ({age_seconds / 3600:.1f}h) exceeds maximum threshold."
        return False, ""

    def _check_thesis_invalidated(
        self,
        direction: str,
        current_price: float,
        stop_loss: float,
        candles: list[Candle],
    ) -> bool:
        """Check if price decisively invalidates the trade direction."""
        if direction == "long" and current_price < stop_loss:
            return True
        if direction == "short" and current_price > stop_loss:
            return True

        # Check if recent candles broke decisive structure
        if len(candles) >= 2:
            last = candles[-1]
            if direction == "long" and last.close < stop_loss:
                return True
            if direction == "short" and last.close > stop_loss:
                return True
        return False

    def _check_profit_taking(
        self,
        direction: str,
        current_price: float,
        target: float,
        progress_pct: float,
        r_achieved: float,
        opposing_zone: Zone | None,
        candles: list[Candle],
    ) -> bool:
        """
        Check for profit taking when close to target (>= 85%) and encountering
        opposing zone or exhaustion wick.
        """
        if progress_pct < 85.0 and r_achieved < 1.3:
            return False

        # Strong opposing zone right at or just before target
        if opposing_zone:
            if direction == "long" and opposing_zone.price_low <= target * 1.01:
                return True
            if direction == "short" and opposing_zone.price_high >= target * 0.99:
                return True

        # Exhaustion wick on latest candle
        if candles:
            last = candles[-1]
            if direction == "long" and last.range_size > 0:
                upper_wick = last.high - max(last.open, last.close)
                if upper_wick / last.range_size > 0.45:  # Significant top rejection
                    return True
            elif direction == "short" and last.range_size > 0:
                lower_wick = min(last.open, last.close) - last.low
                if lower_wick / last.range_size > 0.45:  # Significant bottom rejection
                    return True

        return progress_pct >= 95.0

    def _check_target_extension(
        self,
        direction: str,
        entry: float,
        current_price: float,
        target: float,
        progress_pct: float,
        r_achieved: float,
        opposing_zone: Zone | None,
        candles: list[Candle],
    ) -> float | None:
        """
        Propose target extension if approaching target (>= 75%) with clean air
        and strong continuation momentum.
        """
        if progress_pct < 75.0 or r_achieved < 1.2:
            return None

        # Verify recent candle is strong continuation
        if candles:
            last = candles[-1]
            if direction == "long" and not last.is_bullish:
                return None
            if direction == "short" and not last.is_bearish:
                return None

        # If there is an opposing zone immediately at the target, do NOT extend
        if opposing_zone:
            if direction == "long":
                if opposing_zone.price_low <= target * 1.005:
                    return None  # Zone blocks extension
                # Next zone is further up -> can extend to just before it
                buffer = opposing_zone.price_low * 0.002
                proposed = opposing_zone.price_low - buffer
                if proposed > target * 1.05:  # At least 5% further
                    return proposed
            else:  # short
                if opposing_zone.price_high >= target * 0.995:
                    return None
                buffer = opposing_zone.price_high * 0.002
                proposed = opposing_zone.price_high + buffer
                if proposed < target * 0.95:
                    return proposed

        # If no blocking opposing zone exists, propose 2.0R or +20% beyond target
        risk = abs(entry - target)
        if direction == "long":
            return target + 0.5 * risk
        else:
            return target - 0.5 * risk

    def _check_stop_tightening(
        self,
        direction: str,
        entry: float,
        current_stop: float,
        r_achieved: float,
    ) -> bool:
        """
        Check if stop should be tightened to breakeven or better once trade reaches +1.0R.
        """
        if r_achieved < 1.0:
            return False

        # If stop is still beyond entry price, recommend tightening
        if direction == "long" and current_stop < entry:
            return True
        if direction == "short" and current_stop > entry:
            return True
        return False

    def _find_nearest_opposing_zone(
        self,
        direction: str,
        price: float,
        zones: list[Zone],
    ) -> Zone | None:
        """Find the nearest active opposing zone ahead of current price."""
        if not zones:
            return None

        if direction == "long":
            candidates = [
                z for z in zones
                if z.zone_type == ZoneType.RESISTANCE
                and not getattr(z, "is_broken", False)
                and z.price_low > price
            ]
            if candidates:
                return min(candidates, key=lambda z: z.price_low)
        else:
            candidates = [
                z for z in zones
                if z.zone_type == ZoneType.SUPPORT
                and not getattr(z, "is_broken", False)
                and z.price_high < price
            ]
            if candidates:
                return max(candidates, key=lambda z: z.price_high)
        return None
