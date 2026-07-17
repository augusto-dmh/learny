# v2-active-recall Validation

**Date**: 2026-07-17
**Spec**: `.specs/features/v2-active-recall/spec.md`
**Diff range**: `main..HEAD` (18 commits, d9f6880..0b651b6)
**Verifier**: independent sub-agent (author ≠ verifier); evidence-or-zero

---

## Verdict: PASS ✅

All 25 acceptance criteria (QUIZ-01..25) are covered by located, spec-anchored assertions whose asserted values match the spec-defined outcomes. All four gates are green (backend pytest + ruff; frontend vitest + tsc + build). All 6 injected behaviour-level mutations were killed by the existing tests.

---

## Task Completion

| Phase | Tasks | Status |
| ----- | ----- | ------ |
| A (foundation: deps/settings, migration 0008, domain/QC) | A1–A3 | ✅ Done |
| B (repos, deterministic + Anthropic adapters, factory) | B1–B3 | ✅ Done |
| C (deck services + QC/dedup, Celery tasks, reconcile) | C1–C3 | ✅ Done |
| D (FSRS adapter, review services, router, Anki export) | D1–D4 | ✅ Done |
| E (quiz client, review screen, library integration) | E1–E3 | ✅ Done |
| F (groundedness eval, answerability judge, ADR-0021) | F1–F3 | ✅ Done |

---

