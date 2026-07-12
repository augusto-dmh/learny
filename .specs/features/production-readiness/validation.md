# Production-Like Readiness Validation

**Date**: 2026-07-12
**Spec**: `.specs/features/production-readiness/spec.md`
**Diff range**: `main..HEAD` (branch `feat/production-readiness`, HEAD=3ea25fb, 7 commits)
**Verifier**: independent sub-agent (author ≠ verifier, evidence-or-zero, read-only over the real tree; mutations run only in scratch and were restored)

---

## Verdict: ✅ PASS (with 1 flagged discrimination gap — Minor)

- **Spec-anchored check**: 20/20 ACs traced to a `file:line` + assertion; asserted values match spec-defined outcomes. 1 spec-precision / discrimination note on PROD-14 (below).
- **Gate**: backend 493 passed / 0 failed (ruff clean); frontend build ok, `tsc --noEmit` clean, 92 tests passed. Full backend suite green + stable across two runs.
- **Sensor**: 7 behavior-level mutations, 6 killed, 1 survived (worker `bind_trace` correlation seam — PROD-14).

---

## Task Completion

| Task | Status | Notes |
| ---- | ------ | ----- |
| A1 — trace context module + `log_format` setting | ✅ Done | `tracing.py`, `config.py` |
| A2 — JSON formatter + `configure_logging` rework | ✅ Done | `logging.py` |
| A3 — request-context middleware + wiring + `user_id` bind | ✅ Done | `middleware.py`, `main.py`, `dependencies.py` |
| A4 — worker trace binding + duration + worker logging | ✅ Done | `tasks.py`, `celery_app.py` |
| B1 — compose prod overlay + dev-port split + env examples | ✅ Done | overlay/base/override + `.env.production.example` |
| B2 — frontend production image target | ✅ Done | `Dockerfile`, `next.config.ts` |
| C1 — backup/restore + rollback runbooks | ✅ Done | `docs/ops/backups.md`, `docs/ops/rollback.md` |

---

## Spec-Anchored Acceptance Criteria

### P1 — Production-like deployment shape (config/docs ACs verified by YAML/content assertions)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| PROD-01 db/redis/minio publish no host ports | infra internal-only in prod merge | `backend/tests/test_compose_prod.py:53` — `assert not prod[svc].get("ports")` over `("db","redis","minio")` (base carries no infra `ports`; overlay adds none) | ✅ PASS (meaningful) |
| PROD-02 every long-running service has restart unless-stopped/always | all 6 services | `test_compose_prod.py:58` — `assert prod[svc].get("restart") in {"unless-stopped","always"}` over all 6 | ✅ PASS |
| PROD-03 no `:latest`; each pinned | no floating tags | `test_compose_prod.py:63` — `not image.endswith(":latest")` + `":" in image`; infra must declare `image` (overlay pins base `minio:latest`→`RELEASE.*`, redis→`7.4-alpine`) | ✅ PASS (sensor-killed) |
| PROD-04 api env production/secure/json | 3 exact values | `test_compose_prod.py:74` — `LEARNY_ENVIRONMENT=="production"`, `LEARNY_SESSION_COOKIE_SECURE=="true"`, `LEARNY_LOG_FORMAT=="json"` | ✅ PASS |
| PROD-05 secrets via env_file, not inline | env_file injection | `test_compose_prod.py:81` — `env_file` present for api/worker/db/minio; DB URL + storage keys + POSTGRES/MINIO passwords absent from inline `environment` | ✅ PASS (sensor-killed M7) |
| PROD-06 frontend prod image runs built app, not `next dev` | build+start (standalone) | `frontend/tests/prod-image.test.ts:14-34` — standalone output; `AS build`+`npm run build`; `AS prod`+`CMD ["node","server.js"]`; prod stage not `next dev`; non-root. Plus `test_compose_prod.py:95` — web command `["node","server.js"]`, build target `prod` | ✅ PASS |

