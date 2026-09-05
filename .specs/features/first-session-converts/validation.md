# first-session-converts Validation

**Date**: 2026-09-04
**Spec**: `.specs/features/first-session-converts/spec.md`
**Diff range**: `57dcc4c8..5d358187` (`feat/first-session-converts`)
**Verifier**: independent sub-agent (author ≠ verifier), re-verification iteration 1 of 3
**Verdict**: PASS

---

## Task Completion

All T1–T16 Done-when boxes in `tasks.md` are checked. Implementation commits `b9678377`…`94e7bc62` match the task subjects. Fix commits after iteration 0: `ad72b870` (unreadied sample Ask/Teach), `5d358187` (landing proof order).

| Task | Status | Notes |
| ---- | ------ | ----- |
| T1 | ✅ Done | `0022` sample flag + activation unique pair |
| T2 | ✅ Done | `Source.is_sample` round-trip |
| T3 | ✅ Done | list union + `insert_if_absent` |
| T4 | ✅ Done | `readable_source` vs `authorized_source`; `sample_opened` |
| T5 | ✅ Done | canned `suggested_question`; 401/404 |
| T6 | ✅ Done | five clones, idempotent, unique key |
| T7 | ✅ Done | `POST /quiz/starter`; non-sample 404 |
| T8 | ✅ Done | `account_created` on register |
| T9 | ✅ Done | `first_cited_answer` on shared persist |
| T10 | ✅ Done | `first_review` + idempotent seed |
| T11 | ✅ Done | Open, overflow, PDF, wait copy |
| T12 | ✅ Done | Library heading + sidebar |
| T13 | ✅ Done | Download notes |
| T14 | ✅ Done | Home Ask-first |
| T15 | ✅ Done | canned Ask highlight |
| T16 | ✅ Done | signed-out landing proof above CTAs |

---

## Spec-Anchored Acceptance Criteria

Canned question: `What does Sun Tzu mean by “all warfare is based on deception”?`

### P1: Shared sample book

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| FS-01 at most one `is_sample=true` row | second true insert rejected | `backend/tests/test_migrations.py:3096` - `pytest.raises(IntegrityError)` on second `is_sample=true` insert | ✅ PASS |
| FS-02 authenticated list includes sample plus own sources | same sample id for two users, plus only their own books | `backend/tests/test_repositories.py:311` - `assert sample.id in alice_ids`; `:317` - `alice_ids == {alice_book.id, sample.id}`; `backend/tests/test_application_sources.py:491` - `{s.id for s in listed} == {sample.id, own.id}` | ✅ PASS |
| FS-03 non-owner GET/read/Ask/Teach sample is readable when ready | not 404; GET returns sample; start + chapter succeed | `backend/tests/test_application_sources.py:436` - `assert _get_source(...)(user=reader, source_id=sample.id) == sample`; `backend/tests/test_application_conversations.py:830` - `assert started.source_id == sample.id`; `backend/tests/test_application_reading.py:311` - `assert content.chapter_anchor == "c1"`; `backend/tests/test_web_sources.py:636` - `assert got.status_code == 200` | ✅ PASS |
| FS-04 non-owner delete/re-ingest/deck-gen → 404 no disclosure | 404 identical to missing; no job. No delete-source route exists | `backend/tests/test_application_ingestion.py:213` - `pytest.raises(SourceNotFound)` on `authorized_source` + `start`; `backend/tests/test_web_sources.py:667` - `sample_resp.status_code == 404` and `sample_resp.json() == missing_resp.json()`; `:694` same for `/quiz/deck` | ✅ PASS |
| FS-05 unauthenticated sample request → 401 | HTTP 401 | `backend/tests/test_web_sources.py:649` - `assert ...get(f"/api/sources/{sample.id}").status_code == 401` | ✅ PASS |
| FS-06 no per-user copy of sample corpus/embeddings | one shared `source_id`; seed does not insert a second sample. `corpus_chunks` has no `user_id` | `backend/tests/test_application_sample.py:146` - `assert listed == [sample]`; `:147` - `assert sources.add_calls == 1`; `backend/tests/test_repositories.py:317` shared id. Embedding-row count is structural (chunks keyed by source, not user) | ✅ PASS |
| FS-07 GetSource/list sample payload | `is_sample: true` and canned `suggested_question` | `backend/tests/test_web_sources.py:632` - `assert sample_row["is_sample"] is True`; `:633` - `assert sample_row["suggested_question"] == _SAMPLE_QUESTION`; `:639` same on GET | ✅ PASS |

