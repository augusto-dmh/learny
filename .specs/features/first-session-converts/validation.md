# first-session-converts Validation

**Date**: 2026-09-04
**Spec**: `.specs/features/first-session-converts/spec.md`
**Diff range**: `main...HEAD` (`d68d672c..68d36931`)
**Verifier**: independent sub-agent (author ≠ verifier)
**UAT**: skipped (user away; ship-cycle defers browser checks)

---

## Task Completion

Re-derived from `git log main..HEAD` and the diff, not from `tasks.md` checkboxes.

| Task | Status | Notes |
| ---- | ------ | ----- |
| T1 | ✅ Done | `0022_sample_and_activation` + unique sample/activation |
| T2 | ✅ Done | `Source.is_sample` round-trip |
| T3 | ✅ Done | list union + `insert_if_absent` |
| T4 | ✅ Done | `readable_source` vs `authorized_source`; `sample_opened` |
| T5 | ✅ Done | `is_sample` + canned `suggested_question`; 401/404 |
| T6 | ✅ Done | `EnsureStarterDeck` five clones, idempotent, unique key |
| T7 | ✅ Done | `POST /quiz/starter`; non-sample 404 |
| T8 | ✅ Done | `account_created` on register |
| T9 | ✅ Done | `first_cited_answer` on shared persist |
| T10 | ✅ Done | `first_review` + idempotent seed |
| T11 | ✅ Done | Open, overflow, PDF, wait copy, empty-when-sample |
| T12 | ✅ Done | Library heading + sidebar |
| T13 | ✅ Done | Download notes |
| T14 | ✅ Done | Home Ask-first |
| T15 | ✅ Done | canned Ask highlight |
| T16 | ✅ Done | signed-out landing proof |

---

## Spec-Anchored Acceptance Criteria

Canned question used below: `What does Sun Tzu mean by “all warfare is based on deception”?`

### P1: Shared sample book

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| FS-01 at most one `is_sample=true` row | second true insert is rejected | `backend/tests/test_migrations.py:3096` - `pytest.raises(IntegrityError)` on second `is_sample=true` insert | ✅ PASS |
| FS-02 authenticated list includes sample plus own sources | two users see the same sample id plus only their own books | `backend/tests/test_repositories.py:311` - `assert sample.id in alice_ids` / `bob_ids`; `backend/tests/test_application_sources.py:491` - `{s.id for s in listed} == {sample.id, own.id}` | ✅ PASS |
| FS-03 non-owner GET/read/Ask/Teach sample is readable when ready | not 404; GET returns the sample; conversation start and chapter read succeed | `backend/tests/test_application_sources.py:436` - `assert _get_source(...)(user=reader, source_id=sample.id) == sample`; `backend/tests/test_application_conversations.py:830` - `assert started.source_id == sample.id`; `backend/tests/test_application_reading.py:311` - `assert content.chapter_anchor == "c1"`; `backend/tests/test_web_sources.py:636` - `assert got.status_code == 200` | ✅ PASS |
| FS-04 non-owner delete/re-ingest/deck-gen on sample → 404 no disclosure | 404 identical to missing; no job enqueued. No delete-source route exists (NF-09); mutate ACL is `authorized_source` | `backend/tests/test_application_ingestion.py:213` - `pytest.raises(SourceNotFound)` on `authorized_source` + `start(...)`; `backend/tests/test_web_sources.py:667` - `assert sample_resp.status_code == 404` and `sample_resp.json() == missing_resp.json()`; `backend/tests/test_web_sources.py:694` - same for `/quiz/deck` | ✅ PASS |
| FS-05 unauthenticated sample request → 401 | HTTP 401 | `backend/tests/test_web_sources.py:649` - `assert ...get(f"/api/sources/{sample.id}").status_code == 401` | ✅ PASS |
| FS-06 no per-user copy of sample corpus/embeddings | one sample source_id; list union; seed does not insert a second sample | `backend/tests/test_application_sample.py:146` - `assert listed == [sample]`; `backend/tests/test_application_sample.py:147` - `assert sources.add_calls == 1`; `backend/tests/test_repositories.py:317` - `alice_ids == {alice_book.id, sample.id}` | ✅ PASS |
| FS-07 GetSource/list sample payload | `is_sample: true` and `suggested_question` equals the canned string | `backend/tests/test_web_sources.py:632` - `assert sample_row["is_sample"] is True`; `backend/tests/test_web_sources.py:633` - `assert sample_row["suggested_question"] == _SAMPLE_QUESTION`; `backend/tests/test_web_sources.py:639` - same on GET | ✅ PASS |

