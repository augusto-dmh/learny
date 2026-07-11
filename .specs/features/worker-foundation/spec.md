# Worker Foundation Specification

## Problem Statement

Uploaded sources currently sit at `status="uploaded"` forever — there is no way to run long-running work outside an HTTP request, no durable record of a job's state, and no way for a user to see progress or a failure reason. This cycle (TDD Phase 4) builds the worker foundation: a durable ingestion-job lifecycle driven by a Celery task over Redis, with bounded retries, terminal failure state, an append-only event log, and the API + minimal UI to start and observe ingestion. The actual EPUB parsing is out of scope and deferred to Phase 5 — the Celery task body is a stub that drives the real state machine but does no parsing.

## Goals

- [ ] An explicit endpoint enqueues a Celery task that drives a durable ingestion job through `queued → running → succeeded/failed` **entirely outside the HTTP request** (no parsing in the request handler and no parsing in the task this cycle).
- [ ] Job state, attempt count, terminal failure reason, and an ordered progress-event log are durable in PostgreSQL and readable via API and the sources screen.
- [ ] Retries are bounded with backoff; exhausted retries produce an inspectable `failed` job with a durable error; a terminal job can be restarted.
- [ ] At most one active ingestion job exists per source at any time.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
| ------- | ------ |
| Real EPUB parsing, canonical corpus, derived Markdown, chunks, embeddings, indexes | Phase 5 (EPUB corpus pipeline) and Phase 6 (retrieval). The task body is a stub this cycle. |
| Auto-enqueue ingestion on upload | Decided AD-013: explicit `POST .../ingestion` trigger only; upload flow (Cycle 2) is unchanged. |
| Live progress percentages / real progress milestones | Stub task has no real work to report; events this cycle are lifecycle transitions only. Real milestones arrive in Phase 5. |
| Frontend auto-refresh / polling / websockets for status | Status reflects on page load and after the start action; continuous refresh deferred to keep the cycle bounded. |
| Priority queues, concurrency limits, dedicated queues, Celery beat / scheduled jobs | Default single queue + conservative worker defaults (already configured) suffice for foundation. |
| Presigned direct-to-storage upload, PDF, re-ingestion versioning of corpus IDs | Deferred by ADR-018 / ADR-011 / TDD Identifier Rules; no corpus exists yet. |
| Cancelling / pausing an in-flight job | Not required for the foundation; terminal-state restart covers the failure recovery path. |

---

## Assumptions & Open Questions

Every ambiguity is resolved or recorded here — nothing is left silently unclear.

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --------------------- | -------------- | --------- | ---------- |
| Ingestion job status vocabulary | `queued`, `running`, `succeeded`, `failed` (`queued` and `running` are the two "active" states) | Minimal terminal + active set that supports retry and restart; no `cancelled`/`paused` this cycle | y (design of this cycle) |
| `source.status` is a projection of the latest job | `uploaded` → (start) `processing` → `ready` on success / `failed` on terminal failure | Sources screen already renders `source.status`; keeps the list badge correct without joining jobs. Column is free-text `Text` (Cycle 2), so no enum migration needed | y |
| "Stub task" body | Task marks `running`, performs a no-op placeholder (`# TODO(Phase 5): parse EPUB`), marks `succeeded` | Phase boundary: Phase 4 owns the engine, Phase 5 owns the payload | y (AD confirmed) |
| Retry/failure must be testable despite a stub that never naturally fails | The task body calls one injectable step; tests/verifier force it to raise to exercise retry + terminal failure | Behavior-level ACs need a controllable fault seam; also what the discrimination sensor needs | y |
| `GET .../ingestion` when no job exists yet | Returns `404` (no ingestion job); the sources screen relies on `source.status="uploaded"` for the pre-start state | Clean REST; avoids a null-shaped 200; the list already conveys "not started" | y |
| Duplicate start while a job is active | `409 Conflict`; no second job enqueued | Enforces "at most one active job per source"; concurrency guarded at the DB level | y |
| Broker/enqueue failure during start | Job is marked `failed` with a durable error and `source.status="failed"`; endpoint returns `502`; no phantom `queued` job is left blocking restart | Keeps the restart path usable (prior job terminal → new job allowed); avoids a stuck active job | y |
| Non-owner / missing source on start or read | `404` (not `403`) | Consistent with Cycle 2 `GetSource` (no existence disclosure); reuses `AuthorizeOwnership` → `SourceNotFound` mapping | y |
| Observability surface this cycle | Structured worker logs (job id + source id, no secrets) on start/retry/success/failure, plus the `ingestion_events` table and the read API | ADR-005 "durable and observable"; existing logging redaction (Cycle 1) applies | y |
| Job/event ownership | Reachable only through the parent `source` (which has `user_id`); jobs/events carry no separate `user_id` | TDD Identifier Rules: user-owned via a parent with clear ownership | y |

