# section-checkpoint-and-calibration verification

**Verdict**: FAIL
**Profile**: standard
**Diff range**: 2281250..e2c55e2 (feature base after the rebase onto `main`; round-1 range d43402b..47d200e, where old 47d200e is new bed7114)
**Round**: 2 - scoped
**Verifier**: independent sub-agent (author != verifier)

Batch scope: C1–C32 and C42. C33–C41 are batch 2 and out of scope for this round. They are verified before that batch's PR.

The fix closes 9 of the 10 ranked round-1 gaps. All four round-1 survivors (F1–F4) are now killed, and so is every mutant aimed at a new assertion, at `extra="forbid"` and at the migration renumber. The round fails on two narrow points that the fix did not reach. First, C19's "first feedback citation" clause is still not discriminated: the minting test has a single citation, and `quoted[-1]` survives (M15). Second, the `checkpoint-dialog.tsx` Test policy row is still unmet: the post-"Just explain" passage state has no test, and dropping the passage survives the whole dialog file (M16). Round 1 flagged this row; the fix did not touch it.

Fix scope reviewed: `git diff bed7114..e2c55e2` (tests in 4 files, `GradeRequest` `extra="forbid"`, checks.md proof additions), plus the rebase changes to `c102e08` (`git range-diff d43402b..47d200e 2281250..bed7114`). The rebase only renamed the revision (`0030_section_checkpoints` → `0031_section_checkpoints`, `down_revision` `0030_user_provider_credentials`, `backend/migrations/versions/0031_section_checkpoints.py:34-35`), merged `metadata.py` with `user_provider_credentials`, and updated `test_migrations.py`. Commits `4827953` and `bed7114` are byte-identical to round 1's `1632c51` and `47d200e`.

## Binding sources

