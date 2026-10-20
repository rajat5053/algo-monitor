# Algo Monitor: Complete Codebase Architecture, Trading Mechanics, and Quantitative Audit Report

> **Document Type:** Technical Architecture, Execution Flow Audit & Quantitative System Reference  
> **Target Audience:** Quantitative Developers, Algorithmic Traders, Financial Engineers, and Technical Auditors  
> **Repository Root:** `d:\Projects\Algo Monitor\`  
> **System Status:** **PAPER TRADING ONLY** (Strictly non-custodial; no live exchange order placement capability exists)  
> **Codebase Version:** 3.0.0 (Python 3.10+ / FastAPI / SQLite WAL / APScheduler / pyotp)  
> **Audit Date:** October 2026  

---

## Table of Contents
1. [Executive Summary & Fundamental Principles](#executive-summary--fundamental-principles)
2. [PART 1 — Complete System Architecture & Execution Flow](#part-1--complete-system-architecture--execution-flow)
3. [PART 2 — Markets, Instruments, and Timeframe Mechanics](#part-2--markets-instruments-and-timeframe-mechanics)
4. [PART 3 — Support and Resistance Detection Engine](#part-3--support-and-resistance-detection-engine)
5. [PART 4 — Comprehensive Setup and Entry Signal Catalogue](#part-4--comprehensive-setup-and-entry-signal-catalogue)
6. [PART 5 — Complete Trade Lifecycle & Reversal Scenarios](#part-5--complete-trade-lifecycle--reversal-scenarios)
7. [PART 6 — Stop-Loss, Target, and Risk/Reward Calculations](#part-6--stop-loss-target-and-riskreward-calculations)
8. [PART 7 — Position Sizing, Margin, and Capital Protection](#part-7--position-sizing-margin-and-capital-protection)
9. [PART 8 — Exhaustive Configuration Parameters Reference](#part-8--exhaustive-configuration-parameters-reference)
10. [PART 9 — Historical Backtesting System Audit](#part-9--historical-backtesting-system-audit)
11. [PART 10 — Dashboard, REST API, and Alert Routing](#part-10--dashboard-rest-api-and-alert-routing)
12. [PART 11 — State Persistence, Restarts, and Failure Scenarios](#part-11--state-persistence-restarts-and-failure-scenarios)
13. [PART 12 — Prioritized Audit Findings, Bugs, and Discrepancies](#part-12--prioritized-audit-findings-bugs-and-discrepancies)
14. [PART 13 — Complete End-to-End Worked Trade Example](#part-13--complete-end-to-end-worked-trade-example)
15. [PART 14 — Quantitative Learning Guide & Pre-Live Checklist](#part-14--quantitative-learning-guide--pre-live-checklist)

---

## Executive Summary & Fundamental Principles

**Algo Monitor** is an automated multi-market algorithmic monitoring and simulated paper-trading platform. It connects to two disparate exchange ecosystems:
1. **Indian National Stock Exchange (NSE)** via the **Upstox API v2/v3** (covering indices and F&O equity stocks).
2. **Crypto Derivatives** via the **Delta Exchange India REST and WebSocket feeds** (covering continuous crypto perpetual futures).

### Critical System Facts
- **Pure Paper Trading:** Across the entire codebase, there are **zero live execution endpoints**. Neither `UpstoxClient` nor `DeltaExchangeClient` contains order-routing functions such as `place_order`, `POST /v2/orders`, or broker checkout links. All trades exist exclusively as records in a local SQLite database (`trades` table).
- **Core Philosophy:** The strategy is built on multi-timeframe Support and Resistance (S/R) zones. Major horizontal price structures are discovered on Higher Timeframe (HTF) bars (Daily for Indian equities, 1-Hour for Crypto), and tactical entries are confirmed on Lower Timeframe (LTF) bars (5-Minute completed candles).
- **Dynamic Adaptations:** The codebase features modular extensions including adaptive structural targets (anchoring profit targets to the nearest opposing S/R zone), Black-Scholes options pricing and ATM auto-routing for Indian indices, advanced trade management advisories, Head & Shoulders pattern recognition, and Firsty-style exponential moving average (EMA) trend-continuation logic.

---

## PART 1 — Complete System Architecture & Execution Flow

### 1. Application Startup Sequence
The entry point of the application is [run.py](file:///d:/Projects/Algo%20Monitor/run.py), which invokes `main()` in [algo_monitor/main.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/main.py#L559-L649).

```
run.py::main()
  └── algo_monitor.main::main()
        ├── CLI Argument Parsing (--dashboard, --backend-only, --scan-once, --backtest, --port, --reset-capital)
        ├── AlgoMonitor.__init__(settings)
        │     ├── setup_logging(log_level)
        │     ├── get_database(database_path)  -> Initializes SQLite in WAL mode
        │     ├── CandleStore(db)
        │     ├── Scanner(strategy_config, db)
        │     ├── PaperTradingEngine(risk_config, db, options_config)
        │     ├── AlertManager(db) + ConsoleNotifier()
        │     ├── TradeManager(db, strategy_config, alert_manager)
        │     ├── BackgroundScheduler(daemon=True)
        │     └── create_app(db) (FastAPI Dashboard instance)
        ├── AlgoMonitor.start()
        │     ├── AlgoMonitor.initialise()
        │     │     ├── DeltaExchangeClient (if DELTA_API_KEY)
        │     │     ├── UpstoxAuthManager -> Automated TOTP 2FA Login -> UpstoxClient
        │     │     ├── IngestionService(store, delta_client, upstox_client)
        │     │     └── TelegramNotifier (if TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID)
        │     ├── scheduler.add_job(ingestion, 15m)
        │     ├── scheduler.add_job(scan, 5m)
        │     ├── scheduler.add_job(position_check, 30s)
        │     ├── scheduler.add_job(circuit_reset, daily 00:00)
        │     ├── scheduler.add_job(upstox_token_refresh, mon-fri 08:45 IST)
        │     ├── scheduler.start()
        │     ├── AlgoMonitor._start_websocket() -> DeltaWebSocketClient.start() (Background thread)
        │     ├── Background Bootstrap Thread -> Initial Scan -> Background Ingestion -> Re-scan
        │     └── AlgoMonitor._start_dashboard() -> uvicorn.run(app, host, port) [BLOCKING MAIN THREAD]
```

### 2. Module & Class Initialization Map
| Component | Class | File & Line | Lifetime & Threading |
| :--- | :--- | :--- | :--- |
| **Settings** | `Settings` | [algo_monitor/config/settings.py:L350](file:///d:/Projects/Algo%20Monitor/algo_monitor/config/settings.py#L350) | Singleton dataclass loaded from `.env` |
| **Database** | `Database` | [algo_monitor/database.py:L27](file:///d:/Projects/Algo%20Monitor/algo_monitor/database.py#L27) | Connection-per-thread dictionary (`threading.local`) |
| **Orchestrator** | `AlgoMonitor` | [algo_monitor/main.py:L38](file:///d:/Projects/Algo%20Monitor/algo_monitor/main.py#L38) | Primary lifecycle manager |
| **Candle Store** | `CandleStore` | [algo_monitor/data/candle_store.py:L32](file:///d:/Projects/Algo%20Monitor/algo_monitor/data/candle_store.py#L32) | CRUD operations on SQLite `candles` table |
| **Ingestion** | `IngestionService` | [algo_monitor/data/ingestion.py:L142](file:///d:/Projects/Algo%20Monitor/algo_monitor/data/ingestion.py#L142) | REST candle fetching, pagination, and sanitization |
| **Upstox Auth** | `UpstoxAuthManager` | [algo_monitor/data/upstox_auth.py:L23](file:///d:/Projects/Algo%20Monitor/algo_monitor/data/upstox_auth.py#L23) | Headless TOTP login and OAuth2 token handling |
| **Delta Client** | `DeltaExchangeClient` | [algo_monitor/data/delta_exchange.py:L28](file:///d:/Projects/Algo%20Monitor/algo_monitor/data/delta_exchange.py#L28) | Delta REST client (quotes, historical candles) |
| **Delta WS** | `DeltaWebSocketClient` | [algo_monitor/data/delta_exchange.py:L256](file:///d:/Projects/Algo%20Monitor/algo_monitor/data/delta_exchange.py#L256) | Background daemon thread streaming live tickers |
| **Scanner** | `Scanner` | [algo_monitor/strategy/scanner.py:L42](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/scanner.py#L42) | Multi-timeframe level & signal coordinator |
| **Level Detector** | `LevelDetector` | [algo_monitor/strategy/levels.py:L119](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/levels.py#L119) | Swing detection, clustering, polarity, scoring |
| **Signal Engine** | `SignalGenerator` | [algo_monitor/strategy/signals.py:L114](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/signals.py#L114) | Rule-based trigger evaluation for all setups |
| **Target Planner** | `AdaptiveTargetPlanner` | [algo_monitor/strategy/adaptive_target.py:L42](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/adaptive_target.py#L42) | Opposing S/R zone target projection |
| **Risk Engine** | `RiskManager` | [algo_monitor/risk/manager.py:L77](file:///d:/Projects/Algo%20Monitor/algo_monitor/risk/manager.py#L77) | Sizing, leverage bounds, circuit breaker |
| **Options Engine** | `OptionsEngine` | [algo_monitor/options/engine.py:L37](file:///d:/Projects/Algo%20Monitor/algo_monitor/options/engine.py#L37) | Black-Scholes Greeks, ATM strike selection |
| **Paper Engine** | `PaperTradingEngine` | [algo_monitor/trading/engine.py:L30](file:///d:/Projects/Algo%20Monitor/algo_monitor/trading/engine.py#L30) | Simulated execution, SL/TP checks, P&L tracking |
| **Trade Manager**| `TradeManager` | [algo_monitor/trading/trade_manager.py:L78](file:///d:/Projects/Algo%20Monitor/algo_monitor/trading/trade_manager.py#L78) | Open trade structural monitoring and advisory states |
| **Alert Manager**| `AlertManager` | [algo_monitor/alerts/notifier.py:L95](file:///d:/Projects/Algo%20Monitor/algo_monitor/alerts/notifier.py#L95) | Telegram/console routing, deduplication |
| **Web Server** | `FastAPI` (Uvicorn) | [algo_monitor/dashboard/app.py:L50](file:///d:/Projects/Algo%20Monitor/algo_monitor/dashboard/app.py#L50) | REST API & HTML terminal on port 8501 |

### 3. Background Jobs, Schedulers & Asynchronous Loops
The application utilizes [APScheduler](file:///d:/Projects/Algo%20Monitor/algo_monitor/main.py#L18) (`BackgroundScheduler(daemon=True)`) running on background worker threads, alongside one dedicated WebSocket network thread and one temporary bootstrap thread:

1. **Candle Ingestion Job (`_run_ingestion`):**  
   - **Frequency:** Every 15 minutes (`interval, minutes=15`, [main.py:L156-L162](file:///d:/Projects/Algo%20Monitor/algo_monitor/main.py#L156-L162)).
   - **Action:** Loops through all enabled instruments (`get_enabled_instruments()`). For Indian assets, requests `1d` and `5m` intervals. For Crypto assets, requests `1h`, `4h`, and `5m` intervals over a 90-day lookback window.
2. **Strategy Scanner Job (`_run_scan`):**  
   - **Frequency:** Every 5 minutes (`interval, minutes=5`, [main.py:L163-L169](file:///d:/Projects/Algo%20Monitor/algo_monitor/main.py#L163-L169)).
   - **Action:** Evaluates market data for each symbol. Identifies HTF zones, evaluates LTF completed candles for 6 core S/R setups plus optional modular setups (Head & Shoulders, Firsty Continuation), persists zones and signals to SQLite, issues alerts, and passes actionable trade setups to `PaperTradingEngine`.
3. **Position Monitor Job (`_update_positions`):**  
   - **Frequency:** Every 30 seconds (`interval, seconds=30`, [main.py:L170-L176](file:///d:/Projects/Algo%20Monitor/algo_monitor/main.py#L170-L176)).
   - **Action:** Queries open positions from `trades`. Resolves current prices from Delta WebSocket ticker cache or REST ticker fallbacks. Evaluates hard Stop-Loss, Take-Profit, and session expiries (intraday: 375m; swing: 14d). Additionally calls `TradeManager.evaluate_and_alert_trade()` to evaluate adaptive trade management advisories.
4. **Daily Circuit Breaker Reset Job (`_reset_daily_circuit`):**  
   - **Frequency:** Daily at 00:00 UTC (`cron, hour=0, minute=0`, [main.py:L178-L184](file:///d:/Projects/Algo%20Monitor/algo_monitor/main.py#L178-L184)).
   - **Action:** Resets `RiskManager._circuit_tripped` flag to False.
5. **Daily Upstox Token Auto-Refresh Job (`_refresh_upstox_token`):**  
   - **Frequency:** Monday to Friday at 08:45 AM IST (`cron, day_of_week="mon-fri", hour=8, minute=45`, [main.py:L186-L193](file:///d:/Projects/Algo%20Monitor/algo_monitor/main.py#L186-L193)).
   - **Action:** Executes automated headless TOTP authentication with Upstox, fetches a fresh bearer token, writes it to `system_state`, and reloads `UpstoxClient` before the 09:15 AM IST market open.
6. **Delta WebSocket Thread:**  
   - **Frequency:** Continuous event loop ([delta_exchange.py:L285-L335](file:///d:/Projects/Algo%20Monitor/algo_monitor/data/delta_exchange.py#L285-L335)).
   - **Action:** Maintains WebSocket connection to `wss://public-socket.india.delta.exchange`, sending heartbeats every 30 seconds, receiving live tickers, and updating `_latest_prices` dictionary in memory.
