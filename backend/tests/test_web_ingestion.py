"""T6 gate — /api/sources/{id}/ingestion router (integration, live test DB).

Exercises every route through FastAPI's ``TestClient`` against a real Postgres:
the start happy path (202 + queued job + source ``processing`` + one enqueue),
the duplicate-active 409, non-owner/missing 404, the enqueue-failure 502 (job
compensated to terminal ``failed`` with no active job left), restart after a
terminal job, and the auth/CSRF/Origin rejects; plus the read path (200 with
ordered events and no secret fields, 404 for no-job and non-owner/missing).

Writes land in the shared transactional connection (rolled back per test). The
``ingestion_client`` fixture overrides the start-path UoW factory to share that
connection without committing and installs a recording fake enqueuer.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, func, select
from sqlalchemy.exc import IntegrityError

from app.application.identity import AuthorizeOwnership
from app.application.ingestion import RunIngestion, StartIngestion
from app.domain.entities import IngestionStatus
from app.infrastructure.db.metadata import ingestion_jobs, sources
from app.infrastructure.db.repositories import (
    SqlAlchemyIngestionEventRepository,
    SqlAlchemyIngestionJobRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyUserRepository,
)
from app.infrastructure.web.dependencies import get_ingestion_enqueuer
from app.infrastructure.worker.steps import NoOpIngestionStep
from tests.conftest import TEST_PASSWORD, requires_db
from tests.fakes import FakeClock, FakeIngestionEnqueuer

pytestmark = requires_db

EPUB_BYTES = b"PK\x03\x04-fake-but-nonempty-epub-payload"
EPUB_TYPE = "application/epub+zip"


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


def _create_source(client: TestClient, csrf: str, *, title: str = "My Book") -> str:
    resp = client.post(
        "/api/sources",
        data={"title": title},
        files={"file": ("book.epub", EPUB_BYTES, EPUB_TYPE)},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _start(client: TestClient, source_id: str, *, csrf: str | None, origin: str | None = None):
    headers: dict[str, str] = {}
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    if origin is not None:
        headers["Origin"] = origin
    return client.post(f"/api/sources/{source_id}/ingestion", headers=headers)


def _job_count(conn: Connection, source_id: str) -> int:
    return conn.execute(
        select(func.count())
        .select_from(ingestion_jobs)
        .where(ingestion_jobs.c.source_id == UUID(source_id))
    ).scalar_one()


def _source_status(conn: Connection, source_id: str) -> str:
    return conn.execute(
        select(sources.c.status).where(sources.c.id == UUID(source_id))
    ).scalar_one()


# --- Start (P1 Start / Concurrency / Restart / Enqueue-failure) ----------------


def test_start_returns_202_queues_job_and_enqueues_once(
    ingestion_client: TestClient, db_conn: Connection
) -> None:
    _register(ingestion_client, "start@example.com")
    csrf = _csrf(ingestion_client)
    source_id = _create_source(ingestion_client, csrf)

    resp = _start(ingestion_client, source_id, csrf=csrf)

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == IngestionStatus.QUEUED
    assert body["attempts"] == 0
    assert body["error"] is None
    assert [e["type"] for e in body["events"]] == ["queued"]

    # Durable state: exactly one queued job + source projected to ``processing``.
    assert _job_count(db_conn, source_id) == 1
    row = db_conn.execute(
        select(ingestion_jobs).where(ingestion_jobs.c.id == UUID(body["id"]))
    ).one()
    assert row.status == IngestionStatus.QUEUED
    assert _source_status(db_conn, source_id) == "processing"

    # Exactly one enqueue, carrying the source + job ids and the EPUB content type
    # the adapter routes on (the real queue message still carries only ids).
    calls = ingestion_client.app.state.ingestion_enqueuer.calls
    assert calls == [(UUID(source_id), UUID(body["id"]), EPUB_TYPE)]


def test_duplicate_active_start_returns_409_and_no_second_job(
    ingestion_client: TestClient, db_conn: Connection
) -> None:
    _register(ingestion_client, "dup@example.com")
    csrf = _csrf(ingestion_client)
    source_id = _create_source(ingestion_client, csrf)

    assert _start(ingestion_client, source_id, csrf=csrf).status_code == 202
    resp = _start(ingestion_client, source_id, csrf=csrf)

    assert resp.status_code == 409, resp.text
    assert _job_count(db_conn, source_id) == 1  # no second job created
    # Only the first enqueue happened; the duplicate did not enqueue.
    assert len(ingestion_client.app.state.ingestion_enqueuer.calls) == 1


def test_start_true_race_integrity_error_returns_409(
    ingestion_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ING-03 persistence-layer guard: two starts both pass the application
    # pre-check and the loser's INSERT hits the partial unique index. The handler
    # maps that ``IntegrityError`` to 409 (not a raw 500). Force the create to raise
    # the way a true-race INSERT would, so the web-layer backstop is pinned by a
    # committed test (the duplicate-active test above trips the pre-check first).
    _register(ingestion_client, "race@example.com")
    csrf = _csrf(ingestion_client)
    source_id = _create_source(ingestion_client, csrf)

    def _raising_start(_conn):  # noqa: ANN202 — mirrors build_start_ingestion(conn)
        def _call(**_kwargs):  # noqa: ANN202 — mirrors StartIngestion.__call__
            raise IntegrityError("INSERT", {}, Exception("duplicate active job"))

        return _call

    monkeypatch.setattr(
        "app.infrastructure.web.ingestion.build_start_ingestion", _raising_start
    )

    resp = _start(ingestion_client, source_id, csrf=csrf)

    assert resp.status_code == 409, resp.text
    # The compensation/enqueue paths were never reached — nothing was enqueued.
    assert ingestion_client.app.state.ingestion_enqueuer.calls == []


def test_start_non_owner_source_returns_404(
    ingestion_client: TestClient, db_conn: Connection
) -> None:
    _register(ingestion_client, "owner@example.com")
    csrf = _csrf(ingestion_client)
    source_id = _create_source(ingestion_client, csrf)

    _register(ingestion_client, "intruder@example.com")  # become a different user
    resp = _start(ingestion_client, source_id, csrf=_csrf(ingestion_client))

    assert resp.status_code == 404, resp.text  # no existence disclosure
    assert _job_count(db_conn, source_id) == 0
    assert ingestion_client.app.state.ingestion_enqueuer.calls == []


def test_start_missing_source_returns_404(ingestion_client: TestClient) -> None:
    _register(ingestion_client, "nosrc@example.com")
    resp = _start(ingestion_client, str(uuid4()), csrf=_csrf(ingestion_client))
    assert resp.status_code == 404, resp.text
    assert ingestion_client.app.state.ingestion_enqueuer.calls == []


def test_start_enqueue_failure_returns_502_and_compensates(
    ingestion_client: TestClient, db_conn: Connection
) -> None:
    _register(ingestion_client, "broker@example.com")
    csrf = _csrf(ingestion_client)
    source_id = _create_source(ingestion_client, csrf)

    # A broker that raises on enqueue → 502; the just-created job is compensated
    # to terminal ``failed`` and no active job may remain (ING-11).
    ingestion_client.app.dependency_overrides[get_ingestion_enqueuer] = (
        lambda: FakeIngestionEnqueuer(error=RuntimeError("broker down"))
    )

    resp = _start(ingestion_client, source_id, csrf=csrf)

    assert resp.status_code == 502, resp.text
    assert _job_count(db_conn, source_id) == 1
    row = db_conn.execute(
        select(ingestion_jobs).where(ingestion_jobs.c.source_id == UUID(source_id))
    ).one()
    assert row.status == IngestionStatus.FAILED
    assert row.last_error is not None  # durable failure reason persisted
    assert _source_status(db_conn, source_id) == "failed"

    # No active job remains → a restart is not blocked.
    latest = SqlAlchemyIngestionJobRepository(db_conn).get_latest_for_source(
        UUID(source_id)
    )
    assert latest is not None and latest.status == IngestionStatus.FAILED

    # A ``failed`` event is durable and readable.
    events = SqlAlchemyIngestionEventRepository(db_conn).list_for_job(row.id)
    assert [e.type for e in events] == ["queued", "failed"]


def test_restart_after_terminal_job_returns_202_new_job(
    ingestion_client: TestClient, db_conn: Connection
) -> None:
    _register(ingestion_client, "restart@example.com")
    csrf = _csrf(ingestion_client)
    source_id = _create_source(ingestion_client, csrf)

    first = _start(ingestion_client, source_id, csrf=csrf)
    assert first.status_code == 202
    first_id = first.json()["id"]

    # Drive the first job to a terminal (failed) state, freeing the source.
    jobs = SqlAlchemyIngestionJobRepository(db_conn)
    job = jobs.get_by_id(UUID(first_id))
    jobs.update(job.failed(job.updated_at + timedelta(seconds=1), "boom"))

    second = _start(ingestion_client, source_id, csrf=csrf)

    assert second.status_code == 202, second.text
    assert second.json()["id"] != first_id  # a new job
    assert second.json()["status"] == IngestionStatus.QUEUED
    assert _job_count(db_conn, source_id) == 2


def test_start_unauthenticated_returns_401(
    ingestion_client: TestClient, db_conn: Connection
) -> None:
    _register(ingestion_client, "unauth@example.com")
    csrf = _csrf(ingestion_client)
    source_id = _create_source(ingestion_client, csrf)

    ingestion_client.cookies.clear()
    resp = _start(ingestion_client, source_id, csrf="whatever")

    assert resp.status_code == 401, resp.text
    assert _job_count(db_conn, source_id) == 0


def test_start_missing_csrf_returns_403(
    ingestion_client: TestClient, db_conn: Connection
) -> None:
    _register(ingestion_client, "nocsrf@example.com")
    source_id = _create_source(ingestion_client, _csrf(ingestion_client))

    resp = _start(ingestion_client, source_id, csrf=None)

    assert resp.status_code == 403, resp.text
    assert _job_count(db_conn, source_id) == 0


def test_start_invalid_csrf_returns_403(
    ingestion_client: TestClient, db_conn: Connection
) -> None:
    _register(ingestion_client, "badcsrf@example.com")
    source_id = _create_source(ingestion_client, _csrf(ingestion_client))

    resp = _start(ingestion_client, source_id, csrf="not-the-session-token")

    assert resp.status_code == 403, resp.text
    assert _job_count(db_conn, source_id) == 0


def test_start_untrusted_origin_returns_403(
    ingestion_client: TestClient, db_conn: Connection
) -> None:
    _register(ingestion_client, "origin@example.com")
    csrf = _csrf(ingestion_client)
    source_id = _create_source(ingestion_client, csrf)

    resp = _start(
        ingestion_client, source_id, csrf=csrf, origin="http://evil.example.com"
    )

    assert resp.status_code == 403, resp.text
    assert _job_count(db_conn, source_id) == 0


# --- Read (P1 Observe) ---------------------------------------------------------


def _drive_to_succeeded(conn: Connection, user, source_id: str) -> None:
    """Drive queued→running→succeeded via the real services on ``conn``.

    Uses one advancing :class:`FakeClock` so the three lifecycle events get
    strictly increasing timestamps (the events table orders by ``created_at``),
    making the chronological-order assertion deterministic.
    """
    clock = FakeClock()
    common = {
        "sources": SqlAlchemySourceRepository(conn),
        "jobs": SqlAlchemyIngestionJobRepository(conn),
        "events": SqlAlchemyIngestionEventRepository(conn),
    }
    start = StartIngestion(
        **common, authorize=AuthorizeOwnership(), clock=clock, ids=uuid4
    )
    job, _, _ = start(user=user, source_id=UUID(source_id))
    run = RunIngestion(**common, step=NoOpIngestionStep(), clock=clock, ids=uuid4)
    clock.advance(timedelta(seconds=1))
    run.begin_run(job.id)
    clock.advance(timedelta(seconds=1))
    run.complete(job.id)


def test_read_returns_200_with_ordered_events_and_no_secrets(
    ingestion_client: TestClient, db_conn: Connection
) -> None:
    _register(ingestion_client, "reader@example.com")
    csrf = _csrf(ingestion_client)
    source_id = _create_source(ingestion_client, csrf)

    user = SqlAlchemyUserRepository(db_conn).get_by_email("reader@example.com")
    _drive_to_succeeded(db_conn, user, source_id)

    resp = ingestion_client.get(f"/api/sources/{source_id}/ingestion")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == IngestionStatus.SUCCEEDED
    assert body["attempts"] == 1
    assert body["error"] is None
    assert [e["type"] for e in body["events"]] == ["queued", "started", "succeeded"]
    # Secret-free: no internal storage/integrity fields leak (P1-Observe AC4).
    assert "object_key" not in body and "checksum" not in body


def test_read_no_job_returns_404(ingestion_client: TestClient) -> None:
    _register(ingestion_client, "nojob@example.com")
    csrf = _csrf(ingestion_client)
    source_id = _create_source(ingestion_client, csrf)

    resp = ingestion_client.get(f"/api/sources/{source_id}/ingestion")
    assert resp.status_code == 404, resp.text


def test_read_non_owner_source_returns_404(
    ingestion_client: TestClient,
) -> None:
    _register(ingestion_client, "a@example.com")
    csrf = _csrf(ingestion_client)
    source_id = _create_source(ingestion_client, csrf)
    assert _start(ingestion_client, source_id, csrf=csrf).status_code == 202

    _register(ingestion_client, "b@example.com")  # become another user
    resp = ingestion_client.get(f"/api/sources/{source_id}/ingestion")
    assert resp.status_code == 404, resp.text  # no existence disclosure


def test_read_missing_source_returns_404(ingestion_client: TestClient) -> None:
    _register(ingestion_client, "gone@example.com")
    resp = ingestion_client.get(f"/api/sources/{uuid4()}/ingestion")
    assert resp.status_code == 404, resp.text
