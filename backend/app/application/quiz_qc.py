"""Pure quiz quality-control helpers (design §Domain).

Framework-free text functions shared by the deterministic adapter (grounded by
construction) and the deck-generation QC pipeline (QUIZ-06/07/08). Grounding is
whitespace- and case-normalized containment; ``content_key`` is the ``(source_id,
content_key)`` upsert identity (QUIZ-02) and deliberately includes ``item_type`` so a
free-recall and a cloze item derived from the same sentence never collide.
"""

from __future__ import annotations

import hashlib
import re

# Collapses any run of whitespace to a single space (Unicode-aware via re default).
_WHITESPACE = re.compile(r"\s+")

# Unit separator between the fields folded into a content key — a control character
# that cannot appear in normalized (whitespace-collapsed) text, so field boundaries
# are unambiguous.
_FIELD_SEP = "\x1f"

# The masked-span placeholder a cloze question must contain (A-5).
CLOZE_BLANK = "____"


def normalize_text(text: str) -> str:
    """Lowercase and collapse whitespace for grounding/identity comparisons."""
    return _WHITESPACE.sub(" ", text).strip().lower()


def content_key(item_type: str, question: str, answer: str) -> str:
    """Return the SHA-256 identity of an item's content.

    ``sha256(item_type \\x1f norm(question) \\x1f norm(answer))``. ``item_type`` is a
    fixed vocabulary constant and is not normalized; the question/answer are normalized
    so trivial whitespace/case differences map to the same key (QUIZ-02).
    """
    raw = _FIELD_SEP.join((item_type, normalize_text(question), normalize_text(answer)))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def quote_in_text(quote: str, text: str) -> bool:
    """Return whether ``quote`` appears in ``text`` (whitespace/case-normalized, QUIZ-06)."""
    return normalize_text(quote) in normalize_text(text)


def cloze_is_valid(question: str, answer: str, anchor_quote: str) -> bool:
    """Return whether a cloze item is well-formed (QUIZ-07).

    The masked span (``answer``) must appear in its ``anchor_quote`` and the
    ``question`` must contain the ``____`` blank; otherwise the candidate is discarded.
    """
    return CLOZE_BLANK in question and normalize_text(answer) in normalize_text(anchor_quote)
