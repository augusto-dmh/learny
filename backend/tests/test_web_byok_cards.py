"""Card suggestions on the learner's own Anthropic key (live DB, ADR-0033).

A learner holding an Anthropic key gets highlight and note card suggestions
from a quiz adapter built with that key and ``quiz_model``; the house ledger
debits 0 USD for them. A learner without a key keeps the house generator. The
Anthropic quiz adapter is replaced by a recording fake where the learner-keyed
composition builds it, so each call names the key its adapter was built with.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.domain.entities import SuggestResult, TokenUsage
from app.infrastructure.db.provider_credentials import SqlAlchemyProviderCredentialRepository
from app.infrastructure.db.repositories import SqlAlchemyAiSpendDayRepository
from app.infrastructure.security.secrets_envelope import SecretsEnvelope
from tests.conftest import clear_settings_and_generation_caches, requires_db
from tests.test_web_cards import QUOTE as _QUOTE
from tests.test_web_cards import (  # noqa: F401 — ``cards_client`` is a fixture
    _csrf,
    _persist_source,
    _post_suggestions,
    _register,
    _seed_corpus,
    cards_client,
)

pytestmark = requires_db

_KEK = os.urandom(32)
_KEY = "sk-ant-api03-cards-learner-key-CCCCCCCCCCCCCC"

_HOUSE = {
    "id": "house",
    "kind": "local",
    "model": "local-extractive",
    "max_tokens": 64,
    "price_input_usd_per_million_tokens": 3.0,
    "price_output_usd_per_million_tokens": 15.0,
    "price_cache_read_usd_per_million_tokens": 0.3,
    "price_cache_creation_usd_per_million_tokens": 3.75,
    "grounding": "verified-spans",
    "ask_enabled": True,
    "teach_enabled": True,
}
_BYOK = {**_HOUSE, "id": "byok-claude", "kind": "anthropic", "user_key_provider": "anthropic"}


class _KeyedQuizFake:
    """Stands in for ``AnthropicQuizAdapter``: records its key, reports usage."""

    built: list[_KeyedQuizFake] = []

    def __init__(self, *, api_key: str, model: str, max_tokens: int) -> None:
        self.api_key = api_key
        self.model = model
        self.calls = 0
        _KeyedQuizFake.built.append(self)

    def _result(self) -> SuggestResult:
        self.calls += 1
        return SuggestResult(
            candidates=(), usage=TokenUsage(input_tokens=200_000, output_tokens=100_000)
        )

    def suggest_cards(self, section: Any, quote: str, limit: int) -> SuggestResult:  # noqa: ANN401
        return self._result()

    def suggest_note_cards(self, note_body: str, context: str, limit: int) -> SuggestResult:
        return self._result()


@pytest.fixture
def fakes(cards_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> list[_KeyedQuizFake]:  # noqa: F811
    import app.infrastructure.quiz.learner as learner

    monkeypatch.setenv("LEARNY_GENERATION_PROFILES", json.dumps([_HOUSE, _BYOK]))
    monkeypatch.setenv("LEARNY_SECRETS_KEK", base64.b64encode(_KEK).decode())
    monkeypatch.delenv("LEARNY_SECRETS_KEK_PREVIOUS", raising=False)
    clear_settings_and_generation_caches()
    _KeyedQuizFake.built = []
    monkeypatch.setattr(learner, "AnthropicQuizAdapter", _KeyedQuizFake)
    yield _KeyedQuizFake.built
    clear_settings_and_generation_caches()


def _usd_today(db_conn: Connection, user_id: str) -> int:
    day = SqlAlchemyAiSpendDayRepository(db_conn).get_for_day(
        UUID(user_id), datetime.now(UTC).date()
    )
    return day.usd_micros if day is not None else 0


def _highlight(client: TestClient, db_conn: Connection, email: str) -> dict[str, Any]:  # noqa: ANN401
    """A learner with a highlighted, corpus-built source and a non-empty note."""
    user_id = _register(client, email)
    csrf = _csrf(client)
    source_id = _persist_source(db_conn, user_id)
    _seed_corpus(db_conn, source_id)
    resp = client.post(
        f"/api/sources/{source_id}/highlights",
        json={
            "anchor": "ch1",
            "quote_exact": _QUOTE,
            "title": "highlight",
            "body_markdown": "Why the passage matters to me.",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return {
        "user_id": user_id,
        "csrf": csrf,
        "source_id": source_id,
        "note_id": body["id"],
        "anchor_id": body["anchors"][0]["id"],
    }


def test_suggestions_use_learner_key(
    cards_client: TestClient,  # noqa: F811
    db_conn: Connection,
    fakes: list[_KeyedQuizFake],
) -> None:
    from app.core.config import get_settings

    learner = _highlight(cards_client, db_conn, "cards-byok@example.com")
    SqlAlchemyProviderCredentialRepository(db_conn, SecretsEnvelope(_KEK)).replace(
        UUID(learner["user_id"]), "anthropic", _KEY
    )

    passage = _post_suggestions(
        cards_client, learner["source_id"], learner["anchor_id"], csrf=learner["csrf"]
    )
    note = cards_client.post(
        f"/api/notes/{learner['note_id']}/cards/suggest",
        headers={"X-CSRF-Token": learner["csrf"]},
    )

    assert passage.status_code == 200, passage.text
    assert note.status_code == 200, note.text
    # One adapter, built once with the learner's key and quiz_model, served both.
    assert [fake.api_key for fake in fakes] == [_KEY]
    assert fakes[0].model == get_settings().quiz_model
    assert fakes[0].calls == 2
    # 300k reported tokens would price well above 0 at the house's catalog.
    assert _usd_today(db_conn, learner["user_id"]) == 0


def test_a_learner_without_a_key_keeps_the_house_generator(
    cards_client: TestClient,  # noqa: F811
    db_conn: Connection,
    fakes: list[_KeyedQuizFake],
) -> None:
    learner = _highlight(cards_client, db_conn, "cards-house@example.com")

    resp = _post_suggestions(
        cards_client, learner["source_id"], learner["anchor_id"], csrf=learner["csrf"]
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["suggestions"], "the house's deterministic adapter served"
    assert fakes == []


# --- The learner-side rails at the cards surface -------------------------------------

_PERIOD = datetime.now(UTC).strftime("%Y-%m")


def test_ceiling_refuses_cards(
    cards_client: TestClient,  # noqa: F811
    db_conn: Connection,
    fakes: list[_KeyedQuizFake],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A highlight on a source at the month's prompt-token ceiling refuses pre-flight."""
    from app.infrastructure.db.repositories import SqlAlchemyByokCorpusRepository
    from tests.conftest import clear_settings_and_generation_caches

    monkeypatch.setenv("LEARNY_BYOK_CORPUS_PROMPT_TOKEN_CAP", "1000")
    clear_settings_and_generation_caches()
    learner = _highlight(cards_client, db_conn, "cards-ceiling@example.com")
    SqlAlchemyProviderCredentialRepository(db_conn, SecretsEnvelope(_KEK)).replace(
        UUID(learner["user_id"]), "anthropic", _KEY
    )
    SqlAlchemyByokCorpusRepository(db_conn).record(
        UUID(learner["user_id"]),
        learner["source_id"],
        _PERIOD,
        input_tokens=1000,
    )

    resp = _post_suggestions(
        cards_client, learner["source_id"], learner["anchor_id"], csrf=learner["csrf"]
    )

    assert resp.status_code == 429, resp.text
    assert resp.json()["code"] == "byok_corpus_limit"
    assert all(fake.calls == 0 for fake in fakes)  # nothing was generated


