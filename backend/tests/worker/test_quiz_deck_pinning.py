"""Deck-provider pinning gate (poll uses the handle's provider, never a foreign one).

Derived from the provider-pinning acceptance criteria at the task seam: the poll
task builds the quiz adapter for the provider recorded on the deck handle — even
while the settings declare a different provider — by passing ``handle.provider``
to the factory (the factory's own selection matrix is pinned in the factory
suite); a handle naming a provider the current configuration does not declare
fails the job *terminally* (no retry, no reschedule, no adapter built, nothing
polled) with an operator-actionable log naming the provider; and a deck begin
records its provider into the Celery payload so the identity survives the JSON
round-trip to the poll task. The DB-backed tests drive the task *functions*
against the migrated test engine with a controllable bound ``self`` (no broker),
mirroring ``test_worker_quiz``.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine
from sqlalchemy import delete as sa_delete

from app.domain.entities import (
    QuizDeckHandle,
    QuizDeckResult,
    QuizGenerationJob,
    QuizJobStatus,
    Source,
    User,
)
from app.infrastructure.db.metadata import users
from app.infrastructure.db.repositories import (
    SqlAlchemyQuizJobRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyUserRepository,
)
from app.worker.tasks import generate_quiz_deck, poll_quiz_deck
from tests.conftest import requires_db

_poll = poll_quiz_deck.run.__func__
_generate = generate_quiz_deck.run.__func__


class FakeSelf:
    """A controllable bound-task ``self``: request.retries, max_retries, retry()."""

    class RetrySignal(Exception):
        """Sentinel raised by :meth:`retry`, standing in for Celery's ``Retry``."""

    def __init__(self, *, retries: int = 0, max_retries: int = 3) -> None:
        self.request = SimpleNamespace(retries=retries)
        self.max_retries = max_retries
        self.retry_calls: list[dict] = []

    def retry(self, *, exc, countdown):  # noqa: ANN001, ANN202
        self.retry_calls.append({"exc": exc, "countdown": countdown})
        raise self.RetrySignal


class _RecordingFactory:
    """A fake ``build_quiz_adapter`` recording which provider was requested."""

    def __init__(self, adapter: object) -> None:
        self._adapter = adapter
        self.requested: list[str | None] = []

    def __call__(self, settings, provider: str | None = None):  # noqa: ANN001, ANN202
        self.requested.append(provider)
        return self._adapter


class _PendingAdapter:
    """``QuizGenerationPort`` double whose batch never ends (poll keeps waiting)."""

    model = "fake-quiz@1"

    def begin_deck(self, sections):  # noqa: ANN001, ANN202
        raise AssertionError("begin_deck must not be called by the poll task")

    def collect_deck(self, handle: QuizDeckHandle) -> QuizDeckResult | None:
        return None


# --- PIN-01: the poll asks the factory for the handle's provider -----------------


def test_poll_builds_the_adapter_named_by_the_handle_not_by_settings() -> None:
    # The offline suite pins the settings' provider to local; the handle names
    # anthropic. The factory must be asked for anthropic — the recorded request
    # is the sensor, and the poll proceeds on the (pending) pinned adapter.
    factory = _RecordingFactory(_PendingAdapter())
    handle = QuizDeckHandle(provider="anthropic", batch_id="batch-1", payload={}).to_payload()
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()

    with (
        patch("app.worker.tasks.build_quiz_adapter", factory),
        patch("app.worker.tasks.poll_quiz_deck.apply_async") as apply_async,
    ):
        _poll(FakeSelf(), str(uuid4()), handle, future)

    assert factory.requested == ["anthropic"]
    apply_async.assert_called_once()


def test_poll_passes_the_handle_provider_rather_than_no_override() -> None:
    # The mirror case: the handle names local, so the factory must receive the
    # string "local" — not ``None``, which would silently fall back to whatever
    # the settings currently declare.
    factory = _RecordingFactory(_PendingAdapter())
    handle = QuizDeckHandle(provider="local", batch_id=None, payload={}).to_payload()
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()

    with (
        patch("app.worker.tasks.build_quiz_adapter", factory),
        patch("app.worker.tasks.poll_quiz_deck.apply_async") as apply_async,
    ):
        _poll(FakeSelf(), str(uuid4()), handle, future)

    assert factory.requested == ["local"]
    apply_async.assert_called_once()


# --- PIN-02: an undeclared handle provider fails the job terminally --------------


