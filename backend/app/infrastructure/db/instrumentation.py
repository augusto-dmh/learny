"""Slow-statement capture on the application engine (OBS-11..15).

Turns "this endpoint took four seconds" into "this *statement* took four
seconds". A pair of cursor-execute events times every statement the application
engine runs; the ones that reach the configured threshold produce one structured
``db.slow_query`` log record and one entry on the in-process recorder.

Three properties govern the shape of this module:

- **Only the statement text is captured, never the bound parameters.**
  ``before_cursor_execute`` / ``after_cursor_execute`` receive the SQL text and
  its parameters as *separate* arguments, and the parameters are the dangerous
  half: session tokens and password hashes travel as bound values. This module
  never reads the ``parameters`` argument, on any path — single-execute,
  ``executemany``, or server-side cursor — so a secret cannot reach the recorder
  or the log even by accident.
- **The instrument never changes what it measures.** An exception raised in a
  cursor-execute event propagates to whoever ran the statement, so both handlers
  contain their own failures: a broken capture leaves the database operation's
  result — and the exception it would otherwise have raised — exactly as it was.
- **Capture issues no queries.** Everything it needs is already in hand, so
  timing a statement can never provoke another one on the same connection.

The threshold is read once, at engine build time, and handed in here; nothing in
this module reads settings, which keeps it clear of the import-time
``get_settings`` hazard recorded for ``configure_logging``. Truncation belongs to
the recorder, which caps every statement it stores, so the full text is handed
over untouched.

**Boundary, stated rather than hidden:** ``after_cursor_execute`` does not fire
for a statement that *fails*, so a slow statement that ends in a database error
is not captured. Timing failures would mean a third event (``handle_error``) and
a second code path; the acceptance criteria describe completed statements, so
that is left out deliberately.
"""

from __future__ import annotations

import logging
import time

from sqlalchemy import Engine, event

from app.core.instrumentation import record_query

#: Structured slow-statement log records. Separate from ``app.request`` so a
#: deployment can raise or silence query capture without touching access logs.
SLOW_QUERY_LOGGER = "app.query"

#: Message of the structured record emitted for a captured statement.
SLOW_QUERY_MESSAGE = "db.slow_query"

#: Key under which a statement's start reading is stashed on ``Connection.info``.
_START_KEY = "learny_statement_start"

_logger = logging.getLogger(SLOW_QUERY_LOGGER)


def is_slow(duration_ms: float, threshold_ms: float) -> bool:
    """Return whether a statement lasting ``duration_ms`` counts as slow.

    A statement qualifies at *or above* the threshold, and the comparison has no
    implicit floor: a threshold of zero or below captures every statement, which
    is what lets a test exercise the capture path without sleeping and what lets
    an environment deliberately record everything (AD-175).
    """
    return duration_ms >= threshold_ms


def install_slow_query_listener(engine: Engine, *, threshold_ms: float) -> None:
    """Attach slow-statement capture to ``engine``.

    Called once per engine at build time. ``threshold_ms`` is fixed for the life
    of the engine, so the setting is read where settings may safely be read
    rather than on every statement.
    """

    @event.listens_for(engine, "before_cursor_execute")
    def _stamp_start(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001, ANN202, ARG001
        # Overwrite rather than push: if a statement raises, no ``after`` fires
        # and the reading is left behind, so the next statement on this
        # connection must replace it rather than inherit it.
        try:
            conn.info[_START_KEY] = time.perf_counter()
        except Exception:  # noqa: BLE001 — the instrument never escalates into the query
            _logger.debug("instrument.query.start_failed", exc_info=True)

    @event.listens_for(engine, "after_cursor_execute")
    def _capture_if_slow(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001, ANN202, ARG001
        # ``parameters`` is deliberately never read: bound values are the half of
        # a statement that carries secrets.
        try:
            start = conn.info.pop(_START_KEY, None)
            if start is None:
                return
            duration_ms = round((time.perf_counter() - start) * 1000, 3)
            if not is_slow(duration_ms, threshold_ms):
                return
            # The recorder caps the stored text itself; hand it over whole.
            record_query(statement=statement, duration_ms=duration_ms)
            _logger.warning(
                SLOW_QUERY_MESSAGE,
                extra={"statement": statement, "duration_ms": duration_ms},
            )
        except Exception:  # noqa: BLE001 — the instrument never escalates into the query
            _logger.debug("instrument.query.dropped", exc_info=True)
