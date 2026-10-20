"""
Centralised application settings.

All values come from environment variables (via .env) with sensible defaults.
Secrets are never logged or printed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (idempotent)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _env_float(key: str, default: float = 0.0) -> float:
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def _env_int(key: str, default: int = 0) -> int:
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("true", "1", "yes", "on")



# ---------------------------------------------------------------------------
# Upstox
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class UpstoxConfig:
    api_key: str = field(default_factory=lambda: _env("UPSTOX_API_KEY") or _env("UPSTOX_CLIENT_ID"))
    api_secret: str = field(
        default_factory=lambda: _env("UPSTOX_API_SECRET") or _env("UPSTOX_CLIENT_SECRET"), repr=False
    )
    access_token: str = field(default_factory=lambda: _env("UPSTOX_ACCESS_TOKEN"), repr=False)
    username: str = field(default_factory=lambda: _env("UPSTOX_USERNAME"))
    user_pin: str = field(
        default_factory=lambda: _env("UPSTOX_USER_PIN") or _env("UPSTOX_PIN_CODE") or _env("UPSTOX_PASSWORD"),
        repr=False,
    )
    totp_key: str = field(
        default_factory=lambda: _env("UPSTOX_TOTP_KEY") or _env("UPSTOX_TOTP_SECRET"), repr=False
    )
    redirect_uri: str = field(
        default_factory=lambda: _env("UPSTOX_REDIRECT_URI", "http://127.0.0.1:8501/api/upstox/callback")
    )
    base_url: str = "https://api.upstox.com"

    @property
    def is_configured(self) -> bool:
        return bool(self.access_token) or self.can_auto_login

    @property
    def can_auto_login(self) -> bool:
        return bool(
            self.api_key
            and self.api_secret
            and self.username
            and self.user_pin
            and self.totp_key
        )


# ---------------------------------------------------------------------------
# Delta Exchange India
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DeltaConfig:
    api_key: str = field(default_factory=lambda: _env("DELTA_API_KEY"), repr=False)
    api_secret: str = field(default_factory=lambda: _env("DELTA_API_SECRET"), repr=False)
    base_url: str = "https://api.india.delta.exchange"
    ws_url: str = "wss://public-socket.india.delta.exchange"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN"), repr=False)
    chat_id: str = field(default_factory=lambda: _env("TELEGRAM_CHAT_ID"))

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)


# ---------------------------------------------------------------------------
# LLM (optional)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LLMConfig:
    provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "none"))
    api_key: str = field(default_factory=lambda: _env("LLM_API_KEY"), repr=False)

    @property
    def is_configured(self) -> bool:
        return self.provider != "none" and bool(self.api_key)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Strategy defaults & Modular Extensions
# ---------------------------------------------------------------------------
@dataclass
class HeadAndShouldersConfig:
    """Configuration for Head and Shoulders pattern detection."""
    enabled: bool = False
    min_head_prominence_pct: float = 0.5   # Head must exceed shoulders by >= 0.5%
    shoulder_symmetry_pct: float = 25.0     # Shoulder heights match within 25% of height
    min_pattern_candles: int = 12           # Minimum candles spanning the 3 swings
    max_pattern_candles: int = 100          # Maximum candles spanning pattern
    neckline_tolerance_pct: float = 0.6     # Neckline alignment tolerance
    require_neckline_sr_confluence: bool = True  # Neckline must align with an S/R zone
    min_reward_risk: float = 1.5


@dataclass
class FirstyContinuationConfig:
    """Configuration for Firsty-style EMA trend-continuation setups."""
    enabled: bool = False
    fast_ema_period: int = 20
    slow_ema_period: int = 50
    trend_slope_lookback: int = 5           # Bars to check positive/negative slope
    min_separation_atr_mult: float = 0.25   # Fast vs slow EMA separation in ATR
    pullback_tolerance_atr_mult: float = 0.50 # Pullback closeness to EMA in ATR
    require_sr_confluence: bool = True      # Pullback must test an S/R zone
    sr_confluence_tolerance_pct: float = 0.8
    min_rejection_wick_ratio: float = 0.25  # Trigger candle rejection wick >= 25% of range
    min_reward_risk: float = 1.5


@dataclass
class ExitConfig:
    """Configuration for advanced exit rules (trailing stops, partial profits, breakeven protection)."""
    trailing_stop_mode: str = field(
        default_factory=lambda: _env("TRAILING_STOP_MODE", "atr")
    )        # "none", "atr", "swing", "partial_plus_atr", "partial_plus_swing"
    trailing_atr_mult: float = field(
        default_factory=lambda: _env_float("TRAILING_ATR_MULT", 2.0)
    )          # Multiplier for ATR trailing stop
    swing_lookback: int = field(
        default_factory=lambda: _env_int("SWING_LOOKBACK", 3)
    )                 # Lookback for swing trailing stop
    partial_profit_pct: float = field(
        default_factory=lambda: _env_float("PARTIAL_PROFIT_PCT", 0.50)
    )        # Take 50% profit at partial target
    partial_profit_r_mult: float = field(
        default_factory=lambda: _env_float("PARTIAL_PROFIT_R_MULT", 1.0)
    )      # Partial target at 1.0R (or 1st opposing zone)
    move_to_breakeven_on_partial: bool = True

    # Automatic Breakeven / Profit Protection
    enable_breakeven_protection: bool = field(
        default_factory=lambda: _env_bool("ENABLE_BREAKEVEN_PROTECTION", True)
    )
    breakeven_trigger_r: float = field(
        default_factory=lambda: _env_float("BREAKEVEN_TRIGGER_R", 0.75)
    )
    breakeven_buffer_pct: float = field(
        default_factory=lambda: _env_float("BREAKEVEN_BUFFER_PCT", 0.0)
    )



@dataclass
class StrategyConfig:
    """Configurable parameters for support-and-resistance detection and modular strategies."""

    # Number of candles on each side to confirm a swing high/low
    swing_lookback: int = 3

    # Prominence filter: minimum percentage or ATR depth required for a swing to be meaningful
    min_prominence_pct: float = 0.25

    # Percentage tolerance for clustering nearby levels into zones
    zone_tolerance_pct: float = 0.5

    # Minimum zone width (% of mid price) to guarantee zones are price bands, not single lines
    min_zone_width_pct: float = 0.2

    # Minimum touches for a zone to be considered significant
    min_touches: int = 2

    # Maximum number of zones to track per instrument
    max_zones: int = 20

    # Signal expiry in completed candles (after which a setup is stale)
    signal_expiry_candles: int = 12

    # Minimum distance from current price to zone (% of price) to trigger
    # "approaching zone" early warning
    approach_distance_pct: float = 1.0

    # Breakout confirmation: minimum close beyond zone (% of zone price)
    breakout_threshold_pct: float = 0.3

    # Retest: how close price must return to the broken level (% tolerance)
    retest_tolerance_pct: float = 0.5

    # Minimum reward-to-risk ratio for VALIDATION (rejection floor).
    min_reward_risk: float = 1.5

    # Target mode:
    #   "adaptive" — set initial target at nearest opposing zone (recommended)
    #   "fixed_rr" — set target at entry ± risk * target_fixed_rr_multiple
    target_mode: str = "adaptive"

    # The R multiple used when target_mode="fixed_rr" (or as fallback in
    # adaptive mode when no opposing zone is found within usable distance).
    target_fixed_rr_multiple: float = 1.5

    # Buffer (% of price) to leave before the opposing zone when placing an
    # adaptive target. Prevents the target from sitting exactly at the zone.
    zone_clearance_buffer_pct: float = 0.2

    # Zone invalidation: % beyond zone boundary required to mark a zone broken
    zone_invalidation_threshold_pct: float = 0.5

    # Number of consecutive closes beyond the threshold to mark zone broken
    zone_invalidation_closes: int = 2

    # Polarity changes: whether to flip broken resistance to support and vice versa
    enable_polarity_flips: bool = True

    # Zone merging: merge overlapping zones to prevent clutter
    enable_zone_merging: bool = True

    # Freshness threshold: touches > max_fresh_touches receive a score penalty
    max_fresh_touches: int = 5

    # -------------------------------------------------------------------------
    # Modular Strategy Extensions (Document 2)
    # -------------------------------------------------------------------------
    head_and_shoulders: HeadAndShouldersConfig = field(default_factory=HeadAndShouldersConfig)
    firsty_continuation: FirstyContinuationConfig = field(default_factory=FirstyContinuationConfig)
    exits: ExitConfig = field(default_factory=ExitConfig)

    # -------------------------------------------------------------------------
    # Per-market timeframe configuration
    # -------------------------------------------------------------------------

    # Indian market: daily candles for major S/R, 5-min for entries
    indian_htf_interval: str = "1d"    # Major zones from ~365 daily candles
    indian_ltf_interval: str = "5m"    # Entry confirmation timeframe
    indian_lookback_days: int = 365    # Calendar days of daily history

    # Crypto market: 1-hour context + 5-min entries within rolling window
    crypto_htf_interval: str = "1h"   # Context timeframe (within rolling window)
    crypto_ltf_interval: str = "5m"   # Entry confirmation timeframe
    crypto_rolling_window_hours: int = 72  # Rolling analysis window (48-72 hours)

    # Legacy generic intervals
    htf_interval: str = "1d"     # Defaults to daily (aligns with Indian default)
    ltf_interval: str = "5m"     # Entry timeframe

    # Minimum candles of history needed before generating signals
    min_history_candles: int = 100


# ---------------------------------------------------------------------------
# Risk management defaults
# ---------------------------------------------------------------------------
@dataclass
class RiskConfig:
    starting_balance: float = field(
        default_factory=lambda: _env_float("INDIAN_MARKET_CAPITAL", _env_float("PAPER_TRADING_BALANCE", 20_000))
    )
    indian_market_capital: float = field(
        default_factory=lambda: _env_float("INDIAN_MARKET_CAPITAL", _env_float("PAPER_TRADING_BALANCE", 20_000))
    )

    # Generic risk per trade (fraction of equity). Used when no market-specific
    # override applies. Spec baseline: 0.5%.
    risk_per_trade: float = field(
        default_factory=lambda: _env_float("RISK_PER_TRADE", 0.005)
    )

    # Per-market risk percentages (fraction of equity per trade)
    indian_cash_risk_per_trade: float = field(
        default_factory=lambda: _env_float("INDIAN_CASH_RISK_PER_TRADE", 0.005)
    )
    indian_futures_risk_per_trade: float = field(
        default_factory=lambda: _env_float("INDIAN_FUTURES_RISK_PER_TRADE", 0.005)
    )
    crypto_risk_per_trade: float = field(
        default_factory=lambda: _env_float("CRYPTO_RISK_PER_TRADE", 0.003)
    )
    gold_risk_per_trade: float = field(
        default_factory=lambda: _env_float("GOLD_RISK_PER_TRADE", 0.0025)
    )

    max_positions: int = field(
        default_factory=lambda: _env_int("MAX_POSITIONS", 3)
    )

    # Daily loss breaker: 2% of account equity
    max_daily_loss: float = field(
        default_factory=lambda: _env_float("MAX_DAILY_LOSS", 0.02)
    )

    # Weekly drawdown limit: 4% of peak equity
    max_weekly_loss: float = field(
        default_factory=lambda: _env_float("MAX_WEEKLY_LOSS", 0.04)
    )

    # Peak-to-trough drawdown limit: 8% of peak equity
    max_peak_drawdown: float = field(
        default_factory=lambda: _env_float("MAX_PEAK_DRAWDOWN", 0.08)
    )

    # Maximum aggregate planned open risk across all positions (1% of equity)
    max_aggregate_open_risk: float = field(
        default_factory=lambda: _env_float("MAX_AGGREGATE_OPEN_RISK", 0.01)
    )

    min_reward_risk: float = field(
        default_factory=lambda: _env_float("MIN_REWARD_RISK", 1.5)
    )

    # Leverage ceiling: 1x (spot/cash instruments; no margin amplification)
    max_leverage: float = field(
        default_factory=lambda: _env_float("MAX_LEVERAGE", 1.0)
    )

    # Maximum initial capital allocation per trade: 25% of equity
    max_capital_per_trade_pct: float = field(
        default_factory=lambda: _env_float("MAX_CAPITAL_PER_TRADE_PCT", 0.25)
    )

    usd_inr_rate: float = field(
        default_factory=lambda: _env_float("USD_INR_RATE", 85.0)
    )

    # Assumed trading costs (fraction of notional)
    fee_rate: float = 0.0005        # 5 bps
    slippage_rate: float = 0.0003   # 3 bps

    # Intraday position auto-close after N minutes (0 = disabled)
    intraday_expiry_minutes: int = 375  # Full Indian trading session

    # Swing position maximum holding period in calendar days (0 = unlimited)
    swing_max_days: int = 14

    def get_risk_per_trade(self, exchange: str = "", symbol: str = "") -> float:
        """
        Return the applicable risk fraction for a given instrument.

        Markets:
          - Crypto (Delta Exchange or USD-denominated): crypto_risk_per_trade (0.3%)
          - Indian (Upstox): indian_cash_risk_per_trade (0.5%)
          - Fallback: risk_per_trade (0.5%)
        """
        sym_upper = symbol.upper()
        is_crypto = (
            exchange == "delta"
            or any(c in sym_upper for c in ("BTC", "ETH", "SOL", "XRP",
                                             "BNB", "DOGE", "AVAX",
                                             "LINK", "NEAR", "DOT",
                                             "SUI", "PEPE", "USD"))
        )
        if is_crypto:
            return self.crypto_risk_per_trade
        return self.indian_cash_risk_per_trade


# ---------------------------------------------------------------------------
# Options trading defaults
# ---------------------------------------------------------------------------
@dataclass
class OptionsConfig:
    """Configurable options routing and execution parameters."""

    enabled: bool = field(
        default_factory=lambda: _env("ENABLE_OPTIONS", "true").lower() in ("true", "1", "yes")
    )
    auto_route_indices: bool = field(
        default_factory=lambda: _env("OPTIONS_AUTO_ROUTE_INDICES", "true").lower() in ("true", "1", "yes")
    )
    max_capital_per_option_trade_pct: float = field(
        default_factory=lambda: _env_float("OPTIONS_MAX_CAPITAL_PCT", 0.45)
    )
    max_sl_premium_pct: float = field(
        default_factory=lambda: _env_float("OPTIONS_MAX_SL_PCT", 0.40)
    )


# ---------------------------------------------------------------------------
# Market Toggle — enable/disable Indian or Crypto market sections
# ---------------------------------------------------------------------------
@dataclass
class MarketToggleConfig:
    """Controls which market sections are active for scanning and alerts."""

    indian_enabled: bool = True
    crypto_enabled: bool = True

    def to_dict(self) -> dict:
        return {
            "indian_enabled": self.indian_enabled,
            "crypto_enabled": self.crypto_enabled,
        }


# ---------------------------------------------------------------------------
# Application-wide settings (singleton-like)
# ---------------------------------------------------------------------------
@dataclass
class Settings:
    upstox: UpstoxConfig = field(default_factory=UpstoxConfig)
    delta: DeltaConfig = field(default_factory=DeltaConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    options: OptionsConfig = field(default_factory=OptionsConfig)
    exit: ExitConfig = field(default_factory=ExitConfig)
    market_toggle: MarketToggleConfig = field(default_factory=MarketToggleConfig)

    database_path: str = field(
        default_factory=lambda: _env("DATABASE_PATH", "./algo_monitor.db")
    )
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))
    dashboard_host: str = field(
        default_factory=lambda: _env("DASHBOARD_HOST", "127.0.0.1")
    )
    dashboard_port: int = field(
        default_factory=lambda: _env_int("DASHBOARD_PORT", 8501)
    )


def get_settings() -> Settings:
    """Return a fresh Settings instance populated from current env."""
    return Settings()
