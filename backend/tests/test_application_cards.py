"""Card-capture services (unit, in-memory fakes) — RFC-004 Cycle D.

Covers the passage-scoped use cases against the spec's acceptance criteria with no DB.
``SuggestCards`` is exercised through hand-built candidates so every QC discard branch
is asserted on what the caller receives (CAP-01..04, CAP-09), and the ownership legs pin
404 non-disclosure for a cross-owner or wrong-source anchor.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.application.cards import SuggestCards
from app.application.errors import (
    QuizItemNotFound,
    SourceNotFound,
    StaleCaptureTarget,
)
from app.application.identity import AuthorizeOwnership
from app.domain.entities import (
    Note,
    NoteAnchor,
    NoteAnchorStatus,
    QuizCandidate,
    QuizItemType,
    QuizSection,
    Source,
    User,
)
from tests.fakes import FakeNoteRepository, FakeSourceRepository

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
    the corpus no longer resolves, the stale-target leg).
    """

    def __init__(self, sections: dict[str, QuizSection] | None = None) -> None:
        self._sections = sections or {}

    def section_for_anchor(self, source_id: UUID, anchor: str) -> QuizSection | None:
        return self._sections.get(anchor)


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
        self.suggest = SuggestCards(
            sources=self.sources,
            notes=self.notes,
            items=self.items,
            generation=self.generation,
            authorize=AuthorizeOwnership(),
            max_suggestions=max_suggestions,
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
