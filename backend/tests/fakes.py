"""In-memory fake ports for unit-testing application services (task B4).

These satisfy the domain port Protocols structurally; no DB or hashing library
is involved, so service rules can be tested in isolation and deterministically.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from itertools import count
from uuid import UUID, uuid4

from app.domain.entities import (
    ACTIVE_STATUSES,
    ChunkToEmbed,
    CorpusSectionRecord,
    CorpusStructure,
    Evidence,
    IngestionEvent,
    IngestionJob,
    ParsedBook,
    PasswordCredential,
    Session,
    Source,
    StructureSection,
    User,
)


class FakeClock:
    def __init__(self, now: datetime | None = None) -> None:
        self._now = now or datetime(2026, 6, 27, 12, 0, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, delta) -> None:  # noqa: ANN001 — timedelta
        self._now = self._now + delta


class SequentialTokenGenerator:
    """Deterministic token source: ``token-1``, ``token-2``, ..."""

    def __init__(self) -> None:
        self._counter = count(1)

    def generate(self) -> str:
        return f"token-{next(self._counter)}"


class FakePasswordHasher:
    """Reversible 'hash' for tests: ``hash::<password>``; rehash flag toggleable."""

    def __init__(self, *, needs_rehash: bool = False) -> None:
        self._needs_rehash = needs_rehash

    def hash(self, password: str) -> str:
        return f"hash::{password}"

    def verify(self, password: str, encoded_hash: str) -> bool:
        return encoded_hash == f"hash::{password}"

    def needs_rehash(self, encoded_hash: str) -> bool:
        return self._needs_rehash

    def dummy_hash(self) -> str:
        # A hash in this fake's own ``hash::<x>`` format that no real password
        # produces, so ``verify`` does a genuine (failing) comparison.
        return "hash::__no_such_user__"


class FakeUserRepository:
    def __init__(self) -> None:
        self._by_id: dict[UUID, User] = {}

    def add(self, user: User) -> User:
        if any(u.email.lower() == user.email.lower() for u in self._by_id.values()):
            raise ValueError("duplicate email")
        self._by_id[user.id] = user
        return user

    def get_by_id(self, user_id: UUID) -> User | None:
        return self._by_id.get(user_id)

    def get_by_email(self, email: str) -> User | None:
        for user in self._by_id.values():
            if user.email.lower() == email.lower():
                return user
        return None


class FakeCredentialRepository:
    def __init__(self) -> None:
        self._by_user: dict[UUID, PasswordCredential] = {}

    def add(self, credential: PasswordCredential) -> PasswordCredential:
        self._by_user[credential.user_id] = credential
        return credential

    def get_by_user_id(self, user_id: UUID) -> PasswordCredential | None:
        return self._by_user.get(user_id)

    def update(self, credential: PasswordCredential) -> PasswordCredential:
        self._by_user[credential.user_id] = credential
        return credential


class FakeSessionRepository:
    def __init__(self) -> None:
        self._by_id: dict[UUID, Session] = {}
        self._hash_to_id: dict[str, UUID] = {}

    @staticmethod
    def _hash(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()

    def create(
        self, *, user_id: UUID, raw_token: str, csrf_token: str, expires_at: datetime
    ) -> Session:
        token_hash = self._hash(raw_token)
        if token_hash in self._hash_to_id:
            raise ValueError("duplicate token_hash")
        now = datetime(2026, 6, 27, 12, 0, 0, tzinfo=UTC)
        session = Session(
            id=uuid4(),
            user_id=user_id,
            token_hash=token_hash,
            csrf_token=csrf_token,
            expires_at=expires_at,
            created_at=now,
            last_seen_at=now,
        )
        self._by_id[session.id] = session
        self._hash_to_id[token_hash] = session.id
        return session

    def get_by_raw_token(self, raw_token: str) -> Session | None:
        session_id = self._hash_to_id.get(self._hash(raw_token))
        return self._by_id.get(session_id) if session_id else None

    def touch(self, session_id: UUID, last_seen_at: datetime) -> None:
        session = self._by_id.get(session_id)
        if session is not None:
            import dataclasses

            self._by_id[session_id] = dataclasses.replace(session, last_seen_at=last_seen_at)

    def delete(self, session_id: UUID) -> None:
        session = self._by_id.pop(session_id, None)
        if session is not None:
            self._hash_to_id.pop(session.token_hash, None)


class FakeSourceRepository:
    """In-memory ``SourceRepository``: newest-first list, unique ``object_key``."""

    def __init__(self) -> None:
        self._by_id: dict[UUID, Source] = {}
        self._object_keys: set[str] = set()
        self.add_calls = 0

    def add(self, source: Source) -> Source:
        self.add_calls += 1
        if source.object_key in self._object_keys:
            raise ValueError("duplicate object_key")
        self._object_keys.add(source.object_key)
        self._by_id[source.id] = source
        return source

    def list_by_user(self, user_id: UUID) -> list[Source]:
        owned = [s for s in self._by_id.values() if s.user_id == user_id]
        return sorted(owned, key=lambda s: s.created_at, reverse=True)

    def get_by_id(self, source_id: UUID) -> Source | None:
        return self._by_id.get(source_id)

    def set_status(self, source_id: UUID, status: str, updated_at: datetime) -> None:
        source = self._by_id.get(source_id)
        if source is not None:
            self._by_id[source_id] = replace(source, status=status, updated_at=updated_at)


class FakeStorage:
    """In-memory ``StoragePort``: records puts so tests can assert key/bytes."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.put_calls: list[tuple[str, str]] = []

    def put_object(self, key: str, data: bytes, *, content_type: str) -> None:
        self.put_calls.append((key, content_type))
        self.objects[key] = data

    def get_object(self, key: str) -> bytes:
        return self.objects[key]


