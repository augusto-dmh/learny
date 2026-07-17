"""Spaced-repetition scheduling adapters (implement ``SchedulingPort``, QUIZ-11).

The scheduling library (py-fsrs) lives only in these adapters; callers depend on
``SchedulingPort`` and the Learny-owned ``SchedulingSnapshot``. ``build_scheduling_adapter``
builds the FSRS-6 adapter from settings at the composition root so scheduling knobs never
leak into application/domain code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.infrastructure.scheduling.fsrs import FsrsSchedulingAdapter

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.domain.ports import SchedulingPort

__all__ = ["FsrsSchedulingAdapter", "build_scheduling_adapter"]


def build_scheduling_adapter(settings: Settings) -> SchedulingPort:
    """Return the FSRS-6 scheduling adapter built from ``settings`` (QUIZ-11)."""
    return FsrsSchedulingAdapter(
        desired_retention=settings.fsrs_desired_retention,
        fuzzing=settings.fsrs_fuzzing,
    )
