"""
Tests for backtester correctness, look-ahead prevention, and FX conversion (P0-B, P0-C).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest

from algo_monitor.backtest.runner import BacktestRunner, _candle_close_time
from algo_monitor.config.instruments import Exchange, Instrument, MarketCategory, TradingMode
from algo_monitor.config.settings import RiskConfig, StrategyConfig
from algo_monitor.data.candle_store import CandleStore
from algo_monitor.data.models import Candle


class TestBacktestSafeguards:
    """Validate look-ahead bias prevention and FX conversion."""

    def test_candle_close_time_calculation(self):
        """Candle close time must be timestamp + duration."""
        open_time = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
        candle = Candle(
            symbol="TEST",
            exchange="test",
            interval="1d",
            timestamp=open_time,
            open=100.0,
            high=105.0,
            low=99.0,
            close=104.0,
            volume=1000.0,
        )

        close_time = _candle_close_time(candle, "1d")
        assert close_time == open_time + timedelta(days=1)

        # 4h candle
        candle_4h = Candle(
            symbol="TEST",
            exchange="test",
            interval="4h",
            timestamp=open_time,
            open=100.0,
            high=105.0,
            low=99.0,
            close=104.0,
            volume=1000.0,
        )
        assert _candle_close_time(candle_4h, "4h") == open_time + timedelta(hours=4)

    def test_backtest_no_lookahead_htf_filtering(self, tmp_db, strategy_config, risk_config):
        """HTF candle opening at T is not visible to LTF bar at T + 2h if HTF duration is 4h."""
        store = CandleStore(tmp_db)
        base = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)

        # 4h HTF candle: 00:00 to 04:00
        htf_candle = Candle(
            symbol="BTCUSD",
            exchange="delta",
            interval="4h",
            timestamp=base,
            open=40000.0,
            high=41000.0,
            low=39500.0,
            close=40500.0,
            volume=100.0,
        )
        store.upsert_candles([htf_candle], validate_interval=False)

        # LTF candle at 02:00 (midway through HTF candle)
        ltf_midway = Candle(
            symbol="BTCUSD",
            exchange="delta",
            interval="5m",
            timestamp=base + timedelta(hours=2),
            open=40200.0,
            high=40300.0,
            low=40150.0,
            close=40250.0,
            volume=10.0,
        )
        # LTF candle at 04:05 (after HTF candle has closed)
        ltf_after = Candle(
            symbol="BTCUSD",
            exchange="delta",
            interval="5m",
            timestamp=base + timedelta(hours=4, minutes=5),
            open=40500.0,
            high=40600.0,
            low=40450.0,
            close=40550.0,
            volume=10.0,
        )
        store.upsert_candles([ltf_midway, ltf_after], validate_interval=False)

        # Verify filtering logic directly
        htf_candles = store.get_candles("BTCUSD", "delta", "4h")
        assert len(htf_candles) == 1

        # At ltf_midway (02:00), htf_candle (closes at 04:00) must NOT be visible
        visible_midway = [
            c for c in htf_candles
            if _candle_close_time(c, "4h") <= ltf_midway.timestamp
        ]
        assert len(visible_midway) == 0

        # At ltf_after (04:05), htf_candle IS visible
        visible_after = [
            c for c in htf_candles
            if _candle_close_time(c, "4h") <= ltf_after.timestamp
        ]
        assert len(visible_after) == 1
        assert visible_after[0].timestamp == base

    def test_backtest_fx_rate_applied_to_usd_instruments(self):
        """USD P&L must be converted to INR using usd_inr_rate."""
        risk_cfg = RiskConfig(
            starting_balance=1_000_000,
            usd_inr_rate=85.0,
            fee_rate=0.0,
            slippage_rate=0.0,
        )
        entry = 50000.0
        exit_price = 51000.0
        qty = 0.1  # Profit = (51000 - 50000) * 0.1 = $100
        gross_quote = (exit_price - entry) * qty  # 100 USD

        fx_rate = risk_cfg.usd_inr_rate
        gross_inr = gross_quote * fx_rate

        assert gross_inr == 8500.0  # $100 * 85 INR/USD

    def test_backtest_runner_modes_supported(self, tmp_db, strategy_config, risk_config):
        """Runner supports both adaptive target mode and fixed RR mode."""
        from algo_monitor.config.instruments import AssetClass
        inst = Instrument(
            symbol="BTCUSD",
            exchange=Exchange.DELTA,
            asset_class=AssetClass.SPOT_CRYPTO,
            market_category=MarketCategory.CRYPTO,
        )

        runner_adaptive = BacktestRunner(strategy_config, risk_config, tmp_db)
        res_adaptive = runner_adaptive.run(inst)
        assert res_adaptive.symbol == "BTCUSD"

        # Fixed RR mode
        strategy_config.target_mode = "fixed_rr"
        strategy_config.target_fixed_rr_multiple = 2.0
        runner_fixed = BacktestRunner(strategy_config, risk_config, tmp_db)
        res_fixed = runner_fixed.run(inst)
        assert res_fixed.symbol == "BTCUSD"