Carried from 47d200e. Step 1 (`ui`) does not run under `standard`. The binding sources (the ROADMAP v8 row and research synthesis row #6 with its do-not-build list) set scope and non-goals, not a UI design. The fix touched no screen. The one interface change, the grade route refusing extra fields, sits inside door 2's rejection of a client-sent `assisted`. No contradiction.

## Checks

Verified at e2c55e2. Every proof was re-run in full at `HEAD`.

Backend, one invocation: `cd backend && LEARNY_REQUIRE_DB=1 LEARNY_TEST_DATABASE_URL=…/learny_test_checkpoint uv run pytest tests/test_application_checkpoints.py tests/test_web_checkpoints.py tests/test_repositories_checkpoints.py tests/test_application_reviews.py tests/test_migrations.py -v -k "<all 37 batch-1 names>"`. Result: 49 passed, 77 deselected, exit 0. Every name appears individually, parametrized cases included. That covers the new `create_validation_422[body0-2]`, `recall_grade_rating_bounds[4-200,5-422]` and `grade_refuses_a_client_assisted_field`.

Frontend, one invocation: `cd frontend && npx vitest run tests/chapter-reader.test.tsx tests/checkpoint-dialog.test.tsx --reporter=verbose -t "<11 names>"`. Result: 18 passed, 74 skipped, exit 0. Every name appears, including the new `self-assessment Missed it/Partly/Got it grades the explanation 1/2/3`, `confidence Not sure/Fairly sure/Sure is sent as 1/2/3 with the response` and `starts the checkpoint for the section whose invitation was tapped`.

| Check | Claim | Proof run | Evidence | Result |
| --- | --- | --- | --- | --- |
| C1 | one invite, only after the ≥150-word section, placed after its body | vitest `checkpoint invitation only after sections of at least 150 words` passed | `frontend/tests/chapter-reader.test.tsx:2239` - `expect(invites).toHaveLength(1)`; `:2242` - `expect(longSection.nextElementSibling).toBe(invites[0])` | PASS |
| C2 | the tap opens the dialog on the prediction step for that section's anchor; no request before a choice | vitest `opens on the prediction step without calling the API` and `starts the checkpoint for the section whose invitation was tapped` passed | `frontend/tests/checkpoint-dialog.test.tsx:115` - `expect(fetchMock).not.toHaveBeenCalled()`; `frontend/tests/chapter-reader.test.tsx:2293` - two invites; `:2299` - `dialog.textContent).toContain("The Analytical Engine")`; `:2302` - `expect(started).toEqual([{ anchor: S2, prediction: null }])` (the second section's anchor; M13 killed) | PASS |
| C3 | closing mid-flow unmounts, chapter intact, no further request | vitest `closing mid-flow sends nothing more` passed | `frontend/tests/checkpoint-dialog.test.tsx:320` - `expect(onClose).toHaveBeenCalledTimes(1)`; `:321` - `expect(fetchMock).toHaveBeenCalledTimes(1)`; unmount at `frontend/tests/chapter-reader.test.tsx:2256` | PASS |
| C4 | Little/Some/Most/Skip → 1/2/3/null | vitest `prediction choices map to 1, 2, 3 and null` (4 cases) passed | `frontend/tests/checkpoint-dialog.test.tsx:139` - `expect(bodies).toEqual([{ anchor: "ch1#s1", prediction: expected }])` | PASS |
| C5 | ≤3 owned, active, unflagged, non-checkpoint cards on the anchor, due asc then id, then one explain; stale/flagged/other-anchor/other-learner excluded | pytest `start_selects_due_first_owned_active_cards_on_anchor`, `start_caps_recall_attempts_at_three` passed | `backend/tests/test_application_checkpoints.py:179` - the stranger's card on the **same** source and anchor, due soonest; `:184` - `assert kinds == [(RECALL, sooner.id), (RECALL, later.id), (EXPLAIN, None)]`; `:207` - `recalls == [cards[4].id, cards[3].id, cards[2].id]` (F1/M1 killed) | PASS |
| C6 | no eligible cards → exactly one explain attempt | pytest `start_without_cards_has_only_explain` passed | `backend/tests/test_application_checkpoints.py:217` - `[a.kind …] == [CheckpointAttemptKind.EXPLAIN]` | PASS |
| C7 | the create payload has no answer/excerpt/passage keys or text | pytest `create_payload_carries_no_answers` passed | `backend/tests/test_web_checkpoints.py:91` - `"A distinctive secret answer" not in raw`; `:96` - `assert key not in json.dumps(body)`; `:99` - attempt keys `{attempt_id, kind, question}` | PASS |
| C8 | 404 with nothing persisted for missing/foreign/no-section; sample → 201; prediction 0/4 or empty anchor → 422 with nothing persisted | pytest `create_404_cases_persist_nothing`, `create_on_shared_sample_returns_201`, `create_validation_422` [3] passed | `backend/tests/test_web_checkpoints.py:113` - `== [404, 404, 404]`; `:115` - count unchanged; `:126` - `== 201`; `:429` - `resp.status_code == 422`; `:430` - `_checkpoint_count(db_conn) == before` (M9, M10 killed) | PASS |
| C9 | recall response stores response and confidence=2, returns answer/excerpt/anchor/path; an empty response is accepted | pytest `recall_response_reveals_answer_after_storing` passed | `backend/tests/test_web_checkpoints.py:178` - `resp.json() == {"answer": …, "source_excerpt": …, "anchor": ANCHOR, "section_path": …}`; `:189` - `tuple(stored) == ("", 2)` | PASS |
| C10 | second response 409, first kept | pytest `second_response_is_409_and_keeps_first` passed | `backend/tests/test_web_checkpoints.py:203` - `== 409`; `:209` - `tuple(stored) == ("one", 1)` | PASS |
| C11 | no confidence / 0 / 4 / 4001 chars → 422, responded_at NULL | pytest `response_validation_422` [4] passed | `backend/tests/test_web_checkpoints.py:228` - `== 422`; `:234` - `responded is None` | PASS |
| C12 | response/reveal/grade on a foreign attempt and on a random uuid return identical 404 bodies | pytest `attempt_routes_404_for_foreign_and_missing` passed | `backend/tests/test_web_checkpoints.py:255` - `== [404, 404, 404]` per id; `:259` - `[len(texts) for texts in bodies.values()] == [1, 1, 1]`, with the bodies collected per route across two foreign ids and one missing id (F2/M2 killed: `[2, 2, 2] == [1, 1, 1]`) | PASS |
| C42 | the four POSTs return 401 without a session and 403 without CSRF, and write nothing | pytest `new_routes_require_session_and_csrf` passed | `backend/tests/test_web_checkpoints.py:154` - `== [403, 403, 403, 403]`; `:155` - `== [401, 401, 401, 401]`; `:156` - count unchanged; `:162` - `[tuple(s) for s in stamps] == [(None, None), (None, None)]`, now read on both the recall attempt and the explain attempt the reveal was posted to (M11 killed) | PASS |
| C13 | recall shows the question and no answer; the answer appears only after the confidence submit resolves | vitest `recall answer appears only after a confidence submit resolves` passed | `frontend/tests/checkpoint-dialog.test.tsx:159` - `queryByText(SECRET)).toBeNull()`; `:166` - still null in flight; `:177` - `findByText(SECRET)` | PASS |
| C14 | recall grade 1: FSRS advance, one log row (1, confidence, assisted=false), review_log_id linked, study day +1 | pytest `grade_recall_reviews_card_with_confidence_unassisted` passed | `backend/tests/test_application_checkpoints.py:236` - `items.get_scheduling(card.id) == expected`; `:238` - `== [(1, 2, False)]`; `:245` - `linked == log_id`; `:251` - `reviews == 1` | PASS |
| C15 | grade before response → 409, no log row | pytest `grade_before_response_is_409` passed | `backend/tests/test_web_checkpoints.py:277` - `== 409`; `:278` - `_log_count(db_conn) == before` | PASS |
| C16 | a sequential double grade leaves one row; the second returns 409 | pytest `second_grade_is_409_one_log_row` passed | `backend/tests/test_web_checkpoints.py:290` - `== 200`; `:292` - `== 409`; `:296` - `[r.rating for r in rows] == [3]` | PASS |
| C17 | concurrent claims on separate connections have one winner | pytest `concurrent_grade_claim_has_one_winner` passed | `backend/tests/test_repositories_checkpoints.py:77` - `(won_first, won_second) == (True, False)` | PASS |
| C18 | explain 1/2/3 reviews the checkpoint card (minting it); explain 4 or 0 → 422; recall accepts 4 and refuses 5 with 422 and no log row | pytest `grade_explain_mints_and_reviews_checkpoint_card` [3], `explain_grade_rating_bounds` [4], `recall_grade_rating_bounds` [2] passed | `backend/tests/test_application_checkpoints.py:275-276`; `backend/tests/test_web_checkpoints.py:310-311`; `:444` - `resp.status_code == expected` (4→200, 5→422); `:448` - `[r.rating for r in rows] == ([rating] if expected == 200 else [])` (M7, M8 killed) | PASS |
| C19 | minted card shape and owner on the sample; answer = the **first** feedback citation's quote, cut, else the first chunk; scheduled `initial()` before review | pytest `minted_card_shape_and_owner_on_sample`, `minted_card_falls_back_to_first_chunk` passed | `backend/tests/test_application_checkpoints.py:301-306` owner/origin/type/question/anchor/path; `:307` - `card.answer == CHUNKS[2][:_MAX_CARD_CHARS]` (chunks are 77–91 chars, cut at 40, so the cut is discriminated); `:321` - `tuple(prev) == (fresh.state, fresh.step, fresh.stability, fresh.difficulty, None)` (M6 killed: `(1, 1, 2.30…) != (1, 0, None, None, None)`); `:338` - fallback. **The provider cites exactly one chunk (`:287-291`), so "first" is not discriminated: `quoted[0]` → `quoted[-1]` at `backend/app/application/checkpoints.py:554` survives both proofs (M15)** | FAIL ("first feedback citation" unproven) |
| C20 | an existing checkpoint card is reused, count stays 1, text unchanged | pytest `second_checkpoint_reuses_existing_card` passed | `backend/tests/test_application_checkpoints.py:348` - same `quiz_item_id`; `:354` - `count == 1`; `:356` - text unchanged; `:357` - `== [1, 3]` | PASS |
| C21 | one answer-mode call, evidence capped at 6, fewest-shared-words first, citations = grounded | pytest `explain_calls_answer_mode_once_least_covered_first`, `explain_drops_ungrounded_citations` passed | `backend/tests/test_application_checkpoints.py:384` - `len(generation.calls) == 1`; `:386` - `MODE_ANSWER`; `:389` - `assert len(snippets) == 6` (literal now; F3/M3 killed: `7 == 6`); `:392-393` ordering; `:395`, `:415` grounded quotes | PASS |
| C22 | explain JSON keys are exactly feedback/citations(anchor, section_path, quote); the dialog shows no grade wording | pytest `explain_payload_keys_have_no_score` and vitest `feedback step shows no grade wording` passed | `backend/tests/test_web_checkpoints.py:331` - `set(body) == {"feedback", "citations"}`; `:334` - citation keys; `:335` - `_GRADE_WORDS.search(...) is None`; `frontend/tests/checkpoint-dialog.test.tsx:248` - `dialog.textContent).not.toMatch(...)` | PASS |
| C23 | not-found / raise / ungrounded → fallback quoting the least-covered chunk; a raise debits nothing, a completed call debits | pytest `explain_fallback_on_not_found_raise_or_ungrounded` [3] passed | `backend/tests/test_application_checkpoints.py:444` - `== [CHUNKS[1]]`; `:448` - `row is None` (raise); `:451` - `row.usd_micros == 3000` | PASS |
| C24 | a blank explanation makes no generate call and quotes the least-covered chunk | pytest `blank_explanation_skips_generation` passed | `backend/tests/test_application_checkpoints.py:470` - `== [CHUNKS[0]]`; `:472` - `generation.calls == []` | PASS |
| C25 | at the cap → 429, paused → 503, responded_at stays NULL | pytest `explain_budget_exhausted_429_paused_503` passed | `backend/tests/test_web_checkpoints.py:360` - `== 429`; `:361` - `== 503`; `:367` - `== [None, None]` | PASS |
| C26 | usage debited as KIND_GENERATION, ask_count untouched | pytest `explain_debits_usage_as_generation` passed | `backend/tests/test_application_checkpoints.py:493` - `row.usd_micros == budget.usage_micros(usage, None) == 2000`; `:494` - `row.ask_count == 0` | PASS |
| C27 | feedback renders quote and path, then exactly Missed it/Partly/Got it, grading 1/2/3 | vitest `feedback quotes passages then offers three self-assessments`, `self-assessment` [3], `is sent as` [3] passed | `frontend/tests/checkpoint-dialog.test.tsx:221-222` - quote and path; `:226` - `toEqual(["Missed it", "Partly", "Got it"])`; `:279` - `expect(grades).toEqual([{ rating }])` over `:253-257` (1/2/3; F4/M4 killed); `:308` - `expect(sent).toEqual([{ response: "workers specialise", confidence }])` over 1/2/3 (M12 killed) | PASS |
| C28 | Just explain is link/ghost; confidence buttons are primary; no request until used | vitest `just explain is a secondary action on the explain step` passed | `frontend/tests/checkpoint-dialog.test.tsx:191` - `data-variant` `"link"`; `:193` - confidence `"default"`; `:199` - `toHaveBeenCalledTimes(1)` | PASS |
| C29 | reveal stamps revealed_at and returns the first chunk | pytest `reveal_stamps_and_returns_first_chunk` passed | `backend/tests/test_web_checkpoints.py:382` - `resp.json()["passage"] == CHUNKS[0]`; `:388` - `revealed is not None` | PASS |
| C30 | reveal on a recall attempt or after a response → 409, unchanged | pytest `reveal_409_on_recall_or_after_response` passed | `backend/tests/test_web_checkpoints.py:404` - `== (409, 409)`; `:410` - `== [None, None]` | PASS |
| C31 | revealed → assisted=true, unrevealed → false; the grade route accepts no client `assisted` | pytest `revealed_explain_grade_is_assisted`, `unrevealed_explain_grade_is_unassisted`, `grade_refuses_a_client_assisted_field` passed | `backend/tests/test_application_checkpoints.py:507` - `== [(3, 3, True)]`; `:516` - `== [(3, 3, False)]`; `backend/tests/test_web_checkpoints.py:464` - `resp.status_code == 422` for `{"rating": 3, "assisted": False}` on a revealed attempt; `:465` - `_log_count(db_conn) == before`; code `backend/app/infrastructure/web/checkpoints.py:115` `model_config = ConfigDict(extra="forbid")` (M5 killed: `200 == 422`) | PASS |
| C32 | `SubmitReview` requires the `assisted` keyword and every row has non-null `assisted`; the migration leaves existing rows NULL | pytest `submit_review_requires_assisted_and_stores_it`, `checkpoint_migration_leaves_existing_review_log_unrecorded` passed | `backend/tests/test_application_reviews.py:1105` - `pytest.raises(TypeError)`; `:1116` - `== [(3, 2, True), (1, None, False)]`; `backend/tests/test_migrations.py:4102` - `tuple(row) == (None, None)`, in the renumbered test at `:4075` that downgrades to `0030_user_provider_credentials` (M14 killed: a pre-rebase parent gives multiple heads) | PASS |

