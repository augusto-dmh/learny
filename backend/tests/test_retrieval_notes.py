"""Phase A gate (integration) — the user's notes fused into hybrid retrieval (NL-02,
NL-05, NL-06, NL-07).

Seeds a canonical book corpus (embedded with the deterministic adapter) plus per-user
notes (their trigger-fed ``search_vector`` and, when embedded, their vector), and drives
``SqlAlchemyRetrievalRepository.search`` with ``include_notes`` on and off against the
live test DB. Assertions target spec outcomes:

- fusion: a note carrying a distinctive fact absent from the book ranks first and
  projects note evidence (origin='note', note id, title, ``note:<id>`` anchor, empty
  section path, no page span, body snippet) (NL-02).
- isolation: another user's note is never a candidate (NL-05).
- degrade: a note whose embedding is not yet written is still lexically retrievable and
  the query does not error; an empty-body note is excluded from both arms (NL-06).
- lifecycle: a deleted note disappears immediately (NL-07).
- determinism: the fused ranking is stable across identical runs (NL-02).
- regression: with ``include_notes`` off (or no ``user_id``) results are byte-identical
  to the book-only path, even for a user who has notes (invariant 1).
- composition: the anchored (teaching) variant constrains only the book arms; notes
  (which have no anchors) still fuse in.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Connection, text

from app.domain.entities import (
    CorpusSectionRecord,
    Note,
    ParsedSection,
    SectionChunk,
    Source,
    User,
)
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemyEmbeddingIndexRepository,
    SqlAlchemyNoteRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyUserRepository,
)
from app.infrastructure.db.retrieval import SqlAlchemyRetrievalRepository
from app.infrastructure.embeddings import DeterministicEmbeddingAdapter
from tests.conftest import requires_db

pytestmark = requires_db

_K = 60
_SEMANTIC_LIMIT = 50
_LEXICAL_LIMIT = 50
_EF_SEARCH = 100
_TOP_K = 10

# Book topics, lexically disjoint from the distinctive note fact below.
_PHOTO = "photosynthesis converts sunlight into chemical energy in green plants"
_OCEAN = "ocean currents redistribute heat across the planet over time"
_PHOTO2 = "photosynthesis in leaves turns sunlight and water into sugar"

# A fact the book never mentions — rare tokens so only a note can match it.
_NOTE_FACT = "zolgensma gene therapy costs approximately two million dollars per dose"


def _persisted_user_and_source(db_conn: Connection, email: str) -> tuple[User, Source]:
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


def _section(position: int, title: str, anchor: str, text: str) -> CorpusSectionRecord:
    """One single-chunk section whose chunk anchor equals the section anchor."""
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
        chunks=(
            SectionChunk(index=0, text=text, section_path=(title,), anchor=anchor, page_span=None),
        ),
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
    index = SqlAlchemyEmbeddingIndexRepository(db_conn)
    adapter = DeterministicEmbeddingAdapter()
    chunks = index.chunks_for_source(source_id)
    vectors = adapter.embed_documents([c.text for c in chunks])
    index.set_embeddings(
        list(zip((c.id for c in chunks), vectors, strict=True)), model=adapter.model
    )


def _two_topic_book(db_conn: Connection, source_id: UUID) -> None:
    _seed_corpus(
        db_conn,
        source_id,
        (
            _section(0, "Biology", "bio.xhtml", _PHOTO),
            _section(1, "Geography", "geo.xhtml", _OCEAN),
        ),
    )
    _embed_all(db_conn, source_id)


def _seed_note(
    db_conn: Connection, user_id: UUID, *, title: str, body: str, embed: bool = True
) -> UUID:
    """Insert a note (its search_vector is trigger-fed) and optionally embed its body."""
    repo = SqlAlchemyNoteRepository(db_conn)
    now = datetime.now(UTC)
    note = Note(
        id=uuid4(), user_id=user_id, title=title, body_markdown=body, created_at=now, updated_at=now
    )
    repo.add(note)
    if embed and body:
        adapter = DeterministicEmbeddingAdapter()
        repo.set_embedding(
            note.id, embedding=adapter.embed_documents([body])[0], model=adapter.model
        )
    return note.id


def _search(
    db_conn: Connection,
    source_id: UUID,
    query: str,
    *,
    user_id: UUID | None = None,
    include_notes: bool = False,
    anchors: list[str] | None = None,
    top_k: int = _TOP_K,
):
    qv = DeterministicEmbeddingAdapter().embed_query(query)
    return SqlAlchemyRetrievalRepository(db_conn).search(
        source_id=source_id,
        query_text=query,
        query_vec=qv,
        top_k=top_k,
        semantic_limit=_SEMANTIC_LIMIT,
        lexical_limit=_LEXICAL_LIMIT,
        rrf_k=_K,
        ef_search=_EF_SEARCH,
        anchors=anchors,
        user_id=user_id,
        include_notes=include_notes,
    )


def test_distinctive_note_ranks_first_and_projects_note_evidence(db_conn: Connection) -> None:
    # NL-02: a note carrying a fact the book never mentions ranks first for that query,
    # and its evidence is projected distinctly from a book chunk.
    #
    # Two determinism guards, no assertion changes:
    # 1. Every query token below appears verbatim in the note body ('simple' does not
    #    stem, so "cost" would NOT match the body's "costs") — the note then wins BOTH
    #    note arms while the book (which never mentions zolgensma) can at best take one
    #    semantic slot, making the top rank a decisive 2/(k+1) vs 1/(k+1), never an
    #    RRF tie broken by comparing random UUIDs.
    # 2. Rebuild the HNSW index first (transactional; skips the aborted tuples that
    #    every rolled-back test leaves in the shared graph) so approximate recall of
    #    the freshly seeded note cannot degrade with suite-run history.
    db_conn.execute(text("REINDEX INDEX ix_notes_embedding_hnsw"))
    user, source = _persisted_user_and_source(db_conn, "fuse@example.com")
    _two_topic_book(db_conn, source.id)
    note_id = _seed_note(db_conn, user.id, title="Drug pricing", body=_NOTE_FACT)

    results = _search(
        db_conn, source.id, "zolgensma gene therapy dose", user_id=user.id, include_notes=True
    )

    assert results, "expected the note among the results"
    top = results[0]
    assert top.origin == "note"
    assert top.chunk_id == note_id  # the note id doubles as the opaque evidence id
    assert top.note_id == note_id
    assert top.note_title == "Drug pricing"
    assert top.anchor == f"note:{note_id}"
    assert top.section_path == ()
    assert top.page_span is None
    assert top.snippet == _NOTE_FACT


def test_other_users_note_is_never_a_candidate(db_conn: Connection) -> None:
    # NL-05: retrieval considers only the requesting user's notes, regardless of who
    # owns the book source.
    owner, source = _persisted_user_and_source(db_conn, "owner@example.com")
    other = User(id=uuid4(), email="intruder@example.com", created_at=datetime.now(UTC))
    SqlAlchemyUserRepository(db_conn).add(other)
    _two_topic_book(db_conn, source.id)
    _seed_note(db_conn, other.id, title="Secret", body=_NOTE_FACT)  # the OTHER user's note

    results = _search(
        db_conn, source.id, "zolgensma gene therapy dose cost", user_id=owner.id, include_notes=True
    )

    assert all(e.origin == "book" for e in results)  # the other user's note never appears


def test_note_with_null_embedding_is_still_lexically_retrievable(db_conn: Connection) -> None:
    # NL-06: a note not yet embedded (NULL embedding, async lag) still matches on the
    # lexical arm and the query does not error.
    user, source = _persisted_user_and_source(db_conn, "lag@example.com")
    _two_topic_book(db_conn, source.id)
    note_id = _seed_note(db_conn, user.id, title="Unindexed", body=_NOTE_FACT, embed=False)

    # Every query token is present verbatim in the body — websearch_to_tsquery ANDs the
    # terms, and 'simple' does not stem, so the lexical arm alone (no vector) must match.
    results = _search(
        db_conn, source.id, "zolgensma gene therapy dose", user_id=user.id, include_notes=True
    )

    assert any(e.origin == "note" and e.note_id == note_id for e in results)


def test_empty_body_note_is_excluded_from_both_arms(db_conn: Connection) -> None:
    # NL-06: an empty-body note is not a retrieval candidate on either arm.
    user, source = _persisted_user_and_source(db_conn, "empty@example.com")
    _two_topic_book(db_conn, source.id)
    _seed_note(db_conn, user.id, title="Zolgensma gene therapy dose", body="", embed=False)

    results = _search(
        db_conn, source.id, "zolgensma gene therapy dose cost", user_id=user.id, include_notes=True
    )

    assert all(e.origin == "book" for e in results)  # the empty-body note never appears


def test_deleted_note_disappears_immediately(db_conn: Connection) -> None:
    # NL-07: a deleted note stops appearing at once — its index rows die with it.
    user, source = _persisted_user_and_source(db_conn, "del@example.com")
    _two_topic_book(db_conn, source.id)
    note_id = _seed_note(db_conn, user.id, title="Temp", body=_NOTE_FACT)
    query = "zolgensma gene therapy dose cost"
    assert any(e.note_id == note_id for e in _search(
        db_conn, source.id, query, user_id=user.id, include_notes=True
    ))

    SqlAlchemyNoteRepository(db_conn).delete(note_id)

    after = _search(db_conn, source.id, query, user_id=user.id, include_notes=True)
    assert all(e.note_id != note_id for e in after)


def test_fused_ordering_is_deterministic(db_conn: Connection) -> None:
    # NL-02: identical inputs yield an identical fused order (stable id tie-break).
    user, source = _persisted_user_and_source(db_conn, "det@example.com")
    _two_topic_book(db_conn, source.id)
    _seed_note(db_conn, user.id, title="Fact", body=_NOTE_FACT)
    query = "photosynthesis zolgensma sunlight dose"

    first = _search(db_conn, source.id, query, user_id=user.id, include_notes=True)
    second = _search(db_conn, source.id, query, user_id=user.id, include_notes=True)

    assert [(e.chunk_id, e.score) for e in first] == [(e.chunk_id, e.score) for e in second]


def test_include_notes_off_is_identical_to_book_only(db_conn: Connection) -> None:
    # Invariant 1: with the flag off — even for a user who HAS a matching note — results
    # are exactly the book-only path; and the flag with no user_id stays book-only too.
    user, source = _persisted_user_and_source(db_conn, "regress@example.com")
    _two_topic_book(db_conn, source.id)
    _seed_note(db_conn, user.id, title="Has a note", body=_PHOTO)  # would match if included
    query = "photosynthesis sunlight energy"

    baseline = _search(db_conn, source.id, query)  # today's book-only call
    flag_off = _search(db_conn, source.id, query, user_id=user.id, include_notes=False)
    no_user = _search(db_conn, source.id, query, user_id=None, include_notes=True)

    expected = [(e.chunk_id, e.score) for e in baseline]
    assert all(e.origin == "book" for e in baseline)
    assert [(e.chunk_id, e.score) for e in flag_off] == expected
    assert [(e.chunk_id, e.score) for e in no_user] == expected


def test_zero_notes_user_behaves_as_book_only(db_conn: Connection) -> None:
    # Edge case: notes enabled but the user has zero notes → exactly the book-only
    # result, with no empty-arm artifacts.
    user, source = _persisted_user_and_source(db_conn, "zero@example.com")
    _two_topic_book(db_conn, source.id)
    query = "photosynthesis sunlight energy"

    baseline = _search(db_conn, source.id, query)
    with_notes = _search(db_conn, source.id, query, user_id=user.id, include_notes=True)

    assert [(e.chunk_id, e.score) for e in with_notes] == [(e.chunk_id, e.score) for e in baseline]
    assert all(e.origin == "book" for e in with_notes)


def test_anchored_variant_constrains_only_book_arms(db_conn: Connection) -> None:
    # Invariant 5: an anchor scope (teaching) restricts the BOOK arms to the target
    # subtree while the note arms — which have no anchors — still fuse in.
    user, source = _persisted_user_and_source(db_conn, "anchored@example.com")
    _seed_corpus(
        db_conn,
        source.id,
        (
            _section(0, "Chapter One", "ch1.xhtml", _PHOTO),
            _section(1, "Chapter Two", "ch2.xhtml", _PHOTO2),
        ),
    )
    _embed_all(db_conn, source.id)
    note_id = _seed_note(db_conn, user.id, title="Aside", body=_NOTE_FACT)

    results = _search(
        db_conn,
        source.id,
        "photosynthesis zolgensma sunlight dose",
        user_id=user.id,
        include_notes=True,
        anchors=["ch1.xhtml"],
    )

    anchors = {e.anchor for e in results}
    assert "ch1.xhtml" in anchors  # the in-subtree book chunk is served
    assert "ch2.xhtml" not in anchors  # the out-of-subtree book chunk is excluded
    assert any(e.origin == "note" and e.note_id == note_id for e in results)  # note still fuses in
