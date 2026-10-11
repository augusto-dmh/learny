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


# --- Provider keys in free-form text (ADR-0033, C33) ---------------------------------

_KEY_SHAPES = {
    "anthropic": "sk-ant-api03-Zr8Kq2mVx7Lp4Nw9Bt6Hc3Yd",
    "openai": "sk-proj-Q4wE9rT2yU7iO1pA5sD8fG3h",
    "openai_legacy": "sk-" + "A1b2C3d4E5f6G7h8I9j0K1l2",
    "gemini": "AIzaSyB3x9Kq2mVx7Lp4Nw9Bt6HcZr8",
}


@pytest.fixture
def emitted():  # noqa: ANN201
    """Configure logging in a given format; return a reader of what the handler wrote."""
    import io

    def _configure(log_format: str):  # noqa: ANN202
        configure_logging(log_format=log_format)
        root = logging.getLogger()
        handler = next(h for h in root.handlers if getattr(h, "_learny", False))
        buffer = io.StringIO()
        previous = handler.setStream(buffer)
        return buffer, lambda: handler.setStream(previous)

    yield _configure
    configure_logging(log_format="human")


@pytest.mark.parametrize("log_format", ["human", "json"])
@pytest.mark.parametrize("shape", sorted(_KEY_SHAPES))
def test_masks_provider_key_shapes(shape: str, log_format: str, emitted) -> None:  # noqa: ANN001
    key = _KEY_SHAPES[shape]
    buffer, restore = emitted(log_format)
    logger = logging.getLogger("app.tests.key_masking")
    try:
        logger.warning(f"message carries {key}")
        logger.warning("arg carries %s", key)
        logger.warning("object arg carries %s", ValueError(f"provider said {key}"))
        logger.warning("extra carries", extra={"detail": f"prefix {key} suffix"})
        logger.warning("extra object carries", extra={"cause": ValueError(key)})
        try:
            raise RuntimeError(f"SDK rejected the request with {key}")
        except RuntimeError:
            logger.exception("exception text carries")
    finally:
        restore()

    output = buffer.getvalue()
    assert output.count("carries") == 6, output  # every record was emitted
    assert key not in output
    assert key[-12:] not in output
    assert "***KEY-REDACTED***" in output


def test_masking_keeps_ordinary_text_and_short_lookalikes() -> None:
    from app.core.logging import mask_provider_keys

    text = (
        "task-runner sk-short AIza ok; ask-anthropic is fine; "
        "task-3f2a9c1e-6b7d-4e5f-8a9b-0c1d2e3f4a5b and disk-0123456789abcdefghij"
    )
    assert mask_provider_keys(text) == text


def test_both_process_assemblies_install_the_masking_filter() -> None:
    """The API and the worker both configure logging through ``configure_logging``,
    which installs ``SensitiveDataFilter`` (and the masking formatters) on the
    emitting handler."""
    import inspect

    import app.main as api
    import app.worker.celery_app as worker
    from app.core.logging import HumanFormatter, JsonFormatter

    assert "configure_logging()" in inspect.getsource(api)
    assert "configure_logging()" in inspect.getsource(worker)
    for log_format, formatter in (("human", HumanFormatter), ("json", JsonFormatter)):
        configure_logging(log_format=log_format)
        root = logging.getLogger()
        handler = next(h for h in root.handlers if getattr(h, "_learny", False))
        assert any(isinstance(f, SensitiveDataFilter) for f in handler.filters)
        assert isinstance(handler.formatter, formatter)
    configure_logging(log_format="human")


def test_uvicorn_records_are_masked_on_their_own_handlers() -> None:
    """Uvicorn's loggers keep their own handlers and do not propagate to ours;
    a traceback they log (an unhandled exception) is still masked."""
    import io

    key = _KEY_SHAPES["anthropic"]
    configure_logging()
    server = logging.getLogger("uvicorn.error")
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)  # uvicorn's handlers carry no filter of ours
    previous = server.propagate
    server.addHandler(handler)
    server.propagate = False
    try:
        try:
            raise RuntimeError(f"request failed with {key}")
        except RuntimeError:
            server.exception("Exception in ASGI application")
    finally:
        server.removeHandler(handler)
        server.propagate = previous

    output = buffer.getvalue()
    assert "Exception in ASGI application" in output
    assert key not in output
    assert "***KEY-REDACTED***" in output