Every new proof resolves to a test this fix added (`git diff --stat bed7114..e2c55e2` lists both backend and both frontend test files). The rest resolve to tests the feature added (round 1).

## Coverage

Verified at e2c55e2 for the rows whose authority the fix touched: create statuses, grade rating scale, grade 422 inputs, 404 indistinguishability, recall exclusions, evidence cap, minted card, button→value mappings, auth-guard writes, and the migration chain. The other rows are carried from 47d200e, and their proofs re-ran green at e2c55e2. Batch-2 sets are out of scope.

| Set (size) | Recomputed from | Member -> proof | Unproven |
| --- | --- | --- | --- |
| create statuses (5) | plan Surface; `web/checkpoints.py:56-57` (anchor min_length 1, prediction 1..3) | 201 C8 `test_web_checkpoints.py:126` · 401/403 C42 `:154-155` · 404 C8 `:113` · 422 C8 `:429` (prediction 0, 4, empty anchor) | - |
| response statuses (8) | plan Surface (carried) | 200 C9 · 401/403 C42 · 404 C12 · 409 C10 · 422 C11 · 429/503 C25 | - |
| reveal statuses (5) | plan Surface (carried) | 200 C29 · 401/403 C42 · 404 C12 · 409 C30 | - |
| grade statuses (6) | plan Surface | 200 C16 `:290`, C18 `:310`, `:444` · 401/403 C42 · 404 C12 · 409 C15/C16 · 422 C18 (explain 4/0, recall 5), C31 (extra field) `:464` | - |
| grade rating scale by kind (recall 1–4, explain 1–3) | plan Surface; `checkpoints.py:506`; `web/checkpoints.py:117` | recall 1 C14 · recall 3 C16 · recall 4 → 200 and recall 5 → 422 `:444` · explain 1/2/3 C18 · explain 4/0 → 422 | - |
| grade body fields (1 allowed, extras refused) | door 2; `GradeRequest` `extra="forbid"` | `rating` C18 · `assisted` refused C31 `:464` | - |
| attempt states (4) | plan domain term (carried) | created C5 · revealed C29 · responded C9 · graded C14 | - |
| refused transitions (4) | Landing door 1 (carried) | respond-twice C10 · grade-unresponded C15 · grade-twice C16/C17 · reveal-after-response C30 | - |
| attempt kinds (2) | `kind IN ('recall','explain')` (carried) | recall C14 · explain C18 | - |
| prediction values (4) | Landing door 6 (carried) | 1/2/3/null C4 · stored C5 `test_application_checkpoints.py:194` | - |
| confidence values incl. invalid (5) | Landing door 2 (carried) | 1 C10 · 2 C9 · 3 C31 · 0/4 C11 | - |
| confidence button → value in the dialog (3) | Landing door 6 `Not sure (1) · Fairly sure (2) · Sure (3)`; `checkpoint-dialog.tsx:58-60` | 1/2/3 C27 `checkpoint-dialog.test.tsx:308` | - |
| explain self-assessment button → rating (3) | Landing door 6; `checkpoint-dialog.tsx:71-73` | 1/2/3 C27 `:279` | - |
| recall card exclusions (5) | AC 6; `repositories.py:2913-2918` | stale/flagged/other-anchor/checkpoint-origin/other-learner-on-same-source C5 `test_application_checkpoints.py:184` | - |
| explain generation outcomes (5) | AC 21–24 (carried) | grounded C21 · ungrounded/not-found/raise C23 · blank C24 | - |
| explain evidence cap (1) | AC 21 "at most 6" | C21 `:389` `== 6` | - |
| minted card passage source (2) | AC 19 "first feedback citation, else first chunk"; `checkpoints.py:552-556` | first-chunk fallback C19 `:338` | first citation of several: the fixture has one citation (M15 survived) |
| minted card scheduling (1) | AC 19 `SchedulingPort.initial()` | C19 `:321` | - |
| budget refusals (2) | AC 25 (carried) | exhausted/paused C25 | - |
| assisted values written (3) | Landing door 2 (carried) | true/false C31 · pre-cycle NULL C32 | - |
| 404 indistinguishability (foreign vs missing, per route) | AC 12; `checkpoints.py:198-202` | C12 `test_web_checkpoints.py:259` | - |
| auth-guard "writes nothing" (4 routes) | C42 claim | create `:156` · response and reveal `:162` (both attempts) · grade: posted to an unresponded attempt, which cannot write, and the guard is proven by `:154-155` | - |
| migration chain (1 head) | `0031_section_checkpoints.py:34-35`; `alembic` heads | C32 `test_migrations.py:4075` upgrades to `head` and downgrades to `0030_user_provider_credentials` | - |
| doors (6) | plan Landing (carried; door 2 re-read) | 1 C5/C17 · 2 C31 (now incl. the client field)/C32 · 3 C19/C20 · 4 C21 · 5 C8/C12 · 6 C4, C27 | - |
| startup config: checkpoint router mounted (2 assemblies) | read each assembly (carried; re-read) | `backend/app/main.py:132` `app.include_router(checkpoints_router)` · `quiz_client` builds via `create_app` | - |