@pytest.fixture
def seed(db_engine: Engine, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """Point the deck task's engine at the test DB; seed committed rows.

    Returns a callable committing a user + ready source + a deck job in the given
    status, recording the user for cascade cleanup.
    """
    monkeypatch.setattr("app.worker.tasks.get_engine", lambda: db_engine)
    created_users: list[UUID] = []

    def _seed(*, job_status: QuizJobStatus = QuizJobStatus.RUNNING) -> SimpleNamespace:
        now = datetime.now(UTC)
        user = User(id=uuid4(), email=f"{uuid4()}@example.com", created_at=now)
        source = Source(
            id=uuid4(),
            user_id=user.id,
            title="Biology",
            filename="bio.epub",
            content_type="application/epub+zip",
            byte_size=1024,
            checksum="d" * 64,
            object_key=f"sources/{uuid4()}.epub",
            status="ready",
            created_at=now,
            updated_at=now,
        )
        job = QuizGenerationJob(
            id=uuid4(),
            source_id=source.id,
            status=job_status,
            attempts=0,
            generated_count=0,
            discarded_count=0,
            failed_sections=0,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
        created_users.append(user.id)
        with db_engine.begin() as conn:
            SqlAlchemyUserRepository(conn).add(user)
            SqlAlchemySourceRepository(conn).add(source)
            SqlAlchemyQuizJobRepository(conn).add(job)
        return SimpleNamespace(user=user, source=source, job=job)

    yield _seed

    with db_engine.begin() as conn:
        for user_id in created_users:
            conn.execute(sa_delete(users).where(users.c.id == user_id))


def _read_job(engine: Engine, job_id: UUID) -> QuizGenerationJob:
    with engine.connect() as conn:
        return SqlAlchemyQuizJobRepository(conn).get_by_id(job_id)


@requires_db
def test_an_undeclared_handle_provider_fails_the_job_terminally(
    seed,
    db_engine: Engine,
    caplog,  # noqa: ANN001
) -> None:
    # The REAL factory is used: no settings-declared adapter exists for 'gemini',
    # so building one is impossible — no provider is touched, let alone polled.
    ctx = seed(job_status=QuizJobStatus.RUNNING)
    handle = QuizDeckHandle(provider="gemini", batch_id="batch-1", payload={}).to_payload()
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    bound = FakeSelf(retries=0, max_retries=3)

    with (
        caplog.at_level(logging.ERROR, logger="app.worker.tasks"),
        patch("app.worker.tasks.poll_quiz_deck.apply_async") as apply_async,
    ):
        _poll(bound, str(ctx.job.id), handle, future)

    job = _read_job(db_engine, ctx.job.id)
    assert job.status == QuizJobStatus.FAILED
    assert job.last_error == "Quiz deck generation provider is no longer configured."
    # Terminal means terminal: no retry loop, no further poll scheduled.
    assert bound.retry_calls == []
    apply_async.assert_not_called()
    # The operator learns which provider vanished and what unblocks the deck.
    messages = [r.getMessage() for r in caplog.records if r.name == "app.worker.tasks"]
    assert any("gemini" in m and "does not declare" in m for m in messages)


# --- PIN-03: the begin records its provider into the Celery payload --------------


@requires_db
def test_the_begin_records_its_provider_through_the_json_round_trip(seed) -> None:  # noqa: ANN001
    # The poll task receives only the handle's JSON payload; the beginning
    # provider's identity must survive it intact — it is what the poll pins to.
    ctx = seed(job_status=QuizJobStatus.QUEUED)
    begun = QuizDeckHandle(provider="vendor-a", batch_id="batch-9", payload={"k": "v"})
    adapter = SimpleNamespace(
        begin_deck=lambda sections: begun,
        collect_deck=lambda handle: None,  # still pending → the poll gets scheduled
    )
    factory = _RecordingFactory(adapter)

    with (
        patch("app.worker.tasks.build_quiz_adapter", factory),
        patch("app.worker.tasks.poll_quiz_deck.apply_async") as apply_async,
    ):
        _generate(FakeSelf(), str(ctx.source.id), str(ctx.job.id))

    # The begin-path builds carry no override (a begin follows the settings);
    # the inline collect pins to the provider the begin recorded.
    assert all(requested is None for requested in factory.requested[:-1])
    assert factory.requested[-1] == "vendor-a"
    payload = apply_async.call_args.kwargs["args"][1]
    round_tripped = QuizDeckHandle.from_payload(json.loads(json.dumps(payload)))
    assert round_tripped.provider == "vendor-a"
    assert round_tripped.batch_id == "batch-9"
