"""In-memory fake ports for unit-testing application services (task B4).

These satisfy the domain port Protocols structurally; no DB or hashing library
is involved, so service rules can be tested in isolation and deterministically.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from itertools import count
from uuid import UUID, uuid4

from app.domain.entities import (
    ACTIVE_STATUSES,
    AnchorSection,
    AnswerCompleted,
    AnswerStreamEvent,
    AnswerTextDelta,
    Backlink,
    ChapterIndexRow,
    ChapterSection,
    ChunkToEmbed,
    CorpusSectionRecord,
    CorpusStructure,
    DerivedNoteLink,
    Evidence,
    GeneratedAnswer,
    IngestionEvent,
    IngestionJob,
    Note,
    NoteAnchor,
    NoteAnchorStatus,
    NoteSummary,
    ParsedBook,
    PasswordCredential,
    ReadingPosition,
    SectionContent,
    Session,
    Source,
    SourceHighlight,
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
        self.calls: list[tuple[UUID, UUID, str]] = []

    def enqueue_ingestion(
        self, *, source_id: UUID, job_id: UUID, content_type: str
    ) -> None:
        self.calls.append((source_id, job_id, content_type))
        if self._error is not None:
            raise self._error


class FakeQuizDeckEnqueuer:
    """``QuizDeckEnqueuer`` double: records enqueue calls, or raises if configured."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error
        self.calls: list[tuple[UUID, UUID]] = []

    def enqueue_quiz_deck(self, *, source_id: UUID, job_id: UUID) -> None:
        self.calls.append((source_id, job_id))
        if self._error is not None:
            raise self._error


class FakeNoteIndexEnqueuer:
    """``NoteIndexEnqueuer`` double: records the note ids embed/refresh were asked for."""

    def __init__(self) -> None:
        self.embed_calls: list[UUID] = []
        self.refresh_calls: list[UUID] = []

    def enqueue_embed(self, note_id: UUID) -> None:
        self.embed_calls.append(note_id)

    def enqueue_refresh_cards(self, note_id: UUID) -> None:
        self.refresh_calls.append(note_id)


