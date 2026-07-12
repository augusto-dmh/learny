"""A1 gate — request/task trace context (unit, PROD-18/20).

Proves the trace store, the request-id sanitizer, and the ``TraceContextFilter``:
- sanitize bounds length + charset and maps empty→None (PROD-18);
- the filter stamps the current scope's fields onto a record (PROD-09 mechanism);
- the filter is a no-op outside any scope and scopes do not bleed (PROD-20);
- ``bind_trace`` after a scope starts is visible via ``current_trace``.
"""

from __future__ import annotations

import logging

from app.core.tracing import (
    TraceContextFilter,
    bind_trace,
    current_trace,
    new_request_id,
    new_trace_scope,
    reset_trace,
    sanitize_request_id,
)


def _record(**extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="event",
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_sanitize_request_id_truncates_to_128() -> None:
    long = "a" * 500
    assert sanitize_request_id(long) == "a" * 128


def test_sanitize_request_id_strips_unsafe_chars() -> None:
    # Newline / space / quote would allow log injection — must be removed.
    assert sanitize_request_id("ab c\nd\te\"f/g") == "abcdefg"


def test_sanitize_request_id_empty_and_none_yield_none() -> None:
    assert sanitize_request_id(None) is None
    assert sanitize_request_id("") is None
    assert sanitize_request_id("   ") is None
    # Left empty after stripping unsafe chars.
    assert sanitize_request_id("///") is None


def test_new_request_id_is_hex_and_unique() -> None:
    a, b = new_request_id(), new_request_id()
    assert a != b
    assert sanitize_request_id(a) == a  # already safe charset


def test_filter_stamps_current_scope_fields() -> None:
    token = new_trace_scope()
    try:
        bind_trace(request_id="req-1", user_id="u-1")
        rec = _record()
        assert TraceContextFilter().filter(rec) is True
        assert rec.request_id == "req-1"
        assert rec.user_id == "u-1"
    finally:
        reset_trace(token)


def test_filter_does_not_overwrite_existing_record_attr() -> None:
    token = new_trace_scope()
    try:
        bind_trace(request_id="from-scope")
        rec = _record(request_id="explicit")
        TraceContextFilter().filter(rec)
        assert rec.request_id == "explicit"
    finally:
        reset_trace(token)


def test_filter_is_noop_outside_scope() -> None:
    rec = _record()
    assert TraceContextFilter().filter(rec) is True
    assert not hasattr(rec, "request_id")
    assert current_trace() == {}


def test_scopes_do_not_bleed() -> None:
    token = new_trace_scope()
    bind_trace(request_id="first")
    reset_trace(token)
    # After reset, a new scope starts empty — the first scope's field is gone.
    token2 = new_trace_scope()
    try:
        assert current_trace() == {}
        bind_trace(request_id="second")
        assert current_trace() == {"request_id": "second"}
    finally:
        reset_trace(token2)


def test_bind_trace_none_values_ignored() -> None:
    token = new_trace_scope()
    try:
        bind_trace(request_id="r", user_id=None)
        assert current_trace() == {"request_id": "r"}
    finally:
        reset_trace(token)
