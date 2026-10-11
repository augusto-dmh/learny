"""Logging configuration with sensitive-field redaction (task C4, NFR-SEC-004).

Provides an idempotent root-logging setup plus a ``logging.Filter`` that masks
secret-bearing values before a record is emitted, so passwords, session/CSRF
tokens, and secret-like keys never reach the logs in plaintext (NFR-SEC-004).
Secrets remain env-only and are never returned to clients (NFR-SEC-003); this is
the defense-in-depth layer for anything that is logged.

The filter redacts:
- structured fields attached via ``logging``'s ``extra=`` whose key matches a
  sensitive name (e.g. ``password``, ``token``, ``csrf_token``, ``secret``);
- the same keys inside dict/sequence values, recursively;
- ``%``-style log args that are dict / sequence of such structures.

Free-form text is scrubbed for one shape only: provider API keys (ADR-0033).
A learner's key can reach a log line by a path nobody wrote on purpose, such
as an SDK exception that quotes the request, so every string the record
carries (the rendered message, ``extra`` values, exception and stack text) has
any substring shaped like an Anthropic, OpenAI or Gemini key replaced with
:data:`KEY_REDACTED`. Field-name redaction stays the rule for everything else.
"""

from __future__ import annotations

import json
import logging
import re
import traceback
from collections.abc import Mapping
from datetime import UTC, datetime

REDACTED = "***REDACTED***"

#: What a provider-key-shaped substring becomes in an emitted record.
KEY_REDACTED = "***KEY-REDACTED***"

# Anthropic (``sk-ant-...``), OpenAI (``sk-...``, ``sk-proj-...``) and Gemini
# (``AIza...``) keys. The tail floor sits below the shortest key the key routes
# accept (20 characters in all), so every storable key is covered. The prefix
# must start a token, so ``task-<uuid>`` or ``disk-...`` stay readable. The scan
# is linear (one character class, no nesting).
_PROVIDER_KEY_PATTERN = re.compile(r"(?<![A-Za-z0-9_])(?:sk-|AIza)[A-Za-z0-9_\-]{16,}")


def mask_provider_keys(text: str) -> str:
    """Return ``text`` with every provider-key-shaped substring replaced."""
    return _PROVIDER_KEY_PATTERN.sub(KEY_REDACTED, text)


# Substrings that mark a field name as sensitive (case-insensitive). Matching a
# substring catches variants like ``raw_token``, ``session_token``, ``api_key``.
_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "token",  # session token, csrf_token, raw_token, access/refresh tokens
    "secret",
    "authorization",
    "cookie",
    "api_key",
    "apikey",
    "credential",
    "private_key",
)

# Standard LogRecord attributes that must never be treated as "extra" structured
# fields when scanning for secrets.
_RESERVED_RECORD_ATTRS = frozenset(logging.makeLogRecord({}).__dict__.keys())


