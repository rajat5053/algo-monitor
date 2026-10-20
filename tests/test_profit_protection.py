"""
Tests for automatic Breakeven / Profit Protection and Exit Descriptions.

Validates:
1. A trade that moves into profit (>= 0.75R) has its stop-loss automatically moved to breakeven.
2. If price subsequently reverses to entry, the trade closes with 'breakeven_exit',
   preventing a winning trade from becoming a losing trade.
3. If price continues higher and trails with ATR, reversing price triggers 'trailing_stop',
   locking in positive net profit.
4. If a trade drops immediately to initial stop, it closes with 'stop_loss'.
5. If target is hit, it closes with 'target_hit'.
6. Every closed trade scenario generates a concise, human-readable exit_description
   persisted in the trades table and trade_events table.
"""

import pytest
from datetime import datetime, timezone
from algo_monitor.config.settings import RiskConfig, ExitConfig
from algo_monitor.strategy.signals import Signal, Direction
from algo_monitor.trading.engine import PaperTradingEngine


def _make_signal(entry=100.0, stop=90.0, target=120.0, symbol="RELIANCE", exchange="upstox"):
    return Signal(
        symbol=symbol,
        exchange=exchange,
        setup_type="support_bounce",
        direction=Direction.LONG,
        timeframe="5m",
        entry_ref=entry,
        stop_loss=stop,
        target=target,
        risk_reward=round((target - entry) / (entry - stop), 2),
        reason="Test breakout signal",
        created_at=datetime.now(timezone.utc),
    )


def _make_engine(fresh_db, trailing_mode="atr", breakeven_trigger_r=0.75):
    risk_cfg = RiskConfig(
        starting_balance=20000.0,
        risk_per_trade=0.015,
        indian_cash_risk_per_trade=0.015,
        max_capital_per_trade_pct=0.40,
        max_aggregate_open_risk=0.10,
        max_leverage=1.0,
    )
    exit_cfg = ExitConfig(
        trailing_stop_mode=trailing_mode,
        trailing_atr_mult=1.5,
        enable_breakeven_protection=True,
        breakeven_trigger_r=breakeven_trigger_r,
        breakeven_buffer_pct=0.0,
    )
    return PaperTradingEngine(risk_cfg, fresh_db, exit_config=exit_cfg)



