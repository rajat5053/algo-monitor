"""
Upstox Automated 2FA/TOTP Authentication Service.

Handles daily automatic login without human intervention:
- Uses pyotp and upstox-totp to generate 6-digit TOTP codes mathematically
- Automatically logs in using Upstox credentials (mobile, PIN, TOTP secret)
- Captures authorization code and exchanges it for a fresh access_token
- Persists access_token in SQLite database and updates active clients in memory
- Scheduled to run daily before market open (08:45 AM IST)
- Auto-recovers on 401 Unauthorized response
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from algo_monitor.config.settings import Settings, get_settings
from algo_monitor.utils.logging import get_logger

if TYPE_CHECKING:
    from algo_monitor.database import Database

logger = get_logger("upstox.auth")


class UpstoxAuthManager:
    """
    Automated Upstox token lifecycle manager.
    """

    def __init__(self, db: Database | None = None, settings: Settings | None = None):
        if db is None:
            try:
                from algo_monitor.database import Database
                self.db = Database()
            except Exception:
                self.db = None
        else:
            self.db = db
        self.settings = settings or get_settings()

    def is_configured_for_auto_login(self) -> bool:
        """Return True if all required credentials for 2FA auto-login are present."""
        cfg = self.settings.upstox
        return bool(
            cfg.api_key
            and cfg.api_secret
            and cfg.username
            and cfg.user_pin
            and cfg.totp_key
        )

    def fetch_new_token(self) -> str | None:
        """
        Execute automated TOTP login and return newly minted access token.
        """
        if not self.is_configured_for_auto_login():
            logger.warning(
                "Upstox auto-login missing required credentials in .env. "
                "Requires: UPSTOX_API_KEY, UPSTOX_API_SECRET, UPSTOX_USERNAME, UPSTOX_USER_PIN, UPSTOX_TOTP_KEY"
            )
            return None

        cfg = self.settings.upstox

        # Ensure environment variables are set for upstox-totp
        os.environ["UPSTOX_API_KEY"] = cfg.api_key
        os.environ["UPSTOX_CLIENT_ID"] = cfg.api_key
        os.environ["UPSTOX_API_SECRET"] = cfg.api_secret
        os.environ["UPSTOX_CLIENT_SECRET"] = cfg.api_secret
        os.environ["UPSTOX_USERNAME"] = cfg.username
        os.environ["UPSTOX_USER_PIN"] = cfg.user_pin
        os.environ["UPSTOX_PIN_CODE"] = cfg.user_pin
        os.environ["UPSTOX_PASSWORD"] = cfg.user_pin
        os.environ["UPSTOX_TOTP_KEY"] = cfg.totp_key
        os.environ["UPSTOX_TOTP_SECRET"] = cfg.totp_key
        os.environ["UPSTOX_REDIRECT_URI"] = cfg.redirect_uri or "http://127.0.0.1:8501/api/upstox/callback"

        logger.info("Initiating automated Upstox 2FA/TOTP login for %s...", cfg.username)

        try:
            from upstox_totp import UpstoxTOTP

            upx = UpstoxTOTP(
                username=cfg.username,
                password=cfg.user_pin,
                pin_code=cfg.user_pin,
                totp_secret=cfg.totp_key,
                client_id=cfg.api_key,
                client_secret=cfg.api_secret,
                redirect_uri=cfg.redirect_uri or "http://127.0.0.1:8501/api/upstox/callback",
            )
            response = upx.app_token.get_access_token()

            if response and getattr(response, "success", False) and getattr(response, "data", None):
                token = response.data.access_token
                logger.info("Successfully fetched fresh Upstox access token automatically!")
                if self.db:
                    self.db.set_state("upstox_last_error", "")
                self._persist_token(token)
                return token
            else:
                msg = getattr(response, "message", "Unknown error")
                logger.error("Upstox auto-login failed: %s", msg)
                if self.db:
                    self.db.set_state("upstox_last_error", str(msg))
                return None

        except Exception as exc:
            err_msg = str(exc)
            logger.error("Exception during Upstox automated login: %s", exc, exc_info=True)
            if self.db:
                self.db.set_state("upstox_last_error", err_msg)
            return None

    def get_valid_token(self) -> str | None:
        """
        Get valid access token:
        1. From database cache if present and still valid
        2. From .env if valid
        3. Automatically fetch fresh token via TOTP if auto-login configured
        """
        # Check DB first
        if self.db:
            db_token = self.db.get_state("upstox_access_token")
            if db_token and self.verify_token(db_token):
                return db_token

        # Check .env / settings
        env_token = self.settings.upstox.access_token
        if env_token and self.verify_token(env_token):
            if self.db:
                self.db.set_state("upstox_access_token", env_token)
            return env_token

        # Token is invalid or expired — auto-login if credentials available
        if self.is_configured_for_auto_login():
            return self.fetch_new_token()

        return None

    def verify_token(self, token: str) -> bool:
        """
        Lightweight check to test if token is active and accepted by Upstox.
        """
        if not token:
            return False

        try:
            import requests
            url = "https://api.upstox.com/v3/market-quote/ltp?instrument_key=NSE_INDEX|Nifty%2050"
            resp = requests.get(
                url,
                headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
                timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def _persist_token(self, token: str) -> None:
        """Save token in database, .env file, and update runtime environment."""
        if self.db:
            self.db.set_state("upstox_access_token", token)
            self.db.set_state("upstox_token_updated_at", datetime.now(timezone.utc).isoformat())

        # Update in-memory settings
        object.__setattr__(self.settings.upstox, "access_token", token)
        os.environ["UPSTOX_ACCESS_TOKEN"] = token

        # Update .env file
        try:
            from pathlib import Path
            import re
            env_path = Path(__file__).resolve().parent.parent.parent / ".env"
            if env_path.exists():
                content = env_path.read_text(encoding="utf-8")
                new_content = re.sub(
                    r"^UPSTOX_ACCESS_TOKEN=.*$",
                    f"UPSTOX_ACCESS_TOKEN={token}",
                    content,
                    flags=re.MULTILINE,
                )
                env_path.write_text(new_content, encoding="utf-8")
                logger.info("Persisted new Upstox access token directly into .env")
        except Exception as e:
            logger.warning("Could not write token back to .env: %s", e)
