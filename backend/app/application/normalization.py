"""Format-agnostic structure normalization for parsed books (ING-01..08, AD-084).

The F7 fix: real-world EPUBs (and, later, PDFs) yield noisy corpora — filename
stems as section titles, flat trees, boilerplate front/back matter, and text
attached to caption-level anchors while file-level sections own nothing. This
module is the single seam both parser adapters flow through: a pure,
deterministic, idempotent pass on the library-free ``ParsedBook`` DTO, run inside
``BuildCorpus`` between ``parser.parse()`` and record building.

Pipeline order is fixed (each step is a fixed point on its own output, so the
whole pass is idempotent):

1. **Gutenberg strip** (ING-06): drop everything outside the standard
   ``*** START/END OF THE PROJECT GUTENBERG EBOOK … ***`` markers when both are
   present; no markers → no-op.
2. **Trivial-section merge + anchor promotion** (ING-05): a section owning no
   meaningful content (< 30 words and no heading of its own, or only image
   blocks) merges into the adjacent surviving section; the merged-away anchor
   (plus its own aliases) becomes an alias of the survivor. At least one section
   always survives.
3. **Flat-TOC hierarchy inference** (ING-03): when every section is depth 0 but
   headings carry ≥ 2 distinct levels, re-derive depth from heading level rank.
4. **Depth clamp** (ING-04): each section's depth is clamped to at most its
   predecessor's depth + 1.
5. **Title cascade** (ING-02): a generic title (filename-stem pattern family,
   href-stem match, or empty) is replaced by the first heading text, else the
   first short (< 80 char) leading text, else ``Untitled section (N)``.

``section_path`` is rebuilt once at the end from the final depths and titles, so
it reflects every merge, depth change, and title replacement. The pass reads and
returns only entity DTOs — no I/O, no settings; thresholds are module constants
(a knob would make corpus output environment-dependent).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, replace

from app.domain.entities import ParsedBlock, ParsedBook, ParsedSection

# Below this word count a heading-less section owns nothing worth its own node.
_MIN_WORDS = 30
# A leading text longer than this is body prose, not a styled heading.
_MAX_TITLE_CHARS = 80
# Block kinds that carry no readable text of their own (caption/figure material).
_IMAGE_BLOCK_TYPES = frozenset({"img", "figure"})
# A title is generic when it is the filename-stem pattern family (``part0034``,
# ``wrap0000``, ``chapter5``, bare ``0034`` …), matches the anchor's href stem,
# or is empty.
_GENERIC_TITLE = re.compile(
    r"^(part|split|index|text|wrap|ch(apter)?)?[_-]?\d+$", re.IGNORECASE
)
_GUTENBERG_START = re.compile(
    r"\*\*\*\s*START OF TH(E|IS) PROJECT GUTENBERG EBOOK", re.IGNORECASE
)
_GUTENBERG_END = re.compile(
    r"\*\*\*\s*END OF TH(E|IS) PROJECT GUTENBERG EBOOK", re.IGNORECASE
)
_TAG = re.compile(r"<[^>]+>")
_HEADING_LEVEL = re.compile(r"<\s*h([1-6])", re.IGNORECASE)


@dataclass(frozen=True)
class NormalizationCounts:
    """What the pass changed, for the ``corpus_normalized`` job event (ING-07)."""

    titles_replaced: int
    sections_merged: int
    depths_adjusted: int
    noise_blocks_stripped: int


@dataclass(frozen=True)
class NormalizationResult:
    """The normalized book plus the counts of what changed (AD-084).

    Merged-away anchors live on the returned sections' ``anchor_aliases`` so
    downstream persistence keeps every prior citation resolvable.
    """

    book: ParsedBook
    counts: NormalizationCounts


def normalize_book(book: ParsedBook) -> NormalizationResult:
    """Run the fixed normalization pipeline over ``book`` (pure, idempotent)."""
    sections = list(book.sections)
    sections, stripped = _strip_gutenberg(sections)
    sections, merged = _merge_trivial(sections)
    depths_before = [section.depth for section in sections]
    sections = _infer_flat_hierarchy(sections)
    sections = _clamp_depths(sections)
    depths_adjusted = sum(
        1
        for section, before in zip(sections, depths_before, strict=True)
        if section.depth != before
    )
    sections, titles_replaced = _apply_title_cascade(sections)
    sections = _renumber_and_rebuild_paths(sections)
    counts = NormalizationCounts(
        titles_replaced=titles_replaced,
        sections_merged=merged,
        depths_adjusted=depths_adjusted,
        noise_blocks_stripped=stripped,
    )
    return NormalizationResult(book=replace(book, sections=tuple(sections)), counts=counts)


def _strip_gutenberg(
    sections: list[ParsedSection],
) -> tuple[list[ParsedSection], int]:
    """Drop blocks outside the Gutenberg START/END markers (ING-06)."""
    flat = [(si, bi) for si, sec in enumerate(sections) for bi in range(len(sec.blocks))]
    texts = [_block_text(sections[si].blocks[bi]) for si, bi in flat]
    start = next(
        (i for i, text in enumerate(texts) if _GUTENBERG_START.search(text)), None
    )
    if start is None:
        return sections, 0
    end = next(
        (i for i in range(start + 1, len(flat)) if _GUTENBERG_END.search(texts[i])),
        None,
    )
    if end is None:
        return sections, 0

    keep = {flat[i] for i in range(start + 1, end)}
    stripped = len(flat) - len(keep)
    result = [
        replace(
            sec,
            blocks=tuple(
                block for bi, block in enumerate(sec.blocks) if (si, bi) in keep
            ),
        )
        for si, sec in enumerate(sections)
    ]
    return result, stripped


def _merge_trivial(
    sections: list[ParsedSection],
) -> tuple[list[ParsedSection], int]:
    """Merge content-less sections into an adjacent survivor (ING-05)."""
    survivors: list[ParsedSection] = []
    pending_forward: list[ParsedSection] = []
    merged = 0
    for section in sections:
        if _is_trivial(section):
            if survivors:
                survivors[-1] = _absorb_backward(survivors[-1], section)
                merged += 1
            else:
                pending_forward.append(section)
            continue
        if pending_forward:
            section = _absorb_forward(section, pending_forward)
            merged += len(pending_forward)
            pending_forward = []
        survivors.append(section)

    if pending_forward:
        # Every section was trivial: the first survives and holds all content.
        survivor = pending_forward[0]
        for section in pending_forward[1:]:
            survivor = _absorb_backward(survivor, section)
            merged += 1
        survivors.append(survivor)
    return survivors, merged


def _absorb_backward(survivor: ParsedSection, merged: ParsedSection) -> ParsedSection:
    """Append a following trivial section's content and anchor into ``survivor``."""
    return replace(
        survivor,
        blocks=survivor.blocks + merged.blocks,
        anchor_aliases=_extend_aliases(
            survivor, (merged.anchor, *merged.anchor_aliases)
        ),
    )


