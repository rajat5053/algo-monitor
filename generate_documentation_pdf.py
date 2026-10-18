"""
Generate comprehensive PDF documentation for the Algo Monitor project.
Uses PyMuPDF (fitz.Story) for crisp, professional typography and layout.
"""

import sys
from pathlib import Path
import fitz

OUTPUT_PATH = Path("d:/Projects/Algo Monitor/Algo_Monitor_Complete_Documentation.pdf")

html_content = """
<style>
    @page {
        margin: 16mm 16mm 16mm 16mm;
    }
    body {
        font-family: sans-serif;
        font-size: 8.8pt;
        line-height: 1.42;
        color: #1e293b;
    }
    .cover {
        text-align: center;
        padding-top: 40px;
        padding-bottom: 30px;
    }
    .cover-title {
        font-size: 24pt;
        font-weight: bold;
        color: #0f172a;
        margin-bottom: 6px;
    }
    .cover-subtitle {
        font-size: 13pt;
        color: #2563eb;
        font-weight: 600;
        margin-bottom: 15px;
    }
    .cover-desc {
        font-size: 9.5pt;
        color: #64748b;
        max-width: 600px;
        margin: 0 auto 25px auto;
        line-height: 1.5;
    }
    .meta-box {
        display: inline-block;
        background-color: #f8fafc;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        padding: 10px 18px;
        font-size: 8.5pt;
        color: #334155;
        text-align: left;
    }
    h1 {
        font-size: 15pt;
        color: #0f172a;
        border-bottom: 2px solid #2563eb;
        padding-bottom: 4px;
        margin-top: 22px;
        margin-bottom: 10px;
        page-break-after: avoid;
    }
    h2 {
        font-size: 11.5pt;
        color: #1e40af;
        margin-top: 14px;
        margin-bottom: 6px;
        border-bottom: 1px solid #e2e8f0;
        padding-bottom: 2px;
        page-break-after: avoid;
    }
    h3 {
        font-size: 9.8pt;
        color: #0369a1;
        margin-top: 10px;
        margin-bottom: 4px;
        page-break-after: avoid;
    }
    p {
        margin-bottom: 6px;
        text-align: justify;
    }
    ul, ol {
        margin-top: 3px;
        margin-bottom: 8px;
        padding-left: 18px;
    }
    li {
        margin-bottom: 3px;
    }
    .badge {
        display: inline-block;
        background-color: #e0f2fe;
        color: #0369a1;
        padding: 1px 5px;
        border-radius: 3px;
        font-weight: bold;
        font-size: 7.8pt;
    }
    .badge-green {
        background-color: #dcfce7;
        color: #15803d;
    }
    .badge-amber {
        background-color: #fef3c7;
        color: #b45309;
    }
    .badge-red {
        background-color: #fee2e2;
        color: #b91c1c;
    }
    table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 6px;
        margin-bottom: 10px;
    }
    th {
        background-color: #f1f5f9;
        color: #1e293b;
        font-weight: bold;
        text-align: left;
        padding: 5px 7px;
        border: 1px solid #cbd5e1;
        font-size: 8.2pt;
    }
    td {
        padding: 4.5px 7px;
        border: 1px solid #e2e8f0;
        font-size: 8pt;
        vertical-align: top;
    }
    tr:nth-child(even) td {
        background-color: #f8fafc;
    }
    .callout {
        background-color: #eff6ff;
        border-left: 3.5px solid #3b82f6;
        padding: 7px 11px;
        margin: 8px 0;
        border-radius: 3px;
        font-size: 8.3pt;
    }
    .callout-warn {
        background-color: #fffbeb;
        border-left: 3.5px solid #f59e0b;
        padding: 7px 11px;
        margin: 8px 0;
        border-radius: 3px;
        font-size: 8.3pt;
    }
    .callout-alert {
        background-color: #fef2f2;
        border-left: 3.5px solid #ef4444;
        padding: 7px 11px;
        margin: 8px 0;
        border-radius: 3px;
        font-size: 8.3pt;
    }
    .code-box {
        background-color: #0f172a;
        color: #f8fafc;
        padding: 8px 12px;
        border-radius: 4px;
        font-family: monospace;
        font-size: 7.8pt;
        line-height: 1.35;
        margin: 8px 0;
    }
    .page-break {
        page-break-before: always;
    }
</style>

<div class="cover">
    <div class="cover-title">⚡ ALGO MONITOR v2.0</div>
    <div class="cover-subtitle">Complete Architecture, Quant Strategies & Risk Management Manual</div>
    <div class="cover-desc">
        A comprehensive technical and operational reference covering system capabilities, full file directory breakdown, market terminology, price-action strategy mechanics, automated 2FA ingestion, Telegram alert diagnostics, and quant risk management rules.
    </div>
    <div class="meta-box">
        <strong>Application:</strong> Algo Monitor &nbsp;|&nbsp; <strong>Markets:</strong> Indian Equities/Indices (NSE via Upstox) &amp; Crypto (Delta Exchange)<br>
        <strong>Author/Role:</strong> Quantitative Trading &amp; Systems Architecture &nbsp;|&nbsp; <strong>Target Account:</strong> ₹15,000 Starting Capital (Paper Simulation)<br>
        <strong>Environment:</strong> Python 3.10+, FastAPI, SQLite, APScheduler, Upstox v3, Delta API, Telegram Bot
    </div>
</div>

<hr style="border:none; border-top:1px solid #cbd5e1; margin: 15px 0;">

<h1>1. Executive Summary & System Overview</h1>
<p>
<strong>Algo Monitor</strong> is an institutional-grade, multi-asset trading platform designed to monitor, scan, analyze, and simulate trading operations across the <strong>Indian National Stock Exchange (NSE)</strong> and <strong>Global Crypto Derivatives</strong> markets. The platform operates on a strict quantitative framework with systematic risk controls, automated execution simulation, and multi-channel alerting.
</p>

<h2>Core Architectural Pillars</h2>
<ul>
    <li><strong>Dual-Market Infrastructure:</strong> Dedicated separation between Indian Equities/Indices (NSE indices, F&amp;O stock constituents) and Crypto Markets (Spot, Perpetual Futures, Top Gainers/Losers, and Delta Options).</li>
    <li><strong>Automated 2FA Authentication Engine:</strong> Headless daily authentication with the Upstox API via automated TOTP generation, handling daily login and token renewals without manual OAuth browser intervention.</li>
    <li><strong>Multi-Timeframe Strategy Engine:</strong> Continuous scanning of Higher Timeframe (4h/1d) support and resistance clusters combined with Lower Timeframe (5m/30m) candle confirmation to detect high-probability trading setups.</li>
    <li><strong>Options Execution &amp; Greeks Pricing:</strong> Black-Scholes-Merton model calculating theoretical option premiums, implied volatility (IV), and Greeks (Delta, Gamma, Theta, Vega). Real-time ATM strike mapping, lot-size auto-sizing, and CE/PE contract routing.</li>
    <li><strong>Quant Risk Management Engine:</strong> Strict trade protection enforcing a 2.0% risk budget per setup, a 3.0x broker leverage ceiling, a maximum of 3 concurrent positions, and a 5.0% daily portfolio drawdown circuit breaker.</li>
    <li><strong>Real-Time Financial Terminal (Web Dashboard):</strong> FastAPI + Vanilla JS dark-mode terminal running at <code>http://127.0.0.1:8502</code>, providing 5-second live ticker streaming, interactive option chains with constituent stock sub-filters, open position tracking, and configuration controls.</li>
    <li><strong>Multi-Channel Alert Dispatcher:</strong> Telegram Bot and console notifications with message hashing, duplicate prevention, freshness validation (30-minute staleness guard), and individual market toggle filters.</li>
</ul>

<div class="page-break"></div>

<h1>2. Complete Project Directory & File-by-File Breakdown</h1>
<p>
The codebase follows a modular design with separation between configuration, data feeds, quantitative strategies, risk controls, paper execution, alerts, and user interface.
</p>

<table>
    <tr>
        <th style="width:28%">File Path</th>
        <th style="width:18%">Module</th>
        <th style="width:54%">Purpose & Core Responsibilities</th>
    </tr>
    <tr>
        <td><code>algo_monitor/main.py</code></td>
        <td>Orchestration / CLI</td>
        <td>Main entry point for CLI and background services. Configures <strong>APScheduler</strong> for candle ingestion (every 15m), strategy scanning (every 5m), and position monitoring (every 30s). Manages graceful startup and shutdown.</td>
    </tr>
    <tr>
        <td><code>algo_monitor/database.py</code></td>
        <td>Persistence Layer</td>
        <td>SQLite database interface with thread-safe connections. Manages tables: <code>candles</code>, <code>zones</code>, <code>signals</code>, <code>trades</code>, <code>positions</code>, <code>alert_log</code>, and <code>system_state</code>. Provides atomic commit and rollback handling.</td>
    </tr>
    <tr>
        <td><code>algo_monitor/config/settings.py</code></td>
        <td>Configuration</td>
        <td>Pydantic-based configuration management loading environment variables from <code>.env</code>. Defines dataclasses for <code>StrategyConfig</code>, <code>RiskConfig</code>, <code>TradingConfig</code>, <code>AlertConfig</code>, and <code>DatabaseConfig</code>.</td>
    </tr>
    <tr>
        <td><code>algo_monitor/config/instruments.py</code></td>
        <td>Instrument Registry</td>
        <td>Master symbol directory mapping tickers to exchanges (NSE, Delta), asset classes (Index, Equity, Crypto), lot sizes (Nifty=25, BankNifty=15), tick sizes, and market categories (Indian vs. Crypto).</td>
    </tr>
    <tr>
        <td><code>algo_monitor/data/upstox.py</code></td>
        <td>Upstox Client</td>
        <td>Upstox API v3 client. Fetches real-time LTP quotes, historical OHLCV candles, and live option chains. Handles Bearer token authorization and HTTP rate limits.</td>
    </tr>
    <tr>
        <td><code>algo_monitor/data/upstox_auth.py</code></td>
        <td>2FA Auto-Login</td>
        <td>Automated daily 2FA login engine. Uses client credentials, mobile number, PIN, and TOTP secret (<code>pyotp</code>) to authenticate with Upstox, capture authorization codes, and persist active access tokens.</td>
    </tr>
    <tr>
        <td><code>algo_monitor/data/delta_exchange.py</code></td>
        <td>Delta Crypto Client</td>
        <td>REST and WebSocket client for Delta Exchange India / Global. Retrieves spot prices, perpetual futures orderbooks, 24h ticker statistics, and live crypto option chains.</td>
    </tr>
    <tr>
        <td><code>algo_monitor/data/candle_store.py</code></td>
        <td>Candle Storage</td>
        <td>High-performance time-series storage for OHLCV bars. Stores timestamps, open, high, low, close, and volume. Implements fast queries and gap detection for multi-timeframe analysis.</td>
    </tr>
    <tr>
        <td><code>algo_monitor/data/ingestion.py</code></td>
        <td>Data Ingestion</td>
        <td>Orchestrator that iterates through enabled instruments to fetch and persist the latest historical candles across 4h, 1d, 5m, and 15m timeframes.</td>
    </tr>
    <tr>
        <td><code>algo_monitor/data/models.py</code></td>
        <td>Data Models</td>
        <td>Standardized dataclasses: <code>Candle</code>, <code>MarketQuote</code>, <code>OrderbookLevel</code>, and <code>MarketStatus</code>. Ensures unified data shapes across different exchange APIs.</td>
    </tr>
    <tr>
        <td><code>algo_monitor/strategy/levels.py</code></td>
        <td>Support &amp; Resistance</td>
        <td>Calculates swing highs/lows using a bilateral lookback window. Groups nearby levels within <code>zone_tolerance_pct</code> into zones. Tracks touch frequency, recency, and composite strength scores.</td>
    </tr>
    <tr>
        <td><code>algo_monitor/strategy/signals.py</code></td>
        <td>Signal Generator</td>
        <td>Core rule engine implementing 6 setup types: Bounce, Rejection, Breakout, Breakdown, Retest, and Approaching Zone. Calculates entry, stop loss, take profit, R:R ratio, and invalidation rules.</td>
    </tr>
    <tr>
        <td><code>algo_monitor/strategy/scanner.py</code></td>
        <td>Strategy Scanner</td>
        <td>Multi-instrument scanner matching live candles against active zones. Features Indian market trading hours awareness (09:15–15:30 IST) to suppress stale historical alerts during market closures.</td>
    </tr>
    <tr>
        <td><code>algo_monitor/risk/manager.py</code></td>
        <td>Risk Engine</td>
        <td>Quant risk validator: sizes positions by stop-loss distance (2% risk rule), limits broker leverage to 3.0x, enforces max 3 open positions, and triggers the 5% daily loss circuit breaker.</td>
    </tr>
    <tr>
        <td><code>algo_monitor/options/engine.py</code></td>
        <td>Options Engine</td>
        <td>Translates underlying spot setups into options trades. Selects ATM strikes, routes Call (CE) for longs and Put (PE) for shorts, sizes contracts by lot specifications, and caps premium stop loss at 40%.</td>
    </tr>
    <tr>
        <td><code>algo_monitor/options/pricing.py</code></td>
        <td>Black-Scholes Model</td>
        <td>Mathematical Black-Scholes-Merton option pricing engine. Calculates theoretical Call/Put premiums and analytical Greeks: Delta (&Delta;), Gamma (&Gamma;), Theta (&Theta;), Vega (&nu;), and Rho (&rho;).</td>
    </tr>
    <tr>
        <td><code>algo_monitor/options/models.py</code></td>
        <td>Options Models</td>
        <td>Dataclasses for options trading: <code>OptionContract</code>, <code>OptionGreeks</code>, <code>OptionTradeSetup</code>, and <code>OptionType</code> (Call vs. Put).</td>
    </tr>
    <tr>
        <td><code>algo_monitor/trading/engine.py</code></td>
        <td>Paper Trading</td>
        <td>Simulated execution engine. Matches pending orders, tracks live mark-to-market P&amp;L, simulates slippage (0.03%) and exchange fees (0.05%), and triggers automated SL/TP exits.</td>
    </tr>
    <tr>
        <td><code>algo_monitor/trading/performance.py</code></td>
        <td>Quant Analytics</td>
        <td>Performance calculator: total equity, daily P&amp;L, win rate, profit factor, Sharpe ratio, max drawdown, average winner/loser, and expectancy.</td>
    </tr>
    <tr>
        <td><code>algo_monitor/alerts/notifier.py</code></td>
        <td>Alert Manager</td>
        <td>Alert dispatcher managing Telegram Bot and Console outputs. Features MD5 message hashing, 5-minute rate-limiting, 30-minute freshness checks, and market toggle filters.</td>
    </tr>
    <tr>
        <td><code>algo_monitor/dashboard/app.py</code></td>
        <td>Web Backend</td>
        <td>FastAPI web dashboard backend. Provides REST endpoints for market data, active positions, option chains, F&amp;O securities, token refresh, and market toggle controls.</td>
    </tr>
    <tr>
        <td><code>algo_monitor/dashboard/static/app.js</code></td>
        <td>Frontend Engine</td>
        <td>Client-side dashboard logic. Manages 5-second live polling, tab routing, dual-dropdown index/constituent option chain selection, and live P&amp;L color coding.</td>
    </tr>
    <tr>
        <td><code>algo_monitor/dashboard/static/style.css</code></td>
        <td>Terminal Theme</td>
        <td>Custom dark-mode CSS with glassmorphism effects, responsive CSS Grid layouts, color-coded price badges, and responsive tables.</td>
    </tr>
    <tr>
        <td><code>algo_monitor/dashboard/templates/index.html</code></td>
        <td>Dashboard Template</td>
        <td>Jinja2 HTML template containing Overview, Indian Market, Crypto Market, Option Chain Viewer, Positions, Performance, and Settings tabs.</td>
    </tr>
</table>

<div class="page-break"></div>

<h1>3. Comprehensive Trading Acronyms & Glossary</h1>
<p>
This section defines all abbreviations, financial acronyms, and statistical terms used across Algo Monitor's dashboard, logs, code, and alerts.
</p>

<table>
    <tr>
        <th style="width:16%">Acronym / Term</th>
        <th style="width:28%">Full Terminology</th>
        <th style="width:56%">Quantitative Definition & Practical Application</th>
    </tr>
    <tr>
        <td><strong>HTF</strong></td>
        <td>Higher Timeframe</td>
        <td>The macro candle interval (typically <strong>4-Hour</strong> or <strong>Daily</strong>) used to identify major structural support and resistance levels. HTF levels carry higher liquidity and statistical reliability.</td>
    </tr>
    <tr>
        <td><strong>LTF</strong></td>
        <td>Lower Timeframe</td>
        <td>The micro candle interval (typically <strong>5-Minute</strong> or <strong>15-Minute</strong>) used for trade execution, candle close confirmation, and precise trigger timing against HTF zones.</td>
    </tr>
    <tr>
        <td><strong>LTP</strong></td>
        <td>Last Traded Price</td>
        <td>The most recent execution price recorded by the exchange. Used for mark-to-market calculations and live distance-to-zone monitoring.</td>
    </tr>
    <tr>
        <td><strong>OHLCV</strong></td>
        <td>Open, High, Low, Close, Volume</td>
        <td>Standardized financial candlestick data tuple representing the price movement and total transaction volume within a specific time bar.</td>
    </tr>
    <tr>
        <td><strong>S/R</strong></td>
        <td>Support / Resistance</td>
        <td>Horizontal price bands where buying pressure (support) or selling pressure (resistance) historically halts or reverses price movement.</td>
    </tr>
    <tr>
        <td><strong>ATM</strong></td>
        <td>At The Money</td>
        <td>An option contract whose strike price is identical or closest to the current spot price of the underlying asset. ATM options carry a Delta of ~0.50.</td>
    </tr>
    <tr>
        <td><strong>ITM</strong></td>
        <td>In The Money</td>
        <td>An option possessing intrinsic value. A Call is ITM when Spot &gt; Strike; a Put is ITM when Spot &lt; Strike.</td>
    </tr>
    <tr>
        <td><strong>OTM</strong></td>
        <td>Out of The Money</td>
        <td>An option possessing only extrinsic (time) value. A Call is OTM when Spot &lt; Strike; a Put is OTM when Spot &gt; Strike.</td>
    </tr>
    <tr>
        <td><strong>CE</strong></td>
        <td>Call European</td>
        <td>Standard European-style call option contract conferring the right (not obligation) to buy the underlying asset at the strike price on expiry. Traded on NSE.</td>
    </tr>
    <tr>
        <td><strong>PE</strong></td>
        <td>Put European</td>
        <td>Standard European-style put option contract conferring the right to sell the underlying asset at the strike price on expiry. Traded on NSE.</td>
    </tr>
    <tr>
        <td><strong>DTE</strong></td>
        <td>Days to Expiry</td>
        <td>The exact number of calendar days remaining until the option contract reaches maturity and ceases trading. Critical for calculating time decay (Theta).</td>
    </tr>
    <tr>
        <td><strong>IV</strong></td>
        <td>Implied Volatility</td>
        <td>The market's forward-looking consensus of the underlying asset's annualized price volatility, derived inversely from the current market option premium.</td>
    </tr>
    <tr>
        <td><strong>OI</strong></td>
        <td>Open Interest</td>
        <td>The aggregate number of outstanding, active option or futures contracts that have not yet been settled, exercised, or offset by market participants.</td>
    </tr>
    <tr>
        <td><strong>Delta (&Delta;)</strong></td>
        <td>Option Delta</td>
        <td>The first-order Greek measuring the expected change in option premium for a ₹1.00 move in the underlying spot price (Calls: 0 to +1.0, Puts: -1.0 to 0).</td>
    </tr>
    <tr>
        <td><strong>Gamma (&Gamma;)</strong></td>
        <td>Option Gamma</td>
        <td>The second-order Greek measuring the rate of change of Delta for a ₹1.00 move in the underlying spot price. Highest at ATM strikes near expiry.</td>
    </tr>
    <tr>
        <td><strong>Theta (&Theta;)</strong></td>
        <td>Option Theta (Time Decay)</td>
        <td>The rate of daily loss in option premium resulting solely from the passage of one calendar day, assuming all other variables remain static.</td>
    </tr>
    <tr>
        <td><strong>Vega (&nu;)</strong></td>
        <td>Option Vega</td>
        <td>The sensitivity of the option premium to a 1.0% change in implied volatility. Higher in longer-dated options.</td>
    </tr>
    <tr>
        <td><strong>SL</strong></td>
        <td>Stop Loss</td>
        <td>A predetermined price threshold where a losing position is automatically liquidated to protect capital from adverse market moves.</td>
    </tr>
    <tr>
        <td><strong>TP</strong></td>
        <td>Take Profit / Target</td>
        <td>A predetermined price objective where a winning position is closed to lock in realized gains.</td>
    </tr>
    <tr>
        <td><strong>RR / R:R</strong></td>
        <td>Reward-to-Risk Ratio</td>
        <td>Mathematical ratio of potential profit to potential risk: <code>(Target - Entry) / (Entry - Stop_Loss)</code>. The platform rejects trades with R:R &lt; 1.5.</td>
    </tr>
    <tr>
        <td><strong>F&amp;O</strong></td>
        <td>Futures &amp; Options</td>
        <td>The derivatives segment of the National Stock Exchange (NSE) covering index futures, index options, and single-stock derivatives.</td>
    </tr>
    <tr>
        <td><strong>TOTP</strong></td>
        <td>Time-based One-Time Password</td>
        <td>An RFC 6238 algorithmic security token used by <code>upstox_auth.py</code> to automatically generate 6-digit 2FA login passcodes using a shared base32 secret.</td>
    </tr>
    <tr>
        <td><strong>P&amp;L</strong></td>
        <td>Profit and Loss</td>
        <td>Financial gain or loss from trading. Divided into <strong>Unrealized P&amp;L</strong> (mark-to-market of open positions) and <strong>Realized P&amp;L</strong> (booked upon position closure).</td>
    </tr>
</table>

<div class="page-break"></div>

<h1>4. Quantitative Trading Strategies & Price Action Mechanics</h1>
<p>
Algo Monitor executes a disciplined <strong>Zone-to-Zone Price Action</strong> methodology. Instead of relying on lagging indicators (like moving averages or RSI oscillators), the engine relies entirely on structural swing points, liquidity clusters, and candle close confirmations.
</p>

<h2>Support &amp; Resistance Zone Detection Architecture</h2>
<p>
The <code>LevelDetector</code> module in <code>levels.py</code> converts raw historical candle series into actionable price zones through a 3-step pipeline:
</p>
<ol>
    <li><strong>Bilateral Swing Point Identification:</strong> A candle at index <em>i</em> is recognized as a swing high only if its high is strictly higher than all candles in the window <code>[i - lookback, i + lookback]</code> (default lookback = 5 candles). This ensures <strong>zero look-ahead bias</strong>.</li>
    <li><strong>Zone Clustering:</strong> Swing points occurring within <code>zone_tolerance_pct</code> (default 0.8%) of each other are merged into a single <code>Zone</code>. The zone spans from <code>price_low</code> (lowest swing in cluster) to <code>price_high</code> (highest swing in cluster).</li>
    <li><strong>Strength Scoring:</strong> Each zone is assigned a composite strength metric (0.0 to 1.0) based on:
        <ul>
            <li><strong>Touch Count:</strong> Number of distinct candle wicks/reversals reacting at the zone (diminishing returns above 5 touches).</li>
            <li><strong>Recency:</strong> Exponential decay penalty applied to older zones without recent touches.</li>
            <li><strong>Bounce Magnitude:</strong> Average percentage distance price moved away following previous touches.</li>
        </ul>
    </li>
</ol>

<h2>The 6 Core Setup Types Explained</h2>

<h3>1. Bounce from Support (<code>bounce_support</code>) — LONG</h3>
<p>
<strong>Hypothesis:</strong> Buyers are defending a confirmed support zone. Price touches or enters the support band <code>[price_low, price_high]</code>, forms a lower wick demonstrating liquidity absorption, and prints a bullish candle close above the zone mid-point.<br>
<strong>Execution:</strong> Enter LONG on candle close. Stop Loss is set below <code>price_low - buffer</code>. Target is the next overhead resistance zone.
</p>

<h3>2. Rejection from Resistance (<code>rejection_resistance</code>) — SHORT</h3>
<p>
<strong>Hypothesis:</strong> Sellers are defending an overhead resistance zone. Price tests the resistance band, fails to close above it, forms an upper rejection wick, and closes below the zone mid-point.<br>
<strong>Execution:</strong> Enter SHORT on candle close. Stop Loss is placed above <code>price_high + buffer</code>. Target is the nearest lower support zone.
</p>

<h3>3. Breakout above Resistance (<code>breakout_resistance</code>) — LONG</h3>
<p>
<strong>Hypothesis:</strong> Institutional demand overwhelms available supply at resistance, triggering a momentum expansion.<br>
<strong>Condition:</strong> A complete candle closes cleanly above the resistance zone upper boundary: <code>close &gt; price_high + (mid_price &times; breakout_threshold_pct)</code>.<br>
<strong>Execution:</strong> Enter LONG. Stop Loss is positioned back inside the broken zone (below <code>price_high</code>).
</p>

<h3>4. Breakdown below Support (<code>breakdown_support</code>) — SHORT</h3>
<p>
<strong>Hypothesis:</strong> Bids are exhausted at support, triggering long liquidation and sell stops.<br>
<strong>Condition:</strong> A complete candle closes decisively below the support zone lower boundary: <code>close &lt; price_low - (mid_price &times; breakout_threshold_pct)</code>.<br>
<strong>Execution:</strong> Enter SHORT. Stop Loss is positioned back inside the broken zone (above <code>price_low</code>).
</p>

<h3>5. Retest Breakout / Retest Breakdown (<code>retest_breakout</code> / <code>retest_breakdown</code>) — HIGH CONVICTION</h3>
<p>
<strong>Hypothesis:</strong> The principle of <em>Role Reversal</em> (broken resistance becomes new support; broken support becomes new resistance). Following an initial breakout, price pulls back to re-test the boundary. If the level holds on the retest and prints a reversal candle, it confirms the breakout was genuine rather than a liquidity trap (fakeout).<br>
<strong>Execution:</strong> Offers the highest win-rate and tightest risk parameters. Stop Loss is placed just beyond the re-tested boundary.
</p>

<h3>6. Approaching Zone (<code>approaching_zone</code>) — EARLY WARNING</h3>
<p>
<strong>Hypothesis:</strong> Proximity alert. Triggered when price is within <code>approach_threshold_pct</code> (default 1.0%) of a key zone but has not yet touched it.<br>
<strong>Execution:</strong> Generates an early warning alert on Telegram/Dashboard to notify the trader to prepare for an imminent setup.
</p>

<h2>Options Execution &amp; Strike Routing Strategy</h2>
<p>
When an underlying index or equity generates an approved directional setup, the <code>OptionsEngine</code> automatically routes the trade into an options contract:
</p>
<ul>
    <li><strong>Directional Strike Selection:</strong> Bullish setups (<code>LONG</code>) trigger <strong>Call (CE)</strong> contracts; Bearish setups (<code>SHORT</code>) trigger <strong>Put (PE)</strong> contracts.</li>
    <li><strong>Strike Mapping:</strong> The engine identifies the At-The-Money (ATM) strike using the exact strike step (Nifty: 50 pts, Bank Nifty: 100 pts, Reliance: 20 pts).</li>
    <li><strong>Greeks-Based Sizing:</strong> With Delta ~0.50 at ATM, the underlying stop loss distance is multiplied by Delta to determine the option premium stop loss. A hard risk cap limits the maximum stop loss on the option premium to <strong>40% of the entry price</strong>.</li>
    <li><strong>Capital Allocation:</strong> Option buyers cannot allocate more than 45% of total account capital (~₹6,750 for a ₹15,000 account) to a single options position, preventing ruin during periods of elevated volatility.</li>
</ul>

<div class="page-break"></div>

<h1>5. Telegram Alert Breakdown &amp; Diagnostic Guide</h1>
<p>
Every alert dispatched to Telegram or logged to the console contains structured quantitative parameters. Understanding each line is vital for evaluating signal quality.
</p>

<div class="code-box">
🔔 <b>Retest Breakout</b><br><br>
📊 <b>RELIANCE</b> (upstox)<br>
📈 Direction: LONG<br>
⏰ Timeframe: 5m<br>
📍 Zone: support [1160.00 – 1168.50]<br>
💪 Zone strength: 0.85<br>
🎯 Entry ref: 1170.30<br>
🛑 Stop loss: 1156.20<br>
✅ Target: 1198.50<br>
⚖️ R:R = 2.00<br><br>
📝 Retest of broken resistance (now support) [1160.00 - 1168.50]. Level held with bullish 5m close.<br><br>
❌ Invalidation: Candle close below 1156.20
</div>

<h2>Detailed Field-by-Field Analysis</h2>

<table>
    <tr>
        <th style="width:24%">Alert Field</th>
        <th style="width:24%">Typical Value</th>
        <th style="width:52%">Meaning, Interpretation &amp; Diagnostic Guidance</th>
    </tr>
    <tr>
        <td><strong>Setup Header</strong></td>
        <td><code>Retest Breakout</code></td>
        <td>The pattern classified by the signal generator. Identifies the strategic context (Bounce, Rejection, Breakout, Retest, or Approaching).</td>
    </tr>
    <tr>
        <td><strong>Symbol &amp; Exchange</strong></td>
        <td><code>RELIANCE (upstox)</code></td>
        <td>The trading instrument and source datafeed. Enables immediate identification of the market segment (NSE Equity, Index, or Crypto).</td>
    </tr>
    <tr>
        <td><strong>Direction</strong></td>
        <td><code>LONG / SHORT</code></td>
        <td>The proposed trade bias. LONG indicates buying spot/futures or purchasing Calls (CE); SHORT indicates selling futures or purchasing Puts (PE).</td>
    </tr>
    <tr>
        <td><strong>Timeframe</strong></td>
        <td><code>5m</code></td>
        <td>The lower timeframe where the setup candle closed and triggered execution. Confirms that higher timeframe zones were respected on micro bars.</td>
    </tr>
    <tr>
        <td><strong>Zone Coordinates</strong></td>
        <td><code>[1160.00 – 1168.50]</code></td>
        <td>The upper and lower bounds of the structural support/resistance band. Informs where institutional orders are clustered.</td>
    </tr>
    <tr>
        <td><strong>Zone Strength</strong></td>
        <td><code>0.85 (Scale: 0.0 to 1.0)</code></td>
        <td>
            <strong>Composite quality score:</strong><br>
            &bull; <code>&gt; 0.75</code>: High strength. Multiple confirmed touches with strong historical bounces.<br>
            &bull; <code>0.50 – 0.75</code>: Moderate strength. Standard valid level.<br>
            &bull; <code>&lt; 0.50</code>: Weak or newly formed level with limited touch history.
        </td>
    </tr>
    <tr>
        <td><strong>Entry Ref</strong></td>
        <td><code>1170.30</code></td>
        <td>The theoretical execution price, calibrated to the closing price of the confirmation candle.</td>
    </tr>
    <tr>
        <td><strong>Stop Loss (SL)</strong></td>
        <td><code>1156.20</code></td>
        <td>The exact price level where the trade idea is deemed invalid. Position sizing guarantees that hitting this level loses no more than the risk budget (2%).</td>
    </tr>
    <tr>
        <td><strong>Target (TP)</strong></td>
        <td><code>1198.50</code></td>
        <td>The projected profit objective, mapped directly to the next structural zone or calculated via a fixed risk multiple.</td>
    </tr>
    <tr>
        <td><strong>R:R Ratio</strong></td>
        <td><code>2.00</code></td>
        <td>The Reward-to-Risk ratio: <code>(Target - Entry) / (Entry - Stop_Loss)</code>. Must satisfy the platform minimum of &ge; 1.5 to be eligible for execution.</td>
    </tr>
    <tr>
        <td><strong>Context / Reason</strong></td>
        <td><em>Descriptive text</em></td>
        <td>Plain-English summary detailing candle dynamics, wick rejections, and structural zone interactions that triggered the algorithm.</td>
    </tr>
    <tr>
        <td><strong>❌ Invalidation</strong></td>
        <td><code>Candle close below 1156.20</code></td>
        <td>
            <strong>The structural invalidation rule:</strong> Defines the precise market event that disproves the trade thesis. If price breaches this level, the setup is canceled immediately, and any open position is closed without hesitation.
        </td>
    </tr>
</table>

<div class="page-break"></div>

<h1>6. Quantitative Risk Management Engine &amp; Capital Rules</h1>
<p>
The <code>RiskManager</code> module in <code>risk/manager.py</code> acts as an independent guardian. Every candidate signal must pass all risk checks before the paper trading engine can accept it.
</p>

<h2>The 7 Immutable Risk Rules</h2>

<h3>Rule 1: Fixed Risk-Per-Trade Budget (2.0%)</h3>
<p>
Capital preservation is paramount. Regardless of conviction, the maximum capital risked on any individual setup is strictly capped at <strong>2.0% of total portfolio equity</strong>:
</p>
<div class="code-box">
Risk_Budget = Account_Equity &times; 0.02<br>
Example (₹15,000 Starting Balance): Risk_Budget = ₹15,000 &times; 0.02 = ₹300 Max Loss
</div>

<h3>Rule 2: Volatility-Adjusted Position Sizing</h3>
<p>
Position sizing is dynamically determined by the distance between the entry price and the stop loss. When stop loss is wider, position size shrinks; when stop loss is tighter, position size expands—keeping total risk invariant:
</p>
<div class="code-box">
Quantity = Risk_Budget / | Entry_Price - Stop_Loss |<br>
Example: Entry = ₹1,170.00, SL = ₹1,155.00 (Risk Distance = ₹15.00)<br>
Quantity = ₹300 / ₹15.00 = 20 Shares (Risk = 20 &times; ₹15 = ₹300 exactly)
</div>

<h3>Rule 3: Broker Leverage Ceiling (3.0x Max)</h3>
<p>
To prevent over-leveraging on tight stop losses, total notional exposure is capped at <strong>3.0x account equity</strong> (or margin cap of 50% capital at 3x leverage):
</p>
<div class="code-box">
Max_Notional = (Account_Equity &times; 0.50) &times; 3.0<br>
Final_Quantity = min(Quantity_from_Risk, Quantity_from_Leverage)
</div>

<h3>Rule 4: Minimum Reward-to-Risk Requirement (R:R &ge; 1.5)</h3>
<p>
Any trade candidate where the projected target does not offer at least 1.5 times the stop-loss risk distance is automatically rejected. Over 100 trades, an R:R &ge; 1.5 allows profitability with a win-rate as low as 40%.
</p>

<h3>Rule 5: Maximum Simultaneous Open Positions (Cap: 3)</h3>
<p>
The engine permits a maximum of <strong>3 concurrent open trades</strong> across all markets. If 3 positions are active, no new signals will be executed until an existing position reaches its Target or Stop Loss. This caps portfolio-wide market risk at 6.0% (3 &times; 2%).
</p>

<h3>Rule 6: Daily Loss Circuit Breaker (5.0% Drawdown Halt)</h3>
<p>
If cumulative realized losses within a single calendar day reach or exceed <strong>5.0% of portfolio equity</strong> (₹750 on a ₹15,000 account), the circuit breaker trips. The system halts all new trade entries for the remainder of the session, protecting capital from trending black-swan days.
</p>

<h3>Rule 7: Friction &amp; Cost Modeling (Slippage + Exchange Fees)</h3>
<p>
To prevent unrealistic backtest curves, every simulated trade deducts realistic fees and execution drag:
</p>
<ul>
    <li><strong>Exchange Fees:</strong> 0.05% of notional turnover on entry and exit.</li>
    <li><strong>Simulated Slippage:</strong> 0.03% adverse price execution on market orders.</li>
</ul>

<div class="page-break"></div>

<h1>7. System Operations, Daily Workflow &amp; Best Practices</h1>

<h2>Daily Operational Routine (Indian Market Trading)</h2>
<ol>
    <li><strong>Morning Initialization (08:45 – 09:00 IST):</strong>
        <ul>
            <li>Start the application: <code>python -m algo_monitor.main run</code></li>
            <li>Verify the dashboard is accessible at <code>http://127.0.0.1:8502</code>.</li>
            <li>Check the Upstox authentication badge in the top header. If expired, click <strong>"Refresh Token"</strong> (or let the background TOTP engine authenticate automatically).</li>
        </ul>
    </li>
    <li><strong>Market Hours Ingestion (09:15 – 15:30 IST):</strong>
        <ul>
            <li>The scheduler ingests fresh 5-minute candles every 15 minutes.</li>
            <li>The strategy engine scans all indices (Nifty 50, Bank Nifty, Nifty Auto, Midcap Select) and their constituent stocks.</li>
            <li>When setups trigger, alerts are posted to Telegram, and trades are logged in the <strong>Positions</strong> tab.</li>
        </ul>
    </li>
    <li><strong>Post-Market Review (15:35 IST):</strong>
        <ul>
            <li>Review the <strong>Performance</strong> tab: evaluate daily P&amp;L, win rate, and closed trades log.</li>
            <li>Verify database consistency via SQLite query checks.</li>
        </ul>
    </li>
</ol>

<h2>Quick Command Cheat-Sheet</h2>
<table>
    <tr>
        <th>Action</th>
        <th>CLI Command / Endpoint</th>
        <th>Description</th>
    </tr>
    <tr>
        <td><strong>Start Platform</strong></td>
        <td><code>python -m algo_monitor.main run</code></td>
        <td>Launches scheduler, scanner, paper engine, and web dashboard.</td>
    </tr>
    <tr>
        <td><strong>Dashboard URL</strong></td>
        <td><code>http://127.0.0.1:8502</code></td>
        <td>Accesses the full financial monitoring terminal.</td>
    </tr>
    <tr>
        <td><strong>Manual Scan</strong></td>
        <td><code>python -m algo_monitor.main scan</code></td>
        <td>Performs an immediate manual scan across all instruments.</td>
    </tr>
    <tr>
        <td><strong>Generate Token</strong></td>
        <td><code>POST /api/auth/upstox/refresh</code></td>
        <td>Triggers automated 2FA login to renew the Upstox access token.</td>
    </tr>
    <tr>
        <td><strong>Market Toggle</strong></td>
        <td><code>POST /api/market-toggle</code></td>
        <td>Enables or disables Indian or Crypto market feeds on the fly.</td>
    </tr>
</table>

<div class="callout" style="margin-top:15px;">
    <strong>Summary:</strong> Algo Monitor v2.0 represents a complete, institutional-grade framework combining real-time data feeds, automated authentication, robust zone detection, risk-budgeted execution, options Greeks analysis, and alerting into a cohesive platform.
</div>
"""

doc = fitz.open()
story = fitz.Story(html_content)
writer = fitz.DocumentWriter(str(OUTPUT_PATH))
rect = fitz.paper_rect("a4")

more = 1
page_num = 0
while more:
    page_num += 1
    device = writer.begin_page(rect)
    more, _ = story.place(rect)
    story.draw(device)
    writer.end_page()

writer.close()
print(f"Generated {page_num}-page PDF at: {OUTPUT_PATH}")
