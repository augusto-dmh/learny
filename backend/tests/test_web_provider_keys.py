"""The provider-key routes through the HTTP client (live DB, ADR-0033).

A learner adds, lists, tests, replaces and deletes a key for an offered
provider. The key goes in once; what comes back is the provider row with the
last four characters and nothing else. The test route's probe is replaced by a
recording fake through ``get_key_probe``, so no provider is called.
"""

from __future__ import annotations

import base64
import json
import os
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, select

from app.infrastructure.answering.probe import ProbeOutcome
from app.infrastructure.db.metadata import user_provider_credentials
from app.infrastructure.db.provider_credentials import SqlAlchemyProviderCredentialRepository
from app.infrastructure.security.secrets_envelope import SecretsEnvelope
from tests.conftest import clear_settings_and_generation_caches, requires_db
from tests.test_web_user_generation import _csrf, _register

pytestmark = requires_db

_KEK = os.urandom(32)
_KEY = "sk-ant-api03-route-key-first-AAAAAAAAAAAAAAAA1234"
_NEW_KEY = "sk-ant-api03-route-key-second-BBBBBBBBBBBBBBB5678"
_OPENAI_KEY = "sk-proj-route-openai-key-CCCCCCCCCCCCCCCCC9012"
_BASE = "/api/me/provider-keys"
_BUDGET_INVALID_FRAGMENT = "between 0 (exclusive) and 10,000"


