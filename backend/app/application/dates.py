"""Pure calendar helpers shared across application services.

Framework-free (ADR-007/009). Lives in its own module so the activity writers
(``reviews``, ``reading``) and the study read side can share the day-boundary rule
without importing each other.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def local_day(now: datetime, tz_name: str | None) -> date:
    """Return the user-local calendar date of ``now`` in ``tz_name`` (HOME-09, I-3).

    ``now`` is the timezone-aware UTC instant from the clock. A valid IANA ``tz_name``
    (e.g. ``"America/Sao_Paulo"``) yields the date in that zone, applying its current
    UTC offset (including DST). A missing, empty, or invalid name (e.g. ``"Mars/Olympus"``)
    falls back to the UTC date — this never raises, so an absent or garbage client header
    degrades to UTC rather than failing the request.
    """
    if tz_name:
        try:
            return now.astimezone(ZoneInfo(tz_name)).date()
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return now.astimezone(UTC).date()
