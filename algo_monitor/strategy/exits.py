"""
Advanced Exit Management Module (Document 2 Requirement).

Implements disciplined exit execution strategies:
1. Fixed Initial Target / Stop Loss (Baseline)
2. ATR-Based Trailing Stop:
   - Tracks highest favorable price excursion.
   - Ratchets stop-loss by k * ATR behind the peak (never loosens).
3. Swing-Based Trailing Stop:
   - Trails stop-loss behind confirmed structural swing lows (long) or swing highs (short).
4. Partial-Profit Taking + Trailing Runner:
   - Liquidates a portion (e.g., 50%) of the position at Target 1 (e.g., 1.0R or first opposing zone).
   - Automatically advances the remaining position's stop-loss to Breakeven.
   - Allows the residual position ("runner") to trail until structural exhaustion or trailing stop hit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

from algo_monitor.data.models import Candle
from algo_monitor.strategy.levels import calculate_atr
from algo_monitor.utils.logging import get_logger

if TYPE_CHECKING:
    from algo_monitor.config.settings import ExitConfig

logger = get_logger("strategy.exits")


class ExitMode(str, Enum):
    NONE = "none"
    ATR = "atr"
    SWING = "swing"
    PARTIAL_PLUS_ATR = "partial_plus_atr"
    PARTIAL_PLUS_SWING = "partial_plus_swing"


@dataclass
class PositionExitState:
    """Tracks state and trailing levels for an open trade."""
    trade_id: str | int
    symbol: str
    direction: str  # "long" or "short"
    entry_price: float
    initial_sl: float
    initial_tp: float
    initial_qty: float
    current_sl: float
    remaining_qty: float
    highest_favorable_price: float
    partial_taken: bool = False
    partial_exit_price: float | None = None
    partial_pnl: float = 0.0
    is_closed: bool = False
    exit_price: float | None = None
    exit_reason: str | None = None
    exit_time: datetime | None = None


@dataclass
class ExitEvaluationResult:
    """Outcome of evaluating exit conditions on a single bar/tick."""
    is_closed: bool = False
    exit_price: float | None = None
    exit_reason: str | None = None
    partial_filled: bool = False
    partial_qty: float = 0.0
    partial_exit_price: float | None = None
    new_sl: float | None = None
    notes: str = ""


class AdvancedExitManager:
    """
    Manages trailing stops and partial profit execution.
    """

    def __init__(self, exit_config: ExitConfig):
        self.config = exit_config

    def create_position_state(
        self,
        trade_id: str | int,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        target: float,
        quantity: float,
    ) -> PositionExitState:
        """Initialise exit state tracking for a newly opened position."""
        return PositionExitState(
            trade_id=trade_id,
            symbol=symbol,
            direction=direction.lower(),
            entry_price=entry_price,
            initial_sl=stop_loss,
            initial_tp=target,
            initial_qty=quantity,
            current_sl=stop_loss,
            remaining_qty=quantity,
            highest_favorable_price=entry_price,
        )

    def evaluate_bar(
        self,
        state: PositionExitState,
        candle: Candle,
        atr_val: float | None = None,
        recent_candles: list[Candle] | None = None,
    ) -> ExitEvaluationResult:
        """
        Evaluate an open position against the completed or active bar.
        Checks:
        1. Stop Loss hit
        2. Final Target hit
        3. Partial profit target hit
        4. Trailing stop ratchet
        """
        if state.is_closed or state.remaining_qty <= 0:
            return ExitEvaluationResult(is_closed=True, exit_reason="already_closed")

        is_long = state.direction == "long"
        result = ExitEvaluationResult()

        # 1. Update peak excursion
        if is_long:
            state.highest_favorable_price = max(state.highest_favorable_price, candle.high)
        else:
            state.highest_favorable_price = min(state.highest_favorable_price, candle.low)

        # 2. Check Stop Loss trigger (conservative: check SL first)
        if is_long and candle.low <= state.current_sl:
            state.is_closed = True
            state.exit_price = state.current_sl
            state.exit_reason = "stop_loss"
            state.exit_time = candle.timestamp or datetime.now(timezone.utc)
            result.is_closed = True
            result.exit_price = state.current_sl
            result.exit_reason = "stop_loss"
            return result
        elif not is_long and candle.high >= state.current_sl:
            state.is_closed = True
            state.exit_price = state.current_sl
            state.exit_reason = "stop_loss"
            state.exit_time = candle.timestamp or datetime.now(timezone.utc)
            result.is_closed = True
            result.exit_price = state.current_sl
            result.exit_reason = "stop_loss"
            return result

        # 3. Check Final Target trigger
        if is_long and candle.high >= state.initial_tp:
            state.is_closed = True
            state.exit_price = state.initial_tp
            state.exit_reason = "target_hit"
            state.exit_time = candle.timestamp or datetime.now(timezone.utc)
            result.is_closed = True
            result.exit_price = state.initial_tp
            result.exit_reason = "target_hit"
            return result
        elif not is_long and candle.low <= state.initial_tp:
            state.is_closed = True
            state.exit_price = state.initial_tp
            state.exit_reason = "target_hit"
            state.exit_time = candle.timestamp or datetime.now(timezone.utc)
            result.is_closed = True
            result.exit_price = state.initial_tp
            result.exit_reason = "target_hit"
            return result

        # 4. Check Partial Profit Taking
        mode = self.config.trailing_stop_mode
        is_partial_mode = mode in ("partial_plus_atr", "partial_plus_swing")

        if is_partial_mode and not state.partial_taken:
            risk = abs(state.entry_price - state.initial_sl)
            partial_target_distance = risk * self.config.partial_profit_r_mult

            partial_hit = False
            partial_target_price = 0.0

            if is_long:
                partial_target_price = state.entry_price + partial_target_distance
                if candle.high >= partial_target_price:
                    partial_hit = True
            else:
                partial_target_price = state.entry_price - partial_target_distance
                if candle.low <= partial_target_price:
                    partial_hit = True

            if partial_hit:
                state.partial_taken = True
                take_qty = round(state.initial_qty * self.config.partial_profit_pct, 4)
                state.remaining_qty = max(0.0, state.remaining_qty - take_qty)
                state.partial_exit_price = partial_target_price

                result.partial_filled = True
                result.partial_qty = take_qty
                result.partial_exit_price = partial_target_price

                # Move Stop Loss to Breakeven
                if self.config.move_to_breakeven_on_partial:
                    if is_long and state.current_sl < state.entry_price:
                        state.current_sl = state.entry_price
                        result.new_sl = state.entry_price
                        result.notes = "Partial profit taken; SL moved to breakeven"
                    elif not is_long and state.current_sl > state.entry_price:
                        state.current_sl = state.entry_price
                        result.new_sl = state.entry_price
                        result.notes = "Partial profit taken; SL moved to breakeven"

        # 5. Check Trailing Stop Ratchet
        should_trail = (
            mode in ("atr", "swing") or
            (is_partial_mode and state.partial_taken)
        )

        if should_trail and not result.partial_filled:
            new_trail_sl = self._calculate_trailing_stop(
                state=state,
                candle=candle,
                mode=mode,
                atr_val=atr_val,
                recent_candles=recent_candles,
            )
            if new_trail_sl is not None:
                if is_long and new_trail_sl > state.current_sl:
                    state.current_sl = new_trail_sl
                    result.new_sl = new_trail_sl
                elif not is_long and new_trail_sl < state.current_sl:
                    state.current_sl = new_trail_sl
                    result.new_sl = new_trail_sl

        return result

    def _calculate_trailing_stop(
        self,
        state: PositionExitState,
        candle: Candle,
        mode: str,
        atr_val: float | None,
        recent_candles: list[Candle] | None,
    ) -> float | None:
        """Compute candidate trailing stop price based on mode."""
        is_long = state.direction == "long"

        # ATR Trailing Stop
        if "atr" in mode:
            if atr_val is None or atr_val <= 0:
                if recent_candles:
                    atr_val = calculate_atr(recent_candles)
                else:
                    return None
            if atr_val <= 0:
                return None

            trail_distance = atr_val * self.config.trailing_atr_mult
            if is_long:
                return state.highest_favorable_price - trail_distance
            else:
                return state.highest_favorable_price + trail_distance

        # Swing-Based Trailing Stop
        elif "swing" in mode:
            if not recent_candles or len(recent_candles) < self.config.swing_lookback * 2 + 1:
                return None

            lookback = self.config.swing_lookback
            # Find the most recent confirmed swing pivot in recent candles
            if is_long:
                # Find most recent swing low
                candidate_lows: list[float] = []
                for i in range(len(recent_candles) - 1 - lookback, lookback - 1, -1):
                    bar = recent_candles[i]
                    is_pivot = True
                    for j in range(1, lookback + 1):
                        if recent_candles[i - j].low < bar.low or recent_candles[i + j].low < bar.low:
                            is_pivot = False
                            break
                    if is_pivot:
                        candidate_lows.append(bar.low)
                        break
                if candidate_lows:
                    return candidate_lows[0]
            else:
                # Find most recent swing high
                candidate_highs: list[float] = []
                for i in range(len(recent_candles) - 1 - lookback, lookback - 1, -1):
                    bar = recent_candles[i]
                    is_pivot = True
                    for j in range(1, lookback + 1):
                        if recent_candles[i - j].high > bar.high or recent_candles[i + j].high > bar.high:
                            is_pivot = False
                            break
                    if is_pivot:
                        candidate_highs.append(bar.high)
                        break
                if candidate_highs:
                    return candidate_highs[0]

        return None