### P1: Canned cited Ask and aha event

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| FS-08 sample Ask highlights canned question | highlighted control is the canned string; non-sample does not show it | `frontend/tests/ask-panel.test.tsx:1016` - `expect(highlighted.getAttribute("data-highlighted")).toBe("true")`; `frontend/tests/ask-panel.test.tsx:1028` - `queryByRole("button", { name: SAMPLE_QUESTION })` is null | ✅ PASS |
| FS-09 Ask persist answered + citations ≥ 1 inserts `first_cited_answer` if absent | one row named `first_cited_answer` | `backend/tests/test_application_conversations.py:2552` - `assert list(activations.rows) == [(user.id, ACTIVATION_FIRST_CITED_ANSWER)]` after two cited Asks | ✅ PASS |
| FS-10 failed / not-found / zero-citation Ask does not insert | no activation row | `backend/tests/test_application_conversations.py:2628` - `assert list(activations.rows) == []` after failed Ask; `:2648` not-found `answer_status != "answered"`; `:2669` zero-citation `turn.citations == ()` and rows `[]` | ✅ PASS |
| FS-11 teach persist does not insert `first_cited_answer` | no row even when answered with citations | `backend/tests/test_application_conversations.py:2575` - `assert turn.answer_status == "answered"` and `len(turn.citations) >= 1` and `list(activations.rows) == []` | ✅ PASS |
| FS-12 first insert logs INFO once; second cited Ask does not add a row | one INFO log; unique `(user_id, name)` | `backend/tests/test_application_activation.py:69` - `assert len(recorded) == 1`; `backend/tests/test_application_conversations.py:2552` - still one row after second Ask; `backend/tests/test_repositories.py:342` - `assert first is True` and `second is False` | ✅ PASS |
| FS-13 stamp from persist shared by JSON and stream, never the browser | stream completion inserts the same event; frontend has no activation client | `backend/tests/test_application_conversations.py:2690` - stream path `list(activations.rows) == [(user.id, ACTIVATION_FIRST_CITED_ANSWER)]`; persist hook at `backend/app/application/conversations.py:1079` called from `_stream_turn` `:1093`; no `first_cited_answer` in `frontend/` | ✅ PASS |

### P1: Five-card starter deck

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| FS-14 first starter POST inserts five active caller-owned items with `initial()` | len 5, origin starter, new ids, initial scheduling | `backend/tests/test_application_quiz.py:1044` - `assert len(clones) == 5` and `{c.status} == {ACTIVE}` and `all(items.scheduling[c.id] == _INITIAL ...)`; `backend/tests/test_web_quiz.py:394` - `assert resp.status_code == 200` and `len(items) == 5` | ✅ PASS |
| FS-15 second POST leaves count and scheduling unchanged | same ids; `create_scheduling_calls == 5` | `backend/tests/test_application_quiz.py:1065` - `{c.id for c in second} == {c.id for c in first}` and scheduling maps equal | ✅ PASS |
| FS-16 copy question/answer/content_key; mint new ids | disjoint ids; copied fields match templates | `backend/tests/test_application_quiz.py:1048` - `{c.id}.isdisjoint({t.id})` and question/answer/content_key sets equal templates | ✅ PASS |
| FS-17 starter on non-sample → 404 | `SourceNotFound` / HTTP 404 | `backend/tests/test_application_quiz.py:1124` - `pytest.raises(SourceNotFound)`; `backend/tests/test_web_quiz.py:409` - `assert resp.status_code == 404` | ✅ PASS |
| FS-18 grading a clone does not change template scheduling | templates stay `_GRADED`; other user's `_INITIAL` | `backend/tests/test_application_quiz.py:1078` - `assert {t.id: scheduling[t.id]} == before_templates`; `:1099` user B still `_INITIAL` | ✅ PASS |

