"""genanki ``.apkg`` export for a source's quiz deck (QUIZ-22).

Builds an Anki package from Learny quiz items: ``free_recall`` items become
Basic-style notes (Front = question, Back = answer + citation footnote) and
``cloze`` items become Cloze notes (the masked span reconstructed as
``{{c1::answer}}`` in the passage sentence, footnote in *Back Extra*). Every note's
GUID derives from ``(source_id, content_key)`` — the same upsert identity the DB
uses — so re-importing an updated deck **updates the note in place** rather than
duplicating it. Stale/orphaned items are included (their content is still valid
learning material) with their status noted in the footnote.

The genanki library lives only in this adapter (ADR-0009); callers pass Learny
:class:`~app.domain.entities.QuizItem` entities and receive ``.apkg`` bytes. Model
and deck ids are fixed constants so successive exports target the same Anki
models/deck and the GUID-based upsert holds.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

import genanki

from app.application.quiz_qc import CLOZE_BLANK
from app.domain.entities import QuizItem, QuizItemStatus, QuizItemType

# Fixed deck id — a single Learny deck; note GUIDs (per source+content) keep items
# distinct across books within it, so a fixed id is safe (design §Anki export).
_DECK_ID = 1_607_392_319

# genanki's builtin models carry stable, fixed ids and valid card templates — reused
# so every export targets the same Basic/Cloze models (GUID upsert updates in place).
_BASIC_MODEL = genanki.BASIC_MODEL
_CLOZE_MODEL = genanki.CLOZE_MODEL


def build_apkg(items: Sequence[QuizItem], source_title: str) -> bytes:
    """Return an ``.apkg`` package (bytes) for ``items`` under a deck named ``source_title``.

    Each item maps to one note keyed by ``guid_for(source_id, content_key)``; the
    package is written to a temporary directory and read back as bytes (the temp
    dir is cleaned up on exit). Assumes a non-empty ``items`` — the caller returns
    404 when the source has none.
    """
    deck = genanki.Deck(_DECK_ID, source_title or "Learny")
    for item in items:
        deck.add_note(_note_for(item, source_title))
    with TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "deck.apkg"
        genanki.Package(deck).write_to_file(str(path))
        return path.read_bytes()


def _note_for(item: QuizItem, source_title: str) -> genanki.Note:
    """Build the Basic or Cloze note for ``item`` with its citation footnote."""
    guid = genanki.guid_for(str(item.source_id), item.content_key)
    footnote = _footnote(item, source_title)
    if item.item_type == QuizItemType.CLOZE:
        # Reconstruct the single-mask cloze: the blank in the question sentence
        # becomes an Anki ``{{c1::...}}`` deletion (A-5). Footnote → "Back Extra".
        text = item.question.replace(CLOZE_BLANK, f"{{{{c1::{item.answer}}}}}")
        return genanki.Note(model=_CLOZE_MODEL, fields=[text, footnote], guid=guid)
    back = f"{item.answer}<br><br>{footnote}"
    return genanki.Note(model=_BASIC_MODEL, fields=[item.question, back], guid=guid)


def _footnote(item: QuizItem, source_title: str) -> str:
    """Return the citation footnote: book title, section path, and any non-active status."""
    section = " › ".join(item.section_path)
    footnote = f"{source_title} — {section}" if section else source_title
    if item.status != QuizItemStatus.ACTIVE:
        footnote += f" (status: {item.status})"
    return footnote
