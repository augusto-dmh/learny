"""T6 gate (unit) — Docling document → ParsedBook mapping (ING-10..13, AD-086).

The pure ``_to_parsed_book`` mapping is exercised against ``docling-core``
documents constructed in code (AD-089: no ``docling`` runtime, so these run in CI
where the ``pdf`` extra is absent). Each test derives its expected outcome from
the spec ACs — section structure, opening-section synthesis, page spans, the
AD-086 anchor scheme, and determinism — never from the implementation.
"""

from __future__ import annotations

import re

from docling_core.types.doc import (
    BoundingBox,
    DocItemLabel,
    DoclingDocument,
    ProvenanceItem,
    TableCell,
    TableData,
)

from app.infrastructure.ingestion.docling_pdf import _to_parsed_book

# AD-086: pdf:{heading-path-slug}/b{ordinal:04d}-{sha256[:16]}.
_ANCHOR = re.compile(r"^pdf:[a-z0-9-]+(?:/[a-z0-9-]+)*/b[0-9]{4}-[0-9a-f]{16}$")


def _prov(page: int) -> ProvenanceItem:
    return ProvenanceItem(page_no=page, bbox=BoundingBox(l=0, t=0, r=1, b=1), charspan=(0, 1))


def _table(rows: int = 2) -> TableData:
    cells = [
        TableCell(
            text=f"H{c}",
            start_row_offset_idx=0,
            end_row_offset_idx=1,
            start_col_offset_idx=c,
            end_col_offset_idx=c + 1,
            column_header=True,
        )
        for c in range(2)
    ]
    return TableData(num_rows=1, num_cols=2, table_cells=cells)


def test_sections_open_at_each_heading_with_level_derived_depth() -> None:
    # ING-10: sections carry titles, depths, section paths, and typed blocks;
    # depth follows heading level nesting (h1 → 0, h2 → 1).
    doc = DoclingDocument(name="book")
    doc.add_heading("Chapter One", level=1, prov=_prov(1))
    doc.add_text(label=DocItemLabel.TEXT, text="Body of chapter one.", prov=_prov(1))
    doc.add_heading("Section A", level=2, prov=_prov(2))
    doc.add_text(label=DocItemLabel.TEXT, text="Body of section A.", prov=_prov(2))

    book = _to_parsed_book(doc, filename="book.pdf")

    assert [s.title for s in book.sections] == ["Chapter One", "Section A"]
    assert [s.depth for s in book.sections] == [0, 1]
    assert book.sections[1].section_path == ("Chapter One", "Section A")
    assert [b.block_type for b in book.sections[0].blocks] == ["heading", "paragraph"]


def test_opening_section_synthesized_for_preamble_before_first_heading() -> None:
    # ING-13: text before the first heading becomes a synthesized opening section,
    # titled from the filename stem (the cascade cleans it later).
    doc = DoclingDocument(name="book")
    doc.add_text(label=DocItemLabel.TEXT, text="Front matter before any heading.", prov=_prov(1))
    doc.add_heading("Chapter One", level=1, prov=_prov(2))
    doc.add_text(label=DocItemLabel.TEXT, text="Chapter body.", prov=_prov(2))

    book = _to_parsed_book(doc, filename="A Fine Book.pdf")

    assert book.sections[0].title == "A Fine Book"
    assert book.sections[0].depth == 0
    assert book.sections[0].blocks[0].html_fragment == "<p>Front matter before any heading.</p>"
    assert book.sections[1].title == "Chapter One"


def test_no_headings_single_section_titled_from_filename_stem() -> None:
    # Edge case: no headings and no title item → one section titled the filename stem.
    doc = DoclingDocument(name="book")
    doc.add_text(label=DocItemLabel.TEXT, text="Only body text, no headings at all.", prov=_prov(1))

    book = _to_parsed_book(doc, filename="path/to/plain.pdf")

    assert len(book.sections) == 1
    assert book.sections[0].title == "plain"


def test_no_headings_single_section_titled_from_metadata_title() -> None:
    # Edge case: a title item and no section headers → one section titled by it.
    doc = DoclingDocument(name="book")
    doc.add_title("Meaningful Title", prov=_prov(1))
    doc.add_text(label=DocItemLabel.TEXT, text="Body under the title.", prov=_prov(1))

    book = _to_parsed_book(doc, filename="whatever.pdf")

    assert len(book.sections) == 1
    assert book.sections[0].title == "Meaningful Title"
    assert book.title == "Meaningful Title"


