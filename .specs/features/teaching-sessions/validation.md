# Teaching Sessions Validation

**Date**: 2026-07-12
**Spec**: `.specs/features/teaching-sessions/spec.md`
**Diff range**: `58fac91..2487efa` (15 commits, `feat/teaching-sessions`)
**Verifier**: independent sub-agent (author ≠ verifier); evidence-or-zero, re-derived independently

---

## Task Completion

All 5 execution phases (A–E) landed across the 15-commit range. Every TEACH
requirement (TEACH-01..24) is traced below to a `file:line` + assertion.

---

## Spec-Anchored Acceptance Criteria

Paths are relative to `backend/` and `frontend/`.

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| TEACH-01 start on owned/ready/valid anchor | 201 `{id, source_id, target:{anchor,section_path,title}, created_at}` | `tests/test_web_teaching.py:245` `assert resp.status_code == 201` + `:247` field set + `:250` `body["target"] == {anchor,section_path,title}`; unit `tests/test_application_teaching.py:398-404` snapshot | ✅ PASS |
| TEACH-02 missing/non-owned source | 404, no disclosure (identical body) | `tests/test_web_teaching.py:276-278` `non_owned==missing==404`, `non_owned.json()==missing.json()` | ✅ PASS |
| TEACH-03 source not ready at create | 409 | `tests/test_web_teaching.py:294` `assert resp.status_code == 409` | ✅ PASS |
| TEACH-04 unknown target anchor | 422 | `tests/test_web_teaching.py:310` `assert resp.status_code == 422` | ✅ PASS |
| TEACH-05 read session state | 200 session + turns `turn_index` asc, each with citations | `tests/test_web_teaching.py:391` `200`, `:402` `[t["turn_index"]]==[0,1]`, `:419-425` citation fields | ✅ PASS |
| TEACH-06 missing/non-owned session | 404 | `tests/test_web_teaching.py:445-447` identical 404 bodies | ✅ PASS |
| TEACH-07 post valid turn | 201 turn `{turn_index,message,answer_status,text,citations,evidence_count,model,created_at}`, status ∈ {answered, not_found_in_source} | `tests/test_web_teaching.py:589` `201`, `:591-600` exact field set, `:602` `answer_status=="answered"`; not-found value at `:655` | ✅ PASS |
| TEACH-08 empty/over-max message | 422 | `tests/test_web_teaching.py:672` blank, `:682` whitespace, `:695` over-max → 422 | ✅ PASS |
| TEACH-09 retrieval scoped to target+descendants; no citation outside | anchors = target + descendants; out-of-scope excluded | unit `tests/test_application_teaching.py:685` `call["anchors"]==["ch1.xhtml","ch1.xhtml#sec-a"]` (sibling excluded); DB `tests/test_retrieval.py:330` `{e.anchor for e in scoped}=={"ch1.xhtml"}` | ✅ PASS |
| TEACH-10 ungrounded/found=false/blank | `not_found_in_source`, `text==""`, `citations==()` | ungrounded `tests/test_application_teaching.py:809-813`; found=false `:837-838`; blank `:863-864` | ✅ PASS |
| TEACH-11 empty evidence | `not_found_in_source` without invoking port | `tests/test_application_teaching.py:776` `generation.calls==[]`, `:777` not-found | ✅ PASS |
| TEACH-12 bounded history | port gets at most last `history_turns` pairs | `tests/test_application_teaching.py:719-722` last-2 slice; edge (all) `:752-755` | ✅ PASS |
| TEACH-13 port raises | 502, persist nothing | unit `tests/test_application_teaching.py:883` raises, `:887` `add_calls==0`; web `tests/test_web_teaching.py:785` `502`, `:791` turns empty | ✅ PASS |
| TEACH-14 not_found still persisted (empty) | persisted, empty text, no citations | `tests/test_application_teaching.py:783` persisted; repo `tests/test_repositories.py:1169-1172` | ✅ PASS |
| TEACH-15 source no longer ready at turn | 409 | unit `tests/test_application_teaching.py:907` raises + `:910` no retrieval; web `tests/test_web_teaching.py:731` `409` | ✅ PASS |
| TEACH-16 target anchor gone post-reingest | 409 with readable detail | unit `tests/test_application_teaching.py:928` raises; web `tests/test_web_teaching.py:743` `409` + `:744` `resp.json()["detail"]` truthy | ✅ PASS |
| TEACH-17 turn_index race | at most one wins; loser 409 | repo `tests/test_repositories.py:1183` `raises(TeachingTurnConflict)` on dup index; unit `tests/test_application_teaching.py:953` propagation | ✅ PASS |
| TEACH-18 rate limit | 429 | web `tests/test_web_teaching.py:565` start 429 + Retry-After, `:824` turn 429 | ✅ PASS |
| TEACH-19 one content-free log | exactly 1 line: outcome, session id, evidence count, model; never message/answer | `tests/test_application_teaching.py:1024` `len(records)==1`, `:1026-1029` fields present, `:1030-1031` message/answer absent | ✅ PASS |
| TEACH-20 citations survive re-ingest | stored turns keep full citation snapshots | repo `tests/test_repositories.py:1238-1239` snapshot intact after `corpus_documents` delete cascades chunks | ✅ PASS |
| TEACH-21 list sessions | 200 newest-first `{id,target,created_at,turn_count}` | web `tests/test_web_teaching.py:475` order, `:476` field set, `:477-478` turn_count; unit `tests/test_application_teaching.py:572-573` | ✅ PASS |
| TEACH-22 browser Teach flow | picker/start/cited turn/not-found/error states/resume | `frontend/tests/teach-screen.test.tsx:228-233` cited render, `:252-254` not-found, `:281` 409 banner, `:295-322` 422/429/502, `:363-378` resume history; link `frontend/tests/sources-screen.test.tsx:553-555` | ✅ PASS |
| TEACH-23 auth + CSRF/Origin on endpoints | 401 no session; 403 missing CSRF / untrusted Origin | web `tests/test_web_teaching.py:335` 401, `:344` 403 CSRF, `:358` 403 Origin, `:804` turn 403 CSRF | ✅ PASS |
| TEACH-24 response carries adapter model | turn `model` = adapter identity (both outcomes) | answered `tests/test_application_teaching.py:651` `model==_MODEL`; empty-evidence from port attr `:781` | ✅ PASS |

