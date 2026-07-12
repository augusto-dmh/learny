"""The Cycle-8 golden evaluation book — a topically-rich synthetic EPUB (AD-037).

Unlike the structural parser fixtures in ``fixtures_epub`` (thin prose, chosen to
exercise TOC/anchor edge cases), this single well-formed EPUB3 gives each chapter
a paragraph of **lexically disjoint** prose so a retrieval query built from one
chapter's vocabulary selects that chapter unambiguously (a rank-1 both-arm hit)
under the deterministic embedding + lexical arms. It is the shared corpus for the
retrieval-recall and citation-grounding golden checks; its ``EXPECTED_GOLDEN_*``
constants are the versioned ingestion targets. Built as reviewable code from the
same EPUB-packing helpers as the parser fixtures — no committed binary, no
third-party text (AD-037 resolves TDD open question #9).
"""

from __future__ import annotations

from tests.fixtures_epub import _CONTAINER, _doc, _zip

# Each chapter's TOC label == its <h1> so the section title and heading block read
# the same; the prose vocabularies are pairwise disjoint (tides / volcanoes /
# printing) and share no content token with golden_expected.UNSUPPORTED_QUESTION.
_CH1_TITLE = "The Rhythm of Tides"
_CH1_PROSE = (
    "Ocean tides rise and fall because the moon's gravity pulls seawater across "
    "the planet. When the moon and sun align their gravity, spring tides swell "
    "the highest water along every coastline."
)
_CH2_TITLE = "How Volcanoes Erupt"
_CH2_PROSE = (
    "A volcano erupts when molten magma escapes upward through a vent in the "
    "crust. Basalt lava flows spread outward while ash billows from the crater "
    "during the eruption."
)
_CH3_TITLE = "The Printing Press"
_CH3_PROSE = (
    "The printing press let a workshop reproduce a page from movable metal type. "
    "Inked letters pressed onto paper carried pamphlets and books outward faster "
    "than any scribe could copy them."
)

_CHAPTERS = (
    ("ch1.xhtml", _CH1_TITLE, _CH1_PROSE),
    ("ch2.xhtml", _CH2_TITLE, _CH2_PROSE),
    ("ch3.xhtml", _CH3_TITLE, _CH3_PROSE),
)

GOLDEN_TITLE = "Field Notes on Change"
GOLDEN_AUTHORS = ("Marie Curie",)
GOLDEN_LANGUAGE = "en"

_OPF = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
    'unique-identifier="bookid">\n'
    '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
    '    <dc:identifier id="bookid">urn:uuid:learny-golden</dc:identifier>\n'
    f"    <dc:title>{GOLDEN_TITLE}</dc:title>\n"
    f"    <dc:creator>{GOLDEN_AUTHORS[0]}</dc:creator>\n"
    f"    <dc:language>{GOLDEN_LANGUAGE}</dc:language>\n"
    "  </metadata>\n"
    "  <manifest>\n"
    '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
    'properties="nav"/>\n'
    '    <item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>\n'
    '    <item id="ch2" href="ch2.xhtml" media-type="application/xhtml+xml"/>\n'
    '    <item id="ch3" href="ch3.xhtml" media-type="application/xhtml+xml"/>\n'
    "  </manifest>\n"
    "  <spine>\n"
    '    <itemref idref="ch1"/>\n'
    '    <itemref idref="ch2"/>\n'
    '    <itemref idref="ch3"/>\n'
    "  </spine>\n"
    "</package>\n"
)

_NAV = _doc(
    "Contents",
    '<nav xmlns:epub="http://www.idpf.org/2007/ops" epub:type="toc">\n'
    "  <ol>\n"
    + "".join(f'    <li><a href="{href}">{title}</a></li>\n' for href, title, _ in _CHAPTERS)
    + "  </ol>\n"
    "</nav>",
)


def golden_book() -> bytes:
    """The golden evaluation EPUB: three chapters of lexically disjoint prose."""
    members: dict[str, str | bytes] = {
        "META-INF/container.xml": _CONTAINER,
        "content.opf": _OPF,
        "nav.xhtml": _NAV,
    }
    for href, title, prose in _CHAPTERS:
        members[href] = _doc(title, f"<h1>{title}</h1>\n<p>{prose}</p>")
    return _zip(members)


# The single chunk each chapter packs to: the heading Markdown ("# <title>") and
# the paragraph text joined by a blank line (Bs4MarkupConverter + pack_chunks with
# both blocks under chunk_max_chars → one chunk). These are the EVAL-03 targets.
def _chunk_text(title: str, prose: str) -> str:
    return f"# {title}\n\n{prose}"


# Ordered ingestion golden: (section_path, anchor, depth, chunk_texts) per chapter.
EXPECTED_GOLDEN_SECTIONS = tuple(
    {
        "section_path": (title,),
        "anchor": href,
        "depth": 0,
        "chunk_texts": (_chunk_text(title, prose),),
    }
    for href, title, prose in _CHAPTERS
)

# The book's section anchors — the grounding bound for citations (EVAL-07) and the
# subset check for every case (EVAL-09 self-consistency).
GOLDEN_SECTION_ANCHORS = frozenset(href for href, _, _ in _CHAPTERS)

# One heading + one paragraph block per chapter.
EXPECTED_GOLDEN_BLOCK_COUNT = 2 * len(_CHAPTERS)
EXPECTED_GOLDEN_CHUNK_COUNT = len(_CHAPTERS)

# Anchors keyed by the vocabulary a query/question targets (used to build cases).
CH1_ANCHOR = "ch1.xhtml"
CH2_ANCHOR = "ch2.xhtml"
CH3_ANCHOR = "ch3.xhtml"
