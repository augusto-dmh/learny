"""Formulation gates for generated quiz candidates (REV-10..18).

Each reason-code test is a discriminating fixture: it fails that code and no
other. Duplicate cosine stays caller-side; ``discard_reason`` never returns it.
Author-edited text is not re-gated here (AD-138).
"""

from __future__ import annotations

import pytest

from app.application.quiz_qc import (
    CLOZE_BLANK,
    DISCARD_REASONS,
    discard_reason,
)
from app.domain.entities import QuizCandidate, QuizItemType

_CHUNK = "The mitochondria is the powerhouse of the cell and produces ATP."
_QUOTE = _CHUNK


def _free(question: str, answer: str, *, quote: str = _QUOTE) -> QuizCandidate:
    return QuizCandidate(
        item_type=QuizItemType.FREE_RECALL,
        question=question,
        answer=answer,
        anchor_quote=quote,
    )


def _cloze(question: str, answer: str, *, quote: str = _QUOTE) -> QuizCandidate:
    return QuizCandidate(
        item_type=QuizItemType.CLOZE,
        question=question,
        answer=answer,
        anchor_quote=quote,
    )


def _reason(candidate: QuizCandidate, *, chunk: str | None = _CHUNK) -> str | None:
    return discard_reason(candidate, chunk_text=chunk)


def test_discard_reason_vocabulary_matches_the_spec() -> None:
    assert DISCARD_REASONS == {
        "ungrounded",
        "duplicate",
        "empty",
        "answer_in_question",
        "yes_no",
        "cloze_stopword",
        "cloze_too_wide",
        "answer_too_long",
        "question_too_long",
        "set_dump",
        "generic_stem",
        "other",
    }


def test_legal_short_free_recall_returns_none() -> None:
    candidate = _free("What organelle produces ATP?", "mitochondria")
    assert _reason(candidate) is None


def test_legal_one_word_cloze_returns_none() -> None:
    candidate = _cloze(
        f"The {CLOZE_BLANK} is the powerhouse of the cell and produces ATP.", "mitochondria"
    )
    assert _reason(candidate) is None


def test_legal_free_recall_grounds_against_note_body() -> None:
    candidate = _free("What organelle produces ATP?", "mitochondria")
    assert discard_reason(candidate, note_body=_CHUNK) is None


@pytest.mark.parametrize("field", ["question", "answer", "anchor_quote"])
def test_blank_question_answer_or_quote_is_empty(field: str) -> None:
    fields = {
        "question": "What organelle produces ATP?",
        "answer": "mitochondria",
        "anchor_quote": _QUOTE,
    }
    fields[field] = "   "
    candidate = QuizCandidate(item_type=QuizItemType.FREE_RECALL, **fields)
    assert _reason(candidate) == "empty"


def test_quote_absent_from_source_is_ungrounded() -> None:
    candidate = _free(
        "What organelle produces ATP?",
        "mitochondria",
        quote="this fabricated sentence is not in the chunk",
    )
    assert _reason(candidate) == "ungrounded"


def test_cloze_missing_the_blank_is_ungrounded() -> None:
    candidate = _cloze(
        "The mitochondria is the powerhouse of the cell and produces ATP.", "mitochondria"
    )
    assert _reason(candidate) == "ungrounded"


def test_missing_source_text_is_ungrounded() -> None:
    candidate = _free("What organelle produces ATP?", "mitochondria")
    assert discard_reason(candidate) == "ungrounded"


def test_duplicate_is_reserved_for_caller_side_cosine() -> None:
    candidate = _free("What organelle produces ATP?", "mitochondria")
    assert _reason(candidate) is None
    assert _reason(candidate) is None
    assert "duplicate" in DISCARD_REASONS
    assert discard_reason(candidate, chunk_text=_CHUNK) != "duplicate"


def test_free_recall_answer_substring_of_question_is_answer_in_question() -> None:
    candidate = _free("Where is mitochondria found?", "mitochondria")
    assert _reason(candidate) == "answer_in_question"


def test_question_starting_with_did_is_yes_no() -> None:
    candidate = _free("Did Krebs describe this cycle?", "Hans Krebs")
    assert _reason(candidate) == "yes_no"