### P1 — Request-correlated observability hooks

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| PROD-07 no inbound header → generate + bind + echo | generated id echoed in `X-Request-ID`; bound | `test_web_request_context.py:88` — `resp.headers["X-Request-ID"]` non-empty; `handler_rec.request_id == rid` | ✅ PASS (sensor-killed M2) |
| PROD-08 inbound header adopted (sanitized) + echoed | echo the sanitized value | `:99` — echoes `"abc-123"`; `:105` — unsafe `"bad\nid "+"x"*300` echoed as `("badid"+"x"*300)[:128]` | ✅ PASS |
| PROD-09 any record in a request carries `request_id` automatically | no call-site `extra=` needed | `:95` — `handler_rec.request_id == rid` (route logs a plain record via `TraceContextFilter`) | ✅ PASS (sensor-killed M4) |
| PROD-10 authenticated request carries `user_id` | `user_id` bound on auth | `:145` — `resolve_current` → `current_trace()["user_id"] == str(uid)` (verified at the seam) | ✅ PASS (sensor-killed M4) |
| PROD-11 exactly one access record: method/path/status/duration_ms | single `http.request` with 4 fields | `:115` — `_access_record` asserts exactly one; `rec.method=="GET"`, `rec.path=="/ping"`, `rec.status_code==200`, `isinstance(rec.duration_ms,float)` | ✅ PASS (sensor-killed M6) |
| PROD-12 JSON single-line with standard + trace fields | one-line JSON object | `test_logging_format.py:52` — `"\n" not in out`, message/level/logger/timestamp + extra; `:63` — bound `request_id`/`user_id` present | ✅ PASS |
| PROD-13 sensitive field redacted under JSON | redaction preserved | `test_logging_format.py:76` — `session_token`/`password == REDACTED`, raw secret + `hunter2` absent from output | ✅ PASS (sensor-killed M3) |
| PROD-14 worker records carry job_id/source_id; terminal carries duration_ms | fields on records + terminal duration | `test_worker_tasks.py:650,665` — `rec.job_id/source_id == …`, `isinstance(rec.duration_ms,float)` on succeeded + failed terminal records | ⚠️ PASS (literal AC met) but **discrimination gap** — see sensor M4 |

### P2 — Operator runbooks (content assertions)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| PROD-15 backups.md: PG dump+restore, object-storage backup+restore, restore drill | provider-neutral commands present | `test_ops_docs.py:34` — `pg_dump`,`pg_restore`; `:39` — `mc mirror`,`learny-sources`; `:45` — `"Restore drill"`. Doc contains real both-direction commands + a 6-step drill (meaningful) | ✅ PASS |
| PROD-16 rollback.md: independent image revert, migration reversibility + forward-only, triggers table | sections + triggers present | `test_ops_docs.py:49` — `up -d api/worker/web`; `:56` — `alembic downgrade`+`forward-only`; `:61` — 3 trigger rows reproduced from TDD | ✅ PASS |
| PROD-17 runbook states atomic-replace/no-versioning + rollback implication | AD-018 semantics stated | `test_ops_docs.py:70` — `"no versioning"`/`"no prior corpus version"` + `"re-ingest"` | ✅ PASS |

### Edge cases

| Criterion | `file:line` + assertion | Result |
| --------- | ----------------------- | ------ |
| PROD-18 sanitize/truncate absurd/control-char inbound id | `test_tracing.py:40` truncate→128; `:45` strip `\n \t " /`; `:50` empty/None→None; `test_web_request_context.py:105` end-to-end | ✅ PASS (sensor-killed M1) |
| PROD-19 handled-error keeps header+access log; unhandled 500 still access-logs | `test_web_request_context.py:126` — 404 keeps header + access status 404; `:136` — unhandled `boom` → one access record status 500 | ✅ PASS (sensor-killed M6) |
| PROD-20 trace no-op outside scope; scopes do not bleed; retry field stability | `test_tracing.py:87` — filter no-op outside scope, `current_trace()=={}`; `:94` — scopes don't bleed. Retry-field-stability arm: worker re-binds at each `_run` entry; retry logs carry job_id via `extra=log` (not separately asserted as a trace field) | ✅ PASS (no-op arm sensor-killed M4; retry-stability arm structurally sound, minor) |