**Open questions:** none — all resolved or logged above.

---

## User Stories

### P1: Start ingestion for an uploaded source ⭐ MVP

**User Story**: As a source owner, I want to start ingestion for an uploaded source so that long-running processing runs in the background instead of blocking my request.

**Why P1**: This is the entry point to the whole worker path; without it nothing runs off the request thread.

**Acceptance Criteria**:

1. WHEN the owner sends `POST /api/sources/{source_id}/ingestion` for a source that has no active job THEN the system SHALL create an `ingestion_jobs` row with status `queued`, enqueue exactly one Celery task carrying only `source_id` and `ingestion_job_id`, set `source.status="processing"`, append a `queued` event, and respond `202` with the job id and status.
2. WHEN the enqueued task executes THEN it SHALL transition the job `queued → running` (append `started` event), run its stub body outside the HTTP request, then transition to `succeeded` (append `succeeded` event) and set `source.status="ready"`.
3. WHEN a `POST .../ingestion` targets a source that already has an active (`queued` or `running`) job THEN the system SHALL NOT enqueue a second task, SHALL NOT create a second active job, and SHALL respond `409`.
4. WHEN a `POST .../ingestion` targets a source whose latest job is terminal (`succeeded` or `failed`) THEN the system SHALL create a new `queued` job and enqueue it (restart).
5. WHEN a `POST .../ingestion` targets a source the caller does not own, or a source that does not exist THEN the system SHALL respond `404` and enqueue nothing.

**Independent Test**: POST for an uploaded owned source → 202 + job id; assert a `queued` row exists, one task was enqueued (fake broker), and `source.status="processing"`; run the task → job `succeeded`, `source.status="ready"`.

---

### P1: Observe ingestion progress and failures ⭐ MVP

**User Story**: As a source owner, I want to read the current ingestion status, attempts, failure reason, and event history so that I can see what happened.

**Why P1**: "Visible progress" is the stated Phase 4 outcome; a job the user can't inspect is not durable-and-observable.

**Acceptance Criteria**:

1. WHEN the owner sends `GET /api/sources/{source_id}/ingestion` and an ingestion job exists THEN the system SHALL respond `200` with the latest job's status, attempt count, terminal error (null unless `failed`), and its events in chronological order.
2. WHEN the owner sends `GET .../ingestion` and no ingestion job exists for that source THEN the system SHALL respond `404`.
3. WHEN a `GET .../ingestion` targets a source the caller does not own, or a source that does not exist THEN the system SHALL respond `404`.
4. WHEN the read response is serialized THEN it SHALL NOT expose internal fields (`object_key`, `checksum`) or any secret; it exposes only job/event state.

**Independent Test**: Start a job, run it to `succeeded`, GET → 200 with status `succeeded`, attempts `1`, `error=null`, and ordered events `[queued, started, succeeded]`.

---

### P1: Durable bounded retries and terminal failure ⭐ MVP

**User Story**: As a source owner, I want a failing ingestion to retry a bounded number of times and, if it still fails, leave a durable inspectable failure so that transient errors self-heal and permanent errors are visible.

**Why P1**: ADR-005 and the Phase 4 outcome require durable retries and inspectable failure state; this is the reliability core of the foundation.

**Acceptance Criteria**:

1. WHEN the task body raises a retryable error THEN Celery SHALL retry up to the configured maximum with backoff, and each attempt SHALL increment the job's attempt count and append a `retrying` event with the error summary.
2. WHEN retries are exhausted THEN the system SHALL mark the job `failed`, persist a durable `last_error` (redacted, non-secret), set `source.status="failed"`, and append a `failed` event — all readable via `GET .../ingestion`.
3. WHEN a task runs but its `ingestion_jobs` row is missing THEN the task SHALL exit without raising (defensive no-op) and SHALL NOT create state.
4. WHEN the broker/enqueue call fails during `POST .../ingestion` THEN the system SHALL mark the just-created job `failed` with a durable error, set `source.status="failed"`, leave no active job, and respond `502`.

**Independent Test**: Force the injectable step to raise; drive the task; assert attempts increment and `retrying` events appear per attempt; after the max, assert job `failed`, `last_error` persisted, `source.status="failed"`, `failed` event present.

---

### P1: Concurrency guard — at most one active job per source ⭐ MVP

**User Story**: As the system, I want to guarantee at most one active ingestion job per source so that concurrent start requests cannot double-enqueue.

**Why P1**: Without this guard, AC "duplicate start → 409" is racy and the queue can carry duplicate work.

**Acceptance Criteria**:

