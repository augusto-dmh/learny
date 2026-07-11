"""T5 gate — synthetic EPUB fixture self-check (unit).

Derived from T5 Done-when: every builder returns ``bytes``; ``valid_book()``
produces a real EPUB ZIP whose members are the ones the parser (T6) relies on
(uncompressed ``mimetype`` first, container, OPF, nav, and the spine documents).
This does not parse with ebooklib — it only pins the fixture substrate so the
expected-structure constants the parser tests assert against stay trustworthy.
"""

from __future__ import annotations

import zipfile
from io import BytesIO

from tests import fixtures_epub as fx


def _names(book_bytes: bytes) -> list[str]:
    with zipfile.ZipFile(BytesIO(book_bytes)) as zf:
        return zf.namelist()


def test_every_builder_returns_bytes() -> None:
    for builder in (
        fx.valid_book,
        fx.no_toc_book,
        fx.broken_spine_book,
        fx.empty_body_book,
        fx.not_an_epub,
    ):
        assert isinstance(builder(), bytes)
        assert builder(), f"{builder.__name__} produced empty bytes"


def test_valid_book_is_a_zip_with_the_required_members() -> None:
    names = _names(fx.valid_book())

    for member in (
        "mimetype",
        "META-INF/container.xml",
        "content.opf",
        "nav.xhtml",
        "cover.xhtml",
        "part1.xhtml",
        "chap1.xhtml",
        "chap2.xhtml",
    ):
        assert member in names, f"missing {member}"


def test_valid_book_mimetype_is_stored_first_and_uncompressed() -> None:
    with zipfile.ZipFile(BytesIO(fx.valid_book())) as zf:
        infos = zf.infolist()
        assert infos[0].filename == "mimetype"
        assert infos[0].compress_type == zipfile.ZIP_STORED
        assert zf.read("mimetype") == b"application/epub+zip"


def test_not_an_epub_is_not_a_zip() -> None:
    assert not zipfile.is_zipfile(BytesIO(fx.not_an_epub()))


def test_broken_spine_book_references_an_unresolvable_idref() -> None:
    # The OPF spine points at an idref with no matching manifest item, so the
    # parser (T6) must fail it — pin that the fixture actually encodes the fault.
    with zipfile.ZipFile(BytesIO(fx.broken_spine_book())) as zf:
        opf = zf.read("content.opf").decode("utf-8")
    assert 'idref="ghost"' in opf
    assert 'id="ghost"' not in opf


def test_expected_valid_constants_are_internally_consistent() -> None:
    # Section positions are contiguous from 0 in reading order; block positions
    # are a single global run across the whole book (CORP-02/03).
    sections = fx.EXPECTED_VALID_SECTIONS
    assert [s.position for s in sections] == list(range(len(sections)))

    block_positions = [b.position for s in sections for b in s.blocks]
    assert block_positions == list(range(len(block_positions)))

    # Every section's path ends with its own title (root-to-node, A-1/A-2).
    for section in sections:
        assert section.section_path[-1] == section.title
        assert section.depth == len(section.section_path) - 1
