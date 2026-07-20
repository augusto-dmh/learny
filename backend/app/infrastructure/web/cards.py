"""Cards router — suggest, accept, and edit a card made at the passage (Cycle D).

Thin FastAPI adapter over the framework-free card services (assembled in
``dependencies``). A signed-in owner asks for card suggestions scoped to one of their
own highlights, accepts one of them, and later rewords it — the whole capture path
from a highlighted sentence to a scheduled card, without a page change.

Each route is one request-scoped transaction (like the notes paths), so no
commit-then-enqueue orchestration is needed: the suggestion call persists nothing at
all, and an accept writes its item plus that item's initial scheduling atomically.
The suggestion route makes the app's first *synchronous* generation call inside a
handler — deliberate (AD-134), because the student is waiting on the popover — and is
bounded by the 3-candidate cap and ``rate_limit_quiz``, the same limiter the whole-deck
path uses.

Application errors are translated to HTTP by the global handlers
(``SourceNotFound`` → 404, ``QuizItemNotFound`` → 404, ``StaleCaptureTarget`` → 409,
``InvalidCardText`` → 422, ``CardNotEditable`` → 409). Every ownership failure — a
missing anchor, an anchor on another source, another user's highlight or card —
collapses to the same 404 so nothing's existence is disclosed.

Contract (also consumed by the Next.js proxy):
- ``POST  /api/sources/{source_id}/cards/suggestions`` → 200 ephemeral candidates;
  auth + CSRF/Origin + limit.
- ``POST  /api/sources/{source_id}/cards`` → 201 created card, or 200 with the
  existing card on an idempotent re-accept; auth + CSRF/Origin + limit.
- ``PATCH /api/quiz-items/{item_id}`` → 200 rewritten card; auth + CSRF/Origin + limit.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from app.application.cards import AcceptCard, SuggestCards, UpdateCard
from app.domain.entities import QuizCandidate, QuizItem, User
from app.infrastructure.web.csrf import enforce_csrf, enforce_origin
from app.infrastructure.web.dependencies import (
    get_accept_card,
    get_authenticated_user,
    get_suggest_cards,
    get_update_card,
)
from app.infrastructure.web.rate_limit import rate_limit_quiz

router = APIRouter(tags=["cards"])


# --- Request bodies ------------------------------------------------------------


class SuggestCardsRequest(BaseModel):
    """Suggestion body (CAP-01): the highlight to generate candidates for."""

    note_anchor_id: UUID


class AcceptCardRequest(BaseModel):
    """Accept body (CAP-05/06): the originating highlight plus the chosen card's text.

    The text is whatever the student accepted — the generated candidate verbatim or
    their own edit of it. Generated text was already gated by the suggestion route, and
    edited text is author-owned and not re-gated (AD-138); both are still bounds-checked
    for emptiness and length by the use case (422).
    """

    note_anchor_id: UUID
    item_type: str
    question: str
    answer: str


class UpdateCardRequest(BaseModel):
    """Edit body (CAP-12): the card's new question and answer, nothing else.

    Scheduling and the review log are not addressable here by construction — an edit
    never costs the student their memory history.
    """

    question: str
    answer: str


# --- Response views ------------------------------------------------------------


class CardSuggestionView(BaseModel):
    """One ephemeral card candidate (CAP-01..04).

    Never persisted: it exists only in this response and in the client's component
    state until the student accepts it (AD-134). ``anchor_quote`` is the passage text
    the candidate was verified against, so the chip can show what it is grounded in.
    """

    item_type: str
    question: str
    answer: str
    anchor_quote: str

    @classmethod
    def from_candidate(cls, candidate: QuizCandidate) -> CardSuggestionView:
        return cls(
            item_type=candidate.item_type,
            question=candidate.question,
            answer=candidate.answer,
            anchor_quote=candidate.anchor_quote,
        )


class CardSuggestionsView(BaseModel):
    """The suggestion response: at most ``LEARNY_QUIZ_MAX_SUGGESTIONS`` candidates.

    An empty list is a normal outcome ("no cards for this passage"), not an error.
    """

    suggestions: list[CardSuggestionView]


class CardCitationView(BaseModel):
    """A card's citation snapshot, taken from the highlight it was accepted from."""

    section_path: list[str]
    anchor: str
    source_excerpt: str


