# Worker Foundation Validation

**Date**: 2026-07-11
**Spec**: `.specs/features/worker-foundation/spec.md`
**Diff range**: `ebff6f6..9e3060d` (8 commits, `main..HEAD` on `feat/worker-foundation`)
**Verifier**: independent sub-agent (author ≠ verifier), read-only over the real tree; sensor mutations run in scratch and were reverted.

**Verdict: PASS ✅**

---

## Task Completion

| Task | Status | Notes |
| ---- | ------ | ----- |
| T1 Domain entities + ports | ✅ Done | `entities.py`, `ports.py` |
| T2 Tables + migration `0003` | ✅ Done | partial unique index present |
| T3 Repositories + `set_status` | ✅ Done | `repositories.py` |
| T4 Application services + errors + fakes | ✅ Done | `application/ingestion.py`, `errors.py`, `fakes.py` |
| T5 Celery task + step/enqueuer + config | ✅ Done | `worker/tasks.py`, `worker/steps.py`, `worker/enqueuer.py`, `celery_app.py` |
| T6 Router + wiring + error maps | ✅ Done | `web/ingestion.py`, `dependencies.py`, `error_handlers.py`, `main.py`, `conftest.py` |
| T7 `startIngestion` client | ✅ Done | `frontend/app/lib/sources.ts` |
| T8 Panel status + start control | ✅ Done | `frontend/app/components/SourcesPanel.tsx` |

---

## Spec-Anchored Acceptance Criteria

### P1 Start ingestion (ING-01..05)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| ING-01 POST no active job | 202; queued job; 1 enqueue ids-only; source `processing`; `queued` event | `test_web_ingestion.py:112-129` — `status==202`, `body["status"]=="queued"`, `attempts==0`, `error is None`, `events==["queued"]`, `_job_count==1`, `row.status=="queued"`, `_source_status=="processing"`, `enqueuer.calls==[(source,job)]` | ✅ PASS |
| ING-02 task drives lifecycle off-request | queued→running→succeeded; source `ready`; events `[queued,started,succeeded]` | `test_worker_tasks.py:159-167` — `status=="succeeded"`, `attempts==1`, `last_error is None`, source status `"ready"`, event types `[queued,started,succeeded]` | ✅ PASS |
| ING-03 duplicate active start | 409; no 2nd job; no 2nd enqueue; rejected at persistence layer | `test_web_ingestion.py:142-145` (`409`, `_job_count==1`, `len(calls)==1`); `test_repositories.py:...test_ingestion_job_second_active_is_rejected` (`pytest.raises(IntegrityError)`); `test_application_ingestion.py:146-150` (`ActiveIngestionExists`, `add_calls==1`) | ✅ PASS (both app + persistence layers) |
| ING-04 non-owner / missing start | 404, enqueue nothing | `test_web_ingestion.py:158-160,166-167` (`404`, `_job_count==0`, `calls==[]`); `test_application_ingestion.py:165-167,179-181` (`SourceNotFound`, `add_calls==0`) | ✅ PASS |
| ING-05 restart after terminal | new queued job (202) | `test_web_ingestion.py:223-226` (`202`, `id!=first_id`, `status=="queued"`, `_job_count==2`); `test_application_ingestion.py:203-205` | ✅ PASS |

### P1 Observe (ING-06, ING-12, secret-free)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| ING-06 GET job exists | 200; status/attempts/error(null unless failed)/ordered events | `test_web_ingestion.py:321-326` — `status=="succeeded"`, `attempts==1`, `error is None`, `events==[queued,started,succeeded]` | ✅ PASS |
| ING-12 GET no job | 404 | `test_web_ingestion.py:337` — `status_code==404` | ✅ PASS |
| Observe non-owner / missing | 404 (no disclosure) | `test_web_ingestion.py:350,356` — `status_code==404` | ✅ PASS |
| P1-Observe AC4 secret-free | no `object_key`/`checksum` | `test_web_ingestion.py:328` — `"object_key" not in body and "checksum" not in body` | ✅ PASS |

