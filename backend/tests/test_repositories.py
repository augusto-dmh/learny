"""B3 gate — PostgreSQL repository adapters (integration, live test DB).

Exercises create/fetch for users, credentials, and sessions, and proves the
security-critical constraints: case-insensitive unique email, unique session
``token_hash``, and that only the token hash (never the raw token) is stored.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, func, insert, select
from sqlalchemy import delete as sa_delete
from sqlalchemy.exc import IntegrityError

from app.domain.entities import (
    CorpusSectionRecord,
    IngestionEvent,
    IngestionEventType,
    IngestionJob,
    IngestionStatus,
    ParsedBlock,
    ParsedSection,
    PasswordCredential,
    SectionChunk,
    Source,
    User,
)
from app.infrastructure.db.metadata import (
    corpus_blocks,
    corpus_chunks,
    corpus_documents,
    corpus_sections,
    sources,
)
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemyCredentialRepository,
    SqlAlchemyIngestionEventRepository,
    SqlAlchemyIngestionJobRepository,
    SqlAlchemySessionRepository,
    SqlAlchemySourceRepository,
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
