"""Preserved-HTML → Markdown converter adapter (design §Components, A-6).

Implements :class:`~app.domain.ports.MarkupConverterPort` as a hand-rolled
BeautifulSoup walker over the closed A-6 element set — one fewer dependency than
``markdownify`` and full control over table/text preservation. The input is the
stored HTML fragment, never the EPUB, so the Markdown view is a derived
projection of the canonical corpus (CORP-04, ADR-0002). The guarantee is
bounded fidelity with *no dropped text*: any element outside the A-6 set degrades
to its plain text content (A-6).
"""

from __future__ import annotations

from bs4 import BeautifulSoup, NavigableString, Tag

_HEADING_LEVELS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_INDENT = "  "


class Bs4MarkupConverter:
    """``MarkupConverterPort`` rendering an HTML fragment to Markdown (A-6)."""

    def to_markdown(self, html: str) -> str:
        if not html or not html.strip():
            return ""
        soup = BeautifulSoup(html, "html.parser")
        blocks: list[str] = []
        for node in soup.children:
            if isinstance(node, Tag):
                rendered = _render_block(node)
            elif isinstance(node, NavigableString):
                rendered = str(node).strip()
            else:
                rendered = ""
            if rendered:
                blocks.append(rendered)
        return "\n\n".join(blocks).strip()


def _render_block(element: Tag) -> str:
    """Render a block-level element to its Markdown form (A-6)."""
    name = element.name
    if name in _HEADING_LEVELS:
        return f"{'#' * _HEADING_LEVELS[name]} {_inline(element)}".strip()
    if name == "p":
        return _inline(element).strip()
    if name in ("ul", "ol"):
        return _render_list(element, ordered=name == "ol", depth=0)
    if name == "blockquote":
        inner = _inline(element).strip()
        return "\n".join(f"> {line}" for line in inner.splitlines()) or "> "
    if name in ("pre", "code"):
        return f"```\n{element.get_text()}\n```"
    if name == "table":
        return _render_table(element)
    if name == "img":
        return _image(element)
    if name == "hr":
        return "---"
    # Outside the A-6 set: degrade to text so nothing is ever dropped (A-6).
    return element.get_text().strip()


def _inline(node: Tag, *, skip_lists: bool = False) -> str:
    """Render a node's children as inline Markdown, preserving all text."""
    parts: list[str] = []
    for child in node.children:
        if isinstance(child, NavigableString):
            parts.append(str(child))
            continue
        if not isinstance(child, Tag):
            continue
        name = child.name
        if skip_lists and name in ("ul", "ol"):
            continue
        if name == "a":
            parts.append(f"[{_inline(child)}]({child.get('href', '')})")
        elif name in ("em", "i"):
            parts.append(f"*{_inline(child)}*")
        elif name in ("strong", "b"):
            parts.append(f"**{_inline(child)}**")
        elif name == "code":
            parts.append(f"`{_inline(child)}`")
        elif name == "img":
            parts.append(_image(child))
        elif name == "br":
            parts.append("\n")
        else:
            parts.append(_inline(child))
    return "".join(parts)


def _render_list(element: Tag, *, ordered: bool, depth: int) -> str:
    """Render a ``ul``/``ol`` to dash/number items with nested indentation."""
    lines: list[str] = []
    index = 1
    for item in element.find_all("li", recursive=False):
        marker = f"{index}." if ordered else "-"
        text = _inline(item, skip_lists=True).strip()
        lines.append(f"{_INDENT * depth}{marker} {text}".rstrip())
        index += 1
        for sublist in item.find_all(("ul", "ol"), recursive=False):
            lines.append(_render_list(sublist, ordered=sublist.name == "ol", depth=depth + 1))
    return "\n".join(lines)


def _render_table(element: Tag) -> str:
    """Render a ``table`` to a GitHub pipe table (header row + separator)."""
    rows = element.find_all("tr")
    if not rows:
        return ""
    header = [_inline(cell).strip() for cell in rows[0].find_all(("th", "td"))]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in rows[1:]:
        cells = [_inline(cell).strip() for cell in row.find_all(("th", "td"))]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _image(element: Tag) -> str:
    return f"![{element.get('alt', '')}]({element.get('src', '')})"
