"""Retrieval router — owner-scoped hybrid retrieval over a source (Phase 6).

Thin FastAPI adapter over the framework-free ``RetrieveEvidence`` service
(assembled in ``dependencies``). A signed-in owner POSTs a query for one of their
sources and gets back the fused, citation-ready evidence list; the handler owns
input validation (422) and lets application errors propagate to the global
handlers (``SourceNotFound`` → 404), mirroring the structure endpoint.

Contract (also consumed by the Next.js proxy in Phase 7):
- ``POST /api/sources/{id}/retrieve`` → 200 evidence list; auth + CSRF/Origin.
  Body ``{query, top_k?}``: 422 on empty/whitespace ``query`` or ``top_k``
  outside ``1..LEARNY_RETRIEVAL_MAX_TOP_K``; 404 on missing/non-owned source;
  200 with an empty list when nothing matches.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator, model_serializer
from pydantic.functional_serializers import SerializerFunctionWrapHandler

from app.application.retrieval import RetrieveEvidence
from app.core.config import get_settings
from app.domain.entities import Evidence, User
from app.infrastructure.web.csrf import enforce_csrf, enforce_origin
from app.infrastructure.web.dependencies import (
    get_authenticated_user,
    get_retrieve_evidence,
)

router = APIRouter(prefix="/api/sources", tags=["retrieval"])


class RetrieveRequest(BaseModel):
    """Retrieval request body (A-7).

    ``query`` must be non-empty after stripping surrounding whitespace; ``top_k``,
    when supplied, must fall within ``1..LEARNY_RETRIEVAL_MAX_TOP_K``. Both bounds
    raise a Pydantic validation error → 422 before retrieval runs (the service
    assumes a validated query and never clamps ``top_k``). ``top_k`` omitted →
    the service falls back to ``LEARNY_RETRIEVAL_TOP_K``.
    """

    query: str = Field(min_length=1)
    top_k: int | None = None
    # Diagnostic endpoint: the note arms stay off unless a caller opts in (AD-147);
    # its existing behaviour is unchanged for a body that omits the flag (NL-04).
    include_notes: bool = False

    @field_validator("query")
    @classmethod
    def _query_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be empty or whitespace-only")
        return value

    @field_validator("top_k")
    @classmethod
    def _top_k_in_range(cls, value: int | None) -> int | None:
        if value is None:
            return value
        max_top_k = get_settings().retrieval_max_top_k
        if not (1 <= value <= max_top_k):
            raise ValueError(f"top_k must be between 1 and {max_top_k}")
        return value


class EvidenceView(BaseModel):
    """Public, citation-only view of one evidence item (RET-18, NL-03).

    Exposes only the citation anchors and score — never an internal storage field
    (``object_key``/``checksum``); ``Evidence`` carries none, keeping it that way.

    A note citation additionally carries ``origin='note'`` plus the note's identity
    (``note_id``/``note_title``) so the client renders it distinctly (NL-03). Those
    three fields are emitted **only** for note evidence: a book citation serializes
    to exactly the original seven keys (NL-03 book-citations-unchanged), so existing
    clients and the pinned wire contract see no change.
    """

    chunk_id: UUID
    source_id: UUID
    section_path: list[str]
    anchor: str
    page_span: dict | None
    snippet: str
    score: float
    origin: Literal["book", "note"] = "book"
    note_id: UUID | None = None
    note_title: str | None = None

    @model_serializer(mode="wrap")
    def _serialize(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        # The default handler serializes every field (respecting python/json mode);
        # for book evidence the note-only fields are dropped so the projection is
        # byte-identical to the pre-notes contract (NL-03).
        data = handler(self)
        if self.origin == "book":
            for key in ("origin", "note_id", "note_title"):
                data.pop(key, None)
        return data

    @classmethod
    def from_evidence(cls, evidence: Evidence) -> EvidenceView:
        return cls(
            chunk_id=evidence.chunk_id,
            source_id=evidence.source_id,
            section_path=list(evidence.section_path),
            anchor=evidence.anchor,
            page_span=evidence.page_span,
            snippet=evidence.snippet,
            score=evidence.score,
            origin=evidence.origin,
            note_id=evidence.note_id,
            note_title=evidence.note_title,
        )


class RetrieveResponse(BaseModel):
    """The fused evidence list for a retrieval query (empty when nothing matched)."""

    results: list[EvidenceView]


@router.post(
    "/{source_id}/retrieve",
    dependencies=[Depends(enforce_origin), Depends(enforce_csrf)],
)
def retrieve(
    source_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[RetrieveEvidence, Depends(get_retrieve_evidence)],
    body: RetrieveRequest,
) -> RetrieveResponse:
    """Return owner-scoped, citation-ready evidence (200); 422/404/403 per the ACs.

    ``RetrieveEvidence`` authorizes ownership (missing/non-owner → ``SourceNotFound``
    → 404 via the global handler), embeds the validated query, and runs the hybrid
    RRF search; an unmatched query yields ``results: []`` (200, not an error).
    """
    evidence = service(
        user=user,
        source_id=source_id,
        query=body.query,
        top_k=body.top_k,
        include_notes=body.include_notes,
    )
    return RetrieveResponse(results=[EvidenceView.from_evidence(e) for e in evidence])
