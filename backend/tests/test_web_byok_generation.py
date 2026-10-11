"""Learner-keyed chains at the real conversations surface (live DB).

With a KEK configured and a registry profile bound to a provider, a learner who
holds a key for that provider has their Ask, Tutor and selection-Explain turns
served by the bound profiles, built with their own key, ahead of every house
entry. These tests stand in for the provider adapters with a recording fake
(``_KeyedFake``) installed where the composition root builds Anthropic
adapters, so each served call names the exact key its adapter was built with.

Keys are stored through the repository (no HTTP route stores one yet), with
the same envelope the composition root reads.
"""

from __future__ import annotations

import base64
import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.domain.entities import (
    MODE_TEACH,
    TUTOR_OPENING_MESSAGE,
    AnswerStreamEvent,
    GeneratedAnswer,
    TokenUsage,
    User,
)
from app.infrastructure.db.provider_credentials import SqlAlchemyProviderCredentialRepository
from app.infrastructure.db.repositories import (
    SqlAlchemyAiPreferenceRepository,
    SqlAlchemyAiSpendDayRepository,
)
from app.infrastructure.security.secrets_envelope import SecretsEnvelope
from tests.conftest import TEST_PASSWORD, clear_settings_and_generation_caches, requires_db
from tests.test_web_user_generation import (
    _ANCHOR,
    _csrf,
    _post_turn,
    _register,
    _seed_conversation,
    _seed_source,
)

pytestmark = requires_db

_KEK = os.urandom(32)
_HOUSE_KEY = "sk-ant-house-operator-key-000000000000"
_KEY_A = "sk-ant-api03-learner-alpha-key-AAAAAAAAAA"
_KEY_B = "sk-ant-api03-learner-bravo-key-BBBBBBBBBB"


def _profile(profile_id: str, model: str, **overrides: Any) -> dict[str, Any]:
    profile: dict[str, Any] = {
        "id": profile_id,
        "kind": "anthropic",
        "model": model,
        "max_tokens": 64,
        "price_input_usd_per_million_tokens": 3.0,
        "price_output_usd_per_million_tokens": 15.0,
        "price_cache_read_usd_per_million_tokens": 0.3,
        "price_cache_creation_usd_per_million_tokens": 3.75,
        "grounding": "verified-spans",
        "ask_enabled": True,
        "teach_enabled": True,
    }
    profile.update(overrides)
    return profile


_HOUSE = _profile("house", "claude-house", api_key_env="LEARNY_TEST_HOUSE_KEY")
_BYOK = _profile("byok-claude", "claude-byok", user_key_provider="anthropic")


class _KeyedFake:
    """Stands in for ``AnthropicGenerationAdapter``: records the key it was built with.

    Every instance lands in ``built`` so a test can find the adapter a key
    produced, count its calls, and see whether the house adapter was touched.
    Each answer cites the first evidence chunk and reports token usage, so the
    debit path prices it like a real provider call.
    """

    built: list[_KeyedFake] = []

    def __init__(self, *, api_key: str, model: str, max_tokens: int, **_kwargs: object) -> None:
        self.api_key = api_key
        self.model = model
        self.calls = 0
        _KeyedFake.built.append(self)

    def generate(self, *, evidence: Any, **_kwargs: object) -> GeneratedAnswer:  # noqa: ANN401
        self.calls += 1
        return GeneratedAnswer(
            text=f"served by {self.model}",
            cited_chunk_ids=(evidence[0].chunk_id,) if evidence else (),
            model=self.model,
            found=True,
            usage=TokenUsage(input_tokens=1000, output_tokens=500),
        )

    def generate_stream(self, **_kwargs: object) -> Iterator[AnswerStreamEvent]:
        raise AssertionError("these buffered turns never stream")


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> list[_KeyedFake]:
    import app.infrastructure.answering as answering

    _KeyedFake.built = []
    monkeypatch.setattr(answering, "AnthropicGenerationAdapter", _KeyedFake)
    return _KeyedFake.built


