# Tasks — Cycle 3: Worker Foundation

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user — do not proceed without it.**

---

**Design**: `.specs/features/worker-foundation/design.md`
**Status**: Done — all 8 tasks executed and committed (`ebff6f6..9e3060d`), Verifier PASS (12/12 ACs, 8/8 mutants killed; `validation.md`). Not yet merged.

> 8 tasks / 5 phases. >3 phases → at Execute, offer one sub-agent per phase (offer-then-confirm). `[P]` = order-free within a phase. One atomic commit per task; gate green before done. AC refs trace to spec (ING-01..12).

---

## Test Coverage Matrix

> Generated from codebase, project guidelines, and spec — confirm before Execute. Guidelines found: `CLAUDE.md`, `.specs/codebase/CONVENTIONS.md` (ruff `E,F,I,UP,B`, line 100; pytest `testpaths=["tests"]`), `celery-workers` skill (task-design, reliability, state-and-progress). Cycle-1/2 tests sampled: `backend/tests/test_application_sources.py`, `test_repositories.py`, `test_web_sources.py`, `test_migrations.py`, `conftest.py` (rolled-back-txn + `sources_client` override pattern), `frontend/tests/sources-client.test.ts`, `sources-screen.test.tsx`.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| ---------- | ------------------ | -------------------- | ---------------- | ----------- |
| Domain entities/ports (`IngestionJob` transitions, `IngestionEvent`, status/event constants, new ports) | unit | Every transition helper (`started`/`succeeded`/`retrying`/`failed`) asserts new immutable state + attempts; constants correct | `backend/tests/test_domain_ingestion.py` | `cd backend && uv run pytest` |
| Application services + errors (`StartIngestion`, `RunIngestion`, `ReadIngestion`, compensate) | unit | All branches; 1:1 to spec ACs; every listed edge case (active→409, non-owner→404, no-job→404, restart, missing-row no-op, terminal no-op, retry vs terminal) | `backend/tests/test_application_ingestion.py` | `cd backend && uv run pytest` |
| Repositories (`SqlAlchemyIngestionJobRepository`, `SqlAlchemyIngestionEventRepository`, `SourceRepository.set_status`) | integration | add/get/get_latest/update; **partial unique index rejects 2nd active job**; events append + chronological list; set_status updates projection | `backend/tests/test_repositories.py` (extend) | `cd backend && uv run pytest` (live DB) |
| Migration `0003` | integration | Applies up/down; `ingestion_jobs`/`ingestion_events` schema (FKs cascade, indexes, partial unique index) matches design | `backend/tests/test_migrations.py` (extend) | `cd backend && uv run pytest` (live DB) |
| Celery task + adapters (`run_ingestion`, `NoOpIngestionStep`, `CeleryIngestionEnqueuer`) | integration | Task drives real engine: happy queued→running→succeeded (+source ready); failing step → terminal failed (+source failed, last_error); retryable+remaining → retry branch; exhausted → failed; missing-row no-op; terminal-status no-op. Enqueuer calls `apply_async` with ids only. No Redis (invoke task fn directly; mock `apply_async`) | `backend/tests/test_worker_tasks.py` | `cd backend && uv run pytest` (live DB) |
| Web router (`/api/sources/{id}/ingestion`) | integration | Every route: POST happy 202 (+enqueuer called) + duplicate-active 409 + non-owner/missing 404 + enqueue-failure 502 (+job failed, no active) + unauth 401 + bad CSRF/origin 403; GET 200 with ordered events + no-job 404 + non-owner 404 | `backend/tests/test_web_ingestion.py` | `cd backend && uv run pytest` (live DB) |
| Frontend client (`lib/sources.ts` `startIngestion`) | unit (vitest) | POSTs same-origin `/api/sources/{id}/ingestion` with `X-CSRF-Token`; parses `IngestionSummary`; throws backend `detail` on non-OK (409/502) | `frontend/tests/ingestion-client.test.ts` | `cd frontend && npm test` |
| Frontend screen (`SourcesPanel`) | unit (vitest) | Status badge per row; "Start ingestion" only for `uploaded`; click → proxy POST + row reflects `processing`; error surfaced on 409/502; no double-start for active | `frontend/tests/sources-screen.test.tsx` (extend) | `cd frontend && npm test` |
| `celery_app.py` conf / `main.py` include / constants-only | none | — (behavior covered by task + web integration tests; build gate only) | — | build gate only |

