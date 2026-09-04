"""Interval-preview policy for review grade buttons (REV-29).

Pure mapping from a throwaway ``SchedulingPort.preview`` onto the nine display
buckets. Lives in application so the HTTP adapter does not own the product rule,
and so ``GetDueQueue`` can attach labels from the joined snapshot without a
second scheduling read.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.domain.entities import SchedulingSnapshot
from app.domain.ports import SchedulingPort

# Display buckets for interval preview. Exact minutes are a lie under fuzzing,
# so the UI grades against one of these nine tokens.
INTERVAL_LABELS: frozenset[str] = frozenset(
    {"~1m", "~10m", "~1h", "~1d", "~4d", "~2w", "~1mo", "~4mo", "~1y"}
)


def interval_bucket(delta: timedelta) -> str:
    """Map a next-due delta onto exactly one of the nine preview labels."""
    seconds = delta.total_seconds()
    if seconds < 90:
        return "~1m"
    if seconds < 12 * 60:
        return "~10m"
    if seconds < 90 * 60:
        return "~1h"
    if seconds < 36 * 3600:
        return "~1d"
    if seconds < 6 * 86400:
        return "~4d"
    if seconds < 18 * 86400:
        return "~2w"
    if seconds < 45 * 86400:
        return "~1mo"
    if seconds < 150 * 86400:
        return "~4mo"
    return "~1y"


def interval_labels_for(
    scheduling: SchedulingPort, snapshot: SchedulingSnapshot, now: datetime
) -> dict[int, str]:
    """Return rating → bucket from a non-persisted fuzzing-off preview."""
    return {
        rating: interval_bucket(due - now)
        for rating, due in scheduling.preview(snapshot, now).items()
    }
