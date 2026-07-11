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
) -> tuple[SectionChunk, ...]:
    """Pack a section's block texts into ordered chunks of ``<= max_chars``.

    Whole block texts are appended (joined by ``\\n\\n``) while the running chunk
    stays within ``max_chars``. A single block longer than ``max_chars`` is split
    at sentence boundaries, with a hard character slice for pathological
    sentence-free text so the cap is absolute (A-5). Empty/whitespace-only blocks
    are skipped; chunk indices are contiguous from 0; ``page_span`` is ``None``
    for EPUB (A-9).
    """
    path = tuple(section_path)
    texts = [text for text in block_texts if text.strip()]

    chunk_texts: list[str] = []
    current = ""
    for text in texts:
        if len(text) > max_chars:
            if current:
                chunk_texts.append(current)
                current = ""
            chunk_texts.extend(_split_oversized(text, max_chars))
            continue
        candidate = f"{current}\n\n{text}" if current else text
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunk_texts.append(current)
            current = text
    if current:
        chunk_texts.append(current)

    return tuple(
        SectionChunk(
            index=index,
            text=text,
            section_path=path,
            anchor=anchor,
            page_span=None,
        )
        for index, text in enumerate(chunk_texts)
    )


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