def _declare(
    monkeypatch: pytest.MonkeyPatch,
    profiles: list[dict[str, Any]],
    *,
    kek: bytes | None = _KEK,
    explain_profile: str = "",
) -> None:
    monkeypatch.setenv("LEARNY_GENERATION_PROFILES", json.dumps(profiles))
    monkeypatch.setenv("LEARNY_TEST_HOUSE_KEY", _HOUSE_KEY)
    monkeypatch.setenv("LEARNY_GENERATION_EXPLAIN_PROFILE", explain_profile)
    if kek is None:
        monkeypatch.delenv("LEARNY_SECRETS_KEK", raising=False)
    else:
        monkeypatch.setenv("LEARNY_SECRETS_KEK", base64.b64encode(kek).decode())
    monkeypatch.delenv("LEARNY_SECRETS_KEK_PREVIOUS", raising=False)
    clear_settings_and_generation_caches()


def _store_key(db_conn: Connection, user_id: str, key: str, *, kek: bytes = _KEK) -> None:
    SqlAlchemyProviderCredentialRepository(db_conn, SecretsEnvelope(kek)).replace(
        UUID(user_id), "anthropic", key
    )


def _delete_key(db_conn: Connection, user_id: str) -> None:
    SqlAlchemyProviderCredentialRepository(db_conn, SecretsEnvelope(_KEK)).delete(
        UUID(user_id), "anthropic"
    )


def _login(client: TestClient, email: str) -> str:
    client.cookies.clear()
    resp = client.post("/api/auth/login", json={"email": email, "password": TEST_PASSWORD})
    assert resp.status_code == 200, resp.text
    return _csrf(client)


def _learner(client: TestClient, db_conn: Connection, email: str) -> tuple[str, str, UUID]:
    """Register a learner and seed a whole-book conversation the turn can answer from."""
    user_id = _register(client, email)
    csrf = _csrf(client)
    conversation = _seed_conversation(db_conn, _seed_source(db_conn, user_id), scope=())
    return user_id, csrf, conversation


def _by_key(fakes: list[_KeyedFake], key: str) -> list[_KeyedFake]:
    return [fake for fake in fakes if fake.api_key == key]


def _calls(fakes: list[_KeyedFake], key: str) -> int:
    return sum(fake.calls for fake in _by_key(fakes, key))


# --- C19: Ask and Tutor turns run on the learner's key, ahead of the house ---------


def test_turn_served_by_learner_key(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
    fakes: list[_KeyedFake],
) -> None:
    _declare(monkeypatch, [_HOUSE, _BYOK])
    client = auth_client
    user_id, csrf, conversation = _learner(client, db_conn, "byok-turn@example.com")
    _store_key(db_conn, user_id, _KEY_A)
    teach_conversation = _seed_conversation(
        db_conn, _seed_source(db_conn, user_id), scope=(_ANCHOR,), targeted=True
    )

    ask = _post_turn(client, conversation, csrf)
    teach = _post_turn(
        client, teach_conversation, csrf, mode=MODE_TEACH, message=TUTOR_OPENING_MESSAGE
    )

    assert ask.status_code == 201, ask.text
    assert teach.status_code == 201, teach.text
    assert ask.json()["model"] == "claude-byok"
    assert teach.json()["model"] == "claude-byok"
    # Both turns were served by an adapter built with the learner's own key...
    assert _calls(fakes, _KEY_A) == 2
    assert all(fake.model == "claude-byok" for fake in _by_key(fakes, _KEY_A))
    # ...and the house primary, built with the operator key, was never called.
    assert _calls(fakes, _HOUSE_KEY) == 0


def test_stored_choice_leads_the_learner_keyed_profiles(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
    fakes: list[_KeyedFake],
) -> None:
    # Two profiles bind anthropic; registry order puts the user-key-only one first.
    dual = _profile(
        "dual-claude",
        "claude-dual",
        api_key_env="LEARNY_TEST_HOUSE_KEY",
        user_key_provider="anthropic",
    )
    _declare(monkeypatch, [_HOUSE, _BYOK, dual])
    client = auth_client
    user_id, csrf, conversation = _learner(client, db_conn, "byok-choice@example.com")
    _store_key(db_conn, user_id, _KEY_A)

    unchosen = _post_turn(client, conversation, csrf)
    assert unchosen.status_code == 201, unchosen.text
    assert unchosen.json()["model"] == "claude-byok"

    SqlAlchemyAiPreferenceRepository(db_conn).upsert(UUID(user_id), "dual-claude")
    chosen = _post_turn(client, conversation, csrf)

    assert chosen.status_code == 201, chosen.text
    # The stored choice is bound to the learner's provider, so it leads their keyed
    # entries, and it is served with the learner's key, not the house key.
    assert chosen.json()["model"] == "claude-dual"
    assert [fake.model for fake in _by_key(fakes, _KEY_A) if fake.calls] == [
        "claude-byok",
        "claude-dual",
    ]
    assert _calls(fakes, _HOUSE_KEY) == 0