## Parallelism Assessment

> Generated from codebase — confirm before Execute.

| Test Type | Parallel-Safe? | Isolation Model | Evidence |
| --------- | -------------- | --------------- | -------- |
| Backend unit (fakes) | Yes | Pure in-memory fakes, no shared store | `backend/tests/fakes.py`, `test_application_sources.py` |
| Backend integration (DB) | No | Shared session engine + rolled-back txn per test; migration test upgrades shared DB | `backend/tests/conftest.py` (`db_engine` session-scoped, `db_conn` rollback) |
| Frontend (vitest) | Yes | Per-test mocked `fetch`, no shared backend | `frontend/tests/sources-client.test.ts` |

**Consequence:** integration-tested tasks (T2, T3, T5, T6) run their tests sequentially — no `[P]`. Unit/vitest tasks may carry `[P]` when code-independent.

## Gate Check Commands

> Generated from codebase — confirm before Execute.

| Gate Level | When to Use | Command |
| ---------- | ----------- | ------- |
| Quick | After unit-only tasks (T1, T4) | `cd backend && uv run pytest tests/test_domain_ingestion.py tests/test_application_ingestion.py` |
| Full | After integration tasks (T2, T3, T5, T6) | `cd backend && uv run pytest` (requires live DB from `docker.exe compose up -d db`; `LEARNY_TEST_DATABASE_URL` set) |
| Frontend | After frontend tasks (T7, T8) | `cd frontend && npm test` |
| Build | After phase completion / config-only changes | `cd backend && uv run ruff check . && uv run pytest && cd ../frontend && npm test` (ruff `format --check` scoped to new files — repo-wide drift is a pre-existing Known Gap, STATE.md) |

---

## Execution Plan

### Phase 1: Schema & domain foundation

```
T1 ─┐   (T1 domain+ports; T2 schema+migration — order-free)
T2 ─┘
```

### Phase 2: Persistence & application

```
{T1, T2} ──→ T3        (repositories, integration)
T1 ──────────→ T4 [P]  (application services + fakes, unit; order-free vs T3)
```

### Phase 3: Worker

```
{T3, T4} ──→ T5
```

### Phase 4: Web

```
{T3, T4, T5} ──→ T6
```

### Phase 5: Frontend

```
T6 ──→ T7 ──→ T8
```

---

## Task Breakdown

### T1 — Domain ingestion entities + ports

**What**: Add `IngestionJob` and `IngestionEvent` frozen dataclasses with immutable transition helpers (`started`/`succeeded`/`retrying`/`failed`), status/event constants (`IngestionStatus`, `ACTIVE_STATUSES`, event types), and the new ports: `IngestionJobRepository`, `IngestionEventRepository`, `IngestionStep`, `IngestionEnqueuer`, plus `set_status` on `SourceRepository`.
**Where**: `backend/app/domain/entities.py`, `backend/app/domain/ports.py`
**Depends on**: None
**Reuses**: `@dataclass(frozen=True)` + `runtime_checkable` Protocol + None-on-missing conventions from existing `entities.py`/`ports.py`
**Requirement**: ING-09 (durable job/event shape), supports ING-01/02/07/08

**Tools**: MCP: NONE · Skill: `ruff`

**Done when**:
- [ ] `IngestionJob`/`IngestionEvent` defined with all design fields; no framework/SDK imports (import-boundary respected)
- [ ] Transition helpers return new frozen instances: `started`→running+attempts+1; `succeeded`→succeeded; `retrying`→last_error set; `failed`→failed+last_error
- [ ] Four new ports + `SourceRepository.set_status` defined as Protocols
- [ ] Quick gate passes: `cd backend && uv run pytest tests/test_domain_ingestion.py`
- [ ] Test count: ≥5 unit tests pass (one per transition + constants)

**Tests**: unit — each transition helper asserts resulting status/attempts/last_error; `ACTIVE_STATUSES == {queued, running}`
**Gate**: quick

---

### T2 — Ingestion tables metadata + migration `0003` [P]

