"""Logging configuration plus an in-memory ring buffer for the dashboard.

The bot logs to stdout (and optionally a file) while also keeping the most
recent records in a bounded deque so the dashboard can render a live
``LOGS SYSTÈME`` panel without re-reading files.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import UTC, datetime

_RING: deque[dict] = deque(maxlen=500)


class RingBufferHandler(logging.Handler):
    """Keeps structured copies of recent log records in memory."""

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D102
        _RING.append(
            {
                "time": datetime.fromtimestamp(record.created, tz=UTC),
                "level": record.levelname,
                "name": record.name,
                "message": record.getMessage(),
            }
        )


def recent_logs(limit: int = 100) -> list[dict]:
    """Return up to ``limit`` most recent log records (newest last)."""
    items = list(_RING)
    return items[-limit:]


_CONFIGURED = False


def configure_logging(level: int = logging.INFO) -> None:
    """Idempotently configure root logging for the application."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    fmt = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    datefmt = "%H:%M:%S"

    stream = logging.StreamHandler()
    stream.setFormatter(logging.Formatter(fmt, datefmt))

    ring = RingBufferHandler()
    ring.setFormatter(logging.Formatter(fmt, datefmt))

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(stream)
    root.addHandler(ring)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
