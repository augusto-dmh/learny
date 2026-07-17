"""T8/T10 gate — corpus application services (unit, in-memory fakes).

Drives ``BuildCorpus`` over fake ports (storage/parser/markup/corpus/events) so
the orchestration is asserted in isolation (CORP-01/04/05/08/10, ING-01/07/12):
the stored bytes flow through to the parser, the parsed structure runs through the
format-agnostic normalization pass (trivial sections merge into a survivor and
keep resolving as aliases, generic titles are replaced), each section's Markdown is
the ``\\n\\n``-join of the converter's per-block output, chunks are packed from
those block texts with their page spans rolled up, the whole aggregate is persisted
with ``schema_version=1``, the ``corpus_normalized`` and ``corpus_built`` events
carry the exact counts, and a storage or parser fault propagates unwrapped with
nothing persisted (CORP-08).

Also drives ``ReadSourceStructure`` (CORP-11): the owner reads the persisted
structure value; a missing source and a non-owner both collapse to
``SourceNotFound`` (no existence disclosure); an owned source with no corpus
raises ``CorpusNotFound`` (A-7 → 404).
"""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import count
from uuid import UUID, uuid4

import pytest

from app.application.corpus import BuildCorpus, ReadSourceStructure
from app.application.errors import CorpusNotFound, InvalidDocumentError, SourceNotFound
from app.application.identity import AuthorizeOwnership
from app.domain.entities import (
    CorpusSectionRecord,
    IngestionJob,
    ParsedBlock,
    ParsedBook,
    ParsedSection,
    Source,
    User,
)
from tests.fakes import (
    FailingStorage,
    FakeClock,
    FakeCorpusRepository,
    FakeEpubParser,
    FakeIngestionEventRepository,
    FakeMarkupConverter,
    FakeSourceRepository,
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
    """A clean two-section book normalization passes through unchanged.

    Both sections have a real (non-generic) title and their own heading, so no merge
    or title replacement fires — the persisted aggregate matches the parsed one.
    """
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
                title="Two",
                depth=0,
                section_path=("Two",),
                anchor="two.xhtml",
                blocks=(
                    ParsedBlock(2, "heading", "H1"),
                    ParsedBlock(3, "paragraph", "P1"),
                ),
            ),
        ),
    )


def _build(*, storage, parser, corpus, events, chunk_max_chars: int = 2000) -> BuildCorpus:  # noqa: ANN001 — port doubles
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

    _build(storage=storage, parser=parser, corpus=corpus, events=events)(source=source, job=job)

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

    # Clean book: normalization rebuilds each section (position/path) but leaves its
    # values unchanged, so the persisted section equals the parsed one by value.
    first = records[0]
    assert first.section == book.sections[0]
    assert first.section.anchor_aliases == ()
    assert first.markdown == "md:H0\n\nmd:P0"
    assert len(first.chunks) == 1
    chunk = first.chunks[0]
    assert chunk.index == 0
    assert chunk.text == "md:H0\n\nmd:P0"
    assert chunk.section_path == ("One",)
    assert chunk.anchor == "one.xhtml"
    assert chunk.page_span is None

    second = records[1]
    assert second.section == book.sections[1]
    assert second.markdown == "md:H1\n\nmd:P1"
    assert [c.text for c in second.chunks] == ["md:H1\n\nmd:P1"]


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
    # A clean book normalizes to a no-op, then the build counts event follows.
    assert [event.type for event in appended] == ["corpus_normalized", "corpus_built"]
    normalized, built = appended
    assert normalized.message == (
        "titles_replaced=0 sections_merged=0 depths_adjusted=0 noise_blocks_stripped=0"
    )
    assert built.message == "sections=2 blocks=4 chunks=2"
    assert built.job_id == job.id


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
    built = next(e for e in events.list_for_job(job.id) if e.type == "corpus_built")
    assert built.message == "sections=2 blocks=4 chunks=4"


def _noisy_book() -> ParsedBook:
    """A noisy book exercising the wired normalization pass end to end.

    Gutenberg-framed front matter is stripped; a generic filename-stem title
    (``part0034``) is replaced by its heading; an image-only plate merges into the
    survivor and keeps resolving as an alias; a block page span rolls into the chunk.
    """
    return ParsedBook(
        title="Noisy",
        authors=(),
        language="en",
        sections=(
            ParsedSection(
                position=0,
                title="front",
                depth=0,
                section_path=("front",),
                anchor="front.xhtml",
                blocks=(
                    ParsedBlock(0, "paragraph", "License boilerplate."),
                    ParsedBlock(
                        1,
                        "paragraph",
                        "*** START OF THE PROJECT GUTENBERG EBOOK NOISY ***",
                    ),
                ),
            ),
            ParsedSection(
                position=1,
                title="part0034",
                depth=0,
                section_path=("part0034",),
                anchor="part0034.xhtml",
                blocks=(
                    ParsedBlock(2, "heading", "Real Chapter"),
                    ParsedBlock(3, "paragraph", "Body text.", page_span=(5, 6)),
                    ParsedBlock(
                        4,
                        "paragraph",
                        "*** END OF THE PROJECT GUTENBERG EBOOK NOISY ***",
                    ),
                ),
            ),
            ParsedSection(
                position=2,
                title="Plate",
                depth=0,
                section_path=("Plate",),
                anchor="plate.xhtml",
                blocks=(ParsedBlock(5, "img", "<img/>"),),
            ),
        ),
    )


