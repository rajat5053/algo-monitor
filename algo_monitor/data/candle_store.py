"""
Candle storage layer — read/write OHLCV data to SQLite.

Handles deduplication, validation, and efficient retrieval.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from algo_monitor.data.models import Candle
from algo_monitor.utils.logging import get_logger

if TYPE_CHECKING:
    from algo_monitor.database import Database

logger = get_logger("data.candle_store")


_KNOWN_INTERVAL_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


class CandleStore:
    """Persistent candle storage backed by SQLite."""

    def __init__(self, db: Database):
        self.db = db

    def upsert_candles(self, candles: list[Candle], validate_interval: bool = True) -> int:
        """
        Insert or update candles. Returns number of rows affected.
        Duplicates (same symbol/exchange/interval/timestamp) are updated.

        Raises ValueError if validate_interval is True and the candle timestamps
        are demonstrably inconsistent with the declared interval label.
        """
        if not candles:
            return 0

        if validate_interval and len(candles) >= 3:
            # Check for interval mismatch on consecutive candles
            interval = candles[0].interval
            if interval in _KNOWN_INTERVAL_SECONDS:
                expected = _KNOWN_INTERVAL_SECONDS[interval]
                # Sort sample by timestamp to check consecutive gap
                sample = sorted(candles[:min(len(candles), 15)], key=lambda c: c.timestamp)
                gaps = [
                    (sample[i].timestamp - sample[i - 1].timestamp).total_seconds()
                    for i in range(1, len(sample))
                ]
                pos_gaps = [g for g in gaps if g > 0]
                if pos_gaps:
                    median_gap = sorted(pos_gaps)[len(pos_gaps) // 2]
                    if median_gap >= 2.5 * expected or median_gap <= 0.4 * expected:
                        raise ValueError(
                            f"Candle duration mismatch for {candles[0].symbol} ({interval}): "
                            f"expected ~{expected}s, observed median gap {median_gap:.0f}s."
                        )


        rows = [
            (
                c.symbol,
                c.exchange,
                c.interval,
                c.timestamp.isoformat(),
                c.open,
                c.high,
                c.low,
                c.close,
                c.volume,
                1 if c.is_complete else 0,
            )
            for c in candles
        ]

        with self.db.transaction() as conn:
            conn.executemany(
                """INSERT INTO candles
                       (symbol, exchange, interval, timestamp,
                        open, high, low, close, volume, is_complete)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(symbol, exchange, interval, timestamp)
                   DO UPDATE SET
                       open=excluded.open,
                       high=excluded.high,
                       low=excluded.low,
                       close=excluded.close,
                       volume=excluded.volume,
                       is_complete=excluded.is_complete""",
                rows,
            )

        logger.debug(
            "Upserted %d candles for %s/%s/%s",
            len(rows),
            candles[0].symbol,
            candles[0].exchange,
            candles[0].interval,
        )
        return len(rows)

    def get_candles(
        self,
        symbol: str,
        exchange: str,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 0,
        complete_only: bool = True,
    ) -> list[Candle]:
        """
        Retrieve candles from the database in chronological order.

        Args:
            symbol: Instrument symbol
            exchange: Exchange name
            interval: Candle interval (e.g. '5m', '4h')
            start: Earliest candle timestamp (inclusive)
            end: Latest candle timestamp (inclusive)
            limit: Max number of candles (0 = unlimited)
            complete_only: Only return completed candles
        """
        sql = """SELECT * FROM candles
                 WHERE symbol = ? AND exchange = ? AND interval = ?"""
        params: list = [symbol, exchange, interval]

        if complete_only:
            sql += " AND is_complete = 1"
        if start:
            sql += " AND timestamp >= ?"
            params.append(start.isoformat())
        if end:
            sql += " AND timestamp <= ?"
            params.append(end.isoformat())

        if limit > 0:
            sql += f" ORDER BY timestamp DESC LIMIT {limit}"
            rows = self.db.fetchall(sql, tuple(params))
            return [_row_to_candle(r) for r in reversed(rows)]
        else:
            sql += " ORDER BY timestamp ASC"
            rows = self.db.fetchall(sql, tuple(params))
            return [_row_to_candle(r) for r in rows]

    def get_latest_timestamp(
        self, symbol: str, exchange: str, interval: str
    ) -> datetime | None:
        """Get the most recent candle timestamp for incremental fetching."""
        row = self.db.fetchone(
            """SELECT MAX(timestamp) as max_ts FROM candles
               WHERE symbol = ? AND exchange = ? AND interval = ?""",
            (symbol, exchange, interval),
        )
        if row and row["max_ts"]:
            return datetime.fromisoformat(row["max_ts"])
        return None

    def get_candle_count(
        self, symbol: str, exchange: str, interval: str
    ) -> int:
        """Count stored candles for an instrument/interval."""
        row = self.db.fetchone(
            """SELECT COUNT(*) as cnt FROM candles
               WHERE symbol = ? AND exchange = ? AND interval = ?""",
            (symbol, exchange, interval),
        )
        return row["cnt"] if row else 0

    def get_stored_symbols(self, exchange: str = "") -> list[dict]:
        """List all symbol/exchange/interval combinations in the store."""
        sql = """SELECT symbol, exchange, interval,
                        COUNT(*) as count,
                        MIN(timestamp) as earliest,
                        MAX(timestamp) as latest
                 FROM candles"""
        params: tuple = ()
        if exchange:
            sql += " WHERE exchange = ?"
            params = (exchange,)
        sql += " GROUP BY symbol, exchange, interval"

        rows = self.db.fetchall(sql, params)
        return [dict(r) for r in rows]

    def delete_candles(
        self, symbol: str, exchange: str, interval: str
    ) -> int:
        """Delete all candles for a given instrument/interval."""
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """DELETE FROM candles
                   WHERE symbol = ? AND exchange = ? AND interval = ?""",
                (symbol, exchange, interval),
            )
            return cursor.rowcount


def _row_to_candle(row) -> Candle:
    """Convert a database row to a Candle object."""
    return Candle(
        symbol=row["symbol"],
        exchange=row["exchange"],
        interval=row["interval"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        open=row["open"],
        high=row["high"],
        low=row["low"],
        close=row["close"],
        volume=row["volume"],
        is_complete=bool(row["is_complete"]),
    )
