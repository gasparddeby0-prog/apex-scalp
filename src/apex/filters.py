"""Trade-eligibility filters: spread, trading session and rollover windows.

The economic-calendar / news blackout is intentionally a stub: it requires an
external data feed. Wire a real calendar into :func:`news_blackout` before
relying on the news rule in live trading.
"""

from __future__ import annotations

from datetime import datetime

from apex.models import utcnow


def in_trading_session(now: datetime | None = None) -> bool:
    """True during the London (08-17 UTC) or New York (13-22 UTC) sessions,
    Monday-Friday."""
    now = now or utcnow()
    if now.weekday() >= 5:  # Saturday/Sunday
        return False
    hour = now.hour + now.minute / 60.0
    london = 8.0 <= hour < 17.0
    new_york = 13.0 <= hour < 22.0
    return london or new_york


def in_overlap(now: datetime | None = None) -> bool:
    """London-NY overlap (13-17 UTC) - the spec's signal-boost window."""
    now = now or utcnow()
    if now.weekday() >= 5:
        return False
    hour = now.hour + now.minute / 60.0
    return 13.0 <= hour < 17.0


def is_rollover(now: datetime | None = None) -> bool:
    """Avoid the daily rollover window (23:45-00:15 UTC)."""
    now = now or utcnow()
    hour = now.hour + now.minute / 60.0
    return hour >= 23.75 or hour < 0.25


def news_blackout(symbol: str, now: datetime | None = None) -> bool:  # pragma: no cover
    """Stub: return True if a high-impact news event is within +/-30 min.

    Always returns False until a real economic calendar is connected.
    """
    return False
