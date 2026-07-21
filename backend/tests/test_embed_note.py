"""Phase A gate — the embed_note worker task (integration, live DB).

Drives the ``embed_note`` task *function* directly against the migrated test engine
(no Redis, no eager mode), mirroring ``test_reembed``: the task commits through its
own engine, so each test seeds a committed user + note and the fixture deletes the
user afterwards (FK cascade → notes). The deterministic local adapter is the default,
so the expected vector is reproducible in-test.

Covers NL-01 (a note's body is embedded, model recorded), NL-06 (empty body clears
the vector), NL-07 (a deleted note is a no-op), and the concurrency invariant
(idempotent + newest-body-wins: the body is read at run time, so a stale enqueue
embeds the newest body) plus deterministic truncation of an oversized body.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy import delete as sa_delete

from app.core.config import get_settings
from app.domain.entities import Note
from app.infrastructure.db.metadata import notes, users
from app.infrastructure.db.repositories import SqlAlchemyNoteRepository
from app.infrastructure.embeddings import build_embedding_adapter
from app.worker.tasks import embed_note
from tests.conftest import requires_db

pytestmark = requires_db

# The raw (unbound) task function, driven with a stand-in ``self`` (the body ignores
# it — embed_note has no retry) and no broker.
_embed = embed_note.run.__func__


@pytest.fixture
def embed_env(db_engine: Engine, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """Point the task's engine at the test DB and return a committed-note seeder.

    The seeder commits an owner + one note and records the user for cascade cleanup;
    teardown deletes the users (their notes cascade), leaving the shared DB clean.
    """
    monkeypatch.setattr("app.worker.tasks.get_engine", lambda: db_engine)
    created_users: list[UUID] = []

    def _seed(*, body_markdown: str, title: str = "Note") -> UUID:
        user_id = uuid4()
        now = datetime.now(UTC)
        with db_engine.begin() as conn:
            conn.execute(
                text("INSERT INTO users (id, email) VALUES (:id, :email)"),
                {"id": user_id, "email": f"{user_id}@example.com"},
            )
            SqlAlchemyNoteRepository(conn).add(
                Note(
                    id=uuid4(),
                    user_id=user_id,
                    title=title,
                    body_markdown=body_markdown,
                    created_at=now,
                    updated_at=now,
                )
            )
            note_id = conn.execute(
                select(notes.c.id).where(notes.c.user_id == user_id)
            ).scalar_one()
        created_users.append(user_id)
        return note_id

    yield _seed

    with db_engine.begin() as conn:
        for user_id in created_users:
            conn.execute(sa_delete(users).where(users.c.id == user_id))


def _set_body(engine: Engine, note_id: UUID, body_markdown: str) -> None:
    """Persist a new body directly (simulates a later save the stale task must honor)."""
    with engine.begin() as conn:
        SqlAlchemyNoteRepository(conn).update(
            note_id,
            title="Note",
            body_markdown=body_markdown,
            updated_at=datetime.now(UTC),
        )


def _row(engine: Engine, note_id: UUID):  # noqa: ANN202
    """Return the note's (embedding, embedding_model) row."""
    with engine.connect() as conn:
        return conn.execute(
            select(notes.c.embedding, notes.c.embedding_model).where(notes.c.id == note_id)
        ).one()


def _expected(text_body: str) -> list[float]:
    """The vector the task would compute for ``text_body`` (same default adapter)."""
    return build_embedding_adapter(get_settings()).embed_documents([text_body])[0]


def test_embed_note_populates_vector_and_model(embed_env, db_engine: Engine) -> None:
    # NL-01: a note with a body is embedded, and embedding_model records <model>@<dims>.
    note_id = embed_env(body_markdown="chlorophyll absorbs red and blue light")

    _embed(None, str(note_id))

    row = _row(db_engine, note_id)
    assert row.embedding is not None
    assert row.embedding_model == build_embedding_adapter(get_settings()).model
    assert list(row.embedding) == pytest.approx(
        _expected("chlorophyll absorbs red and blue light"), abs=1e-3
    )


def test_embed_note_is_idempotent(embed_env, db_engine: Engine) -> None:
    # Running twice writes the same vector + model (deterministic; safe under redelivery).
    note_id = embed_env(body_markdown="a stable distinctive fact")

    _embed(None, str(note_id))
    first = _row(db_engine, note_id)
    _embed(None, str(note_id))
    second = _row(db_engine, note_id)

    assert list(second.embedding) == pytest.approx(list(first.embedding), abs=0.0)
    assert second.embedding_model == first.embedding_model


def test_embed_note_empty_body_clears_embedding(embed_env, db_engine: Engine) -> None:
    # NL-06: emptying a note's body clears its stored vector so it leaves the semantic arm.
    note_id = embed_env(body_markdown="had content once")
    _embed(None, str(note_id))
    assert _row(db_engine, note_id).embedding is not None

    _set_body(db_engine, note_id, "")
    _embed(None, str(note_id))

    row = _row(db_engine, note_id)
    assert row.embedding is None
    assert row.embedding_model is None


def test_embed_note_newest_body_wins_on_stale_enqueue(embed_env, db_engine: Engine) -> None:
    # Concurrency invariant: the body is read at run time, so a stale enqueue that lands
    # after a newer save embeds the NEWEST body, not the one present when it was queued.
    note_id = embed_env(body_markdown="alpha alpha alpha")
    _set_body(db_engine, note_id, "zeta zeta zeta")  # a newer save before the task runs

    _embed(None, str(note_id))  # the stale enqueue finally runs

    stored = list(_row(db_engine, note_id).embedding)
    assert stored == pytest.approx(_expected("zeta zeta zeta"), abs=1e-3)
    assert stored != pytest.approx(_expected("alpha alpha alpha"), abs=1e-3)


def test_embed_note_missing_note_is_a_noop(embed_env, db_engine: Engine) -> None:
    # NL-07 interplay: a note deleted before the task runs is a no-op (no error, no write).
    missing = uuid4()

    _embed(None, str(missing))  # must not raise

    with db_engine.connect() as conn:
        count = conn.execute(
            select(notes.c.id).where(notes.c.id == missing)
        ).all()
    assert count == []  # no row was created by the no-op


def test_embed_note_truncates_oversized_body(
    embed_env, db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Deterministic truncation: a body over the provider limit is embedded from its
    # first ``notes_embedding_max_chars`` characters, not the whole (or a failure).
    small = get_settings().model_copy(update={"notes_embedding_max_chars": 10})
    monkeypatch.setattr("app.worker.tasks.get_settings", lambda: small)
    body = "aaaa bbbb cccc dddd"  # 19 chars; first 10 = "aaaa bbbb "
    note_id = embed_env(body_markdown=body)

    _embed(None, str(note_id))

    stored = list(_row(db_engine, note_id).embedding)
    assert stored == pytest.approx(_expected("aaaa bbbb "), abs=1e-3)
    assert stored != pytest.approx(_expected(body), abs=1e-3)
