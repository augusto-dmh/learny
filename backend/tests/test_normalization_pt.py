"""Portuguese-aware normalization heuristics (unit, CI-safe).

The heuristics table's ``pt`` row must localize two passes for a ``language="pt"``
book — keyword-driven flat-hierarchy inference and PT generic-title recognition —
while any other tag (or none) keeps the neutral behavior on identical input.
"""

from __future__ import annotations

from dataclasses import replace

from app.application.normalization import normalize_book
from app.domain.entities import ParsedBlock, ParsedBook, ParsedSection

_BODY = "<p>" + ("Texto do corpo com palavras suficientes para não ser trivial. " * 8) + "</p>"


def _section(position: int, title: str, anchor: str) -> ParsedSection:
    # Uniform h1 headings: heading levels are uninformative, so only the keyword
    # fallback can derive structure.
    return ParsedSection(
        position=position,
        title=title,
        depth=0,
        section_path=(title,),
        anchor=anchor,
        blocks=(
            ParsedBlock(position * 2, "heading", f"<h1>{title}</h1>"),
            ParsedBlock(position * 2 + 1, "paragraph", _BODY),
        ),
    )


def _pt_flat_book() -> ParsedBook:
    return ParsedBook(
        title="Um Livro",
        authors=(),
        language="pt",
        sections=(
            _section(0, "Prefácio", "pref.xhtml"),
            _section(1, "Parte I", "parte1.xhtml"),
            _section(2, "Capítulo 1", "cap1.xhtml"),
            _section(3, "Capítulo 2", "cap2.xhtml"),
            _section(4, "Parte II", "parte2.xhtml"),
            _section(5, "Capítulo 3", "cap3.xhtml"),
        ),
    )


def test_pt_keywords_drive_flat_hierarchy_inference() -> None:
    # Parts and front matter rank depth 0, chapters depth 1; paths follow.
    result = normalize_book(_pt_flat_book())

    sections = result.book.sections
    assert [s.depth for s in sections] == [0, 0, 1, 1, 0, 1]
    assert sections[2].section_path == ("Parte I", "Capítulo 1")
    assert sections[5].section_path == ("Parte II", "Capítulo 3")


def test_pt_hierarchy_needs_both_ranks_to_fire() -> None:
    # An all-chapters flat book has one keyword rank only — it stays flat rather
    # than inventing nesting.
    book = replace(
        _pt_flat_book(),
        sections=tuple(
            _section(i, f"Capítulo {i + 1}", f"c{i}.xhtml") for i in range(4)
        ),
    )

    result = normalize_book(book)

    assert [s.depth for s in result.book.sections] == [0, 0, 0, 0]


def test_unknown_language_keeps_the_neutral_behavior_on_identical_input() -> None:
    # The same structure tagged with an unknown language gets no keyword
    # inference — the table row, not the content, activates the localization.
    book = replace(_pt_flat_book(), language="xx")

    result = normalize_book(book)

    assert [s.depth for s in result.book.sections] == [0, 0, 0, 0, 0, 0]


def test_pt_primary_subtag_is_honored() -> None:
    # A regional tag (pt-BR) resolves to the pt row.
    result = normalize_book(replace(_pt_flat_book(), language="pt-BR"))

    assert [s.depth for s in result.book.sections] == [0, 0, 1, 1, 0, 1]


def test_pt_filename_stem_titles_are_replaced_by_headings() -> None:
    # ``capitulo0003``-style titles are generic under the pt row and replaced by
    # the section's real heading text via the existing cascade.
    section = ParsedSection(
        position=0,
        title="capitulo0003",
        depth=0,
        section_path=("capitulo0003",),
        anchor="capitulo0003.xhtml",
        blocks=(
            ParsedBlock(0, "heading", "<h1>A Verdadeira História</h1>"),
            ParsedBlock(1, "paragraph", _BODY),
        ),
    )
    book = ParsedBook(title="Um Livro", authors=(), language="pt", sections=(section,))

    result = normalize_book(book)

    assert result.book.sections[0].title == "A Verdadeira História"
    assert result.counts.titles_replaced == 1


def test_pt_stem_title_survives_under_neutral_language() -> None:
    # Guard the row boundary: the same ``capitulo0003`` title is NOT generic
    # without the pt row (language None), so it stays.
    section = ParsedSection(
        position=0,
        title="capitulo0003",
        depth=0,
        section_path=("capitulo0003",),
        anchor="other.xhtml",
        blocks=(
            ParsedBlock(0, "heading", "<h1>A Verdadeira História</h1>"),
            ParsedBlock(1, "paragraph", _BODY),
        ),
    )
    book = ParsedBook(title="Um Livro", authors=(), language=None, sections=(section,))

    result = normalize_book(book)

    assert result.book.sections[0].title == "capitulo0003"
    assert result.counts.titles_replaced == 0
