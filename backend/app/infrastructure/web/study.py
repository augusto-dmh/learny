"""Study + continue-reading router — the read side of the Home surface (RFC-004 Cycle E).

Thin FastAPI adapters over the framework-free ``GetStudySummary`` and ``ContinueReading``
services. Both are plain authenticated GETs (no CSRF, no job). The optional
``X-Client-Timezone`` header sets the study-day boundary for the summary; the continue
endpoint has no day logic and does not read it.

Contract:
- ``GET /api/study/days?window=`` → 200 window rows + ``studied_last_14``; ``window``
  defaults to 84, bounds 7..365 (else 422). No session → 401 (HOME-11).
- ``GET /api/reading/continue`` → 200 hero shape, or ``null`` when the caller has no
  reading positions. No session → 401 (HOME-01/02).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel

from app.application.study import ContinueReading, GetStudySummary
from app.domain.entities import ContinuePoint, StudySummary, User
from app.infrastructure.web.dependencies import (
    get_authenticated_user,
    get_continue_reading,
    get_study_summary,
)

router = APIRouter(tags=["study"])


class StudyDayView(BaseModel):
    """One user-local day of activity with its per-kind counters (HOME-11)."""

    day: date
    reviews_count: int
    reading_updates: int


class StudySummaryView(BaseModel):
    """The adherence read model: window rows + the 14-day adherence count (HOME-11/12)."""

    days: list[StudyDayView]
    studied_last_14: int

    @classmethod
    def from_summary(cls, summary: StudySummary) -> StudySummaryView:
        return cls(
            days=[
                StudyDayView(
                    day=d.day,
                    reviews_count=d.reviews_count,
                    reading_updates=d.reading_updates,
                )
                for d in summary.days
            ],
            studied_last_14=summary.studied_last_14,
        )


class ContinueReadingView(BaseModel):
    """The continue-reading hero: where to resume in one click (HOME-01/03)."""

    source_id: UUID
    source_title: str
    chapter_title: str
    percent: float
    updated_at: datetime

    @classmethod
    def from_point(cls, point: ContinuePoint) -> ContinueReadingView:
        return cls(
            source_id=point.source_id,
            source_title=point.source_title,
            chapter_title=point.chapter_title,
            percent=float(point.percent),
            updated_at=point.updated_at,
        )


@router.get("/api/study/days")
def get_study_days(
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[GetStudySummary, Depends(get_study_summary)],
    window: Annotated[int, Query(ge=7, le=365)] = 84,
    client_tz: Annotated[str | None, Header(alias="X-Client-Timezone")] = None,
) -> StudySummaryView:
    """Return the caller's study-day window + ``studied_last_14`` (200; 401; 422).

    ``window`` defaults to 84 (12 weeks) and is bounded 7..365 by Pydantic — out of
    range → 422. The day boundary follows the optional ``X-Client-Timezone`` header
    (silent UTC fallback). Everything is derived at read time; nothing is stored.
    """
    summary = service(user=user, window=window, tz=client_tz)
    return StudySummaryView.from_summary(summary)


@router.get("/api/reading/continue")
def get_continue_reading_endpoint(
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[ContinueReading, Depends(get_continue_reading)],
) -> ContinueReadingView | None:
    """Return the caller's most-recent reading position as the hero, or ``null`` (200; 401).

    ``ContinueReading`` reads the caller's most-recent position (user-scoped in SQL) and
    resolves its chapter title; a caller with no positions gets ``null`` (200) so the hero
    renders its pick-a-book empty state.
    """
    point = service(user=user)
    return ContinueReadingView.from_point(point) if point is not None else None
