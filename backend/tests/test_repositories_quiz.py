"""B1 gate — quiz repository adapters (integration, live test DB).

Exercises the quiz-item and deck-job repositories against Postgres and pins the
correctness invariants this phase exists for: an upsert on ``(source_id,
content_key)`` updates content fields only and never touches the item's
``quiz_item_scheduling`` or ``review_log`` rows (QUIZ-02); the due queue joins
through ``sources`` for ownership and excludes other users, non-active items, and
future-due items (QUIZ-13/17); and the deck-job single-active guard is a query
(QUIZ-04).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, func, select

from app.application.quiz_qc import content_key
from app.domain.entities import (
    CorpusSectionRecord,
    ParsedBlock,
    ParsedSection,
    QuizGenerationJob,
    QuizItem,
    QuizItemStatus,
    QuizItemType,
    QuizJobStatus,
    ReviewLogEntry,
    SchedulingSnapshot,
    SectionChunk,
    Source,
    User,
)
from app.infrastructure.db.metadata import quiz_items, review_log
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemyQuizItemRepository,
    SqlAlchemyQuizJobRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyUserRepository,
)
from tests.conftest import requires_db

pytestmark = requires_db


# --- Fixtures / builders --------------------------------------------------------


def _persisted_source(db_conn: Connection, email: str, *, title: str = "A Book") -> Source:
    users = SqlAlchemyUserRepository(db_conn)
    sources = SqlAlchemySourceRepository(db_conn)
    now = datetime.now(UTC)
    user = User(id=uuid4(), email=email, created_at=now)
    users.add(user)
    source = Source(
        id=uuid4(),
        user_id=user.id,
        title=title,
        filename="a-book.epub",
        content_type="application/epub+zip",
        byte_size=1024,
        checksum="d" * 64,
        object_key=f"sources/{user.id}/{uuid4()}.epub",
        status="ready",
        created_at=now,
        updated_at=now,
    )
    return sources.add(source)


def _item(
    source_id: UUID,
    *,
    item_type: str = QuizItemType.FREE_RECALL,
    question: str = "What is the capital of France?",
    answer: str = "Paris",
    section_path: tuple[str, ...] = ("Chapter 1",),
    anchor: str = "ch01.xhtml",
    source_excerpt: str = "The capital of France is Paris.",
    chunk_hash: str = "c" * 64,
    status: str = QuizItemStatus.ACTIVE,
    generation_meta: dict | None = None,
) -> QuizItem:
    now = datetime.now(UTC)
    return QuizItem(
        id=uuid4(),
        source_id=source_id,
        item_type=item_type,
        question=question,
        answer=answer,
        section_path=section_path,
        anchor=anchor,
        source_excerpt=source_excerpt,
        chunk_hash=chunk_hash,
        content_key=content_key(item_type, question, answer),
        status=status,
        generation_meta=generation_meta or {},
        created_at=now,
        updated_at=now,
    )


def _snapshot(
    *,
    due: datetime,
    state: int = 1,
    step: int | None = 0,
    stability: float | None = 3.5,
    difficulty: float | None = 5.0,
    last_review: datetime | None = None,
) -> SchedulingSnapshot:
    return SchedulingSnapshot(
        state=state,
        step=step,
        stability=stability,
        difficulty=difficulty,
        due=due,
        last_review=last_review,
    )


def _section_record(
    *,
    position: int,
    title: str,
    depth: int,
    section_path: tuple[str, ...],
    anchor: str,
    chunk_texts: tuple[str, ...],
) -> CorpusSectionRecord:
    chunks = tuple(
        SectionChunk(
            index=index,
            text=text,
            section_path=section_path,
            anchor=anchor,
            page_span=None,
        )
        for index, text in enumerate(chunk_texts)
    )
    return CorpusSectionRecord(
        section=ParsedSection(
            position=position,
            title=title,
            depth=depth,
            section_path=section_path,
            anchor=anchor,
            blocks=(ParsedBlock(position=0, block_type="paragraph", html_fragment="<p/>"),),
        ),
        markdown="".join(chunk_texts),
        chunks=chunks,
    )


# --- upsert content-only + scheduling/log preservation (QUIZ-02) ----------------


def test_upsert_new_item_returns_true_and_persists(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-upsert-new@example.com")
    repo = SqlAlchemyQuizItemRepository(db_conn)
    item = _item(source.id)

    inserted = repo.upsert(item, embedding=None)

    assert inserted is True
    stored = repo.get_by_id(item.id)
    assert stored is not None
    assert stored.question == item.question
    assert stored.answer == item.answer
    assert stored.content_key == item.content_key
    assert stored.status == QuizItemStatus.ACTIVE


def test_upsert_same_content_key_updates_content_and_returns_false(
    db_conn: Connection,
) -> None:
    source = _persisted_source(db_conn, "quiz-upsert-conflict@example.com")
    repo = SqlAlchemyQuizItemRepository(db_conn)
    original = _item(source.id, source_excerpt="Old excerpt.", anchor="old.xhtml")
    repo.upsert(original, embedding=None)

    # Same type/question/answer → same content_key; changed snapshot fields.
    regenerated = _item(
        source.id,
        source_excerpt="New excerpt with more detail.",
        anchor="new.xhtml",
        chunk_hash="f" * 64,
        generation_meta={"model": "local-deterministic"},
    )
    assert regenerated.content_key == original.content_key

    inserted = repo.upsert(regenerated, embedding=None)

    assert inserted is False
    # Exactly one row for this (source, content_key) — no duplicate minted.
    total = db_conn.execute(
        select(func.count())
        .select_from(quiz_items)
        .where(quiz_items.c.source_id == source.id)
    ).scalar_one()
    assert total == 1
    stored = repo.get_by_id(original.id)  # the original row survives the upsert
    assert stored is not None
    assert stored.source_excerpt == "New excerpt with more detail."
    assert stored.anchor == "new.xhtml"
    assert stored.chunk_hash == "f" * 64
    assert stored.generation_meta == {"model": "local-deterministic"}


def test_reupsert_preserves_scheduling_and_review_log(db_conn: Connection) -> None:
    # QUIZ-02 cardinal invariant: regenerating an existing item must not reset the
    # learner's scheduling state or destroy their review history.
    source = _persisted_source(db_conn, "quiz-preserve@example.com")
    repo = SqlAlchemyQuizItemRepository(db_conn)
    item = _item(source.id)
    repo.upsert(item, embedding=None)

    due = datetime.now(UTC) - timedelta(hours=1)
    repo.create_scheduling(item.id, _snapshot(due=due, state=2, step=1))
    reviewed_at = datetime.now(UTC) - timedelta(minutes=30)
    repo.append_log(
        item.id, ReviewLogEntry(rating=3, reviewed_at=reviewed_at, review_duration_ms=4200)
    )
    scheduling_before = repo.get_scheduling(item.id)
    log_before = db_conn.execute(
        select(review_log.c.rating, review_log.c.reviewed_at, review_log.c.review_duration_ms)
        .where(review_log.c.quiz_item_id == item.id)
    ).all()

    # Re-upsert the same item with changed content.
    repo.upsert(
        _item(source.id, source_excerpt="Regenerated excerpt.", chunk_hash="e" * 64),
        embedding=None,
    )

    assert repo.get_scheduling(item.id) == scheduling_before
    log_after = db_conn.execute(
        select(review_log.c.rating, review_log.c.reviewed_at, review_log.c.review_duration_ms)
        .where(review_log.c.quiz_item_id == item.id)
    ).all()
    assert log_after == log_before
    assert [(row.rating, row.review_duration_ms) for row in log_after] == [(3, 4200)]


def test_upsert_stores_and_reads_back_embedding(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-embed@example.com")
    repo = SqlAlchemyQuizItemRepository(db_conn)
    embedded = _item(source.id, question="Embedded?", answer="Yes")
    plain = _item(source.id, question="Plain?", answer="No")
    repo.upsert(embedded, embedding=[0.25] * 1536)
    repo.upsert(plain, embedding=None)

    pairs = repo.existing_embeddings(source.id)

    assert [item_id for item_id, _ in pairs] == [embedded.id]
    vector = pairs[0][1]
    assert len(vector) == 1536
    assert vector[0] == pytest.approx(0.25)


# --- scheduling + review log ----------------------------------------------------


def test_scheduling_create_get_update_roundtrip(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-sched@example.com")
    repo = SqlAlchemyQuizItemRepository(db_conn)
    item = _item(source.id)
    repo.upsert(item, embedding=None)
    assert repo.get_scheduling(item.id) is None

    initial = _snapshot(due=datetime.now(UTC), state=1, step=0)
    repo.create_scheduling(item.id, initial)
    assert repo.get_scheduling(item.id) == initial

    later = datetime.now(UTC) + timedelta(days=3)
    advanced = _snapshot(
        due=later, state=2, step=None, stability=10.0, last_review=datetime.now(UTC)
    )
    repo.update_scheduling(item.id, advanced)
    assert repo.get_scheduling(item.id) == advanced


def test_get_by_id_and_get_scheduling_return_none_when_absent(db_conn: Connection) -> None:
    repo = SqlAlchemyQuizItemRepository(db_conn)
    assert repo.get_by_id(uuid4()) is None
    assert repo.get_scheduling(uuid4()) is None


# --- due queue (QUIZ-13/17, A-6) ------------------------------------------------


def _due_item(
    db_conn: Connection,
    repo: SqlAlchemyQuizItemRepository,
    source_id: UUID,
    *,
    due: datetime,
    status: str = QuizItemStatus.ACTIVE,
    question: str,
) -> QuizItem:
    item = _item(source_id, question=question, answer=f"answer to {question}", status=status)
    repo.upsert(item, embedding=None)
    repo.create_scheduling(item.id, _snapshot(due=due))
    return item


def test_due_for_user_returns_active_past_due_ordered_with_title(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-due@example.com", title="Due Book")
    repo = SqlAlchemyQuizItemRepository(db_conn)
    now = datetime.now(UTC)
    later = _due_item(db_conn, repo, source.id, due=now - timedelta(hours=1), question="Q late")
    earlier = _due_item(db_conn, repo, source.id, due=now - timedelta(hours=5), question="Q early")

    total, items = repo.due_for_user(source.user_id, now=now, limit=20)

    assert total == 2
    # A-6: due ASC — the earlier-due item comes first.
    assert [d.item.id for d in items] == [earlier.id, later.id]
    assert items[0].source_title == "Due Book"
    assert items[0].due == now - timedelta(hours=5)


def test_due_for_user_excludes_future_due(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-future@example.com")
    repo = SqlAlchemyQuizItemRepository(db_conn)
    now = datetime.now(UTC)
    _due_item(db_conn, repo, source.id, due=now - timedelta(hours=1), question="Q due")
    _due_item(db_conn, repo, source.id, due=now + timedelta(days=1), question="Q not yet")

    total, items = repo.due_for_user(source.user_id, now=now, limit=20)

    assert total == 1
    assert [d.item.question for d in items] == ["Q due"]


def test_due_for_user_excludes_stale_and_orphaned(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-status@example.com")
    repo = SqlAlchemyQuizItemRepository(db_conn)
    now = datetime.now(UTC)
    past = now - timedelta(hours=1)
    active = _due_item(db_conn, repo, source.id, due=past, question="Q active")
    _due_item(db_conn, repo, source.id, due=past, status=QuizItemStatus.STALE, question="Q stl")
    _due_item(db_conn, repo, source.id, due=past, status=QuizItemStatus.ORPHANED, question="Q orp")

    total, items = repo.due_for_user(source.user_id, now=now, limit=20)

    assert total == 1
    assert [d.item.id for d in items] == [active.id]


def test_due_for_user_isolates_other_users(db_conn: Connection) -> None:
    now = datetime.now(UTC)
    past = now - timedelta(hours=1)
    source_a = _persisted_source(db_conn, "quiz-owner-a@example.com")
    source_b = _persisted_source(db_conn, "quiz-owner-b@example.com")
    repo = SqlAlchemyQuizItemRepository(db_conn)
    mine = _due_item(db_conn, repo, source_a.id, due=past, question="Q mine")
    _due_item(db_conn, repo, source_b.id, due=past, question="Q theirs")

    total, items = repo.due_for_user(source_a.user_id, now=now, limit=20)

    assert total == 1
    assert [d.item.id for d in items] == [mine.id]


def test_due_for_user_respects_limit_but_counts_full_total(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-limit@example.com")
    repo = SqlAlchemyQuizItemRepository(db_conn)
    now = datetime.now(UTC)
    first = _due_item(db_conn, repo, source.id, due=now - timedelta(hours=3), question="Q1")
    second = _due_item(db_conn, repo, source.id, due=now - timedelta(hours=2), question="Q2")
    _due_item(db_conn, repo, source.id, due=now - timedelta(hours=1), question="Q3")

    total, items = repo.due_for_user(source.user_id, now=now, limit=2)

    assert total == 3
    assert [d.item.id for d in items] == [first.id, second.id]


def test_due_for_user_source_filter(db_conn: Connection) -> None:
    now = datetime.now(UTC)
    past = now - timedelta(hours=1)
    source_a = _persisted_source(db_conn, "quiz-src-filter@example.com")
    # Second source owned by the SAME user.
    sources = SqlAlchemySourceRepository(db_conn)
    source_b = sources.add(
        Source(
            id=uuid4(),
            user_id=source_a.user_id,
            title="Book B",
            filename="b.epub",
            content_type="application/epub+zip",
            byte_size=1,
            checksum="d" * 64,
            object_key=f"sources/{source_a.user_id}/{uuid4()}.epub",
            status="ready",
            created_at=now,
            updated_at=now,
        )
    )
    repo = SqlAlchemyQuizItemRepository(db_conn)
    in_a = _due_item(db_conn, repo, source_a.id, due=past, question="Q in A")
    _due_item(db_conn, repo, source_b.id, due=past, question="Q in B")

    total, items = repo.due_for_user(source_a.user_id, now=now, limit=20, source_id=source_a.id)

    assert total == 1
    assert [d.item.id for d in items] == [in_a.id]


def test_due_for_user_orders_ties_by_id(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-tie@example.com")
    repo = SqlAlchemyQuizItemRepository(db_conn)
    now = datetime.now(UTC)
    same_due = now - timedelta(hours=1)
    a = _due_item(db_conn, repo, source.id, due=same_due, question="Q A")
    b = _due_item(db_conn, repo, source.id, due=same_due, question="Q B")

    _total, items = repo.due_for_user(source.user_id, now=now, limit=20)

    expected = sorted([a.id, b.id])
    assert [d.item.id for d in items] == expected


# --- overview reads (QUIZ-14) ---------------------------------------------------


def test_list_for_source_returns_all_statuses(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-list@example.com")
    repo = SqlAlchemyQuizItemRepository(db_conn)
    active = _item(source.id, question="A", answer="1")
    stale = _item(source.id, question="B", answer="2", status=QuizItemStatus.STALE)
    repo.upsert(active, embedding=None)
    repo.upsert(stale, embedding=None)

    items = repo.list_for_source(source.id)

    assert {i.id for i in items} == {active.id, stale.id}


def test_counts_by_status(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-counts@example.com")
    repo = SqlAlchemyQuizItemRepository(db_conn)
    repo.upsert(_item(source.id, question="A", answer="1"), embedding=None)
    repo.upsert(_item(source.id, question="B", answer="2"), embedding=None)
    repo.upsert(
        _item(source.id, question="C", answer="3", status=QuizItemStatus.STALE), embedding=None
    )

    counts = repo.counts_by_status(source.id)

    assert counts == {QuizItemStatus.ACTIVE: 2, QuizItemStatus.STALE: 1}


def test_due_map(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-duemap@example.com")
    repo = SqlAlchemyQuizItemRepository(db_conn)
    now = datetime.now(UTC)
    item = _item(source.id)
    repo.upsert(item, embedding=None)
    repo.create_scheduling(item.id, _snapshot(due=now))

    mapping = repo.due_map(source.id)

    assert mapping == {item.id: now}


# --- reconciliation (QUIZ-16) ---------------------------------------------------


def test_update_reconciliation_touches_only_anchor_path_status(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-reconcile@example.com")
    repo = SqlAlchemyQuizItemRepository(db_conn)
    item = _item(source.id, anchor="orig.xhtml", section_path=("Old",))
    repo.upsert(item, embedding=None)
    due = datetime.now(UTC) - timedelta(hours=1)
    repo.create_scheduling(item.id, _snapshot(due=due, state=2))
    repo.append_log(item.id, ReviewLogEntry(rating=4, reviewed_at=due))
    scheduling_before = repo.get_scheduling(item.id)
    log_before = db_conn.execute(
        select(func.count()).select_from(review_log).where(review_log.c.quiz_item_id == item.id)
    ).scalar_one()

    repo.update_reconciliation(
        item.id, anchor="moved.xhtml", section_path=["New", "Sub"], status=QuizItemStatus.STALE
    )

    stored = repo.get_by_id(item.id)
    assert stored is not None
    assert stored.anchor == "moved.xhtml"
    assert stored.section_path == ("New", "Sub")
    assert stored.status == QuizItemStatus.STALE
    # Content fields untouched by reconciliation.
    assert stored.question == item.question
    assert stored.source_excerpt == item.source_excerpt
    # Scheduling + log rows byte-identical.
    assert repo.get_scheduling(item.id) == scheduling_before
    log_after = db_conn.execute(
        select(func.count()).select_from(review_log).where(review_log.c.quiz_item_id == item.id)
    ).scalar_one()
    assert log_after == log_before == 1


def test_items_for_reconcile_returns_all_items(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-reconcile-list@example.com")
    repo = SqlAlchemyQuizItemRepository(db_conn)
    a = _item(source.id, question="A", answer="1")
    b = _item(source.id, question="B", answer="2", status=QuizItemStatus.ORPHANED)
    repo.upsert(a, embedding=None)
    repo.upsert(b, embedding=None)

    items = repo.items_for_reconcile(source.id)

    assert {i.id for i in items} == {a.id, b.id}


# --- sections_for_generation (A-3) ----------------------------------------------


def test_sections_for_generation_returns_eligible_leaves(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-sections@example.com")
    corpus = SqlAlchemyCorpusRepository(db_conn)
    long_text = "Sentence one is here. " * 20  # ≥ 200 chars
    corpus.replace(
        source.id,
        title="Book",
        authors=("Author",),
        language="en",
        schema_version=1,
        sections=(
            # Parent (has a child that strictly extends its path) → not a leaf.
            _section_record(
                position=0,
                title="Part One",
                depth=0,
                section_path=("Part One",),
                anchor="part1.xhtml",
                chunk_texts=(long_text,),
            ),
            # Eligible leaf: long enough, no child path.
            _section_record(
                position=1,
                title="Chapter A",
                depth=1,
                section_path=("Part One", "Chapter A"),
                anchor="chA.xhtml",
                chunk_texts=("First chunk. ", long_text),
            ),
            # Leaf but too short → excluded (A-3).
            _section_record(
                position=2,
                title="Chapter B",
                depth=1,
                section_path=("Part One", "Chapter B"),
                anchor="chB.xhtml",
                chunk_texts=("Too short.",),
            ),
        ),
    )
    repo = SqlAlchemyQuizItemRepository(db_conn)

    sections = repo.sections_for_generation(source.id, min_chars=200)

    assert [s.title for s in sections] == ["Chapter A"]
    section = sections[0]
    assert section.anchor == "chA.xhtml"
    assert section.section_path == ("Part One", "Chapter A")
    # Chunks carried in reading order as (chunk_id, text) pairs.
    assert [text for _, text in section.chunks] == ["First chunk. ", long_text]
    assert all(isinstance(chunk_id, UUID) for chunk_id, _ in section.chunks)


def test_sections_for_generation_empty_without_corpus(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-nocorpus@example.com")
    repo = SqlAlchemyQuizItemRepository(db_conn)
    assert repo.sections_for_generation(source.id, min_chars=200) == []


# --- deck generation jobs (QUIZ-04/09) ------------------------------------------


def _job(source_id: UUID, *, status: str = QuizJobStatus.QUEUED) -> QuizGenerationJob:
    now = datetime.now(UTC)
    return QuizGenerationJob(
        id=uuid4(),
        source_id=source_id,
        status=status,
        attempts=0,
        generated_count=0,
        discarded_count=0,
        failed_sections=0,
        last_error=None,
        created_at=now,
        updated_at=now,
    )


def test_job_add_and_get_roundtrip(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-job-add@example.com")
    jobs = SqlAlchemyQuizJobRepository(db_conn)
    job = _job(source.id)

    jobs.add(job)

    stored = jobs.get_by_id(job.id)
    assert stored is not None
    assert stored.status == QuizJobStatus.QUEUED
    assert stored.generated_count == 0
    assert jobs.get_by_id(uuid4()) is None


def test_get_active_for_source_returns_queued_or_running(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-job-active@example.com")
    jobs = SqlAlchemyQuizJobRepository(db_conn)
    job = _job(source.id, status=QuizJobStatus.QUEUED)
    jobs.add(job)

    assert jobs.get_active_for_source(source.id).id == job.id

    running = job.started(datetime.now(UTC))
    jobs.update(running)
    assert jobs.get_active_for_source(source.id).id == job.id

    jobs.update(
        running.succeeded(
            datetime.now(UTC), generated_count=5, discarded_count=2, failed_sections=0
        )
    )
    assert jobs.get_active_for_source(source.id) is None


def test_get_active_for_source_none_when_only_terminal(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-job-terminal@example.com")
    jobs = SqlAlchemyQuizJobRepository(db_conn)
    jobs.add(_job(source.id, status=QuizJobStatus.FAILED))
    assert jobs.get_active_for_source(source.id) is None


def test_get_latest_for_source_returns_newest(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-job-latest@example.com")
    jobs = SqlAlchemyQuizJobRepository(db_conn)
    base = datetime.now(UTC)
    older = _job(source.id, status=QuizJobStatus.SUCCEEDED)
    older = QuizGenerationJob(**{**older.__dict__, "created_at": base - timedelta(hours=1)})
    newer = _job(source.id, status=QuizJobStatus.QUEUED)
    newer = QuizGenerationJob(**{**newer.__dict__, "created_at": base})
    jobs.add(older)
    jobs.add(newer)

    assert jobs.get_latest_for_source(source.id).id == newer.id
    assert jobs.get_latest_for_source(uuid4()) is None


def test_job_update_persists_counts_and_error(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-job-update@example.com")
    jobs = SqlAlchemyQuizJobRepository(db_conn)
    job = _job(source.id)
    jobs.add(job)

    running = job.started(datetime.now(UTC))
    jobs.update(
        running.succeeded(
            datetime.now(UTC), generated_count=7, discarded_count=3, failed_sections=1
        )
    )
    succeeded = jobs.get_by_id(job.id)
    assert succeeded.status == QuizJobStatus.SUCCEEDED
    assert succeeded.attempts == 1
    assert (succeeded.generated_count, succeeded.discarded_count, succeeded.failed_sections) == (
        7,
        3,
        1,
    )

    jobs.update(running.failed(datetime.now(UTC), "boom"))
    failed = jobs.get_by_id(job.id)
    assert failed.status == QuizJobStatus.FAILED
    assert failed.last_error == "boom"
