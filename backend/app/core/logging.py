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

It intentionally does not try to scrub free-form message strings (a brittle,
incomplete approach); the application logs structured fields, and the
secret-free ``User`` summary is what auth flows log.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime

REDACTED = "***REDACTED***"

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
    """Return ``value`` with any sensitive keys masked, recursively."""
    if isinstance(value, Mapping):
        return {
            k: (REDACTED if _is_sensitive_key(k) else _redact(v))
            for k, v in value.items()
        }
    # Strings/bytes are sequences but must be left intact (they are values, not
    # containers of key/value pairs).
    if isinstance(value, str | bytes):
        return value
    if isinstance(value, list):
        return [_redact(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_redact(v) for v in value)
    return value


class SensitiveDataFilter(logging.Filter):
    """Mask sensitive structured fields on each ``LogRecord`` before emission."""

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
        return True


_HUMAN_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


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
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


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
    handler.setFormatter(
        JsonFormatter() if resolved == "json" else logging.Formatter(_HUMAN_FORMAT)
    )
    # Redaction must run before trace enrichment cannot re-introduce secrets — both
    # are on the emitting handler so JSON/human output is masked + correlated.
    _ensure_filter(handler, SensitiveDataFilter)
    _ensure_filter(handler, TraceContextFilter)
    # Also on the root logger for records emitted directly on it (parity w/ prior).
    _ensure_filter(root, SensitiveDataFilter)
    _ensure_filter(root, TraceContextFilter)