### P1 Retries & terminal failure (ING-07, ING-08)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| ING-07 retryable + backoff | retry up to max w/ backoff; attempts increment; `retrying` event w/ error | `test_worker_tasks.py:204-215` — `len(retry_calls)==1`, `countdown>0`, `status=="running"`, `attempts==1`, `last_error=="provider timeout"`, events `[queued,started,retrying]`; exhaustion branch `test_worker_tasks.py:228-233` | ✅ PASS |
| ING-08 exhausted / non-retryable terminal | `failed` + durable `last_error` + source `failed` + `failed` event | `test_worker_tasks.py:180-187` (plain error → `failed`, `last_error=="corrupt epub"`, source `"failed"`, events `[queued,started,failed]`); `:229-233` (exhausted) | ✅ PASS |
| ING-08 AC3 missing job row | task no-ops, creates no state | `test_worker_tasks.py:242-245` — job `None`, no events, source untouched `"processing"` | ✅ PASS |

### P1 Concurrency guard (ING-03 persistence, ING-09)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| Persistence rejects 2nd active | DB-level (partial unique index) | `test_repositories.py` `test_ingestion_job_second_active_is_rejected` — `pytest.raises(IntegrityError)`; `test_migrations.py:test_migration_0003...` — indexdef `UNIQUE`, `source_id`, `queued`/`running` | ✅ PASS |
| ING-09 queue carries ids only | `apply_async(args=[str(source_id),str(job_id)])` | `test_worker_tasks.py:267` — `apply_async.assert_called_once_with(args=[str(source_id),str(job_id)])` | ✅ PASS |

### Edge / ING-11

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| ING-11 enqueue failure | job `failed`, source `failed`, 502, no phantom active job, `failed` event | `test_web_ingestion.py:185-202` — `status_code==502`, `row.status=="failed"`, `last_error is not None`, source `"failed"`, `get_latest_for_source().status=="failed"`, events `[queued,failed]` | ✅ PASS |
| Unauth / bad CSRF / bad Origin on start | 401 / 403 / 403, no job | `test_web_ingestion.py:239-240,251-252,263-264,278-279` — `401`/`403` + `_job_count==0` | ✅ PASS |

### P1 Frontend (ING-10)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| AC1 status badge per row | badge from `source.status` | `sources-screen.test.tsx:186-189` — testid text `uploaded/processing/ready/failed` | ✅ PASS |
| AC2 Start only for uploaded | control on uploaded rows only | `sources-screen.test.tsx:205-219` — exactly 1 Start button; active/terminal rows have none | ✅ PASS |
| AC3 start → proxy POST + processing | same-origin POST; row `processing` on success | `sources-screen.test.tsx:237-246` — status flips to `processing`, POST to `/api/sources/s-up/ingestion` | ✅ PASS |
| AC4 no double-start / error on reject | 409 surfaced, row stays uploaded | `sources-screen.test.tsx:266-271` — alert text, status stays `uploaded`, button remains | ✅ PASS |
| Client same-origin + CSRF + 409/502 | POST w/ `X-CSRF-Token`; throws `detail` | `ingestion-client.test.ts:51-56,66,76` — url `/api/sources/s1/ingestion`, `X-CSRF-Token`, rejects with backend detail | ✅ PASS |

**Status**: ✅ All 12 ACs covered; asserted values match spec-defined outcomes. No spec-precision gaps.

---

## Discrimination Sensor

Behavior-level faults injected in scratch, relevant tests run, mutation reverted via `git checkout`.

| # | File:line | Mutation | Killed? |
| - | --------- | -------- | ------- |
| 1 | `application/ingestion.py:66-69` | Skip ownership check in `_authorized_source` | ✅ Killed (4 tests: app + web non-owner start/read) |
| 2 | `application/ingestion.py:110` | Bypass `StartIngestion` active pre-check (`if False and ...`) | ✅ Killed (web duplicate 409 via DB index; app-level `test_start_with_active_job...`) |
| 3 | `worker/tasks.py:99-103` | Non-retryable path swallows error instead of `fail()` | ✅ Killed (`test_run_ingestion_plain_error_is_terminal_failure`: running≠failed) |
| 4 | `web/ingestion.py:136-137` | Enqueue-failure path skips compensation (job left `queued`) | ✅ Killed (`test_start_enqueue_failure_returns_502_and_compensates`) |
| 5 | `repositories.py:290` | `list_for_job` orders `created_at.desc()` (reversed) | ✅ Killed (web ordered-events + repo chronological) |
| 6 | `web/ingestion.py:80` | Add `object_key` field to `IngestionSummary` (leak) | ✅ Killed (secret-free assertion) |
| 7 | `worker/tasks.py:44` | `_retry_countdown` returns `0` (no backoff) | ✅ Killed (`countdown>0` assertion, ING-07) |
| 8 | `SourcesPanel.tsx:94-98` | Remove processing-flip on success | ✅ Killed (`reflects processing on success`) |

