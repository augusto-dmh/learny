"""C3 gate — quiz-item reconciliation on re-ingestion (integration, live test DB).

Exercises ``ReconcileQuizItems`` against a freshly replaced corpus and pins the QUIZ-16
matrix (keep / stale / relocate / orphaned) plus its cardinal invariant: reconciliation
writes only ``anchor``/``section_path``/``status`` and never touches an item's
``quiz_item_scheduling`` or ``review_log`` rows. Runs on the rolled-back ``db_conn`` so
each case is isolated.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Connection, select

from app.application.quiz import ReconcileQuizItems
from app.application.quiz_qc import content_key
from app.domain.entities import (
    CorpusSectionRecord,
    ParsedBlock,
    ParsedSection,
    QuizItem,
    QuizItemStatus,
    QuizItemType,
    ReviewLogEntry,
    SchedulingSnapshot,
    SectionChunk,
    Source,
    User,
)
from app.infrastructure.db.metadata import quiz_item_scheduling, review_log
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemyQuizItemRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyUserRepository,
)
from tests.conftest import requires_db

pytestmark = requires_db


def _source(db_conn: Connection) -> Source:
    now = datetime.now(UTC)
    user = User(id=uuid4(), email=f"{uuid4()}@x.com", created_at=now)
    SqlAlchemyUserRepository(db_conn).add(user)
    source = Source(
        id=uuid4(),
        user_id=user.id,
        title="Book",
        filename="b.epub",
        content_type="application/epub+zip",
        byte_size=10,
        checksum="d" * 64,
        object_key=f"sources/{uuid4()}.epub",
        status="ready",
        created_at=now,
        updated_at=now,
    )
    return SqlAlchemySourceRepository(db_conn).add(source)


def _section(
    position: int, section_path: tuple[str, ...], anchor: str, text: str
) -> CorpusSectionRecord:
    return CorpusSectionRecord(
        section=ParsedSection(
            position=position,
            title=section_path[-1],
            depth=len(section_path),
            section_path=section_path,
            anchor=anchor,
            blocks=(ParsedBlock(position=0, block_type="paragraph", html_fragment="<p/>"),),
        ),
        markdown=text,
        chunks=(
            SectionChunk(
                index=0,
                text=text,
                section_path=section_path,
                anchor=anchor,
                page_span=None,
            ),
        ),
    )


# The replaced (v2) corpus: ch1 keeps the kept quote, ch2 dropped its quote, ch9 now
# carries the relocated quote, and there is no ch3/ch4 anymore.
_V2_SECTIONS = [
    _section(1, ("One",), "ch1", "The alpha beta section explains the core idea here."),
    _section(2, ("Two",), "ch2", "This chapter now covers unrelated material entirely."),
    _section(3, ("Later", "Nine"), "ch9", "A later part states epsilon zeta plainly here."),
]


def _item(
    source_id: UUID,
    *,
    question: str,
    anchor: str,
    section_path: tuple[str, ...],
    excerpt: str,
    status: str = QuizItemStatus.ACTIVE,
) -> QuizItem:
    now = datetime.now(UTC)
    return QuizItem(
        id=uuid4(),
        source_id=source_id,
        item_type=QuizItemType.FREE_RECALL,
        question=question,
        answer="A",
        section_path=section_path,
        anchor=anchor,
        source_excerpt=excerpt,
        chunk_hash="h" * 64,
        content_key=content_key(QuizItemType.FREE_RECALL, question, "A"),
        status=status,
        generation_meta={},
        created_at=now,
        updated_at=now,
    )


def _seed_item(repo: SqlAlchemyQuizItemRepository, item: QuizItem) -> None:
    repo.upsert(item, embedding=None)
    repo.create_scheduling(
        item.id,
        SchedulingSnapshot(
            state=1, step=0, stability=3.5, difficulty=5.0, due=item.created_at, last_review=None
        ),
    )
    repo.append_log(
        item.id, ReviewLogEntry(rating=3, reviewed_at=item.created_at, review_duration_ms=1200)
    )


def _reconcile(db_conn: Connection, source_id: UUID) -> None:
    ReconcileQuizItems(
        items=SqlAlchemyQuizItemRepository(db_conn),
        corpus=SqlAlchemyCorpusRepository(db_conn),
    )(source_id=source_id)


def _scheduling_row(db_conn: Connection, item_id: UUID):  # noqa: ANN202
    return (
        db_conn.execute(
            select(quiz_item_scheduling).where(quiz_item_scheduling.c.quiz_item_id == item_id)
        )
        .one()
        ._mapping
    )


def _log_rows(db_conn: Connection, item_id: UUID) -> list:
    return [
        row._mapping
        for row in db_conn.execute(
            select(review_log).where(review_log.c.quiz_item_id == item_id)
        ).all()
    ]


def test_reconcile_matrix_keep_stale_relocate_orphan(db_conn: Connection) -> None:
    source = _source(db_conn)
    SqlAlchemyCorpusRepository(db_conn).replace(
        source.id,
        title="Book",
        authors=["A"],
        language="en",
        schema_version=1,
        sections=_V2_SECTIONS,
    )
    repo = SqlAlchemyQuizItemRepository(db_conn)
    keep = _item(
        source.id, question="Q keep?", anchor="ch1", section_path=("One",), excerpt="alpha beta"
    )
    stale = _item(
        source.id, question="Q stale?", anchor="ch2", section_path=("Two",), excerpt="gamma delta"
    )
    relocate = _item(
        source.id,
        question="Q reloc?",
        anchor="ch3",
        section_path=("Three",),
        excerpt="epsilon zeta",
    )
    orphan = _item(
        source.id,
        question="Q orphan?",
        anchor="ch4",
        section_path=("Four",),
        excerpt="phrase not present",
    )
    for item in (keep, stale, relocate, orphan):
        _seed_item(repo, item)

    _reconcile(db_conn, source.id)

    # keep: anchor present, quote present → active, anchor/path unchanged.
    kept = repo.get_by_id(keep.id)
    assert (kept.status, kept.anchor, kept.section_path) == (
        QuizItemStatus.ACTIVE,
        "ch1",
        ("One",),
    )
    # stale: anchor present, quote gone → stale, anchor/path unchanged.
    staled = repo.get_by_id(stale.id)
    assert (staled.status, staled.anchor) == (QuizItemStatus.STALE, "ch2")
    # relocate: anchor gone, quote found in ch9 → active, adopts ch9's anchor + path.
    moved = repo.get_by_id(relocate.id)
    assert (moved.status, moved.anchor, moved.section_path) == (
        QuizItemStatus.ACTIVE,
        "ch9",
        ("Later", "Nine"),
    )
    # orphan: anchor gone, quote nowhere → orphaned, anchor/path unchanged.
    orphaned = repo.get_by_id(orphan.id)
    assert (orphaned.status, orphaned.anchor) == (QuizItemStatus.ORPHANED, "ch4")


def test_reconcile_never_touches_scheduling_or_review_log(db_conn: Connection) -> None:
    source = _source(db_conn)
    SqlAlchemyCorpusRepository(db_conn).replace(
        source.id,
        title="Book",
        authors=["A"],
        language="en",
        schema_version=1,
        sections=_V2_SECTIONS,
    )
    repo = SqlAlchemyQuizItemRepository(db_conn)
    # A relocated item (its quiz_items row *is* rewritten) — the strongest case that
    # scheduling/log stay untouched even when the item itself changes.
    relocate = _item(
        source.id,
        question="Q reloc?",
        anchor="ch3",
        section_path=("Three",),
        excerpt="epsilon zeta",
    )
    _seed_item(repo, relocate)
    before_sched = dict(_scheduling_row(db_conn, relocate.id))
    before_log = [dict(row) for row in _log_rows(db_conn, relocate.id)]

    _reconcile(db_conn, source.id)

    assert repo.get_by_id(relocate.id).anchor == "ch9"  # the item did change
    assert dict(_scheduling_row(db_conn, relocate.id)) == before_sched
    assert [dict(row) for row in _log_rows(db_conn, relocate.id)] == before_log


def test_reconcile_reactivates_stale_item_when_quote_returns(db_conn: Connection) -> None:
    source = _source(db_conn)
    SqlAlchemyCorpusRepository(db_conn).replace(
        source.id,
        title="Book",
        authors=["A"],
        language="en",
        schema_version=1,
        sections=_V2_SECTIONS,
    )
    repo = SqlAlchemyQuizItemRepository(db_conn)
    # Previously stale, but the anchor + quote are present in the new corpus.
    revived = _item(
        source.id,
        question="Q revive?",
        anchor="ch1",
        section_path=("One",),
        excerpt="alpha beta",
        status=QuizItemStatus.STALE,
    )
    _seed_item(repo, revived)

    _reconcile(db_conn, source.id)

    assert repo.get_by_id(revived.id).status == QuizItemStatus.ACTIVE


def test_reconcile_noop_when_source_has_no_items(db_conn: Connection) -> None:
    source = _source(db_conn)
    # No corpus, no items: the fast path returns without reading the corpus.
    _reconcile(db_conn, source.id)  # must not raise
    assert SqlAlchemyQuizItemRepository(db_conn).list_for_source(source.id) == []
