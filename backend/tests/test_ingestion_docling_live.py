"""T7 gate (integration, docling-gated) — real Docling PDF conversion (ING-10/14).

These exercise :class:`~app.infrastructure.ingestion.docling_pdf.DoclingPdfParser`
end to end against the actual ``docling`` runtime. ``docling`` is not installed in
CI (the ``pdf`` extra is optional, AD-089), so the whole module skips via
``importorskip`` and runs only where the extra is present (locally / the pdf
worker image). PDFs are generated in code — no binary fixtures — mirroring the
EPUB suite's build-in-code convention.
"""

from __future__ import annotations

import pytest

pytest.importorskip("docling")

from app.application.errors import InvalidDocumentError  # noqa: E402
from app.infrastructure.ingestion.docling_pdf import DoclingPdfParser  # noqa: E402


def _make_pdf(lines: list[tuple[int, int, str]]) -> bytes:
    """Build a minimal single-page PDF drawing ``(font_size, y, text)`` lines."""
    content = b""
    for size, y, text in lines:
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content += f"BT /F1 {size} Tf 72 {y} Td ({escaped}) Tj ET\n".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = b"%PDF-1.4\n"
    offsets: list[int] = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets:
        pdf += f"{offset:010d} 00000 n \n".encode()
    pdf += (
        b"trailer\n<< /Size " + str(len(objects) + 1).encode() + b" /Root 1 0 R >>\n"
        b"startxref\n" + str(xref).encode() + b"\n%%EOF"
    )
    return pdf


def _book_pdf() -> bytes:
    return _make_pdf(
        [
            (24, 700, "Chapter One"),
            (12, 670, "Some intro text here about the matter at hand."),
            (12, 650, "Another paragraph of body content follows here."),
        ]
    )


def test_parses_born_digital_pdf_into_sections_with_page_spans() -> None:
    # ING-10/12: a real conversion yields sections, typed blocks, page-spanned
    # content, and pdf: anchors (parity with the EPUB parsed-book shape).
    book = DoclingPdfParser().parse(_book_pdf(), filename="book.pdf")

    assert book.sections
    assert any(section.title == "Chapter One" for section in book.sections)
    assert all(section.anchor.startswith("pdf:") for section in book.sections)
    assert any(
        block.page_span == (1, 1)
        for section in book.sections
        for block in section.blocks
    )


def test_same_bytes_parse_to_identical_anchors() -> None:
    # ING-11: parsing identical bytes twice yields identical anchors and paths.
    pdf = _book_pdf()
    first = DoclingPdfParser().parse(pdf, filename="book.pdf")
    second = DoclingPdfParser().parse(pdf, filename="book.pdf")

    assert [s.anchor for s in first.sections] == [s.anchor for s in second.sections]
    assert [s.section_path for s in first.sections] == [s.section_path for s in second.sections]


def test_corrupt_pdf_is_terminal() -> None:
    # ING-14: unreadable bytes (also the branch encrypted PDFs raise through) are
    # a terminal InvalidDocumentError, not a retryable fault.
    with pytest.raises(InvalidDocumentError):
        DoclingPdfParser().parse(b"%PDF-1.4 not a real pdf at all", filename="corrupt.pdf")


def test_text_free_pdf_is_terminal() -> None:
    # ING-14 + the OCR retry's failure leg: a blank page has no text for the fast
    # path AND nothing for OCR to recognize, so even with OCR enabled the parse
    # is terminal.
    with pytest.raises(InvalidDocumentError):
        DoclingPdfParser().parse(_make_pdf([]), filename="blank.pdf")


# --- scanned (image-only) PDFs: the selective-OCR path -------------------------

# A 5x7 bitmap font for the letters the scanned fixture needs. Each glyph is
# seven 5-bit rows, MSB left; rendered into an uncompressed grayscale image
# XObject so the page has zero programmatic text — exactly a scanned book page.
_GLYPHS: dict[str, tuple[int, ...]] = {
    "C": (0b01110, 0b10001, 0b10000, 0b10000, 0b10000, 0b10001, 0b01110),
    "A": (0b01110, 0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0b10001),
    "P": (0b11110, 0b10001, 0b10001, 0b11110, 0b10000, 0b10000, 0b10000),
    "I": (0b11111, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b11111),
    "T": (0b11111, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100),
    "U": (0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110),
    "L": (0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b11111),
    "O": (0b01110, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110),
    "M": (0b10001, 0b11011, 0b10101, 0b10101, 0b10001, 0b10001, 0b10001),
    " ": (0, 0, 0, 0, 0, 0, 0),
}
_PX = 8  # image pixels per font pixel — big, clean glyphs for the OCR engine


def _raster_line(text: str) -> tuple[bytes, int, int]:
    """Render ``text`` as raw 8-bit grayscale bytes (white bg, black glyphs)."""
    cols = len(text) * 6 - 1  # 5 px glyph + 1 px spacing
    width, height = cols * _PX, 7 * _PX
    rows = bytearray()
    for row in range(height):
        font_row = row // _PX
        line = bytearray()
        for index, char in enumerate(text):
            bits = _GLYPHS[char][font_row]
            for bit in range(5):
                on = bits & (1 << (4 - bit))
                line.extend((0 if on else 255,) * _PX)
            if index < len(text) - 1:
                line.extend((255,) * _PX)
        rows.extend(line)
    return bytes(rows), width, height


def _scanned_pdf(text: str = "CAPITULO UM") -> bytes:
    """A single-page PDF whose only content is a rasterized line of ``text``."""
    raster, width, height = _raster_line(text)
    content = f"q {width} 0 0 {height} 60 620 cm /Im1 Do Q\n".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /XObject << /Im1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"endstream",
        b"<< /Type /XObject /Subtype /Image /Width " + str(width).encode()
        + b" /Height " + str(height).encode()
        + b" /ColorSpace /DeviceGray /BitsPerComponent 8 /Length "
        + str(len(raster)).encode() + b" >>\nstream\n" + raster + b"\nendstream",
    ]
    pdf = b"%PDF-1.4\n"
    offsets: list[int] = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets:
        pdf += f"{offset:010d} 00000 n \n".encode()
    pdf += (
        b"trailer\n<< /Size " + str(len(objects) + 1).encode() + b" /Root 1 0 R >>\n"
        b"startxref\n" + str(xref).encode() + b"\n%%EOF"
    )
    return pdf


def test_scanned_pdf_ingests_via_the_ocr_retry() -> None:
    # The OCR proof: an image-only page fails the fast path, succeeds through the
    # OCR retry, and yields the standard parsed shape (non-empty sections, pdf:
    # anchors, recognized words).
    book = DoclingPdfParser(ocr_enabled=True, ocr_langs=("en", "pt")).parse(
        _scanned_pdf(), filename="scan.pdf"
    )

    assert book.sections
    assert all(section.anchor.startswith("pdf:") for section in book.sections)
    texts = " ".join(
        block.html_fragment
        for section in book.sections
        for block in section.blocks
    ).lower()
    assert "capitulo" in texts


def test_scanned_pdf_is_terminal_when_ocr_is_disabled() -> None:
    # Kill-switch discrimination: the very same bytes fail without the retry,
    # proving OCR (not the fast path) is what ingested the scanned page.
    with pytest.raises(InvalidDocumentError):
        DoclingPdfParser(ocr_enabled=False).parse(_scanned_pdf(), filename="scan.pdf")
