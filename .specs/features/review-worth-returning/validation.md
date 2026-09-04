# review-worth-returning Validation

**Date**: 2026-09-04
**Spec**: `.specs/features/review-worth-returning/spec.md`
**Diff range**: `acd20b86..HEAD` (`feat/review-worth-returning`), commits `d018bee5..2a50c71f`
**Verifier**: independent sub-agent (author ≠ verifier)

**Verdict**: ✅ PASS

---

## Task Completion

| Task | Status | Notes |
| ---- | ------ | ----- |
| T1 Formulation gates | ✅ Done | `backend/app/application/quiz_qc.py` |
| T2 Anthropic rubric | ✅ Done | `backend/app/infrastructure/quiz/anthropic.py` |
| T3 Legal local fixtures | ✅ Done | `backend/app/infrastructure/quiz/local.py` |
| T4 Schema 0021 | ✅ Done | `backend/migrations/versions/0021_review_quality.py` |
| T5 Discard reasons on finalize | ✅ Done | `backend/app/application/quiz.py` |
| T6 Highlight/note generated QC | ✅ Done | `backend/app/application/cards.py` |
| T7 Compensating undo | ✅ Done | `backend/app/application/reviews.py` `UndoLastReview` |
| T8 Flag out of due | ✅ Done | `FlagCard` + `due_for_user` `flagged_at IS NULL` |
| T9 FSRS interval preview | ✅ Done | `backend/app/infrastructure/scheduling/fsrs.py` |
| T10 Session page + labels | ✅ Done | `GetDueQueue` + `DueQueueView` |
| T11 Library honesty copy | ✅ Done | `frontend/app/components/library-screen.tsx` |
| T12 Intervals, requeue, Space=Good | ✅ Done | `frontend/app/components/review-screen.tsx` |
| T13 Undo/flag/edit in review | ✅ Done | same + `frontend/app/lib/quiz.ts` |
| T14 Done-for-today / Home job | ✅ Done | `home-screen.tsx` + review done state |

No blocked or partial tasks. No `SPEC_DEVIATION` in this cycle.

---

## Spec-Anchored Acceptance Criteria

### P1: Empty-deck honesty

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| REV-01 job succeeds → persist `discard_reasons` JSON whose values sum to `discarded_count` | JSON object; `sum(values)==discarded_count` | `backend/tests/test_application_quiz.py:650-651` — `discard_reasons == {"generic_stem": 1}` and `sum(...) == discarded_count`; `:680-681` two codes; `backend/tests/test_domain_quiz.py:289-290` entity `sum == discarded_count`; `backend/tests/test_web_quiz.py:471-472` overview exposes the object | ✅ PASS |
| REV-02 each discarded candidate classified with exactly one of the 12 codes | closed vocabulary including `duplicate`/`other` | `backend/tests/test_application_quiz_qc.py:46-59` — `DISCARD_REASONS == {12 codes}`; per-code tests `:88` `== "empty"` through `:232` `== "other"`; cosine mapped as `duplicate` at `backend/tests/test_application_quiz.py:550` | ✅ PASS |
| REV-03 generated=0 discarded=0 failed=0 → library copy: no section long enough (leaf ~200+) + highlight alternative | that copy; highlight link | `frontend/tests/library-screen.test.tsx:347-352` — `/no section long enough/i`, `/200\+/`, `/leaf/i`, link `/highlight a passage/i` | ✅ PASS |
| REV-04 generated=0 discarded>0 → drafts written, none survived, including discarded count | that copy + count | `frontend/tests/library-screen.test.tsx:384-386` — `/drafts were written/i`, `/none survived/i`, `toContain("7")` | ✅ PASS |
| REV-05 generated≥1 → item/due counts; discarded>0 → quiet footnote with count | counts + muted footnote | `frontend/tests/library-screen.test.tsx:417-421` — `"2 items"`, `"1 due"`, footnote `"4"`, `className` `/muted/` | ✅ PASS |
| REV-06 failed_sections>0 and generated≥1 → mention saved count and failed-section count | saved + failed section counts | `frontend/tests/library-screen.test.tsx:451-455` — `/saved/i`, `"3"`, `/section/i`, `"1 item"` | ✅ PASS |
| REV-07 empty success stays job status `succeeded` (no new empty status) | `succeeded`; not an error surface | `backend/tests/test_application_quiz.py:631-632` — `status == SUCCEEDED` and `(0,0,0)` counts; `frontend/tests/library-screen.test.tsx:353` — `quiz-error-s1` is null on that triple | ✅ PASS |
| REV-08 discarded candidate → do not persist question/answer text | absent from `quiz_items` | `backend/tests/test_application_quiz.py:652-656` — `persisted == []` and generic-stem question not in stored questions; `:682-684` discarded stem not in `questions` | ✅ PASS |

