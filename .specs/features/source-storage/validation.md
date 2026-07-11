# Source Storage Validation

**Date**: 2026-07-04
**Spec**: `.specs/features/source-storage/spec.md`
**Diff range**: `9d94dee..d7223b8` (branch `feat/source-storage`, 8 commits T1–T8)
**Verifier**: independent sub-agent (author ≠ verifier), evidence-or-zero

**Post-verification update**: both Fix 1 and Fix 2 below were landed in `2a1f890`
(test-only, additive) — the boundary test kills the size-guard mutant (confirmed
by re-running it), and the insert-failure path is now regression-locked. Backend
gate re-run: 123 passed, 0 failed, ruff clean. SRC-03 and SRC-09 traceability
rows below are superseded by this — both are fully covered as of `2a1f890`.

---

## Task Completion

| Task | Status | Notes |
| ---- | ------ | ----- |
| T1 Domain `Source` + `SourceRepository` port | ✅ Done | `4b641bd` |
| T2 `sources` table + migration `0002` | ✅ Done | `566385e` |
| T3 `SqlAlchemySourceRepository` | ✅ Done | `1c8b69f` |
| T4 `S3StorageAdapter` (boto3) + config | ✅ Done | `52a1536` |
| T5 Application services + validation | ✅ Done | `8aead7e` |
| T6 `/api/sources` router + wiring | ✅ Done | `2ad5cb0` |
| T7 Sources client (same-origin) | ✅ Done | `1a109c6` — carries accepted `SPEC_DEVIATION` (dedicated proxy routes skipped; reuse existing catch-all `frontend/app/api/[...path]/route.ts`) |
| T8 `/sources` screen + `SourcesPanel` | ✅ Done | `d7223b8` |

All 8 tasks committed; none blocked or partial.

---

## Spec-Anchored Acceptance Criteria

