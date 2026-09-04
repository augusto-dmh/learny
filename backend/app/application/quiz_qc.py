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

from app.domain.entities import QuizCandidate, QuizItemType

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


# The two item kinds accepted anywhere in the quiz pipeline (QUIZ-10 — no MCQ).
_VALID_ITEM_TYPES = frozenset({QuizItemType.FREE_RECALL, QuizItemType.CLOZE})

# Closed vocabulary of discard reason codes (REV-02). ``duplicate`` is reserved
# for the caller-side embedding cosine check; ``discard_reason`` never computes it.
DISCARD_REASONS = frozenset(
    {
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
)

# Closed English ∪ Portuguese function words (AD-308). Lookup is against
# ``normalize_text`` (lowercase). 1–2 letter cloze answers fail independently.
CLOZE_STOPWORDS = frozenset(
    """
    a an the i me my mine we us our ours you your yours he him his she her hers
    it its they them their theirs this that these those who whom whose which what
    of to in on at by for with from as into about up out over after before between
    through during without within against among around behind below beside beyond
    down off under until upon via than and or but nor so yet if because while
    although though unless whether since is are was were be been being am do does
    did have has had having can could will would shall should may might must not
    no some any each every all both few many much more most other another such
    when where why how there too also just only even still already always never
    very then now here
    o os as um uma uns umas de do da dos das em no na nos nas para por com sem
    sob sobre entre até desde após contra e ou mas nem que se como não sim é são
    era eram foi foram ser estar está estão esteve estou estamos eu tu ele ela
    nós vós eles elas me te lhe nos vos lhes meu minha meus minhas teu tua teus
    tuas seu sua seus suas nosso nossa nossos nossas este esta estes estas esse
    essa esses essas aquele aquela aqueles aquelas isto isso aquilo ao à aos às
    pelo pela pelos pelas já ainda também só mais menos muito pouco ter tem têm
    tenho tinha havia há fui sou somos dele dela deles delas neste nesta nisso
    qual quais quem
    """.split()
)

_YES_NO_START = re.compile(r"^(is|are|do|does|did|can|was|were)\b")
_BINARY_CHOICE = re.compile(r"(yes or no|true or false)\s*\??$")
_GENERIC_STEM = re.compile(r"what does (the )?(passage|section|note|text)")
_SET_DUMP_SPLIT = re.compile(r"[,/;]")


def _words(text: str) -> list[str]:
    return normalize_text(text).split()


def discard_reason(
    candidate: QuizCandidate,
    *,
    chunk_text: str | None = None,
    note_body: str | None = None,
) -> str | None:
    """Return a discard code, or ``None`` when the generated candidate may persist.

    Grounding uses ``chunk_text`` when provided, otherwise ``note_body``. Duplicate
    cosine similarity is caller-side (needs embeddings); this function never
    returns ``duplicate``.
    """
    if not (
        candidate.question.strip() and candidate.answer.strip() and candidate.anchor_quote.strip()
    ):
        return "empty"

    source = chunk_text if chunk_text is not None else note_body
    if source is None or not quote_in_text(candidate.anchor_quote, source):
        return "ungrounded"
    if candidate.item_type == QuizItemType.CLOZE and not cloze_is_valid(
        candidate.question, candidate.answer, candidate.anchor_quote
    ):
        return "ungrounded"

    if candidate.item_type not in _VALID_ITEM_TYPES:
        return "other"

    question_n = normalize_text(candidate.question)
    answer_n = normalize_text(candidate.answer)

    if _YES_NO_START.search(question_n) or _BINARY_CHOICE.search(question_n):
        return "yes_no"

    if candidate.item_type == QuizItemType.FREE_RECALL:
        if _GENERIC_STEM.search(question_n):
            return "generic_stem"
        if answer_n in question_n:
            return "answer_in_question"

    parts = [part.strip() for part in _SET_DUMP_SPLIT.split(candidate.answer) if part.strip()]
    if len(parts) >= 4:
        return "set_dump"

    if candidate.item_type == QuizItemType.FREE_RECALL:
        answer_words = _words(candidate.answer)
        if len(answer_words) > 12 or len(candidate.answer) > 120:
            return "answer_too_long"
        if len(candidate.question) > 280:
            return "question_too_long"
        return None

    if len(candidate.question) > 400:
        return "question_too_long"
    if answer_n in CLOZE_STOPWORDS or len(answer_n) <= 2:
        return "cloze_stopword"
    answer_words = _words(candidate.answer)
    question_words = _words(candidate.question)
    if len(answer_words) > 8 or (question_words and len(answer_words) / len(question_words) >= 0.6):
        return "cloze_too_wide"
    return None


def note_card_passes_qc(candidate: QuizCandidate, note_body: str) -> bool:
    """Return whether a note candidate is grounded in ``note_body`` (NL-08).

    The note→quiz mirror of the highlight ``_passes_qc``: the note *is* the source, so
    the candidate's ``anchor_quote`` is verified for verbatim (whitespace/case-normalized)
    containment against the whole note body rather than a chunk. A known item type,
    non-empty question/answer/quote, that containment, and — for a cloze — a valid mask
    against the quote (QUIZ-07). Applied to *generated* text only; text the reader edits
    before accepting is author-owned and not re-gated (AD-138).
    """
    if candidate.item_type not in _VALID_ITEM_TYPES:
        return False
    if not (candidate.question.strip() and candidate.answer.strip()):
        return False
    if not candidate.anchor_quote.strip():
        return False
    if not quote_in_text(candidate.anchor_quote, note_body):
        return False
    if candidate.item_type == QuizItemType.CLOZE:
        return cloze_is_valid(candidate.question, candidate.answer, candidate.anchor_quote)
    return True
