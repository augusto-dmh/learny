# Production-Like Readiness Tasks

**Spec:** spec.md · **Design:** design.md · **Decisions:** AD-040..AD-044

Execution: **3 phases → inline** (sub-agent offer triggers only at >3 phases). One atomic commit per task.
Gate per task; a fresh independent Verifier runs after the final commit.

Gate commands (from repo root):
- Backend: `LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test /home/augusto/myenv/bin/uv run --project backend pytest` + `... ruff check .` (+ `ruff format --check` scoped to touched files; repo has a known pre-existing format drift on 10 Cycle-1 files — do not touch those).
- Frontend (Phase B2 only): `cd frontend && npm run build` + `npx tsc --noEmit` + `npm run test`.

---

## Phase A — Observability hooks

### A1 — Trace context module + log-format setting
- **Files:** `backend/app/core/tracing.py` (new), `backend/app/core/config.py` (+`log_format`), `backend/tests/test_tracing.py` (new).
- **Do:** `ContextVar` trace store; `bind_trace`, `current_trace`, `new_trace_scope`/`reset_trace`, `new_request_id`, `sanitize_request_id`, `TraceContextFilter` (design §2.1). `Settings.log_format: str = "human"`.
- **Tests (PROD-18/20):** sanitize truncates to 128 + strips unsafe chars + `None`/empty→`None`; filter injects current trace fields onto a record; filter is a no-op outside a scope; two sequential `new_trace_scope`s do not bleed; `bind_trace` after scope start is visible via `current_trace`.
- **Gate:** backend pytest (new file) + ruff. **Commit:** `feat(observability): add request trace context and log-format setting`.

### A2 — JSON formatter + configure_logging rework
- **Files:** `backend/app/core/logging.py`, `backend/tests/test_logging_redaction.py` (extend) or `backend/tests/test_logging_format.py` (new).
- **Do:** `JsonFormatter` (design §2.2); rework `configure_logging(level, log_format=None)` to build one root handler, choose formatter by format, attach BOTH `SensitiveDataFilter` + `TraceContextFilter` to handler and root, stay idempotent (no dup handlers/filters).
- **Tests (PROD-12/13 + idempotent edge):** JSON output is one line of valid JSON carrying message + a bound trace field; a sensitive `extra` (`password`/`session_token`) is `REDACTED` in JSON output; existing human redaction test still passes; calling `configure_logging()` twice yields one handler and both filters present.
- **Gate:** backend pytest + ruff. **Commit:** `feat(observability): structured JSON logging with preserved secret redaction`.

### A3 — Request-context middleware + wiring + user_id bind
- **Files:** `backend/app/infrastructure/web/middleware.py` (new), `backend/app/main.py`, `backend/app/infrastructure/web/dependencies.py` (`resolve_current`), `backend/tests/test_web_request_context.py` (new).
- **Do:** pure-ASGI `RequestContextMiddleware` (design §2.3): sanitize/generate request id, fresh trace scope, bind `request_id`/`method`/`path`, send-wrapper echoes `X-Request-ID` + captures status, one `app.request` `http.request` access log with `status_code`+`duration_ms` in `finally`, reset scope. `add_middleware` in `create_app`. `resolve_current` binds `user_id` on success. Document the unhandled-500 header gap in the module.
- **Tests (PROD-07..11, 19):** missing header → generated hex id echoed; inbound id echoed; oversized/unsafe inbound id sanitized in the echoed header; a record logged from a route carries `request_id`; authenticated route record carries `user_id`; exactly one `http.request` access record with method/path/status/`duration_ms`; a handled-error route (e.g. 404/422) still logs access + carries the header; an unhandled-exception route (`TestClient(raise_server_exceptions=False)`) still logs one access record with status 500.
- **Gate:** backend pytest (new + existing web/auth unaffected) + ruff. **Commit:** `feat(observability): correlate requests with an ID, trace fields, and access logging`.