## Spec-Anchored Acceptance Criteria

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion expression | Result |
| --- | --- | --- | --- |
| QUIZ-01 migration 0008 creates the 4 tables and downgrade removes them | 4 tables present with cascade FKs, `(source_id, content_key)` unique, rating CHECK 1..4, no corpus FK, indexes; up→down→up round-trips | `tests/test_migrations.py:764` `assert ["source_id","content_key"] in item_uniques`; `:780` `assert "1" in check_def and "4" in check_def`; `:798-802` down drops all four; `:810-816` re-up restores | ✅ PASS |
| QUIZ-02 duplicate content_key upserts content, never touches scheduling/log | one row survives; content updated; scheduling snapshot + log rows byte-identical | `tests/test_repositories_quiz.py:239` `assert repo.get_scheduling(item.id) == scheduling_before`; `:244` `assert log_after == log_before`; `:204` `assert total == 1` | ✅ PASS |
| QUIZ-03 deck POST on ready owned source → 202 + queued job + enqueue after commit | 202; job row status `queued`; enqueuer called with (source_id, job_id) | `tests/test_web_quiz.py:199` `assert resp.status_code == 202`; `:206` `stored.status == QUEUED`; `:208` `assert calls == [(UUID(source_id), UUID(body["id"]))]` | ✅ PASS |
| QUIZ-04 second POST while job queued/running → 409 | status 409 | `tests/test_web_quiz.py:220` `assert resp.status_code == 409`; svc `tests/test_application_quiz.py:341` `pytest.raises(QuizDeckConflict)` | ✅ PASS |
| QUIZ-05 local provider offline; anthropic submits 1 batch/section, poll reschedules, persists | local persists grounded items; anthropic 1 request/section w/ chunk-id enum schema; collect None while processing | local `tests/test_worker_quiz.py:262-273`; anthropic `tests/test_quiz_anthropic.py:123` (one request/section + constrained schema), `:173` collect None while processing; poll reschedule `tests/test_worker_quiz.py:328-341` | ✅ PASS |
| QUIZ-06 anchor_quote not verbatim in chunk → discarded; accepted store anchor/path/excerpt/chunk_hash | discarded (0 generated, 1 discarded); snapshot fields stored | `tests/test_application_quiz.py:451` `(generated, discarded) == (0,1)` + `:452` empty; positive `:433-435` excerpt/path/anchor stored; chunk_hash `tests/eval/test_quiz_groundedness.py:156` | ✅ PASS |
| QUIZ-07 cloze masked span not in anchor_quote → discarded | discarded | `tests/test_application_quiz.py:489` `(0,1)`; unit `tests/test_domain_quiz.py:84` `cloze_is_valid(...dog...) is False`; `:90` blank-missing False | ✅ PASS |
| QUIZ-08 embedding cosine ≥ threshold (0.90) vs accepted → discarded | at threshold (=) discarded; below kept; vs persisted too | `tests/test_application_quiz.py:547` at-threshold `(1,1)`; `:563` below `(2,0)`; `:595` vs persisted `(0,1)` | ✅ PASS |
| QUIZ-09 job succeeded w/ counts; each item gets initial scheduling row; re-run idempotent; failure → failed+last_error | succeeded w/ counts; 1 scheduling row/item; re-run no scheduling reset; fail sets last_error | `tests/test_worker_quiz.py:265-273` succeeded+scheduling==items; `:288-290` idempotent re-run; `:411-413` failed + `last_error == "Quiz deck generation failed."` | ✅ PASS |
| QUIZ-10 candidates typed free_recall/cloze only; no MCQ anywhere | vocabulary == {free_recall, cloze}; mcq candidate discarded | `tests/test_domain_quiz.py:101` `assert values == {"free_recall","cloze"}`; `tests/test_application_quiz.py:525` mcq `(0,1)` + empty | ✅ PASS |
| QUIZ-11 SchedulingPort initial + review; FSRS-6 defaults; snapshot as real columns; ratings monotonic | initial due-now Learning; Again<Hard<Good<Easy; repeated Good grows; UTC; snapshot round-trips | `tests/test_scheduling_fsrs.py:56-60` initial; `:80` `again<hard<good<easy`; `:110` grows; `:66` UTC; `:154` lossless round-trip | ✅ PASS |
| QUIZ-12 review rating 1..4 on active → atomic scheduling update + log append; 422 out-of-range; 409 stale/orphaned | 200 + due advanced + log row (rating,duration); 422; 409 | `tests/test_web_quiz.py:520` due>now, `:527` log `[(3,4200)]`; `:537` 422; `:547` 409 (stale/orphaned param); svc `tests/test_application_reviews.py:221` | ✅ PASS |
| QUIZ-13 due queue returns active due<=now across sources, ordered due/id, limit cap, total | active past-due only, order due ASC/id, limit honored + full total; source filter | `tests/test_repositories_quiz.py:321` order earlier-first; `:379-380` total 3 w/ limit 2; `:411` source filter; route `tests/test_web_quiz.py:475` 422 over-100 | ✅ PASS |
| QUIZ-14 overview returns items+counts+due count+latest job | items(id,type,question,status,due) + counts_by_status + due_count + latest_job | `tests/test_web_quiz.py:382-392` keys+counts+due_count==1+latest_job status; `:402-404` null job/empty | ✅ PASS |
| QUIZ-15 review card includes citation; anchor resolves; source-changed shows excerpt+indication | citation(section_path,anchor,excerpt) in due view; Open-in-book link; stale/orphaned surfaced as source-changed | due view `tests/test_web_quiz.py:463-467` citation dict; UI `frontend/tests/review-screen.test.tsx:124-130` footnote + Open-in-book href; source-changed badge `frontend/tests/library-screen.test.tsx:177` (due queue is active-only by design, so the indication is realized on the library screen) | ✅ PASS |
| QUIZ-16 reconcile keep/stale/relocate/orphan; never touch scheduling/log | matrix statuses; relocate adopts anchor+path; scheduling/log byte-identical | `tests/test_reconcile_quiz.py:203-220` full matrix; `:250-251` scheduling+log unchanged after relocate; wired in pipeline `tests/test_worker_quiz.py:493` | ✅ PASS |
| QUIZ-17 stale/orphaned excluded from due, included in overview | due excludes stale/orphaned; overview includes with status | `tests/test_repositories_quiz.py:350-351` due excludes; overview `tests/test_web_quiz.py:384` counts include STALE | ✅ PASS |
| QUIZ-18 auth 401; non-owner/missing 404 no-disclosure; state-changing enforce origin+CSRF+rate_limit (429) | 401/404-identical/403/429 | `tests/test_web_quiz.py:257` 401; `:246-248` identical 404 bodies; `:265` 403 CSRF; `:273` 403 origin; `:360` 429 | ✅ PASS |
| QUIZ-19 review screen: queue, cloze blank, reveal+citation+Open-in-book, 4-button grade, advance, summary | full session flow + summary counts per rating | `frontend/tests/review-screen.test.tsx:117` cloze blank shown; `:181-205` grade/advance/summary counts; `:260` empty state | ✅ PASS |
| QUIZ-20 library Generate-deck w/ polling + counts + stale/orphaned badges | generate button, in-progress polling, counts, badges | `frontend/tests/library-screen.test.tsx:133,154,177,271`; polling `frontend/tests/use-quiz-deck-polling.test.tsx:55,84,104` | ✅ PASS |
| QUIZ-21 new clients + screens have vitest coverage | fetchImpl client tests + jsdom component tests | `frontend/tests/quiz-client.test.ts` (18 cases, all 5 fns success+error); review-screen + library-screen component tests | ✅ PASS |
| QUIZ-22 export streams genanki .apkg; GUID from (source_id, content_key); 404 empty | non-empty valid zip; GUID stable across builds + regenerated item; cloze reconstruction; 404 empty | `tests/test_export_anki.py:100` GUID == guid_for(source_id,content_key); `:110` stable; `:119` stable across regenerated; `:133` cloze `{{c1::}}`; route `:195` filename, `:208` 404 empty | ✅ PASS |
| QUIZ-23 deterministic groundedness eval in PR suite: 100% containment, cloze validity, anchor resolvability + poisoned discard | every persisted item grounded (containment+chunk_hash+anchor resolves); poisoned candidate discarded | `tests/eval/test_quiz_groundedness.py:154-168` invariants; `:217-220` poisoned discarded (generated 1, discarded 1) | ✅ PASS |
| QUIZ-24 answerability judge (`live and eval`), versioned prompt, JSONL, offline-skipped | prompt versioned by sha256; structured-outputs parse; JSONL; capped; live marker | `tests/eval/test_quiz_answerability.py:74-79` prompt hash; parse + JSONL + cap (offline, fake client); live test carries `live and eval` marker | ✅ PASS |
| QUIZ-25 ADR-0021 Accepted, cross-references RFC-002, matches decision set | Accepted; free-recall/cloze, FSRS-6, snapshot/reconcile, Batch API, genanki | `docs/adr/0021-active-recall-design.md:4` Status Accepted; §Decision Outcome enumerates all 5 decisions; references RFC-002 Cycle E | ✅ PASS |