**Status**: ✅ All 24 ACs covered with assertions matching the spec-defined outcome. No spec-precision gaps. (TEACH-16 "readable detail" is loosely specified; the test asserts a non-empty `detail` body, which satisfies the spec's stated bar.)

---

## Discrimination Sensor

Lightweight+ (6 behavior-level mutations on the highest-risk new logic), each run in scratch state (Edit → run targeted file → confirm FAIL → `git checkout -- <file>`). Tree verified clean after each.

| # | File:line | Mutation | Killed by | Killed? |
| --- | --- | --- | --- | --- |
| 1 | `app/application/teaching.py:272` | Subtree filter `s.section_path[:depth]==target...` → `True or ...` (include siblings) | `test_turn_scopes_retrieval_to_target_and_descendants` (extra `ch2.xhtml`) | ✅ Killed |
| 2 | `app/application/grounding.py:31` | Grounding guard `not grounded` → `grounded` | `test_turn_answered`, `test_turn_ungrounded`, and QA `test_ask_answered_grounds...` | ✅ Killed |
| 3 | `app/application/teaching.py:293` | Empty-evidence short-circuit `if not evidence:` → `if not evidence and False:` (force port call) | `test_turn_empty_evidence_not_found_without_invoking_port` | ✅ Killed |
| 4 | `app/application/teaching.py:281` | Bounded history slice `prior[-history_turns:]` → `prior[:]` | `test_turn_passes_bounded_history_last_n` | ✅ Killed |
| 5 | `app/application/teaching.py:307` | 502 mapping `except Exception` → `except ValueError` (RuntimeError escapes) | unit `test_turn_port_raise_maps_to_502...` + web `test_post_turn_generation_failure_returns_502...` | ✅ Killed |
| 6 | `app/infrastructure/db/repositories.py:573` | Conflict translation `except IntegrityError` → `except KeyError` | `test_teaching_turn_duplicate_index_raises_conflict` | ✅ Killed |

**Sensor depth**: lightweight+ (6 mutations)
**Result**: 6/6 killed — PASS ✅. Notably mutation 2 was also caught by the pre-existing QA suite, empirically confirming the grounding-extraction refactor (`89f15e3`) preserved Q&A behavior.

---

## Code Quality

| Principle | Status |
| --- | --- |
| Minimum code (no features beyond spec) | ✅ |
| Surgical changes (only in-scope files) | ✅ |
| No scope creep / no unrelated "improvements" | ✅ |
| Matches existing patterns (mirrors `qa.py` / `questions.py` / retrieval RRF) | ✅ |
| Spec-anchored outcome check (asserted values match spec) | ✅ |
| Per-layer coverage (domain 1:1 ACs; routes happy+edge+error) | ✅ |
| Every test maps to a TEACH AC / edge case / Done-when — no unclaimed tests | ✅ |
| Framework-free domain boundary (ADR-0007/0009) asserted by import test | ✅ `test_teaching_module_imports_no_web_or_provider_sdk` |
| Documented guidelines followed | ✅ ADR-0003/0006/0007/0009/0014, AD-018/024/027/030-035 honored |

---

## Edge Cases

- [x] Target with descendants → their chunks in scope (`test_turn_scopes_retrieval_to_target_and_descendants`; DB `test_anchor_scope_filters_both_arms_to_subtree`).
- [x] Corpus re-ingested, anchor survived → turns continue against new rows (anchor re-resolved per turn; `test_turn_target_gone` proves the negative, `test_teaching_turn_citations_survive_corpus_deletion` proves snapshot survival).
- [x] `history_turns` exceeds stored turns → all passed, no error (`test_turn_history_bound_exceeds_stored_passes_all`).
- [x] Session create races a source status change → readiness is per-request; next turn 409s (`test_turn_source_not_ready_raises_before_retrieval` / web 409).
- [x] Malformed body (missing field, bad UUID) → 422 (`test_start_missing_source_id_returns_422`; bounds tests).

---

## Gate Check

- **Backend**: `LEARNY_TEST_DATABASE_URL=...learny_test uv run pytest -q` → **426 passed, 0 failed, 0 skipped**, 1 warning (starlette httpx deprecation, pre-existing). Integration tests ran (env var set; `requires_db` active).
- **Backend lint**: `uv run ruff check .` → **clean (exit 0)**.
- **Frontend**: `npm test` → **88 passed** (12 files, 0 failed).
- **Frontend types**: `npx tsc --noEmit` → **clean (exit 0)**.
- **Test count before feature**: backend 351 / frontend 60.
- **Test count after feature**: backend 426 / frontend 88.
- **Delta**: **+75 backend, +28 frontend**. No decrease; no weakened assertions observed.
- **Skipped**: none.
- **Failures**: none.

---

## Requirement Traceability Update

| Requirement | Previous | New |
| --- | --- | --- |
| TEACH-01..04 | Design/Pending | ✅ Verified |
| TEACH-05,06,20 | Design/Pending | ✅ Verified |
| TEACH-07..19,24 | Design/Pending | ✅ Verified |
| TEACH-21 | Design/Pending | ✅ Verified |
| TEACH-22 | Design/Pending | ✅ Verified |
| TEACH-23 | Design/Pending | ✅ Verified |

---

## Summary

**Overall**: ✅ Ready

**Spec-anchored check**: 24/24 ACs matched the spec-defined outcome; 0 spec-precision gaps.
**Sensor**: 6/6 mutations killed (lightweight+).
**Gate**: backend 426 passed, frontend 88 passed, ruff clean, tsc clean.

**What works**: Session start with target snapshot; owner-scoped 404 collapse (identical bodies); readiness (409) and unknown-anchor (422) guards; cited turns scoped to the target subtree (proven both at the service anchor set and the DB filter); the AD-027 grounding guard shared with Q&A (regression net intact); empty-evidence short-circuit that never invokes the port; bounded history; 502-with-no-persist; turn-index race → 409; content-free completion log; citation snapshots that survive re-ingestion; per-source list newest-first with turn counts; full browser Teach slice with cited/not-found/error/resume states; auth + CSRF/Origin + rate limiting on every mutating route.

**Issues found**: none.

**Next steps**: mark the feature verified; no fix tasks. Clean PASS → no lessons recorded (per lessons.md).