### A4 — Worker trace binding + duration + worker logging config
- **Files:** `backend/app/worker/tasks.py`, `backend/app/worker/celery_app.py` (disable root-logger hijack + configure logging), `backend/tests/test_worker_tasks.py` (extend, `requires_db`).
- **Do:** at `run_ingestion` entry `new_trace_scope()` + `bind_trace(job_id, source_id)`, `try/finally reset`; `perf_counter` duration added to terminal (succeeded/failed/exhausted) log `extra`. In `celery_app`: `worker_hijack_root_logger=False` + call `configure_logging()` so worker logs pass our filters.
- **Tests (PROD-14):** succeeded path emits a record carrying `job_id`+`source_id`+`duration_ms`; a terminal failed path likewise. (Guarded by `requires_db`; run with the test DB.)
- **Gate:** backend pytest (with `LEARNY_TEST_DATABASE_URL`) + ruff. **Commit:** `feat(observability): bind worker task trace fields and log durations`.

---

## Phase B — Production deployment shape

### B1 — Compose prod overlay + dev-port split + env examples
- **Files:** `docker-compose.override.yml` (new — db/redis/minio host ports for local), `docker-compose.yml` (remove those three `ports:` blocks; api/web ports stay), `docker-compose.prod.yml` (new overlay), `backend/.env.production.example` (new), `frontend/.env.production.example` (new), `backend/tests/test_compose_prod.py` (new).
- **Do:** design §3.1/§3.3. Overlay: restart policies, pinned images (no `:latest`), env_file secrets, `api` prod env (`LEARNY_ENVIRONMENT=production`, `LEARNY_SESSION_COOKIE_SECURE=true`, `LEARNY_LOG_FORMAT=json`), multi-worker uvicorn, `web` `build.target: prod`. Keep local aligned (base + auto override reproduces today's local ports).
- **Tests (PROD-01..05):** with `yaml.safe_load` on base + overlay (merged the way `-f base -f prod` merges): db/redis/minio publish no host ports; every service has `restart` ∈ {unless-stopped, always}; no image ends with `:latest`; api env has the three prod values; secrets come via `env_file` not inline literals. Assert `docker-compose.override.yml` restores db/redis/minio ports for local.
- **Verify:** `docker.exe compose -f docker-compose.yml -f docker-compose.prod.yml config -q` parses (manual/CI check, noted in commit if run).
- **Gate:** backend pytest (new file) + ruff. **Commit:** `feat(deploy): add a hardened production compose overlay`.

### B2 — Frontend production image target
- **Files:** `frontend/next.config.ts` (+`output: "standalone"`), `frontend/Dockerfile` (multi-stage build+prod), `backend/tests/test_compose_prod.py` or `frontend` static assertion (Dockerfile has a build stage + non-`dev` start).
- **Do:** design §3.2. Multi-stage: deps → build (`npm run build`) → `prod` runtime running the standalone server (non-root), no `next dev`.
- **Tests (PROD-06):** static assertion that `frontend/Dockerfile` contains a build stage and a start command that is not `next dev`; `next.config` sets `output: "standalone"`.
- **Gate:** `cd frontend && npm run build` succeeds + `npx tsc --noEmit` + `npm run test`; backend static test + ruff. **Commit:** `feat(deploy): build the frontend as a production image`.

---

## Phase C — Operator runbooks

### C1 — Backup/restore + rollback runbooks
- **Files:** `docs/ops/backups.md` (new), `docs/ops/rollback.md` (new), `backend/tests/test_ops_docs.py` (new).
- **Do:** design §4. Provider-neutral commands; TDD triggers table reproduced; corpus atomic-replace/no-versioning implication (AD-018); two-`-f` prod invocation reminder; retention/offsite + OQ #10 as operator TODO.
- **Tests (PROD-15/16/17):** both files exist; `backups.md` contains PostgreSQL dump+restore and object-storage backup+restore commands and a restore-drill section; `rollback.md` contains an independent-image-revert section, a migration downgrade reference, and the rollback-triggers table rows.
- **Gate:** backend pytest (new file) + ruff. **Commit:** `docs(ops): add backup/restore and rollback runbooks`.

---

## Coverage map

| AC | Task |
|---|---|
| PROD-01..05 | B1 |
| PROD-06 | B2 |
| PROD-07..11, 19 | A3 |
| PROD-12, 13 | A2 |
| PROD-14 | A4 |
| PROD-18, 20 | A1 |
| PROD-15, 16, 17 | C1 |

8 tasks. Every PROD-ID maps to exactly one owning task.
