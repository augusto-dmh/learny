"""T16 gate — vault-export route (integration, live test DB; NL-16/20).

Exercises ``GET /api/export/vault`` end-to-end through FastAPI's ``TestClient`` against a
real Postgres:

- owner → 200 ``application/zip`` attachment ``learny-vault.zip`` that unzips to the
  expected ``Learny/`` tree, with the caller's note (body verbatim) and its highlight
  rendered both as a book callout with a ``^lh-<id>`` block and as a deep link from the
  note file (NL-16, exercising the ``anchors_for_user`` read + builder end-to-end);
- the zip contains only the caller's data — a second user's note is never present (NL-20);
- no session → 401.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.domain.entities import NoteAnchor, NoteAnchorStatus
from app.infrastructure.db.repositories import SqlAlchemyNoteRepository
from tests.conftest import TEST_ORIGIN, TEST_PASSWORD, requires_db

pytestmark = requires_db


# --- Fixtures ------------------------------------------------------------------


@pytest.fixture
def vault_client(db_conn: Connection, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """A ``TestClient`` sharing the test's rolled-back txn (notes created via the API).

    Mirrors ``notes_client``: the note-write UoW yields the shared ``db_conn`` without
    committing and the after-commit embed enqueuer is a no-op fake, so creating a note
    through ``POST /api/notes`` stays inside the one transaction the export then reads.
    """
    from app.core.config import get_settings
    from app.infrastructure.web.dependencies import (
        get_db_connection,
        get_note_index_enqueuer,
        get_note_uow,
    )
    from app.infrastructure.web.rate_limit import (
        InMemoryFixedWindowRateLimiter,
        get_rate_limiter,
        set_rate_limiter,
    )
    from app.main import create_app
    from tests.fakes import FakeNoteIndexEnqueuer

    monkeypatch.setenv("LEARNY_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("LEARNY_CSRF_TRUSTED_ORIGINS", TEST_ORIGIN)
    get_settings.cache_clear()

    previous_limiter = get_rate_limiter()
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=1000))

    app = create_app()

    def _override() -> Iterator[Connection]:
        yield db_conn

    @contextmanager
    def _shared_uow() -> Iterator[Connection]:
        yield db_conn

    app.dependency_overrides[get_db_connection] = _override
    app.dependency_overrides[get_note_uow] = lambda: _shared_uow
    app.dependency_overrides[get_note_index_enqueuer] = lambda: FakeNoteIndexEnqueuer()
    with TestClient(app, headers={"Origin": TEST_ORIGIN}) as c:
        yield c
    app.dependency_overrides.clear()
    set_rate_limiter(previous_limiter)
    get_settings.cache_clear()


# --- Helpers -------------------------------------------------------------------


def _register(client: TestClient, email: str) -> str:
    resp = client.post(
        "/api/auth/register", json={"email": email, "password": TEST_PASSWORD}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _csrf(client: TestClient) -> str:
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200, resp.text
    return resp.json()["csrf_token"]


def _create_note(client: TestClient, *, title: str, body: str = "") -> str:
    resp = client.post(
        "/api/notes",
        json={"title": title, "body_markdown": body, "tags": []},
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _seed_anchor(
    db_conn: Connection,
    *,
    note_id: str,
    source_title: str,
    quote_exact: str,
) -> NoteAnchor:
    now = datetime.now(UTC)
    anchor = NoteAnchor(
        id=uuid4(),
        note_id=UUID(note_id),
        source_id=uuid4(),
        source_title=source_title,
        anchor="ch1",
        section_path=("Chapter 1", "Intro"),
        block_hash="h" * 64,
        block_ordinal=1,
        start_offset=0,
        end_offset=None,
        quote_exact=quote_exact,
        quote_prefix="",
        quote_suffix="",
        status=NoteAnchorStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    return SqlAlchemyNoteRepository(db_conn).add_anchor(anchor)


def _entries(data: bytes) -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {
            info.filename: archive.read(info.filename).decode("utf-8")
            for info in archive.infolist()
            if not info.is_dir()
        }


# --- Tests ---------------------------------------------------------------------


def test_export_returns_the_callers_vault_zip(
    vault_client: TestClient, db_conn: Connection
) -> None:
    _register(vault_client, "vault-owner@example.com")
    note_id = _create_note(
        vault_client, title="Cited", body="See [[Other]] — a thought.\n"
    )
    anchor = _seed_anchor(
        db_conn, note_id=note_id, source_title="The Book", quote_exact="a passage"
    )

    resp = vault_client.get("/api/export/vault")

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/zip"
    assert resp.headers["content-disposition"] == 'attachment; filename="learny-vault.zip"'
    entries = _entries(resp.content)
    note_file = entries["Learny/Notes/Cited.md"]
    assert "See [[Other]] — a thought.\n" in note_file
    assert f"[[The Book#^lh-{anchor.id}]]" in note_file
    book_file = entries["Learny/Books/The Book.md"]
    assert "> [!quote] Chapter 1 › Intro" in book_file
    assert f"^lh-{anchor.id}" in book_file
    assert "> a passage" in book_file


def test_export_contains_only_the_callers_data(
    vault_client: TestClient, db_conn: Connection
) -> None:
    _register(vault_client, "vault-a@example.com")
    _create_note(vault_client, title="AlphaSecret", body="mine alone")

    _register(vault_client, "vault-b@example.com")  # become a different user
    _create_note(vault_client, title="BetaOwn", body="b's note")

    entries = _entries(vault_client.get("/api/export/vault").content)

    assert "Learny/Notes/BetaOwn.md" in entries
    assert "Learny/Notes/AlphaSecret.md" not in entries
    assert all("AlphaSecret" not in text for text in entries.values())


def test_export_empty_vault_is_a_valid_skeleton_zip(
    vault_client: TestClient, db_conn: Connection
) -> None:
    _register(vault_client, "vault-empty@example.com")

    resp = vault_client.get("/api/export/vault")

    assert resp.status_code == 200, resp.text
    with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
        assert archive.testzip() is None
        assert "Learny/Notes/" in set(archive.namelist())


def test_export_unauthenticated_returns_401(
    vault_client: TestClient, db_conn: Connection
) -> None:
    vault_client.cookies.clear()
    assert vault_client.get("/api/export/vault").status_code == 401
