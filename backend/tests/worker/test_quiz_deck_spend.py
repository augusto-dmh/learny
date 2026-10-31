"""The deck settle's spend recording (live DB).

The settle unit of work claims the job's one-time spend marker, debits the
pass's actual usage to the owner's UTC day, and — for a pass the owner's own
key served — records the same usage and its estimated cost to the owner's
monthly and per-book ledgers. The estimate prices the deck model at the
operator's primary catalog (the deck model is not a registry profile).
"""

from __future__ import annotations

import base64
import json
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import Engine
from sqlalchemy import delete as sa_delete

from app.domain.entities import (
    QuizDeckHandle,
    QuizDeckResult,
    QuizGenerationJob,
    QuizJobStatus,
    Source,
    TokenUsage,
    User,
)
from app.infrastructure.db.metadata import users
from app.infrastructure.db.provider_credentials import SqlAlchemyProviderCredentialRepository
from app.infrastructure.db.repositories import (
    SqlAlchemyAiSpendDayRepository,
    SqlAlchemyByokCorpusRepository,
    SqlAlchemyByokMonthRepository,
    SqlAlchemyQuizJobRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyUserRepository,
)
from app.infrastructure.security.secrets_envelope import SecretsEnvelope
from app.worker.tasks import generate_quiz_deck, poll_quiz_deck
from tests.conftest import clear_settings_and_generation_caches, requires_db
from tests.worker.test_quiz_deck_pinning import FakeSelf

pytestmark = requires_db

_poll = poll_quiz_deck.run.__func__
_generate = generate_quiz_deck.run.__func__

_KEK = os.urandom(32)
_KEY = "sk-ant-api03-deck-spend-owner-key-GGGGGGGGGGGG"

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

_PERIOD = datetime.now(UTC).strftime("%Y-%m")


class _KeyedQuizFake:
    """Stands in for ``AnthropicQuizAdapter``: reports a fixed usage when collected."""

    built: list[_KeyedQuizFake] = []
    pending = True

    def __init__(self, *, api_key: str, model: str, max_tokens: int) -> None:
        self.api_key = api_key
        self.model = model
        _KeyedQuizFake.built.append(self)

    def begin_deck(self, sections: Any) -> QuizDeckHandle:  # noqa: ANN401
        return QuizDeckHandle(provider="anthropic", batch_id="batch-spend", payload={})

    def collect_deck(self, handle: QuizDeckHandle) -> QuizDeckResult | None:
        if _KeyedQuizFake.pending:
            return None
        return QuizDeckResult(
            candidates=(), errors=(), usage=TokenUsage(input_tokens=5_000, output_tokens=5_000)
        )


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
    created: list[User] = []

    def _seed() -> SimpleNamespace:
        now = datetime.now(UTC)
        user = User(id=uuid4(), email=f"{uuid4()}@example.com", created_at=now)
        source = Source(
            id=uuid4(),
            user_id=user.id,
            title="Biology",
            filename="bio.epub",
            content_type="application/epub+zip",
            byte_size=1024,
            checksum="f" * 64,
            object_key=f"sources/{uuid4()}.epub",
            status="ready",
            created_at=now,
            updated_at=now,
        )
        job = QuizGenerationJob(
            id=uuid4(),
            source_id=source.id,
            status=QuizJobStatus.QUEUED,
            attempts=0,
            generated_count=0,
            discarded_count=0,
            failed_sections=0,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
        created.append(user)
        with db_engine.begin() as conn:
            SqlAlchemyUserRepository(conn).add(user)
            SqlAlchemySourceRepository(conn).add(source)
            SqlAlchemyQuizJobRepository(conn).add(job)
        return SimpleNamespace(user=user, source=source, job=job)

    yield _seed

    with db_engine.begin() as conn:
        for user in created:
            conn.execute(sa_delete(users).where(users.c.id == user.id))


def _store_key(engine: Engine, user_id: uuid4) -> None:
    with engine.begin() as conn:
        SqlAlchemyProviderCredentialRepository(conn, SecretsEnvelope(_KEK)).replace(
            user_id, "anthropic", _KEY
        )


def _run_deck(ctx: SimpleNamespace) -> None:
    """Run the deck task to a pending batch, then poll it to a settled success."""
    with patch("app.worker.tasks.poll_quiz_deck.apply_async") as apply_async:
        _generate(FakeSelf(), str(ctx.source.id), str(ctx.job.id))
    payload = apply_async.call_args.kwargs["args"][1]
    _KeyedQuizFake.pending = False
    deadline = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    with patch("app.worker.tasks.poll_quiz_deck.apply_async"):
        _poll(FakeSelf(), str(ctx.job.id), payload, deadline)


def test_settle_records_byok_ledgers(
    byok: None,
    seed,
    db_engine: Engine,
    fakes: list[_KeyedQuizFake],  # noqa: ANN001
) -> None:
    """A learner-keyed settle records the owner's ledgers beside the 0-USD house debit.

    5k input x $3/M + 5k output x $15/M (the operator's primary catalog — the deck
    model is not a registry profile) is 90_000 micros, and the book's prompt
    ledger counts the same pass's 5k input tokens. A house-served settle records
    nothing to either ledger.
    """
    ctx = seed()
    _store_key(db_engine, ctx.user.id)

    _run_deck(ctx)

    month = SqlAlchemyByokMonthRepository(db_engine.connect()).get_for_month(ctx.user.id, _PERIOD)
    assert month is not None
    assert (month.input_tokens, month.output_tokens) == (5_000, 5_000)
    assert month.cost_usd_micros == 90_000
    corpus = SqlAlchemyByokCorpusRepository(db_engine.connect()).get_for_month(
        ctx.user.id, ctx.source.id, _PERIOD
    )
    assert corpus is not None
    assert corpus.input_tokens == 5_000
    day = SqlAlchemyAiSpendDayRepository(db_engine.connect()).get_for_day(
        ctx.user.id, datetime.now(UTC).date()
    )
    # A 0-USD generation debit never mints a day row (the ledger's own rule);
    # the house ledger certainly holds no learner-keyed spend.
    assert day is None or day.usd_micros == 0

    # A house-served deck (no key) leaves both ledgers empty for its owner.
    # The local house adapter finalizes inline — no poll is ever scheduled.
    house_ctx = seed()
    with patch("app.worker.tasks.poll_quiz_deck.apply_async"):
        _generate(FakeSelf(), str(house_ctx.source.id), str(house_ctx.job.id))
    assert (
        SqlAlchemyByokMonthRepository(db_engine.connect()).get_for_month(house_ctx.user.id, _PERIOD)
        is None
    )
    assert (
        SqlAlchemyByokCorpusRepository(db_engine.connect()).get_for_month(
            house_ctx.user.id, house_ctx.source.id, _PERIOD
        )
        is None
    )
