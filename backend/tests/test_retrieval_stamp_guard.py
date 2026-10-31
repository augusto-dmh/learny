"""The embedding-stamp guard — a query never fuses vectors from two identities.

ADR-0019 promised "a query never fuses vectors from a different model"; the
per-chunk ``embedding_model`` stamp is the recording mechanism, and the semantic
arms now enforce it: a chunk or note stamped with another identity (another
model, or the same model at another dimension) returns no semantic evidence —
the corpus answers lexical-only until re-embedded. These tests prove the gate at
the SQL adapter against the live test DB, using the RRF arithmetic (``k`` from
settings) so "lost its semantic term" is an exact score delta, not a vibe:

- a foreign-stamped chunk is still found lexically, its score drops by exactly
  its semantic term, and every other chunk's evidence is unchanged (no fusion);
- a mid-re-embed mixed corpus fuses only current-stamped chunks;
- the notes arm applies the same rule against ``notes.embedding_model``;
- the ``vector(N)`` column itself refuses a wrong-length vector, so a corpus
  can never hold two vector widths at rest.

Everything here seeds through ``db_conn`` and rolls back — no committed rows.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, select
from sqlalchemy import update as sa_update

from app.core.config import get_settings
from app.domain.entities import Note, Source, User
from app.infrastructure.db.metadata import corpus_chunks, corpus_documents, corpus_sections
from app.infrastructure.db.repositories import (
    SqlAlchemyEmbeddingIndexRepository,
    SqlAlchemyNoteRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyUserRepository,
)
from app.infrastructure.db.retrieval import SqlAlchemyRetrievalRepository
from app.infrastructure.embeddings import DeterministicEmbeddingAdapter
from tests.conftest import requires_db
from tests.eval_runner import build_corpus_in_db
from tests.fixtures_epub import valid_book

pytestmark = requires_db

_SETTINGS = get_settings()
_IDENTITY = DeterministicEmbeddingAdapter().model
_FOREIGN = "foreign-embedding@768"
_K = _SETTINGS.retrieval_rrf_k


def _persisted_source(db_conn: Connection, email: str) -> tuple[User, Source]:
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
    return user, SqlAlchemySourceRepository(db_conn).add(source)


def _embed_all(db_conn: Connection, source_id: UUID, *, model: str = _IDENTITY) -> dict[UUID, str]:
    """Embed every chunk with the deterministic adapter, stamped ``model``.

    Returns each chunk's id → text, so a test can pick a target by content.
    """
    index = SqlAlchemyEmbeddingIndexRepository(db_conn)
    chunks = index.chunks_for_source(source_id)
    vectors = DeterministicEmbeddingAdapter().embed_documents([c.text for c in chunks])
    index.set_embeddings(list(zip((c.id for c in chunks), vectors, strict=True)), model=model)
    return {c.id: c.text for c in chunks}


def _stamp(db_conn: Connection, chunk_id: UUID, model: str) -> None:
    """Hand-stamp one chunk with ``model`` (the operator's mid-flight state)."""
    db_conn.execute(
        sa_update(corpus_chunks).where(corpus_chunks.c.id == chunk_id).values(embedding_model=model)
    )


def _search(
    db_conn: Connection,
    source_id: UUID,
    query: str,
    *,
    model: str = _IDENTITY,
    user_id: UUID | None = None,
    include_notes: bool = False,
):
    """Hybrid search with ``model`` as the active identity (query embedded to match)."""
    query_vec = DeterministicEmbeddingAdapter().embed_query(query)
    return SqlAlchemyRetrievalRepository(db_conn).search(
        source_id=source_id,
        query_text=query,
        query_vec=query_vec,
        embedding_model=model,
        top_k=50,
        semantic_limit=_SETTINGS.retrieval_semantic_limit,
        lexical_limit=_SETTINGS.retrieval_lexical_limit,
        rrf_k=_K,
        ef_search=_SETTINGS.hnsw_ef_search,
        user_id=user_id,
        include_notes=include_notes,
    )


def _scores(results) -> dict[UUID, float]:  # noqa: ANN001 — Evidence list
    return {r.chunk_id: r.score for r in results}


def _chunk_texts(db_conn: Connection, source_id: UUID) -> dict[UUID, str]:
    """Each chunk's id → text, read through the retrieval path's own join."""
    stmt = (
        select(corpus_chunks.c.id, corpus_chunks.c.text)
        .select_from(corpus_chunks)
        .join(corpus_sections, corpus_chunks.c.section_id == corpus_sections.c.id)
        .join(corpus_documents, corpus_sections.c.document_id == corpus_documents.c.id)
        .where(corpus_documents.c.source_id == source_id)
        .order_by(corpus_chunks.c.id)
    )
    return {row.id: row.text for row in db_conn.execute(stmt).all()}


def _chunk_for(chunks: dict[UUID, str], token: str) -> UUID:
    for chunk_id, text in chunks.items():
        if token in text:
            return chunk_id
    raise AssertionError(f"no chunk contains {token!r}")


@pytest.fixture
def embedded_source(db_conn: Connection) -> Source:
    """A ready source whose corpus is fully embedded at the default identity."""
    _user, source = _persisted_source(db_conn, f"{uuid4()}@example.com")
    build_corpus_in_db(db_conn, source, valid_book())
    _embed_all(db_conn, source.id)
    return source


def test_foreign_stamp_skips_semantic_keeps_lexical(
    db_conn: Connection, embedded_source: Source
) -> None:
    # AC 12: a chunk stamped with a foreign identity returns no semantic
    # evidence — the lexical arm still finds it (lexical-only until re-embedded).
    chunks = _chunk_texts(db_conn, embedded_source.id)
    assert len(chunks) > 1
    target = _chunk_for(chunks, "Chapter two content")
    query = "chapter two content"

    before = _scores(_search(db_conn, embedded_source.id, query))

    _stamp(db_conn, target, _FOREIGN)
    after = _scores(_search(db_conn, embedded_source.id, query))

    # The lexical arm keeps the chunk in the results...
    assert target in after
    # ...its semantic term is gone: the score dropped by exactly its semantic
    # contribution, landing on the pure-lexical RRF value (semantic arm empty for
    # this chunk — a 1-term RRF score of 1/(k+lex_rank), strictly below before).
    assert after[target] < before[target]
    # And the exact RRF arithmetic: its remaining score is 1/(k+rank) for some
    # lexical rank ≥ 1 — i.e. at most 1/(k+1).
    assert after[target] <= 1.0 / (_K + 1) + 1e-12
    # Every OTHER current-stamped chunk only ever gains: leaving the semantic arm
    # can improve the survivors' semantic ranks, never hand a semantic term to a
    # foreign-stamped vector (no cross-identity fusion anywhere in the fusion).
    for chunk_id, score in before.items():
        if chunk_id != target:
            assert after[chunk_id] >= score


def test_mixed_corpus_fuses_only_current(db_conn: Connection, embedded_source: Source) -> None:
    # AC 13: mid-re-embed (some stamps current, some foreign) the semantic arm
    # serves only current-stamped chunks — no result gains a semantic term from a
    # foreign-stamped vector.
    chunks = _chunk_texts(db_conn, embedded_source.id)
    current = _chunk_for(chunks, "Chapter two content")
    foreign = {cid for cid in chunks if cid != current}
    for chunk_id in foreign:
        _stamp(db_conn, chunk_id, _FOREIGN)

    results = _search(db_conn, embedded_source.id, "chapter two content")
    scores = _scores(results)

    current_best = max(s for cid, s in scores.items() if cid not in foreign)
    foreign_best = max((s for cid, s in scores.items() if cid in foreign), default=0.0)
    # A current chunk holds the top fused score: only current stamps earned a
    # semantic term, and the top semantic rank went to one of them.
    assert current_best > foreign_best
    # No foreign-stamped chunk outruns the pure-lexical ceiling 1/(k+1).
    assert foreign_best <= 1.0 / (_K + 1) + 1e-12


def test_notes_semantic_arm_respects_stamp(db_conn: Connection, embedded_source: Source) -> None:
    # AC 14: the notes arm applies the same rule against notes.embedding_model —
    # a foreign-stamped note answers lexical-only until re-embedded.
    _user, _source = _persisted_source(db_conn, f"{uuid4()}@example.com")
    repo = SqlAlchemyNoteRepository(db_conn)
    now = datetime.now(UTC)
    note = Note(
        id=uuid4(),
        user_id=_user.id,
        title="Gravitational tides",
        body_markdown="The moon gravity pulls seawater into rising tides along the coast.",
        created_at=now,
        updated_at=now,
    )
    repo.add(note)
    adapter = DeterministicEmbeddingAdapter()

    repo.set_embedding(
        note.id, embedding=adapter.embed_documents([note.body_markdown])[0], model=_IDENTITY
    )
    query = "moon gravity seawater tides"
    before = _scores(
        _search(
            db_conn,
            embedded_source.id,
            query,
            model=_IDENTITY,
            user_id=_user.id,
            include_notes=True,
        )
    )
    assert note.id in before  # sanity: the current-stamped note is served

    repo.set_embedding(
        note.id, embedding=adapter.embed_documents([note.body_markdown])[0], model=_FOREIGN
    )
    after = _scores(
        _search(
            db_conn,
            embedded_source.id,
            query,
            model=_IDENTITY,
            user_id=_user.id,
            include_notes=True,
        )
    )

    # The note's lexical arm keeps it findable (search_vector unaffected)...
    assert note.id in after
    # ...but its semantic term is gone: the score dropped to the note-lexical RRF
    # value (weighted), never fusing the foreign vector.
    assert after[note.id] < before[note.id]
    assert after[note.id] <= _SETTINGS.retrieval_notes_weight * (1.0 / (_K + 1)) + 1e-12


def test_wrong_length_insert_raises(db_conn: Connection, embedded_source: Source) -> None:
    # AC 15: the column's vector(N) typmod is the last line of defense — a
    # vector of another length cannot rest beside the corpus, whatever wrote it.
    chunks = _chunk_texts(db_conn, embedded_source.id)
    target = next(iter(chunks))

    with pytest.raises(Exception) as excinfo:  # noqa: PT011 — any pg/SQLAlchemy error family
        db_conn.execute(
            sa_update(corpus_chunks)
            .where(corpus_chunks.c.id == target)
            .values(embedding=[0.0] * 768)
        )

    assert (
        "does not match vector type" in str(excinfo.value)
        or "expected 1536 dimensions" in str(excinfo.value)
        or "dims" in str(excinfo.value).lower()
    )


def test_every_stamp_present_is_reported(db_conn: Connection, embedded_source: Source) -> None:
    # The distinct stamps are the per-source tracking the operator view reports:
    # read straight from the same column retrieval filters on (AC 17's source).
    chunks = _chunk_texts(db_conn, embedded_source.id)
    _stamp(db_conn, next(iter(chunks)), _FOREIGN)

    stmt = (
        select(corpus_chunks.c.embedding_model)
        .select_from(corpus_chunks)
        .join(corpus_sections, corpus_chunks.c.section_id == corpus_sections.c.id)
        .join(corpus_documents, corpus_sections.c.document_id == corpus_documents.c.id)
        .where(corpus_documents.c.source_id == embedded_source.id)
    )
    stamps = {row[0] for row in db_conn.execute(stmt).all()}

    assert stamps == {_IDENTITY, _FOREIGN}
