"""Selective-OCR retry logic of the Docling PDF parser (unit, CI-safe).

The heavy ``docling`` runtime is absent in CI, so these tests install minimal
fake ``docling`` modules into ``sys.modules`` that record the pipeline options
the adapter builds and return canned ``docling_core`` documents. That exercises
the REAL ``_convert`` (option construction, stream handling, error wrap) and the
REAL ``parse`` retry policy end to end — only Docling's conversion engine is
faked. Spec: a textless fast path retries exactly once with OCR when enabled;
conversion *errors* never retry; disabled OCR reproduces the OCR-less behavior.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field
from typing import Any

import pytest
from docling_core.types.doc import DocItemLabel, DoclingDocument

from app.application.errors import InvalidDocumentError


def _text_doc() -> DoclingDocument:
    doc = DoclingDocument(name="book")
    doc.add_heading("Chapter One", level=1)
    doc.add_text(label=DocItemLabel.TEXT, text="Recovered body text.")
    return doc


def _empty_doc() -> DoclingDocument:
    return DoclingDocument(name="book")


@dataclass
class _FakeDocling:
    """Canned conversion results + a recorder of each pass's pipeline options."""

    results: list[Any]
    calls: list[Any] = field(default_factory=list)

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = self

        class PdfPipelineOptions:
            def __init__(
                self, do_ocr: bool, do_table_structure: bool, ocr_options: Any = None
            ) -> None:
                self.do_ocr = do_ocr
                self.do_table_structure = do_table_structure
                self.ocr_options = ocr_options

        class EasyOcrOptions:
            def __init__(self, lang: list[str]) -> None:
                self.lang = lang

        class PdfFormatOption:
            def __init__(self, pipeline_options: PdfPipelineOptions) -> None:
                self.pipeline_options = pipeline_options

        class DocumentConverter:
            def __init__(self, format_options: dict[Any, PdfFormatOption]) -> None:
                (self._format_option,) = format_options.values()

            def convert(self, stream: Any, raises_on_error: bool) -> Any:
                fake.calls.append(self._format_option.pipeline_options)
                outcome = fake.results[len(fake.calls) - 1]
                if isinstance(outcome, Exception):
                    raise outcome
                return types.SimpleNamespace(document=outcome)

        root = types.ModuleType("docling")
        datamodel = types.ModuleType("docling.datamodel")
        base_models = types.ModuleType("docling.datamodel.base_models")
        base_models.InputFormat = types.SimpleNamespace(PDF="pdf")
        pipeline = types.ModuleType("docling.datamodel.pipeline_options")
        pipeline.PdfPipelineOptions = PdfPipelineOptions
        pipeline.EasyOcrOptions = EasyOcrOptions
        converter_mod = types.ModuleType("docling.document_converter")
        converter_mod.DocumentConverter = DocumentConverter
        converter_mod.PdfFormatOption = PdfFormatOption
        for name, module in {
            "docling": root,
            "docling.datamodel": datamodel,
            "docling.datamodel.base_models": base_models,
            "docling.datamodel.pipeline_options": pipeline,
            "docling.document_converter": converter_mod,
        }.items():
            monkeypatch.setitem(sys.modules, name, module)


def _parser(**kwargs: Any):
    from app.infrastructure.ingestion.docling_pdf import DoclingPdfParser

    return DoclingPdfParser(**kwargs)


def test_pdf_with_text_takes_the_fast_path_without_ocr(monkeypatch) -> None:
    fake = _FakeDocling(results=[_text_doc()])
    fake.install(monkeypatch)

    book = _parser().parse(b"%PDF", filename="book.pdf")

    assert len(fake.calls) == 1
    assert fake.calls[0].do_ocr is False
    assert fake.calls[0].ocr_options is None
    assert book.sections and book.sections[0].title == "Chapter One"


def test_textless_pdf_retries_exactly_once_with_ocr_langs(monkeypatch) -> None:
    # The OCR pass must actually carry do_ocr=True and the configured languages
    # (payload rule) and yield the same mapped-book contract as the fast path.
    fake = _FakeDocling(results=[_empty_doc(), _text_doc()])
    fake.install(monkeypatch)

    book = _parser(ocr_enabled=True, ocr_langs=("en", "pt")).parse(
        b"%PDF", filename="scan.pdf"
    )

    assert [options.do_ocr for options in fake.calls] == [False, True]
    assert fake.calls[1].do_table_structure is True
    assert fake.calls[1].ocr_options.lang == ["en", "pt"]
    assert book.sections and book.sections[0].blocks


def test_textless_pdf_after_ocr_is_terminal(monkeypatch) -> None:
    fake = _FakeDocling(results=[_empty_doc(), _empty_doc()])
    fake.install(monkeypatch)

    with pytest.raises(InvalidDocumentError, match="'scan.pdf' has no extractable text"):
        _parser().parse(b"%PDF", filename="scan.pdf")
    assert [options.do_ocr for options in fake.calls] == [False, True]


def test_disabled_ocr_reproduces_the_ocr_less_behavior(monkeypatch) -> None:
    # Kill-switch: one conversion, no retry, the pre-OCR error shape.
    fake = _FakeDocling(results=[_empty_doc()])
    fake.install(monkeypatch)

    with pytest.raises(InvalidDocumentError, match="'scan.pdf' has no extractable text"):
        _parser(ocr_enabled=False).parse(b"%PDF", filename="scan.pdf")
    assert [options.do_ocr for options in fake.calls] == [False]


def test_conversion_error_is_terminal_and_never_retried(monkeypatch) -> None:
    # Only a *successful but textless* conversion triggers OCR; a corrupt PDF
    # fails on the first pass without a second conversion.
    fake = _FakeDocling(results=[RuntimeError("broken xref")])
    fake.install(monkeypatch)

    with pytest.raises(InvalidDocumentError, match="could not read PDF 'bad.pdf'"):
        _parser().parse(b"%PDF", filename="bad.pdf")
    assert len(fake.calls) == 1


def test_error_during_the_ocr_retry_is_terminal(monkeypatch) -> None:
    # The retry's own error leg: a docling failure on the OCR pass surfaces as
    # the terminal could-not-read error (never swallowed into the no-text
    # message, never a third conversion).
    fake = _FakeDocling(results=[_empty_doc(), RuntimeError("ocr engine crashed")])
    fake.install(monkeypatch)

    with pytest.raises(InvalidDocumentError, match="could not read PDF 'scan.pdf'"):
        _parser().parse(b"%PDF", filename="scan.pdf")
    assert [options.do_ocr for options in fake.calls] == [False, True]


def test_factory_builds_the_parser_from_settings(monkeypatch) -> None:
    # The composition root threads the two OCR knobs from Settings.
    from app.core.config import get_settings
    from app.infrastructure.ingestion.factory import build_parser

    _FakeDocling(results=[]).install(monkeypatch)
    monkeypatch.setenv("LEARNY_PDF_OCR_ENABLED", "false")
    monkeypatch.setenv("LEARNY_PDF_OCR_LANGS", "pt")
    get_settings.cache_clear()
    try:
        parser = build_parser("application/pdf")
        assert parser._ocr_enabled is False
        assert parser._ocr_langs == ("pt",)
    finally:
        get_settings.cache_clear()
