# section-checkpoint-and-calibration verification

**Verdict**: FAIL
**Profile**: standard
**Diff range**: 8c11ad3..9fcf165 (feature base is the rebase onto `main` at PR #78). The change under review is 2c69997..9fcf165, which holds the round-4 gap fixes.
**Round**: 5 - scoped
**Verifier**: independent sub-agent (author != verifier)

Batch scope: C1–C32 and C42. C33–C41 are batch 2 and out of scope.

The fix closes all three round-4 gaps. Its new proofs are green at 9fcf165, and each one kills the mutant that survived in round 4:

- M23, the dropped owner filter in `active_checkpoint_card`, is now killed.
- M26b, which showed the backend `detail` for 5xx, is now killed by the 503 case.
- M33, where the reader stopped passing `onRequireAuth`, is now killed by the new reader test.

The source, anchor and status filters in the same query are now each killed too (M34–M36).

The round still fails, on one gap. Round 4's Coverage row for the reuse lookup listed five members and left out the query's fifth predicate, `quiz_items.origin == CHECKPOINT` (`backend/app/infrastructure/db/repositories.py:2028`). The new test seeds only checkpoint-origin decoys. Dropping that filter (M37) survives all 51 tests in the three checkpoint files.

In the product, a learner who already has a generated quiz card on the section would have that recall card reviewed as their checkpoint card, and no checkpoint card would be minted. C18 claims "reviews **the caller's checkpoint card**, minting one when absent", so this member is owed a proof. The production code is correct today, because the filter is present. The gap is in the tests only.

Fix scope reviewed with `git diff 2c69997..9fcf165`. No file under `backend/app` or `frontend/app` changed. It touches:

- `backend/tests/test_application_checkpoints.py` (+39: the new `reuse_skips_…` test)
- `backend/tests/test_web_checkpoints.py` (comment only, -1 line; the round-4 stale-comment note is resolved)
- `frontend/tests/checkpoint-dialog.test.tsx` (the refusal test is parametrized over 429 and 503; net 0 lines)
- `frontend/tests/chapter-reader.test.tsx` (+31: the new reader 401 test, appended)
- `checks.md`: C2 gains the 401 hand-over clause and two proofs; C20 gains the not-reused enumeration and one proof; C25's dialog proof filter is broadened to `a refused explanation`. Each amendment only adds: the original claims and proofs are kept. `validate_checks.py` reports 0 errors and 0 warnings.
- the round-4 `verification.md`

## Binding sources

Carried from 47d200e (via 2c69997). Step 1 (`ui`) does not run under `standard`, and the fix touched no interface. The binding sources are the ROADMAP v8 row and the research synthesis row #6 with its do-not-build list. They set scope and non-goals, not a UI design. No contradiction.

## Checks

Verified at 9fcf165. Every batch-1 proof was re-run in full at `HEAD`, in the real tree.

- Backend, one invocation: `cd backend && LEARNY_REQUIRE_DB=1 LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test_checkpoint uv run pytest tests/test_application_checkpoints.py tests/test_application_reviews.py tests/test_migrations.py tests/test_repositories_checkpoints.py tests/test_web_checkpoints.py -v -k "<all 40 batch-1 names>"`. Result: 53 passed, 78 deselected, exit 0. Each of the 40 names appears individually as PASSED, parametrized cases included. The new name is `reuse_skips_checkpoint_cards_that_are_not_the_callers_on_this_section`.
- Frontend, one invocation: `cd frontend && npx vitest run tests/chapter-reader.test.tsx tests/checkpoint-dialog.test.tsx --reporter=verbose -t "<16 names>"`. Result: 24 passed, 75 skipped, exit 0. Each name appears individually. New since round 4: `a refused explanation (429) …`, `a refused explanation (503) …`, and `hands a checkpoint that finds the session gone to the reader's sign-in redirect`.

Citations were refreshed in every touched test file:

- `test_application_checkpoints.py`: +39 after `:368`.
- `test_web_checkpoints.py`: -1 after `:490`.
- `checkpoint-dialog.test.tsx`: net 0; the refusal test now spans `:220-249`.
- `chapter-reader.test.tsx`: appended only.

The other citations are carried from 2c69997 and were re-read at the same lines.

| Check | Claim | Proof run | Evidence | Result |
| --- | --- | --- | --- | --- |
| C1 | one invite, only after the ≥150-word section, placed after its body | vitest `checkpoint invitation only after sections of at least 150 words` passed | `frontend/tests/chapter-reader.test.tsx:2240` - `expect(invites).toHaveLength(1)`; `:2243` - `expect(longSection.nextElementSibling).toBe(invites[0])` | PASS |
| C2 | the tap opens the dialog on the prediction step for that anchor; no request before a choice; **new:** a 401 inside the dialog hands over to the reader's sign-in redirect | vitest `opens on the prediction step without calling the API`, `starts the checkpoint for the section whose invitation was tapped`, `a lost session hands over to the sign-in redirect`, `hands a checkpoint that finds the session gone to the reader's sign-in redirect` passed | `frontend/tests/checkpoint-dialog.test.tsx:116` - `expect(fetchMock).not.toHaveBeenCalled()`; `frontend/tests/chapter-reader.test.tsx:2303` - `expect(started).toEqual([{ anchor: S2, prediction: null }])`; dialog side `frontend/tests/checkpoint-dialog.test.tsx:270` - `expect(onRequireAuth).toHaveBeenCalledTimes(1)`; reader side `frontend/tests/chapter-reader.test.tsx:2334` - `expect(onRequireAuth).toHaveBeenCalledTimes(1)` after a 401 on `POST /api/sources/s1/checkpoints`. M33 was killed at `:2334` | PASS |
| C3 | closing mid-flow unmounts, the chapter stays intact, no further request | vitest `closing mid-flow sends nothing more` passed | `frontend/tests/checkpoint-dialog.test.tsx:460` - `expect(onClose).toHaveBeenCalledTimes(1)`; `:461` - `expect(fetchMock).toHaveBeenCalledTimes(1)`; unmount `frontend/tests/chapter-reader.test.tsx:2257` | PASS |
| C4 | Little/Some/Most/Skip → 1/2/3/null | vitest `prediction choices map to 1, 2, 3 and null` (4 cases) passed | `frontend/tests/checkpoint-dialog.test.tsx:140` - `expect(bodies).toEqual([{ anchor: "ch1#s1", prediction: expected }])` | PASS |
| C5 | ≤3 owned, active, unflagged, non-checkpoint cards on the anchor, due ascending then id, then one explain; the exclusions hold | pytest `start_selects_due_first_owned_active_cards_on_anchor`, `start_caps_recall_attempts_at_three` passed | `backend/tests/test_application_checkpoints.py:180` - a stranger's card on the same source and anchor; `:185` - `assert kinds == [(RECALL, sooner.id), (RECALL, later.id), (EXPLAIN, None)]`; `:208` - `recalls == [cards[4].id, cards[3].id, cards[2].id]` | PASS |
| C6 | no eligible cards → exactly one explain attempt | pytest `start_without_cards_has_only_explain` passed | `backend/tests/test_application_checkpoints.py:218` - `[a.kind …] == [CheckpointAttemptKind.EXPLAIN]` | PASS |
| C7 | the create payload has no answer/excerpt/passage keys or text | pytest `create_payload_carries_no_answers` passed | `backend/tests/test_web_checkpoints.py:92` - `"A distinctive secret answer" not in raw`; `:97` - `assert key not in json.dumps(body)`; `:100` - attempt keys `{attempt_id, kind, question}` | PASS |
| C8 | 404 with nothing persisted for missing/foreign/no-section; sample → 201; prediction 0/4 or empty anchor → 422, nothing persisted | pytest `create_404_cases_persist_nothing`, `create_on_shared_sample_returns_201`, `create_validation_422` [3] passed | `backend/tests/test_web_checkpoints.py:114` - `== [404, 404, 404]`; `:116` - count unchanged; `:127` - `== 201`; `:448` - `resp.status_code == 422`; `:449` - `_checkpoint_count(db_conn) == before` | PASS |
| C9 | a recall response stores response and confidence=2, returns answer/excerpt/anchor/path; an empty response is accepted | pytest `recall_response_reveals_answer_after_storing` passed | `backend/tests/test_web_checkpoints.py:179` - `resp.json() == {"answer": …, "source_excerpt": …, "anchor": ANCHOR, "section_path": …}`; `:190` - `tuple(stored) == ("", 2)` | PASS |
| C10 | second response → 409, the first is kept; an explanation that loses the claim to a concurrent response is refused without calling the provider | pytest `second_response_is_409_and_keeps_first`, `explain_lost_to_a_concurrent_response_never_calls_the_provider` passed | `backend/tests/test_web_checkpoints.py:204` - `== 409`; `:210` - `tuple(stored) == ("one", 1)`; `backend/tests/test_application_checkpoints.py:587` - `pytest.raises(CheckpointAttemptConflict)`; `:592` - `generation.calls == []`; `:598` - `tuple(stored) == ("the winner", 2)` | PASS |
| C11 | no confidence / 0 / 4 / 4001 chars → 422, responded_at NULL | pytest `response_validation_422` [4] passed | `backend/tests/test_web_checkpoints.py:229` - `== 422`; `:235` - `responded is None` | PASS |
| C12 | response/reveal/grade on a foreign and on a random attempt → identical 404 bodies | pytest `attempt_routes_404_for_foreign_and_missing` passed | `backend/tests/test_web_checkpoints.py:256` - `== [404, 404, 404]`; `:260` - `[len(texts) for texts in bodies.values()] == [1, 1, 1]` | PASS |
| C42 | the four POSTs → 401 without a session and 403 without CSRF, writing nothing | pytest `new_routes_require_session_and_csrf` passed | `backend/tests/test_web_checkpoints.py:155` - `== [403, 403, 403, 403]`; `:156` - `== [401, 401, 401, 401]`; `:157` - count unchanged; `:163` - `[tuple(s) for s in stamps] == [(None, None), (None, None)]` | PASS |
| C13 | recall shows the question and no answer; the answer appears only after the confidence submit resolves; grading the recall moves to the next attempt with an empty draft | vitest `recall answer appears only after a confidence submit resolves`, `grading a recall moves on to the explanation with an empty draft` passed | `frontend/tests/checkpoint-dialog.test.tsx:160` - `queryByText(SECRET)).toBeNull()`; `:178` - `findByText(SECRET)`; `:212` - `expect(grades).toEqual([{ rating: 3 }])`; `:217` - `expect(explanation.value).toBe("")` | PASS |
| C14 | recall grade 1: FSRS advance, one log row (1, confidence, assisted=false), review_log_id linked, study day +1 | pytest `grade_recall_reviews_card_with_confidence_unassisted` passed | `backend/tests/test_application_checkpoints.py:237` - `items.get_scheduling(card.id) == expected`; `:239` - `== [(1, 2, False)]`; `:246` - `linked == log_id`; `:252` - `reviews == 1` | PASS |
| C15 | grade before response → 409, no log row; grading a recall whose card was deleted → 404, no row, attempt left ungraded | pytest `grade_before_response_is_409`, `grade_on_a_deleted_card_is_404_and_leaves_the_attempt_ungraded` passed | `backend/tests/test_web_checkpoints.py:278` - `== 409`; `:279` - `_log_count(db_conn) == before`; `:501` - `resp.status_code == 404`; `:505` - `graded is None`; `:506` - `_log_count(db_conn) == before` | PASS |
| C16 | a sequential double grade leaves one row; the second → 409 | pytest `second_grade_is_409_one_log_row` passed | `backend/tests/test_web_checkpoints.py:291` - `== 200`; `:293` - `== 409`; `:297` - `[r.rating for r in rows] == [3]` | PASS |
| C17 | concurrent claims on separate connections have one winner | pytest `concurrent_grade_claim_has_one_winner` passed | `backend/tests/test_repositories_checkpoints.py:77` - `(won_first, won_second) == (True, False)` | PASS |
| C18 | explain 1/2/3 reviews **the caller's checkpoint card**, minting one when absent; explain 4/0 → 422; recall accepts 4, refuses 5 with 422 and no log row | pytest `grade_explain_mints_and_reviews_checkpoint_card` [3], `explain_grade_rating_bounds` [4], `recall_grade_rating_bounds` [2] passed | `backend/tests/test_application_checkpoints.py:276` - `card.origin == QuizItemOrigin.CHECKPOINT`; `:277` - `== [rating]`; `backend/tests/test_web_checkpoints.py:311-312`; `:463`; `:467`. The round-4 owner gap is closed: `backend/tests/test_application_checkpoints.py:403` - `graded.quiz_item_id not in {card.id for card in decoys}` with a stranger's checkpoint card on the sample section (M23 killed). **Gap:** "the caller's checkpoint card" is unproven against the caller's own generated card on the same section. No explain-grade test seeds a non-checkpoint card on the anchor (`rg -n "add_card\(" backend/tests/test_application_checkpoints.py`: the only non-checkpoint seeds are in the C5 start tests, `:168-200`, and C14, `:227`, none of which grade an explanation). M37, which drops `quiz_items.origin == CHECKPOINT` at `repositories.py:2028`, survived 51 tests. In the product, the explanation's grade would review the learner's recall card, and no checkpoint card would be minted | FAIL |
| C19 | minted card shape and owner on the sample; answer = the first feedback citation's quote, cut, else the first chunk; scheduled `initial()` before review | pytest `minted_card_shape_and_owner_on_sample`, `minted_card_falls_back_to_first_chunk` passed | `backend/tests/test_application_checkpoints.py:307` - `[c.quote for c in responded.citations] == [CHUNKS[2], CHUNKS[1]]`; `:312` - `card.user_id == user.id`; `:318` - `card.answer == CHUNKS[2][:_MAX_CARD_CHARS]`; `:332` - `initial()` snapshot; `:349` - fallback `CHUNKS[0]` | PASS |
| C20 | an existing checkpoint card of the caller's is reused, the count stays 1, the text is unchanged; **new:** a stranger's card on the same section and the caller's stale, other-anchor and other-book checkpoint cards are never reused | pytest `second_checkpoint_reuses_existing_card`, `reuse_skips_checkpoint_cards_that_are_not_the_callers_on_this_section` passed | `backend/tests/test_application_checkpoints.py:359` - same `quiz_item_id`; `:365` - `count == 1`; `:367` - text unchanged; `:403` - `graded.quiz_item_id not in {card.id for card in decoys}`; `:405` - `(minted.user_id, minted.source_id, minted.anchor) == (user.id, source_id, ANCHOR)`; `:407` - `_log_rows(db_conn, card.id) == []` for every decoy. M23, M34, M35 and M36 were each killed by this test | PASS |
| C21 | one answer-mode call, evidence capped at 6, least-covered first, citations = grounded | pytest `explain_calls_answer_mode_once_least_covered_first`, `explain_drops_ungrounded_citations` passed | `backend/tests/test_application_checkpoints.py:434` - `len(generation.calls) == 1`; `:436` - `MODE_ANSWER`; `:439` - `len(snippets) == 6`; `:442-443` ordering; `:445`, `:465` grounded quotes | PASS |
| C22 | the explain JSON keys are exactly feedback/citations(anchor, section_path, quote); the dialog shows no grade wording | pytest `explain_payload_keys_have_no_score`, vitest `feedback step shows no grade wording` passed | `backend/tests/test_web_checkpoints.py:332` - `set(body) == {"feedback", "citations"}`; `:335` citation keys; `:336` - `_GRADE_WORDS.search(...) is None`; `frontend/tests/checkpoint-dialog.test.tsx:388` - `dialog.textContent).not.toMatch(...)` | PASS |
| C23 | not-found / raise / ungrounded → fallback quoting the least-covered chunk; a raise debits nothing, a completed call debits | pytest `explain_fallback_on_not_found_raise_or_ungrounded` [3] passed | `backend/tests/test_application_checkpoints.py:494` - `== [CHUNKS[1]]`; `:498` - `row is None`; `:501` - `row.usd_micros == 3000` | PASS |
| C24 | a blank explanation makes no generate call and quotes the least-covered chunk | pytest `blank_explanation_skips_generation` passed | `backend/tests/test_application_checkpoints.py:520` - `== [CHUNKS[0]]`; `:522` - `generation.calls == []` | PASS |
| C25 | at the cap → 429, paused → 503, responded_at stays NULL; in both cases the dialog shows the catalog copy for that status (never the backend's detail) with the draft kept | pytest `explain_budget_exhausted_429_paused_503`, vitest `a refused explanation (429) …`, `a refused explanation (503) …` passed | `backend/tests/test_web_checkpoints.py:361` - `== 429`; `:362` - `== 503`; `:368` - `== [None, None]`; `frontend/tests/checkpoint-dialog.test.tsx:221-222` - cases `[429, …, "Too many requests. …"]`, `[503, "AI is paused.", "The server had a problem. Please try again."]` (the `status.rateLimited` and `status.server` copies, `frontend/messages/en.json:20-21`); `:228` - the stub returns `status`; `:239` - alert `toBe(copy)`; `:240` - `queryByText(detail)).toBeNull()`; `:245` - draft kept. M26b was killed on the 503 case at `:240` | PASS |
| C26 | usage debited as KIND_GENERATION, ask_count untouched | pytest `explain_debits_usage_as_generation` passed | `backend/tests/test_application_checkpoints.py:543` - `row.usd_micros == budget.usage_micros(usage, None) == 2000`; `:544` - `row.ask_count == 0` | PASS |
| C27 | feedback renders quote and path, then exactly Missed it/Partly/Got it grading 1/2/3; confidence 1/2/3 sent | vitest `feedback quotes passages then offers three self-assessments`, `self-assessment` [3], `is sent as` [3] passed | `frontend/tests/checkpoint-dialog.test.tsx:361-362` - quote and path; `:366` - `toEqual(["Missed it", "Partly", "Got it"])`; `:419` - `expect(grades).toEqual([{ rating }])`; `:448` - `expect(sent).toEqual([{ response: "workers specialise", confidence }])` | PASS |
| C28 | Just explain is link/ghost, confidence is primary, no request until used; using it sends one reveal, shows passage + path, removes the action, keeps the explanation and confidence | vitest `just explain is a secondary action on the explain step`, `just explain shows the passage and still asks for the explanation` passed | `frontend/tests/checkpoint-dialog.test.tsx:298` - `data-variant` `"link"`; `:306` - `toHaveBeenCalledTimes(1)`; `:332` - passage; `:333` - section path; `:334` - `reveals` length 1; `:336` - action gone; `:337` - textbox kept; `:339` - feedback after `Sure` | PASS |
| C29 | reveal stamps revealed_at and returns the first chunk; a repeated reveal returns the same passage and keeps the first stamp | pytest `reveal_stamps_and_returns_first_chunk`, `second_reveal_keeps_the_first_stamp` passed | `backend/tests/test_web_checkpoints.py:383` - `resp.json()["passage"] == CHUNKS[0]`; `:389` - `revealed is not None`; `:404` - `== [200, 200]`; `:405` - `first.json() == second.json()`; `:407` - `scalar_one() == first_stamp` | PASS |
| C30 | reveal on a recall attempt or after a response → 409, unchanged | pytest `reveal_409_on_recall_or_after_response` passed | `backend/tests/test_web_checkpoints.py:423` - `== (409, 409)`; `:429` - `== [None, None]` | PASS |
| C31 | revealed → assisted=true, unrevealed → false; the grade route accepts no client `assisted` | pytest `revealed_explain_grade_is_assisted`, `unrevealed_explain_grade_is_unassisted`, `grade_refuses_a_client_assisted_field` passed | `backend/tests/test_application_checkpoints.py:610` - `== [(3, 3, True)]`; `:619` - `== [(3, 3, False)]`; `backend/tests/test_web_checkpoints.py:483` - `== 422`; `:484` - `_log_count(db_conn) == before` | PASS |
| C32 | `SubmitReview` requires `assisted` and stores it; the migration leaves existing rows NULL | pytest `submit_review_requires_assisted_and_stores_it`, `checkpoint_migration_leaves_existing_review_log_unrecorded` passed | `backend/tests/test_application_reviews.py:1105` - `pytest.raises(TypeError)`; `:1116` - `== [(3, 2, True), (1, None, False)]`; `backend/tests/test_migrations.py:4154` - `tuple(row) == (None, None)` | PASS |

Every new proof resolves to a test this fix added (`git diff --stat 2c69997..9fcf165`: +39, +31 and a parametrized rewrite across the touched test files).

## Coverage

Verified at 9fcf165 for the rows whose authority this fix touched, and for the three that were not PASS in round 4. Every other row is carried from 2c69997, and its proofs re-ran green at 9fcf165.

| Set (size) | Recomputed from | Member -> proof | Unproven |
| --- | --- | --- | --- |
| create statuses (5) | plan Surface (carried) | 201 C8 · 401/403 C42 · 404 C8 · 422 C8 | - |
| response statuses (8) | plan Surface (carried) | 200 C9 · 401/403 C42 · 404 C12 · 409 C10 · 422 C11 · 429/503 C25 | - |
| reveal statuses (5) | plan Surface (carried) | 200 C29 · 401/403 C42 · 404 C12 · 409 C30 | - |
| grade statuses (6) | plan Surface (carried) | 200 C16/C18 · 401/403 C42 · 404 C12, C15 `test_web_checkpoints.py:501` · 409 C15/C16 · 422 C18, C31 | - |
| refused transitions (6) | Landing door 1 (carried) | respond-twice C10 · respond lost to a concurrent claim C10 `test_application_checkpoints.py:592` · grade-unresponded C15 · grade on a deleted card C15 `test_web_checkpoints.py:505` · grade-twice C16/C17 · reveal-after-response C30 | - |
| recall card selection filters (6) | `repositories.py:2000-2016` (carried) | owner · source and anchor · stale · flagged · checkpoint origin, all C5 | - |
| checkpoint-card reuse lookup filters (6) | recomputed from the code, the five predicates at `backend/app/infrastructure/db/repositories.py:2025-2029`, plus reuse-when-present; AC 20 "the caller's active checkpoint card on that source and anchor" | reuse when present C20 `test_application_checkpoints.py:359` · owner `:403` (M23 killed) · source `:403` (M34 killed) · anchor `:403` (M35 killed) · status active `:401` (M36 killed) | origin = CHECKPOINT (`:2028`): the caller's generated card on the same section is never seeded before an explain grade; M37 survived. Round 4 enumerated five members and left this one out |
| dialog error copy per budget refusal (2) | C25's clause "in both cases … for that status"; `statusClassOf` in `frontend/app/lib/errors.ts:115-116` | 429 → `status.rateLimited` `checkpoint-dialog.test.tsx:221`, `:239` · 503 → `status.server` `:222`, `:239`, detail hidden `:240` (M26b killed), draft kept `:245` | - |
| dialog 401 routing (2) | plan Observable "unauthorised state - the reader's `onRequireAuth` 401 path"; now claimed by C2 | dialog calls `onRequireAuth` `checkpoint-dialog.test.tsx:270` (M27 killed in round 4) · reader passes it to the dialog `chapter-reader.test.tsx:2334` (M33 killed) | - |
| attempt states (4) | plan domain term (carried) | created C5 · revealed C29 · responded C9 · graded C14 | - |
| attempt kinds (2) | `kind IN ('recall','explain')` (carried) | recall C14 · explain C18 | - |
| prediction values (4) | Landing door 6 (carried) | 1/2/3/null C4 `:140` | - |
| confidence button → value (3) | Landing door 6 (carried) | 1/2/3 C27 `:448` | - |
| explain self-assessment → rating (3) | Landing door 6 (carried) | 1/2/3 C27 `:419` | - |
| dialog explain-step states (2) | AC 28–29 (carried) | unrevealed C28 · revealed C28 | - |
| explain generation outcomes (5) | AC 21–24 (carried) | grounded C21 · ungrounded/not-found/raise C23 · blank C24 | - |
| minted card passage source (2) | AC 19 (carried) | first citation C19 `:318` · first-chunk fallback C19 `:349` | - |
| budget refusals, backend (2) | AC 25 (carried) | exhausted `test_web_checkpoints.py:361` · paused `:362` | - |
| assisted values written (3) | Landing door 2 (carried) | true/false C31 · pre-cycle NULL C32 | - |
| 404 indistinguishability | AC 12 (carried) | C12 `test_web_checkpoints.py:260` | - |
| migration chain (1 head) | `0032_section_checkpoints.py:34-35` (carried) | C32 `test_migrations.py:4154` | - |
| doors (6) | plan Landing (carried) | 1 C5/C17 · 2 C31/C32 · 3 C19/C20 · 4 C21 · 5 C8/C12 · 6 C4, C27 | - |
| startup config: checkpoint router mounted (2 assemblies) | carried from 2c69997 | `backend/app/main.py:134` · `quiz_client` via `create_app` (`tests/conftest.py:259`) | - |

## Test policy rows

The fix touched only test files. The first row's expectation depends on the reuse-lookup coverage, so it was re-judged at 9fcf165. The step-machine row's member gap from round 4 is closed. The other two rows are carried from 2c69997.

| Row | Files it classifies | Required proof | Expectation met |
| --- | --- | --- | --- |
| Decides: card selection, guards, assisted, evidence order, fallback, mint-or-reuse | `backend/app/application/checkpoints.py` | own layer vs Postgres and real FSRS, present | yes for its listed members, with reuse owner, source, anchor and status now asserted (`test_application_checkpoints.py:403`). The origin member of mint-or-reuse is the coverage row above, which is the one open item |
| Entry point: validation, status mapping | `backend/app/infrastructure/web/checkpoints.py` | HTTP boundary, present | yes (carried from 2c69997; file untouched) |
| Repository conditional updates | `SqlAlchemyCheckpointRepository.claim_response`, `claim_grade`, `reveal` | two-connection race, plus once-only stamps | yes (carried from 2c69997; untouched) |
| Step machine: what is visible when | `frontend/app/components/checkpoint-dialog.tsx` | component test, present | yes - the error state is now asserted for both 429 and 503 (`checkpoint-dialog.test.tsx:239-245`) |

Swept `existing` rows re-read: the plan's Observable "unauthorised state → the reader's `onRequireAuth` path" is wired (`chapter-reader.tsx:1006`), and it is now asserted (`chapter-reader.test.tsx:2334`).

## Faults injected

Verified at 9fcf165. Isolation worked like this:

- a scratch `git worktree add --detach <scratchpad>/verify-wt HEAD`
- a fresh `uv sync --extra dev`, with `app` confirmed to import from the scratch path
- frontend `node_modules` symlinked
- runs used `learny_test_checkpoint`, sequentially, never at the same time as a real-tree run

The scratch baselines were green: the two reuse tests gave 2 passed, the dialog refusal gave 2 passed, and the reader checkpoint tests gave 3 passed.

Each mutant was an exact-anchor replacement that had to match exactly once. It ran against its covering test, then was reverted with `git checkout`, and the scratch porcelain was confirmed clean apart from the symlink.

The real tree's `git status --porcelain` was empty before and empty after both scratch sessions. When the runs finished, the symlink was removed and the scratch worktree was removed and pruned (`git worktree list` shows no `verify-wt`).

The cap of five was exceeded on purpose. Each of the reuse lookup's five predicates is a separate member that C18 and C20 claim.

| Mutation | Location | Killed |
| --- | --- | --- |
| M23 drop `quiz_items.user_id == user_id` in `active_checkpoint_card` | `backend/app/infrastructure/db/repositories.py:2025` | yes - `reuse_skips_…` failed at `test_application_checkpoints.py:401`: the stranger's card was picked and the grade raised `QuizItemNotFound` (`reviews.py:53`) |
| M34 drop `quiz_items.source_id == source_id` | `repositories.py:2026` | yes - `reuse_skips_…` failed at `:403` (the other book's card was reused) |
| M35 drop `quiz_items.anchor == anchor` | `repositories.py:2027` | yes - `reuse_skips_…` failed at `:403` (the other anchor's card was reused) |
| M36 drop `quiz_items.status == ACTIVE` | `repositories.py:2029` | yes - `reuse_skips_…` failed at `:401`: the stale card was picked and the grade raised `QuizItemNotReviewable` (`reviews.py:193`) |
| M37 drop `quiz_items.origin == CHECKPOINT` | `repositories.py:2028` | no - survived: `test_application_checkpoints.py`, `test_web_checkpoints.py` and `test_repositories_checkpoints.py` gave 51 passed |
| M26b the dialog renders the backend `detail` for status ≥500 | `frontend/app/components/checkpoint-dialog.tsx:121` | yes - `a refused explanation (503) …` failed at `checkpoint-dialog.test.tsx:240`; the 429 case stayed green |
| M33 the reader stops passing `onRequireAuth` to the dialog | `frontend/app/components/chapter-reader.tsx:1006` | yes - `hands a checkpoint that finds the session gone…` failed at `chapter-reader.test.tsx:2334` (spy called 0 times) |

## Gate

Verified at 9fcf165.

- Batch-1 named proofs: 53 passed (backend) and 24 passed (frontend), 0 failed.
- Touched-module regression in the real tree: `LEARNY_REQUIRE_DB=1 … pytest tests/test_application_checkpoints.py tests/test_web_checkpoints.py tests/test_repositories_checkpoints.py tests/test_application_reviews.py tests/test_migrations.py` gave 131 passed, 0 failed. `vitest run tests/checkpoint-dialog.test.tsx tests/chapter-reader.test.tsx tests/i18n-parity.test.ts` gave 102 passed, 0 failed.
- `make lint`, exit 0. `ruff check` and `ruff format --check` were clean (348 files). `tsc --noEmit` was clean. `check_commits` reported 23 commits in `origin/main..HEAD`, all OK. Architecture boundaries were clean.
- CI on PR #77 at 9fcf165: `backend-test`, `commits`, `compose-smoke`, `frontend` and `lint` all pass.
- The full local suites were not re-run, because the fix changed no production code and CI runs both suites in full.

## Ranked gaps

1. **The checkpoint-card reuse lookup's origin filter is unproven** (C18 "the caller's checkpoint card, minting one when absent"; Coverage, reuse lookup). The location is `backend/app/infrastructure/db/repositories.py:2028`. M37 survived 51 tests. Generated quiz cards on a section's anchor are the common case, since they are the ones C5 offers as recall attempts. With the filter gone, grading the explanation would review the learner's recall card and mint no checkpoint card, and no test would notice. Fix, test-only: add a `QuizItemOrigin.GENERATED` card owned by the caller on `source_id`/`ANCHOR` to the decoys in `test_reuse_skips_checkpoint_cards_that_are_not_the_callers_on_this_section` (`backend/tests/test_application_checkpoints.py:382`). Then extend C20's enumeration with "or the caller's non-checkpoint card".

Notes, none of which fail the round:

- M23 and M36 are killed by an exception from the grade call (`:401`), not by the reuse assertion at `:403`. For M23 that exception is the defect the round-4 gap described: a 404 on the learner's own grade. The failure is still a failing proof.
- The round-4 stale comment in `test_grade_on_a_deleted_card_is_404_and_leaves_the_attempt_ungraded` is fixed (`test_web_checkpoints.py:490-491`).
- Carried from round 4: the M30 position-counter precision note; M8 and M9 are killed by a downstream crash rather than a clean 422; and C28's "keeps … confidence buttons" is asserted through `Sure` alone.
- `origin/main` is still 8c11ad3, the feature base, so it has not moved since 9fcf165. GitHub reports #77 as `MERGEABLE` / `CLEAN`.

## Round 6 - completed by the resuming session (2026-10-30)

**Verdict**: PASS (batch-1 scope)
**Profile**: standard
**Diff range**: 9fcf165..0ed0280 (round 5 verified through 9fcf165; this range holds the generated-card decoy, the response-language threading, the merge of `main`, the runnable-proof chore and the hidden-card fix)
**Round**: 6 - continued
**Verifier**: the dispatched verifier session was cut off before it closed; the resuming session completed the round inline, so author == verifier for this round (degraded). The fresh-context `pr-review` over PR #77 after this round is the independent pass before merge.

Batch scope: C1–C32 and C42. C33–C41 are batch 2 and out of scope; in `proofs.md` they read "no test ran" until batch 2 builds them, which is expected and is why `check_proofs.py` exits 1 and the completion gate (`validate_verification.py`) is owed at batch-2 completion.

What this round verified:

- The response-language threading (5d087d3) is proven and mutation-tested. C21's four proofs pass at HEAD, and four mutants over the new seam are each killed: dropping the caller's language from the explain-back call, dropping the response route's language resolution, letting `Accept-Language` beat the stored locale, and removing English as the uninstructed locale.
- Round 5's gap (the reuse lookup's origin filter, M37) is closed: the generated-card decoy landed (108fcf1) and the mutant is now killed.
- The round-6 finding is closed by 0ed0280: `active_checkpoint_card` minted past a hidden card only after the fix; grading an explanation could previously have landed on the caller's hidden checkpoint card instead of minting a fresh one. The fix skips flagged checkpoint cards in the reuse lookup and extends `reuse_skips_checkpoint_cards_that_are_not_the_callers_on_this_section`; the flagged-predicate mutant is killed.
- `check_proofs.py` at HEAD 0ed0280 (clean tree, `LEARNY_REQUIRE_DB=1` against this lane's Postgres): 61 pass, 10 fail - the 10 are the batch-2 rows - and mutations 6 killed, 0 survived, 0 blocked.
- CI on PR #77 at 0ed0280: `backend-test`, `commits`, `compose-smoke`, `frontend` and `lint` all pass.

Deviations, recorded plainly:

- This round ran inline (self-verified degraded), because the verifier session died on a provider limit and no sub-agent dispatch completed. Mitigation: every mechanical proof is script-run (`check_proofs.py`), and a fresh-context review runs on the PR before merge.
- Running the script on this machine needed two local fixes to the lean skill's vitest runner: resolving `vitest.cmd`/`npx.cmd` shims through `cmd /c` (bare `subprocess` spawn fails on Windows), and a 120s per-test / 60s hook timeout on the grouped selection run only (the machine was concurrently running other suites; the default 5s timeout turned passing cases into timeout failures). The vitest groups also had to run under Node 24 (`nvm` v24.22.0): the machine's default Node 25 breaks jsdom's `localStorage` in vitest workers, which leaked a stored pt-BR locale across test describes and failed the English checkpoint-invitation tests. CI gates on Node 20 and is green at the same commit, so CI remains the authoritative frontend result. The proof commands in `checks.md` are unchanged.

## Findings

| Finding | Location | Verdict | Closed |
| --- | --- | --- | --- |
| A graded explanation could reuse the caller's hidden (flagged) checkpoint card instead of minting a fresh one | `backend/app/infrastructure/db/repositories.py` `active_checkpoint_card` | real - fixed with covering test | 0ed0280 |
| The reuse lookup's origin filter was unproven (M37 survived; round 5 gap) | `backend/app/infrastructure/db/repositories.py:2028` | real - test-only | 108fcf1 |
| Explain-back made no provider call in the learner's interface language | `backend/app/application/checkpoints.py`, `backend/app/infrastructure/web/checkpoints.py` | real - fixed with tests | 5d087d3 |


## Round 7 - batch 2 (2026-10-31)

**Verdict**: PASS (batch-2 scope)
**Profile**: standard
**Diff range**: origin/main..3d8d97b (e757a9e..3d8d97b: b511281 "record how sure the learner was before the answer showed" + 3d8d97b "show how often feeling sure meant recalling, per book"; 19 files, +749/-40)
**Round**: 7 - batch 2 (S6-S7)
**Verifier**: independent sub-agent (author != verifier)

Batch scope: C33-C41 - confidence capture on review grades (S6) and the per-book calibration view (S7). C1-C32 and C42 are batch 1 (rounds 1-6) and out of scope; they re-ran green inside the same proof run, because `check_proofs.py` executes all of `checks.md`.

Proofs re-derived fresh at HEAD 3d8d97b, real tree, lane Postgres 5434/learny_test with `LEARNY_REQUIRE_DB=1`:

- `check_proofs.py` (with `--mutations`, see Faults): **71 pass, 0 fail**, Tree clean, exit 0. Every one of the 10 batch-2 proof rows ran with 1 test selected and 1 passed - no deselected or skipped selector.
- Build rows from `checks.md`: `ruff check .` + `ruff format --check .` (repo-wide), `npx tsc --noEmit`, `check_commits.py origin/main..HEAD` (2 commits, OK) - all pass.
- Run directly and clean: `uv run ruff check app tests`, `uv run ruff format --check app tests` (325 files already formatted), `python backend/scripts/check_boundaries.py` ("architecture boundaries clean").
- Frontend full suite `npx vitest run`: **1080 passed, 2 failed of 1082** - both failures are the pre-existing `tests/i18n-typed-keys.test.ts` cases (environment note 1); the batch-2 files are green (`review-screen.test.tsx` 46 incl. 3 new, `dock-review-tab.test.tsx` 8 incl. 2 new, plus the touched `chapter-reader`, `reader-panel`, `quiz-client`).

### Checks (C33-C41)

| Check | Claim | Proof run | Evidence | Result |
| --- | --- | --- | --- | --- |
| C33 | While hidden, the review card shows Not sure / Fairly sure / Sure beside Reveal answer; each confidence button reveals the answer | vitest `confidence buttons reveal the answer beside Reveal answer` 1/1 at 3d8d97b | `frontend/tests/review-screen.test.tsx:1174-1177` the group's buttons are exactly the three labels; `:1179` Reveal answer present; `:1180` answer hidden; `:1184`, `:1188`, `:1192` each of the three taps reveals. Production: `frontend/app/components/review-screen.tsx:845-861` (role=group + three buttons + Reveal answer), `:552-555` (`onConfidence` sets confidence and reveals) | PASS |
| C34 | Grading after `Sure` sends `confidence: 3`; grading after `Reveal answer` or Space sends a body with no `confidence` key | vitest `grade carries confidence only when revealed by a confidence tap` 1/1 | `frontend/tests/review-screen.test.tsx:1226` confidence `toBe(3)`; `:1234` `"confidence" in body` false after Reveal answer; `:1238-1242` Space reveals then grades, key still absent. Production: `frontend/app/lib/quiz.ts:312-319` (the key is added only when a confidence was taken), `frontend/app/components/review-screen.tsx:256-260` (`confidence ?? undefined`) | PASS |
| C35 | The review route stores `confidence` 1-3 or NULL and `assisted` from the body (default false); 0 or 4 returns 422 with no log row | pytest `tests/test_web_quiz.py -k review_stores_confidence_and_assisted` 1/1 and `-k review_confidence_out_of_range_422` 1/1 | `backend/tests/test_web_quiz.py:1310` stored `[(2, True)]`; `:1321` a body without the fields stores `[(2, True), (None, False)]`; `:1330` 422 for 0 and 4; `:1332-1337` log count still 0. Production: `backend/app/infrastructure/web/quiz.py:123` (`Field(ge=1, le=3)`), `:126` (`assisted: bool = False`), `:503-504` (both reach `SubmitReview`; the comment notes the schedule never reads them) | PASS |
| C36 | Grading after opening the editor before the reveal sends `assisted: true`; without it `assisted: false` | vitest `editor peek before reveal marks the grade assisted` 1/1 | `frontend/tests/review-screen.test.tsx:1274` editor-peek grade sends `assisted: true`; `:1284` a plain reveal-and-grade sends `false`. Production: `frontend/app/components/review-screen.tsx:402-409` (opening the editor while hidden peeks), `:259` (`assisted: peeked`) | PASS |
| C37 | Calibration returns exactly 3 rows (confidence 1, 2, 3); each counts the caller's not-undone, `assisted=false` log rows with that confidence on the source's cards and how many graded 2+; undone, assisted, NULL-confidence and other-source rows are excluded | pytest `tests/test_web_checkpoints.py -k calibration_counts_unassisted_not_undone_by_level` 1/1 | `backend/tests/test_web_checkpoints.py:603-610` exact JSON `{1: 2/1, 2: 1/1, 3: 1/0}`; the four exclusions are each seeded: undone `:585-586`, assisted `:587`, NULL confidence `:588`, other source `:589-594`. Production: `backend/app/infrastructure/db/repositories.py:1841` (`rating >= 2` recalled), `:1845-1849` (owner, source, not-undone, unassisted, has-confidence), `:1854-1862` (zero-filled 3 rows); `backend/app/application/checkpoints.py:628-632` (`readable_source` then the query) | PASS |
| C38 | Calibration on another learner's source or a missing one returns 404 (identical bodies); without a session 401 | pytest `-k calibration_404_foreign_and_missing` 1/1 | `backend/tests/test_web_checkpoints.py:620-621` both 404; `:622` identical JSON bodies; `:626` 401 after clearing cookies | PASS |
| C39 | On the shared sample, learner A's calibration counts only A's reviews while B has graded sample cards too | pytest `-k calibration_on_sample_is_per_learner` 1/1 | `backend/tests/test_web_checkpoints.py:653-655` both 200; `:656-663` A sees `{1: 0, 2: 0, 3: 2/1}` - B's confidence-2 grade absent; `:664-671` B sees `{1: 0, 2: 1/1, 3: 0}` | PASS |
| C40 | The dock Review tab renders "When you felt Sure, you recalled 8 of 10" per level with attempts, omits zero-attempt levels, and shows no overall percentage | vitest `tests/dock-review-tab.test.tsx -t "calibration lines per level with attempts"` 1/1 | `frontend/tests/dock-review-tab.test.tsx:286-287` both level lines; `:289` the zero-attempt level's words absent; `:293` no `%` anywhere on the tab. Production: `frontend/app/components/dock-review-panel.tsx:110` (filter `attempts > 0`), `:120-125` (the `calibrationLine` copy, `frontend/messages/en.json:260`) | PASS |
| C41 | With all three levels at zero attempts, the tab shows the empty-state copy and no level lines | vitest `-t "calibration empty state"` 1/1 | `frontend/tests/dock-review-tab.test.tsx:301-303` the exact `calibrationEmpty` copy (`frontend/messages/en.json:261`); `:305` no `calibration-lines` node. Production: `frontend/app/components/dock-review-panel.tsx:111-118` | PASS |

### Coverage (batch-2 rows recomputed at 3d8d97b)

| Set (size) | Recomputed from | Member -> proof | Unproven |
| --- | --- | --- | --- |
| `POST /api/quiz-items/{id}/reviews` added-field statuses (2) | plan Surface (batch-2 addition); `web/quiz.py:117-126` | 200 C35 `test_web_quiz.py:1310` · 422 C35 `:1330` | - |
| `GET /api/sources/{id}/calibration` statuses (3) | plan Surface; route `web/checkpoints.py:245-258` | 200 C37 `test_web_checkpoints.py:603` · 401 C38 `:626` · 404 C38 `:620-621` (foreign and missing) | - |
| calibration exclusions (4) | the five predicates at `repositories.py:1845-1849`, plus the 3-row zero-fill `:1854-1862` and the `rating >= 2` recalled rule `:1841` | undone C37 `:585-586` · assisted C37 `:587` · NULL confidence C37 `:588` · other source C37 `:589-594` · per-learner on the shared sample C39 · recalled = rating 2+ C37 `:603-610` (mutant 7 killed) | - |
| confidence values (5, shared row) | carried; C35 adds the review-route members | 1/2/3 stored on the review route C35 `test_web_quiz.py:1310`, `:1321` · 0/4 → 422 on the review route C35 `:1330` (checkpoint-surface members remain C9, C11, C14, C27) | - |
| doors (6) | plan Landing door 6 | vocabulary C4, C27, C33 - C33 now covers the review card's Not sure / Fairly sure / Sure (`review-screen.test.tsx:1174-1177`) | - |

No unproven member in any batch-2 row. One honesty note: the `confidence.isnot(None)` predicate (`repositories.py:1849`) has no behavior-changing mutant - `group_by(confidence)` keeps the NULL group out of the 1..3 rows even without it - so the member is proven by exclusion at the boundary (`test_web_checkpoints.py:588` seeded, `:603-610` excluded), not by a killed mutation.

### Faults injected (batch-2 surface)

Two layers: (a) manual exact-anchor edits in a detached scratch worktree (`git worktree add --detach .../wt-ver-r7 3d8d97b`, real `.venv` via `UV_PROJECT_ENVIRONMENT`, `node_modules` junctioned; baselines green first; each fault reverted with `git checkout --` and the scratch porcelain confirmed clean), and (b) the same spec run through `check_proofs.py --mutations` (mutate.py in the real tree with journal + byte-for-byte restore), which wrote the `## Mutations` table into `proofs.md`. The real tree ended clean apart from `.specs` artifacts.

