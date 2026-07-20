"""Deterministic, network-free quiz generation adapter (QUIZ-05 local path).

The CI/offline default behind :class:`~app.domain.ports.QuizGenerationPort`: it makes
the whole deck pipeline testable with no provider key. Per eligible section it derives
exactly two candidates from the first chunk's leading sentence — one ``free_recall``
(the sentence is the answer) and one ``cloze`` (the sentence's longest word masked with
``____``) — so every candidate is grounded by construction (its ``anchor_quote`` is a
verbatim span of the chunk it cites, QUIZ-06/07). Generation is synchronous: ``begin_deck``
computes the candidates inline onto the handle's JSON-safe payload, and ``collect_deck``
reconstructs and returns them immediately (never ``None``), so it round-trips through the
Celery poll hand-off like the batched adapter without ever pending.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from uuid import UUID

from app.application.quiz_qc import CLOZE_BLANK, quote_in_text
from app.domain.entities import (
    QuizCandidate,
    QuizDeckHandle,
    QuizDeckResult,
    QuizItemType,
    QuizSection,
)

_MODEL = "local-deterministic"

# First run of characters ending at a sentence terminator (``.``/``!``/``?``).
_SENTENCE = re.compile(r"^(.*?[.!?])(?:\s|$)", re.DOTALL)
# A "word" for cloze masking: a maximal run of letters/digits (no punctuation).
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def _leading_sentence(text: str) -> str:
    """Return the chunk's first sentence (up to its terminator), else the whole text."""
    stripped = text.strip()
    match = _SENTENCE.search(stripped)
    return match.group(1).strip() if match else stripped


def _longest_word(sentence: str) -> str | None:
    """Return the sentence's longest word (first on ties), or ``None`` if it has none."""
    words = _WORD.findall(sentence)
    if not words:
        return None
    return max(words, key=len)


def _candidates_from(sentence: str, chunk_id: UUID, title: str) -> list[QuizCandidate]:
    """Derive the free-recall + cloze pair for one sentence of ``chunk_id``.

    Both candidates cite ``chunk_id`` and quote ``sentence`` verbatim, so they are
    grounded by construction (QUIZ-06/07). Returns an empty list when the sentence has
    no maskable word — shared by the deck pass and the quote-scoped suggestion path so
    the two never drift apart.
    """
    word = _longest_word(sentence)
    if not sentence or word is None:
        return []

    free_recall = QuizCandidate(
        item_type=QuizItemType.FREE_RECALL,
        question=f"What does the passage in “{title}” state?",
        answer=sentence,
        source_chunk_id=chunk_id,
        anchor_quote=sentence,
    )
    cloze_question = re.sub(rf"\b{re.escape(word)}\b", CLOZE_BLANK, sentence, count=1)
    cloze = QuizCandidate(
        item_type=QuizItemType.CLOZE,
        question=cloze_question,
        answer=word,
        source_chunk_id=chunk_id,
        anchor_quote=sentence,
    )
    return [free_recall, cloze]


def _section_candidates(section: QuizSection) -> list[QuizCandidate]:
    """Derive the free-recall + cloze candidates for one section (grounded by construction).

    Returns an empty list for a section with no chunks or no usable leading sentence —
    the adapter's own eligibility guard on top of the repository's leaf/length filter.
    """
    if not section.chunks:
        return []
    chunk_id, chunk_text = section.chunks[0]
    return _candidates_from(_leading_sentence(chunk_text), chunk_id, section.title)


def _locate_quote(section: QuizSection, quote: str) -> UUID | None:
    """Return the id of the first section chunk containing ``quote``, else ``None``.

    Uses the same normalized containment the QC pipeline applies, so a quote this
    adapter accepts is one whose candidates can survive grounding.
    """
    for chunk_id, chunk_text in section.chunks:
        if quote_in_text(quote, chunk_text):
            return chunk_id
    return None


def _candidate_to_payload(candidate: QuizCandidate) -> dict:
    return {
        "item_type": candidate.item_type,
        "question": candidate.question,
        "answer": candidate.answer,
        "source_chunk_id": str(candidate.source_chunk_id),
        "anchor_quote": candidate.anchor_quote,
    }


def _candidate_from_payload(data: dict) -> QuizCandidate:
    return QuizCandidate(
        item_type=data["item_type"],
        question=data["question"],
        answer=data["answer"],
        source_chunk_id=UUID(data["source_chunk_id"]),
        anchor_quote=data["anchor_quote"],
    )


class DeterministicQuizAdapter:
    """``QuizGenerationPort`` implementation that generates offline, deterministically.

    Same sections in → byte-identical candidates out (a pure function of the inputs), so
    the offline deck pipeline and the groundedness eval are reproducible.
    """

    @property
    def model(self) -> str:
        """Stable model identity, readable without a network call."""
        return _MODEL

    def begin_deck(self, sections: Sequence[QuizSection]) -> QuizDeckHandle:
        """Compute all candidates inline and carry them on the handle's JSON-safe payload."""
        candidates = [
            _candidate_to_payload(candidate)
            for section in sections
            for candidate in _section_candidates(section)
        ]
        return QuizDeckHandle(
            provider="local", batch_id=None, payload={"candidates": candidates, "errors": []}
        )

    def suggest_cards(
        self, section: QuizSection, quote: str, limit: int
    ) -> list[QuizCandidate]:
        """Derive candidates from ``quote`` itself, capped at ``limit`` (AD-134).

        The deck path's construction narrowed to the passage the student highlighted:
        the quote *is* the anchor quote, so the pair stays grounded by construction. A
        quote that no chunk of ``section`` contains yields nothing — the caller reports
        "no cards for this passage" rather than an error.
        """
        if limit <= 0:
            return []
        chunk_id = _locate_quote(section, quote)
        if chunk_id is None:
            return []
        return _candidates_from(quote.strip(), chunk_id, section.title)[:limit]

    def collect_deck(self, handle: QuizDeckHandle) -> QuizDeckResult | None:
        """Return the inline result immediately — the local adapter never pends."""
        candidates = tuple(
            _candidate_from_payload(data) for data in handle.payload.get("candidates", ())
        )
        errors = tuple(handle.payload.get("errors", ()))
        return QuizDeckResult(candidates=candidates, errors=errors)