class CardView(BaseModel):
    """A persisted card (CAP-05, CAP-10..12).

    ``id`` is the creation-minted stable identity a ``highlight`` card keeps across
    every later edit; ``note_anchor_id`` is the typed provenance back to the highlight,
    and it goes ``null`` when that highlight's note is deleted while the card itself
    survives on its own ``citation`` snapshot.
    """

    id: UUID
    source_id: UUID
    origin: str
    note_anchor_id: UUID | None
    item_type: str
    question: str
    answer: str
    citation: CardCitationView
    status: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_item(cls, item: QuizItem) -> CardView:
        return cls(
            id=item.id,
            source_id=item.source_id,
            origin=item.origin,
            note_anchor_id=item.note_anchor_id,
            item_type=item.item_type,
            question=item.question,
            answer=item.answer,
            citation=CardCitationView(
                section_path=list(item.section_path),
                anchor=item.anchor,
                source_excerpt=item.source_excerpt,
            ),
            status=item.status,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )


# --- Endpoints -----------------------------------------------------------------


@router.post(
    "/api/sources/{source_id}/cards/suggestions",
    dependencies=[
        Depends(rate_limit_quiz),
        Depends(enforce_origin),
        Depends(enforce_csrf),
    ],
)
def suggest_cards(
    source_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[SuggestCards, Depends(get_suggest_cards)],
    body: SuggestCardsRequest,
) -> CardSuggestionsView:
    """Return QC-passing card candidates for one owned highlight (200; 404/409).

    ``SuggestCards`` authorizes the source (missing/non-owner → ``SourceNotFound`` →
    404) and the anchor (missing, wrong source, or another user's → ``QuizItemNotFound``
    → 404), then generates against the anchor's section and drops every candidate that
    is not quoted verbatim from it. A section the highlight no longer binds to →
    ``StaleCaptureTarget`` → 409. Nothing is persisted on this path.
    """
    candidates = service(
        user=user, source_id=source_id, note_anchor_id=body.note_anchor_id
    )
    return CardSuggestionsView(
        suggestions=[CardSuggestionView.from_candidate(c) for c in candidates]
    )


@router.post(
    "/api/sources/{source_id}/cards",
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(rate_limit_quiz),
        Depends(enforce_origin),
        Depends(enforce_csrf),
    ],
)
def accept_card(
    source_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[AcceptCard, Depends(get_accept_card)],
    body: AcceptCardRequest,
    response: Response,
) -> CardView:
    """Persist the accepted card and schedule it due now (201; 200/404/409/422).

    ``AcceptCard`` authorizes source + anchor as the suggestion route does, rejects
    empty/over-long text and unknown item types (``InvalidCardText`` → 422), and mints
    the item with its initial FSRS state. Accepting the same text from the same
    highlight twice is idempotent: the second call returns the **existing** card with
    200 instead of 201, so a double submit cannot produce a duplicate.
    """
    item, created = service(
        user=user,
        source_id=source_id,
        note_anchor_id=body.note_anchor_id,
        item_type=body.item_type,
        question=body.question,
        answer=body.answer,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return CardView.from_item(item)


@router.patch(
    "/api/quiz-items/{item_id}",
    dependencies=[
        Depends(rate_limit_quiz),
        Depends(enforce_origin),
        Depends(enforce_csrf),
    ],
)
def update_card(
    item_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[UpdateCard, Depends(get_update_card)],
    body: UpdateCardRequest,
) -> CardView:
    """Rewrite an owned highlight card's text under its stable id (200; 404/409/422).

    ``UpdateCard`` collapses a missing card and a non-owner to ``QuizItemNotFound`` →
    404, refuses a ``deck``-origin card whose identity is its content hash
    (``CardNotEditable`` → 409), and rejects empty/over-long text (422). The row's id,
    its scheduling, and its review log are left untouched.
    """
    item = service(
        user=user, item_id=item_id, question=body.question, answer=body.answer
    )
    return CardView.from_item(item)
