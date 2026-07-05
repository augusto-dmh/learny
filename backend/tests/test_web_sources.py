"""T6 gate — /api/sources router (integration, live test DB + MinIO).

Exercises every route through FastAPI's ``TestClient`` against a real Postgres
and a real S3-compatible store: the happy upload (row + object persisted), each
validation/auth/CSRF reject (which must persist nothing), owner-scoped list, and
per-source ownership enforcement (cross-user → 404). Uploads land in the shared
transactional connection (rolled back per test); stored objects are opaque and
left in MinIO (accepted orphan behaviour, SRC-09).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import Connection, select

from app.infrastructure.db.metadata import sources
from app.infrastructure.web.dependencies import _storage, get_storage
from tests.conftest import (
    SOURCES_MAX_BYTES,
    TEST_PASSWORD,
    requires_db,
)
from tests.fakes import FailingStorage

pytestmark = requires_db

EPUB_BYTES = b"PK\x03\x04-fake-but-nonempty-epub-payload"
EPUB_TYPE = "application/epub+zip"


class _RecordingHandler(logging.Handler):
    """Collects emitted ``LogRecord``s for assertion (no formatting)."""

    def __init__(self) -> None:
        super().__init__(level=logging.NOTSET)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@contextmanager
def _capture_source_logs(level: int):
    """Capture records off the sources logger, forcing it enabled at ``level``.

    Another test in the suite runs a ``dictConfig``/``fileConfig`` whose default
    ``disable_existing_loggers=True`` leaves this module logger ``disabled`` (a
    test-suite artifact — production never disables it), which would otherwise
    swallow the record regardless of any handler.
    """
    records = _RecordingHandler()
    logger = logging.getLogger("app.infrastructure.web.sources")
    previous_level, previous_disabled = logger.level, logger.disabled
    logger.setLevel(level)
    logger.disabled = False
    logger.addHandler(records)
    try:
        yield records
    finally:
        logger.removeHandler(records)
        logger.setLevel(previous_level)
        logger.disabled = previous_disabled


def _register(client: TestClient, email: str) -> str:
    resp = client.post(
        "/api/auth/register", json={"email": email, "password": TEST_PASSWORD}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _login(client: TestClient, email: str) -> None:
    client.cookies.clear()
    resp = client.post(
        "/api/auth/login", json={"email": email, "password": TEST_PASSWORD}
    )
    assert resp.status_code == 200, resp.text


def _csrf(client: TestClient) -> str:
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200, resp.text
    return resp.json()["csrf_token"]


def _upload(
    client: TestClient,
    *,
    csrf: str | None,
    filename: str = "book.epub",
    content_type: str = EPUB_TYPE,
    title: str = "My Book",
    data: bytes = EPUB_BYTES,
    include_file: bool = True,
    origin: str | None = None,
):
    headers: dict[str, str] = {}
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    if origin is not None:
        headers["Origin"] = origin
    kwargs = {"data": {"title": title}, "headers": headers}
    if include_file:
        kwargs["files"] = {"file": (filename, data, content_type)}
    return client.post("/api/sources", **kwargs)


def _source_rows(conn: Connection) -> list:
    return conn.execute(select(sources)).all()


# --- Upload (P1 Upload) --------------------------------------------------------


def test_upload_valid_epub_persists_row_and_object(
    sources_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(sources_client, "up@example.com")
    resp = _upload(sources_client, csrf=_csrf(sources_client), title="Moby Dick")

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == "Moby Dick"
    assert body["filename"] == "book.epub"
    assert body["byte_size"] == len(EPUB_BYTES)
    assert body["content_type"] == EPUB_TYPE
    assert body["status"] == "uploaded"
    assert "id" in body and "created_at" in body
    # Secret-free summary: no internal storage/integrity fields leak (AC1).
    assert "object_key" not in body and "checksum" not in body

    row = db_conn.execute(
        select(sources).where(sources.c.id == body["id"])
    ).one()
    assert str(row.user_id) == user_id
    assert row.status == "uploaded"
    assert row.checksum  # sha256 hex persisted
    # Opaque, owner-partitioned key with no email/title (AC7).
    assert row.object_key == f"sources/{user_id}/{body['id']}.epub"
    assert "up@example.com" not in row.object_key
    assert "Moby Dick" not in row.object_key

    # Bytes actually landed in object storage under that key.
    assert _storage.get_object(row.object_key) == EPUB_BYTES


def test_upload_non_epub_extension_returns_415(
    sources_client: TestClient, db_conn: Connection
) -> None:
    _register(sources_client, "txt@example.com")
    resp = _upload(
        sources_client,
        csrf=_csrf(sources_client),
        filename="notes.txt",
        content_type="text/plain",
    )
    assert resp.status_code == 415, resp.text
    assert _source_rows(db_conn) == []


def test_upload_wrong_content_type_returns_415(
    sources_client: TestClient, db_conn: Connection
) -> None:
    _register(sources_client, "ct@example.com")
    resp = _upload(
        sources_client,
        csrf=_csrf(sources_client),
        filename="book.epub",
        content_type="text/plain",
    )
    assert resp.status_code == 415, resp.text
    assert _source_rows(db_conn) == []


def test_upload_oversize_returns_413(
    sources_client: TestClient, db_conn: Connection
) -> None:
    _register(sources_client, "big@example.com")
    resp = _upload(
        sources_client,
        csrf=_csrf(sources_client),
        data=b"x" * (SOURCES_MAX_BYTES + 1),
    )
    assert resp.status_code == 413, resp.text
    assert _source_rows(db_conn) == []


def test_upload_empty_title_returns_422(
    sources_client: TestClient, db_conn: Connection
) -> None:
    _register(sources_client, "notitle@example.com")
    resp = _upload(sources_client, csrf=_csrf(sources_client), title="   ")
    assert resp.status_code == 422, resp.text
    assert _source_rows(db_conn) == []


def test_upload_zero_byte_file_returns_422(
    sources_client: TestClient, db_conn: Connection
) -> None:
    _register(sources_client, "empty@example.com")
    resp = _upload(sources_client, csrf=_csrf(sources_client), data=b"")
    assert resp.status_code == 422, resp.text
    assert _source_rows(db_conn) == []


def test_upload_no_file_part_returns_422(
    sources_client: TestClient, db_conn: Connection
) -> None:
    _register(sources_client, "nofile@example.com")
    resp = _upload(sources_client, csrf=_csrf(sources_client), include_file=False)
    assert resp.status_code == 422, resp.text
    assert _source_rows(db_conn) == []


def test_upload_unauthenticated_returns_401(
    sources_client: TestClient, db_conn: Connection
) -> None:
    # A valid multipart body, but no session cookie → 401 (nothing persisted).
    sources_client.cookies.clear()
    resp = _upload(sources_client, csrf="whatever")
    assert resp.status_code == 401, resp.text
    assert _source_rows(db_conn) == []


def test_upload_missing_csrf_returns_403(
    sources_client: TestClient, db_conn: Connection
) -> None:
    _register(sources_client, "nocsrf@example.com")
    resp = _upload(sources_client, csrf=None)
    assert resp.status_code == 403, resp.text
    assert _source_rows(db_conn) == []


def test_upload_invalid_csrf_returns_403(
    sources_client: TestClient, db_conn: Connection
) -> None:
    _register(sources_client, "badcsrf@example.com")
    _csrf(sources_client)  # a real token exists, but we send a wrong one
    resp = _upload(sources_client, csrf="not-the-session-token")
    assert resp.status_code == 403, resp.text
    assert _source_rows(db_conn) == []


def test_upload_untrusted_origin_returns_403(
    sources_client: TestClient, db_conn: Connection
) -> None:
    _register(sources_client, "origin@example.com")
    csrf = _csrf(sources_client)
    resp = _upload(sources_client, csrf=csrf, origin="http://evil.example.com")
    assert resp.status_code == 403, resp.text
    assert _source_rows(db_conn) == []


def test_upload_storage_unavailable_returns_503_and_logs(
    sources_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(sources_client, "down@example.com")
    csrf = _csrf(sources_client)
    sources_client.app.dependency_overrides[get_storage] = lambda: FailingStorage()

    with _capture_source_logs(logging.WARNING) as records:
        resp = _upload(sources_client, csrf=csrf)

    assert resp.status_code == 503, resp.text
    assert _source_rows(db_conn) == []
    failures = [r for r in records.records if getattr(r, "user_id", None) == user_id]
    assert failures, "expected a storage-failure log carrying the user id"
    # No secrets in the log line (no object key or checksum material).
    logged = failures[0].getMessage()
    assert "sources/" not in logged and "checksum" not in logged


def test_upload_logs_source_created_with_ids(sources_client: TestClient) -> None:
    user_id = _register(sources_client, "logged@example.com")
    csrf = _csrf(sources_client)

    with _capture_source_logs(logging.INFO) as records:
        resp = _upload(sources_client, csrf=csrf, title="Logged Book")

    assert resp.status_code == 201, resp.text
    source_id = resp.json()["id"]
    created = [
        r
        for r in records.records
        if getattr(r, "user_id", None) == user_id
        and getattr(r, "source_id", None) == source_id
    ]
    assert created, "expected a source-created log carrying user_id + source_id"
    # SRC-10: the lifecycle log carries ids only, never storage/integrity secrets.
    logged = created[0].getMessage()
    assert "sources/" not in logged and "checksum" not in logged


def test_same_file_uploaded_twice_creates_two_sources(
    sources_client: TestClient, db_conn: Connection
) -> None:
    _register(sources_client, "twice@example.com")
    csrf = _csrf(sources_client)
    first = _upload(sources_client, csrf=csrf, title="Copy A")
    second = _upload(sources_client, csrf=csrf, title="Copy B")

    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    keys = {row.object_key for row in _source_rows(db_conn)}
    assert len(keys) == 2  # distinct object keys, no dedup


# --- List (P1 List) ------------------------------------------------------------


def test_list_returns_owner_sources_newest_first(sources_client: TestClient) -> None:
    _register(sources_client, "owner@example.com")
    csrf_a = _csrf(sources_client)
    _upload(sources_client, csrf=csrf_a, title="First")
    _upload(sources_client, csrf=csrf_a, title="Second")

    # A different user's source must not appear in A's list.
    _register(sources_client, "other@example.com")
    _upload(sources_client, csrf=_csrf(sources_client), title="Not Mine")

    _login(sources_client, "owner@example.com")
    resp = sources_client.get("/api/sources")
    assert resp.status_code == 200, resp.text
    titles = [s["title"] for s in resp.json()]
    assert titles == ["Second", "First"]  # owner-scoped, newest-first


def test_list_empty_returns_empty_array(sources_client: TestClient) -> None:
    _register(sources_client, "fresh@example.com")
    resp = sources_client.get("/api/sources")
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


def test_list_unauthenticated_returns_401(sources_client: TestClient) -> None:
    sources_client.cookies.clear()
    assert sources_client.get("/api/sources").status_code == 401


# --- View (P1 View) ------------------------------------------------------------


def test_get_own_source_returns_200(sources_client: TestClient) -> None:
    _register(sources_client, "viewer@example.com")
    created = _upload(sources_client, csrf=_csrf(sources_client), title="Readable")
    source_id = created.json()["id"]

    resp = sources_client.get(f"/api/sources/{source_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == source_id and body["title"] == "Readable"
    assert "object_key" not in body and "checksum" not in body


def test_get_cross_user_source_returns_404(sources_client: TestClient) -> None:
    _register(sources_client, "a@example.com")
    created = _upload(sources_client, csrf=_csrf(sources_client))
    source_id = created.json()["id"]

    _login(sources_client, "a@example.com")  # refresh A's own session first
    _register(sources_client, "b@example.com")  # now become B
    resp = sources_client.get(f"/api/sources/{source_id}")
    assert resp.status_code == 404, resp.text  # no existence disclosure


def test_get_missing_source_returns_404(sources_client: TestClient) -> None:
    _register(sources_client, "missing@example.com")
    resp = sources_client.get(f"/api/sources/{uuid4()}")
    assert resp.status_code == 404, resp.text


def test_get_malformed_uuid_returns_422(sources_client: TestClient) -> None:
    _register(sources_client, "bad@example.com")
    resp = sources_client.get("/api/sources/not-a-uuid")
    assert resp.status_code == 422, resp.text


def test_get_unauthenticated_returns_401(sources_client: TestClient) -> None:
    sources_client.cookies.clear()
    assert sources_client.get(f"/api/sources/{uuid4()}").status_code == 401
