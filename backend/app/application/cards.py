"""Card-capture use-case services (RFC-004 Cycle D, design §Components).

The passage-scoped half of active recall, kept out of ``quiz.py`` (which already owns
deck planning, running, listing, export, and reconcile). Framework-free like every other
application module: nothing here imports FastAPI, SQLAlchemy, or Celery.

:class:`SuggestCards` generates candidates for a single highlighted quote and gates them
through the same groundedness QC the deck pipeline applies (QUIZ-06/07), because those
checks catch model fabrication rather than police the student.

Ownership is reachable only through the parent source (AD-014); every ownership failure
collapses to ``QuizItemNotFound`` → 404 so no anchor's or card's existence is disclosed.
"""

from __future__ import annotations

from uuid import UUID

from app.application.errors import QuizItemNotFound, StaleCaptureTarget
from app.application.identity import AuthorizeOwnership
from app.application.ingestion import authorized_source
from app.application.quiz_qc import cloze_is_valid, quote_in_text
from app.domain.entities import (
    NoteAnchor,
    QuizCandidate,
    QuizItemType,
    QuizSection,
    User,
)
from app.domain.ports import (
    NoteRepository,
    QuizGenerationPort,
    QuizItemRepository,
    SourceRepository,
)

# The two item kinds accepted anywhere in the quiz pipeline (QUIZ-10 — no MCQ).
_VALID_ITEM_TYPES = frozenset({QuizItemType.FREE_RECALL, QuizItemType.CLOZE})


def _owned_anchor(
    notes: NoteRepository, user: User, source_id: UUID, note_anchor_id: UUID
) -> NoteAnchor:
    """Return the caller's note anchor on ``source_id``, else ``QuizItemNotFound``.

    A missing anchor, an anchor citing a different source, and an anchor whose note
    belongs to someone else all collapse to the same 404 (CAP-09): the card surfaces
    must never reveal that another user's highlight exists.
    """
    anchor = notes.get_anchor(note_anchor_id)
    if anchor is None or anchor.source_id != source_id:
        raise QuizItemNotFound("Highlight not found.")
    note = notes.get_by_id(anchor.note_id)
    if note is None or note.user_id != user.id:
        raise QuizItemNotFound("Highlight not found.")
    return anchor


def _section_text(section: QuizSection) -> str:
    """Return the section's full text — the corpus a candidate must be grounded in."""
    return "\n".join(text for _chunk_id, text in section.chunks)


def _passes_qc(candidate: QuizCandidate, section_text: str) -> bool:
    """Return whether a generated candidate survives groundedness QC (CAP-03/04).

    The deck pipeline's checks narrowed to one section: a known item type, non-empty
    text, an ``anchor_quote`` contained verbatim in the section (QUIZ-06), and for a
    cloze a mask that is valid against that quote (QUIZ-07). Applied to *generated*
    text only — text the student edited before accepting is author-owned and is not
    re-gated (AD-138).
    """
    if candidate.item_type not in _VALID_ITEM_TYPES:
        return False
    if not (candidate.question.strip() and candidate.answer.strip()):
        return False
    if not candidate.anchor_quote.strip():
        return False
    if not quote_in_text(candidate.anchor_quote, section_text):
        return False
    if candidate.item_type == QuizItemType.CLOZE:
        return cloze_is_valid(candidate.question, candidate.answer, candidate.anchor_quote)
    return True


class SuggestCards:
    """Generate QC-passing card candidates for one highlighted passage (CAP-01..04, 09).

    Authorizes the source, resolves the anchor to the caller's own highlight on it,
    loads that anchor's section, and asks the generation port for at most
    ``max_suggestions`` candidates scoped to the highlighted quote. Every candidate is
    re-verified against the section text here rather than trusted from the adapter, so
    grounding holds for any provider.

    Nothing is persisted: suggestions are ephemeral by construction (AD-134), so "no
    silent bulk generation" is a structural property — only acceptance writes a row. A
    pass where no candidate survives QC returns an empty list, which is an outcome
    ("no cards for this passage"), not an error.
    """

    def __init__(
        self,
        *,
        sources: SourceRepository,
        notes: NoteRepository,
        items: QuizItemRepository,
        generation: QuizGenerationPort,
        authorize: AuthorizeOwnership,
        max_suggestions: int,
    ) -> None:
        self._sources = sources
        self._notes = notes
        self._items = items
        self._generation = generation
        self._authorize = authorize
        self._max_suggestions = max_suggestions

    def __call__(
        self, *, user: User, source_id: UUID, note_anchor_id: UUID
    ) -> list[QuizCandidate]:
        authorized_source(
            user=user,
            source_id=source_id,
            sources=self._sources,
            authorize=self._authorize,
        )
        anchor = _owned_anchor(self._notes, user, source_id, note_anchor_id)

        section = self._items.section_for_anchor(source_id, anchor.anchor)
        if section is None:
            # The corpus was replaced under the highlight; nothing to generate from.
            raise StaleCaptureTarget("The selected passage no longer matches the source.")

        candidates = self._generation.suggest_cards(
            section, anchor.quote_exact, self._max_suggestions
        )
        section_text = _section_text(section)
        survivors = [c for c in candidates if _passes_qc(c, section_text)]
        return survivors[: self._max_suggestions]