### P1: Deterministic formulation gates

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| REV-09 generated fail → discard with that code and do not persist | reason tally; no row | `backend/tests/test_application_quiz.py:649-653` — `(0,1)` and `{"generic_stem": 1}` and `persisted == []`; highlight `backend/tests/test_application_cards.py:514` — generic stem omitted from suggestions | ✅ PASS |
| REV-10 free-recall answer substring of question → `answer_in_question` | exact code | `backend/tests/test_application_quiz_qc.py:122` — `_reason(...) == "answer_in_question"` | ✅ PASS |
| REV-11 `^(is\|are\|do\|does\|did\|can\|was\|were)\b` or binary choice → `yes_no` | exact code | `backend/tests/test_application_quiz_qc.py:127` — `"Did ..."` → `"yes_no"`; `:132` — `"yes or no?"` → `"yes_no"` | ✅ PASS |
| REV-12 cloze in EN∪PT stopwords or 1–2 letters → `cloze_stopword` | exact code | `backend/tests/test_application_quiz_qc.py:140` — `"the"` → `"cloze_stopword"`; `:146` — PT `"para"`; `:152` — `"Mg"` (2 letters) | ✅ PASS |
| REV-13 cloze >8 words or ≥60% of question words → `cloze_too_wide` | exact code | `backend/tests/test_application_quiz_qc.py:162` — 9-word answer; `:168` — 2/3 of question words | ✅ PASS |
| REV-14 free-recall answer >12 words or >120 chars → `answer_too_long` | exact code | `backend/tests/test_application_quiz_qc.py:176` — 13 words; `:181` — `"x"*121` | ✅ PASS |
| REV-15 free-recall question >280 or cloze >400 → `question_too_long` | exact code | `backend/tests/test_application_quiz_qc.py:189` — len 281; `:199` — cloze len 401 | ✅ PASS |
| REV-16 ≥4 comma/slash/semicolon items → `set_dump` | exact code | `backend/tests/test_application_quiz_qc.py:207` — three separators parametrized `== "set_dump"` | ✅ PASS |
| REV-17 free-recall matches `what does (the )?(passage\|section\|note\|text)` → `generic_stem` | exact code | `backend/tests/test_application_quiz_qc.py:222` — five stems `== "generic_stem"` | ✅ PASS |
| REV-18 grounding/empty/cloze-blank/duplicate still map to `ungrounded`/`empty`/`duplicate` | those codes | `backend/tests/test_application_quiz_qc.py:88` empty; `:97` ungrounded quote; `:104` cloze missing blank; `:117` `discard_reason != "duplicate"`; `backend/tests/test_application_quiz.py:550` finalize `{"duplicate": 1}` | ✅ PASS |
| REV-19 author-edited (`UpdateCard` / accept-after-edit) SHALL NOT apply formulation gates | 200-char answer persists; scheduling/`review_log` unchanged | `backend/tests/test_application_cards.py:995-998` — `updated.answer == long_answer`, due unchanged, `review_log == {}`; `backend/tests/test_web_cards.py:684-690` — PATCH 200, `answer == long_answer`, scheduling equal, log count equal. Accept path never calls `_passes_qc` (`backend/app/application/cards.py:240-261` validates length only) | ✅ PASS |
| REV-20 Anthropic section and quote prompts instruct the formulation bar | six rubric tokens on both helpers | `backend/tests/test_quiz_anthropic.py:476-477` and `:487-488` — each of `_RUBRIC_TOKENS` `in prompt` | ✅ PASS |
| REV-21 local adapter emits only formulation-legal candidates | `discard_reason is None`; honest empty if no legal term | `backend/tests/test_quiz_local.py:66` — every candidate `is None`; `:116-117` — stopword-only section `candidates == ()` | ✅ PASS |