def test_budget_trips_cards(
    cards_client: TestClient,  # noqa: F811
    db_conn: Connection,
    fakes: list[_KeyedQuizFake],
) -> None:
    """The learner's own monthly budget pauses their key at the cards surface too."""
    from app.infrastructure.db.repositories import (
        SqlAlchemyByokMonthRepository,
        SqlAlchemyUserByokSettingsRepository,
    )

    learner = _highlight(cards_client, db_conn, "cards-budget@example.com")
    SqlAlchemyProviderCredentialRepository(db_conn, SecretsEnvelope(_KEK)).replace(
        UUID(learner["user_id"]), "anthropic", _KEY
    )
    SqlAlchemyUserByokSettingsRepository(db_conn).set_budget(UUID(learner["user_id"]), 5_000_000)
    SqlAlchemyByokMonthRepository(db_conn).record(
        UUID(learner["user_id"]),
        _PERIOD,
        input_tokens=200_000,
        output_tokens=100_000,
        cost_usd_micros=5_000_000,
    )

    resp = _post_suggestions(
        cards_client, learner["source_id"], learner["anchor_id"], csrf=learner["csrf"]
    )

    assert resp.status_code == 429, resp.text
    assert resp.json()["code"] == "byok_budget"
    assert all(fake.calls == 0 for fake in fakes)  # nothing was generated
