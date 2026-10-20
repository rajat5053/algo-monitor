"""
Paper-trading simulation engine.

Processes signals, manages simulated positions, and persists trades
across restarts.  Handles stop-loss, target, position expiry, and
separates intraday vs swing performance.

PAPER TRADING ONLY — no real orders are ever placed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from algo_monitor.config.instruments import TradingMode
from algo_monitor.options.engine import OptionsEngine
from algo_monitor.options.models import OptionTradeSetup
from algo_monitor.risk.manager import RiskDecision, RiskManager
from algo_monitor.strategy.signals import Direction, Signal
from algo_monitor.utils.logging import get_logger

if TYPE_CHECKING:
    from algo_monitor.config.settings import OptionsConfig, RiskConfig
    from algo_monitor.database import Database

logger = get_logger("trading.engine")


class PaperTradingEngine:
    """
    Simulation engine for paper trading.

    Features:
    - Processes approved signals into simulated positions
    - Seamlessly routes Index & small-capital setups to Options engine
    - Tracks open and closed positions in SQLite
    - Checks stop-loss and target on each price update
    - Handles intraday expiry and swing holding limits
    - Prevents duplicate trades and look-ahead bias
    - Persists state across application restarts
    """

    def __init__(
        self,
        risk_config: RiskConfig,
        db: Database,
        options_config: OptionsConfig | None = None,
        exit_config: ExitConfig | None = None,
    ):
        self.config = risk_config
        self.db = db
        self.options_config = options_config
        from algo_monitor.config.settings import ExitConfig
        self.exit_config = exit_config or ExitConfig()
        self.risk_manager = RiskManager(risk_config)
        self.options_engine = OptionsEngine(risk_config)
        self._balance: float | None = None

    @property
    def balance(self) -> float:
        """Current simulated balance, loaded from DB on first access."""
        if self._balance is None:
            stored = self.db.get_state("paper_balance")
            if stored:
                self._balance = float(stored)
            else:
                self._balance = self.config.starting_balance
                self.db.set_state(
                    "paper_balance", str(self._balance)
                )
        return self._balance

    @balance.setter
    def balance(self, value: float) -> None:
        self._balance = value
        self.db.set_state("paper_balance", str(value))

    # ----- Position management -----

    def get_open_positions(self) -> list[dict]:
        """Get all open paper trades."""
        rows = self.db.fetchall(
            "SELECT * FROM trades WHERE status = 'open' ORDER BY entry_time"
        )
        return [dict(r) for r in rows]

    def get_closed_positions(self, limit: int = 100) -> list[dict]:
        """Get recent closed paper trades."""
        rows = self.db.fetchall(
            "SELECT * FROM trades WHERE status = 'closed' ORDER BY exit_time DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in rows]

    def get_daily_pnl(self, date: str = "") -> dict:
        """Get P&L for a specific date (default: today)."""
        if not date:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        row = self.db.fetchone(
            "SELECT * FROM daily_pnl WHERE date = ?", (date,)
        )
        if row:
            return dict(row)

        # Compute from trades
        rows = self.db.fetchall(
            """SELECT * FROM trades WHERE status = 'closed'
               AND date(exit_time) = ?""",
            (date,),
        )
        total_pnl = sum(r["net_pnl"] or 0 for r in rows)
        total_fees = sum(r["fees"] or 0 for r in rows)

        return {
            "date": date,
            "realised_pnl": total_pnl,
            "total_fees": total_fees,
            "trade_count": len(rows),
        }

    # ----- Signal processing -----

    def process_signal(
        self,
        signal: Signal,
        current_price: float,
        trading_mode: TradingMode = TradingMode.BOTH,
    ) -> dict | None:
        """
        Evaluate a signal and open a paper trade if approved.
        Automatically routes indices (NIFTY/BANKNIFTY) or capital-constrained
        setups to the Options engine for defined-risk option buying.

        Returns the trade record if opened, None if rejected.
        """
        if current_price <= 0:
            logger.warning("Cannot process signal: invalid price %s", current_price)
            return None

        open_positions = self.get_open_positions()

        # Get today's realised P&L for daily circuit breaker
        daily = self.get_daily_pnl()
        daily_pnl = daily.get("realised_pnl", 0)

        # Get this ISO week's realised P&L for weekly circuit breaker
        from datetime import timedelta
        now_ist = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
        iso = now_ist.isocalendar()
        week_start = now_ist - timedelta(days=now_ist.weekday())  # Monday
        week_start_str = week_start.strftime("%Y-%m-%d")
        weekly_rows = self.db.fetchall(
            "SELECT realised_pnl FROM daily_pnl WHERE date >= ?",
            (week_start_str,),
        )
        weekly_pnl = sum(float(r["realised_pnl"] or 0) for r in weekly_rows)

        # Check if options routing should be prioritized (e.g. Indian Indices on ₹15k capital)
        opt_cfg = getattr(self, "options_config", None)
        sym_upper = signal.symbol.upper()
        is_index = "NIFTY" in sym_upper or "BANKNIFTY" in sym_upper
        options_enabled = opt_cfg is not None and opt_cfg.enabled

        if options_enabled and is_index and opt_cfg.auto_route_indices:
            return self._process_option_signal(
                signal=signal,
                current_price=current_price,
                trading_mode=trading_mode,
                open_positions=open_positions,
                daily_pnl=daily_pnl,
            )

        # Standard risk evaluation
        decision = self.risk_manager.evaluate(
            signal=signal,
            current_price=current_price,
            current_balance=self.balance,
            open_positions=open_positions,
            daily_realised_pnl=daily_pnl,
            weekly_realised_pnl=weekly_pnl,
        )

        if not decision.approved:
            # If rejected because futures capital/lot size exceeds ₹15,000, attempt options
            is_size_issue = any(
                "Position size" in r or "capital constraints" in r
                for r in (decision.reject_reasons or [])
            )
            if options_enabled and is_size_issue and self.options_engine.is_option_eligible(signal.symbol):
                logger.info(
                    "Futures sizing rejected for %s (capital constraint); routing to Options Engine",
                    signal.symbol,
                )
                return self._process_option_signal(
                    signal=signal,
                    current_price=current_price,
                    trading_mode=trading_mode,
                    open_positions=open_positions,
                    daily_pnl=daily_pnl,
                )

            logger.info(
                "Signal rejected for %s: %s",
                signal.symbol,
                "; ".join(decision.reject_reasons or []),
            )
            return None

        # Open the standard paper trade
        trade = self._open_trade(signal, decision, trading_mode)
        return trade

    def _process_option_signal(
        self,
        signal: Signal,
        current_price: float,
        trading_mode: TradingMode,
        open_positions: list[dict],
        daily_pnl: float,
    ) -> dict | None:
        """Prepare and open an option trade for small-capital defined-risk execution."""
        # 1. Circuit breaker
        max_daily_loss_amount = self.balance * self.config.max_daily_loss
        if daily_pnl < 0 and abs(daily_pnl) >= max_daily_loss_amount:
            logger.info("Option trade rejected: Daily loss limit reached")
            return None

        # 2. Maximum positions
        if len(open_positions) >= self.config.max_positions:
            logger.info("Option trade rejected: Max positions (%d) reached", self.config.max_positions)
            return None

        # 3. Duplicate check
        for pos in open_positions:
            pos_sym = pos.get("symbol", "")
            if pos_sym.startswith(signal.symbol):
                logger.info("Option trade rejected: Position already open for %s", signal.symbol)
                return None

        # 4. Prepare option setup
        max_cap_pct = getattr(self.options_config, "max_capital_per_option_trade_pct", 0.45) if self.options_config else 0.45
        usd_rate = getattr(self.config, "usd_inr_rate", 85.0)

        setup = self.options_engine.prepare_trade_setup(
            signal=signal,
            spot_price=current_price,
            balance_inr=self.balance,
            max_capital_pct=max_cap_pct,
            usd_inr_rate=usd_rate,
        )

        if not setup:
            logger.info("Option trade rejected: Unable to size contract within capital limits")
            return None

        if setup.capital_required_inr > self.balance:
            logger.info(
                "Option trade rejected: Required outlay INR %.1f > balance INR %.1f",
                setup.capital_required_inr,
                self.balance,
            )
            return None

        return self._open_option_trade(signal, setup, current_price, trading_mode)

    def _open_option_trade(
        self,
        signal: Signal,
        setup: OptionTradeSetup,
        spot_price: float,
        trading_mode: TradingMode,
    ) -> dict:
        """Create and persist a new paper options trade."""
        now = datetime.now(timezone.utc).isoformat()
        mode = trading_mode.value if trading_mode != TradingMode.BOTH else "intraday"

        fee_rate = getattr(self.config, "fee_rate", 0.0005)
        slippage_rate = getattr(self.config, "slippage_rate", 0.0003)
        est_fees = setup.capital_required_inr * fee_rate * 2
        est_slippage = setup.capital_required_inr * slippage_rate * 2

        notes = (
            f"OPTION BUY: {setup.contract.option_type.value} Strike {int(setup.contract.strike)} "
            f"({setup.lots} lot{'s' if setup.lots > 1 else ''} / {int(setup.quantity)} qty) | "
            f"Underlying: {signal.symbol} @ {spot_price:.2f} ({signal.direction.value.upper()}) | "
            f"Setup: {signal.setup_type.value} | Δ={setup.contract.greeks.delta:.2f}, IV={setup.contract.implied_volatility*100:.0f}%"
        )

        trade_data = {
            "signal_id": None,
            "symbol": setup.contract.symbol,
            "exchange": setup.contract.exchange,
            "direction": "long",  # Option buyer is LONG Call/Put
            "trading_mode": mode,
            "status": "open",
            "quantity": setup.quantity,
            "entry_price": setup.entry_premium,
            "entry_time": now,
            "stop_loss": setup.stop_loss_premium,
            "target": setup.target_premium,
            "exit_price": None,
            "exit_time": None,
            "exit_reason": None,
            "gross_pnl": 0,
            "fees": round(est_fees, 2),
            "slippage": round(est_slippage, 2),
            "net_pnl": 0,
            "risk_amount": setup.max_risk_inr,
            "notes": notes,
            "source": "paper",
        }

        with self.db.transaction() as conn:
            cursor = conn.execute(
                """INSERT INTO trades
                   (signal_id, symbol, exchange, direction, trading_mode,
                    status, quantity, entry_price, entry_time, stop_loss,
                    target, fees, slippage, risk_amount, notes, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trade_data["signal_id"],
                    trade_data["symbol"],
                    trade_data["exchange"],
                    trade_data["direction"],
                    trade_data["trading_mode"],
                    trade_data["status"],
                    trade_data["quantity"],
                    trade_data["entry_price"],
                    trade_data["entry_time"],
                    trade_data["stop_loss"],
                    trade_data["target"],
                    trade_data["fees"],
                    trade_data["slippage"],
                    trade_data["risk_amount"],
                    trade_data["notes"],
                    trade_data["source"],
                ),
            )
            trade_data["id"] = cursor.lastrowid

        logger.info(
            "OPTION TRADE OPENED: %s %s @ Premium=%.2f | SL=%.2f | TP=%.2f | Lots=%d (Qty=%.0f) | MaxRisk=INR %.1f",
            trade_data["symbol"],
            trade_data["exchange"],
            trade_data["entry_price"],
            trade_data["stop_loss"],
            trade_data["target"],
            setup.lots,
            trade_data["quantity"],
            trade_data["risk_amount"],
        )

        return trade_data

    def _open_trade(
        self,
        signal: Signal,
        decision: RiskDecision,
        trading_mode: TradingMode,
    ) -> dict:
        """Create and persist a new paper trade."""
        now = datetime.now(timezone.utc).isoformat()

        mode = trading_mode.value
        if trading_mode == TradingMode.BOTH:
            mode = "intraday"  # Default to intraday if not specified

        entry_sl = signal.stop_loss
        entry_target = signal.target

        trade_data = {
            "signal_id": None,  # Will be set if signal is persisted
            "symbol": signal.symbol,
            "exchange": signal.exchange,
            "direction": signal.direction.value,
            "trading_mode": mode,
            "status": "open",
            "quantity": decision.quantity,
            "remaining_quantity": decision.quantity,
            "entry_price": signal.entry_ref,
            "entry_time": now,
            "initial_stop_loss": entry_sl,
            "stop_loss": entry_sl,
            "target": entry_target,
            "initial_target": entry_target,
            "exit_price": None,
            "exit_time": None,
            "exit_reason": None,
            "gross_pnl": 0,
            "fees": decision.estimated_fees,
            "slippage": decision.estimated_slippage,
            "net_pnl": 0,
            "risk_amount": decision.risk_amount,
            "capital_utilized": decision.capital_utilized,
            "leverage": decision.leverage,
            "notes": signal.reason[:500] if signal.reason else "",
            "source": "paper",
            "trailing_mode": getattr(self, "exit_config", None) and getattr(self.exit_config, "trailing_stop_mode", "none") or "none",
            "partial_taken": 0,
            "realized_partial_pnl": 0,
            "exit_description": "",
        }

        with self.db.transaction() as conn:
            cursor = conn.execute(
                """INSERT INTO trades
                   (signal_id, symbol, exchange, direction, trading_mode,
                    status, quantity, remaining_quantity, entry_price, entry_time,
                    initial_stop_loss, stop_loss, target, initial_target,
                    fees, slippage, risk_amount, capital_utilized, leverage,
                    notes, source, trailing_mode, exit_description)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trade_data["signal_id"],
                    trade_data["symbol"],
                    trade_data["exchange"],
                    trade_data["direction"],
                    trade_data["trading_mode"],
                    trade_data["status"],
                    trade_data["quantity"],
                    trade_data["remaining_quantity"],
                    trade_data["entry_price"],
                    trade_data["entry_time"],
                    trade_data["initial_stop_loss"],
                    trade_data["stop_loss"],
                    trade_data["target"],
                    trade_data["initial_target"],
                    trade_data["fees"],
                    trade_data["slippage"],
                    trade_data["risk_amount"],
                    trade_data["capital_utilized"],
                    trade_data["leverage"],
                    trade_data["notes"],
                    trade_data["source"],
                    trade_data["trailing_mode"],
                    trade_data["exit_description"],
                ),
            )
            trade_data["id"] = cursor.lastrowid

        logger.info(
            "PAPER TRADE OPENED: %s %s %s @ %.2f | SL=%.2f | TP=%.2f | Qty=%.4f | "
            "Capital=%.2f INR | Risk=%.2f INR | Leverage=%.2fx",
            trade_data["direction"].upper(),
            trade_data["symbol"],
            trade_data["exchange"],
            trade_data["entry_price"],
            trade_data["stop_loss"],
            trade_data["target"],
            trade_data["quantity"],
            trade_data["capital_utilized"],
            trade_data["risk_amount"],
            trade_data["leverage"],
        )

        return trade_data

    # ----- Position monitoring -----

    def update_positions(self, prices: dict[str, float]) -> list[dict]:
        """
        Check all open positions against current prices.

        For each open position:
        1. Updates trailing stop via AdvancedExitManager (ATR-based by default).
        2. Persists any stop-loss changes as trade_events.
        3. Closes positions that hit stop-loss, target, or expiry.

        Args:
            prices: Dict mapping 'symbol/exchange' or 'symbol' -> current_price

        Returns:
            List of closed trade records.
        """
        from algo_monitor.strategy.exits import AdvancedExitManager, PositionExitState
        from algo_monitor.strategy.levels import calculate_atr

        closed = []
        open_positions = self.get_open_positions()
        now = datetime.now(timezone.utc)

        # Get exit config for trailing stop mode
        exit_cfg = getattr(self, "exit_config", None)
        if exit_cfg is not None:
            exit_mgr = AdvancedExitManager(exit_cfg)
        else:
            exit_mgr = None

        for pos in open_positions:
            symbol = pos["symbol"]
            is_option = "-CE" in symbol or "-PE" in symbol

            if is_option:
                underlying = symbol.split("-")[0]
                underlying_price = prices.get(underlying) or prices.get(f"{underlying}/{pos['exchange']}")
                key = f"{symbol}/{pos['exchange']}"
                option_price = prices.get(key) or prices.get(symbol)

                if option_price is None and underlying_price is not None and underlying_price > 0:
                    option_price = self.options_engine.mark_to_market(
                        contract_symbol=symbol,
                        current_spot=underlying_price,
                        entry_spot=underlying_price,
                        entry_premium=pos["entry_price"],
                    )
                price = option_price
            else:
                key = f"{pos['symbol']}/{pos['exchange']}"
                price = prices.get(key) or prices.get(pos["symbol"])

            if price is None or price <= 0:
                continue

            exit_reason = None
            exit_price = None

            direction = pos["direction"]
            sl = float(pos["stop_loss"])
            tp = float(pos["target"])
            entry = float(pos["entry_price"])
            qty = float(pos["quantity"])
            remaining_qty = float(pos.get("remaining_quantity") or qty)
            trade_id = pos["id"]

            # ---- Trailing stop update (ATR / swing) ----
            if exit_mgr is not None and not is_option:
                # Restore persisted peak excursion (survives restart)
                stored_peak = pos.get("highest_favorable_price")
                if stored_peak is not None and float(stored_peak) > 0:
                    peak = float(stored_peak)
                else:
                    # First tick after trade open or missing column
                    peak = price if direction == "long" else min(price, entry)

                # Reconstruct PositionExitState from DB record
                exit_state = PositionExitState(
                    trade_id=trade_id,
                    symbol=symbol,
                    direction=direction,
                    entry_price=entry,
                    initial_sl=float(pos.get("initial_stop_loss") or sl),
                    initial_tp=tp,
                    initial_qty=qty,
                    current_sl=sl,
                    remaining_qty=remaining_qty,
                    highest_favorable_price=peak,
                    partial_taken=bool(pos.get("partial_taken", 0)),
                )

                # Build a synthetic candle representing the latest tick
                from algo_monitor.data.models import Candle
                tick_candle = Candle(
                    symbol=symbol,
                    exchange=pos["exchange"],
                    interval="tick",
                    timestamp=now,
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume=0,
                    is_complete=False,
                )

                exit_result = exit_mgr.evaluate_bar(
                    state=exit_state,
                    candle=tick_candle,
                    atr_val=None,  # Will be computed from recent candles if needed
                )

                # Update trailing stop if it ratcheted
                if exit_result.new_sl is not None:
                    new_sl = round(exit_result.new_sl, 4)
                    if new_sl != sl:
                        self.db.execute(
                            "UPDATE trades SET stop_loss = ? WHERE id = ?",
                            (new_sl, trade_id),
                        )
                        self.db._get_connection().commit()
                        is_be_event = bool(exit_result.notes and "breakeven" in exit_result.notes.lower())
                        event_type = "breakeven_update" if is_be_event else "trailing_update"
                        event_reason = exit_result.notes or f"Trailing stop ratcheted at price {price:.4f}"
                        self._log_trade_event(
                            trade_id=trade_id,
                            event_type=event_type,
                            prev_stop=sl,
                            new_stop=new_sl,
                            reason=event_reason,
                        )
                        sl = new_sl  # Use updated stop for exit check below
                        logger.debug(
                            "Stop updated (%s): %s trade %d SL %.4f -> %.4f",
                            event_type, symbol, trade_id, pos["stop_loss"], sl,
                        )

                # Persist the updated peak excursion so restarts can restore it
                new_peak = exit_state.highest_favorable_price
                if stored_peak is None or abs(new_peak - float(stored_peak or 0)) > 0.0001:
                    self.db.execute(
                        "UPDATE trades SET highest_favorable_price = ? WHERE id = ?",
                        (new_peak, trade_id),
                    )
                    self.db._get_connection().commit()

                # Handle partial exit if triggered
                if exit_result.partial_filled and not bool(pos.get("partial_taken", 0)):
                    partial_qty = exit_result.partial_qty
                    partial_price = exit_result.partial_exit_price or price
                    is_usd = "USD" in symbol or symbol.endswith("USD")
                    usd_rate = getattr(self.config, "usd_inr_rate", 85.0)
                    fx_rate = usd_rate if is_usd else 1.0
                    if direction == "long":
                        partial_gross = (partial_price - entry) * partial_qty * fx_rate
                    else:
                        partial_gross = (entry - partial_price) * partial_qty * fx_rate

                    # Estimate costs for partial close
                    partial_notional = partial_qty * partial_price * fx_rate
                    partial_fees = partial_notional * self.config.fee_rate
                    partial_slippage = partial_notional * self.config.slippage_rate
                    partial_net = partial_gross - partial_fees - partial_slippage

                    self.balance += partial_net
                    new_remaining = max(0.0, remaining_qty - partial_qty)
                    new_sl_be = exit_result.new_sl if exit_result.new_sl is not None else sl

                    self.db.execute(
                        """UPDATE trades SET partial_taken = 1,
                               realized_partial_pnl = realized_partial_pnl + ?,
                               remaining_quantity = ?,
                               stop_loss = ?
                           WHERE id = ?""",
                        (partial_net, new_remaining, new_sl_be, trade_id),
                    )
                    self.db._get_connection().commit()

                    self._log_trade_event(
                        trade_id=trade_id,
                        event_type="partial_exit",
                        prev_stop=sl,
                        new_stop=new_sl_be,
                        quantity_closed=partial_qty,
                        fill_price=partial_price,
                        gross_pnl=partial_gross,
                        fees=partial_fees + partial_slippage,
                        net_pnl=partial_net,
                        reason=f"Partial profit: closed {exit_result.partial_qty:.4f} units @ {partial_price:.4f}; SL moved to breakeven",
                    )
                    logger.info(
                        "PARTIAL EXIT: %s trade %d: %.4f units @ %.4f | Net PnL=%.2f INR",
                        symbol, trade_id, partial_qty, partial_price, partial_net,
                    )

                # If exit manager closed the position (SL or TP from trailing state)
                if exit_result.is_closed:
                    exit_reason = exit_result.exit_reason or "trailing_stop"
                    exit_price = exit_result.exit_price or price

            else:
                # Standard fixed SL/TP check (non-trailing, options, no exit manager)
                # Check stop-loss
                if direction == "long" and price <= sl:
                    exit_reason = "stop_loss"
                    exit_price = sl
                elif direction == "short" and price >= sl:
                    exit_reason = "stop_loss"
                    exit_price = sl

                # Check target
                if not exit_reason:
                    if direction == "long" and price >= tp:
                        exit_reason = "target_hit"
                        exit_price = tp
                    elif direction == "short" and price <= tp:
                        exit_reason = "target_hit"
                        exit_price = tp

            # Standard SL/TP check for non-trailing path (already set above)
            if exit_mgr is not None and not is_option and not exit_reason:
                # Also do standard SL/TP checks after trailing update
                if direction == "long" and price <= sl:
                    exit_reason = "stop_loss"
                    exit_price = sl
                elif direction == "short" and price >= sl:
                    exit_reason = "stop_loss"
                    exit_price = sl

                if not exit_reason:
                    if direction == "long" and price >= tp:
                        exit_reason = "target_hit"
                        exit_price = tp
                    elif direction == "short" and price <= tp:
                        exit_reason = "target_hit"
                        exit_price = tp

            # If closed due to hitting stop, differentiate between:
            # - Initial Stop Loss (technical invalidation, negative P&L)
            # - Breakeven Protection (price peaked favorably and reversed, protected capital)
            # - Trailing Stop (stop ratcheted into profit, locked in gain)
            if exit_reason == "stop_loss":
                initial_sl = float(pos.get("initial_stop_loss") or sl)
                if direction == "long":
                    if sl > entry * 1.001:
                        exit_reason = "trailing_stop"
                    elif sl >= entry * 0.9995:
                        exit_reason = "breakeven_exit"
                    else:
                        exit_reason = "stop_loss"
                else:
                    if sl < entry * 0.999:
                        exit_reason = "trailing_stop"
                    elif sl <= entry * 1.0005:
                        exit_reason = "breakeven_exit"
                    else:
                        exit_reason = "stop_loss"

            # Check expiry
            if not exit_reason:
                entry_time = datetime.fromisoformat(pos["entry_time"])

                if pos["trading_mode"] == "intraday":
                    expiry_minutes = self.config.intraday_expiry_minutes
                    if expiry_minutes > 0:
                        expiry = entry_time + timedelta(minutes=expiry_minutes)
                        if now >= expiry:
                            exit_reason = "intraday_expiry"
                            exit_price = price

                elif pos["trading_mode"] == "swing":
                    max_days = self.config.swing_max_days
                    if max_days > 0:
                        expiry = entry_time + timedelta(days=max_days)
                        if now >= expiry:
                            exit_reason = "swing_expiry"
                            exit_price = price

            if exit_reason and exit_price:
                peak_val = float(pos.get("highest_favorable_price") or (new_peak if 'new_peak' in locals() else price))
                closed_trade = self._close_trade(
                    pos, exit_price, exit_reason, now, peak_price=peak_val
                )
                closed.append(closed_trade)

        return closed

    def _log_trade_event(
        self,
        trade_id: int,
        event_type: str,
        prev_stop: float | None = None,
        new_stop: float | None = None,
        prev_target: float | None = None,
        new_target: float | None = None,
        quantity_closed: float = 0,
        fill_price: float | None = None,
        gross_pnl: float = 0,
        fees: float = 0,
        net_pnl: float = 0,
        reason: str = "",
    ) -> None:
        """Persist a trade lifecycle event to the trade_events table."""
        try:
            self.db.execute(
                """INSERT INTO trade_events
                   (trade_id, event_time, event_type, prev_stop, new_stop,
                    prev_target, new_target, quantity_closed, fill_price,
                    gross_pnl, fees, net_pnl, reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trade_id,
                    datetime.now(timezone.utc).isoformat(),
                    event_type,
                    prev_stop,
                    new_stop,
                    prev_target,
                    new_target,
                    quantity_closed,
                    fill_price,
                    gross_pnl,
                    fees,
                    net_pnl,
                    reason,
                ),
            )
            self.db._get_connection().commit()
        except Exception as exc:
            logger.warning("Failed to log trade event for trade %d: %s", trade_id, exc)

    def _build_exit_description(
        self,
        position: dict,
        exit_price: float,
        exit_reason: str,
        net_pnl: float,
        peak_price: float | None = None,
    ) -> str:
        """
        Generate a concise, human-readable description explaining why the position was closed.
        Covers: breakeven reversals, trailing stops, full targets, initial stop losses, and session expiries.
        """
        entry = float(position["entry_price"])
        initial_sl = float(position.get("initial_stop_loss") or position["stop_loss"])
        direction = position.get("direction", "long").lower()
        risk = abs(entry - initial_sl)
        is_usd = "USD" in position.get("symbol", "") or position.get("symbol", "").endswith("USD")
        currency = "USD" if is_usd else "INR"
        pnl_str = f"{net_pnl:+.2f} {currency}"

        # Calculate R-multiples
        if direction == "long":
            r_exit = (exit_price - entry) / risk if risk > 0 else 0.0
            peak = peak_price if (peak_price is not None and peak_price > 0) else exit_price
            peak_r = (peak - entry) / risk if risk > 0 else r_exit
        else:
            r_exit = (entry - exit_price) / risk if risk > 0 else 0.0
            peak = peak_price if (peak_price is not None and peak_price > 0) else exit_price
            peak_r = (entry - peak) / risk if risk > 0 else r_exit

        if exit_reason in ("breakeven_exit", "breakeven_reversal"):
            return (
                f"Breakeven Protection: Trade peaked at {peak:.2f} (+{peak_r:.2f}R) and reversed. "
                f"Closed at {exit_price:.2f} to protect capital and prevent a winning trade from becoming a loss ({pnl_str})."
            )
        elif exit_reason == "trailing_stop":
            return (
                f"Trailing Stop Hit: Reversal from peak of {peak:.2f} (+{peak_r:.2f}R). "
                f"Trailing stop triggered at {exit_price:.2f}, locking in profit ({pnl_str}, {r_exit:+.2f}R)."
            )
        elif exit_reason == "target_hit":
            return (
                f"Target Reached: Price hit take-profit goal at {exit_price:.2f} (+{r_exit:.2f}R). "
                f"Full position liquidated for profit ({pnl_str})."
            )
        elif exit_reason == "stop_loss":
            return (
                f"Stop Loss Hit: Technical invalidation level touched at {exit_price:.2f} (-{abs(r_exit):.2f}R). "
                f"Position closed to preserve risk budget ({pnl_str})."
            )
        elif exit_reason == "intraday_expiry":
            expiry_m = getattr(self.config, "intraday_expiry_minutes", 375)
            return (
                f"Intraday Expiry: Session time limit ({expiry_m}m) reached. "
                f"Auto-squared off at market price {exit_price:.2f} ({pnl_str}, {r_exit:+.2f}R)."
            )
        elif exit_reason == "swing_expiry":
            days = getattr(self.config, "swing_max_days", 14)
            return (
                f"Swing Expiry: Maximum swing duration ({days} days) reached. "
                f"Closed at market price {exit_price:.2f} ({pnl_str}, {r_exit:+.2f}R)."
            )
        elif exit_reason == "partial_exit":
            return (
                f"Partial Profit: First target reached at {exit_price:.2f} (+{r_exit:.2f}R). "
                f"Booked 50% and moved runner stop to breakeven ({pnl_str})."
            )
        else:
            clean_reason = exit_reason.replace("_", " ").title()
            return f"{clean_reason}: Position closed at {exit_price:.2f} ({pnl_str}, {r_exit:+.2f}R)."

    def _close_trade(
        self,
        position: dict,
        exit_price: float,
        reason: str,
        exit_time: datetime,
        peak_price: float | None = None,
        description: str = "",
    ) -> dict:
        """Close a paper trade and update balance."""
        qty = float(position.get("remaining_quantity") or position["quantity"])
        entry = position["entry_price"]
        direction = position["direction"]
        fees = position.get("fees", 0) or 0
        slippage = position.get("slippage", 0) or 0

        is_usd = "USD" in position.get("symbol", "") or position.get("symbol", "").endswith("USD")
        usd_rate = getattr(self.config, "usd_inr_rate", 85.0)
        fx_rate = usd_rate if is_usd else 1.0

        if direction == "long":
            gross_pnl = (exit_price - entry) * qty * fx_rate
        else:
            gross_pnl = (entry - exit_price) * qty * fx_rate

        # Add back any previously realized partial P&L
        realized_partial = float(position.get("realized_partial_pnl") or 0)
        total_gross = gross_pnl + realized_partial
        net_pnl = gross_pnl - fees - slippage + realized_partial

        # Update balance
        self.balance += net_pnl

        # Generate human-readable exit description
        peak = peak_price if (peak_price is not None and peak_price > 0) else float(position.get("highest_favorable_price") or exit_price)
        exit_desc = description or self._build_exit_description(
            position, exit_price, reason, net_pnl, peak_price=peak
        )

        # Update database
        with self.db.transaction() as conn:
            conn.execute(
                """UPDATE trades SET
                       status = 'closed',
                       exit_price = ?,
                       exit_time = ?,
                       exit_reason = ?,
                       exit_description = ?,
                       gross_pnl = ?,
                       net_pnl = ?
                   WHERE id = ?""",
                (
                    exit_price,
                    exit_time.isoformat(),
                    reason,
                    exit_desc,
                    total_gross,
                    net_pnl,
                    position["id"],
                ),
            )

        # Log full_exit trade_event
        self._log_trade_event(
            trade_id=position["id"],
            event_type="full_exit",
            quantity_closed=qty,
            fill_price=exit_price,
            gross_pnl=gross_pnl,
            fees=fees + slippage,
            net_pnl=net_pnl,
            reason=reason,
        )

        # Update daily P&L
        date_str = exit_time.strftime("%Y-%m-%d")
        self.db.execute(
            """INSERT INTO daily_pnl (date, realised_pnl, total_fees, trade_count)
               VALUES (?, ?, ?, 1)
               ON CONFLICT(date) DO UPDATE SET
                   realised_pnl = realised_pnl + excluded.realised_pnl,
                   total_fees = total_fees + excluded.total_fees,
                   trade_count = trade_count + 1""",
            (date_str, net_pnl, fees),
        )
        self.db._get_connection().commit()

        logger.info(
            "PAPER TRADE CLOSED: %s %s | Entry=%.2f | Exit=%.2f | "
            "PnL=%.2f | Reason=%s | Desc=%s",
            direction.upper(),
            position["symbol"],
            entry,
            exit_price,
            net_pnl,
            reason,
            exit_desc,
        )

        position.update({
            "status": "closed",
            "exit_price": exit_price,
            "exit_time": exit_time.isoformat(),
            "exit_reason": reason,
            "exit_description": exit_desc,
            "gross_pnl": total_gross,
            "net_pnl": net_pnl,
        })
        return position

    def force_close_all(self, prices: dict[str, float], reason: str = "manual") -> list[dict]:
        """Force-close all open positions at current prices."""
        closed = []
        now = datetime.now(timezone.utc)
        for pos in self.get_open_positions():
            key = f"{pos['symbol']}/{pos['exchange']}"
            price = prices.get(key) or prices.get(pos["symbol"])
            if price and price > 0:
                closed.append(self._close_trade(pos, price, reason, now))
        return closed
