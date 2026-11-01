"""Guest sample ask router (AD-320 thaw).

The one unauthenticated write route: a signed-out visitor asks the shared
sample one question and gets the same grounded, citation-carrying answer shape
an authenticated Ask produces — or an explicit honest refusal. The caps are
backend-owned end to end:

- ``rate_limit_sample_ask`` keys the per-day ask cap on the trusted client IP
  (Redis-backed in production, fail-closed 503 when it is down);
- the question length ceiling is validated here, before any retrieval,
  generation, or budget spend (422 like every other validation failure);
- the sample's own ``DailyBudget`` (its seeded operator's ledger row) refuses
  with the honest exhausted copy (429) when the day is spent;
- a missing or unready sample answers 503; a generation that grounds nothing
  answers ``found: false`` with no citations — never placeholder text.

No session cookie exists, so CSRF-token enforcement does not apply; the Origin
gate (the same one register/login use) and the IP limiter are the brakes.
Everything about the visitor stays in memory: nothing is persisted anywhere.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from app.application.errors import ValidationError
from app.application.sample_ask import GuestAnswer, GuestSampleAsk
from app.core.config import get_settings
from app.infrastructure.web.csrf import enforce_origin
from app.infrastructure.web.dependencies import (
    get_guest_response_language,
    get_guest_sample_ask,
)
from app.infrastructure.web.rate_limit import rate_limit_sample_ask
from app.infrastructure.web.retrieval import EvidenceView

router = APIRouter(tags=["sample"])


class SampleAskRequest(BaseModel):
    """One visitor question about the shared sample."""

    question: str = Field(min_length=1)


class SampleAskResponse(BaseModel):
    """The grounded answer, clearly labeled as the shared sample.

    ``found`` is false for both honest misses — nothing relevant in the sample,
    or nothing the generation grounded (AD-027) — with ``answer`` and
    ``citations`` empty either way. ``citations`` reuse the retrieval endpoint's
    ``EvidenceView`` citation-only projection, so the client renders them
    exactly like an authenticated turn's.
    """

    found: bool
    answer: str | None
    citations: list[EvidenceView]
    sample: bool = True

    @classmethod
    def from_guest_answer(cls, result: GuestAnswer) -> SampleAskResponse:
        return cls(
            found=result.found,
            answer=result.answer,
            citations=[EvidenceView.from_evidence(c) for c in result.citations],
        )


@router.post(
    "/api/sample/ask",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit_sample_ask), Depends(enforce_origin)],
)
def sample_ask(
    service: Annotated[GuestSampleAsk, Depends(get_guest_sample_ask)],
    response_language: Annotated[str | None, Depends(get_guest_response_language)],
    body: SampleAskRequest,
) -> SampleAskResponse:
    """Answer one guest question about the shared sample (200; 422/429/502/503).

    The question is trimmed and length-capped at this boundary before the
    service runs — an empty or oversized question costs nothing. The answer is
    requested in the visitor's negotiated language (cookie else
    ``Accept-Language`` else English); citations stay verbatim in the book's
    language, exactly like every Ask.
    """
    question = body.question.strip()
    max_chars = get_settings().guest_sample_question_max_chars
    if not question:
        raise ValidationError("Ask the sample a question first.")
    if len(question) > max_chars:
        raise ValidationError("That question is too long for the sample. Shorten it and try again.")
    result = service(question=question, response_language=response_language)
    return SampleAskResponse.from_guest_answer(result)
