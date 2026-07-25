"""B1 gate — the request middleware feeds the timing recorder (unit, OBS-01/02/07).

Every case derives from the spec's "One timing recorder" acceptance criteria as
they apply to the HTTP producer: what a completed request contributes (route
template, method, status, duration), what an unmatched request contributes (one
constant placeholder, never the raw path), and the containment property — a
recorder that fails must leave the response it measures exactly as it was.

The parametrized-route case is also the framework sensor: the route template is
read from the ASGI ``scope`` the router populates, so if a future Starlette or
FastAPI release stops publishing it, the recorded label degrades to the
placeholder and this file fails rather than silently recording raw paths.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.instrumentation import (
    UNMATCHED_ROUTE,
    InstrumentRecorder,
    get_recorder,
    set_recorder,
)
from app.core.tracing import TraceContextFilter
from app.infrastructure.web.middleware import RequestContextMiddleware

SECRET_ID = "9f1c0e2a-secret-resource"


class _RecordingHandler(logging.Handler):
    """Collect records, self-stamping trace fields via its own filter."""

    def __init__(self) -> None:
        super().__init__(level=logging.NOTSET)
        self.addFilter(TraceContextFilter())
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def captured() -> Iterator[_RecordingHandler]:
    """Attach a recording handler to root; force the access logger enabled."""
    handler = _RecordingHandler()
    root = logging.getLogger()
    root.addHandler(handler)
    previous_level = root.level
    root.setLevel(logging.INFO)
    access = logging.getLogger("app.request")
    access.disabled = False
    access.setLevel(logging.INFO)
    try:
        yield handler
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)


@pytest.fixture
def recorder() -> Iterator[InstrumentRecorder]:
    """Install a fresh recorder for the duration of one test."""
    previous = get_recorder()
    fresh = InstrumentRecorder()
    set_recorder(fresh)
    try:
        yield fresh
    finally:
        set_recorder(previous)


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/items/{item_id}")
    def item(item_id: str) -> dict[str, str]:
        return {"id": item_id}

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


# --- OBS-01: a completed request is recorded by its route template ------------


def test_completed_request_is_recorded_with_template_method_status_and_duration(
    recorder: InstrumentRecorder,
) -> None:
    client = TestClient(_build_app())

    assert client.get(f"/items/{SECRET_ID}").status_code == 200

    (sample,) = recorder.recent_requests()
    assert sample.route == "/items/{item_id}"
    assert sample.method == "GET"
    assert sample.status_code == 200
    assert sample.duration_ms >= 0.0


def test_recorded_route_carries_no_parameter_value_or_query_string(
    recorder: InstrumentRecorder,
) -> None:
    # Invariant 1: the ranking surface has weaker access control than the
    # resources a raw path names, so no identifier may reach it.
    client = TestClient(_build_app())

    client.get(f"/items/{SECRET_ID}?token=super-secret")

    (sample,) = recorder.recent_requests()
    assert SECRET_ID not in sample.route
    assert "super-secret" not in sample.route
    assert "?" not in sample.route


def test_handled_error_is_recorded_with_its_final_status(
    recorder: InstrumentRecorder,
) -> None:
    client = TestClient(_build_app())

    assert client.get("/http-error").status_code == 404

    (sample,) = recorder.recent_requests()
    assert sample.route == "/http-error"
    assert sample.status_code == 404


# --- OBS-02: an unmatched request buckets under the placeholder ---------------


def test_unmatched_request_is_recorded_under_the_constant_placeholder(
    recorder: InstrumentRecorder,
) -> None:
    client = TestClient(_build_app())

    assert client.get(f"/no-such-route/{SECRET_ID}").status_code == 404

    (sample,) = recorder.recent_requests()
    assert sample.route == UNMATCHED_ROUTE
    assert SECRET_ID not in sample.route
    assert sample.status_code == 404


# --- Invariant 2: one measurement, two consumers -----------------------------


def test_recorded_duration_is_the_one_the_access_log_reports(
    recorder: InstrumentRecorder, captured: _RecordingHandler
) -> None:
    client = TestClient(_build_app())

    client.get(f"/items/{SECRET_ID}")

    (sample,) = recorder.recent_requests()
    assert sample.duration_ms == _access_record(captured).duration_ms


# --- OBS-07: the instrument never changes the outcome it measures ------------


def test_a_failing_recorder_leaves_the_response_untouched(
    captured: _RecordingHandler,
) -> None:
    class _BrokenRecorder(InstrumentRecorder):
        def record_request(self, **kwargs: object) -> None:
            raise RuntimeError("recorder exploded")

    previous = get_recorder()
    set_recorder(_BrokenRecorder())
    try:
        client = TestClient(_build_app())
        response = client.get(f"/items/{SECRET_ID}")
    finally:
        set_recorder(previous)

    assert response.status_code == 200
    assert response.json() == {"id": SECRET_ID}
    assert response.headers["X-Request-ID"]
    assert _access_record(captured).status_code == 200


def test_unhandled_exception_is_still_recorded_with_its_final_status(
    recorder: InstrumentRecorder,
) -> None:
    client = TestClient(_build_app(), raise_server_exceptions=False)

    assert client.get("/boom").status_code == 500

    (sample,) = recorder.recent_requests()
    assert sample.route == "/boom"
    assert sample.status_code == 500
