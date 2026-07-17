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
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, select

from app.application.sources import CreateSource
from app.infrastructure.db.metadata import sources
from app.infrastructure.db.repositories import SqlAlchemySourceRepository
from app.infrastructure.web.dependencies import (
    AppSettings,
    DbConnection,
    Storage,
    _clock,
    _storage,
    get_create_source,
    get_storage,
)
from tests.conftest import (
    SOURCES_MAX_BYTES,
    TEST_ORIGIN,
    TEST_PASSWORD,
    requires_db,
)
from tests.fakes import FailingStorage

pytestmark = requires_db

EPUB_BYTES = b"PK\x03\x04-fake-but-nonempty-epub-payload"
EPUB_TYPE = "application/epub+zip"
PDF_BYTES = b"%PDF-1.7-fake-but-nonempty-pdf-payload"
PDF_TYPE = "application/pdf"

# Distinct, tiny caps (pdf > epub) for the read-bound test below. The absolute
# sizes are irrelevant; only the ordering matters, so payloads stay minuscule.
PDF_CAP_EPUB_MAX = 2048
PDF_CAP_PDF_MAX = 8192


@pytest.fixture
def pdf_caps_client(db_conn: Connection, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """A sources ``TestClient`` with distinct EPUB/PDF caps (``pdf > epub``).

    Mirrors :func:`sources_client` but overrides both size caps so the handler's
    ``max(epub_max_bytes, pdf_max_bytes) + 1`` read bound is exercised at the HTTP
    boundary: a PDF sized between the caps must be read whole (not truncated to the
    smaller EPUB cap) and stored intact, while one past the PDF cap is rejected 413.
    """
    from app.core.config import get_settings
    from app.infrastructure.web.dependencies import get_db_connection
    from app.infrastructure.web.rate_limit import (
        InMemoryFixedWindowRateLimiter,
        get_rate_limiter,
        set_rate_limiter,
    )
    from app.main import create_app

    monkeypatch.setenv("LEARNY_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("LEARNY_CSRF_TRUSTED_ORIGINS", TEST_ORIGIN)
    monkeypatch.setenv("LEARNY_EPUB_MAX_BYTES", str(PDF_CAP_EPUB_MAX))
    monkeypatch.setenv("LEARNY_PDF_MAX_BYTES", str(PDF_CAP_PDF_MAX))
    get_settings.cache_clear()

    previous_limiter = get_rate_limiter()
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=1000))

    app = create_app()

    def _override() -> Iterator[Connection]:
        yield db_conn

    app.dependency_overrides[get_db_connection] = _override
    with TestClient(app, headers={"Origin": TEST_ORIGIN}) as c:
        yield c
    app.dependency_overrides.clear()
    set_rate_limiter(previous_limiter)
    get_settings.cache_clear()


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