### P1: Review undo as a compensating event

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| REV-22 undo restores snapshot, sets `undone_at`, does not delete the row | byte-identical scheduling; row kept with `undone_at` | `backend/tests/test_application_reviews.py:653-662` — `restored == before`, `get_scheduling == before`, `len(rows)==1`, `undone_at == _NOW+5s`; `backend/tests/test_web_quiz.py:999-1006` — same at HTTP 200 | ✅ PASS |
| REV-23 no undoable review or NULL snapshot → 409 | 409 / `QuizReviewNotUndoable` | `backend/tests/test_web_quiz.py:1018` empty 409; `:1027` second 409; `backend/tests/test_application_reviews.py:691-692` legacy NULL snapshot raises `QuizReviewNotUndoable`; `:700-701` no reviews | ✅ PASS |
| REV-24 undo only the caller's most recent not-yet-undone row | latest across items; other user's row untouched | `backend/tests/test_application_reviews.py:783-792` — second restored, first `undone_at is None`; `:804-810` intruder raises not-undoable, owner `undone_at is None`; `backend/tests/test_web_quiz.py:1041-1045` other user 409 | ✅ PASS |
| REV-25 decrement `study_days.reviews_count` for credited local day, floor 0, never INSERT | count-1 or 0; no new row | `backend/tests/test_application_reviews.py:718-720` — Tokyo local day count `== 0`; `:738` floor `== 0`; `:754` after deleting the day row `remaining == 0` | ✅ PASS |
| REV-26 `quiz_items` content columns untouched on undo | question/answer/`content_key` unchanged | `backend/tests/test_application_reviews.py:664-666` — `question`/`answer`/`content_key` equal to pre-grade | ✅ PASS |
| REV-27 missing item → 404 indistinguishable (AD-149) | `QuizItemNotFound` → 404 | `backend/tests/test_application_reviews.py:841-846` — vanished item raises `QuizItemNotFound` (mapped `error_handlers.py:97` → 404). Non-owned undo has no row → 409 per REV-23 (`:804-805`), not a leak | ✅ PASS |
| REV-28 grade stores pre-grade snapshot on the new log row | prev_* == pre-grade snapshot | `backend/tests/test_application_reviews.py:620-625` — `prev_state/step/stability/difficulty/due/last_review == before` | ✅ PASS |