## Test policy rows

Verified at e2c55e2 for the three rows that were unmet in round 1. The repository row is carried from 47d200e.

| Row | Files it classifies | Required proof | Expectation met |
| --- | --- | --- | --- |
| Decides: card selection, guards, assisted, evidence order, fallback, mint-or-reuse | `backend/app/application/checkpoints.py` | own layer vs Postgres and real FSRS, present | no - the round-1 gaps are closed (other learner M1, cap M3, `initial()` M6), but the mint path's passage choice ("first citation") still has no discriminating case (M15) |
| Entry point: validation, status mapping | `backend/app/infrastructure/web/checkpoints.py` | HTTP boundary, present | yes - create 422 `test_web_checkpoints.py:429`, recall 5 `:444`, client `assisted` `:464`, all with nothing written |
| Repository conditional updates | `SqlAlchemyCheckpointRepository.claim_grade` | two-connection race | yes - `test_repositories_checkpoints.py:77` (carried) |
| Step machine: what is visible when | `frontend/app/components/checkpoint-dialog.tsx` | component test, present | no - the button→value mappings are now complete (`:279`, `:308`), but the post-"Just explain" state (`ask` with `passage`, `checkpoint-dialog.tsx:157-171`) is still untested: making it set `passage: null` survives all 16 dialog tests (M16). Round 1 named this gap; the fix did not address it |