**Status**: ✅ All 25 ACs covered with spec-matching assertions. No spec-precision gaps.

**Note (QUIZ-15, not a gap):** The spec's "source changed" clause is realized on the **library** screen (stale/orphaned badges), not inside the review card, because the due queue is active-only by design (design.md §Review; QUIZ-17). Active items always have a resolving anchor (reconciliation keeps `active` only when the anchor exists or the quote relocated), so the review card's Open-in-book link always resolves. The snapshotted `source_excerpt` is always carried in the citation. This is a coherent design choice, fully covered, not a shortfall.

---

## Discrimination Sensor

Six behaviour-level faults injected one at a time in a scratch working tree (edit → run targeted tests → revert with `git checkout -- <file>`; only source files were mutated, never `.specs`).

| # | File | Mutation | Target tests | Killed? |
| - | ---- | -------- | ------------ | ------- |
| 1 | `app/application/quiz_qc.py:45` | `quote_in_text` containment inverted (`in` → `not in`) | test_domain_quiz + test_application_quiz | ✅ Killed (10 failures inc. `test_finalize_discards_unverbatim_quote`) |
| 2 | `app/infrastructure/db/repositories.py:1060` | due query drops `status == ACTIVE` filter | test_repositories_quiz | ✅ Killed (`test_due_for_user_excludes_stale_and_orphaned`) |
| 3 | `app/application/quiz.py:479` | reconcile misclassifies stale as `ORPHANED` | test_reconcile_quiz | ✅ Killed (`test_reconcile_matrix_keep_stale_relocate_orphan`) |
| 4 | `app/infrastructure/scheduling/fsrs.py:81` | FSRS review ignores rating (`Rating(rating)` → `Rating(3)`) | test_scheduling_fsrs | ✅ Killed (3 failures: monotonic, easy>good, again-resets) |
| 5 | `app/application/quiz.py:281-283` | finalize re-creates scheduling on every upsert (`if inserted` → always) | test_application_quiz + test_worker_quiz | ✅ Killed (`test_finalize_reupsert_preserves_scheduling_and_count`, `test_generate_is_idempotent_across_reruns`) |
| 6 | `app/infrastructure/web/quiz.py:349` | `rate_limit_quiz` dependency dropped from review POST | test_web_quiz | ✅ Killed (`test_review_rate_limit_returns_429`) |

