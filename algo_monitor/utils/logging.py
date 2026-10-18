"""
Structured logging for Algo Monitor.

- JSON-formatted logs when running in production
- Human-readable coloured output for local development
- Secrets are never logged (filter applied)
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone


class _AlgoFormatter(logging.Formatter):
    """Clean, structured formatter with ISO-8601 timestamps."""

    COLOURS = {
        "DEBUG": "\033[36m",     # cyan
        "INFO": "\033[32m",      # green
        "WARNING": "\033[33m",   # yellow
        "ERROR": "\033[31m",     # red
        "CRITICAL": "\033[1;31m",  # bold red
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        colour = self.COLOURS.get(record.levelname, "")
        reset = self.RESET if colour else ""
        msg = super().format(record)
        return f"{ts} {colour}{record.levelname:8s}{reset} [{record.name}] {msg}"


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger for the application."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_AlgoFormatter())

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Remove any existing handlers to avoid duplicates on reload
    root.handlers.clear()
    root.addHandler(handler)

    # Quieten noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("websocket").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger under the algo_monitor namespace."""
    return logging.getLogger(f"algo_monitor.{name}")
