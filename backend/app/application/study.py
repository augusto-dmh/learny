"""Study rollup + adherence application logic (RFC-004 Cycle E, design §Components).

Framework-free (ADR-007/009): no FastAPI/SQLAlchemy/SDK imports. ``local_day`` is the
pure day-boundary helper shared by the activity writes (``SubmitReview``,
``SaveReadingPosition``) and the read side — it maps a UTC instant to the user-local
calendar date from a client-supplied IANA timezone, degrading silently to UTC so a
garbage header can never break a write or a read.
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
