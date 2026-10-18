# Algo Monitor — Implementation Plan

## Repository Inspection Summary

| Item | Status |
|------|--------|
| Delta Exchange REST (products, tickers) | ✅ Working |
| Delta Exchange WebSocket (ticker stream) | ✅ Working |
| Upstox Nifty 50 LTP quote | ✅ Working |
| Project structure | ❌ Flat scripts, no packages |
| Database / persistence | ❌ None |
| Strategy engine | ❌ None |
| Risk management | ❌ None |
| Paper trading | ❌ None |
| Alerts / notifications | ❌ None |
| Dashboard / UI | ❌ None |
| Tests | ❌ None |
| Security | ⚠️ Secrets in plaintext `secret.txt` |

## Architecture

```
algo_monitor/                 # Python package
├── config/                   # Settings, env loading, instrument config
├── data/                     # Market data providers
│   ├── delta_exchange.py     # Delta REST + WebSocket client
│   ├── upstox.py             # Upstox REST client
│   ├── candle_store.py       # Historical candle storage (SQLite)
│   └── ingestion.py          # Candle ingestion service
├── strategy/                 # Strategy engine
│   ├── levels.py             # Support/resistance detection
│   ├── signals.py            # Setup detection (bounce/rejection/breakout/etc.)
│   └── scanner.py            # Multi-instrument scanner
├── risk/                     # Risk management
│   └── manager.py            # Position sizing, limits, circuit breaker
├── trading/                  # Paper trading engine
│   ├── engine.py             # Order simulation, position tracking
│   ├── models.py             # Trade, Position, Order dataclasses
│   └── performance.py        # Performance metrics & reports
├── alerts/                   # Notification system
│   ├── base.py               # Abstract notifier
│   └── telegram.py           # Telegram bot notifier
├── dashboard/                # Web dashboard
│   ├── app.py                # FastAPI/Flask app
│   ├── static/               # CSS, JS
│   └── templates/            # HTML templates
├── backtest/                 # Backtesting module
│   └── runner.py             # Historical simulation runner
└── utils/                    # Logging, health checks, helpers

tests/                        # Test suite
├── test_levels.py
├── test_signals.py
├── test_risk.py
├── test_trading.py
├── test_data_providers.py
└── fixtures/                 # Mock data for tests
```

## Implementation Stages

### Stage 1: Foundation
- Project structure, config, `.env` cleanup, `.gitignore`
- SQLite database setup
- Structured logging

### Stage 2: Data Layer
- Delta Exchange client (reuse existing code)
- Upstox client (reuse existing code)
- Historical candle ingestion and storage
- Instrument configuration

### Stage 3: Strategy Engine
- Support/resistance level detection
- Zone clustering
- Signal generation (6 setup types)
- Multi-timeframe scanning

### Stage 4: Risk & Paper Trading
- Risk manager
- Paper trading engine
- Position tracking
- Performance reports

### Stage 5: Alerts
- Notification abstraction
- Telegram integration
- Deduplication & rate limiting

### Stage 6: Dashboard
- FastAPI web app
- Real-time market overview
- Trade history, P&L, signals display

### Stage 7: Testing & Validation
- Unit tests with mock data
- Backtest runner
- Integration verification

### Stage 8: Documentation
- README with setup instructions
- Configuration guide
- `.env.example`

## Technology Choices

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Web framework | FastAPI | Async-ready, lightweight, modern |
| Database | SQLite | Zero config, file-based, sufficient for personal use |
| ORM | Raw SQL via `sqlite3` | Minimal dependencies, full control |
| WebSocket client | `websocket-client` | Already used in existing code |
| HTTP client | `requests` + `httpx` | `requests` for sync, `httpx` for async |
| Dashboard | Jinja2 templates + vanilla JS | Lightweight, no build step |
| Charting | Chart.js | Client-side, no server load |
| Task scheduling | APScheduler | Mature, lightweight |
| Testing | pytest | Standard Python testing |