7. **FastAPI Web Server (Uvicorn):**  
   - **Frequency:** Continuous blocking event loop on main thread ([main.py:L430-L466](file:///d:/Projects/Algo%20Monitor/algo_monitor/main.py#L430-L466)).
   - **Action:** Serves UI and responds to REST polling requests. Includes automatic port collision resolution (+1 up to +50).

---

### 4. End-to-End Architecture & Data Flow Diagram

```mermaid
flowchart TD
    subgraph Market Data Feeds
        D_WS["Delta Exchange WebSocket<br/>(wss://public-socket.india.delta.exchange)"]
        D_REST["Delta Exchange REST API<br/>(/v2/history/candles, /v2/tickers)"]
        U_REST["Upstox API v2/v3<br/>(/v2/historical-candle, /v3/market-quote)"]
        U_AUTH["Upstox 2FA TOTP Auto-Auth<br/>(Scheduled 08:45 IST)"]
    end

    subgraph Data Ingestion & Storage Layer
        INGEST["IngestionService<br/>(Every 15 min via APScheduler)"]
        D_WS -->|Live Tickers| T_CACHE["_latest_prices In-Memory Cache"]
        D_REST -->|Historical Crypto OHLCV| INGEST
        U_REST -->|Historical Indian OHLCV| INGEST
        U_AUTH -->|Daily Bearer Token| U_REST
        INGEST -->|Sanitize & Strip Incomplete Bar| CSTORE["CandleStore"]
        CSTORE -->|Upsert OHLCV| DB_CANDLES[("SQLite Table: candles")]
    end

    subgraph Strategy Analysis Layer
        SCANNER["Scanner.scan_instrument<br/>(Every 5 min via APScheduler)"]
        DB_CANDLES -->|Query HTF: Daily/1h| SCANNER
        DB_CANDLES -->|Query LTF: 5m| SCANNER
        SCANNER -->|HTF Candles| LVL["LevelDetector.detect_zones<br/>• Swing Lookback (±3)<br/>• Prominence Filter<br/>• 0.5% Clustering<br/>• Polarity Flips<br/>• Zone Merging"]
        LVL -->|Top Ranked HTF S/R Zones| ZONES[("SQLite Table: zones")]
        
        ZONES --> SIG_GEN["SignalGenerator.generate_signals"]
        SCANNER -->|LTF Completed Candles| SIG_GEN
        
        SIG_GEN -->|Evaluate 6 Core S/R Rules| SETUPS{"Setup Detection<br/>• Bounce Support<br/>• Rejection Resistance<br/>• Breakout Resistance<br/>• Breakdown Support<br/>• Retest Breakout/Down<br/>• Approaching Zone"}
        SIG_GEN -->|Modular Extensions| MOD_SETUPS{"• Head & Shoulders<br/>• Firsty Continuation"}
        
        SETUPS --> TARGET_CALC["AdaptiveTargetPlanner<br/>(Anchor TP to nearest opposing zone)"]
        MOD_SETUPS --> TARGET_CALC
        TARGET_CALC --> SIG_OUT["Active Signal Object<br/>(entry, stop_loss, target, R:R)"]
        SIG_OUT --> DB_SIGNALS[("SQLite Table: signals")]
    end

    subgraph Risk Engine & Order Routing
        SIG_OUT --> PTE["PaperTradingEngine.process_signal"]
        PTE --> OPT_CHECK{"Is Indian Index &<br/>Options Enabled?"}
        
        OPT_CHECK -->|YES| OPT_ENG["OptionsEngine.prepare_trade_setup<br/>• ATM Strike Selection<br/>• Black-Scholes Greeks (Δ, IV)<br/>• Risk-defined Option Buy"]
        OPT_CHECK -->|NO| RM["RiskManager.evaluate<br/>• R:R >= 1.5 Floor<br/>• Circuit Breaker (5% max daily loss)<br/>• Max Positions (3)<br/>• Correlation / Duplicate Check<br/>• Continuous Sizing & Leverage Ceiling"]
        
        OPT_ENG --> OPEN_OPT["PaperTradingEngine._open_option_trade"]
        RM -->|Approved| OPEN_STD["PaperTradingEngine._open_trade"]
        RM -->|Rejected| REJ_LOG["Logged to Console / Ignored"]
        
        OPEN_OPT --> DB_TRADES[("SQLite Table: trades (status='open')")]
        OPEN_STD --> DB_TRADES
    end

    subgraph Real-Time Position Monitoring & Lifecycle
        P_CHECK["PaperTradingEngine.update_positions<br/>(Every 30s via APScheduler)"]
        T_CACHE -->|Live Prices| P_CHECK
        DB_TRADES -->|Active Open Trades| P_CHECK
        
        P_CHECK --> SL_TP_CHECK{"Price Breaches SL or TP?<br/>Session Expired?"}
        SL_TP_CHECK -->|YES| CLOSE_TRADE["PaperTradingEngine._close_trade<br/>• Realize P&L (FX converted)<br/>• Update Balance & Daily P&L"]
        CLOSE_TRADE --> DB_PNL[("SQLite Table: daily_pnl")]
        CLOSE_TRADE --> DB_STATE[("SQLite Table: system_state")]
        
        SL_TP_CHECK -->|NO| TM["TradeManager.evaluate_and_alert_trade<br/>• Thesis Invalidation<br/>• Consider Profit Taking<br/>• Consider Target Extension<br/>• Consider Stop Tightening"]
        TM --> DB_MGMT[("SQLite Table: trade_management")]
    end

    subgraph Delivery, UI & Telemetry
        SIG_OUT --> ALERT_MGR["AlertManager.send_signal_alert"]
        CLOSE_TRADE --> ALERT_MGR
        TM --> ALERT_MGR
        ALERT_MGR -->|Rate Limit 5m & Hash Deduplication| TG["Telegram Notifier"]
        ALERT_MGR --> CONSOLE["Console Logger"]
        
        FASTAPI["FastAPI Dashboard (Port 8501)<br/>/api/positions, /api/signals, /api/zones"]
        DB_TRADES --> FASTAPI
        DB_SIGNALS --> FASTAPI
        DB_PNL --> FASTAPI
        DB_STATE --> FASTAPI
        T_CACHE --> FASTAPI
        FASTAPI --> UI["Web Browser (Quant Terminal)"]
    end
```

---

### 5. Data Flow Trace: From Ingestion to Alert
1. **Ingestion:** `AlgoMonitor._run_ingestion()` calls `IngestionService.ingest()` every 15 minutes ([algo_monitor/data/ingestion.py:L162](file:///d:/Projects/Algo%20Monitor/algo_monitor/data/ingestion.py#L162)). Historical candles are fetched from Upstox or Delta, verified for chronological spacing and OHLC validity via `Candle.validate()`, and the trailing open/incomplete candle is discarded (`valid_candles.pop()`). Valid completed candles are upserted into SQLite (`candles` table).
2. **Scanner & Zones:** `AlgoMonitor._run_scan()` runs every 5 minutes ([algo_monitor/strategy/scanner.py:L59](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/scanner.py#L59)). For each symbol, `Scanner` pulls HTF candles (Daily for Upstox, 1-Hour rolling 72-hour window for Delta). `LevelDetector.detect_zones()` identifies swing highs/lows using a $\pm 3$ candle lookback, clusters them within 0.5% tolerance into horizontal bands, counts historical touch reactions, evaluates pin bar wicks, tests for polarity flips, and retains the top 20 zones ranked by composite strength. Active zones are saved to SQLite (`zones` table).
3. **Signals:** `Scanner` passes the latest 5-minute candles and active HTF zones to `SignalGenerator.generate_signals()` ([algo_monitor/strategy/signals.py:L134](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/signals.py#L134)). The last two completed 5-minute candles (`completed[-1]` and `completed[-2]`) are evaluated against the zones for 6 core setups plus modular pattern setups. If a setup matches, `AdaptiveTargetPlanner` calculates the initial target by locating the nearest opposing zone.
4. **Risk & Paper Execution:** Approved signals are passed to `PaperTradingEngine.process_signal()` ([algo_monitor/trading/engine.py:L122](file:///d:/Projects/Algo%20Monitor/algo_monitor/trading/engine.py#L122)). If the instrument is an Indian index and options are enabled, it is automatically routed to `OptionsEngine.prepare_trade_setup()`, which picks an ATM Call or Put and sizes it under capital constraints. Otherwise, `RiskManager.evaluate()` validates the setup against circuit breaker rules, maximum position limits (3), leverage ceilings (3.0x), and currency-adjusted stop-loss risk. Upon approval, an open paper trade record is written to SQLite (`trades` table, `status='open'`).
5. **Position Monitoring:** `AlgoMonitor._update_positions()` executes every 30 seconds ([algo_monitor/main.py:L335](file:///d:/Projects/Algo%20Monitor/algo_monitor/main.py#L335)). It queries open trades, pairs them with live ticker updates, and executes trade closures if price breaches Stop-Loss, Target, or session duration limits. For surviving trades, `TradeManager` generates situational advisories (`HOLD`, `PROFIT_TAKING`, `STOP_TIGHTENING`, `TARGET_EXTENSION`, or `THESIS_INVALIDATED`).
6. **Alerts & UI:** Whenever a signal is generated, a trade closed, or an advisory state changed, `AlertManager` formats an HTML payload, hashes the message to enforce deduplication, checks a 300-second rate limiter, and dispatches it to Telegram and the console. The FastAPI web dashboard queries SQLite and in-memory caches to update UI widgets.

---

### 6. Persistence Model: What Survives a Restart
| State Entity | Storage Medium | Survives Restart? | Notes / Source Location |
| :--- | :--- | :--- | :--- |
| **Historical Candles** | SQLite `candles` table | **YES** | Keyed by `(symbol, exchange, interval, timestamp)` ([database.py:L110](file:///d:/Projects/Algo%20Monitor/algo_monitor/database.py#L110)) |
| **S/R Zones** | SQLite `zones` table | **YES** | Active zones updated with `is_active=1` ([main.py:L280](file:///d:/Projects/Algo%20Monitor/algo_monitor/main.py#L280)) |
| **Signals** | SQLite `signals` table | **YES** | History preserved with timestamps ([main.py:L296](file:///d:/Projects/Algo%20Monitor/algo_monitor/main.py#L296)) |
| **Open Paper Trades** | SQLite `trades` table | **YES** | Read via `WHERE status = 'open'` ([trading/engine.py:L80](file:///d:/Projects/Algo%20Monitor/algo_monitor/trading/engine.py#L80)) |
| **Closed Paper Trades**| SQLite `trades` table | **YES** | Full historical audit trail preserved ([trading/engine.py:L85](file:///d:/Projects/Algo%20Monitor/algo_monitor/trading/engine.py#L85)) |
| **Paper Account Balance**| SQLite `system_state` | **YES** | Persisted under key `"paper_balance"` ([trading/engine.py:L60-L75](file:///d:/Projects/Algo%20Monitor/algo_monitor/trading/engine.py#L60-L75)) |
| **Daily Realized P&L** | SQLite `daily_pnl` table| **YES** | Grouped by date string `YYYY-MM-DD` ([trading/engine.py:L563](file:///d:/Projects/Algo%20Monitor/algo_monitor/trading/engine.py#L563)) |
| **Market Toggles** | SQLite `system_state` | **YES** | Keys: `"market_toggle_indian"`, `"market_toggle_crypto"` |
| **Upstox Bearer Token**| SQLite `system_state` | **YES** | Key: `"upstox_access_token"` ([upstox_auth.py:L142](file:///d:/Projects/Algo%20Monitor/algo_monitor/data/upstox_auth.py#L142)) |
| **Trade Advisories** | SQLite `trade_management` | **YES** | Keyed by `(trade_id, recommendation, proposed_target)` |
| **Recent Signal Cache**| In-memory `set` | **NO** | `SignalGenerator._recent_signal_ids` wipes on reboot ([signals.py:L132](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/signals.py#L132)) |
| **Live Price Ticker Cache**| In-memory `dict` | **NO** | `_latest_prices` wipes; repopulates via WS/REST ([main.py:L96](file:///d:/Projects/Algo%20Monitor/algo_monitor/main.py#L96)) |
| **WebSocket Connection**| Network Socket | **NO** | Re-established on boot with auto-reconnect ([main.py:L405](file:///d:/Projects/Algo%20Monitor/algo_monitor/main.py#L405)) |
| **Circuit Breaker Flag**| In-memory `bool` | **NO / PARTIAL**| Flag in `RiskManager` wipes on reboot, but checked against `daily_realised_pnl` |

---

### 7. Failure Modes and Resilience Matrix
- **Upstox API Failure / 401 Unauthorized:**  
  Handled by `UpstoxClient._auto_refresh_if_unauthorized()` ([algo_monitor/data/upstox.py:L43-L55](file:///d:/Projects/Algo%20Monitor/algo_monitor/data/upstox.py#L43-L55)). If a request returns HTTP 401, the client automatically calls `UpstoxAuthManager.fetch_new_token()` using headless TOTP, updates its internal headers, and retries. If the network drops or the API is offline, errors are logged and empty candle lists are returned without crashing the engine.
- **Delta WebSocket Disconnection:**  
  Handled by `DeltaWebSocketClient._run_loop()` ([algo_monitor/data/delta_exchange.py:L285-L335](file:///d:/Projects/Algo%20Monitor/algo_monitor/data/delta_exchange.py#L285-L335)). It implements automatic reconnection with exponential backoff starting at 1s up to 60s. During disconnection, the position monitor automatically falls back to REST ticker endpoints (`get_ticker()`).
- **Database Locked / SQLite Busy:**  
  The database connection enables Write-Ahead Logging (`PRAGMA journal_mode=WAL`) and sets a busy timeout of 5,000ms (`PRAGMA busy_timeout=5000`, [algo_monitor/database.py:L45-L47](file:///d:/Projects/Algo%20Monitor/algo_monitor/database.py#L45-L47)). Write collisions between background workers and web requests will retry for up to 5 seconds before raising an operational error.
- **Scheduler Failure:**  
  APScheduler runs with `daemon=True`. Unhandled exceptions within individual scheduled jobs (`_run_ingestion`, `_run_scan`, `_update_positions`) are caught inside top-level `try...except Exception as exc:` blocks ([main.py:L231](file:///d:/Projects/Algo%20Monitor/algo_monitor/main.py#L231), [L332](file:///d:/Projects/Algo%20Monitor/algo_monitor/main.py#L332), [L389](file:///d:/Projects/Algo%20Monitor/algo_monitor/main.py#L389)). A failure in one cycle is logged as an error, and the scheduler proceeds to trigger the next interval normally.
- **Telegram Outage:**  
  Calls to the Telegram Bot API use `httpx.post()` with a 15-second timeout inside `try...except` ([algo_monitor/alerts/notifier.py:L63-L89](file:///d:/Projects/Algo%20Monitor/algo_monitor/alerts/notifier.py#L63-L89)). If Telegram is unreachable, it logs a warning and returns `False`. The core trading engine and database persistence remain unaffected.

---

## PART 2 — Markets, Instruments, and Timeframe Mechanics

### Supported Instruments Overview
The application classifies instruments into two market categories via `Instrument` dataclass in [algo_monitor/config/instruments.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/config/instruments.py#L44-L74):
1. **Indian Market (`MarketCategory.INDIAN`):** 4 Indices and 38 F&O Equity Securities traded via Upstox.
2. **Crypto Derivatives (`MarketCategory.CRYPTO`):** 12 Perpetual Futures traded via Delta Exchange India.
3. **Gold-Related Instruments:** **None configured.** A codebase search for "gold" reveals only CSS frontend color definitions (`--gold: #f59e0b;`) in stylesheets and UI badges. No commodity gold contracts (such as MCX GOLD or PAXG) exist in `instruments.py`.

```
=================================================================================================
                            CONFIGURED INSTRUMENT ROSTER
=================================================================================================
[INDIAN MARKET — INDICES] (4 Instruments)
  • NIFTY50             (Upstox: "NSE_INDEX|Nifty 50")
  • BANKNIFTY           (Upstox: "NSE_INDEX|Nifty Bank")
  • NIFTYAUTO           (Upstox: "NSE_INDEX|Nifty Auto")
  • NIFTYMIDCAPSELECT   (Upstox: "NSE_INDEX|NIFTY MID SELECT")

[INDIAN MARKET — F&O EQUITIES] (38 Configured, 37 Active, 1 Disabled)
  • Nifty 50 Constituents (12): RELIANCE, TCS, HDFCBANK, INFY, ICICIBANK, BHARTIARTL,
                                SBIN, ITC, HINDUNILVR, KOTAKBANK, LT, AXISBANK
  • Bank Nifty Focus (6):       INDUSINDBK, BANKBARODA, FEDERALBNK, PNB, AUBANK, IDFCFIRSTB
  • Nifty Auto Focus (10):      TATAMOTORS, M&M, MARUTI, BAJAJ-AUTO, HEROMOTOCO,
                                EICHERMOT, ASHOKLEY, BALKRISIND, TVSMOTOR, MRF
  • Midcap Select Focus (10):   DIXON, PERSISTENT, MPHASIS, VOLTAS, CUMMINSIND,
                                INDHOTEL, OBEROIRLTY, COFORGE, SUPREMEIND
                                (FEDERALBNK_MID is explicitly disabled to avoid duplicate)

[CRYPTO MARKET — DELTA PERPETUAL FUTURES] (12 Instruments)
  • Major USD Perpetuals:       BTCUSD, ETHUSD, SOLUSD, XRPUSD, BNBUSD, DOGEUSD,
                                AVAXUSD, LINKUSD, NEARUSD, DOTUSD, SUIUSD, PEPEUSD
=================================================================================================
```

---

### Detailed Market Properties Specification Table

| Property | Indian Market (Indices & Stocks) | Crypto Derivatives (Perpetuals) |
| :--- | :--- | :--- |
| **Primary Data Provider** | Upstox API v2 / v3 ([upstox.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/data/upstox.py)) | Delta Exchange India ([delta_exchange.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/data/delta_exchange.py)) |
| **Configured Products** | 4 NSE Indices + 37 active NSE equities | 12 USD Perpetual Futures |
| **Entry Timeframe (LTF)** | `5m` (5-minute completed bars) | `5m` (5-minute completed bars) |
| **Context Timeframe (HTF)**| `1d` (Daily candles; config fallback: `indian_htf_interval="1d"`) | `1h` (1-hour candles within rolling 72-hour window) |
| **Historical Data Window** | Up to 365 calendar days for Daily; up to 100 days for 5m | Rolling 72-hour window for 1h; 300 bars for 5m |
| **Live Ingestion Source** | REST Polling (`/v3/market-quote/quotes` & `ltp`) | WebSocket (`wss://public-socket.india.delta.exchange`) |
| **Data Fallback** | Static/cached prices in `_DEFAULT_PRICES` ([app.py:L1367](file:///d:/Projects/Algo%20Monitor/algo_monitor/dashboard/app.py#L1367)) | REST Ticker `/v2/tickers/{symbol}` ([delta_exchange.py:L119](file:///d:/Projects/Algo%20Monitor/algo_monitor/data/delta_exchange.py#L119)) |
| **Scan Frequency** | Every 5 minutes via APScheduler | Every 5 minutes via APScheduler |
| **Trading Style** | Intraday (default) or Swing | Intraday (default) or Swing |
| **Session Rules** | Mon–Fri 09:15–15:30 IST; weekends & holidays closed | Continuous 24/7/365; no weekend or holiday halts |
| **Options Routing** | ATM Call/Put buying via `OptionsEngine` for indices | Perpetuals only (Options Engine supports BTC/ETH in math) |

---

### Candle Handling, Timestamps, and Timeframe Discrepancies

#### 1. The Timeframe Aliasing Bug and Its Resolution
In earlier versions of the codebase, Upstox API v2 calls for `5minute` were returning HTTP 400 Bad Request. To circumvent this, the historical ingestion service mapped `"5m" → "30minute"` and `"4h" → "day"`. As a result, 30-minute bars were being stored in SQLite labeled as `interval="5m"`, and daily bars were stored labeled as `interval="4h"`.

In the current code:
- **Upstox Interval Fix (P0-A):** In [algo_monitor/data/ingestion.py:L58-L67](file:///d:/Projects/Algo%20Monitor/algo_monitor/data/ingestion.py#L58-L67), the dictionary now maps `"5m" → "5minute"` and `"1d" → "day"`. "4h" is rejected for Upstox because the API does not natively support 4-hour aggregation.
- **Duration Verification:** `check_candle_duration()` in [ingestion.py:L95-L140](file:///d:/Projects/Algo%20Monitor/algo_monitor/data/ingestion.py#L95-L140) and `CandleStore.upsert_candles()` in [candle_store.py:L49-L68](file:///d:/Projects/Algo%20Monitor/algo_monitor/data/candle_store.py#L49-L68) compute the median second gap of incoming candles. If a candle labeled `"5m"` exhibits a median gap near 1800s (30m), `CandleStore` raises a `ValueError` to block corrupt data from polluting the database.
- **Local Resampling:** The application **does not perform dynamic algorithmic candle resampling** (e.g., aggregating five 1-minute bars into a 5-minute bar using Pandas). It relies strictly on the native candle aggregations returned by the exchange APIs.

#### 2. Open vs. Completed Candles
To prevent intra-candle noise and look-ahead bias:
- During ingestion, the trailing uncompleted candle is discarded:
  ```python
  if valid_candles and not valid_candles[-1].is_complete:
      valid_candles.pop()
  ```
- During scanning, `SignalGenerator` filters:
  ```python
  completed = [c for c in candles if c.is_complete]
  ```
  Only closed bars (`completed[-1]` as `current` and `completed[-2]` as `prev`) trigger strategy signals.

#### 3. Timestamps and Timezones
- All internal candle timestamps are converted to **UTC timezone-aware Python `datetime` objects** and stored in SQLite as ISO-8601 strings (e.g., `2026-10-16T18:20:00+00:00`).
- Indian market sessions operate between 09:15 and 15:30 IST (03:45 to 10:00 UTC). `is_indian_market_hours()` ([algo_monitor/strategy/scanner.py:L27-L40](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/scanner.py#L27-L40)) shifts UTC time to IST (`UTC+05:30`) to evaluate market open/close boundaries.

#### 4. Stale Market Data and Historical Suppression
In [algo_monitor/strategy/scanner.py:L157-L177](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/scanner.py#L157-L177):
- For Indian assets during live market hours, candles older than **6 hours (21,600s)** are treated as historical data. Outside market hours, candles older than **2 hours (7,200s)** are treated as historical data.
- When market data is stale, **zone detection still executes** (enabling chart visualization on the dashboard), but **signal generation is suppressed**. This prevents the system from issuing phantom alerts when restarting on weekends or after hours.

---

## PART 3 — Support and Resistance Detection Engine

The Support and Resistance detection algorithm is located in [algo_monitor/strategy/levels.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/levels.py#L119-L615).

```
Historical Candles (HTF)
       │
       ▼
[find_swing_points] ──► Lookback Window ±3 candles; Prominence filter (ATR * 0.3 or 0.25%)
       │
       ▼
[cluster_into_zones] ──► Group swings of same polarity within 0.5% tolerance
       │                 Enforce min_zone_width_pct (0.20% or ATR * 0.25)
       ▼
[_count_touches] ─────► Scan all candles for reaction touches & rejection wicks (>= 35% of range)
       │                 Assign freshness score (1.0 for <=3 touches; 0.40 for >5 touches)
       ▼
[update_polarity_flips]► Flip broken Resistance -> Support or Support -> Resistance
       │                 (Requires 2 consecutive closes > 0.5% beyond zone boundary)
       ▼
[merge_overlapping] ──► Merge overlapping zones of same polarity to eliminate clutter
       │
       ▼
[_score_zones] ───────► Composite Strength = (0.25*T + 0.25*Rej + 0.25*Rec + 0.25*Prox) * Freshness
       │
       ▼
[Sort & Cap] ─────────► Retain top 20 zones with >= 2 touches (discard broken zones)
```

---

### Step-by-Step Algorithm Breakdown

#### 1. Swing High and Swing Low Mechanics
Implemented in `LevelDetector.find_swing_points()` ([levels.py:L146-L230](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/levels.py#L146-L230)):
- **Lookback Window:** Uses `swing_lookback = 3` (configurable in `StrategyConfig`). A candidate candle $i$ must be compared against 3 closed candles before it and 3 closed candles after it. Total window size is $2 \times 3 + 1 = 7$ candles.
- **Swing High Condition:** $\text{candles}[i].\text{high} \ge \text{candles}[j].\text{high}$ for all $j \in [i - 3, i + 3]$ where $j \ne i$.
- **Swing Low Condition:** $\text{candles}[i].\text{low} \le \text{candles}[j].\text{low}$ for all $j \in [i - 3, i + 3]$ where $j \ne i$.
- **Confirmation Delay:** Iteration bounds are `for i in range(self.lookback, n - self.lookback)`. Because index $n-1$ is the latest candle, the latest candidate candle evaluated is $n - 4$. **The current candle and the two preceding candles can never be identified as swings.** Confirmation requires an exact **3-candle delay**. On a 1-hour chart, a swing high is confirmed 3 hours after the peak; on a Daily chart, it is confirmed 3 trading days later.
- **Prominence Filter:** Insignificant wicks in tight ranges are filtered out. A candidate swing must stand out from its neighboring troughs/crests by at least:
  $$\text{Prominence} = \min(\text{depth}_{\text{left}}, \text{depth}_{\text{right}}) \ge \max\left(P \times \frac{\text{min\_prominence\_pct}}{100}, 0.3 \times \text{ATR}_{14}\right)$$
  Default `min_prominence_pct` is `0.25%`.

#### 2. Zone Clustering and Width Enclosure
Implemented in `_cluster_one_type()` ([levels.py:L442-L465](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/levels.py#L442-L465)):
- Support swings and Resistance swings are clustered **strictly separately**.
- Swings are sorted by price ascending. The algorithm iterates through them, tracking a running `group_avg`. If a swing's price is within `zone_tolerance_pct` (default: **0.5%**) of the group average:
  $$\text{distance\_pct} = \frac{|\text{swing.price} - \text{group\_avg}|}{\text{group\_avg}} \times 100 \le 0.5\%$$
  it is appended to the group. Otherwise, the current group is closed into a `Zone` and a new group begins.
- **Boundaries:** The raw boundaries are the lowest and highest constituent swing prices:
  $$\text{price\_low} = \min(P_{\text{group}}), \quad \text{price\_high} = \max(P_{\text{group}})$$
- **Minimum Zone Width:** To prevent single-line horizontal levels that get violated by fractional ticks, `_group_to_zone()` ([levels.py:L466-L505](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/levels.py#L466-L505)) enforces a minimum width:
  $$\text{min\_width} = \max\left(\text{mid} \times \frac{\text{min\_zone\_width\_pct}}{100}, 0.25 \times \text{ATR}_{14}\right)$$
  Default `min_zone_width_pct` is `0.20%`. If $\text{price\_high} - \text{price\_low} < \text{min\_width}$, the zone is padded symmetrically around `mid_price`.

#### 3. Touch Counting and Rejection Behavior
Implemented in `_count_touches()` ([levels.py:L506-L569](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/levels.py#L506-L569)):
The algorithm scans all historical candles to identify reactive tests:
- **Support Touch:** $\text{candle.low} \le \text{zone.price\_high}$ AND $\text{candle.low} \ge \text{zone.price\_low} \times 0.99$ AND $\text{candle.close} > \text{zone.price\_high}$.
  *(Price entered the zone from above and closed back outside above it)*.
- **Resistance Touch:** $\text{candle.high} \ge \text{zone.price\_low}$ AND $\text{candle.high} \le \text{zone.price\_high} \times 1.01$ AND $\text{candle.close} < \text{zone.price\_low}$.
  *(Price entered the zone from below and closed back outside below it)*.
- **Rejection Wick Detection:** A touch is credited with a "clean rejection" if the candle formed a strong rejection wick pointing into the zone:
  - Support: $\text{lower\_wick} = \min(\text{open}, \text{close}) - \text{low} \ge 0.35 \times (\text{high} - \text{low})$
  - Resistance: $\text{upper\_wick} = \text{high} - \max(\text{open}, \text{close}) \ge 0.35 \times (\text{high} - \text{low})$

#### 4. Freshness Scoring
Recognizing that an over-tested level becomes fragile, `levels.py:L557-L564` applies a freshness multiplier:
- $1 \le \text{touches} \le 3$: $\text{freshness\_score} = 1.00$ (Highest quality, unabsorbed institutional liquidity).
- $4 \le \text{touches} \le 5$: $\text{freshness\_score} = 0.75$.
- $\text{touches} > 5$: $\text{freshness\_score} = 0.40$ (Penalized; level is absorbed and prone to breakout).

#### 5. Polarity Flips & Zone Invalidation
Implemented in `update_polarity_flips()` ([levels.py:L307-L360](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/levels.py#L307-L360)):
- When price breaks through a zone, the code checks if the trailing candles closed beyond the zone by at least `zone_invalidation_threshold_pct` (default: **0.5%**) for `zone_invalidation_closes` (default: **2**) consecutive bars:
  - Support breakdown: 2 consecutive closes $< \text{price\_low} \times (1 - 0.005)$.
  - Resistance breakout: 2 consecutive closes $> \text{price\_high} \times (1 + 0.005)$.
- If confirmed and `enable_polarity_flips = True`:
  - Resistance flips to **Support** (`zone.is_flipped = True`, `zone.touches = 1`).
  - Support flips to **Resistance** (`zone.is_flipped = True`, `zone.touches = 1`).
- If polarity flips are disabled (`enable_polarity_flips = False`), `invalidate_broken_zones()` marks `zone.is_broken = True`, which causes it to be filtered out.

#### 6. Anti-Clutter Merging of Overlapping Zones
Implemented in `merge_overlapping_zones()` ([levels.py:L393-L434](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/levels.py#L393-L434)):
Zones of the same polarity are sorted by `price_low`. If adjacent zones overlap:
$$\text{prev.price\_high} + \text{margin} \ge \text{current.price\_low}$$
they are consolidated into a single master zone spanning $[\min(\text{low}_1, \text{low}_2), \max(\text{high}_1, \text{high}_2)]$, summing touches and merging constituent swing prices.

#### 7. Composite Strength Score Formula
Implemented in `_score_zones()` ([levels.py:L570-L614](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/levels.py#L570-L614)):
$$\text{Raw Strength} = 0.25 \times \text{touch\_score} + 0.25 \times \text{rejection\_score} + 0.25 \times \text{recency\_score} + 0.25 \times \text{proximity\_score}$$
$$\text{Final Strength} = \text{round}(\text{Raw Strength} \times \text{freshness\_score}, 2)$$
Where:
- $\text{touch\_score} = \min\left(\frac{\text{touches}}{\max(\text{max\_touches}, 1)}, 1.0\right)$
- $\text{rejection\_score} = \frac{\text{rejection\_count}}{\max(\text{max\_rejections}, 1)}$
- $\text{recency\_score} = \frac{1}{1 + \frac{\text{days\_ago}}{30}}$ (30-day exponential half-life decay)
- $\text{proximity\_score} = \frac{1}{1 + \frac{\text{distance\_pct}}{5}}$ (Distance from current reference price)

#### 8. Pruning and Retention
- Zones must have at least `min_touches` (default: **2**) to survive ([levels.py:L289](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/levels.py#L289)).
- Surviving zones are sorted descending by `strength`. The array is capped at `max_zones` (default: **20**).

---

### Quantitative vs. Human Chart Interpretation vs. Missing Calculations

```
┌──────────────────────────────────────┬──────────────────────────────────────┬──────────────────────────────────────┐
│       WHAT THE ALGORITHM DOES        │       WHAT A TRADER INTERPRETS       │      WHAT THE CODE DOES NOT DO       │
├──────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────┤
│ Evaluates fixed ±3 bar local extremes│ Subjectively spots "obvious" peaks   │ Does NOT use dynamic ZigZag pivots   │
│ Requires 0.25% or 0.3*ATR prominence │ Visualizes major swing reversals     │ Does NOT consider volume profile/POC │
│ Groups within static 0.5% tolerance  │ Draws subjective diagonal trendlines │ Does NOT draw diagonal trendlines    │
│ Evaluates 2 closes beyond 0.5%       │ Considers a single wick as broken    │ Does NOT assess orderbook depth      │
│ Requires 35% wick for rejection      │ Interprets candlestick psychology    │ Does NOT track multi-year macro S/R  │
└──────────────────────────────────────┴──────────────────────────────────────┴──────────────────────────────────────┘
```

---

## PART 4 — Comprehensive Setup and Entry Signal Catalogue

All trading setups are implemented in [algo_monitor/strategy/signals.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/signals.py), [algo_monitor/strategy/head_and_shoulders.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/head_and_shoulders.py), and [algo_monitor/strategy/trend_continuation.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/trend_continuation.py).

Every setup requires completed candles (`completed[-1]` as `current`, `completed[-2]` as `prev`).

---

### Setup 1: Bounce from Support (`BOUNCE_SUPPORT`)
- **File & Function:** [algo_monitor/strategy/signals.py:L332-L396](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/signals.py#L332-L396) (`_check_bounce_support`)
- **Target Market Behavior:** Price declines into an established Higher Timeframe support zone, finds buying demand, and reverses upward, forming a confirmed bullish candle.
- **Exact Detection Rules (Evaluated in strict sequence):**
  1. `zone.zone_type == ZoneType.SUPPORT` and `zone.is_broken == False`.
  2. Previous candle low penetrated into or slightly below the support zone:  
     `prev.low <= zone.price_high` AND `prev.low >= zone.price_low * 0.995`.
  3. Current candle confirmed a bounce: closed strictly above the top of the zone:  
     `current.close > zone.price_high`.
  4. Current candle is bullish: `current.is_bullish` (`current.close > current.open`).
- **Entry Timing & Price Construction:**
  - **Trigger:** Immediate close of the confirming 5-minute candle.
  - **Entry Reference Price ($P_{\text{entry}}$):** `current.close`.
  - **Stop-Loss Price ($P_{\text{sl}}$):** `zone.price_low * 0.995` (0.5% below the lower boundary of the support zone).
  - **Risk Distance ($R$):** $P_{\text{entry}} - P_{\text{sl}}$. (Must be $> 0$).
  - **Take-Profit Target ($P_{\text{target}}$):** Computed via `AdaptiveTargetPlanner` as $\text{opposing\_resistance.price\_low} - \text{buffer}$. If no opposing zone exists, falls back to $P_{\text{entry}} + 1.5 \times R$.
- **Hypothetical Numerical Example:**
  - Support Zone: $[24,780.00 - 24,800.00]$
  - Previous 5m Candle: Open = $24,820$, High = $24,825$, Low = $24,790$ (enters zone), Close = $24,795$.
  - Current 5m Candle: Open = $24,796$, Low = $24,792$, High = $24,818$, Close = $24,815$ (bullish, closed above $24,800$).
  - **Result:** LONG signal generated.
    - $P_{\text{entry}} = 24,815.00$
    - $P_{\text{sl}} = 24,780.00 \times 0.995 = 24,656.10$
    - $R = 24,815.00 - 24,656.10 = 158.90$
    - Target (at 1.5R fallback): $24,815.00 + (1.5 \times 158.90) = 25,053.35$.
- **Invalidation & Limitations:** A close below $24,656.10$ invalidates the setup. False signals occur during high-momentum market dumps where a minor green candle closes 1 point above the zone before continuation downward.

---

### Setup 2: Rejection from Resistance (`REJECTION_RESISTANCE`)
- **File & Function:** [algo_monitor/strategy/signals.py:L397-L458](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/signals.py#L397-L458) (`_check_rejection_resistance`)
- **Target Market Behavior:** Price rallies into an established resistance zone, encounters institutional supply, and closes back below the zone as a bearish candle.
- **Exact Detection Rules:**
  1. `zone.zone_type == ZoneType.RESISTANCE` and `zone.is_broken == False`.
  2. Previous candle high penetrated into the resistance zone:  
     `prev.high >= zone.price_low` AND `prev.high <= zone.price_high * 1.005`.
  3. Current candle confirmed rejection: closed strictly below the bottom of the zone:  
     `current.close < zone.price_low`.
  4. Current candle is bearish: `current.is_bearish` (`current.close < current.open`).
- **Entry Timing & Price Construction:**
  - **Trigger:** Immediate close of confirming 5-minute candle.
  - **Entry Reference Price ($P_{\text{entry}}$):** `current.close`.
  - **Stop-Loss Price ($P_{\text{sl}}$):** `zone.price_high * 1.005` (0.5% above resistance top).
  - **Risk Distance ($R$):** $P_{\text{sl}} - P_{\text{entry}}$.
  - **Take-Profit Target ($P_{\text{target}}$):** Nearest opposing support zone top $+ \text{buffer}$, or $P_{\text{entry}} - 1.5 \times R$.
- **Hypothetical Numerical Example:**
  - Resistance Zone: $[83,000.00 - 83,200.00]$
  - Previous 5m Candle: High = $83,150.00$ (inside zone), Close = $83,080.00$.
  - Current 5m Candle: Open = $83,075.00$, High = $83,090.00$, Low = $82,920.00$, Close = $82,940.00$ (bearish, closed below $83,000.00$).
  - **Result:** SHORT signal generated.
    - $P_{\text{entry}} = 82,940.00$
    - $P_{\text{sl}} = 83,200.00 \times 1.005 = 83,616.00$
    - $R = 83,616.00 - 82,940.00 = 676.00$
    - Target: $82,940.00 - (1.5 \times 676.00) = 81,926.00$.
- **Invalidation & Limitations:** A close above $83,616.00$ invalidates the setup. Prone to generating premature short entries during aggressive parabolic breakout rallies.

---

### Setup 3: Breakout above Resistance (`BREAKOUT_RESISTANCE`)
- **File & Function:** [algo_monitor/strategy/signals.py:L459-L523](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/signals.py#L459-L523) (`_check_breakout_resistance`)
- **Target Market Behavior:** Strong bullish momentum pushes price completely through an overhead resistance zone, establishing institutional acceptance above the barrier.
- **Exact Detection Rules:**
  1. `zone.zone_type == ZoneType.RESISTANCE`.
  2. Previous candle closed below zone top: `prev.close < zone.price_high`.
  3. Current candle closed decisively above zone top by at least `breakout_threshold_pct` (default: **0.3%**):  
     `current.close >= zone.price_high * (1 + 0.003)`.
  4. Candle body filter: Candle must exhibit decisive expansion:  
     `current.body_size / current.range_size >= 0.40` (Real body covers $\ge 40\%$ of total high-to-low range).
- **Entry Timing & Price Construction:**
  - **Trigger:** Immediate close of breakout candle.
  - **Entry Reference Price ($P_{\text{entry}}$):** `current.close`.
  - **Stop-Loss Price ($P_{\text{sl}}$):** `zone.price_low * 0.998` (0.2% below the bottom of the broken resistance zone).
  - **Risk Distance ($R$):** $P_{\text{entry}} - P_{\text{sl}}$.
  - **Take-Profit Target ($P_{\text{target}}$):** Next opposing overhead resistance zone minus clearance buffer, or $P_{\text{entry}} + 1.5 \times R$.
- **Hypothetical Numerical Example:**
  - Resistance Zone: $[2,920.00 - 2,940.00]$
  - Breakout Threshold ($+0.3\%$): $2,940.00 \times 1.003 = 2,948.82$
  - Previous 5m Candle: Close = $2,935.00$
  - Current 5m Candle: Open = $2,936.00$, Low = $2,934.00$, High = $2,956.00$, Close = $2,952.00$ (Range = $22.00$, Body = $16.00$, Body Ratio = $72.7\% \ge 40\%$).
  - **Result:** LONG signal generated.
    - $P_{\text{entry}} = 2,952.00$
    - $P_{\text{sl}} = 2,920.00 \times 0.998 = 2,914.16$
    - $R = 2,952.00 - 2,914.16 = 37.84$
    - Target: $2,952.00 + (1.5 \times 37.84) = 3,008.76$.
- **Invalidation & Limitations:** A close back below $2,940.00$ signifies a false breakout ("bull trap"). Stop-loss distance can be large if the breakout candle is exceptionally long.

---

### Setup 4: Breakdown below Support (`BREAKDOWN_SUPPORT`)
- **File & Function:** [algo_monitor/strategy/signals.py:L525-L586](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/signals.py#L525-L586) (`_check_breakdown_support`)
- **Target Market Behavior:** Aggressive selling pushes price decisively through a major support zone, triggering stop runs and signaling downward trend continuation.
- **Exact Detection Rules:**
  1. `zone.zone_type == ZoneType.SUPPORT`.
  2. Previous candle closed above zone bottom: `prev.close > zone.price_low`.
  3. Current candle closed decisively below zone bottom by at least `breakout_threshold_pct` (**0.3%**):  
     `current.close <= zone.price_low * (1 - 0.003)`.
  4. Candle body filter: `current.body_size / current.range_size >= 0.40`.
- **Entry Timing & Price Construction:**
  - **Trigger:** Close of the breakdown candle.
  - **Entry Reference Price ($P_{\text{entry}}$):** `current.close`.
  - **Stop-Loss Price ($P_{\text{sl}}$):** `zone.price_high * 1.002` (0.2% above broken support top).
  - **Risk Distance ($R$):** $P_{\text{sl}} - P_{\text{entry}}$.
  - **Take-Profit Target ($P_{\text{target}}$):** Next opposing lower support zone plus buffer, or $P_{\text{entry}} - 1.5 \times R$.
- **Hypothetical Numerical Example:**
  - Support Zone: $[1,640.00 - 1,650.00]$
  - Breakdown Threshold ($-0.3\%$): $1,640.00 \times 0.997 = 1,635.08$
  - Current 5m Candle: Open = $1,642.00$, High = $1,643.00$, Low = $1,630.00$, Close = $1,632.00$ (Body = $10.00$, Range = $13.00$, Ratio = $76.9\%$).
  - **Result:** SHORT signal generated.
    - $P_{\text{entry}} = 1,632.00$
    - $P_{\text{sl}} = 1,650.00 \times 1.002 = 1,653.30$
    - $R = 1,653.30 - 1,632.00 = 21.30$
    - Target: $1,632.00 - (1.5 \times 21.30) = 1,600.05$.
- **Invalidation & Limitations:** A close back above $1,640.00$ indicates a bear trap.

---

### Setup 5: Breakout Retest (`RETEST_BREAKOUT`)
- **File & Function:** [algo_monitor/strategy/signals.py:L588-L658](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/signals.py#L588-L658) (`_check_retest`)
- **Target Market Behavior:** After breaking out above resistance, price pulls back to retest the top of the broken zone (polarity transition: old resistance acting as new support) and resumes upward.
- **Exact Detection Rules:**
  1. `zone.zone_type == ZoneType.RESISTANCE`.
  2. Prior Breakout Verification: In the preceding 10 to 20 candles (excluding `current` and `prev`), at least one candle closed above `zone.price_high * 1.002`.
  3. Proximity Retest Tolerance: Current candle low tested within `retest_tolerance_pct` (default: **0.5%**) of `zone.price_high`:  
     $|current.\text{low} - zone.\text{price\_high}| \le zone.\text{mid\_price} \times 0.005$.
  4. Confirmation: `current.close > zone.price_high` AND `current.is_bullish`.
- **Entry Timing & Price Construction:**
  - **Entry Reference Price ($P_{\text{entry}}$):** `current.close`.
  - **Stop-Loss Price ($P_{\text{sl}}$):** `zone.price_low * 0.998` (0.2% below zone bottom).
  - **Take-Profit Target ($P_{\text{target}}$):** Nearest overhead resistance or $1.5R$ fallback.
- **Hypothetical Numerical Example:**
  - Resistance Zone: $[104.50 - 105.00]$
  - 8 bars ago, price broke out to $107.00$.
  - Current 5m Candle: Pulls back to Low = $105.10$ (Retest tolerance of mid 104.75 is $\pm 0.52$; $105.10 - 105.00 = 0.10 \le 0.52$), and closes bullish at $105.80$.
  - **Result:** LONG signal generated ($P_{\text{entry}} = 105.80$, $P_{\text{sl}} = 104.29$).

---

### Setup 6: Breakdown Retest (`RETEST_BREAKDOWN`)
- **File & Function:** [algo_monitor/strategy/signals.py:L660-L706](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/signals.py#L660-L706) (`_check_retest`)
- **Target Market Behavior:** After breaking down below support, price bounces back up to retest the bottom of the broken zone (old support acting as new resistance) and resumes downward.
- **Exact Detection Rules:**
  1. `zone.zone_type == ZoneType.SUPPORT`.
  2. Prior Breakdown Verification: In preceding 10 to 20 candles, at least one candle closed below `zone.price_low * 0.998`.
  3. Retest Tolerance: $|current.\text{high} - zone.\text{price\_low}| \le zone.\text{mid\_price} \times 0.005$.
  4. Confirmation: `current.close < zone.price_low` AND `current.is_bearish`.
- **Entry Timing & Price Construction:**
  - **Entry Reference Price ($P_{\text{entry}}$):** `current.close`.
  - **Stop-Loss Price ($P_{\text{sl}}$):** `zone.price_high * 1.002`.
  - **Take-Profit Target ($P_{\text{target}}$):** Nearest lower support or $1.5R$ fallback.

---

### Setup 7: Approaching Zone (`APPROACHING_ZONE` — Informational Alert)
- **File & Function:** [algo_monitor/strategy/signals.py:L709-L758](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/signals.py#L709-L758) (`_check_approaching`)
- **Target Market Behavior:** Early warning radar alerting the trader that price is moving close to a major support or resistance zone.
- **Exact Detection Rules:**
  1. `zone.is_broken == False`.
  2. Distance condition: $0 < zone.\text{distance\_pct}(current.\text{close}) \le \text{approach\_distance\_pct}$ (default: **1.0%**).
  3. Strength threshold: `zone.strength >= 0.40`.
- **Entry Timing & Price Construction:**
  - **Prices:** `entry_ref = None, stop_loss = None, target = None, risk_reward = None`.
  - **Actionability:** **Strictly Informational.** Because `entry_ref` is `None`, `RiskManager.evaluate()` immediately rejects the setup ([algo_monitor/risk/manager.py:L110](file:///d:/Projects/Algo%20Monitor/algo_monitor/risk/manager.py#L110)). **It cannot create a paper trade.** It dispatches a Telegram notice alerting the user to watch the chart.

---

### Setup 8: Head & Shoulders Pattern (`HEAD_AND_SHOULDERS` — Modular Extension)
- **File & Function:** [algo_monitor/strategy/head_and_shoulders.py:L69-L250](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/head_and_shoulders.py#L69-L250)
- **Target Market Behavior:** Reversal chart pattern. Standard H&S signals top distribution and bearish trend change; Inverse H&S signals bottom accumulation and bullish trend change.
- **Exact Detection Rules:**
  1. High/Low Sequence: Identifies 3 consecutive swing peaks (Left Shoulder, Head, Right Shoulder) with 2 intervening troughs.
  2. Head Prominence: Head must exceed highest shoulder by $\ge \text{min\_head\_prominence\_pct}$ (default: **0.5%**).
  3. Shoulder Symmetry: Difference between Left and Right Shoulder heights must be within `shoulder_symmetry_pct` (default: **25%**).
  4. S/R Neckline Confluence: The line connecting intervening troughs must overlap an active Support Zone (Standard) or Resistance Zone (Inverse).
  5. Trigger: 5-minute candle closes across the neckline by $\ge 0.15\%$.
  6. Target: Measured move projection: $P_{\text{neckline}} \pm (P_{\text{head}} - P_{\text{neckline}})$.
  7. Stop-Loss: Placed just beyond the Right Shoulder apex.

---

### Setup 9: Firsty-Style EMA Trend Continuation (`FIRSTY_CONTINUATION` — Modular Extension)
- **File & Function:** [algo_monitor/strategy/trend_continuation.py:L83-L250](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/trend_continuation.py#L83-L250)
- **Target Market Behavior:** High-momentum trend-following setup. Enters pullbacks in the direction of established 20/50 EMA moving average trends when supported by horizontal S/R confluence.
- **Exact Detection Rules:**
  1. Moving Average Alignment: Fast EMA (20) and Slow EMA (50) correctly ordered (Fast > Slow for Bullish; Fast < Slow for Bearish).
  2. Trend Slope: Fast EMA slope $> 0$ over last 5 bars.
  3. Minimum Separation: $|EMA_{20} - EMA_{50}| \ge 0.25 \times \text{ATR}_{14}$.
  4. Value Area Pullback: Low of candle tests within $0.5 \times \text{ATR}_{14}$ of Fast EMA.
  5. S/R Confluence: Pullback low simultaneously interacts with an active Support Zone within $0.8\%$ tolerance.
  6. Rejection Wick: Trigger candle leaves a lower wick covering $\ge 25\%$ of total candle range and closes bullish.
  7. Target & Stop: Stop below pullback swing low minus $0.15 \times \text{ATR}$; target at next opposing resistance zone.

---

## PART 5 — Complete Trade Lifecycle & Reversal Scenarios

### 1. Step-by-Step Execution Sequence
```
Signal Generated by Strategy Scanner
       │
       ▼
[Signal Deduplication] ──► MD5 hash checked against recent 500 signals
       │
       ▼
[Risk Engine Evaluation] ─► RiskManager.evaluate() checks R:R, Max Positions, Leverage, Daily Circuit
       │
       ▼ (If Approved)
[Option Check] ──────────► If Indian Index & Enabled -> OptionsEngine builds defined-risk Option Buy
       │                   Else -> Standard Paper Trade opened
       ▼
[Database Persistence] ──► INSERT INTO trades (status='open') with entry, SL, TP, qty, fees, slippage
       │
       ▼
[Alert Dispatch] ────────► AlertManager formats HTML alert -> Telegram & Console
       │
       ▼
[Position Monitor Loop] ─► Every 30s AlgoMonitor._update_positions() resolves live price:
       │                   • Checks SL hit: price <= SL (long) or price >= SL (short)
       │                   • Checks TP hit: price >= TP (long) or price <= TP (short)
       │                   • Checks Expiry: Intraday (375m) or Swing (14d)
       │                   • Evaluates TradeManager structural advisory states
       ▼ (When Exit Breached)
[Trade Closure] ─────────► PaperTradingEngine._close_trade():
                           • Computes Gross P&L (FX converted if USD)
                           • Deducts Fees & Slippage
                           • Updates paper_balance in system_state
                           • Updates daily_pnl table
                           • Updates trades SET status='closed'
                           • Sends Telegram closure notification
```

---

### 2. Comprehensive Scenario Audit: Trade Reverses Before Reaching Target

#### The Scenario
Suppose the system opens a **LONG** paper trade:
- **Entry Price:** ₹100.00
- **Stop-Loss:** ₹95.00 ($R = ₹5.00$)
- **Target:** ₹107.50 ($1.5R$)
- **Price Progression:** $100 \rightarrow 102 \rightarrow 105 \rightarrow 103 \rightarrow 101 \rightarrow 98 \rightarrow 96$

*(Price surged favorably to ₹105, covering 66.7% of the distance to target (+1.0R), but stalled and reversed sharply toward the stop-loss).*

#### Exact Behavior of the Existing Code at Each Stage

1. **Does it keep the original target and stop-loss unchanged?**  
   **YES.** In `PaperTradingEngine.update_positions()` ([trading/engine.py:L432-L510](file:///d:/Projects/Algo%20Monitor/algo_monitor/trading/engine.py#L432-L510)), `pos["stop_loss"]` remains ₹95.00 and `pos["target"]` remains ₹107.50 throughout the entire trade. The paper trading engine contains **no code that mutates the trade record's stop-loss or take-profit columns while open**.
2. **Does it automatically exit when profit starts decreasing?**  
   **NO.** There is no profit-retraction exit, trailing drawdown stop, or high-water-mark exit in `PaperTradingEngine`. When price drops from ₹105 back to ₹103 and ₹101, the engine does nothing.
3. **Does it trail the stop-loss?**  
   **NO, not in execution.** While a dedicated trailing-stop module exists (`AdvancedExitManager` in [algo_monitor/strategy/exits.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/exits.py)), **it is NOT connected to `PaperTradingEngine`**. `PaperTradingEngine` does not import or instantiate `AdvancedExitManager`.  
   *However*, `TradeManager.evaluate_and_alert_trade()` ([trading/trade_manager.py:L254-L275](file:///d:/Projects/Algo%20Monitor/algo_monitor/trading/trade_manager.py#L254-L275)) detects when price reaches ₹105 ($+1.0R$) and issues a Telegram advisory: `Action: CONSIDER STOP TIGHTENING - Capital preservation rule: move stop loss to breakeven`. This is an informational advisory; it does not alter the trade in the database.
4. **Does it move the target further away?**  
   **NO.** The target remains locked at ₹107.50. `TradeManager` can recommend `CONSIDER_TARGET_EXTENSION`, but that advisory requires price progress $\ge 75\%$ and clean air ahead. At ₹105 (66%), it does not trigger.
5. **Does it partially book profit?**  
   **NO.** In `PaperTradingEngine`, partial profit taking is not implemented. Positions are strictly binary (100% open or 100% closed).
6. **Does it detect that the trade's original setup has weakened or become invalid?**  
   **YES, via TradeManager advisories.** When price breaks down back toward ₹98, `TradeManager._check_thesis_invalidated()` ([trade_manager.py:L398-L418](file:///d:/Projects/Algo%20Monitor/algo_monitor/trading/trade_manager.py#L398-L418)) checks whether structure has collapsed. If the latest completed 5m candle closes below support, it sends a Telegram advisory: `Action: EXIT THESIS INVALIDATED`. But again, `PaperTradingEngine` does not close the position until ₹95 is breached.
7. **Does it close the position if price reverses sharply?**  
   **NO.** Momentum-exhaustion exits are not implemented in the execution engine.
8. **Does it wait for the stop-loss or target?**  
   **YES.** The engine waits passively until the live price either touches the Stop-Loss ($\le ₹95.00$), touches the Target ($\ge ₹107.50$), or reaches the session timeout.
9. **What happens if the market gaps beyond the stop-loss?**  
   **Optimistic Fill Assumption:** In [trading/engine.py:L469-L475](file:///d:/Projects/Algo%20Monitor/algo_monitor/trading/engine.py#L469-L475):
   ```python
   if direction == "long" and price <= sl:
       exit_reason = "stop_loss"
       exit_price = sl  # Assume fill at SL (optimistic for paper)
   ```
   If price gaps down from ₹98 directly to ₹90, the trade is filled at **₹95.00**, completely ignoring the ₹5 gap slippage.
10. **What happens if price touches both stop-loss and target within the same candle?**  
    In `PaperTradingEngine.update_positions()`, the code checks `price <= sl` first. If both levels are touched simultaneously, **Stop-Loss takes precedence**. (In the live loop, prices arrive sequentially as single float ticks).
11. **What happens if price data becomes unavailable?**  
    The position remains open indefinitely in SQLite with `status='open'`. It is neither closed nor liquidated.
12. **Does behavior differ between intraday and swing positions?**  
    **Only in time-based expiry.** Intraday positions auto-close after 375 minutes (6.25 hours, covering one full NSE session); swing positions auto-close after 14 calendar days ([trading/engine.py:L488-L503](file:///d:/Projects/Algo%20Monitor/algo_monitor/trading/engine.py#L488-L503)).

---

## PART 6 — Stop-Loss, Target, and Risk/Reward Calculations

### Mathematical Formulation Table

| Metric | Implemented Formula in Code | Code Location | Plain-English Meaning |
| :--- | :--- | :--- | :--- |
| **Entry Price ($P_{\text{entry}}$)** | $C_{\text{current}}$ (close of confirmation candle) | [signals.py:L360](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/signals.py#L360) | Price where trade is executed |
| **SL Distance (Long)** | $P_{\text{entry}} - Z_{\text{low}} \times 0.995$ | [signals.py:L361](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/signals.py#L361) | Distance from entry to 0.5% below support zone |
| **SL Distance (Short)** | $Z_{\text{high}} \times 1.005 - P_{\text{entry}}$ | [signals.py:L423](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/signals.py#L423) | Distance from entry to 0.5% above resistance zone |
| **SL Percentage** | $(R / P_{\text{entry}}) \times 100$ | [manager.py:L198](file:///d:/Projects/Algo%20Monitor/algo_monitor/risk/manager.py#L198) | Percentage drop required to trigger stop |
| **Risk per Unit ($R$)** | $|P_{\text{entry}} - P_{\text{sl}}|$ | [manager.py:L134](file:///d:/Projects/Algo%20Monitor/algo_monitor/risk/manager.py#L134) | Maximum loss per share/token |
| **Target Distance** | $|P_{\text{target}} - P_{\text{entry}}|$ | [signals.py:L369](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/signals.py#L369) | Expected gross profit per share/token |
| **Reward/Risk Ratio** | $\text{Reward per unit} / \text{Risk per unit}$ | [manager.py:L146](file:///d:/Projects/Algo%20Monitor/algo_monitor/risk/manager.py#L146) | Reward multiple relative to risk |
| **Risk Budget (Quote)** | $(\text{Balance} / \text{FX}) \times \text{risk\_per\_trade}$ | [manager.py:L197](file:///d:/Projects/Algo%20Monitor/algo_monitor/risk/manager.py#L197) | 2% cash risk budget in asset currency |
| **Quantity ($Q_{\text{raw}}$)** | $\min\left(\frac{\text{Risk Budget}}{R}, \frac{\text{Balance} \times 0.5 \times 3.0}{P_{\text{entry}} \times \text{FX}}\right)$ | [manager.py:L208](file:///d:/Projects/Algo%20Monitor/algo_monitor/risk/manager.py#L208) | Sizing bounded by risk budget & 3x leverage |
| **Estimated Fees** | $Q \times P_{\text{entry}} \times \text{FX} \times 0.0005 \times 2$ | [manager.py:L223](file:///d:/Projects/Algo%20Monitor/algo_monitor/risk/manager.py#L223) | 5 bps applied twice (entry + exit) |
| **Estimated Slippage**| $Q \times P_{\text{entry}} \times \text{FX} \times 0.0003 \times 2$ | [manager.py:L224](file:///d:/Projects/Algo%20Monitor/algo_monitor/risk/manager.py#L224) | 3 bps applied twice (entry + exit) |
| **Gross Realized P&L** | $(P_{\text{exit}} - P_{\text{entry}}) \times Q \times \text{FX}$ (Long) | [trading/engine.py:L531](file:///d:/Projects/Algo%20Monitor/algo_monitor/trading/engine.py#L531) | Gross profit before trading frictions |
| **Net Realized P&L** | $\text{Gross P\&L} - \text{Fees} - \text{Slippage}$ | [trading/engine.py:L535](file:///d:/Projects/Algo%20Monitor/algo_monitor/trading/engine.py#L535) | Final cash added/subtracted from balance |
| **Unrealized P&L** | $(P_{\text{current}} - P_{\text{entry}}) \times Q$ | [dashboard/app.py:L763](file:///d:/Projects/Algo%20Monitor/algo_monitor/dashboard/app.py#L763) | Mark-to-market open position P&L |

---

### Opposing Zone Targeting vs. Fixed R:R Fallback
In [algo_monitor/strategy/adaptive_target.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/adaptive_target.py#L54-L152):
1. **Adaptive Mode (`target_mode = "adaptive"`):**  
   The planner finds the nearest opposing active S/R zone in front of the trade:
   - For LONG trades: Finds the nearest Resistance zone where $\text{price\_low} > P_{\text{entry}}$.
   - It sets the target just before that resistance zone, subtracting a clearance buffer (`zone_clearance_buffer_pct = 0.2%`):
     $$P_{\text{target}} = \text{opposing\_zone.price\_low} \times (1 - 0.002)$$
   - It checks whether $(P_{\text{target}} - P_{\text{entry}}) / R \ge 1.5$. If this condition is met, the adaptive target is locked.
2. **Fixed R:R Fallback:**  
   If no opposing zone is found, or if the nearest zone is too close ($R:R < 1.5$), it falls back to:
   $$P_{\text{target}} = P_{\text{entry}} \pm (R \times \text{target\_fixed\_rr\_multiple})$$
   where `target_fixed_rr_multiple` is `1.5`.

---

## PART 7 — Position Sizing, Margin, and Capital Protection

### 1. Capital and Risk Configuration Defaults
- **Starting Balance:** ₹20,000 INR default in code (`PAPER_TRADING_BALANCE` in `.env.example` shows ₹1,000,000, while `settings.py:L268` defaults to ₹20,000).
- **Risk per Trade:** 2% (`risk_per_trade = 0.02`). Maximum risk budget per trade on ₹20,000 is ₹400.
- **Maximum Open Positions:** 3 concurrent positions (`max_positions = 3`).
- **Maximum Margin Allocation per Trade:** 50% of available account equity (`max_capital_per_trade_pct = 0.50`).
- **Maximum Broker Leverage:** 3.0x (`max_leverage = 3.0`).
- **Daily Circuit Breaker:** 5% of balance (`max_daily_loss = 0.05`). On ₹20,000, if daily realized losses reach ₹1,000, no further trades are permitted until the next session.

---

### 2. Multi-Currency Accounting (USD vs. INR)
A critical quantitative audit finding in previous versions was the cross-currency sizing error on crypto assets.
In the current implementation ([algo_monitor/risk/manager.py:L189-L220](file:///d:/Projects/Algo%20Monitor/algo_monitor/risk/manager.py#L189-L220)):
- **Quote Currency Identification:** Checked via `is_usd = "USD" in signal.symbol or signal.symbol.endswith("USD")`.
- **Conversion Rate:** Configured via `usd_inr_rate = 85.0`.
- **Account Equity in Quote Currency:**
  $$\text{balance\_quote} = \frac{\text{current\_balance}}{\text{fx\_rate}} = \frac{₹20,000}{85.0} = \$235.29 \text{ USD}$$
- **Risk Budget in USD:**
  $$\text{risk\_budget\_quote} = \$235.29 \times 0.02 = \$4.71 \text{ USD}$$
- **Margin Cap in USD:**
  $$\text{max\_notional\_quote} = (\$235.29 \times 0.50) \times 3.0 = \$352.94 \text{ USD}$$
- **Quantity Bounded by Leverage:**
  $$Q_{\text{leverage}} = \frac{\$352.94}{P_{\text{entry}}}$$
  This strictly prevents multi-million-dollar notional crypto positions on small rupee accounts.

---

### 3. Lot Sizing and Quantization Rules
Implemented in `RiskManager._apply_lot_sizing()` ([manager.py:L282-L297](file:///d:/Projects/Algo%20Monitor/algo_monitor/risk/manager.py#L282-L297)):
- **NIFTY50:** Quantized to integer multiples of 25: `float(int(quantity // 25) * 25)`.
- **BANKNIFTY:** Quantized to integer multiples of 15: `float(int(quantity // 15) * 15)`.
- **BTCUSD:** Rounded to 3 decimals: `round(quantity, 3)`.
- **ETHUSD:** Rounded to 2 decimals: `round(quantity, 2)`.
- **All other assets:** Rounded to 4 decimals: `round(quantity, 4)`.

---

### 4. Options Capital Protection Logic
Because buying a single futures lot of NIFTY50 (25 qty @ 24,800 = ₹6.2 Lakh notional) exceeds the leverage capacity of a ₹20,000 account, `PaperTradingEngine` automatically routes Indian indices to `OptionsEngine.prepare_trade_setup()` ([algo_monitor/options/engine.py:L220-L301](file:///d:/Projects/Algo%20Monitor/algo_monitor/options/engine.py#L220-L301)):
- **Defined-Risk Call/Put Buying:** The system buys ATM options where maximum risk is strictly capped at the premium paid.
- **Capital Cap:** Capped at 45% of capital (`max_capital_per_option_trade_pct = 0.45` = ₹9,000).
- **Lot Cap:** Restricted to `max(1, min(max_lots, 3))` (max 3 lots).
- **Stop-Loss Premium:** Calculated via Black-Scholes delta projection corresponding to underlying spot S/R violation.

---

## PART 8 — Exhaustive Configuration Parameters Reference

Below is the complete dictionary of all configuration parameters defined across `Settings`, `StrategyConfig`, `RiskConfig`, `OptionsConfig`, and `.env.example`.

| Parameter | Code Default | Unit | Used By Module | Description & Effect | Risk / Gotcha | Runtime Behavior |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `PAPER_TRADING_BALANCE` | `20000` | INR | `RiskConfig` | Starting paper capital base | Sizing scales linearly with this value | Requires restart |
| `RISK_PER_TRADE` | `0.02` | Fraction | `RiskManager` | Risk budget fraction per trade (2%) | Higher values increase drawdown risk | Requires restart |
| `MAX_POSITIONS` | `3` | Integer | `RiskManager` | Simultaneous open trade limit | Blocks signals when reached | Requires restart |
| `MAX_DAILY_LOSS` | `0.05` | Fraction | `RiskManager` | Circuit breaker threshold (5%) | Halts all trading if hit | Requires restart |
| `MIN_REWARD_RISK` | `1.5` | Ratio | `RiskManager` | Validation floor for trade approval | Rejects setups with R:R $< 1.5$ | Requires restart |
| `MAX_LEVERAGE` | `3.0` | Multiplier | `RiskManager` | Maximum broker notional leverage | Prevents catastrophic crypto exposure | Requires restart |
| `MAX_CAPITAL_PER_TRADE_PCT`| `0.5` | Fraction | `RiskManager` | Maximum account margin per trade | Caps single-position concentration | Requires restart |
| `USD_INR_RATE` | `85.0` | Exchange Rate | `RiskManager` | Conversion factor for USD crypto pairs | Hardcoded conversion baseline | Requires restart |
| `fee_rate` | `0.0005` | Fraction | `RiskManager` | Trading fee estimate (5 bps each way) | Deducted from realized P&L | Hardcoded |
| `slippage_rate` | `0.0003` | Fraction | `RiskManager` | Slippage estimate (3 bps each way) | Deducted from realized P&L | Hardcoded |
| `intraday_expiry_minutes` | `375` | Minutes | `PaperTradingEngine` | Auto-close timer for intraday trades | Closes trades after 6h 15m | Hardcoded |
| `swing_max_days` | `14` | Days | `PaperTradingEngine` | Auto-close timer for swing trades | Closes trades after 14 days | Hardcoded |
| `swing_lookback` | `3` | Candles | `LevelDetector` | Window on each side of swing pivot | Higher values detect fewer, wider zones | Requires restart |
| `min_prominence_pct` | `0.25` | Percentage | `LevelDetector` | Minimum depth required for swing | Filters out consolidation noise | Requires restart |
| `zone_tolerance_pct` | `0.5` | Percentage | `LevelDetector` | Clustering tolerance for nearby levels | Higher values create broader zones | Requires restart |
| `min_zone_width_pct` | `0.2` | Percentage | `LevelDetector` | Minimum zone width enclosure | Prevents single-line boundary errors | Requires restart |
| `min_touches` | `2` | Count | `LevelDetector` | Minimum touches to validate zone | Filters out one-off random pivots | Requires restart |
| `max_zones` | `20` | Count | `LevelDetector` | Maximum zones retained per symbol | Limits memory and chart clutter | Requires restart |
| `breakout_threshold_pct`| `0.3` | Percentage | `SignalGenerator` | Close required beyond zone for breakout | Prevents false breakout triggers | Requires restart |
| `retest_tolerance_pct` | `0.5` | Percentage | `SignalGenerator` | Closeness to zone required for retest | Higher values trigger looser retests | Requires restart |
| `target_mode` | `"adaptive"` | String | `SignalGenerator` | Target algorithm (`adaptive` vs `fixed_rr`) | Anchors target to opposing zone | Requires restart |
| `target_fixed_rr_multiple`| `1.5` | Multiplier | `SignalGenerator` | Fallback R:R when no opposing zone | Fixed multiple exit distance | Requires restart |
| `zone_clearance_buffer_pct`| `0.2` | Percentage | `AdaptiveTargetPlanner`| Buffer before opposing zone | Prevents placing TP inside zone | Requires restart |
| `zone_invalidation_threshold_pct`| `0.5` | Percentage | `LevelDetector` | Close required beyond zone to break | Flips zone polarity if exceeded | Requires restart |
| `zone_invalidation_closes`| `2` | Count | `LevelDetector` | Consecutive closes required to break | Prevents single-bar false breaks | Requires restart |
| `enable_polarity_flips` | `True` | Boolean | `LevelDetector` | Flips broken Resistance $\leftrightarrow$ Support | Enables retest of broken levels | Requires restart |
| `enable_zone_merging` | `True` | Boolean | `LevelDetector` | Merges overlapping same-polarity zones | Eliminates chart clutter | Requires restart |
| `max_fresh_touches` | `5` | Count | `LevelDetector` | Threshold before freshness penalty | Levels with $>5$ touches penalized | Requires restart |
| `indian_htf_interval` | `"1d"` | Interval | `Scanner` | Major zone timeframe for Upstox | S/R zones derived from Daily bars | Requires restart |
| `indian_ltf_interval` | `"5m"` | Interval | `Scanner` | Entry timeframe for Upstox | Signal entries derived from 5m bars | Requires restart |
| `crypto_htf_interval` | `"1h"` | Interval | `Scanner` | Major zone timeframe for Delta | S/R zones derived from 1h bars | Requires restart |
| `crypto_ltf_interval` | `"5m"` | Interval | `Scanner` | Entry timeframe for Delta | Signal entries derived from 5m bars | Requires restart |
| `crypto_rolling_window_hours`| `72` | Hours | `Scanner` | Rolling analysis window for crypto | Restricts crypto S/R to 3 days | Requires restart |
| `ENABLE_OPTIONS` | `True` | Boolean | `OptionsConfig` | Enable quant options trading module | Routes indices to Call/Put buying | Requires restart |
| `OPTIONS_AUTO_ROUTE_INDICES`| `True` | Boolean | `OptionsConfig` | Automatically route Nifty/BankNifty | Bypasses unaffordable index futures | Requires restart |
| `OPTIONS_MAX_CAPITAL_PCT`| `0.45` | Fraction | `OptionsConfig` | Max capital allocated to option buy | Capped at 45% of balance | Requires restart |
| `DASHBOARD_HOST` | `"127.0.0.1"` | Host IP | `FastAPI` | Web server listening address | Default binds to localhost | Requires restart |
| `DASHBOARD_PORT` | `8501` | Port | `FastAPI` | Web server listening port | Auto-resolves collision up to +50 | Requires restart |

---

## PART 9 — Historical Backtesting System Audit

The backtester is implemented in [algo_monitor/backtest/runner.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/backtest/runner.py#L59-L368).

### 1. Data Ingestion & Strategy Code Reuse
- **Data Source:** Pulls stored OHLCV candles directly from SQLite `candles` table via `CandleStore.get_candles()`.
- **Logic Reused:** Instantiates and reuses the exact production strategy classes: `LevelDetector`, `SignalGenerator`, `AdaptiveTargetPlanner`, and `RiskManager`.
- **Advanced Exits:** Uniquely instantiates `AdvancedExitManager` ([runner.py:L83](file:///d:/Projects/Algo%20Monitor/algo_monitor/backtest/runner.py#L83)) to evaluate trailing stops and partial profits during backtests.

---

### 2. Elimination of Look-Ahead Bias
In earlier audits, the backtester allowed future data leakage because `htf_window` checked `c.timestamp <= current_ltf.timestamp`. Because `Candle.timestamp` is the candle's open time, an intra-day 5m bar at 09:30 could see the completed OHLC of a 4h candle that opened at 08:00 but did not close until 12:00.

In the current code ([algo_monitor/backtest/runner.py:L41-L56](file:///d:/Projects/Algo%20Monitor/algo_monitor/backtest/runner.py#L41-L56)):
```python
def _candle_close_time(candle: Candle, interval: str) -> datetime:
    duration_secs = CANDLE_DURATION_SECONDS.get(interval, 0)
    return candle.timestamp + timedelta(seconds=duration_secs)
```
And in [runner.py:L181-L184](file:///d:/Projects/Algo%20Monitor/algo_monitor/backtest/runner.py#L181-L184):
```python
htf_window = [
    c for c in htf_candles
    if _candle_close_time(c, htf_interval) <= current_ltf.timestamp
]
```
A daily candle that opened on Monday at 00:00 UTC is not closed until Tuesday at 00:00 UTC. **It is strictly inaccessible to 5-minute bars on Monday**, completely eliminating higher-timeframe future leakage.

---

### 3. Currency Conversion in Backtesting
In earlier versions, USD profits from BTCUSD were added 1:1 into an INR starting balance.
In the current code ([algo_monitor/backtest/runner.py:L280-L287](file:///d:/Projects/Algo%20Monitor/algo_monitor/backtest/runner.py#L280-L287)):
```python
fx_rate = usd_inr if is_usd_instrument else 1.0
gross_inr = gross_quote * fx_rate
fees_inr = entry * qty * self.risk_config.fee_rate * 2 * fx_rate
slippage_inr = entry * qty * self.risk_config.slippage_rate * 2 * fx_rate
net_inr = gross_inr - fees_inr - slippage_inr
balance += net_inr
```
Crypto profits and trading costs are accurately converted to INR before updating account equity.

---

### 4. Remaining Backtester Limitations
1. **Options Execution Bypassed:** While live paper trading routes Nifty/BankNifty setups to `OptionsEngine` for Black-Scholes ATM Call/Put buying, `BacktestRunner` calls `RiskManager.evaluate()` directly on underlying index prices ([runner.py:L310](file:///d:/Projects/Algo%20Monitor/algo_monitor/backtest/runner.py#L310)). It cannot backtest options decay, implied volatility changes, or delta movement.
2. **Single-Instrument Only:** `BacktestRunner.run()` takes a single `Instrument`. It cannot execute multi-instrument portfolio simulations with shared cash pools, cross-asset correlation caps, or concurrent margin allocation.
3. **Execution Fills:** Stop-Loss and Target fills are assumed at the exact limit/stop price. Gap-down slippage through stop-losses is not modeled.
4. **Current Performance Evidence:** In the live database, exactly **6 paper trades** exist (all crypto perpetuals). **There is currently zero statistically verified evidence of long-term strategy profitability.**

---

## PART 10 — Dashboard, REST API, and Alert Routing

### 1. Dashboard Architecture & Launch
The dashboard is built on **FastAPI** with **Jinja2 templates** and **vanilla CSS/JavaScript** (featuring an advanced React Quant Terminal bundle).
- **Default Address:** `http://127.0.0.1:8501`
- **Port Collision Resolver:** If port 8501 is occupied, `AlgoMonitor._start_dashboard()` ([main.py:L446-L450](file:///d:/Projects/Algo%20Monitor/algo_monitor/main.py#L446-L450)) scans sequential ports up to `8551` and automatically binds to the first free port.

---

### 2. Comprehensive API Route Catalogue

| Method | Endpoint | Description & Responsibility | Response Type | Security & Auth |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/` | Serves modern Quant Terminal UI | `text/html` | Open (No Auth) |
| `GET` | `/legacy` | Serves legacy fallback dashboard | `text/html` | Open (No Auth) |
| `GET` | `/api/status` | System health, uptime, engine status, market status | `application/json` | Open (No Auth) |
| `GET` | `/api/market-toggle` | Returns active status of Indian & Crypto scanning | `application/json` | Open (No Auth) |
| `POST`| `/api/market-toggle` | Toggles Indian or Crypto scanning ON/OFF | `application/json` | Open (No Auth) |
| `GET` | `/api/upstox/auth-status`| Returns Upstox OAuth2 & TOTP validity & expiry time | `application/json` | Open (No Auth) |
| `POST`| `/api/upstox/refresh-token`| Triggers headless TOTP auto-login to fetch new token| `application/json` | Open (No Auth) |
| `GET` | `/api/indian/indices` | Live quotes and day changes for NSE indices | `application/json` | Open (No Auth) |
| `GET` | `/api/indian/fno-securities`| Filtered F&O equity quotes (Nifty50, BankNifty, Auto)| `application/json` | Open (No Auth) |
| `GET` | `/api/indian/index-constituents`| Weighted constituent stock lists for major indices | `application/json` | Open (No Auth) |
| `GET` | `/api/indian/option-chain/{symbol}`| Full options matrix, PCR, Max Pain, ATM Greeks | `application/json` | Open (No Auth) |
| `GET` | `/api/crypto/market` | Delta perpetual quotes, 24h volume, funding rates | `application/json` | Open (No Auth) |
| `GET` | `/api/crypto/options` | Crypto options volatility skew and strike chain | `application/json` | Open (No Auth) |
| `GET` | `/api/crypto/futures-movers`| Top 24h gainers and losers across crypto futures | `application/json` | Open (No Auth) |
| `GET` | `/api/live-prices` | Global cache dump of all instrument LTPs | `application/json` | Open (No Auth) |
| `GET` | `/api/positions` | Open and closed paper positions enriched with live P&L | `application/json` | Open (No Auth) |
| `GET` | `/api/signals` | Active and historical trading signals | `application/json` | Open (No Auth) |
| `GET` | `/api/zones` | Detected S/R zones with strength scores & touches | `application/json` | Open (No Auth) |
| `GET` | `/api/candles/{symbol}`| OHLCV candle feed for TradingView Lightweight charts| `application/json` | Open (No Auth) |
| `GET` | `/api/performance` | Win rate, profit factor, Sharpe, drawdown metrics | `application/json` | Open (No Auth) |
| `GET` | `/api/balance` | Current simulated cash balance and daily P&L | `application/json` | Open (No Auth) |
| `GET` | `/api/scan-results` | Raw output of the latest 5-minute scanner cycle | `application/json` | Open (No Auth) |
| `GET` | `/api/alerts` | Historical alert dispatch log from SQLite | `application/json` | Open (No Auth) |
| `GET` | `/api/config` | Read-only dump of active risk & options settings | `application/json` | Open (No Auth) |

---

### 3. Critical Security Notice: Unauthenticated Endpoints
The FastAPI web server is instantiated with **no authentication, API keys, HTTP Basic Auth, or session cookies**.
- Anyone with network access to the port (e.g., exposed on a public VPS IP) can view account balances, inspect trading signals, toggle markets on/off via `POST /api/market-toggle`, or force TOTP token refreshes via `POST /api/upstox/refresh-token`.
- **Remediation:** Before exposing this service on a remote server, HTTP Basic Auth, an API token middleware, or an Nginx reverse proxy with SSL and password protection must be configured.

---

### 4. Telegram Notification Architecture
Implemented in [algo_monitor/alerts/notifier.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/alerts/notifier.py#L95-L248):
- **Formatting:** HTML formatted messages specifying Setup, Symbol, Direction, Entry Reference, Stop-Loss, Target, Risk/Reward, and Reason.
- **Informational vs. Trade Alerts:** Informational alerts (`APPROACHING_ZONE`) clearly state `Watch for reaction` without entry prices. Trade alerts include specific entry, stop, and target levels with a explicit footer: `Status: PAPER TRADING ONLY`.
- **Deduplication:** The message is hashed using MD5. The hash is checked against SQLite `alert_log` and an in-memory dictionary `_last_alert_time` with a 300-second rate limit.
- **Trade Management Advisories:** When `TradeManager` identifies a state change on an open position (`CONSIDER_STOP_TIGHTENING`, `CONSIDER_PROFIT_TAKING`, etc.), it sends an alert formatted with `Status: PAPER TRADING ADVISORY`.

---

## PART 11 — State Persistence, Restarts, and Failure Scenarios

### Detailed Scenario Walkthroughs

#### 1. Application Restart or Crash
- **SQLite Database:** The SQLite database uses Write-Ahead Logging (`PRAGMA journal_mode=WAL`). In the event of a process crash or sudden `SIGKILL`, SQLite recovers uncommitted transactions on next startup without database corruption.
- **Open Positions:** Open trades are stored with `status = 'open'`. When the engine restarts, `PaperTradingEngine.get_open_positions()` queries `SELECT * FROM trades WHERE status = 'open'`. The trades are immediately loaded back into memory and monitored on the 30-second loop.
- **Account Equity:** The paper balance is read from `system_state WHERE key = 'paper_balance'`. It does not reset to ₹20,000 on reboot.
- **Temporary State Loss:** In-memory caches (`_latest_prices`, `_recent_signal_ids`) are cleared. The application bootstrap thread re-scans stored candles and establishes fresh WebSocket/REST feeds.

#### 2. Complete VPS Reboot
- Managed by `systemd` via [algo-monitor.service](file:///d:/Projects/Algo%20Monitor/algo-monitor.service).
- Configured with `Restart=always` and `RestartSec=5`. Upon VPS reboot, systemd automatically spawns `python run.py`, reattaches to `algo_monitor.db`, connects to the network, and resumes background monitoring.

#### 3. Complete Exchange API Outage
- If Upstox or Delta APIs become unreachable, `IngestionService` catches the network exception, logs an error, and skips that interval.
- Existing candles remain safe in SQLite.
- S/R zones and charts remain visible on the dashboard using cached historical bars.
- If data age exceeds 2 hours (crypto) or 6 hours (Indian market), the scanner logs a staleness notice and **suppresses all signal generation**, ensuring that broken connections never trigger outdated orders.

---

## PART 12 — Prioritized Audit Findings, Bugs, and Discrepancies

The following table reflects a thorough, prioritized audit of the current codebase, distinguishing verified fixes, design limitations, and remaining discrepancies.

| Severity | Classification | Issue & Evidence | Practical Impact | Recommended Fix |
| :--- | :--- | :--- | :--- | :--- |
| **HIGH** | **Missing Feature** | **No Live Exchange Execution OMS**<br>Evidence: Neither `UpstoxClient` nor `DeltaExchangeClient` contains order placement endpoints (`POST /order`, etc.). | The system cannot place real money orders on an exchange. It is strictly a monitoring and paper trading simulator. | Build an isolated Order Management System (OMS) adapter with broker confirmation hooks before attempting live trading. |
| **HIGH** | **Security Risk** | **Unauthenticated Dashboard & API**<br>Evidence: `create_app()` in [app.py:L50](file:///d:/Projects/Algo%20Monitor/algo_monitor/dashboard/app.py#L50) has no auth middleware or token checks. | Anyone with network access to port 8501 can toggle market feeds or trigger Upstox token refreshes. | Add HTTP Basic Authentication or Bearer Token middleware to all `/api/*` endpoints. |
| **HIGH** | **Design Limitation**| **Advanced Exit Execution Disconnected**<br>Evidence: `AdvancedExitManager` ([exits.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/exits.py)) is used in backtesting but NOT imported into `PaperTradingEngine` ([engine.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/trading/engine.py)). | Open paper trades never trail stops or take partial profits; they wait statically for hard SL or TP hits. | Wire `AdvancedExitManager` into `PaperTradingEngine.update_positions()`. |
| **HIGH** | **Design Limitation**| **Options Bypassed in Backtester**<br>Evidence: [backtest/runner.py:L310](file:///d:/Projects/Algo%20Monitor/algo_monitor/backtest/runner.py#L310) evaluates spot prices directly and never invokes `OptionsEngine`. | Backtesting cannot simulate actual options buying P&L, theta decay, or delta movement. | Integrate `OptionsEngine.prepare_trade_setup()` into the backtest runner loop. |
| **MEDIUM** | **Discrepancy** | **Default Capital Inconsistency**<br>Evidence: `.env.example:L43` specifies `1000000`, while `settings.py:L268` defaults to `20000`. | Users who do not set `.env` operate with ₹20k, while documentation references ₹10 Lakhs. | Synchronize `.env.example` and `settings.py` default values. |
| **MEDIUM** | **Design Limitation**| **Optimistic Gap Fill Assumption**<br>Evidence: [trading/engine.py:L471](file:///d:/Projects/Algo%20Monitor/algo_monitor/trading/engine.py#L471) sets `exit_price = sl`. | Paper trades that gap through a stop-loss are filled at the stop price rather than the worse market price. | Set `exit_price = min(price, sl)` for long stop-losses to reflect real gap slippage. |
| **MEDIUM** | **Design Limitation**| **Single-Instrument Backtesting Only**<br>Evidence: `BacktestRunner.run()` accepts only one `Instrument` at a time. | Cannot simulate cross-asset correlation, portfolio drawdowns, or shared margin constraints. | Build a portfolio-level simulation driver that walks all instruments synchronously. |
| **LOW** | **Verified Behavior** | **Look-Ahead Bias Fixed in Backtester**<br>Evidence: [backtest/runner.py:L183](file:///d:/Projects/Algo%20Monitor/algo_monitor/backtest/runner.py#L183) enforces `_candle_close_time(c) <= current_ltf.timestamp`. | Higher-timeframe candles are only visible once fully completed. Verified and working. | None (Safeguard confirmed). |
| **LOW** | **Verified Behavior** | **Cross-Currency Sizing Protected**<br>Evidence: [risk/manager.py:L194-L208](file:///d:/Projects/Algo%20Monitor/algo_monitor/risk/manager.py#L194-L208) converts balance to quote currency and caps by 3x leverage. | Prevents astronomical multi-million-dollar crypto exposures on small rupee accounts. | None (Safeguard confirmed). |
| **LOW** | **Verified Behavior** | **Adaptive Opposing Zone Targets**<br>Evidence: [adaptive_target.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/adaptive_target.py) actively anchors targets to opposing zones. Verified in DB trades. | Targets respect overhead resistance rather than blindly multiplying risk by 1.5. | None (Feature confirmed). |

---

## PART 13 — Complete End-to-End Worked Trade Example

The following is a hypothetical, step-by-step walkthrough of a trade executed according to the exact mathematical rules of the codebase.

### Phase 1: Setup and Market Context
- **Instrument:** `RELIANCE` (NSE Equity via Upstox)
- **Account Balance:** ₹20,000.00 INR
- **Higher Timeframe:** Daily (`1d`) candles loaded into `LevelDetector`.
- **Detected S/R Structure:**
  - Major Support Zone: $[2,920.00 - 2,935.00]$ (Strength: 0.82, Touches: 4)
  - Nearest Overhead Resistance Zone: $[3,040.00 - 3,055.00]$ (Strength: 0.74, Touches: 3)

---

### Phase 2: Signal Generation on the 5-Minute Timeframe
- **Previous 5m Completed Candle ($C_{-2}$):**
  - Open: ₹2,945.00, High: ₹2,948.00, Low: ₹2,928.00 (entered support zone), Close: ₹2,932.00.
- **Current 5m Completed Candle ($C_{-1}$):**
  - Open: ₹2,933.00, Low: ₹2,930.00, High: ₹2,952.00, Close: ₹2,950.00 (bullish, closed above zone top ₹2,935.00).
- **Rule Verification:** Meets all conditions for `SetupType.BOUNCE_SUPPORT` ([signals.py:L351-L358](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/signals.py#L351-L358)).
- **Price Geometry:**
  - $P_{\text{entry}} = ₹2,950.00$
  - $P_{\text{sl}} = \text{zone.price\_low} \times 0.995 = 2,920.00 \times 0.995 = ₹2,905.40$
  - Risk Distance: $R = 2,950.00 - 2,905.40 = ₹44.60$
- **Target Projection (Adaptive Mode):**
  - Nearest Opposing Zone: Resistance at $[3,040.00 - 3,055.00]$.
  - Clearance Buffer ($0.2\%$ of mid 3047.50): $₹6.10$.
  - Adaptive Target: $P_{\text{target}} = 3,040.00 - 6.10 = ₹3,033.90$.
  - Gross Reward: $3,033.90 - 2,950.00 = ₹83.90$.
  - Reward-to-Risk: $83.90 / 44.60 = 1.88$ (Exceeds validation floor of 1.50).

---

### Phase 3: Risk Manager Checks & Position Sizing
In `RiskManager.evaluate()` ([manager.py:L92-L270](file:///d:/Projects/Algo%20Monitor/algo_monitor/risk/manager.py#L92-L270)):
1. **Circuit Breaker:** Daily realized P&L is ₹0.00 ($< 5\%$ limit of ₹1,000.00). Approved.
2. **Position Limit:** Currently 0 open positions ($< 3$). Approved.
3. **Risk Budget Sizing:**
   $$\text{Risk Budget} = ₹20,000.00 \times 0.02 = ₹400.00$$
   $$Q_{\text{risk}} = \frac{₹400.00}{₹44.60} = 8.9686 \text{ shares}$$
4. **Leverage Ceiling Sizing:**
   $$\text{Max Margin Allowed} = ₹20,000.00 \times 0.50 = ₹10,000.00$$
   $$\text{Max Notional Allowed} = ₹10,000.00 \times 3.0 = ₹30,000.00$$
   $$Q_{\text{leverage}} = \frac{₹30,000.00}{₹2,950.00} = 10.1695 \text{ shares}$$
5. **Raw Sizing:** $Q = \min(8.9686, 10.1695) = 8.9686$.
6. **Lot Sizing / Rounding:** For equities, rounded to 4 decimals: $Q = 8.9686$ shares.
7. **Notional Value:** $8.9686 \times ₹2,950.00 = ₹26,457.37$ (Within 3x leverage cap).
8. **Friction Estimates:**
   - Fees ($0.05\% \times 2$): $₹26,457.37 \times 0.0010 = ₹26.46$
   - Slippage ($0.03\% \times 2$): $₹26,457.37 \times 0.0006 = ₹15.87$
   - Total Cost: $₹42.33$ ($5.6\%$ of gross reward; $< 30\%$ warning threshold).
- **Verdict:** Trade **APPROVED**.

---

### Phase 4: Execution and Database Persistence
`PaperTradingEngine._open_trade()` executes:
- Writes row to SQLite `trades` table:
  - `symbol = 'RELIANCE'`, `direction = 'long'`, `quantity = 8.9686`
  - `entry_price = 2950.00`, `stop_loss = 2905.40`, `target = 3033.90`
  - `status = 'open'`, `fees = 26.46`, `slippage = 15.87`
- `AlertManager` sends Telegram notification:
  > 🔔 **Bounce Support**  
  > 📊 **RELIANCE** (upstox) | Direction: **LONG**  
  > 🎯 Entry ref: **2950.00** | 🛑 Stop loss: **2905.40** | ✅ Target: **3033.90** | ⚖️ R:R = **1.88**  
  > 📋 Status: PAPER TRADING ONLY  

---

### Phase 5: Two Alternate Exit Scenarios

#### Scenario A: Target Hit
1. **Price Trajectory:** Price rises steadily: $2,950 \rightarrow 2,980 \rightarrow 3,010 \rightarrow 3,035$.
2. **Trigger:** On the 30-second monitor cycle, `current_price = 3,035.00 \ge 3,033.90`.
3. **Execution:**
   - `exit_reason = 'target_hit'`, `exit_price = 3,033.90`
   - $\text{Gross P\&L} = (3,033.90 - 2,950.00) \times 8.9686 = ₹752.47$
   - $\text{Net P\&L} = ₹752.47 - ₹26.46 - ₹15.87 = \mathbf{+₹710.14}$
4. **State Update:**
   - `trades` row marked `status = 'closed'`, `net_pnl = 710.14`.
   - `paper_balance` updated in `system_state`: $₹20,000.00 + ₹710.14 = \mathbf{₹20,710.14}$.
   - `daily_pnl` updated with $+₹710.14$.
   - Telegram sends closure alert: `📊 Trade closed: LONG RELIANCE | P&L: ₹710.14 | Reason: target_hit`.

#### Scenario B: Reversal Before Target to Stop-Loss
1. **Price Trajectory:** Price moves favorably to ₹3,010 (+1.35R), but stalls.
2. **Advisory Trigger:** At ₹3,010, `TradeManager` evaluates $r_{\text{achieved}} = 1.35 > 1.0$. It issues a Telegram advisory: `Action: CONSIDER STOP TIGHTENING - Favorable excursion of 1.35R reached`.
3. **Reversal:** The market rolls over sharply: $3,010 \rightarrow 2,970 \rightarrow 2,940 \rightarrow 2,900$.
4. **Execution:**
   - In `PaperTradingEngine`, the stop was not modified. At ₹2,900, `price <= 2905.40`.
   - `exit_reason = 'stop_loss'`, `exit_price = 2,905.40`
   - $\text{Gross P\&L} = (2,905.40 - 2,950.00) \times 8.9686 = -₹400.00$
   - $\text{Net P\&L} = -₹400.00 - ₹26.46 - ₹15.87 = \mathbf{-₹442.33}$
5. **State Update:**
   - `trades` row marked `status = 'closed'`, `net_pnl = -442.33`.
   - `paper_balance` updated: $₹20,000.00 - ₹442.33 = \mathbf{₹19,557.67}$.
   - `daily_pnl` updated with $-₹442.33$ (Circuit breaker remains untripped as $-442.33 > -1000.00$).

---

## PART 14 — Quantitative Learning Guide & Pre-Live Checklist

### 1. The Strategy in Three Sentences
Algo Monitor locates horizontal institutional liquidity bands (Support and Resistance) on daily and hourly charts using confirmed swing highs and lows with strict prominence filtering. It then monitors 5-minute completed bars for reaction patterns—bounces, rejections, breakouts, and retests—and projects adaptive profit targets just short of the next opposing structural barrier. Trades are simulated with conservative risk budgets (2%), strict leverage bounds (3.0x), daily circuit breakers (5%), and options routing for high-notional index contracts.

---

### 2. Comprehensive Trading & Programming Glossary
- **ATR (Average True Range):** Volatility metric measuring the average range of price movement over $N$ candles, accounting for gaps. Used here for swing prominence and dynamic zone width.
- **Circuit Breaker:** Automatic safety mechanism that disables further trade execution for the remainder of the trading day once cumulative realized losses exceed a threshold (5%).
- **Confirmation Delay:** The necessary waiting period (3 bars in this codebase) required before a swing pivot can be mathematically confirmed without using future data.
- **Look-Ahead Bias:** A backtesting error where an algorithm makes decisions using price data that would not have been available at that historical moment.
- **Neckline:** The horizontal or slanted support/resistance boundary in a Head & Shoulders pattern whose breach triggers trade execution.
- **Notional Exposure:** The total gross value of the underlying asset controlled by a contract ($Q \times P$).
- **Polarity Flip:** The technical principle where broken resistance transforms into support, or broken support transforms into resistance.
- **Prominence Filter:** A mathematical threshold requiring a candidate swing peak to stand out above neighboring price bars by a given percentage or ATR multiple.
- **Quantization:** The rounding of fractional continuous share calculations to match discrete exchange lot sizes (e.g., multiples of 25 for Nifty).
- **Reward-to-Risk (R:R):** The ratio of anticipated profit distance to maximum stop-loss risk distance. Must be $\ge 1.5$ for trade acceptance.
- **Slippage:** The difference between the expected execution price and the actual fill price caused by market movement or latency.
- **TOTP (Time-Based One-Time Password):** The algorithm used by authenticator apps (and `pyotp` in this codebase) to generate automated 2FA login tokens for Upstox daily access.
- **WAL (Write-Ahead Logging):** An SQLite journaling mode that enables concurrent read operations while writes are in progress.

---

### 3. Top 20 Configuration Parameters to Understand First
1. `PAPER_TRADING_BALANCE`: Account equity baseline.
2. `RISK_PER_TRADE`: Maximum fraction of capital risked on one trade (default: 0.02).
3. `MAX_POSITIONS`: Maximum simultaneous open positions (default: 3).
4. `MAX_DAILY_LOSS`: Daily circuit breaker trip percentage (default: 0.05).
5. `MIN_REWARD_RISK`: Minimum allowable R:R ratio (default: 1.5).
6. `MAX_LEVERAGE`: Maximum allowed notional leverage (default: 3.0x).
7. `USD_INR_RATE`: Currency conversion factor for crypto perpetuals (default: 85.0).
8. `target_mode`: Target selection method (`adaptive` vs `fixed_rr`).
9. `target_fixed_rr_multiple`: Multiplier for fixed target fallback (default: 1.5).
10. `zone_clearance_buffer_pct`: Space left before opposing S/R zone (default: 0.2%).
11. `swing_lookback`: Candles required on each side to confirm a swing (default: 3).
12. `min_prominence_pct`: Minimum swing depth percentage (default: 0.25%).
13. `zone_tolerance_pct`: Clustering tolerance for grouping swings (default: 0.5%).
14. `min_zone_width_pct`: Minimum vertical thickness of S/R bands (default: 0.2%).
15. `min_touches`: Reactions required before a zone is active (default: 2).
16. `max_zones`: Zone retention limit per symbol (default: 20).
17. `breakout_threshold_pct`: Penetration required to confirm breakout (default: 0.3%).
18. `enable_polarity_flips`: Whether broken S/R levels flip roles (default: True).
19. `indian_htf_interval`: Timeframe for Indian S/R discovery (default: `1d`).
20. `crypto_htf_interval`: Timeframe for Crypto S/R discovery (default: `1h`).

---

### 4. Top 10 Risks in the Current Implementation
1. **Zero Live Order Routing:** Attempting to trade live with this code will do nothing on the exchange. Orders are strictly simulated in SQLite.
2. **Unsecured Dashboard:** If deployed to a cloud server without an auth proxy, anyone can access settings, view trades, and toggle feeds.
3. **No Trailing Stop Execution:** Trailing stops and partial profit exits are modeled in backtesting and advisories, but `PaperTradingEngine` leaves stops completely static until hit.
4. **Optimistic Stop Fills:** Gap-downs through stop-losses assume fills at the stop price rather than the market gap price.
5. **No Options Backtesting:** Options strategies cannot be backtested historically; backtest reports only reflect underlying spot performance.
6. **No Real-Time Timeframe Resampling:** The system cannot assemble 1-minute bars into custom timeframes; it is bound to exchange native intervals.
7. **Single-Instrument Backtesting Bias:** Backtests do not model portfolio cash constraints or simultaneous multi-instrument margin calls.
8. **Lack of Crypto Lot Quantization:** Continuous float quantities (e.g., 0.11 ETH) are used rather than discrete Delta contract multiples.
9. **No Volume Profile Integration:** S/R levels rely purely on OHLC geometric price action without evaluating traded volume profiles or order book liquidity.
10. **Statistical Evidence Void:** The system has only 6 recorded trades in its database; there is no statistical proof of strategy alpha or profitability.

---

### 5. Implementation Status Matrix

```
=================================================================================================
                                  SYSTEM CAPABILITY MATRIX
=================================================================================================
FEATURE / SUBSYSTEM                   STATUS        EVIDENCE / NOTES
-------------------------------------------------------------------------------------------------
Delta WebSocket Ticker Feed           IMPLEMENTED   Auto-reconnect, exponential backoff (delta_exchange.py)
Delta REST Candle Ingestion           IMPLEMENTED   Paginated historical OHLCV (delta_exchange.py)
Upstox Headless TOTP 2FA Auto-Auth    IMPLEMENTED   pyotp + upstox-totp daily scheduled refresh (upstox_auth.py)
Upstox REST Candle Ingestion          IMPLEMENTED   Native 1d and 5m fetching; verified no 30m alias (ingestion.py)
Swing Pivot Detection                 IMPLEMENTED   ±3 candle window with ATR prominence filter (levels.py)
Zone Clustering & Enclosure           IMPLEMENTED   0.5% tolerance with 0.2% minimum width band (levels.py)
Rejection Wick & Touch Counting       IMPLEMENTED   >=35% wick detection & freshness scoring (levels.py)
Zone Polarity Flips (Broken S/R)      IMPLEMENTED   2 consecutive closes > 0.5% flips polarity (levels.py)
Zone Anti-Clutter Merging             IMPLEMENTED   Merges overlapping same-polarity zones (levels.py)
Adaptive Opposing-Zone Targets        IMPLEMENTED   Decoupled from fixed 1.5R; anchors to next zone (adaptive_target.py)
6 Core S/R Trading Setups             IMPLEMENTED   Bounce, Rejection, Breakout, Breakdown, Retests (signals.py)
Head & Shoulders Detection            IMPLEMENTED   Modular detector with S/R neckline confluence (head_and_shoulders.py)
Firsty Trend Continuation            IMPLEMENTED   20/50 EMA slope & separation with S/R confluence (trend_continuation.py)
Black-Scholes Options Sizing          IMPLEMENTED   ATM Call/Put routing for Indian indices (options/engine.py)
Currency-Aware Risk Management        IMPLEMENTED   Quote-currency conversion & 3x leverage ceiling (manager.py)
Daily Circuit Breaker                 IMPLEMENTED   5% daily loss cutoff with IST timezone awareness (manager.py)
Trade Management Advisories           IMPLEMENTED   Evaluates profit taking, stop tightening, invalidation (trade_manager.py)
Telegram Alert Dispatch               IMPLEMENTED   Rate-limited (5m) with MD5 deduplication (notifier.py)
FastAPI Web Dashboard                 IMPLEMENTED   Next-Gen Quant Terminal UI with TradingView charts (app.py)
-------------------------------------------------------------------------------------------------
Trailing Stop Live Execution          PARTIAL       Coded in exits.py & backtest, but NOT in PaperTradingEngine
Backtesting Engine                    PARTIAL       Fixed look-ahead bias & FX, but bypasses options & portfolio
Exchange Order Management (OMS)       MISSING       Zero live order placement endpoints exist in codebase
Dynamic Bar Resampling                MISSING       Relies strictly on exchange native candle intervals
Dashboard Authentication              MISSING       No password, session, or token verification on API routes
Standardized Contract Multipliers     MISSING       Sizes in raw token floats rather than integer contract lots
=================================================================================================
```

---

### 6. Recommended Source Code Reading Order
To gain an intimate developer understanding of the application, inspect the source files in this sequence:

1. [algo_monitor/config/instruments.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/config/instruments.py): Understand what assets are monitored and how exchange properties are stored.
2. [algo_monitor/config/settings.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/config/settings.py): Understand default parameters, risk limits, and environment variable bindings.
3. [algo_monitor/data/models.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/data/models.py): Understand the fundamental data structures (`Candle`, `TickerUpdate`).
4. [algo_monitor/database.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/database.py): Inspect SQLite schemas, indexing, and connection lifecycle.
5. [algo_monitor/strategy/levels.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/levels.py): Read the heart of the technical analysis engine: swing detection, clustering, polarity flips, and strength scoring.
6. [algo_monitor/strategy/adaptive_target.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/adaptive_target.py): Understand how targets anchor to opposing market structure.
7. [algo_monitor/strategy/signals.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/strategy/signals.py): Trace the exact logic that converts price action near zones into trade signals.
8. [algo_monitor/risk/manager.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/risk/manager.py): Trace how risk budgets, leverage ceilings, and currency conversions size positions.
9. [algo_monitor/options/engine.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/options/engine.py): Study the Black-Scholes strike selection and defined-risk option routing.
10. [algo_monitor/trading/engine.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/trading/engine.py): Trace how simulated trades are recorded, monitored, and closed.
11. [algo_monitor/trading/trade_manager.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/trading/trade_manager.py): Examine open position structural evaluation and advisory state changes.
12. [algo_monitor/alerts/notifier.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/alerts/notifier.py): Understand how alerts are formatted, deduplicated, and dispatched.
13. [algo_monitor/main.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/main.py): See how the scheduler, threads, feeds, and engine are orchestrated together.
14. [algo_monitor/dashboard/app.py](file:///d:/Projects/Algo%20Monitor/algo_monitor/dashboard/app.py): Trace the REST endpoints and data feeding the web terminal.

---

### 7. Ten Critical Questions to Answer Before Ever Considering Real-Money Trading
1. **Where is the live broker order adapter?**  
   *Current Reality:* None exists. You must build and audit an execution gateway with order acknowledgments, rejects, and fills before connecting live capital.
2. **What happens during an internet or API disconnection while a live position is open?**  
   *Current Reality:* The engine monitors stops locally. If the machine loses power or internet, no exchange-side stop-loss order exists to protect your capital.
3. **Is the historical win rate statistically valid?**  
   *Current Reality:* The live database contains only 6 trades. You must run rigorous, out-of-sample backtests across multiple market regimes (trending, choppy, high-volatility) before trusting capital to this strategy.
4. **How are market orders handled during illiquid market openings?**  
   *Current Reality:* The code assumes theoretical fills at candle closes and exact limit prices. Real market slippage during gap openings can be multiples of theoretical estimates.
5. **How does the system handle exchange contract lot sizes?**  
   *Current Reality:* Sizing is calculated in continuous floats. Live exchanges reject non-standardized lot sizes.
6. **Are options Greeks calibrated to live implied volatility?**  
   *Current Reality:* `OptionsEngine` uses fixed historical IV baselines (e.g., 14% for Nifty, 16% for Bank Nifty). Live market IV spikes or crashes will distort premium pricing.
7. **Is the web dashboard accessible to the public internet?**  
   *Current Reality:* There is no password protection on API routes. Anyone could toggle your feeds or view positions unless protected by a firewall or VPN.
8. **What is the maximum portfolio drawdown under correlated market crashes?**  
   *Current Reality:* The system permits 3 simultaneous positions without cross-asset correlation checks. If NIFTY, BANKNIFTY, and RELIANCE are all long during an unexpected crash, all three will hit stop-loss simultaneously.
9. **How does the system treat exchange tick sizes?**  
   *Current Reality:* Equities trade in ₹0.05 tick increments. S/R calculations use floating-point numbers that must be rounded to valid exchange ticks.
10. **Who is responsible for monitoring overnight gap risk?**  
    *Current Reality:* Indian equity markets close at 15:30 IST and reopen at 09:15 IST the next business day. Major macroeconomic events can cause the market to open 2% beyond your stop-loss, causing severe capital impairment.
