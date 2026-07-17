"""Sources router — upload, list, and read owned EPUB sources (Cycle 2).

Thin FastAPI adapter over the framework-free source services (assembled in
``dependencies``). Handlers delegate to a use-case service and return a
secret-free ``SourceSummary``; application errors raised by the services are
translated to HTTP status codes by the global handlers in ``error_handlers``.

Contract (also consumed by the Next.js proxy in Phase 4):
- ``POST /api/sources``        → 201, multipart ``file`` + ``title``; auth + CSRF.
- ``GET  /api/sources``        → 200, owner-scoped list, newest-first (auth).
- ``GET  /api/sources/{id}``   → 200 owner; 404 cross-user/missing (auth).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from pydantic import BaseModel

from app.application.corpus import ReadSection, ReadSourceStructure
from app.application.errors import StorageUnavailable
from app.application.sources import CreateSource, GetSource, ListSources
from app.domain.entities import (
    CorpusStructure,
    SectionContent,
    Source,
    StructureSection,
    User,
)
from app.infrastructure.web.csrf import enforce_csrf, enforce_origin
from app.infrastructure.web.dependencies import (
    AppSettings,
    get_authenticated_user,
    get_create_source,
    get_get_source,
    get_list_sources,
    get_read_section,
    get_read_source_structure,
)
from app.infrastructure.web.rate_limit import rate_limit_upload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sources", tags=["sources"])


class SourceSummary(BaseModel):
    """Public, secret-free view of a source (safe to return/log).

    Deliberately omits ``object_key`` and ``checksum`` — those are internal
    storage/integrity details, never exposed to clients (spec P1-Upload AC1).
    """

    id: UUID
    title: str
    filename: str
    byte_size: int
    content_type: str
    status: str
    created_at: datetime

    @classmethod
    def from_entity(cls, source: Source) -> SourceSummary:
        return cls(
            id=source.id,
            title=source.title,
            filename=source.filename,
            byte_size=source.byte_size,
            content_type=source.content_type,
            status=source.status,
            created_at=source.created_at,
        )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(rate_limit_upload),
        Depends(enforce_origin),
        Depends(enforce_csrf),
    ],
)
def create_source(
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[CreateSource, Depends(get_create_source)],
    settings: AppSettings,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form()],
) -> SourceSummary:
    """Store an uploaded EPUB or PDF and persist an owned source row (201 + summary).

    The read is bounded to ``max(epub_max_bytes, pdf_max_bytes) + 1`` so an oversize
    upload is detected (→ 413) without buffering more than the largest cap in the
    request worker; validation then enforces the exact per-format cap.
    """
    read_bound = max(settings.epub_max_bytes, settings.pdf_max_bytes) + 1
    data = file.file.read(read_bound)
    try:
        source = service(
            user=user,
            title=title,
            filename=file.filename or "",
            content_type=file.content_type or "",
            data=data,
        )
    except StorageUnavailable:
        # SRC-10: record the failure with the owner id only — no secrets, and no
        # row was persisted (the service raised before ``sources.add``).
        logger.warning("source upload storage failure", extra={"user_id": str(user.id)})
        raise
    logger.info(
        "source created", extra={"user_id": str(user.id), "source_id": str(source.id)}
    )
    return SourceSummary.from_entity(source)


@router.get("")
def list_sources(
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[ListSources, Depends(get_list_sources)],
) -> list[SourceSummary]:
    """Return the caller's sources, newest-first (200; 401 if unauthenticated)."""
    return [SourceSummary.from_entity(s) for s in service(user=user)]


@router.get("/{source_id}")
def get_source(
    source_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[GetSource, Depends(get_get_source)],
) -> SourceSummary:
    """Return one owned source (200); 404 if missing or owned by another user."""
    return SourceSummary.from_entity(service(user=user, source_id=source_id))


class StructureSectionView(BaseModel):
    """One node in the nested section tree (CORP-11).

    ``children`` holds the sections nested beneath this one per the TOC hierarchy;
    the tree is built in this web layer from the flat depth-ordered read model, so
    the domain and repository stay flat (design §Tech Decisions).
    """

    title: str
    depth: int
    section_path: list[str]
    anchor: str
    children: list[StructureSectionView]


class BookStructureView(BaseModel):
    """Public view of a source's parsed book structure (CORP-11).

    Book metadata plus the nested section tree. ``title``/``language`` are null and
    ``authors`` empty when the OPF omitted them (CORP-01).
    """

    title: str | None
    authors: list[str]
    language: str | None
    sections: list[StructureSectionView]

    @classmethod
    def from_structure(cls, structure: CorpusStructure) -> BookStructureView:
        return cls(
            title=structure.title,
            authors=list(structure.authors),
            language=structure.language,
            sections=_nest_sections(structure.sections),
        )


def _nest_sections(sections: Sequence[StructureSection]) -> list[StructureSectionView]:
    """Fold the flat, depth/position-ordered sections into a TOC tree.

    Each section nests under the most recent preceding section with a smaller
    depth (its parent); sections with no such ancestor are roots.
    """
    roots: list[StructureSectionView] = []
    stack: list[StructureSectionView] = []
    for section in sections:
        node = StructureSectionView(
            title=section.title,
            depth=section.depth,
            section_path=list(section.section_path),
            anchor=section.anchor,
            children=[],
        )
        while stack and stack[-1].depth >= section.depth:
            stack.pop()
        if stack:
            stack[-1].children.append(node)
        else:
            roots.append(node)
        stack.append(node)
    return roots


@router.get("/{source_id}/structure")
def get_source_structure(
    source_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[ReadSourceStructure, Depends(get_read_source_structure)],
) -> BookStructureView:
    """Return the owner's parsed book structure (200); 404 missing/non-owner/no-corpus."""
    return BookStructureView.from_structure(service(user=user, source_id=source_id))


class SectionContentView(BaseModel):
    """Public view of one section's readable content (FE-14).

    ``anchor`` echoes the requested location so a citation round-trips to exactly
    this section; ``section_path`` is the root-to-node breadcrumb and ``markdown``
    is the section's derived text for the reader.
    """

    anchor: str
    title: str
    section_path: list[str]
    markdown: str

    @classmethod
    def from_content(cls, section: SectionContent) -> SectionContentView:
        return cls(
            anchor=section.anchor,
            title=section.title,
            section_path=list(section.section_path),
            markdown=section.markdown,
        )


@router.get("/{source_id}/section")
def get_source_section(
    source_id: UUID,
    anchor: Annotated[str, Query(min_length=1)],
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[ReadSection, Depends(get_read_section)],
) -> SectionContentView:
    """Return one owned section by anchor (200); 404 missing/non-owner/no-corpus/unknown-anchor."""
    return SectionContentView.from_content(
        service(user=user, source_id=source_id, anchor=anchor)
    )