### P1: Interval labels and in-session learning-step requeue

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| REV-29 due card shows bucketed labels for ratings 1–4 from non-persisted preview | four labels on buttons and wire | `frontend/tests/review-screen.test.tsx:760-763` — `~1m`/`~10m`/`~1d`/`~4d`; `backend/tests/test_web_quiz.py:626-627` each item has four buckets; `backend/tests/test_scheduling_fsrs.py:183` `set(dues) == {1,2,3,4}` | ✅ PASS |
| REV-30 preview fuzzing off; bucket exactly one of nine tokens | nine labels at documented boundaries | `backend/tests/test_scheduling_fsrs.py:210-211` fuzzy preview == exact; `:260` parametrized `interval_bucket(delta) == label`; `:265-274` `INTERVAL_LABELS` is the nine tokens | ✅ PASS |
| REV-31 new due within `LEARNY_REVIEW_REQUEUE_MINUTES` (default 15) → client inserts into remaining queue with fresh labels | ~1m reappears; ~4d does not; no pile refetch | `frontend/tests/review-screen.test.tsx:789-805` — position `2/2`, one due GET, new labels; `:822-824` 4d due → Session complete, no short-term; `backend/tests/test_config.py:293-294` default 15 | ✅ PASS |
| REV-32 while requeued cards remain, do not show Done-for-today; show short-term remaining count | no done; count copy | `frontend/tests/review-screen.test.tsx:791-794` — `Session complete` null, `/1 still in short-term review/` | ✅ PASS |
| REV-33 interval preview SHALL NOT write scheduling or `review_log` | scheduling bytes and log length unchanged | `backend/tests/test_web_quiz.py:671-675` — `get_scheduling == before`, log count `0==0`; `backend/tests/test_scheduling_fsrs.py:230-231` preview is not a `ReviewLogEntry` tuple | ✅ PASS |

### P1: Flag and edit on due cards

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| REV-34 flag sets `flagged_at`; scheduling and `review_log` untouched | `flagged_at` set; snapshot/log identical | `backend/tests/test_application_reviews.py:872-878` — `flagged_at == _NOW`, `get_scheduling == before`, log count equal; `backend/tests/test_web_quiz.py:1099-1105` HTTP | ✅ PASS |
| REV-35 while flagged, absent from due even if active and past-due | `total_due==0`, empty items | `backend/tests/test_application_reviews.py:879-881` — `total==0`, `due==[]`; `backend/tests/test_web_quiz.py:1103-1104` | ✅ PASS |
| REV-36 unflag clears `flagged_at`; due follows status+due | restored membership; stale stays out | `backend/tests/test_application_reviews.py:897-900` — `flagged_at is None`, `total==1`; `:915-919` stale unflag `total==0` and status still STALE; `backend/tests/test_web_quiz.py:1109-1112` | ✅ PASS |
| REV-37 edit from review uses content-only `UpdateCard` (id/scheduling/`review_log` unchanged) | PATCH text only | `frontend/tests/review-screen.test.tsx:1006-1022` — same position `1/1`, PATCH body `{question,answer}`, no schedule-reset URL; `backend/tests/test_application_cards.py:995-998`; `backend/tests/test_web_cards.py:686-690` | ✅ PASS |
| REV-38 missing or non-owned flag/unflag → identical 404 | both 404, same body | `backend/tests/test_web_quiz.py:1127-1129` — both 404, `non_owned.json() == missing.json()`; `backend/tests/test_application_reviews.py:931-934` `QuizItemNotFound` | ✅ PASS |
| REV-39 Anki export omits flagged cards | GUID list excludes flagged id | `backend/tests/test_export_anki.py:165-166` — `guids == [kept]`, dropped GUID `not in guids` | ✅ PASS |