**Status**: ✅ All 20 ACs covered with located evidence; 1 discrimination gap flagged (PROD-14).

---

## Discrimination Sensor

Depth: lightweight fault-injection (7 mutations, higher-risk new code). All mutations applied in scratch via Edit and restored with `git checkout --`; final `git diff HEAD` over source is empty.

| # | File:line | Mutation | Killed? |
| - | --------- | -------- | ------- |
| 1 | `app/core/tracing.py:48` | `sanitize_request_id` drop `[:_MAX_REQUEST_ID_LEN]` (no truncation) | ✅ Killed (2 tests: truncate + web sanitize) |
| 2 | `app/infrastructure/web/middleware.py:90` | send-wrapper skips setting `X-Request-ID` header | ✅ Killed (4 web tests) |
| 3 | `app/core/logging.py:53` | `_is_sensitive_key` always returns False (redaction disabled) | ✅ Killed (5 tests: JSON redaction + human redaction) |
| 4 | `app/core/tracing.py:79` | `bind_trace` no-op (fields never stored) | ⚠️ **Partial** — Killed the HTTP/unit trace arm (8 tests: tracing + web + user_id) but **SURVIVED** the worker arm: `test_worker_tasks.py` PROD-14 trace tests still pass |
| 5 | `docker-compose.prod.yml:26` | redis image → `redis:latest` | ✅ Killed (compose latest test) |
| 6 | `app/infrastructure/web/middleware.py:76` | skip emitting the `http.request` access log | ✅ Killed (3 web tests) |
| 7 | `docker-compose.prod.yml` api env | inline `LEARNY_DATABASE_URL` secret added | ✅ Killed (compose secrets test) |

**Result**: 6/7 killed, 1 survived.

**Surviving mutant (M4, worker arm) — root cause**: every `logger` call in `app/worker/tasks.py` passes `job_id`/`source_id`/`duration_ms` explicitly via `extra=log` / `extra={**log, "duration_ms": …}`. The PROD-14 tests assert those fields on the terminal record, which are present via the explicit `extra=` regardless of the trace-context mechanism. Therefore `new_trace_scope()`+`bind_trace(job_id, source_id)` at task entry — whose real purpose is to correlate *downstream* service logs that do NOT pass `extra=` — is not exercised by any assertion. The literal AC PROD-14 ("terminal record carries job_id/source_id + duration") is genuinely satisfied and discriminating for the terminal record; the untested behavior is worker-side trace correlation of records emitted without `extra=`.

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code / no scope creep | ✅ — provider-neutral, no metrics/TLS/proxy dependency added (matches Out-of-Scope + Success Criteria) |
| Surgical changes / only required files | ✅ |
| Matches existing patterns | ✅ — reuses `SensitiveDataFilter`/idempotent `configure_logging`, `LEARNY_`-prefixed settings, ports/adapters |
| Spec-anchored outcome check | ✅ (1 discrimination note, PROD-14) |
| Per-layer coverage (routes happy+edge+error) | ✅ — generated/adopted/sanitized id, handled 4xx, unhandled 500 all covered |
| Every test maps to a spec AC / edge / Done-when | ✅ — no unclaimed tests |
| Documented guidelines followed | ✅ — celery-workers skill (`worker_hijack_root_logger=False`), ADR-0008 §3/§5 alignment |

---

## Known-Risky Areas (explicitly checked)

