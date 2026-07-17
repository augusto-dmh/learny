"""Structure-preserving EPUB parser adapter (design §Components, A-1..A-4).

Implements :class:`~app.domain.ports.DocumentParserPort` with ebooklib for package
structure (spine order, OPF metadata, nav TOC) and BeautifulSoup for splitting
each spine document into preserved-HTML content blocks. This module is the only
one importing those libraries for parsing (ADR-0009); it returns the library-free
:class:`~app.domain.entities.ParsedBook` DTO so no ebooklib/bs4 type ever crosses
into ``domain`` or ``application``. Every unparseable input — non-EPUB bytes, a
corrupt archive, an unresolvable spine idref — becomes a terminal
:class:`~app.application.errors.InvalidDocumentError` (CORP-06).
"""

from __future__ import annotations

import zipfile
from collections.abc import Iterable
from dataclasses import dataclass, replace
from io import BytesIO

import ebooklib
from bs4 import BeautifulSoup, Tag
from ebooklib import epub

from app.application.errors import InvalidDocumentError
from app.domain.entities import ParsedBlock, ParsedBook, ParsedSection

# Coarse block-type vocabulary for the top-level elements a spine body contains
# (design §Components step 5); anything outside this set degrades to ``other``.
_BLOCK_TYPES = {
    "h1": "heading",
    "h2": "heading",
    "h3": "heading",
    "h4": "heading",
    "h5": "heading",
    "h6": "heading",
    "p": "paragraph",
    "ul": "list",
    "ol": "list",
    "table": "table",
    "pre": "pre",
    "blockquote": "blockquote",
    "figure": "figure",
    "img": "img",
    "hr": "hr",
}
_HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})


@dataclass(frozen=True)
class _TocEntry:
    """A flattened TOC node: where it points and how it nests (A-1/A-4)."""

    href: str | None
    fragment: str | None
    title: str
    depth: int
    section_path: tuple[str, ...]


# Default summed-uncompressed cap; production wiring injects the configured
# ``epub_max_uncompressed_bytes`` setting (see ``app.worker.tasks._build_step``).
_DEFAULT_MAX_UNCOMPRESSED_BYTES = 524288000  # 500 MiB


class EbooklibEpubParser:
    """``DocumentParserPort`` backed by ebooklib + BeautifulSoup.

    ``max_uncompressed_bytes`` caps the archive's *declared* summed uncompressed
    size before any inflation happens: the upload limit only bounds compressed
    bytes, and ``read_epub`` eagerly inflates every manifest item into memory,
    so an unchecked crafted archive could balloon a small upload into gigabytes
    inside the worker. Violations are terminal ``InvalidDocumentError`` (CORP-06).
    """

    def __init__(
        self, *, max_uncompressed_bytes: int = _DEFAULT_MAX_UNCOMPRESSED_BYTES
    ) -> None:
        self._max_uncompressed_bytes = max_uncompressed_bytes

    def parse(self, source_bytes: bytes, *, filename: str) -> ParsedBook:
        self._reject_oversized_archive(source_bytes, filename)
        try:
            book = epub.read_epub(BytesIO(source_bytes))
        except Exception as exc:  # noqa: BLE001 — any read failure is a bad EPUB
            raise InvalidDocumentError(f"could not read EPUB {filename!r}") from exc

        title = _first(_metadata_values(book, "title"))
        authors = tuple(_metadata_values(book, "creator"))
        language = _first(_metadata_values(book, "language"))

        opening_by_href, fragments_by_href = _index_toc(_flatten_toc(book.toc))

        sections: list[ParsedSection] = []
        position = 0
        for idref, linear in book.spine:
            if linear == "no":  # A-3: non-linear items are auxiliary content.
                continue
            item = book.get_item_with_id(idref)
            if item is None:
                raise InvalidDocumentError(f"unresolvable spine idref: {idref!r}")
            if item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue

            href = item.get_name()
            elements = _top_level_elements(item.get_body_content())
            current = _opening_section(len(sections), href, elements, opening_by_href)
            pending = dict(fragments_by_href.get(href, {}))
            blocks: list[ParsedBlock] = []

            for element in elements:
                fragment = _matching_fragment(element, pending)
                if fragment is not None:
                    entry = pending.pop(fragment)
                    sections.append(replace(current, blocks=tuple(blocks)))
                    current = _entry_section(len(sections), href, fragment, entry)
                    blocks = []
                block_type = _BLOCK_TYPES.get(element.name, "other")
                blocks.append(ParsedBlock(position, block_type, str(element)))
                position += 1

            sections.append(replace(current, blocks=tuple(blocks)))

        return ParsedBook(
            title=title,
            authors=authors,
            language=language,
            sections=tuple(sections),
        )


    def _reject_oversized_archive(self, source_bytes: bytes, filename: str) -> None:
        """Fail terminally when the archive declares more than the inflation cap."""
        try:
            with zipfile.ZipFile(BytesIO(source_bytes)) as archive:
                declared = sum(info.file_size for info in archive.infolist())
        except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
            raise InvalidDocumentError(f"could not read EPUB {filename!r}") from exc
        if declared > self._max_uncompressed_bytes:
            raise InvalidDocumentError(
                f"EPUB {filename!r} declares {declared} uncompressed bytes, "
                f"over the {self._max_uncompressed_bytes} byte cap"
            )


