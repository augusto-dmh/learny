"""Synthetic EPUB fixtures for the corpus pipeline (design §Components, D-5).

EPUBs are built **as code** from stdlib ``zipfile`` plus literal OPF/XHTML
strings — no committed binaries and no ebooklib writer, so the parser tests are
not "parse what we wrote" tautologies and every byte is reviewable in the diff.

Each builder returns a full EPUB (or, for ``not_an_epub``, deliberately invalid
bytes). The ``EXPECTED_*`` constants describe the exact structure the parser
(T6) must recover — book metadata, spine-ordered sections with their TOC-derived
paths/anchors/depths (A-1..A-4), and the global block sequence with preserved
HTML (CORP-01..03). They are the golden targets the parser asserts against.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from io import BytesIO


@dataclass(frozen=True)
class ExpectedBlock:
    """One content block the parser must emit, in global reading order."""

    position: int
    block_type: str
    html: str


@dataclass(frozen=True)
class ExpectedSection:
    """One section the parser must emit, with its TOC-derived identity."""

    position: int
    title: str
    depth: int
    section_path: tuple[str, ...]
    anchor: str
    blocks: tuple[ExpectedBlock, ...]


_XHTML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    "<!DOCTYPE html>\n"
    '<html xmlns="http://www.w3.org/1999/xhtml">\n'
    "<head><title>{title}</title></head>\n"
    "<body>\n{body}\n</body>\n</html>\n"
)


def _doc(title: str, body: str) -> str:
    return _XHTML.format(title=title, body=body)


def _zip(members: dict[str, str | bytes]) -> bytes:
    """Pack ``members`` into an EPUB ZIP with an uncompressed leading mimetype."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            zipfile.ZipInfo("mimetype"),
            "application/epub+zip",
            compress_type=zipfile.ZIP_STORED,
        )
        for name, content in members.items():
            data = content.encode("utf-8") if isinstance(content, str) else content
            archive.writestr(name, data)
    return buffer.getvalue()


_CONTAINER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<container version="1.0" '
    'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
    "  <rootfiles>\n"
    '    <rootfile full-path="content.opf" '
    'media-type="application/oebps-package+xml"/>\n'
    "  </rootfiles>\n"
    "</container>\n"
)


# --- valid_book -------------------------------------------------------------
#
# A complete, well-formed EPUB exercising every branch of the parser: two-level
# TOC (Part I › {Chapter 1, Section 2}) with an in-document fragment anchor, a
# spine document absent from the TOC (A-2 fallback), a non-linear spine item
# (A-3), an image and a footnote, and a dangling TOC entry whose href is not in
# the spine (dropped without error).

_VALID_OPF = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
    'unique-identifier="bookid">\n'
    '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
    '    <dc:identifier id="bookid">urn:uuid:learny-valid</dc:identifier>\n'
    "    <dc:title>The Test Book</dc:title>\n"
    "    <dc:creator>Ada Lovelace</dc:creator>\n"
    "    <dc:creator>Alan Turing</dc:creator>\n"
    "    <dc:language>en</dc:language>\n"
    "  </metadata>\n"
    "  <manifest>\n"
    '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
    'properties="nav"/>\n'
    '    <item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>\n'
    '    <item id="part1" href="part1.xhtml" media-type="application/xhtml+xml"/>\n'
    '    <item id="chap1" href="chap1.xhtml" media-type="application/xhtml+xml"/>\n'
    '    <item id="chap2" href="chap2.xhtml" media-type="application/xhtml+xml"/>\n'
    '    <item id="notes" href="notes.xhtml" media-type="application/xhtml+xml"/>\n'
    '    <item id="coverimg" href="cover.png" media-type="image/png"/>\n'
    "  </manifest>\n"
    "  <spine>\n"
    '    <itemref idref="cover"/>\n'
    '    <itemref idref="part1"/>\n'
    '    <itemref idref="chap1"/>\n'
    '    <itemref idref="chap2"/>\n'
    '    <itemref idref="notes" linear="no"/>\n'
    "  </spine>\n"
    "</package>\n"
)

_VALID_NAV = _doc(
    "Contents",
    "<nav xmlns:epub=\"http://www.idpf.org/2007/ops\" epub:type=\"toc\">\n"
    "  <ol>\n"
    "    <li><a href=\"part1.xhtml\">Part I</a>\n"
    "      <ol>\n"
    "        <li><a href=\"chap1.xhtml\">Chapter 1</a></li>\n"
    "        <li><a href=\"chap1.xhtml#sec-2\">Section 2</a></li>\n"
    "      </ol>\n"
    "    </li>\n"
    "    <li><a href=\"chap2.xhtml\">Chapter 2</a></li>\n"
    "    <li><a href=\"missing.xhtml\">Ghost Chapter</a></li>\n"
    "  </ol>\n"
    "</nav>",
)