### P1: Canned cited Ask and aha event

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| FS-08 sample Ask highlights canned question | highlighted control is the canned string; non-sample does not show it | `frontend/tests/ask-panel.test.tsx:1016` - `expect(highlighted.getAttribute("data-highlighted")).toBe("true")`; `:1028` - `queryByRole("button", { name: SAMPLE_QUESTION })` is null | ✅ PASS |
| FS-09 Ask persist answered + citations ≥ 1 inserts `first_cited_answer` if absent | one row named `first_cited_answer` | `backend/tests/test_application_conversations.py:2573` - `assert list(activations.rows) == [(user.id, ACTIVATION_FIRST_CITED_ANSWER)]` after two cited Asks | ✅ PASS |
| FS-10 failed / not-found / zero-citation Ask does not insert | no activation row | `backend/tests/test_application_conversations.py:2649` - failed Ask `rows == []`; `:2669` not-found `answer_status != "answered"`; `:2691` `turn.citations == ()` and `rows == []` | ✅ PASS |
| FS-11 teach persist does not insert `first_cited_answer` | no row even when answered with citations | `backend/tests/test_application_conversations.py:2596` - `answer_status == "answered"` and `len(turn.citations) >= 1` and `rows == []` | ✅ PASS |
| FS-12 first insert logs INFO once; second cited Ask does not add a row | one INFO log; unique `(user_id, name)` | `backend/tests/test_application_activation.py:69` - `assert len(recorded) == 1`; `backend/tests/test_application_conversations.py:2573` still one row; `backend/tests/test_repositories.py:342` - `first is True` and `second is False` | ✅ PASS |
| FS-13 stamp from persist shared by JSON and stream, never the browser | stream uses `_persist`; no client event name | `backend/tests/test_application_conversations.py:2711` - stream `rows == [(user.id, ACTIVATION_FIRST_CITED_ANSWER)]`; hook `backend/app/application/conversations.py:1079` called from `_stream_turn` `:1093` | ✅ PASS |

### P1: Five-card starter deck

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| FS-14 first starter POST inserts five active caller-owned items with `initial()` | len 5, starter origin, new ids, initial scheduling | `backend/tests/test_application_quiz.py:1044` - `len(clones) == 5`, `{c.status} == {ACTIVE}`, `all(...scheduling[c.id] == _INITIAL)`; `backend/tests/test_web_quiz.py:394` - `status_code == 200` and `len(items) == 5` | ✅ PASS |
| FS-15 second POST leaves count and scheduling unchanged | same ids; no extra `create_scheduling` | `backend/tests/test_application_quiz.py:1065` - id sets equal and scheduling maps equal; `:1068` - `create_scheduling_calls == 5` | ✅ PASS |
| FS-16 copy question/answer/content_key; mint new ids | disjoint ids; copied fields match templates | `backend/tests/test_application_quiz.py:1048` - `{c.id}.isdisjoint({t.id})` and question/answer/content_key sets equal templates | ✅ PASS |
| FS-17 starter on non-sample → 404 | `SourceNotFound` / HTTP 404 | `backend/tests/test_application_quiz.py:1124` - `pytest.raises(SourceNotFound)`; `backend/tests/test_web_quiz.py:409` - `status_code == 404` | ✅ PASS |
| FS-18 grading a clone does not change template scheduling | templates unchanged; other user still initial | `backend/tests/test_application_quiz.py:1079` - template scheduling `== before_templates`; `:1099` other learner `_INITIAL` | ✅ PASS |

### P1: Library honesty, naming, ingest wait

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| FS-19 ready row primary control is Open → `/sources/{id}/read` | name Open; href is the read URL | `frontend/tests/sources-screen.test.tsx:290` - `getByRole("link", { name: "Open" })`; `:291` - `href === "/sources/s-ready/read"` | ✅ PASS |
| FS-20 overflow Ask, Tutor, Review; Re-ingest only when not sample | those links; sample has no Re-ingest; Teach link absent | `frontend/tests/sources-screen.test.tsx:554` Ask/Tutor/Review hrefs; `:564` Teach link null; `:586` sample Re-ingest null | ✅ PASS |
| FS-21 file picker accepts `.epub` and `.pdf` | accept contains both | `frontend/tests/sources-screen.test.tsx:603` - `toContain(".epub")` and `.pdf` | ✅ PASS |
| FS-22 while a non-sample is processing, show sample-ready wait copy | wait copy visible | `frontend/tests/sources-screen.test.tsx:622` - `getByText("The sample book is ready to use while you wait.")` | ✅ PASS |
| FS-23 sample in list ⇒ not “No sources yet.” | empty copy absent | `frontend/tests/sources-screen.test.tsx:637` - `queryByText("No sources yet.")` is null | ✅ PASS |
| FS-24 sidebar and `/sources` heading read Library | h1 and nav label | `frontend/tests/bookshelf-page.test.tsx:73` - `heading.textContent === "Library"`; `frontend/tests/app-sidebar.test.tsx:80` - `["Home", "Library", "Review", "Notes"]` | ✅ PASS |
| FS-25 Chat Teach label reads Tutor | Tutor present; Teach link gone | `frontend/tests/sources-screen.test.tsx:557` Tutor `?panel=teach`; `:564` Teach null; `frontend/tests/ask-panel.test.tsx:456` - body matches `/Tutor/` | ✅ PASS |
| FS-26 notes vault control reads Download notes | accessible name + export href | `frontend/tests/notes-screen.test.tsx:183` - `name: "Download notes"`; `:184` - `href === "/api/export/vault"` | ✅ PASS |

