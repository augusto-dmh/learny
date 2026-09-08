"""T8 gate (integration) — hybrid RRF retrieval repository (RET-13..17).

Seeds a canonical corpus via ``SqlAlchemyCorpusRepository.replace``, embeds its
chunks with the deterministic adapter (so the semantic arm has vectors), and
drives ``SqlAlchemyRetrievalRepository.search`` against the live test DB. The same
deterministic adapter embeds the query text for ``query_vec`` so ordering is
reproducible. Assertions target spec outcomes:

- recall: a query whose terms appear in a known section returns that chunk's
  ``chunk_id``/``anchor`` (RET-13).
- fusion: a chunk matching both arms scores ``1/(k+rank_sem) + 1/(k+rank_lex)``
  and outranks a single-arm hit (RET-14).
- degrade: with embeddings left NULL, a lexical query still returns matches and
  does not error (RET-15).
- empty: a no-match query returns ``[]`` (RET-16).
- scoping: a query scoped to source A returns no source-B chunk (RET-17).
- anchor scope: an anchor filter restricts both arms to the target subtree and
  never bypasses the source scope (TEACH-09, AD-031).
- position bound: ``not_past_anchor`` restricts book evidence to sections at or
  before the bound anchor's section in document order — the bound section itself
  stays admissible, later sections never; scores/order of admissible rows are
  the shipped RRF values; PDF sources take the same section-order predicate;
  notes are never bounded; an unmatched bound anchor yields zero book evidence
  plus a warning (SPOILER-01..04, 07, 11, 12, 14). Edge cases: a sectionless
  source yields no evidence with or without a bound; a 0.00-percent position
  still bounds at its anchor's section — the anchor, not the percent, defines
  the bound.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection

from app.domain.entities import (
    CorpusSectionRecord,
    ParsedSection,
    SectionChunk,
    Source,
    User,
)
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemyEmbeddingIndexRepository,
    SqlAlchemyReadingPositionRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyUserRepository,
)
from app.infrastructure.db.retrieval import SqlAlchemyRetrievalRepository
from app.infrastructure.embeddings import DeterministicEmbeddingAdapter
from tests.conftest import requires_db

pytestmark = requires_db

# RRF smoothing constant and per-arm limits used by every test here; small,
# fixed values so the fusion arithmetic is exactly computable.
_K = 60
_SEMANTIC_LIMIT = 50
_LEXICAL_LIMIT = 50
_EF_SEARCH = 100
_TOP_K = 10


def _persisted_source(db_conn: Connection, email: str) -> Source:
    now = datetime.now(UTC)
    user = User(id=uuid4(), email=email, created_at=now)
    SqlAlchemyUserRepository(db_conn).add(user)
    source = Source(
        id=uuid4(),
        user_id=user.id,
        title="A Book",
        filename="a-book.epub",
        content_type="application/epub+zip",
        byte_size=1024,
        checksum="d" * 64,
        object_key=f"sources/{user.id}/{uuid4()}.epub",
        status="ready",
        created_at=now,
        updated_at=now,
    )
    return SqlAlchemySourceRepository(db_conn).add(source)


def _chunk(
    index: int,
    text: str,
    *,
    title: str,
    anchor: str,
    page_span: tuple[int, int] | None = None,
) -> SectionChunk:
    return SectionChunk(
        index=index,
        text=text,
        section_path=(title,),
        anchor=anchor,
        page_span=page_span,
    )


def _persisted_pdf_source(db_conn: Connection, email: str) -> Source:
    """A PDF-flavored source (SPOILER-03 exercises the bound on paged formats)."""
    now = datetime.now(UTC)
    user = User(id=uuid4(), email=email, created_at=now)
    SqlAlchemyUserRepository(db_conn).add(user)
    source = Source(
        id=uuid4(),
        user_id=user.id,
        title="A PDF",
        filename="a-book.pdf",
        content_type="application/pdf",
        byte_size=1024,
        checksum="e" * 64,
        object_key=f"sources/{user.id}/{uuid4()}.pdf",
        status="ready",
        created_at=now,
        updated_at=now,
    )
    return SqlAlchemySourceRepository(db_conn).add(source)


def _section(
    position: int, title: str, anchor: str, chunks: tuple[SectionChunk, ...]
) -> CorpusSectionRecord:
    return CorpusSectionRecord(
        section=ParsedSection(
            position=position,
            title=title,
            depth=0,
            section_path=(title,),
            anchor=anchor,
            blocks=(),
        ),
        markdown="",
        chunks=chunks,
    )


def _seed_corpus(
    db_conn: Connection, source_id: UUID, sections: tuple[CorpusSectionRecord, ...]
) -> None:
    SqlAlchemyCorpusRepository(db_conn).replace(
        source_id,
        title="A Book",
        authors=("Author",),
        language="en",
        schema_version=1,
        sections=sections,
    )


def _embed_all(db_conn: Connection, source_id: UUID) -> None:
    """Embed every chunk of the source with the deterministic adapter."""
    index = SqlAlchemyEmbeddingIndexRepository(db_conn)
    adapter = DeterministicEmbeddingAdapter()
    chunks = index.chunks_for_source(source_id)
    vectors = adapter.embed_documents([c.text for c in chunks])
    index.set_embeddings(
        list(zip((c.id for c in chunks), vectors, strict=True)), model=adapter.model
    )


def _chunk_id_by_text(db_conn: Connection, source_id: UUID, text: str) -> UUID:
    index = SqlAlchemyEmbeddingIndexRepository(db_conn)
    for chunk in index.chunks_for_source(source_id):
        if chunk.text == text:
            return chunk.id
    raise AssertionError(f"no chunk with text {text!r}")


def _search(
    db_conn: Connection,
    source_id: UUID,
    query: str,
    *,
    top_k: int = _TOP_K,
    anchors: list[str] | None = None,
    not_past_anchor: str | None = None,
):
    query_vec = DeterministicEmbeddingAdapter().embed_query(query)
    return SqlAlchemyRetrievalRepository(db_conn).search(
        source_id=source_id,
        query_text=query,
        query_vec=query_vec,
        top_k=top_k,
        semantic_limit=_SEMANTIC_LIMIT,
        lexical_limit=_LEXICAL_LIMIT,
        rrf_k=_K,
        ef_search=_EF_SEARCH,
        anchors=anchors,
        not_past_anchor=not_past_anchor,
    )


# A three-chunk corpus with lexically disjoint topics, so query terms select a
# single known chunk on the lexical arm.
_PHOTO = "photosynthesis converts sunlight into chemical energy in green plants"
_OCEAN = "ocean currents redistribute heat across the planet over time"
_QUANTUM = "quantum entanglement links distant particles instantly"
# A second passage that also matches the photosynthesis query, planted in another
# section/source to prove the anchor scope (and source scope) excludes it.
_PHOTO2 = "photosynthesis in leaves turns sunlight and water into energy and sugar"


def _seed_three_topic_corpus(db_conn: Connection, source_id: UUID) -> None:
    _seed_corpus(
        db_conn,
        source_id,
        (
            _section(
                0,
                "Biology",
                "bio.xhtml",
                (_chunk(0, _PHOTO, title="Biology", anchor="bio.xhtml#p"),),
            ),
            _section(
                1,
                "Geography",
                "geo.xhtml",
                (_chunk(0, _OCEAN, title="Geography", anchor="geo.xhtml#o"),),
            ),
            _section(
                2,
                "Physics",
                "phys.xhtml",
                (_chunk(0, _QUANTUM, title="Physics", anchor="phys.xhtml#q"),),
            ),
        ),
    )


def test_search_returns_known_chunk_for_matching_query(db_conn: Connection) -> None:
    # RET-13: a query whose terms appear in a known section returns that chunk's
    # chunk_id and anchor, with citation anchors projected.
    source = _persisted_source(db_conn, "recall@example.com")
    _seed_three_topic_corpus(db_conn, source.id)
    _embed_all(db_conn, source.id)
    target_id = _chunk_id_by_text(db_conn, source.id, _PHOTO)

    results = _search(db_conn, source.id, "photosynthesis sunlight energy")

    hit = next((e for e in results if e.chunk_id == target_id), None)
    assert hit is not None
    assert hit.anchor == "bio.xhtml#p"
    assert hit.source_id == source.id
    assert hit.section_path == ("Biology",)
    assert hit.page_span is None
    assert hit.snippet == _PHOTO


def test_both_arm_hit_scores_fused_sum_and_outranks_single_arm(db_conn: Connection) -> None:
    # RET-14: a chunk matching BOTH arms scores 1/(k+rank_sem) + 1/(k+rank_lex).
    # The quantum chunk uniquely contains every query term, so it is the sole
    # lexical match (rank 1) and, sharing the most tokens, the nearest semantic
    # neighbour (rank 1) → score == 2/(k+1); other chunks match only the semantic
    # arm and score strictly lower.
    source = _persisted_source(db_conn, "fusion@example.com")
    _seed_three_topic_corpus(db_conn, source.id)
    _embed_all(db_conn, source.id)
    target_id = _chunk_id_by_text(db_conn, source.id, _QUANTUM)

    results = _search(db_conn, source.id, "quantum entanglement particles")

    assert results, "expected at least the both-arm hit"
    top = results[0]
    assert top.chunk_id == target_id
    # 2/(k+1) is only reachable as 1/(k+1)+1/(k+1): a single arm maxes at 1/(k+1),
    # so this exact value proves both arms contributed at rank 1 (fused, not one arm).
    expected = 1.0 / (_K + 1) + 1.0 / (_K + 1)
    assert top.score == pytest.approx(expected)
    # Every other returned chunk matched only the semantic arm → strictly lower.
    for other in results[1:]:
        assert other.score < top.score


def test_lexical_only_when_embeddings_are_null(db_conn: Connection) -> None:
    # RET-15: with embeddings left NULL (no embed step), the semantic arm returns
    # nothing and the lexical arm alone drives results — no error.
    source = _persisted_source(db_conn, "degrade@example.com")
    _seed_three_topic_corpus(db_conn, source.id)
    target_id = _chunk_id_by_text(db_conn, source.id, _OCEAN)

    results = _search(db_conn, source.id, "ocean currents heat")

    ids = {e.chunk_id for e in results}
    assert target_id in ids
    # Lexical-only: the score is a single RRF term (rank 1) for the sole match.
    hit = next(e for e in results if e.chunk_id == target_id)
    assert hit.score == pytest.approx(1.0 / (_K + 1))


def test_no_match_query_returns_empty(db_conn: Connection) -> None:
    # RET-16: a query matching no chunk on either arm returns an empty list. With
    # NULL embeddings the semantic arm is empty, so a non-lexical-matching query
    # yields nothing rather than an error.
    source = _persisted_source(db_conn, "empty@example.com")
    _seed_three_topic_corpus(db_conn, source.id)

    results = _search(db_conn, source.id, "zzzqqq nonsensical unmatchable token")

    assert results == []


def test_search_is_source_scoped(db_conn: Connection) -> None:
    # RET-17: a query scoped to source A returns no chunk belonging to source B,
    # even when B holds a chunk that matches the query terms.
    source_a = _persisted_source(db_conn, "scope-a@example.com")
    source_b = _persisted_source(db_conn, "scope-b@example.com")
    _seed_three_topic_corpus(db_conn, source_a.id)
    _seed_corpus(
        db_conn,
        source_b.id,
        (
            _section(
                0,
                "Biology",
                "bio.xhtml",
                (_chunk(0, _PHOTO, title="Biology", anchor="bio.xhtml#b"),),
            ),
        ),
    )
    _embed_all(db_conn, source_a.id)
    _embed_all(db_conn, source_b.id)
    b_ids = {
        c.id for c in SqlAlchemyEmbeddingIndexRepository(db_conn).chunks_for_source(source_b.id)
    }

    results = _search(db_conn, source_a.id, "photosynthesis sunlight energy")

    assert results, "expected source-A matches"
    result_ids = {e.chunk_id for e in results}
    assert result_ids.isdisjoint(b_ids)
    assert all(e.source_id == source_a.id for e in results)


def test_anchor_scope_filters_both_arms_to_subtree(db_conn: Connection) -> None:
    # TEACH-09 (AD-031): with an anchor scope, retrieval returns only chunks whose
    # section anchor is in the set. Both sections' chunks match the query on both
    # arms (embeddings populated + lexical match), so the out-of-scope chunk being
    # excluded proves the filter constrains the shared scoped CTE, not one arm.
    source = _persisted_source(db_conn, "anchor-scope@example.com")
    _seed_corpus(
        db_conn,
        source.id,
        (
            _section(
                0,
                "Chapter One",
                "ch1.xhtml",
                (_chunk(0, _PHOTO, title="Chapter One", anchor="ch1.xhtml"),),
            ),
            _section(
                1,
                "Chapter Two",
                "ch2.xhtml",
                (_chunk(0, _PHOTO2, title="Chapter Two", anchor="ch2.xhtml"),),
            ),
        ),
    )
    _embed_all(db_conn, source.id)

    # Unfiltered: the query matches chunks in BOTH sections (baseline).
    unscoped = _search(db_conn, source.id, "photosynthesis sunlight energy")
    assert {"ch1.xhtml", "ch2.xhtml"} <= {e.anchor for e in unscoped}

    # Scoped to Chapter One only: the Chapter Two chunk is excluded despite matching.
    scoped = _search(db_conn, source.id, "photosynthesis sunlight energy", anchors=["ch1.xhtml"])
    assert scoped, "expected the in-scope chunk to still be returned"
    assert {e.anchor for e in scoped} == {"ch1.xhtml"}


# A Portuguese sentence with a gerund ('correndo') whose lemma is the infinitive
# 'correr': the Portuguese stemmer collapses both to 'corr', the English stemmer
# does not — the F8 discriminator.
_PT_INFLECTED = "As crianças estavam correndo pelas montanhas"


def _seed_single_chunk(
    db_conn: Connection, source_id: UUID, *, language: str | None, body: str
) -> None:
    SqlAlchemyCorpusRepository(db_conn).replace(
        source_id,
        title="Livro",
        authors=("Autor",),
        language=language,
        schema_version=1,
        sections=(
            _section(
                0,
                "Capitulo",
                "cap.xhtml",
                (_chunk(0, body, title="Capitulo", anchor="cap.xhtml#p"),),
            ),
        ),
    )


def test_lexical_arm_uses_document_language_regconfig(db_conn: Connection) -> None:
    # EMB-13 (F8 proof): a Portuguese corpus matches an inflected-form query via the
    # book's own 'portuguese' regconfig — the infinitive 'correr' finds the stored
    # gerund 'correndo'. The identical text stored under 'english' does not match,
    # proving the per-chunk regconfig is what makes the difference. Embeddings are
    # left NULL so only the language-aware lexical arm decides.
    pt_source = _persisted_source(db_conn, "f8-pt@example.com")
    _seed_single_chunk(db_conn, pt_source.id, language="pt", body=_PT_INFLECTED)
    target_id = _chunk_id_by_text(db_conn, pt_source.id, _PT_INFLECTED)

    pt_results = _search(db_conn, pt_source.id, "correr")

    assert target_id in {e.chunk_id for e in pt_results}

    # Same text, English regconfig: the English stemmer does not relate 'correr' to
    # 'correndo', so the lexical arm finds nothing and (NULL embeddings) it returns [].
    en_source = _persisted_source(db_conn, "f8-en@example.com")
    _seed_single_chunk(db_conn, en_source.id, language="en", body=_PT_INFLECTED)

    en_results = _search(db_conn, en_source.id, "correr")

    assert en_results == []


def test_anchor_scope_does_not_bypass_source_scope(db_conn: Connection) -> None:
    # AD-031 + RET-17: the anchor filter never widens the source scope — a chunk in
    # another source that shares the same anchor value is not returned.
    source_a = _persisted_source(db_conn, "anchor-src-a@example.com")
    source_b = _persisted_source(db_conn, "anchor-src-b@example.com")
    for source_id in (source_a.id, source_b.id):
        _seed_corpus(
            db_conn,
            source_id,
            (
                _section(
                    0,
                    "Chapter One",
                    "ch1.xhtml",
                    (_chunk(0, _PHOTO, title="Chapter One", anchor="ch1.xhtml"),),
                ),
            ),
        )
    _embed_all(db_conn, source_a.id)
    _embed_all(db_conn, source_b.id)
    b_ids = {
        c.id for c in SqlAlchemyEmbeddingIndexRepository(db_conn).chunks_for_source(source_b.id)
    }

    results = _search(db_conn, source_a.id, "photosynthesis sunlight energy", anchors=["ch1.xhtml"])

    assert results, "expected the in-scope source-A chunk"
    assert all(e.source_id == source_a.id for e in results)
    assert {e.chunk_id for e in results}.isdisjoint(b_ids)


# --- Position bound (SPOILER-01..04, 07, 12, 14) --------------------------------


def test_position_bound_excludes_later_sections(db_conn: Connection) -> None:
    # SPOILER-01/02: with a bound in the middle section, book evidence carries only
    # sections at or before it — the bound section itself stays admissible, later
    # sections are inadmissible. The same query without a bound still surfaces the
    # later-section chunk (the spec's independent test).
    source = _persisted_source(db_conn, "bound-mid@example.com")
    _seed_three_topic_corpus(db_conn, source.id)
    _embed_all(db_conn, source.id)

    bounded = _search(
        db_conn, source.id, "quantum entanglement particles", not_past_anchor="geo.xhtml"
    )
    unbounded = _search(db_conn, source.id, "quantum entanglement particles")

    assert {e.anchor for e in bounded} == {"bio.xhtml#p", "geo.xhtml#o"}
    assert "phys.xhtml#q" in {e.anchor for e in unbounded}


def test_bound_at_first_section_admits_only_first_section(db_conn: Connection) -> None:
    # Edge case: a bound on the book's FIRST section admits only first-section chunks.
    source = _persisted_source(db_conn, "bound-first@example.com")
    _seed_three_topic_corpus(db_conn, source.id)
    _embed_all(db_conn, source.id)

    results = _search(
        db_conn, source.id, "quantum entanglement particles", not_past_anchor="bio.xhtml"
    )

    assert {e.anchor for e in results} == {"bio.xhtml#p"}


def test_bound_at_last_section_admits_whole_book(db_conn: Connection) -> None:
    # Edge case: a bound on the book's LAST section admits the whole book — and the
    # full result sequence (ids + scores + order) must be identical to the unbounded
    # run: a whole-book-admissible bound never perturbs RRF scoring (SPOILER-04).
    source = _persisted_source(db_conn, "bound-last@example.com")
    _seed_three_topic_corpus(db_conn, source.id)
    _embed_all(db_conn, source.id)

    baseline = _search(db_conn, source.id, "quantum entanglement particles")
    bounded = _search(
        db_conn, source.id, "quantum entanglement particles", not_past_anchor="phys.xhtml"
    )

    assert [(e.chunk_id, e.score) for e in bounded] == [(e.chunk_id, e.score) for e in baseline]


def test_single_section_book_with_bound_admits_all_chunks(db_conn: Connection) -> None:
    # Edge case: a single-section book with a bound present admits all chunks.
    source = _persisted_source(db_conn, "bound-single@example.com")
    _seed_single_chunk(db_conn, source.id, language="en", body=_PHOTO)
    _embed_all(db_conn, source.id)
    target_id = _chunk_id_by_text(db_conn, source.id, _PHOTO)

    results = _search(
        db_conn, source.id, "photosynthesis sunlight energy", not_past_anchor="cap.xhtml"
    )

    assert [e.chunk_id for e in results] == [target_id]


def test_pdf_source_bound_uses_section_order_not_page_span(db_conn: Connection) -> None:
    # SPOILER-03: a PDF source takes the same section-order predicate — page_span
    # plays no part. The seeded page spans run OPPOSITE to section order (the first
    # section holds the later pages), so no page threshold can reproduce the bound
    # outcome: only a section-order comparison admits the first section while
    # excluding the second.
    source = _persisted_pdf_source(db_conn, "bound-pdf@example.com")
    _seed_corpus(
        db_conn,
        source.id,
        (
            _section(
                0,
                "Chapter One",
                "p1.xhtml",
                (
                    _chunk(
                        0,
                        _PHOTO,
                        title="Chapter One",
                        anchor="p1.xhtml",
                        page_span=(5, 6),
                    ),
                ),
            ),
            _section(
                1,
                "Chapter Two",
                "p2.xhtml",
                (
                    _chunk(
                        0,
                        _PHOTO2,
                        title="Chapter Two",
                        anchor="p2.xhtml",
                        page_span=(1, 2),
                    ),
                ),
            ),
        ),
    )
    _embed_all(db_conn, source.id)

    bounded = _search(
        db_conn, source.id, "photosynthesis sunlight energy", not_past_anchor="p1.xhtml"
    )
    unbounded = _search(db_conn, source.id, "photosynthesis sunlight energy")

    assert {e.anchor for e in bounded} == {"p1.xhtml"}
    assert {e.anchor for e in unbounded} == {"p1.xhtml", "p2.xhtml"}


def test_bound_keeps_shipped_rrf_scores_for_admissible_rows(db_conn: Connection) -> None:
    # SPOILER-04: inside the bounded pool the shipped RRF arithmetic is untouched.
    # The ocean chunk matches BOTH arms at rank 1 within the bound (only it shares
    # query tokens), so its score is exactly 1/(k+1) + 1/(k+1) — the fused value the
    # statement has always produced for a both-arm rank-1 hit, not a re-scored one.
    source = _persisted_source(db_conn, "bound-score@example.com")
    _seed_three_topic_corpus(db_conn, source.id)
    _embed_all(db_conn, source.id)
    target_id = _chunk_id_by_text(db_conn, source.id, _OCEAN)

    results = _search(db_conn, source.id, "ocean currents heat", not_past_anchor="geo.xhtml")

    assert results, "expected the bounded both-arm hit"
    top = results[0]
    assert top.chunk_id == target_id
    expected = 1.0 / (_K + 1) + 1.0 / (_K + 1)
    assert top.score == pytest.approx(expected)


def test_anchors_scope_and_position_bound_compose_as_conjunction(db_conn: Connection) -> None:
    # SPOILER-07: the anchor scope and the position bound both constrain the shared
    # scoped CTE and compose as a logical AND — a scope pointing past the bound takes
    # the existing empty outcome (no bypass), a scope inside the bound serves exactly
    # the intersection.
    source = _persisted_source(db_conn, "bound-and-scope@example.com")
    _seed_three_topic_corpus(db_conn, source.id)
    _embed_all(db_conn, source.id)

    past_bound = _search(
        db_conn,
        source.id,
        "quantum entanglement particles",
        anchors=["phys.xhtml#q"],
        not_past_anchor="geo.xhtml",
    )
    within = _search(
        db_conn,
        source.id,
        "photosynthesis sunlight energy",
        anchors=["bio.xhtml#p"],
        not_past_anchor="geo.xhtml",
    )

    assert past_bound == []
    assert {e.anchor for e in within} == {"bio.xhtml#p"}


def test_unmatched_bound_anchor_yields_zero_book_evidence_and_warns(
    db_conn: Connection, caplog: pytest.LogCaptureFixture
) -> None:
    # SPOILER-14: a bound anchor matching no section of the source fails closed —
    # ZERO book evidence, never an unfiltered fallback — and a warning is logged
    # identifying the source and the unmatched anchor.
    source = _persisted_source(db_conn, "bound-stale@example.com")
    _seed_three_topic_corpus(db_conn, source.id)
    _embed_all(db_conn, source.id)

    with caplog.at_level(logging.WARNING, logger="app.infrastructure.db.retrieval"):
        results = _search(
            db_conn,
            source.id,
            "photosynthesis sunlight energy",
            not_past_anchor="ghost.xhtml#missing",
        )

    assert results == []
    expected_message = (
        "retrieval.position_bound_unmatched: anchor ghost.xhtml#missing"
        f" matches no section of source {source.id}"
    )
    records = [r for r in caplog.records if r.getMessage() == expected_message]
    assert records
    assert records[0].source_id == str(source.id)
    assert records[0].anchor == "ghost.xhtml#missing"


def test_explicit_none_bound_matches_unbounded_behavior(db_conn: Connection) -> None:
    # SPOILER-12: passing ``not_past_anchor=None`` explicitly is exactly the pre-cycle
    # call — identical results to omitting the parameter.
    source = _persisted_source(db_conn, "bound-none@example.com")
    _seed_three_topic_corpus(db_conn, source.id)
    _embed_all(db_conn, source.id)

    omitted = _search(db_conn, source.id, "quantum entanglement particles")
    explicit = _search(db_conn, source.id, "quantum entanglement particles", not_past_anchor=None)

    assert [(e.chunk_id, e.score, e.anchor) for e in explicit] == [
        (e.chunk_id, e.score, e.anchor) for e in omitted
    ]


def test_bound_resolves_within_the_queried_source(db_conn: Connection) -> None:
    # Edge case: the bound is per-source. An anchor that exists only in source A must
    # not bound source B by A's section positions — resolved within B it matches
    # nothing, so B fails closed (empty) rather than being half-bounded by another
    # book's ordering; B's own anchor bounds B normally, serving only B's rows.
    source_a = _persisted_source(db_conn, "bound-src-a@example.com")
    source_b = _persisted_source(db_conn, "bound-src-b@example.com")
    _seed_three_topic_corpus(db_conn, source_a.id)
    _seed_corpus(
        db_conn,
        source_b.id,
        (
            _section(
                0,
                "Biology",
                "bio.xhtml",
                (_chunk(0, _PHOTO, title="Biology", anchor="bio.xhtml#b"),),
            ),
            _section(
                1,
                "Geography",
                "geo.xhtml",
                (_chunk(0, _OCEAN, title="Geography", anchor="geo.xhtml#b"),),
            ),
        ),
    )
    _embed_all(db_conn, source_a.id)
    _embed_all(db_conn, source_b.id)

    foreign_anchor = _search(
        db_conn, source_b.id, "photosynthesis sunlight energy", not_past_anchor="phys.xhtml"
    )
    own_anchor = _search(db_conn, source_b.id, "ocean currents heat", not_past_anchor="geo.xhtml")

    assert foreign_anchor == []
    # B's own last-section bound admits B's whole (two-section) book — and nothing
    # from A, even though A shares corpus content and A holds the foreign anchor.
    assert {e.anchor for e in own_anchor} == {"bio.xhtml#b", "geo.xhtml#b"}
    assert all(e.source_id == source_b.id for e in own_anchor)


def test_sectionless_source_yields_no_evidence_with_or_without_bound(
    db_conn: Connection,
) -> None:
    # Edge case: a source with NO sections/chunks behaves as today — no evidence
    # either way. Search returns empty with no bound, and stays empty (no error,
    # no fallback) when a bound is supplied; the sectionless source has nothing
    # for any anchor to match, so the bound withholds rather than widening.
    source = _persisted_source(db_conn, "bound-sectionless@example.com")

    unbounded = _search(db_conn, source.id, "photosynthesis sunlight energy")
    bounded = _search(
        db_conn, source.id, "photosynthesis sunlight energy", not_past_anchor="bio.xhtml"
    )

    assert unbounded == []
    assert bounded == []


def test_zero_percent_position_bounds_at_anchor_section_not_percent(
    db_conn: Connection,
) -> None:
    # Edge case: percent reads 0.00 (book start or prose-free book) — the ANCHOR,
    # not the percent, defines the bound. A position saved with percent 0.00 on a
    # MID-book section anchor still bounds at that anchor's section: earlier
    # sections and the bound section itself stay admissible, later sections are
    # excluded. A percent-defined bound (0.00 = book start) could admit neither —
    # the adapter never reads the stored percent; this pins that contract at the
    # SQL layer.
    source = _persisted_source(db_conn, "bound-zero@example.com")
    _seed_three_topic_corpus(db_conn, source.id)
    _embed_all(db_conn, source.id)
    SqlAlchemyReadingPositionRepository(db_conn).upsert(
        source.user_id,
        source.id,
        anchor="geo.xhtml",
        percent=Decimal("0.00"),
        updated_at=datetime.now(UTC),
    )
    saved = SqlAlchemyReadingPositionRepository(db_conn).get(source.user_id, source.id)
    assert saved is not None
    assert saved.anchor == "geo.xhtml"
    assert saved.percent == Decimal("0.00")

    results = _search(
        db_conn, source.id, "quantum entanglement particles", not_past_anchor="geo.xhtml"
    )

    # The mid-book anchor's section (Geography) and everything before it are
    # admissible; the later Physics section never surfaces despite the 0.00.
    assert {e.anchor for e in results} == {"bio.xhtml#p", "geo.xhtml#o"}