def _metadata_values(book: epub.EpubBook, name: str) -> list[str]:
    """Return non-empty OPF Dublin Core values for ``name`` (empty if absent)."""
    try:
        raw = book.get_metadata("DC", name)
    except KeyError:
        return []
    return [value for value, _ in raw if value]


def _first(values: list[str]) -> str | None:
    return values[0] if values else None


def _flatten_toc(
    toc: Iterable[object], depth: int = 0, prefix: tuple[str, ...] = ()
) -> list[_TocEntry]:
    """Depth-first flatten of ``book.toc`` into entries carrying their path."""
    entries: list[_TocEntry] = []
    for node in toc:
        if isinstance(node, tuple):
            section, children = node
            path = prefix + (section.title,)
            href, fragment = _split_href(section.href)
            entries.append(_TocEntry(href, fragment, section.title, depth, path))
            entries.extend(_flatten_toc(children, depth + 1, path))
        else:
            path = prefix + (node.title,)
            href, fragment = _split_href(getattr(node, "href", ""))
            entries.append(_TocEntry(href, fragment, node.title, depth, path))
    return entries


def _index_toc(
    entries: list[_TocEntry],
) -> tuple[dict[str, _TocEntry], dict[str, dict[str, _TocEntry]]]:
    """Split flattened entries into per-doc opening sections and fragment maps."""
    opening_by_href: dict[str, _TocEntry] = {}
    fragments_by_href: dict[str, dict[str, _TocEntry]] = {}
    for entry in entries:
        if entry.href is None:
            continue
        if entry.fragment is None:
            opening_by_href.setdefault(entry.href, entry)
        else:
            fragments_by_href.setdefault(entry.href, {})[entry.fragment] = entry
    return opening_by_href, fragments_by_href


def _split_href(raw: str | None) -> tuple[str | None, str | None]:
    if not raw:
        return None, None
    if "#" in raw:
        href, fragment = raw.split("#", 1)
        return href, fragment
    return raw, None


def _top_level_elements(body_html: bytes) -> list[Tag]:
    """The direct block elements of a spine body, skipping whitespace nodes."""
    soup = BeautifulSoup(body_html, "html.parser")
    return [node for node in soup.find_all(recursive=False) if isinstance(node, Tag)]


def _opening_section(
    position: int,
    href: str,
    elements: list[Tag],
    opening_by_href: dict[str, _TocEntry],
) -> ParsedSection:
    """The section a document opens in: its TOC entry, else the A-2 fallback."""
    entry = opening_by_href.get(href)
    if entry is not None:
        return _entry_section(position, href, None, entry)
    title = _fallback_title(href, elements)
    return ParsedSection(position, title, 0, (title,), href, ())


def _entry_section(
    position: int, href: str, fragment: str | None, entry: _TocEntry
) -> ParsedSection:
    return ParsedSection(
        position=position,
        title=entry.title,
        depth=entry.depth,
        section_path=entry.section_path,
        anchor=_anchor(href, fragment),
        blocks=(),
    )


def _fallback_title(href: str, elements: list[Tag]) -> str:
    """A-2: the first heading's text, else the href filename without extension."""
    for element in elements:
        if element.name in _HEADINGS:
            text = element.get_text(strip=True)
            if text:
                return text
    return _href_stem(href)


def _href_stem(href: str) -> str:
    return href.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def _anchor(href: str, fragment: str | None) -> str:
    return f"{href}#{fragment}" if fragment else href


def _matching_fragment(element: Tag, pending: dict[str, _TocEntry]) -> str | None:
    """Return the pending TOC fragment id this element (or a descendant) carries."""
    if not pending:
        return None
    own_id = element.get("id")
    if own_id in pending:
        return own_id
    for descendant in element.find_all(id=True):
        descendant_id = descendant.get("id")
        if descendant_id in pending:
            return descendant_id
    return None
