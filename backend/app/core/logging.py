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

import logging
from collections.abc import Mapping

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


_CONFIGURED = False


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root logging once and attach the redaction filter.

    Safe to call multiple times. The filter is attached to every root handler so
    all log output passes through redaction (NFR-SEC-004).
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    redaction = SensitiveDataFilter()
    root = logging.getLogger()
    for handler in root.handlers:
        handler.addFilter(redaction)
    # Also attach to the root logger so records created on child loggers without
    # their own handlers are still filtered when they propagate.
    root.addFilter(redaction)
    _CONFIGURED = True