def _profile(profile_id: str, **overrides: Any) -> dict[str, Any]:  # noqa: ANN401
    profile: dict[str, Any] = {
        "id": profile_id,
        "kind": "anthropic",
        "model": f"model-{profile_id}",
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


_HOUSE = _profile("house", api_key_env="LEARNY_TEST_HOUSE_KEY")
_CLAUDE = _profile("byok-claude", display_name="Your Claude", user_key_provider="anthropic")
_CLAUDE_ASK = _profile("byok-claude-ask", teach_enabled=False, user_key_provider="anthropic")
_GPT = _profile(
    "byok-gpt",
    kind="openai-compatible",
    grounding="prompt-cited",
    base_url="https://api.openai.com/v1",
    display_name="Your GPT",
    teach_enabled=False,
    user_key_provider="openai",
)


def _declare(
    monkeypatch: pytest.MonkeyPatch, profiles: list[dict[str, Any]], *, kek: bool = True
) -> None:
    monkeypatch.setenv("LEARNY_GENERATION_PROFILES", json.dumps(profiles))
    monkeypatch.setenv("LEARNY_TEST_HOUSE_KEY", "sk-ant-house-operator-key-000000000000")
    if kek:
        monkeypatch.setenv("LEARNY_SECRETS_KEK", base64.b64encode(_KEK).decode())
    else:
        monkeypatch.delenv("LEARNY_SECRETS_KEK", raising=False)
    monkeypatch.delenv("LEARNY_SECRETS_KEK_PREVIOUS", raising=False)
    clear_settings_and_generation_caches()


class _Probe:
    """Records what the test route probed with, and answers a set outcome."""

    def __init__(self) -> None:
        self.outcome = ProbeOutcome(ok=True)
        self.calls: list[tuple[str, str, str]] = []

    def __call__(self, profile: Any, api_key: str) -> ProbeOutcome:  # noqa: ANN401
        self.calls.append((profile.id, profile.base_url, api_key))
        return self.outcome


@pytest.fixture
def probe(auth_client: TestClient) -> Iterator[_Probe]:
    from app.infrastructure.web.provider_keys import get_key_probe

    fake = _Probe()
    auth_client.app.dependency_overrides[get_key_probe] = lambda: fake
    yield fake
    auth_client.app.dependency_overrides.pop(get_key_probe, None)


def _learner(client: TestClient, email: str) -> tuple[UUID, dict[str, str]]:
    user_id = _register(client, email)
    return UUID(user_id), {"X-CSRF-Token": _csrf(client)}


def _put(client: TestClient, headers: dict[str, str], key: Any, provider: str = "anthropic"):  # noqa: ANN202, ANN401
    return client.put(f"{_BASE}/{provider}", json={"api_key": key}, headers=headers)


def _rows(db_conn: Connection, user_id: UUID) -> list[Any]:  # noqa: ANN401
    return db_conn.execute(
        select(user_provider_credentials).where(user_provider_credentials.c.user_id == user_id)
    ).all()


# --- C8: the feature off -----------------------------------------------------------


@pytest.mark.parametrize("off", ["no_kek", "no_binding"])
def test_disabled_feature(
    off: str, auth_client: TestClient, monkeypatch: pytest.MonkeyPatch, probe: _Probe
) -> None:
    if off == "no_kek":
        _declare(monkeypatch, [_HOUSE, _CLAUDE], kek=False)
    else:
        _declare(monkeypatch, [_HOUSE])
    _, headers = _learner(auth_client, f"keys-off-{off}@example.com")

    listed = auth_client.get(_BASE)
    put = _put(auth_client, headers, _KEY)
    tested = auth_client.post(f"{_BASE}/anthropic/test", headers=headers)
    deleted = auth_client.delete(f"{_BASE}/anthropic", headers=headers)

    assert listed.status_code == 200
    assert listed.json() == {
        "enabled": False,
        "hosted": False,
        "providers": [],
        "usage": {
            "period": listed.json()["usage"]["period"],
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd_micros": 0,
            "budget_usd_micros": None,
        },
    }
    assert (put.status_code, tested.status_code, deleted.status_code) == (404, 404, 404)
    assert probe.calls == []


# --- The hosted gate ---------------------------------------------------------------


def test_hosted_without_optin_reads_nothing(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
    probe: _Probe,
) -> None:
    """Hosted and not opted in: the surface reads as off and no credential row is read."""
    import app.infrastructure.learner_keys as learner_keys

    monkeypatch.setenv("LEARNY_HOSTED_INSTANCE", "true")
    monkeypatch.delenv("LEARNY_HOSTED_BYOK_ENABLED", raising=False)
    _declare(monkeypatch, [_HOUSE, _CLAUDE])  # KEK set, a binding exists: only the gate is closed
    built: list[int] = []
    real_repo = learner_keys.SqlAlchemyProviderCredentialRepository

    class _CountingRepo(real_repo):  # noqa: ANN401 — same signature, records construction
        def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
            built.append(1)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(learner_keys, "SqlAlchemyProviderCredentialRepository", _CountingRepo)
    _, headers = _learner(auth_client, "hosted-off@example.com")

    listed = auth_client.get(_BASE)
    put = _put(auth_client, headers, _KEY)
    tested = auth_client.post(f"{_BASE}/anthropic/test", headers=headers)
    deleted = auth_client.delete(f"{_BASE}/anthropic", headers=headers)

    assert listed.status_code == 200
    assert listed.json() == {
        "enabled": False,
        "hosted": True,
        "providers": [],
        "usage": {
            "period": listed.json()["usage"]["period"],
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd_micros": 0,
            "budget_usd_micros": None,
        },
    }
    assert (put.status_code, tested.status_code, deleted.status_code) == (404, 404, 404)
    assert probe.calls == []
    assert built == []  # the gate closed before any credential row was read


def test_hosted_optin_serves_like_selfhost(
    auth_client: TestClient, monkeypatch: pytest.MonkeyPatch, probe: _Probe
) -> None:
    """Both hosted flags on, KEK + binding: the surface serves exactly as a self-host's."""
    monkeypatch.setenv("LEARNY_HOSTED_INSTANCE", "true")
    monkeypatch.setenv("LEARNY_HOSTED_BYOK_ENABLED", "true")
    _declare(monkeypatch, [_HOUSE, _CLAUDE])
    _, headers = _learner(auth_client, "hosted-on@example.com")

    put = _put(auth_client, headers, _KEY)
    body = auth_client.get(_BASE).json()
    tested = auth_client.post(f"{_BASE}/anthropic/test", headers=headers)
    deleted = auth_client.delete(f"{_BASE}/anthropic", headers=headers)

    assert put.status_code == 200
    assert body["enabled"] is True
    assert body["hosted"] is True
    assert [row["provider"] for row in body["providers"]] == ["anthropic"]
    assert body["providers"][0]["configured"] is True
    assert (tested.status_code, tested.json()) == (200, {"ok": True, "reason": None})
    assert deleted.status_code == 204


def test_byok_flag_needs_hosted_declaration(
    auth_client: TestClient, monkeypatch: pytest.MonkeyPatch, probe: _Probe
) -> None:
    """``LEARNY_HOSTED_BYOK_ENABLED`` alone changes nothing: availability stays KEK + binding."""
    monkeypatch.delenv("LEARNY_HOSTED_INSTANCE", raising=False)
    monkeypatch.setenv("LEARNY_HOSTED_BYOK_ENABLED", "true")
    _declare(monkeypatch, [_HOUSE, _CLAUDE])
    _, headers = _learner(auth_client, "selfhost-flag@example.com")

    put = _put(auth_client, headers, _KEY)
    body = auth_client.get(_BASE).json()

    assert put.status_code == 200
    assert body["enabled"] is True
    assert body["hosted"] is False
    assert [row["provider"] for row in body["providers"]] == ["anthropic"]


# --- A request body shapes nothing but the key ---------------------------------------


def test_extra_body_fields_ignored(
    auth_client: TestClient, db_conn: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Extra PUT fields (`base_url`, `model`, ...) never touch what is stored.

    The stored row equals a clean PUT's row in every key-derived column, and no
    column anywhere carries a submitted value other than the key itself.
    """
    _declare(monkeypatch, [_HOUSE, _CLAUDE])
    user_id, headers = _learner(auth_client, "keys-extra@example.com")

    # The baseline: a clean PUT stores exactly the key. Then the same PUT with
    # extra fields must store exactly the same thing.
    plain = _put(auth_client, headers, _KEY)
    clean_rows = _rows(db_conn, user_id)

    evil_url = "http://169.254.169.254/v1"
    extra = auth_client.put(
        f"{_BASE}/anthropic",
        json={"api_key": _KEY, "base_url": evil_url, "model": "evil-model"},
        headers=headers,
    )

    assert plain.status_code == 200, plain.text
    assert extra.status_code == 200, extra.text
    assert extra.json()["last4"] == plain.json()["last4"] == _KEY[-4:]

    extra_rows = _rows(db_conn, user_id)
    assert len(extra_rows) == len(clean_rows) == 1
    # The stored row holds exactly what a clean PUT stores: the same key comes
    # back out of the envelope, and no column carries a submitted extra value.
    repo = SqlAlchemyProviderCredentialRepository(db_conn, SecretsEnvelope(_KEK))
    stored = repo.get(user_id, "anthropic")
    assert stored is not None
    assert stored.last4 == _KEY[-4:]
    assert repo.reveal(stored) == _KEY
    for row in extra_rows:
        for column in row._mapping:
            value = row._mapping[column]
            if isinstance(value, (str, bytes)):
                text = value.decode("utf-8", "ignore") if isinstance(value, bytes) else value
                assert evil_url not in text
                assert "evil-model" not in text


# --- C9: the list -------------------------------------------------------------------


def test_lists_offered_providers_with_powers(
    auth_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _declare(monkeypatch, [_HOUSE, _GPT, _CLAUDE, _CLAUDE_ASK])
    _, headers = _learner(auth_client, "keys-list@example.com")
    assert _put(auth_client, headers, _KEY).status_code == 200

    body = auth_client.get(_BASE).json()

    assert body["enabled"] is True
    assert [row["provider"] for row in body["providers"]] == ["openai", "anthropic"]
    openai, anthropic = body["providers"]
    assert openai == {
        "provider": "openai",
        "label": "OpenAI",
        "configured": False,
        "last4": None,
        "added_at": None,
        "powers": [
            {"profile_id": "byok-gpt", "display_name": "Your GPT", "ask": True, "teach": False}
        ],
        "powers_cards": False,
    }
    assert anthropic["configured"] is True
    assert anthropic["last4"] == _KEY[-4:]
    assert anthropic["added_at"]
    assert anthropic["label"] == "Anthropic"
    assert anthropic["powers"] == [
        {"profile_id": "byok-claude", "display_name": "Your Claude", "ask": True, "teach": True},
        {
            "profile_id": "byok-claude-ask",
            "display_name": "byok-claude-ask",
            "ask": True,
            "teach": False,
        },
    ]
    assert anthropic["powers_cards"] is True


# --- C10: store and replace ---------------------------------------------------------


def test_put_stores_and_replace_mints_new_row(
    auth_client: TestClient, db_conn: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _declare(monkeypatch, [_HOUSE, _CLAUDE])
    user_id, headers = _learner(auth_client, "keys-put@example.com")

    first = _put(auth_client, headers, _KEY)
    first_rows = _rows(db_conn, user_id)
    second = _put(auth_client, headers, _NEW_KEY)
    second_rows = _rows(db_conn, user_id)

    assert first.status_code == 200, first.text
    assert first.json()["configured"] is True
    assert first.json()["last4"] == _KEY[-4:]
    assert second.status_code == 200, second.text
    assert second.json()["last4"] == _NEW_KEY[-4:]
    assert len(first_rows) == 1
    assert len(second_rows) == 1
    assert second_rows[0].id != first_rows[0].id
    repo = SqlAlchemyProviderCredentialRepository(db_conn, SecretsEnvelope(_KEK))
    credential = repo.get(user_id, "anthropic")
    assert credential is not None
    assert repo.reveal(credential) == _NEW_KEY


# --- C11: malformed keys are refused without an echo --------------------------------


@pytest.mark.parametrize(
    ("label", "body"),
    [
        ("missing", {}),
        ("not_a_string", {"api_key": ["sk-ant-api03-in-a-list-QQQQQQQQQQQQ"]}),
        ("whitespace", {"api_key": "sk-ant-api03-has a-space-QQQQQQQQQQQQ"}),
        ("too_short", {"api_key": "sk-ant-QQQQQQQQQQQQ"}),  # 19 characters
        ("too_long", {"api_key": "sk-ant-" + "Q" * 250}),  # 257 characters
        ("no_prefix", {"api_key": "sk-proj-not-anthropic-QQQQQQQQQQQQ"}),
        ("raw_string_body", "sk-ant-api03-raw-string-body-QQQQQQQQQQ"),
    ],
)
def test_malformed_key_422_never_echoes(
    label: str,
    body: Any,  # noqa: ANN401
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _declare(monkeypatch, [_HOUSE, _CLAUDE])
    user_id, headers = _learner(auth_client, f"keys-422-{label.replace('_', '-')}@example.com")

    resp = auth_client.put(f"{_BASE}/anthropic", json=body, headers=headers)

    assert resp.status_code == 422, resp.text
    submitted = body.get("api_key") if isinstance(body, dict) else body
    values = submitted if isinstance(submitted, list) else [submitted]
    for value in values:
        if isinstance(value, str):
            for start in range(0, len(value) - 7):
                assert value[start : start + 8] not in resp.text
    assert "QQQQ" not in resp.text
    assert _rows(db_conn, user_id) == []


@pytest.mark.parametrize("length", [20, 256])
def test_keys_at_the_length_bounds_are_accepted(
    length: int, auth_client: TestClient, db_conn: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _declare(monkeypatch, [_HOUSE, _CLAUDE])
    user_id, headers = _learner(auth_client, f"keys-bound-{length}@example.com")
    key = "sk-ant-" + "K" * (length - len("sk-ant-"))

    resp = _put(auth_client, headers, key)

    assert resp.status_code == 200, resp.text
    assert resp.json()["last4"] == "KKKK"
    assert len(_rows(db_conn, user_id)) == 1


# --- C12: providers this instance does not offer -------------------------------------


@pytest.mark.parametrize("provider", ["gemini", "mistral"])
def test_unoffered_provider_404(
    provider: str, auth_client: TestClient, monkeypatch: pytest.MonkeyPatch, probe: _Probe
) -> None:
    _declare(monkeypatch, [_HOUSE, _CLAUDE])
    _, headers = _learner(auth_client, f"keys-404-{provider}@example.com")

    put = _put(auth_client, headers, "AIzaSyD-route-gemini-key-QQQQQQQQQQQQ", provider)
    tested = auth_client.post(f"{_BASE}/{provider}/test", headers=headers)
    deleted = auth_client.delete(f"{_BASE}/{provider}", headers=headers)

    assert (put.status_code, tested.status_code, deleted.status_code) == (404, 404, 404)
    assert probe.calls == []


# --- C13 / C14: testing a key ---------------------------------------------------------


@pytest.mark.parametrize(
    "outcome",
    [
        ProbeOutcome(ok=True),
        ProbeOutcome(ok=False, reason="rejected"),
        ProbeOutcome(ok=False, reason="rate_limited"),
        ProbeOutcome(ok=False, reason="unavailable"),
    ],
)
def test_test_route_maps_probe_outcomes(
    outcome: ProbeOutcome,
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    probe: _Probe,
) -> None:
    _declare(monkeypatch, [_HOUSE, _GPT, _CLAUDE])
    _, headers = _learner(auth_client, f"keys-test-{outcome.reason or 'ok'}@example.com")
    assert _put(auth_client, headers, _OPENAI_KEY, "openai").status_code == 200
    probe.outcome = outcome

    resp = auth_client.post(f"{_BASE}/openai/test", headers=headers)

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": outcome.ok, "reason": outcome.reason}
    # The stored key, through the bound profile's own host.
    assert probe.calls == [("byok-gpt", "https://api.openai.com/v1", _OPENAI_KEY)]


def test_test_without_key_404(
    auth_client: TestClient, monkeypatch: pytest.MonkeyPatch, probe: _Probe
) -> None:
    _declare(monkeypatch, [_HOUSE, _CLAUDE])
    _, headers = _learner(auth_client, "keys-test-none@example.com")

    resp = auth_client.post(f"{_BASE}/anthropic/test", headers=headers)

    assert resp.status_code == 404
    assert probe.calls == []


# --- C15: delete ----------------------------------------------------------------------


def test_delete_is_idempotent_204(
    auth_client: TestClient, db_conn: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _declare(monkeypatch, [_HOUSE, _CLAUDE])
    user_id, headers = _learner(auth_client, "keys-delete@example.com")
    assert _put(auth_client, headers, _KEY).status_code == 200

    first = auth_client.delete(f"{_BASE}/anthropic", headers=headers)
    rows_after = _rows(db_conn, user_id)
    second = auth_client.delete(f"{_BASE}/anthropic", headers=headers)

    assert first.status_code == 204
    assert rows_after == []
    assert second.status_code == 204
    assert auth_client.get(_BASE).json()["providers"][0]["configured"] is False


def test_replace_and_delete_release_the_cached_adapters(
    auth_client: TestClient, db_conn: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A replaced or deleted key's adapters leave this process's caches at once."""
    from app.infrastructure.answering.user_adapters import UserAdapterKey
    from app.infrastructure.web import dependencies

    _declare(monkeypatch, [_HOUSE, _CLAUDE])
    user_id, headers = _learner(auth_client, "keys-evict@example.com")
    assert _put(auth_client, headers, _KEY).status_code == 200

    def _cache_one() -> str:
        repo = SqlAlchemyProviderCredentialRepository(db_conn, SecretsEnvelope(_KEK))
        credential = repo.get(user_id, "anthropic")
        assert credential is not None
        for cache in (dependencies._user_adapters, dependencies._user_quiz_adapters):
            cache.get_or_build(
                UserAdapterKey("anthropic", "slot", "model", credential.fingerprint), object
            )
        return credential.fingerprint

    replaced = _cache_one()
    assert _put(auth_client, headers, _NEW_KEY).status_code == 200
    deleted = _cache_one()
    assert auth_client.delete(f"{_BASE}/anthropic", headers=headers).status_code == 204

    for cache in (dependencies._user_adapters, dependencies._user_quiz_adapters):
        fingerprints = {key.fingerprint for key in cache.keys()}
        assert replaced not in fingerprints
        assert deleted not in fingerprints


def test_one_learners_routes_never_reach_anothers_key(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
    probe: _Probe,
) -> None:
    _declare(monkeypatch, [_HOUSE, _CLAUDE])
    owner_id, owner_headers = _learner(auth_client, "keys-owner@example.com")
    assert _put(auth_client, owner_headers, _KEY).status_code == 200
    owner_rows = _rows(db_conn, owner_id)

    _, other_headers = _learner(auth_client, "keys-other@example.com")
    listed = auth_client.get(_BASE).json()["providers"][0]
    tested = auth_client.post(f"{_BASE}/anthropic/test", headers=other_headers)
    deleted = auth_client.delete(f"{_BASE}/anthropic", headers=other_headers)

    assert listed["configured"] is False
    assert listed["last4"] is None
    assert tested.status_code == 404  # no key of their own to test
    assert probe.calls == []
    assert deleted.status_code == 204  # idempotent, and it removes nothing of the owner's
    assert _rows(db_conn, owner_id) == owner_rows


# --- C16: CSRF ------------------------------------------------------------------------


def test_writes_require_csrf(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
    probe: _Probe,
) -> None:
    _declare(monkeypatch, [_HOUSE, _CLAUDE])
    user_id, headers = _learner(auth_client, "keys-csrf@example.com")
    assert _put(auth_client, headers, _KEY).status_code == 200
    before = _rows(db_conn, user_id)

    put = _put(auth_client, {}, _NEW_KEY)
    tested = auth_client.post(f"{_BASE}/anthropic/test")
    deleted = auth_client.delete(f"{_BASE}/anthropic")

    assert (put.status_code, tested.status_code, deleted.status_code) == (403, 403, 403)
    assert _rows(db_conn, user_id) == before
    assert probe.calls == []


# --- C17: rate limits -----------------------------------------------------------------


def test_writes_rate_limited_429(
    auth_client: TestClient, monkeypatch: pytest.MonkeyPatch, probe: _Probe
) -> None:
    from app.infrastructure.web.rate_limit import InMemoryFixedWindowRateLimiter, set_rate_limiter

    _declare(monkeypatch, [_HOUSE, _CLAUDE])
    _, headers = _learner(auth_client, "keys-429@example.com")
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=2, window_seconds=300))

    puts = [_put(auth_client, headers, _KEY).status_code for _ in range(3)]
    tests = [
        auth_client.post(f"{_BASE}/anthropic/test", headers=headers).status_code for _ in range(3)
    ]

    assert puts == [200, 200, 429]
    assert tests == [200, 200, 429]
    assert len(probe.calls) == 2