### P1: Library honesty, naming, ingest wait

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| FS-19 ready row primary control is Open → `/sources/{id}/read` | accessible name Open; href is the read URL | `frontend/tests/sources-screen.test.tsx:290` - `getByRole("link", { name: "Open" })`; `:291` - `expect(open.getAttribute("href")).toBe("/sources/s-ready/read")` | ✅ PASS |
| FS-20 overflow Ask, Tutor, Review; Re-ingest only when not sample | those links present; sample has no Re-ingest; Teach string absent | `frontend/tests/sources-screen.test.tsx:554` - Ask/Tutor/Review hrefs; `:564` - `queryByRole("link", { name: "Teach" })` null; `:586` - sample `queryByRole("button", { name: "Re-ingest" })` null | ✅ PASS |
| FS-21 file picker accepts `.epub` and `.pdf` | accept contains both | `frontend/tests/sources-screen.test.tsx:603` - `expect(accept).toContain(".epub")` and `.pdf` | ✅ PASS |
| FS-22 while a non-sample is processing, show sample-is-ready wait copy | wait copy visible | `frontend/tests/sources-screen.test.tsx:622` - `getByText("The sample book is ready to use while you wait.")` | ✅ PASS |
| FS-23 sample in list ⇒ not “No sources yet.” | empty copy absent | `frontend/tests/sources-screen.test.tsx:637` - `expect(screen.queryByText("No sources yet.")).toBeNull()` | ✅ PASS |
| FS-24 sidebar and `/sources` heading read Library | h1 and nav label | `frontend/tests/bookshelf-page.test.tsx:73` - `expect(heading.textContent).toBe("Library")`; `frontend/tests/app-sidebar.test.tsx:80` - `labels).toEqual(["Home", "Library", "Review", "Notes"])` | ✅ PASS |
| FS-25 Chat Teach label reads Tutor | Tutor in overflow and Ask surface; Teach link gone | `frontend/tests/sources-screen.test.tsx:557` - Tutor href `?panel=teach`; `:564` Teach link null; `frontend/tests/ask-panel.test.tsx:456` - `document.body.textContent).toMatch(/Tutor/)` | ✅ PASS |
| FS-26 notes vault control reads Download notes | accessible name + export href | `frontend/tests/notes-screen.test.tsx:183` - `findByRole("link", { name: "Download notes" })`; `:184` - `href === "/api/export/vault"` | ✅ PASS |

### P1: Landing proof and Home Ask-first

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| FS-27 signed-out `/` shows cited proof above CTAs, no generation call | quote, locator, *The Art of War*, Create account; fetch unused | `frontend/tests/landing.test.tsx:56` - quote text; `:58` - `getByText("The Art of War")`; `:59` - `I. Laying Plans`; `:61` - Create account; `:63` - `expect(fetchMock).not.toHaveBeenCalled()` | ✅ PASS |
| FS-28 RegisterUser inserts `account_created` if absent | one row | `backend/tests/test_application_activation.py:42` - `assert list(activations.rows) == [(result.user.id, ACTIVATION_ACCOUNT_CREATED)]` | ✅ PASS |
| FS-29 first successful `readable_source` of sample inserts `sample_opened` | one row; second read does not add | `backend/tests/test_application_sources.py:451` - `assert activations.rows == {(reader.id, "sample_opened"): clock.now()}` after two GETs | ✅ PASS |
| FS-30 Home with `total_due = 0` and no continue offers Ask on the sample | Ask href is sample Ask URL | `frontend/tests/home-screen.test.tsx:356` - `getByRole("link", { name: "Ask" })`; `:357` - `href === "/sources/s-sample/read?panel=ask"` | ✅ PASS |
| FS-31 Home with `total_due > 0` leads with due-session card | due count + Review; no Ask | `frontend/tests/home-screen.test.tsx:377` - `due-count` contains `"5"`; `:379` Review `/review`; `:381` - `queryByRole("link", { name: "Ask" })` null | ✅ PASS |
| FS-32 first successful `SubmitReview` inserts `first_review` | one row after two grades | `backend/tests/test_application_reviews.py:275` - `assert list(activations.rows) == [(user.id, ACTIVATION_FIRST_REVIEW)]` | ✅ PASS |