**What**: Define `ingestion_jobs` and `ingestion_events` tables under the shared `MetaData` (incl. the partial unique index `WHERE status IN ('queued','running')`), and add reversible Alembic migration `0003_ingestion_schema.py`.
**Where**: `backend/app/infrastructure/db/metadata.py`, `backend/migrations/versions/0003_ingestion_schema.py`
**Depends on**: None (schema standalone; ordered before T3)
**Reuses**: `NAMING_CONVENTION`/`metadata`; `0002_sources_schema.py` migration pattern; `Index(..., postgresql_where=...)` for the partial unique index
**Requirement**: ING-09, ING-03 (partial unique index)

**Tools**: MCP: NONE · Skill: `uv` (run alembic)

**Done when**:
- [ ] `ingestion_jobs` (id, source_id FK→sources CASCADE + index, status, attempts default 0, last_error nullable, timestamps) + `ingestion_events` (id, job_id FK→ingestion_jobs CASCADE + index, type, message nullable, created_at) match design
- [ ] Partial unique index `uq_ingestion_jobs_active_source` on `(source_id) WHERE status IN ('queued','running')` present
- [ ] `alembic upgrade head` then `downgrade` both succeed against live DB
- [ ] Full gate passes: `cd backend && uv run pytest` (migration test asserts tables + FKs + partial unique index)
- [ ] Test count: existing migration tests + ≥2 new pass

**Tests**: integration — migration up/down; both tables + cascade FKs + indexes + partial unique index exist
**Gate**: full

---

### T3 — Ingestion repositories + `SourceRepository.set_status`

**What**: Connection-injected `SqlAlchemyIngestionJobRepository` (`add`, `get_by_id`, `get_latest_for_source`, `update`) and `SqlAlchemyIngestionEventRepository` (`append`, `list_for_job`); add `set_status` to `SqlAlchemySourceRepository`.
**Where**: `backend/app/infrastructure/db/repositories.py`
**Depends on**: T1, T2
**Reuses**: `SqlAlchemySourceRepository` structure (Connection in ctor, Core `insert`/`select`/`update`), `_to_*` mapping helpers
**Requirement**: ING-03, ING-06, ING-09, supports ING-01/02/05/08

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] `add` inserts + returns job; a 2nd active job for the same source raises `IntegrityError` (partial unique index)
- [ ] `get_by_id`/`get_latest_for_source` (newest by `created_at`) return entity or `None`; `update` persists status/attempts/last_error/updated_at
- [ ] `append` inserts event; `list_for_job` returns chronological; `set_status` updates `sources.status`+`updated_at`
- [ ] Full gate passes: `cd backend && uv run pytest`
- [ ] Test count: ≥6 new repository tests pass (no silent deletions)

**Tests**: integration — add/get/get_latest/update roundtrip; duplicate-active rejected; events append + ordered; set_status projection
**Gate**: full

---

### T4 — Application services + errors + fakes [P]

**What**: `StartIngestion`, `RunIngestion` (with `begin_run`/`run_step`/`complete`/`record_retry`/`fail`), `ReadIngestion`, and errors (`ActiveIngestionExists`, `IngestionNotFound`, `EnqueueFailed`); plus test fakes (`FakeIngestionJobRepository` with active-guard, `FakeIngestionEventRepository`, `FakeIngestionStep`, `FakeIngestionEnqueuer`).
**Where**: `backend/app/application/ingestion.py` (new), `backend/app/application/errors.py` (extend), `backend/tests/fakes.py` (extend)
**Depends on**: T1
**Reuses**: `AuthorizeOwnership`, `SourceNotFound`, `GetSource` ownership→404 pattern; constructor-injection style of `CreateSource`; `FakeSourceRepository` style
**Requirement**: ING-01, ING-02, ING-03, ING-04, ING-05, ING-06, ING-07, ING-08, ING-12

**Tools**: MCP: NONE · Skill: `ruff`