### P1: Landing proof and Home Ask-first

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| FS-27 signed-out `/` shows cited proof above Create account and Log in, no generation call | quote, locator, *The Art of War* appear before the account CTAs; no fetch | `frontend/tests/landing.test.tsx:55` quote; `:59` title; `:60` `I. Laying Plans`; `:62` `proof.compareDocumentPosition(createAccount) & DOCUMENT_POSITION_FOLLOWING`; `:66` same for Log in; `:68` `fetchMock` not called | ✅ PASS |
| FS-28 RegisterUser inserts `account_created` if absent | one row | `backend/tests/test_application_activation.py:42` - `rows == [(result.user.id, ACTIVATION_ACCOUNT_CREATED)]` | ✅ PASS |
| FS-29 first successful `readable_source` of sample inserts `sample_opened` | one row after two reads | `backend/tests/test_application_sources.py:451` - `activations.rows == {(reader.id, "sample_opened"): clock.now()}` | ✅ PASS |
| FS-30 Home with `total_due = 0` and no continue offers Ask on the sample | Ask href is sample Ask URL | `frontend/tests/home-screen.test.tsx:356` Ask link; `:357` - `href === "/sources/s-sample/read?panel=ask"` | ✅ PASS |
| FS-31 Home with `total_due > 0` leads with due-session card | due count + Review; no Ask | `frontend/tests/home-screen.test.tsx:377` due-count contains `"5"`; `:379` Review `/review`; `:381` Ask null | ✅ PASS |
| FS-32 first successful `SubmitReview` inserts `first_review` | one row after two grades | `backend/tests/test_application_reviews.py:275` - `rows == [(user.id, ACTIVATION_FIRST_REVIEW)]` | ✅ PASS |

**Status**: ✅ All ACs covered (32/32 matched spec outcome, 0 spec-precision gaps)

---

## Discrimination Sensor

Scratch: `git worktree add /tmp/learny-fsc-sensor-r2 HEAD`. Real tree not mutated (`git stash` unused). Pre-sensor porcelain: ` M .specs/features/first-session-converts/validation.md`. After `git worktree remove --force`, real porcelain is unchanged aside from this report.

P0-full: onboarding ACL, activation persist hook, starter gate, seed compensation, Home weighting, library overflow/wait copy, plus the two iteration-0 survivors.

| Mutation | File:line | Description | Killed? |
| -------- | --------- | ----------- | ------- |
| 1 | `backend/app/application/conversations.py:224` | Skip `SourceNotReady` when `source.is_sample` on start | ✅ Killed (`test_start_on_an_unreadied_sample_raises_source_not_ready` DID NOT RAISE) |
| 2 | `frontend/app/page.tsx:25-46` | Moved proof `<figure>` below Create account / Log in | ✅ Killed (`landing.test.tsx` `compareDocumentPosition` → 0) |
| 3 | `backend/app/application/ingestion.py:105` | Flipped `if source.is_sample` → `if not source.is_sample` | ✅ Killed (`test_get_source_returns_ready_sample_for_non_owner`, `test_get_source_stamps_sample_opened_once`) |
| 4 | `backend/app/application/conversations.py:1083` | Raised citation gate `>= 1` → `>= 2` | ✅ Killed (JSON + stream `first_cited_answer` tests) |
| 5 | `backend/app/application/quiz.py:456` | Inverted `if not source.is_sample` so sample starter 404s | ✅ Killed (`test_ensure_starter_inserts_five_...`, `test_ensure_starter_rejects_a_non_sample_source`) |
| 6 | `backend/app/application/sample.py:192` | Enqueue-failure compensation marks sample `"ready"` | ✅ Killed (`test_enqueue_failure_leaves_no_ready_sample` `status == 'ready'` vs `'failed'`) |
| 7 | `frontend/app/components/home-screen.tsx:130` | `totalDue === 0` → `!== 0` | ✅ Killed (Ask-first + due-session tests) |
| 8 | `frontend/app/components/library-screen.tsx:357` | Sample overflow shows Re-ingest | ✅ Killed (`hides Re-ingest on the sample row overflow`) |
| 9 | `backend/app/application/conversations.py:1081` | Dropped `mode == MODE_ANSWER` so cited Teach stamps aha | ✅ Killed (`test_teach_answered_does_not_insert_first_cited_answer_even_with_citations`) |
| 10 | `frontend/app/components/library-screen.tsx:557` | Wait copy requires every source to be the sample | ✅ Killed (`points waiters at the sample while a non-sample book is processing`) |