def test_block_page_span_is_min_max_of_provenance() -> None:
    # ING-12: a block's page span is the (min, max) of its item's provenance pages.
    doc = DoclingDocument(name="book")
    doc.add_heading("Chapter One", level=1, prov=_prov(4))
    item = doc.add_text(label=DocItemLabel.TEXT, text="Spans two pages.", prov=_prov(4))
    item.prov.append(_prov(5))

    book = _to_parsed_book(doc, filename="book.pdf")

    paragraph = book.sections[0].blocks[1]
    assert paragraph.page_span == (4, 5)
    assert book.sections[0].blocks[0].page_span == (4, 4)


def test_anchor_follows_ad086_scheme_and_is_deterministic() -> None:
    # ING-11: anchors match the AD-086 format; re-mapping identical input yields
    # identical anchors, section paths, and blocks.
    doc = DoclingDocument(name="book")
    doc.add_heading("Chapter One", level=1, prov=_prov(1))
    doc.add_text(label=DocItemLabel.TEXT, text="Deterministic body content.", prov=_prov(1))

    first = _to_parsed_book(doc, filename="book.pdf")
    second = _to_parsed_book(doc, filename="book.pdf")

    assert _ANCHOR.match(first.sections[0].anchor)
    assert first.sections[0].anchor == "pdf:chapter-one/b0000-" + first.sections[0].anchor[-16:]
    assert [s.anchor for s in first.sections] == [s.anchor for s in second.sections]
    assert [s.section_path for s in first.sections] == [s.section_path for s in second.sections]
    assert [
        (b.block_type, b.html_fragment) for b in first.sections[0].blocks
    ] == [(b.block_type, b.html_fragment) for b in second.sections[0].blocks]


def test_repeated_heading_titles_get_unique_anchors() -> None:
    # Edge case: the same heading text on distinct sections stays unique — the
    # ordinal and the content hash both disambiguate.
    doc = DoclingDocument(name="book")
    doc.add_heading("Notes", level=1, prov=_prov(1))
    doc.add_text(label=DocItemLabel.TEXT, text="First notes body.", prov=_prov(1))
    doc.add_heading("Notes", level=1, prov=_prov(2))
    doc.add_text(label=DocItemLabel.TEXT, text="Second, different notes body.", prov=_prov(2))

    book = _to_parsed_book(doc, filename="book.pdf")

    anchors = [s.anchor for s in book.sections]
    assert anchors[0] != anchors[1]
    assert anchors[0].startswith("pdf:notes/b0000-")
    assert anchors[1].startswith("pdf:notes/b0001-")


def test_table_item_becomes_html_table_block() -> None:
    # ING-10: tables appear in the section as an HTML table block (rendered as text
    # downstream by the existing Markdown converter).
    doc = DoclingDocument(name="book")
    doc.add_heading("Data", level=1, prov=_prov(1))
    doc.add_table(data=_table(), prov=_prov(1))

    book = _to_parsed_book(doc, filename="book.pdf")

    table_blocks = [b for b in book.sections[0].blocks if b.block_type == "table"]
    assert len(table_blocks) == 1
    assert table_blocks[0].html_fragment.startswith("<table")
    assert "H0" in table_blocks[0].html_fragment


def test_list_item_becomes_list_block() -> None:
    doc = DoclingDocument(name="book")
    doc.add_heading("Points", level=1, prov=_prov(1))
    doc.add_list_item("A single point", prov=_prov(1))

    book = _to_parsed_book(doc, filename="book.pdf")

    list_blocks = [b for b in book.sections[0].blocks if b.block_type == "list"]
    assert len(list_blocks) == 1
    assert list_blocks[0].html_fragment == "<ul><li>A single point</li></ul>"


def test_running_furniture_items_are_dropped() -> None:
    # Design §4: page headers/footers/footnotes carry no body content and are
    # dropped by label even if Docling leaves them in the body layer.
    doc = DoclingDocument(name="book")
    doc.add_heading("Chapter One", level=1, prov=_prov(1))
    doc.add_text(label=DocItemLabel.PAGE_HEADER, text="running header", prov=_prov(1))
    doc.add_text(label=DocItemLabel.TEXT, text="Real body content here.", prov=_prov(1))

    book = _to_parsed_book(doc, filename="book.pdf")

    texts = [b.html_fragment for b in book.sections[0].blocks]
    assert "<p>Real body content here.</p>" in texts
    assert all("running header" not in fragment for fragment in texts)
