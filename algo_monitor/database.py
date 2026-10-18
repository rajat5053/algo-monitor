"""
SQLite database layer for Algo Monitor.

Tables:
- candles:        Historical OHLCV data
- zones:          Detected support/resistance zones
- signals:        Generated trading signals
- trades:         Paper-trade records
- alert_log:      Sent alert history (for deduplication)
- system_state:   Key-value store for persistent state
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from algo_monitor.utils.logging import get_logger

logger = get_logger("database")

_local = threading.local()


class Database:
    """Thread-safe SQLite database wrapper with schema migration."""

    def __init__(self, db_path: str = "./algo_monitor.db"):
        self.db_path = str(Path(db_path).resolve())
        self._init_lock = threading.Lock()
        self._initialised = False

    def _get_connection(self) -> sqlite3.Connection:
        """One connection per thread per database path for safety."""
        conns = getattr(_local, "db_conns", None)
        if conns is None:
            conns = {}
            _local.db_conns = conns
        conn = conns.get(self.db_path)
        if conn is None:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            conns[self.db_path] = conn
        return conn

    def close(self) -> None:
        """Close the database connection for this thread if open."""
        conns = getattr(_local, "db_conns", None)
        if conns and self.db_path in conns:
            try:
                conns[self.db_path].close()
            except Exception:
                pass
            del conns[self.db_path]

    @contextmanager
    def transaction(self):
        """Context manager for atomic writes."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        conn = self._get_connection()
        return conn.execute(sql, params)

    def executemany(self, sql: str, params_list: list[tuple]) -> sqlite3.Cursor:
        conn = self._get_connection()
        return conn.executemany(sql, params_list)

    def fetchone(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        return self.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return self.execute(sql, params).fetchall()

    def initialise(self) -> None:
        """Create tables if they don't exist. Idempotent."""
        with self._init_lock:
            if self._initialised:
                return
            self._create_tables()
            self._initialised = True
            logger.info("Database initialised at %s", self.db_path)

    def _create_tables(self) -> None:
        with self.transaction() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS candles (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol          TEXT    NOT NULL,
                    exchange        TEXT    NOT NULL,
                    interval        TEXT    NOT NULL,
                    timestamp       TEXT    NOT NULL,   -- ISO-8601 UTC
                    open            REAL    NOT NULL,
                    high            REAL    NOT NULL,
                    low             REAL    NOT NULL,
                    close           REAL    NOT NULL,
                    volume          REAL    NOT NULL DEFAULT 0,
                    is_complete     INTEGER NOT NULL DEFAULT 1,
                    UNIQUE(symbol, exchange, interval, timestamp)
                );

                CREATE INDEX IF NOT EXISTS idx_candles_lookup
                    ON candles(symbol, exchange, interval, timestamp);

                CREATE TABLE IF NOT EXISTS zones (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol          TEXT    NOT NULL,
                    exchange        TEXT    NOT NULL,
                    zone_type       TEXT    NOT NULL,   -- 'support' or 'resistance'
                    price_low       REAL    NOT NULL,
                    price_high      REAL    NOT NULL,
                    strength        REAL    NOT NULL DEFAULT 1.0,
                    touches         INTEGER NOT NULL DEFAULT 1,
                    first_seen      TEXT    NOT NULL,
                    last_seen       TEXT    NOT NULL,
                    interval        TEXT    NOT NULL DEFAULT '4h',
                    is_active       INTEGER NOT NULL DEFAULT 1,
                    reason          TEXT    NOT NULL DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_zones_lookup
                    ON zones(symbol, exchange, is_active);

                CREATE TABLE IF NOT EXISTS signals (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol          TEXT    NOT NULL,
                    exchange        TEXT    NOT NULL,
                    setup_type      TEXT    NOT NULL,
                    direction       TEXT    NOT NULL,   -- 'long' or 'short'
                    timeframe       TEXT    NOT NULL,
                    zone_id         INTEGER,
                    entry_ref       REAL,
                    stop_loss       REAL,
                    target          REAL,
                    risk_reward     REAL,
                    strength        REAL    NOT NULL DEFAULT 0.5,
                    reason          TEXT    NOT NULL DEFAULT '',
                    invalidation    TEXT    NOT NULL DEFAULT '',
                    created_at      TEXT    NOT NULL,
                    expires_at      TEXT,
                    is_active       INTEGER NOT NULL DEFAULT 1,
                    was_traded      INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (zone_id) REFERENCES zones(id)
                );

                CREATE INDEX IF NOT EXISTS idx_signals_active
                    ON signals(symbol, exchange, is_active);

                CREATE TABLE IF NOT EXISTS trades (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id       INTEGER,
                    symbol          TEXT    NOT NULL,
                    exchange        TEXT    NOT NULL,
                    direction       TEXT    NOT NULL,
                    trading_mode    TEXT    NOT NULL DEFAULT 'intraday',
                    status          TEXT    NOT NULL DEFAULT 'open',
                    quantity        REAL    NOT NULL,
                    entry_price     REAL    NOT NULL,
                    entry_time      TEXT    NOT NULL,
                    stop_loss       REAL    NOT NULL,
                    target          REAL    NOT NULL,
                    exit_price      REAL,
                    exit_time       TEXT,
                    exit_reason     TEXT,
                    gross_pnl       REAL    DEFAULT 0,
                    fees            REAL    DEFAULT 0,
                    slippage        REAL    DEFAULT 0,
                    net_pnl         REAL    DEFAULT 0,
                    risk_amount     REAL    DEFAULT 0,
                    notes           TEXT    DEFAULT '',
                    source          TEXT    NOT NULL DEFAULT 'paper',
                    FOREIGN KEY (signal_id) REFERENCES signals(id)
                );

                CREATE INDEX IF NOT EXISTS idx_trades_status
                    ON trades(status, symbol);

                CREATE TABLE IF NOT EXISTS alert_log (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id       INTEGER,
                    channel         TEXT    NOT NULL,
                    message_hash    TEXT    NOT NULL,
                    sent_at         TEXT    NOT NULL,
                    success         INTEGER NOT NULL DEFAULT 1,
                    UNIQUE(message_hash, channel)
                );

                CREATE TABLE IF NOT EXISTS system_state (
                    key             TEXT    PRIMARY KEY,
                    value           TEXT    NOT NULL,
                    updated_at      TEXT    NOT NULL
                );

                CREATE TABLE IF NOT EXISTS daily_pnl (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    date            TEXT    NOT NULL,
                    realised_pnl    REAL    NOT NULL DEFAULT 0,
                    unrealised_pnl  REAL    NOT NULL DEFAULT 0,
                    total_fees      REAL    NOT NULL DEFAULT 0,
                    trade_count     INTEGER NOT NULL DEFAULT 0,
                    circuit_tripped INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(date)
                );

                CREATE TABLE IF NOT EXISTS trade_management (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id            INTEGER NOT NULL REFERENCES trades(id),
                    evaluated_at        TEXT    NOT NULL,
                    recommendation      TEXT    NOT NULL,
                    proposed_target     REAL,
                    current_target      REAL    NOT NULL,
                    evidence_for        TEXT    NOT NULL DEFAULT '',
                    evidence_against    TEXT    NOT NULL DEFAULT '',
                    alert_sent          INTEGER NOT NULL DEFAULT 0,
                    alert_hash          TEXT    NOT NULL DEFAULT '',
                    UNIQUE(trade_id, recommendation, proposed_target)
                );

                CREATE INDEX IF NOT EXISTS idx_trade_management_trade_id
                    ON trade_management(trade_id);
            """)

    # ---- Convenience helpers for system_state ----

    def get_state(self, key: str, default: str = "") -> str:
        row = self.fetchone(
            "SELECT value FROM system_state WHERE key = ?", (key,)
        )
        return row["value"] if row else default

    def set_state(self, key: str, value: str) -> None:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        self.execute(
            """INSERT INTO system_state (key, value, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                                              updated_at=excluded.updated_at""",
            (key, value, now),
        )
        self._get_connection().commit()


# Module-level singleton
_db: Database | None = None


def get_database(db_path: str | None = None) -> Database:
    """Return the shared Database instance, creating it on first call."""
    global _db
    if _db is None:
        path = db_path or "./algo_monitor.db"
        _db = Database(path)
        _db.initialise()
    return _db
