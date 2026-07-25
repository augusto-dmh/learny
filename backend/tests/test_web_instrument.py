"""D1 gate — the dev-only instrument surface (integration, live test DB;
OBS-19..22, OBS-26).

Every case derives from the spec's "The dev-only surface" acceptance criteria:
what the flag decides, what authentication decides, what an enabled and
authenticated read returns, what an idle process returns, and — the gap Phase B
found — that the configured bounds actually govern the recorder the surface
reads, instead of being documented settings that change nothing.

The two gates are exercised independently on purpose. A single test that turned
the flag on *and* authenticated would pass with either gate removed; one test per
gate is what makes each of them a sensor.

The surface renders only what the recorder holds, so "no identifier reaches the
surface" is pinned here as a property of the whole path (a real parametrized
request, a query string, and an unmatched path, read back through the response
body) rather than re-tested as recorder behaviour.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import ExitStack
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.core.instrumentation import get_recorder, set_recorder
from tests.conftest import TEST_ORIGIN, requires_db

pytestmark = requires_db

#: Builds a client over an app assembled with a chosen flag value and environment.
ClientBuilder = Callable[..., TestClient]

INSTRUMENT_PATH = "/api/dev/instrument"

#: Stands in for a resource identifier a raw path would carry into the surface.
SECRET_ID = uuid4()


@pytest.fixture(autouse=True)
def _restore_recorder() -> Iterator[None]:
    """Undo the recorder ``create_app`` installs, so tests stay independent."""
    previous = get_recorder()
    try:
        yield
    finally:
        set_recorder(previous)


@pytest.fixture
def build_client(db_conn: Connection, monkeypatch: pytest.MonkeyPatch) -> Iterator[ClientBuilder]:
    """Build a ``TestClient`` over an app assembled with a chosen environment.

    Mirrors the sibling web fixtures (shared rolled-back ``db_conn``, non-Secure
    cookie, trusted Origin, generous limiter) but defers assembly to the test,
    because the flag and the instrument bounds are read at app-assembly time and
    each case needs a different reading of them.
    """
    from app.core.config import get_settings
    from app.infrastructure.web.dependencies import get_db_connection
    from app.infrastructure.web.rate_limit import (
        InMemoryFixedWindowRateLimiter,
        get_rate_limiter,
        set_rate_limiter,
    )
    from app.main import create_app

    previous_limiter = get_rate_limiter()
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=1000))

    with ExitStack() as stack:

        def _build(*, enabled: bool, **env: str) -> TestClient:
            monkeypatch.setenv("LEARNY_SESSION_COOKIE_SECURE", "false")
            monkeypatch.setenv("LEARNY_CSRF_TRUSTED_ORIGINS", TEST_ORIGIN)
            monkeypatch.setenv("LEARNY_DEV_INSTRUMENT_ENABLED", "true" if enabled else "false")
            for name, value in env.items():
                monkeypatch.setenv(name, value)
            get_settings.cache_clear()

            app = create_app()

            def _override() -> Iterator[Connection]:
                yield db_conn

            app.dependency_overrides[get_db_connection] = _override
            client = stack.enter_context(TestClient(app, headers={"Origin": TEST_ORIGIN}))
            stack.callback(app.dependency_overrides.clear)
            return client

        yield _build

    set_rate_limiter(previous_limiter)
    get_settings.cache_clear()


def _register(client: TestClient, email: str) -> None:
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": "correct horse battery staple"},
    )
    assert resp.status_code == 201, resp.text


# --- OBS-19: the flag decides whether the route exists at all -----------------


def test_surface_is_absent_when_the_flag_is_off(build_client: ClientBuilder) -> None:
    client = build_client(enabled=False)
    _register(client, "instrument-flag-off@example.com")

    assert client.get(INSTRUMENT_PATH).status_code == 404


def test_surface_is_absent_from_the_schema_when_the_flag_is_off(
    build_client: ClientBuilder,
) -> None:
    # An unmounted route is not merely refused — it is not advertised either.
    off = build_client(enabled=False)
    on = build_client(enabled=True)

    assert INSTRUMENT_PATH not in off.get("/openapi.json").json()["paths"]
    assert INSTRUMENT_PATH in on.get("/openapi.json").json()["paths"]


# --- OBS-20: enabling it does not remove the need to authenticate -------------


def test_enabled_surface_still_requires_a_session(build_client: ClientBuilder) -> None:
    client = build_client(enabled=True)
    client.cookies.clear()

    assert client.get(INSTRUMENT_PATH).status_code == 401


# --- OBS-21: enabled + authenticated returns the two rankings -----------------


def test_authenticated_read_returns_ranked_endpoints_and_slow_queries(
    build_client: ClientBuilder,
) -> None:
    client = build_client(enabled=True)
    _register(client, "instrument-read@example.com")
    get_recorder().record_query(statement="SELECT pg_sleep(4)", duration_ms=4000.0)

    resp = client.get(INSTRUMENT_PATH)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    ranked = {(row["method"], row["route"]) for row in body["endpoints"]}
    assert ("POST", "/api/auth/register") in ranked
    row = next(r for r in body["endpoints"] if r["route"] == "/api/auth/register")
    assert row["count"] >= 1
    assert row["max_ms"] >= 0.0
    assert row["p95_ms"] >= 0.0
    assert row["mean_ms"] >= 0.0
    assert body["slow_queries"] == [{"statement": "SELECT pg_sleep(4)", "duration_ms": 4000.0}]


def test_response_states_that_it_covers_one_process_only(build_client: ClientBuilder) -> None:
    # A partial view read as a total one is worse than no view at all: the payload
    # itself must say what it leaves out (AD-171), not only a runbook.
    client = build_client(enabled=True)
    _register(client, "instrument-scope@example.com")

    scope = client.get(INSTRUMENT_PATH).json()["scope"]

    lowered = scope.lower()
    assert "process" in lowered
    assert "worker" in lowered
    assert "restart" in lowered


# --- OBS-22: an idle process is a 200, not an error ---------------------------


def test_idle_process_returns_empty_collections(build_client: ClientBuilder) -> None:
    client = build_client(enabled=True)
    _register(client, "instrument-idle@example.com")
    # Assembly and registration have already been recorded; clear the buffers so
    # the read observes a genuinely empty recorder.
    get_recorder().reset()

    resp = client.get(INSTRUMENT_PATH)

    assert resp.status_code == 200, resp.text
    assert resp.json()["endpoints"] == []
    assert resp.json()["slow_queries"] == []


# --- Invariant: no identifier reaches the surface -----------------------------


def test_surface_exposes_no_path_parameter_query_string_or_raw_path(
    build_client: ClientBuilder,
) -> None:
    client = build_client(enabled=True)
    _register(client, "instrument-redaction@example.com")
    client.get(f"/api/sources/{SECRET_ID}?token=super-secret")
    client.get(f"/no-such-route/{SECRET_ID}")

    body = client.get(INSTRUMENT_PATH).text

    assert str(SECRET_ID) not in body
    assert "super-secret" not in body
    assert "/api/sources/{source_id}" in body


# --- OBS-26: the configured bounds govern the recorder the surface reads ------


def test_configured_capacity_bounds_what_the_surface_returns(build_client: ClientBuilder) -> None:
    # With the setting ignored the recorder would keep its 500-sample default and
    # all five entries would come back, so this fails unless create_app builds the
    # recorder from LEARNY_INSTRUMENT_CAPACITY.
    client = build_client(enabled=True, LEARNY_INSTRUMENT_CAPACITY="2")
    _register(client, "instrument-capacity@example.com")
    for index in range(5):
        get_recorder().record_query(statement=f"SELECT {index}", duration_ms=1000.0)

    slow_queries = client.get(INSTRUMENT_PATH).json()["slow_queries"]

    assert [entry["statement"] for entry in slow_queries] == ["SELECT 4", "SELECT 3"]


def test_configured_statement_cap_truncates_what_the_surface_returns(
    build_client: ClientBuilder,
) -> None:
    # Same shape for the second bound: the 2000-char default would return the
    # statement whole, so a passing assertion here means the setting is live.
    client = build_client(enabled=True, LEARNY_SLOW_QUERY_STATEMENT_CHARS="10")
    _register(client, "instrument-cap@example.com")
    get_recorder().record_query(statement="SELECT " + "x" * 100, duration_ms=1000.0)

    (entry,) = client.get(INSTRUMENT_PATH).json()["slow_queries"]

    assert entry["statement"] == "SELECT xxx"


def test_reported_capacity_is_the_configured_one(build_client: ClientBuilder) -> None:
    client = build_client(enabled=True, LEARNY_INSTRUMENT_CAPACITY="7")
    _register(client, "instrument-reported-capacity@example.com")

    assert client.get(INSTRUMENT_PATH).json()["capacity"] == 7


# --- Existing behaviour: mounting the surface adds a route and removes none ---


def test_enabling_the_surface_adds_exactly_one_route(build_client: ClientBuilder) -> None:
    off = build_client(enabled=False)
    on = build_client(enabled=True)

    off_paths = set(off.get("/openapi.json").json()["paths"])
    on_paths = set(on.get("/openapi.json").json()["paths"])

    assert on_paths - off_paths == {INSTRUMENT_PATH}
    assert off_paths - on_paths == set()
