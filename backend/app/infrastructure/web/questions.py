"""Questions router — owner-scoped cited Q&A over a ready source (Phase 7).

Thin FastAPI adapter over the framework-free ``AskQuestion`` service (assembled
in ``dependencies``). A signed-in owner POSTs a question for one of their ready
sources and gets back a grounded, cited answer — or an explicit
``not_found_in_source`` outcome. The handler owns input validation (422) and
lets application errors propagate to the global handlers (``SourceNotFound`` →
404, ``SourceNotReady`` → 409, ``AnswerGenerationFailed`` → 502), mirroring the
retrieval endpoint.

Contract (also consumed by the Next.js proxy):
- ``POST /api/sources/{id}/questions`` → 200 answer; auth + CSRF/Origin + rate
  limit. Body ``{question}``: the question is stripped and validated 1..
  ``LEARNY_QA_QUESTION_MAX_CHARS`` chars → 422 otherwise, before the service
  runs; the **trimmed** value is passed on. Both 200 outcomes (answered /
  not-found) carry ``retrieval`` diagnostics and ``model`` (QA-04).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from app.application.qa import AskQuestion
from app.core.config import get_settings
from app.domain.entities import QuestionAnswer, User
from app.infrastructure.web.csrf import enforce_csrf, enforce_origin
from app.infrastructure.web.dependencies import (
    get_ask_question,
    get_authenticated_user,
)
from app.infrastructure.web.rate_limit import rate_limit_questions
from app.infrastructure.web.retrieval import EvidenceView
from app.infrastructure.web.ui_message_stream import (
    to_sse_response,
)

router = APIRouter(prefix="/api/sources", tags=["questions"])


class QuestionRequest(BaseModel):
    """Question request body (QA-09/QA-10).

    ``question`` must be non-blank after stripping and, once trimmed, at most
    ``LEARNY_QA_QUESTION_MAX_CHARS`` chars (the bound is inclusive). Both raise a
    Pydantic validation error → 422 before the service runs. The validator
    returns the **trimmed** value, so the service receives a normalized question
    (matching retrieve's non-blank rule).
    """

    question: str = Field(min_length=1)
    # AD-147: Q&A includes the user's notes by default. The client sends the flag
    # only after an explicit choice; an absent flag defaults on here (server-owned),
    # so a note-carrying answer is the out-of-the-box behaviour (NL-04).
    include_notes: bool = True

    @field_validator("question")
    @classmethod
    def _question_bounds(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("question must not be empty or whitespace-only")
        max_chars = get_settings().qa_question_max_chars
        if len(trimmed) > max_chars:
            raise ValueError(f"question must be at most {max_chars} characters")
        return trimmed


class RetrievalDiagnostics(BaseModel):
    """Retrieval diagnostics carried on every 200 (answered or not-found, QA-04)."""

    strategy: str
    evidence_count: int


class AnswerResponse(BaseModel):
    """A cited answer (answered) or the explicit not-found outcome (QA-01..04, 13).

    ``citations`` reuses the retrieval endpoint's ``EvidenceView`` (the same
    citation-only projection); it is non-empty and grounded for ``answered`` and
    empty for ``not_found_in_source``. ``retrieval`` and ``model`` appear on both
    outcomes so the UI and future evaluation always see diagnostics (QA-04).
    """

    answer_status: str
    answer: str
    citations: list[EvidenceView]
    retrieval: RetrievalDiagnostics
    model: str

    @classmethod
    def from_question_answer(cls, result: QuestionAnswer) -> AnswerResponse:
        return cls(
            answer_status=result.status,
            answer=result.text,
            citations=[EvidenceView.from_evidence(c) for c in result.citations],
            retrieval=RetrievalDiagnostics(
                strategy="hybrid", evidence_count=result.evidence_count
            ),
            model=result.model,
        )


@router.post(
    "/{source_id}/questions",
    dependencies=[
        Depends(rate_limit_questions),
        Depends(enforce_origin),
        Depends(enforce_csrf),
    ],
)
def ask_question(
    source_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[AskQuestion, Depends(get_ask_question)],
    body: QuestionRequest,
) -> AnswerResponse:
    """Return a grounded cited answer (200); 422/401/403/404/409/429/502 per the ACs.

    ``AskQuestion`` authorizes ownership (missing/non-owner → ``SourceNotFound`` →
    404), enforces readiness (``SourceNotReady`` → 409), retrieves evidence, and
    either composes a grounded answer or returns the explicit not-found outcome;
    a generation failure surfaces as ``AnswerGenerationFailed`` → 502 (generic).
    """
    result = service(
        user=user,
        source_id=source_id,
        question=body.question,
        include_notes=body.include_notes,
    )
    return AnswerResponse.from_question_answer(result)


@router.post(
    "/{source_id}/questions/stream",
    dependencies=[
        Depends(rate_limit_questions),
        Depends(enforce_origin),
        Depends(enforce_csrf),
    ],
)
def ask_question_stream(
    source_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[AskQuestion, Depends(get_ask_question)],
    body: QuestionRequest,
):
    """Stream a grounded cited answer as UI Message Stream v1 SSE frames (GEN-14).

    The SSE sibling of :func:`ask_question`: identical request schema and
    auth/CSRF/Origin/rate-limit dependencies. ``AskQuestion.stream`` runs all guards
    **eagerly** here in the handler body, so ownership (404), readiness (409),
    validation (422) and rate-limit (429) surface as the same plain HTTP errors as
    the JSON endpoint *before* any SSE byte is sent; only then is the presenter's
    frame generator returned. A generation failure after that point is rendered by
    the presenter as a protocol ``error`` part (headers are already sent).
    """
    events = service.stream(
        user=user,
        source_id=source_id,
        question=body.question,
        include_notes=body.include_notes,
    )
    return to_sse_response(events)