| Mutation | Location | Killed |
| --- | --- | --- |
| The review route accepts an out-of-range confidence (`ge=1, le=3` dropped) | `backend/app/infrastructure/web/quiz.py:123` | yes - `test_review_confidence_out_of_range_422` fails: 0/4 pass pydantic and die on `ck_review_log_confidence_range` (IntegrityError) instead of 422 (manual + script) |
| The review route stores the rating as the confidence (`confidence=body.confidence` → `confidence=body.rating`) | `backend/app/infrastructure/web/quiz.py:504` | yes - `test_review_stores_confidence_and_assisted` fails at `test_web_quiz.py:1310`: `[(3, True)] != [(2, True)]` (manual + script) |
| Calibration counts assisted grades as unaided (predicate → tautology) | `backend/app/infrastructure/db/repositories.py:1848` | yes - C37 fails at `test_web_checkpoints.py:603` (level 3 attempts 1 → 2) (script) |
| Calibration counts undone grades (predicate → tautology) | `backend/app/infrastructure/db/repositories.py:1847` | yes - C37 fails at `:603` (script) |
| Calibration counts another learner's reviews (`user_id` predicate dropped) | `backend/app/infrastructure/db/repositories.py:1845` | yes - `test_calibration_on_sample_is_per_learner` fails at `:656`: B's confidence-2 row appears in A's response (manual + script) |
| Calibration counts another book's reviews (`source_id` predicate dropped) | `backend/app/infrastructure/db/repositories.py:1846` | yes - C37 fails at `:603` (level 3 attempts 1 → 2 from the other-source row) (script) |
| A lapse counts as recalled (`rating >= 2` → `rating >= 1`) | `backend/app/infrastructure/db/repositories.py:1841` | yes - C37 fails at `:603` (level 1 recalled 1 → 2) (script) |
| The review client serializes an absent confidence as `null` (key no longer conditional) | `frontend/app/lib/quiz.ts:316-318` | yes - `grade carries confidence only when revealed by a confidence tap` fails at `review-screen.test.tsx:1234`: `"confidence" in body` is true (manual + script) |
| The dock shows levels with no attempts (filter dropped) | `frontend/app/components/dock-review-panel.tsx:110` | yes - `calibration lines per level with attempts` fails at `dock-review-tab.test.tsx:289` (a "Not sure" line renders) (manual + script) |
| Every review grade is marked assisted (`assisted: peeked` → `assisted: true`) | `frontend/app/components/review-screen.tsx:259` | yes - `editor peek before reveal marks the grade assisted` fails at `review-screen.test.tsx:1284` (script) |

