"""Decks and note card refresh on the owner's own Anthropic key (ADR-0033).

The worker receives ids only. These tests drive the deck and refresh task
*functions* against the migrated test engine (no broker), with a recording fake
installed where ``build_user_keyed_quiz_adapter`` builds the Anthropic quiz
adapter, so every provider call names the exact key its adapter was built with.
The deck pin is proven end to end: the begin stamps the credential row id on
the handle, the handle crosses the Celery JSON boundary, and the poll collects
with that row or fails the job terminally.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine
from sqlalchemy import delete as sa_delete

from app.application.budget import KIND_GENERATION
from app.core.config import get_settings
from app.domain.entities import (
    QuizDeckHandle,
    QuizDeckResult,
    QuizGenerationJob,
    QuizJobStatus,
    Source,
    SuggestResult,
    TokenUsage,
    User,
)
from app.infrastructure.db.metadata import users
from app.infrastructure.db.provider_credentials import SqlAlchemyProviderCredentialRepository
from app.infrastructure.db.repositories import (
    SqlAlchemyAiSpendDayRepository,
    SqlAlchemyQuizJobRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyUserRepository,
)
from app.infrastructure.security.secrets_envelope import SecretsEnvelope
from app.worker.tasks import generate_quiz_deck, poll_quiz_deck, refresh_note_cards
from tests.conftest import clear_settings_and_generation_caches, requires_db
from tests.worker.test_quiz_deck_pinning import FakeSelf, _RecordingFactory

pytestmark = requires_db

_poll = poll_quiz_deck.run.__func__
_generate = generate_quiz_deck.run.__func__
_refresh = refresh_note_cards.run.__func__

_KEK = os.urandom(32)
_KEY = "sk-ant-api03-deck-owner-key-DDDDDDDDDDDDDDDD"
_NEW_KEY = "sk-ant-api03-deck-owner-new-key-EEEEEEEEEEEE"
_DECK_KEY_GONE = (
    "Quiz deck generation stopped because the provider key it started with was removed or replaced."
)

_HOUSE = {
    "id": "house",
    "kind": "local",
    "model": "local-extractive",
    "max_tokens": 64,
    "price_input_usd_per_million_tokens": 0.0,
    "price_output_usd_per_million_tokens": 0.0,
    "price_cache_read_usd_per_million_tokens": 0.0,
    "price_cache_creation_usd_per_million_tokens": 0.0,
    "grounding": "verified-spans",
    "ask_enabled": True,
    "teach_enabled": True,
}
_BYOK = {
    **_HOUSE,
    "id": "byok-claude",
    "kind": "anthropic",
    "model": "claude-byok",
    "price_input_usd_per_million_tokens": 3.0,
    "price_output_usd_per_million_tokens": 15.0,
    "user_key_provider": "anthropic",
}


class _KeyedQuizFake:
    """Stands in for ``AnthropicQuizAdapter``: records its key and every call."""

    built: list[_KeyedQuizFake] = []
    pending = True

    def __init__(self, *, api_key: str, model: str, max_tokens: int) -> None:
        self.api_key = api_key
        self.model = model
        self.begun = 0
        self.collected = 0
        self.suggested = 0
        _KeyedQuizFake.built.append(self)

    def begin_deck(self, sections: Any) -> QuizDeckHandle:  # noqa: ANN401
        self.begun += 1
        return QuizDeckHandle(provider="anthropic", batch_id="batch-byok", payload={})

    def collect_deck(self, handle: QuizDeckHandle) -> QuizDeckResult | None:
        self.collected += 1
        if _KeyedQuizFake.pending:
            return None
        return QuizDeckResult(
            candidates=(), errors=(), usage=TokenUsage(input_tokens=5000, output_tokens=5000)
        )

    def suggest_note_cards(self, note_body: str, context: str, limit: int) -> SuggestResult:
        self.suggested += 1
        return SuggestResult(candidates=(), usage=TokenUsage(input_tokens=1000, output_tokens=1000))


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> list[_KeyedQuizFake]:
    import app.infrastructure.quiz.learner as learner

    _KeyedQuizFake.built = []
    _KeyedQuizFake.pending = True
    monkeypatch.setattr(learner, "AnthropicQuizAdapter", _KeyedQuizFake)
    return _KeyedQuizFake.built


@pytest.fixture
def byok(monkeypatch: pytest.MonkeyPatch) -> None:
    """A KEK and a registry whose house is local and one profile binds Anthropic."""
    monkeypatch.setenv("LEARNY_GENERATION_PROFILES", json.dumps([_HOUSE, _BYOK]))
    monkeypatch.setenv("LEARNY_SECRETS_KEK", base64.b64encode(_KEK).decode())
    monkeypatch.delenv("LEARNY_SECRETS_KEK_PREVIOUS", raising=False)
    clear_settings_and_generation_caches()
    yield
    clear_settings_and_generation_caches()


@pytest.fixture
def seed(db_engine: Engine, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """Point the tasks at the test DB; commit a user, a ready source and a deck job."""
    monkeypatch.setattr("app.worker.tasks.get_engine", lambda: db_engine)
    created: list[UUID] = []

    def _seed(*, job_status: str = QuizJobStatus.QUEUED) -> SimpleNamespace:
        now = datetime.now(UTC)
        user = User(id=uuid4(), email=f"{uuid4()}@example.com", created_at=now)
        source = Source(
            id=uuid4(),
            user_id=user.id,
            title="Biology",
            filename="bio.epub",
            content_type="application/epub+zip",
            byte_size=1024,
            checksum="e" * 64,
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
        created.append(user.id)
        with db_engine.begin() as conn:
            SqlAlchemyUserRepository(conn).add(user)
            SqlAlchemySourceRepository(conn).add(source)
            SqlAlchemyQuizJobRepository(conn).add(job)
        return SimpleNamespace(user=user, source=source, job=job)

    yield _seed

    with db_engine.begin() as conn:
        for user_id in created:
            conn.execute(sa_delete(users).where(users.c.id == user_id))


def _repo(conn: Any) -> SqlAlchemyProviderCredentialRepository:  # noqa: ANN401
    return SqlAlchemyProviderCredentialRepository(conn, SecretsEnvelope(_KEK))


def _store(engine: Engine, user_id: UUID, key: str) -> UUID:
    with engine.begin() as conn:
        return _repo(conn).replace(user_id, "anthropic", key).id


def _delete(engine: Engine, user_id: UUID) -> None:
    with engine.begin() as conn:
        _repo(conn).delete(user_id, "anthropic")


def _job(engine: Engine, job_id: UUID) -> QuizGenerationJob:
    with engine.connect() as conn:
        return SqlAlchemyQuizJobRepository(conn).get_by_id(job_id)


def _usd_today(engine: Engine, user_id: UUID) -> int:
    with engine.connect() as conn:
        day = SqlAlchemyAiSpendDayRepository(conn).get_for_day(user_id, date.today())
    return day.usd_micros if day is not None else 0


def _future() -> str:
    return (datetime.now(UTC) + timedelta(hours=1)).isoformat()


def _begin(ctx: SimpleNamespace) -> dict:
    """Run the deck task to a pending batch; return the scheduled poll's handle payload."""
    with patch("app.worker.tasks.poll_quiz_deck.apply_async") as apply_async:
        _generate(FakeSelf(), str(ctx.source.id), str(ctx.job.id))
    apply_async.assert_called_once()
    return apply_async.call_args.kwargs["args"][1]


