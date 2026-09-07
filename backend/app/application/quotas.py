"""Library quotas (RFC-0007 Cycle F; design §Components, Quotas).

Framework-free per-user caps over the owned library: how many books a learner may
own, how many stored bytes, and how many ingestion jobs may be in flight at once.
The shared sample book is nobody's book — ``list_by_user`` returns it to every
caller, so the quota subtracts it back out — and it neither counts toward a quota
nor is blocked by one.

Both assertions run *before* anything is written: ``assert_upload`` before the
bytes are put to storage (a post-put rejection would orphan an object), and
``assert_ingest_start`` before a job row exists, keeping the persistence-layer
partial unique as the race backstop rather than the primary guard.
"""

from __future__ import annotations

from uuid import UUID

from app.application.errors import (
    ActiveIngestionExists,
    SourceCountQuotaExceeded,
    StoredBytesQuotaExceeded,
)
from app.domain.entities import User
from app.domain.ports import IngestionJobRepository, SourceRepository

#: The quota copies (design §Error Handling): honest about the limit and the way
#: out, without naming internal numbers a client could not act on anyway.
SOURCE_COUNT_COPY = "You've reached this library's book limit. Delete a book to upload another."
STORED_BYTES_COPY = (
    "This upload would exceed the library's storage limit. Try a smaller file or delete a book."
)
IN_FLIGHT_COPY = "You already have an ingestion in progress. Wait for it to finish."


class Quotas:
    """Assert owned-source count, stored-byte sum, and in-flight ingest caps.

    The owned set is the caller's sources minus the shared sample (DOOR-16), so a
    sample book never consumes a seat or a byte. The byte check is the stored
    ``byte_size`` sum **plus the new upload** against the cap (DOOR-17) — the same
    column the library already reads, no storage listing.
    """

    def __init__(
        self,
        *,
        sources: SourceRepository,
        jobs: IngestionJobRepository,
        max_sources: int,
        max_stored_bytes: int,
    ) -> None:
        self._sources = sources
        self._jobs = jobs
        self._max_sources = max_sources
        self._max_stored_bytes = max_stored_bytes

    def _owned(self, user_id: UUID):
        """The caller's non-sample sources — the only ones the quotas see."""
        return [s for s in self._sources.list_by_user(user_id) if not s.is_sample]

    def assert_upload(self, user: User, *, byte_size: int) -> None:
        """Refuse an upload that would breach the count or stored-byte cap."""
        owned = self._owned(user.id)
        if len(owned) >= self._max_sources:
            raise SourceCountQuotaExceeded(SOURCE_COUNT_COPY)
        if sum(s.byte_size for s in owned) + byte_size > self._max_stored_bytes:
            raise StoredBytesQuotaExceeded(STORED_BYTES_COPY)

    def assert_ingest_start(self, user: User) -> None:
        """Refuse a start while the caller already has a queued/running job (DOOR-18).

        The caller-scoped pre-check; the per-source partial unique index stays as
        the true-race backstop and still maps to the same 409.
        """
        if self._jobs.count_active_for_user(user.id) > 0:
            raise ActiveIngestionExists(IN_FLIGHT_COPY)