**Sensor depth**: lightweight+ (8 mutations, exceeds the 1–3 default; covers all high-risk paths — ownership, concurrency, terminal failure, compensation, ordering, secret leak, backoff, UI state).
**Result**: 8/8 killed — PASS ✅

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code / surgical changes | ✅ |
| No scope creep (no EPUB parsing; stub `NoOpIngestionStep` only) | ✅ |
| Matches existing patterns (port/adapter/fake, composition root, error-map) | ✅ |
| Spec-anchored outcome check (asserted values match spec) | ✅ |
| Per-layer coverage (domain 1:1 ACs; routes happy+edge+error) | ✅ |
| Every test maps to a spec AC / edge / Done-when — no unclaimed tests | ✅ |
| Documented guidelines: `CLAUDE.md`, `.specs/codebase/CONVENTIONS.md`, `celery-workers` skill; ruff clean on new files | ✅ |

---

## Known deviations evaluated

- **ING-03 defense-in-depth** (app pre-check + DB partial-unique index + web `IntegrityError`→409): confirmed satisfied at BOTH the application layer (`test_start_with_active_job...`) and the persistence layer (`test_ingestion_job_second_active_is_rejected`, migration indexdef test). Not a gap.
- **Frontend `SPEC_DEVIATION`** (SourcesPanel keeps the row `uploaded`/button-disabled during the request, flips to `processing` only on success instead of an optimistic pre-await flip): end states match spec AC3 exactly — `processing` on success (`sources-screen.test.tsx:237`), error surfaced + row unchanged on 409 (`:266-271`). Rationale (button unmount) is sound. Acceptable deviation.

---

## Edge Cases

- [x] Start on active source → 409, no enqueue (ING-03)
- [x] Start on failed/terminal source → restart 202 (ING-05)
- [x] Broker unreachable at enqueue → job failed, 502, no active job (ING-11)
- [x] Task fires for missing job row → no-op (ING-08 AC3); terminal-job redelivery → no-op
- [x] GET before any start → 404 (ING-12)
- [x] Non-owner start/read → 404, no disclosure (ING-04)

---

## Gate Check

- **Backend**: `cd backend && LEARNY_TEST_DATABASE_URL=... uv run pytest` → **183 passed**, 0 failed, 1 warning
- **Frontend**: `cd frontend && npm test` → **39 passed** (8 files), 0 failed
- **Ruff**: `ruff check` on new files → All checks passed
- **New feature tests** (approx from diff): backend +~48 (domain 19, application 19, worker 7, web 15, repos 6, migration 1 net across files), frontend +7 (ingestion-client 3, sources-screen +4)
- **Skipped tests**: only the DB-gated migration test when `LEARNY_TEST_DATABASE_URL` is unset (guarded, expected); DB present here so it ran.
- **Post-sensor integrity**: tree pristine — 8 commits, only `.specs/` planning files unstaged, both suites green.

---

## Requirement Traceability Update

| Requirement | Previous | New |
| ----------- | -------- | --- |
| ING-01..ING-12 | Implementing | ✅ Verified |

---

## Summary

**Overall**: ✅ Ready

**Spec-anchored check**: 12/12 ACs matched spec outcome; 0 spec-precision gaps.
**Sensor**: 8/8 mutations killed.
**Gate**: backend 183 passed, frontend 39 passed.

**What works**: durable `queued→running→succeeded/failed` lifecycle driven entirely by the Celery task; bounded retries with backoff + terminal `failed` with durable redacted `last_error`; DB-enforced at-most-one-active-job guard; secret-free read API with ordered events; enqueue-after-commit with compensation on broker failure (502, no phantom job); sources screen status badge + same-origin start control. No EPUB parsing in handler or task — Phase-5 boundary intact.

**Issues found**: none.

**Next steps**: proceed to `learny-finalize` for the PR.
