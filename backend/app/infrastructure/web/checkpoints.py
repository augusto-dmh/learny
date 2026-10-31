"""Checkpoint router — the end-of-section predict → recall → explain loop.

- ``POST /api/sources/{source_id}/checkpoints`` → 201 the checkpoint and its
  attempts, questions only and never an answer. 404 for an unreadable source or
  an anchor with no section.
- ``POST /api/checkpoint-attempts/{attempt_id}/response`` → 200 what the
  response unlocks: a recall's answer, or an explanation's formative feedback.
  409 on a second response. 429/503 when the AI budget refuses explain-back.
- ``POST /api/checkpoint-attempts/{attempt_id}/reveal`` → 200 the passage
  ("Just explain"). 409 on a recall attempt or after a response.
- ``POST /api/checkpoint-attempts/{attempt_id}/grade`` → 200 the reviewed card's
  new schedule. 409 before a response or on a second grade, 422 outside the
  attempt kind's scale.
- ``GET /api/sources/{source_id}/calibration`` → 200 the per-book calibration:
  always three rows, one per confidence level, counting the learner's unaided
  not-undone grades and how many recalled. 404 for an unreadable source.

Every route requires a session. The POSTs add origin + CSRF and the quiz rate
limit, as the review routes do. A missing attempt and another learner's attempt
are the same 404. Confidence and assistance are never accepted on the grade:
the server already holds both.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, ConfigDict, Field

from app.application.checkpoints import (
    MAX_RESPONSE_CHARS,
    ExplainFeedback,
    GradeAttempt,
    RespondToAttempt,
    RevealPassage,
    SourceCalibration,
    StartCheckpoint,
)
from app.domain.entities import User
from app.infrastructure.web.csrf import enforce_csrf, enforce_origin
from app.infrastructure.web.dependencies import (
    get_authenticated_user,
    get_grade_attempt,
    get_respond_to_attempt,
    get_response_language,
    get_reveal_passage,
    get_source_calibration,
    get_start_checkpoint,
)
from app.infrastructure.web.rate_limit import rate_limit_quiz

router = APIRouter(tags=["checkpoints"])

_GUARDS = [Depends(rate_limit_quiz), Depends(enforce_origin), Depends(enforce_csrf)]


class StartCheckpointRequest(BaseModel):
    """The section to check, and the prediction made before any attempt (or none)."""

    anchor: str = Field(min_length=1, max_length=2048)
    prediction: int | None = Field(default=None, ge=1, le=3)


class AttemptView(BaseModel):
    """One attempt as the learner first sees it: what to retrieve, never the answer."""

    attempt_id: UUID
    kind: Literal["recall", "explain"]
    question: str


class CheckpointView(BaseModel):
    checkpoint_id: UUID
    section_title: str
    anchor: str
    attempts: list[AttemptView]


class RespondRequest(BaseModel):
    """A typed attempt (empty means "I don't remember") and its one-tap confidence."""

    response: str = Field(max_length=MAX_RESPONSE_CHARS)
    confidence: int = Field(ge=1, le=3)


class RecallRevealView(BaseModel):
    answer: str
    source_excerpt: str
    anchor: str
    section_path: list[str]


class CitationQuoteView(BaseModel):
    anchor: str
    section_path: list[str]
    quote: str


class ExplainFeedbackView(BaseModel):
    """Formative feedback: prose and the passages it quotes. No score, by design."""

    feedback: str
    citations: list[CitationQuoteView]


class PassageView(BaseModel):
    passage: str
    anchor: str
    section_path: list[str]


class GradeRequest(BaseModel):
    """FSRS rating. A recall takes 1–4; an explanation 1–3 (enforced by the service).

    Extra fields are refused rather than ignored: confidence and assistance are
    already held server-side, and a client that sends them is told so (422).
    """

    model_config = ConfigDict(extra="forbid")

    rating: int = Field(ge=1, le=4)


class GradeView(BaseModel):
    quiz_item_id: UUID
    due: str
    state: int


@router.post(
    "/api/sources/{source_id}/checkpoints",
    status_code=status.HTTP_201_CREATED,
    dependencies=_GUARDS,
)
def start_checkpoint(
    source_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[StartCheckpoint, Depends(get_start_checkpoint)],
    body: StartCheckpointRequest,
) -> CheckpointView:
    """Begin a checkpoint on one section (201). Returns questions only."""
    started = service(
        user=user, source_id=source_id, anchor=body.anchor, prediction=body.prediction
    )
    return CheckpointView(
        checkpoint_id=started.checkpoint.id,
        section_title=started.checkpoint.section_title,
        anchor=started.checkpoint.anchor,
        attempts=[
            AttemptView(attempt_id=attempt.id, kind=attempt.kind, question=question)
            for attempt, question in started.attempts
        ],
    )


@router.post("/api/checkpoint-attempts/{attempt_id}/response", dependencies=_GUARDS)
def respond_to_attempt(
    attempt_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[RespondToAttempt, Depends(get_respond_to_attempt)],
    response_language: Annotated[str | None, Depends(get_response_language)],
    body: RespondRequest,
) -> RecallRevealView | ExplainFeedbackView:
    """Store the attempt once, then return what it unlocks (200).

    The explanation's feedback is asked for in the learner's language: the
    stored locale, else ``Accept-Language``, else English.
    """
    result = service(
        user=user,
        attempt_id=attempt_id,
        response=body.response,
        confidence=body.confidence,
        response_language=response_language,
    )
    if isinstance(result, ExplainFeedback):
        return ExplainFeedbackView(
            feedback=result.feedback,
            citations=[
                CitationQuoteView(
                    anchor=citation.anchor,
                    section_path=list(citation.section_path),
                    quote=citation.quote,
                )
                for citation in result.citations
            ],
        )
    return RecallRevealView(
        answer=result.answer,
        source_excerpt=result.source_excerpt,
        anchor=result.anchor,
        section_path=list(result.section_path),
    )


@router.post("/api/checkpoint-attempts/{attempt_id}/reveal", dependencies=_GUARDS)
def reveal_passage(
    attempt_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[RevealPassage, Depends(get_reveal_passage)],
) -> PassageView:
    """ "Just explain": show the passage, and mark the attempt assisted (200)."""
    revealed = service(user=user, attempt_id=attempt_id)
    return PassageView(
        passage=revealed.passage,
        anchor=revealed.anchor,
        section_path=list(revealed.section_path),
    )


@router.post("/api/checkpoint-attempts/{attempt_id}/grade", dependencies=_GUARDS)
def grade_attempt(
    attempt_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[GradeAttempt, Depends(get_grade_attempt)],
    body: GradeRequest,
    client_tz: Annotated[str | None, Header(alias="X-Client-Timezone")] = None,
) -> GradeView:
    """Self-assess the attempt once and schedule it through FSRS (200)."""
    graded = service(user=user, attempt_id=attempt_id, rating=body.rating, client_tz=client_tz)
    snapshot = graded.reviewed.snapshot
    return GradeView(
        quiz_item_id=graded.quiz_item_id,
        due=snapshot.due.isoformat(),
        state=snapshot.state,
    )


class CalibrationLevelView(BaseModel):
    """One confidence level's calibration: attempts and how many recalled."""

    confidence: int
    attempts: int
    recalled: int


class CalibrationView(BaseModel):
    """The per-book calibration: exactly three rows, for confidence 1, 2 and 3."""

    levels: list[CalibrationLevelView]


@router.get("/api/sources/{source_id}/calibration")
def source_calibration(
    source_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[SourceCalibration, Depends(get_source_calibration)],
) -> CalibrationView:
    """How often feeling sure meant recalling on this book (200).

    A missing or unreadable source is the same 404 as everywhere else. Rows are
    never another learner's: the counts join the caller's own log rows to their
    own cards on this source.
    """
    levels = service(user=user, source_id=source_id)
    return CalibrationView(
        levels=[
            CalibrationLevelView(
                confidence=level.confidence, attempts=level.attempts, recalled=level.recalled
            )
            for level in levels
        ]
    )
