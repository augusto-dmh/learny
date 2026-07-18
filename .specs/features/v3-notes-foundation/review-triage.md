# PR #31 Review Triage — v3-notes-foundation

Review: 2 inline + 2 PR-level comments, 6 lanes (security/architecture/regression all zero-finding; requirements: 14/14 implemented, NF-08 deviation judged defensible). Comments are deleted after fixes; this file is the surviving record.

| # | Source | Location | Finding | Verdict | Action | Rationale |
|---|---|---|---|---|---|---|
| F1 | inline (test-coverage) | `backend/app/application/notes.py:342` | Capture-highlight over-cap body (422) documented but untested — the only route where `_validate_body` runs after anchor resolution, so the 422 branch had no covering test | **Real** | **Fix** | One DB-gated TestClient case: resolvable selection + over-cap body → 422, nothing persisted |
| F2 | inline (performance) | `backend/app/infrastructure/db/repositories.py:1516-1528` | `set_tags` ran `1 + 3N` statements per save (per-tag upsert + select + insert loop), firing on every create/update/capture | **Real** | **Fix** | Batched to a constant four statements (bulk upsert, one `IN` lookup, bulk wire-up) with defensive in-batch dedupe; behavior identical — existing DB-gated tag tests (uniqueness, normalization, rewrite-on-update) pass unchanged |
| F3 | requirements comment | NF-08 | Source-delete orphaning has no product call site (no delete-source feature exists) | Real (recorded) | **Won't fix** | Already an accepted SPEC_DEVIATION in-code and in validation.md; capability shipped (`orphan_anchors_for_source`) + reconcile-path orphaning DB-tested |

**Counts:** 3 findings — 3 real (2 fixed, 1 recorded won't-fix), 0 false.
**Fix commits:** `test(notes): cover the over-cap body on highlight capture` + `perf(notes): batch tag writes on note save`.
**Post-fix gates:** DB-gated notes suites 50 passed; offline full backend 777 passed / 403 skipped; ruff clean.
