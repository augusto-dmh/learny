"""System clock adapter (implements the ``Clock`` port)."""

from __future__ import annotations

from datetime import UTC, datetime


class SystemClock:
    """``Clock`` backed by the wall clock, in timezone-aware UTC."""

    def now(self) -> datetime:
        return datetime.now(UTC)