`checks.md` declares `Mutations: 5`; 10 were injected because the batch-2 predicates are separate members (the round-5 precedent). 10 killed, 0 survived, 0 blocked (`proofs.md` `## Mutations`). One earlier manual variant - assigning `payload.confidence = body.confidence` unconditionally - survived, and rightly: `JSON.stringify` drops `undefined` keys, so the wire format is unchanged and no test can discriminate an equivalent mutant; it was replaced with the non-equivalent null-serialization fault above and is recorded here as an observation, not a sensor failure.

### Environment notes (verified this round, not charged to batch 2)

- i18n-typed-keys: the 2 failures reproduce identically on pristine `origin/main` (e757a9e, detached A/B worktree): `tsc rejects a key missing from en` and `tsc accepts a key that exists in en` fail with empty tsc output (`tests/i18n-typed-keys.test.ts:51`, `:58`). The harness spawns `execFileSync("npx", ...)`, a bare spawn that fails on this Windows machine. Not batch 2's; CI runs the same tests green on Linux.
- `test_worker_task_duration.py::test_overlapping_tasks_each_report_their_own_duration` failed standalone on this machine (`assert 408.487 < 200.0`, a timing ceiling) **and** failed the same way on the pristine `origin/main` A/B worktree - confirmed environmental, not batch 2's.
- `check_proofs.py` needed `frontend/node_modules/.bin` on PATH: the `cd frontend && vitest run ...` proof form cannot resolve `vitest` when the harness spawns it directly on Windows (WinError 2). Environment-only workaround; no repo file changed.
- Suites on this lane ran while sibling lanes were also busy; wall-clock times are inflated, and the worker-duration result above is consistent with that load.