class FailingStorage:
    """``StoragePort`` whose ``put_object`` always fails (storage-down path)."""

    def put_object(self, key: str, data: bytes, *, content_type: str) -> None:
        raise RuntimeError("storage down")

    def get_object(self, key: str) -> bytes:
        raise RuntimeError("storage down")


class FakeIngestionJobRepository:
    """In-memory ``IngestionJobRepository`` that emulates the active-job guard.

    ``add`` raises (like the partial unique index) when an active
    (``queued``/``running``) job already exists for the same source, so the
    persistence-layer invariant (ING-03) is modelled in unit tests. Insertion
    order breaks ``created_at`` ties so ``get_latest_for_source`` is deterministic
    under a fixed test clock.
    """

    def __init__(self) -> None:
        self._by_id: dict[UUID, IngestionJob] = {}
        self._order: list[UUID] = []
        self.add_calls = 0

    def add(self, job: IngestionJob) -> IngestionJob:
        self.add_calls += 1
        if any(
            j.source_id == job.source_id and j.status in ACTIVE_STATUSES
            for j in self._by_id.values()
        ):
            raise ValueError("active ingestion job already exists")
        self._by_id[job.id] = job
        self._order.append(job.id)
        return job

    def get_by_id(self, job_id: UUID) -> IngestionJob | None:
        return self._by_id.get(job_id)

    def get_latest_for_source(self, source_id: UUID) -> IngestionJob | None:
        for job_id in reversed(self._order):
            job = self._by_id[job_id]
            if job.source_id == source_id:
                return job
        return None

    def update(self, job: IngestionJob) -> IngestionJob:
        self._by_id[job.id] = job
        return job


class FakeIngestionEventRepository:
    """In-memory ``IngestionEventRepository``: append-only, chronological list."""

    def __init__(self) -> None:
        self._events: list[IngestionEvent] = []

    def append(self, event: IngestionEvent) -> IngestionEvent:
        self._events.append(event)
        return event

    def list_for_job(self, job_id: UUID) -> list[IngestionEvent]:
        return [e for e in self._events if e.job_id == job_id]


class FakeIngestionStep:
    """``IngestionStep`` double: no-op by default, or raises a configured error.

    Records its calls so tests can assert the source/job passed to the Phase-5
    seam; the ``error`` seam drives the retry/terminal branches.
    """

    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error
        self.calls: list[tuple[Source | None, IngestionJob]] = []

    def run(self, *, source: Source | None, job: IngestionJob) -> None:
        self.calls.append((source, job))
        if self._error is not None:
            raise self._error