### P1: Bounded today's session

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| REV-40 due response `total_due` is full overdue active unflagged count; `items` at most session size (default 20, cap 100) | 25 due → 20 items, `total_due=25`, knobs 20/15 | `backend/tests/test_web_quiz.py:622-625` — `total_due==25`, `len(items)==20`, `session_size==20`, `requeue_minutes==15`; `backend/tests/test_config.py:293` default 20; `backend/tests/test_application_reviews.py:111` cap 100 | ✅ PASS |
| REV-41 while `total_due>0`, Home presents `min(session size, total_due)` as the Reviews job, not the pile | 25 due / session 20 → UI 20, not 25 | `frontend/tests/home-screen.test.tsx:164-165` — `toContain("20")`, `not.toContain("25")` | ✅ PASS |
| REV-42 session page exhausted and `total_due>0` → Done-for-today, Keep going (next page), continue-reading link when present | those three; next page loads | `frontend/tests/review-screen.test.tsx:1059-1088` — `done-for-today`, Keep going, continue href `/sources/s1/read`, second due GET without `limit=` | ✅ PASS |
| REV-43 `total_due==0` → existing caught-up copy; no Keep going | Home due-done; Review Session complete | `frontend/tests/home-screen.test.tsx:182-187` — `due-done`, no Review CTA; `frontend/tests/review-screen.test.tsx:1108-1116` — Session complete, Keep going null, no continue fetch | ✅ PASS |
| REV-44 Space while revealed grades Good (3); Space before reveal still reveals | rating 3 vs reveal-only | `frontend/tests/review-screen.test.tsx:718` — `body.rating === 3`; `:736` — answer shown, `reviews === 0` | ✅ PASS |
| REV-45 Ctrl/Cmd+Z and `u` undo; `f` flags; `e` opens content edit | those shortcuts | `frontend/tests/review-screen.test.tsx:875-885` — `u` posts `/api/reviews/undo`; `:909-915` meta+z; `:956-966` `f` posts flag, no `/reviews`; `:989-1017` `e` then PATCH | ✅ PASS |

**Status**: ✅ All 45/45 ACs covered with `file:line` evidence. 0 spec-precision gaps.

---

## Discrimination Sensor

Scratch: `git worktree add /tmp/learny-rwr-sensor HEAD`. Real tree never mutated. Targeted tests only (not the whole suite). Restored each file before the next mutant. `git worktree remove --force` afterward. Real `git status --porcelain` empty before and after (matches pre-sensor baseline).

| Mutation | File:line | Description | Killed? |
| -------- | --------- | ----------- | ------- |
| 1 | `backend/app/application/quiz_qc.py:152` | Disabled `_GENERIC_STEM` so a generic stem returns `None` and can persist | ✅ Killed (`test_application_quiz_qc.py:222` `None == 'generic_stem'`; `test_application_quiz.py:649` `(1,0)==(0,1)` — text persisted) |
| 2 | `backend/app/application/cards.py` `UpdateCard` | Injected `discard_reason` on author PATCH (200-char answer would be `answer_too_long`) | ✅ Killed (`test_application_cards.py:995` `InvalidCardText`; `test_web_cards.py:684` not 200) |
| 3 | `backend/app/application/reviews.py:189` | Removed `update_scheduling` on undo (return value still the snapshot) | ✅ Killed (`test_application_reviews.py:654` persisted snapshot ≠ before; web `:999`) |
| 4 | `backend/app/infrastructure/db/repositories.py:1666` | Dropped `flagged_at IS NULL` from due predicate | ✅ Killed (`test_application_reviews.py:880` `total==1`; web `:1103` `total_due==1`) |
| 5 | `backend/app/application/reviews.py:93` | `GetDueQueue` used `MAX_DUE_LIMIT` when `limit` omitted | ✅ Killed (`test_web_quiz.py:623` `len(items) 25==20`; unit `:102` `100==7`) |
| 6 | `frontend/app/components/review-screen.tsx:94` | `shouldRequeue` always `false` | ✅ Killed (`review-screen.test.tsx:789` expected `2/2`, got Session complete) |
| 7 | `backend/app/infrastructure/export/anki.py:50` | Removed flagged skip in `build_apkg` | ✅ Killed (`test_export_anki.py:165` two GUIDs including flagged) |
| 8 | `backend/app/infrastructure/db/repositories.py:2323` | `decrement_reviews` called `record()` (INSERT-on-miss) first | ✅ Killed (`test_application_reviews.py:754` `remaining 1==0`) |
| 9 | `frontend/app/components/home-screen.tsx:84` | Home job = `totalDue` instead of `min(sessionSize, totalDue)` | ✅ Killed (`home-screen.test.tsx:164` copy contained `25` not `20`) |

**Sensor depth**: expanded (9 mutations; scheduling / due membership / undo)
**Result**: 9/9 killed - PASS ✅

---

## Interactive UAT Results (if performed)

