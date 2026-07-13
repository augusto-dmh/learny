# v2-foundation Validation

**Date**: 2026-07-13
**Spec**: `.specs/features/v2-foundation/spec.md`
**Diff range**: `main..HEAD` = `b3bbe99..d1f5923` (12 commits on `feat/v2-foundation`; `d1f5923` is the FND-08 fix landed after round 1)
**Re-verification**: round 2 (2026-07-13) re-checked only the FND-08 gap after fix commit `d1f5923`
**Verifier**: independent sub-agent (author ≠ verifier), evidence re-derived from the tree and test runs

---

## Task Completion

| Task | Status | Notes |
| ---- | ------ | ----- |
| A1 README | ✅ Done | `README.md` at HEAD (commit `b3bbe99`) |
| A2 QA runbook + report | ✅ Done | `docs/ops/e2e-qa.md`, `docs/ops/e2e-qa-report-2026-07-12.md` (commit `1cc18d0`) |
| A3 Research + RFC-002 | ✅ Done | 13 files in `docs/research/2026-07-12/`, RFC status `Accepted (2026-07-13)` (commit `b1fe397`) |
| A4 Compose F1 fix + test | ✅ Done | commit `56dee08`; regression test kills the mutant (sensor M5) |
| B1 F2 storage classification | ✅ Done | commit `091692f`; sensor M3 killed |
| B2 F3 proxy headers | ✅ Done | commit `11c6315`; round-1 test gap (transfer-encoding assertion) fixed in `d1f5923`; sensor M2 now killed |
| B3 F4 first-run determinism | ✅ Done | commit `c15fe2f`; sensor M4 killed; fresh-DB re-run env-restricted for Verifier (see FND-12) |
| C1 CI workflow | ✅ Done | commit `7ccf4ef`; YAML valid, jobs match spec |
| C2 License | ✅ Done | commit `64fef46` |
| C3 SECURITY/CONTRIBUTING/dependabot | ✅ Done | commit `3a40a9c` |
| C4 CLAUDE.md/ROADMAP/STATE refresh | ✅ Done | commit `08cd719` |

---

## Spec-Anchored Acceptance Criteria

