"""
Risk management module.

Validates trade candidates against configurable risk rules before
they are accepted by the paper-trading engine.

Rules enforced:
- Per-market position sizing based on stop-loss distance and risk budget
- Maximum simultaneous positions
- Maximum daily loss (circuit breaker) — 2% of equity
- Maximum weekly loss — 4% of peak equity
- Maximum peak-to-trough drawdown — 8% of peak equity
- Maximum aggregate planned open risk — 1% of equity across all open positions
- Minimum reward-to-risk ratio
- Duplicate / conflicting position prevention
- Trading cost assumptions (fees + slippage)
- Stale / invalid data rejection
- Capital allocation limit — 25% of equity per trade
- Leverage ceiling — 1x (spot positions)
- If minimum lot exceeds risk budget, the trade is skipped
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

    Indian market instruments use IST (UTC+05:30) so the daily
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


def _iso_week_str(symbol: str, exchange: str) -> str:
    """Return ISO year-week string for weekly drawdown tracking."""
    is_indian = (
        exchange == "upstox"
        or not any(c in symbol.upper() for c in ("BTC", "ETH", "SOL", "XRP",
                                                   "BNB", "DOGE", "AVAX",
                                                   "LINK", "NEAR", "DOT",
                                                   "SUI", "PEPE", "USD"))
    )
    if is_indian:
        dt = datetime.now(_IST)
    else:
        dt = datetime.now(timezone.utc)
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


@dataclass
class RiskDecision:
    """Result of a risk check on a trade candidate."""

    approved: bool
    quantity: float = 0
    capital_utilized: float = 0   # Position value (qty * entry * fx_rate) in INR
    risk_amount: float = 0        # Planned cash at risk in INR (qty * risk_per_unit * fx_rate)
    leverage: float = 1.0         # Effective leverage applied
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

    Key invariants:
    - Risk budget per trade is determined by the per-market risk percentage.
    - Position size is the MINIMUM of: risk budget, capital allocation limit,
      available balance, and leverage constraint.
    - If the minimum lot would exceed the risk budget, the trade is skipped.
    - Aggregate open risk across all positions cannot exceed max_aggregate_open_risk.
    - Daily, weekly, and peak drawdown circuit breakers block new entries.
    """

    def __init__(self, config: RiskConfig):
        self.config = config
        self._daily_pnl: dict[str, float] = {}
        self._open_positions: list[dict] = []
        self._circuit_tripped = False
        self._circuit_trip_date: str = ""
        # Peak balance tracking for drawdown calculation
        self._peak_balance: float = config.starting_balance

    def update_peak_balance(self, current_balance: float) -> None:
        """Update the peak balance for drawdown calculation. Call after each trade close."""
        if current_balance > self._peak_balance:
            self._peak_balance = current_balance

    def evaluate(
        self,
        signal: Signal,
        current_price: float,
        current_balance: float,
        open_positions: list[dict],
        daily_realised_pnl: float = 0,
        weekly_realised_pnl: float = 0,
    ) -> RiskDecision:
        """
        Evaluate a signal against all risk rules.

        Returns a RiskDecision with approval status and computed values.
        If rejected, reject_reasons explains why.

        Parameters:
            signal: The trading signal to evaluate.
            current_price: Current market price of the instrument.
            current_balance: Current paper-trading account balance (INR).
            open_positions: List of currently open position dicts.
            daily_realised_pnl: Today's realised P&L (negative = loss).
            weekly_realised_pnl: This week's realised P&L (negative = loss).
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
                f"Invalid risk distance: entry={entry:.4f}, stop={stop:.4f}"
            )
            return RiskDecision(approved=False, reject_reasons=reasons)

        rr_ratio = reward_per_unit / risk_per_unit
        if round(rr_ratio, 2) < self.config.min_reward_risk:
            reasons.append(
                f"Reward-to-risk {rr_ratio:.2f} < minimum {self.config.min_reward_risk}"
            )

        # --- 3. Daily loss circuit breaker ---
        today = _trading_day_str(signal.symbol, signal.exchange)
        if self._circuit_tripped and self._circuit_trip_date == today:
            reasons.append("Daily loss circuit breaker is active")

        max_daily_loss_amount = current_balance * self.config.max_daily_loss
        if daily_realised_pnl < 0 and abs(daily_realised_pnl) >= max_daily_loss_amount:
            self._circuit_tripped = True
            self._circuit_trip_date = today
            reasons.append(
                f"Daily loss {daily_realised_pnl:.2f} exceeds limit "
                f"{-max_daily_loss_amount:.2f} ({self.config.max_daily_loss*100:.0f}% of equity)"
            )

        # --- 4. Weekly drawdown breaker ---
        max_weekly_loss_amount = current_balance * self.config.max_weekly_loss
        if weekly_realised_pnl < 0 and abs(weekly_realised_pnl) >= max_weekly_loss_amount:
            reasons.append(
                f"Weekly loss {weekly_realised_pnl:.2f} exceeds limit "
                f"{-max_weekly_loss_amount:.2f} ({self.config.max_weekly_loss*100:.0f}% of equity)"
            )

        # --- 5. Peak drawdown breaker ---
        self.update_peak_balance(current_balance)
        if self._peak_balance > 0:
            peak_drawdown_pct = (self._peak_balance - current_balance) / self._peak_balance
            if peak_drawdown_pct >= self.config.max_peak_drawdown:
                reasons.append(
                    f"Peak drawdown {peak_drawdown_pct*100:.1f}% exceeds limit "
                    f"{self.config.max_peak_drawdown*100:.0f}%"
                )

        # --- 6. Maximum positions ---
        if len(open_positions) >= self.config.max_positions:
            reasons.append(
                f"Maximum positions ({self.config.max_positions}) reached"
            )

        # --- 7. Duplicate / conflicting position check ---
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

        # --- 8. Position sizing with per-market risk budget ---
        is_usd = "USD" in signal.symbol or signal.symbol.endswith("USD")
        usd_rate = getattr(self.config, "usd_inr_rate", 85.0)
        fx_rate = usd_rate if is_usd else 1.0

        # Balance in instrument's quote currency (USD for crypto, INR for Indian)
        balance_quote = current_balance / fx_rate

        # 8a. Per-market risk budget sizing
        per_market_risk_pct = self.config.get_risk_per_trade(
            exchange=signal.exchange, symbol=signal.symbol
        )
        risk_budget_quote = balance_quote * per_market_risk_pct
        qty_risk = risk_budget_quote / risk_per_unit

        # 8b. Capital allocation limit: max 25% of equity per trade (1x leverage ceiling)
        max_allocation_pct = getattr(self.config, "max_capital_per_trade_pct", 0.25)
        max_leverage = getattr(self.config, "max_leverage", 1.0)
        max_allocation_quote = balance_quote * max_allocation_pct
        max_notional_quote = max_allocation_quote * max_leverage
        qty_leverage = max_notional_quote / entry

        # Most restrictive: risk budget or capital allocation limit
        raw_quantity = min(qty_risk, qty_leverage)

        # 8c. Apply lot sizing rules per asset class
        quantity = self._apply_lot_sizing(signal.symbol, raw_quantity)

        if quantity <= 0:
            reasons.append(
                f"Position size is zero or below minimum lot "
                f"(balance=INR {current_balance:.0f}, "
                f"risk_budget={risk_budget_quote * fx_rate:.2f} INR, "
                f"risk/unit={risk_per_unit:.4f}, leverage_cap={max_leverage:.1f}x)"
            )
        else:
            # 8d. Verify: the sized quantity must not exceed the risk budget
            actual_risk_inr = quantity * risk_per_unit * fx_rate
            if actual_risk_inr > risk_budget_quote * fx_rate * 1.05:  # 5% tolerance for rounding
                reasons.append(
                    f"Sized quantity would risk {actual_risk_inr:.2f} INR, "
                    f"exceeding risk budget {risk_budget_quote * fx_rate:.2f} INR"
                )
                quantity = 0

        # Capital utilized = position notional value in INR
        capital_utilized_inr = quantity * entry * fx_rate
        # Planned risk in INR
        risk_budget_inr = quantity * risk_per_unit * fx_rate
        # Effective leverage
        effective_leverage = (capital_utilized_inr / current_balance) if current_balance > 0 else 0.0

        # --- 9. Aggregate open risk check ---
        # Sum risk_amount of all open positions plus this new trade's risk
        existing_risk_inr = sum(
            float(pos.get("risk_amount", 0) or 0) for pos in open_positions
        )
        total_planned_risk_inr = existing_risk_inr + risk_budget_inr
        max_aggregate_risk_inr = current_balance * self.config.max_aggregate_open_risk
        if total_planned_risk_inr > max_aggregate_risk_inr:
            reasons.append(
                f"Aggregate open risk {total_planned_risk_inr:.2f} INR would exceed "
                f"limit {max_aggregate_risk_inr:.2f} INR "
                f"({self.config.max_aggregate_open_risk*100:.0f}% of equity)"
            )

        # --- 10. Estimated costs ---
        notional_inr = capital_utilized_inr
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

        # --- 11. Data staleness check ---
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
                capital_utilized=capital_utilized_inr,
                risk_amount=risk_budget_inr,
                leverage=effective_leverage,
                estimated_fees=est_fees,
                estimated_slippage=est_slippage,
                reject_reasons=reasons,
                warnings=warnings,
            )

        logger.info(
            "Trade APPROVED for %s: qty=%.4f, capital=%.2f INR, risk=%.2f INR, R:R=%.2f, leverage=%.2fx",
            signal.symbol,
            quantity,
            capital_utilized_inr,
            risk_budget_inr,
            rr_ratio,
            effective_leverage,
        )

        return RiskDecision(
            approved=True,
            quantity=quantity,
            capital_utilized=capital_utilized_inr,
            risk_amount=risk_budget_inr,
            leverage=effective_leverage,
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
        """
        Apply instrument-specific lot sizes, minimum quantities, and rounding.

        For index futures/options with large lot sizes, if even one lot exceeds
        the risk budget, return 0 (trade skipped) rather than rounding up.
        """
        sym = symbol.upper()
        if "NIFTY50" in sym or "NIFTY 50" in sym:
            lot_size = 25
            lots = int(quantity // lot_size)
            return float(lots * lot_size)
        elif "BANKNIFTY" in sym:
            lot_size = 15
            lots = int(quantity // lot_size)
            return float(lots * lot_size)
        elif "NIFTYAUTO" in sym or "NIFTYMIDCAP" in sym or "MIDCPNIFTY" in sym:
            lot_size = 50
            lots = int(quantity // lot_size)
            return float(lots * lot_size)
        elif "BTC" in sym:
            return round(quantity, 3)
        elif "ETH" in sym:
            return round(quantity, 2)
        elif "SOL" in sym or "XRP" in sym or "BNB" in sym:
            return round(quantity, 1)
        else:
            return round(quantity, 4)
