"""The interface-language choice surface (live DB): ``PUT/DELETE /api/me/locale``
and the ``locale`` field on ``GET /api/auth/me``."""

from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.infrastructure.db.repositories import SqlAlchemyLocalePreferenceRepository
from tests.conftest import TEST_PASSWORD, requires_db

pytestmark = requires_db


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


def _put(client: TestClient, locale: str, csrf: str | None = None):
    headers = {"X-CSRF-Token": csrf} if csrf is not None else {}
    return client.put("/api/me/locale", json={"locale": locale}, headers=headers)


def test_put_stores_and_replaces_the_choice(auth_client: TestClient, db_conn: Connection) -> None:
    client = auth_client
    user_id = _register(client, "chooser-locale@example.com")
    csrf = _csrf(client)

    stored = _put(client, "pt-BR", csrf)
    assert stored.status_code == 200, stored.text
    assert stored.json() == {"locale": "pt-BR"}
    assert client.get("/api/auth/me").json()["locale"] == "pt-BR"

    replaced = _put(client, "en", csrf)
    assert replaced.status_code == 200, replaced.text
    assert replaced.json() == {"locale": "en"}
    assert client.get("/api/auth/me").json()["locale"] == "en"
    row = SqlAlchemyLocalePreferenceRepository(db_conn).get_by_user(UUID(user_id))
    assert row is not None and row.locale == "en"


def test_put_rejects_unsupported_locale(auth_client: TestClient, db_conn: Connection) -> None:
    client = auth_client
    user_id = _register(client, "typo-locale@example.com")
    csrf = _csrf(client)
    assert _put(client, "pt-BR", csrf).status_code == 200

    for bad in ("fr", "pt", "", "PT-BR", "en-US"):
        refused = _put(client, bad, csrf)
        assert refused.status_code == 422, (bad, refused.text)
    # A refused put persists nothing: the previous choice survives.
    row = SqlAlchemyLocalePreferenceRepository(db_conn).get_by_user(UUID(user_id))
    assert row is not None and row.locale == "pt-BR"
    assert client.get("/api/auth/me").json()["locale"] == "pt-BR"


def test_mutations_need_session_and_csrf(auth_client: TestClient, db_conn: Connection) -> None:
    client = auth_client
    # No session yet: 401 before anything else.
    assert client.put("/api/me/locale", json={"locale": "pt-BR"}).status_code == 401
    assert client.delete("/api/me/locale").status_code == 401

    user_id = _register(client, "csrfless-locale@example.com")
    _csrf(client)
    assert _put(client, "pt-BR").status_code == 403
    assert client.delete("/api/me/locale").status_code == 403
    # The refused writes persisted nothing.
    assert SqlAlchemyLocalePreferenceRepository(db_conn).get_by_user(UUID(user_id)) is None


def test_delete_is_idempotent(auth_client: TestClient) -> None:
    client = auth_client
    _register(client, "unsetter-locale@example.com")
    csrf = _csrf(client)
    assert _put(client, "pt-BR", csrf).status_code == 200

    first = client.delete("/api/me/locale", headers={"X-CSRF-Token": csrf})
    assert first.status_code == 204, first.text
    assert client.get("/api/auth/me").json()["locale"] is None
    # Nothing stored any more: still a 204, not an error.
    second = client.delete("/api/me/locale", headers={"X-CSRF-Token": csrf})
    assert second.status_code == 204, second.text


def test_me_reports_the_stored_locale(auth_client: TestClient, db_conn: Connection) -> None:
    client = auth_client
    user_id = _register(client, "me-locale@example.com")
    csrf = _csrf(client)
    repo = SqlAlchemyLocalePreferenceRepository(db_conn)

    assert client.get("/api/auth/me").json()["locale"] is None  # unset

    assert _put(client, "en", csrf).status_code == 200
    assert client.get("/api/auth/me").json()["locale"] == "en"
    assert _put(client, "pt-BR", csrf).status_code == 200
    assert client.get("/api/auth/me").json()["locale"] == "pt-BR"

    # A value that is no longer supported reads as unset and is not rewritten.
    repo.upsert(UUID(user_id), "fr")
    assert client.get("/api/auth/me").json()["locale"] is None
    row = repo.get_by_user(UUID(user_id))
    assert row is not None and row.locale == "fr"


def test_preferences_are_isolated_per_learner(auth_client: TestClient, db_conn: Connection) -> None:
    client = auth_client
    first_id = _register(client, "first-locale@example.com")
    csrf = _csrf(client)
    assert _put(client, "pt-BR", csrf).status_code == 200

    # A second account, same client: its own preference is separate.
    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    second_id = _register(client, "second-locale@example.com")
    second_csrf = _csrf(client)
    assert client.get("/api/auth/me").json()["locale"] is None
    assert _put(client, "en", second_csrf).status_code == 200
    assert client.delete("/api/me/locale", headers={"X-CSRF-Token": second_csrf}).status_code == 204

    repo = SqlAlchemyLocalePreferenceRepository(db_conn)
    survivor = repo.get_by_user(UUID(first_id))
    assert survivor is not None and survivor.locale == "pt-BR"
    assert repo.get_by_user(UUID(second_id)) is None