class FakeEpubParser:
    """``DocumentParserPort`` double: returns a preset ``ParsedBook`` or raises.

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
        self._sections_by_source: dict[UUID, tuple[SectionContent, ...]] = {}
        self._records_by_source: dict[UUID, tuple[CorpusSectionRecord, ...]] = {}
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
        self._sections_by_source[source_id] = tuple(
            SectionContent(
                anchor=record.section.anchor,
                title=record.section.title,
                section_path=tuple(record.section.section_path),
                markdown=record.markdown,
            )
            for record in sections
        )
        self._records_by_source[source_id] = tuple(sections)

    def get_structure(self, source_id: UUID) -> CorpusStructure | None:
        return self._by_source.get(source_id)

    def get_section(self, source_id: UUID, anchor: str) -> SectionContent | None:
        sections = self._sections_by_source.get(source_id, ())
        return next((s for s in sections if s.anchor == anchor), None)

    def get_chapter_index(self, source_id: UUID) -> tuple[ChapterIndexRow, ...] | None:
        if source_id not in self._records_by_source:
            return None
        records = sorted(
            self._records_by_source[source_id], key=lambda r: r.section.position
        )
        return tuple(
            ChapterIndexRow(
                position=record.section.position,
                depth=record.section.depth,
                title=record.section.title,
                section_path=tuple(record.section.section_path),
                anchor=record.section.anchor,
                anchor_aliases=tuple(record.section.anchor_aliases),
                word_count=record.word_count,
            )
            for record in records
        )

    def get_sections_span(
        self, source_id: UUID, first_position: int, last_position: int
    ) -> tuple[ChapterSection, ...]:
        records = sorted(
            self._records_by_source.get(source_id, ()), key=lambda r: r.section.position
        )
        return tuple(
            ChapterSection(
                anchor=record.section.anchor,
                title=record.section.title,
                section_path=tuple(record.section.section_path),
                markdown=record.markdown,
                word_count=record.word_count,
            )
            for record in records
            if first_position <= record.section.position <= last_position
        )


class FakeEmbeddingPort:
    """``EmbeddingPort`` double: records each ``embed_documents`` batch call.

    Returns a distinct 1-D vector per text — the running call index across all
    batches — so a test can assert both order preservation (vector value == the
    chunk's overall position) and correct chunk-id↔vector pairing, and can read
    ``document_batches`` to assert batch boundaries. No network, no provider SDK.
    """

    model = "fake-embedding@1"

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
        self.set_models: list[str] = []
        self.persisted: dict[UUID, list[float]] = {}

    def chunks_for_source(self, source_id: UUID) -> list[ChunkToEmbed]:
        return list(self._chunks.get(source_id, []))

    def set_embeddings(
        self, items: Sequence[tuple[UUID, list[float]]], *, model: str
    ) -> None:
        recorded = [(chunk_id, vector) for chunk_id, vector in items]
        self.set_calls.append(recorded)
        self.set_models.append(model)
        for chunk_id, vector in recorded:
            self.persisted[chunk_id] = vector


class FakeRetrieveEvidence:
    """``RetrieveEvidence`` double: records calls, returns preset evidence or raises.

    Lets ``AskQuestion`` tests assert the readiness/ownership guards short-circuit
    before retrieval (``calls == []``) and that the trimmed question plus the
    settings-sourced ``top_k`` reach retrieval, without wiring the real
    embedding/retrieval ports.
    """

    def __init__(
        self, results: list[Evidence] | None = None, *, error: Exception | None = None
    ) -> None:
        self.results: list[Evidence] = results if results is not None else []
        self._error = error
        self.calls: list[dict[str, object]] = []

    def __call__(
        self, *, user: User, source_id: UUID, query: str, top_k: int | None = None
    ) -> list[Evidence]:
        self.calls.append(
            {"user": user, "source_id": source_id, "query": query, "top_k": top_k}
        )
        if self._error is not None:
            raise self._error
        return self.results


class FakeAnswerGeneration:
    """``AnswerGenerationPort`` double: returns a preset answer or raises.

    Records each ``generate`` / ``generate_stream`` call so tests assert the port
    was (not) invoked and that the trimmed question plus the retrieved evidence
    reached it. ``model`` is the stable adapter identity the service reads on the
    not-found-on-empty path (where the port is deliberately not called).

    ``generate_stream`` yields the text deltas (``deltas`` when given, else the
    preset answer's text as one delta) then exactly one ``AnswerCompleted``; a
    configured ``error`` raises on first iteration (a provider failure surfacing
    during the stream). Its ``try/finally`` sets ``stream_closed`` so cancellation
    (consumer ``close()``) is observable.
    """

    def __init__(
        self,
        *,
        answer: GeneratedAnswer | None = None,
        error: Exception | None = None,
        deltas: Sequence[str] | None = None,
        model: str = "local-extractive",
    ) -> None:
        self._answer = answer
        self._error = error
        self._deltas = deltas
        self.model = model
        self.calls: list[dict[str, object]] = []
        self.stream_calls: list[dict[str, object]] = []
        self.stream_closed = False

    def generate(
        self, *, question: str, evidence: Sequence[Evidence]
    ) -> GeneratedAnswer:
        self.calls.append({"question": question, "evidence": list(evidence)})
        if self._error is not None:
            raise self._error
        assert self._answer is not None, "no preset answer configured"
        return self._answer

    def generate_stream(
        self, *, question: str, evidence: Sequence[Evidence]
    ) -> Iterator[AnswerStreamEvent]:
        self.stream_calls.append({"question": question, "evidence": list(evidence)})
        if self._error is not None:
            raise self._error
        assert self._answer is not None, "no preset answer configured"
        texts = (
            list(self._deltas)
            if self._deltas is not None
            else ([self._answer.text] if self._answer.text else [])
        )
        try:
            for text in texts:
                yield AnswerTextDelta(text=text)
            yield AnswerCompleted(answer=self._answer)
        finally:
            self.stream_closed = True


class IdentityMarkupConverter:
    """``MarkupConverterPort`` double whose Markdown is the fragment verbatim.

    The anchoring use cases derive block text through this port; returning the fragment
    unchanged lets a test set a block's text directly and assert offsets against it.
    """

    def to_markdown(self, html: str) -> str:
        return html


class FakeAnchorCorpus:
    """``CorpusRepository`` double for the anchoring read paths (NF-06/07).

    Seeded with a source's :class:`AnchorSection` list; only the two block-level reads
    the notes use cases call are implemented. ``blocks_for_section`` resolves canonical
    anchors first, then aliases, mirroring the real repository.
    """

    def __init__(
        self, sections_by_source: dict[UUID, list[AnchorSection]] | None = None
    ) -> None:
        self._by_source: dict[UUID, list[AnchorSection]] = sections_by_source or {}

    def set_sections(self, source_id: UUID, sections: list[AnchorSection]) -> None:
        self._by_source[source_id] = sections

    def blocks_for_section(self, source_id: UUID, anchor: str) -> AnchorSection | None:
        sections = self._by_source.get(source_id, [])
        for section in sections:
            if section.anchor == anchor:
                return section
        for section in sections:
            if anchor in section.anchor_aliases:
                return section
        return None

    def blocks_for_reconcile(self, source_id: UUID) -> list[AnchorSection]:
        return list(self._by_source.get(source_id, []))


class FakeNoteRepository:
    """In-memory ``NoteRepository`` for unit-testing the notes use cases (NF-04..08).

    Models owner-agnostic persistence (the service authorizes) plus the derived-index
    rewrites and per-user tag identity. ``resolve_titles`` returns the earliest-created
    note per lowercased title, and reconciliation writes touch only the anchor payload
    and status — never a note's body.
    """

    def __init__(self) -> None:
        self._notes: dict[UUID, Note] = {}
        self._tags_by_note: dict[UUID, list[str]] = {}
        self._links_by_note: dict[UUID, list[DerivedNoteLink]] = {}
        self._anchors: dict[UUID, NoteAnchor] = {}
        # Anchor ids passed to update_anchor_reconciliation, so a reconcile test can
        # assert the write-only-on-change discipline (an unchanged anchor is skipped).
        self.reconciliation_writes: list[UUID] = []

    def add(self, note: Note) -> Note:
        self._notes[note.id] = note
        return note

    def get_by_id(self, note_id: UUID) -> Note | None:
        return self._notes.get(note_id)

    def update(
        self, note_id: UUID, *, title: str, body_markdown: str, updated_at: datetime
    ) -> None:
        note = self._notes[note_id]
        self._notes[note_id] = replace(
            note, title=title, body_markdown=body_markdown, updated_at=updated_at
        )

    def delete(self, note_id: UUID) -> None:
        self._notes.pop(note_id, None)
        self._tags_by_note.pop(note_id, None)
        self._links_by_note.pop(note_id, None)
        for anchor_id, anchor in list(self._anchors.items()):
            if anchor.note_id == note_id:
                del self._anchors[anchor_id]
        # Inbound links to the deleted note lose their resolved target (SET NULL).
        for source_note_id, links in self._links_by_note.items():
            self._links_by_note[source_note_id] = [
                replace(link, target_note_id=None)
                if link.target_note_id == note_id
                else link
                for link in links
            ]

    def list_summaries(
        self, user_id: UUID, *, tag: str | None = None
    ) -> list[NoteSummary]:
        owned = [n for n in self._notes.values() if n.user_id == user_id]
        if tag is not None:
            owned = [n for n in owned if tag in self._tags_by_note.get(n.id, [])]
        owned.sort(key=lambda n: (n.updated_at, str(n.id)), reverse=True)
        return [
            NoteSummary(
                note=note,
                tags=tuple(sorted(self._tags_by_note.get(note.id, []))),
                anchor_statuses=tuple(
                    a.status for a in self._anchors.values() if a.note_id == note.id
                ),
            )
            for note in owned
        ]

    def tags_for_note(self, note_id: UUID) -> list[str]:
        return sorted(self._tags_by_note.get(note_id, []))

    def anchors_for_note(self, note_id: UUID) -> list[NoteAnchor]:
        return sorted(
            (a for a in self._anchors.values() if a.note_id == note_id),
            key=lambda a: (a.created_at, str(a.id)),
        )

    def backlinks(self, note_id: UUID) -> list[Backlink]:
        seen: set[UUID] = set()
        result: list[Backlink] = []
        for source_note_id, links in self._links_by_note.items():
            if source_note_id in seen:
                continue
            if any(link.target_note_id == note_id for link in links):
                seen.add(source_note_id)
                note = self._notes.get(source_note_id)
                if note is not None:
                    result.append(Backlink(note_id=note.id, title=note.title))
        result.sort(key=lambda b: str(b.note_id))
        return result

    def resolve_titles(
        self, user_id: UUID, titles: Sequence[str]
    ) -> dict[str, UUID]:
        wanted = {t.lower() for t in titles}
        candidates = sorted(
            (
                n
                for n in self._notes.values()
                if n.user_id == user_id and n.title.lower() in wanted
            ),
            key=lambda n: (n.created_at, str(n.id)),
        )
        resolved: dict[str, UUID] = {}
        for note in candidates:
            resolved.setdefault(note.title.lower(), note.id)
        return resolved

    def set_tags(self, note_id: UUID, user_id: UUID, names: Sequence[str]) -> None:
        self._tags_by_note[note_id] = list(names)

    def set_links(self, note_id: UUID, links: Sequence[DerivedNoteLink]) -> None:
        self._links_by_note[note_id] = list(links)

    def links_for_note(self, note_id: UUID) -> list[DerivedNoteLink]:
        """Test-only accessor for the derived links written for a note."""
        return list(self._links_by_note.get(note_id, []))

    def add_anchor(self, anchor: NoteAnchor) -> NoteAnchor:
        self._anchors[anchor.id] = anchor
        return anchor

    def get_anchor(self, anchor_id: UUID) -> NoteAnchor | None:
        return self._anchors.get(anchor_id)

    def anchors_for_source(self, source_id: UUID) -> list[NoteAnchor]:
        return sorted(
            (a for a in self._anchors.values() if a.source_id == source_id),
            key=lambda a: (a.created_at, str(a.id)),
        )

    def highlights_for_source(
        self, user_id: UUID, source_id: UUID
    ) -> tuple[SourceHighlight, ...]:
        anchors = sorted(
            (a for a in self._anchors.values() if a.source_id == source_id),
            key=lambda a: (a.created_at, str(a.id)),
        )
        return tuple(
            SourceHighlight(
                note_id=anchor.note_id,
                anchor=anchor.anchor,
                quote_exact=anchor.quote_exact,
                quote_prefix=anchor.quote_prefix,
                quote_suffix=anchor.quote_suffix,
                status=anchor.status,
            )
            for anchor in anchors
            if (note := self._notes.get(anchor.note_id)) is not None
            and note.user_id == user_id
        )

    def update_anchor_reconciliation(
        self,
        anchor_id: UUID,
        *,
        anchor: str,
        section_path: Sequence[str],
        block_hash: str | None,
        block_ordinal: int | None,
        start_offset: int | None,
        end_offset: int | None,
        status: str,
    ) -> None:
        self.reconciliation_writes.append(anchor_id)
        existing = self._anchors[anchor_id]
        self._anchors[anchor_id] = replace(
            existing,
            anchor=anchor,
            section_path=tuple(section_path),
            block_hash=block_hash,
            block_ordinal=block_ordinal,
            start_offset=start_offset,
            end_offset=end_offset,
            status=status,
        )

    def orphan_anchors_for_source(self, source_id: UUID) -> None:
        for anchor_id, anchor in list(self._anchors.items()):
            if (
                anchor.source_id == source_id
                and anchor.status != NoteAnchorStatus.ORPHANED
            ):
                self._anchors[anchor_id] = replace(
                    anchor, status=NoteAnchorStatus.ORPHANED
                )


class FakeReadingPositionRepository:
    """In-memory ``ReadingPositionRepository``: last-write-wins on (user, source).

    ``upsert`` overwrites any stored position for the ``(user_id, source_id)`` key and
    records each call so a test can assert nothing was written on the 404 path.
    """

    def __init__(self) -> None:
        self._by_key: dict[tuple[UUID, UUID], ReadingPosition] = {}
        self.upsert_calls: list[tuple[UUID, UUID]] = []

    def get(self, user_id: UUID, source_id: UUID) -> ReadingPosition | None:
        return self._by_key.get((user_id, source_id))

    def upsert(
        self,
        user_id: UUID,
        source_id: UUID,
        *,
        anchor: str,
        percent,  # noqa: ANN001 — Decimal
        updated_at: datetime,
    ) -> ReadingPosition:
        self.upsert_calls.append((user_id, source_id))
        stored = ReadingPosition(anchor=anchor, percent=percent, updated_at=updated_at)
        self._by_key[(user_id, source_id)] = stored
        return stored


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
        anchors: Sequence[str] | None = None,
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
                "anchors": anchors,
            }
        )
        return self.results
