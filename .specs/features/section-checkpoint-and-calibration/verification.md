# section-checkpoint-and-calibration verification

**Verdict**: PASS
**Profile**: standard
**Diff range**: 2281250..992176c (feature base after the rebase onto `main`; the fix under review is e2c55e2..992176c)
**Round**: 3 - scoped
**Verifier**: independent sub-agent (author != verifier)

Batch scope: C1–C32 and C42. C33–C41 are batch 2 and out of scope. They are verified before that batch's PR.

The fix closes both round-2 failures, and no production code changed. First, the minted-card test now has the provider cite two chunks in the reverse of evidence order. It asserts the stored feedback order, and the card takes the first quote. M15 (`quoted[-1]`) is now killed. Second, a new dialog test clicks "Just explain" and asserts five things: one reveal request, the passage with its section path, the action gone, the explanation box kept, and a confidence submit that still works. M16 (`passage: null`) is now killed. Three more mutants aimed at the new assertions were all killed. The checks.md amendment to C28 only adds: it keeps the original claim and proof, appends the dialog side of AC 29 with a second proof, and closes the round-2 precision gap. `validate_checks.py` reports 0 errors and 0 warnings.

Fix scope reviewed: `git diff e2c55e2..992176c` touches `backend/tests/test_application_checkpoints.py` (+20/-5), `frontend/tests/checkpoint-dialog.test.tsx` (+33), `checks.md` (C28, 3 lines) and the previous `verification.md`. No file under `backend/app` or `frontend/app` changed.

## Binding sources

Carried from 47d200e (via e2c55e2). Step 1 (`ui`) does not run under `standard`. The binding sources are the ROADMAP v8 row and research synthesis row #6 with its do-not-build list. They set scope and non-goals, not a UI design. The fix touched no interface. No contradiction.

## Checks

Verified at 992176c. Every batch-1 proof was re-run in full at `HEAD`, in the real tree.

Backend, one invocation: `cd backend && LEARNY_REQUIRE_DB=1 LEARNY_TEST_DATABASE_URL=…/learny_test_checkpoint uv run pytest tests/test_application_checkpoints.py tests/test_web_checkpoints.py tests/test_repositories_checkpoints.py tests/test_application_reviews.py tests/test_migrations.py -v -k "<all 36 batch-1 names>"`. Result: 49 passed, 77 deselected, exit 0. Every name appears individually as PASSED, parametrized cases included.

Frontend, one invocation: `cd frontend && npx vitest run tests/chapter-reader.test.tsx tests/checkpoint-dialog.test.tsx --reporter=verbose -t "<12 names>"`. Result: 19 passed, 74 skipped, exit 0. Every name appears individually, including the new `just explain shows the passage and still asks for the explanation`.

Citations were refreshed in the two touched test files. In `test_application_checkpoints.py`, lines after the minted test moved +10. In `checkpoint-dialog.test.tsx`, lines after `:201` moved +33. Citations in untouched files are carried from e2c55e2 and were re-read at the same lines.