### Observations

- The DB CHECK `ck_review_log_confidence_range` is a second line of defense behind pydantic's `ge=1, le=3` (mutant 1 died on it, not on a clean 422). Defense in depth, already recorded as door 2's shape.
- The dock now renders the calibration block even when `total === 0` (the panel restructured its `nothingDue` branch, `dock-review-panel.tsx:154-181`); C40/C41 exercise both shapes and the due-count behavior is covered by the pre-existing dock tests, which stayed green.
- `source_calibration` joins the caller's log rows to `quiz_items.user_id == user_id`, so a review of a card the learner does not own cannot enter any count even before the source scoping; C39 pins the shared-sample case end to end.
- The full backend suite (3476 tests) was not re-run this round; the brief's proof set for batch 2 is the named proofs plus the grouped files (`test_web_quiz.py`, `test_web_checkpoints.py`, `test_application_checkpoints.py`, `test_application_reviews.py`, `test_migrations.py`, `test_repositories_checkpoints.py`), which `check_proofs.py` ran in full. CI carries the complete suite.

### Gate

- `check_proofs.py` at 3d8d97b: 71 pass, 0 fail; mutations 10 killed, 0 survived, 0 blocked; Tree clean; exit 0.
- `ruff check`, `ruff format --check`, `check_boundaries.py`, `tsc --noEmit`, `check_commits.py origin/main..HEAD`: all exit 0.
- Frontend suite: 1080 passed, 2 failed (environment note 1), CI-authoritative for those 2.
- Findings: none new this round - no surviving non-equivalent mutant, no unproven coverage member. The cumulative `## Findings` table above is unchanged.
- `validate_verification.py` exits 0 with one WARN: it matches the word "self-verified" in the historical round-6 and Handoff records (that round ran inline). Round 7 itself is an independent sub-agent pass (author != verifier).