**Done when**:
- [ ] `StartIngestion`: owner+exists check (else `SourceNotFound`); create queued job (active→`ActiveIngestionExists`); `set_status(processing)`; append `queued`; terminal-prior-job path creates a new job (ING-05)
- [ ] `RunIngestion.begin_run` → `None` on missing/terminal (ING-08 no-op); else running+attempts+1+`set_status(processing)`+`started`; `complete`→succeeded+ready+`succeeded`; `record_retry`→last_error+`retrying`; `fail`→failed+`set_status(failed)`+`failed`
- [ ] `ReadIngestion`: owner check (`SourceNotFound`); latest job (`None`→`IngestionNotFound`) + ordered events
- [ ] Quick gate passes: `cd backend && uv run pytest tests/test_domain_ingestion.py tests/test_application_ingestion.py`
- [ ] Test count: ≥12 unit tests pass (no silent deletions)

**Tests**: unit (fake ports) — 1:1 to spec ACs incl. active→409, non-owner→404, no-job→404, restart, retry vs terminal, missing/terminal no-op
**Gate**: quick

---

### T5 — Celery task + step/enqueuer adapters + celery config

**What**: `run_ingestion` bound task (owns retry decision via `self.retry`/`max_retries`, per-transition `engine.begin()` UoWs, structured logs); `NoOpIngestionStep` default adapter (`# TODO(Phase 5): parse EPUB`); `CeleryIngestionEnqueuer` (`apply_async` ids only); register `include=["app.worker.tasks"]` and extend the conf block (time limits, `task_track_started`, `visibility_timeout`).
**Where**: `backend/app/worker/tasks.py` (new), `backend/app/infrastructure/worker/steps.py` (new), `backend/app/infrastructure/worker/enqueuer.py` (new), `backend/app/worker/celery_app.py` (edit)
**Depends on**: T3, T4
**Reuses**: `celery-workers` skill (thin-adapter task, `engine.begin()`, manual `self.retry`, idempotent terminal no-op); `get_engine`; repositories from T3; services from T4
**Requirement**: ING-02, ING-07, ING-08, ING-09 (queue ids only)

**Tools**: MCP: `context7` (Celery task/retry API) · Skill: `celery-workers`

**Done when**:
- [ ] `run_ingestion(source_id, job_id)` drives happy path against real engine: queued→running→succeeded, `source.status="ready"`, events `[queued(seeded),started,succeeded]`
- [ ] Injected failing step → terminal `failed` + durable `last_error` + `source.status="failed"` + `failed` event; retryable error with retries remaining → `record_retry` + `self.retry`; exhausted → `fail`
- [ ] Missing job row → no-op; already-terminal job → no-op (idempotent redelivery)
- [ ] `CeleryIngestionEnqueuer.enqueue_ingestion` calls `run_ingestion.apply_async(args=[str(source_id), str(job_id)])` (asserted via mock; no Redis needed)
- [ ] `celery_app` registers the task and keeps `acks_late`/`prefetch=1` + adds time limits/`visibility_timeout`
- [ ] Full gate passes: `cd backend && uv run pytest`
- [ ] Test count: ≥7 integration tests pass (no silent deletions)

**Tests**: integration — task lifecycle (success/terminal-failure/retry-branch/exhausted/missing/terminal-noop) on real engine with injected step + fake bound `self`; enqueuer `apply_async` args
**Gate**: full

**Commit**: `feat(ingestion): durable ingestion job lifecycle via celery worker`

---

### T6 — `/api/sources/{id}/ingestion` router + wiring + error mappings

**What**: FastAPI router with `POST` (202, auth+CSRF+origin, commit-then-enqueue-then-compensate) and `GET`; `IngestionSummary`/`IngestionEventView`; `get_ingestion_uow` factory dependency + `get_ingestion_enqueuer` + composition-root builders; error mappings (`ActiveIngestionExists`→409, `IngestionNotFound`→404, `EnqueueFailed`→502); `main.py` include; `conftest.py` `ingestion_client` fixture (overrides uow→`db_conn`, enqueuer→fake).
**Where**: `backend/app/infrastructure/web/ingestion.py` (new), `backend/app/infrastructure/web/dependencies.py` (extend), `backend/app/infrastructure/web/error_handlers.py` (extend), `backend/app/main.py` (edit), `backend/tests/conftest.py` (extend)
**Depends on**: T3, T4, T5
**Reuses**: `get_authenticated_user`, `enforce_csrf`/`enforce_origin`, `SourceSummary`/`from_entity` pattern, error-handler registration, `sources_client` fixture pattern (uow/enqueuer overrides mirror `get_db_connection` override)
**Requirement**: ING-01, ING-03, ING-04, ING-05, ING-06, ING-10 (API), ING-11, ING-12

