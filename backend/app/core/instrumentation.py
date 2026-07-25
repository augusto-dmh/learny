"""In-process instrumentation recorder — request timings and slow queries (OBS-01..06).

One module owns all in-memory instrumentation state. Producers (the request
middleware, the database event listener) push completed samples; the dev-only
surface reads a snapshot. No producer knows about the consumer.

Storage is a pair of bounded ring buffers **in this process only** (AD-170): no
migration, no new dependency, no I/O in the path being measured. The consequence
— a process sees only its own traffic, and everything is lost on restart — is
accepted and stated on the surface itself (AD-171).

Three properties matter more than anything this module computes:

- **Nothing identifying is stored.** Requests are keyed on the *route template*.
  There is no parameter that accepts a raw path, a header, or a body, and a
  request that matched no route buckets under one constant label
  (:data:`UNMATCHED_ROUTE`). A surface has weaker access control than the
  resources a raw path would name, so the values never enter here at all.
- **Recording never raises into its caller.** :func:`record_request` and
  :func:`record_query` validate at the boundary and contain their own failures,
  so a producer sitting on a request or database path needs no defensive
  ``try``/``except`` and the instrument cannot change the outcome of what it
  measures. Because bad samples are rejected on the way in, the read path
  (:meth:`InstrumentRecorder.snapshot`) is total.
- **Storage is bounded in both dimensions.** The sample count is capped by
  ``capacity`` and each captured statement is capped by ``statement_max_chars``,
  so a buffer of long SQL strings cannot grow without limit.

Collection is always on; only the surface that exposes it is flag-gated
(AD-173), so nothing here reads ``dev_instrument_enabled``. Nothing here reads
settings at all: the process default is constructed from the constants below and
the configured recorder is injected at app assembly, which keeps this module
clear of the import-time ``get_settings`` hazard recorded for
``configure_logging``.
"""

from __future__ import annotations

import logging
import math
import threading
from collections import deque
from dataclasses import dataclass

#: Ranking label for a request that matched no route. The raw path is never stored.
UNMATCHED_ROUTE = "<unmatched>"

#: Ranking label for a sample whose HTTP method is missing or blank.
UNKNOWN_METHOD = "-"

#: Retained samples per buffer, and captured characters per statement. These are
#: the process defaults; ``LEARNY_INSTRUMENT_CAPACITY`` and
#: ``LEARNY_SLOW_QUERY_STATEMENT_CHARS`` carry the same values and override them.
DEFAULT_CAPACITY = 500
DEFAULT_STATEMENT_MAX_CHARS = 2000

_logger = logging.getLogger("app.instrument")


@dataclass(frozen=True, slots=True)
class RequestSample:
    """One completed HTTP request. Carries a route template, never a path."""

    method: str
    route: str
    status_code: int
    duration_ms: float


@dataclass(frozen=True, slots=True)
class QuerySample:
    """One slow SQL statement. Carries statement text only, never bound parameters."""

    statement: str
    duration_ms: float


@dataclass(frozen=True, slots=True)
class EndpointStat:
    """Aggregated timings for one ``(method, route template)`` group."""

    method: str
    route: str
    count: int
    mean_ms: float
    max_ms: float
    p95_ms: float


@dataclass(frozen=True, slots=True)
class InstrumentSnapshot:
    """A consistent read of the recorder: ranked endpoints + recent slow queries."""

    endpoints: tuple[EndpointStat, ...]
    slow_queries: tuple[QuerySample, ...]


def _normalize_method(method: object) -> str:
    """Return an upper-cased HTTP method, or :data:`UNKNOWN_METHOD` when absent."""
    return str(method or "").strip().upper() or UNKNOWN_METHOD


def _normalize_route(route: object) -> str:
    """Return the ranking label for ``route``.

    ``None`` or blank means the request matched no route, which buckets under the
    one constant placeholder. A query string or fragment is stripped defensively:
    no producer should ever pass one, and if one arrives it must not be stored.
    """
    text = str(route or "").split("?", 1)[0].split("#", 1)[0].strip()
    return text or UNMATCHED_ROUTE


def _normalize_duration(duration_ms: object) -> float:
    """Return ``duration_ms`` as a finite, non-negative float.

    Raises ``ValueError`` / ``TypeError`` for anything else, which the recording
    boundary turns into a dropped sample: a NaN or negative duration would poison
    every mean, maximum and percentile computed from the buffer afterwards.
    """
    value = float(duration_ms)  # type: ignore[arg-type]
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"duration_ms must be finite and non-negative, got {duration_ms!r}")
    return value


def _p95(durations: list[float]) -> float:
    """Nearest-rank p95: the ascending-sorted value at index ``ceil(0.95 * n) - 1``."""
    ordered = sorted(durations)
    index = math.ceil(0.95 * len(ordered)) - 1
    return ordered[min(max(index, 0), len(ordered) - 1)]


