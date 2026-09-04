"""Markdown image-src rewrite — allowlisted media URLs, HTML left alone.

Derived from the figure-extract acceptance criteria: a mapped packaged-raster
href becomes ``/api/sources/{source_id}/media/{sha256}`` and must not remain
EPUB-relative; unmapped hrefs stay; the function rewrites markdown image syntax
only, never HTML ``<img>`` fragments; alt metacharacters are not wrapped as
nested markdown.
"""

from __future__ import annotations

from uuid import UUID

from app.application.media import rewrite_markdown_images

_SOURCE = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_HASH = "a" * 64


def test_mapped_href_becomes_allowlisted_media_url() -> None:
    rewritten = rewrite_markdown_images(
        "![Cover image](cover.png)",
        source_id=_SOURCE,
        href_to_hash={"cover.png": _HASH},
    )

    expected = f"![Cover image](/api/sources/{_SOURCE}/media/{_HASH})"
    assert rewritten == expected
    assert "cover.png" not in rewritten
    assert rewritten.startswith("![Cover image](/api/sources/")


def test_unmapped_href_is_left_unchanged() -> None:
    original = "![Remote](https://evil.example/x.png)"
    rewritten = rewrite_markdown_images(
        original,
        source_id=_SOURCE,
        href_to_hash={"cover.png": _HASH},
    )

    assert rewritten == original


def test_html_img_fragment_is_not_rewritten() -> None:
    html = '<img alt="Cover image" src="cover.png"/>'
    rewritten = rewrite_markdown_images(
        html,
        source_id=_SOURCE,
        href_to_hash={"cover.png": _HASH},
    )

    assert rewritten == html
    assert "/api/sources/" not in rewritten


def test_alt_metacharacters_are_not_nested_as_markdown() -> None:
    rewritten = rewrite_markdown_images(
        "![a *b* _c_](fig.png)",
        source_id=_SOURCE,
        href_to_hash={"fig.png": _HASH},
    )

    assert rewritten == f"![a *b* _c_](/api/sources/{_SOURCE}/media/{_HASH})"
    assert rewritten.count("![") == 1
    assert "*b*" in rewritten


def test_surrounding_prose_is_preserved() -> None:
    rewritten = rewrite_markdown_images(
        "See ![one](a.png) and ![two](b.png).",
        source_id=_SOURCE,
        href_to_hash={"a.png": _HASH},
    )

    assert rewritten == (f"See ![one](/api/sources/{_SOURCE}/media/{_HASH}) and ![two](b.png).")