def test_a_stored_choice_not_bound_to_the_key_is_ignored(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
    fakes: list[_KeyedFake],
) -> None:
    # The learner once chose the house profile, which binds no provider: holding
    # a key, they are still served by the profile bound to it, on their key.
    _declare(monkeypatch, [_HOUSE, _BYOK])
    client = auth_client
    user_id, csrf, conversation = _learner(client, db_conn, "byok-unbound-choice@example.com")
    SqlAlchemyAiPreferenceRepository(db_conn).upsert(UUID(user_id), "house")
    _store_key(db_conn, user_id, _KEY_A)

    turn = _post_turn(client, conversation, csrf)

    assert turn.status_code == 201, turn.text
    assert turn.json()["model"] == "claude-byok"
    assert _calls(fakes, _KEY_A) == 1
    assert _calls(fakes, _HOUSE_KEY) == 0


def test_an_explain_profile_not_bound_to_the_key_is_ignored(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
    fakes: list[_KeyedFake],
) -> None:
    # The operator's Explain profile is the house one; a learner holding a key
    # is still served their Explain by the profile bound to it, on their key.
    _declare(monkeypatch, [_HOUSE, _BYOK], explain_profile="house")
    client = auth_client
    user_id, csrf, conversation = _learner(client, db_conn, "byok-unbound-explain@example.com")
    _store_key(db_conn, user_id, _KEY_A)

    explained = _post_turn(client, conversation, csrf, origin="explain_selection")

    assert explained.status_code == 201, explained.text
    assert explained.json()["model"] == "claude-byok"
    assert _calls(fakes, _KEY_A) == 1
    assert _calls(fakes, _HOUSE_KEY) == 0


# --- C20: selection-Explain runs on the learner's key -------------------------------


def test_explain_served_by_learner_key(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
    fakes: list[_KeyedFake],
) -> None:
    explain = _profile(
        "byok-explain", "claude-byok-explain", user_key_provider="anthropic", teach_enabled=False
    )
    _declare(monkeypatch, [_HOUSE, _BYOK, explain], explain_profile="byok-explain")
    client = auth_client
    _keyless_id, keyless_csrf, keyless_conversation = _learner(
        client, db_conn, "byok-explain-keyless@example.com"
    )
    keyless_explained = _post_turn(
        client, keyless_conversation, keyless_csrf, origin="explain_selection"
    )
    user_id = _register(client, "byok-explain@example.com")
    csrf = _csrf(client)
    conversation = _seed_conversation(db_conn, _seed_source(db_conn, user_id), scope=())
    _store_key(db_conn, user_id, _KEY_A)

    explained = _post_turn(client, conversation, csrf, origin="explain_selection")
    ordinary = _post_turn(client, conversation, csrf)

    assert explained.status_code == 201, explained.text
    assert ordinary.status_code == 201, ordinary.text
    # The named explain profile is bound to the learner's provider, so it leads
    # their Explain chain; their ordinary turn keeps the registry order.
    assert explained.json()["model"] == "claude-byok-explain"
    assert ordinary.json()["model"] == "claude-byok"
    assert {fake.model for fake in _by_key(fakes, _KEY_A) if fake.calls} == {
        "claude-byok-explain",
        "claude-byok",
    }
    # A learner without a key still gets the house Explain chain.
    assert keyless_explained.status_code == 201, keyless_explained.text
    assert keyless_explained.json()["model"] == "claude-house"


def test_explain_served_by_learner_key_without_a_named_explain_profile(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
    fakes: list[_KeyedFake],
) -> None:
    _declare(monkeypatch, [_HOUSE, _BYOK])
    client = auth_client
    user_id, csrf, conversation = _learner(client, db_conn, "byok-explain-plain@example.com")
    _store_key(db_conn, user_id, _KEY_A)

    explained = _post_turn(client, conversation, csrf, origin="explain_selection")

    assert explained.status_code == 201, explained.text
    assert explained.json()["model"] == "claude-byok"
    assert _calls(fakes, _KEY_A) == 1
    assert _calls(fakes, _HOUSE_KEY) == 0