**Tools**: MCP: NONE · Skill: `fastapi`

**Done when**:
- [ ] `POST /api/sources/{id}/ingestion` → `202` + `IngestionSummary`; job `queued` + `source.status="processing"` + enqueuer called; duplicate active → `409`; non-owner/missing → `404`; restart after terminal → `202` new job
- [ ] Enqueuer failure → `502`; job `failed` + `source.status="failed"`; no active job remains (ING-11)
- [ ] Missing/invalid CSRF or bad Origin → `403`; unauth → `401`
- [ ] `GET /api/sources/{id}/ingestion` → `200` latest job (status/attempts/error/ordered events); no job → `404`; non-owner/missing → `404`; summary exposes no `object_key`/`checksum`
- [ ] Full gate passes: `cd backend && uv run pytest`
- [ ] Test count: ≥12 integration tests pass (no silent deletions)

**Tests**: integration — every route: happy + 409 + 404(both) + 502 + 401 + 403 + GET 200/404/404
**Gate**: full

**Commit**: `feat(ingestion): start and read endpoints for source ingestion`

---

### T7 — `startIngestion` browser client [P-frontend]

**What**: `startIngestion(sourceId, csrfToken, fetchImpl)` + `IngestionSummary` type calling same-origin `POST /api/sources/{id}/ingestion` with `X-CSRF-Token`.
**Where**: `frontend/app/lib/sources.ts` (extend)
**Depends on**: T6
**Reuses**: `uploadSource` CSRF-header + `credentials: "same-origin"` + `toSourceError` pattern; existing catch-all proxy (no new proxy code)
**Requirement**: ING-10

**Tools**: MCP: NONE · Skill: `vercel-react-best-practices`

**Done when**:
- [ ] `startIngestion` POSTs same-origin only, sends `X-CSRF-Token`, parses `IngestionSummary`
- [ ] Non-OK surfaces backend `detail` (409 "already in progress", 502) via `toSourceError`
- [ ] Frontend gate passes: `cd frontend && npm test`
- [ ] Test count: ≥3 vitest tests pass

**Tests**: unit (vitest) — same-origin path, CSRF header, summary parse, error on 409/502
**Gate**: frontend

---

### T8 — `SourcesPanel` status badge + "Start ingestion" control

**What**: Render each source's ingestion status and a "Start ingestion" button (only when `status === "uploaded"`) that calls `startIngestion`, optimistically sets the row to `processing`, disables while in flight, and surfaces errors.
**Where**: `frontend/app/components/SourcesPanel.tsx` (edit)
**Depends on**: T7
**Reuses**: existing panel state/`role="alert"` error pattern; CSRF token from `state.user.csrf_token` (already read on mount)
**Requirement**: ING-10

**Tools**: MCP: NONE · Skill: `vercel-composition-patterns`

**Done when**:
- [ ] Each row shows its `status`; "Start ingestion" appears only for `uploaded`
- [ ] Clicking it issues the proxy POST and the row reflects `processing`; button disabled while submitting; no second start offered for an active job
- [ ] A rejected start (409/502) surfaces an error and does not change the row to processing
- [ ] Frontend gate passes: `cd frontend && npm test`
- [ ] Test count: ≥4 vitest tests pass (extends `sources-screen.test.tsx`)

**Tests**: unit (vitest) — badge per row, button-only-for-uploaded, click→POST+processing, error-on-reject, no-double-start
**Gate**: frontend

**Commit**: `feat(ingestion): show ingestion status and start control on sources screen`

---

## Verifier (always-on, after last task)

Fresh Verifier (author ≠ verifier): spec-anchored outcome check across ING-01..ING-12 + discrimination sensor. Inject faults and confirm tests kill them: skip the ownership check → cross-user start/read must fail; drop the partial unique index (or bypass the active guard) → duplicate-start 409 test must fail; make the failing-step path swallow instead of marking `failed` → terminal-failure test must fail; make enqueue-failure skip compensation → 502/no-phantom test must fail; break event ordering → GET ordered-events test must fail. Writes `validation.md` (PASS/FAIL, per-AC evidence, sensor result, diff range). Gaps → bounded fix loop (≤3). Then `learny-finalize` for the PR.

