"""
Notification abstraction with Telegram support.

Features:
- Abstract notifier interface
- Console notifier (always available)
- Telegram notifier (requires bot token + chat ID)
- Deduplication via message hashing
- Rate limiting to prevent alert spam
- Graceful handling of unavailable providers
"""

from __future__ import annotations

import hashlib
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from algo_monitor.strategy.signals import Signal
from algo_monitor.utils.logging import get_logger

if TYPE_CHECKING:
    from algo_monitor.database import Database

logger = get_logger("alerts")


class Notifier(ABC):
    """Abstract base for notification channels."""

    @abstractmethod
    def send(self, message: str) -> bool:
        """Send a message. Returns True on success."""
        ...

    @property
    @abstractmethod
    def channel_name(self) -> str:
        ...


class ConsoleNotifier(Notifier):
    """Logs alerts to the console (always available)."""

    def send(self, message: str) -> bool:
        logger.info("📢 ALERT: %s", message)
        return True

    @property
    def channel_name(self) -> str:
        return "console"


class TelegramNotifier(Notifier):
    """Sends alerts via Telegram Bot API."""

    def __init__(self, bot_token: str, chat_id: str):
        self._bot_token = bot_token
        self._chat_id = chat_id

    def send(self, message: str) -> bool:
        try:
            import httpx

            url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
            resp = httpx.post(
                url,
                json={
                    "chat_id": self._chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=15,
            )
            resp.raise_for_status()
            result = resp.json()
            if result.get("ok"):
                logger.debug("Telegram message sent successfully")
                return True
            else:
                logger.warning("Telegram API error: %s", result)
                return False
        except Exception as exc:
            logger.error("Telegram send failed: %s", exc)
            return False

    @property
    def channel_name(self) -> str:
        return "telegram"


class AlertManager:
    """
    Manages alert routing, deduplication, and rate limiting.
    """

    # Minimum seconds between alerts for the same signal
    RATE_LIMIT_SECONDS = 300  # 5 minutes

    def __init__(self, db: Database | None = None):
        self._notifiers: list[Notifier] = []
        self._db = db
        self._last_alert_time: dict[str, float] = {}

    def add_notifier(self, notifier: Notifier) -> None:
        self._notifiers.append(notifier)
        logger.info("Added notifier: %s", notifier.channel_name)

    def send_signal_alert(self, signal: Signal) -> bool:
        """
        Format and send a trading signal alert through all channels.
        Handles deduplication, freshness check, market toggle filter, and rate limiting.
        """
        # 1. Freshness check: reject expired or stale signals (>30 minutes old)
        if signal.is_expired():
            logger.info("Suppressed expired signal for %s", signal.symbol)
            return False

        if signal.created_at:
            age_sec = (datetime.now(timezone.utc) - signal.created_at).total_seconds()
            if age_sec > 1800:  # > 30 mins
                logger.info("Suppressed stale signal for %s (age: %.1f min)", signal.symbol, age_sec / 60)
                return False

        # 2. Market toggle filter: check if market is turned off
        if self._db:
            is_crypto = signal.exchange in ("delta", "binance") or any(
                c in signal.symbol.upper() for c in ("BTC", "ETH", "SOL", "USDT", "USD")
            )
            if is_crypto:
                crypto_enabled = self._db.get_state("market_toggle_crypto", "true") == "true"
                if not crypto_enabled:
                    logger.debug("Crypto alert suppressed (Crypto market toggled OFF)")
                    return False
            else:
                indian_enabled = self._db.get_state("market_toggle_indian", "true") == "true"
                if not indian_enabled:
                    logger.debug("Indian alert suppressed (Indian market toggled OFF)")
                    return False

        msg = self._format_signal_message(signal)
        msg_hash = hashlib.md5(msg.encode()).hexdigest()[:16]

        # Rate limit check
        now = time.time()
        if msg_hash in self._last_alert_time:
            elapsed = now - self._last_alert_time[msg_hash]
            if elapsed < self.RATE_LIMIT_SECONDS:
                logger.debug("Rate limited alert for %s", signal.symbol)
                return False

        # Deduplication check (database)
        if self._db:
            existing = self._db.fetchone(
                "SELECT id FROM alert_log WHERE message_hash = ?",
                (msg_hash,),
            )
            if existing:
                logger.debug("Duplicate alert suppressed for %s", signal.symbol)
                return False

        # Send through all channels
        sent = False
        for notifier in self._notifiers:
            try:
                success = notifier.send(msg)
                if success:
                    sent = True
                    if self._db:
                        self._db.execute(
                            """INSERT OR IGNORE INTO alert_log
                               (signal_id, channel, message_hash, sent_at, success)
                               VALUES (?, ?, ?, ?, ?)""",
                            (
                                None,
                                notifier.channel_name,
                                msg_hash,
                                datetime.now(timezone.utc).isoformat(),
                                1,
                            ),
                        )
                        self._db._get_connection().commit()
            except Exception as exc:
                logger.error(
                    "Notifier %s failed: %s", notifier.channel_name, exc
                )

        if sent:
            self._last_alert_time[msg_hash] = now

        return sent

    def send_text(self, message: str) -> bool:
        """Send a plain text alert (for system messages, etc.)."""
        sent = False
        for notifier in self._notifiers:
            try:
                if notifier.send(message):
                    sent = True
            except Exception as exc:
                logger.error("Notifier %s failed: %s", notifier.channel_name, exc)
        return sent

    def _is_duplicate(self, msg_hash: str, now: float) -> bool:
        """Check if message hash was recently sent or already logged in database."""
        if msg_hash in self._last_alert_time:
            elapsed = now - self._last_alert_time[msg_hash]
            if elapsed < self.RATE_LIMIT_SECONDS:
                return True

        if self._db:
            try:
                existing = self._db.fetchone(
                    "SELECT id FROM alert_log WHERE message_hash = ?",
                    (msg_hash,),
                )
                if existing:
                    return True
            except Exception:
                pass
        return False

    def send_trade_management_alert(self, evaluation: Any) -> bool:
        """
        Send a trade management advisory alert for an open position (P2-B, P2-C).
        Formatted distinctly from initial entry signals with duplicate suppression.
        """
        message = self._format_trade_management_message(evaluation)
        msg_hash = getattr(evaluation, "alert_hash", "") or hashlib.sha256(message.encode()).hexdigest()[:16]

        now = time.time()
        if self._is_duplicate(msg_hash, now):
            logger.debug(
                "Suppressing duplicate trade management alert for trade %s",
                getattr(evaluation, "trade_id", 0),
            )
            return False

        sent = False
        for notifier in self._notifiers:
            try:
                if notifier.send(message):
                    sent = True
                    if self._db:
                        with self._db.transaction() as conn:
                            conn.execute(
                                """INSERT OR IGNORE INTO alert_log
                                       (signal_id, channel, message_hash, sent_at, success)
                                   VALUES (?, ?, ?, ?, ?)""",
                                (
                                    None,
                                    notifier.channel_name,
                                    msg_hash,
                                    datetime.now(timezone.utc).isoformat(),
                                    1,
                                ),
                            )
            except Exception as exc:
                logger.error("Notifier %s failed for trade management: %s", notifier.channel_name, exc)

        if sent:
            self._last_alert_time[msg_hash] = now
        return sent

    def _format_trade_management_message(self, evaluation: Any) -> str:
        """Format an open trade management advisory into a readable message."""
        state_val = getattr(evaluation.state, "value", str(evaluation.state))
        entry_time_str = getattr(evaluation, "entry_time", "")
        parts = [
            f"🛡️ <b>TRADE MANAGEMENT UPDATE</b>",
            f"Action: <b>{state_val.replace('_', ' ')}</b>",
            f"",
            f"📊 <b>{evaluation.symbol}</b> (Trade #{evaluation.trade_id})",
            f"📈 Direction: {evaluation.direction.upper()}",
            f"💰 Entry: {evaluation.entry_price:.2f} | Current: {evaluation.current_price:.2f}",
            f"🛑 Stop Loss: {evaluation.stop_loss:.2f}",
            f"🎯 Current Target: {evaluation.current_target:.2f}",
        ]
        if entry_time_str:
            parts.append(f"⏱️ Executed: {entry_time_str[:19].replace('T', ' ')} UTC")

        if getattr(evaluation, "proposed_target", None):
            parts.append(f"✨ <b>Proposed Extended Target: {evaluation.proposed_target:.2f}</b>")

        parts.append(f"📈 Progress: {evaluation.progress_pct:.1f}% ({evaluation.r_achieved:.2f}R)")

        if getattr(evaluation, "opposing_zone_info", ""):
            parts.append(f"🧱 {evaluation.opposing_zone_info}")

        if getattr(evaluation, "evidence_for", None):
            parts.append("")
            parts.append("<b>Evidence For:</b>")
            for item in evaluation.evidence_for:
                parts.append(f" • {item}")

        if getattr(evaluation, "evidence_against", None):
            parts.append("")
            parts.append("<b>Evidence Against / Risks:</b>")
            for item in evaluation.evidence_against:
                parts.append(f" • {item}")

        parts.append("")
        eval_time = getattr(evaluation, "evaluated_at", datetime.now(timezone.utc))
        parts.append(f"🕐 {eval_time.strftime('%Y-%m-%d %H:%M UTC')}")
        parts.append("📋 Status: PAPER TRADING ADVISORY")

        return "\n".join(parts)

    def _format_signal_message(self, signal: Signal) -> str:
        """Format a signal into a readable alert message."""
        parts = [
            f"🔔 <b>{signal.setup_type.value.replace('_', ' ').title()}</b>",
            f"",
            f"📊 <b>{signal.symbol}</b> ({signal.exchange})",
            f"📈 Direction: {signal.direction.value.upper()}",
            f"⏰ Timeframe: {signal.timeframe}",
        ]

        if signal.zone:
            parts.append(
                f"📍 Zone: {signal.zone.zone_type.value} "
                f"[{signal.zone.price_low:.2f} – {signal.zone.price_high:.2f}]"
            )
            parts.append(f"💪 Zone strength: {signal.zone.strength:.2f}")

        if signal.entry_ref:
            parts.append(f"🎯 Entry ref: {signal.entry_ref:.2f}")
        if signal.stop_loss:
            parts.append(f"🛑 Stop loss: {signal.stop_loss:.2f}")
        if signal.target:
            parts.append(f"✅ Target: {signal.target:.2f}")
        if signal.risk_reward:
            parts.append(f"⚖️ R:R = {signal.risk_reward:.2f}")

        parts.append(f"")
        if signal.reason:
            parts.append(f"📝 {signal.reason[:300]}")

        if signal.invalidation:
            parts.append(f"")
            parts.append(f"❌ Invalidation: {signal.invalidation[:200]}")

        parts.append(f"")
        parts.append(
            f"🕐 {signal.created_at.strftime('%Y-%m-%d %H:%M UTC')}"
        )
        parts.append(f"📋 Status: PAPER TRADING ONLY")

        return "\n".join(parts)