_VALID_COVER = _doc(
    "Cover",
    '<h1>Cover</h1>\n<img src="cover.png" alt="Cover image"/>',
)
_VALID_PART1 = _doc(
    "Part I",
    "<h1>Part I</h1>\n<p>Introduction to part one.</p>",
)
_VALID_CHAP1 = _doc(
    "Chapter 1",
    "<h2>Chapter 1</h2>\n"
    "<p>First paragraph of chapter one.</p>\n"
    "<ul><li>alpha</li><li>beta</li></ul>\n"
    '<h3 id="sec-2">Section 2</h3>\n'
    '<p>Second section paragraph.<a href="#fn1">1</a></p>\n'
    '<aside id="fn1">Footnote text.</aside>',
)
_VALID_CHAP2 = _doc(
    "Chapter 2",
    "<h1>Chapter 2</h1>\n<p>Chapter two content.</p>",
)
_VALID_NOTES = _doc(
    "Endnotes",
    "<h1>Endnotes</h1>\n<p>These notes are non-linear.</p>",
)


def valid_book() -> bytes:
    """A well-formed EPUB covering every parser branch (see module docstring)."""
    return _zip(
        {
            "META-INF/container.xml": _CONTAINER,
            "content.opf": _VALID_OPF,
            "nav.xhtml": _VALID_NAV,
            "cover.xhtml": _VALID_COVER,
            "part1.xhtml": _VALID_PART1,
            "chap1.xhtml": _VALID_CHAP1,
            "chap2.xhtml": _VALID_CHAP2,
            "notes.xhtml": _VALID_NOTES,
            "cover.png": b"\x89PNG\r\n\x1a\n",
        }
    )


EXPECTED_VALID_TITLE = "The Test Book"
EXPECTED_VALID_AUTHORS = ("Ada Lovelace", "Alan Turing")
EXPECTED_VALID_LANGUAGE = "en"

EXPECTED_VALID_SECTIONS = (
    ExpectedSection(
        position=0,
        title="Cover",
        depth=0,
        section_path=("Cover",),
        anchor="cover.xhtml",
        blocks=(
            ExpectedBlock(0, "heading", "<h1>Cover</h1>"),
            ExpectedBlock(1, "img", '<img alt="Cover image" src="cover.png"/>'),
        ),
    ),
    ExpectedSection(
        position=1,
        title="Part I",
        depth=0,
        section_path=("Part I",),
        anchor="part1.xhtml",
        blocks=(
            ExpectedBlock(2, "heading", "<h1>Part I</h1>"),
            ExpectedBlock(3, "paragraph", "<p>Introduction to part one.</p>"),
        ),
    ),
    ExpectedSection(
        position=2,
        title="Chapter 1",
        depth=1,
        section_path=("Part I", "Chapter 1"),
        anchor="chap1.xhtml",
        blocks=(
            ExpectedBlock(4, "heading", "<h2>Chapter 1</h2>"),
            ExpectedBlock(5, "paragraph", "<p>First paragraph of chapter one.</p>"),
            ExpectedBlock(6, "list", "<ul><li>alpha</li><li>beta</li></ul>"),
        ),
    ),
    ExpectedSection(
        position=3,
        title="Section 2",
        depth=1,
        section_path=("Part I", "Section 2"),
        anchor="chap1.xhtml#sec-2",
        blocks=(
            ExpectedBlock(7, "heading", '<h3 id="sec-2">Section 2</h3>'),
            ExpectedBlock(
                8,
                "paragraph",
                '<p>Second section paragraph.<a href="#fn1">1</a></p>',
            ),
            ExpectedBlock(9, "other", '<aside id="fn1">Footnote text.</aside>'),
        ),
    ),
    ExpectedSection(
        position=4,
        title="Chapter 2",
        depth=0,
        section_path=("Chapter 2",),
        anchor="chap2.xhtml",
        blocks=(
            ExpectedBlock(10, "heading", "<h1>Chapter 2</h1>"),
            ExpectedBlock(11, "paragraph", "<p>Chapter two content.</p>"),
        ),
    ),
)


# --- no_toc_book ------------------------------------------------------------
#
# No nav and no NCX, so every section is derived per spine document via the A-2
# fallback: the first heading's text, else the href stem. Metadata is minimal
# (identifier only) so title/language are absent and authors empty (CORP-01).

