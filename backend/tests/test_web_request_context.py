"""A3 gate — request-context middleware + user_id binding (unit, PROD-07..11/18/19).

Drives a minimal app wrapped in ``RequestContextMiddleware`` (no DB) and asserts:
- a request id is generated when absent, echoed when present, sanitized when unsafe;
- log records emitted during a request carry ``request_id``;
- exactly one ``http.request`` access record carries method/path/status/duration;
- handled errors keep the header + access log; unhandled 500s still access-log.

``user_id`` binding (PROD-10) is verified directly at its seam, ``resolve_current``.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.tracing import (
    TraceContextFilter,
    current_trace,
    new_trace_scope,
    reset_trace,
)
from app.infrastructure.web.middleware import RequestContextMiddleware


class _RecordingHandler(logging.Handler):
    """Collect records, self-stamping trace fields via its own filter."""

    def __init__(self) -> None:
        super().__init__(level=logging.NOTSET)
        self.addFilter(TraceContextFilter())
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def captured():  # noqa: ANN201
    """Attach a recording handler to root; force our loggers enabled."""
    handler = _RecordingHandler()
    root = logging.getLogger()
    root.addHandler(handler)
    previous_level = root.level
    root.setLevel(logging.INFO)
    for name in ("app.request", "test.route"):
        lg = logging.getLogger(name)
        lg.disabled = False
        lg.setLevel(logging.INFO)
    try:
        yield handler
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/ping")
    def ping() -> dict[str, bool]:
        logging.getLogger("test.route").info("in-handler")
        return {"ok": True}

    @app.get("/http-error")
    def http_error() -> None:
        raise HTTPException(status_code=404, detail="nope")

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("kaboom")

    return app


def _access_record(handler: _RecordingHandler) -> logging.LogRecord:
    hits = [r for r in handler.records if r.getMessage() == "http.request"]
    assert len(hits) == 1, f"expected one access record, got {len(hits)}"
    return hits[0]


def test_generates_request_id_when_absent(captured: _RecordingHandler) -> None:
    client = TestClient(_build_app())
    resp = client.get("/ping")
    assert resp.status_code == 200
    rid = resp.headers["X-Request-ID"]
    assert rid  # non-empty generated id
    # The in-handler record carries the same request id.
    handler_rec = next(r for r in captured.records if r.getMessage() == "in-handler")
    assert handler_rec.request_id == rid


def test_echoes_inbound_request_id(captured: _RecordingHandler) -> None:
    client = TestClient(_build_app())
    resp = client.get("/ping", headers={"X-Request-ID": "abc-123"})
    assert resp.headers["X-Request-ID"] == "abc-123"


def test_sanitizes_unsafe_inbound_request_id(captured: _RecordingHandler) -> None:
    client = TestClient(_build_app())
    # Newline + overly long: unsafe chars stripped, length bounded to 128.
    raw = "bad\nid " + "x" * 300
    resp = client.get("/ping", headers={"X-Request-ID": raw})
    echoed = resp.headers["X-Request-ID"]
    assert "\n" not in echoed and " " not in echoed
    assert echoed == ("badid" + "x" * 300)[:128]


def test_access_log_has_method_path_status_duration(captured: _RecordingHandler) -> None:
    client = TestClient(_build_app())
    client.get("/ping")
    rec = _access_record(captured)
    assert rec.method == "GET"
    assert rec.path == "/ping"
    assert rec.status_code == 200
    assert isinstance(rec.duration_ms, float)
    assert rec.duration_ms >= 0.0


def test_handled_error_keeps_header_and_access_log(captured: _RecordingHandler) -> None:
    client = TestClient(_build_app())
    resp = client.get("/http-error")
    assert resp.status_code == 404
    assert resp.headers["X-Request-ID"]  # produced inside the middleware
    rec = _access_record(captured)
    assert rec.status_code == 404
    assert rec.path == "/http-error"


def test_unhandled_exception_still_access_logs_500(captured: _RecordingHandler) -> None:
    client = TestClient(_build_app(), raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 500
    rec = _access_record(captured)
    assert rec.status_code == 500
    assert rec.path == "/boom"


def test_resolve_current_binds_user_id() -> None:
    """PROD-10: resolving an authenticated principal binds user_id into trace."""
    from app.infrastructure.web.dependencies import resolve_current

    uid = uuid4()
    user = SimpleNamespace(id=uid)
    session = SimpleNamespace(id=uuid4())
    settings = SimpleNamespace(session_cookie_name="learny_session")
    request = SimpleNamespace(cookies={"learny_session": "tok"})

    def fake_current_user(*, raw_token: str | None):  # noqa: ANN202 — CurrentUser is callable
        assert raw_token == "tok"
        return user, session

    token = new_trace_scope()
    try:
        result = resolve_current(request, settings, fake_current_user)
        assert result == (user, session)
        assert current_trace()["user_id"] == str(uid)
    finally:
        reset_trace(token)
