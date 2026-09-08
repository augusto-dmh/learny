"""T6 gate (unit) — EmbedCorpus application service (RET-09).

Drives ``EmbedCorpus`` over fake ports (embedding/embedding-index/events) so the
orchestration is asserted in isolation: every chunk of the source is embedded and
paired with its chunk id in reading order, the embedding provider is called in
``batch_size`` batches, a zero-chunk source is a no-op write, and one
``embeddings_built`` event carries the exact chunk count. Assertions target the
persisted ``(chunk_id, vector)`` pairs (via the fake index repo), not call counts.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from itertools import count
from uuid import UUID, uuid4

import pytest

from app.application.errors import SourceNotFound
from app.application.identity import AuthorizeOwnership
from app.application.retrieval import EmbedCorpus, RetrieveEvidence
from app.domain.entities import ChunkToEmbed, Evidence, IngestionJob, Source, User
from tests.fakes import (
    FakeClock,
    FakeEmbeddingIndexRepository,
    FakeEmbeddingPort,
    FakeIngestionEventRepository,
    FakeReadingPositionRepository,
    FakeRetrievalPort,
    FakeSourceRepository,
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


def _chunks(n: int) -> list[ChunkToEmbed]:
    return [ChunkToEmbed(id=uuid4(), text=f"chunk-{i}") for i in range(n)]


def _embed(
    *,
    index: FakeEmbeddingIndexRepository,
    embeddings: FakeEmbeddingPort,
    events: FakeIngestionEventRepository,
    batch_size: int,
) -> EmbedCorpus:
    ids = count(1)
    return EmbedCorpus(
        embeddings=embeddings,
        index=index,
        events=events,
        clock=FakeClock(_NOW),
        ids=lambda: UUID(int=next(ids)),
        batch_size=batch_size,
    )


def test_embed_corpus_embeds_all_chunks_in_order() -> None:
    source = _source()
    job = _job(source.id)
    chunks = _chunks(3)
    index = FakeEmbeddingIndexRepository({source.id: chunks})
    embeddings = FakeEmbeddingPort()
    events = FakeIngestionEventRepository()

    _embed(index=index, embeddings=embeddings, events=events, batch_size=128)(
        source=source, job=job
    )

    # One set_embeddings write carrying every chunk id paired with its vector, in
    # reading order (vector value == the chunk's overall position, per the fake).
    assert len(index.set_calls) == 1
    assert index.set_calls[0] == [
        (chunks[0].id, [0.0]),
        (chunks[1].id, [1.0]),
        (chunks[2].id, [2.0]),
    ]


def test_embed_corpus_respects_batch_boundaries() -> None:
    source = _source()
    job = _job(source.id)
    chunks = _chunks(5)
    index = FakeEmbeddingIndexRepository({source.id: chunks})
    embeddings = FakeEmbeddingPort()
    events = FakeIngestionEventRepository()

    _embed(index=index, embeddings=embeddings, events=events, batch_size=2)(source=source, job=job)

    # 5 chunks embedded in batches of 2 → [2, 2, 1], texts kept in reading order.
    assert [len(batch) for batch in embeddings.document_batches] == [2, 2, 1]
    assert [text for batch in embeddings.document_batches for text in batch] == [
        c.text for c in chunks
    ]
    # Every chunk id persisted with the position-ordered vector, across batches.
    assert index.set_calls[0] == [(chunks[i].id, [float(i)]) for i in range(5)]


def test_embed_corpus_zero_chunks_is_noop_with_event_count_zero() -> None:
    source = _source()
    job = _job(source.id)
    index = FakeEmbeddingIndexRepository({source.id: []})
    embeddings = FakeEmbeddingPort()
    events = FakeIngestionEventRepository()

    _embed(index=index, embeddings=embeddings, events=events, batch_size=128)(
        source=source, job=job
    )

    # No embedding call and no write for a source with no chunks (no-op write).
    assert embeddings.document_batches == []
    assert index.set_calls == []
    # Still exactly one embeddings_built event, carrying count 0.
    appended = events.list_for_job(job.id)
    assert len(appended) == 1
    assert appended[0].type == "embeddings_built"
    assert appended[0].message == "chunks=0"


def test_embed_corpus_appends_embeddings_built_event_with_count() -> None:
    source = _source()
    job = _job(source.id)
    index = FakeEmbeddingIndexRepository({source.id: _chunks(3)})
    events = FakeIngestionEventRepository()

    _embed(index=index, embeddings=FakeEmbeddingPort(), events=events, batch_size=128)(
        source=source, job=job
    )

    appended = events.list_for_job(job.id)
    assert len(appended) == 1
    event = appended[0]
    assert event.type == "embeddings_built"
    assert event.message == "chunks=3"
    assert event.job_id == job.id


# --- T9 gate (unit) — RetrieveEvidence orchestration (RET-13/20) -----------
#
# Drives ``RetrieveEvidence`` over fakes: the source/retrieval/embedding ports
# and the real (pure) ``AuthorizeOwnership`` primitive. Asserts ownership-as-404
# (missing + non-owner → ``SourceNotFound``), and that a normal call forwards the
# embedded query vector and the settings-sourced limits/k/ef by value and returns
# exactly what the retrieval port returns (including an empty passthrough).

# Distinct sentinel tuning values so a forwarded-args assertion pins each knob to
# its own slot (a swapped/hard-coded knob would fail).
_SEMANTIC_LIMIT = 7
_LEXICAL_LIMIT = 9
_RRF_K = 11
_EF_SEARCH = 13
_DEFAULT_TOP_K = 5


class _StubEmbeddings:
    """``EmbeddingPort`` stub: ``embed_query`` returns a text-derived vector.

    The returned vector is a deterministic function of the exact query text, so a
    test asserting the forwarded ``query_vec`` proves the service embedded *this*
    query and passed the result through. ``embed_documents`` must never be called
    on the retrieval path.
    """

    def __init__(self) -> None:
        self.queries: list[str] = []

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return [float(len(text)), 42.0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise AssertionError("RetrieveEvidence must not embed documents")


def _owned_source(user_id: UUID) -> Source:
    return Source(
        id=uuid4(),
        user_id=user_id,
        title="A Book",
        filename="a-book.epub",
        content_type="application/epub+zip",
        byte_size=10,
        checksum="d" * 64,
        object_key=f"sources/{user_id}/a-book.epub",
        status="ready",
        created_at=_NOW,
        updated_at=_NOW,
    )


def _user() -> User:
    return User(id=uuid4(), email="owner@example.com", created_at=_NOW)


def _retrieve(
    *,
    sources: FakeSourceRepository,
    retrieval: FakeRetrievalPort,
    embeddings: _StubEmbeddings,
    positions: FakeReadingPositionRepository | None = None,
) -> RetrieveEvidence:
    return RetrieveEvidence(
        sources=sources,
        retrieval=retrieval,
        embeddings=embeddings,
        positions=positions or FakeReadingPositionRepository(),
        authorize=AuthorizeOwnership(),
        semantic_limit=_SEMANTIC_LIMIT,
        lexical_limit=_LEXICAL_LIMIT,
        rrf_k=_RRF_K,
        ef_search=_EF_SEARCH,
        default_top_k=_DEFAULT_TOP_K,
    )


def _evidence(source_id: UUID) -> Evidence:
    return Evidence(
        chunk_id=uuid4(),
        source_id=source_id,
        section_path=("Chapter 1",),
        anchor="ch1.xhtml#p",
        page_span=None,
        snippet="a matching passage",
        score=0.5,
    )


def test_retrieve_evidence_missing_source_raises_source_not_found() -> None:
    sources = FakeSourceRepository()
    retrieval = FakeRetrievalPort()
    service = _retrieve(sources=sources, retrieval=retrieval, embeddings=_StubEmbeddings())

    with pytest.raises(SourceNotFound):
        service(user=_user(), source_id=uuid4(), query="anything")

    # Ownership fails closed before any retrieval or embedding work runs.
    assert retrieval.calls == []


def test_retrieve_evidence_non_owner_raises_source_not_found() -> None:
    owner = _user()
    other = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    retrieval = FakeRetrievalPort()
    service = _retrieve(sources=sources, retrieval=retrieval, embeddings=_StubEmbeddings())

    # A non-owner is collapsed to not-found (existence never disclosed), and no
    # retrieval runs.
    with pytest.raises(SourceNotFound):
        service(user=other, source_id=source.id, query="anything")
    assert retrieval.calls == []


def test_retrieve_evidence_returns_sample_for_non_owner() -> None:
    operator = _user()
    reader = _user()
    sources = FakeSourceRepository()
    sample = replace(_owned_source(operator.id), is_sample=True)
    sources.add(sample)
    expected = [_evidence(sample.id)]
    retrieval = FakeRetrievalPort(results=expected)
    service = _retrieve(sources=sources, retrieval=retrieval, embeddings=_StubEmbeddings())

    assert service(user=reader, source_id=sample.id, query="deception") == expected
    assert retrieval.calls[0]["source_id"] == sample.id


def test_retrieve_evidence_forwards_vector_and_settings_and_returns_results() -> None:
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    expected = [_evidence(source.id), _evidence(source.id)]
    retrieval = FakeRetrievalPort(results=expected)
    embeddings = _StubEmbeddings()
    service = _retrieve(sources=sources, retrieval=retrieval, embeddings=embeddings)

    query = "photosynthesis"
    result = service(user=owner, source_id=source.id, query=query, top_k=3)

    # Returns exactly what the port returned (same object, not a rebuilt list).
    assert result is expected
    # The query was embedded once, and that vector is what reached the port.
    assert embeddings.queries == [query]
    assert len(retrieval.calls) == 1
    call = retrieval.calls[0]
    assert call == {
        "source_id": source.id,
        "query_text": query,
        "query_vec": [float(len(query)), 42.0],
        "top_k": 3,
        "semantic_limit": _SEMANTIC_LIMIT,
        "lexical_limit": _LEXICAL_LIMIT,
        "rrf_k": _RRF_K,
        "ef_search": _EF_SEARCH,
        # Whole-source retrieval passes no anchor scope (the teaching turn path
        # supplies one; the Q&A path does not).
        "anchors": None,
    }


def test_retrieve_evidence_forwards_anchors_to_port() -> None:
    # AD-031: a caller-supplied anchor scope reaches the retrieval port verbatim,
    # so the target-subtree filter is applied by the SQL adapter (TEACH-09).
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    retrieval = FakeRetrievalPort(results=[])
    service = _retrieve(sources=sources, retrieval=retrieval, embeddings=_StubEmbeddings())

    anchors = ["ch1.xhtml", "ch1.xhtml#s1"]
    service(user=owner, source_id=source.id, query="anything", anchors=anchors)

    assert retrieval.calls[0]["anchors"] == anchors


def test_retrieve_evidence_passes_empty_through_and_defaults_top_k() -> None:
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    retrieval = FakeRetrievalPort(results=[])
    service = _retrieve(sources=sources, retrieval=retrieval, embeddings=_StubEmbeddings())

    # top_k omitted → falls back to the injected default; an empty port result is
    # returned unchanged (the Phase-7 "not found" hook, not an error).
    result = service(user=owner, source_id=source.id, query="unmatched")

    assert result == []


def test_retrieve_evidence_forwards_owner_and_include_notes_flag() -> None:
    # NL-04/NL-05: when the caller opts notes in, the flag AND the owner id reach
    # the port, so the note arms run scoped to this user's own notes.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    retrieval = FakeRetrievalPort(results=[])
    service = _retrieve(sources=sources, retrieval=retrieval, embeddings=_StubEmbeddings())

    service(user=owner, source_id=source.id, query="anything", include_notes=True)

    assert retrieval.note_scope_calls == [{"user_id": owner.id, "include_notes": True}]


def test_retrieve_evidence_defaults_notes_off_but_forwards_owner() -> None:
    # NL-04: the service defaults the note arms OFF (the web layer owns the Q&A
    # on-default); the owner id is forwarded regardless so scoping is always ready.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    retrieval = FakeRetrievalPort(results=[])
    service = _retrieve(sources=sources, retrieval=retrieval, embeddings=_StubEmbeddings())

    service(user=owner, source_id=source.id, query="anything")

    assert retrieval.note_scope_calls == [{"user_id": owner.id, "include_notes": False}]
    assert retrieval.calls[0]["top_k"] == _DEFAULT_TOP_K


# --- Reading-position bound (SPOILER-01/05/06/13) -------------------------------
#
# Drives the position resolution: with ``respect_reading_position=True`` the
# service reads the CALLING user's own position row for the source and passes its
# canonical anchor down as ``not_past_anchor``; a missing row passes ``None``
# (unfiltered, not empty evidence); with the flag off the position repository is
# never read at all. Assertions target the recorded position reads and the bound
# that reached the retrieval port, never call counts alone.


def test_retrieve_evidence_default_never_reads_the_position_repository() -> None:
    # SPOILER-13: with the flag off (the default) the service must not consult the
    # position repository at all — even when a saved position exists — and no bound
    # reaches the port. Proven with the recording fake, not just the absence of a
    # crash.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    positions = FakeReadingPositionRepository()
    positions.upsert(
        owner.id, source.id, anchor="geo.xhtml", percent=Decimal("40.00"), updated_at=_NOW
    )
    expected = [_evidence(source.id)]
    retrieval = FakeRetrievalPort(results=expected)
    service = _retrieve(
        sources=sources, retrieval=retrieval, embeddings=_StubEmbeddings(), positions=positions
    )

    result = service(user=owner, source_id=source.id, query="photosynthesis")

    assert result is expected
    assert positions.get_calls == []
    assert retrieval.not_past_calls == [None]


def test_retrieve_evidence_respects_position_by_forwarding_the_saved_anchor() -> None:
    # SPOILER-01 (propagation) / SPOILER-06: with the flag on, the bound passed to
    # the port is the canonical anchor of the calling user's own position row for
    # that source — read by (user_id, source_id) — and evidence at or before the
    # bound still flows through (a saved position never means empty evidence).
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    positions = FakeReadingPositionRepository()
    positions.upsert(
        owner.id, source.id, anchor="geo.xhtml", percent=Decimal("40.00"), updated_at=_NOW
    )
    reached = [
        _anchored_evidence(source.id, "bio.xhtml#p"),
        _anchored_evidence(source.id, "geo.xhtml#o"),
    ]
    retrieval = FakeRetrievalPort(
        results=reached, sections_by_source={source.id: ["bio.xhtml", "geo.xhtml"]}
    )
    service = _retrieve(
        sources=sources, retrieval=retrieval, embeddings=_StubEmbeddings(), positions=positions
    )

    result = service(
        user=owner, source_id=source.id, query="photosynthesis", respect_reading_position=True
    )

    assert result == reached
    assert positions.get_calls == [(owner.id, source.id)]
    assert retrieval.not_past_calls == ["geo.xhtml"]


def test_retrieve_evidence_without_a_saved_position_passes_no_bound_not_empty_evidence() -> None:
    # SPOILER-05: a missing position row means an unread book — the service passes
    # no bound (None) and the port's evidence flows through unchanged. A missing
    # row must degrade to unfiltered, never to empty evidence.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    expected = [_evidence(source.id), _evidence(source.id)]
    retrieval = FakeRetrievalPort(results=expected)
    service = _retrieve(
        sources=sources,
        retrieval=retrieval,
        embeddings=_StubEmbeddings(),
        positions=FakeReadingPositionRepository(),
    )

    result = service(
        user=owner, source_id=source.id, query="photosynthesis", respect_reading_position=True
    )

    assert result is expected
    assert retrieval.not_past_calls == [None]


def test_retrieve_evidence_never_reads_another_users_position_row() -> None:
    # SPOILER-06: the bound is derived only from the calling user's own row —
    # another user's position for the same source is never read and never bounds.
    owner = _user()
    other = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    positions = FakeReadingPositionRepository()
    positions.upsert(
        other.id, source.id, anchor="phys.xhtml", percent=Decimal("90.00"), updated_at=_NOW
    )
    retrieval = FakeRetrievalPort(results=[_evidence(source.id)])
    service = _retrieve(
        sources=sources, retrieval=retrieval, embeddings=_StubEmbeddings(), positions=positions
    )

    service(user=owner, source_id=source.id, query="photosynthesis", respect_reading_position=True)

    assert positions.get_calls == [(owner.id, source.id)]
    assert retrieval.not_past_calls == [None]


def test_retrieve_evidence_ownership_precedes_any_position_read() -> None:
    # The position repository is only ever queried for a source the user may read:
    # a non-owner collapses to SourceNotFound (existence never disclosed) before
    # the position row is touched, and no retrieval runs.
    owner = _user()
    intruder = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    positions = FakeReadingPositionRepository()
    positions.upsert(
        owner.id, source.id, anchor="geo.xhtml", percent=Decimal("40.00"), updated_at=_NOW
    )
    retrieval = FakeRetrievalPort()
    service = _retrieve(
        sources=sources, retrieval=retrieval, embeddings=_StubEmbeddings(), positions=positions
    )

    with pytest.raises(SourceNotFound):
        service(
            user=intruder,
            source_id=source.id,
            query="photosynthesis",
            respect_reading_position=True,
        )

    assert positions.get_calls == []
    assert retrieval.calls == []


# --- FakeRetrievalPort mirrors the section-order bound (double correctness) -----
#
# The matrix requires the fakes to reproduce the SQL adapter's contract so
# upper-layer tests exercise the real semantics: section-order filtering with the
# bound section admissible, note evidence unbounded, and fail-closed on an
# unmatched anchor.


def _three_section_port(source_id: UUID, results: list[Evidence]) -> FakeRetrievalPort:
    return FakeRetrievalPort(
        results=results,
        sections_by_source={source_id: ["bio.xhtml", "geo.xhtml", "phys.xhtml"]},
    )


def _anchored_evidence(source_id: UUID, anchor: str, *, origin: str = "book") -> Evidence:
    return Evidence(
        chunk_id=uuid4(),
        source_id=source_id,
        section_path=("Chapter",),
        anchor=anchor,
        page_span=None,
        snippet="a matching passage",
        score=0.5,
        origin=origin,  # type: ignore[arg-type]
    )


def _port_search(
    port: FakeRetrievalPort, source_id: UUID, *, not_past_anchor: str | None = None
) -> list[Evidence]:
    return port.search(
        source_id=source_id,
        query_text="photosynthesis",
        query_vec=[1.0],
        top_k=5,
        semantic_limit=7,
        lexical_limit=9,
        rrf_k=11,
        ef_search=13,
        not_past_anchor=not_past_anchor,
    )


def test_fake_retrieval_port_bound_keeps_sections_at_or_before_the_bound() -> None:
    # SPOILER-02 (mirrored by the double): the bound section and every earlier
    # section stay admissible; later sections are inadmissible; a None bound
    # returns everything.
    source_id = uuid4()
    port = _three_section_port(
        source_id,
        [
            _anchored_evidence(source_id, "bio.xhtml#p"),
            _anchored_evidence(source_id, "geo.xhtml#o"),
            _anchored_evidence(source_id, "phys.xhtml#q"),
        ],
    )

    bounded = _port_search(port, source_id, not_past_anchor="geo.xhtml")
    unbounded = _port_search(port, source_id, not_past_anchor=None)

    assert {e.anchor for e in bounded} == {"bio.xhtml#p", "geo.xhtml#o"}
    assert {e.anchor for e in unbounded} == {"bio.xhtml#p", "geo.xhtml#o", "phys.xhtml#q"}
    assert port.not_past_calls == ["geo.xhtml", None]


def test_fake_retrieval_port_unmatched_bound_anchor_fails_closed() -> None:
    # SPOILER-14 (mirrored by the double): a bound anchor matching no section of
    # the source yields zero book evidence — never an unfiltered fallback.
    source_id = uuid4()
    port = _three_section_port(source_id, [_anchored_evidence(source_id, "bio.xhtml#p")])

    assert _port_search(port, source_id, not_past_anchor="ghost.xhtml") == []


def test_fake_retrieval_port_bound_never_restricts_note_evidence() -> None:
    # SPOILER-11 (mirrored by the double): the user's own notes survive a bound
    # that eliminates the book evidence.
    source_id = uuid4()
    note = _anchored_evidence(source_id, "note:abc", origin="note")
    port = FakeRetrievalPort(
        results=[_anchored_evidence(source_id, "phys.xhtml#q"), note],
        sections_by_source={source_id: ["bio.xhtml"]},
    )

    bounded = _port_search(port, source_id, not_past_anchor="bio.xhtml")

    assert bounded == [note]