| Criterion | Spec-defined outcome | Evidence (`file:line` + assertion) | Result |
| --------- | -------------------- | ---------------------------------- | ------ |
| FND-01 artifacts committed | README, 2 ops docs, 13 research files, RFC-002 `Accepted` at HEAD | `git ls-tree HEAD` lists all; `docs/research/2026-07-12/` = 13 files; `docs/rfc/0002-learny-v2-roadmap.md:3` — `Status: Accepted (2026-07-13)` | ✅ PASS |
| FND-02 worker storage env + test | worker defines `LEARNY_STORAGE_ENDPOINT/BUCKET/REGION`; a test asserts it | `docker-compose.yml:87-89`; `backend/tests/test_compose_prod.py:113-120` — `assert env["LEARNY_STORAGE_ENDPOINT"] == "http://minio:9000"` (+ BUCKET, REGION) | ✅ PASS |
| FND-03 get + unreachable → `StorageUnavailable` | `BotoCoreError` from bucket-ensure or get raises `StorageUnavailable` | `backend/tests/test_storage_s3.py:157-162` — `pytest.raises(StorageUnavailable)` with `head_bucket=EndpointConnectionError`; `:145-147` — get itself raising `BotoCoreError`; impl `backend/app/infrastructure/storage/s3.py:70-71,95-96` | ✅ PASS |
| FND-04 put + `BotoCoreError`/non-not-found `ClientError` → `StorageUnavailable` | same, for put + bucket-ensure + create-bucket | `test_storage_s3.py:165-170` (ensure fault), `:173-177` (put `BotoCoreError`), `:180-185` (put `ClientError` SlowDown), `:189-196` (create_bucket fault); impl `s3.py:68-69,83-84` | ✅ PASS |
| FND-05 get missing key → `ObjectNotFound` | not-found `ClientError` still raises `ObjectNotFound` | `test_storage_s3.py:150-154` — `pytest.raises(ObjectNotFound)` with `Code: NoSuchKey`; integration `:74-76` | ✅ PASS |
| FND-06 ingestion retries `StorageUnavailable` | existing retry-with-backoff behavior stays green | `backend/tests/test_ingestion_step.py:92-95` — `pytest.raises(RetryableIngestionError)` on `StorageUnavailable`; `backend/tests/test_worker_tasks.py:295-300` (backoff retry path); all green in gate run | ✅ PASS |
| FND-07 `Expect` not forwarded | upstream request has no `Expect` header (any casing) | `frontend/tests/proxy.test.ts:48-62` — `expect(out.headers.get("expect")).toBeNull()`; casing handled by `Headers` normalization + `key.toLowerCase()` (`proxy.ts:84`) | ✅ PASS |
| FND-08 hop-by-hop headers not forwarded | none of 8 named headers forwarded | `frontend/tests/proxy.test.ts:64-92` asserts all 8 null — `"transfer-encoding": "chunked"` in incoming headers (`:71`) and `"transfer-encoding"` in the asserted-null loop (`:84`, `expect(out.headers.get(name)).toBeNull()`), added in `d1f5923`; impl `proxy.ts:42-57`. Round-1 gap closed; mutant M2 re-run and killed | ✅ PASS |
| FND-09 response `content-encoding`/`content-length` stripped | relayed response lacks both | `frontend/tests/proxy-forwarding.test.ts:105-123` — `expect(relayed.headers.get("content-encoding")).toBeNull()` + content-length | ✅ PASS |
| FND-10 cookie/csrf/content-type forwarded; set-cookie relayed | preserved verbatim | `proxy.test.ts:23-37` (cookie, x-csrf-token, content-type); `proxy-forwarding.test.ts:52-69,94-103` (set-cookie verbatim, multiple cookies distinct) | ✅ PASS |
| FND-11 F4 root cause recorded | mechanism named in context.md + AD-049 | `.specs/features/v2-foundation/context.md:25-30` (D-5: env.py clobbered caller URL → dev DB migrated, test DB schemaless); `.specs/project/STATE.md:60` (AD-049) | ✅ PASS |
| FND-12 fresh-DB first run passes | full suite green on first run vs freshly created DB | Mechanism fix `backend/migrations/env.py:33-34` (`if not config.get_main_option(...)`); discriminating regression test `backend/tests/test_migrations.py:107-126` (settings pointed at dead endpoint — killed sensor M4). Full suite green in this session: 504 passed. Direct DROP/CREATE re-run **blocked by environment policy** for the Verifier; implementer gate recorded twice-green fresh-DB runs (STATE.md Handoff:79); CI backend-test re-verifies on a fresh service-container DB every PR run | ✅ PASS (with caveat) |
| FND-13 ci.yml defines 4 jobs per spec | backend-test (pgvector/pgvector:pg16 + pg_isready, redis:7-alpine + ping, setup-uv cache, `uv sync --locked`, pytest w/ `LEARNY_TEST_DATABASE_URL`), lint (ruff check only), frontend (npm ci cache, vitest, tsc, build), compose-smoke (bake + GHA cache, up, `/healthz` poll, teardown), concurrency cancel-in-progress | `.github/workflows/ci.yml:22-61` (backend-test incl. `:29` image, `:37` pg_isready, `:46` redis ping, `:52-57` uv, `:60` env), `:63-69` (lint, ruff-action check), `:71-86` (frontend), `:88-109` (compose-smoke incl. `:104` healthz poll), `:17-19` (concurrency) | ✅ PASS |
| FND-14 valid YAML, real `LEARNY_*` env names | parses; only env vars the codebase reads | `yaml.safe_load` OK (this session); `LEARNY_TEST_DATABASE_URL` read at `backend/tests/conftest.py:21`; `LEARNY_REDIS_URL` via `env_prefix="LEARNY_"` (`backend/app/core/config.py:22`) | ✅ PASS |
| FND-15 each job's commands pass locally | pytest, ruff, vitest+tsc+build, compose+healthz | Verifier re-ran: pytest **504 passed** (44s); `ruff check .` — "All checks passed!"; vitest **95 passed (13 files)**; `tsc --noEmit` OK; `npm run build` OK. Compose: not rebuilt by Verifier (docker write access out of bounds); live stack observed healthy read-only — `curl /healthz` → `{"status":"ok"}`, all 6 services `(healthy)` | ✅ PASS (compose leg observed, not rebuilt) |
| FND-16 Apache-2.0 everywhere | full text + both manifests declare it | `LICENSE` (202 lines, full Apache-2.0 text); `backend/pyproject.toml:6` — `license = "Apache-2.0"`; `frontend/package.json:4` — `"license": "Apache-2.0"` | ✅ PASS |
| FND-17 SECURITY/CONTRIBUTING/dependabot | private reporting; setup+tests+conventional commits ≤1 page; pip+npm+github-actions security-only | `SECURITY.md:3` (GitHub private vulnerability reporting link); `CONTRIBUTING.md` (27 lines: setup, tests, Conventional Commits at `:25`); `.github/dependabot.yml:6-20` (3 ecosystems, `open-pull-requests-limit: 0` = security-only) | ✅ PASS |
| FND-18 CLAUDE.md truthful | MVP-shipped status, RFC-002-driven v2, no stale claims | `CLAUDE.md` Current Status rewritten (diff `08cd719`); grep for "no runtime scaffold"/"research, decision, and design artifacts only" → no matches | ✅ PASS |
| FND-19 ROADMAP v2 section | cycles A–G mapped, `v2-foundation` in progress | `.specs/project/ROADMAP.md:20-35` — v2 table, row `v2-foundation | A | ... | In progress`, B–G "Not started" | ✅ PASS |

