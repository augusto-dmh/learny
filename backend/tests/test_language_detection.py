"""Language detection — decisive tags for en/pt, None on ambiguity (unit).

Fixtures are generated running prose (repeated natural sentences) so token
counts clear the minimum-sample gate without shipping book-sized literals.
"""

from __future__ import annotations

from app.application.language import detect_language, sample_text
from app.domain.entities import ParsedBlock, ParsedBook, ParsedSection

_EN_SENTENCE = (
    "It was the best of times and the people said that all of the things "
    "they could see from the water were more than they would have known. "
)
_PT_SENTENCE = (
    "Era uma vez um livro que não tinha mais de uma história para contar, "
    "mas que já era muito conhecido por todos os que estão na cidade. "
)


def test_english_prose_detects_en() -> None:
    assert detect_language(_EN_SENTENCE * 20) == "en"


def test_portuguese_prose_detects_pt() -> None:
    assert detect_language(_PT_SENTENCE * 20) == "pt"


def test_short_text_yields_none() -> None:
    # Below the minimum sample size no guess is made (spec: None below sample).
    assert detect_language(_EN_SENTENCE) is None


def test_evenly_mixed_text_yields_none() -> None:
    # Neither language wins by the confidence ratio → None, never a wrong tag.
    assert detect_language((_EN_SENTENCE + _PT_SENTENCE) * 20) is None


def test_foreign_language_yields_none() -> None:
    # Plenty of tokens but few stopword hits for either table (Latin).
    latin = (
        "Gallia est omnis divisa in partes tres quarum unam incolunt Belgae "
        "aliam Aquitani tertiam qui ipsorum lingua Celtae nostra Galli appellantur. "
    )
    assert detect_language(latin * 20) is None


def _book(fragments: list[str]) -> ParsedBook:
    blocks = tuple(
        ParsedBlock(i, "paragraph", f"<p>{fragment}</p>", None)
        for i, fragment in enumerate(fragments)
    )
    section = ParsedSection(
        position=0,
        title="One",
        depth=0,
        section_path=("One",),
        anchor="pdf:one/b0000-0000000000000000",
        blocks=blocks,
    )
    return ParsedBook(title="Book", authors=(), language=None, sections=(section,))


def test_sample_text_strips_html_and_bounds_words() -> None:
    book = _book(["word " * 100] * 100)  # 10k words across blocks

    sample = sample_text(book, max_words=250)

    assert len(sample.split()) == 250
    assert "<p>" not in sample


def test_sample_text_feeds_detection_end_to_end() -> None:
    book = _book([_PT_SENTENCE * 5] * 5)

    assert detect_language(sample_text(book)) == "pt"