**Sensor depth**: P0-full (10 behavior-level mutations)
**Result**: 10/10 killed - PASS

---

## Interactive UAT Results (if performed)

| # | Test | Result | Details |
| --- | ---- | ------ | ------- |
| — | Browser UAT | ⏭️ Skip | Operator is away; ship-cycle defers human/browser checks |

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code | ✅ |
| Surgical changes | ✅ |
| No scope creep | ✅ no guest Ask, closed activation names, seed is CLI not boot |
| Matches patterns | ✅ ports/adapters, 404 collapse, CSRF on starter POST |
| Spec-anchored outcome check (asserted values match spec) | ✅ including FS-27 document order |
| Per-layer Coverage Expectation met (domain 1:1 ACs; routes happy+edge+error) | ✅ unreadied sample start now has a sample-identity test |
| Every test maps to a spec requirement - no unclaimed tests | ✅ extra CSRF/origin tests map to auth assumptions |
| Documented guidelines followed: `CLAUDE.md` (local providers, infra, pytest/vitest) | ✅ |

Would a senior engineer approve? Yes. The two iteration-0 survivors are now discriminating.

---

## Edge Cases

- [x] Overlapping `EnsureStarterDeck` ends at five clones: `backend/tests/test_migrations.py:3244` indexdef includes `origin = 'starter'`; `backend/tests/test_application_quiz.py:1115` `len(starters) == 5`
- [x] Sample not `ready` → Ask/Teach 409: `backend/tests/test_application_conversations.py:846` - `pytest.raises(SourceNotReady)` for non-owner `is_sample=True` `status="processing"` and no conversation row. Library status badge is generic (`frontend/tests/sources-screen.test.tsx:277`)
- [x] Seed enqueue failure does not mark ready: `backend/tests/test_application_sample.py:116` `status == SOURCE_STATUS_FAILED` and `!= "ready"`
- [x] Client-sent activation name ignored: no activation HTTP route; `backend/tests/test_application_activation.py:77` unknown name `ValueError`
- [x] Operator login fails like unknown password: seed inserts email with no credential (`backend/tests/test_application_sample.py:161`); `AuthenticateUser` dummy-hash path (`backend/app/application/identity.py:165`). Same `InvalidCredentials` as unknown email (`backend/tests/test_application_identity.py:119`)

---

## Gate Check

- **Gate command**: `make lint` plus matrix suites (`test_migrations.py` isolated, then remaining backend matrix files in one process; frontend `library-screen app-shell notes-screen home-screen ask-panel landing sources-screen bookshelf-page app-sidebar`)
- **Lint**: pass (`ruff check`, `ruff format --check`, `tsc --noEmit`, architecture boundaries clean)
- **Result**: 485 passed, 0 failed, 0 skipped (backend matrix 358 = migrations 30 + remainder 328; frontend 127)
- **Test count before feature** (matrix files at merge-base `57dcc4c8`): 307 pytest `def test_` + 117 vitest `it(`
- **Test count after feature**: 348 pytest + 127 vitest
- **Delta**: +41 pytest / +10 vitest on the matrix files; no net deletion. Iteration-0 remainder was 327; +1 is `test_start_on_an_unreadied_sample_raises_source_not_ready`
- **Skipped tests**: none in the passing gate runs
- **Failures**: none

---

## Fix Plans (if issues found)

None. Iteration-0 ranked gaps are closed:

1. Unreadied sample Ask/Teach 409 is discriminating (`ad72b870`).
2. Landing proof-above-CTAs asserts document order (`5d358187`).

---

## Requirement Traceability Update

Update spec.md requirement statuses:

| Requirement | Previous Status | New Status |
| ----------- | --------------- | ---------- |
| FS-01 … FS-32 | Implemented | ✅ Verified |

---

## Summary

**Overall**: ✅ Ready

**Spec-anchored check**: 32/32 ACs matched spec outcome | 0 spec-precision gaps
**Sensor**: 10/10 mutations killed
**Gate**: 485 passed (358 backend matrix + 127 frontend), 0 failed

**What works**: shared sample ACL including unreadied 409, canned Ask + persist-hook aha, per-user starter uniqueness, library Open/overflow/wait copy, Library/Tutor/Download notes, Home Ask-first, activation events, seed enqueue compensation, landing proof above the account CTAs.

**Issues found**: none

**Next steps**: none. Feature is ready for finalize.