# --- C22: a mode no bound profile serves stays on the house chain --------------------


def test_uncovered_mode_served_by_house(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
    fakes: list[_KeyedFake],
) -> None:
    teach_only = _profile(
        "byok-teach", "claude-byok-teach", user_key_provider="anthropic", ask_enabled=False
    )
    _declare(monkeypatch, [_HOUSE, teach_only])
    client = auth_client
    user_id, csrf, conversation = _learner(client, db_conn, "byok-uncovered@example.com")
    _store_key(db_conn, user_id, _KEY_A)

    ask = _post_turn(client, conversation, csrf)

    assert ask.status_code == 201, ask.text
    assert ask.json()["model"] == "claude-house"
    assert _calls(fakes, _HOUSE_KEY) == 1
    assert _calls(fakes, _KEY_A) == 0


# --- C23: two learners, two keys, one process -----------------------------------------


def test_two_learners_two_keys(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
    fakes: list[_KeyedFake],
) -> None:
    from app.infrastructure.web import dependencies

    _declare(monkeypatch, [_HOUSE, _BYOK])
    client = auth_client
    a_id, _a_csrf, a_conversation = _learner(client, db_conn, "byok-alpha@example.com")
    b_id, b_csrf, b_conversation = _learner(client, db_conn, "byok-bravo@example.com")
    _store_key(db_conn, a_id, _KEY_A)
    _store_key(db_conn, b_id, _KEY_B)

    b_turn = _post_turn(client, b_conversation, b_csrf)
    a_csrf = _login(client, "byok-alpha@example.com")
    a_turn = _post_turn(client, a_conversation, a_csrf)

    assert a_turn.status_code == 201, a_turn.text
    assert b_turn.status_code == 201, b_turn.text
    assert _calls(fakes, _KEY_A) == 1
    assert _calls(fakes, _KEY_B) == 1
    assert _calls(fakes, _HOUSE_KEY) == 0
    assert len(dependencies._user_adapters) == 2
    # No house chain picked up either learner's adapter.
    house_keys = {
        getattr(entry.adapter, "api_key", None)
        for chain in (dependencies.get_generation(), dependencies.get_explain_generation())
        for entry in chain._chain
    }
    assert house_keys == {_HOUSE_KEY}


# --- C24: replace and delete take effect on the next request --------------------------


def test_replace_and_delete_take_effect_next_request(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
    fakes: list[_KeyedFake],
) -> None:
    _declare(monkeypatch, [_HOUSE, _BYOK])
    client = auth_client
    user_id, csrf, conversation = _learner(client, db_conn, "byok-lifecycle@example.com")
    _store_key(db_conn, user_id, _KEY_A)

    first = _post_turn(client, conversation, csrf)
    _store_key(db_conn, user_id, _KEY_B)  # replace
    second = _post_turn(client, conversation, csrf)
    _delete_key(db_conn, user_id)
    third = _post_turn(client, conversation, csrf)

    assert [r.status_code for r in (first, second, third)] == [201, 201, 201]
    assert first.json()["model"] == "claude-byok"
    assert second.json()["model"] == "claude-byok"
    assert third.json()["model"] == "claude-house"
    # The old key's adapter served exactly the first turn and was never called again.
    assert _calls(fakes, _KEY_A) == 1
    assert _calls(fakes, _KEY_B) == 1
    assert _calls(fakes, _HOUSE_KEY) == 1


# --- C25: a learner-paid call debits 0 USD but still counts -------------------------