- **(a) settings-cache / env.py interaction** — ✅ `configure_logging` reads `os.environ.get("LEARNY_LOG_FORMAT", "human")` directly (`logging.py:163`), never calls `get_settings`, so it cannot prime the `lru_cache` and pin a stale DB URL for Alembic. Full backend suite green and stable across two independent runs (493 passed each). No order-fragility observed after truncating the shared test DB.
- **(b) secret redaction under JSON** — ✅ Redaction runs as a filter before the formatter; `test_json_output_redacts_sensitive_fields` proves masking in JSON output; sensor M3 confirms the assertion is discriminating.
- **(c) compose test reflects `-f base -f prod` hardening** — ✅ `test_compose_prod.py` deep-merges base+overlay the way an added `-f` file overrides keys; asserts no infra host ports, no `:latest`, secrets via `env_file`. Base carries no infra `ports`/secrets (moved to `docker-compose.override.yml`, auto-loaded for local); overlay adds restart/pinned images/prod env/env_file. Sensors M5 (`:latest`) and M7 (inline secret) confirm discrimination. `docker.exe compose config` not executed (Docker unavailable), but the YAML-merge test is faithful.

---

## Gate Check

- **Backend**: `LEARNY_TEST_DATABASE_URL=… uv run --directory backend pytest -q` → **493 passed, 0 failed, 0 skipped** (1 pre-existing StarletteDeprecationWarning). `ruff check .` → All checks passed.
- **Frontend**: `npm run build` → success (9 routes built); `npx tsc --noEmit` → clean; `npm run test` (vitest) → **92 passed** across 13 files (incl. `prod-image.test.ts` 4/4).
- **Test count delta**: +6 new backend test files/blocks (test_tracing, test_logging_format, test_web_request_context, test_worker_tasks PROD-14 block, test_compose_prod, test_ops_docs) + frontend prod-image.test.ts. No test deleted; no assertion weakened.

---

## Requirement Traceability Update

PROD-01..13, PROD-15..20 → ✅ Verified. PROD-14 → ✅ Verified (literal AC) with a flagged test-strength gap (fix task below).

---

## Fix Plans

### Fix 1: Strengthen PROD-14 to exercise worker trace correlation (Minor)

- **Root cause**: PROD-14 assertions read fields that `tasks.py` supplies via explicit `extra=log`, so the `bind_trace()` correlation seam is untested (sensor M4 worker arm survived).
- **Fix task**: In `backend/tests/test_worker_tasks.py`, within `_capture_worker_logs`, emit (or capture) a log record produced *without* `extra=log` during the task run — e.g. assert a record from a downstream/plain logger emitted inside the task scope carries `job_id`/`source_id` via `TraceContextFilter`, OR assert `current_trace()` holds them mid-task. This makes a `bind_trace` no-op fail.
- **Verify**: re-apply the M4 mutation (`bind_trace` no-op) and confirm the worker PROD-14 test now FAILS.
- **Priority**: Minor — feature behavior is correct; this hardens the regression sensor for a currently-redundant seam.

---

## Summary

**Overall**: ✅ Ready (Minor test-strength gap on PROD-14).

**What works**: Provider-neutral prod compose overlay (no infra host ports, pinned images, env_file secrets, hardened api env), request-correlated structured logging with request-id echo/sanitization + single access log + preserved redaction, worker trace/duration logging, and complete backup/restore + rollback runbooks. No monitoring/metrics/TLS/proxy dependency introduced — OQ #10 remains the single flagged follow-up.

**Issues found**: PROD-14 worker trace tests do not discriminate a broken `bind_trace` (fields arrive via explicit `extra=`). Fix task above.

**Next steps**: Optionally apply Fix 1 before merge; the merge gate should carry the flagged OQ #10 (metrics/monitoring/TLS/reverse-proxy/VPS) as the blocking project-wide follow-up.

---

## Post-verification fix (orchestrator, commit 28668e4)

The one surviving mutant (M4) is resolved. Added
`test_run_ingestion_populates_trace_context_during_the_task`
(`backend/tests/test_worker_tasks.py`), which snapshots `current_trace()` while
the task body runs and asserts `{job_id, source_id}` — the correlation seam the
`TraceContextFilter` stamps onto downstream records. Scratch re-mutation confirmed:
with `bind_trace` a no-op the new test **fails** (mutant now killed); it passes on
the real tree. Full backend suite: **494 passed**, ruff clean. Verdict remains
**PASS**, now with the sensor gap closed (7/7 discriminated).
