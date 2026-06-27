"""Logging configuration.

This cycle provides a minimal, idempotent logging setup. The sensitive-field
redaction filter (NFR-SEC-004) is added in task C4; `configure_logging` is the
single seam where that filter will be attached.
"""

from __future__ import annotations

import logging

_CONFIGURED = False


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root logging once. Safe to call multiple times."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    _CONFIGURED = True
