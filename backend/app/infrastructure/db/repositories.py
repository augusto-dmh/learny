"""PostgreSQL repository adapters for the Identity module (task B3).

SQLAlchemy 2.x Core adapters implementing the domain repository ports against
the shared table metadata (``app.infrastructure.db.metadata``). Each repository
operates on a caller-provided ``Connection`` so the transaction boundary lives
at the composition root (Phase C), not inside the adapter.

Mapping notes:
- ``User`` ↔ ``users``; email is ``citext`` (case-insensitive unique).
- ``PasswordCredential`` ↔ ``user_credentials`` (one row per user, pk = user_id).
- ``Session`` ↔ ``sessions``: the adapter hashes the raw opaque token and
  persists only ``token_hash`` (design §4); lookup is by hashing the presented
  raw token and matching the unique ``token_hash``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Connection, bindparam, func, insert, select, update
from sqlalchemy import delete as sa_delete
from sqlalchemy.exc import IntegrityError

from app.application.errors import TeachingTurnConflict
from app.domain.entities import (
    ChunkToEmbed,
    CorpusSectionRecord,
    CorpusStructure,
    Evidence,
    HistoryTurn,
    IngestionEvent,
    IngestionJob,
    PasswordCredential,
    Session,
    Source,
    StructureSection,
    TeachingSession,
    TeachingSessionSummary,
    TeachingTurn,
    User,
)
from app.infrastructure.db.metadata import (
    corpus_blocks,
    corpus_chunks,
    corpus_documents,
    corpus_sections,
    ingestion_events,
    ingestion_jobs,
    sessions,
    sources,
    teaching_sessions,
    teaching_turn_citations,
    teaching_turns,
    user_credentials,
    users,
)
from app.infrastructure.security.tokens import hash_token


class SqlAlchemyUserRepository:
    """``UserRepository`` backed by the ``users`` table."""

    def __init__(self, connection: Connection) -> None:
        self._conn = connection

    def add(self, user: User) -> User:
        """Insert a user. Propagates ``IntegrityError`` on duplicate email."""
        self._conn.execute(
            insert(users).values(
                id=user.id,
                email=user.email,
                created_at=user.created_at,
            )
        )
        return user

    def get_by_id(self, user_id: UUID) -> User | None:
        row = self._conn.execute(
            select(users).where(users.c.id == user_id)
        ).one_or_none()
        return _to_user(row) if row is not None else None

    def get_by_email(self, email: str) -> User | None:
        # citext makes this comparison case-insensitive at the DB level.
        row = self._conn.execute(
            select(users).where(users.c.email == email)
        ).one_or_none()
        return _to_user(row) if row is not None else None


class SqlAlchemyCredentialRepository:
    """``CredentialRepository`` backed by the ``user_credentials`` table."""

    def __init__(self, connection: Connection) -> None:
        self._conn = connection

    def add(self, credential: PasswordCredential) -> PasswordCredential:
        self._conn.execute(
            insert(user_credentials).values(
                user_id=credential.user_id,
                password_hash=credential.password_hash,
                algo_params=credential.algo_params,
                updated_at=credential.updated_at,
            )
        )
        return credential

    def get_by_user_id(self, user_id: UUID) -> PasswordCredential | None:
        row = self._conn.execute(
            select(user_credentials).where(user_credentials.c.user_id == user_id)
        ).one_or_none()
        return _to_credential(row) if row is not None else None

    def update(self, credential: PasswordCredential) -> PasswordCredential:
        self._conn.execute(
            update(user_credentials)
            .where(user_credentials.c.user_id == credential.user_id)
            .values(
                password_hash=credential.password_hash,
                algo_params=credential.algo_params,
                updated_at=credential.updated_at,
            )
        )
        return credential


class SqlAlchemySessionRepository:
    """``SessionRepository`` backed by the ``sessions`` table.

    Stores only ``token_hash`` (SHA-256 of the raw opaque token). The raw token
    is never persisted; it is returned to the caller once at creation time.
    """

    def __init__(self, connection: Connection) -> None:
        self._conn = connection

    def create(
        self,
        *,
        user_id: UUID,
        raw_token: str,
        csrf_token: str,
        expires_at: datetime,
    ) -> Session:
        session_id = uuid4()
        token_hash = hash_token(raw_token)
        row = self._conn.execute(
            insert(sessions)
            .values(
                id=session_id,
                user_id=user_id,
                token_hash=token_hash,
                csrf_token=csrf_token,
                expires_at=expires_at,
            )
            .returning(sessions)
        ).one()
        return _to_session(row)

    def get_by_raw_token(self, raw_token: str) -> Session | None:
        row = self._conn.execute(
            select(sessions).where(sessions.c.token_hash == hash_token(raw_token))
        ).one_or_none()
        return _to_session(row) if row is not None else None

    def touch(self, session_id: UUID, last_seen_at: datetime) -> None:
        self._conn.execute(
            update(sessions)
            .where(sessions.c.id == session_id)
            .values(last_seen_at=last_seen_at)
        )

    def delete(self, session_id: UUID) -> None:
        self._conn.execute(sa_delete(sessions).where(sessions.c.id == session_id))


class SqlAlchemySourceRepository:
    """``SourceRepository`` backed by the ``sources`` table.

    Owner-scoped: ``list_by_user`` filters on ``user_id`` and returns newest
    first. The unique ``object_key`` constraint propagates as ``IntegrityError``.
    """

    def __init__(self, connection: Connection) -> None:
        self._conn = connection

    def add(self, source: Source) -> Source:
        """Insert a source. Propagates ``IntegrityError`` on duplicate object_key."""
        self._conn.execute(
            insert(sources).values(
                id=source.id,
                user_id=source.user_id,
                title=source.title,
                filename=source.filename,
                content_type=source.content_type,
                byte_size=source.byte_size,
                checksum=source.checksum,
                object_key=source.object_key,
                status=source.status,
                created_at=source.created_at,
                updated_at=source.updated_at,
            )
        )
        return source

    def list_by_user(self, user_id: UUID) -> list[Source]:
        rows = self._conn.execute(
            select(sources)
            .where(sources.c.user_id == user_id)
            .order_by(sources.c.created_at.desc())
        ).all()
        return [_to_source(row) for row in rows]

    def get_by_id(self, source_id: UUID) -> Source | None:
        row = self._conn.execute(
            select(sources).where(sources.c.id == source_id)
        ).one_or_none()
        return _to_source(row) if row is not None else None

    def set_status(self, source_id: UUID, status: str, updated_at: datetime) -> None:
        """Update the ``source.status`` projection alongside a job transition."""
        self._conn.execute(
            update(sources)
            .where(sources.c.id == source_id)
            .values(status=status, updated_at=updated_at)
        )


class SqlAlchemyIngestionJobRepository:
    """``IngestionJobRepository`` backed by the ``ingestion_jobs`` table.

    ``add`` propagates ``IntegrityError`` when a second active (``queued``/
    ``running``) job for the same source hits the partial unique index — the
    race-proof concurrency guard (ING-03).
    """

    def __init__(self, connection: Connection) -> None:
        self._conn = connection

    def add(self, job: IngestionJob) -> IngestionJob:
        """Insert a job. Propagates ``IntegrityError`` on the active guard (ING-03)."""
        self._conn.execute(
            insert(ingestion_jobs).values(
                id=job.id,
                source_id=job.source_id,
                status=job.status,
                attempts=job.attempts,
                last_error=job.last_error,
                created_at=job.created_at,
                updated_at=job.updated_at,
            )
        )
        return job

    def get_by_id(self, job_id: UUID) -> IngestionJob | None:
        row = self._conn.execute(
            select(ingestion_jobs).where(ingestion_jobs.c.id == job_id)
        ).one_or_none()
        return _to_ingestion_job(row) if row is not None else None

    def get_latest_for_source(self, source_id: UUID) -> IngestionJob | None:
        row = self._conn.execute(
            select(ingestion_jobs)
            .where(ingestion_jobs.c.source_id == source_id)
            .order_by(ingestion_jobs.c.created_at.desc())
            .limit(1)
        ).one_or_none()
        return _to_ingestion_job(row) if row is not None else None

    def update(self, job: IngestionJob) -> IngestionJob:
        """Persist ``status``/``attempts``/``last_error``/``updated_at``."""
        self._conn.execute(
            update(ingestion_jobs)
            .where(ingestion_jobs.c.id == job.id)
            .values(
                status=job.status,
                attempts=job.attempts,
                last_error=job.last_error,
                updated_at=job.updated_at,
            )
        )
        return job


class SqlAlchemyIngestionEventRepository:
    """``IngestionEventRepository`` backed by the ``ingestion_events`` table."""

    def __init__(self, connection: Connection) -> None:
        self._conn = connection

    def append(self, event: IngestionEvent) -> IngestionEvent:
        self._conn.execute(
            insert(ingestion_events).values(
                id=event.id,
                job_id=event.job_id,
                type=event.type,
                message=event.message,
                created_at=event.created_at,
            )
        )
        return event

    def list_for_job(self, job_id: UUID) -> list[IngestionEvent]:
        rows = self._conn.execute(
            select(ingestion_events)
            .where(ingestion_events.c.job_id == job_id)
            .order_by(ingestion_events.c.created_at)
        ).all()
        return [_to_ingestion_event(row) for row in rows]


class SqlAlchemyCorpusRepository:
    """``CorpusRepository`` backed by the corpus_* tables (ADR-0002).

    ``replace`` is delete-then-insert inside the caller's transaction: deleting the
    source's ``corpus_documents`` row cascades its sections/blocks/chunks away, then
    the new aggregate is bulk-inserted. So a re-ingestion atomically rebuilds the
    corpus (CORP-09) and a mid-build rollback leaves the prior corpus intact
    (CORP-08). ``get_structure`` returns the flat, position-ordered section read
    model; the web layer nests it (CORP-11).
    """

    def __init__(self, connection: Connection) -> None:
        self._conn = connection

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
        # Cascade clears any existing sections/blocks/chunks for this source.
        self._conn.execute(
            sa_delete(corpus_documents).where(corpus_documents.c.source_id == source_id)
        )

        document_id = uuid4()
        self._conn.execute(
            insert(corpus_documents).values(
                id=document_id,
                source_id=source_id,
                title=title,
                authors=list(authors),
                language=language,
                schema_version=schema_version,
            )
        )

        section_rows: list[dict[str, object]] = []
        block_rows: list[dict[str, object]] = []
        chunk_rows: list[dict[str, object]] = []
        for record in sections:
            section = record.section
            section_id = uuid4()
            section_rows.append(
                {
                    "id": section_id,
                    "document_id": document_id,
                    "position": section.position,
                    "depth": section.depth,
                    "title": section.title,
                    "section_path": list(section.section_path),
                    "anchor": section.anchor,
                    "markdown": record.markdown,
                }
            )
            for block in section.blocks:
                block_rows.append(
                    {
                        "id": uuid4(),
                        "section_id": section_id,
                        "position": block.position,
                        "block_type": block.block_type,
                        "html_fragment": block.html_fragment,
                    }
                )
            for chunk in record.chunks:
                chunk_rows.append(
                    {
                        "id": uuid4(),
                        "section_id": section_id,
                        "chunk_index": chunk.index,
                        "text": chunk.text,
                        "section_path": list(chunk.section_path),
                        "anchor": chunk.anchor,
                        "page_span": chunk.page_span,
                    }
                )

        if section_rows:
            self._conn.execute(insert(corpus_sections), section_rows)
        if block_rows:
            self._conn.execute(insert(corpus_blocks), block_rows)
        if chunk_rows:
            self._conn.execute(insert(corpus_chunks), chunk_rows)

    def get_structure(self, source_id: UUID) -> CorpusStructure | None:
        document = self._conn.execute(
            select(corpus_documents).where(corpus_documents.c.source_id == source_id)
        ).one_or_none()
        if document is None:
            return None

        # Project only the read-model columns: ``markdown`` is the section's full
        # derived text and would make this TOC read O(book size) if selected.
        rows = self._conn.execute(
            select(
                corpus_sections.c.position,
                corpus_sections.c.title,
                corpus_sections.c.depth,
                corpus_sections.c.section_path,
                corpus_sections.c.anchor,
            )
            .where(corpus_sections.c.document_id == document.id)
            .order_by(corpus_sections.c.position)
        ).all()
        sections = tuple(
            StructureSection(
                position=row.position,
                title=row.title,
                depth=row.depth,
                section_path=tuple(row.section_path),
                anchor=row.anchor,
            )
            for row in rows
        )
        return CorpusStructure(
            title=document.title,
            authors=tuple(document.authors),
            language=document.language,
            sections=sections,
        )


class SqlAlchemyEmbeddingIndexRepository:
    """``EmbeddingIndexRepository`` backed by ``corpus_chunks`` (RET-09/11).

    Reads a source's chunks to embed by joining chunks → sections → documents on
    ``source_id`` (ownership is reachable only via the parent source, AD-014) and
    writes each chunk's vector back to ``corpus_chunks.embedding``. The write goes
    through the ``VECTOR`` column type, which serializes the ``list[float]`` — so it
    does not depend on the engine-level ``register_vector`` adaptation. Operates on
    the caller's ``Connection`` so the embed transaction boundary lives in the task.
    """

    def __init__(self, connection: Connection) -> None:
        self._conn = connection

    def chunks_for_source(self, source_id: UUID) -> list[ChunkToEmbed]:
        """Return ``source_id``'s chunks (id + text), stably ordered.

        Ordered by section ``position`` then ``chunk_index`` so re-embedding a
        rebuilt corpus pairs vectors to the same reading-order chunks each run.
        """
        rows = self._conn.execute(
            select(corpus_chunks.c.id, corpus_chunks.c.text)
            .select_from(corpus_chunks)
            .join(corpus_sections, corpus_chunks.c.section_id == corpus_sections.c.id)
            .join(corpus_documents, corpus_sections.c.document_id == corpus_documents.c.id)
            .where(corpus_documents.c.source_id == source_id)
            .order_by(corpus_sections.c.position, corpus_chunks.c.chunk_index)
        ).all()
        return [ChunkToEmbed(id=row.id, text=row.text) for row in rows]

    def set_embeddings(self, items: Sequence[tuple[UUID, list[float]]]) -> None:
        """Write each ``(chunk_id, vector)`` to ``corpus_chunks.embedding``.

        One ``executemany`` ``update`` keyed on the chunk id, so a whole source is
        written in a single round trip instead of one statement per chunk; the
        ``VECTOR`` type serializes each list on bind, so this write path needs no
        global vector registration.
        """
        if not items:
            return
        stmt = (
            update(corpus_chunks)
            .where(corpus_chunks.c.id == bindparam("chunk_id"))
            .values(embedding=bindparam("embedding"))
        )
        self._conn.execute(
            stmt,
            [{"chunk_id": chunk_id, "embedding": vector} for chunk_id, vector in items],
        )


class SqlAlchemyTeachingSessionRepository:
    """``TeachingSessionRepository`` backed by the ``teaching_sessions`` table.

    Source-keyed: authorization (ownership) is the application service's job
    (AD-014). ``list_for_source`` returns newest first with each session's turn
    count (TEACH-21) via a correlated count over ``teaching_turns``.
    """

    def __init__(self, connection: Connection) -> None:
        self._conn = connection

    def add(self, session: TeachingSession) -> TeachingSession:
        self._conn.execute(
            insert(teaching_sessions).values(
                id=session.id,
                source_id=session.source_id,
                target_anchor=session.target_anchor,
                target_section_path=list(session.target_section_path),
                target_title=session.target_title,
                created_at=session.created_at,
                updated_at=session.updated_at,
            )
        )
        return session

    def get_by_id(self, session_id: UUID) -> TeachingSession | None:
        row = self._conn.execute(
            select(teaching_sessions).where(teaching_sessions.c.id == session_id)
        ).one_or_none()
        return _to_teaching_session(row) if row is not None else None

    def list_for_source(self, source_id: UUID) -> list[TeachingSessionSummary]:
        turn_count = (
            select(func.count())
            .select_from(teaching_turns)
            .where(teaching_turns.c.session_id == teaching_sessions.c.id)
            .scalar_subquery()
            .label("turn_count")
        )
        rows = self._conn.execute(
            select(teaching_sessions, turn_count)
            .where(teaching_sessions.c.source_id == source_id)
            .order_by(teaching_sessions.c.created_at.desc())
        ).all()
        return [
            TeachingSessionSummary(
                session=_to_teaching_session(row), turn_count=row.turn_count
            )
            for row in rows
        ]


class SqlAlchemyTeachingTurnRepository:
    """``TeachingTurnRepository`` backed by ``teaching_turns`` + citations.

    ``add`` inserts the turn then its citation snapshot rows (rank = tuple
    position), translating the ``(session_id, turn_index)`` unique violation to
    :class:`~app.application.errors.TeachingTurnConflict` — the turn-index race
    loser (TEACH-17). Citations are denormalized snapshots with no chunk FK, so
    they survive a corpus replace (AD-033); ``chunk_id.page_span`` and the source
    are recovered on read from the parent session (retrieval is source-scoped, so
    every citation's source is the session's — ``page_span`` is ``None`` for EPUB).
    """

    def __init__(self, connection: Connection) -> None:
        self._conn = connection

    def add(self, turn: TeachingTurn) -> TeachingTurn:
        try:
            self._conn.execute(
                insert(teaching_turns).values(
                    id=turn.id,
                    session_id=turn.session_id,
                    turn_index=turn.turn_index,
                    message=turn.message,
                    answer_status=turn.answer_status,
                    answer_text=turn.answer_text,
                    model=turn.model,
                    evidence_count=turn.evidence_count,
                    created_at=turn.created_at,
                )
            )
        except IntegrityError as exc:
            # The only unique on this insert is (session_id, turn_index): a racing
            # writer already claimed this index (TEACH-17).
            raise TeachingTurnConflict(
                "another turn already claimed this turn index"
            ) from exc

        citation_rows = [
            {
                "id": uuid4(),
                "turn_id": turn.id,
                "rank": rank,
                "chunk_id": citation.chunk_id,
                "section_path": list(citation.section_path),
                "anchor": citation.anchor,
                "snippet": citation.snippet,
                "score": citation.score,
            }
            for rank, citation in enumerate(turn.citations)
        ]
        if citation_rows:
            self._conn.execute(insert(teaching_turn_citations), citation_rows)
        return turn

    def list_for_session(self, session_id: UUID) -> list[TeachingTurn]:
        # All turns share the session's source, so one lookup recovers the source
        # for every citation's Evidence (not stored per-citation).
        source_id = self._conn.execute(
            select(teaching_sessions.c.source_id).where(
                teaching_sessions.c.id == session_id
            )
        ).scalar_one_or_none()
        if source_id is None:
            return []

        rows = self._conn.execute(
            select(
                teaching_turns,
                teaching_turn_citations.c.rank,
                teaching_turn_citations.c.chunk_id,
                teaching_turn_citations.c.section_path,
                teaching_turn_citations.c.anchor,
                teaching_turn_citations.c.snippet,
                teaching_turn_citations.c.score,
            )
            .select_from(
                teaching_turns.outerjoin(
                    teaching_turn_citations,
                    teaching_turns.c.id == teaching_turn_citations.c.turn_id,
                )
            )
            .where(teaching_turns.c.session_id == session_id)
            .order_by(teaching_turns.c.turn_index, teaching_turn_citations.c.rank)
        ).all()

        # Group the flat join back into turns (turn_index asc) with their
        # rank-ordered citations; a turn with no citations yields NULL cite cols.
        turns: dict[UUID, list] = {}
        for row in rows:
            citations = turns.setdefault(row.id, [])
            if row.rank is not None:
                citations.append(
                    Evidence(
                        chunk_id=row.chunk_id,
                        source_id=source_id,
                        section_path=tuple(row.section_path),
                        anchor=row.anchor,
                        page_span=None,
                        snippet=row.snippet,
                        score=row.score,
                    )
                )
        seen: set[UUID] = set()
        result: list[TeachingTurn] = []
        for row in rows:
            if row.id in seen:
                continue
            seen.add(row.id)
            result.append(_to_teaching_turn(row, tuple(turns[row.id])))
        return result

    def recent_history(
        self, session_id: UUID, limit: int
    ) -> tuple[int, list[HistoryTurn]]:
        # Two cheap statements, no citation join: the turn path needs only the
        # count (the next turn_index) and the bounded (message, answer_text)
        # pairs, oldest first.
        total = self._conn.execute(
            select(func.count())
            .select_from(teaching_turns)
            .where(teaching_turns.c.session_id == session_id)
        ).scalar_one()
        rows = self._conn.execute(
            select(teaching_turns.c.message, teaching_turns.c.answer_text)
            .where(teaching_turns.c.session_id == session_id)
            .order_by(teaching_turns.c.turn_index.desc())
            .limit(limit)
        ).all()
        history = [
            HistoryTurn(message=row.message, response_text=row.answer_text)
            for row in reversed(rows)
        ]
        return total, history


def _to_user(row) -> User:  # noqa: ANN001 — Row is an internal SQLAlchemy type
    return User(id=row.id, email=row.email, created_at=row.created_at)


def _to_credential(row) -> PasswordCredential:  # noqa: ANN001
    return PasswordCredential(
        user_id=row.user_id,
        password_hash=row.password_hash,
        algo_params=row.algo_params,
        updated_at=row.updated_at,
    )


def _to_session(row) -> Session:  # noqa: ANN001
    return Session(
        id=row.id,
        user_id=row.user_id,
        token_hash=row.token_hash,
        csrf_token=row.csrf_token,
        expires_at=row.expires_at,
        created_at=row.created_at,
        last_seen_at=row.last_seen_at,
    )


def _to_source(row) -> Source:  # noqa: ANN001
    return Source(
        id=row.id,
        user_id=row.user_id,
        title=row.title,
        filename=row.filename,
        content_type=row.content_type,
        byte_size=row.byte_size,
        checksum=row.checksum,
        object_key=row.object_key,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_ingestion_job(row) -> IngestionJob:  # noqa: ANN001
    return IngestionJob(
        id=row.id,
        source_id=row.source_id,
        status=row.status,
        attempts=row.attempts,
        last_error=row.last_error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_ingestion_event(row) -> IngestionEvent:  # noqa: ANN001
    return IngestionEvent(
        id=row.id,
        job_id=row.job_id,
        type=row.type,
        message=row.message,
        created_at=row.created_at,
    )


def _to_teaching_session(row) -> TeachingSession:  # noqa: ANN001
    return TeachingSession(
        id=row.id,
        source_id=row.source_id,
        target_anchor=row.target_anchor,
        target_section_path=tuple(row.target_section_path),
        target_title=row.target_title,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_teaching_turn(row, citations: tuple[Evidence, ...]) -> TeachingTurn:  # noqa: ANN001
    return TeachingTurn(
        id=row.id,
        session_id=row.session_id,
        turn_index=row.turn_index,
        message=row.message,
        answer_status=row.answer_status,
        answer_text=row.answer_text,
        model=row.model,
        evidence_count=row.evidence_count,
        citations=citations,
        created_at=row.created_at,
    )