# --- C29: the deck and the note refresh resolve the owner's key in the task -------


def test_deck_task_resolves_owner_key(
    byok: None, seed, db_engine: Engine, fakes: list[_KeyedQuizFake]
) -> None:  # noqa: ANN001
    ctx = seed()
    _store(db_engine, ctx.user.id, _KEY)
    other = seed()  # another learner, no key: the house adapter serves them

    _begin(ctx)
    house = _RecordingFactory(
        SimpleNamespace(
            model="house-quiz",
            begin_deck=lambda sections: QuizDeckHandle(provider="local"),
            collect_deck=lambda handle: None,
        )
    )
    with (
        patch("app.worker.tasks.poll_quiz_deck.apply_async"),
        patch("app.worker.tasks.build_quiz_adapter", house),
    ):
        _generate(FakeSelf(), str(other.source.id), str(other.job.id))

    assert [fake.api_key for fake in fakes] == [_KEY]
    assert fakes[0].model == get_settings().quiz_model
    assert fakes[0].begun == 1
    assert fakes[0].collected == 1  # the inline collect ran on the same key
    assert house.requested, "the keyless learner's deck ran on the house adapter"


def test_refresh_cards_resolves_owner_key(
    byok: None, seed, db_engine: Engine, fakes: list[_KeyedQuizFake]
) -> None:  # noqa: ANN001
    ctx = seed()
    _store(db_engine, ctx.user.id, _KEY)
    note = SimpleNamespace(id=uuid4(), user_id=ctx.user.id, body_markdown="A note.")
    captured: dict[str, Any] = {}

    class _NoteRepo:
        def __init__(self, _conn: Any) -> None:  # noqa: ANN401
            pass

        def get_by_id(self, note_id: UUID) -> SimpleNamespace | None:
            return note if note_id == note.id else None

    class _Refresh:
        """Stands in for ``RefreshNoteCards``: makes the one provider call it makes."""

        def __init__(self, *, generation: Any, budget: Any, **_kwargs: Any) -> None:  # noqa: ANN401
            captured["generation"] = generation
            captured["budget"] = budget

        def __call__(self, *, note_id: UUID) -> None:
            result = captured["generation"].suggest_note_cards(note.body_markdown, "", 3)
            captured["result"] = result
            captured["budget"].record(
                note.user_id,
                usd_micros=captured["budget"].usage_micros(
                    result.usage, user_keyed=result.user_keyed
                ),
                kind=KIND_GENERATION,
            )

    with (
        patch("app.worker.tasks.SqlAlchemyNoteRepository", _NoteRepo),
        patch("app.worker.tasks.RefreshNoteCards", _Refresh),
    ):
        _refresh(SimpleNamespace(), str(note.id))

    assert [fake.api_key for fake in fakes] == [_KEY]
    assert fakes[0].suggested == 1
    assert captured["result"].user_keyed is True
    assert _usd_today(db_engine, ctx.user.id) == 0


