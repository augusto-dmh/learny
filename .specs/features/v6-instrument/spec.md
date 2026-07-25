# App Instrumentation Specification

## Problem Statement

The app feels slow and there is no way to find out why. Host- and container-level
monitoring exists (netdata, ADR-0024) and every request already emits a structured
access log carrying `duration_ms` (AD-041), but nothing aggregates those durations,
nothing records *which SQL statement* was slow, Celery durations are hand-rolled
per task and therefore missing from most of them, and the browser's own devtools
receive no server-side timing split. Diagnosis today is guesswork.

This cycle builds the ruler. It measures nothing faster; later cycles cite it.

## Goals

- [ ] Every HTTP request, every slow SQL statement, and every Celery task reports a duration through one deliberate instrument rather than ad-hoc code.
- [ ] A single dev-only surface ranks the slowest endpoints and lists recent slow queries with their statement text.
- [ ] The browser sees the server's share of each request via a `Server-Timing` header that survives the Next.js proxy.
- [ ] Nothing is optimized, no new runtime dependency is added, and the instrument is prod-safe by construction.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
| --- | --- |
| Any performance optimization or latency fix | RFC-006 Cycle A produces the measurement; optimization is Cycle E's, citing these numbers |
| Prometheus / OpenTelemetry / statsd exporter or scrape endpoint | AD-041 deferred it deliberately; ADR-0024 locked a self-hosted, no-SaaS stance. Would be its own decision |
| Persisting timings to PostgreSQL | Needs a migration; RFC-006 criterion 4 keeps schema changes out of non-schema cycles |
| Cross-process aggregation of timings (API workers, Celery) into one view | Requires a shared store; see Assumptions. Log records remain the cross-process substrate |
| Client-side / browser performance instrumentation | Cycle E owns the answer-experience UI and its perceived-latency work |
| Alerting, thresholds, notifications, retention policies | Not a monitoring stack; this is a development diagnosis tool |
| Distributed tracing spans or a trace backend | Trace *correlation* already exists (`app/core/tracing.py`); spans are a different commitment |
| Refactoring the existing hand-rolled per-task `duration_ms` logs | Working code with live test sensors; the new instrument is additive |

---

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| Where recorded samples live | In-process bounded buffer, per process | No migration, no new dependency, no I/O in the request path. Alternatives evaluated in `context.md` D-1 | y (auto, AD-170) |
| Prod runs `--workers 2`, so the panel shows one worker's slice of traffic | Accepted and documented on the surface itself | The tool is dev-first; local compose runs a single API worker, where the view is complete | y (auto, AD-171) |
| Celery task durations cannot appear in the API panel (separate process) | Worker durations ship as uniform structured log records, not panel rows | Same reason as D-1; logs are already the cross-process substrate (AD-041) | y (auto, AD-171) |
| `Server-Timing` survives the Next.js proxy | Verified before specifying — the response denylist is `content-encoding`/`content-length` only (`frontend/app/lib/proxy.ts:60`) | Read, not assumed; a regression sensor is still required (OBS-07) | y (verified) |
| Whether collection is also flag-gated, or only exposure | Collection always on; only the surface is gated | The risk is exposure, not the cost of a bounded append. Gating collection would make a production process undiagnosable without a restart | y (auto, AD-173) |
| Slow-query threshold default | 200 ms | Above local-noise, below the "app feels slow" band the dogfood finding describes; configurable per environment | y (auto, AD-175) |
| Whether the dev surface needs auth on top of the flag | Yes — flag AND authenticated user | Defense in depth at negligible cost; the browser reaches it through the existing proxy with the session cookie | y (auto, AD-174) |

**Open questions:** none — all resolved or logged above.

---

## User Stories

### P1: One timing recorder ⭐ MVP

**User Story**: As the developer diagnosing slowness, I want every measured duration to land in one bounded, queryable place so that ranking and inspection are a property of the instrument, not of each call site.

**Why P1**: Every other story reads from it.

**Acceptance Criteria**:

1. WHEN a completed HTTP request is recorded THEN the recorder SHALL store the route template, HTTP method, status code, and duration in milliseconds, and SHALL NOT store path-parameter values, query strings, request headers, or bodies.
2. WHEN a request does not match any route THEN the recorder SHALL bucket it under a single constant placeholder label and SHALL NOT store the raw request path.
3. WHEN more samples are recorded than the configured capacity THEN the recorder SHALL retain exactly the most recent `capacity` samples and SHALL discard the oldest.
4. WHEN the recorder is asked to rank endpoints THEN it SHALL return one row per `(method, route template)` carrying the sample count, mean duration, maximum duration, and p95 duration, ordered by descending p95 and, on ties, by descending maximum.
5. WHEN p95 is computed over `n` samples THEN it SHALL be the nearest-rank value — the ascending-sorted duration at index `ceil(0.95 * n) - 1`.
6. WHEN samples are recorded concurrently from multiple threads THEN no sample SHALL be lost or corrupted and the buffer SHALL remain within capacity.
7. WHEN the recorder raises for any reason during a request THEN the HTTP request SHALL still complete with its normal response and status code.

**Independent Test**: Feed a known sequence of samples into the recorder and assert the ranking rows, the eviction boundary, and the p95 index.

---

### P1: Server timing on the wire ⭐ MVP

**User Story**: As the developer, I want the browser's devtools to show the server's share of each request so that I can tell backend time from network and render time without leaving the browser.

**Why P1**: It is the cheapest diagnosis path and the only one that reaches the client.

**Acceptance Criteria**:

1. WHEN any HTTP response leaves the application THEN it SHALL carry a `Server-Timing` header containing an `app` metric whose `dur` value equals the duration reported on that request's access log record.
2. WHEN a response is relayed through the Next.js API proxy THEN the `Server-Timing` header SHALL still be present on the response delivered to the browser.
3. WHEN the request handler raises an unhandled exception THEN the response SHALL still carry `Server-Timing` and the request SHALL still be recorded, with its final status code.

**Independent Test**: Call any endpoint through the test client and assert the header; call the proxy relay with an upstream response carrying the header and assert it survives.

---

### P1: Slow query capture ⭐ MVP

**User Story**: As the developer, I want the statement text and duration of every slow SQL statement so that "this endpoint took four seconds" becomes "this statement took four seconds".

**Why P1**: It is the "and why" half of the dogfood finding.

**Acceptance Criteria**:

1. WHEN a statement executed on the application engine takes at least `LEARNY_SLOW_QUERY_MS` THEN the system SHALL emit one structured log record and record one sample, each carrying the statement text and the duration in milliseconds.
2. WHEN a statement takes less than that threshold THEN no slow-query log record and no slow-query sample SHALL be produced for it.
3. WHEN a slow statement is captured THEN the captured text SHALL be the SQL statement only and SHALL NOT contain bound parameter values.
4. WHEN a captured statement is longer than the configured cap THEN it SHALL be stored truncated to that cap rather than in full.
5. WHEN slow-query capture raises for any reason THEN the database operation SHALL still complete normally.

**Independent Test**: Execute a deliberately slow statement (e.g. `pg_sleep`) against the application engine with a low threshold and assert one captured sample carrying the statement text and no parameter values; execute a fast one and assert nothing is captured.

---

### P1: Uniform Celery task durations ⭐ MVP

**User Story**: As the developer, I want every background task to report its duration and outcome without per-task code so that worker slowness is as visible as request slowness.

**Why P1**: Ingestion and embedding are the longest operations in the product, and most tasks currently report nothing.

**Acceptance Criteria**:

1. WHEN any Celery task finishes THEN a structured log record SHALL be emitted carrying the task name, the terminal state, and the duration in milliseconds — for every registered task, with no per-task instrumentation code.
2. WHEN a task raises THEN the duration record SHALL still be emitted and SHALL carry a state distinguishing failure from success.
3. WHEN the new instrument is active THEN the existing per-task `duration_ms` log records SHALL continue to be emitted unchanged.

**Independent Test**: Run a trivial task that succeeds and one that raises through the existing eager/worker test path and assert one duration record each, with distinct states.

---

### P1: The dev-only surface ⭐ MVP