# --- C18: no key material in any response ----------------------------------------------


def test_responses_never_carry_key_material(
    auth_client: TestClient, monkeypatch: pytest.MonkeyPatch, probe: _Probe
) -> None:
    _declare(monkeypatch, [_HOUSE, _CLAUDE])
    _, headers = _learner(auth_client, "keys-leak@example.com")

    bodies = [
        _put(auth_client, headers, _KEY).text,
        auth_client.get(_BASE).text,
        auth_client.post(f"{_BASE}/anthropic/test", headers=headers).text,
        _put(auth_client, headers, _NEW_KEY).text,
        auth_client.get(_BASE).text,
    ]
    probe.outcome = ProbeOutcome(ok=False, reason="rejected")
    bodies.append(auth_client.post(f"{_BASE}/anthropic/test", headers=headers).text)
    bodies.append(auth_client.delete(f"{_BASE}/anthropic", headers=headers).text)
    bodies.append(auth_client.get(_BASE).text)

    for key in (_KEY, _NEW_KEY):
        for start in range(0, len(key) - 7):
            fragment = key[start : start + 8]
            for body in bodies:
                assert fragment not in body, (fragment, body)


# --- C43: a session is required --------------------------------------------------------


def test_routes_require_session_401(
    auth_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _declare(monkeypatch, [_HOUSE, _CLAUDE])
    auth_client.cookies.clear()

    responses = [
        auth_client.get(_BASE),
        _put(auth_client, {"X-CSRF-Token": "x"}, _KEY),
        auth_client.post(f"{_BASE}/anthropic/test", headers={"X-CSRF-Token": "x"}),
        auth_client.delete(f"{_BASE}/anthropic", headers={"X-CSRF-Token": "x"}),
    ]

    assert [resp.status_code for resp in responses] == [401, 401, 401, 401]


# --- The learner's own monthly budget ------------------------------------------------


def _budget_put(
    client: TestClient,
    headers: dict[str, str],
    value: Any,  # noqa: ANN401
) -> Any:  # noqa: ANN401
    return client.put(f"{_BASE}/budget", json={"monthly_budget_usd": value}, headers=headers)


def test_budget_route_stores_clears_and_validates(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
    probe: _Probe,
) -> None:
    """The budget route: 200 store/clear, 422 without an echo, 404/403/429 like siblings."""
    from app.infrastructure.web.rate_limit import InMemoryFixedWindowRateLimiter, set_rate_limiter
    from tests.conftest import clear_settings_and_generation_caches

    _declare(monkeypatch, [_HOUSE, _CLAUDE])
    _, headers = _learner(auth_client, "budget-route@example.com")

    stored = _budget_put(auth_client, headers, 25)
    assert stored.status_code == 200, stored.text
    assert stored.json()["budget_usd_micros"] == 25_000_000
    # Storing twice is one row (a full upsert), not an increment.
    again = _budget_put(auth_client, headers, 25)
    assert again.json() == stored.json()
    # A boundary store at the top of the range.
    top = _budget_put(auth_client, headers, 10_000)
    assert top.status_code == 200, top.text
    assert top.json()["budget_usd_micros"] == 10_000_000_000

    cleared = _budget_put(auth_client, headers, None)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["budget_usd_micros"] is None

    # Invalid input: 422 with fixed copy echoing no submitted value.
    cases = [("zero", 0), ("negative", -5), ("too_big", 10_001), ("text", "ten"), ("bool", True)]
    for label, value in cases:
        bad = _budget_put(auth_client, headers, value)
        assert bad.status_code == 422, (label, bad.text)
        assert _BUDGET_INVALID_FRAGMENT in bad.json()["detail"]
        if str(value) not in _BUDGET_INVALID_FRAGMENT:  # "0" itself is part of the copy
            assert str(value) not in bad.json()["detail"]

    # Feature off (no KEK): 404 like every other write.
    _declare(monkeypatch, [_HOUSE, _CLAUDE], kek=False)
    clear_settings_and_generation_caches()
    off = _budget_put(auth_client, headers, 25)
    assert off.status_code == 404, off.text

    # CSRF: 403 like every sibling write.
    _declare(monkeypatch, [_HOUSE, _CLAUDE])
    no_csrf = _budget_put(auth_client, {}, 25)
    assert no_csrf.status_code == 403

    # Write rate limit: 429 like every sibling write.
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=2, window_seconds=300))
    first = _budget_put(auth_client, headers, 25).status_code
    second = _budget_put(auth_client, headers, 25).status_code
    third = _budget_put(auth_client, headers, 25).status_code
    assert (first, second, third) == (200, 200, 429)