Not performed in this Verifier pass. Coverage is automated (jsdom + HTTP + DB). Product UAT remains available to the orchestrator for the library/review/home surfaces.

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code | ✅ |
| Surgical changes | ✅ cycle-scoped; no MCQ/optimizer/email |
| No scope creep | ✅ AD-303..313 honored; Accept/Update stay ungated |
| Matches patterns | ✅ ports/adapters, AD-149 404 collapse, CSRF+rate-limit on new POST routes |
| Spec-anchored outcome check (asserted values match spec) | ✅ |
| Per-layer Coverage Expectation met (domain 1:1 ACs; routes happy+edge+error) | ✅ QC unit per code; undo/flag 409/404/403/401/429; due page; Anki; jsdom library/review/home |
| Every test maps to a spec requirement - no unclaimed tests | ✅ new tests map to REV-01..45 or listed edges; pre-existing tests in touched files remain QUIZ/CAP/HOME |
| Documented guidelines followed: `CLAUDE.md` (infra/pytest/vitest), `coding-principles.md` | ✅ |

Cycle `ruff check` + `ruff format --check` on cycle backend modules: clean. Full-repo `ruff format --check` not used (known unrelated drift).

---

## Edge Cases

- [x] Two tabs / later grade: undo restores the latest not-undone log row — `backend/tests/test_application_reviews.py:783-792`
- [x] Undo vs a second grade on another item: globally latest row — same test
- [x] `study_days.reviews_count` already 0: stays 0 — `:738`
- [x] continue-reading null: omit book link — `frontend/tests/review-screen.test.tsx:1143-1144`
- [x] Flagged card reconciled to stale/orphaned stays flagged and out of due; unflag does not force active — `backend/tests/test_reconcile_quiz.py:303-304`; `backend/tests/test_application_reviews.py:915-919`
- [x] Local adapter section with no legal term emits zero candidates — `backend/tests/test_quiz_local.py:116-117`
- [x] Session size 1 + requeue continues instead of Done-for-today — `frontend/tests/review-screen.test.tsx:789-791` (single-card queue, position `2/2`, no Session complete)

---

## Gate Check

- **Gate command**: cycle backend matrix modules (see `tasks.md` Test Coverage Matrix) + `cd frontend && npm test -- library-screen home-screen review-screen`; cycle `ruff check`/`ruff format --check`; `npx tsc --noEmit`
- **Result**: backend **549 passed**, 0 failed, 0 skipped; frontend **61 passed** (3 files); tsc clean; cycle ruff clean
- **Test count before feature** (changed test files at `acd20b86`): 449 backend `def test_`, 63 frontend `it(`
- **Test count after feature**: 537 backend `def test_` (+88), 86 frontend `it(` (+23). Collected backend gate 549 includes parametrize expansions
- **Delta**: +88 backend test functions, +23 frontend cases in the diff surface
- **Skipped tests**: none in the gate run
- **Failures**: none
- **Integrity**: test count increased; no skipped/weakened assertions observed in the cycle diff

---

## Fix Plans (if issues found)

None.

---

## Requirement Traceability Update

Update spec.md requirement statuses:

| Requirement | Previous Status | New Status |
| ----------- | --------------- | ---------- |
| REV-01 .. REV-45 | Done | ✅ Verified |

---

## Summary

**Overall**: ✅ Ready

**Spec-anchored check**: 45/45 ACs matched spec outcome | 0 spec-precision gaps
**Sensor**: 9/9 mutations killed
**Gate**: 549 backend + 61 frontend passed

**What works**: formulation QC (including author-path exemption), discard-reason honesty, compensating undo (snapshot, log retained, study-day UPDATE-only), flag/due/Anki/reconcile split, session page of 20 with `total_due=25`, client requeue, Home `min(session, pile)`, Done-for-today / Keep going.

**Issues found**: none.

**Next steps**: orchestrator may run interactive UAT; no fix tasks.