class InstrumentRecorder:
    """Bounded, thread-safe, in-process store of request and slow-query samples.

    Producers may call :meth:`record_request` and :meth:`record_query` from the
    event loop and from the sync threadpool at the same time, so concurrent
    recording is the normal case: a lock guards every buffer mutation and every
    read, and neither method raises. The lock is deliberate rather than
    decorative — a bounded ``deque`` append happens to be atomic under CPython's
    GIL, but that is an implementation detail (it does not hold on a
    free-threaded build), and it would stop covering a read-modify-write the day
    one is added here.

    ``capacity`` bounds each buffer independently — the newest ``capacity``
    samples are kept and the oldest are discarded. A capacity of zero or below
    retains nothing (recording stays a no-op rather than an error), and a
    statement cap of zero or below stores empty statement text; both are honest
    readings of a deliberate configuration rather than silently floored values.
    """

    def __init__(
        self,
        *,
        capacity: int = DEFAULT_CAPACITY,
        statement_max_chars: int = DEFAULT_STATEMENT_MAX_CHARS,
    ) -> None:
        self._capacity = max(0, int(capacity))
        self._statement_max_chars = max(0, int(statement_max_chars))
        self._lock = threading.Lock()
        self._requests: deque[RequestSample] = deque(maxlen=self._capacity)
        self._queries: deque[QuerySample] = deque(maxlen=self._capacity)

    @property
    def capacity(self) -> int:
        """Retained samples per buffer."""
        return self._capacity

    @property
    def statement_max_chars(self) -> int:
        """Captured characters per statement."""
        return self._statement_max_chars

    def record_request(
        self,
        *,
        method: str,
        route: str | None,
        status_code: int,
        duration_ms: float,
    ) -> None:
        """Record one completed request. Never raises.

        ``route`` is the matched route *template*; ``None`` or blank records under
        :data:`UNMATCHED_ROUTE`. There is deliberately no parameter for the raw
        path, the query string, headers, or the body.
        """
        try:
            sample = RequestSample(
                method=_normalize_method(method),
                route=_normalize_route(route),
                status_code=int(status_code),
                duration_ms=_normalize_duration(duration_ms),
            )
            with self._lock:
                self._requests.append(sample)
        except Exception:  # pragma: no cover - defensive; the instrument never escalates
            _logger.debug("instrument.request.dropped", exc_info=True)

    def record_query(self, *, statement: str, duration_ms: float) -> None:
        """Record one slow SQL statement. Never raises.

        ``statement`` is the SQL text only — bound parameter values (session
        tokens, password hashes) must never reach it — and is stored truncated to
        ``statement_max_chars``.
        """
        try:
            sample = QuerySample(
                statement=str(statement or "").strip()[: self._statement_max_chars],
                duration_ms=_normalize_duration(duration_ms),
            )
            with self._lock:
                self._queries.append(sample)
        except Exception:  # pragma: no cover - defensive; the instrument never escalates
            _logger.debug("instrument.query.dropped", exc_info=True)

    def recent_requests(self, limit: int | None = None) -> tuple[RequestSample, ...]:
        """Return recorded request samples, newest first, capped by ``limit``."""
        with self._lock:
            entries = list(self._requests)
        entries.reverse()
        if limit is not None:
            entries = entries[: max(0, limit)]
        return tuple(entries)

    def rank_endpoints(self) -> tuple[EndpointStat, ...]:
        """Rank recorded requests, one row per ``(method, route template)``.

        Ordered by descending p95 and, on ties, by descending maximum. Rows still
        tied on both keep first-seen order. An empty recorder ranks to ``()``.
        """
        with self._lock:
            samples = list(self._requests)

        groups: dict[tuple[str, str], list[float]] = {}
        for sample in samples:
            groups.setdefault((sample.method, sample.route), []).append(sample.duration_ms)

        stats = [
            EndpointStat(
                method=method,
                route=route,
                count=len(durations),
                # Rounded like the access log's duration_ms, so the surface is not
                # asked to render float noise; max and p95 are stored values.
                mean_ms=round(sum(durations) / len(durations), 3),
                max_ms=max(durations),
                p95_ms=_p95(durations),
            )
            for (method, route), durations in groups.items()
        ]
        stats.sort(key=lambda stat: (stat.p95_ms, stat.max_ms), reverse=True)
        return tuple(stats)

    def recent_queries(self, limit: int | None = None) -> tuple[QuerySample, ...]:
        """Return captured slow statements, newest first, capped by ``limit``."""
        with self._lock:
            entries = list(self._queries)
        entries.reverse()
        if limit is not None:
            entries = entries[: max(0, limit)]
        return tuple(entries)

    def snapshot(self, *, slow_query_limit: int | None = None) -> InstrumentSnapshot:
        """Return the ranked endpoints and the recent slow statements."""
        return InstrumentSnapshot(
            endpoints=self.rank_endpoints(),
            slow_queries=self.recent_queries(slow_query_limit),
        )

    def reset(self) -> None:
        """Drop every recorded sample (test isolation)."""
        with self._lock:
            self._requests.clear()
            self._queries.clear()


# Active recorder (module-level singleton, process defaults). Swap at app assembly
# or in tests via set_recorder; producers go through the free functions below so a
# swapped-in recorder can never escalate a failure into the path it measures.
_recorder = InstrumentRecorder()


def set_recorder(recorder: InstrumentRecorder) -> None:
    """Replace the active recorder (composition root / tests)."""
    global _recorder
    _recorder = recorder


def get_recorder() -> InstrumentRecorder:
    """Return the active recorder."""
    return _recorder


def record_request(
    *,
    method: str,
    route: str | None,
    status_code: int,
    duration_ms: float,
) -> None:
    """Record a completed request on the active recorder. Never raises.

    This is the producer entry point: it holds the containment, so the request
    path needs no guard of its own even if the installed recorder misbehaves.
    """
    try:
        get_recorder().record_request(
            method=method,
            route=route,
            status_code=status_code,
            duration_ms=duration_ms,
        )
    except Exception:
        _logger.debug("instrument.request.dropped", exc_info=True)


def record_query(*, statement: str, duration_ms: float) -> None:
    """Record a slow statement on the active recorder. Never raises.

    This is the producer entry point: it holds the containment, so the database
    event listener needs no guard of its own even if the installed recorder
    misbehaves.
    """
    try:
        get_recorder().record_query(statement=statement, duration_ms=duration_ms)
    except Exception:
        _logger.debug("instrument.query.dropped", exc_info=True)