**Status**: ✅ All 32 ACs covered with spec-anchored assertions

Independent-test note: FS-06 does not count `corpus_chunks.embedding` rows after a second user appears. Coverage is the shared `source_id` plus seed not inserting a second sample (embeddings are keyed by that source).

---

## Discrimination Sensor

Scratch: git worktree `/tmp/learny-fsc-sensor-SKAu8v` at HEAD. Real tree never mutated (`git stash` unused). Targeted tests only. After `git worktree remove --force`, real `git status --porcelain` matched the empty pre-sensor baseline.

| Mutation | File:line | Description | Killed? |
| -------- | --------- | ----------- | ------- |
| 1 ACL readable | `backend/app/application/ingestion.py:105` | `if source.is_sample` → `if not source.is_sample` | ✅ Killed (`test_get_source_returns_ready_sample_for_non_owner`) |
| 2 ACL authorized | `backend/app/application/ingestion.py:80` | sample bypass on `authorized_source` (treat sample as writable) | ✅ Killed (`test_authorized_source_hides_sample_from_non_owner`) |
| 3 starter uniqueness | `backend/app/application/quiz.py:478` | `content_key=template.content_key` → unique per clone | ✅ Killed (overlap count 10≠5; second-call ids changed) |
| 4 persist hook removed | `backend/app/application/conversations.py:1079` | deleted `first_cited_answer` persist block | ✅ Killed (JSON + stream cited-Ask tests) |
| 5 citations conjunct | `backend/app/application/conversations.py:1083` | `len(citations) >= 1` → `>= 0` | ⚠️ Equivalent: Ask `ground()` already collapses empty citations to not-found (AD-027), so answered Ask always has citations. `test_zero_citation_ask_does_not_insert_first_cited_answer` still passes. Not a weak persist hook. |
| 6 frontend Open CTA | `frontend/app/components/library-screen.tsx:592` | `Open` → `View` | ✅ Killed (`links a ready card through one Open`) |
| 7 frontend empty-when-sample | `frontend/app/components/library-screen.tsx:568` | show “No sources yet.” when any sample is listed | ✅ Killed (`does not show No sources yet when the sample is the only book`) |
| 8 persist mode | `backend/app/application/conversations.py:1081` | `mode == MODE_ANSWER` → `!=` | ✅ Killed (teach-answered inserts; cited Ask does not) |
| 9 persist status | `backend/app/application/conversations.py:1082` | `answer_status == ANSWERED` → `!=` | ✅ Killed (`test_cited_ask_persist_inserts_first_cited_answer_once`) |

**Sensor depth**: P0-full (≥5 behavior-level mutations: ACL read, ACL write, starter uniqueness, persist hook, persist mode/status, plus two frontend invariants)
**Result**: 8/9 killed (1 equivalent mutant) PASS

---

## Interactive UAT Results (if performed)

| # | Test | Result | Details |
| --- | ---- | ------ | ------- |
| — | Browser UAT | ⏭️ Skip | User away; ship-cycle defers browser checks |

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code | ✅ |
| Surgical changes | ✅ |
| No scope creep | ✅ seed CLI, closed activation names, no guest Ask |
| Matches patterns | ✅ ports/adapters, 404 collapse, CSRF on starter POST |
| Spec-anchored outcome check (asserted values match spec) | ✅ |
| Per-layer Coverage Expectation met (domain 1:1 ACs; routes happy+edge+error) | ✅ starter 200/404/401/403; sample GET 200/401; mutate 404 |
| Every test maps to a spec requirement - no unclaimed tests | ✅ extra CSRF/origin/seed tests map to auth and seed assumptions |
| Documented guidelines followed: `CLAUDE.md` (local providers, infra, pytest/vitest) | ✅ |

