"""Markdown image-src rewrite — allowlisted media URLs, HTML left alone.

Derived from the figure-extract acceptance criteria: a mapped packaged-raster
href becomes ``/api/sources/{source_id}/media/{sha256}`` and must not remain
EPUB-relative; unmapped hrefs stay; the function rewrites markdown image syntax
only, never HTML ``<img>`` fragments; alt metacharacters are not wrapped as
nested markdown.
"""

from __future__ import annotations

from uuid import UUID

from app.application.media import media_object_key, rewrite_markdown_images

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


def test_media_object_key_is_the_one_shared_shape() -> None:
    # The stored-object shape the corpus builder PUTs, the media read serves,
    # and account erasure re-derives from markdown — pinned exactly once here.
    key = media_object_key(
        user_id=UUID("11111111-2222-3333-4444-555555555555"),
        source_id=_SOURCE,
        digest=_HASH,
    )
    assert key == (
        f"sources/{UUID('11111111-2222-3333-4444-555555555555')}/{_SOURCE}/media/{_HASH}.webp"
    )


def test_media_object_key_matches_the_embedded_markdown_url() -> None:
    # The markdown the corpus embeds and the key the object is stored under are
    # two halves of one contract: the digest in the URL is the key's file stem.
    markdown = rewrite_markdown_images(
        "![Cover](cover.png)", source_id=_SOURCE, href_to_hash={"cover.png": _HASH}
    )
    digest = markdown.rsplit("/", 1)[-1].rstrip(")")
    assert media_object_key(user_id=_SOURCE, source_id=_SOURCE, digest=digest).endswith(
        f"/media/{digest}.webp"
    )
