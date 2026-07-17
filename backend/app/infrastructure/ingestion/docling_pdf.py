"""Docling document → ParsedBook mapping (design §Components 4, AD-086/089).

The pure half of the PDF parser adapter: :func:`_to_parsed_book` maps a
``docling_core`` ``DoclingDocument`` to the library-free
:class:`~app.domain.entities.ParsedBook` DTO. It imports only ``docling_core`` (a
pydantic model library carried in the dev group), never ``docling`` itself, so it
is unit-testable in CI where the heavy ``pdf`` extra is absent (AD-089). The
conversion half (running Docling to produce the document) is the parser adapter
added alongside it.

The mapping mirrors the EPUB adapter's contract: sections carry titles, depths,
section paths, typed HTML blocks, and per-block page spans. It keeps its output
close to Docling's reading order and leaves generic-title and hierarchy cleanup
to the format-agnostic normalization pass that ``BuildCorpus`` runs next.
"""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass, field

from docling_core.types.doc import (
    DoclingDocument,
    ListItem,
    SectionHeaderItem,
    TableItem,
    TitleItem,
)

from app.domain.entities import ParsedBlock, ParsedBook, ParsedSection

# Labels whose text is running furniture, not body content, and is dropped even
# when Docling leaves it in the body layer (design §4 block handling).
_DROPPED_LABELS = frozenset({"page_header", "page_footer", "footnote"})
_TAG = re.compile(r"<[^>]+>")
# A slug segment: lowercase alphanumerics, other runs collapsed to a single dash.
_NON_SLUG = re.compile(r"[^a-z0-9]+")
_MAX_SLUG_CHARS = 40
_HASH_CHARS = 16
_MAX_HEADING_LEVEL = 6


@dataclass
class _RawSection:
    """A section under construction: heading metadata plus accumulated blocks."""

    title: str
    depth: int
    heading_slugs: tuple[str, ...]
    section_path: tuple[str, ...]
    ordinal: int
    blocks: list[ParsedBlock] = field(default_factory=list)


def _to_parsed_book(document: DoclingDocument, *, filename: str) -> ParsedBook:
    """Map a ``DoclingDocument`` to a ``ParsedBook`` (pure; AD-086 anchors).

    Walks the document in reading order, opening a section at each heading
    (``TitleItem``/``SectionHeaderItem``) and attaching typed HTML blocks to the
    current section. Content before the first heading becomes a synthesized
    opening section (ING-13); a document with no heading at all becomes a single
    section titled from the book title else the filename stem (edge case). Page
    spans come from each item's provenance; anchors follow the AD-086 scheme.
    """
    raw = _collect_sections(document, filename)
    sections = tuple(
        _finalize_section(section, index) for index, section in enumerate(raw)
    )
    return ParsedBook(
        title=_book_title(document),
        authors=(),
        language=None,
        sections=sections,
    )


def _collect_sections(document: DoclingDocument, filename: str) -> list[_RawSection]:
    """Group the document's body items into raw sections in reading order."""
    sections: list[_RawSection] = []
    ancestors: list[tuple[int, str, str]] = []  # (depth, title, slug) chain
    child_counts: dict[tuple[str, ...], int] = {}
    position = 0

    def open_section(title: str, depth: int) -> None:
        nonlocal ancestors
        while ancestors and ancestors[-1][0] >= depth:
            ancestors.pop()
        slug = _slug(title)
        parent_key = tuple(item[2] for item in ancestors)
        ordinal = child_counts.get(parent_key, 0)
        child_counts[parent_key] = ordinal + 1
        heading_slugs = parent_key + (slug,)
        section_path = tuple(item[1] for item in ancestors) + (title,)
        sections.append(
            _RawSection(
                title=title,
                depth=depth,
                heading_slugs=heading_slugs,
                section_path=section_path,
                ordinal=ordinal,
            )
        )
        ancestors.append((depth, title, slug))

    for item, _level in document.iterate_items():
        if _is_dropped(item):
            continue
        heading = _heading_of(item)
        if heading is not None:
            title, level = heading
            open_section(title, depth=level - 1)
        block = _block_of(item, position, document)
        if block is None:
            continue
        if not sections:
            # Content before any heading: synthesize the opening section (ING-13).
            open_section(_fallback_title(document, filename), depth=0)
        sections[-1].blocks.append(block)
        position += 1

    if not sections:
        # No headings and no mapped blocks: one empty section (never title-less).
        open_section(_fallback_title(document, filename), depth=0)
    return sections