| Check | Claim | Proof run | Evidence | Result |
| --- | --- | --- | --- | --- |
| C1 | one invite, only after the ≥150-word section, placed after its body | vitest `checkpoint invitation only after sections of at least 150 words` passed | `frontend/tests/chapter-reader.test.tsx:2239` - `expect(invites).toHaveLength(1)`; `:2242` - `expect(longSection.nextElementSibling).toBe(invites[0])` | PASS |
| C2 | the tap opens the dialog on the prediction step for that section's anchor; no request before a choice | vitest `opens on the prediction step without calling the API`, `starts the checkpoint for the section whose invitation was tapped` passed | `frontend/tests/checkpoint-dialog.test.tsx:115` - `expect(fetchMock).not.toHaveBeenCalled()`; `frontend/tests/chapter-reader.test.tsx:2302` - `expect(started).toEqual([{ anchor: S2, prediction: null }])` | PASS |
| C3 | closing mid-flow unmounts, chapter intact, no further request | vitest `closing mid-flow sends nothing more` passed | `frontend/tests/checkpoint-dialog.test.tsx:353` - `expect(onClose).toHaveBeenCalledTimes(1)`; `:354` - `expect(fetchMock).toHaveBeenCalledTimes(1)`; unmount `frontend/tests/chapter-reader.test.tsx:2256` | PASS |
| C4 | Little/Some/Most/Skip → 1/2/3/null | vitest `prediction choices map to 1, 2, 3 and null` (4 cases) passed | `frontend/tests/checkpoint-dialog.test.tsx:139` - `expect(bodies).toEqual([{ anchor: "ch1#s1", prediction: expected }])` | PASS |
| C5 | ≤3 owned, active, unflagged, non-checkpoint cards on the anchor, due asc then id, then one explain; exclusions hold | pytest `start_selects_due_first_owned_active_cards_on_anchor`, `start_caps_recall_attempts_at_three` passed | `backend/tests/test_application_checkpoints.py:179` - the stranger's card on the same source and anchor; `:184` - `assert kinds == [(RECALL, sooner.id), (RECALL, later.id), (EXPLAIN, None)]`; `:207` - `recalls == [cards[4].id, cards[3].id, cards[2].id]` | PASS |
| C6 | no eligible cards → exactly one explain attempt | pytest `start_without_cards_has_only_explain` passed | `backend/tests/test_application_checkpoints.py:217` - `[a.kind …] == [CheckpointAttemptKind.EXPLAIN]` | PASS |
| C7 | the create payload has no answer/excerpt/passage keys or text | pytest `create_payload_carries_no_answers` passed | `backend/tests/test_web_checkpoints.py:91` - `"A distinctive secret answer" not in raw`; `:96` - `assert key not in json.dumps(body)`; `:99` - attempt keys `{attempt_id, kind, question}` | PASS |
| C8 | 404 with nothing persisted for missing/foreign/no-section; sample → 201; prediction 0/4 or empty anchor → 422, nothing persisted | pytest `create_404_cases_persist_nothing`, `create_on_shared_sample_returns_201`, `create_validation_422` [3] passed | `backend/tests/test_web_checkpoints.py:113` - `== [404, 404, 404]`; `:115` - count unchanged; `:126` - `== 201`; `:429` - `resp.status_code == 422`; `:430` - `_checkpoint_count(db_conn) == before` | PASS |
| C9 | recall response stores response and confidence=2, returns answer/excerpt/anchor/path; empty accepted | pytest `recall_response_reveals_answer_after_storing` passed | `backend/tests/test_web_checkpoints.py:178` - `resp.json() == {"answer": …, "source_excerpt": …, "anchor": ANCHOR, "section_path": …}`; `:189` - `tuple(stored) == ("", 2)` | PASS |
| C10 | second response 409, first kept | pytest `second_response_is_409_and_keeps_first` passed | `backend/tests/test_web_checkpoints.py:203` - `== 409`; `:209` - `tuple(stored) == ("one", 1)` | PASS |
| C11 | no confidence / 0 / 4 / 4001 chars → 422, responded_at NULL | pytest `response_validation_422` [4] passed | `backend/tests/test_web_checkpoints.py:228` - `== 422`; `:234` - `responded is None` | PASS |
| C12 | response/reveal/grade on a foreign and on a random attempt return identical 404 bodies | pytest `attempt_routes_404_for_foreign_and_missing` passed | `backend/tests/test_web_checkpoints.py:255` - `== [404, 404, 404]`; `:259` - `[len(texts) for texts in bodies.values()] == [1, 1, 1]` | PASS |
| C42 | the four POSTs return 401 without a session and 403 without CSRF, and write nothing | pytest `new_routes_require_session_and_csrf` passed | `backend/tests/test_web_checkpoints.py:154` - `== [403, 403, 403, 403]`; `:155` - `== [401, 401, 401, 401]`; `:156` - count unchanged; `:162` - `[tuple(s) for s in stamps] == [(None, None), (None, None)]` | PASS |
| C13 | recall shows the question and no answer; the answer appears only after the confidence submit resolves | vitest `recall answer appears only after a confidence submit resolves` passed | `frontend/tests/checkpoint-dialog.test.tsx:159` - `queryByText(SECRET)).toBeNull()`; `:166` - still null in flight; `:177` - `findByText(SECRET)` | PASS |
| C14 | recall grade 1: FSRS advance, one log row (1, confidence, assisted=false), review_log_id linked, study day +1 | pytest `grade_recall_reviews_card_with_confidence_unassisted` passed | `backend/tests/test_application_checkpoints.py:236` - `items.get_scheduling(card.id) == expected`; `:238` - `== [(1, 2, False)]`; `:245` - `linked == log_id`; `:251` - `reviews == 1` | PASS |
| C15 | grade before response → 409, no log row | pytest `grade_before_response_is_409` passed | `backend/tests/test_web_checkpoints.py:277` - `== 409`; `:278` - `_log_count(db_conn) == before` | PASS |
| C16 | sequential double grade leaves one row; the second returns 409 | pytest `second_grade_is_409_one_log_row` passed | `backend/tests/test_web_checkpoints.py:290` - `== 200`; `:292` - `== 409`; `:296` - `[r.rating for r in rows] == [3]` | PASS |
| C17 | concurrent claims on separate connections have one winner | pytest `concurrent_grade_claim_has_one_winner` passed | `backend/tests/test_repositories_checkpoints.py:77` - `(won_first, won_second) == (True, False)` | PASS |
| C18 | explain 1/2/3 reviews the minted checkpoint card; explain 4/0 → 422; recall accepts 4, refuses 5 with 422 and no log row | pytest `grade_explain_mints_and_reviews_checkpoint_card` [3], `explain_grade_rating_bounds` [4], `recall_grade_rating_bounds` [2] passed | `backend/tests/test_application_checkpoints.py:275` - `card.origin == QuizItemOrigin.CHECKPOINT`; `:276` - `== [rating]`; `backend/tests/test_web_checkpoints.py:310-311`; `:444` - `resp.status_code == expected`; `:448` - `[r.rating for r in rows] == ([rating] if expected == 200 else [])` | PASS |
| C19 | minted card shape and owner on the sample; answer = the **first** feedback citation's quote, cut, else the first chunk; scheduled `initial()` before review | pytest `minted_card_shape_and_owner_on_sample`, `minted_card_falls_back_to_first_chunk` passed | `backend/tests/test_application_checkpoints.py:306` - `[c.quote for c in responded.citations] == [CHUNKS[2], CHUNKS[1]]` (two citations; the provider listed `CHUNKS[1]` first, so the first stored quote differs from both the provider's first pick and the last quote); `:311-316` owner/origin/type/question/anchor/path; `:317` - `card.answer == CHUNKS[2][:_MAX_CARD_CHARS]`; `:318` - `source_excerpt` likewise; `:331` - `tuple(prev) == (fresh.state, fresh.step, fresh.stability, fresh.difficulty, None)`; `:348` - fallback `CHUNKS[0][:_MAX_CARD_CHARS]`. I checked the coverage arithmetic by hand: the response's words cover `CHUNKS[2]` 0/10, `CHUNKS[0]` 5/11 and `CHUNKS[1]` 6/12, so least-covered-first yields `[2, 0, 1]` and the grounded order is `[2, 1]`. M15 is killed at `:317` | PASS |
| C20 | an existing checkpoint card is reused, count stays 1, text unchanged | pytest `second_checkpoint_reuses_existing_card` passed | `backend/tests/test_application_checkpoints.py:358` - same `quiz_item_id`; `:364` - `count == 1`; `:366` - text unchanged; `:367` - `== [1, 3]` | PASS |
| C21 | one answer-mode call, evidence capped at 6, least-covered first, citations = grounded | pytest `explain_calls_answer_mode_once_least_covered_first`, `explain_drops_ungrounded_citations` passed | `backend/tests/test_application_checkpoints.py:394` - `len(generation.calls) == 1`; `:396` - `MODE_ANSWER`; `:399` - `len(snippets) == 6`; `:402-403` ordering; `:405`, `:425` grounded quotes | PASS |
| C22 | explain JSON keys are exactly feedback/citations(anchor, section_path, quote); the dialog shows no grade wording | pytest `explain_payload_keys_have_no_score`, vitest `feedback step shows no grade wording` passed | `backend/tests/test_web_checkpoints.py:331` - `set(body) == {"feedback", "citations"}`; `:334` citation keys; `:335` - `_GRADE_WORDS.search(...) is None`; `frontend/tests/checkpoint-dialog.test.tsx:281` - `dialog.textContent).not.toMatch(...)` | PASS |
| C23 | not-found / raise / ungrounded → fallback quoting the least-covered chunk; a raise debits nothing, a completed call debits | pytest `explain_fallback_on_not_found_raise_or_ungrounded` [3] passed | `backend/tests/test_application_checkpoints.py:454` - `== [CHUNKS[1]]`; `:458` - `row is None`; `:461` - `row.usd_micros == 3000` | PASS |
| C24 | a blank explanation makes no generate call and quotes the least-covered chunk | pytest `blank_explanation_skips_generation` passed | `backend/tests/test_application_checkpoints.py:480` - `== [CHUNKS[0]]`; `:482` - `generation.calls == []` | PASS |
| C25 | at the cap → 429, paused → 503, responded_at stays NULL | pytest `explain_budget_exhausted_429_paused_503` passed | `backend/tests/test_web_checkpoints.py:360` - `== 429`; `:361` - `== 503`; `:367` - `== [None, None]` | PASS |
| C26 | usage debited as KIND_GENERATION, ask_count untouched | pytest `explain_debits_usage_as_generation` passed | `backend/tests/test_application_checkpoints.py:503` - `row.usd_micros == budget.usage_micros(usage, None) == 2000`; `:504` - `row.ask_count == 0` | PASS |
| C27 | feedback renders quote and path, then exactly Missed it/Partly/Got it grading 1/2/3; confidence 1/2/3 sent | vitest `feedback quotes passages then offers three self-assessments`, `self-assessment` [3], `is sent as` [3] passed | `frontend/tests/checkpoint-dialog.test.tsx:254-255` - quote and path; `:259` - `toEqual(["Missed it", "Partly", "Got it"])`; `:312` - `expect(grades).toEqual([{ rating }])`; `:341` - `expect(sent).toEqual([{ response: "workers specialise", confidence }])` | PASS |
| C28 | Just explain is link/ghost, confidence primary, no request until used; using it sends one reveal, shows passage + path, removes the action, keeps explanation and confidence | vitest `just explain is a secondary action on the explain step`, `just explain shows the passage and still asks for the explanation` passed | `frontend/tests/checkpoint-dialog.test.tsx:191` - `data-variant` `"link"`; `:193` - confidence `"default"`; `:199` - `toHaveBeenCalledTimes(1)`; `:225` - `expect(await within(step).findByText(PASSAGE)).toBeTruthy()`; `:226` - `getByText("Book I › The Division of Labour")`; `:227` - `expect(reveals).toHaveLength(1)` (only to `a2`; `routedFetch` throws on any unrouted call, `:32`); `:229` - `queryByRole("button", { name: "Just explain" })).toBeNull()`; `:230` - `getByRole("textbox", { name: "Your explanation" })`; `:232` - feedback after clicking `Sure` | PASS |
| C29 | reveal stamps revealed_at and returns the first chunk | pytest `reveal_stamps_and_returns_first_chunk` passed | `backend/tests/test_web_checkpoints.py:382` - `resp.json()["passage"] == CHUNKS[0]`; `:388` - `revealed is not None` | PASS |
| C30 | reveal on a recall attempt or after a response → 409, unchanged | pytest `reveal_409_on_recall_or_after_response` passed | `backend/tests/test_web_checkpoints.py:404` - `== (409, 409)`; `:410` - `== [None, None]` | PASS |
| C31 | revealed → assisted=true, unrevealed → false; the grade route accepts no client `assisted` | pytest `revealed_explain_grade_is_assisted`, `unrevealed_explain_grade_is_unassisted`, `grade_refuses_a_client_assisted_field` passed | `backend/tests/test_application_checkpoints.py:517` - `== [(3, 3, True)]`; `:526` - `== [(3, 3, False)]`; `backend/tests/test_web_checkpoints.py:464` - `resp.status_code == 422`; `:465` - `_log_count(db_conn) == before` | PASS |
| C32 | `SubmitReview` requires `assisted` and stores it; the migration leaves existing rows NULL | pytest `submit_review_requires_assisted_and_stores_it`, `checkpoint_migration_leaves_existing_review_log_unrecorded` passed | `backend/tests/test_application_reviews.py:1105` - `pytest.raises(TypeError)`; `:1116` - `== [(3, 2, True), (1, None, False)]`; `backend/tests/test_migrations.py:4102` - `tuple(row) == (None, None)` | PASS |

