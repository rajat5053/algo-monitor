"""
Comprehensive tests for TradeManager (P2-B, P2-C, P3-A).

Validates all 6 recommendation states, duplicate alert suppression,
restart safety, and persistence.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import pytest

from algo_monitor.alerts.notifier import AlertManager
from algo_monitor.config.settings import StrategyConfig
from algo_monitor.data.models import Candle
from algo_monitor.strategy.levels import Zone, ZoneType
from algo_monitor.trading.trade_manager import (
    TradeManager,
    TradeManagementState,
)


class TestTradeManagerRecommendations:
    """Validate all 6 recommendation states of TradeManager."""

    @pytest.fixture
    def mock_alert_manager(self):
        am = MagicMock(spec=AlertManager)
        am.send_trade_management_alert.return_value = True
        return am

    @pytest.fixture
    def trade_manager(self, tmp_db, strategy_config, mock_alert_manager):
        return TradeManager(tmp_db, strategy_config, mock_alert_manager)

    def _sample_candles(self, count=10, last_close=100.0, is_bullish=True):
        now = datetime.now(timezone.utc)
        candles = []
        for i in range(count):
            c_time = now - timedelta(minutes=5 * (count - i))
            c_close = last_close if i == count - 1 else 99.0 + (i * 0.1)
            c_open = c_close - 0.5 if is_bullish else c_close + 0.5
            candles.append(
                Candle(
                    symbol="BTCUSD",
                    exchange="delta",
                    interval="5m",
                    timestamp=c_time,
                    open=c_open,
                    high=max(c_open, c_close) + 0.2,
                    low=min(c_open, c_close) - 0.2,
                    close=c_close,
                    volume=10.0,
                    is_complete=True,
                )
            )
        return candles

    def test_state_hold_current_plan(self, trade_manager):
        """Trade in normal progression should receive HOLD_CURRENT_PLAN."""
        trade = {
            "id": 1,
            "symbol": "BTCUSD",
            "direction": "long",
            "entry_price": 100.0,
            "stop_loss": 95.0,  # Risk = 5.0
            "target": 115.0,    # Target distance = 15.0
        }
        # Current price = 102.0 (progress = 2/15 = 13.3%, R = +0.4)
        candles = self._sample_candles(last_close=102.0)

        evaluation = trade_manager.evaluate_trade(trade, 102.0, candles, [])
        assert evaluation.state == TradeManagementState.HOLD_CURRENT_PLAN
        assert evaluation.r_achieved == pytest.approx(0.4)
        assert len(evaluation.evidence_for) > 0

    def test_state_consider_stop_tightening(self, trade_manager):
        """Trade reaching +1.0R excursion should recommend CONSIDER_STOP_TIGHTENING."""
        trade = {
            "id": 2,
            "symbol": "BTCUSD",
            "direction": "long",
            "entry_price": 100.0,
            "stop_loss": 95.0,  # Risk = 5.0
            "target": 115.0,
        }
        # Current price = 105.5 (+1.1R) while stop is still at 95.0
        candles = self._sample_candles(last_close=105.5)

        evaluation = trade_manager.evaluate_trade(trade, 105.5, candles, [])
        assert evaluation.state == TradeManagementState.CONSIDER_STOP_TIGHTENING
        assert evaluation.r_achieved >= 1.0
        assert any("excursion" in e.lower() for e in evaluation.evidence_for)

    def test_state_consider_profit_taking_at_opposing_zone(self, trade_manager):
        """Trade near target (>= 85%) encountering opposing zone should recommend CONSIDER_PROFIT_TAKING."""
        trade = {
            "id": 3,
            "symbol": "BTCUSD",
            "direction": "long",
            "entry_price": 100.0,
            "stop_loss": 95.0,  # Risk = 5.0
            "target": 115.0,
        }
        # Current price = 113.5 (progress = 90%, R = 2.7)
        candles = self._sample_candles(last_close=113.5)
        # Opposing resistance zone sitting at 115.0
        now = datetime.now(timezone.utc)
        opposing_resistance = Zone(
            zone_type=ZoneType.RESISTANCE,
            price_low=114.5,
            price_high=116.0,
            first_seen=now,
            last_seen=now,
            touches=4,
        )

        evaluation = trade_manager.evaluate_trade(
            trade, 113.5, candles, [opposing_resistance]
        )
        assert evaluation.state == TradeManagementState.CONSIDER_PROFIT_TAKING
        assert any("opposing" in e.lower() or "profit" in e.lower() for e in evaluation.evidence_for)

    def test_state_consider_target_extension(self, trade_manager):
        """Approaching target with strong bullish momentum and clean air proposes target extension."""
        trade = {
            "id": 4,
            "symbol": "BTCUSD",
            "direction": "long",
            "entry_price": 100.0,
            "stop_loss": 95.0,  # Risk = 5.0
            "target": 110.0,    # Target distance = 10.0
        }
        # Current price = 108.0 (progress = 80%, R = 1.6), strong bullish candle
        candles = self._sample_candles(last_close=108.0, is_bullish=True)
        # Opposing zone is much higher at 125.0
        now = datetime.now(timezone.utc)
        far_resistance = Zone(
            zone_type=ZoneType.RESISTANCE,
            price_low=124.0,
            price_high=126.0,
            first_seen=now,
            last_seen=now,
            touches=3,
        )

        evaluation = trade_manager.evaluate_trade(
            trade, 108.0, candles, [far_resistance]
        )
        assert evaluation.state == TradeManagementState.CONSIDER_TARGET_EXTENSION
        assert evaluation.proposed_target is not None
        assert evaluation.proposed_target > trade["target"]
        assert any("extension" in e.lower() or "momentum" in e.lower() for e in evaluation.evidence_for)

    def test_state_exit_thesis_invalidated(self, trade_manager):
        """When price breaks below stop loss, recommend EXIT_THESIS_INVALIDATED."""
        trade = {
            "id": 5,
            "symbol": "BTCUSD",
            "direction": "long",
            "entry_price": 100.0,
            "stop_loss": 95.0,
            "target": 115.0,
        }
        # Current price = 94.0 (broke below stop loss 95.0)
        candles = self._sample_candles(last_close=94.0, is_bullish=False)

        evaluation = trade_manager.evaluate_trade(trade, 94.0, candles, [])
        assert evaluation.state == TradeManagementState.EXIT_THESIS_INVALIDATED
        assert any("invalidation" in e.lower() for e in evaluation.evidence_for)

    def test_state_monitoring_unavailable_on_stale_data(self, trade_manager):
        """If candles are older than 2 hours for crypto, yield MONITORING_UNAVAILABLE."""
        trade = {
            "id": 6,
            "symbol": "BTCUSD",
            "direction": "long",
            "entry_price": 100.0,
            "stop_loss": 95.0,
            "target": 115.0,
        }
        # Stale candles (3 hours old)
        stale_time = datetime.now(timezone.utc) - timedelta(hours=3)
        stale_candles = [
            Candle(
                symbol="BTCUSD",
                exchange="delta",
                interval="5m",
                timestamp=stale_time,
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=10.0,
            )
        ]

        evaluation = trade_manager.evaluate_trade(trade, 100.5, stale_candles, [])
        assert evaluation.state == TradeManagementState.MONITORING_UNAVAILABLE
        assert any("age" in e.lower() or "stale" in e.lower() or "threshold" in e.lower() for e in evaluation.evidence_against)


class TestTradeManagerPersistenceAndDeduplication:
    """Validate duplicate suppression, restart safety, and DB persistence."""

    def test_duplicate_alert_suppressed(self, tmp_db, strategy_config):
        """Repeated evaluations of the same recommendation should NOT fire duplicate alerts."""
        mock_am = MagicMock(spec=AlertManager)
        mock_am.send_trade_management_alert.return_value = True

        # Insert trade into DB for FK constraint
        with tmp_db.transaction() as conn:
            conn.execute(
                """INSERT INTO trades (id, symbol, exchange, direction, quantity, entry_price, entry_time, stop_loss, target)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (10, "BTCUSD", "delta", "long", 1.0, 100.0, datetime.now(timezone.utc).isoformat(), 95.0, 115.0)
            )

        tm = TradeManager(tmp_db, strategy_config, mock_am)
        trade = {
            "id": 10,
            "symbol": "BTCUSD",
            "direction": "long",
            "entry_price": 100.0,
            "stop_loss": 95.0,
            "target": 115.0,
        }
        candles = [
            Candle(
                symbol="BTCUSD",
                exchange="delta",
                interval="5m",
                timestamp=datetime.now(timezone.utc),
                open=105.0,
                high=106.0,
                low=104.5,
                close=105.5,  # +1.1R -> stop tightening
                volume=10.0,
            )
        ]

        # First evaluation: alert should fire
        sent1 = tm.evaluate_and_alert_trade(trade, 105.5, candles, [])
        assert mock_am.send_trade_management_alert.call_count == 1

        # Second evaluation with identical state: alert must be suppressed
        sent2 = tm.evaluate_and_alert_trade(trade, 105.5, candles, [])
        assert mock_am.send_trade_management_alert.call_count == 1  # Still 1!

    def test_restart_safety_loads_state_from_database(self, tmp_db, strategy_config):
        """A new TradeManager instance after process restart must not re-alert existing states."""
        mock_am1 = MagicMock(spec=AlertManager)
        mock_am1.send_trade_management_alert.return_value = True

        # Insert trade into DB for FK constraint
        with tmp_db.transaction() as conn:
            conn.execute(
                """INSERT INTO trades (id, symbol, exchange, direction, quantity, entry_price, entry_time, stop_loss, target)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (20, "BTCUSD", "delta", "long", 1.0, 100.0, datetime.now(timezone.utc).isoformat(), 95.0, 115.0)
            )

        tm1 = TradeManager(tmp_db, strategy_config, mock_am1)
        trade = {
            "id": 20,
            "symbol": "BTCUSD",
            "direction": "long",
            "entry_price": 100.0,
            "stop_loss": 95.0,
            "target": 115.0,
        }
        candles = [
            Candle(
                symbol="BTCUSD",
                exchange="delta",
                interval="5m",
                timestamp=datetime.now(timezone.utc),
                open=105.0,
                high=106.0,
                low=104.5,
                close=105.5,
                volume=10.0,
            )
        ]

        # First manager alerts and persists to DB
        tm1.evaluate_and_alert_trade(trade, 105.5, candles, [])
        assert mock_am1.send_trade_management_alert.call_count == 1

        # Simulate process restart by creating a new TradeManager on the same DB
        mock_am2 = MagicMock(spec=AlertManager)
        mock_am2.send_trade_management_alert.return_value = True
        tm2 = TradeManager(tmp_db, strategy_config, mock_am2)

        # Evaluating again should load persisted hash and suppress re-alert
        tm2.evaluate_and_alert_trade(trade, 105.5, candles, [])
        assert mock_am2.send_trade_management_alert.call_count == 0  # Suppressed!


class TestDashboardPositionsIntegration:
    """Validate P3-A: /api/positions enriched with trade management data."""

    def test_dashboard_positions_enriched_with_trade_management(self, tmp_db):
        """Dashboard positions endpoint should include recommendation, progress, and evidence."""
        from fastapi.testclient import TestClient
        from algo_monitor.dashboard.app import create_app

        app = create_app(tmp_db)
        client = TestClient(app)

        now_str = datetime.now(timezone.utc).isoformat()
        with tmp_db.transaction() as conn:
            conn.execute(
                """INSERT INTO trades (id, symbol, exchange, direction, quantity, entry_price, entry_time, stop_loss, target, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (99, "BTCUSD", "delta", "long", 1.0, 100.0, now_str, 95.0, 115.0, "open"),
            )
            conn.execute(
                """INSERT INTO trade_management (trade_id, evaluated_at, recommendation, proposed_target, current_target, evidence_for, evidence_against, alert_sent, alert_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (99, now_str, "CONSIDER_STOP_TIGHTENING", None, 115.0, '["+1R reached"]', '["Trailing risks"]', 1, "test_hash_99"),
            )

        resp = client.get("/api/positions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["open"]) == 1
        pos = data["open"][0]
        assert pos["trade_management"]["recommendation"] == "CONSIDER_STOP_TIGHTENING"
        assert pos["trade_management"]["evidence_for"] == ["+1R reached"]
        assert pos["trade_management"]["evidence_against"] == ["Trailing risks"]
        assert "progress_to_target_pct" in pos
        assert "r_achieved" in pos