**Sensor depth**: P0-full (6 mutations across QC grounding, ownership/status filtering, reconciliation classification, FSRS rating fidelity, scheduling-preservation idempotency, and route hardening — the highest-risk surfaces).
**Result**: 6/6 killed — PASS ✅

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code (no features beyond spec) | ✅ |
| Surgical changes; mirrors existing hexagonal layout | ✅ |
| No scope creep; ports keep provider SDKs at edges (ADR-0007/0009) | ✅ |
| Matches existing patterns/style (ingestion job machine, fetchImpl tests, requires_db) | ✅ |
| Spec-anchored outcome check (asserted values match spec) | ✅ |
| Per-layer coverage (domain 1:1 ACs; routes happy+401/404/409/422/429; repos DB-backed) | ✅ |
| Every test maps to a spec AC/edge case; no unclaimed tests | ✅ |
| Documented guidelines followed (CLAUDE.md golden fixtures, citations/eval as core; CI markers) | ✅ |

---

## Edge Cases

- [x] Deck POST on non-ready corpus → 409 (`test_web_quiz.py:232`, `test_application_quiz.py:330`)
- [x] Zero eligible sections → job succeeds with 0 items (`test_application_quiz.py:636`)
- [x] Batch per-request errors counted, successful sections persist (`test_application_quiz.py:655`, `test_quiz_anthropic.py:207`)
- [x] Batch never ends → poll deadline → job failed "timed out" (`test_worker_quiz.py:358-359`)
- [x] Due limit over max → 422 (`test_web_quiz.py:475`)
- [x] Structured-output/quote-unverified candidate discarded, counted (`test_quiz_anthropic.py:229`, `test_application_quiz.py:451`)

---

## Gate Check

| Gate | Command | Result |
| ---- | ------- | ------ |
| Backend tests | `uv run pytest -q` | **833 passed, 11 skipped**, 1 warning |
| Backend lint | `uv run ruff check .` | All checks passed |
| Frontend tests | `npx vitest run` | **174 passed** (27 files) |
| Frontend types | `npx tsc --noEmit` | exit 0 (no errors) |
| Frontend build | `npm run build` | exit 0 |

- 11 backend skips are all pre-existing marker/live-gated (live OpenAI retrieval metrics, empty-parameter generation-invariant snapshots, live-marked answerability judge) — none introduced or weakened by this cycle.
- Counts match the tasks.md expected floors moved forward (backend 833/11, frontend 174) — no test deleted or assertion weakened; suite grew by the quiz modules.

---

## Requirement Traceability Update

All requirements QUIZ-01..25 move **In Tasks → ✅ Verified**.

---

## Summary

**Overall**: ✅ Ready

**Spec-anchored check**: 25/25 ACs matched spec outcome; 0 spec-precision gaps.
**Sensor**: 6/6 mutations killed (P0-full).
**Gate**: backend 833 passed / 11 skipped + ruff clean; frontend 174 passed + tsc + build.

**What works**: The full offline path (golden EPUB → deterministic deck → grounded items + FSRS scheduling → due queue → 4-button review → summary) with zero network; the re-ingest reconciliation matrix preserving every scheduling/review-log row; ownership/CSRF/origin/rate-limit hardening on all state-changing routes; genanki `.apkg` export with stable upsert-identity GUIDs; deterministic groundedness eval with a poisoned-candidate discrimination case.

**Issues found**: none.

**Next steps**: proceed to publish/PR review. No fix tasks required; no lessons recorded (clean PASS, no grounded failure signal).
