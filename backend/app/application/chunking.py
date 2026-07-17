"""Structure-first retrieval chunk packing (CORP-05, A-5).

A pure function — no I/O, no libraries, no framework imports (ADR-0009). Chunks
never cross a section boundary because the caller invokes this per section; here
we only pack that section's derived-Markdown block texts into ``SectionChunk``s
that stay within ``max_chars`` while preserving reading order.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.domain.entities import SectionChunk

# A sentence boundary is terminal punctuation followed by whitespace. Used only
# to break a single block that is itself larger than the cap (A-5).
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def pack_chunks(
    block_texts: Sequence[str],
    *,
    max_chars: int,
    section_path: Sequence[str],
    anchor: str,
    page_spans: Sequence[tuple[int, int] | None] | None = None,
) -> tuple[SectionChunk, ...]:
    """Pack a section's block texts into ordered chunks of ``<= max_chars``.

    Whole block texts are appended (joined by ``\\n\\n``) while the running chunk
    stays within ``max_chars``. A single block longer than ``max_chars`` is split
    at sentence boundaries, with a hard character slice for pathological
    sentence-free text so the cap is absolute (A-5). Empty/whitespace-only blocks
    are skipped; chunk indices are contiguous from 0.

    ``page_spans`` is the per-block source page range parallel to ``block_texts``
    (PDF); each chunk's ``page_span`` is the ``(min start, max end)`` over the
    blocks that fed it. Omitted (EPUB), every chunk's ``page_span`` is ``None`` and
    the text output is byte-identical to the span-less pack (A-9).
    """
    path = tuple(section_path)
    spans = list(page_spans) if page_spans is not None else [None] * len(block_texts)
    blocks = [
        (text, span)
        for text, span in zip(block_texts, spans, strict=True)
        if text.strip()
    ]

    chunk_texts: list[str] = []
    chunk_spans: list[list[tuple[int, int] | None]] = []
    current = ""
    current_spans: list[tuple[int, int] | None] = []
    for text, span in blocks:
        if len(text) > max_chars:
            if current:
                chunk_texts.append(current)
                chunk_spans.append(current_spans)
                current = ""
                current_spans = []
            for piece in _split_oversized(text, max_chars):
                chunk_texts.append(piece)
                chunk_spans.append([span])
            continue
        candidate = f"{current}\n\n{text}" if current else text
        if len(candidate) <= max_chars:
            current = candidate
            current_spans.append(span)
        else:
            chunk_texts.append(current)
            chunk_spans.append(current_spans)
            current = text
            current_spans = [span]
    if current:
        chunk_texts.append(current)
        chunk_spans.append(current_spans)

    return tuple(
        SectionChunk(
            index=index,
            text=text,
            section_path=path,
            anchor=anchor,
            page_span=_roll_up_spans(spans_for_chunk),
        )
        for index, (text, spans_for_chunk) in enumerate(
            zip(chunk_texts, chunk_spans, strict=True)
        )
    )


def _roll_up_spans(
    spans: Sequence[tuple[int, int] | None],
) -> tuple[int, int] | None:
    """The ``(min start, max end)`` over a chunk's block spans, or ``None`` (A-9)."""
    present = [span for span in spans if span is not None]
    if not present:
        return None
    return (min(start for start, _ in present), max(end for _, end in present))


def _split_oversized(text: str, max_chars: int) -> list[str]:
    """Split a single over-cap block into sentence-packed pieces of ``<= max_chars``."""
    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_BOUNDARY.split(text.strip()):
        if not sentence:
            continue
        if len(sentence) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(_hard_slices(sentence, max_chars))
            continue
        candidate = f"{current} {sentence}" if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
        else:
            pieces.append(current)
            current = sentence
    if current:
        pieces.append(current)
    return pieces


def _hard_slices(text: str, max_chars: int) -> list[str]:
    """Slice sentence-free text into fixed ``max_chars`` pieces (absolute cap)."""
    return [text[start : start + max_chars] for start in range(0, len(text), max_chars)]