class FakeIngestionEnqueuer:
    """``IngestionEnqueuer`` double: records enqueue calls, or raises if configured."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error
        self.calls: list[tuple[UUID, UUID]] = []

    def enqueue_ingestion(self, *, source_id: UUID, job_id: UUID) -> None:
        self.calls.append((source_id, job_id))
        if self._error is not None:
            raise self._error


class FakeEpubParser:
    """``EpubParserPort`` double: returns a preset ``ParsedBook`` or raises.

    Records the (bytes, filename) it was called with so ``BuildCorpus`` tests can
    assert the storage bytes flow through to the parser; the ``error`` seam drives
    the terminal-failure branch (a raise propagates unwrapped).
    """

    def __init__(self, *, book: ParsedBook | None = None, error: Exception | None = None) -> None:
        self._book = book
        self._error = error
        self.calls: list[tuple[bytes, str]] = []

    def parse(self, source_bytes: bytes, *, filename: str) -> ParsedBook:
        self.calls.append((source_bytes, filename))
        if self._error is not None:
            raise self._error
        assert self._book is not None
        return self._book


class FakeMarkupConverter:
    """``MarkupConverterPort`` double: a deterministic ``md:<html>`` rendering.

    The prefix makes each block's derived text traceable to its HTML fragment, so
    tests can assert the section Markdown is the join of the converter's per-block
    output and that chunks are packed from those block texts (not re-parsed).
    """

    def to_markdown(self, html: str) -> str:
        return f"md:{html}"


class FakeCorpusRepository:
    """In-memory ``CorpusRepository``: atomic replace by source_id, flat read.

    ``replace`` overwrites any existing corpus for the source (mirroring the
    delete-then-insert semantics), records each call's full aggregate so service
    tests can assert what was persisted (schema_version, per-section markdown and
    chunks, zero-block sections), and exposes the flat structure via
    ``get_structure``.
    """

    def __init__(self) -> None:
        self._by_source: dict[UUID, CorpusStructure] = {}
        self.replace_calls: list[dict[str, object]] = []

    def replace(
        self,
        source_id: UUID,
        *,
        title: str | None,
        authors: Sequence[str],
        language: str | None,
        schema_version: int,
        sections: Sequence[CorpusSectionRecord],
    ) -> None:
        self.replace_calls.append(
            {
                "source_id": source_id,
                "title": title,
                "authors": tuple(authors),
                "language": language,
                "schema_version": schema_version,
                "sections": tuple(sections),
            }
        )
        self._by_source[source_id] = CorpusStructure(
            title=title,
            authors=tuple(authors),
            language=language,
            sections=tuple(
                StructureSection(
                    position=record.section.position,
                    title=record.section.title,
                    depth=record.section.depth,
                    section_path=tuple(record.section.section_path),
                    anchor=record.section.anchor,
                )
                for record in sections
            ),
        )

    def get_structure(self, source_id: UUID) -> CorpusStructure | None:
        return self._by_source.get(source_id)


class FakeEmbeddingPort:
    """``EmbeddingPort`` double: records each ``embed_documents`` batch call.

    Returns a distinct 1-D vector per text — the running call index across all
    batches — so a test can assert both order preservation (vector value == the
    chunk's overall position) and correct chunk-id↔vector pairing, and can read
    ``document_batches`` to assert batch boundaries. No network, no provider SDK.
    """

    def __init__(self) -> None:
        self.document_batches: list[list[str]] = []
        self.query_calls: list[str] = []
        self._counter = 0

    def embed_query(self, text: str) -> list[float]:
        self.query_calls.append(text)
        return [0.0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.document_batches.append(list(texts))
        vectors: list[list[float]] = []
        for _ in texts:
            vectors.append([float(self._counter)])
            self._counter += 1
        return vectors


class FakeEmbeddingIndexRepository:
    """In-memory ``EmbeddingIndexRepository``: preset chunks, records writes.

    ``chunks_for_source`` returns the chunks seeded for a source (stably ordered
    as given); ``set_embeddings`` records each call's ordered ``(chunk_id, vector)``
    items and exposes the resulting ``persisted`` chunk_id→vector map so service
    tests assert the persisted pairs, not just call counts.
    """

    def __init__(self, chunks_by_source: dict[UUID, list[ChunkToEmbed]] | None = None) -> None:
        self._chunks: dict[UUID, list[ChunkToEmbed]] = chunks_by_source or {}
        self.set_calls: list[list[tuple[UUID, list[float]]]] = []
        self.persisted: dict[UUID, list[float]] = {}

    def chunks_for_source(self, source_id: UUID) -> list[ChunkToEmbed]:
        return list(self._chunks.get(source_id, []))

    def set_embeddings(self, items: Sequence[tuple[UUID, list[float]]]) -> None:
        recorded = [(chunk_id, vector) for chunk_id, vector in items]
        self.set_calls.append(recorded)
        for chunk_id, vector in recorded:
            self.persisted[chunk_id] = vector


class FakeRetrievalPort:
    """``RetrievalPort`` double: records each ``search`` call's kwargs, returns preset.

    Returns the exact preset ``results`` list object (not a copy) so a test can
    assert the service passes the port's return through unchanged, and records the
    full keyword arguments so tests assert the forwarded query vector and the
    settings-sourced limits/k/ef by value, not just that ``search`` was called.
    """

    def __init__(self, results: list[Evidence] | None = None) -> None:
        self.results: list[Evidence] = results if results is not None else []
        self.calls: list[dict[str, object]] = []

    def search(
        self,
        *,
        source_id: UUID,
        query_text: str,
        query_vec: list[float],
        top_k: int,
        semantic_limit: int,
        lexical_limit: int,
        rrf_k: int,
        ef_search: int,
    ) -> list[Evidence]:
        self.calls.append(
            {
                "source_id": source_id,
                "query_text": query_text,
                "query_vec": query_vec,
                "top_k": top_k,
                "semantic_limit": semantic_limit,
                "lexical_limit": lexical_limit,
                "rrf_k": rrf_k,
                "ef_search": ef_search,
            }
        )
        return self.results
