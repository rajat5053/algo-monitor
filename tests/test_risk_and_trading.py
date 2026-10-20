"""
Tests for risk management and paper-trading engine.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from algo_monitor.config.settings import RiskConfig
from algo_monitor.data.candle_store import CandleStore
from algo_monitor.data.models import Candle
from algo_monitor.database import Database
from algo_monitor.risk.manager import RiskDecision, RiskManager
from algo_monitor.strategy.signals import Direction, SetupType, Signal
from algo_monitor.strategy.levels import Zone, ZoneType
from algo_monitor.trading.engine import PaperTradingEngine
from algo_monitor.trading.performance import PerformanceAnalyser


# Each test gets its own DB to avoid cross-test contamination.

@pytest.fixture
def fresh_db(tmp_path, request):
    """Provide a truly fresh SQLite database per test."""
    db_path = str(tmp_path / f"test_{request.node.name}.db")
    db = Database(db_path)
    db.initialise()
    return db


# ===== Risk Manager Tests =====

class TestRiskManager:
    """Test risk evaluation logic."""

    def _make_signal(
        self,
        direction=Direction.LONG,
        entry=100.0,
        stop=95.0,
        target=110.0,
    ) -> Signal:
        return Signal(
            symbol="TEST",
            exchange="test",
            setup_type=SetupType.BOUNCE_SUPPORT,
            direction=direction,
            timeframe="5m",
            entry_ref=entry,
            stop_loss=stop,
            target=target,
            risk_reward=2.0,
            strength=0.7,
            reason="Test signal",
        )

    def test_approved_signal(self, risk_config):
        """Valid signal with good R:R should be approved."""
        rm = RiskManager(risk_config)
        sig = self._make_signal()

        decision = rm.evaluate(
            signal=sig,
            current_price=100.0,
            current_balance=1_000_000,
            open_positions=[],
        )

        assert decision.approved
        assert decision.quantity > 0
        assert decision.risk_amount > 0
        assert decision.estimated_fees > 0

    def test_position_sizing_respects_risk_budget(self, risk_config):
        """Position size should not exceed the risk budget."""
        # Set all per-market risk fields to 1% so get_risk_per_trade() returns 1%
        risk_config.risk_per_trade = 0.01
        risk_config.indian_cash_risk_per_trade = 0.01
        risk_config.indian_futures_risk_per_trade = 0.01
        risk_config.crypto_risk_per_trade = 0.01
        # Also raise capital cap so it's not the binding constraint
        risk_config.max_capital_per_trade_pct = 0.5
        rm = RiskManager(risk_config)

        sig = self._make_signal(entry=100.0, stop=95.0, target=115.0)
        decision = rm.evaluate(
            signal=sig,
            current_price=100.0,
            current_balance=1_000_000,
            open_positions=[],
        )

        assert decision.approved
        # Risk per unit = 100 - 95 = 5
        # Risk budget = 1M * 0.01 = 10,000
        # Max quantity from risk = 10,000 / 5 = 2,000
        # Capital limit = 1M * 0.5 / 100 = 5,000 → qty_leverage = 5,000  (not binding)
        assert abs(decision.quantity - 2000) < 1


    def test_reject_bad_reward_risk(self, risk_config):
        """Should reject signals with R:R below minimum."""
        risk_config.min_reward_risk = 2.0
        rm = RiskManager(risk_config)

        # R:R = 1.0 (5 risk, 5 reward)
        sig = self._make_signal(entry=100.0, stop=95.0, target=105.0)
        decision = rm.evaluate(
            signal=sig,
            current_price=100.0,
            current_balance=1_000_000,
            open_positions=[],
        )

        assert not decision.approved
        assert any("Reward-to-risk" in r for r in decision.reject_reasons)

    def test_reject_max_positions(self, risk_config):
        """Should reject when max positions reached."""
        risk_config.max_positions = 2
        rm = RiskManager(risk_config)
        sig = self._make_signal()

        open_pos = [
            {"symbol": "A", "exchange": "test", "direction": "long"},
            {"symbol": "B", "exchange": "test", "direction": "long"},
        ]

        decision = rm.evaluate(
            signal=sig,
            current_price=100.0,
            current_balance=1_000_000,
            open_positions=open_pos,
        )

        assert not decision.approved
        assert any("Maximum positions" in r for r in decision.reject_reasons)

    def test_reject_duplicate_position(self, risk_config):
        """Should reject duplicate positions for the same instrument."""
        rm = RiskManager(risk_config)
        sig = self._make_signal()

        open_pos = [
            {"symbol": "TEST", "exchange": "test", "direction": "long"},
        ]

        decision = rm.evaluate(
            signal=sig,
            current_price=100.0,
            current_balance=1_000_000,
            open_positions=open_pos,
        )

        assert not decision.approved
        assert any("Duplicate" in r for r in decision.reject_reasons)

    def test_reject_conflicting_direction(self, risk_config):
        """Should reject conflicting positions (long vs short)."""
        rm = RiskManager(risk_config)
        sig = self._make_signal(direction=Direction.LONG)

        open_pos = [
            {"symbol": "TEST", "exchange": "test", "direction": "short"},
        ]

        decision = rm.evaluate(
            signal=sig,
            current_price=100.0,
            current_balance=1_000_000,
            open_positions=open_pos,
        )

        assert not decision.approved
        assert any("Conflicting" in r for r in decision.reject_reasons)

    def test_reject_no_entry_price(self, risk_config):
        """Should reject if entry price is missing."""
        rm = RiskManager(risk_config)
        sig = self._make_signal()
        sig.entry_ref = None

        decision = rm.evaluate(
            signal=sig,
            current_price=100.0,
            current_balance=1_000_000,
            open_positions=[],
        )

        assert not decision.approved

    def test_reject_no_stop_loss(self, risk_config):
        """Should reject if stop loss is missing."""
        rm = RiskManager(risk_config)
        sig = self._make_signal()
        sig.stop_loss = None

        decision = rm.evaluate(
            signal=sig,
            current_price=100.0,
            current_balance=1_000_000,
            open_positions=[],
        )

        assert not decision.approved

    def test_circuit_breaker(self, risk_config):
        """Should reject trades when daily loss exceeds limit."""
        risk_config.max_daily_loss = 0.05
        rm = RiskManager(risk_config)
        sig = self._make_signal()

        # Daily loss exceeds 5% of 1M = 50,000
        decision = rm.evaluate(
            signal=sig,
            current_price=100.0,
            current_balance=1_000_000,
            open_positions=[],
            daily_realised_pnl=-60_000,
        )

        assert not decision.approved
        assert any("circuit breaker" in r.lower() or "Daily loss" in r for r in decision.reject_reasons)

    def test_circuit_breaker_ist_timezone(self):
        """Verify _trading_day_str uses IST for Indian instruments and UTC for crypto."""
        from algo_monitor.risk.manager import _trading_day_str, _IST
        from unittest.mock import patch

        # Mock a time that is 2024-05-01 20:00 UTC -> which is 2024-05-02 01:30 IST
        mock_utc_time = datetime(2024, 5, 1, 20, 0, tzinfo=timezone.utc)
        with patch("algo_monitor.risk.manager.datetime") as mock_dt:
            mock_dt.now.side_effect = lambda tz=None: mock_utc_time.astimezone(tz) if tz else mock_utc_time

            # Upstox (Indian) should be in IST -> 2024-05-02
            ist_day = _trading_day_str("NIFTY", "upstox")
            assert ist_day == "2024-05-02"

            # Delta (Crypto) should be in UTC -> 2024-05-01
            utc_day = _trading_day_str("BTCUSD", "delta")
            assert utc_day == "2024-05-01"

    def test_stale_signal_rejected(self, risk_config):
        """Should reject signals older than 2 hours."""
        rm = RiskManager(risk_config)
        sig = self._make_signal()
        sig.created_at = datetime.now(timezone.utc) - timedelta(hours=3)

        decision = rm.evaluate(
            signal=sig,
            current_price=100.0,
            current_balance=1_000_000,
            open_positions=[],
        )

        assert not decision.approved
        assert any("stale" in r.lower() for r in decision.reject_reasons)

    def test_short_signal_sizing(self, risk_config):
        """Short signals should calculate risk correctly."""
        rm = RiskManager(risk_config)
        sig = self._make_signal(
            direction=Direction.SHORT,
            entry=100.0,
            stop=105.0,
            target=90.0,
        )

        decision = rm.evaluate(
            signal=sig,
            current_price=100.0,
            current_balance=1_000_000,
            open_positions=[],
        )

        assert decision.approved
        assert decision.quantity > 0
        # Risk per unit = 105 - 100 = 5
        # Budget = 1M * 0.02 = 20,000
        # Qty = 20,000 / 5 = 4,000
        assert abs(decision.quantity - 4000) < 1


# ===== Paper Trading Engine Tests =====

class TestPaperTradingEngine:
    """Test the paper trading simulation engine."""

    def _make_signal(self, direction=Direction.LONG, symbol="TEST") -> Signal:
        if direction == Direction.LONG:
            return Signal(
                symbol=symbol, exchange="test",
                setup_type=SetupType.BOUNCE_SUPPORT,
                direction=direction, timeframe="5m",
                entry_ref=100.0, stop_loss=95.0, target=110.0,
                risk_reward=2.0, strength=0.7, reason="Test",
            )
        else:
            return Signal(
                symbol=symbol, exchange="test",
                setup_type=SetupType.REJECTION_RESISTANCE,
                direction=direction, timeframe="5m",
                entry_ref=100.0, stop_loss=105.0, target=90.0,
                risk_reward=2.0, strength=0.7, reason="Test",
            )

    def test_open_trade(self, fresh_db, risk_config):
        """Should open a paper trade from a valid signal."""
        engine = PaperTradingEngine(risk_config, fresh_db)
        sig = self._make_signal()

        trade = engine.process_signal(sig, current_price=100.0)

        assert trade is not None
        assert trade["symbol"] == "TEST"
        assert trade["direction"] == "long"
        assert trade["status"] == "open"
        assert trade["entry_price"] == 100.0

    def test_trade_persists(self, fresh_db, risk_config):
        """Trade should be saved in database."""
        engine = PaperTradingEngine(risk_config, fresh_db)
        sig = self._make_signal()

        engine.process_signal(sig, current_price=100.0)

        open_pos = engine.get_open_positions()
        assert len(open_pos) == 1
        assert open_pos[0]["symbol"] == "TEST"

    def test_stop_loss_closes_trade(self, fresh_db, risk_config):
        """Position should close when price hits stop loss."""
        engine = PaperTradingEngine(risk_config, fresh_db)
        sig = self._make_signal()

        engine.process_signal(sig, current_price=100.0)

        # Price drops to stop loss
        closed = engine.update_positions({"TEST": 94.0})

        assert len(closed) == 1
        assert closed[0]["exit_reason"] == "stop_loss"
        assert closed[0]["net_pnl"] < 0

    def test_target_closes_trade(self, fresh_db, risk_config):
        """Position should close when price hits target."""
        engine = PaperTradingEngine(risk_config, fresh_db)
        sig = self._make_signal()

        engine.process_signal(sig, current_price=100.0)

        # Price rises to target
        closed = engine.update_positions({"TEST": 111.0})

        assert len(closed) == 1
        assert closed[0]["exit_reason"] == "target_hit"
        assert closed[0]["net_pnl"] > 0

    def test_balance_updates_on_close(self, fresh_db, risk_config):
        """Balance should update when a trade is closed."""
        engine = PaperTradingEngine(risk_config, fresh_db)
        initial_balance = engine.balance

        sig = self._make_signal()
        engine.process_signal(sig, current_price=100.0)

        # Close at target
        engine.update_positions({"TEST": 111.0})

        assert engine.balance > initial_balance

    def test_no_duplicate_trades(self, fresh_db, risk_config):
        """Should not open duplicate trades for the same instrument."""
        engine = PaperTradingEngine(risk_config, fresh_db)
        sig = self._make_signal()

        first = engine.process_signal(sig, current_price=100.0)
        second = engine.process_signal(sig, current_price=100.0)

        assert first is not None
        assert second is None  # Rejected as duplicate

    def test_force_close_all(self, fresh_db, risk_config):
        """Force close should close all open positions."""
        risk_config.max_positions = 5
        engine = PaperTradingEngine(risk_config, fresh_db)

        for sym in ["A", "B", "C"]:
            sig = self._make_signal(symbol=sym)
            engine.process_signal(sig, current_price=100.0)

        assert len(engine.get_open_positions()) == 3

        closed = engine.force_close_all({"A": 101, "B": 99, "C": 100})
        assert len(closed) == 3
        assert len(engine.get_open_positions()) == 0


# ===== Performance Tests =====

class TestPerformanceAnalyser:
    """Test performance reporting."""

    def test_empty_report(self, fresh_db):
        """Should handle no trades gracefully."""
        analyser = PerformanceAnalyser(fresh_db)
        report = analyser.generate_report(starting_balance=1_000_000)

        assert report.total_trades == 0
        assert report.win_rate == 0
        assert report.ending_balance == 1_000_000


    def test_report_with_trades(self, fresh_db, risk_config):
        """Should compute correct metrics from trades."""
        engine = PaperTradingEngine(risk_config, fresh_db)

        # Open and close a winning trade
        sig = Signal(
            symbol="WIN", exchange="test",
            setup_type=SetupType.BOUNCE_SUPPORT,
            direction=Direction.LONG, timeframe="5m",
            entry_ref=100.0, stop_loss=95.0, target=110.0,
            risk_reward=2.0, strength=0.7,
        )
        engine.process_signal(sig, current_price=100.0)
        engine.update_positions({"WIN": 111.0})

        analyser = PerformanceAnalyser(fresh_db)
        report = analyser.generate_report()

        assert report.total_trades == 1
        assert report.winning_trades == 1
        assert report.win_rate == 100.0
        assert report.net_pnl > 0


# ===== Candle Store Tests =====

class TestCandleStore:
    """Test candle persistence."""

    def test_upsert_and_retrieve(self, fresh_db):
        """Should store and retrieve candles correctly."""
        from tests.conftest import make_candle_series

        store = CandleStore(fresh_db)
        candles = make_candle_series(count=10)

        count = store.upsert_candles(candles)
        assert count == 10

        retrieved = store.get_candles("TEST", "test", "4h")
        assert len(retrieved) == 10
        assert retrieved[0].timestamp < retrieved[-1].timestamp

    def test_deduplication(self, fresh_db):
        """Inserting same candles twice should update, not duplicate."""
        from datetime import datetime, timezone

        store = CandleStore(fresh_db)

        # Create candles with explicit fixed timestamps
        candles = []
        for i in range(5):
            candles.append(Candle(
                symbol="DEDUP", exchange="test", interval="1h",
                timestamp=datetime(2024, 1, 1, i, 0, 0, tzinfo=timezone.utc),
                open=100.0, high=101.0, low=99.0, close=100.5,
                volume=1000.0, is_complete=True,
            ))

        store.upsert_candles(candles)
        store.upsert_candles(candles)  # Insert again

        retrieved = store.get_candles("DEDUP", "test", "1h")
        assert len(retrieved) == 5

    def test_latest_timestamp(self, fresh_db):
        """Should return the most recent candle timestamp."""
        from tests.conftest import make_candle_series

        store = CandleStore(fresh_db)
        candles = make_candle_series(count=10)
        store.upsert_candles(candles)

        latest = store.get_latest_timestamp("TEST", "test", "4h")
        assert latest is not None
        assert latest == candles[-1].timestamp

    def test_candle_count(self, fresh_db):
        """Should return correct candle count."""
        from tests.conftest import make_candle_series

        store = CandleStore(fresh_db)
        candles = make_candle_series(count=15)
        store.upsert_candles(candles)

        assert store.get_candle_count("TEST", "test", "4h") == 15


# ===== Database Tests =====

class TestDatabase:
    """Test database system_state and integrity."""

    def test_system_state(self, fresh_db):
        """Key-value state should persist."""
        fresh_db.set_state("test_key", "test_value")
        assert fresh_db.get_state("test_key") == "test_value"

    def test_state_default(self, fresh_db):
        """Missing keys should return default."""
        assert fresh_db.get_state("nonexistent", "default") == "default"

    def test_state_upsert(self, fresh_db):
        """Setting a key twice should update it."""
        fresh_db.set_state("key", "first")
        fresh_db.set_state("key", "second")
        assert fresh_db.get_state("key") == "second"


def test_compare_strategies():
    """Verify compare_strategies produces accurate comparison deltas."""
    from algo_monitor.trading.performance import PerformanceReport, compare_strategies

    baseline = PerformanceReport(
        total_trades=20,
        win_rate=50.0,
        profit_factor=1.5,
        net_pnl=5000.0,
        max_drawdown=1200.0,
    )
    hs_variant = PerformanceReport(
        total_trades=10,
        win_rate=60.0,
        profit_factor=2.0,
        net_pnl=7500.0,
        max_drawdown=800.0,
    )
    firsty_variant = PerformanceReport(
        total_trades=15,
        win_rate=45.0,
        profit_factor=1.2,
        net_pnl=3000.0,
        max_drawdown=1500.0,
    )

    comp = compare_strategies(baseline, {
        "head_and_shoulders": hs_variant,
        "firsty_continuation": firsty_variant,
    })

    assert comp["baseline"]["net_pnl"] == 5000.0
    assert comp["variants"]["head_and_shoulders"]["delta_pnl"] == 2500.0
    assert comp["variants"]["head_and_shoulders"]["delta_win_rate"] == 10.0
    assert comp["variants"]["firsty_continuation"]["delta_pnl"] == -2000.0
    assert comp["variants"]["firsty_continuation"]["delta_win_rate"] == -5.0


def test_indian_market_capital_default():
    """Verify default Indian market capital is 20,000."""
    cfg = RiskConfig()
    assert cfg.starting_balance == 20000.0
    assert cfg.indian_market_capital == 20000.0


def test_api_positions_includes_execution_time(fresh_db):
    """Verify /api/positions includes execution_time for both open and closed positions."""
    from algo_monitor.dashboard.app import create_app
    from starlette.testclient import TestClient

    # Insert an open trade and a closed trade
    fresh_db.execute(
        """INSERT INTO trades
           (symbol, exchange, direction, quantity, entry_price, entry_time, stop_loss, target, status)
           VALUES ('RELIANCE', 'upstox', 'long', 10, 2500.0, '2026-10-15T09:30:00+00:00', 2450.0, 2600.0, 'open')"""
    )
    fresh_db.execute(
        """INSERT INTO trades
           (symbol, exchange, direction, quantity, entry_price, entry_time, exit_price, exit_time, stop_loss, target, status, net_pnl)
           VALUES ('INFY', 'upstox', 'long', 5, 1800.0, '2026-10-15T09:45:00+00:00', 1850.0, '2026-10-15T10:15:00+00:00', 1780.0, 1850.0, 'closed', 250.0)"""
    )

    app = create_app(fresh_db)
    client = TestClient(app)
    resp = client.get("/api/positions")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["open"]) == 1
    assert data["open"][0]["symbol"] == "RELIANCE"
    assert data["open"][0]["execution_time"] == "2026-10-15T09:30:00+00:00"
    assert data["open"][0]["take_profit"] == 2600.0

    assert len(data["closed"]) == 1
    assert data["closed"][0]["symbol"] == "INFY"
    assert data["closed"][0]["execution_time"] == "2026-10-15T09:45:00+00:00"
    assert data["closed"][0]["closed_at"] == "2026-10-15T10:15:00+00:00"
    assert data["closed"][0]["realized_pnl"] == 250.0