def test_upload_valid_pdf_persists_row_and_object(
    sources_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(sources_client, "pdf@example.com")
    resp = _upload(
        sources_client,
        csrf=_csrf(sources_client),
        filename="report.pdf",
        content_type=PDF_TYPE,
        title="Annual Report",
        data=PDF_BYTES,
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["filename"] == "report.pdf"
    assert body["content_type"] == PDF_TYPE
    assert body["status"] == "uploaded"

    row = db_conn.execute(
        select(sources).where(sources.c.id == body["id"])
    ).one()
    # The object key carries the .pdf extension (parser dispatch depends on it).
    assert row.object_key == f"sources/{user_id}/{body['id']}.pdf"
    assert _storage.get_object(row.object_key) == PDF_BYTES


def test_upload_pdf_between_caps_persists_untruncated(
    pdf_caps_client: TestClient, db_conn: Connection
) -> None:
    # Read-bound guard: with pdf_max_bytes > epub_max_bytes, a PDF sized strictly
    # between the two caps must be read in full (the handler reads max(epub, pdf)+1,
    # not epub+1) so validation sees its true size and stores every byte. A revert
    # to an epub-only read bound would truncate this payload to epub_max+1, that
    # smaller size would still pass the PDF cap, and a corrupt object would land.
    user_id = _register(pdf_caps_client, "between@example.com")
    payload = PDF_BYTES + b"x" * (PDF_CAP_EPUB_MAX + 1 - len(PDF_BYTES))
    assert PDF_CAP_EPUB_MAX < len(payload) < PDF_CAP_PDF_MAX

    resp = _upload(
        pdf_caps_client,
        csrf=_csrf(pdf_caps_client),
        filename="report.pdf",
        content_type=PDF_TYPE,
        title="Big Report",
        data=payload,
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["byte_size"] == len(payload)

    row = db_conn.execute(select(sources).where(sources.c.id == body["id"])).one()
    assert row.object_key == f"sources/{user_id}/{body['id']}.pdf"
    # The full, untruncated payload reached storage — byte-for-byte identical.
    assert _storage.get_object(row.object_key) == payload


def test_upload_pdf_over_pdf_cap_returns_413(
    pdf_caps_client: TestClient, db_conn: Connection
) -> None:
    # The upper edge of the same read bound: a PDF larger than pdf_max_bytes is
    # detected as oversize and rejected, persisting nothing.
    _register(pdf_caps_client, "toobig@example.com")
    payload = PDF_BYTES + b"x" * (PDF_CAP_PDF_MAX + 1 - len(PDF_BYTES))
    assert len(payload) > PDF_CAP_PDF_MAX

    resp = _upload(
        pdf_caps_client,
        csrf=_csrf(pdf_caps_client),
        filename="report.pdf",
        content_type=PDF_TYPE,
        data=payload,
    )
    assert resp.status_code == 413, resp.text
    assert _source_rows(db_conn) == []


def test_upload_pdf_extension_with_epub_content_type_returns_415(
    sources_client: TestClient, db_conn: Connection
) -> None:
    # Spec edge case: a .pdf file declared as application/epub+zip is a mismatch.
    _register(sources_client, "pdfmismatch@example.com")
    resp = _upload(
        sources_client,
        csrf=_csrf(sources_client),
        filename="report.pdf",
        content_type=EPUB_TYPE,
        data=PDF_BYTES,
    )
    assert resp.status_code == 415, resp.text
    assert _source_rows(db_conn) == []


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


class _AddFailsRepository:
    """Real repo for reads, but ``add`` always fails (simulates the INSERT
    step failing after the object was already stored)."""

    def __init__(self, inner: SqlAlchemySourceRepository) -> None:
        self._inner = inner

    def add(self, source):
        raise RuntimeError("insert failed")

    def list_by_user(self, user_id):
        return self._inner.list_by_user(user_id)

    def get_by_id(self, source_id):
        return self._inner.get_by_id(source_id)


def test_upload_insert_failure_after_store_returns_5xx_and_persists_nothing(
    sources_client: TestClient, db_conn: Connection
) -> None:
    # SRC-09 edge case: bytes already landed in storage, but the row INSERT
    # fails — the response must be a server error and no row may be committed.
    user_id = _register(sources_client, "insertfail@example.com")
    csrf = _csrf(sources_client)
    fixed_id = uuid4()

    def _create_source_with_failing_insert(
        conn: DbConnection, storage: Storage, settings: AppSettings
    ) -> CreateSource:
        return CreateSource(
            sources=_AddFailsRepository(SqlAlchemySourceRepository(conn)),
            storage=storage,
            clock=_clock,
            ids=lambda: fixed_id,
            max_bytes=settings.epub_max_bytes,
        )

    sources_client.app.dependency_overrides[get_create_source] = (
        _create_source_with_failing_insert
    )
    lenient_client = TestClient(
        sources_client.app,
        cookies=sources_client.cookies,
        headers={"Origin": TEST_ORIGIN},
        raise_server_exceptions=False,
    )

    resp = _upload(lenient_client, csrf=csrf)

    assert resp.status_code >= 500, resp.text
    assert _source_rows(db_conn) == []
    # The bytes reached storage even though the row never committed.
    assert _storage.get_object(f"sources/{user_id}/{fixed_id}.epub") == EPUB_BYTES


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


def test_upload_repeated_hits_rate_limit_returns_429(
    throttled_sources_client: TestClient, db_conn: Connection
) -> None:
    # SRC-05 rate-limit half: the tight fixture allows 3 uploads per window, so
    # the 4th POST /api/sources trips ``rate_limit_upload`` before the handler.
    client = throttled_sources_client
    _register(client, "flood@example.com")
    csrf = _csrf(client)

    for _ in range(3):
        resp = _upload(client, csrf=csrf)
        assert resp.status_code == 201, resp.text

    throttled = _upload(client, csrf=csrf)
    assert throttled.status_code == 429, throttled.text
    assert "retry-after" in {k.lower() for k in throttled.headers}
    # The throttled request short-circuits before the service, so no extra row
    # is persisted — only the 3 that passed the limiter exist.
    assert len(_source_rows(db_conn)) == 3


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
