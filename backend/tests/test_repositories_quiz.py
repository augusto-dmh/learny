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

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, func, select

from app.application.quiz_qc import content_key
from app.domain.entities import (
    CorpusSectionRecord,
    Note,
    NoteAnchor,
    NoteAnchorStatus,
    ParsedBlock,
    ParsedSection,
    QuizGenerationJob,
    QuizItem,
    QuizItemOrigin,
    QuizItemStatus,
    QuizItemType,
    QuizJobStatus,
    ReviewLogEntry,
    SchedulingSnapshot,
    SectionChunk,
    Source,
    User,
)
from app.infrastructure.db.metadata import note_anchors, quiz_items, review_log
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemyNoteRepository,
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
    anchor_aliases: tuple[str, ...] = (),
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
            anchor_aliases=anchor_aliases,
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


# --- section_for_anchor (quote-scoped generation, CAP-01) -----------------------


def _anchor_corpus(db_conn: Connection, source_id: UUID) -> None:
    """Seed a two-section corpus: a short parent leaf and an aliased child."""
    SqlAlchemyCorpusRepository(db_conn).replace(
        source_id,
        title="Book",
        authors=("Author",),
        language="en",
        schema_version=1,
        sections=(
            _section_record(
                position=0,
                title="Part One",
                depth=0,
                section_path=("Part One",),
                anchor="part1.xhtml",
                chunk_texts=("Short.",),
            ),
            _section_record(
                position=1,
                title="Chapter A",
                depth=1,
                section_path=("Part One", "Chapter A"),
                anchor="chA.xhtml",
                chunk_texts=("First chunk. ", "Second chunk."),
                anchor_aliases=("chA.xhtml#old",),
            ),
        ),
    )


def test_section_for_anchor_returns_the_cited_section_with_its_chunks(
    db_conn: Connection,
) -> None:
    source = _persisted_source(db_conn, "quiz-anchor-section@example.com")
    _anchor_corpus(db_conn, source.id)
    repo = SqlAlchemyQuizItemRepository(db_conn)

    section = repo.section_for_anchor(source.id, "chA.xhtml")

    assert section is not None
    assert section.title == "Chapter A"
    assert section.section_path == ("Part One", "Chapter A")
    # Chunks in reading order as (chunk_id, text) pairs, so a candidate's citation
    # can be constrained to them.
    assert [text for _, text in section.chunks] == ["First chunk. ", "Second chunk."]
    assert all(isinstance(chunk_id, UUID) for chunk_id, _ in section.chunks)


