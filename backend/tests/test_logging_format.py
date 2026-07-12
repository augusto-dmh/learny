"""A2 gate — structured JSON logging + config idempotency (unit, PROD-12/13).

Proves the JSON formatter and the reworked ``configure_logging``:
- JSON output is a single line carrying message + standard fields + trace/extra;
- a sensitive field is REDACTED in JSON output (redaction runs before format);
- ``configure_logging`` stays idempotent (one handler, one of each filter) and can
  switch format (the worker configures ``json``).
"""

from __future__ import annotations

import json
import logging

import pytest

from app.core.logging import (
    REDACTED,
    JsonFormatter,
    SensitiveDataFilter,
    configure_logging,
)
from app.core.tracing import (
    TraceContextFilter,
    bind_trace,
    new_trace_scope,
    reset_trace,
)


@pytest.fixture(autouse=True)
def _restore_human_format():
    yield
    configure_logging(log_format="human")


def _record(msg: str = "event", **extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_single_line_with_standard_fields() -> None:
    out = JsonFormatter().format(_record("hello", source_id="s-1"))
    assert "\n" not in out
    parsed = json.loads(out)
    assert parsed["message"] == "hello"
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "app.test"
    assert parsed["source_id"] == "s-1"
    assert "timestamp" in parsed


def test_json_formatter_includes_bound_trace_fields() -> None:
    token = new_trace_scope()
    try:
        bind_trace(request_id="req-9", user_id="u-9")
        rec = _record()
        TraceContextFilter().filter(rec)
        parsed = json.loads(JsonFormatter().format(rec))
        assert parsed["request_id"] == "req-9"
        assert parsed["user_id"] == "u-9"
    finally:
        reset_trace(token)


def test_json_output_redacts_sensitive_fields() -> None:
    secret = "raw-session-token-xyz"
    rec = _record(session_token=secret, password="hunter2", email="a@b.co")
    # Redaction is a filter — it runs before the handler formats.
    SensitiveDataFilter().filter(rec)
    out = JsonFormatter().format(rec)
    parsed = json.loads(out)
    assert parsed["session_token"] == REDACTED
    assert parsed["password"] == REDACTED
    assert parsed["email"] == "a@b.co"
    assert secret not in out
    assert "hunter2" not in out


def test_configure_logging_json_sets_json_formatter() -> None:
    configure_logging(log_format="json")
    root = logging.getLogger()
    handler = next(h for h in root.handlers if getattr(h, "_learny", False))
    assert isinstance(handler.formatter, JsonFormatter)


def test_configure_logging_idempotent_single_handler_and_filters() -> None:
    configure_logging()
    configure_logging()
    root = logging.getLogger()
    learny_handlers = [h for h in root.handlers if getattr(h, "_learny", False)]
    assert len(learny_handlers) == 1
    handler = learny_handlers[0]
    assert sum(isinstance(f, SensitiveDataFilter) for f in handler.filters) == 1
    assert sum(isinstance(f, TraceContextFilter) for f in handler.filters) == 1


def test_configure_logging_can_switch_format() -> None:
    configure_logging(log_format="human")
    root = logging.getLogger()
    handler = next(h for h in root.handlers if getattr(h, "_learny", False))
    assert not isinstance(handler.formatter, JsonFormatter)
    configure_logging(log_format="json")
    # Same single handler, now JSON.
    learny_handlers = [h for h in root.handlers if getattr(h, "_learny", False)]
    assert len(learny_handlers) == 1
    assert isinstance(learny_handlers[0].formatter, JsonFormatter)
