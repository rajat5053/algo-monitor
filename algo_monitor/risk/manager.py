"""
Risk management module.

Validates trade candidates against configurable risk rules before
they are accepted by the paper-trading engine.

Rules enforced:
- Position sizing based on stop-loss distance and risk budget
- Maximum simultaneous positions
- Maximum daily loss (circuit breaker)
- Minimum reward-to-risk ratio
- Duplicate / conflicting position prevention
- Trading cost assumptions (fees + slippage)
- Stale / invalid data rejection
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from algo_monitor.strategy.signals import Direction, Signal
from algo_monitor.utils.logging import get_logger

if TYPE_CHECKING:
    from algo_monitor.config.settings import RiskConfig

logger = get_logger("risk.manager")

# IST offset: UTC+05:30
_IST = timezone(timedelta(hours=5, minutes=30))


def _trading_day_str(symbol: str, exchange: str) -> str:
    """
    Return the trading-day date string for circuit-breaker accounting.

    P0-D FIX: Indian market instruments use IST (UTC+05:30) so the daily
    loss limit covers the full NSE session (09:15–15:30 IST) without being
    split across two UTC dates.

    Crypto instruments (Delta Exchange) use UTC because their sessions are
    continuous and exchange timestamps are UTC-native.
    """
    is_indian = (
        exchange == "upstox"
        or not any(c in symbol.upper() for c in ("BTC", "ETH", "SOL", "XRP",
                                                   "BNB", "DOGE", "AVAX",
                                                   "LINK", "NEAR", "DOT",
                                                   "SUI", "PEPE", "USD"))
    )
    if is_indian:
        return datetime.now(_IST).strftime("%Y-%m-%d")
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@dataclass
class RiskDecision:
    """Result of a risk check on a trade candidate."""

    approved: bool
    quantity: float = 0
    risk_amount: float = 0        # Total INR at risk
    estimated_fees: float = 0
    estimated_slippage: float = 0
    reject_reasons: list[str] | None = None
    warnings: list[str] | None = None

    def __post_init__(self):
        if self.reject_reasons is None:
            self.reject_reasons = []
        if self.warnings is None:
            self.warnings = []


class RiskManager:
    """
    Independent risk management engine for paper trading.

    Performs all validation and position-sizing calculations
    without relying on the strategy engine.
    """

    def __init__(self, config: RiskConfig):
        self.config = config
        self._daily_pnl: dict[str, float] = {}  # date string -> realised P&L
        self._open_positions: list[dict] = []    # Track open positions
        self._circuit_tripped = False
        self._circuit_trip_date: str = ""

    def evaluate(
        self,
        signal: Signal,
        current_price: float,
        current_balance: float,
        open_positions: list[dict],
        daily_realised_pnl: float = 0,
    ) -> RiskDecision:
        """
        Evaluate a signal against all risk rules.

        Returns a RiskDecision with approval status and computed values.
        If rejected, reject_reasons explains why.
        """
        reasons = []
        warnings = []

        # --- 1. Basic validation ---
        if signal.entry_ref is None or signal.entry_ref <= 0:
            reasons.append("No valid entry reference price")

        if signal.stop_loss is None or signal.stop_loss <= 0:
            reasons.append("No valid stop-loss level")

        if signal.target is None or signal.target <= 0:
            reasons.append("No valid target level")

        if current_price <= 0:
            reasons.append("Current price is zero or negative")

        if current_balance <= 0:
            reasons.append("No available balance")

        if reasons:
            return RiskDecision(approved=False, reject_reasons=reasons)

        entry = signal.entry_ref
        stop = signal.stop_loss
        target = signal.target

        # --- 2. Reward-to-risk check ---
        if signal.direction == Direction.LONG:
            risk_per_unit = entry - stop
            reward_per_unit = target - entry
        else:
            risk_per_unit = stop - entry
            reward_per_unit = entry - target

        if risk_per_unit <= 0:
            reasons.append(
                f"Invalid risk distance: entry={entry:.2f}, stop={stop:.2f}"
            )
            return RiskDecision(approved=False, reject_reasons=reasons)

        rr_ratio = reward_per_unit / risk_per_unit
        if round(rr_ratio, 2) < self.config.min_reward_risk:
            reasons.append(
                f"Reward-to-risk {rr_ratio:.2f} < minimum {self.config.min_reward_risk}"
            )

        # --- 3. Circuit breaker (daily loss limit) ---
        # P0-D FIX: use IST-aware date for Indian instruments, UTC for crypto.
        today = _trading_day_str(signal.symbol, signal.exchange)
        if self._circuit_tripped and self._circuit_trip_date == today:
            reasons.append("Daily loss circuit breaker is active")

        max_daily_loss_amount = current_balance * self.config.max_daily_loss
        if daily_realised_pnl < 0 and abs(daily_realised_pnl) >= max_daily_loss_amount:
            self._circuit_tripped = True
            self._circuit_trip_date = today
            reasons.append(
                f"Daily loss {daily_realised_pnl:.2f} exceeds limit "
                f"{-max_daily_loss_amount:.2f}"
            )

        # --- 4. Maximum positions ---
        if len(open_positions) >= self.config.max_positions:
            reasons.append(
                f"Maximum positions ({self.config.max_positions}) reached"
            )

        # --- 5. Duplicate / conflicting position check ---
        for pos in open_positions:
            if (pos.get("symbol") == signal.symbol and
                    pos.get("exchange") == signal.exchange):
                if pos.get("direction") == signal.direction.value:
                    reasons.append(
                        f"Duplicate position already open for "
                        f"{signal.symbol}/{signal.exchange} ({signal.direction.value})"
                    )
                else:
                    reasons.append(
                        f"Conflicting position: existing {pos.get('direction')} "
                        f"vs new {signal.direction.value} for {signal.symbol}"
                    )

        # --- 6. Position sizing & Manageable Leverage Constraints ---
        is_usd = "USD" in signal.symbol or signal.symbol.endswith("USD")
        usd_rate = getattr(self.config, "usd_inr_rate", 85.0)
        fx_rate = usd_rate if is_usd else 1.0

        # Available capital in quote currency (e.g. USD for ETHUSD, INR for BTC_INR)
        balance_quote = current_balance / fx_rate

        # 6a. Risk-budget sizing (% of capital)
        risk_budget_quote = balance_quote * self.config.risk_per_trade
        qty_risk = risk_budget_quote / risk_per_unit

        # 6b. Manageable broker leverage & margin limits
        max_leverage = getattr(self.config, "max_leverage", 3.0)
        max_margin_pct = getattr(self.config, "max_capital_per_trade_pct", 0.5)
        max_margin_quote = balance_quote * max_margin_pct
        max_notional_quote = max_margin_quote * max_leverage
        qty_leverage = max_notional_quote / entry

        # Conservative size bounded by risk budget and broker margin
        raw_quantity = min(qty_risk, qty_leverage)

        # 6c. Apply lot sizing rules per asset class
        quantity = self._apply_lot_sizing(signal.symbol, raw_quantity)

        if quantity <= 0:
            reasons.append(
                f"Position size exceeds capital constraints or below minimum lot (balance=INR {current_balance:.0f}, max leverage={max_leverage:.1f}x)"
            )

        # Total INR amount at risk
        risk_budget = (quantity * risk_per_unit) * fx_rate

        # --- 7. Estimated costs ---
        notional_inr = quantity * entry * fx_rate
        est_fees = notional_inr * self.config.fee_rate * 2  # Entry + exit
        est_slippage = notional_inr * self.config.slippage_rate * 2
        total_cost = est_fees + est_slippage

        # Check if costs eat into the reward unreasonably
        gross_reward_inr = quantity * reward_per_unit * fx_rate
        if gross_reward_inr > 0 and total_cost / gross_reward_inr > 0.3:
            warnings.append(
                f"Trading costs ({total_cost:.2f}) are >{30}% of "
                f"gross reward ({gross_reward_inr:.2f})"
            )

        # --- 8. Data staleness check ---
        if signal.created_at:
            age = (datetime.now(timezone.utc) - signal.created_at).total_seconds()
            if age > 3600:  # Signal older than 1 hour
                warnings.append(f"Signal is {age / 60:.0f} minutes old")
            if age > 7200:  # Reject if > 2 hours
                reasons.append(f"Signal too stale ({age / 3600:.1f} hours old)")

        if reasons:
            logger.info(
                "Trade REJECTED for %s: %s",
                signal.symbol,
                "; ".join(reasons),
            )
            return RiskDecision(
                approved=False,
                quantity=quantity,
                risk_amount=risk_budget,
                estimated_fees=est_fees,
                estimated_slippage=est_slippage,
                reject_reasons=reasons,
                warnings=warnings,
            )

        logger.info(
            "Trade APPROVED for %s: qty=%.4f, risk=%.2f, R:R=%.2f",
            signal.symbol,
            quantity,
            risk_budget,
            rr_ratio,
        )

        return RiskDecision(
            approved=True,
            quantity=quantity,
            risk_amount=risk_budget,
            estimated_fees=est_fees,
            estimated_slippage=est_slippage,
            warnings=warnings,
        )

    def reset_circuit_breaker(self) -> None:
        """Reset the daily circuit breaker (called at start of new trading day)."""
        self._circuit_tripped = False
        self._circuit_trip_date = ""
        logger.info("Circuit breaker reset")

    def _apply_lot_sizing(self, symbol: str, quantity: float) -> float:
        """Apply instrument-specific lot sizes, minimum quantities, and rounding."""
        sym = symbol.upper()
        if "NIFTY50" in sym or "NIFTY 50" in sym:
            lot_size = 25
            return float(int(quantity // lot_size) * lot_size)
        elif "BANKNIFTY" in sym:
            lot_size = 15
            return float(int(quantity // lot_size) * lot_size)
        elif "BTC" in sym:
            return round(quantity, 3)
        elif "ETH" in sym:
            return round(quantity, 2)
        else:
            return round(quantity, 4)
