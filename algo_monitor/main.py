"""
Algo Monitor — Main Application Orchestrator.

Ties together all modules: data ingestion, strategy scanning,
paper trading, alerts, and the web dashboard.

PAPER TRADING ONLY — no real orders are ever placed.
"""

from __future__ import annotations

import signal
import sys
import threading
import time
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from algo_monitor.alerts.notifier import AlertManager, ConsoleNotifier, TelegramNotifier
from algo_monitor.config.instruments import Exchange, MarketCategory, get_enabled_instruments
from algo_monitor.config.settings import Settings, get_settings
from algo_monitor.dashboard.app import create_app
from algo_monitor.data.candle_store import CandleStore
from algo_monitor.data.delta_exchange import DeltaExchangeClient, DeltaWebSocketClient
from algo_monitor.data.ingestion import IngestionService
from algo_monitor.data.models import ConnectionStatus, TickerUpdate
from algo_monitor.data.upstox import UpstoxClient
from algo_monitor.database import get_database
from algo_monitor.strategy.scanner import Scanner
from algo_monitor.trading.engine import PaperTradingEngine
from algo_monitor.trading.trade_manager import TradeManager
from algo_monitor.utils.logging import get_logger, setup_logging

logger = get_logger("main")


class AlgoMonitor:
    """
    Main application class that orchestrates all components.

    Lifecycle:
    1. Initialise settings, database, clients
    2. Start data ingestion
    3. Start strategy scanner on schedule
    4. Start WebSocket feeds
    5. Start web dashboard
    6. Run until shutdown
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        setup_logging(self.settings.log_level)

        logger.info("=" * 60)
        logger.info("  Algo Monitor v0.1.0 — Paper Trading Only")
        logger.info("=" * 60)

        # Database
        self.db = get_database(self.settings.database_path)

        # Data clients
        self.delta_client: DeltaExchangeClient | None = None
        self.upstox_client: UpstoxClient | None = None
        self.delta_ws: DeltaWebSocketClient | None = None

        # Candle store & ingestion
        self.candle_store = CandleStore(self.db)
        self.ingestion: IngestionService | None = None

        # Strategy
        self.scanner = Scanner(self.settings.strategy, self.db)

        # Trading
        self.trading_engine = PaperTradingEngine(
            self.settings.risk, self.db, self.settings.options, self.settings.exit
        )

        # Alerts
        self.alert_manager = AlertManager(self.db)
        self.alert_manager.add_notifier(ConsoleNotifier())

        # Trade Manager for Open Positions (P2-B, P2-C)
        self.trade_manager = TradeManager(
            self.db, self.settings.strategy, self.alert_manager
        )

        # Scheduler
        self.scheduler = BackgroundScheduler(daemon=True)

        # Dashboard app
        self.app = create_app(self.db)
        self.app.state.trade_manager = self.trade_manager

        # Live ticker cache
        self._latest_prices: dict[str, float] = {}
        self._shutdown_event = threading.Event()

    def initialise(self) -> None:
        """Set up all clients and services."""

        # --- Delta Exchange ---
        if self.settings.delta.is_configured:
            self.delta_client = DeltaExchangeClient(
                api_key=self.settings.delta.api_key,
                api_secret=self.settings.delta.api_secret,
            )
            logger.info("Delta Exchange client initialised")
        else:
            logger.warning("Delta Exchange not configured (no API key)")

        # --- Upstox & Auto-Auth ---
        from algo_monitor.data.upstox_auth import UpstoxAuthManager
        self.auth_manager = UpstoxAuthManager(self.db, self.settings)
        active_token = self.auth_manager.get_valid_token()

        if active_token:
            self.upstox_client = UpstoxClient(
                access_token=active_token,
                api_key=self.settings.upstox.api_key,
            )
            logger.info("Upstox client initialised with active access token")
        elif self.settings.upstox.is_configured:
            self.upstox_client = UpstoxClient(
                access_token=self.settings.upstox.access_token,
                api_key=self.settings.upstox.api_key,
            )
            logger.warning("Upstox client initialised with unverified access token")
        else:
            logger.warning("Upstox not configured")

        # --- Ingestion ---
        self.ingestion = IngestionService(
            store=self.candle_store,
            delta_client=self.delta_client,
            upstox_client=self.upstox_client,
        )

        # --- Telegram ---
        if self.settings.telegram.is_configured:
            self.alert_manager.add_notifier(
                TelegramNotifier(
                    bot_token=self.settings.telegram.bot_token,
                    chat_id=self.settings.telegram.chat_id,
                )
            )
            logger.info("Telegram notifier enabled")

        logger.info("Initialisation complete")

    def start(self) -> None:
        """Start all services."""
        self.initialise()

        # Schedule periodic tasks
        self.scheduler.add_job(
            self._run_ingestion,
            "interval",
            minutes=15,
            id="ingestion",
            name="Candle Ingestion",
        )
        self.scheduler.add_job(
            self._run_scan,
            "interval",
            minutes=5,
            id="scan",
            name="Strategy Scan",
        )
        self.scheduler.add_job(
            self._update_positions,
            "interval",
            seconds=30,
            id="position_check",
            name="Position Monitor",
        )
        self.scheduler.add_job(
            self._reset_daily_circuit,
            "cron",
            hour=0,
            minute=0,
            id="circuit_reset",
            name="Daily Circuit Reset",
        )
        self.scheduler.add_job(
            self._refresh_upstox_token,
            "cron",
            day_of_week="mon-fri",
            hour=8,
            minute=45,
            id="upstox_token_refresh",
            name="Daily Upstox Token Auto-Refresh",
        )
        self.scheduler.start()
        logger.info("Scheduler started")

        # Start WebSocket for Delta
        self._start_websocket()

        # Run initial ingestion and scan in background thread so dashboard starts instantly
        def _bg_bootstrap():
            try:
                # Fast initial scan using historical candles already in SQLite
                self._run_scan()
                # Background ingestion across API endpoints
                self._run_ingestion()
                # Re-scan with newly ingested candles
                self._run_scan()
            except Exception as exc:
                logger.error("Background bootstrap error: %s", exc)

        threading.Thread(target=_bg_bootstrap, daemon=True, name="bg_bootstrap").start()

        # Start dashboard (binds immediately to port)
        self._start_dashboard()

    def _run_ingestion(self) -> None:
        """Fetch latest candle data for all enabled instruments."""
        try:
            instruments = get_enabled_instruments()
            if not instruments:
                logger.warning("No enabled instruments to ingest")
                return

            for inst in instruments:
                cat = getattr(inst, "market_category", None)
                intervals = ["1d", "5m"] if cat == MarketCategory.INDIAN else ["1h", "4h", "5m"]
                self.ingestion.ingest(inst, intervals=intervals, lookback_days=90)
                time.sleep(0.2)
            logger.info("Ingestion complete for %d instruments", len(instruments))
        except Exception as exc:
            logger.error("Ingestion error: %s", exc)

    def _run_scan(self) -> None:
        """Scan all instruments for trading setups."""
        try:
            instruments = get_enabled_instruments()
            results = self.scanner.scan_all(instruments)

            # Store results for dashboard
            self.app.state.scan_results = results
            self.app.state.last_scan_time = datetime.now(timezone.utc).isoformat()

            # Persist detected active zones to SQLite
            now_iso = datetime.now(timezone.utc).isoformat()
            try:
                symbols = [r["symbol"] for r in results]
                with self.db.transaction() as conn:
                    if symbols:
                        placeholders = ",".join("?" for _ in symbols)
                        conn.execute(
                            f"UPDATE zones SET is_active = 0 WHERE symbol IN ({placeholders})",
                            symbols,
                        )
                    zone_rows = []
                    for r in results:
                        sym = r["symbol"]
                        exch = r["exchange"]
                        for z in r.get("htf_zones", []):
                            zone_rows.append((
                                sym,
                                exch,
                                z.zone_type.value if hasattr(z, "zone_type") else str(getattr(z, "zone_type", "support")),
                                z.price_low if hasattr(z, "price_low") else getattr(z, "price_low", 0),
                                z.price_high if hasattr(z, "price_high") else getattr(z, "price_high", 0),
                                z.strength if hasattr(z, "strength") else getattr(z, "strength", 1.0),
                                z.touches if hasattr(z, "touches") else getattr(z, "touches", 1),
                                getattr(z, "first_seen", datetime.now(timezone.utc)).isoformat()
                                    if hasattr(getattr(z, "first_seen", None), "isoformat")
                                    else now_iso,
                                getattr(z, "last_seen", datetime.now(timezone.utc)).isoformat()
                                    if hasattr(getattr(z, "last_seen", None), "isoformat")
                                    else now_iso,
                                "1d" if exch == "upstox" else "1h",
                                0 if getattr(z, "is_broken", False) else 1,
                                "; ".join(getattr(z, "reasons", []))[:300],
                            ))
                    if zone_rows:
                        conn.executemany(
                            """INSERT INTO zones
                                (symbol, exchange, zone_type, price_low, price_high,
                                 strength, touches, first_seen, last_seen, interval,
                                 is_active, reason)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            zone_rows,
                        )
            except Exception as zone_err:
                logger.warning("Could not persist active zones: %s", zone_err)

            # Process and persist signals
            for result in results:
                for sig in result.get("signals", []):
                    try:
                        with self.db.transaction() as conn:
                            conn.execute(
                                """INSERT INTO signals
                                    (symbol, exchange, setup_type, direction, timeframe,
                                     entry_ref, stop_loss, target, risk_reward, strength,
                                     reason, invalidation, created_at, is_active, was_traded)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (
                                    sig.symbol,
                                    sig.exchange,
                                    sig.setup_type.value if hasattr(sig.setup_type, "value") else str(sig.setup_type),
                                    sig.direction.value if hasattr(sig.direction, "value") else str(sig.direction),
                                    sig.timeframe,
                                    sig.entry_ref,
                                    sig.stop_loss,
                                    sig.target,
                                    sig.risk_reward,
                                    sig.strength,
                                    sig.reason,
                                    sig.invalidation,
                                    sig.created_at.isoformat() if hasattr(sig.created_at, "isoformat") else now_iso,
                                    1,
                                    0,
                                ),
                            )
                    except Exception as sig_err:
                        logger.warning("Could not persist signal: %s", sig_err)

                    # Send alert
                    self.alert_manager.send_signal_alert(sig)

                    # Try to open paper trade
                    price = result.get("last_price") or (
                        sig.entry_ref if sig.entry_ref else 0
                    )
                    if price and price > 0:
                        self.trading_engine.process_signal(sig, price)

        except Exception as exc:
            logger.error("Scan error: %s", exc)

    def _update_positions(self) -> None:
        """Check open positions against current prices."""
        try:
            open_pos = self.trading_engine.get_open_positions()
            if not open_pos:
                return

            needed_symbols = {p["symbol"] for p in open_pos}
            # Combine WebSocket prices with any recent fetch
            prices = {s: self._latest_prices[s] for s in needed_symbols if s in self._latest_prices}

            # Only fetch tickers for symbols with open positions that aren't already cached
            for inst in get_enabled_instruments():
                key = inst.symbol
                if key in needed_symbols and key not in prices:
                    if inst.exchange == Exchange.DELTA and self.delta_client:
                        ticker = self.delta_client.get_ticker(inst.symbol)
                        if ticker and ticker.get("close"):
                            prices[key] = float(ticker["close"])
                    elif inst.exchange == Exchange.UPSTOX and self.upstox_client:
                        t = self.upstox_client.get_ticker(inst.instrument_key)
                        if t:
                            prices[key] = t.last_price

            closed = self.trading_engine.update_positions(prices)
            if closed:
                for trade in closed:
                    self.alert_manager.send_text(
                        f"📊 Trade closed: {trade['direction'].upper()} "
                        f"{trade['symbol']} | "
                        f"P&L: ₹{trade.get('net_pnl', 0):.2f} | "
                        f"Reason: {trade.get('exit_reason', 'unknown')}"
                    )

            # Evaluate remaining open positions with TradeManager (P2-B, P2-C)
            remaining_open = self.trading_engine.get_open_positions()
            for pos in remaining_open:
                try:
                    sym = pos["symbol"]
                    exch = pos.get("exchange", "delta")
                    curr_price = prices.get(sym, float(pos.get("entry_price", 0)))
                    candles = self.candle_store.get_candles(sym, exch, "5m", limit=30)
                    is_indian = (exch == "upstox") or ("NSE" in sym)
                    htf_interval = "1d" if is_indian else "1h"
                    htf_candles = self.candle_store.get_candles(sym, exch, htf_interval, limit=50)
                    zones = (
                        self.scanner.level_detector.detect_zones(htf_candles, reference_price=curr_price)
                        if htf_candles
                        else []
                    )
                    self.trade_manager.evaluate_and_alert_trade(pos, curr_price, candles, zones)
                except Exception as inner_exc:
                    logger.warning("TradeManager evaluation failed for trade %s: %s", pos.get("id"), inner_exc)
        except Exception as exc:
            logger.error("Position update error: %s", exc)

    def _start_websocket(self) -> None:
        """Start Delta Exchange WebSocket for live prices."""
        delta_instruments = get_enabled_instruments(Exchange.DELTA)
        if not delta_instruments:
            return

        symbols = [inst.symbol for inst in delta_instruments]

        def on_ticker(update: TickerUpdate) -> None:
            self._latest_prices[update.symbol] = update.last_price

        def on_status(status: ConnectionStatus) -> None:
            self.app.state.ws_status = status.value

        self.delta_ws = DeltaWebSocketClient(
            symbols=symbols,
            on_ticker=on_ticker,
            on_status_change=on_status,
        )
        self.delta_ws.start()

    def _reset_daily_circuit(self) -> None:
        """Reset daily circuit breaker at midnight."""
        self.trading_engine.risk_manager.reset_circuit_breaker()

    def _refresh_upstox_token(self) -> None:
        """Fetch fresh Upstox token and reinitialize client."""
        logger.info("Running daily Upstox token auto-refresh...")
        token = self.auth_manager.fetch_new_token()
        if token:
            self.upstox_client = UpstoxClient(
                access_token=token,
                api_key=self.settings.upstox.api_key,
            )
            if self.ingestion:
                self.ingestion.upstox_client = self.upstox_client
            logger.info("Upstox client successfully reloaded with fresh token")

    def _start_dashboard(self) -> None:
        """Start the web dashboard (blocking). Automatically resolves port collisions."""
        import socket
        import uvicorn

        host = self.settings.dashboard_host
        port = self.settings.dashboard_port

        def is_port_available(h: str, p: int) -> bool:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind((h, p))
                    return True
                except OSError:
                    return False

        # If previous instance just exited, wait briefly for port to clear before jumping
        for _ in range(3):
            if is_port_available(host, port):
                break
            time.sleep(1)

        # If port is still occupied by an external app, auto-select next available port
        while not is_port_available(host, port) and port < self.settings.dashboard_port + 50:
            logger.warning("Port %d is already in use, trying port %d...", port, port + 1)
            port += 1

        self.settings.dashboard_port = port
        logger.info("Starting dashboard at http://%s:%d", host, port)

        try:
            uvicorn.run(
                self.app,
                host=host,
                port=port,
                log_level="warning",
            )
        except OSError as exc:
            logger.error("Could not bind dashboard to http://%s:%d: %s", host, port, exc)
            if not self._shutdown_event.is_set():
                logger.info("Continuing background monitoring without embedded dashboard...")
                while not self._shutdown_event.is_set():
                    time.sleep(1)

    def start_dashboard_only(self) -> None:
        """Run only the web dashboard without data feeds or trading."""
        self.initialise()
        logger.info("Running in dashboard-only mode")
        self._start_dashboard()

    def start_backend_only(self) -> None:
        """Run only the backend services (feeds, scanner, paper trading) without dashboard."""
        self.initialise()
        logger.info("Starting Algo Monitor in backend-only mode...")

        self._run_ingestion()

        self.scheduler.add_job(
            self._run_ingestion,
            "interval",
            minutes=15,
            id="ingestion",
            name="Candle Ingestion",
        )
        self.scheduler.add_job(
            self._run_scan,
            "interval",
            minutes=5,
            id="scan",
            name="Strategy Scan",
        )
        self.scheduler.add_job(
            self._update_positions,
            "interval",
            seconds=30,
            id="position_check",
            name="Position Monitor",
        )
        self.scheduler.add_job(
            self._reset_daily_circuit,
            "cron",
            hour=0,
            minute=0,
            id="circuit_reset",
            name="Daily Circuit Reset",
        )
        self.scheduler.start()
        logger.info("Scheduler started")

        self._start_websocket()
        self._run_scan()

        logger.info("Backend running. Monitoring markets and positions. Press Ctrl+C to stop.")
        while not self._shutdown_event.is_set():
            time.sleep(1)

    def run_single_scan(self) -> None:
        """Run a single scan cycle across enabled instruments and exit."""
        self.initialise()
        logger.info("Running single scan cycle...")
        self._run_scan()
        logger.info("Single scan cycle completed")

    def run_backtest(self) -> None:
        """Run historical backtest on stored candles."""
        from algo_monitor.backtest.runner import BacktestRunner

        self.initialise()
        logger.info("Running backtest on historical candles...")
        instruments = get_enabled_instruments()
        runner = BacktestRunner(self.settings.strategy, self.settings.risk, self.db)
        for inst in instruments:
            logger.info("Backtesting %s...", inst.symbol)
            report = runner.run(inst)
            logger.info(
                "Backtest result for %s: %d trades, win rate: %.1f%%, PnL: %.2f",
                inst.symbol,
                report.total_trades,
                report.win_rate,
                report.net_pnl,
            )

    def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("Shutting down Algo Monitor...")
        self._shutdown_event.set()

        if self.delta_ws:
            self.delta_ws.stop()

        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

        logger.info("Shutdown complete")


def main():
    """Entry point for the application."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Algo Monitor — Automated Trading Monitoring Platform (Paper Trading Only)"
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Start dashboard only without background market feeds",
    )
    parser.add_argument(
        "--backend-only",
        "--no-dashboard",
        action="store_true",
        dest="backend_only",
        help="Start backend services only without web dashboard",
    )
    parser.add_argument(
        "--scan-once",
        action="store_true",
        help="Run a single market scan cycle and exit",
    )
    parser.add_argument(
        "--backtest",
        action="store_true",
        help="Run historical backtest on stored candle data",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Custom port for the web dashboard (default from settings: 8501)",
    )
    parser.add_argument(
        "--reset-capital",
        type=float,
        nargs="?",
        const=-1.0,
        metavar="AMOUNT",
        help="Reset paper balance to AMOUNT (or .env PAPER_TRADING_BALANCE if omitted) and clear past trades before starting",
    )
    args = parser.parse_args()

    monitor = AlgoMonitor()
    if args.port:
        monitor.settings.dashboard_port = args.port

    if args.reset_capital is not None:
        from pathlib import Path
        from reset_capital import reset_capital as do_reset
        target_cap = args.reset_capital if args.reset_capital > 0 else monitor.settings.risk.starting_balance
        env_file = Path(__file__).resolve().parent.parent / ".env"
        do_reset(
            db_path=Path(monitor.settings.database_path),
            capital=target_cap,
            clear_trades=True,
            update_env=True,
            env_path=env_file,
        )

    def signal_handler(sig, frame):
        monitor.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        if args.dashboard:
            monitor.start_dashboard_only()
        elif args.backend_only:
            monitor.start_backend_only()
        elif args.scan_once:
            monitor.run_single_scan()
        elif args.backtest:
            monitor.run_backtest()
        else:
            monitor.start()
    except KeyboardInterrupt:
        monitor.shutdown()
    except Exception as exc:
        logger.critical("Fatal error: %s", exc, exc_info=True)
        monitor.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    main()