# --- C30: the handle pins the credential row; the poll collects with it -----------


def test_poll_pins_credential(
    byok: None, seed, db_engine: Engine, fakes: list[_KeyedQuizFake]
) -> None:  # noqa: ANN001
    ctx = seed()
    credential_id = _store(db_engine, ctx.user.id, _KEY)

    payload = _begin(ctx)
    # The pin survives the Celery JSON boundary as the row id, nothing more.
    round_tripped = json.loads(json.dumps(payload))
    assert round_tripped["credential_id"] == str(credential_id)
    assert QuizDeckHandle.from_payload(round_tripped).credential_id == credential_id

    _KeyedQuizFake.pending = False
    with patch("app.worker.tasks.poll_quiz_deck.apply_async") as apply_async:
        _poll(FakeSelf(), str(ctx.job.id), round_tripped, _future())

    apply_async.assert_not_called()
    poll_adapters = fakes[1:]
    assert [fake.api_key for fake in poll_adapters] == [_KEY]
    assert poll_adapters[0].collected == 1
    job = _job(db_engine, ctx.job.id)
    assert job.status == QuizJobStatus.SUCCEEDED
    # The pass reported usage, but it ran on the learner's key: the house pays 0.
    assert _usd_today(db_engine, ctx.user.id) == 0