Both strengthened proofs resolve to tests this fix changed or added (`git diff --stat e2c55e2..992176c`). All others resolve to tests the feature added in rounds 1 and 2.

## Coverage

Verified at 992176c for the rows whose authority the fix touched: minted card passage source, and the dialog's explain-step states (new row, from AC 28–29 and `checkpoint-dialog.tsx` `Phase`/`AskStep`). Every other row is carried from e2c55e2, and its proofs re-ran green at 992176c. Batch-2 sets are out of scope.

| Set (size) | Recomputed from | Member -> proof | Unproven |
| --- | --- | --- | --- |
| create statuses (5) | plan Surface (carried from e2c55e2) | 201 C8 · 401/403 C42 · 404 C8 · 422 C8 | - |
| response statuses (8) | plan Surface (carried) | 200 C9 · 401/403 C42 · 404 C12 · 409 C10 · 422 C11 · 429/503 C25 | - |
| reveal statuses (5) | plan Surface (carried) | 200 C29 · 401/403 C42 · 404 C12 · 409 C30 | - |
| grade statuses (6) | plan Surface (carried) | 200 C16/C18 · 401/403 C42 · 404 C12 · 409 C15/C16 · 422 C18, C31 | - |
| grade rating scale by kind (recall 1–4, explain 1–3) | plan Surface (carried) | recall 1 C14 · 3 C16 · 4/5 `test_web_checkpoints.py:444` · explain 1/2/3 C18 · 4/0 → 422 | - |
| grade body fields (1 allowed, extras refused) | door 2 (carried) | `rating` C18 · `assisted` refused C31 | - |
| attempt states (4) | plan domain term (carried) | created C5 · revealed C29 · responded C9 · graded C14 | - |
| refused transitions (4) | Landing door 1 (carried) | C10 · C15 · C16/C17 · C30 | - |
| attempt kinds (2) | `kind IN ('recall','explain')` (carried) | recall C14 · explain C18 | - |
| prediction values (4) | Landing door 6 (carried) | 1/2/3/null C4 | - |
| confidence values incl. invalid (5) | Landing door 2 (carried) | 1 C10 · 2 C9 · 3 C31 · 0/4 C11 | - |
| confidence button → value in the dialog (3) | Landing door 6 (carried) | 1/2/3 C27 `checkpoint-dialog.test.tsx:341` | - |
| explain self-assessment button → rating (3) | Landing door 6 (carried) | 1/2/3 C27 `:312` | - |
| dialog explain-step states (2: unrevealed, revealed) | AC 28–29; `checkpoint-dialog.tsx` `Phase.ask.passage` and `AskStep` `{explain && !passage ? …}` | unrevealed: Just explain as link, no request C28 `:191`, `:199` · revealed: passage + path `:225-226`, one reveal `:227`, action gone `:229`, textbox kept `:230`, submit still works `:232` | - |
| recall card exclusions (5) | AC 6 (carried) | C5 `test_application_checkpoints.py:184` | - |
| explain generation outcomes (5) | AC 21–24 (carried) | grounded C21 · ungrounded/not-found/raise C23 · blank C24 | - |
| explain evidence cap (1) | AC 21 (carried) | C21 `:399` `== 6` | - |
| minted card passage source (2) | AC 19 "first passage the feedback quoted, else the section's first chunk"; `backend/app/application/checkpoints.py:542-547` | first of several citations C19 `test_application_checkpoints.py:306`, `:317` (M15 killed) · first-chunk fallback C19 `:348` | - |
| minted card scheduling (1) | AC 19 (carried) | C19 `:331` | - |
| budget refusals (2) | AC 25 (carried) | C25 | - |
| assisted values written (3) | Landing door 2 (carried) | true/false C31 · pre-cycle NULL C32 | - |
| 404 indistinguishability | AC 12 (carried) | C12 `test_web_checkpoints.py:259` | - |
| auth-guard "writes nothing" (4 routes) | C42 claim (carried) | `:156`, `:162`, guard `:154-155` | - |
| migration chain (1 head) | `0031_section_checkpoints.py:34-35` (carried) | C32 `test_migrations.py:4075` | - |
| doors (6) | plan Landing (carried) | 1 C5/C17 · 2 C31/C32 · 3 C19/C20 · 4 C21 · 5 C8/C12 · 6 C4, C27 | - |
| startup config: checkpoint router mounted (2 assemblies) | read each assembly (carried) | `backend/app/main.py:132` · `quiz_client` via `create_app` | - |

