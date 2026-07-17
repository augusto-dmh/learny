"""Source-storage use-case services (Cycle 2, design §Components).

Framework-free services orchestrating the source repository, the storage port,
and the Cycle-1 ownership primitive. Same layering as Identity (ADR-007/009):
nothing here imports FastAPI, SQLAlchemy, or boto3 — the web layer (Phase 3) maps
the errors raised here to HTTP responses.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from uuid import UUID

from app.application.errors import (
    NotAuthorized,
    SourceNotFound,
    StorageUnavailable,
)
from app.application.identity import AuthorizeOwnership
from app.application.validation import extension_of, validate_source_upload
from app.domain.entities import Source, User
from app.domain.ports import Clock, SourceRepository, StoragePort


class CreateSource:
    """Validate an upload, store its bytes, then persist an owned source row.

    Ordering is store-then-persist (design §Architecture): a failed ``put_object``
    leaves nothing (SRC-09), and validation runs first so no invalid upload ever
    reaches storage. ``max_bytes`` caps EPUB uploads and ``pdf_max_bytes`` caps PDF
    uploads (ING-09); when a PDF cap is not supplied it falls back to ``max_bytes``.
    """

    def __init__(
        self,
        *,
        sources: SourceRepository,
        storage: StoragePort,
        clock: Clock,
        ids: Callable[[], UUID],
        max_bytes: int,
        pdf_max_bytes: int | None = None,
    ) -> None:
        self._sources = sources
        self._storage = storage
        self._clock = clock
        self._ids = ids
        self._max_bytes = max_bytes
        self._pdf_max_bytes = max_bytes if pdf_max_bytes is None else pdf_max_bytes

    def __call__(
        self,
        *,
        user: User,
        title: str,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> Source:
        byte_size = len(data)
        validate_source_upload(
            title=title,
            filename=filename,
            content_type=content_type,
            byte_size=byte_size,
            max_bytes=self._max_bytes,
            pdf_max_bytes=self._pdf_max_bytes,
        )

        source_id = self._ids()
        # Opaque, owner-partitioned key — no email or title (SRC-06 / data
        # protection). The extension mirrors the validated format so downstream
        # parser dispatch and content-type inference stay consistent (ING-09).
        extension = extension_of(filename)
        object_key = f"sources/{user.id}/{source_id}{extension}"

        try:
            self._storage.put_object(object_key, data, content_type=content_type)
        except Exception as exc:
            # Any storage failure must leave no persisted row (SRC-09): map to a
            # Learny error and return before ``sources.add`` is ever called.
            raise StorageUnavailable("Could not store the uploaded file.") from exc

        now = self._clock.now()
        return self._sources.add(
            Source(
                id=source_id,
                user_id=user.id,
                title=title,
                filename=filename,
                content_type=content_type,
                byte_size=byte_size,
                checksum=hashlib.sha256(data).hexdigest(),
                object_key=object_key,
                status="uploaded",
                created_at=now,
                updated_at=now,
            )
        )


class ListSources:
    """Return the caller's sources, newest-first (delegates to the repository)."""

    def __init__(self, *, sources: SourceRepository) -> None:
        self._sources = sources

    def __call__(self, *, user: User) -> list[Source]:
        return self._sources.list_by_user(user.id)


class GetSource:
    """Return one owned source, or raise ``SourceNotFound`` (404, no disclosure)."""

    def __init__(
        self, *, sources: SourceRepository, authorize: AuthorizeOwnership
    ) -> None:
        self._sources = sources
        self._authorize = authorize

    def __call__(self, *, user: User, source_id: UUID) -> Source:
        source = self._sources.get_by_id(source_id)
        if source is None:
            raise SourceNotFound("Source not found.")
        try:
            self._authorize(user=user, owner_id=source.user_id)
        except NotAuthorized as exc:
            # Non-owners get 404, not 403, so a source's existence isn't disclosed.
            raise SourceNotFound("Source not found.") from exc
        return source