def test_a_handle_without_a_pin_polls_with_the_house_adapter(
    byok: None, seed, db_engine: Engine, fakes: list[_KeyedQuizFake]
) -> None:  # noqa: ANN001
    ctx = seed(job_status=QuizJobStatus.RUNNING)
    _store(db_engine, ctx.user.id, _KEY)  # a key exists, but this deck began on the house
    legacy = {"provider": "anthropic", "batch_id": "batch-house", "payload": {}}
    house = _RecordingFactory(SimpleNamespace(collect_deck=lambda handle: None))

    with (
        patch("app.worker.tasks.build_quiz_adapter", house),
        patch("app.worker.tasks.poll_quiz_deck.apply_async") as apply_async,
    ):
        _poll(FakeSelf(), str(ctx.job.id), legacy, _future())

    assert house.requested == ["anthropic"]
    assert fakes == []  # the learner's key never touched a house-begun batch
    apply_async.assert_called_once()


# --- C31: a pinned key that is gone fails the job terminally ----------------------


@pytest.mark.parametrize("change", ["deleted", "replaced"])
def test_poll_fails_when_pinned_key_gone(
    change: str, byok: None, seed, db_engine: Engine, fakes: list[_KeyedQuizFake]
) -> None:  # noqa: ANN001
    ctx = seed()
    _store(db_engine, ctx.user.id, _KEY)
    payload = _begin(ctx)
    if change == "deleted":
        _delete(db_engine, ctx.user.id)
    else:
        _store(db_engine, ctx.user.id, _NEW_KEY)  # a new row id: the pin no longer matches
    built_before = len(fakes)
    bound = FakeSelf()

    with patch("app.worker.tasks.poll_quiz_deck.apply_async") as apply_async:
        _poll(bound, str(ctx.job.id), payload, _future())

    job = _job(db_engine, ctx.job.id)
    assert job.status == QuizJobStatus.FAILED
    assert job.last_error == _DECK_KEY_GONE
    assert len(fakes) == built_before  # no adapter built, so nothing collected
    assert all(fake.collected <= 1 for fake in fakes)  # only the begin's inline collect
    assert bound.retry_calls == []
    apply_async.assert_not_called()


# --- C32: task payloads carry ids only --------------------------------------------


def test_task_payloads_carry_ids_only(
    byok: None, seed, db_engine: Engine, fakes: list[_KeyedQuizFake]
) -> None:  # noqa: ANN001
    from app.infrastructure.worker.enqueuer import CeleryNoteIndexEnqueuer, CeleryQuizDeckEnqueuer

    ctx = seed()
    credential_id = _store(db_engine, ctx.user.id, _KEY)
    sent: list[dict[str, Any]] = []

    def _capture(*args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        sent.append({"args": list(args), "kwargs": kwargs})

    with (
        patch("app.worker.tasks.generate_quiz_deck.apply_async", side_effect=_capture),
        patch("app.worker.tasks.refresh_note_cards.apply_async", side_effect=_capture),
        patch("app.worker.tasks.poll_quiz_deck.apply_async", side_effect=_capture),
    ):
        CeleryQuizDeckEnqueuer().enqueue_quiz_deck(source_id=ctx.source.id, job_id=ctx.job.id)
        CeleryNoteIndexEnqueuer().enqueue_refresh_cards(uuid4())
        _generate(FakeSelf(), str(ctx.source.id), str(ctx.job.id))  # schedules the poll
        payload = sent[-1]["kwargs"]["args"][1]
        _poll(FakeSelf(), str(ctx.job.id), payload, _future())  # reschedules the poll

    assert len(sent) == 4
    for call in sent:
        serialized = json.dumps(call, default=str)
        assert _KEY not in serialized
        assert _KEY[-12:] not in serialized
    poll_args = sent[-1]["kwargs"]["args"]
    assert poll_args[0] == str(ctx.job.id)
    assert set(poll_args[1]) == {"provider", "batch_id", "payload", "credential_id"}
    assert poll_args[1]["credential_id"] == str(credential_id)
    datetime.fromisoformat(poll_args[2])  # the deadline, and nothing else
