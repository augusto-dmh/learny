"""The pre-unification question and teaching surface is gone (integration + unit).

The compatibility layer existed so the release that unified conversations was
invisible to the panels of the day. Those panels now speak ``/api/conversations``,
so the layer is deleted outright rather than deprecated — there is no external
consumer to owe a window to.

Deleting a wire is only half the claim: a router that is still constructed but no
longer included would leave the modules in the tree and the endpoints one line from
returning. So both halves are asserted — the paths answer 404 for a caller who owns
everything they name, and the modules are not importable at all.

The settings those surfaces were tuned by retire with them, and there the required
behaviour is the opposite: an environment that still carries them must boot, so that
a machine restarted after this change comes back up rather than failing on a
variable that no longer means anything.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.domain.entities import Source
from app.infrastructure.db.repositories import SqlAlchemySourceRepository
from tests.conftest import TEST_PASSWORD, declared_routes, requires_db

#: Modules that only ever existed to keep the retired wires speaking — the two
#: routers, the presenter that collapsed the scoped verdict for them, and the
#: application adapters that translated their vocabulary onto the unified services.
RETIRED_MODULES = (
    "app.infrastructure.web.teaching",
    "app.infrastructure.web.questions",
    "app.infrastructure.web.legacy_status",
    "app.application.teaching",
    "app.application.qa",
)


def _retired_paths(source_id: str, session_id: str) -> list[tuple[str, str]]:
    return [
        ("POST", "/api/teaching-sessions"),
        ("GET", f"/api/teaching-sessions/{session_id}"),
        ("POST", f"/api/teaching-sessions/{session_id}/turns"),
        ("POST", f"/api/teaching-sessions/{session_id}/turns/stream"),
        ("GET", f"/api/sources/{source_id}/teaching-sessions"),
        ("POST", f"/api/sources/{source_id}/questions"),
        ("POST", f"/api/sources/{source_id}/questions/stream"),
    ]


def test_no_retired_module_is_importable() -> None:
    # The strongest form of "deleted": not merely unrouted, but absent. A module
    # left behind is a router one ``include_router`` line from being live again.
    for module in RETIRED_MODULES:
        assert importlib.util.find_spec(module) is None, module


def test_the_app_declares_no_route_on_a_retired_path() -> None:
    # Read off the assembled application rather than a list of URLs, so a route
    # re-added under any of these shapes is caught wherever it is declared.
    from app.main import create_app

    templates = [route.path for route in declared_routes(create_app())]

    assert templates, "the route inventory must not be empty, or this proves nothing"
    assert not [path for path in templates if "teaching-sessions" in path]
    assert not [path for path in templates if path.endswith(("/questions", "/questions/stream"))]


def test_no_throttle_outlives_the_routes_it_guarded() -> None:
    # A limiter dependency that no route depends on is the quietest residue a
    # retirement can leave: it imports, it is covered by its own unit test, and it
    # throttles nothing. Worse, its name still advertises a wire that answers 404,
    # so a reader looking for how questions are throttled finds a live-looking
    # answer. Every throttle the module offers must be reachable from a route of
    # the assembled app, which also means a new one cannot ship unwired.
    from app.infrastructure.web import rate_limit
    from app.main import create_app

    def _dependency_calls(dependant: object) -> set[object]:
        calls = {getattr(dependant, "call", None)}
        for sub in getattr(dependant, "dependencies", []):
            calls |= _dependency_calls(sub)
        return calls

    wired: set[object] = set()
    for route in declared_routes(create_app()):
        dependant = getattr(route, "dependant", None)
        if dependant is not None:
            wired |= _dependency_calls(dependant)

    offered = {
        getattr(rate_limit, name) for name in dir(rate_limit) if name.startswith("rate_limit_")
    }
    assert offered, "the module must offer throttles, or this proves nothing"
    assert offered <= wired, f"unwired throttles: {sorted(t.__name__ for t in offered - wired)}"


def test_the_app_boots_with_every_retired_variable_still_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Retiring a knob must never take a deployment down on the next restart: a
    # machine whose environment file still carries all three comes up and serves.
    from app.core.config import get_settings
    from app.main import create_app

    for name in ("LEARNY_QA_EVIDENCE_TOP_K", "LEARNY_TEACHING_EVIDENCE_TOP_K"):
        monkeypatch.setenv(name, "12")
    monkeypatch.setenv("LEARNY_TEACHING_HISTORY_TURNS", "12")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            resp = client.get("/healthz")
    finally:
        get_settings.cache_clear()

    assert resp.status_code == 200, resp.text


@requires_db
def test_every_retired_path_answers_404_to_its_owner(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # A 404 from a missing source would prove nothing, so the source named here is
    # one the caller owns and could still ask about through /api/conversations.
    registered = auth_client.post(
        "/api/auth/register",
        json={"email": "retired@example.com", "password": TEST_PASSWORD},
    )
    assert registered.status_code == 201, registered.text
    user_id = registered.json()["id"]
    csrf = auth_client.get("/api/auth/me").json()["csrf_token"]

    now = datetime.now(UTC)
    source = SqlAlchemySourceRepository(db_conn).add(
        Source(
            id=uuid4(),
            user_id=UUID(user_id),
            title="A Book",
            filename="a-book.epub",
            content_type="application/epub+zip",
            byte_size=1024,
            checksum="d" * 64,
            object_key=f"sources/{user_id}/{uuid4()}.epub",
            status="ready",
            created_at=now,
            updated_at=now,
        )
    )

    # One body carrying every field the retired wires ever wanted, so no path can
    # answer 404 merely because its request was malformed.
    body = {
        "source_id": str(source.id),
        "target_anchor": "a",
        "question": "q",
        "message": "m",
    }
    for method, path in _retired_paths(str(source.id), str(uuid4())):
        resp = auth_client.request(
            method,
            path,
            json=body if method == "POST" else None,
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 404, f"{method} {path} -> {resp.status_code}"
