"""T8 gate — BuildCorpus application service (unit, in-memory fakes).

Drives ``BuildCorpus`` over fake ports (storage/parser/markup/corpus/events) so
the orchestration is asserted in isolation (CORP-01/04/05/08/10): the stored bytes
flow through to the parser, each section's Markdown is the ``\\n\\n``-join of the
converter's per-block output, chunks are packed from those block texts, the whole
aggregate — including zero-block sections — is persisted with ``schema_version=1``,
the ``corpus_built`` event carries the exact section/block/chunk counts, and a
storage or parser fault propagates unwrapped with nothing persisted (CORP-08).
"""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import count
from uuid import UUID, uuid4

import pytest

from app.application.corpus import BuildCorpus
from app.application.errors import InvalidEpubError
from app.domain.entities import (
    IngestionJob,
    ParsedBlock,
    ParsedBook,
    ParsedSection,
    Source,
)
from tests.fakes import (
    FailingStorage,
    FakeClock,
    FakeCorpusRepository,
    FakeEpubParser,
    FakeIngestionEventRepository,
    FakeMarkupConverter,
    FakeStorage,
)

_NOW = datetime(2026, 6, 27, 12, 0, 0, tzinfo=UTC)


def _source() -> Source:
    return Source(
        id=uuid4(),
        user_id=uuid4(),
        title="A Book",
        filename="a-book.epub",
        content_type="application/epub+zip",
        byte_size=10,
        checksum="d" * 64,
        object_key="sources/a-book.epub",
        status="processing",
        created_at=_NOW,
        updated_at=_NOW,
    )


def _job(source_id: UUID) -> IngestionJob:
    return IngestionJob(
        id=uuid4(),
        source_id=source_id,
        status="running",
        attempts=1,
        last_error=None,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _book() -> ParsedBook:
    """A two-section book: one with blocks, one with none (zero-block, kept)."""
    return ParsedBook(
        title="The Test Book",
        authors=("Ada", "Alan"),
        language="en",
        sections=(
            ParsedSection(
                position=0,
                title="One",
                depth=0,
                section_path=("One",),
                anchor="one.xhtml",
                blocks=(
                    ParsedBlock(0, "heading", "H0"),
                    ParsedBlock(1, "paragraph", "P0"),
                ),
            ),
            ParsedSection(
                position=1,
                title="Empty",
                depth=0,
                section_path=("Empty",),
                anchor="empty.xhtml",
                blocks=(),
            ),
        ),
    )


def _build(
    *, storage, parser, corpus, events, chunk_max_chars: int = 2000
) -> BuildCorpus:  # noqa: ANN001 — port doubles
    ids = count(1)
    return BuildCorpus(
        storage=storage,
        parser=parser,
        markup=FakeMarkupConverter(),
        corpus=corpus,
        events=events,
        clock=FakeClock(_NOW),
        ids=lambda: UUID(int=next(ids)),
        chunk_max_chars=chunk_max_chars,
    )


def test_build_corpus_persists_full_aggregate() -> None:
    source = _source()
    job = _job(source.id)
    book = _book()
    storage = FakeStorage()
    storage.objects[source.object_key] = b"epub-bytes"
    parser = FakeEpubParser(book=book)
    corpus = FakeCorpusRepository()
    events = FakeIngestionEventRepository()

    _build(storage=storage, parser=parser, corpus=corpus, events=events)(
        source=source, job=job
    )

    # The stored bytes flow through to the parser with the source filename.
    assert parser.calls == [(b"epub-bytes", "a-book.epub")]

    assert len(corpus.replace_calls) == 1
    call = corpus.replace_calls[0]
    assert call["source_id"] == source.id
    assert call["title"] == "The Test Book"
    assert call["authors"] == ("Ada", "Alan")
    assert call["language"] == "en"
    assert call["schema_version"] == 1

    records = call["sections"]
    assert len(records) == 2

    # Section with blocks: markdown is the join of the converter's per-block output;
    # a single chunk carries that text plus the section's citation anchors.
    first = records[0]
    assert first.section is book.sections[0]
    assert first.markdown == "md:H0\n\nmd:P0"
    assert len(first.chunks) == 1
    chunk = first.chunks[0]
    assert chunk.index == 0
    assert chunk.text == "md:H0\n\nmd:P0"
    assert chunk.section_path == ("One",)
    assert chunk.anchor == "one.xhtml"
    assert chunk.page_span is None

    # Zero-block section is still persisted: empty markdown, no chunks (CORP-08 edge).
    second = records[1]
    assert second.section is book.sections[1]
    assert second.markdown == ""
    assert second.chunks == ()


def test_build_corpus_appends_counts_event_with_exact_message() -> None:
    source = _source()
    job = _job(source.id)
    storage = FakeStorage()
    storage.objects[source.object_key] = b"epub-bytes"
    events = FakeIngestionEventRepository()

    _build(
        storage=storage,
        parser=FakeEpubParser(book=_book()),
        corpus=FakeCorpusRepository(),
        events=events,
    )(source=source, job=job)

    appended = events.list_for_job(job.id)
    assert len(appended) == 1
    event = appended[0]
    assert event.type == "corpus_built"
    assert event.message == "sections=2 blocks=2 chunks=1"
    assert event.job_id == job.id


def test_build_corpus_chunks_derive_from_block_markdown() -> None:
    # A cap of 5 (== len("md:H0")) forces each block text into its own chunk, so a
    # 2-block section yields 2 chunks — proving chunks come from the per-block
    # converter output, not the joined section markdown.
    source = _source()
    job = _job(source.id)
    corpus = FakeCorpusRepository()
    events = FakeIngestionEventRepository()
    storage = FakeStorage()
    storage.objects[source.object_key] = b"epub-bytes"

    _build(
        storage=storage,
        parser=FakeEpubParser(book=_book()),
        corpus=corpus,
        events=events,
        chunk_max_chars=5,
    )(source=source, job=job)

    first = corpus.replace_calls[0]["sections"][0]
    assert [c.text for c in first.chunks] == ["md:H0", "md:P0"]
    assert [c.index for c in first.chunks] == [0, 1]
    assert events.list_for_job(job.id)[0].message == "sections=2 blocks=2 chunks=2"


def test_build_corpus_propagates_storage_error_without_persisting() -> None:
    source = _source()
    job = _job(source.id)
    corpus = FakeCorpusRepository()
    events = FakeIngestionEventRepository()

    build = _build(
        storage=FailingStorage(),
        parser=FakeEpubParser(book=_book()),
        corpus=corpus,
        events=events,
    )
    with pytest.raises(RuntimeError):
        build(source=source, job=job)

    assert corpus.replace_calls == []
    assert events.list_for_job(job.id) == []


def test_build_corpus_propagates_parser_error_without_persisting() -> None:
    source = _source()
    job = _job(source.id)
    corpus = FakeCorpusRepository()
    events = FakeIngestionEventRepository()
    storage = FakeStorage()
    storage.objects[source.object_key] = b"epub-bytes"

    build = _build(
        storage=storage,
        parser=FakeEpubParser(error=InvalidEpubError("bad epub")),
        corpus=corpus,
        events=events,
    )
    with pytest.raises(InvalidEpubError):
        build(source=source, job=job)

    assert corpus.replace_calls == []
    assert events.list_for_job(job.id) == []