def test_section_for_anchor_resolves_a_merged_away_alias(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-anchor-alias@example.com")
    _anchor_corpus(db_conn, source.id)
    repo = SqlAlchemyQuizItemRepository(db_conn)

    section = repo.section_for_anchor(source.id, "chA.xhtml#old")

    assert section is not None
    # Resolves to the survivor under its canonical anchor (AD-085).
    assert section.anchor == "chA.xhtml"


def test_section_for_anchor_ignores_the_deck_eligibility_filters(
    db_conn: Connection,
) -> None:
    # A passage the student highlighted is eligible even in a non-leaf section far
    # below the deck path's ``min_chars`` floor.
    source = _persisted_source(db_conn, "quiz-anchor-short@example.com")
    _anchor_corpus(db_conn, source.id)
    repo = SqlAlchemyQuizItemRepository(db_conn)

    assert repo.sections_for_generation(source.id, min_chars=200) == []
    section = repo.section_for_anchor(source.id, "part1.xhtml")
    assert section is not None
    assert section.title == "Part One"


def test_section_for_anchor_is_none_for_an_unknown_anchor(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-anchor-missing@example.com")
    _anchor_corpus(db_conn, source.id)
    repo = SqlAlchemyQuizItemRepository(db_conn)

    assert repo.section_for_anchor(source.id, "gone.xhtml") is None


def test_section_for_anchor_is_scoped_to_its_own_source(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-anchor-scope-a@example.com")
    other = _persisted_source(db_conn, "quiz-anchor-scope-b@example.com")
    _anchor_corpus(db_conn, source.id)
    repo = SqlAlchemyQuizItemRepository(db_conn)

    assert repo.section_for_anchor(other.id, "chA.xhtml") is None


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


# --- origin-scoped identity: two modes in one table (CAP-13, CAP-14) ------------


def _persisted_anchor(
    db_conn: Connection, source: Source, *, title: str = "On attention", body: str = ""
) -> NoteAnchor:
    """Persist a note + one anchor on ``source``, owned by the source's owner."""
    notes = SqlAlchemyNoteRepository(db_conn)
    now = datetime.now(UTC)
    note = notes.add(
        Note(
            id=uuid4(),
            user_id=source.user_id,
            title=title,
            body_markdown=body,
            created_at=now,
            updated_at=now,
        )
    )
    return notes.add_anchor(
        NoteAnchor(
            id=uuid4(),
            note_id=note.id,
            source_id=source.id,
            source_title="A Book",
            anchor="ch01.xhtml",
            section_path=("Chapter 1",),
            block_hash="a" * 64,
            block_ordinal=1,
            start_offset=0,
            end_offset=10,
            quote_exact="the quoted sentence",
            quote_prefix="",
            quote_suffix="",
            status=NoteAnchorStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )


def _owner_of(db_conn: Connection, source: Source) -> UUID:
    return source.user_id


def _note_id_of_anchor(db_conn: Connection, anchor_id: UUID) -> UUID:
    return db_conn.execute(
        select(note_anchors.c.note_id).where(note_anchors.c.id == anchor_id)
    ).scalar_one()


def _highlight_item(
    source_id: UUID,
    note_anchor_id: UUID | None,
    *,
    question: str = "What is the capital of France?",
    answer: str = "Paris",
) -> QuizItem:
    return replace(
        _item(source_id, question=question, answer=answer),
        origin=QuizItemOrigin.HIGHLIGHT,
        note_anchor_id=note_anchor_id,
    )


def test_upsert_persists_origin_and_provenance(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-origin-persist@example.com")
    anchor = _persisted_anchor(db_conn, source)
    repo = SqlAlchemyQuizItemRepository(db_conn)
    item = _highlight_item(source.id, anchor.id)

    assert repo.upsert(item, embedding=None) is True

    stored = repo.get_by_id(item.id)
    assert stored.origin == QuizItemOrigin.HIGHLIGHT
    assert stored.note_anchor_id == anchor.id


def test_deck_items_default_to_deck_origin_with_no_provenance(
    db_conn: Connection,
) -> None:
    source = _persisted_source(db_conn, "quiz-origin-default@example.com")
    repo = SqlAlchemyQuizItemRepository(db_conn)
    item = _item(source.id)

    repo.upsert(item, embedding=None)

    stored = repo.get_by_id(item.id)
    assert stored.origin == QuizItemOrigin.DECK
    assert stored.note_anchor_id is None


def test_two_deck_items_with_one_content_key_collapse_to_one_row(
    db_conn: Connection,
) -> None:
    """The shipped deck upsert identity is unchanged by the origin split (CAP-13)."""
    source = _persisted_source(db_conn, "quiz-deck-collapse@example.com")
    repo = SqlAlchemyQuizItemRepository(db_conn)
    first = _item(source.id)
    second = _item(source.id, source_excerpt="Regenerated excerpt.")
    assert first.content_key == second.content_key

    assert repo.upsert(first, embedding=None) is True
    assert repo.upsert(second, embedding=None) is False

    stored = repo.list_for_source(source.id)
    assert len(stored) == 1
    assert stored[0].id == first.id  # the original row survived, keyed by content
    assert stored[0].source_excerpt == "Regenerated excerpt."


def test_two_highlight_items_share_a_content_key_across_different_anchors(
    db_conn: Connection,
) -> None:
    """THE origin-split invariant: the same sentence highlighted in two places is two
    cards. A global unique on (source_id, content_key) would collapse them (CAP-14)."""
    source = _persisted_source(db_conn, "quiz-highlight-distinct@example.com")
    first_anchor = _persisted_anchor(db_conn, source, title="First")
    second_anchor = _persisted_anchor(db_conn, source, title="Second")
    repo = SqlAlchemyQuizItemRepository(db_conn)
    first = _highlight_item(source.id, first_anchor.id)
    second = _highlight_item(source.id, second_anchor.id)
    assert first.content_key == second.content_key

    assert repo.upsert(first, embedding=None) is True
    assert repo.upsert(second, embedding=None) is True

    stored = {item.id for item in repo.list_for_source(source.id)}
    assert stored == {first.id, second.id}


def test_reaccepting_identical_text_from_one_anchor_is_idempotent(
    db_conn: Connection,
) -> None:
    """Double-submit protection lives in the database, not a disabled button."""
    source = _persisted_source(db_conn, "quiz-highlight-idempotent@example.com")
    anchor = _persisted_anchor(db_conn, source)
    repo = SqlAlchemyQuizItemRepository(db_conn)
    first = _highlight_item(source.id, anchor.id)
    duplicate = _highlight_item(source.id, anchor.id)
    assert first.id != duplicate.id

    assert repo.upsert(first, embedding=None) is True
    assert repo.upsert(duplicate, embedding=None) is False

    stored = repo.list_for_source(source.id)
    assert len(stored) == 1
    assert stored[0].id == first.id  # the id minted first is the stable identity


def test_highlight_item_does_not_collide_with_a_deck_item_of_the_same_key(
    db_conn: Connection,
) -> None:
    """Different origins never share an identity, even on one source (CAP-14)."""
    source = _persisted_source(db_conn, "quiz-cross-origin@example.com")
    anchor = _persisted_anchor(db_conn, source)
    repo = SqlAlchemyQuizItemRepository(db_conn)
    deck = _item(source.id)
    highlight = _highlight_item(source.id, anchor.id)
    assert deck.content_key == highlight.content_key

    assert repo.upsert(deck, embedding=None) is True
    assert repo.upsert(highlight, embedding=None) is True

    stored = {item.id: item.origin for item in repo.list_for_source(source.id)}
    assert stored == {deck.id: QuizItemOrigin.DECK, highlight.id: QuizItemOrigin.HIGHLIGHT}


def test_get_by_anchor_and_key_returns_the_accepted_card(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-anchor-lookup@example.com")
    anchor = _persisted_anchor(db_conn, source)
    repo = SqlAlchemyQuizItemRepository(db_conn)
    item = _highlight_item(source.id, anchor.id)
    repo.upsert(item, embedding=None)

    found = repo.get_by_anchor_and_key(anchor.id, item.content_key)

    assert found is not None
    assert found.id == item.id


def test_get_by_anchor_and_key_is_none_for_an_unaccepted_key(
    db_conn: Connection,
) -> None:
    source = _persisted_source(db_conn, "quiz-anchor-lookup-miss@example.com")
    anchor = _persisted_anchor(db_conn, source)
    repo = SqlAlchemyQuizItemRepository(db_conn)

    assert repo.get_by_anchor_and_key(anchor.id, "no-such-key") is None


def test_get_by_anchor_and_key_ignores_deck_items(db_conn: Connection) -> None:
    """A deck item that happens to share the key is not the accepted card."""
    source = _persisted_source(db_conn, "quiz-anchor-lookup-deck@example.com")
    anchor = _persisted_anchor(db_conn, source)
    repo = SqlAlchemyQuizItemRepository(db_conn)
    deck = _item(source.id)
    repo.upsert(deck, embedding=None)

    assert repo.get_by_anchor_and_key(anchor.id, deck.content_key) is None


# --- get_by_note_and_key: the re-promotion dedup read (NL-15) --------------------


def test_get_by_note_and_key_returns_the_promoted_card(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-note-lookup@example.com")
    note = _persisted_note(db_conn, source.user_id)
    repo = SqlAlchemyQuizItemRepository(db_conn)
    item = _note_item(source.user_id, note.id)
    repo.upsert(item, embedding=None)

    found = repo.get_by_note_and_key(note.id, item.content_key)

    assert found is not None
    assert found.id == item.id


def test_get_by_note_and_key_is_none_for_an_unpromoted_key(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-note-lookup-miss@example.com")
    note = _persisted_note(db_conn, source.user_id)
    repo = SqlAlchemyQuizItemRepository(db_conn)

    assert repo.get_by_note_and_key(note.id, "no-such-key") is None


def test_get_by_note_and_key_ignores_non_note_items(db_conn: Connection) -> None:
    """A deck item sharing the key is not a promoted note card (origin-scoped, NL-15)."""
    source = _persisted_source(db_conn, "quiz-note-lookup-deck@example.com")
    note = _persisted_note(db_conn, source.user_id)
    repo = SqlAlchemyQuizItemRepository(db_conn)
    deck = _item(source.id)
    repo.upsert(deck, embedding=None)

    assert repo.get_by_note_and_key(note.id, deck.content_key) is None


# --- update_text keeps identity, scheduling, and review log (CAP-12) ------------


def test_update_text_rewrites_content_and_keeps_the_row_id(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-update-text@example.com")
    anchor = _persisted_anchor(db_conn, source)
    repo = SqlAlchemyQuizItemRepository(db_conn)
    item = _highlight_item(source.id, anchor.id)
    repo.upsert(item, embedding=None)

    rewritten_key = content_key(item.item_type, "Reworded?", "Reworded answer")
    repo.update_text(
        item.id,
        question="Reworded?",
        answer="Reworded answer",
        content_key=rewritten_key,
    )

    stored = repo.get_by_id(item.id)
    assert stored.id == item.id  # identity is the minted id, not the content
    assert stored.question == "Reworded?"
    assert stored.answer == "Reworded answer"
    assert stored.content_key == rewritten_key
    # Provenance and origin are untouched by a text edit.
    assert stored.origin == QuizItemOrigin.HIGHLIGHT
    assert stored.note_anchor_id == anchor.id


def test_update_text_leaves_scheduling_and_review_log_byte_identical(
    db_conn: Connection,
) -> None:
    """Editing a card must cost none of its memory history (CAP-12) — asserted on the
    stored values, not on the absence of an exception."""
    source = _persisted_source(db_conn, "quiz-update-preserves@example.com")
    anchor = _persisted_anchor(db_conn, source)
    repo = SqlAlchemyQuizItemRepository(db_conn)
    item = _highlight_item(source.id, anchor.id)
    repo.upsert(item, embedding=None)

    due = datetime(2026, 8, 1, 12, tzinfo=UTC)
    reviewed = datetime(2026, 7, 19, 9, tzinfo=UTC)
    repo.create_scheduling(
        item.id,
        _snapshot(due=due, state=2, step=1, stability=7.25, difficulty=4.5,
                  last_review=reviewed),
    )
    repo.append_log(
        item.id, ReviewLogEntry(rating=3, reviewed_at=reviewed, review_duration_ms=1200)
    )
    before = repo.get_scheduling(item.id)
    log_before = db_conn.execute(
        select(review_log.c.rating, review_log.c.reviewed_at, review_log.c.review_duration_ms)
        .where(review_log.c.quiz_item_id == item.id)
    ).all()

    repo.update_text(
        item.id,
        question="Reworded?",
        answer="Reworded answer",
        content_key=content_key(item.item_type, "Reworded?", "Reworded answer"),
    )

    after = repo.get_scheduling(item.id)
    assert after == before
    assert after.due == due  # the value the student's memory schedule depends on
    assert after.state == 2
    assert after.stability == 7.25
    assert after.difficulty == 4.5
    assert after.last_review == reviewed
    log_after = db_conn.execute(
        select(review_log.c.rating, review_log.c.reviewed_at, review_log.c.review_duration_ms)
        .where(review_log.c.quiz_item_id == item.id)
    ).all()
    assert log_after == log_before
    assert len(log_after) == 1


# --- read models carry the new fields (CAP-10) ---------------------------------


def test_reconcile_and_list_reads_carry_origin_and_provenance(
    db_conn: Connection,
) -> None:
    source = _persisted_source(db_conn, "quiz-reads-carry@example.com")
    anchor = _persisted_anchor(db_conn, source)
    repo = SqlAlchemyQuizItemRepository(db_conn)
    deck = _item(source.id, question="Deck question?", answer="Deck answer")
    highlight = _highlight_item(source.id, anchor.id)
    repo.upsert(deck, embedding=None)
    repo.upsert(highlight, embedding=None)

    for read in (repo.list_for_source(source.id), repo.items_for_reconcile(source.id)):
        by_id = {item.id: item for item in read}
        assert by_id[deck.id].origin == QuizItemOrigin.DECK
        assert by_id[deck.id].note_anchor_id is None
        assert by_id[highlight.id].origin == QuizItemOrigin.HIGHLIGHT
        assert by_id[highlight.id].note_anchor_id == anchor.id


# --- due-queue provenance join is NULL-safe (CAP-15, CAP-16) --------------------


def test_due_queue_carries_origin_note_provenance(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "quiz-due-provenance@example.com")
    anchor = _persisted_anchor(db_conn, source, title="On attention")
    repo = SqlAlchemyQuizItemRepository(db_conn)
    item = _highlight_item(source.id, anchor.id)
    repo.upsert(item, embedding=None)
    now = datetime.now(UTC)
    repo.create_scheduling(item.id, _snapshot(due=now - timedelta(minutes=1)))

    total, due = repo.due_for_user(_owner_of(db_conn, source), now=now, limit=10)

    assert total == 1
    assert due[0].provenance is not None
    assert due[0].provenance.note_title == "On attention"


def test_due_queue_keeps_deck_cards_that_have_no_provenance(
    db_conn: Connection,
) -> None:
    """THE join-safety check: the provenance hops are OUTER joins, so a deck card —
    which has no anchor at all — must still appear in the due queue."""
    source = _persisted_source(db_conn, "quiz-due-deck-kept@example.com")
    repo = SqlAlchemyQuizItemRepository(db_conn)
    item = _item(source.id)
    repo.upsert(item, embedding=None)
    now = datetime.now(UTC)
    repo.create_scheduling(item.id, _snapshot(due=now - timedelta(minutes=1)))

    total, due = repo.due_for_user(_owner_of(db_conn, source), now=now, limit=10)

    assert total == 1
    assert [row.item.id for row in due] == [item.id]
    assert due[0].provenance is None


def test_deleting_the_origin_note_keeps_the_card_due_with_null_provenance(
    db_conn: Connection,
) -> None:
    """Deleting a note severs the link and nothing else: the card stays in the queue,
    keeps its own excerpt, and simply reports no provenance (CAP-15)."""
    source = _persisted_source(db_conn, "quiz-due-severed@example.com")
    anchor = _persisted_anchor(db_conn, source, title="Doomed note")
    repo = SqlAlchemyQuizItemRepository(db_conn)
    item = _highlight_item(source.id, anchor.id)
    repo.upsert(item, embedding=None)
    now = datetime.now(UTC)
    repo.create_scheduling(item.id, _snapshot(due=now - timedelta(minutes=1)))

    SqlAlchemyNoteRepository(db_conn).delete(_note_id_of_anchor(db_conn, anchor.id))

    total, due = repo.due_for_user(_owner_of(db_conn, source), now=now, limit=10)
    assert total == 1
    assert due[0].item.id == item.id
    assert due[0].provenance is None
    assert due[0].item.note_anchor_id is None
    assert due[0].item.source_excerpt == item.source_excerpt


def test_due_queue_mixes_deck_and_highlight_cards_without_dropping_either(
    db_conn: Connection,
) -> None:
    """The outer joins must not drop rows or inflate the total count."""
    source = _persisted_source(db_conn, "quiz-due-mixed@example.com")
    anchor = _persisted_anchor(db_conn, source, title="Mixed")
    repo = SqlAlchemyQuizItemRepository(db_conn)
    deck = _item(source.id, question="Deck question?", answer="Deck answer")
    highlight = _highlight_item(source.id, anchor.id)
    repo.upsert(deck, embedding=None)
    repo.upsert(highlight, embedding=None)
    now = datetime.now(UTC)
    repo.create_scheduling(deck.id, _snapshot(due=now - timedelta(minutes=2)))
    repo.create_scheduling(highlight.id, _snapshot(due=now - timedelta(minutes=1)))

    total, due = repo.due_for_user(_owner_of(db_conn, source), now=now, limit=10)

    assert total == 2
    assert {row.item.id for row in due} == {deck.id, highlight.id}
    by_id = {row.item.id: row.provenance for row in due}
    assert by_id[deck.id] is None
    assert by_id[highlight.id].note_title == "Mixed"


# --- note cards: source-less ownership by user_id (AD-148/149) ------------------


def _persisted_note(db_conn: Connection, user_id: UUID, *, title: str = "My note") -> Note:
    """Persist an empty note owned by ``user_id``."""
    now = datetime.now(UTC)
    return SqlAlchemyNoteRepository(db_conn).add(
        Note(
            id=uuid4(),
            user_id=user_id,
            title=title,
            body_markdown="",
            created_at=now,
            updated_at=now,
        )
    )


def _note_item(
    user_id: UUID,
    note_id: UUID | None,
    *,
    question: str = "What is spaced repetition?",
    answer: str = "Reviewing at increasing intervals.",
) -> QuizItem:
    """A source-less ``note`` card owned directly by ``user_id`` (AD-148/149)."""
    return replace(
        _item(None, question=question, answer=answer),
        source_id=None,
        origin=QuizItemOrigin.NOTE,
        user_id=user_id,
        note_id=note_id,
    )


def test_upsert_persists_a_source_less_note_card(db_conn: Connection) -> None:
    """A note card is owned by its user directly and carries no source (AD-148/149)."""
    source = _persisted_source(db_conn, "quiz-note-persist@example.com")
    note = _persisted_note(db_conn, source.user_id)
    repo = SqlAlchemyQuizItemRepository(db_conn)
    item = _note_item(source.user_id, note.id)

    assert repo.upsert(item, embedding=None) is True

    stored = repo.get_by_id(item.id)
    assert stored.origin == QuizItemOrigin.NOTE
    assert stored.source_id is None
    assert stored.user_id == source.user_id
    assert stored.note_id == note.id


def test_due_for_user_serves_source_less_note_cards_titled_your_notes(
    db_conn: Connection,
) -> None:
    """A note card with no source stays in the due queue and reads 'Your notes'."""
    source = _persisted_source(db_conn, "quiz-note-due@example.com")
    note = _persisted_note(db_conn, source.user_id)
    repo = SqlAlchemyQuizItemRepository(db_conn)
    item = _note_item(source.user_id, note.id)
    repo.upsert(item, embedding=None)
    now = datetime.now(UTC)
    repo.create_scheduling(item.id, _snapshot(due=now - timedelta(minutes=1)))

    total, due = repo.due_for_user(source.user_id, now=now, limit=10)

    assert total == 1
    assert due[0].item.id == item.id
    assert due[0].source_title == "Your notes"


def test_due_for_user_isolates_another_users_note_cards(db_conn: Connection) -> None:
    """Ownership is the card's own user_id now: a note card never leaks across users."""
    now = datetime.now(UTC)
    past = now - timedelta(minutes=1)
    owner = _persisted_source(db_conn, "quiz-note-owner@example.com")
    other = _persisted_source(db_conn, "quiz-note-other@example.com")
    note = _persisted_note(db_conn, owner.user_id)
    repo = SqlAlchemyQuizItemRepository(db_conn)
    mine = _note_item(owner.user_id, note.id)
    repo.upsert(mine, embedding=None)
    repo.create_scheduling(mine.id, _snapshot(due=past))

    total, due = repo.due_for_user(other.user_id, now=now, limit=10)

    assert total == 0
    assert due == []


def test_two_highlight_items_with_no_anchor_both_persist(db_conn: Connection) -> None:
    """A highlight row with a severed link matches neither partial index.

    Both partial uniques require a non-null ``note_anchor_id``, so these rows take the
    plain-insert branch with no conflict target. Two of them must coexist rather than
    silently collapsing: after a note is deleted its cards keep their own identity, and
    a conflict target that matched them would merge two students' distinct cards into
    one row.
    """
    repo = SqlAlchemyQuizItemRepository(db_conn)
    source = _persisted_source(db_conn, "quiz-null-anchor@example.com")

    first = _highlight_item(source.id, None)
    second = _highlight_item(source.id, None)
    assert first.content_key == second.content_key
    assert first.id != second.id

    assert repo.upsert(first, embedding=None) is True
    assert repo.upsert(second, embedding=None) is True

    stored = {item.id for item in repo.list_for_source(source.id)}
    assert stored == {first.id, second.id}