1. WHEN two `POST .../ingestion` requests for the same source race THEN the system SHALL create at most one active job and enqueue at most one task; the loser SHALL receive `409`.
2. WHEN an active job exists for a source THEN any attempt to create another active job for that source SHALL be rejected at the persistence layer (not only by an application-level read-then-write check).

**Independent Test**: With one active job present, attempt to create a second active job for the same `source_id` → persistence rejects it; API returns `409`.

---

### P1: Visible ingestion status on the sources screen ⭐ MVP

**User Story**: As a source owner using the web app, I want to see each source's ingestion status and start ingestion from the sources screen so that the background work is visible and controllable.

**Why P1**: AD-010 requires each cycle to ship a full vertical slice; the Phase 4 outcome "visible progress" must reach the user.

**Acceptance Criteria**:

1. WHEN the owner views the sources screen THEN each source SHALL display its ingestion status derived from `source.status` (e.g. `uploaded`, `processing`, `ready`, `failed`).
2. WHEN a source is in the `uploaded` state THEN the screen SHALL show a "Start ingestion" control for it.
3. WHEN the owner activates "Start ingestion" THEN the browser SHALL call the same-origin Next.js proxy to `POST /api/sources/{id}/ingestion` and reflect the resulting `processing` state (on success) or a surfaced error (on `409`/`502`).
4. WHEN a source is already `processing`, `ready`, or `failed` THEN the screen SHALL show that status and SHALL NOT offer a second "Start ingestion" action for an active job.

**Independent Test**: Render the sources screen with a mix of `uploaded`/`processing`/`ready`/`failed` sources; assert the badge per row and that "Start ingestion" appears only for `uploaded`; click it → proxy POST issued, row reflects `processing`.

---

## Edge Cases

- WHEN a start request targets a source in `processing` (active job) THEN system SHALL return `409` and not enqueue (ING-03).
- WHEN a start request targets a source in `failed` THEN system SHALL create a fresh job and enqueue (restart, ING-05).
- WHEN the broker is unreachable at enqueue time THEN system SHALL mark the job `failed`, surface `502`, and leave no active job (ING-11).
- WHEN a task fires for a job row that no longer exists THEN the task SHALL no-op without error (ING-08 AC3).
- WHEN `GET .../ingestion` is called before any start THEN system SHALL return `404` (ING-12).
- WHEN a non-owner calls start or read THEN system SHALL return `404` with no existence disclosure (ING-04).

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| -------------- | ----- | ----- | ------ |
| ING-01 | P1: Start ingestion (create queued job, enqueue, source→processing, 202) | Execute | Verified |
| ING-02 | P1: Start ingestion (task drives queued→running→succeeded off-request, source→ready) | Execute | Verified |
| ING-03 | P1: Concurrency guard (duplicate start on active job → 409, no second job) | Execute | Verified |
| ING-04 | P1: Start/read authz (non-owner/missing → 404) | Execute | Verified |
| ING-05 | P1: Restart (terminal job → new queued job) | Execute | Verified |
| ING-06 | P1: Observe (GET returns latest status, attempts, error, ordered events) | Execute | Verified |
| ING-07 | P1: Retries (bounded retries with backoff, attempts increment, retrying events) | Execute | Verified |
| ING-08 | P1: Terminal failure (failed + durable last_error + source→failed + failed event; missing-row no-op) | Execute | Verified |
| ING-09 | P1: Persistence (ingestion_jobs + ingestion_events durable; ownership via parent source; queue carries ids only) | Execute | Verified |
| ING-10 | P1: Frontend (status badge + Start ingestion via proxy; no double-start) | Execute | Verified |
| ING-11 | Edge: broker enqueue failure → job failed, 502, no phantom active job | Execute | Verified |
| ING-12 | Edge: GET with no job yet → 404 | Execute | Verified |

**ID format:** `ING-[NUMBER]`

**Status values:** Pending → In Design → In Tasks → Implementing → Verified

**Coverage:** 12 total, 12 mapped to tasks (T1–T8), 12 Verified (Verifier PASS — 8/8 sensor mutants killed, 0 gaps; see `validation.md`).

---

## Success Criteria

How we know the feature is successful:

- [ ] A source can be taken `uploaded → processing → ready` end-to-end with the state machine driven entirely by a Celery worker, not the request handler.
- [ ] A forced-failing task retries a bounded number of times and lands in `failed` with a durable, redacted `last_error` and a `failed` event — all visible via `GET .../ingestion`.
- [ ] Concurrent start requests never produce two active jobs (DB-level guard proven).
- [ ] The sources screen shows per-source ingestion status and starts ingestion through the same-origin proxy.
- [ ] No EPUB parsing exists in either the request handler or the task (stub body only); Phase 5 boundary is intact.
