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
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Connection,
    bindparam,
    func,
    insert,
    literal_column,
    or_,
    select,
    update,
)
from sqlalchemy import delete as sa_delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from app.application.errors import TeachingTurnConflict
from app.application.text_search import resolve_text_search_config
from app.domain.entities import (
    ACTIVE_QUIZ_JOB_STATUSES,
    AnchorBlockSnapshot,
    AnchorSection,
    Backlink,
    ChapterIndexRow,
    ChapterSection,
    ChunkToEmbed,
    CorpusSectionRecord,
    CorpusStructure,
    DerivedNoteLink,
    DueReviewItem,
    Evidence,
    HistoryTurn,
    IngestionEvent,
    IngestionJob,
    Note,
    NoteAnchor,
    NoteAnchorStatus,
    NoteSummary,
    PasswordCredential,
    QuizGenerationJob,
    QuizItem,
    QuizItemStatus,
    QuizSection,
    ReadingPosition,
    ReconcileSection,
    ReviewLogEntry,
    SchedulingSnapshot,
    SectionContent,
    Session,
    Source,
    SourceHighlight,
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
    note_anchors,
    note_links,
    note_tags,
    notes,
    quiz_generation_jobs,
    quiz_item_scheduling,
    quiz_items,
    reading_positions,
    review_log,
    sessions,
    sources,
    tags,
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

        # One regconfig per document: the chunk's lexical arm stems in the book's
        # own language (EMB-11). The 0007 trigger builds ``search_vector`` from it;
        # the app never writes ``search_vector`` directly.
        search_config = resolve_text_search_config(language)

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
                    "anchor_aliases": list(section.anchor_aliases),
                    "markdown": record.markdown,
                    "word_count": record.word_count,
                }
            )
            for index, block in enumerate(section.blocks):
                block_rows.append(
                    {
                        "id": uuid4(),
                        "section_id": section_id,
                        "position": block.position,
                        "block_type": block.block_type,
                        "html_fragment": block.html_fragment,
                        # Positionally aligned with ``section.blocks`` (NF-02); NULL
                        # when the build did not compute a hash for this block.
                        "content_hash": (
                            record.block_hashes[index]
                            if index < len(record.block_hashes)
                            else None
                        ),
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
                        "search_config": search_config,
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

    def get_section(self, source_id: UUID, anchor: str) -> SectionContent | None:
        # Owner-agnostic read: ownership is enforced one layer up via the source
        # lookup (AD-014), so this keys on ``source_id`` alone. Matches the canonical
        # anchor OR any section that carries ``anchor`` as an alias (normalization
        # merged that section away, AD-085). A canonical hit is ordered first so it
        # wins a collision with another section's alias; ``position`` then breaks
        # ties, so a duplicate anchor resolves to the first section in reading order —
        # matching how teaching resolves a target anchor.
        canonical_first = (corpus_sections.c.anchor == anchor).desc()
        row = self._conn.execute(
            select(
                corpus_sections.c.title,
                corpus_sections.c.section_path,
                corpus_sections.c.anchor,
                corpus_sections.c.markdown,
            )
            .join(corpus_documents, corpus_sections.c.document_id == corpus_documents.c.id)
            .where(corpus_documents.c.source_id == source_id)
            .where(
                or_(
                    corpus_sections.c.anchor == anchor,
                    corpus_sections.c.anchor_aliases.any(anchor),
                )
            )
            .order_by(canonical_first, corpus_sections.c.position)
            .limit(1)
        ).first()
        if row is None:
            return None
        return SectionContent(
            anchor=row.anchor,
            title=row.title,
            section_path=tuple(row.section_path),
            markdown=row.markdown,
        )

    def get_chapter_index(self, source_id: UUID) -> tuple[ChapterIndexRow, ...] | None:
        # The flat, position-ordered index chapter partitioning / percent math run over.
        # Mirrors ``get_structure``'s document guard (None => no corpus) but selects the
        # per-section word_count too, and deliberately NOT markdown — the index never
        # loads chapter bodies (design §Components).
        document = self._conn.execute(
            select(corpus_documents.c.id).where(corpus_documents.c.source_id == source_id)
        ).one_or_none()
        if document is None:
            return None
        rows = self._conn.execute(
            select(
                corpus_sections.c.position,
                corpus_sections.c.depth,
                corpus_sections.c.title,
                corpus_sections.c.section_path,
                corpus_sections.c.anchor,
                corpus_sections.c.anchor_aliases,
                corpus_sections.c.word_count,
            )
            .where(corpus_sections.c.document_id == document.id)
            .order_by(corpus_sections.c.position)
        ).all()
        return tuple(
            ChapterIndexRow(
                position=row.position,
                depth=row.depth,
                title=row.title,
                section_path=tuple(row.section_path),
                anchor=row.anchor,
                anchor_aliases=tuple(row.anchor_aliases),
                word_count=row.word_count,
            )
            for row in rows
        )

    def get_sections_span(
        self, source_id: UUID, first_position: int, last_position: int
    ) -> tuple[ChapterSection, ...]:
        # One chapter's body: the sections in the inclusive [first, last] position span,
        # with their derived markdown + word_count, position-ordered. Loads markdown for
        # this span only (never the whole book).
        rows = self._conn.execute(
            select(
                corpus_sections.c.anchor,
                corpus_sections.c.title,
                corpus_sections.c.section_path,
                corpus_sections.c.markdown,
                corpus_sections.c.word_count,
            )
            .join(corpus_documents, corpus_sections.c.document_id == corpus_documents.c.id)
            .where(corpus_documents.c.source_id == source_id)
            .where(corpus_sections.c.position >= first_position)
            .where(corpus_sections.c.position <= last_position)
            .order_by(corpus_sections.c.position)
        ).all()
        return tuple(
            ChapterSection(
                anchor=row.anchor,
                title=row.title,
                section_path=tuple(row.section_path),
                markdown=row.markdown,
                word_count=row.word_count,
            )
            for row in rows
        )

    def section_texts(self, source_id: UUID) -> list[ReconcileSection]:
        # Reading-order sections with their chunk text concatenated (reconciliation
        # checks a snapshotted excerpt against the same chunk text it was verified
        # against at generation, QUIZ-16). One query joins chunks → sections →
        # documents on ``source_id``; sections with no chunks still appear (empty text)
        # via the outer join so an anchor that survives is always found.
        rows = self._conn.execute(
            select(
                corpus_sections.c.position,
                corpus_sections.c.anchor,
                corpus_sections.c.anchor_aliases,
                corpus_sections.c.section_path,
                corpus_chunks.c.chunk_index,
                corpus_chunks.c.text,
            )
            .select_from(
                corpus_sections.join(
                    corpus_documents,
                    corpus_sections.c.document_id == corpus_documents.c.id,
                ).outerjoin(
                    corpus_chunks,
                    corpus_chunks.c.section_id == corpus_sections.c.id,
                )
            )
            .where(corpus_documents.c.source_id == source_id)
            .order_by(corpus_sections.c.position, corpus_chunks.c.chunk_index)
        ).all()

        ordered_positions: list[int] = []
        anchors: dict[int, tuple[str, tuple[str, ...], tuple[str, ...]]] = {}
        chunks: dict[int, list[str]] = {}
        for row in rows:
            if row.position not in anchors:
                ordered_positions.append(row.position)
                anchors[row.position] = (
                    row.anchor,
                    tuple(row.section_path),
                    tuple(row.anchor_aliases),
                )
                chunks[row.position] = []
            if row.text is not None:
                chunks[row.position].append(row.text)
        return [
            ReconcileSection(
                anchor=anchors[pos][0],
                section_path=anchors[pos][1],
                text=" ".join(chunks[pos]),
                anchor_aliases=anchors[pos][2],
            )
            for pos in ordered_positions
        ]

    def expand_anchors(
        self, source_id: UUID, anchors: Sequence[str]
    ) -> tuple[str, ...]:
        # Grow a set of section anchors to include every alias that resolves to the
        # same sections (AD-085), so teaching-scoped retrieval filtered by a target
        # anchor still reaches evidence after normalization merged a section away.
        # A section is in scope when its canonical anchor is in ``anchors`` OR any of
        # its aliases is; the result is the input plus those sections' canonical
        # anchors and aliases. Order is deterministic: the input order first (deduped),
        # then any newly reached anchors in section reading order.
        requested = list(anchors)
        if not requested:
            return ()
        rows = self._conn.execute(
            select(
                corpus_sections.c.anchor,
                corpus_sections.c.anchor_aliases,
            )
            .join(corpus_documents, corpus_sections.c.document_id == corpus_documents.c.id)
            .where(corpus_documents.c.source_id == source_id)
            .where(
                or_(
                    corpus_sections.c.anchor.in_(requested),
                    corpus_sections.c.anchor_aliases.overlap(requested),
                )
            )
            .order_by(corpus_sections.c.position)
        ).all()

        expanded: list[str] = list(dict.fromkeys(requested))
        seen = set(expanded)
        for row in rows:
            for anchor in (row.anchor, *row.anchor_aliases):
                if anchor not in seen:
                    seen.add(anchor)
                    expanded.append(anchor)
        return tuple(expanded)

    def blocks_for_section(self, source_id: UUID, anchor: str) -> AnchorSection | None:
        # Resolve the section canonical-first then by alias (mirrors ``get_section``),
        # then load its reading-order blocks with their stored hash and preserved HTML.
        canonical_first = (corpus_sections.c.anchor == anchor).desc()
        section = self._conn.execute(
            select(
                corpus_sections.c.id,
                corpus_sections.c.anchor,
                corpus_sections.c.anchor_aliases,
                corpus_sections.c.section_path,
            )
            .join(corpus_documents, corpus_sections.c.document_id == corpus_documents.c.id)
            .where(corpus_documents.c.source_id == source_id)
            .where(
                or_(
                    corpus_sections.c.anchor == anchor,
                    corpus_sections.c.anchor_aliases.any(anchor),
                )
            )
            .order_by(canonical_first, corpus_sections.c.position)
            .limit(1)
        ).first()
        if section is None:
            return None
        block_rows = self._conn.execute(
            select(
                corpus_blocks.c.position,
                corpus_blocks.c.content_hash,
                corpus_blocks.c.html_fragment,
            )
            .where(corpus_blocks.c.section_id == section.id)
            .order_by(corpus_blocks.c.position)
        ).all()
        return AnchorSection(
            anchor=section.anchor,
            section_path=tuple(section.section_path),
            anchor_aliases=tuple(section.anchor_aliases),
            blocks=tuple(_to_anchor_block(row) for row in block_rows),
        )

    def blocks_for_reconcile(self, source_id: UUID) -> list[AnchorSection]:
        # Every section with its reading-order blocks — the block-level analogue of
        # ``section_texts`` the 4-tier note-anchor cascade reads. One join pulls sections
        # and their blocks; a section with no blocks still appears (empty ``blocks``) so a
        # surviving anchor is always reachable.
        rows = self._conn.execute(
            select(
                corpus_sections.c.position,
                corpus_sections.c.anchor,
                corpus_sections.c.anchor_aliases,
                corpus_sections.c.section_path,
                corpus_blocks.c.position.label("block_position"),
                corpus_blocks.c.content_hash,
                corpus_blocks.c.html_fragment,
            )
            .select_from(
                corpus_sections.join(
                    corpus_documents,
                    corpus_sections.c.document_id == corpus_documents.c.id,
                ).outerjoin(
                    corpus_blocks,
                    corpus_blocks.c.section_id == corpus_sections.c.id,
                )
            )
            .where(corpus_documents.c.source_id == source_id)
            .order_by(corpus_sections.c.position, corpus_blocks.c.position)
        ).all()

        ordered_positions: list[int] = []
        meta: dict[int, tuple[str, tuple[str, ...], tuple[str, ...]]] = {}
        blocks: dict[int, list[AnchorBlockSnapshot]] = {}
        for row in rows:
            if row.position not in meta:
                ordered_positions.append(row.position)
                meta[row.position] = (
                    row.anchor,
                    tuple(row.section_path),
                    tuple(row.anchor_aliases),
                )
                blocks[row.position] = []
            if row.block_position is not None:
                blocks[row.position].append(
                    AnchorBlockSnapshot(
                        ordinal=row.block_position,
                        content_hash=row.content_hash,
                        html_fragment=row.html_fragment,
                    )
                )
        return [
            AnchorSection(
                anchor=meta[pos][0],
                section_path=meta[pos][1],
                anchor_aliases=meta[pos][2],
                blocks=tuple(blocks[pos]),
            )
            for pos in ordered_positions
        ]


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

    def stale_chunks_for_source(
        self, source_id: UUID, model: str, limit: int
    ) -> list[ChunkToEmbed]:
        """Return up to ``limit`` of ``source_id``'s chunks needing (re)embedding.

        Selects chunks whose ``embedding IS NULL`` or whose ``embedding_model`` is
        distinct from ``model`` — the not-yet-embedded and the stale-model rows —
        ordered by section ``position`` then ``chunk_index`` (the same stable order
        as :meth:`chunks_for_source`) and bounded to ``limit`` rows in SQL.
        ``reembed_document`` re-queries per committed batch, so committed progress
        shrinks this set as it lands (idempotent + resumable); the SQL ``LIMIT`` keeps
        each pass O(limit) rather than fetching the whole remaining stale set.
        """
        rows = self._conn.execute(
            select(corpus_chunks.c.id, corpus_chunks.c.text)
            .select_from(corpus_chunks)
            .join(corpus_sections, corpus_chunks.c.section_id == corpus_sections.c.id)
            .join(corpus_documents, corpus_sections.c.document_id == corpus_documents.c.id)
            .where(corpus_documents.c.source_id == source_id)
            .where(
                corpus_chunks.c.embedding.is_(None)
                | corpus_chunks.c.embedding_model.is_distinct_from(model)
            )
            .order_by(corpus_sections.c.position, corpus_chunks.c.chunk_index)
            .limit(limit)
        ).all()
        return [ChunkToEmbed(id=row.id, text=row.text) for row in rows]

    def set_embeddings(
        self, items: Sequence[tuple[UUID, list[float]]], *, model: str
    ) -> None:
        """Write each ``(chunk_id, vector)`` plus ``model`` to ``corpus_chunks``.

        One ``executemany`` ``update`` keyed on the chunk id sets ``embedding`` and
        ``embedding_model`` together, so a whole source is written in a single round
        trip instead of one statement per chunk and every embedded chunk records the
        producing model (ADR-0019). ``model`` is constant across the batch, so it is
        bound once into the statement rather than repeated per row; the ``VECTOR``
        type serializes each list on bind, so this write path needs no global vector
        registration.
        """
        if not items:
            return
        stmt = (
            update(corpus_chunks)
            .where(corpus_chunks.c.id == bindparam("chunk_id"))
            .values(embedding=bindparam("embedding"), embedding_model=model)
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


class SqlAlchemyQuizItemRepository:
    """``QuizItemRepository`` backed by ``quiz_items`` + scheduling/log tables.

    Upsert keys on ``(source_id, content_key)`` and updates content fields only, so a
    deck regeneration never touches an existing item's ``quiz_item_scheduling`` or
    ``review_log`` rows (QUIZ-02). Reads/due queries reach ownership only via the
    parent source's ``user_id`` (AD-014). Operates on the caller's ``Connection`` so
    the transaction boundary lives at the composition root.
    """

    def __init__(self, connection: Connection) -> None:
        self._conn = connection

    def sections_for_generation(
        self, source_id: UUID, *, min_chars: int
    ) -> list[QuizSection]:
        """Return ``source_id``'s eligible leaf sections (≥ ``min_chars`` text, A-3).

        A section is a *leaf* when no other section's ``section_path`` strictly extends
        it (the TOC-tree leaves); each eligible leaf carries its citation anchors and its
        ``(chunk_id, text)`` chunks in reading order for candidate grounding. Sections
        whose summed chunk text is shorter than ``min_chars`` (stub sections) are skipped.
        """
        document_id = self._conn.execute(
            select(corpus_documents.c.id).where(
                corpus_documents.c.source_id == source_id
            )
        ).scalar_one_or_none()
        if document_id is None:
            return []

        section_rows = self._conn.execute(
            select(
                corpus_sections.c.id,
                corpus_sections.c.section_path,
                corpus_sections.c.anchor,
                corpus_sections.c.title,
            )
            .where(corpus_sections.c.document_id == document_id)
            .order_by(corpus_sections.c.position)
        ).all()

        chunk_rows = self._conn.execute(
            select(
                corpus_chunks.c.section_id,
                corpus_chunks.c.id,
                corpus_chunks.c.text,
            )
            .join(corpus_sections, corpus_chunks.c.section_id == corpus_sections.c.id)
            .where(corpus_sections.c.document_id == document_id)
            .order_by(corpus_sections.c.position, corpus_chunks.c.chunk_index)
        ).all()
        chunks_by_section: dict[UUID, list[tuple[UUID, str]]] = {}
        for row in chunk_rows:
            chunks_by_section.setdefault(row.section_id, []).append((row.id, row.text))

        paths = [tuple(row.section_path) for row in section_rows]

        def _is_leaf(index: int) -> bool:
            path = paths[index]
            depth = len(path)
            return not any(
                other[:depth] == path and len(other) > depth
                for pos, other in enumerate(paths)
                if pos != index
            )

        result: list[QuizSection] = []
        for index, row in enumerate(section_rows):
            if not _is_leaf(index):
                continue
            chunks = tuple(chunks_by_section.get(row.id, ()))
            if sum(len(text) for _, text in chunks) < min_chars:
                continue
            result.append(
                QuizSection(
                    section_path=tuple(row.section_path),
                    anchor=row.anchor,
                    title=row.title,
                    chunks=chunks,
                )
            )
        return result

    def existing_embeddings(self, source_id: UUID) -> list[tuple[UUID, list[float]]]:
        """Return ``(item_id, embedding)`` for the source's already-embedded items."""
        rows = self._conn.execute(
            select(quiz_items.c.id, quiz_items.c.embedding)
            .where(quiz_items.c.source_id == source_id)
            .where(quiz_items.c.embedding.is_not(None))
        ).all()
        return [(row.id, [float(value) for value in row.embedding]) for row in rows]

    def upsert(self, item: QuizItem, *, embedding: Sequence[float] | None) -> bool:
        """Upsert on ``(source_id, content_key)``; update content fields only on conflict.

        Returns ``True`` when a new row was inserted and ``False`` when an existing row's
        content was updated. The conflict update leaves ``status`` and the scheduling/
        review-log rows untouched (QUIZ-02); the ``(xmax = 0)`` projection is Postgres'
        was-inserted signal (zero on a fresh insert, the updater's xid otherwise).
        """
        stmt = pg_insert(quiz_items).values(
            id=item.id,
            source_id=item.source_id,
            item_type=item.item_type,
            question=item.question,
            answer=item.answer,
            section_path=list(item.section_path),
            anchor=item.anchor,
            source_excerpt=item.source_excerpt,
            chunk_hash=item.chunk_hash,
            content_key=item.content_key,
            status=item.status,
            embedding=list(embedding) if embedding is not None else None,
            generation_meta=item.generation_meta,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["source_id", "content_key"],
            set_={
                "question": stmt.excluded.question,
                "answer": stmt.excluded.answer,
                "section_path": stmt.excluded.section_path,
                "anchor": stmt.excluded.anchor,
                "source_excerpt": stmt.excluded.source_excerpt,
                "chunk_hash": stmt.excluded.chunk_hash,
                "embedding": stmt.excluded.embedding,
                "generation_meta": stmt.excluded.generation_meta,
                "updated_at": stmt.excluded.updated_at,
            },
        ).returning(literal_column("(xmax = 0)").label("inserted"))
        return bool(self._conn.execute(stmt).scalar_one())

    def create_scheduling(
        self, quiz_item_id: UUID, snapshot: SchedulingSnapshot
    ) -> None:
        """Insert the initial scheduling row for a newly created item (QUIZ-09)."""
        self._conn.execute(
            insert(quiz_item_scheduling).values(
                quiz_item_id=quiz_item_id,
                state=snapshot.state,
                step=snapshot.step,
                stability=snapshot.stability,
                difficulty=snapshot.difficulty,
                due=snapshot.due,
                last_review=snapshot.last_review,
            )
        )

    def get_scheduling(self, quiz_item_id: UUID) -> SchedulingSnapshot | None:
        """Return the item's current scheduling snapshot, or ``None`` if absent."""
        row = self._conn.execute(
            select(quiz_item_scheduling).where(
                quiz_item_scheduling.c.quiz_item_id == quiz_item_id
            )
        ).one_or_none()
        return _to_scheduling(row) if row is not None else None

    def update_scheduling(
        self, quiz_item_id: UUID, snapshot: SchedulingSnapshot
    ) -> None:
        """Replace the item's scheduling snapshot after a review (QUIZ-12)."""
        self._conn.execute(
            update(quiz_item_scheduling)
            .where(quiz_item_scheduling.c.quiz_item_id == quiz_item_id)
            .values(
                state=snapshot.state,
                step=snapshot.step,
                stability=snapshot.stability,
                difficulty=snapshot.difficulty,
                due=snapshot.due,
                last_review=snapshot.last_review,
                updated_at=func.now(),
            )
        )

    def append_log(self, quiz_item_id: UUID, entry: ReviewLogEntry) -> None:
        """Append an immutable review-log entry for the item (QUIZ-12)."""
        self._conn.execute(
            insert(review_log).values(
                id=uuid4(),
                quiz_item_id=quiz_item_id,
                rating=entry.rating,
                reviewed_at=entry.reviewed_at,
                review_duration_ms=entry.review_duration_ms,
            )
        )

    def list_for_source(self, source_id: UUID) -> list[QuizItem]:
        """Return all of ``source_id``'s items (any status), oldest first (QUIZ-14)."""
        rows = self._conn.execute(
            select(*_QUIZ_ITEM_READ_COLUMNS)
            .where(quiz_items.c.source_id == source_id)
            .order_by(quiz_items.c.created_at, quiz_items.c.id)
        ).all()
        return [_to_quiz_item(row) for row in rows]

    def due_map(self, source_id: UUID) -> dict[UUID, datetime]:
        """Return ``item_id → due`` for ``source_id``'s items — the overview due column."""
        rows = self._conn.execute(
            select(quiz_item_scheduling.c.quiz_item_id, quiz_item_scheduling.c.due)
            .select_from(
                quiz_item_scheduling.join(
                    quiz_items,
                    quiz_item_scheduling.c.quiz_item_id == quiz_items.c.id,
                )
            )
            .where(quiz_items.c.source_id == source_id)
        ).all()
        return {row.quiz_item_id: row.due for row in rows}

    def counts_by_status(self, source_id: UUID) -> dict[str, int]:
        """Return ``status → count`` for ``source_id``'s items (QUIZ-14)."""
        rows = self._conn.execute(
            select(quiz_items.c.status, func.count())
            .where(quiz_items.c.source_id == source_id)
            .group_by(quiz_items.c.status)
        ).all()
        return {row[0]: row[1] for row in rows}

    def due_for_user(
        self,
        user_id: UUID,
        *,
        now: datetime,
        limit: int,
        source_id: UUID | None = None,
    ) -> tuple[int, list[DueReviewItem]]:
        """Return the caller's due queue: total due count and up to ``limit`` items.

        Active items with ``due <= now`` across the user's sources (optionally filtered to
        one ``source_id``), joined through ``sources`` for ownership so no other user's
        items leak, ordered ``due ASC, id ASC`` (A-6). Stale/orphaned items are excluded
        (QUIZ-17); the returned count is the full due total before the ``limit``.
        """
        join = quiz_items.join(
            sources, quiz_items.c.source_id == sources.c.id
        ).join(
            quiz_item_scheduling,
            quiz_item_scheduling.c.quiz_item_id == quiz_items.c.id,
        )
        conditions = [
            sources.c.user_id == user_id,
            quiz_items.c.status == QuizItemStatus.ACTIVE,
            quiz_item_scheduling.c.due <= now,
        ]
        if source_id is not None:
            conditions.append(quiz_items.c.source_id == source_id)

        total = self._conn.execute(
            select(func.count()).select_from(join).where(*conditions)
        ).scalar_one()

        rows = self._conn.execute(
            select(
                *_QUIZ_ITEM_READ_COLUMNS,
                sources.c.title.label("source_title"),
                quiz_item_scheduling.c.due.label("due"),
            )
            .select_from(join)
            .where(*conditions)
            .order_by(quiz_item_scheduling.c.due.asc(), quiz_items.c.id.asc())
            .limit(limit)
        ).all()
        items = [
            DueReviewItem(
                item=_to_quiz_item(row), source_title=row.source_title, due=row.due
            )
            for row in rows
        ]
        return total, items

    def get_by_id(self, item_id: UUID) -> QuizItem | None:
        """Return the item with ``item_id``, or ``None`` if absent."""
        row = self._conn.execute(
            select(*_QUIZ_ITEM_READ_COLUMNS).where(quiz_items.c.id == item_id)
        ).one_or_none()
        return _to_quiz_item(row) if row is not None else None

    def items_for_reconcile(self, source_id: UUID) -> list[QuizItem]:
        """Return ``source_id``'s items for post-re-ingestion reconciliation (QUIZ-16)."""
        rows = self._conn.execute(
            select(*_QUIZ_ITEM_READ_COLUMNS)
            .where(quiz_items.c.source_id == source_id)
            .order_by(quiz_items.c.created_at, quiz_items.c.id)
        ).all()
        return [_to_quiz_item(row) for row in rows]

    def update_reconciliation(
        self,
        item_id: UUID,
        *,
        anchor: str,
        section_path: Sequence[str],
        status: str,
    ) -> None:
        """Update only an item's ``anchor``/``section_path``/``status`` (QUIZ-16).

        Reconciliation touches these three fields only — the scheduling and review-log
        rows are never modified or deleted.
        """
        self._conn.execute(
            update(quiz_items)
            .where(quiz_items.c.id == item_id)
            .values(anchor=anchor, section_path=list(section_path), status=status)
        )


class SqlAlchemyQuizJobRepository:
    """``QuizJobRepository`` backed by ``quiz_generation_jobs`` (mirrors the ingestion jobs repo).

    The single-active-job guard (QUIZ-04) is the ``get_active_for_source`` query rather
    than a partial unique index, so a caller checks for a queued/running job before
    inserting a new one.
    """

    def __init__(self, connection: Connection) -> None:
        self._conn = connection

    def add(self, job: QuizGenerationJob) -> QuizGenerationJob:
        """Insert a new deck-generation job."""
        self._conn.execute(
            insert(quiz_generation_jobs).values(
                id=job.id,
                source_id=job.source_id,
                status=job.status,
                attempts=job.attempts,
                generated_count=job.generated_count,
                discarded_count=job.discarded_count,
                failed_sections=job.failed_sections,
                last_error=job.last_error,
                created_at=job.created_at,
                updated_at=job.updated_at,
            )
        )
        return job

    def get_by_id(self, job_id: UUID) -> QuizGenerationJob | None:
        row = self._conn.execute(
            select(quiz_generation_jobs).where(quiz_generation_jobs.c.id == job_id)
        ).one_or_none()
        return _to_quiz_job(row) if row is not None else None

    def get_active_for_source(self, source_id: UUID) -> QuizGenerationJob | None:
        """Return the source's queued/running job if one exists (QUIZ-04), else ``None``."""
        row = self._conn.execute(
            select(quiz_generation_jobs)
            .where(quiz_generation_jobs.c.source_id == source_id)
            .where(quiz_generation_jobs.c.status.in_(ACTIVE_QUIZ_JOB_STATUSES))
            .order_by(quiz_generation_jobs.c.created_at.desc())
            .limit(1)
        ).one_or_none()
        return _to_quiz_job(row) if row is not None else None

    def get_latest_for_source(self, source_id: UUID) -> QuizGenerationJob | None:
        row = self._conn.execute(
            select(quiz_generation_jobs)
            .where(quiz_generation_jobs.c.source_id == source_id)
            .order_by(quiz_generation_jobs.c.created_at.desc())
            .limit(1)
        ).one_or_none()
        return _to_quiz_job(row) if row is not None else None

    def update(self, job: QuizGenerationJob) -> QuizGenerationJob:
        """Persist ``status``/``attempts``/counts/``last_error``/``updated_at``."""
        self._conn.execute(
            update(quiz_generation_jobs)
            .where(quiz_generation_jobs.c.id == job.id)
            .values(
                status=job.status,
                attempts=job.attempts,
                generated_count=job.generated_count,
                discarded_count=job.discarded_count,
                failed_sections=job.failed_sections,
                last_error=job.last_error,
                updated_at=job.updated_at,
            )
        )
        return job


class SqlAlchemyNoteRepository:
    """``NoteRepository`` backed by the notes/anchors/tags/links tables (ADR-0026 §2).

    Owner scoping is the application service's job (AD-014); these methods key on ids.
    The derived-index writes (``set_tags``/``set_links``) are delete-then-insert so a
    save rebuilds the wikilink and tag indexes from the note body. Reconciliation writes
    only an anchor's payload + status, never a note's prose (NF-07). Operates on the
    caller's ``Connection`` so the transaction boundary lives at the composition root.
    """

    def __init__(self, connection: Connection) -> None:
        self._conn = connection

    def add(self, note: Note) -> Note:
        self._conn.execute(
            insert(notes).values(
                id=note.id,
                user_id=note.user_id,
                title=note.title,
                body_markdown=note.body_markdown,
                created_at=note.created_at,
                updated_at=note.updated_at,
            )
        )
        return note

    def get_by_id(self, note_id: UUID) -> Note | None:
        row = self._conn.execute(
            select(notes).where(notes.c.id == note_id)
        ).one_or_none()
        return _to_note(row) if row is not None else None

    def update(
        self, note_id: UUID, *, title: str, body_markdown: str, updated_at: datetime
    ) -> None:
        self._conn.execute(
            update(notes)
            .where(notes.c.id == note_id)
            .values(title=title, body_markdown=body_markdown, updated_at=updated_at)
        )

    def delete(self, note_id: UUID) -> None:
        self._conn.execute(sa_delete(notes).where(notes.c.id == note_id))

    def list_summaries(
        self, user_id: UUID, *, tag: str | None = None
    ) -> list[NoteSummary]:
        query = select(notes).where(notes.c.user_id == user_id)
        if tag is not None:
            query = query.where(
                notes.c.id.in_(
                    select(note_tags.c.note_id)
                    .join(tags, note_tags.c.tag_id == tags.c.id)
                    .where(tags.c.user_id == user_id, tags.c.name == tag)
                )
            )
        rows = self._conn.execute(
            query.order_by(notes.c.updated_at.desc(), notes.c.id)
        ).all()
        note_list = [_to_note(row) for row in rows]
        if not note_list:
            return []

        ids = [note.id for note in note_list]
        tag_rows = self._conn.execute(
            select(note_tags.c.note_id, tags.c.name)
            .join(tags, note_tags.c.tag_id == tags.c.id)
            .where(note_tags.c.note_id.in_(ids))
            .order_by(tags.c.name)
        ).all()
        tags_by_note: dict[UUID, list[str]] = {}
        for row in tag_rows:
            tags_by_note.setdefault(row.note_id, []).append(row.name)

        status_rows = self._conn.execute(
            select(note_anchors.c.note_id, note_anchors.c.status)
            .where(note_anchors.c.note_id.in_(ids))
            .order_by(note_anchors.c.created_at)
        ).all()
        statuses_by_note: dict[UUID, list[str]] = {}
        for row in status_rows:
            statuses_by_note.setdefault(row.note_id, []).append(row.status)

        return [
            NoteSummary(
                note=note,
                tags=tuple(tags_by_note.get(note.id, [])),
                anchor_statuses=tuple(statuses_by_note.get(note.id, [])),
            )
            for note in note_list
        ]

    def tags_for_note(self, note_id: UUID) -> list[str]:
        rows = self._conn.execute(
            select(tags.c.name)
            .join(note_tags, note_tags.c.tag_id == tags.c.id)
            .where(note_tags.c.note_id == note_id)
            .order_by(tags.c.name)
        ).all()
        return [row.name for row in rows]

    def anchors_for_note(self, note_id: UUID) -> list[NoteAnchor]:
        rows = self._conn.execute(
            select(note_anchors)
            .where(note_anchors.c.note_id == note_id)
            .order_by(note_anchors.c.created_at, note_anchors.c.id)
        ).all()
        return [_to_note_anchor(row) for row in rows]

    def backlinks(self, note_id: UUID) -> list[Backlink]:
        rows = self._conn.execute(
            select(notes.c.id, notes.c.title, notes.c.updated_at)
            .join(note_links, note_links.c.note_id == notes.c.id)
            .where(note_links.c.target_note_id == note_id)
            .order_by(notes.c.updated_at.desc(), notes.c.id)
        ).all()
        # A note may link to the target more than once; collapse to distinct notes.
        seen: set[UUID] = set()
        result: list[Backlink] = []
        for row in rows:
            if row.id in seen:
                continue
            seen.add(row.id)
            result.append(Backlink(note_id=row.id, title=row.title))
        return result

    def resolve_titles(
        self, user_id: UUID, titles: Sequence[str]
    ) -> dict[str, UUID]:
        wanted = [title.lower() for title in titles]
        if not wanted:
            return {}
        rows = self._conn.execute(
            select(notes.c.id, notes.c.title)
            .where(notes.c.user_id == user_id)
            .where(func.lower(notes.c.title).in_(wanted))
            .order_by(notes.c.created_at, notes.c.id)
        ).all()
        resolved: dict[str, UUID] = {}
        for row in rows:
            # First (earliest-created) note wins a title collision.
            resolved.setdefault(row.title.lower(), row.id)
        return resolved

    def set_tags(self, note_id: UUID, user_id: UUID, names: Sequence[str]) -> None:
        self._conn.execute(sa_delete(note_tags).where(note_tags.c.note_id == note_id))
        # Batched get-or-create: one bulk upsert, one lookup, one bulk wire-up —
        # a constant four statements per save instead of three per tag. Deduped
        # defensively: duplicate (user_id, name) rows in a single INSERT would
        # error before ON CONFLICT could ignore them.
        unique_names = list(dict.fromkeys(names))
        if not unique_names:
            return
        self._conn.execute(
            pg_insert(tags)
            .values(
                [
                    {"id": uuid4(), "user_id": user_id, "name": name}
                    for name in unique_names
                ]
            )
            .on_conflict_do_nothing(index_elements=["user_id", "name"])
        )
        rows = self._conn.execute(
            select(tags.c.id).where(
                tags.c.user_id == user_id, tags.c.name.in_(unique_names)
            )
        ).all()
        self._conn.execute(
            insert(note_tags).values(
                [{"note_id": note_id, "tag_id": row.id} for row in rows]
            )
        )

    def set_links(self, note_id: UUID, links: Sequence[DerivedNoteLink]) -> None:
        self._conn.execute(sa_delete(note_links).where(note_links.c.note_id == note_id))
        rows = [
            {
                "id": uuid4(),
                "note_id": note_id,
                "target_note_id": link.target_note_id,
                "target_text": link.target_text,
            }
            for link in links
        ]
        if rows:
            self._conn.execute(insert(note_links), rows)

    def add_anchor(self, anchor: NoteAnchor) -> NoteAnchor:
        self._conn.execute(
            insert(note_anchors).values(
                id=anchor.id,
                note_id=anchor.note_id,
                source_id=anchor.source_id,
                source_title=anchor.source_title,
                anchor=anchor.anchor,
                section_path=list(anchor.section_path),
                block_hash=anchor.block_hash,
                block_ordinal=anchor.block_ordinal,
                start_offset=anchor.start_offset,
                end_offset=anchor.end_offset,
                quote_exact=anchor.quote_exact,
                quote_prefix=anchor.quote_prefix,
                quote_suffix=anchor.quote_suffix,
                status=anchor.status,
                created_at=anchor.created_at,
                updated_at=anchor.updated_at,
            )
        )
        return anchor

    def anchors_for_source(self, source_id: UUID) -> list[NoteAnchor]:
        rows = self._conn.execute(
            select(note_anchors)
            .where(note_anchors.c.source_id == source_id)
            .order_by(note_anchors.c.created_at, note_anchors.c.id)
        ).all()
        return [_to_note_anchor(row) for row in rows]

    def highlights_for_source(
        self, user_id: UUID, source_id: UUID
    ) -> tuple[SourceHighlight, ...]:
        # Owner-scoped highlights for inline painting: a note anchor belongs to its
        # note's owner, so join notes and filter by user_id (unlike ``anchors_for_source``
        # which spans all owners for reconciliation). Projects only the quote-with-context
        # + status the reader painter needs, stably ordered.
        rows = self._conn.execute(
            select(
                note_anchors.c.note_id,
                note_anchors.c.anchor,
                note_anchors.c.quote_exact,
                note_anchors.c.quote_prefix,
                note_anchors.c.quote_suffix,
                note_anchors.c.status,
            )
            .join(notes, note_anchors.c.note_id == notes.c.id)
            .where(notes.c.user_id == user_id)
            .where(note_anchors.c.source_id == source_id)
            .order_by(note_anchors.c.created_at, note_anchors.c.id)
        ).all()
        return tuple(
            SourceHighlight(
                note_id=row.note_id,
                anchor=row.anchor,
                quote_exact=row.quote_exact,
                quote_prefix=row.quote_prefix,
                quote_suffix=row.quote_suffix,
                status=row.status,
            )
            for row in rows
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
        self._conn.execute(
            update(note_anchors)
            .where(note_anchors.c.id == anchor_id)
            .values(
                anchor=anchor,
                section_path=list(section_path),
                block_hash=block_hash,
                block_ordinal=block_ordinal,
                start_offset=start_offset,
                end_offset=end_offset,
                status=status,
                updated_at=func.now(),
            )
        )

    def orphan_anchors_for_source(self, source_id: UUID) -> None:
        self._conn.execute(
            update(note_anchors)
            .where(note_anchors.c.source_id == source_id)
            .where(note_anchors.c.status != NoteAnchorStatus.ORPHANED)
            .values(status=NoteAnchorStatus.ORPHANED, updated_at=func.now())
        )


class SqlAlchemyReadingPositionRepository:
    """``ReadingPositionRepository`` backed by ``reading_positions`` (RD-08/12).

    Owner scoping is the application service's job (AD-014); these methods key on the
    ``(user_id, source_id)`` primary key. ``upsert`` is a last-write-wins
    ``INSERT ... ON CONFLICT DO UPDATE`` on that key, so two concurrent position writes
    never conflict — the later one overwrites with no error surfaced. Operates on the
    caller's ``Connection`` so the transaction boundary lives at the composition root.
    """

    def __init__(self, connection: Connection) -> None:
        self._conn = connection

    def get(self, user_id: UUID, source_id: UUID) -> ReadingPosition | None:
        row = self._conn.execute(
            select(
                reading_positions.c.anchor,
                reading_positions.c.percent,
                reading_positions.c.updated_at,
            )
            .where(reading_positions.c.user_id == user_id)
            .where(reading_positions.c.source_id == source_id)
        ).one_or_none()
        if row is None:
            return None
        return ReadingPosition(
            anchor=row.anchor, percent=row.percent, updated_at=row.updated_at
        )

    def upsert(
        self,
        user_id: UUID,
        source_id: UUID,
        *,
        anchor: str,
        percent: Decimal,
        updated_at: datetime,
    ) -> ReadingPosition:
        stmt = pg_insert(reading_positions).values(
            user_id=user_id,
            source_id=source_id,
            anchor=anchor,
            percent=percent,
            updated_at=updated_at,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[reading_positions.c.user_id, reading_positions.c.source_id],
            set_={
                "anchor": stmt.excluded.anchor,
                "percent": stmt.excluded.percent,
                "updated_at": stmt.excluded.updated_at,
            },
        ).returning(
            reading_positions.c.anchor,
            reading_positions.c.percent,
            reading_positions.c.updated_at,
        )
        row = self._conn.execute(stmt).one()
        return ReadingPosition(
            anchor=row.anchor, percent=row.percent, updated_at=row.updated_at
        )


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


# Every quiz_items column except ``embedding``: the 1536-dim vector exists only for
# generation-time dedup, so read models must not drag it across the wire (the overview
# is a 3 s polling target and the due queue returns up to 100 rows per request).
_QUIZ_ITEM_READ_COLUMNS = tuple(c for c in quiz_items.c if c.name != "embedding")


def _to_quiz_item(row) -> QuizItem:  # noqa: ANN001
    return QuizItem(
        id=row.id,
        source_id=row.source_id,
        item_type=row.item_type,
        question=row.question,
        answer=row.answer,
        section_path=tuple(row.section_path),
        anchor=row.anchor,
        source_excerpt=row.source_excerpt,
        chunk_hash=row.chunk_hash,
        content_key=row.content_key,
        status=row.status,
        generation_meta=row.generation_meta,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_scheduling(row) -> SchedulingSnapshot:  # noqa: ANN001
    return SchedulingSnapshot(
        state=row.state,
        step=row.step,
        stability=row.stability,
        difficulty=row.difficulty,
        due=row.due,
        last_review=row.last_review,
    )


def _to_quiz_job(row) -> QuizGenerationJob:  # noqa: ANN001
    return QuizGenerationJob(
        id=row.id,
        source_id=row.source_id,
        status=row.status,
        attempts=row.attempts,
        generated_count=row.generated_count,
        discarded_count=row.discarded_count,
        failed_sections=row.failed_sections,
        last_error=row.last_error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_note(row) -> Note:  # noqa: ANN001
    return Note(
        id=row.id,
        user_id=row.user_id,
        title=row.title,
        body_markdown=row.body_markdown,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_note_anchor(row) -> NoteAnchor:  # noqa: ANN001
    return NoteAnchor(
        id=row.id,
        note_id=row.note_id,
        source_id=row.source_id,
        source_title=row.source_title,
        anchor=row.anchor,
        section_path=tuple(row.section_path),
        block_hash=row.block_hash,
        block_ordinal=row.block_ordinal,
        start_offset=row.start_offset,
        end_offset=row.end_offset,
        quote_exact=row.quote_exact,
        quote_prefix=row.quote_prefix,
        quote_suffix=row.quote_suffix,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_anchor_block(row) -> AnchorBlockSnapshot:  # noqa: ANN001
    return AnchorBlockSnapshot(
        ordinal=row.position,
        content_hash=row.content_hash,
        html_fragment=row.html_fragment,
    )