def _absorb_forward(
    survivor: ParsedSection, leading: list[ParsedSection]
) -> ParsedSection:
    """Prepend leading trivial sections' content and anchors into ``survivor``."""
    prefix = tuple(block for section in leading for block in section.blocks)
    new_anchors = [
        anchor
        for section in leading
        for anchor in (section.anchor, *section.anchor_aliases)
    ]
    return replace(
        survivor,
        blocks=prefix + survivor.blocks,
        anchor_aliases=_extend_aliases(survivor, new_anchors),
    )


def _extend_aliases(
    survivor: ParsedSection, new_anchors: tuple[str, ...] | list[str]
) -> tuple[str, ...]:
    """Aliases plus ``new_anchors``, deduped, canonical anchor never an alias."""
    result = list(survivor.anchor_aliases)
    for anchor in new_anchors:
        if anchor != survivor.anchor and anchor not in result:
            result.append(anchor)
    return tuple(result)


def _infer_flat_hierarchy(sections: list[ParsedSection]) -> list[ParsedSection]:
    """Re-derive depth from heading levels when the TOC is flat (ING-03)."""
    if any(section.depth != 0 for section in sections):
        return sections
    levels = [_first_heading_level(section) for section in sections]
    distinct = sorted({level for level in levels if level is not None})
    if len(distinct) < 2:
        return sections

    rank = {level: index for index, level in enumerate(distinct)}
    result: list[ParsedSection] = []
    previous_depth = 0
    for section, level in zip(sections, levels, strict=True):
        depth = rank[level] if level is not None else previous_depth
        result.append(replace(section, depth=depth))
        previous_depth = depth
    return result