def _finalize_section(section: _RawSection, index: int) -> ParsedSection:
    """Assign the AD-086 anchor and freeze a raw section into a ``ParsedSection``."""
    text = " ".join(_plain(block.html_fragment) for block in section.blocks)
    digest = hashlib.sha256(_collapse(text).encode("utf-8")).hexdigest()[:_HASH_CHARS]
    path = "/".join(section.heading_slugs)
    anchor = f"pdf:{path}/b{section.ordinal:04d}-{digest}"
    return ParsedSection(
        position=index,
        title=section.title,
        depth=section.depth,
        section_path=section.section_path,
        anchor=anchor,
        blocks=tuple(section.blocks),
    )


def _heading_of(item: object) -> tuple[str, int] | None:
    """Return ``(title, heading_level)`` when ``item`` opens a section, else ``None``."""
    if isinstance(item, TitleItem):
        return _collapse(item.text), 1
    if isinstance(item, SectionHeaderItem):
        return _collapse(item.text), min(item.level, _MAX_HEADING_LEVEL)
    return None


def _block_of(
    item: object, position: int, document: DoclingDocument
) -> ParsedBlock | None:
    """Map a Docling item to a typed ``ParsedBlock``, or ``None`` to skip it."""
    if isinstance(item, (TitleItem, SectionHeaderItem)):
        level = 1 if isinstance(item, TitleItem) else min(item.level, _MAX_HEADING_LEVEL)
        text = _collapse(item.text)
        return ParsedBlock(
            position, "heading", f"<h{level}>{html.escape(text)}</h{level}>", _page_span(item)
        )
    if isinstance(item, TableItem):
        return ParsedBlock(position, "table", _table_html(item, document), _page_span(item))
    if isinstance(item, ListItem):
        text = _collapse(item.text)
        if not text:
            return None
        return ParsedBlock(
            position, "list", f"<ul><li>{html.escape(text)}</li></ul>", _page_span(item)
        )
    text = _collapse(getattr(item, "text", "") or "")
    if not text:
        return None
    return ParsedBlock(position, "paragraph", f"<p>{html.escape(text)}</p>", _page_span(item))


def _table_html(item: TableItem, document: DoclingDocument) -> str:
    """Export a table to plain HTML the Markdown converter renders as a pipe table."""
    return item.export_to_html(doc=document, add_caption=False)


def _is_dropped(item: object) -> bool:
    """True for running furniture (headers/footers/footnotes) Docling left in-body."""
    label = getattr(item, "label", None)
    return getattr(label, "value", "") in _DROPPED_LABELS


def _page_span(item: object) -> tuple[int, int] | None:
    """The ``(min, max)`` provenance page numbers of an item, or ``None``."""
    pages = [prov.page_no for prov in getattr(item, "prov", []) or []]
    if not pages:
        return None
    return (min(pages), max(pages))


def _book_title(document: DoclingDocument) -> str | None:
    """The document's title item text, if any (feeds the corpus book title)."""
    for item, _level in document.iterate_items():
        if isinstance(item, TitleItem):
            title = _collapse(item.text)
            if title:
                return title
    return None


def _fallback_title(document: DoclingDocument, filename: str) -> str:
    """Opening/single-section title: the book title else the filename stem."""
    return _book_title(document) or _stem(filename)


def _plain(html_fragment: str) -> str:
    """The block's tag-stripped, entity-decoded plain text."""
    return html.unescape(_TAG.sub(" ", html_fragment))


def _collapse(text: str) -> str:
    """Whitespace-collapsed text (single spaces, trimmed)."""
    return " ".join(text.split())


def _slug(text: str) -> str:
    """A stable slug segment: lowercased, non-alphanumerics to dashes (AD-086)."""
    slug = _NON_SLUG.sub("-", text.lower()).strip("-")[:_MAX_SLUG_CHARS].strip("-")
    return slug or "section"


def _stem(filename: str) -> str:
    """The filename without directory or extension."""
    return filename.rsplit("/", 1)[-1].rsplit(".", 1)[0]