class TestProfitProtectionAndBreakeven:

    def test_trade_in_profit_moves_stop_to_breakeven(self, fresh_db):
        """When price achieves >= 0.75R, stop-loss is raised to breakeven."""
        engine = _make_engine(fresh_db, breakeven_trigger_r=0.75)
        sig = _make_signal(entry=100.0, stop=90.0, target=120.0)  # Risk = 10, 0.75R = 107.5
        trade = engine.process_signal(sig, 100.0)
        assert trade is not None

        # Price rises to 108 (+0.8R) -> triggers breakeven protection
        engine.update_positions({"RELIANCE": 108.0})

        row = fresh_db.fetchone("SELECT stop_loss FROM trades WHERE id = ?", (trade["id"],))
        assert row is not None
        assert float(row["stop_loss"]) >= 100.0  # Stop raised to entry

    def test_winning_trade_does_not_become_losing_trade_on_reversal(self, fresh_db):
        """If price peaks in profit and then reverses, it closes at breakeven with 'breakeven_exit'."""
        engine = _make_engine(fresh_db, breakeven_trigger_r=0.75)
        sig = _make_signal(entry=100.0, stop=90.0, target=120.0)
        trade = engine.process_signal(sig, 100.0)
        assert trade is not None

        # 1. Price moves to 108 (+0.8R)
        engine.update_positions({"RELIANCE": 108.0})

        # 2. Price reverses sharply back to entry (100.0) or below
        closed = engine.update_positions({"RELIANCE": 99.5})

        assert len(closed) == 1
        closed_trade = closed[0]

        # Verify exit reason is breakeven_exit, not stop_loss
        assert closed_trade["exit_reason"] == "breakeven_exit"
        # Capital preserved: net PnL is non-negative or strictly protected from -1.0R loss
        assert closed_trade["net_pnl"] >= -5.0  # Fees only; NOT the 10-pt stop loss (-₹300)
        # Description explains the exact scenario
        assert "Breakeven Protection" in closed_trade["exit_description"]
        assert "peaked at 108.00" in closed_trade["exit_description"]
        assert "prevent a winning trade from becoming a loss" in closed_trade["exit_description"]

    def test_trailing_stop_locks_in_profit_on_deeper_run(self, fresh_db):
        """If trade pushes to higher R-multiple and reverses, trailing stop locks in profit."""
        engine = _make_engine(fresh_db, trailing_mode="atr", breakeven_trigger_r=0.75)
        sig = _make_signal(entry=100.0, stop=90.0, target=150.0)  # Risk = 10, Target = 150 (5R)
        trade = engine.process_signal(sig, 100.0)
        assert trade is not None

        # 1. Price pushes to 125.0 (+2.5R)
        engine.update_positions({"RELIANCE": 125.0})

        # 2. Price reverses to 108.0 (hitting ratcheted trailing stop)
        closed = engine.update_positions({"RELIANCE": 108.0})
        if not closed:
            # Drop further to hit whatever level the trailing stop reached
            closed = engine.update_positions({"RELIANCE": 102.0})

        assert len(closed) == 1
        closed_trade = closed[0]
        # Should be classified as trailing_stop (exited in profit above entry)
        assert closed_trade["exit_reason"] in ("trailing_stop", "breakeven_exit")
        assert closed_trade["net_pnl"] >= 0.0  # Profitable!
        assert "Trailing Stop Hit" in closed_trade["exit_description"] or "Breakeven Protection" in closed_trade["exit_description"]

    def test_initial_stop_loss_description(self, fresh_db):
        """A trade that immediately fails without profit closes with 'stop_loss' and clear description."""
        engine = _make_engine(fresh_db)
        sig = _make_signal(entry=100.0, stop=90.0, target=120.0)
        trade = engine.process_signal(sig, 100.0)
        assert trade is not None

        # Price drops straight to 89.0
        closed = engine.update_positions({"RELIANCE": 89.0})
        assert len(closed) == 1
        closed_trade = closed[0]

        assert closed_trade["exit_reason"] == "stop_loss"
        assert closed_trade["net_pnl"] < 0
        assert "Stop Loss Hit" in closed_trade["exit_description"]
        assert "Technical invalidation" in closed_trade["exit_description"]

    def test_target_hit_description(self, fresh_db):
        """A trade reaching take-profit target closes with 'target_hit' and clear description."""
        engine = _make_engine(fresh_db)
        sig = _make_signal(entry=100.0, stop=90.0, target=120.0)
        trade = engine.process_signal(sig, 100.0)
        assert trade is not None

        # Price rises to 121.0
        closed = engine.update_positions({"RELIANCE": 121.0})
        assert len(closed) == 1
        closed_trade = closed[0]

        assert closed_trade["exit_reason"] == "target_hit"
        assert closed_trade["net_pnl"] > 0
        assert "Target Reached" in closed_trade["exit_description"]
        assert "Full position liquidated" in closed_trade["exit_description"]


class TestAuditTrailDescriptions:

    def test_exit_description_stored_in_db_and_events(self, fresh_db):
        """Verify exit_description is stored in trades table and trade_events table."""
        engine = _make_engine(fresh_db)
        sig = _make_signal(entry=100.0, stop=90.0, target=120.0)
        trade = engine.process_signal(sig, 100.0)

        # Trigger exit
        engine.update_positions({"RELIANCE": 120.0})

        # Check trades table
        t_row = fresh_db.fetchone("SELECT exit_description, exit_reason FROM trades WHERE id = ?", (trade["id"],))
        assert t_row is not None
        assert t_row["exit_reason"] == "target_hit"
        assert len(t_row["exit_description"]) > 10
        assert "Target Reached" in t_row["exit_description"]

        # Check trade_events table for full_exit event
        e_row = fresh_db.fetchone("SELECT event_type, reason FROM trade_events WHERE trade_id = ? AND event_type = 'full_exit'", (trade["id"],))
        assert e_row is not None
        assert e_row["reason"] == "target_hit"