_NO_TOC_OPF = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
    'unique-identifier="bookid">\n'
    '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
    '    <dc:identifier id="bookid">urn:uuid:learny-no-toc</dc:identifier>\n'
    "  </metadata>\n"
    "  <manifest>\n"
    '    <item id="intro" href="intro.xhtml" media-type="application/xhtml+xml"/>\n'
    '    <item id="body" href="body.xhtml" media-type="application/xhtml+xml"/>\n'
    "  </manifest>\n"
    "  <spine>\n"
    '    <itemref idref="intro"/>\n'
    '    <itemref idref="body"/>\n'
    "  </spine>\n"
    "</package>\n"
)

_NO_TOC_INTRO = _doc(
    "Intro",
    "<h1>Introduction</h1>\n<p>Opening remarks.</p>",
)
_NO_TOC_BODY = _doc(
    "Body",
    "<p>No heading here.</p>",
)


def no_toc_book() -> bytes:
    """An EPUB with no TOC and minimal metadata (A-2 fallback, CORP-01 nulls)."""
    return _zip(
        {
            "META-INF/container.xml": _CONTAINER,
            "content.opf": _NO_TOC_OPF,
            "intro.xhtml": _NO_TOC_INTRO,
            "body.xhtml": _NO_TOC_BODY,
        }
    )


EXPECTED_NO_TOC_SECTIONS = (
    ExpectedSection(
        position=0,
        title="Introduction",
        depth=0,
        section_path=("Introduction",),
        anchor="intro.xhtml",
        blocks=(
            ExpectedBlock(0, "heading", "<h1>Introduction</h1>"),
            ExpectedBlock(1, "paragraph", "<p>Opening remarks.</p>"),
        ),
    ),
    ExpectedSection(
        position=1,
        title="body",
        depth=0,
        section_path=("body",),
        anchor="body.xhtml",
        blocks=(ExpectedBlock(2, "paragraph", "<p>No heading here.</p>"),),
    ),
)


# --- broken_spine_book ------------------------------------------------------
#
# A well-formed ZIP whose spine references an idref with no manifest item; the
# parser must raise InvalidEpubError on the unresolvable spine entry (CORP-06).

_BROKEN_OPF = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
    'unique-identifier="bookid">\n'
    '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
    '    <dc:identifier id="bookid">urn:uuid:learny-broken</dc:identifier>\n'
    "    <dc:title>Broken</dc:title>\n"
    "  </metadata>\n"
    "  <manifest>\n"
    '    <item id="chap1" href="chap1.xhtml" media-type="application/xhtml+xml"/>\n'
    "  </manifest>\n"
    "  <spine>\n"
    '    <itemref idref="chap1"/>\n'
    '    <itemref idref="ghost"/>\n'
    "  </spine>\n"
    "</package>\n"
)


def broken_spine_book() -> bytes:
    """A valid ZIP with an unresolvable spine idref (terminal parse, CORP-06)."""
    return _zip(
        {
            "META-INF/container.xml": _CONTAINER,
            "content.opf": _BROKEN_OPF,
            "chap1.xhtml": _doc("Chapter 1", "<h1>Chapter 1</h1>\n<p>Body.</p>"),
        }
    )


# --- empty_body_book --------------------------------------------------------
#
# A single spine document with an empty <body>; the parser must yield a section
# with zero blocks and still succeed (edge case).

_EMPTY_OPF = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
    'unique-identifier="bookid">\n'
    '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
    '    <dc:identifier id="bookid">urn:uuid:learny-empty</dc:identifier>\n'
    "    <dc:title>Empty</dc:title>\n"
    "  </metadata>\n"
    "  <manifest>\n"
    '    <item id="hollow" href="hollow.xhtml" media-type="application/xhtml+xml"/>\n'
    "  </manifest>\n"
    "  <spine>\n"
    '    <itemref idref="hollow"/>\n'
    "  </spine>\n"
    "</package>\n"
)


def empty_body_book() -> bytes:
    """An EPUB whose only spine document has an empty body (zero-block section)."""
    return _zip(
        {
            "META-INF/container.xml": _CONTAINER,
            "content.opf": _EMPTY_OPF,
            "hollow.xhtml": _doc("Hollow", ""),
        }
    )


EXPECTED_EMPTY_SECTION = ExpectedSection(
    position=0,
    title="hollow",
    depth=0,
    section_path=("hollow",),
    anchor="hollow.xhtml",
    blocks=(),
)


def not_an_epub() -> bytes:
    """Plain, non-ZIP bytes — a corrupt archive the parser must reject (CORP-06)."""
    return b"this is plainly not an epub archive"
