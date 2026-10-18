"""
Upstox API client for Indian market data.

Reuses the working Nifty 50 quote integration with proper error handling,
token management, and historical candle support.

API docs: https://upstox.com/developer/api-documentation
"""

from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta
from typing import Any

import requests

from algo_monitor.data.models import Candle, TickerUpdate
from algo_monitor.utils.logging import get_logger

logger = get_logger("data.upstox")


class UpstoxClient:
    """REST client for Upstox v2/v3 API."""

    BASE_URL = "https://api.upstox.com"

    def __init__(self, access_token: str, api_key: str = ""):
        self._access_token = access_token
        self._api_key = api_key
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        })

    def update_access_token(self, new_token: str) -> None:
        """Update runtime access token and headers."""
        self._access_token = new_token
        self._session.headers["Authorization"] = f"Bearer {new_token}"

    def _auto_refresh_if_unauthorized(self) -> bool:
        """Try to refresh token via UpstoxAuthManager if 401 occurred."""
        try:
            from algo_monitor.data.upstox_auth import UpstoxAuthManager
            auth = UpstoxAuthManager()
            new_tok = auth.fetch_new_token()
            if new_tok:
                self.update_access_token(new_tok)
                logger.info("UpstoxClient token auto-refreshed successfully")
                return True
        except Exception as e:
            logger.warning("UpstoxClient auto-refresh error: %s", e)
        return False

    def _check_token_valid(self) -> bool:
        """Quick check if the access token is still usable."""
        try:
            resp = self._session.get(
                f"{self.BASE_URL}/v2/user/profile",
                timeout=10,
            )
            if resp.status_code == 401:
                return self._auto_refresh_if_unauthorized()
            return resp.status_code == 200
        except requests.RequestException:
            return False

    # ----- Market Quotes -----

    def get_ltp(self, instrument_key: str) -> dict | None:
        """
        Get Last Traded Price for an instrument.
        instrument_key format: "NSE_INDEX|Nifty 50"
        """
        try:
            resp = self._session.get(
                f"{self.BASE_URL}/v3/market-quote/ltp",
                params={"instrument_key": instrument_key},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") == "success":
                return data.get("data", {})
            else:
                logger.warning("LTP request unsuccessful: %s", data)
                return None

        except requests.RequestException as exc:
            logger.error("LTP request failed for %s: %s", instrument_key, exc)
            return None

    def get_full_quote(self, instrument_key: str) -> dict | None:
        """Get full market quote including OHLC, volume, etc."""
        try:
            resp = self._session.get(
                f"{self.BASE_URL}/v3/market-quote/quotes",
                params={"instrument_key": instrument_key},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") == "success":
                return data.get("data", {})
            else:
                logger.warning("Quote request unsuccessful: %s", data)
                return None

        except requests.RequestException as exc:
            logger.error("Quote request failed for %s: %s", instrument_key, exc)
            return None

    # ----- Historical Candles -----

    def get_candles(
        self,
        instrument_key: str,
        interval: str = "5minute",
        from_date: str = "",
        to_date: str = "",
        symbol: str = "",
        storage_interval: str = "",
    ) -> list[Candle]:
        """
        Fetch historical candles from Upstox.

        interval: '1minute', '5minute', '15minute', '30minute', '1hour',
                  '4hour' (if available), 'day', 'week', 'month'
        from_date, to_date: 'YYYY-MM-DD' format
        """
        if not to_date:
            to_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if not from_date:
            from_date = (
                datetime.now(timezone.utc) - timedelta(days=30)
            ).strftime("%Y-%m-%d")

        try:
            resp = self._session.get(
                f"{self.BASE_URL}/v2/historical-candle/{instrument_key}/{interval}/{to_date}/{from_date}",
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            logger.error(
                "Historical candles failed for %s: %s", instrument_key, exc
            )
            return []

        if data.get("status") != "success":
            logger.warning("Candle API unsuccessful: %s", data)
            return []

        raw_candles = data.get("data", {}).get("candles", [])
        candles = []

        cand_symbol = symbol or instrument_key.split("|")[-1].replace(" ", "").upper()
        norm_interval = storage_interval or _normalise_interval(interval)

        # Upstox candle format: [timestamp, open, high, low, close, volume, oi]
        for c in raw_candles:
            try:
                ts = datetime.fromisoformat(c[0].replace("Z", "+00:00"))
                candle = Candle(
                    symbol=cand_symbol,
                    exchange="upstox",
                    interval=norm_interval,
                    timestamp=ts,
                    open=float(c[1]),
                    high=float(c[2]),
                    low=float(c[3]),
                    close=float(c[4]),
                    volume=float(c[5]) if len(c) > 5 else 0,
                    is_complete=True,
                )
                errors = candle.validate()
                if errors:
                    logger.warning("Invalid candle %s@%s: %s", symbol, ts, errors)
                    continue
                candles.append(candle)
            except (IndexError, ValueError, TypeError) as exc:
                logger.warning("Skipping malformed Upstox candle: %s", exc)

        # Upstox returns newest first; reverse to chronological
        candles.sort(key=lambda c: c.timestamp)
        logger.debug(
            "Fetched %d candles for %s (%s)", len(candles), instrument_key, interval
        )
        return candles

    def get_ticker(self, instrument_key: str) -> TickerUpdate | None:
        """Create a TickerUpdate from an LTP call."""
        ltp_data = self.get_ltp(instrument_key)
        if not ltp_data:
            return None

        # LTP response has data keyed by instrument_key
        for key, info in ltp_data.items():
            symbol = instrument_key.split("|")[-1].replace(" ", "").upper()
            return TickerUpdate(
                symbol=symbol,
                exchange="upstox",
                last_price=float(info.get("last_price", 0)),
                timestamp=datetime.now(timezone.utc),
            )
        return None


def _normalise_interval(upstox_interval: str) -> str:
    """Convert Upstox interval names to our standard format."""
    mapping = {
        "1minute": "1m",
        "5minute": "5m",
        "15minute": "15m",
        "30minute": "30m",
        "1hour": "1h",
        "4hour": "4h",
        "day": "1d",
        "week": "1w",
        "month": "1M",
    }
    return mapping.get(upstox_interval, upstox_interval)