The `Swept` rows that resolve to existing code are carried from 47d200e. The CSRF/origin/rate-limit guards (`_GUARDS`, `web/checkpoints.py:50`) and the warning log on generation failure are unchanged by the fix.

## Faults injected

Verified at e2c55e2. Isolation: a scratch `git worktree add --detach <scratchpad>/verify-wt HEAD`, a fresh `uv sync --extra dev` (`app` imported from the scratch path), frontend `node_modules` symlinked, and a separate DB `learny_test_checkpoint_verify`. The scratch baseline was green (46 passed). Each mutant was applied by an exact-anchor replacement, run against only its narrowest proof, then reverted with `git checkout`. The real tree's `git status --porcelain` was empty before and empty after (matched). The scratch worktree was removed and the DB dropped.

Round 2 exceeds the cap of five on purpose. The brief asked for round 1's four survivors to be re-run, and the fix created nine new assertion surfaces, each of which had to be made to fail once. M15 and M16 re-probe the round-1 FAIL verdicts that the fix did not touch.

| Mutation | Location | Killed |
| --- | --- | --- |
| M1 (= F1) drop `quiz_items.c.user_id == user_id` from `recall_cards` | `backend/app/infrastructure/db/repositories.py:2913` | yes - C5 `test_application_checkpoints.py:184` failed |
| M2 (= F2) a foreign attempt raises "not yours." while a missing one raises "not found." | `backend/app/application/checkpoints.py:198-201` | yes - C12 `test_web_checkpoints.py:259` `[2, 2, 2] == [1, 1, 1]` |
| M3 (= F3) `MAX_EXPLAIN_EVIDENCE = 6` → `7` | `backend/app/application/checkpoints.py:84` | yes - C21 `:389` `7 == 6` |
| M4 (= F4) `Got it` rating 3 → 4 | `frontend/app/components/checkpoint-dialog.tsx:73` | yes - `self-assessment Got it grades the explanation 3` failed |
| M5 remove `model_config = ConfigDict(extra="forbid")` | `backend/app/infrastructure/web/checkpoints.py:115` | yes - C31 `test_web_checkpoints.py:464` `200 == 422` |
| M6 mint schedules `review(initial(), 3, now)` instead of `initial()` | `backend/app/application/checkpoints.py:571` | yes - C19 `test_application_checkpoints.py:321` |
| M7 the explain rating bound applied to every kind (`if rating > 3`) | `backend/app/application/checkpoints.py:506` | yes - C18 `recall_grade_rating_bounds[4-200]` `422 == 200` |
| M8 `GradeRequest.rating` `le=4` → `le=5` | `backend/app/infrastructure/web/checkpoints.py:117` | yes - `recall_grade_rating_bounds[5-422]` failed (FSRS `ValueError`, not a 422) |
| M9 create `prediction` `le=3` → `le=4` | `backend/app/infrastructure/web/checkpoints.py:57` | yes - `create_validation_422[body1]` failed (it hit the DB CHECK instead of a 422) |
| M10 create `anchor` `min_length=1` → `0` | `backend/app/infrastructure/web/checkpoints.py:56` | yes - `create_validation_422[body2]` `404 == 422` |
| M11 explain attempts stored already revealed (a stand-in for a reveal written past the guard) | `backend/app/infrastructure/db/repositories.py` `SqlAlchemyCheckpointRepository.add` | yes - C42 `test_web_checkpoints.py:162` (the round-1 assertion would have survived it) |
| M12 `Not sure` value 1 → 2 | `frontend/app/components/checkpoint-dialog.tsx:58` | yes - `confidence Not sure is sent as 1 with the response` failed |
| M13 the invite opens the chapter's first section anchor | `frontend/app/components/chapter-reader.tsx:918` | yes - `starts the checkpoint for the section whose invitation was tapped` failed |
| M14 the migration revises `0029_user_ai_preferences` (pre-rebase parent) | `backend/migrations/versions/0031_section_checkpoints.py:35` | yes - C32 migration test, `Multiple head revisions` |
| M15 the minted card takes the last feedback citation, not the first | `backend/app/application/checkpoints.py:554` | no - survived (C19 proofs: 2 passed) |
| M16 "Just explain" reveals but never shows the passage (`passage: null`) | `frontend/app/components/checkpoint-dialog.tsx:157-171` | no - survived (all 16 dialog tests passed) |