## Test policy rows

Verified at 992176c for the two rows that round 2 left unmet. The other two are carried from e2c55e2, because the fix touched none of the files they classify.

| Row | Files it classifies | Required proof | Expectation met |
| --- | --- | --- | --- |
| Decides: card selection, guards, assisted, evidence order, fallback, mint-or-reuse | `backend/app/application/checkpoints.py` | own layer vs Postgres and real FSRS, present | yes - the mint-or-reuse passage choice now has one asserted case per member: first of several citations `test_application_checkpoints.py:306`, `:317`; fallback `:348`. M15 and M17 killed |
| Entry point: validation, status mapping | `backend/app/infrastructure/web/checkpoints.py` | HTTP boundary, present | yes (carried from e2c55e2) |
| Repository conditional updates | `SqlAlchemyCheckpointRepository.claim_grade` | two-connection race | yes (carried) - `test_repositories_checkpoints.py:77` |
| Step machine: what is visible when | `frontend/app/components/checkpoint-dialog.tsx` | component test, present | yes - every step now has its visible/hidden contract asserted: predict `:115`/`:139`, ask-recall `:159`/`:166`, recalled `:177`, ask-explain unrevealed `:191`/`:199`, ask-explain revealed `:225-232` (new), feedback `:254-259`/`:281`, done via grades `:312`, close `:353-354`. M16, M18 and M19 killed |

