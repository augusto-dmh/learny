"""C4 gate — sensitive-data logging redaction (unit, NFR-SEC-004).

Proves the redaction filter masks secret-bearing fields before emission:
- structured ``extra=`` fields named like secrets (password, csrf_token, raw
  session token, api keys) are masked;
- nested dict/list values are masked recursively;
- non-sensitive fields and message text are preserved;
- an end-to-end check through ``configure_logging`` shows no plaintext secret in
  the emitted output.
"""

from __future__ import annotations

import logging

import pytest

from app.core.logging import (
    REDACTED,
    SensitiveDataFilter,
    configure_logging,
)


def _record(**extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="auth event",
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_filter_masks_top_level_sensitive_keys() -> None:
    f = SensitiveDataFilter()
    rec = _record(
        password="hunter2",
        csrf_token="csrf-abc",
        session_token="raw-opaque-token",
        api_key="sk-live-123",
        email="user@example.com",
    )
    assert f.filter(rec) is True
    assert rec.password == REDACTED
    assert rec.csrf_token == REDACTED
    assert rec.session_token == REDACTED
    assert rec.api_key == REDACTED
    # Non-sensitive field preserved.
    assert rec.email == "user@example.com"


def test_filter_masks_nested_structures() -> None:
    f = SensitiveDataFilter()
    rec = _record(
        context={
            "user_id": "u-1",
            "password": "hunter2",
            "nested": {"csrf_token": "x", "ok": "keep"},
            "items": [{"secret": "s"}, {"plain": "p"}],
        }
    )
    f.filter(rec)
    ctx = rec.context
    assert ctx["user_id"] == "u-1"
    assert ctx["password"] == REDACTED
    assert ctx["nested"]["csrf_token"] == REDACTED
    assert ctx["nested"]["ok"] == "keep"
    assert ctx["items"][0]["secret"] == REDACTED
    assert ctx["items"][1]["plain"] == "p"


def test_filter_masks_mapping_args() -> None:
    f = SensitiveDataFilter()
    rec = _record()
    rec.args = {"password": "hunter2", "user": "alice"}
    f.filter(rec)
    assert rec.args["password"] == REDACTED
    assert rec.args["user"] == "alice"


def test_filter_preserves_message_and_returns_true() -> None:
    f = SensitiveDataFilter()
    rec = _record()
    assert f.filter(rec) is True
    assert rec.getMessage() == "auth event"


def test_configure_logging_redacts_emitted_output(
    caplog: pytest.LogCaptureFixture,
) -> None:
    configure_logging()
    logger = logging.getLogger("app.tests.redaction")

    secret_password = "S3cretP@ssw0rd!!"
    secret_token = "raw-session-token-xyz"
    with caplog.at_level(logging.INFO):
        logger.info(
            "auth flow",
            extra={
                "password": secret_password,
                "session_token": secret_token,
                "email": "redact@example.com",
            },
        )

    # The configured filter must have masked the secrets on the captured record.
    record = next(r for r in caplog.records if r.name == "app.tests.redaction")
    assert record.password == REDACTED
    assert record.session_token == REDACTED
    assert record.email == "redact@example.com"
    # And no plaintext secret appears anywhere in the captured text.
    assert secret_password not in caplog.text
    assert secret_token not in caplog.text