## Gate

Verified at e2c55e2.

- Batch-1 named proofs: 49 passed (backend) and 18 passed (frontend), 0 failed.
- Touched-module regression (`test_application_checkpoints`, `test_web_checkpoints`, `test_repositories_checkpoints`, `test_application_reviews`, `test_migrations`, `test_web_quiz`, `test_domain_quiz`, `test_application_budget`): 266 passed, 0 failed. `vitest run tests/chapter-reader.test.tsx tests/checkpoint-dialog.test.tsx`: 92 passed, 0 failed.
- The orchestrator's full gate at e2c55e2: backend 3222 passed, 2 failed (`test_deploy_topology` dev-merge, environmental skip-worktree override, outside this feature); frontend 940 passed. Not re-run here.

## Ranked gaps

1. The `checkpoint-dialog.tsx` step-machine Test policy row is unmet. After "Just explain", nothing asserts that the passage is shown, or that a reveal request is sent from the dialog. M16 survives the whole file. No check claims the dialog side of AC 29, which is a precision gap in `checks.md` as well as a missing test. `frontend/app/components/checkpoint-dialog.tsx:157-171`, no test (`rg "Just explain" frontend/tests/checkpoint-dialog.test.tsx` hits only `:190`, which never clicks it)
2. C19's "first feedback citation" clause is not discriminated: the fixture's provider cites exactly one chunk, and `quoted[-1]` survives (M15). `backend/tests/test_application_checkpoints.py:287-291`, `:307`
3. Minor, not failing: M8 and M9 were killed by a downstream crash (FSRS `ValueError`, DB `CHECK` `IntegrityError`) rather than by the 422 assertion firing on a clean response. The boundary is still pinned. This is noted so that nobody reads those kills as proof of the HTTP mapping alone.
