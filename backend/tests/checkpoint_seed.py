"""Seeding helpers shared by the checkpoint test modules.

Every helper writes through the real repositories on the caller's rolled-back
connection, so a test sees exactly the rows production code would.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import Connection, update

from app.application.quiz_qc import content_key
from app.domain.entities import (
    CorpusSectionRecord,
    ParsedBlock,
    ParsedSection,
    QuizItem,
    QuizItemOrigin,
    QuizItemStatus,
    QuizItemType,
    SchedulingSnapshot,
    SectionChunk,
    Source,
    User,
)
from app.infrastructure.db.metadata import sources
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemyQuizItemRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyUserRepository,
)

ANCHOR = "ch1.xhtml#s1"
TITLE = "The Division of Labour"
# Three distinct passages, so "least covered" has an unambiguous order.
CHUNKS = (
    "Pin making is divided into about eighteen distinct operations performed by different hands.",
    "Dexterity grows when each worker repeats a single simple operation all day long.",
    "Machines are invented by workers whose attention is fixed on one narrow task.",
)


def add_user(db_conn: Connection, email: str | None = None) -> User:
    return SqlAlchemyUserRepository(db_conn).add(
        User(id=uuid4(), email=email or f"{uuid4()}@example.test", created_at=datetime.now(UTC))
    )


def add_source(db_conn: Connection, owner_id: UUID, *, is_sample: bool = False) -> UUID:
    if is_sample:
        db_conn.execute(
            update(sources).where(sources.c.is_sample.is_(True)).values(is_sample=False)
        )
    now = datetime.now(UTC)
    source = Source(
        id=uuid4(),
        user_id=owner_id,
        title="The Wealth of Nations",
        filename="wealth.epub",
        content_type="application/epub+zip",
        byte_size=1024,
        checksum="d" * 64,
        object_key=f"sources/{owner_id}/{uuid4()}.epub",
        status="ready",
        created_at=now,
        updated_at=now,
        is_sample=is_sample,
    )
    return SqlAlchemySourceRepository(db_conn).add(source).id


def add_corpus(
    db_conn: Connection,
    source_id: UUID,
    *,
    sections: Sequence[tuple[str, str, Sequence[str]]] = ((ANCHOR, TITLE, CHUNKS),),
) -> None:
    """Replace the source's corpus with ``(anchor, title, chunk texts)`` sections."""
    records = []
    for position, (anchor, title, chunks) in enumerate(sections):
        markdown = "\n\n".join(chunks)
        section = ParsedSection(
            position=position,
            title=title,
            depth=1,
            section_path=("Book I", title),
            anchor=anchor,
            blocks=(ParsedBlock(position=0, block_type="paragraph", html_fragment=markdown),),
            anchor_aliases=(),
        )
        records.append(
            CorpusSectionRecord(
                section=section,
                markdown=markdown,
                chunks=tuple(
                    SectionChunk(
                        index=index,
                        text=text,
                        section_path=("Book I", title),
                        anchor=anchor,
                        page_span=None,
                    )
                    for index, text in enumerate(chunks)
                ),
                block_hashes=(f"hash-{anchor}-0",),
            )
        )
    SqlAlchemyCorpusRepository(db_conn).replace(
        source_id,
        title="The Wealth of Nations",
        authors=(),
        language="en",
        schema_version=1,
        sections=records,
    )


def add_card(
    db_conn: Connection,
    source_id: UUID,
    *,
    user_id: UUID | None = None,
    anchor: str = ANCHOR,
    question: str | None = None,
    answer: str | None = None,
    due: datetime | None = None,
    status: str = QuizItemStatus.ACTIVE,
    origin: str = QuizItemOrigin.DECK,
    flagged: bool = False,
) -> QuizItem:
    now = datetime.now(UTC)
    question = question or f"Question {uuid4()}?"
    answer = answer or f"Answer {uuid4()}"
    item = QuizItem(
        id=uuid4(),
        source_id=source_id,
        user_id=user_id,
        origin=origin,
        item_type=QuizItemType.FREE_RECALL,
        question=question,
        answer=answer,
        section_path=("Book I", TITLE),
        anchor=anchor,
        source_excerpt=CHUNKS[0],
        chunk_hash="c" * 64,
        content_key=content_key(QuizItemType.FREE_RECALL, question, answer),
        status=status,
        generation_meta={},
        created_at=now,
        updated_at=now,
    )
    repo = SqlAlchemyQuizItemRepository(db_conn)
    repo.upsert(item, embedding=None)
    if flagged:
        repo.set_flagged_at(item.id, now)
    repo.create_scheduling(
        item.id,
        SchedulingSnapshot(
            state=1,
            step=0,
            stability=None,
            difficulty=None,
            due=due or (now - timedelta(hours=1)),
            last_review=None,
        ),
    )
    return item