def test_build_corpus_runs_structure_normalization() -> None:
    # ING-01/02/05/07/12: BuildCorpus normalizes the parsed structure before building
    # records — boilerplate is stripped, the generic title is replaced, the trivial
    # plate + stripped front survive as aliases, the surviving block's page span rolls
    # into the chunk, and a corpus_normalized event carries the exact counts.
    source = _source()
    job = _job(source.id)
    corpus = FakeCorpusRepository()
    events = FakeIngestionEventRepository()
    storage = FakeStorage()
    storage.objects[source.object_key] = b"epub-bytes"

    _build(
        storage=storage,
        parser=FakeEpubParser(book=_noisy_book()),
        corpus=corpus,
        events=events,
    )(source=source, job=job)

    records = corpus.replace_calls[0]["sections"]
    assert len(records) == 1
    record = records[0]
    # ING-02: the filename-stem title is replaced by the section's heading text.
    assert record.section.title == "Real Chapter"
    assert record.section.section_path == ("Real Chapter",)
    assert record.section.anchor == "part0034.xhtml"
    # ING-05: the stripped-empty front and the image-only plate merge in as aliases.
    assert record.section.anchor_aliases == ("front.xhtml", "plate.xhtml")
    # ING-06: no Gutenberg boilerplate reaches the persisted corpus.
    assert "boilerplate" not in record.markdown.lower()
    assert "gutenberg" not in record.markdown.lower()
    # ING-12: the surviving block's page span rolls up into its chunk.
    assert record.chunks[0].page_span == (5, 6)
    # ING-07: the normalization counts event carries exactly what the pass changed.
    normalized = next(
        e for e in events.list_for_job(job.id) if e.type == "corpus_normalized"
    )
    assert normalized.message == (
        "titles_replaced=1 sections_merged=2 depths_adjusted=0 noise_blocks_stripped=4"
    )


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
        parser=FakeEpubParser(error=InvalidDocumentError("bad epub")),
        corpus=corpus,
        events=events,
    )
    with pytest.raises(InvalidDocumentError):
        build(source=source, job=job)

    assert corpus.replace_calls == []
    assert events.list_for_job(job.id) == []


# --- ReadSourceStructure (CORP-11) ---------------------------------------------


def _user() -> User:
    return User(id=uuid4(), email="owner@example.com", created_at=_NOW)


def _owned_source(user: User) -> Source:
    return Source(
        id=uuid4(),
        user_id=user.id,
        title="A Book",
        filename="a-book.epub",
        content_type="application/epub+zip",
        byte_size=10,
        checksum="d" * 64,
        object_key="sources/a-book.epub",
        status="ready",
        created_at=_NOW,
        updated_at=_NOW,
    )


def _seed_corpus(corpus: FakeCorpusRepository, source_id: UUID) -> None:
    """Persist a one-section corpus for ``source_id`` via the fake's replace."""
    corpus.replace(
        source_id,
        title="The Test Book",
        authors=("Ada", "Alan"),
        language="en",
        schema_version=1,
        sections=(
            CorpusSectionRecord(
                section=ParsedSection(
                    position=0,
                    title="One",
                    depth=0,
                    section_path=("One",),
                    anchor="one.xhtml",
                    blocks=(),
                ),
                markdown="",
                chunks=(),
            ),
        ),
    )


def _read_structure(
    sources: FakeSourceRepository, corpus: FakeCorpusRepository
) -> ReadSourceStructure:
    return ReadSourceStructure(
        sources=sources,
        corpus=corpus,
        authorize=AuthorizeOwnership(),
    )


def test_read_structure_returns_owner_structure_value() -> None:
    user = _user()
    source = _owned_source(user)
    sources = FakeSourceRepository()
    sources.add(source)
    corpus = FakeCorpusRepository()
    _seed_corpus(corpus, source.id)

    structure = _read_structure(sources, corpus)(user=user, source_id=source.id)

    # The persisted structure value is returned verbatim (== the repo's read model).
    assert structure == corpus.get_structure(source.id)
    assert structure.title == "The Test Book"
    assert structure.authors == ("Ada", "Alan")
    assert structure.language == "en"
    assert [
        (s.position, s.title, s.depth, s.section_path, s.anchor) for s in structure.sections
    ] == [(0, "One", 0, ("One",), "one.xhtml")]


def test_read_structure_missing_source_raises_source_not_found() -> None:
    user = _user()
    sources = FakeSourceRepository()
    corpus = FakeCorpusRepository()

    with pytest.raises(SourceNotFound):
        _read_structure(sources, corpus)(user=user, source_id=uuid4())


def test_read_structure_non_owner_collapses_to_source_not_found() -> None:
    owner = _user()
    source = _owned_source(owner)
    sources = FakeSourceRepository()
    sources.add(source)
    corpus = FakeCorpusRepository()
    _seed_corpus(corpus, source.id)

    intruder = User(id=uuid4(), email="intruder@example.com", created_at=_NOW)
    # Non-owner collapses to the same not-found as a missing source (no disclosure),
    # even though the corpus exists.
    with pytest.raises(SourceNotFound):
        _read_structure(sources, corpus)(user=intruder, source_id=source.id)


def test_read_structure_owned_source_without_corpus_raises_corpus_not_found() -> None:
    user = _user()
    source = _owned_source(user)
    sources = FakeSourceRepository()
    sources.add(source)
    corpus = FakeCorpusRepository()  # no corpus persisted for this source

    with pytest.raises(CorpusNotFound):
        _read_structure(sources, corpus)(user=user, source_id=source.id)
