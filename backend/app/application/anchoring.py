"""Pure highlight-anchor resolution (design §Components, NF-03).

Binds a reader selection to the corpus block that owns it. ``resolve`` is
framework-free application logic shared by capture (bind at save) and reconcile
(re-validate/rebind after a re-ingest): given the section's blocks and the
selection's quote-with-context, it locates the owning block and the selection's
offsets *within that block's normalized text*.

NORMALIZATION BOUNDARY (rq02): all matching and every returned offset are against
each block's ``normalize_text`` form — whitespace collapsed to single spaces and
lowercased (the shared quiz-QC idiom). Offsets therefore index the normalized
block text, never the raw Markdown or the rendered DOM; a consumer that needs raw
positions must re-derive them, and reconcile compares like-for-like because the
stored ``block_hash`` is the sha256 of that same normalized text.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.application.quiz_qc import normalize_text


@dataclass(frozen=True)
class AnchorBlock:
    """One section block as seen by the resolver.

    ``content_hash`` is the block's stored normalized-text sha256 (NF-02) and may be
    ``None`` for a pre-0010 block that was never hashed; the resolver tolerates that
    and still returns a binding carrying the ordinal and offsets.
    """

    ordinal: int
    content_hash: str | None
    text: str


@dataclass(frozen=True)
class AnchorBinding:
    """Where a selection bound: the owning block plus in-block normalized offsets.

    ``block_hash`` mirrors the resolved block's ``content_hash`` (``None`` when the
    block was unhashed); ``start_offset``/``end_offset`` index the block's normalized
    text (half-open). For a selection spanning multiple blocks the binding is to the
    first block and ``end_offset`` is that block's normalized length (the selection
    runs off the block's end); the full quote snapshot recovers the rest downstream.
    """

    block_hash: str | None
    block_ordinal: int
    start_offset: int
    end_offset: int


def resolve(
    blocks: Sequence[AnchorBlock],
    quote: str,
    prefix: str = "",
    suffix: str = "",
) -> AnchorBinding | None:
    """Resolve a selection to its owning block, or ``None`` when it is unfindable.

    Two ordered passes over ``blocks``:

    1. Containment — the first block whose normalized text contains the whole
       normalized quote wins. When the quote occurs more than once in that block,
       the 32-char ``prefix``/``suffix`` context disambiguates which occurrence.
    2. Spanning — no single block holds the whole quote (a multi-block selection);
       the first block whose trailing text is a prefix of the quote wins (the
       selection starts there and runs off the block's end), per the spec edge.

    Offsets index the resolved block's normalized text; see the module docstring.
    """
    nq = normalize_text(quote)
    if not nq:
        return None
    nprefix = normalize_text(prefix)
    nsuffix = normalize_text(suffix)

    for block in blocks:
        nt = normalize_text(block.text)
        occurrences = _find_all(nt, nq)
        if occurrences:
            start = _disambiguate(nt, occurrences, len(nq), nprefix, nsuffix)
            return AnchorBinding(
                block_hash=block.content_hash,
                block_ordinal=block.ordinal,
                start_offset=start,
                end_offset=start + len(nq),
            )

    for block in blocks:
        nt = normalize_text(block.text)
        start = _leading_overlap(nt, nq)
        if start is not None:
            return AnchorBinding(
                block_hash=block.content_hash,
                block_ordinal=block.ordinal,
                start_offset=start,
                end_offset=len(nt),
            )

    return None


def _find_all(text: str, quote: str) -> list[int]:
    """Return every start index of ``quote`` in ``text`` (non-overlapping, left to right)."""
    starts: list[int] = []
    pos = text.find(quote)
    while pos != -1:
        starts.append(pos)
        pos = text.find(quote, pos + 1)
    return starts


def _disambiguate(
    text: str, occurrences: list[int], quote_len: int, prefix: str, suffix: str
) -> int:
    """Pick the occurrence whose surrounding context best matches prefix/suffix.

    Scores each occurrence +1 when the preceding text ends with ``prefix`` and +1
    when the following text starts with ``suffix`` (each ignored when empty), and
    returns the highest-scoring start — the first occurrence on a tie, which also
    covers the single-occurrence and no-context cases.
    """
    if len(occurrences) == 1 or (not prefix and not suffix):
        return occurrences[0]

    best_start = occurrences[0]
    best_score = -1
    for start in occurrences:
        # Strip the single word-boundary space normalization leaves between the
        # context and the quote, so a stripped prefix/suffix still matches.
        preceding = text[:start].rstrip()
        following = text[start + quote_len :].lstrip()
        score = 0
        if prefix and preceding.endswith(prefix):
            score += 1
        if suffix and following.startswith(suffix):
            score += 1
        if score > best_score:
            best_score = score
            best_start = start
    return best_start


def _leading_overlap(text: str, quote: str) -> int | None:
    """Return where ``quote`` begins in ``text`` for a selection spanning off its end.

    Finds the smallest start such that ``text[start:]`` is a non-empty prefix of
    ``quote`` — i.e. the longest trailing run of the block that opens the quote — or
    ``None`` when the quote does not begin within this block.
    """
    for start in range(len(text)):
        tail = text[start:]
        if quote.startswith(tail):
            return start
    return None