The `Swept` rows that resolve to existing code are carried from 47d200e. The fix changed no production code.

## Faults injected

Verified at 992176c. Isolation: a scratch `git worktree add --detach <scratchpad>/verify-wt HEAD`, a fresh `uv sync --extra dev` (`app` imported from the scratch path, confirmed), frontend `node_modules` symlinked, and a separate DB `learny_test_checkpoint_verify`. The scratch baseline was green: `minted_card` 2 passed, and the dialog file 17 passed. Each mutant was applied by an exact-anchor replacement that had to match exactly once. It was run against only its narrowest covering test file, then reverted with `git checkout`. The real tree's `git status --porcelain` was empty before and empty after (matched). Afterwards, only the symlink was removed, the scratch worktree was removed and pruned, and the DB was dropped.

The scope is M15 and M16 (the round-2 survivors) plus one fault on each surface the new assertions created. That makes five, within the cap.

| Mutation | Location | Killed |
| --- | --- | --- |
| M15 the minted card takes the last feedback citation (`quoted[-1]`), not the first | `backend/app/application/checkpoints.py:544` | yes - `minted_card_shape_and_owner_on_sample` failed at `test_application_checkpoints.py:317` (`'Dexterity grows when each worker repeats' != 'Machines are invented by workers whose a'`) |
| M17 feedback citations emitted in reverse grounded order (`for item in reversed(citations)`), the surface of the new stored-order assertion | `backend/app/application/checkpoints.py:460` | yes - failed at `test_application_checkpoints.py:306` (index 0 `CHUNKS[1]` != `CHUNKS[2]`) |
| M16 "Just explain" reveals but never shows the passage (`passage: null`) | `frontend/app/components/checkpoint-dialog.tsx:164-168` | yes - `just explain shows the passage…` failed at `checkpoint-dialog.test.tsx:225` (passage not found) |
| M18 "Just explain" stays offered after the reveal (`{explain && !passage ?` → `{explain ?`) | `frontend/app/components/checkpoint-dialog.tsx:363` | yes - failed at `checkpoint-dialog.test.tsx:229` |
| M19 the revealed passage is labelled with its anchor instead of the section path | `frontend/app/components/checkpoint-dialog.tsx:338` | yes - failed at `checkpoint-dialog.test.tsx:226` (`Book I › The Division of Labour` not found) |