---

## Pre-Approval Validation

### Task Granularity Check

| Task | Scope | Status |
| ---- | ----- | ------ |
| T1: entities + ports | cohesive domain defs, one module area | ✅ Granular |
| T2: tables + migration | 2 related tables + their migration | ✅ Granular |
| T3: repositories | 2 cohesive adapters + 1 method (one file) | ✅ Granular |
| T4: services + errors + fakes | ingestion services for one resource (unit-tested together) | ✅ Granular |
| T5: task + adapters + config | worker wiring (task + its 2 adapters + conf) — cohesive | ✅ Granular |
| T6: router + wiring | 1 router + its composition | ✅ Granular |
| T7: client | 1 client function + type | ✅ Granular |
| T8: panel control | 1 component change | ✅ Granular |

### Diagram-Definition Cross-Check

| Task | Depends On (body) | Diagram Shows | Status |
| ---- | ----------------- | ------------- | ------ |
| T1 | None | (root) | ✅ Match |
| T2 | None | (root, order-free) | ✅ Match |
| T3 | T1, T2 | {T1,T2}→T3 | ✅ Match |
| T4 | T1 | T1→T4 | ✅ Match |
| T5 | T3, T4 | {T3,T4}→T5 | ✅ Match |
| T6 | T3, T4, T5 | {T3,T4,T5}→T6 | ✅ Match |
| T7 | T6 | T6→T7 | ✅ Match |
| T8 | T7 | T7→T8 | ✅ Match |

### Test Co-location Validation

| Task | Code Layer Created/Modified | Matrix Requires | Task Says | Status |
| ---- | --------------------------- | --------------- | --------- | ------ |
| T1 | Domain entities/ports | unit | unit | ✅ OK |
| T2 | Migration/schema | integration | integration | ✅ OK |
| T3 | Repositories | integration | integration | ✅ OK |
| T4 | Application services + errors | unit | unit | ✅ OK |
| T5 | Celery task + adapters | integration | integration | ✅ OK |
| T6 | Web router | integration | integration | ✅ OK |
| T7 | Frontend client | unit (vitest) | unit (vitest) | ✅ OK |
| T8 | Frontend screen | unit (vitest) | unit (vitest) | ✅ OK |

All three checks pass — no ❌.

---

## Requirement → Task Coverage

| Requirement | Task(s) |
| ----------- | ------- |
| ING-01 start create queued + enqueue + processing + 202 | T4, T6 (+T3) |
| ING-02 task drives lifecycle off-request → ready | T4, T5 |
| ING-03 concurrency guard, duplicate → 409 | T2 (index), T3 (repo), T4 (map), T6 (409) |
| ING-04 start/read authz → 404 | T4, T6 |
| ING-05 restart after terminal | T4, T6 |
| ING-06 GET status/attempts/error/events | T4, T6 (+T3) |
| ING-07 bounded retries + backoff + retrying events | T4, T5 |
| ING-08 terminal failure durable + missing-row no-op | T4, T5 |
| ING-09 jobs+events durable, ownership via source, queue ids only | T1, T2, T3, T5 |
| ING-10 frontend status + start + no double-start | T7, T8 (+T6 API) |
| ING-11 enqueue failure → job failed, 502, no phantom | T6 |
| ING-12 GET no job → 404 | T4, T6 |

**Coverage:** 12/12 requirements mapped to tasks.

## Dependency summary

T1, T2 are roots; {T1,T2}→T3; T1→T4 (T4 `[P]` vs T3, unit-tested); {T3,T4}→T5; {T3,T4,T5}→T6; T6→T7→T8. Integration-tested tasks (T2, T3, T5, T6) run tests sequentially (shared DB). Verifier runs after T8.

## Open pre-Execute item (per Tasks step 6)

Tools/skills per task are pre-filled above (default: none; `uv` for migration, `celery-workers`+`context7` for T5, `fastapi` for T6, `ruff` backend, `vercel-*` frontend, `learny-finalize` at publish). Confirm or adjust at the start of Execute.
