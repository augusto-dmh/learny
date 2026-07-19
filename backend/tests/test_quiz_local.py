"""B2 gate — the deterministic quiz generation adapter (unit, offline).

Pins the offline generation contract: exactly one free-recall and one cloze per
section derived from the first chunk's leading sentence, grounded by construction
(``anchor_quote`` a verbatim span, cloze mask valid — QUIZ-06/07), typed only
``free_recall``/``cloze`` (QUIZ-10), and byte-identical across runs (QUIZ-05 local
path is reproducible).
"""

from __future__ import annotations

from uuid import uuid4

from app.application.quiz_qc import cloze_is_valid, quote_in_text
from app.domain.entities import QuizDeckHandle, QuizItemType, QuizSection
from app.infrastructure.quiz.local import DeterministicQuizAdapter


def _section(text: str, *, title: str = "Cell Biology") -> tuple[QuizSection, object]:
    chunk_id = uuid4()
    section = QuizSection(
        section_path=("Unit", title),
        anchor="sec.xhtml",
        title=title,
        chunks=((chunk_id, text),),
    )
    return section, chunk_id


_TEXT = "The mitochondria is the powerhouse of the cell. It also does more."


def _collect(adapter: DeterministicQuizAdapter, sections):
    result = adapter.collect_deck(adapter.begin_deck(sections))
    assert result is not None
    return result


def test_model_identity() -> None:
    assert DeterministicQuizAdapter().model == "local-deterministic"


def test_generates_one_free_recall_and_one_cloze_per_section() -> None:
    section, chunk_id = _section(_TEXT)
    result = _collect(DeterministicQuizAdapter(), [section])

    assert len(result.candidates) == 2
    by_type = {c.item_type: c for c in result.candidates}
    assert set(by_type) == {QuizItemType.FREE_RECALL, QuizItemType.CLOZE}

    free = by_type[QuizItemType.FREE_RECALL]
    assert free.answer == "The mitochondria is the powerhouse of the cell."
    assert free.anchor_quote == "The mitochondria is the powerhouse of the cell."
    assert free.source_chunk_id == chunk_id

    cloze = by_type[QuizItemType.CLOZE]
    # Longest word of the leading sentence is masked.
    assert cloze.answer == "mitochondria"
    assert cloze.question == "The ____ is the powerhouse of the cell."
    assert cloze.source_chunk_id == chunk_id


def test_candidates_are_grounded_by_construction() -> None:
    section, _ = _section(_TEXT)
    result = _collect(DeterministicQuizAdapter(), [section])

    for candidate in result.candidates:
        # anchor_quote is a verbatim span of the chunk it cites (QUIZ-06).
        assert quote_in_text(candidate.anchor_quote, _TEXT)
    cloze = next(c for c in result.candidates if c.item_type == QuizItemType.CLOZE)
    # The cloze mask is valid: masked span in the quote, blank in the question (QUIZ-07).
    assert cloze_is_valid(cloze.question, cloze.answer, cloze.anchor_quote)


def test_only_free_recall_and_cloze_types() -> None:
    section, _ = _section(_TEXT)
    result = _collect(DeterministicQuizAdapter(), [section])
    assert all(
        c.item_type in {QuizItemType.FREE_RECALL, QuizItemType.CLOZE}
        for c in result.candidates
    )


def test_multiple_sections_each_grounded_to_own_chunk() -> None:
    section_a, chunk_a = _section("Alpha beta gammaword delta. Rest.", title="A")
    section_b, chunk_b = _section("Second sentence longestword here. Rest.", title="B")
    result = _collect(DeterministicQuizAdapter(), [section_a, section_b])

    assert len(result.candidates) == 4
    assert {c.source_chunk_id for c in result.candidates} == {chunk_a, chunk_b}


def test_deterministic_same_input_same_output() -> None:
    section, _ = _section(_TEXT)
    adapter = DeterministicQuizAdapter()
    first = _collect(adapter, [section])
    second = _collect(adapter, [section])
    assert first == second


def test_section_without_chunks_yields_no_candidates() -> None:
    empty = QuizSection(section_path=("Empty",), anchor="e.xhtml", title="Empty", chunks=())
    result = _collect(DeterministicQuizAdapter(), [empty])
    assert result.candidates == ()
    assert result.errors == ()


def test_collect_deck_returns_immediately_never_pending() -> None:
    section, _ = _section(_TEXT)
    adapter = DeterministicQuizAdapter()
    handle = adapter.begin_deck([section])
    assert handle.provider == "local"
    assert handle.batch_id is None
    assert adapter.collect_deck(handle) is not None


# --- suggest_cards (quote-scoped, CAP-02) ---------------------------------------


def test_suggest_cards_never_exceeds_the_limit() -> None:
    section, _ = _section(_TEXT)
    adapter = DeterministicQuizAdapter()

    for limit in (1, 2, 3):
        candidates = adapter.suggest_cards(section, "It also does more.", limit)
        assert len(candidates) <= limit


def test_suggest_cards_are_scoped_to_the_quote_not_the_section() -> None:
    # The quote is the section's *second* sentence, which the deck path never picks.
    section, chunk_id = _section(_TEXT)
    quote = "It also does more."

    candidates = DeterministicQuizAdapter().suggest_cards(section, quote, 3)

    assert candidates
    for candidate in candidates:
        assert candidate.anchor_quote == quote
        assert candidate.source_chunk_id == chunk_id
        # Still grounded in the chunk it cites (QUIZ-06).
        assert quote_in_text(candidate.anchor_quote, _TEXT)
    cloze = next(c for c in candidates if c.item_type == QuizItemType.CLOZE)
    assert cloze_is_valid(cloze.question, cloze.answer, cloze.anchor_quote)


def test_suggest_cards_only_free_recall_and_cloze_types() -> None:
    section, _ = _section(_TEXT)
    candidates = DeterministicQuizAdapter().suggest_cards(section, _TEXT, 5)
    assert all(
        c.item_type in {QuizItemType.FREE_RECALL, QuizItemType.CLOZE}
        for c in candidates
    )


def test_suggest_cards_for_a_quote_absent_from_the_section_yields_none() -> None:
    section, _ = _section(_TEXT)
    assert DeterministicQuizAdapter().suggest_cards(section, "Not in this book.", 3) == []


def test_suggest_cards_with_a_non_positive_limit_yields_none() -> None:
    section, _ = _section(_TEXT)
    assert DeterministicQuizAdapter().suggest_cards(section, _TEXT, 0) == []


def test_handle_survives_json_payload_roundtrip() -> None:
    section, chunk_id = _section(_TEXT)
    adapter = DeterministicQuizAdapter()
    handle = adapter.begin_deck([section])

    # Round-trip through the Celery JSON hand-off (to_payload/from_payload).
    round_tripped = QuizDeckHandle.from_payload(handle.to_payload())
    result = adapter.collect_deck(round_tripped)

    assert len(result.candidates) == 2
    assert all(c.source_chunk_id == chunk_id for c in result.candidates)
