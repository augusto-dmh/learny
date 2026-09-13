"""The learner-facing AI-profile surface — catalog and choice (live DB).

Exercises the two new resources end to end through FastAPI against a real
Postgres:

- The catalog (``GET /api/ai/profiles``) is the declared registry with its
  honest copy, in registry order — and it is a pure function of the current
  settings: an undeclared registry is an empty catalog (the synthetic legacy
  seed never appears), and redeclaring the registry env changes the catalog on
  the next request in the same process.
- The choice (``GET/PUT/DELETE /api/me/ai-profile``) reads, stores, replaces,
  and unsets the caller's single preference row; an unknown id is a 422 naming
  the problem and persists nothing; the unset is an idempotent 204.
- ``MeResponse`` carries the stored id as stored (null when unset, stale ids
  never rewritten), and every endpoint rejects an unauthenticated caller with
  401 while the writes refuse a missing CSRF token with 403.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.infrastructure.db.repositories import SqlAlchemyAiPreferenceRepository
from tests.conftest import TEST_PASSWORD, clear_settings_and_generation_caches, requires_db

pytestmark = requires_db

# A declared two-profile registry: "primary" (no copy — the fallback path) and
# the economy tier with its honest copy and teach-ineligibility. Both local
# adapters so the suite stays offline.
_COPIED_PROFILES_JSON = (
    '[{"id": "primary", "kind": "local", "model": "m", "max_tokens": 1, '
    '"price_input_usd_per_million_tokens": 3.0, "price_output_usd_per_million_tokens": 15.0, '
    '"price_cache_read_usd_per_million_tokens": 0.3, '
    '"price_cache_creation_usd_per_million_tokens": 3.75, "grounding": "verified-spans", '
    '"ask_enabled": true, "teach_enabled": true},'
    '{"id": "cheap", "kind": "local", "model": "m", "max_tokens": 1, '
    '"price_input_usd_per_million_tokens": 0.2, "price_output_usd_per_million_tokens": 1.0, '
    '"price_cache_read_usd_per_million_tokens": 0.02, '
    '"price_cache_creation_usd_per_million_tokens": 0.25, "grounding": "prompt-cited", '
    '"ask_enabled": true, "teach_enabled": false, '
    '"display_name": "Economy", "description": "Cheaper answers; citations may be less precise."}]'
)
# A different registry, for the same-process redeclaration sensor.
_SOLO_PROFILES_JSON = (
    '[{"id": "solo", "kind": "local", "model": "m", "max_tokens": 1, '
    '"price_input_usd_per_million_tokens": 3.0, "price_output_usd_per_million_tokens": 15.0, '
    '"price_cache_read_usd_per_million_tokens": 0.3, '
    '"price_cache_creation_usd_per_million_tokens": 3.75, "grounding": "verified-spans", '
    '"ask_enabled": true, "teach_enabled": true}]'
)


def _declare_registry(monkeypatch: pytest.MonkeyPatch, profiles_json: str) -> None:
    """Declare a registry for this test and reset the settings-derived caches."""
    monkeypatch.setenv("LEARNY_GENERATION_PROFILES", profiles_json)
    clear_settings_and_generation_caches()


def _register(client: TestClient, email: str) -> str:
    resp = client.post(
        "/api/auth/register", json={"email": email, "password": TEST_PASSWORD, "accepted_tos": True}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _csrf(client: TestClient) -> str:
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200, resp.text
    return resp.json()["csrf_token"]


def _put(client: TestClient, profile_id: str, csrf: str | None = None):
    headers = {"X-CSRF-Token": csrf} if csrf is not None else {}
    return client.put("/api/me/ai-profile", json={"profile_id": profile_id}, headers=headers)


# --- The catalog (declared registry, honest copy, no seed) ------------------------


def test_the_catalog_lists_declared_profiles_with_honest_copy(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _declare_registry(monkeypatch, _COPIED_PROFILES_JSON)
    client = auth_client
    _register(client, "catalog-reader@example.com")

    resp = client.get("/api/ai/profiles")

    assert resp.status_code == 200, resp.text
    catalog = resp.json()
    assert [entry["id"] for entry in catalog] == ["primary", "cheap"]  # registry order
    # Empty copy falls back honestly: the id names it, no invented description.
    assert catalog[0]["display_name"] == "primary"
    assert catalog[0]["description"] == ""
    assert catalog[0]["grounding"] == "verified-spans"
    assert catalog[0]["ask_enabled"] is True
    assert catalog[0]["teach_enabled"] is True
    # Declared copy and eligibility travel with the profile.
    assert catalog[1]["display_name"] == "Economy"
    assert catalog[1]["description"] == "Cheaper answers; citations may be less precise."
    assert catalog[1]["grounding"] == "prompt-cited"
    assert catalog[1]["teach_enabled"] is False
    # Nothing operational leaks: no adapter kind, key env-var name, base URL,
    # price, or token budget.
    assert set(catalog[0]) == {
        "id",
        "display_name",
        "description",
        "grounding",
        "ask_enabled",
        "teach_enabled",
    }


def test_an_undeclared_registry_is_an_empty_catalog(
    auth_client: TestClient,
) -> None:
    """Nothing declared → nothing selectable: the synthetic legacy seed is the
    operator default, never a catalog entry."""
    client = auth_client
    _register(client, "empty-catalog@example.com")

    resp = client.get("/api/ai/profiles")

    assert resp.status_code == 200, resp.text
    assert resp.json() == []


def test_the_catalog_tracks_a_redeclared_registry_in_the_same_process(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _declare_registry(monkeypatch, _COPIED_PROFILES_JSON)
    client = auth_client
    _register(client, "redeclared@example.com")

    first = client.get("/api/ai/profiles")
    assert [entry["id"] for entry in first.json()] == ["primary", "cheap"]

    _declare_registry(monkeypatch, _SOLO_PROFILES_JSON)
    second = client.get("/api/ai/profiles")

    assert [entry["id"] for entry in second.json()] == ["solo"]


# --- The choice: read, store, replace, unset --------------------------------------


def test_an_unset_choice_reads_null_and_me_reports_null(
    auth_client: TestClient,
) -> None:
    client = auth_client
    _register(client, "unset-choice@example.com")

    choice = client.get("/api/me/ai-profile")
    me = client.get("/api/auth/me")

    assert choice.status_code == 200, choice.text
    assert choice.json() == {"profile_id": None}
    assert me.status_code == 200, me.text
    assert me.json()["ai_profile_id"] is None


def test_put_stores_replaces_and_me_carries_the_choice(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _declare_registry(monkeypatch, _COPIED_PROFILES_JSON)
    client = auth_client
    _register(client, "chooser@example.com")
    csrf = _csrf(client)

    stored = _put(client, "primary", csrf)
    assert stored.status_code == 200, stored.text
    assert stored.json() == {"profile_id": "primary"}
    assert client.get("/api/me/ai-profile").json() == {"profile_id": "primary"}
    assert client.get("/api/auth/me").json()["ai_profile_id"] == "primary"

    # A re-put replaces the previous choice on the single row.
    replaced = _put(client, "cheap", csrf)
    assert replaced.status_code == 200, replaced.text
    assert replaced.json() == {"profile_id": "cheap"}
    assert client.get("/api/me/ai-profile").json() == {"profile_id": "cheap"}
    assert client.get("/api/auth/me").json()["ai_profile_id"] == "cheap"


def test_a_put_with_an_unknown_id_is_a_422_naming_the_problem_and_persists_nothing(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _declare_registry(monkeypatch, _COPIED_PROFILES_JSON)
    client = auth_client
    _register(client, "typo@example.com")
    csrf = _csrf(client)
    assert _put(client, "primary", csrf).status_code == 200

    refused = _put(client, "ghost-profile", csrf)

    assert refused.status_code == 422, refused.text
    assert "ghost-profile" in refused.json()["detail"]
    # The previous choice survives untouched: a refused put persists nothing.
    assert client.get("/api/me/ai-profile").json() == {"profile_id": "primary"}
    assert client.get("/api/auth/me").json()["ai_profile_id"] == "primary"


def test_delete_unsets_and_is_idempotent(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _declare_registry(monkeypatch, _COPIED_PROFILES_JSON)
    client = auth_client
    _register(client, "unsetter@example.com")
    csrf = _csrf(client)
    assert _put(client, "cheap", csrf).status_code == 200

    first = client.delete("/api/me/ai-profile", headers={"X-CSRF-Token": csrf})
    assert first.status_code == 204, first.text
    assert client.get("/api/me/ai-profile").json() == {"profile_id": None}
    assert client.get("/api/auth/me").json()["ai_profile_id"] is None

    # Unsetting again is still a 204, not an error.
    second = client.delete("/api/me/ai-profile", headers={"X-CSRF-Token": csrf})
    assert second.status_code == 204, second.text


def test_a_stale_stored_id_is_returned_as_stored(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An operator edit that removes a stored profile id never rewrites the
    learner's row: the id is reported as stored everywhere, and the catalog
    simply does not offer it (serving falls back to the default)."""
    _declare_registry(monkeypatch, _COPIED_PROFILES_JSON)
    client = auth_client
    user_id = _register(client, "stale@example.com")
    SqlAlchemyAiPreferenceRepository(db_conn).upsert(UUID(user_id), "removed-profile")

    choice = client.get("/api/me/ai-profile")
    me = client.get("/api/auth/me")
    catalog_ids = [entry["id"] for entry in client.get("/api/ai/profiles").json()]

    assert choice.json() == {"profile_id": "removed-profile"}
    assert me.json()["ai_profile_id"] == "removed-profile"
    assert "removed-profile" not in catalog_ids


# --- The rails: 401 unauthenticated everywhere, 403 for a tokenless write ----------


def test_unauthenticated_callers_are_rejected_on_every_endpoint(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _declare_registry(monkeypatch, _COPIED_PROFILES_JSON)
    client = auth_client  # no session registered yet

    assert client.get("/api/ai/profiles").status_code == 401
    assert client.get("/api/me/ai-profile").status_code == 401
    assert client.put("/api/me/ai-profile", json={"profile_id": "primary"}).status_code == 401
    assert client.delete("/api/me/ai-profile").status_code == 401


def test_the_writes_refuse_a_missing_csrf_token(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _declare_registry(monkeypatch, _COPIED_PROFILES_JSON)
    client = auth_client
    user_id = _register(client, "csrfless@example.com")
    _csrf(client)

    tokenless_put = _put(client, "primary")
    tokenless_delete = client.delete("/api/me/ai-profile")

    assert tokenless_put.status_code == 403, tokenless_put.text
    assert tokenless_delete.status_code == 403, tokenless_delete.text
    # The refused writes persisted nothing.
    assert SqlAlchemyAiPreferenceRepository(db_conn).get_by_user(UUID(user_id)) is None
