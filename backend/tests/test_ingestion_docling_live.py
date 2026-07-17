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
    # ING-14: a converted PDF with no extractable text (a scanned/blank page this
    # OCR-disabled pipeline cannot use) fails terminally.
    with pytest.raises(InvalidDocumentError):
        DoclingPdfParser().parse(_make_pdf([]), filename="blank.pdf")
