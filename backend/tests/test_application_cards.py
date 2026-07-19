"""Card-capture services (unit, in-memory fakes) — RFC-004 Cycle D.

Covers the passage-scoped use cases against the spec's acceptance criteria with no DB.
``SuggestCards`` is exercised through hand-built candidates so every QC discard branch
is asserted on what the caller receives (CAP-01..04, CAP-09), and the ownership legs pin
404 non-disclosure for a cross-owner or wrong-source anchor.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.application.cards import AcceptCard, SuggestCards, UpdateCard
from app.application.errors import (
    CardNotEditable,
    InvalidCardText,
    QuizItemNotFound,
    SourceNotFound,
    StaleCaptureTarget,
)
from app.application.identity import AuthorizeOwnership
from app.application.quiz_qc import content_key, normalize_text
from app.domain.entities import (
    Note,
    NoteAnchor,
    NoteAnchorStatus,
    QuizCandidate,
    QuizItem,
    QuizItemOrigin,
    QuizItemStatus,
    QuizItemType,
    QuizSection,
    SchedulingSnapshot,
    Source,
    User,
)
from tests.fakes import FakeClock, FakeNoteRepository, FakeSourceRepository

_NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)

_CHUNK_ID = uuid4()
_SECTION_TEXT = (
    "The mitochondria is the powerhouse of the cell. "
    "Chloroplasts capture light in plants."
)
_QUOTE = "The mitochondria is the powerhouse of the cell."


# --- fakes ----------------------------------------------------------------------


class FakeCardItemRepository:
    """In-memory ``QuizItemRepository`` slice the card services touch.

    ``section_for_anchor`` returns a preset section per anchor (``None`` for an anchor
    the corpus no longer resolves, the stale-target leg). ``upsert`` models the two
    partial unique indexes faithfully: a ``deck`` row collapses on
    ``(source_id, content_key)`` and a ``highlight`` row on
    ``(note_anchor_id, content_key)``, so a card minted with the wrong origin would
    collide with an unrelated deck row exactly as it would in Postgres.
    """

    def __init__(self, sections: dict[str, QuizSection] | None = None) -> None:
        self._sections = sections or {}
        self._by_key: dict[tuple, QuizItem] = {}
        self.embeddings: dict[UUID, list[float] | None] = {}
        self.scheduling: dict[UUID, SchedulingSnapshot] = {}
        self.update_text_calls = 0
        self.create_scheduling_calls = 0
        self.update_scheduling_calls = 0
        self.review_log: dict[UUID, list[int]] = {}

    def append_log(self, quiz_item_id: UUID, entry) -> None:  # noqa: ANN001
        self.review_log.setdefault(quiz_item_id, []).append(entry.rating)

    @staticmethod
    def _identity(item: QuizItem) -> tuple:
        if item.origin == QuizItemOrigin.HIGHLIGHT:
            return (QuizItemOrigin.HIGHLIGHT, item.note_anchor_id, item.content_key)
        return (QuizItemOrigin.DECK, item.source_id, item.content_key)

    def seed(self, item: QuizItem, embedding: list[float] | None = None) -> QuizItem:
        self._by_key[self._identity(item)] = item
        self.embeddings[item.id] = embedding
        self.scheduling[item.id] = _INITIAL
        return item

    def section_for_anchor(self, source_id: UUID, anchor: str) -> QuizSection | None:
        return self._sections.get(anchor)

    def upsert(self, item: QuizItem, *, embedding) -> bool:  # noqa: ANN001
        key = self._identity(item)
        inserted = key not in self._by_key
        if inserted:
            self._by_key[key] = item
        else:
            existing = self._by_key[key]
            self._by_key[key] = replace(
                item, id=existing.id, created_at=existing.created_at
            )
        self.embeddings[self._by_key[key].id] = (
            list(embedding) if embedding is not None else None
        )
        return inserted

    def get_by_anchor_and_key(
        self, note_anchor_id: UUID, content_key: str
    ) -> QuizItem | None:
        # Scoped to highlight origin: a deck row sharing the key is never returned.
        return self._by_key.get(
            (QuizItemOrigin.HIGHLIGHT, note_anchor_id, content_key)
        )

    def get_by_id(self, item_id: UUID) -> QuizItem | None:
        return next(
            (item for item in self._by_key.values() if item.id == item_id), None
        )

    def update_text(
        self, item_id: UUID, *, question: str, answer: str, content_key: str
    ) -> None:
        self.update_text_calls += 1
        for key, item in list(self._by_key.items()):
            if item.id != item_id:
                continue
            updated = replace(
                item, question=question, answer=answer, content_key=content_key
            )
            del self._by_key[key]
            self._by_key[self._identity(updated)] = updated

    def create_scheduling(self, quiz_item_id: UUID, snapshot: SchedulingSnapshot) -> None:
        self.create_scheduling_calls += 1
        self.scheduling[quiz_item_id] = snapshot

    def update_scheduling(self, quiz_item_id: UUID, snapshot: SchedulingSnapshot) -> None:
        self.update_scheduling_calls += 1
        self.scheduling[quiz_item_id] = snapshot

    def list_all(self) -> list[QuizItem]:
        """Test-only accessor for every persisted row."""
        return list(self._by_key.values())


_INITIAL = SchedulingSnapshot(
    state=1, step=0, stability=None, difficulty=None, due=_NOW, last_review=None
)


class FakeCardScheduling:
    """``SchedulingPort`` double whose ``initial`` returns a due-now snapshot."""

    def initial(self) -> SchedulingSnapshot:
        return _INITIAL

    def review(self, snapshot, rating, reviewed_at):  # noqa: ANN001, ANN201
        raise NotImplementedError


class FakeCardEmbedding:
    """``EmbeddingPort`` double returning one preset vector for every text."""

    model = "fake-embedding@2"

    def __init__(self, vector: list[float] | None = None) -> None:
        self._vector = vector or [1.0, 0.0]
        self.calls: list[list[str]] = []

    def embed_query(self, text: str) -> list[float]:
        return list(self._vector)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [list(self._vector) for _ in texts]


class FakeSuggestGeneration:
    """``QuizGenerationPort`` double: replays preset candidates, records the call."""

    model = "fake-generation@1"

    def __init__(self, candidates: list[QuizCandidate] | None = None) -> None:
        self._candidates = candidates or []
        self.calls: list[tuple[QuizSection, str, int]] = []

    def suggest_cards(self, section, quote, limit):  # noqa: ANN001, ANN201
        self.calls.append((section, quote, limit))
        return list(self._candidates)

    def begin_deck(self, sections):  # noqa: ANN001, ANN201
        raise NotImplementedError

    def collect_deck(self, handle):  # noqa: ANN001, ANN201
        raise NotImplementedError


# --- helpers --------------------------------------------------------------------


_OWNER = User(id=uuid4(), email="owner@example.com", created_at=_NOW)
_STRANGER = User(id=uuid4(), email="other@example.com", created_at=_NOW)


def _source(user_id: UUID) -> Source:
    return Source(
        id=uuid4(),
        user_id=user_id,
        title="Biology",
        filename="bio.epub",
        content_type="application/epub+zip",
        byte_size=10,
        checksum="a" * 64,
        object_key=f"sources/{uuid4()}.epub",
        status="ready",
        created_at=_NOW,
        updated_at=_NOW,
    )


def _section(anchor: str = "ch1#cells") -> QuizSection:
    return QuizSection(
        section_path=("Chapter 1", "Cells"),
        anchor=anchor,
        title="Cells",
        chunks=((_CHUNK_ID, _SECTION_TEXT),),
    )


def _anchor(note_id: UUID, source_id: UUID, *, anchor: str = "ch1#cells") -> NoteAnchor:
    return NoteAnchor(
        id=uuid4(),
        note_id=note_id,
        source_id=source_id,
        source_title="Biology",
        anchor=anchor,
        section_path=("Chapter 1", "Cells"),
        block_hash="b" * 64,
        block_ordinal=0,
        start_offset=0,
        end_offset=len(_QUOTE),
        quote_exact=_QUOTE,
        quote_prefix="",
        quote_suffix="",
        status=NoteAnchorStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _candidate(
    *,
    item_type: str = QuizItemType.FREE_RECALL,
    question: str = "What is the powerhouse of the cell?",
    answer: str = "The mitochondria",
    anchor_quote: str = _QUOTE,
) -> QuizCandidate:
    return QuizCandidate(
        item_type=item_type,
        question=question,
        answer=answer,
        source_chunk_id=_CHUNK_ID,
        anchor_quote=anchor_quote,
    )


class _World:
    """A seeded owner + ready source + captured highlight, wired to the services."""

    def __init__(
        self,
        *,
        candidates: list[QuizCandidate] | None = None,
        max_suggestions: int = 3,
        max_card_chars: int = 2000,
        anchor_resolves: bool = True,
        owner: User = _OWNER,
    ) -> None:
        self.sources = FakeSourceRepository()
        self.notes = FakeNoteRepository()
        self.source = _source(owner.id)
        self.sources.add(self.source)

        note = Note(
            id=uuid4(),
            user_id=owner.id,
            title="Cells",
            body_markdown="",
            created_at=_NOW,
            updated_at=_NOW,
        )
        self.notes.add(note)
        self.anchor = self.notes.add_anchor(_anchor(note.id, self.source.id))

        sections = {"ch1#cells": _section()} if anchor_resolves else {}
        self.items = FakeCardItemRepository(sections)
        self.generation = FakeSuggestGeneration(candidates)
        self.embeddings = FakeCardEmbedding()
        self.clock = FakeClock(_NOW)
        self.suggest = SuggestCards(
            sources=self.sources,
            notes=self.notes,
            items=self.items,
            generation=self.generation,
            authorize=AuthorizeOwnership(),
            max_suggestions=max_suggestions,
        )
        self.accept = AcceptCard(
            sources=self.sources,
            notes=self.notes,
            items=self.items,
            generation=self.generation,
            embeddings=self.embeddings,
            scheduling=FakeCardScheduling(),
            authorize=AuthorizeOwnership(),
            clock=self.clock,
            ids=uuid4,
            max_card_chars=max_card_chars,
        )
        self.update = UpdateCard(
            sources=self.sources,
            items=self.items,
            authorize=AuthorizeOwnership(),
            max_card_chars=max_card_chars,
        )


# --- SuggestCards: generation scoped to the quote (CAP-01, CAP-02) ---------------


def test_suggestions_are_scoped_to_the_highlighted_quote() -> None:
    world = _World(candidates=[_candidate()])

    result = world.suggest(
        user=_OWNER, source_id=world.source.id, note_anchor_id=world.anchor.id
    )

    assert len(result) == 1
    section, quote, limit = world.generation.calls[0]
    assert quote == _QUOTE
    assert section.anchor == "ch1#cells"
    assert limit == 3


def test_suggestions_are_capped_at_the_configured_maximum() -> None:
    # An adapter that over-returns must not widen the chip row (CAP-02).
    over_eager = [
        _candidate(question=f"Question {index}?") for index in range(6)
    ]
    world = _World(candidates=over_eager, max_suggestions=3)

    result = world.suggest(
        user=_OWNER, source_id=world.source.id, note_anchor_id=world.anchor.id
    )

    assert len(result) == 3


def test_nothing_is_persisted_by_generating_suggestions() -> None:
    # Suggestions are ephemeral (AD-134): generating writes no note and no anchor.
    world = _World(candidates=[_candidate()])

    world.suggest(
        user=_OWNER, source_id=world.source.id, note_anchor_id=world.anchor.id
    )

    assert world.notes.anchors_for_source(world.source.id) == [world.anchor]


# --- SuggestCards: QC filtering (CAP-03, CAP-04) ---------------------------------


def test_candidate_whose_quote_is_absent_from_the_section_is_discarded() -> None:
    grounded = _candidate()
    fabricated = _candidate(
        question="Who discovered ribosomes?",
        answer="Palade",
        anchor_quote="Ribosomes were discovered in 1955.",
    )
    world = _World(candidates=[grounded, fabricated])

    result = world.suggest(
        user=_OWNER, source_id=world.source.id, note_anchor_id=world.anchor.id
    )

    assert [c.question for c in result] == [grounded.question]


def test_cloze_candidate_with_an_invalid_mask_is_discarded() -> None:
    valid = _candidate(
        item_type=QuizItemType.CLOZE,
        question="The ____ is the powerhouse of the cell.",
        answer="mitochondria",
    )
    # The masked span is not in its own anchor quote — an invalid cloze (QUIZ-07).
    wrong_span = _candidate(
        item_type=QuizItemType.CLOZE,
        question="The ____ is the powerhouse of the cell.",
        answer="chloroplast",
    )
    # No blank at all — also invalid.
    no_blank = _candidate(
        item_type=QuizItemType.CLOZE,
        question="The mitochondria is the powerhouse of the cell.",
        answer="mitochondria",
    )
    world = _World(candidates=[valid, wrong_span, no_blank])

    result = world.suggest(
        user=_OWNER, source_id=world.source.id, note_anchor_id=world.anchor.id
    )

    assert [c.answer for c in result] == ["mitochondria"]


def test_candidate_of_an_unsupported_type_is_discarded() -> None:
    world = _World(candidates=[_candidate(item_type="multiple_choice")])

    result = world.suggest(
        user=_OWNER, source_id=world.source.id, note_anchor_id=world.anchor.id
    )

    assert result == []


def test_candidate_with_empty_text_is_discarded() -> None:
    world = _World(candidates=[_candidate(question="   "), _candidate(answer="")])

    result = world.suggest(
        user=_OWNER, source_id=world.source.id, note_anchor_id=world.anchor.id
    )

    assert result == []


def test_zero_surviving_candidates_is_an_empty_list_not_an_error() -> None:
    # "No cards for this passage" is an outcome, not a failure (spec edge case).
    world = _World(
        candidates=[_candidate(anchor_quote="Nothing in this book says that.")]
    )

    result = world.suggest(
        user=_OWNER, source_id=world.source.id, note_anchor_id=world.anchor.id
    )

    assert result == []


def test_generator_returning_nothing_is_an_empty_list_not_an_error() -> None:
    world = _World(candidates=[])

    result = world.suggest(
        user=_OWNER, source_id=world.source.id, note_anchor_id=world.anchor.id
    )

    assert result == []


# --- SuggestCards: ownership and staleness (CAP-09, edge cases) ------------------


def test_anchor_whose_note_belongs_to_another_user_is_not_found() -> None:
    # The caller owns the source but not the highlight: a 404, never a 403 or a leak.
    world = _World(candidates=[_candidate()])
    stranger_note = Note(
        id=uuid4(),
        user_id=_STRANGER.id,
        title="Theirs",
        body_markdown="",
        created_at=_NOW,
        updated_at=_NOW,
    )
    world.notes.add(stranger_note)
    foreign = world.notes.add_anchor(_anchor(stranger_note.id, world.source.id))

    with pytest.raises(QuizItemNotFound):
        world.suggest(
            user=_OWNER, source_id=world.source.id, note_anchor_id=foreign.id
        )

    assert world.generation.calls == []


def test_anchor_belonging_to_a_different_source_is_not_found() -> None:
    world = _World(candidates=[_candidate()])
    other_source = _source(_OWNER.id)
    world.sources.add(other_source)
    foreign = world.notes.add_anchor(
        replace(_anchor(uuid4(), other_source.id), id=uuid4())
    )

    with pytest.raises(QuizItemNotFound):
        world.suggest(
            user=_OWNER, source_id=world.source.id, note_anchor_id=foreign.id
        )


def test_unknown_anchor_is_not_found() -> None:
    world = _World(candidates=[_candidate()])

    with pytest.raises(QuizItemNotFound):
        world.suggest(
            user=_OWNER, source_id=world.source.id, note_anchor_id=uuid4()
        )


def test_anchor_whose_section_no_longer_resolves_is_a_stale_target() -> None:
    world = _World(candidates=[_candidate()], anchor_resolves=False)

    with pytest.raises(StaleCaptureTarget):
        world.suggest(
            user=_OWNER, source_id=world.source.id, note_anchor_id=world.anchor.id
        )


def test_another_users_source_is_not_found_and_generates_nothing() -> None:
    world = _World(candidates=[_candidate()])

    with pytest.raises(SourceNotFound):
        world.suggest(
            user=_STRANGER,
            source_id=world.source.id,
            note_anchor_id=world.anchor.id,
        )

    assert world.generation.calls == []


# --- AcceptCard: minting one card (CAP-05, CAP-10, CAP-11) ----------------------


def _deck_item(source_id: UUID, *, item_type: str, question: str, answer: str) -> QuizItem:
    """A whole-deck item, built the way ``RunDeckGeneration`` builds one."""
    return QuizItem(
        id=uuid4(),
        source_id=source_id,
        item_type=item_type,
        question=question,
        answer=answer,
        section_path=("Chapter 1", "Cells"),
        anchor="ch1#cells",
        source_excerpt=_QUOTE,
        chunk_hash="c" * 64,
        content_key=content_key(item_type, question, answer),
        status=QuizItemStatus.ACTIVE,
        generation_meta={"model": "fake-generation@1"},
        created_at=_NOW,
        updated_at=_NOW,
    )


def test_accepting_persists_exactly_one_card_due_immediately() -> None:
    world = _World()

    item, created = world.accept(
        user=_OWNER,
        source_id=world.source.id,
        note_anchor_id=world.anchor.id,
        item_type=QuizItemType.FREE_RECALL,
        question="What is the powerhouse of the cell?",
        answer="The mitochondria",
    )

    assert created is True
    assert len(world.items.list_all()) == 1
    # Its initial scheduling exists and is due at acceptance time (CAP-05).
    assert world.items.scheduling[item.id].due == _NOW


def test_accepted_card_records_highlight_origin_and_provenance() -> None:
    world = _World()

    item, _ = world.accept(
        user=_OWNER,
        source_id=world.source.id,
        note_anchor_id=world.anchor.id,
        item_type=QuizItemType.FREE_RECALL,
        question="What is the powerhouse of the cell?",
        answer="The mitochondria",
    )

    assert item.origin == QuizItemOrigin.HIGHLIGHT
    assert item.note_anchor_id == world.anchor.id


def test_accepted_card_does_not_collide_with_a_deck_card_of_the_same_text() -> None:
    # The identity guard that origin exists for: a deck row with the identical
    # content key must not swallow the accepted card (CAP-13/14).
    world = _World()
    question, answer = "What is the powerhouse of the cell?", "The mitochondria"
    world.items.seed(
        _deck_item(
            world.source.id,
            item_type=QuizItemType.FREE_RECALL,
            question=question,
            answer=answer,
        )
    )

    item, created = world.accept(
        user=_OWNER,
        source_id=world.source.id,
        note_anchor_id=world.anchor.id,
        item_type=QuizItemType.FREE_RECALL,
        question=question,
        answer=answer,
    )

    assert created is True
    stored = world.items.list_all()
    assert len(stored) == 2
    assert {i.origin for i in stored} == {QuizItemOrigin.DECK, QuizItemOrigin.HIGHLIGHT}
    assert item.id != next(i.id for i in stored if i.origin == QuizItemOrigin.DECK)


def test_accepted_card_snapshots_its_citation_from_the_highlight() -> None:
    world = _World()

    item, _ = world.accept(
        user=_OWNER,
        source_id=world.source.id,
        note_anchor_id=world.anchor.id,
        item_type=QuizItemType.FREE_RECALL,
        question="What is the powerhouse of the cell?",
        answer="The mitochondria",
    )

    # Renderable from its own snapshot even once provenance is severed (CAP-15).
    assert item.anchor == world.anchor.anchor
    assert item.section_path == world.anchor.section_path
    assert item.source_excerpt == _QUOTE
    assert item.chunk_hash == hashlib.sha256(
        normalize_text(_QUOTE).encode("utf-8")
    ).hexdigest()
    assert item.status == QuizItemStatus.ACTIVE
    assert item.generation_meta == {"model": "fake-generation@1"}


def test_accepting_stores_the_edited_text_not_the_suggested_text() -> None:
    world = _World()

    item, _ = world.accept(
        user=_OWNER,
        source_id=world.source.id,
        note_anchor_id=world.anchor.id,
        item_type=QuizItemType.FREE_RECALL,
        question="Which organelle produces the cell's energy?",
        answer="The mitochondria",
    )

    assert item.question == "Which organelle produces the cell's energy?"
    assert world.items.get_by_id(item.id).question == item.question


def test_discarding_a_suggestion_persists_nothing() -> None:
    # Discard is the absence of an accept: nothing is written for it (CAP-07).
    world = _World(candidates=[_candidate()])

    world.suggest(
        user=_OWNER, source_id=world.source.id, note_anchor_id=world.anchor.id
    )

    assert world.items.list_all() == []


# --- AcceptCard: embeddings without dedup (CAP-A5 / AD-138) ---------------------


def test_accepting_stores_the_embedding() -> None:
    world = _World()

    item, _ = world.accept(
        user=_OWNER,
        source_id=world.source.id,
        note_anchor_id=world.anchor.id,
        item_type=QuizItemType.FREE_RECALL,
        question="What is the powerhouse of the cell?",
        answer="The mitochondria",
    )

    # Stored so future deck generation dedups against this card.
    assert world.items.embeddings[item.id] == [1.0, 0.0]


def test_a_near_duplicate_of_an_existing_card_is_still_accepted() -> None:
    # The deliberate asymmetry: dedup protects bulk generation, never overrules an
    # explicit acceptance (CAP-A5). The fake embeds every text identically, so an
    # applied dedup guard would discard this card.
    world = _World()
    world.items.seed(
        _deck_item(
            world.source.id,
            item_type=QuizItemType.FREE_RECALL,
            question="What is the powerhouse of the cell?",
            answer="The mitochondria",
        ),
        embedding=[1.0, 0.0],
    )

    item, created = world.accept(
        user=_OWNER,
        source_id=world.source.id,
        note_anchor_id=world.anchor.id,
        item_type=QuizItemType.FREE_RECALL,
        question="Which organelle is the powerhouse of the cell?",
        answer="The mitochondria",
    )

    assert created is True
    assert world.items.get_by_id(item.id) is not None


# --- AcceptCard: idempotent re-accept (double submit) ---------------------------


def test_accepting_the_same_text_twice_yields_one_card() -> None:
    world = _World()
    payload = {
        "user": _OWNER,
        "source_id": world.source.id,
        "note_anchor_id": world.anchor.id,
        "item_type": QuizItemType.FREE_RECALL,
        "question": "What is the powerhouse of the cell?",
        "answer": "The mitochondria",
    }

    first, first_created = world.accept(**payload)
    second, second_created = world.accept(**payload)

    assert first_created is True
    assert second_created is False
    assert second.id == first.id
    assert len(world.items.list_all()) == 1


def test_the_same_text_from_a_different_highlight_is_a_distinct_card() -> None:
    # Two highlights of the same sentence are two cards (CAP-14).
    world = _World()
    other_anchor = world.notes.add_anchor(
        _anchor(
            next(iter(world.notes.anchors_for_source(world.source.id))).note_id,
            world.source.id,
        )
    )
    payload = {
        "user": _OWNER,
        "source_id": world.source.id,
        "item_type": QuizItemType.FREE_RECALL,
        "question": "What is the powerhouse of the cell?",
        "answer": "The mitochondria",
    }

    first, _ = world.accept(note_anchor_id=world.anchor.id, **payload)
    second, second_created = world.accept(note_anchor_id=other_anchor.id, **payload)

    assert second_created is True
    assert second.id != first.id
    assert len(world.items.list_all()) == 2


# --- AcceptCard: validation and ownership (edge cases, CAP-09) ------------------


@pytest.mark.parametrize("question", ["", "   ", "\n\t"])
def test_accepting_an_empty_question_is_rejected(question: str) -> None:
    world = _World()

    with pytest.raises(InvalidCardText):
        world.accept(
            user=_OWNER,
            source_id=world.source.id,
            note_anchor_id=world.anchor.id,
            item_type=QuizItemType.FREE_RECALL,
            question=question,
            answer="The mitochondria",
        )

    assert world.items.list_all() == []


def test_accepting_an_empty_answer_is_rejected() -> None:
    world = _World()

    with pytest.raises(InvalidCardText):
        world.accept(
            user=_OWNER,
            source_id=world.source.id,
            note_anchor_id=world.anchor.id,
            item_type=QuizItemType.FREE_RECALL,
            question="What is the powerhouse of the cell?",
            answer="  ",
        )

    assert world.items.list_all() == []


def test_accepting_over_long_text_is_rejected() -> None:
    world = _World(max_card_chars=50)

    with pytest.raises(InvalidCardText):
        world.accept(
            user=_OWNER,
            source_id=world.source.id,
            note_anchor_id=world.anchor.id,
            item_type=QuizItemType.FREE_RECALL,
            question="q" * 51,
            answer="The mitochondria",
        )

    assert world.items.list_all() == []


def test_accepting_an_unsupported_card_type_is_rejected() -> None:
    world = _World()

    with pytest.raises(InvalidCardText):
        world.accept(
            user=_OWNER,
            source_id=world.source.id,
            note_anchor_id=world.anchor.id,
            item_type="multiple_choice",
            question="What is the powerhouse of the cell?",
            answer="The mitochondria",
        )

    assert world.items.list_all() == []


def test_accepting_against_another_users_highlight_is_not_found() -> None:
    world = _World()
    stranger_note = Note(
        id=uuid4(),
        user_id=_STRANGER.id,
        title="Theirs",
        body_markdown="",
        created_at=_NOW,
        updated_at=_NOW,
    )
    world.notes.add(stranger_note)
    foreign = world.notes.add_anchor(_anchor(stranger_note.id, world.source.id))

    with pytest.raises(QuizItemNotFound):
        world.accept(
            user=_OWNER,
            source_id=world.source.id,
            note_anchor_id=foreign.id,
            item_type=QuizItemType.FREE_RECALL,
            question="What is the powerhouse of the cell?",
            answer="The mitochondria",
        )

    assert world.items.list_all() == []


# --- UpdateCard: editing keeps identity and scheduling (CAP-12) -----------------


def _accepted(world: _World) -> QuizItem:
    item, _ = world.accept(
        user=_OWNER,
        source_id=world.source.id,
        note_anchor_id=world.anchor.id,
        item_type=QuizItemType.FREE_RECALL,
        question="What is the powerhouse of the cell?",
        answer="The mitochondria",
    )
    return item


def test_editing_a_card_keeps_its_id_and_due_date() -> None:
    world = _World()
    original = _accepted(world)
    due_before = world.items.scheduling[original.id].due

    updated = world.update(
        user=_OWNER,
        item_id=original.id,
        question="Which organelle produces the cell's energy?",
        answer="The mitochondrion",
    )

    assert updated.id == original.id
    assert world.items.scheduling[original.id].due == due_before
    assert updated.question == "Which organelle produces the cell's energy?"
    assert updated.answer == "The mitochondrion"


def test_editing_a_card_never_writes_scheduling_or_the_review_log() -> None:
    world = _World()
    original = _accepted(world)
    scheduling_writes = world.items.create_scheduling_calls

    world.update(
        user=_OWNER,
        item_id=original.id,
        question="Which organelle produces the cell's energy?",
        answer="The mitochondrion",
    )

    assert world.items.create_scheduling_calls == scheduling_writes
    assert world.items.update_scheduling_calls == 0
    assert world.items.review_log == {}


def test_editing_a_card_recomputes_its_fingerprint() -> None:
    world = _World()
    original = _accepted(world)

    updated = world.update(
        user=_OWNER,
        item_id=original.id,
        question="Which organelle produces the cell's energy?",
        answer="The mitochondrion",
    )

    assert updated.content_key != original.content_key
    assert updated.content_key == content_key(
        QuizItemType.FREE_RECALL,
        "Which organelle produces the cell's energy?",
        "The mitochondrion",
    )


def test_editing_a_card_leaves_its_citation_snapshot_alone() -> None:
    world = _World()
    original = _accepted(world)

    updated = world.update(
        user=_OWNER,
        item_id=original.id,
        question="Which organelle produces the cell's energy?",
        answer="The mitochondrion",
    )

    assert updated.anchor == original.anchor
    assert updated.section_path == original.section_path
    assert updated.source_excerpt == original.source_excerpt
    assert updated.note_anchor_id == original.note_anchor_id
    assert updated.origin == QuizItemOrigin.HIGHLIGHT


# --- UpdateCard: guards (CAP-12) ------------------------------------------------


def test_editing_a_deck_card_is_rejected() -> None:
    # A deck card's identity is its content hash; rewriting its text would move which
    # row the next regeneration upserts into.
    world = _World()
    deck = world.items.seed(
        _deck_item(
            world.source.id,
            item_type=QuizItemType.FREE_RECALL,
            question="What is the powerhouse of the cell?",
            answer="The mitochondria",
        )
    )

    with pytest.raises(CardNotEditable):
        world.update(
            user=_OWNER,
            item_id=deck.id,
            question="Reworded question?",
            answer="Reworded answer",
        )

    assert world.items.update_text_calls == 0
    assert world.items.get_by_id(deck.id).question == "What is the powerhouse of the cell?"


@pytest.mark.parametrize("field", ["question", "answer"])
def test_editing_a_card_to_empty_text_is_rejected(field: str) -> None:
    world = _World()
    original = _accepted(world)
    payload = {"question": "A question?", "answer": "An answer"}
    payload[field] = "   "

    with pytest.raises(InvalidCardText):
        world.update(user=_OWNER, item_id=original.id, **payload)

    assert world.items.update_text_calls == 0


def test_editing_a_card_to_over_long_text_is_rejected() -> None:
    world = _World(max_card_chars=50)
    original = _accepted(world)

    with pytest.raises(InvalidCardText):
        world.update(
            user=_OWNER,
            item_id=original.id,
            question="q" * 51,
            answer="An answer",
        )

    assert world.items.update_text_calls == 0


def test_editing_another_users_card_is_not_found() -> None:
    world = _World()
    original = _accepted(world)

    with pytest.raises(QuizItemNotFound):
        world.update(
            user=_STRANGER,
            item_id=original.id,
            question="Reworded question?",
            answer="Reworded answer",
        )

    assert world.items.update_text_calls == 0


def test_editing_an_unknown_card_is_not_found() -> None:
    world = _World()

    with pytest.raises(QuizItemNotFound):
        world.update(
            user=_OWNER,
            item_id=uuid4(),
            question="Reworded question?",
            answer="Reworded answer",
        )