Each mutant killed only the test aimed at it: 1 failed, 16 passed in the dialog file for each frontend mutant, and 1 failed, 1 passed in the `minted_card` selection for each backend mutant.

## Gate

Verified at 992176c.

- Batch-1 named proofs: 49 passed (backend) and 19 passed (frontend), 0 failed.
- Touched-module regression: `pytest tests/test_application_checkpoints.py tests/test_web_checkpoints.py tests/test_repositories_checkpoints.py` 47 passed, 0 failed. `vitest run tests/checkpoint-dialog.test.tsx tests/chapter-reader.test.tsx` 93 passed, 0 failed.
- Lint on the touched files: `ruff check` and `ruff format --check tests/test_application_checkpoints.py` both clean. `tsc --noEmit` (frontend) clean.
- Full gate: not re-run here. The fix changed only two test files and checks.md. The orchestrator's full gate at e2c55e2 was backend 3222 passed, 2 failed (`test_deploy_topology` dev-merge, environmental) and frontend 940 passed.

## Ranked gaps

None failing.

Notes, none of which fail the round:

1. Carried from round 2: M8 and M9 were killed by a downstream crash (FSRS `ValueError`, DB `CHECK` `IntegrityError`), not by a clean 422. The boundary is still pinned.
2. C28's "keeps … confidence buttons" is asserted by submitting through `Sure` alone (`checkpoint-dialog.test.tsx:231-232`). "Not sure" and "Fairly sure" are not re-queried after the reveal. Only a mutant that hides some confidence buttons, and only after a reveal, would survive. That is not a plausible implementation of `AskStep`, which renders `CONFIDENCES` unconditionally, so this is not counted as a gap.
3. C28 was amended after approval at the round-2 Verifier's request. The change only adds: the original claim text and its proof are kept verbatim, and a clause plus a second proof are appended. It strengthens the check rather than weakening it.
