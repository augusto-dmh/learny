"""Embedding-status CLI (live DB): the per-source stamp census and the exit contract.

``python -m app.cli.embedding_status`` reads the same environment the application
reads. The tests seed a real corpus through the real parser/chunker, embed it
with the deterministic adapter, and run the command's ``main`` against the
shared rolled-back connection:

- the aligned path: per-source totals/current/stale/distinct stamps plus the
  active identity and dimension on stdout, and exit ``0``;
- the misaligned path: a configured dimension the columns do not match prints
  the exact resize + re-embed procedure (drop index, clear, resize all three
  embedding columns, recreate index, per-source ``reembed.document``) and exits
  ``1`` — the command never resizes anything itself.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

import pytest
from sqlalchemy import Connection

from app.cli import embedding_status
from app.infrastructure.embeddings import DeterministicEmbeddingAdapter
from tests.conftest import requires_db
from tests.test_retrieval_stamp_guard import (
    _IDENTITY,
    _embed_all,
    _persisted_source,
    _stamp,
)

pytestmark = requires_db


@pytest.fixture
def status_uow(db_conn: Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def _uow() -> Iterator[Connection]:
        yield db_conn

    monkeypatch.setattr(embedding_status, "_uow", _uow)


def _run(capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = embedding_status.main()
    out = capsys.readouterr().out
    return code, out


def test_reports_per_source_state_and_exits_zero(
    db_conn: Connection, status_uow: None, capsys: pytest.CaptureFixture[str]
) -> None:
    # AC 17: per source — total, current, stale, distinct stamps — plus the
    # active identity and dimension; exit 0 while the columns match.
    _user, source = _persisted_source(db_conn, f"{uuid4()}@example.com")
    from tests.eval_runner import build_corpus_in_db
    from tests.fixtures_epub import valid_book

    build_corpus_in_db(db_conn, source, valid_book())
    chunks = _embed_all(db_conn, source.id)
    # One foreign stamp makes the source mixed, not stale — the report says so.
    _stamp(db_conn, next(iter(chunks)), "foreign-embedding@768")

    code, out = _run(capsys)

    assert code == 0
    assert f"active embedding identity: {_IDENTITY}" in out
    assert f"(dimension {DeterministicEmbeddingAdapter().model.split('@')[1]})" in out
    assert f"total={len(chunks)} current={len(chunks) - 1} stale=1" in out
    assert "state=mixed" in out
    assert _IDENTITY in out and "foreign-embedding@768" in out
    # Aligned: no resize procedure, and the vector columns are reported ok.
    assert "MISMATCH" not in out
    assert "vector(1536) — ok" in out
    assert "ALTER TABLE" not in out


def test_reports_stale_source_and_names_the_reembed_command(
    db_conn: Connection, status_uow: None, capsys: pytest.CaptureFixture[str]
) -> None:
    # A source fully stamped at a foreign identity is stale: exit stays 0 (the
    # columns match) but the command prints the exact re-embed call.
    _user, source = _persisted_source(db_conn, f"{uuid4()}@example.com")
    from tests.eval_runner import build_corpus_in_db
    from tests.fixtures_epub import valid_book

    build_corpus_in_db(db_conn, source, valid_book())
    _embed_all(db_conn, source.id, model="foreign-embedding@768")

    code, out = _run(capsys)

    assert code == 0
    assert "state=stale" in out
    assert f"reembed.document --args '[\"{source.id}\"]'" in out
    assert "answers lexical-only" in out


def test_misaligned_prints_procedure_and_exits_one(
    db_conn: Connection,
    status_uow: None,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # AC 16: a configured dimension the columns do not match — exit 1 with the
    # exact resize + reembed procedure, naming all three columns. Nothing is
    # executed: the command's only writes are its prints.
    _user, source = _persisted_source(db_conn, f"{uuid4()}@example.com")
    from tests.eval_runner import build_corpus_in_db
    from tests.fixtures_epub import valid_book

    build_corpus_in_db(db_conn, source, valid_book())
    _embed_all(db_conn, source.id)

    monkeypatch.setenv("LEARNY_EMBEDDING_DIM", "768")
    from tests.conftest import clear_settings_and_generation_caches

    clear_settings_and_generation_caches()
    try:
        code, out = _run(capsys)
    finally:
        monkeypatch.undo()
        clear_settings_and_generation_caches()

    assert code == 1
    assert "MISMATCH (configured 768)" in out
    assert "DROP INDEX IF EXISTS ix_corpus_chunks_embedding_hnsw" in out
    assert "UPDATE corpus_chunks SET embedding = NULL;" in out
    assert "UPDATE notes SET embedding = NULL;" in out
    assert "UPDATE quiz_items SET embedding = NULL;" in out
    assert "ALTER TABLE corpus_chunks ALTER COLUMN embedding TYPE vector(768);" in out
    assert "ALTER TABLE notes ALTER COLUMN embedding TYPE vector(768);" in out
    assert "ALTER TABLE quiz_items ALTER COLUMN embedding TYPE vector(768);" in out
    assert (
        "CREATE INDEX ix_corpus_chunks_embedding_hnsw ON corpus_chunks USING hnsw "
        "(embedding vector_cosine_ops)" in out
    )
    assert f"reembed.document --args '[\"{source.id}\"]'" in out
    assert "notes.embed" in out
