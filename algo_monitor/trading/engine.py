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
    ):
        self.config = risk_config
        self.db = db
        self.options_config = options_config
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

        # Get today's realised P&L for circuit breaker
        daily = self.get_daily_pnl()
        daily_pnl = daily.get("realised_pnl", 0)

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

        trade_data = {
            "signal_id": None,  # Will be set if signal is persisted
            "symbol": signal.symbol,
            "exchange": signal.exchange,
            "direction": signal.direction.value,
            "trading_mode": mode,
            "status": "open",
            "quantity": decision.quantity,
            "entry_price": signal.entry_ref,
            "entry_time": now,
            "stop_loss": signal.stop_loss,
            "target": signal.target,
            "exit_price": None,
            "exit_time": None,
            "exit_reason": None,
            "gross_pnl": 0,
            "fees": decision.estimated_fees,
            "slippage": decision.estimated_slippage,
            "net_pnl": 0,
            "risk_amount": decision.risk_amount,
            "notes": signal.reason[:500] if signal.reason else "",
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
            "PAPER TRADE OPENED: %s %s %s @ %.2f | SL=%.2f | TP=%.2f | Qty=%.4f",
            trade_data["direction"].upper(),
            trade_data["symbol"],
            trade_data["exchange"],
            trade_data["entry_price"],
            trade_data["stop_loss"],
            trade_data["target"],
            trade_data["quantity"],
        )

        return trade_data

    # ----- Position monitoring -----

    def update_positions(self, prices: dict[str, float]) -> list[dict]:
        """
        Check all open positions against current prices.
        Closes positions that hit stop-loss, target, or expiry.

        Args:
            prices: Dict mapping 'symbol/exchange' -> current_price

        Returns:
            List of closed trade records.
        """
        closed = []
        open_positions = self.get_open_positions()
        now = datetime.now(timezone.utc)

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
            sl = pos["stop_loss"]
            tp = pos["target"]

            # Check stop-loss
            if direction == "long" and price <= sl:
                exit_reason = "stop_loss"
                exit_price = sl  # Assume fill at SL (optimistic for paper)
            elif direction == "short" and price >= sl:
                exit_reason = "stop_loss"
                exit_price = sl

            # Check target
            if direction == "long" and price >= tp:
                exit_reason = "target_hit"
                exit_price = tp
            elif direction == "short" and price <= tp:
                exit_reason = "target_hit"
                exit_price = tp

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
                closed_trade = self._close_trade(
                    pos, exit_price, exit_reason, now
                )
                closed.append(closed_trade)

        return closed

    def _close_trade(
        self,
        position: dict,
        exit_price: float,
        reason: str,
        exit_time: datetime,
    ) -> dict:
        """Close a paper trade and update balance."""
        qty = position["quantity"]
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

        net_pnl = gross_pnl - fees - slippage

        # Update balance
        self.balance += net_pnl

        # Update database
        with self.db.transaction() as conn:
            conn.execute(
                """UPDATE trades SET
                       status = 'closed',
                       exit_price = ?,
                       exit_time = ?,
                       exit_reason = ?,
                       gross_pnl = ?,
                       net_pnl = ?
                   WHERE id = ?""",
                (
                    exit_price,
                    exit_time.isoformat(),
                    reason,
                    gross_pnl,
                    net_pnl,
                    position["id"],
                ),
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
            "PnL=%.2f | Reason=%s",
            direction.upper(),
            position["symbol"],
            entry,
            exit_price,
            net_pnl,
            reason,
        )

        position.update({
            "status": "closed",
            "exit_price": exit_price,
            "exit_time": exit_time.isoformat(),
            "exit_reason": reason,
            "gross_pnl": gross_pnl,
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
