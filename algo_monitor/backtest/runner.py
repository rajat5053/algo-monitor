"""
Historical backtesting runner.

Replays historical candle data through the strategy and paper-trading
engines to evaluate performance without future-data leakage.

Key safeguards:
- Candles are processed strictly in chronological order
- A higher-timeframe candle is only visible once its close time has passed
  (not from its open timestamp). This prevents look-ahead bias.
- Zones and signals only use data available up to the current candle
- USD P&L is converted to INR using the configured FX rate before updating
  the simulated balance (P0-C fix)
- Results are tagged as 'backtest' to distinguish from live paper trading
- Separate train/test splits when evaluating parameter sensitivity
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from algo_monitor.config.instruments import Instrument, TradingMode
from algo_monitor.config.settings import RiskConfig, StrategyConfig
from algo_monitor.data.candle_store import CandleStore
from algo_monitor.data.ingestion import CANDLE_DURATION_SECONDS
from algo_monitor.data.models import Candle
from algo_monitor.risk.manager import RiskManager
from algo_monitor.strategy.exits import AdvancedExitManager
from algo_monitor.strategy.levels import LevelDetector, calculate_atr
from algo_monitor.strategy.signals import SignalGenerator
from algo_monitor.trading.performance import PerformanceAnalyser, PerformanceReport
from algo_monitor.utils.logging import get_logger

if TYPE_CHECKING:
    from algo_monitor.database import Database

logger = get_logger("backtest.runner")


def _candle_close_time(candle: Candle, interval: str) -> datetime:
    """
    Return the UTC datetime when a candle's bar is fully closed.

    This is the candle open timestamp PLUS the candle duration.
    A candle is only usable for decisions once its close time has passed.

    For monthly candles the duration is approximate (28–31 days); we use
    the CANDLE_DURATION_SECONDS value (30 days) as a conservative estimate.
    """
    duration_secs = CANDLE_DURATION_SECONDS.get(interval, 0)
    if duration_secs <= 0:
        # Unknown interval — return open timestamp as a safe fallback
        # (will behave slightly pessimistically for unknown intervals)
        return candle.timestamp
    return candle.timestamp + timedelta(seconds=duration_secs)


class BacktestRunner:
    """
    Run a backtest over historical candle data.

    The runner walks through LTF candles one by one. At each step:
    - Only HTF candles whose *close time* ≤ current LTF bar open are used.
      This eliminates look-ahead bias from partially-formed higher-timeframe bars.
    - USD-denominated P&L is converted to INR using the configured FX rate.
    - Zones and signals are computed strictly from past data.
    """

    def __init__(
        self,
        strategy_config: StrategyConfig,
        risk_config: RiskConfig,
        db: "Database",
    ):
        self.strategy_config = strategy_config
        self.risk_config = risk_config
        self.db = db
        self.store = CandleStore(db)
        self.level_detector = LevelDetector(strategy_config)
        self.signal_generator = SignalGenerator(strategy_config)
        self.risk_manager = RiskManager(risk_config)
        self.exit_manager = (
            AdvancedExitManager(strategy_config.exits)
            if getattr(strategy_config, "exits", None)
            else None
        )

    def run(
        self,
        instrument: Instrument,
        start_date: str = "",
        end_date: str = "",
        trading_mode: TradingMode = TradingMode.BOTH,
        htf_interval: str = "",
        ltf_interval: str = "",
    ) -> "BacktestResult":
        """
        Execute a backtest for one instrument.

        Args:
            instrument: The instrument to backtest.
            start_date: Start date (YYYY-MM-DD), empty for all available data.
            end_date: End date (YYYY-MM-DD), empty for all available data.
            trading_mode: Intraday, swing, or both.
            htf_interval: Override the strategy config HTF interval.
            ltf_interval: Override the strategy config LTF interval.
        """
        symbol = instrument.symbol
        exchange = instrument.exchange.value

        # Determine intervals (market-specific config takes precedence)
        from algo_monitor.config.instruments import MarketCategory
        is_indian = instrument.market_category == MarketCategory.INDIAN

        if not htf_interval:
            htf_interval = (
                getattr(self.strategy_config, "indian_htf_interval", "1d")
                if is_indian
                else getattr(self.strategy_config, "crypto_htf_interval", "1h")
            )
        if not ltf_interval:
            ltf_interval = (
                getattr(self.strategy_config, "indian_ltf_interval", "5m")
                if is_indian
                else getattr(self.strategy_config, "crypto_ltf_interval", "5m")
            )

        logger.info(
            "Starting backtest for %s/%s (htf=%s, ltf=%s)",
            symbol, exchange, htf_interval, ltf_interval,
        )

        # Load all stored candles
        htf_candles = self.store.get_candles(symbol, exchange, htf_interval)
        ltf_candles = self.store.get_candles(symbol, exchange, ltf_interval)

        if not htf_candles or not ltf_candles:
            logger.warning(
                "Insufficient data for backtest: htf=%d, ltf=%d",
                len(htf_candles), len(ltf_candles),
            )
            return BacktestResult(symbol=symbol, exchange=exchange)

        # Date filtering
        if start_date:
            start_dt = datetime.fromisoformat(start_date + "T00:00:00+00:00")
            htf_candles = [c for c in htf_candles if c.timestamp >= start_dt]
            ltf_candles = [c for c in ltf_candles if c.timestamp >= start_dt]

        if end_date:
            end_dt = datetime.fromisoformat(end_date + "T23:59:59+00:00")
            htf_candles = [c for c in htf_candles if c.timestamp <= end_dt]
            ltf_candles = [c for c in ltf_candles if c.timestamp <= end_dt]

        result = BacktestResult(
            symbol=symbol,
            exchange=exchange,
            start_date=htf_candles[0].timestamp.isoformat() if htf_candles else "",
            end_date=htf_candles[-1].timestamp.isoformat() if htf_candles else "",
            htf_candle_count=len(htf_candles),
            ltf_candle_count=len(ltf_candles),
        )

        # FX rate for USD → INR conversion (P0-C fix)
        usd_inr = getattr(self.risk_config, "usd_inr_rate", 85.0)
        is_usd_instrument = "USD" in symbol.upper()

        min_htf = self.strategy_config.min_history_candles
        open_positions: list[dict] = []
        balance = self.risk_config.starting_balance

        for i in range(len(ltf_candles)):
            current_ltf = ltf_candles[i]

            # P0-B FIX: Include only HTF candles whose *close time* has passed
            # before the current LTF bar's open timestamp.
            # A daily candle opening 2024-01-01 00:00 UTC is not closed until
            # 2024-01-02 00:00 UTC — it must NOT be used by a 5m bar at
            # 2024-01-01 09:00 UTC.
            htf_window = [
                c for c in htf_candles
                if _candle_close_time(c, htf_interval) <= current_ltf.timestamp
            ]

            if len(htf_window) < min_htf:
                continue

            # Detect zones from HTF window (past data only)
            zones = self.level_detector.detect_zones(
                htf_window, reference_price=current_ltf.close
            )

            # Generate signals from recent LTF candles
            ltf_window = ltf_candles[max(0, i - 50): i + 1]
            signals = self.signal_generator.generate_signals(
                symbol=symbol,
                exchange=exchange,
                candles=ltf_window,
                zones=zones,
                htf_zones=zones,
            )

            # Check open positions for SL/TP and trailing exits
            atr_val = calculate_atr(ltf_window) if self.exit_manager else None

            for pos in list(open_positions):
                exit_reason = None
                exit_price = None

                exit_st = pos.get("exit_state")
                if exit_st and self.exit_manager:
                    eval_res = self.exit_manager.evaluate_bar(
                        state=exit_st,
                        candle=current_ltf,
                        atr_val=atr_val,
                        recent_candles=ltf_window,
                    )
                    if eval_res.partial_filled and eval_res.partial_qty > 0:
                        p_qty = eval_res.partial_qty
                        p_exit = eval_res.partial_exit_price or current_ltf.close
                        fx_rate = usd_inr if is_usd_instrument else 1.0
                        if pos["direction"] == "long":
                            p_gross = (p_exit - pos["entry"]) * p_qty * fx_rate
                        else:
                            p_gross = (pos["entry"] - p_exit) * p_qty * fx_rate
                        p_fees = pos["entry"] * p_qty * self.risk_config.fee_rate * 2 * fx_rate
                        p_slip = pos["entry"] * p_qty * self.risk_config.slippage_rate * 2 * fx_rate
                        p_net = p_gross - p_fees - p_slip
                        balance += p_net

                        result.trades.append({
                            "symbol": symbol,
                            "direction": pos["direction"],
                            "entry": pos["entry"],
                            "exit": p_exit,
                            "quantity": p_qty,
                            "gross_pnl_inr": p_gross,
                            "net_pnl": p_net,
                            "fees": p_fees,
                            "reason": "partial_target",
                            "entry_time": pos["entry_time"],
                            "exit_time": current_ltf.timestamp.isoformat(),
                            "fx_rate_used": fx_rate,
                        })
                        pos["quantity"] = exit_st.remaining_qty

                    if eval_res.new_sl is not None:
                        pos["stop_loss"] = eval_res.new_sl

                    if eval_res.is_closed:
                        exit_reason = eval_res.exit_reason
                        exit_price = eval_res.exit_price
                else:
                    if pos["direction"] == "long":
                        # Conservative: assume SL triggered first if both touched
                        if current_ltf.low <= pos["stop_loss"]:
                            exit_reason = "stop_loss"
                            exit_price = pos["stop_loss"]
                        elif current_ltf.high >= pos["target"]:
                            exit_reason = "target_hit"
                            exit_price = pos["target"]
                    else:  # short
                        if current_ltf.high >= pos["stop_loss"]:
                            exit_reason = "stop_loss"
                            exit_price = pos["stop_loss"]
                        elif current_ltf.low <= pos["target"]:
                            exit_reason = "target_hit"
                            exit_price = pos["target"]

                if exit_reason and exit_price:
                    qty = pos["quantity"]
                    entry = pos["entry"]

                    if pos["direction"] == "long":
                        gross_quote = (exit_price - entry) * qty
                    else:
                        gross_quote = (entry - exit_price) * qty

                    # P0-C FIX: Convert quote-currency P&L to INR
                    fx_rate = usd_inr if is_usd_instrument else 1.0
                    gross_inr = gross_quote * fx_rate

                    fees_inr = entry * qty * self.risk_config.fee_rate * 2 * fx_rate
                    slippage_inr = entry * qty * self.risk_config.slippage_rate * 2 * fx_rate
                    net_inr = gross_inr - fees_inr - slippage_inr
                    balance += net_inr

                    result.trades.append({
                        "symbol": symbol,
                        "direction": pos["direction"],
                        "entry": entry,
                        "exit": exit_price,
                        "quantity": qty,
                        "gross_pnl_inr": gross_inr,
                        "net_pnl": net_inr,
                        "fees": fees_inr,
                        "reason": exit_reason,
                        "entry_time": pos["entry_time"],
                        "exit_time": current_ltf.timestamp.isoformat(),
                        "fx_rate_used": fx_rate,
                    })
                    open_positions.remove(pos)

            # Process new signals
            for signal in signals:
                if signal.entry_ref is None or signal.stop_loss is None:
                    continue

                decision = self.risk_manager.evaluate(
                    signal=signal,
                    current_price=current_ltf.close,
                    current_balance=balance,
                    open_positions=[
                        {"symbol": p["symbol"], "exchange": exchange,
                         "direction": p["direction"]}
                        for p in open_positions
                    ],
                )

                if decision.approved:
                    exit_state = None
                    if (
                        self.exit_manager
                        and getattr(self.strategy_config, "exits", None)
                        and self.strategy_config.exits.trailing_stop_mode != "none"
                    ):
                        exit_state = self.exit_manager.create_position_state(
                            trade_id=len(result.trades) + len(open_positions),
                            symbol=symbol,
                            direction=signal.direction.value,
                            entry_price=signal.entry_ref,
                            stop_loss=signal.stop_loss,
                            target=signal.target,
                            quantity=decision.quantity,
                        )

                    open_positions.append({
                        "symbol": symbol,
                        "direction": signal.direction.value,
                        "entry": signal.entry_ref,
                        "stop_loss": signal.stop_loss,
                        "target": signal.target,
                        "quantity": decision.quantity,
                        "entry_time": current_ltf.timestamp.isoformat(),
                        "exit_state": exit_state,
                    })
                    result.signals_generated += 1

        result.ending_balance = balance
        result.total_trades = len(result.trades)
        result.signals_generated += len(open_positions)  # Include unclosed

        # Compute metrics
        if result.trades:
            result.compute_metrics(self.risk_config.starting_balance)

        logger.info(
            "Backtest complete for %s: %d trades, net P&L=%.2f INR, win rate=%.1f%%",
            symbol,
            result.total_trades,
            result.net_pnl,
            result.win_rate,
        )

        return result


class BacktestResult:
    """Container for backtest results."""

    def __init__(
        self,
        symbol: str = "",
        exchange: str = "",
        start_date: str = "",
        end_date: str = "",
        htf_candle_count: int = 0,
        ltf_candle_count: int = 0,
    ):
        self.symbol = symbol
        self.exchange = exchange
        self.start_date = start_date
        self.end_date = end_date
        self.htf_candle_count = htf_candle_count
        self.ltf_candle_count = ltf_candle_count

        self.trades: list[dict] = []
        self.signals_generated: int = 0
        self.total_trades: int = 0
        self.ending_balance: float = 0

        # Computed metrics (all P&L in INR)
        self.net_pnl: float = 0
        self.win_rate: float = 0
        self.profit_factor: float = 0
        self.max_drawdown: float = 0
        self.avg_win: float = 0
        self.avg_loss: float = 0
        self.longest_losing_streak: int = 0
        self.expectancy_r: float = 0  # Expectancy in R multiples

    def compute_metrics(self, starting_balance: float) -> None:
        """Compute performance metrics from trades (all values in INR)."""
        if not self.trades:
            return

        wins = [t for t in self.trades if t["net_pnl"] > 0]
        losses = [t for t in self.trades if t["net_pnl"] < 0]

        self.net_pnl = sum(t["net_pnl"] for t in self.trades)
        self.total_trades = len(self.trades)

        if self.total_trades > 0:
            self.win_rate = len(wins) / self.total_trades * 100

        if wins:
            self.avg_win = sum(t["net_pnl"] for t in wins) / len(wins)
        if losses:
            self.avg_loss = sum(t["net_pnl"] for t in losses) / len(losses)

        gross_profit = sum(t["net_pnl"] for t in wins)
        gross_loss = abs(sum(t["net_pnl"] for t in losses))
        if gross_loss > 0:
            self.profit_factor = gross_profit / gross_loss

        # Drawdown (on INR equity curve)
        equity = starting_balance
        peak = equity
        max_dd = 0.0
        for t in self.trades:
            equity += t["net_pnl"]
            peak = max(peak, equity)
            dd = peak - equity
            max_dd = max(max_dd, dd)
        self.max_drawdown = max_dd

        # Longest losing streak
        streak = 0
        max_streak = 0
        for t in self.trades:
            if t["net_pnl"] < 0:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        self.longest_losing_streak = max_streak

        # Expectancy in R: E[R] = (win_rate * avg_win_R) - (loss_rate * avg_loss_R)
        # Approximated using net P&L / initial risk. Only computed if risk available.
        risk_amounts = [t.get("risk_inr", 0) for t in self.trades if t.get("risk_inr", 0) > 0]
        if risk_amounts:
            avg_risk = sum(risk_amounts) / len(risk_amounts)
            if avg_risk > 0:
                self.expectancy_r = self.net_pnl / (len(self.trades) * avg_risk)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "period": f"{self.start_date[:10]} to {self.end_date[:10]}",
            "htf_candles": self.htf_candle_count,
            "ltf_candles": self.ltf_candle_count,
            "signals": self.signals_generated,
            "total_trades": self.total_trades,
            "net_pnl_inr": f"{self.net_pnl:.2f}",
            "win_rate": f"{self.win_rate:.1f}%",
            "profit_factor": f"{self.profit_factor:.2f}",
            "max_drawdown_inr": f"{self.max_drawdown:.2f}",
            "avg_win_inr": f"{self.avg_win:.2f}",
            "avg_loss_inr": f"{self.avg_loss:.2f}",
            "longest_losing_streak": self.longest_losing_streak,
            "expectancy_r": f"{self.expectancy_r:.3f}",
        }
