"""ParsedMedia / ParsedBook.media — library-free packaged-image DTO (unit).

The parser copies packaged rasters onto ``ParsedBook.media`` so application
code never imports ebooklib. The DTO is frozen, carries href + type + bytes,
and defaults to empty when a parser supplies none.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.domain.entities import ParsedBook, ParsedMedia


def test_parsed_media_carries_href_type_and_bytes() -> None:
    item = ParsedMedia(href="images/cover.png", content_type="image/png", data=b"\x89PNG")

    assert item.href == "images/cover.png"
    assert item.content_type == "image/png"
    assert item.data == b"\x89PNG"


def test_parsed_media_is_frozen() -> None:
    item = ParsedMedia(href="cover.png", content_type="image/png", data=b"x")
    with pytest.raises(FrozenInstanceError):
        item.href = "tampered"  # type: ignore[misc]


def test_parsed_book_media_defaults_to_empty() -> None:
    book = ParsedBook(title="A Book", authors=(), language="en", sections=())

    assert book.media == ()


def test_parsed_book_preserves_supplied_media() -> None:
    item = ParsedMedia(href="fig.png", content_type="image/png", data=b"bytes")
    book = ParsedBook(
        title="A Book",
        authors=(),
        language="en",
        sections=(),
        media=(item,),
    )

    assert book.media == (item,)
    assert book.sections == ()