def test_learner_key_debits_zero_usd_counts_call(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
    fakes: list[_KeyedFake],
) -> None:
    _declare(monkeypatch, [_HOUSE, _BYOK])
    client = auth_client
    keyed_id, keyed_csrf, keyed_conversation = _learner(client, db_conn, "byok-ledger@example.com")
    _store_key(db_conn, keyed_id, _KEY_A)

    keyed = _post_turn(client, keyed_conversation, keyed_csrf)
    house_id, house_csrf, house_conversation = _learner(client, db_conn, "house-ledger@example.com")
    housed = _post_turn(client, house_conversation, house_csrf)

    assert keyed.status_code == 201, keyed.text
    assert housed.status_code == 201, housed.text
    ledger = SqlAlchemyAiSpendDayRepository(db_conn)
    today = datetime.now(UTC).date()
    keyed_day = ledger.get_for_day(UUID(keyed_id), today)
    house_day = ledger.get_for_day(UUID(house_id), today)
    assert keyed_day is not None and house_day is not None
    # Same usage reported by both adapters; only the house-served one costs the house.
    assert keyed_day.usd_micros == 0
    assert keyed_day.ask_count == 1
    assert house_day.usd_micros > 0
    assert house_day.ask_count == 1


# --- C26: the kill switch refuses learner-keyed generation too -----------------------


def test_kill_switch_refuses_learner_key(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
    fakes: list[_KeyedFake],
) -> None:
    _declare(monkeypatch, [_HOUSE, _BYOK])
    monkeypatch.setenv("LEARNY_AI_KILL_SWITCH", "true")
    clear_settings_and_generation_caches()
    client = auth_client
    user_id, csrf, conversation = _learner(client, db_conn, "byok-paused@example.com")
    _store_key(db_conn, user_id, _KEY_A)

    resp = _post_turn(client, conversation, csrf)

    assert resp.status_code == 503, resp.text
    assert sum(fake.calls for fake in fakes) == 0


# --- C5: a row under an unknown KEK is no credential ---------------------------------


def test_unknown_kek_serves_house_chain(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
    fakes: list[_KeyedFake],
) -> None:
    _declare(monkeypatch, [_HOUSE, _BYOK])
    client = auth_client
    user_id, csrf, conversation = _learner(client, db_conn, "byok-orphan@example.com")
    _store_key(db_conn, user_id, _KEY_A, kek=os.urandom(32))  # a KEK nobody configured

    resp = _post_turn(client, conversation, csrf)

    assert resp.status_code == 201, resp.text
    assert resp.json()["model"] == "claude-house"
    assert _calls(fakes, _KEY_A) == 0
    assert _by_key(fakes, _KEY_A) == []  # never even decrypted into an adapter


# --- Off by default: no KEK means stored rows are never read -------------------------


def _domain_user(user_id: str) -> User:
    return User(id=UUID(user_id), email=f"{user_id}@example.com", created_at=datetime.now(UTC))


def test_without_a_kek_a_learner_with_a_row_gets_the_house_chain_object(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
    fakes: list[_KeyedFake],
) -> None:
    from app.infrastructure.web import dependencies

    _declare(monkeypatch, [_HOUSE, _BYOK], kek=None)
    user_id = _register(auth_client, "byok-off@example.com")
    _store_key(db_conn, user_id, _KEY_A)
    house = dependencies.get_generation()
    explain = dependencies.get_explain_generation()

    user = _domain_user(user_id)
    assert dependencies.get_generation_for_user(db_conn, user, house) is house
    assert dependencies.get_explain_generation_for_user(db_conn, user, explain) is explain
    assert _by_key(fakes, _KEY_A) == []


def test_without_a_bound_profile_the_feature_stays_off(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
    fakes: list[_KeyedFake],
) -> None:
    from app.infrastructure.web import dependencies

    _declare(monkeypatch, [_HOUSE])
    user_id = _register(auth_client, "byok-unbound@example.com")
    _store_key(db_conn, user_id, _KEY_A)
    house = dependencies.get_generation()

    assert dependencies.get_generation_for_user(db_conn, _domain_user(user_id), house) is house
    assert _by_key(fakes, _KEY_A) == []


def test_clearing_the_generation_caches_drops_learner_adapters(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
    fakes: list[_KeyedFake],
) -> None:
    from app.infrastructure.web import dependencies

    _declare(monkeypatch, [_HOUSE, _BYOK])
    user_id = _register(auth_client, "byok-clear@example.com")
    _store_key(db_conn, user_id, _KEY_A)
    dependencies.get_generation_for_user(
        db_conn, _domain_user(user_id), dependencies.get_generation()
    )
    assert len(dependencies._user_adapters) == 1

    dependencies.clear_generation_chain_caches()

    assert len(dependencies._user_adapters) == 0