**Status**: ✅ All 19 ACs covered (FND-08 gap from round 1 closed by `d1f5923`).

---

## Discrimination Sensor

All mutations applied in scratch state only (edit → run → `git checkout --`); tree verified clean afterwards.

| # | Mutation | File | Test command | Killed? |
| - | -------- | ---- | ------------ | ------- |
| M1 | Removed `"expect"` from `STRIPPED_HEADERS` | `frontend/app/lib/proxy.ts:56` | `npx vitest run tests/proxy.test.ts` | ✅ Killed (1 failed: "strips the Expect header") |
| M2 | Removed `"transfer-encoding"` from `STRIPPED_HEADERS` | `frontend/app/lib/proxy.ts:50` | round 1: `npx vitest run` (full suite) — SURVIVED (95 passed); round 2 after `d1f5923`: `npx vitest run tests/proxy.test.ts` | ✅ Killed (round 2: 1 failed — "strips every hop-by-hop request header"; suite green again after restore) |
| M3 | Reverted `_ensure_bucket` BotoCoreError classification (bare `create_bucket`, no `except BotoCoreError`) | `backend/app/infrastructure/storage/s3.py:65-71` | `pytest tests/test_storage_s3.py` | ✅ Killed (3 failed: get-unreachable, put-unreachable, bucket-create-failure) |
| M4 | Reverted `env.py` to unconditionally set `sqlalchemy.url` from settings | `backend/migrations/env.py:33-34` | `pytest tests/test_migrations.py` | ✅ Killed (1 failed: `test_upgrade_honors_caller_provided_url`, OperationalError on dead endpoint) |
| M5 | Removed `LEARNY_STORAGE_ENDPOINT` from worker environment | `docker-compose.yml:87` | `pytest tests/test_compose_prod.py` | ✅ Killed (1 failed: `test_worker_receives_object_storage_configuration`, KeyError) |
| M6 | Removed `"content-encoding"` from `STRIPPED_RESPONSE_HEADERS` | `frontend/app/lib/proxy.ts:65` | `npx vitest run tests/proxy-forwarding.test.ts` | ✅ Killed (1 failed: "drops content-encoding and content-length") |