def _is_sensitive_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def _redact(value: object) -> object:
    """Return ``value`` with any sensitive keys masked, recursively.

    String values keep their content except for provider-key-shaped substrings,
    which are masked wherever they sit.
    """
    if isinstance(value, Mapping):
        return {k: (REDACTED if _is_sensitive_key(k) else _redact(v)) for k, v in value.items()}
    if isinstance(value, str):
        return mask_provider_keys(value)
    # Bytes are sequences but must be left intact (values, not containers).
    if isinstance(value, bytes):
        return value
    if isinstance(value, list):
        return [_redact(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_redact(v) for v in value)
    return value


def _mask_record_text(record: logging.LogRecord) -> None:
    """Mask provider keys in the rendered message, exception text and stack text.

    The message is rendered once (``msg % args``); when masking changes it, the
    record carries the masked text with no args, so no formatter can re-render
    the key from an argument whose ``str()`` holds it. The exception is
    formatted here into ``exc_text``, which formatters reuse instead of
    formatting ``exc_info`` again.
    """
    try:
        rendered = record.getMessage()
    except Exception:  # noqa: BLE001 — a malformed record still gets emitted
        rendered = None
    if rendered is not None:
        masked = mask_provider_keys(rendered)
        if masked != rendered:
            record.msg = masked
            record.args = None
    if record.exc_info and record.exc_info[0] is not None and not record.exc_text:
        record.exc_text = "".join(traceback.format_exception(*record.exc_info)).rstrip("\n")
    if record.exc_text:
        record.exc_text = mask_provider_keys(record.exc_text)
    if record.stack_info:
        record.stack_info = mask_provider_keys(record.stack_info)


class SensitiveDataFilter(logging.Filter):
    """Mask sensitive structured fields and provider keys on each ``LogRecord``."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Redact structured ``extra=`` fields set directly on the record.
        for key, value in list(record.__dict__.items()):
            if key in _RESERVED_RECORD_ATTRS:
                continue
            if _is_sensitive_key(key):
                setattr(record, key, REDACTED)
            else:
                setattr(record, key, _redact(value))

        # Redact %-style args that are mappings/sequences of sensitive data.
        if record.args:
            if isinstance(record.args, Mapping):
                record.args = _redact(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(_redact(a) for a in record.args)
        _mask_record_text(record)
        return True


_HUMAN_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

#: The ASGI server's own loggers, which do not propagate to the Learny handler.
_SERVER_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


class HumanFormatter(logging.Formatter):
    """The human line format, with provider keys masked in the final text.

    The filter already masks the record; masking the formatted line as well
    covers what the filter cannot see, such as an ``extra`` object whose
    ``str()`` carries a key.
    """

    def __init__(self) -> None:
        super().__init__(_HUMAN_FORMAT)

    def format(self, record: logging.LogRecord) -> str:
        return mask_provider_keys(super().format(record))


class JsonFormatter(logging.Formatter):
    """Serialize a record as one line of JSON (AD-041).

    Emits the standard fields (``timestamp``/``level``/``logger``/``message``)
    plus every non-reserved record attribute — the trace fields stamped by
    ``TraceContextFilter`` and any ``extra=`` the call site passed. Redaction runs
    as a filter *before* the handler formats, so secret-bearing attributes are
    already masked by the time they are serialized here (NFR-SEC-004 preserved).
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Trace fields + structured ``extra=`` live as non-reserved attributes.
        for key, value in record.__dict__.items():
            if key in _RESERVED_RECORD_ATTRS or key == "message" or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_text:
            # Already formatted (and key-masked) by ``SensitiveDataFilter``.
            payload["exc_info"] = record.exc_text
        elif record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)
        # The final line is masked too: ``default=str`` may render an ``extra``
        # object whose text carries a provider key the filter could not see.
        return mask_provider_keys(json.dumps(payload, default=str, ensure_ascii=False))


def _learny_handler(root: logging.Logger) -> logging.StreamHandler:
    """Return our tagged root handler, creating and attaching it once."""
    for handler in root.handlers:
        if getattr(handler, "_learny", False):
            return handler  # type: ignore[return-value]
    handler = logging.StreamHandler()
    handler._learny = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    return handler


def _ensure_filter(target: logging.Logger | logging.Handler, filter_cls: type) -> None:
    """Attach a single instance of ``filter_cls`` to ``target`` (idempotent)."""
    if not any(isinstance(f, filter_cls) for f in target.filters):
        target.addFilter(filter_cls())


def configure_logging(level: int = logging.INFO, log_format: str | None = None) -> None:
    """Configure root logging: format toggle + redaction + trace-field correlation.

    Idempotent and re-entrant: repeated calls do not duplicate handlers or filters,
    and a later call may switch the format (the worker configures ``json``). The
    redaction and trace-context filters are attached to our handler so every line
    it emits is both correlated and secret-masked (NFR-SEC-004 / AD-041). Deferred
    import of ``TraceContextFilter`` avoids an import cycle with ``config``.

    ``LEARNY_LOG_FORMAT`` is the single source of truth for the format and is read
    straight from the environment (not a ``Settings`` field) on purpose:
    ``configure_logging`` runs at import/startup, and priming the ``get_settings``
    lru-cache here would pin a stale DB URL that Alembic's ``env.py`` later reads (a
    real test-isolation hazard).
    """
    import os

    from app.core.tracing import TraceContextFilter

    resolved = log_format or os.environ.get("LEARNY_LOG_FORMAT", "human")
    root = logging.getLogger()
    root.setLevel(level)

    handler = _learny_handler(root)
    handler.setFormatter(JsonFormatter() if resolved == "json" else HumanFormatter())
    # Redaction must run before trace enrichment cannot re-introduce secrets — both
    # are on the emitting handler so JSON/human output is masked + correlated.
    _ensure_filter(handler, SensitiveDataFilter)
    _ensure_filter(handler, TraceContextFilter)
    # Also on the root logger for records emitted directly on it (parity w/ prior).
    _ensure_filter(root, SensitiveDataFilter)
    _ensure_filter(root, TraceContextFilter)
    # Uvicorn's loggers emit through their own handlers and do not propagate to
    # ours, so a server-level record (an unhandled exception's traceback) would
    # skip the masking. A logger filter runs for every record logged on that
    # logger whatever handlers uvicorn later installs.
    for name in _SERVER_LOGGERS:
        _ensure_filter(logging.getLogger(name), SensitiveDataFilter)