def _clamp_depths(sections: list[ParsedSection]) -> list[ParsedSection]:
    """Clamp each section's depth to at most its predecessor's depth + 1 (ING-04)."""
    result: list[ParsedSection] = []
    previous_depth = -1
    for section in sections:
        depth = max(0, min(section.depth, previous_depth + 1))
        result.append(section if depth == section.depth else replace(section, depth=depth))
        previous_depth = depth
    return result


def _apply_title_cascade(
    sections: list[ParsedSection],
) -> tuple[list[ParsedSection], int]:
    """Replace generic titles via the heading/short-text/placeholder cascade (ING-02)."""
    result: list[ParsedSection] = []
    replaced = 0
    for index, section in enumerate(sections):
        if _is_generic_title(section):
            result.append(replace(section, title=_infer_title(section, index)))
            replaced += 1
        else:
            result.append(section)
    return result, replaced


def _renumber_and_rebuild_paths(
    sections: list[ParsedSection],
) -> list[ParsedSection]:
    """Assign sequential positions and rebuild section paths from depth + title."""
    result: list[ParsedSection] = []
    ancestors: list[str] = []
    for index, section in enumerate(sections):
        ancestors = ancestors[: section.depth]
        path = (*ancestors, section.title)
        ancestors = [*ancestors, section.title]
        result.append(replace(section, position=index, section_path=path))
    return result


def _is_trivial(section: ParsedSection) -> bool:
    """True when a section owns no meaningful content of its own (ING-05)."""
    if not section.blocks:
        return True
    if all(block.block_type in _IMAGE_BLOCK_TYPES for block in section.blocks):
        return True
    if any(block.block_type == "heading" for block in section.blocks):
        return False
    words = sum(len(_block_text(block).split()) for block in section.blocks)
    return words < _MIN_WORDS


def _is_generic_title(section: ParsedSection) -> bool:
    """True when the title is a filename stem, matches the href stem, or is empty."""
    title = section.title.strip()
    if not title:
        return True
    if _GENERIC_TITLE.fullmatch(title):
        return True
    return title == _href_stem(section.anchor)


def _infer_title(section: ParsedSection, index: int) -> str:
    """The replacement title for a generic section, per the ING-02 cascade."""
    for block in section.blocks:
        if block.block_type == "heading":
            text = _block_text(block)
            if text:
                return text
    for block in section.blocks:
        text = _block_text(block)
        if text and len(text) < _MAX_TITLE_CHARS:
            return text
    return f"Untitled section ({index + 1})"


def _first_heading_level(section: ParsedSection) -> int | None:
    """The h-level of the section's first heading block, or ``None``."""
    for block in section.blocks:
        if block.block_type == "heading":
            match = _HEADING_LEVEL.search(block.html_fragment)
            return int(match.group(1)) if match else None
    return None


def _block_text(block: ParsedBlock) -> str:
    """The block's whitespace-collapsed plain text (tags stripped, entities decoded)."""
    return " ".join(html.unescape(_TAG.sub(" ", block.html_fragment)).split())


def _href_stem(anchor: str) -> str:
    """The filename stem of an ``href[#fragment]`` anchor (matches the parser's rule)."""
    href = anchor.split("#", 1)[0]
    return href.rsplit("/", 1)[-1].rsplit(".", 1)[0]