def test_budget_requires_session_401(
    auth_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _declare(monkeypatch, [_HOUSE, _CLAUDE])
    auth_client.cookies.clear()

    resp = auth_client.put(f"{_BASE}/budget", json={"monthly_budget_usd": 25})

    assert resp.status_code == 401


def test_list_reports_usage_and_budget(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The keys list carries the month-to-date usage row and the stored budget."""
    from datetime import UTC, datetime

    from app.infrastructure.db.repositories import (
        SqlAlchemyByokMonthRepository,
        SqlAlchemyUserByokSettingsRepository,
    )

    _declare(monkeypatch, [_HOUSE, _CLAUDE])
    user_id, _headers = _learner(auth_client, "budget-list@example.com")
    period = datetime.now(UTC).strftime("%Y-%m")
    SqlAlchemyByokMonthRepository(db_conn).record(
        user_id,
        period,
        input_tokens=1234,
        output_tokens=567,
        cost_usd_micros=8_900,
    )
    SqlAlchemyUserByokSettingsRepository(db_conn).set_budget(user_id, 2_500_000)

    body = auth_client.get(_BASE).json()

    assert body["usage"] == {
        "period": period,
        "input_tokens": 1234,
        "output_tokens": 567,
        "cost_usd_micros": 8_900,
        "budget_usd_micros": 2_500_000,
    }