**User Story**: As the developer, I want one place that ranks the slowest endpoints and lists recent slow queries so that diagnosis does not mean grepping logs.

**Why P1**: It is the deliverable the RFC names; the recorder is invisible without it.

**Acceptance Criteria**:

1. WHEN `LEARNY_DEV_INSTRUMENT_ENABLED` is unset or false THEN a request to the dev instrument path SHALL receive 404.
2. WHEN the flag is true and the caller has no valid session THEN the request SHALL receive 401.
3. WHEN the flag is true and the caller is authenticated THEN the response SHALL be 200 and SHALL carry the ranked endpoint rows and the recent slow-query entries.
4. WHEN no samples have been recorded THEN the response SHALL be 200 with empty collections, not an error.
5. WHEN the environment contract is read THEN `.env.example` SHALL document the instrument flag, the slow-query threshold, the buffer capacity, and the statement cap.
6. WHEN the production compose configuration is read THEN it SHALL NOT enable the dev instrument flag.

**Independent Test**: Build the app with the flag off and assert 404; with the flag on, assert 401 unauthenticated and 200 with the documented shape when authenticated.

---

## Edge Cases

- WHEN the recorder holds zero samples THEN ranking SHALL return an empty collection and SHALL NOT raise.
- WHEN a single sample exists THEN its p95 SHALL be that sample's duration.
- WHEN two endpoint groups have equal p95 THEN ordering SHALL fall back to descending maximum.
- WHEN a request 404s on an unmatched path THEN it SHALL be recorded under the constant placeholder label, never under the raw path.
- WHEN the slow-query threshold is configured to zero or below THEN every statement SHALL qualify as slow (no implicit floor), so the setting stays honest under test.
- WHEN a Celery task is retried THEN each attempt SHALL produce its own duration record.

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| --- | --- | --- | --- |
| OBS-01 | P1: One timing recorder | A | Pending |
| OBS-02 | P1: One timing recorder | A | Pending |
| OBS-03 | P1: One timing recorder | A | Pending |
| OBS-04 | P1: One timing recorder | A | Pending |
| OBS-05 | P1: One timing recorder | A | Pending |
| OBS-06 | P1: One timing recorder | B | Pending |
| OBS-07 | P1: One timing recorder | B | Pending |
| OBS-08 | P1: Server timing on the wire | B | Pending |
| OBS-09 | P1: Server timing on the wire | B | Pending |
| OBS-10 | P1: Server timing on the wire | B | Pending |
| OBS-11 | P1: Slow query capture | C | Pending |
| OBS-12 | P1: Slow query capture | C | Pending |
| OBS-13 | P1: Slow query capture | C | Pending |
| OBS-14 | P1: Slow query capture | C | Pending |
| OBS-15 | P1: Slow query capture | C | Pending |
| OBS-16 | P1: Uniform Celery task durations | C | Pending |
| OBS-17 | P1: Uniform Celery task durations | C | Pending |
| OBS-18 | P1: Uniform Celery task durations | C | Pending |
| OBS-19 | P1: The dev-only surface | D | Pending |
| OBS-20 | P1: The dev-only surface | D | Pending |
| OBS-21 | P1: The dev-only surface | D | Pending |
| OBS-22 | P1: The dev-only surface | D | Pending |
| OBS-23 | P1: The dev-only surface | D | Pending |
| OBS-24 | P1: The dev-only surface | D | Pending |

**Mapping:** OBS-01..07 = recorder ACs 1–7; OBS-08..10 = server-timing ACs 1–3;
OBS-11..15 = slow-query ACs 1–5; OBS-16..18 = Celery ACs 1–3; OBS-19..24 = surface ACs 1–6.

**Coverage:** 24 total, 24 mapped to phases, 0 unmapped.

---

## Success Criteria

- [ ] Opening the dev surface after exercising the app names the slowest endpoint and the slowest statement without reading a log file.
- [ ] Every Celery task reports a duration, including ones that were never hand-instrumented.
- [ ] The browser network panel shows a server-time split for API calls.
- [ ] The production configuration cannot expose the surface, and no bound parameter value can reach a captured statement.
- [ ] No endpoint, query, or task is made faster by this cycle.