Would a senior engineer approve? Yes. `ListQuizItems` stays owner-only (`authorized_source`); learners review via cloned items and global due, which matches starter ownership.

---

## Edge Cases

- [x] Overlapping `EnsureStarterDeck`: unique `(user_id, source_id, content_key)` — `backend/tests/test_migrations.py:3244` indexdef includes `origin = 'starter'`; `backend/tests/test_repositories_quiz.py:1788` second upsert `is False`; unit overlap `backend/tests/test_application_quiz.py:1115` `len(starters) == 5`
- [x] Sample not `ready` → Ask/Teach 409: shared `SourceNotReady` after `readable_source` (`backend/tests/test_application_conversations.py:839`). Starter POST has no ready guard (templates do not need corpus). Library status badge is generic (`frontend/tests/sources-screen.test.tsx:277`)
- [x] Seed enqueue failure does not mark ready: `backend/tests/test_application_sample.py:116` - `sample.status == SOURCE_STATUS_FAILED` and `!= "ready"`; storage failure leaves no sample row `:126`
- [x] Client-sent activation name ignored: no activation HTTP route; `backend/tests/test_application_activation.py:77` - `pytest.raises(ValueError, match="unknown activation name")`
- [x] Operator login fails like unknown password: seed inserts email with no credential (`backend/tests/test_application_sample.py:161`); `AuthenticateUser` uses dummy hash when credential is missing (`backend/app/application/identity.py:165`). No dedicated `SAMPLE_OPERATOR_EMAIL` login test; covered by uniform `InvalidCredentials` path (`backend/tests/test_application_identity.py:119`)

---

## Gate Check

- **Gate command**: `make lint` plus cycle backend suites (matrix files + diff-touched application/web/repo tests) and cycle frontend files (`library-screen`, `app-shell`, `notes-screen`, `home-screen`, `ask-panel`, `landing`, `sources-screen`, `bookshelf-page`, `app-sidebar`)
- **Lint**: pass (`ruff check` + `ruff format --check`, `tsc --noEmit`, architecture boundaries clean)
- **Result**: backend 708 passed when `test_migrations.py` is isolated (30/30); mixing that module with other DB tests in one session dropped schema and produced 18 spurious migration failures (deadlocks / missing relations). Other 678 backend tests in that session passed. Frontend 127 passed, 0 failed.
- **Test count before feature**: not re-collected on `main`
- **Test count after feature**: diff adds 51 `def test_` and 13 vitest `it(`; four old names removed and replaced (bookshelf→Library, Export vault→Download notes, Ask/Teach/Read primary links→Open, origins set +`starter`)
- **Delta**: +51 pytest / +13 vitest; replacements are naming/CTA updates, not weakened assertions
- **Skipped tests**: none in the passing gate runs
- **Failures**: none after isolating migrations

---

## Fix Plans (if issues found)

None. Mutation 5 is an equivalent mutant under AD-027, not a missing assertion on the persist hook (mutations 4, 8, and 9 killed that hook).

---

## Requirement Traceability Update

`spec.md` left unchanged (verifier writes only this report). Verifier statuses:

| Requirement | Previous Status | New Status |
| ----------- | --------------- | ---------- |
| FS-01 … FS-32 | Implemented | ✅ Verified |

---

## Summary

**Overall**: ✅ Ready

**Spec-anchored check**: 32/32 ACs matched spec outcome, 0 spec-precision gaps
**Sensor**: 8/9 killed (1 equivalent)
**Gate**: lint pass; 708 backend + 127 frontend passed

**What works**: shared sample ACL (`readable_source` vs `authorized_source`), canned Ask + persist-hook aha, per-user starter uniqueness, library Open/overflow/wait copy, Library/Tutor/Download notes, landing proof, Home Ask-first, activation events.

**Issues found**: none that block ship. Equivalent mutant on `citations >= 1` is implied by Ask grounding.

**Next steps**: none from this verifier.
