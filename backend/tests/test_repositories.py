"""B3 gate — PostgreSQL repository adapters (integration, live test DB).

Exercises create/fetch for users, credentials, and sessions, and proves the
security-critical constraints: case-insensitive unique email, unique session
``token_hash``, and that only the token hash (never the raw token) is stored.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, func, insert, select, update
from sqlalchemy import delete as sa_delete
from sqlalchemy.exc import IntegrityError

from app.application.errors import TeachingTurnConflict
from app.domain.entities import (
    CorpusSectionRecord,
    Evidence,
    HistoryTurn,
    IngestionEvent,
    IngestionEventType,
    IngestionJob,
    IngestionStatus,
    ParsedBlock,
    ParsedSection,
    PasswordCredential,
    SectionChunk,
    Source,
    TeachingSession,
    TeachingTurn,
    User,
)
from app.infrastructure.db.metadata import (
    corpus_blocks,
    corpus_chunks,
    corpus_documents,
    corpus_sections,
    sources,
    teaching_turns,
)
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemyCredentialRepository,
    SqlAlchemyEmbeddingIndexRepository,
    SqlAlchemyIngestionEventRepository,
    SqlAlchemyIngestionJobRepository,
    SqlAlchemySessionRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyTeachingSessionRepository,
    SqlAlchemyTeachingTurnRepository,
    SqlAlchemyUserRepository,
)
from app.infrastructure.security.tokens import generate_token, hash_token
from tests.conftest import requires_db

pytestmark = requires_db


def _new_user(email: str) -> User:
    return User(id=uuid4(), email=email, created_at=datetime.now(UTC))


def _new_source(user_id: UUID, *, object_key: str, created_at: datetime | None = None) -> Source:
    now = created_at or datetime.now(UTC)
    return Source(
        id=uuid4(),
        user_id=user_id,
        title="A Book",
        filename="a-book.epub",
        content_type="application/epub+zip",
        byte_size=1024,
        checksum="d" * 64,
        object_key=object_key,
        status="uploaded",
        created_at=now,
        updated_at=now,
    )


def test_user_create_and_fetch(db_conn: Connection) -> None:
    repo = SqlAlchemyUserRepository(db_conn)
    user = _new_user("alice@example.com")
    repo.add(user)

    by_id = repo.get_by_id(user.id)
    by_email = repo.get_by_email("alice@example.com")
    assert by_id is not None and by_id.email == "alice@example.com"
    assert by_email is not None and by_email.id == user.id


def test_user_email_is_case_insensitive_unique(db_conn: Connection) -> None:
    repo = SqlAlchemyUserRepository(db_conn)
    repo.add(_new_user("Bob@Example.com"))
    # citext: lookup with different casing resolves the same row.
    assert repo.get_by_email("bob@example.com") is not None
    with pytest.raises(IntegrityError):
        repo.add(_new_user("bob@EXAMPLE.com"))


def test_get_missing_user_returns_none(db_conn: Connection) -> None:
    repo = SqlAlchemyUserRepository(db_conn)
    assert repo.get_by_id(uuid4()) is None
    assert repo.get_by_email("nobody@example.com") is None


def test_credential_create_fetch_update(db_conn: Connection) -> None:
    users = SqlAlchemyUserRepository(db_conn)
    creds = SqlAlchemyCredentialRepository(db_conn)
    user = _new_user("carol@example.com")
    users.add(user)

    cred = PasswordCredential(
        user_id=user.id,
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$abc$def",
        algo_params={"t": 3},
        updated_at=datetime.now(UTC),
    )
    creds.add(cred)
    fetched = creds.get_by_user_id(user.id)
    assert fetched is not None
    assert fetched.password_hash == cred.password_hash
    assert fetched.algo_params == {"t": 3}

    updated = PasswordCredential(
        user_id=user.id,
        password_hash="$argon2id$v=19$m=131072,t=4,p=4$ghi$jkl",
        algo_params={"t": 4},
        updated_at=datetime.now(UTC),
    )
    creds.update(updated)
    refetched = creds.get_by_user_id(user.id)
    assert refetched is not None and refetched.algo_params == {"t": 4}


def test_session_create_stores_only_token_hash(db_conn: Connection) -> None:
    users = SqlAlchemyUserRepository(db_conn)
    sessions = SqlAlchemySessionRepository(db_conn)
    user = _new_user("dave@example.com")
    users.add(user)

    raw = generate_token()
    created = sessions.create(
        user_id=user.id,
        raw_token=raw,
        csrf_token="csrf-123",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    # Persisted value is the hash, not the raw token.
    assert created.token_hash == hash_token(raw)
    assert created.token_hash != raw
    assert created.csrf_token == "csrf-123"

    resolved = sessions.get_by_raw_token(raw)
    assert resolved is not None and resolved.id == created.id
    assert sessions.get_by_raw_token("not-the-token") is None


def test_session_token_hash_unique(db_conn: Connection) -> None:
    users = SqlAlchemyUserRepository(db_conn)
    sessions = SqlAlchemySessionRepository(db_conn)
    user = _new_user("erin@example.com")
    users.add(user)

    raw = generate_token()
    sessions.create(
        user_id=user.id,
        raw_token=raw,
        csrf_token="c1",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    # Same raw token → same token_hash → unique constraint must reject.
    with pytest.raises(IntegrityError):
        sessions.create(
            user_id=user.id,
            raw_token=raw,
            csrf_token="c2",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )


def test_session_touch_and_delete(db_conn: Connection) -> None:
    users = SqlAlchemyUserRepository(db_conn)
    sessions = SqlAlchemySessionRepository(db_conn)
    user = _new_user("frank@example.com")
    users.add(user)

    raw = generate_token()
    created = sessions.create(
        user_id=user.id,
        raw_token=raw,
        csrf_token="c",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    later = datetime.now(UTC) + timedelta(minutes=5)
    sessions.touch(created.id, later)
    touched = sessions.get_by_raw_token(raw)
    assert touched is not None and touched.last_seen_at >= created.last_seen_at

    sessions.delete(created.id)
    assert sessions.get_by_raw_token(raw) is None


def test_source_add_and_get_by_id(db_conn: Connection) -> None:
    users = SqlAlchemyUserRepository(db_conn)
    sources = SqlAlchemySourceRepository(db_conn)
    user = _new_user("grace@example.com")
    users.add(user)

    source = _new_source(user.id, object_key=f"sources/{user.id}/{uuid4()}.epub")
    returned = sources.add(source)
    assert returned.id == source.id

    fetched = sources.get_by_id(source.id)
    assert fetched is not None
    assert fetched.object_key == source.object_key
    assert fetched.user_id == user.id
    assert fetched.byte_size == 1024
    assert fetched.checksum == "d" * 64
    assert fetched.status == "uploaded"


def test_source_get_missing_returns_none(db_conn: Connection) -> None:
    sources = SqlAlchemySourceRepository(db_conn)
    assert sources.get_by_id(uuid4()) is None


def test_source_list_by_user_is_newest_first(db_conn: Connection) -> None:
    users = SqlAlchemyUserRepository(db_conn)
    sources = SqlAlchemySourceRepository(db_conn)
    user = _new_user("heidi@example.com")
    users.add(user)

    base = datetime.now(UTC)
    older = _new_source(user.id, object_key=f"sources/{user.id}/{uuid4()}.epub", created_at=base)
    newer = _new_source(
        user.id,
        object_key=f"sources/{user.id}/{uuid4()}.epub",
        created_at=base + timedelta(minutes=1),
    )
    sources.add(older)
    sources.add(newer)

    listed = sources.list_by_user(user.id)
    assert [s.id for s in listed] == [newer.id, older.id]


def test_source_list_is_owner_scoped(db_conn: Connection) -> None:
    users = SqlAlchemyUserRepository(db_conn)
    sources = SqlAlchemySourceRepository(db_conn)
    alice = _new_user("ivan@example.com")
    bob = _new_user("judy@example.com")
    users.add(alice)
    users.add(bob)

    a1 = _new_source(alice.id, object_key=f"sources/{alice.id}/{uuid4()}.epub")
    a2 = _new_source(alice.id, object_key=f"sources/{alice.id}/{uuid4()}.epub")
    b1 = _new_source(bob.id, object_key=f"sources/{bob.id}/{uuid4()}.epub")
    for source in (a1, a2, b1):
        sources.add(source)

    alice_ids = {s.id for s in sources.list_by_user(alice.id)}
    assert alice_ids == {a1.id, a2.id}
    assert b1.id not in alice_ids
    assert [s.id for s in sources.list_by_user(bob.id)] == [b1.id]


def test_source_object_key_is_unique(db_conn: Connection) -> None:
    users = SqlAlchemyUserRepository(db_conn)
    sources = SqlAlchemySourceRepository(db_conn)
    user = _new_user("mallory@example.com")
    users.add(user)

    key = f"sources/{user.id}/{uuid4()}.epub"
    sources.add(_new_source(user.id, object_key=key))
    with pytest.raises(IntegrityError):
        sources.add(_new_source(user.id, object_key=key))


# ---- Ingestion job / event repositories -----------------------------------


def _persisted_source(db_conn: Connection, email: str) -> Source:
    users = SqlAlchemyUserRepository(db_conn)
    sources = SqlAlchemySourceRepository(db_conn)
    user = _new_user(email)
    users.add(user)
    source = _new_source(user.id, object_key=f"sources/{user.id}/{uuid4()}.epub")
    return sources.add(source)


def _new_job(
    source_id: UUID,
    *,
    status: str = IngestionStatus.QUEUED,
    attempts: int = 0,
    last_error: str | None = None,
    created_at: datetime | None = None,
) -> IngestionJob:
    now = created_at or datetime.now(UTC)
    return IngestionJob(
        id=uuid4(),
        source_id=source_id,
        status=status,
        attempts=attempts,
        last_error=last_error,
        created_at=now,
        updated_at=now,
    )


def test_ingestion_job_add_and_get_by_id(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "job-add@example.com")
    jobs = SqlAlchemyIngestionJobRepository(db_conn)

    job = _new_job(source.id)
    returned = jobs.add(job)
    assert returned.id == job.id

    fetched = jobs.get_by_id(job.id)
    assert fetched is not None
    assert fetched.source_id == source.id
    assert fetched.status == IngestionStatus.QUEUED
    assert fetched.attempts == 0
    assert fetched.last_error is None
    assert jobs.get_by_id(uuid4()) is None


def test_ingestion_job_get_latest_returns_newest(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "job-latest@example.com")
    jobs = SqlAlchemyIngestionJobRepository(db_conn)

    base = datetime.now(UTC)
    older = _new_job(source.id, status=IngestionStatus.SUCCEEDED, created_at=base)
    newer = _new_job(
        source.id,
        status=IngestionStatus.QUEUED,
        created_at=base + timedelta(minutes=1),
    )
    jobs.add(older)
    jobs.add(newer)

    latest = jobs.get_latest_for_source(source.id)
    assert latest is not None and latest.id == newer.id
    assert jobs.get_latest_for_source(uuid4()) is None


def test_ingestion_job_update_persists_transition(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "job-update@example.com")
    jobs = SqlAlchemyIngestionJobRepository(db_conn)
    job = jobs.add(_new_job(source.id))

    later = job.created_at + timedelta(seconds=5)
    jobs.update(job.started(later))
    running = jobs.get_by_id(job.id)
    assert running is not None
    assert running.status == IngestionStatus.RUNNING
    assert running.attempts == 1
    assert running.updated_at == later

    later2 = later + timedelta(seconds=5)
    jobs.update(running.failed(later2, "permanent boom"))
    failed = jobs.get_by_id(job.id)
    assert failed is not None
    assert failed.status == IngestionStatus.FAILED
    assert failed.last_error == "permanent boom"
    assert failed.updated_at == later2


def test_ingestion_job_second_active_is_rejected(db_conn: Connection) -> None:
    # ING-03: the partial unique index rejects a 2nd active job for one source.
    source = _persisted_source(db_conn, "job-active@example.com")
    jobs = SqlAlchemyIngestionJobRepository(db_conn)
    jobs.add(_new_job(source.id, status=IngestionStatus.QUEUED))

    with pytest.raises(IntegrityError):
        jobs.add(_new_job(source.id, status=IngestionStatus.RUNNING))


def test_ingestion_events_append_and_list_chronological(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "events@example.com")
    jobs = SqlAlchemyIngestionJobRepository(db_conn)
    events = SqlAlchemyIngestionEventRepository(db_conn)
    job = jobs.add(_new_job(source.id))

    base = datetime.now(UTC)
    events.append(
        IngestionEvent(
            id=uuid4(),
            job_id=job.id,
            type=IngestionEventType.QUEUED,
            message=None,
            created_at=base,
        )
    )
    events.append(
        IngestionEvent(
            id=uuid4(),
            job_id=job.id,
            type=IngestionEventType.STARTED,
            message=None,
            created_at=base + timedelta(seconds=1),
        )
    )
    events.append(
        IngestionEvent(
            id=uuid4(),
            job_id=job.id,
            type=IngestionEventType.FAILED,
            message="boom",
            created_at=base + timedelta(seconds=2),
        )
    )

    listed = events.list_for_job(job.id)
    assert [e.type for e in listed] == [
        IngestionEventType.QUEUED,
        IngestionEventType.STARTED,
        IngestionEventType.FAILED,
    ]
    assert listed[-1].message == "boom"
    assert events.list_for_job(uuid4()) == []


def test_source_set_status_updates_projection(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "set-status@example.com")
    sources_repo = SqlAlchemySourceRepository(db_conn)
    assert source.status == "uploaded"

    later = source.updated_at + timedelta(seconds=5)
    sources_repo.set_status(source.id, "processing", later)

    updated = sources_repo.get_by_id(source.id)
    assert updated is not None
    assert updated.status == "processing"
    assert updated.updated_at == later


# ---- Corpus repository ----------------------------------------------------


def _section_record(
    *,
    position: int,
    title: str,
    depth: int = 0,
    section_path: tuple[str, ...],
    anchor: str,
    markdown: str,
    blocks: tuple[ParsedBlock, ...] = (),
    chunks: tuple[SectionChunk, ...] = (),
) -> CorpusSectionRecord:
    return CorpusSectionRecord(
        section=ParsedSection(
            position=position,
            title=title,
            depth=depth,
            section_path=section_path,
            anchor=anchor,
            blocks=blocks,
        ),
        markdown=markdown,
        chunks=chunks,
    )


def test_corpus_replace_persists_full_aggregate(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "corpus-aggregate@example.com")
    repo = SqlAlchemyCorpusRepository(db_conn)

    record = _section_record(
        position=0,
        title="Chapter 1",
        depth=0,
        section_path=("Chapter 1",),
        anchor="chapter01.xhtml#sec-1",
        markdown="# Chapter 1\n\nHello world.",
        blocks=(
            ParsedBlock(position=0, block_type="heading", html_fragment="<h1>Chapter 1</h1>"),
            ParsedBlock(position=1, block_type="paragraph", html_fragment="<p>Hello world.</p>"),
        ),
        chunks=(
            SectionChunk(
                index=0,
                text="# Chapter 1\n\nHello world.",
                section_path=("Chapter 1",),
                anchor="chapter01.xhtml#sec-1",
                page_span=None,
            ),
        ),
    )
    repo.replace(
        source.id,
        title="A Book",
        authors=("Ada", "Grace"),
        language="en",
        schema_version=1,
        sections=(record,),
    )

    doc = db_conn.execute(
        select(corpus_documents).where(corpus_documents.c.source_id == source.id)
    ).one()
    assert doc.title == "A Book"
    assert doc.authors == ["Ada", "Grace"]
    assert doc.language == "en"
    assert doc.schema_version == 1

    section = db_conn.execute(
        select(corpus_sections).where(corpus_sections.c.document_id == doc.id)
    ).one()
    assert section.position == 0
    assert section.depth == 0
    assert section.title == "Chapter 1"
    assert section.section_path == ["Chapter 1"]
    assert section.anchor == "chapter01.xhtml#sec-1"
    assert section.markdown == "# Chapter 1\n\nHello world."

    blocks = db_conn.execute(
        select(corpus_blocks)
        .where(corpus_blocks.c.section_id == section.id)
        .order_by(corpus_blocks.c.position)
    ).all()
    assert [(b.position, b.block_type, b.html_fragment) for b in blocks] == [
        (0, "heading", "<h1>Chapter 1</h1>"),
        (1, "paragraph", "<p>Hello world.</p>"),
    ]

    chunk = db_conn.execute(
        select(corpus_chunks).where(corpus_chunks.c.section_id == section.id)
    ).one()
    assert chunk.chunk_index == 0
    assert chunk.text == "# Chapter 1\n\nHello world."
    assert chunk.section_path == ["Chapter 1"]
    assert chunk.anchor == "chapter01.xhtml#sec-1"
    assert chunk.page_span is None


@pytest.mark.parametrize(
    ("language", "expected_config"),
    [("pt", "portuguese"), ("en", "english"), (None, "simple"), ("xx", "simple")],
)
def test_corpus_replace_sets_language_search_config(
    db_conn: Connection, language: str | None, expected_config: str
) -> None:
    # EMB-11: every chunk row carries the regconfig resolved from the document
    # language — a Portuguese book's chunks get 'portuguese', an English book's
    # 'english', an unknown/absent language 'simple'.
    source = _persisted_source(db_conn, f"corpus-lang-{language}@example.com")
    repo = SqlAlchemyCorpusRepository(db_conn)
    record = _section_record(
        position=0,
        title="Capitulo",
        section_path=("Capitulo",),
        anchor="c1.xhtml",
        markdown="corpo",
        chunks=(
            SectionChunk(
                index=0,
                text="as criancas estavam correndo",
                section_path=("Capitulo",),
                anchor="c1.xhtml",
                page_span=None,
            ),
            SectionChunk(
                index=1,
                text="mais texto",
                section_path=("Capitulo",),
                anchor="c1.xhtml",
                page_span=None,
            ),
        ),
    )
    repo.replace(
        source.id,
        title="Livro",
        authors=(),
        language=language,
        schema_version=1,
        sections=(record,),
    )

    configs = db_conn.execute(
        select(corpus_chunks.c.search_config)
        .select_from(corpus_chunks)
        .join(corpus_sections, corpus_chunks.c.section_id == corpus_sections.c.id)
        .join(corpus_documents, corpus_sections.c.document_id == corpus_documents.c.id)
        .where(corpus_documents.c.source_id == source.id)
    ).scalars().all()
    assert configs == [expected_config, expected_config]


def test_corpus_replace_persists_zero_block_section(db_conn: Connection) -> None:
    # An empty-body spine doc yields a section with no blocks and no chunks; the
    # aggregate still persists the section row (edge case; CORP-04 markdown may be "").
    source = _persisted_source(db_conn, "corpus-empty@example.com")
    repo = SqlAlchemyCorpusRepository(db_conn)

    repo.replace(
        source.id,
        title=None,
        authors=(),
        language=None,
        schema_version=1,
        sections=(
            _section_record(
                position=0,
                title="Cover",
                section_path=("Cover",),
                anchor="cover.xhtml",
                markdown="",
            ),
        ),
    )

    doc = db_conn.execute(
        select(corpus_documents).where(corpus_documents.c.source_id == source.id)
    ).one()
    assert doc.title is None
    assert doc.authors == []
    assert doc.language is None
    section = db_conn.execute(
        select(corpus_sections).where(corpus_sections.c.document_id == doc.id)
    ).one()
    assert section.title == "Cover"
    assert section.markdown == ""
    assert (
        db_conn.execute(
            select(func.count()).select_from(corpus_blocks).where(
                corpus_blocks.c.section_id == section.id
            )
        ).scalar_one()
        == 0
    )
    assert (
        db_conn.execute(
            select(func.count()).select_from(corpus_chunks).where(
                corpus_chunks.c.section_id == section.id
            )
        ).scalar_one()
        == 0
    )


def test_corpus_replace_twice_leaves_single_corpus(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "corpus-replace@example.com")
    repo = SqlAlchemyCorpusRepository(db_conn)

    repo.replace(
        source.id,
        title="First",
        authors=(),
        language=None,
        schema_version=1,
        sections=(
            _section_record(
                position=0,
                title="Old",
                section_path=("Old",),
                anchor="old.xhtml",
                markdown="old",
                blocks=(
                    ParsedBlock(position=0, block_type="paragraph", html_fragment="<p>old</p>"),
                ),
                chunks=(
                    SectionChunk(
                        index=0,
                        text="old",
                        section_path=("Old",),
                        anchor="old.xhtml",
                        page_span=None,
                    ),
                ),
            ),
        ),
    )
    repo.replace(
        source.id,
        title="Second",
        authors=("Neo",),
        language="en",
        schema_version=1,
        sections=(
            _section_record(
                position=0, title="New A", section_path=("New A",), anchor="a.xhtml", markdown="a"
            ),
            _section_record(
                position=1, title="New B", section_path=("New B",), anchor="b.xhtml", markdown="b"
            ),
        ),
    )

    docs = db_conn.execute(
        select(corpus_documents).where(corpus_documents.c.source_id == source.id)
    ).all()
    assert len(docs) == 1
    assert docs[0].title == "Second"
    # The old section (and its cascaded blocks/chunks) is gone, not duplicated.
    old_sections = db_conn.execute(
        select(corpus_sections).where(corpus_sections.c.title == "Old")
    ).all()
    assert old_sections == []
    assert db_conn.execute(select(func.count()).select_from(corpus_blocks)).scalar_one() == 0
    assert db_conn.execute(select(func.count()).select_from(corpus_chunks)).scalar_one() == 0

    structure = repo.get_structure(source.id)
    assert structure is not None
    assert [s.title for s in structure.sections] == ["New A", "New B"]


def test_corpus_document_source_id_is_unique(db_conn: Connection) -> None:
    # The UNIQUE(source_id) backstop (CORP-09) rejects a second corpus for one source.
    source = _persisted_source(db_conn, "corpus-unique@example.com")
    db_conn.execute(
        insert(corpus_documents).values(
            id=uuid4(),
            source_id=source.id,
            title=None,
            authors=[],
            language=None,
            schema_version=1,
        )
    )
    with pytest.raises(IntegrityError):
        db_conn.execute(
            insert(corpus_documents).values(
                id=uuid4(),
                source_id=source.id,
                title=None,
                authors=[],
                language=None,
                schema_version=1,
            )
        )


def test_deleting_source_cascades_corpus(db_conn: Connection) -> None:
    # CORP-14: deleting the source row removes the whole corpus aggregate by FK cascade.
    source = _persisted_source(db_conn, "corpus-cascade@example.com")
    repo = SqlAlchemyCorpusRepository(db_conn)
    repo.replace(
        source.id,
        title="X",
        authors=("Author",),
        language="en",
        schema_version=1,
        sections=(
            _section_record(
                position=0,
                title="Ch",
                section_path=("Ch",),
                anchor="ch.xhtml",
                markdown="body",
                blocks=(
                    ParsedBlock(position=0, block_type="paragraph", html_fragment="<p>body</p>"),
                ),
                chunks=(
                    SectionChunk(
                        index=0,
                        text="body",
                        section_path=("Ch",),
                        anchor="ch.xhtml",
                        page_span=None,
                    ),
                ),
            ),
        ),
    )
    assert db_conn.execute(select(func.count()).select_from(corpus_documents)).scalar_one() == 1

    db_conn.execute(sa_delete(sources).where(sources.c.id == source.id))

    assert db_conn.execute(select(func.count()).select_from(corpus_documents)).scalar_one() == 0
    assert db_conn.execute(select(func.count()).select_from(corpus_sections)).scalar_one() == 0
    assert db_conn.execute(select(func.count()).select_from(corpus_blocks)).scalar_one() == 0
    assert db_conn.execute(select(func.count()).select_from(corpus_chunks)).scalar_one() == 0


def test_get_structure_returns_none_without_corpus(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "corpus-none@example.com")
    repo = SqlAlchemyCorpusRepository(db_conn)
    assert repo.get_structure(source.id) is None
    assert repo.get_structure(uuid4()) is None


def test_get_structure_returns_ordered_flat_sections(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "corpus-structure@example.com")
    repo = SqlAlchemyCorpusRepository(db_conn)
    # Insert out of position order to prove get_structure orders by position.
    repo.replace(
        source.id,
        title="Bk",
        authors=("Author",),
        language="en",
        schema_version=1,
        sections=(
            _section_record(
                position=1,
                title="Two",
                depth=1,
                section_path=("One", "Two"),
                anchor="c.xhtml#two",
                markdown="two",
            ),
            _section_record(
                position=0,
                title="One",
                depth=0,
                section_path=("One",),
                anchor="c.xhtml",
                markdown="one",
            ),
        ),
    )

    structure = repo.get_structure(source.id)
    assert structure is not None
    assert structure.title == "Bk"
    assert structure.authors == ("Author",)
    assert structure.language == "en"
    assert [
        (s.position, s.title, s.depth, s.section_path, s.anchor) for s in structure.sections
    ] == [
        (0, "One", 0, ("One",), "c.xhtml"),
        (1, "Two", 1, ("One", "Two"), "c.xhtml#two"),
    ]


# ---- Embedding-index repository (RET-09/11) -------------------------------


def _seed_two_chunk_corpus(db_conn: Connection, source_id: UUID) -> None:
    """Persist a 2-section corpus for embedding tests.

    Section 0 (position 0) carries chunks ``alpha``/``beta``; section 1
    (position 1) carries ``gamma`` — so reading-order is ``alpha, beta, gamma``
    across the section boundary.
    """
    SqlAlchemyCorpusRepository(db_conn).replace(
        source_id,
        title="Bk",
        authors=("Author",),
        language="en",
        schema_version=1,
        sections=(
            _section_record(
                position=0,
                title="One",
                section_path=("One",),
                anchor="one.xhtml",
                markdown="a\n\nb",
                chunks=(
                    SectionChunk(
                        index=0,
                        text="alpha text",
                        section_path=("One",),
                        anchor="one.xhtml",
                        page_span=None,
                    ),
                    SectionChunk(
                        index=1,
                        text="beta text",
                        section_path=("One",),
                        anchor="one.xhtml",
                        page_span=None,
                    ),
                ),
            ),
            _section_record(
                position=1,
                title="Two",
                section_path=("Two",),
                anchor="two.xhtml",
                markdown="c",
                chunks=(
                    SectionChunk(
                        index=0,
                        text="gamma text",
                        section_path=("Two",),
                        anchor="two.xhtml",
                        page_span=None,
                    ),
                ),
            ),
        ),
    )


def _unit_vector(index: int, value: float) -> list[float]:
    """A 1536-dim vector, all zeros except ``index`` = ``value``.

    Values are exactly representable in ``float4`` so a persist→read round-trip
    is bit-exact and equality assertions are stable.
    """
    vec = [0.0] * 1536
    vec[index] = value
    return vec


def test_embedding_index_chunks_for_source_returns_stable_order(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "embed-order@example.com")
    _seed_two_chunk_corpus(db_conn, source.id)

    chunks = SqlAlchemyEmbeddingIndexRepository(db_conn).chunks_for_source(source.id)

    # Ordered by section position then chunk_index (reading order across sections).
    assert [c.text for c in chunks] == ["alpha text", "beta text", "gamma text"]
    # Each ChunkToEmbed carries the persisted chunk id (distinct, for the write-back).
    assert len({c.id for c in chunks}) == 3


def test_embedding_index_chunks_for_source_is_source_scoped(db_conn: Connection) -> None:
    source_a = _persisted_source(db_conn, "embed-a@example.com")
    source_b = _persisted_source(db_conn, "embed-b@example.com")
    _seed_two_chunk_corpus(db_conn, source_a.id)
    SqlAlchemyCorpusRepository(db_conn).replace(
        source_b.id,
        title="Other",
        authors=(),
        language=None,
        schema_version=1,
        sections=(
            _section_record(
                position=0,
                title="X",
                section_path=("X",),
                anchor="x.xhtml",
                markdown="x",
                chunks=(
                    SectionChunk(
                        index=0,
                        text="other-source text",
                        section_path=("X",),
                        anchor="x.xhtml",
                        page_span=None,
                    ),
                ),
            ),
        ),
    )

    repo = SqlAlchemyEmbeddingIndexRepository(db_conn)
    a_texts = [c.text for c in repo.chunks_for_source(source_a.id)]

    # Only source A's chunks are read — no cross-source leakage.
    assert a_texts == ["alpha text", "beta text", "gamma text"]
    assert "other-source text" not in a_texts
    assert [c.text for c in repo.chunks_for_source(source_b.id)] == ["other-source text"]


def test_embedding_index_set_embeddings_persists_vectors(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "embed-write@example.com")
    _seed_two_chunk_corpus(db_conn, source.id)
    repo = SqlAlchemyEmbeddingIndexRepository(db_conn)
    chunks = repo.chunks_for_source(source.id)

    # A distinct exactly-representable vector per chunk, paired by chunk id.
    items = [(chunk.id, _unit_vector(i, float(i + 1))) for i, chunk in enumerate(chunks)]
    repo.set_embeddings(items, model="local-deterministic@1536")

    # Every chunk of the source now has a non-NULL embedding (RET-09 support).
    non_null = db_conn.execute(
        select(func.count())
        .select_from(corpus_chunks)
        .join(corpus_sections, corpus_chunks.c.section_id == corpus_sections.c.id)
        .join(corpus_documents, corpus_sections.c.document_id == corpus_documents.c.id)
        .where(corpus_documents.c.source_id == source.id)
        .where(corpus_chunks.c.embedding.isnot(None))
    ).scalar_one()
    assert non_null == 3

    # Each id reads back the exact vector AND the model string written (EMB-15).
    for chunk_id, expected in items:
        stored = db_conn.execute(
            select(corpus_chunks.c.embedding, corpus_chunks.c.embedding_model).where(
                corpus_chunks.c.id == chunk_id
            )
        ).one()
        assert stored.embedding is not None
        assert stored.embedding.tolist() == expected
        assert stored.embedding_model == "local-deterministic@1536"


def test_embedding_index_set_embeddings_replaces_existing(db_conn: Connection) -> None:
    # RET-11 support: a second write overwrites the prior vector (no stale value).
    source = _persisted_source(db_conn, "embed-replace@example.com")
    _seed_two_chunk_corpus(db_conn, source.id)
    repo = SqlAlchemyEmbeddingIndexRepository(db_conn)
    chunk_id = repo.chunks_for_source(source.id)[0].id

    repo.set_embeddings([(chunk_id, _unit_vector(0, 1.0))], model="local-deterministic@1536")
    repo.set_embeddings([(chunk_id, _unit_vector(0, 0.5))], model="local-deterministic@1536")

    stored = db_conn.execute(
        select(corpus_chunks.c.embedding).where(corpus_chunks.c.id == chunk_id)
    ).scalar_one()
    assert stored.tolist() == _unit_vector(0, 0.5)


def test_stale_chunks_for_source_selects_null_or_differing_model(db_conn: Connection) -> None:
    # EMB-17 selection: only NULL-embedding or stale-model chunks are returned, in
    # the same stable reading order as ``chunks_for_source`` (alpha, beta, gamma).
    source = _persisted_source(db_conn, "embed-stale@example.com")
    _seed_two_chunk_corpus(db_conn, source.id)
    repo = SqlAlchemyEmbeddingIndexRepository(db_conn)
    chunks = repo.chunks_for_source(source.id)
    ordered_ids = [c.id for c in chunks]
    model_x = "text-embedding-3-large@1536"

    # All embeddings NULL → every chunk is stale for any target model.
    assert [c.id for c in repo.stale_chunks_for_source(source.id, model_x)] == ordered_ids

    # Embed every chunk at model X → none stale for X, all stale for another model.
    repo.set_embeddings(
        [(c.id, _unit_vector(i, float(i + 1))) for i, c in enumerate(chunks)],
        model=model_x,
    )
    assert repo.stale_chunks_for_source(source.id, model_x) == []
    assert [c.id for c in repo.stale_chunks_for_source(source.id, "other@1")] == ordered_ids

    # Now blank one chunk's embedding back to NULL: exactly that chunk is stale for X.
    db_conn.execute(
        update(corpus_chunks)
        .where(corpus_chunks.c.id == ordered_ids[1])
        .values(embedding=None, embedding_model=None)
    )
    assert [c.id for c in repo.stale_chunks_for_source(source.id, model_x)] == [ordered_ids[1]]


# ---- Teaching session repository (TEACH-01/05/21) -------------------------


def _new_teaching_session(
    source_id: UUID,
    *,
    anchor: str = "chapter01.xhtml#sec-1",
    section_path: tuple[str, ...] = ("Chapter 1",),
    title: str = "Chapter 1",
    created_at: datetime | None = None,
) -> TeachingSession:
    now = created_at or datetime.now(UTC)
    return TeachingSession(
        id=uuid4(),
        source_id=source_id,
        target_anchor=anchor,
        target_section_path=section_path,
        target_title=title,
        created_at=now,
        updated_at=now,
    )


def _insert_turn(db_conn: Connection, session_id: UUID, turn_index: int) -> None:
    """Insert a minimal turn row so a session's turn_count is non-zero (B2 owns
    the turn repository; this exercises only the count in ``list_for_source``)."""
    db_conn.execute(
        insert(teaching_turns).values(
            id=uuid4(),
            session_id=session_id,
            turn_index=turn_index,
            message="m",
            answer_status="answered",
            answer_text="a",
            model="local-extractive",
            evidence_count=0,
            created_at=datetime.now(UTC),
        )
    )


def test_teaching_session_add_and_get_by_id(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "teach-session-add@example.com")
    repo = SqlAlchemyTeachingSessionRepository(db_conn)

    session = _new_teaching_session(
        source.id,
        anchor="chapter02.xhtml#s3",
        section_path=("Part I", "Chapter 2"),
        title="Chapter 2",
    )
    returned = repo.add(session)
    assert returned.id == session.id

    fetched = repo.get_by_id(session.id)
    assert fetched is not None
    assert fetched.source_id == source.id
    assert fetched.target_anchor == "chapter02.xhtml#s3"
    # section_path round-trips through JSONB back to a tuple (not a list).
    assert fetched.target_section_path == ("Part I", "Chapter 2")
    assert fetched.target_title == "Chapter 2"
    assert repo.get_by_id(uuid4()) is None


def test_teaching_session_list_for_source_is_newest_first(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "teach-session-order@example.com")
    repo = SqlAlchemyTeachingSessionRepository(db_conn)

    base = datetime.now(UTC)
    older = _new_teaching_session(source.id, created_at=base)
    newer = _new_teaching_session(source.id, created_at=base + timedelta(minutes=1))
    repo.add(older)
    repo.add(newer)

    listed = repo.list_for_source(source.id)
    assert [s.session.id for s in listed] == [newer.id, older.id]


def test_teaching_session_list_includes_turn_count(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "teach-session-count@example.com")
    repo = SqlAlchemyTeachingSessionRepository(db_conn)

    base = datetime.now(UTC)
    with_turns = _new_teaching_session(source.id, created_at=base + timedelta(minutes=1))
    without_turns = _new_teaching_session(source.id, created_at=base)
    repo.add(with_turns)
    repo.add(without_turns)
    _insert_turn(db_conn, with_turns.id, 0)
    _insert_turn(db_conn, with_turns.id, 1)

    summaries = {s.session.id: s.turn_count for s in repo.list_for_source(source.id)}
    assert summaries[with_turns.id] == 2
    assert summaries[without_turns.id] == 0


def test_teaching_session_list_is_source_scoped(db_conn: Connection) -> None:
    source_a = _persisted_source(db_conn, "teach-session-a@example.com")
    source_b = _persisted_source(db_conn, "teach-session-b@example.com")
    repo = SqlAlchemyTeachingSessionRepository(db_conn)

    a1 = _new_teaching_session(source_a.id)
    a2 = _new_teaching_session(source_a.id)
    b1 = _new_teaching_session(source_b.id)
    for session in (a1, a2, b1):
        repo.add(session)

    a_ids = {s.session.id for s in repo.list_for_source(source_a.id)}
    assert a_ids == {a1.id, a2.id}
    assert b1.id not in a_ids
    assert [s.session.id for s in repo.list_for_source(source_b.id)] == [b1.id]


# ---- Teaching turn repository (TEACH-07/14/17/20) -------------------------


def _persisted_session(db_conn: Connection, source_id: UUID) -> TeachingSession:
    session = _new_teaching_session(source_id)
    return SqlAlchemyTeachingSessionRepository(db_conn).add(session)


def _citation(
    source_id: UUID,
    *,
    anchor: str,
    snippet: str,
    score: float,
    section_path: tuple[str, ...] = ("Chapter 1",),
    chunk_id: UUID | None = None,
) -> Evidence:
    return Evidence(
        chunk_id=chunk_id or uuid4(),
        source_id=source_id,
        section_path=section_path,
        anchor=anchor,
        page_span=None,
        snippet=snippet,
        score=score,
    )


def _new_turn(
    session_id: UUID,
    *,
    turn_index: int,
    message: str = "explain this",
    answer_status: str = "answered",
    answer_text: str = "an answer",
    model: str = "local-extractive",
    citations: tuple[Evidence, ...] = (),
) -> TeachingTurn:
    return TeachingTurn(
        id=uuid4(),
        session_id=session_id,
        turn_index=turn_index,
        message=message,
        answer_status=answer_status,
        answer_text=answer_text,
        model=model,
        evidence_count=len(citations),
        citations=citations,
        created_at=datetime.now(UTC),
    )


def test_teaching_turn_add_and_list_with_ranked_citations(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "teach-turn-cites@example.com")
    session = _persisted_session(db_conn, source.id)
    repo = SqlAlchemyTeachingTurnRepository(db_conn)

    # Two citations in a deliberate order — rank is their tuple position.
    first = _citation(source.id, anchor="ch.xhtml#a", snippet="alpha", score=0.5)
    second = _citation(
        source.id,
        anchor="ch.xhtml#b",
        snippet="beta",
        score=0.25,
        section_path=("Chapter 1", "Section B"),
    )
    turn = _new_turn(session.id, turn_index=0, citations=(first, second))
    repo.add(turn)

    listed = repo.list_for_session(session.id)
    assert len(listed) == 1
    got = listed[0]
    assert got.id == turn.id
    assert got.turn_index == 0
    assert got.message == "explain this"
    assert got.answer_status == "answered"
    assert got.answer_text == "an answer"
    assert got.model == "local-extractive"
    assert got.evidence_count == 2
    # Citations round-trip in rank order, each field intact (source + page_span
    # are recovered from the session, not stored per-citation).
    assert [c.anchor for c in got.citations] == ["ch.xhtml#a", "ch.xhtml#b"]
    assert got.citations[0] == first
    assert got.citations[1] == second


def test_teaching_turn_list_orders_by_turn_index_and_persists_not_found(
    db_conn: Connection,
) -> None:
    source = _persisted_source(db_conn, "teach-turn-order@example.com")
    session = _persisted_session(db_conn, source.id)
    repo = SqlAlchemyTeachingTurnRepository(db_conn)

    answered = _new_turn(
        session.id,
        turn_index=1,
        citations=(_citation(source.id, anchor="ch.xhtml#a", snippet="alpha", score=0.5),),
    )
    # A not-found turn is still persisted with empty text and no citations (TEACH-14).
    not_found = _new_turn(
        session.id,
        turn_index=0,
        answer_status="not_found_in_source",
        answer_text="",
        citations=(),
    )
    # Add out of order to prove the list orders by turn_index ascending.
    repo.add(answered)
    repo.add(not_found)

    listed = repo.list_for_session(session.id)
    assert [t.turn_index for t in listed] == [0, 1]
    assert listed[0].answer_status == "not_found_in_source"
    assert listed[0].answer_text == ""
    assert listed[0].citations == ()
    assert listed[0].evidence_count == 0
    assert [c.anchor for c in listed[1].citations] == ["ch.xhtml#a"]


def test_teaching_turn_recent_history_counts_and_bounds(db_conn: Connection) -> None:
    # The turn path's read: total turn count plus the last N (message,
    # answer_text) pairs oldest-first, without loading citation payloads.
    source = _persisted_source(db_conn, "teach-turn-history@example.com")
    session = _persisted_session(db_conn, source.id)
    repo = SqlAlchemyTeachingTurnRepository(db_conn)

    repo.add(
        _new_turn(
            session.id,
            turn_index=0,
            message="message 0",
            answer_text="answer 0",
            citations=(
                _citation(source.id, anchor="ch.xhtml#a", snippet="alpha", score=0.5),
            ),
        )
    )
    repo.add(
        _new_turn(
            session.id,
            turn_index=1,
            message="message 1",
            answer_status="not_found_in_source",
            answer_text="",
        )
    )
    repo.add(
        _new_turn(session.id, turn_index=2, message="message 2", answer_text="answer 2")
    )

    total, history = repo.recent_history(session.id, 2)
    assert total == 3
    assert history == [
        HistoryTurn(message="message 1", response_text=""),
        HistoryTurn(message="message 2", response_text="answer 2"),
    ]

    # A limit beyond the stored turns returns everything, still oldest-first.
    total_all, history_all = repo.recent_history(session.id, 10)
    assert total_all == 3
    assert [h.message for h in history_all] == ["message 0", "message 1", "message 2"]


def test_teaching_turn_duplicate_index_raises_conflict(db_conn: Connection) -> None:
    # TEACH-17: the (session_id, turn_index) unique makes the racing loser 409.
    source = _persisted_source(db_conn, "teach-turn-race@example.com")
    session = _persisted_session(db_conn, source.id)
    repo = SqlAlchemyTeachingTurnRepository(db_conn)

    repo.add(_new_turn(session.id, turn_index=0))
    with pytest.raises(TeachingTurnConflict):
        repo.add(_new_turn(session.id, turn_index=0))


def test_teaching_turn_citations_survive_corpus_deletion(db_conn: Connection) -> None:
    # TEACH-20/AD-033: citations are snapshots (no chunk FK), so a corpus replace
    # (delete-then-insert) never breaks stored history.
    source = _persisted_source(db_conn, "teach-turn-snapshot@example.com")
    SqlAlchemyCorpusRepository(db_conn).replace(
        source.id,
        title="Bk",
        authors=(),
        language=None,
        schema_version=1,
        sections=(
            _section_record(
                position=0,
                title="Ch",
                section_path=("Ch",),
                anchor="ch.xhtml",
                markdown="body",
                chunks=(
                    SectionChunk(
                        index=0,
                        text="chunk text",
                        section_path=("Ch",),
                        anchor="ch.xhtml",
                        page_span=None,
                    ),
                ),
            ),
        ),
    )
    live_chunk_id = db_conn.execute(select(corpus_chunks.c.id)).scalar_one()

    session = _persisted_session(db_conn, source.id)
    repo = SqlAlchemyTeachingTurnRepository(db_conn)
    citation = _citation(
        source.id,
        anchor="ch.xhtml",
        snippet="chunk text",
        score=0.5,
        section_path=("Ch",),
        chunk_id=live_chunk_id,
    )
    repo.add(_new_turn(session.id, turn_index=0, citations=(citation,)))

    # Simulate re-ingestion: deleting the corpus document cascades its chunks away.
    db_conn.execute(sa_delete(corpus_documents).where(corpus_documents.c.source_id == source.id))
    assert db_conn.execute(
        select(func.count()).select_from(corpus_chunks).where(corpus_chunks.c.id == live_chunk_id)
    ).scalar_one() == 0

    # The citation snapshot is intact even though the live chunk is gone.
    listed = repo.list_for_session(session.id)
    assert len(listed) == 1
    assert listed[0].citations == (citation,)
