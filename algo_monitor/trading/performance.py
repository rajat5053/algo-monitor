"""
Performance reporting for paper trades.

Calculates key metrics: net return, win rate, profit factor,
maximum drawdown, Sharpe-like ratio, average win/loss, and more.
Separates intraday vs swing and backtested vs live results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from algo_monitor.utils.logging import get_logger

if TYPE_CHECKING:
    from algo_monitor.database import Database

logger = get_logger("trading.performance")


@dataclass
class PerformanceReport:
    """Comprehensive performance metrics for paper trades."""

    # Identification
    report_type: str = "all"        # 'all', 'intraday', 'swing'
    source: str = "paper"           # 'paper' or 'backtest'
    period_start: str = ""
    period_end: str = ""

    # Core metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0

    # P&L
    gross_profit: float = 0
    gross_loss: float = 0
    total_fees: float = 0
    net_pnl: float = 0

    # Rates
    win_rate: float = 0
    profit_factor: float = 0      # gross_profit / abs(gross_loss)
    avg_win: float = 0
    avg_loss: float = 0
    avg_rr_achieved: float = 0    # Average reward-to-risk on winners

    # Risk metrics
    max_drawdown: float = 0
    max_drawdown_pct: float = 0
    max_consecutive_losses: int = 0
    largest_win: float = 0
    largest_loss: float = 0

    # Balance
    starting_balance: float = 0
    ending_balance: float = 0
    net_return_pct: float = 0

    # Breakdown
    by_setup: dict = field(default_factory=dict)
    by_symbol: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "report_type": self.report_type,
            "source": self.source,
            "period": f"{self.period_start} to {self.period_end}",
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": f"{self.win_rate:.1f}%",
            "net_pnl": f"{self.net_pnl:.2f}",
            "gross_profit": f"{self.gross_profit:.2f}",
            "gross_loss": f"{self.gross_loss:.2f}",
            "total_fees": f"{self.total_fees:.2f}",
            "profit_factor": f"{self.profit_factor:.2f}",
            "avg_win": f"{self.avg_win:.2f}",
            "avg_loss": f"{self.avg_loss:.2f}",
            "max_drawdown": f"{self.max_drawdown:.2f}",
            "max_drawdown_pct": f"{self.max_drawdown_pct:.1f}%",
            "max_consecutive_losses": self.max_consecutive_losses,
            "largest_win": f"{self.largest_win:.2f}",
            "largest_loss": f"{self.largest_loss:.2f}",
            "net_return_pct": f"{self.net_return_pct:.2f}%",
        }


class PerformanceAnalyser:
    """Generates performance reports from trade history."""

    def __init__(self, db: Database):
        self.db = db

    def generate_report(
        self,
        trading_mode: str = "all",
        source: str = "paper",
        start_date: str = "",
        end_date: str = "",
        starting_balance: float = 0,
    ) -> PerformanceReport:
        """
        Generate a performance report from closed trades.

        Args:
            trading_mode: 'all', 'intraday', or 'swing'
            source: 'paper' or 'backtest'
            start_date: Filter by exit date (YYYY-MM-DD)
            end_date: Filter by exit date (YYYY-MM-DD)
            starting_balance: Initial account balance (0 = auto-read from settings)
        """
        # Resolve starting balance from settings if not explicitly passed
        if starting_balance <= 0:
            try:
                from algo_monitor.config.settings import get_settings
                starting_balance = get_settings().risk.starting_balance
            except Exception:
                starting_balance = 20_000  # Spec baseline

        sql = "SELECT * FROM trades WHERE status = 'closed'"

        params: list = []

        if trading_mode != "all":
            sql += " AND trading_mode = ?"
            params.append(trading_mode)

        if source:
            sql += " AND source = ?"
            params.append(source)

        if start_date:
            sql += " AND exit_time >= ?"
            params.append(start_date)

        if end_date:
            sql += " AND exit_time <= ?"
            params.append(end_date + "T23:59:59")

        sql += " ORDER BY exit_time ASC"
        rows = self.db.fetchall(sql, tuple(params))
        trades = [dict(r) for r in rows]

        report = PerformanceReport(
            report_type=trading_mode,
            source=source,
            starting_balance=starting_balance,
        )

        if not trades:
            report.ending_balance = starting_balance
            return report

        report.period_start = trades[0].get("entry_time", "")[:10]
        report.period_end = trades[-1].get("exit_time", "")[:10]
        report.total_trades = len(trades)

        # Classify trades
        pnl_list = []
        consecutive_losses = 0
        max_consec = 0

        setup_stats: dict[str, dict] = {}
        symbol_stats: dict[str, dict] = {}

        for trade in trades:
            net = trade.get("net_pnl", 0) or 0
            pnl_list.append(net)
            fees = trade.get("fees", 0) or 0
            report.total_fees += fees

            if net > 0:
                report.winning_trades += 1
                report.gross_profit += net
                report.largest_win = max(report.largest_win, net)
                consecutive_losses = 0
            elif net < 0:
                report.losing_trades += 1
                report.gross_loss += net
                report.largest_loss = min(report.largest_loss, net)
                consecutive_losses += 1
                max_consec = max(max_consec, consecutive_losses)
            else:
                report.breakeven_trades += 1
                consecutive_losses = 0

            # By-setup breakdown
            # (setup info would come from the signal, stored in notes)
            symbol = trade.get("symbol", "unknown")
            if symbol not in symbol_stats:
                symbol_stats[symbol] = {"trades": 0, "pnl": 0}
            symbol_stats[symbol]["trades"] += 1
            symbol_stats[symbol]["pnl"] += net

        report.max_consecutive_losses = max_consec
        report.net_pnl = sum(pnl_list)

        if report.winning_trades > 0:
            report.avg_win = report.gross_profit / report.winning_trades

        if report.losing_trades > 0:
            report.avg_loss = report.gross_loss / report.losing_trades

        if report.total_trades > 0:
            report.win_rate = (report.winning_trades / report.total_trades) * 100

        if report.gross_loss != 0:
            report.profit_factor = abs(report.gross_profit / report.gross_loss)

        # Drawdown calculation
        equity_curve = [starting_balance]
        for pnl in pnl_list:
            equity_curve.append(equity_curve[-1] + pnl)

        peak = starting_balance
        max_dd = 0
        max_dd_pct = 0
        for equity in equity_curve:
            if equity > peak:
                peak = equity
            dd = peak - equity
            dd_pct = (dd / peak * 100) if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
                max_dd_pct = dd_pct

        report.max_drawdown = max_dd
        report.max_drawdown_pct = max_dd_pct
        report.ending_balance = equity_curve[-1]
        report.net_return_pct = (
            (report.ending_balance - starting_balance) / starting_balance * 100
            if starting_balance > 0
            else 0
        )

        report.by_symbol = symbol_stats

        return report


def compare_strategies(
    baseline: Any,
    variants: dict[str, Any],
) -> dict:
    """
    Compare modular strategy variants against the core S/R baseline.

    Args:
        baseline: PerformanceReport or BacktestResult for core S/R baseline.
        variants: Dict mapping variant_name -> PerformanceReport or BacktestResult.

    Returns:
        Structured dictionary comparing trades, win rate, profit factor, net P&L,
        max drawdown, and delta metrics relative to the baseline.
    """
    def _extract_metrics(obj: Any) -> dict:
        total = getattr(obj, "total_trades", 0)
        win_rate = getattr(obj, "win_rate", 0.0)
        pf = getattr(obj, "profit_factor", 0.0)
        net_pnl = getattr(obj, "net_pnl", 0.0)
        max_dd = getattr(obj, "max_drawdown", 0.0)
        return {
            "total_trades": total,
            "win_rate": round(win_rate, 2),
            "profit_factor": round(pf, 2),
            "net_pnl": round(net_pnl, 2),
            "max_drawdown": round(max_dd, 2),
        }

    base_metrics = _extract_metrics(baseline)
    comparison = {
        "baseline": base_metrics,
        "variants": {},
    }

    for name, var_obj in variants.items():
        var_metrics = _extract_metrics(var_obj)
        var_metrics["delta_pnl"] = round(var_metrics["net_pnl"] - base_metrics["net_pnl"], 2)
        var_metrics["delta_win_rate"] = round(var_metrics["win_rate"] - base_metrics["win_rate"], 2)
        var_metrics["delta_profit_factor"] = round(var_metrics["profit_factor"] - base_metrics["profit_factor"], 2)
        comparison["variants"][name] = var_metrics

    return comparison