def test_question_ending_in_yes_or_no_is_yes_no() -> None:
    candidate = _free("The citric acid cycle is mitochondrial, yes or no?", "matrix")
    assert _reason(candidate) == "yes_no"


def test_english_function_word_cloze_is_cloze_stopword() -> None:
    candidate = _cloze(
        f"{CLOZE_BLANK} mitochondria is the powerhouse of the cell and produces ATP.",
        "the",
    )
    assert _reason(candidate) == "cloze_stopword"


def test_portuguese_function_word_cloze_is_cloze_stopword() -> None:
    chunk = "A energia para a célula vem da mitocôndria."
    candidate = _cloze(f"A energia {CLOZE_BLANK} a célula vem da mitocôndria.", "para", quote=chunk)
    assert _reason(candidate, chunk=chunk) == "cloze_stopword"


def test_two_letter_cloze_answer_is_cloze_stopword() -> None:
    chunk = "Mg is a cofactor in chlorophyll."
    candidate = _cloze(f"{CLOZE_BLANK} is a cofactor in chlorophyll.", "Mg", quote=chunk)
    assert _reason(candidate, chunk=chunk) == "cloze_stopword"


def test_cloze_answer_over_eight_words_is_cloze_too_wide() -> None:
    quote = "one two three four five six seven eight nine appear together."
    question = (
        "Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu "
        f"xi omicron pi rho the {CLOZE_BLANK} remainder."
    )
    candidate = _cloze(question, "one two three four five six seven eight nine", quote=quote)
    assert _reason(candidate, chunk=quote) == "cloze_too_wide"


def test_cloze_answer_at_least_sixty_percent_of_question_is_cloze_too_wide() -> None:
    quote = "The powerhouse organelle here."
    candidate = _cloze(f"The {CLOZE_BLANK} here.", "powerhouse organelle", quote=quote)
    assert _reason(candidate, chunk=quote) == "cloze_too_wide"


def test_free_recall_answer_over_twelve_words_is_answer_too_long() -> None:
    candidate = _free(
        "What organelle produces ATP?",
        "one two three four five six seven eight nine ten eleven twelve thirteen",
    )
    assert _reason(candidate) == "answer_too_long"


def test_free_recall_answer_over_120_characters_is_answer_too_long() -> None:
    candidate = _free("What organelle produces ATP?", "x" * 121)
    assert _reason(candidate) == "answer_too_long"


def test_free_recall_question_over_280_characters_is_question_too_long() -> None:
    prefix = "Name the organelle "
    question = prefix + ("x" * (281 - len(prefix)))
    assert len(question) == 281
    candidate = _free(question, "mitochondria")
    assert _reason(candidate) == "question_too_long"


def test_cloze_question_over_400_characters_is_question_too_long() -> None:
    prefix = f"The {CLOZE_BLANK} is "
    question = prefix + ("word " * 80)
    question = question[:401]
    assert CLOZE_BLANK in question
    assert len(question) == 401
    candidate = _cloze(question, "mitochondria")
    assert _reason(candidate) == "question_too_long"


@pytest.mark.parametrize(
    "answer", ["alpha, beta, gamma, delta", "alpha/beta/gamma/delta", "alpha; beta; gamma; delta"]
)
def test_four_separated_items_are_set_dump(answer: str) -> None:
    candidate = _free("Which cofactors are required?", answer)
    assert _reason(candidate) == "set_dump"


@pytest.mark.parametrize(
    "question",
    [
        "What does the passage in Cell Biology state?",
        "What does passage mean here?",
        "What does the section cover?",
        "What does the note state?",
        "What does the text claim?",
    ],
)
def test_what_does_the_passage_stem_is_generic_stem(question: str) -> None:
    candidate = _free(question, "chemiosmosis")
    assert _reason(candidate) == "generic_stem"


def test_unknown_item_type_is_other() -> None:
    candidate = QuizCandidate(
        item_type="mcq",
        question="What organelle produces ATP?",
        answer="mitochondria",
        anchor_quote=_QUOTE,
    )
    assert _reason(candidate) == "other"