**Sensor depth**: lightweight+ (6 behavior-level mutations across all four code fixes)
**Result**: 6/6 killed (M2 killed on round-2 re-run after fix `d1f5923`) — ✅ PASS

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code / no scope creep | ✅ (diff surface matches spec exactly; no unrelated edits) |
| Surgical changes | ✅ (s3.py +30/-, proxy.ts +15, env.py guard = 2-line semantic change) |
| Matches patterns | ✅ (Learny-owned errors at ports; fake-client stub mirrors existing test style) |
| Spec-anchored outcome check | ✅ (FND-08 closed in round 2) |
| Per-layer coverage | ✅ (adapter faults per path; proxy happy+strip+preserve; compose regression test) |
| No unclaimed tests | ✅ (every new test maps to FND-02..12) |
| Documented guidelines | ✅ (tasks.md gates followed; conventional commits; no ID leakage in commit subjects) |

---

## Gate Check

- **Backend**: `LEARNY_TEST_DATABASE_URL=... .venv/bin/pytest -q` → **504 passed, 0 failed, 1 warning** (44.27s). STATE.md records 504 at implementation time — no test-count regression.
- **Ruff**: `ruff check .` → All checks passed.
- **Frontend**: `npx vitest run` → **95 passed (13 files)**; `tsc --noEmit` → clean; `npm run build` → success.
- **CI YAML**: `yaml.safe_load` on `ci.yml` + `dependabot.yml` → valid.
- **Compose**: not rebuilt (Verifier docker access read-only); live stack: `GET /healthz` → `{"status":"ok"}`, 6/6 services healthy. First live CI run on the PR is the remaining acceptance evidence (per spec assumption "CI proof").
- **FND-12 fresh-DB**: Verifier's DROP/CREATE re-run denied by environment policy; relied on the killed M4 mutant + implementer's recorded twice-green fresh-DB gate + CI's per-run fresh DB.

---

## Fix Plans

### Fix 1: FND-08 — `transfer-encoding` strip had no discriminating test (round-1 surviving mutant M2) — ✅ RESOLVED

- **Root cause**: `frontend/tests/proxy.test.ts` ("strips every hop-by-hop request header") omitted `transfer-encoding` from both the incoming headers and the asserted-null list. The implementation stripped it (`proxy.ts:50`), but removing that entry passed the whole suite.
- **Fix applied**: commit `d1f5923` adds `"transfer-encoding": "chunked"` to the incoming headers (`proxy.test.ts:71`) and `"transfer-encoding"` to the asserted-null loop (`:84`).
- **Re-verified**: assertion located at its `file:line`; mutant M2 re-applied in scratch state → 1 failed (killed); file restored; tests green on restored code (6 passed); tree clean.

---

## Requirement Traceability

| Requirement | Status |
| ----------- | ------ |
| FND-01..19 | ✅ Verified (FND-08 verified in round 2 after `d1f5923`) |

---

## Summary

**Overall**: ✅ Ready.

**Spec-anchored check**: 19/19 ACs matched to spec outcomes (round-1 FND-08 gap closed by `d1f5923`).
**Sensor**: 6/6 mutants killed (M2 killed on round-2 re-run).
**Gate**: backend 504 passed; ruff clean; frontend 95 passed + tsc + build; CI YAML valid; compose observed healthy.

**Verdict**: PASS ✅ — caveats (not gaps): FND-12's direct fresh-DB re-run and the compose rebuild were environment-restricted for the Verifier; both are re-proven by the PR's first CI run (per the spec's own "CI proof" assumption).
