# Production-Like Readiness Specification

## Problem Statement

The MVP runs today only via the local development Docker Compose topology, with plain-text logs that cannot be correlated across a request and no operator guidance for backups or rollback. Before Learny can run in a first production-like environment (ADR-0008), it needs a production deployment shape, request-correlated observability hooks, and durable operator runbooks — without prematurely locking a monitoring/TLS/reverse-proxy vendor (that decision is deferred to TDD open question #10).

## Goals

- [ ] Ship a production-like Docker Compose deployment shape distinct from the local dev topology, keeping local aligned (ADR-0008 §3).
- [ ] Add request-correlated observability hooks: a request ID and the TDD's required trace fields threaded through structured logs, with per-request latency/outcome, preserving existing secret redaction.
- [ ] Provide durable operator runbooks for PostgreSQL + object-storage backup/restore and for deployment/operational rollback.
- [ ] Keep every deliverable provider-neutral — no concrete monitoring, metrics-scrape, TLS, or reverse-proxy implementation is locked this cycle.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
| ------- | ------ |
| Metrics scrape endpoint (`/metrics`) + a metrics client/exporter dependency (Prometheus/OTel/StatsD) | Locks the observability implementation ADR-0008 and TDD OQ #10 defer; structured latency/outcome log events are the provider-neutral hook this cycle ships (AD-041). Follow-up: OQ #10 ADR. |
| Concrete monitoring/alerting stack, TLS certificates, reverse-proxy product choice | TDD OQ #10 + ADR-0008 §5 explicitly defer these; the prod shape documents them as an external front, it does not embed one. |
| A real VPS provider / live deployment automation (CI/CD, image registry) | ADR-0008 §4 defers the provider; this cycle delivers the runnable shape + runbooks, not a hosted pipeline. |
| Frontend user-facing feature or UI change | Production readiness has no end-user surface (AD-044); a production build target is added but no UI behavior changes. |
| Database schema / migration changes | No product data model change is required for readiness. |
| Corpus/index output versioning (TDD "versioned outputs so old citations remain interpretable") | Re-ingestion is atomic-replace with no versioning (AD-018); adding versioning is its own decision. The rollback runbook documents the current replace semantics and their implication instead. |

---

## Assumptions & Open Questions

Every ambiguity is resolved or recorded here — nothing is left silently unclear.

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --------------------- | -------------- | --------- | ---------- |
| Observability "hooks" = request-correlated structured logs carrying trace fields + latency/outcome; no metrics scrape surface | Structured JSON logs (env-toggled) + request-ID/trace-context; metrics deferred | Correlated latency-bearing logs are the substrate every TDD metric derives from and stay provider-neutral; a scrape endpoint/dependency would lock what OQ #10 defers (AD-041) | y (auto, AD-041) |
| Deployment shape = a Compose **overlay** over the base file, not a standalone prod compose | `docker-compose.prod.yml` applied via `-f docker-compose.yml -f docker-compose.prod.yml` | Keeps local aligned with prod topology (ADR-0008 §3); a standalone file duplicates and drifts (AD-042) | y (auto, AD-042) |
| Required trace fields concretely wired this cycle | `request_id` (always) + `user_id` (when authenticated) for HTTP; `job_id` + `source_id` for the worker; `bind_trace()` seam left for `source_id`/`session_id`/provider-model to attach where cheap | The TDD lists the full field set as the target; this cycle wires the always-available ones and provides the binding seam the rest use, rather than half-plumbing every field (bounded scope) | y (auto) |
| Trace context propagation mechanism | `contextvars.ContextVar` + a `logging.Filter` that injects the current trace fields onto every record | One seam auto-enriches every log line in a request/task without threading `extra=` everywhere; standard-library only | y (auto) |
| Default log format stays human-readable; JSON is opt-in via env | `LEARNY_LOG_FORMAT=human` default, `json` in the prod overlay | Local dev readability is preserved; production gets machine-parseable logs without a code change | y (auto) |
| Production images pinned in the overlay, not the dev base | Overlay overrides `image:` to pinned tags; base keeps floating dev tags | Reproducible prod pulls without disrupting the dev workflow; bounded blast radius | y (auto) |
| Backup retention schedule / offsite target | Documented as an operator TODO in `backups.md`, not fixed | Retention/offsite depends on the (deferred) VPS provider and cost, OQ #10; the runbook gives the commands and drill, leaves the policy to the operator | y (auto) |
| Ops docs are verified by presence + required-section/content checks, not by executing backup/restore against a live host | Light `test_ops_docs` presence/content assertions | Runbook correctness is operational, not unit-testable in the gate; the checks guard the required triggers/commands stay present (regression) | y (auto) |

**Open questions:** none — all resolved or logged above. TDD OQ #10 (backup/TLS/reverse-proxy/monitoring stack) remains intentionally open project-wide and is flagged at the merge gate as the blocking follow-up; it is not a spec-level open question for this cycle.

---

## User Stories

### P1: Production-like deployment shape ⭐ MVP

**User Story**: As the operator, I want a production Compose overlay distinct from local dev so that I can run the full MVP topology in a first production-like environment with hardened defaults.

**Why P1**: Phase 10's outcome ("MVP can run in local and first production-like topology") is not met without a deployable shape.

**Acceptance Criteria**:

1. WHEN the prod overlay is merged over the base compose THEN the `db`, `redis`, and `minio` services SHALL publish no host ports (internal network only).
2. WHEN the prod overlay is merged over the base compose THEN every long-running service (`api`, `worker`, `web`, `db`, `redis`, `minio`) SHALL declare a restart policy of `unless-stopped` (or `always`).
3. WHEN the prod overlay is merged THEN no service image SHALL use a floating `:latest` tag; each pinned to an explicit version tag.
4. WHEN the prod overlay is merged THEN the `api` service SHALL run with `LEARNY_SESSION_COOKIE_SECURE=true` and `LEARNY_ENVIRONMENT=production` and `LEARNY_LOG_FORMAT=json`.
5. WHEN the prod overlay is merged THEN service secrets (DB password, storage keys, session/CSRF config) SHALL be sourced from environment/`env_file` injection, not inline literal values in the overlay.
6. WHEN the frontend production image target is built THEN it SHALL run a built Next.js app (`next build` output served by `next start`/standalone), not `next dev`.

**Independent Test**: Load `docker-compose.prod.yml` (and the base) as YAML and assert the structural hardening properties; build the frontend with `npm run build`; assert the production Dockerfile target uses a build+start flow.

---

### P1: Request-correlated observability hooks ⭐ MVP

**User Story**: As an operator diagnosing an incident, I want every log line within a request/worker task correlated by a request/trace ID and emitted as structured data with latency and outcome so that I can trace a user-facing failure end to end.

**Why P1**: The TDD requires trace fields, lifecycle logs, and latency; without correlation logs are not actionable in production.

**Acceptance Criteria**:

1. WHEN an HTTP request arrives without an `X-Request-ID` header THEN the system SHALL generate a request ID, bind it to the request's trace context, and echo it in the response `X-Request-ID` header.
2. WHEN an HTTP request arrives with an `X-Request-ID` header THEN the system SHALL adopt that value (bounded/sanitized) as the request ID and echo it back.
3. WHEN any log record is emitted during an HTTP request THEN it SHALL carry the request's `request_id` field automatically (without the call site passing it).
4. WHEN an authenticated request logs a record THEN the record SHALL also carry the `user_id` trace field.
5. WHEN an HTTP request completes THEN the system SHALL emit exactly one structured request-access log record carrying method, request path/route, status code, and duration in milliseconds.
6. WHEN `LEARNY_LOG_FORMAT=json` THEN log records SHALL be emitted as single-line JSON objects containing the standard fields plus the bound trace fields.
7. WHEN a sensitive field (password, token, secret, cookie, authorization) is attached to a log record under JSON format THEN its value SHALL still be redacted (existing NFR-SEC-004 redaction preserved).
8. WHEN a worker ingestion task runs THEN its log records SHALL carry `job_id` and `source_id` trace fields, and the terminal (succeeded/failed) record SHALL carry a duration in milliseconds.

**Independent Test**: Drive the app with `TestClient` and assert `X-Request-ID` echo + generation; capture log records and assert trace-field presence, single access log with duration, JSON serialization, and preserved redaction; call the worker task with fakes and assert `job_id`/`source_id`/duration on records.

---

### P2: Operator runbooks — backup/restore and rollback

**User Story**: As the operator, I want documented backup/restore and rollback procedures so that I can recover data and safely revert a bad deploy.

**Why P2**: Required by Phase 10 ("backups/restore notes, and rollback checks") but has no runtime surface; it is durable operator documentation, not shipped behavior.

**Acceptance Criteria**:

1. WHEN an operator opens `docs/ops/backups.md` THEN it SHALL document backing up and restoring PostgreSQL (logical dump + restore) and the object-storage bucket, with concrete provider-neutral commands and a restore-drill step.
2. WHEN an operator opens `docs/ops/rollback.md` THEN it SHALL document independent revert of the `api`, `worker`, and `web` images, migration reversibility (and the forward-only exception path), and reproduce the TDD operational rollback-triggers table.
3. WHEN either runbook references the current corpus re-ingestion behavior THEN it SHALL correctly state atomic-replace-with-no-versioning (AD-018) and its rollback implication.

**Independent Test**: A presence/content check asserts both files exist and contain the required section headings and key commands/triggers.

---

## Edge Cases

- WHEN an inbound `X-Request-ID` is absurdly long or contains control/newline characters THEN the system SHALL sanitize/truncate it (bounded length, safe charset) before binding and echoing, so it cannot inject into log lines.
- WHEN a request handler raises an application error mapped by the exception handlers (e.g. 401/404/422) THEN the access log SHALL still be emitted with that status AND the `X-Request-ID` response header SHALL be present (these responses are produced inside the request-context middleware).
- WHEN a truly unhandled exception propagates past the exception handlers THEN the request-access log SHALL still be emitted with status 500 (via the middleware's `finally`); the response itself is produced by Starlette's outermost error handler, so the `X-Request-ID` header is not guaranteed on that specific response — this is the one accepted gap and is noted in the code.
- WHEN `configure_logging()` is called more than once THEN it SHALL remain idempotent and SHALL NOT attach duplicate handlers/filters or lose the redaction filter.
- WHEN the trace context is read outside any request/task (module import, standalone script) THEN trace-field injection SHALL be a no-op (records carry no stale/foreign trace fields).
- WHEN a worker task fails and retries THEN each attempt's logs SHALL carry the same `job_id`/`source_id` and the retry/terminal records SHALL not leak secrets (existing ING-08 behavior preserved).

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| -------------- | ----- | ----- | ------ |
| PROD-01 | P1 Deploy | Design | Pending |
| PROD-02 | P1 Deploy | Design | Pending |
| PROD-03 | P1 Deploy | Design | Pending |
| PROD-04 | P1 Deploy | Design | Pending |
| PROD-05 | P1 Deploy | Design | Pending |
| PROD-06 | P1 Deploy | Design | Pending |
| PROD-07 | P1 Observability | Design | Pending |
| PROD-08 | P1 Observability | Design | Pending |
| PROD-09 | P1 Observability | Design | Pending |
| PROD-10 | P1 Observability | Design | Pending |
| PROD-11 | P1 Observability | Design | Pending |
| PROD-12 | P1 Observability | Design | Pending |
| PROD-13 | P1 Observability | Design | Pending |
| PROD-14 | P1 Observability | Design | Pending |
| PROD-15 | P2 Runbooks | Design | Pending |
| PROD-16 | P2 Runbooks | Design | Pending |
| PROD-17 | P2 Runbooks | Design | Pending |
| PROD-18 | Edge: request-id sanitization | Design | Pending |
| PROD-19 | Edge: access log on exception + idempotent logging | Design | Pending |
| PROD-20 | Edge: trace no-op outside request + retry field stability | Design | Pending |

**ID format:** `PROD-[NUMBER]`

**Status values:** Pending → In Design → In Tasks → Implementing → Verified

**Coverage:** 20 total, 0 mapped to tasks yet (mapped in tasks.md).

---

## Success Criteria

How we know the feature is successful:

- [ ] `docker compose -f docker-compose.yml -f docker-compose.prod.yml config` renders a hardened topology (verified structurally).
- [ ] Every log line inside a request is correlatable by `request_id`; JSON logs are emitted under the prod format; secrets stay redacted.
- [ ] An operator can follow `backups.md` and `rollback.md` to back up/restore and to revert a deploy without reading source code.
- [ ] No new monitoring/metrics/TLS/reverse-proxy dependency is introduced; OQ #10 remains the single flagged follow-up.
