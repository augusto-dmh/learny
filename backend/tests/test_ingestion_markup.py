"""T7 gate — Bs4MarkupConverter HTML→Markdown derivation (unit).

Derived from CORP-04 / A-6: headings become ``#``-levels, paragraphs plain text,
lists ``-``/``1.`` items with nested indentation, blockquotes ``>``, pre/code
fenced blocks, tables GitHub pipe tables, images ``![alt](src)``, links
``[text](href)``, and ``em``/``strong`` ``*``/``**``. Unknown elements degrade to
their text — never dropped — and empty input yields an empty string.
"""

from __future__ import annotations

from app.infrastructure.ingestion.markup import Bs4MarkupConverter

_conv = Bs4MarkupConverter()


def test_headings_become_hash_levels() -> None:
    assert _conv.to_markdown("<h1>One</h1>") == "# One"
    assert _conv.to_markdown("<h2>Two</h2>") == "## Two"
    assert _conv.to_markdown("<h3>Three</h3>") == "### Three"
    assert _conv.to_markdown("<h4>Four</h4>") == "#### Four"
    assert _conv.to_markdown("<h5>Five</h5>") == "##### Five"
    assert _conv.to_markdown("<h6>Six</h6>") == "###### Six"


def test_paragraph_becomes_plain_text() -> None:
    assert _conv.to_markdown("<p>Some plain text.</p>") == "Some plain text."


def test_unordered_list_uses_dash_markers() -> None:
    html = "<ul><li>alpha</li><li>beta</li></ul>"
    assert _conv.to_markdown(html) == "- alpha\n- beta"


def test_ordered_list_uses_numbered_markers() -> None:
    html = "<ol><li>alpha</li><li>beta</li></ol>"
    assert _conv.to_markdown(html) == "1. alpha\n2. beta"


def test_nested_list_indents_children() -> None:
    html = "<ul><li>alpha<ul><li>nested</li></ul></li><li>beta</li></ul>"
    assert _conv.to_markdown(html) == "- alpha\n  - nested\n- beta"


def test_blockquote_is_prefixed() -> None:
    assert _conv.to_markdown("<blockquote>Wisdom.</blockquote>") == "> Wisdom."


def test_pre_code_becomes_fenced_block() -> None:
    html = "<pre><code>x = 1</code></pre>"
    assert _conv.to_markdown(html) == "```\nx = 1\n```"


def test_table_becomes_github_pipe_table() -> None:
    html = (
        "<table><thead><tr><th>A</th><th>B</th></tr></thead>"
        "<tbody><tr><td>1</td><td>2</td></tr></tbody></table>"
    )
    assert _conv.to_markdown(html) == "| A | B |\n| --- | --- |\n| 1 | 2 |"


def test_image_becomes_markdown_image() -> None:
    html = '<img src="cover.png" alt="Cover image"/>'
    assert _conv.to_markdown(html) == "![Cover image](cover.png)"


def test_link_becomes_markdown_link() -> None:
    html = '<p>See <a href="https://example.test">the site</a>.</p>'
    assert _conv.to_markdown(html) == "See [the site](https://example.test)."


def test_emphasis_and_strong_become_markers() -> None:
    html = "<p>a <em>b</em> and <strong>c</strong></p>"
    assert _conv.to_markdown(html) == "a *b* and **c**"


def test_unknown_element_preserves_its_text() -> None:
    # <aside> is outside the A-6 set; its text must survive, never be dropped.
    assert _conv.to_markdown("<aside>Footnote text.</aside>") == "Footnote text."


def test_empty_input_returns_empty_string() -> None:
    assert _conv.to_markdown("") == ""


def test_whitespace_only_input_returns_empty_string() -> None:
    assert _conv.to_markdown("   \n\t ") == ""
