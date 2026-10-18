"""
Delta Exchange India — REST & WebSocket client.

Reuses patterns from the existing delta_*.py scripts with proper
error handling, pagination, reconnection, and structured data output.

REST API: https://api.india.delta.exchange
WebSocket: wss://public-socket.india.delta.exchange
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

import requests
import websocket

from algo_monitor.data.models import Candle, ConnectionStatus, TickerUpdate
from algo_monitor.utils.logging import get_logger

logger = get_logger("data.delta")


class DeltaExchangeClient:
    """REST client for Delta Exchange India."""

    BASE_URL = "https://api.india.delta.exchange"

    def __init__(self, api_key: str = "", api_secret: str = ""):
        self._api_key = api_key
        self._api_secret = api_secret
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})
        if api_key:
            self._session.headers["api-key"] = api_key

    # ----- Products / Instruments -----

    def get_products(
        self,
        contract_type: str | None = None,
        state: str = "live",
        page_size: int = 100,
    ) -> list[dict]:
        """
        Fetch products with automatic pagination.
        contract_type: 'spot', 'perpetual_futures', 'call_options', 'put_options', etc.
        """
        all_products = []
        cursor = None

        while True:
            params: dict[str, Any] = {"states": state, "page_size": page_size}
            if contract_type:
                params["contract_types"] = contract_type
            if cursor:
                params["after"] = cursor

            try:
                resp = self._session.get(
                    f"{self.BASE_URL}/v2/products",
                    params=params,
                    timeout=30,
                )
                resp.raise_for_status()
                payload = resp.json()
            except requests.RequestException as exc:
                logger.error("Failed to fetch products (type=%s): %s", contract_type, exc)
                break

            if not payload.get("success"):
                logger.warning("API returned unsuccessful: %s", payload)
                break

            products = payload.get("result", [])
            all_products.extend(products)

            meta = payload.get("meta") or {}
            next_cursor = meta.get("after")

            if not next_cursor or not products:
                break
            cursor = next_cursor

        logger.info(
            "Fetched %d products (type=%s, state=%s)",
            len(all_products),
            contract_type or "all",
            state,
        )
        return all_products

    def discover_products(self) -> dict[str, list[dict]]:
        """
        Discover all live products grouped by contract type.
        Returns counts dynamically instead of hardcoding.
        """
        contract_types = [
            "spot",
            "perpetual_futures",
            "futures",
            "call_options",
            "put_options",
        ]
        result = {}
        for ct in contract_types:
            products = self.get_products(contract_type=ct)
            if products:
                result[ct] = products
                logger.info("%s: %d live products", ct, len(products))
        return result

    # ----- Ticker -----

    def get_ticker(self, symbol: str) -> dict | None:
        """Fetch current ticker for a symbol."""
        try:
            resp = self._session.get(
                f"{self.BASE_URL}/v2/tickers/{symbol}",
                timeout=15,
            )
            resp.raise_for_status()
            payload = resp.json()

            if not payload.get("success"):
                logger.warning("Ticker unsuccessful for %s: %s", symbol, payload)
                return None

            return payload.get("result", {})

        except requests.RequestException as exc:
            logger.error("Ticker request failed for %s: %s", symbol, exc)
            return None

    def get_tickers_batch(self, symbols: list[str]) -> dict[str, dict]:
        """Fetch tickers for multiple symbols."""
        results = {}
        for symbol in symbols:
            ticker = self.get_ticker(symbol)
            if ticker:
                results[symbol] = ticker
            time.sleep(0.1)  # Respect rate limits
        return results

    # ----- Historical candles -----

    def get_candles(
        self,
        symbol: str,
        resolution: str = "5m",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Candle]:
        """
        Fetch historical OHLCV candles.

        Resolution values: '1m', '3m', '5m', '15m', '30m', '1h', '2h',
                          '4h', '6h', '1d', '1w'
        """
        params: dict[str, Any] = {"symbol": symbol, "resolution": resolution}
        if start:
            params["start"] = int(start.timestamp())
        if end:
            params["end"] = int(end.timestamp())

        try:
            resp = self._session.get(
                f"{self.BASE_URL}/v2/history/candles",
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as exc:
            logger.error("Candle fetch failed for %s: %s", symbol, exc)
            return []

        if not payload.get("success"):
            logger.warning("Candle API unsuccessful for %s: %s", symbol, payload)
            return []

        raw_candles = payload.get("result", [])
        candles = []

        for c in raw_candles:
            try:
                ts = datetime.fromtimestamp(c["time"], tz=timezone.utc)
                candle = Candle(
                    symbol=symbol,
                    exchange="delta",
                    interval=resolution,
                    timestamp=ts,
                    open=float(c["open"]),
                    high=float(c["high"]),
                    low=float(c["low"]),
                    close=float(c["close"]),
                    volume=float(c.get("volume", 0)),
                    is_complete=True,
                )
                errors = candle.validate()
                if errors:
                    logger.warning("Invalid candle %s@%s: %s", symbol, ts, errors)
                    continue
                candles.append(candle)
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning("Skipping malformed candle for %s: %s", symbol, exc)

        # Sort chronologically
        candles.sort(key=lambda c: c.timestamp)
        logger.debug("Fetched %d valid candles for %s (%s)", len(candles), symbol, resolution)
        return candles

    def get_candles_paginated(
        self,
        symbol: str,
        resolution: str,
        start: datetime,
        end: datetime,
        max_pages: int = 50,
    ) -> list[Candle]:
        """Fetch candles over a large date range with pagination."""
        all_candles = []
        current_start = start
        page = 0

        while current_start < end and page < max_pages:
            batch = self.get_candles(symbol, resolution, current_start, end)
            if not batch:
                break

            all_candles.extend(batch)
            last_ts = batch[-1].timestamp
            if last_ts <= current_start:
                break  # No progress
            current_start = last_ts
            page += 1
            time.sleep(0.2)  # Rate limit

        # Deduplicate by timestamp
        seen = set()
        unique = []
        for c in all_candles:
            key = c.timestamp.isoformat()
            if key not in seen:
                seen.add(key)
                unique.append(c)

        unique.sort(key=lambda c: c.timestamp)
        return unique


class DeltaWebSocketClient:
    """
    WebSocket client for live Delta Exchange market data.

    Features: auto-reconnect, heartbeat, callback-based updates.
    """

    WS_URL = "wss://public-socket.india.delta.exchange"

    def __init__(
        self,
        symbols: list[str],
        on_ticker: Callable[[TickerUpdate], None] | None = None,
        on_status_change: Callable[[ConnectionStatus], None] | None = None,
    ):
        self.symbols = symbols
        self._on_ticker = on_ticker
        self._on_status_change = on_status_change
        self._ws: websocket.WebSocketApp | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._status = ConnectionStatus.DISCONNECTED
        self._reconnect_delay = 1  # seconds, doubles on failure
        self._max_reconnect_delay = 60
        self._message_count = 0

    @property
    def status(self) -> ConnectionStatus:
        return self._status

    @property
    def message_count(self) -> int:
        return self._message_count

    def start(self) -> None:
        """Start the WebSocket connection in a background thread."""
        if self._running:
            logger.warning("WebSocket already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("Delta WebSocket started for %s", self.symbols)

    def stop(self) -> None:
        """Gracefully stop the WebSocket."""
        self._running = False
        if self._ws:
            self._ws.close()
        self._set_status(ConnectionStatus.DISCONNECTED)
        logger.info("Delta WebSocket stopped")

    def _set_status(self, status: ConnectionStatus) -> None:
        self._status = status
        if self._on_status_change:
            try:
                self._on_status_change(status)
            except Exception as exc:
                logger.error("Status callback error: %s", exc)

    def _run_loop(self) -> None:
        """Main reconnection loop."""
        while self._running:
            try:
                self._set_status(ConnectionStatus.RECONNECTING)
                self._ws = websocket.WebSocketApp(
                    self.WS_URL,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self._ws.run_forever(ping_interval=30, ping_timeout=10)
            except Exception as exc:
                logger.error("WebSocket run error: %s", exc)

            if not self._running:
                break

            # Exponential backoff
            logger.info("Reconnecting in %ds...", self._reconnect_delay)
            time.sleep(self._reconnect_delay)
            self._reconnect_delay = min(
                self._reconnect_delay * 2, self._max_reconnect_delay
            )

    def _on_open(self, ws) -> None:
        logger.info("Delta WebSocket connected")
        self._reconnect_delay = 1  # Reset backoff

        # Enable heartbeat
        ws.send(json.dumps({"type": "enable_heartbeat"}))

        # Subscribe to ticker
        subscription = {
            "type": "subscribe",
            "payload": {
                "channels": [
                    {"name": "ticker", "symbols": self.symbols}
                ]
            },
        }
        ws.send(json.dumps(subscription))
        self._set_status(ConnectionStatus.CONNECTED)

    def _on_message(self, ws, message: str) -> None:
        self._message_count += 1

        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return

        msg_type = data.get("type", "")

        if msg_type == "heartbeat":
            return  # Silently handle heartbeat

        # Ticker channel updates
        if msg_type == "ticker" and self._on_ticker:
            try:
                symbol = data.get("symbol", "")
                update = TickerUpdate(
                    symbol=symbol,
                    exchange="delta",
                    last_price=float(data.get("close", 0) or 0),
                    mark_price=_safe_float(data.get("mark_price")),
                    volume_24h=_safe_float(data.get("volume")),
                    high_24h=_safe_float(data.get("high")),
                    low_24h=_safe_float(data.get("low")),
                    timestamp=datetime.now(timezone.utc),
                )
                self._on_ticker(update)
            except Exception as exc:
                logger.error("Error processing ticker update: %s", exc)

    def _on_error(self, ws, error) -> None:
        logger.error("Delta WebSocket error: %s", error)
        self._set_status(ConnectionStatus.ERROR)

    def _on_close(self, ws, status_code, message) -> None:
        logger.info("Delta WebSocket closed (code=%s, msg=%s)", status_code, message)
        self._set_status(ConnectionStatus.DISCONNECTED)


def _safe_float(val) -> float | None:
    """Safely convert a value to float, returning None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
