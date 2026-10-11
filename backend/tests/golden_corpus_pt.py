"""The Portuguese golden book — three short public-domain excerpts in pt (AD-037 pattern).

The English golden book (``golden_corpus``) proves retrieval and citations in
English; this one proves the same pipeline in Portuguese: OPF ``dc:language`` is
``pt``, so every chunk is stored with the ``portuguese`` text-search config, and a
question that uses another inflection of a word in a chapter (``recitou`` for
``recitando``, ``verso`` for ``versos``) still reaches that chapter through the
Portuguese stemmer. Built in code from the same EPUB-packing helpers — no committed
binary — and kept small: one short paragraph per chapter.

Provenance
----------
- Work: *Dom Casmurro*, by Joaquim Maria Machado de Assis (1839-1908), first
  published in 1899 (Rio de Janeiro and Paris: H. Garnier).
- Text: Project Gutenberg eBook #55752, "Dom Casmurro" (released 2017-10-15,
  updated 2024-10-23), https://www.gutenberg.org/ebooks/55752 — plain-text file
  ``pg55752.txt``, fetched 2026-10-11.
- Licence: public domain. The author died on 1908-09-29, so the work entered the
  public domain in Brazil in 1979 (Lei 9.610/1998, art. 41: seventy years counted
  from 1 January after the author's death) and is public domain in the United
  States (published before 1930) and in every life+70 or shorter jurisdiction.
  Project Gutenberg's licence governs only its trademark and its own edition's
  packaging; these excerpts carry neither.
- Excerpts are quoted verbatim, keeping the 1899 orthography the Gutenberg edition
  preserves (``chapéo``, ``atraz``, ``Matacavallos``): chapter I "Do titulo." (its
  first sentences), chapter II "Do livro." (one sentence of its second paragraph)
  and chapter III "A denuncia." (its first paragraph). Chapter titles drop the
  trailing full stop.
"""

from __future__ import annotations

from tests.epub_builder import CONTAINER, build_doc, zip_epub

_CH1_TITLE = "Do titulo"
_CH1_PROSE = (
    "Uma noite destas, vindo da cidade para o Engenho Novo, encontrei no trem da "
    "Central um rapaz aqui do bairro, que eu conheço de vista e de chapéo. "
    "Comprimentou-me, sentou-se ao pé de mim, falou da lua e dos ministros, e "
    "acabou recitando-me versos."
)
_CH2_TITLE = "Do livro"
_CH2_PROSE = (
    "Na principal destas, a pintura do tecto e das paredes é mais ou menos egual, "
    "umas grinaldas de flores miudas e grandes passaros que as tomam nos bicos, de "
    "espaço a espaço."
)
_CH3_TITLE = "A denuncia"
_CH3_PROSE = (
    "Ia a entrar na sala de visitas, quando ouvi proferir o meu nome e escondi-me "
    "atraz da porta. A casa era a da rua de Matacavallos, o mez Novembro, o anno é "
    "que é um tanto remoto, mas eu não hei de trocar as datas á minha vida só para "
    "agradar ás pessoas que não amam historias velhas; o anno era de 1857."
)

# Hrefs distinct from the English golden book's, so an anchor can never be read
# against the wrong book.
_CHAPTERS = (
    ("cap1.xhtml", _CH1_TITLE, _CH1_PROSE),
    ("cap2.xhtml", _CH2_TITLE, _CH2_PROSE),
    ("cap3.xhtml", _CH3_TITLE, _CH3_PROSE),
)

PT_GOLDEN_TITLE = "Dom Casmurro"
PT_GOLDEN_AUTHORS = ("Machado de Assis",)
PT_GOLDEN_LANGUAGE = "pt"
PT_GOLDEN_PROVENANCE = {
    "work": "Dom Casmurro (1899)",
    "author": "Joaquim Maria Machado de Assis (1839-1908)",
    "source": "https://www.gutenberg.org/ebooks/55752",
    "licence": "public domain (author died 1908; Brazil Lei 9.610/1998 art. 41; US pre-1930)",
}

_OPF = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
    'unique-identifier="bookid">\n'
    '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
    '    <dc:identifier id="bookid">urn:uuid:learny-golden-pt</dc:identifier>\n'
    f"    <dc:title>{PT_GOLDEN_TITLE}</dc:title>\n"
    f"    <dc:creator>{PT_GOLDEN_AUTHORS[0]}</dc:creator>\n"
    f"    <dc:language>{PT_GOLDEN_LANGUAGE}</dc:language>\n"
    "  </metadata>\n"
    "  <manifest>\n"
    '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
    'properties="nav"/>\n'
    + "".join(
        f'    <item id="{href[:-6]}" href="{href}" media-type="application/xhtml+xml"/>\n'
        for href, _, _ in _CHAPTERS
    )
    + "  </manifest>\n"
    "  <spine>\n"
    + "".join(f'    <itemref idref="{href[:-6]}"/>\n' for href, _, _ in _CHAPTERS)
    + "  </spine>\n"
    "</package>\n"
)

_NAV = build_doc(
    "Índice",
    '<nav xmlns:epub="http://www.idpf.org/2007/ops" epub:type="toc">\n'
    "  <ol>\n"
    + "".join(f'    <li><a href="{href}">{title}</a></li>\n' for href, title, _ in _CHAPTERS)
    + "  </ol>\n"
    "</nav>",
)


def portuguese_golden_book() -> bytes:
    """The Portuguese golden EPUB: three chapters of *Dom Casmurro*, one paragraph each."""
    members: dict[str, str | bytes] = {
        "META-INF/container.xml": CONTAINER,
        "content.opf": _OPF,
        "nav.xhtml": _NAV,
    }
    for href, title, prose in _CHAPTERS:
        members[href] = build_doc(title, f"<h1>{title}</h1>\n<p>{prose}</p>")
    return zip_epub(members)


# Ordered ingestion golden, built the same way as the English book's: one chunk per
# chapter, the heading Markdown and the paragraph joined by a blank line.
EXPECTED_PT_GOLDEN_SECTIONS = tuple(
    {
        "section_path": (title,),
        "anchor": href,
        "depth": 0,
        "chunk_texts": (f"# {title}\n\n{prose}",),
    }
    for href, title, prose in _CHAPTERS
)
PT_GOLDEN_SECTION_ANCHORS = frozenset(href for href, _, _ in _CHAPTERS)
EXPECTED_PT_GOLDEN_BLOCK_COUNT = 2 * len(_CHAPTERS)
EXPECTED_PT_GOLDEN_CHUNK_COUNT = len(_CHAPTERS)

PT_CH1_ANCHOR = "cap1.xhtml"
PT_CH2_ANCHOR = "cap2.xhtml"
PT_CH3_ANCHOR = "cap3.xhtml"
