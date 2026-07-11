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
"""

from __future__ import annotations

from datetime import UTC, datetime
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


def _chunk(index: int, text: str, *, title: str, anchor: str) -> SectionChunk:
    return SectionChunk(
        index=index,
        text=text,
        section_path=(title,),
        anchor=anchor,
        page_span=None,
    )


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
    index.set_embeddings(list(zip((c.id for c in chunks), vectors, strict=True)))


def _chunk_id_by_text(db_conn: Connection, source_id: UUID, text: str) -> UUID:
    index = SqlAlchemyEmbeddingIndexRepository(db_conn)
    for chunk in index.chunks_for_source(source_id):
        if chunk.text == text:
            return chunk.id
    raise AssertionError(f"no chunk with text {text!r}")


def _search(db_conn: Connection, source_id: UUID, query: str, *, top_k: int = _TOP_K):
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
    )


# A three-chunk corpus with lexically disjoint topics, so query terms select a
# single known chunk on the lexical arm.
_PHOTO = "photosynthesis converts sunlight into chemical energy in green plants"
_OCEAN = "ocean currents redistribute heat across the planet over time"
_QUANTUM = "quantum entanglement links distant particles instantly"


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