### P1: Upload an EPUB source

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| Valid `.epub` + title → store bytes, persist owned row, `201` + secret-free summary | `201`; summary has id/title/filename/byte_size/status/created_at, NO object_key/checksum; row owned, status `uploaded`, checksum set; bytes in storage under opaque key | `test_web_sources.py:126` `assert resp.status_code == 201`; `:132` `status == "uploaded"`; `:135` `"object_key" not in body and "checksum" not in body`; `:144` `row.object_key == f"sources/{user_id}/{id}.epub"`; `:149` `_storage.get_object(...) == EPUB_BYTES` | ✅ PASS |
| Not `.epub` ext OR wrong content-type → `415`, persist nothing | `415`; no row, no object | ext: `test_web_sources.py:162` `== 415` + `:163` `_source_rows == []`; ctype: `:176` `== 415` + `:177` `[]` | ✅ PASS |
| Exceeds `LEARNY_EPUB_MAX_BYTES` → `413`, persist nothing | `413`; nothing persisted | `test_web_sources.py:189` `== 413` + `:190` `_source_rows == []` | ✅ PASS (boundary weak — see Sensor #3) |
| Missing/empty/whitespace/`>500` title → `422`, persist nothing | `422`; nothing persisted | whitespace: `test_web_sources.py:198` `== 422` + `:199` `[]`; `>500` (unit) `test_application_sources.py:92` `kind == "title"` | ✅ PASS |
| Unauthenticated POST → `401`, persist nothing | `401`; nothing persisted | `test_web_sources.py:226` `== 401` + `:227` `[]` | ✅ PASS |
| No CSRF OR untrusted origin → `403`, persist nothing | `403`; nothing persisted | missing: `test_web_sources.py:235` `== 403`; invalid: `:245` `== 403`; bad origin: `:255` `== 403` (each + `_source_rows == []`) | ✅ PASS |
| Object key has no email/title and is unique | key opaque owner-partitioned; unique | `test_web_sources.py:145` `"up@example.com" not in row.object_key`; `:146` `"Moby Dick" not in`; unit `test_application_sources.py:155-156`; uniqueness `test_repositories.py:247` `pytest.raises(IntegrityError)` | ✅ PASS |

### P1: List my sources

| Criterion | Spec outcome | `file:line` + assertion | Result |
| --------- | ------------ | ----------------------- | ------ |
| GET → `200` array, own only, newest-first | `200`; only owner rows, newest-first | `test_web_sources.py:328` `== 200`; `:330` `titles == ["Second", "First"]` (other user's "Not Mine" excluded) | ✅ PASS |
| No sources → `200` empty array | `200`; `[]` | `test_web_sources.py:336` `== 200` + `:337` `resp.json() == []` | ✅ PASS |
| Unauthenticated → `401` | `401` | `test_web_sources.py:342` `.status_code == 401` | ✅ PASS |

### P1: View a single source

| Criterion | Spec outcome | `file:line` + assertion | Result |
| --------- | ------------ | ----------------------- | ------ |
| Own source → `200` summary | `200`; that source | `test_web_sources.py:354` `== 200`; `:356` `body["id"] == source_id`; `:357` no object_key/checksum | ✅ PASS |
| Another user's source → `404`, no disclosure | `404` (not 403) | `test_web_sources.py:368` `== 404`; unit `test_application_sources.py:231` `pytest.raises(SourceNotFound)` | ✅ PASS |
| Nonexistent id → `404` | `404` | `test_web_sources.py:374` `== 404` | ✅ PASS |
| Malformed (non-UUID) id → `422` | `422` | `test_web_sources.py:380` `== 422` | ✅ PASS |

### P1: Sources screen in the web app

| Criterion | Spec outcome | `file:line` + assertion | Result |
| --------- | ------------ | ----------------------- | ------ |
| Visit `/sources` → fetch+render via same-origin proxy, empty-state | render through `/api/sources`; empty-state | screen `sources-screen.test.tsx:82` `findByText("No sources yet.")`; client same-origin `sources-client.test.ts:50` `url == "/api/sources"` + `:52` `credentials == "same-origin"` | ✅ PASS |
| Select epub+title+submit → POST via proxy (cookie+CSRF), show new source | multipart POST same-origin w/ X-CSRF-Token; list updates | screen `sources-screen.test.tsx:101` `findByText("My Book")`; client `sources-client.test.ts:89` `url == "/api/sources"` + `:94` `X-CSRF-Token == "csrf-xyz"` + `:102` `body.get("title")` | ✅ PASS |
| API rejects (415/413/422) → surface error, add nothing | error shown; no row added | `sources-screen.test.tsx:123` `alert.textContent == "Only EPUB files are supported."` + `:124` `queryByText("Not a book") == null` | ✅ PASS |
| Unauthenticated visit → redirect to `/login` (UX only) | onRequireAuth fires | `sources-screen.test.tsx:139` `expect(onRequireAuth).toHaveBeenCalledTimes(1)` | ✅ PASS |

**Status**: ✅ All 18 acceptance criteria covered with assertions matching the spec-defined outcome.

---

## Edge Cases

- [x] **Storage unavailable at upload → `502`/`503` + log user_id, no row** — `test_web_sources.py:269` `== 503`, `:270` `_source_rows == []`, `:271-272` log carries `user_id`, `:275` no secrets in log. (Spec allows 502/503; impl returns 503.) ✅
- [ ] **Object stored but INSERT fails → rollback row + `5xx`, orphan object** — ⚠️ **NO DIRECT TEST EVIDENCE.** The storage-*put*-failure path is tested (unit `test_application_sources.py:177`, web `:259`), and repo-level uniqueness proves `add` raises `IntegrityError` (`test_repositories.py:239`), but no test forces a post-`put_object` INSERT failure to assert the request UoW rolls back the row and returns `5xx`. Behavior is inherited from the Cycle-1 transactional `get_db_connection` (rolls back on any exception) and is very likely correct, but is unverified for this feature. **Coverage gap (minor).**
- [x] **Same file twice → two independent sources, distinct keys** — `test_web_sources.py:307-310` both `201`, distinct ids, `len(keys) == 2`. ✅
- [x] **No file part → `422`, persist nothing** — `test_web_sources.py:216` `== 422` + `:217` `[]`. ✅
- [x] **Zero-byte file → `422`** — `test_web_sources.py:207` `== 422` + `:208` `[]`; unit `test_application_sources.py:80` `kind == "empty"`. ✅

---

## Discrimination Sensor

| # | File:line | Description | Killed? |
| - | --------- | ----------- | ------- |
| 1 | `app/application/sources.py:119-123` | Removed the `NotAuthorized`→`SourceNotFound` remap in `GetSource` (non-owner would get 403, not 404) | ✅ Killed — `test_application_sources.py::test_get_source_hides_other_users_source_as_not_found` + `test_web_sources.py::test_get_cross_user_source_returns_404` (got 403, expected 404) both FAILED |
| 2 | `app/infrastructure/web/sources.py:49-67` | Added `object_key`/`checksum` to `SourceSummary` + `from_entity` (leak internal fields) | ✅ Killed — `test_upload_valid_epub_persists_row_and_object` + `test_get_own_source_returns_200` (secret-free assertion) both FAILED |
| 3 | `app/application/validation.py:75` | Flipped size guard `byte_size > max_bytes` → `>= max_bytes` (a file of exactly `max_bytes` would be wrongly rejected) | ❌ **Survived** — all 37 sources tests still passed; no test pins the exact `max_bytes` boundary (spec AC3 "exceeds" = strictly greater, so a max-size file must be accepted, but nothing asserts it) |

**Sensor depth**: lightweight (3 mutations on highest-risk new code — ownership 404, secret-free summary, size guard)
**Result**: 2/3 killed, 1 survived — the two P0-security-shaped invariants (no existence disclosure, no secret leakage) are well-guarded; the size guard's exact boundary is under-tested.
**Tree state**: all three mutations reverted; `git status` confirms no residue in `sources.py`, `web/sources.py`, `validation.py`.

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code (no features beyond spec) | ✅ — single `uploaded` state, one table, no dedup/versioning (all in Out of Scope) |
| Surgical changes (no unrelated refactors) | ✅ — extends `validation.py`/`errors.py`/`error_handlers.py`/`dependencies.py`/`repositories.py` in-place, mirrors Cycle-1 patterns |
| No scope creep | ✅ — T7 SPEC_DEVIATION actively *avoided* speculative duplicate proxy files |
| Matches existing patterns/style | ✅ — frozen-dataclass entity, `runtime_checkable` Protocol, Connection-injected repo, composition-root wiring, port/adapter boundary (boto3 confined to `storage/s3.py`) |
| Spec-anchored outcome check (asserted values match spec) | ✅ — every assertion targets the exact spec status/state |
| Per-layer Coverage Expectation met (domain 1:1; routes happy+edge+error) | ⚠️ — routes cover happy+edge+error thoroughly; one listed edge case (INSERT-fail rollback) and one boundary (exact max_bytes) are unasserted |
| Every test maps to a spec requirement — no unclaimed tests | ✅ — all sources tests trace to an AC / edge case / Done-when |
| Documented guidelines followed | ✅ — ruff `E,F,I,UP,B` line 100 clean; `testpaths=["tests"]`, `asyncio_mode=auto`; boundary/layering per ADR-007/009; secret-free logging (SRC-10) asserted |

---

## Gate Check

- **Backend gate**: `uv run pytest` → **121 passed, 0 failed, 0 skipped** (1 unrelated StarletteDeprecationWarning); `uv run ruff check .` → **All checks passed!**
- **Frontend gate**: `npm test` → **32 passed (7 files), 0 failed**; `npx tsc --noEmit` → **exit 0**
- **Pre-existing non-blocking item (ignored per brief)**: `ruff format --check .` drift on 10 unrelated Cycle-1 files — confirmed pre-existing on `main`, not part of this gate.
- **Test delta**: +~50 new tests across `test_domain_sources.py` (3), `test_application_sources.py` (17), `test_repositories.py` (+5 source), `test_storage_s3.py` (3), `test_web_sources.py` (22), `test_migrations.py` (+1), frontend `sources-client.test.ts` (5) + `sources-screen.test.tsx` (4). No test count decrease; no weakened assertions.

---

## Fix Plans (recommended, non-blocking)

### Fix 1: Assert the exact `max_bytes` boundary (surviving mutant #3)
- **Root cause**: The oversize test uses `max_bytes + 1`; nothing asserts a file of exactly `max_bytes` is *accepted*, so a `>`→`>=` regression passes undetected.
- **Fix task**: Add a unit test to `test_application_sources.py` — `validate_source_upload(byte_size=MAX_BYTES)` returns `None` (accepted at the boundary).
- **Priority**: Minor.

### Fix 2: Cover the "object stored then INSERT fails → rollback + 5xx" edge (uncovered spec edge case)
- **Root cause**: Only the put-*failure* path is tested; the put-succeeds-then-insert-fails rollback path (spec Edge Cases + SRC-09) has no direct assertion.
- **Fix task**: Add an integration test that lets `put_object` succeed but forces the INSERT to fail (e.g. pre-insert a row with the same `object_key`, or a fake repo whose `add` raises), then assert `5xx` and zero committed `sources` rows.
- **Priority**: Minor (mechanism is proven Cycle-1 UoW; value is regression-locking it for sources).

---

## Requirement Traceability Update

| Requirement | Previous | New |
| ----------- | -------- | --- |
| SRC-01 upload create | Pending | ✅ Verified |
| SRC-02 type/ext validation | Pending | ✅ Verified |
| SRC-03 size cap | Pending | ✅ Verified (⚠️ exact boundary untested — Fix 1) |
| SRC-04 title validation | Pending | ✅ Verified |
| SRC-05 auth + CSRF/origin + rate-limit | Pending | ✅ Verified |
| SRC-06 opaque owner-partitioned key | Pending | ✅ Verified |
| SRC-07 boto3 adapter + bucket ensure | Pending | ✅ Verified |
| SRC-08 owner-scoped list newest-first | Pending | ✅ Verified |
| SRC-09 ownership→404 + storage/DB failure | Pending | ✅ Verified (⚠️ INSERT-fail rollback edge untested — Fix 2) |
| SRC-10 lifecycle logging, no secrets | Pending | ✅ Verified |
| SRC-11 web `/sources` via same-origin proxy | Pending | ✅ Verified |
| SRC-12 migration 0002 | Pending | ✅ Verified |

---

## Summary

**Overall**: ✅ Ready (2 minor, non-blocking coverage recommendations)

**Spec-anchored check**: 18/18 acceptance criteria matched the spec outcome with cited evidence.
**Sensor**: 2/3 mutations killed; 1 survived (size-guard exact boundary — a test-strength gap, not a defect).
**Gate**: backend 121 passed / 0 failed + ruff clean; frontend 32 passed / 0 failed + tsc clean.

**What works**: The full vertical slice — validated multipart EPUB upload → opaque owner-partitioned S3 key → owned Postgres row → secret-free summary; owner-scoped list (newest-first) and single-source read with 404-not-403 no-disclosure enforcement; every auth/CSRF/origin/type/size/title/empty reject persisting nothing; same-origin Next.js `/sources` screen with empty-state, add-on-success, error surface, and UX-only unauth redirect. Port/adapter and layering boundaries are respected; boto3 stays confined to the storage adapter.

**Issues found**:
1. Surviving mutant — `validate_source_upload` exact `max_bytes` boundary is unasserted (Fix 1, minor).
2. Uncovered edge case — "object stored then INSERT fails → rollback + 5xx" has no direct test (Fix 2, minor).
Both are test-coverage refinements; no acceptance criterion is unmet and the implementation is correct.

**Next steps**: Optionally land Fix 1 + Fix 2 to lock the boundary and rollback behaviors, then run `learny-finalize` for the PR. Neither blocks merge on its own.
