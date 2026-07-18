"""Format-dispatch factory for document parsers (design §Components 5, ING-15).

Selects the concrete :class:`~app.domain.ports.DocumentParserPort` adapter from a
source's content type at the worker composition root. EPUB stays on ebooklib
(ADR-0011); PDF uses Docling, whose import is probed lazily so a PDF misrouted to
a worker without the ``pdf`` extra fails terminally with a clear operator message
instead of retry-looping. An unknown content type is likewise a terminal
:class:`~app.application.errors.InvalidDocumentError`. No Celery/SQLAlchemy type
enters here — this is plain infrastructure composition (ADR-0009).
"""

from __future__ import annotations

from app.application.errors import InvalidDocumentError
from app.core.config import get_settings
from app.domain.ports import DocumentParserPort
from app.infrastructure.ingestion.epub import EbooklibEpubParser

EPUB_CONTENT_TYPE = "application/epub+zip"
PDF_CONTENT_TYPE = "application/pdf"


def build_parser(content_type: str) -> DocumentParserPort:
    """Return the parser adapter for ``content_type`` (ING-15).

    ``application/epub+zip`` → the ebooklib parser (configured with the archive
    inflation cap); ``application/pdf`` → the Docling parser, guarded by a lazy
    import so a worker without the ``pdf`` extra fails terminally; any other type
    → a terminal ``InvalidDocumentError`` so a misrouted task never retry-loops.
    """
    if content_type == EPUB_CONTENT_TYPE:
        return EbooklibEpubParser(
            max_uncompressed_bytes=get_settings().epub_max_uncompressed_bytes
        )
    if content_type == PDF_CONTENT_TYPE:
        try:
            import docling  # noqa: F401 — availability probe for the pdf extra
        except ImportError as exc:
            raise InvalidDocumentError(
                "pdf support not installed in this worker"
            ) from exc
        from app.infrastructure.ingestion.docling_pdf import DoclingPdfParser

        settings = get_settings()
        return DoclingPdfParser(
            ocr_enabled=settings.pdf_ocr_enabled,
            ocr_langs=settings.pdf_ocr_lang_list(),
        )
    raise InvalidDocumentError(f"unsupported source content type: {content_type!r}")
