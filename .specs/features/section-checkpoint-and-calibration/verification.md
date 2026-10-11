# section-checkpoint-and-calibration verification

**Verdict**: FAIL
**Profile**: standard
**Diff range**: 8c11ad3..2c69997 (feature base after the rebase onto `main` at PR #78). The change under review is 7bffc79..2c69997, plus the rebase that rewrote 2281250..992176c into 8c11ad3..7bffc79.
**Round**: 4 - scoped
**Verifier**: independent sub-agent (author != verifier)

Batch scope: C1–C32 and C42. C33–C41 are batch 2 and out of scope.

Every batch-1 proof is green at 2c69997. Every amended clause (C10, C13, C15, C25 for 429, C29) is proven, and its mutant was killed. The round still fails, for two reasons.

1. A query this diff moved, `SqlAlchemyQuizItemRepository.active_checkpoint_card`, has no test for its owner filter. Dropping `quiz_items.user_id == user_id` survives every checkpoint test (M23).
2. C25's new dialog clause covers 429 and 503, but only 429 is proven. A dialog that shows the backend `detail` for 5xx survives (M26b).

A third mutant also survived (M33): the reader no longer passes `onRequireAuth` to the dialog. No check claims that wiring, so it ranks below the other two.

Rebase scope reviewed with `git range-diff 2281250..992176c 8c11ad3..7bffc79`. Only `be26aaf` changed. In it, the migration was renamed `0031` → `0032_section_checkpoints` (revises `0031_user_locale_preferences`), the `metadata.py` comment and placement moved, and the `test_migrations.py` downgrade targets were updated. The other ten commits are identical (`=`).

Fix scope reviewed with `git diff 7bffc79..2c69997`. It touches these files:

- `backend/app/application/checkpoints.py`, `domain/ports.py` and `infrastructure/db/repositories.py`
- `frontend/app/components/checkpoint-dialog.tsx`, `chapter-reader.tsx` and `app/lib/checkpoints.ts`
- `frontend/messages/{en,pt-BR}.json`
- the three test files
- the spec docs

## Binding sources

Carried from 47d200e (via 7bffc79). Step 1 (`ui`) does not run under `standard`. The binding sources are the ROADMAP v8 row and the research synthesis row #6 with its do-not-build list. They set scope and non-goals, not a UI design. The i18n change alters copy delivery, not composition. No contradiction.

## Checks

Verified at 2c69997. Every batch-1 proof was re-run in full at `HEAD`, in the real tree.

- Backend, one invocation: `cd backend && LEARNY_REQUIRE_DB=1 LEARNY_TEST_DATABASE_URL=…/learny_test_checkpoint uv run pytest tests/test_application_checkpoints.py tests/test_application_reviews.py tests/test_migrations.py tests/test_repositories_checkpoints.py tests/test_web_checkpoints.py -v -k "<all 39 batch-1 names>"`. Result: 52 passed, 78 deselected, exit 0. Each of the 39 names appears individually as PASSED, parametrized cases included. The three new names are `explain_lost_to_a_concurrent_response_never_calls_the_provider`, `grade_on_a_deleted_card_is_404_and_leaves_the_attempt_ungraded` and `second_reveal_keeps_the_first_stamp`.
- Frontend, one invocation: `cd frontend && npx vitest run tests/chapter-reader.test.tsx tests/checkpoint-dialog.test.tsx --reporter=verbose -t "<14 names>"`. Result: 21 passed, 76 skipped, exit 0. Each name appears individually, including the new `grading a recall moves on to the explanation with an empty draft` and `a refused explanation shows catalog copy, not the server's detail, and keeps the draft`.

Citations were refreshed in every touched test file, and in the files the rebase moved:

- `checkpoint-dialog.test.tsx`: +1 before `:181`, +108 after.
- `test_application_checkpoints.py`: +1, then +53 after `:506`.
- `test_web_checkpoints.py`: +1, then +18 after `:389`.
- `chapter-reader.test.tsx`: +1 from the rebase.
- `test_migrations.py`: moved by the rebase.

| Check | Claim | Proof run | Evidence | Result |
| --- | --- | --- | --- | --- |
| C1 | one invite, only after the ≥150-word section, placed after its body | vitest `checkpoint invitation only after sections of at least 150 words` passed | `frontend/tests/chapter-reader.test.tsx:2240` - `expect(invites).toHaveLength(1)`; `:2243` - `expect(longSection.nextElementSibling).toBe(invites[0])` | PASS |
| C2 | the tap opens the dialog on the prediction step for that anchor; no request before a choice | vitest `opens on the prediction step without calling the API`, `starts the checkpoint for the section whose invitation was tapped` passed | `frontend/tests/checkpoint-dialog.test.tsx:116` - `expect(fetchMock).not.toHaveBeenCalled()`; `frontend/tests/chapter-reader.test.tsx:2303` - `expect(started).toEqual([{ anchor: S2, prediction: null }])` | PASS |
| C3 | closing mid-flow unmounts, the chapter stays intact, no further request | vitest `closing mid-flow sends nothing more` passed | `frontend/tests/checkpoint-dialog.test.tsx:460` - `expect(onClose).toHaveBeenCalledTimes(1)`; `:461` - `expect(fetchMock).toHaveBeenCalledTimes(1)`; unmount `frontend/tests/chapter-reader.test.tsx:2257` | PASS |
| C4 | Little/Some/Most/Skip → 1/2/3/null | vitest `prediction choices map to 1, 2, 3 and null` (4 cases) passed | `frontend/tests/checkpoint-dialog.test.tsx:140` - `expect(bodies).toEqual([{ anchor: "ch1#s1", prediction: expected }])` | PASS |
| C5 | ≤3 owned, active, unflagged, non-checkpoint cards on the anchor, due ascending then id, then one explain; the exclusions hold | pytest `start_selects_due_first_owned_active_cards_on_anchor`, `start_caps_recall_attempts_at_three` passed | `backend/tests/test_application_checkpoints.py:180` - a stranger's card on the same source and anchor; `:185` - `assert kinds == [(RECALL, sooner.id), (RECALL, later.id), (EXPLAIN, None)]`; `:208` - `recalls == [cards[4].id, cards[3].id, cards[2].id]`. The query moved to `QuizItemRepository.recall_cards` (`repositories.py:2000`), and M22 was killed at `:185` | PASS |
| C6 | no eligible cards → exactly one explain attempt | pytest `start_without_cards_has_only_explain` passed | `backend/tests/test_application_checkpoints.py:218` - `[a.kind …] == [CheckpointAttemptKind.EXPLAIN]` | PASS |
| C7 | the create payload has no answer/excerpt/passage keys or text | pytest `create_payload_carries_no_answers` passed | `backend/tests/test_web_checkpoints.py:92` - `"A distinctive secret answer" not in raw`; `:97` - `assert key not in json.dumps(body)`; `:100` - attempt keys `{attempt_id, kind, question}` | PASS |
| C8 | 404 with nothing persisted for missing/foreign/no-section; sample → 201; prediction 0/4 or empty anchor → 422, nothing persisted | pytest `create_404_cases_persist_nothing`, `create_on_shared_sample_returns_201`, `create_validation_422` [3] passed | `backend/tests/test_web_checkpoints.py:114` - `== [404, 404, 404]`; `:116` - count unchanged; `:127` - `== 201`; `:448` - `resp.status_code == 422`; `:449` - `_checkpoint_count(db_conn) == before` | PASS |
| C9 | a recall response stores response and confidence=2, returns answer/excerpt/anchor/path; an empty response is accepted | pytest `recall_response_reveals_answer_after_storing` passed | `backend/tests/test_web_checkpoints.py:179` - `resp.json() == {"answer": …, "source_excerpt": …, "anchor": ANCHOR, "section_path": …}`; `:190` - `tuple(stored) == ("", 2)` | PASS |
| C10 | second response → 409, the first is kept; **new:** an explanation that loses the claim to a concurrent response is refused without calling the provider | pytest `second_response_is_409_and_keeps_first`, `explain_lost_to_a_concurrent_response_never_calls_the_provider` passed | `backend/tests/test_web_checkpoints.py:204` - `== 409`; `:210` - `tuple(stored) == ("one", 1)`; `backend/tests/test_application_checkpoints.py:548` - `pytest.raises(CheckpointAttemptConflict)`; `:553` - `generation.calls == []`; `:559` - `tuple(stored) == ("the winner", 2)`. The new clause names no status, so the application level settles it. M20 (generate before claim) was killed at `:553` | PASS |
| C11 | no confidence / 0 / 4 / 4001 chars → 422, responded_at NULL | pytest `response_validation_422` [4] passed | `backend/tests/test_web_checkpoints.py:229` - `== 422`; `:235` - `responded is None` | PASS |
| C12 | response/reveal/grade on a foreign and on a random attempt → identical 404 bodies | pytest `attempt_routes_404_for_foreign_and_missing` passed | `backend/tests/test_web_checkpoints.py:256` - `== [404, 404, 404]`; `:260` - `[len(texts) for texts in bodies.values()] == [1, 1, 1]` | PASS |
| C42 | the four POSTs → 401 without a session and 403 without CSRF, writing nothing | pytest `new_routes_require_session_and_csrf` passed | `backend/tests/test_web_checkpoints.py:155` - `== [403, 403, 403, 403]`; `:156` - `== [401, 401, 401, 401]`; `:157` - count unchanged; `:163` - `[tuple(s) for s in stamps] == [(None, None), (None, None)]` | PASS |
| C13 | recall shows the question and no answer; the answer appears only after the confidence submit resolves; **new:** grading the recall moves to the next attempt with an empty draft | vitest `recall answer appears only after a confidence submit resolves`, `grading a recall moves on to the explanation with an empty draft` passed | `frontend/tests/checkpoint-dialog.test.tsx:160` - `queryByText(SECRET)).toBeNull()`; `:167` - still null in flight; `:178` - `findByText(SECRET)`; `:211` - `findByTestId("checkpoint-ask-explain")`; `:212` - `expect(grades).toEqual([{ rating: 3 }])`; `:217` - `expect(explanation.value).toBe("")` (the recall draft was `"eighteen?"`, `:206`). M31 (draft kept on advance) was killed at `:217` | PASS |
| C14 | recall grade 1: FSRS advance, one log row (1, confidence, assisted=false), review_log_id linked, study day +1 | pytest `grade_recall_reviews_card_with_confidence_unassisted` passed | `backend/tests/test_application_checkpoints.py:237` - `items.get_scheduling(card.id) == expected`; `:239` - `== [(1, 2, False)]`; `:246` - `linked == log_id`; `:252` - `reviews == 1` | PASS |
| C15 | grade before response → 409, no log row; **new:** grading a recall whose card was deleted → 404, no row, attempt left ungraded | pytest `grade_before_response_is_409`, `grade_on_a_deleted_card_is_404_and_leaves_the_attempt_ungraded` passed | `backend/tests/test_web_checkpoints.py:278` - `== 409`; `:279` - `_log_count(db_conn) == before`; `:502` - `resp.status_code == 404`; `:506` - `graded is None`; `:507` - `_log_count(db_conn) == before`. The FK is `ON DELETE SET NULL` (`0032_section_checkpoints.py:122`), so the attempt row survives and `:506` is meaningful. M21 (check moved after the claim) was killed at `:506` | PASS |
| C16 | a sequential double grade leaves one row; the second → 409 | pytest `second_grade_is_409_one_log_row` passed | `backend/tests/test_web_checkpoints.py:291` - `== 200`; `:293` - `== 409`; `:297` - `[r.rating for r in rows] == [3]` | PASS |
| C17 | concurrent claims on separate connections have one winner | pytest `concurrent_grade_claim_has_one_winner` passed | `backend/tests/test_repositories_checkpoints.py:77` - `(won_first, won_second) == (True, False)` | PASS |
| C18 | explain 1/2/3 reviews **the caller's** checkpoint card, minting one when absent; explain 4/0 → 422; recall accepts 4, refuses 5 with 422 and no log row | pytest `grade_explain_mints_and_reviews_checkpoint_card` [3], `explain_grade_rating_bounds` [4], `recall_grade_rating_bounds` [2] passed | `backend/tests/test_application_checkpoints.py:276` - `card.origin == QuizItemOrigin.CHECKPOINT`; `:277` - `== [rating]`; `backend/tests/test_web_checkpoints.py:311-312`; `:463` - `resp.status_code == expected`; `:467`. **Gap:** no test seeds another learner's checkpoint card on the same source and anchor. M23 dropped the owner filter in `active_checkpoint_card` (`repositories.py:2025`) and survived all 50 checkpoint tests. On the shared sample, learner B would then pick up learner A's card, and `_owned_item` (`reviews.py:52`) would 404 B's grade, so B could never grade an explanation | FAIL |
| C19 | minted card shape and owner on the sample; answer = the first feedback citation's quote, cut, else the first chunk; scheduled `initial()` before review | pytest `minted_card_shape_and_owner_on_sample`, `minted_card_falls_back_to_first_chunk` passed | `backend/tests/test_application_checkpoints.py:307` - `[c.quote for c in responded.citations] == [CHUNKS[2], CHUNKS[1]]`; `:312` - `card.user_id == user.id`; `:318` - `card.answer == CHUNKS[2][:_MAX_CARD_CHARS]`; `:319` excerpt; `:332` - `initial()` snapshot; `:349` - fallback `CHUNKS[0]`. Feedback now reaches the DB through the new `store_feedback` (`repositories.py:3118`). M24 (`store_feedback` a no-op) was killed at `:318` | PASS |
| C20 | an existing checkpoint card of the caller's is reused, the count stays 1, the text is unchanged | pytest `second_checkpoint_reuses_existing_card` passed | `backend/tests/test_application_checkpoints.py:359` - same `quiz_item_id`; `:365` - `count == 1`; `:367` - text unchanged; `:368` - `== [1, 3]` | PASS |
| C21 | one answer-mode call, evidence capped at 6, least-covered first, citations = grounded | pytest `explain_calls_answer_mode_once_least_covered_first`, `explain_drops_ungrounded_citations` passed | `backend/tests/test_application_checkpoints.py:395` - `len(generation.calls) == 1`; `:397` - `MODE_ANSWER`; `:400` - `len(snippets) == 6`; `:403-404` ordering; `:406`, `:426` grounded quotes | PASS |
| C22 | the explain JSON keys are exactly feedback/citations(anchor, section_path, quote); the dialog shows no grade wording | pytest `explain_payload_keys_have_no_score`, vitest `feedback step shows no grade wording` passed | `backend/tests/test_web_checkpoints.py:332` - `set(body) == {"feedback", "citations"}`; `:335` citation keys; `:336` - `_GRADE_WORDS.search(...) is None`; `frontend/tests/checkpoint-dialog.test.tsx:388` - `dialog.textContent).not.toMatch(...)` | PASS |
| C23 | not-found / raise / ungrounded → fallback quoting the least-covered chunk; a raise debits nothing, a completed call debits | pytest `explain_fallback_on_not_found_raise_or_ungrounded` [3] passed | `backend/tests/test_application_checkpoints.py:455` - `== [CHUNKS[1]]`; `:459` - `row is None`; `:462` - `row.usd_micros == 3000` | PASS |
| C24 | a blank explanation makes no generate call and quotes the least-covered chunk | pytest `blank_explanation_skips_generation` passed | `backend/tests/test_application_checkpoints.py:481` - `== [CHUNKS[0]]`; `:483` - `generation.calls == []` | PASS |
| C25 | at the cap → 429, paused → 503, responded_at stays NULL; **new:** "in both cases … the dialog shows the catalog copy for that status (never the backend's detail) with the draft kept" | pytest `explain_budget_exhausted_429_paused_503`, vitest `a refused explanation shows catalog copy, not the server's detail, and keeps the draft` passed | `backend/tests/test_web_checkpoints.py:361` - `== 429`; `:362` - `== 503`; `:368` - `== [None, None]`; `frontend/tests/checkpoint-dialog.test.tsx:226` - the stub returns **429 only**; `:237` - alert `toBe("Too many requests. …")`; `:240` - detail absent; `:245` - draft kept. **Gap:** the 503 member of the dialog clause has no proof (`rg -n "503" frontend/tests/checkpoint-dialog.test.tsx` → no hit). M26b (show `err.detail` for status ≥500) survived | FAIL |
| C26 | usage debited as KIND_GENERATION, ask_count untouched | pytest `explain_debits_usage_as_generation` passed | `backend/tests/test_application_checkpoints.py:504` - `row.usd_micros == budget.usage_micros(usage, None) == 2000`; `:505` - `row.ask_count == 0` | PASS |
| C27 | feedback renders quote and path, then exactly Missed it/Partly/Got it grading 1/2/3; confidence 1/2/3 sent | vitest `feedback quotes passages then offers three self-assessments`, `self-assessment` [3], `is sent as` [3] passed | `frontend/tests/checkpoint-dialog.test.tsx:361-362` - quote and path; `:366` - `toEqual(["Missed it", "Partly", "Got it"])`; `:419` - `expect(grades).toEqual([{ rating }])`; `:448` - `expect(sent).toEqual([{ response: "workers specialise", confidence }])`. Labels now come from the `checkpoint` catalog. M29 (swap the `notSure`/`fairlySure` keys) was killed at `:448` | PASS |
| C28 | Just explain is link/ghost, confidence is primary, no request until used; using it sends one reveal, shows passage + path, removes the action, keeps the explanation and confidence | vitest `just explain is a secondary action on the explain step`, `just explain shows the passage and still asks for the explanation` passed | `frontend/tests/checkpoint-dialog.test.tsx:298` - `data-variant` `"link"`; `:300` - confidence `"default"`; `:306` - `toHaveBeenCalledTimes(1)`; `:332` - passage; `:333` - section path; `:334` - `reveals` length 1; `:336` - action gone; `:337` - textbox kept; `:339` - feedback after `Sure` | PASS |
| C29 | reveal stamps revealed_at and returns the first chunk; **new:** a repeated reveal returns the same passage and keeps the first stamp | pytest `reveal_stamps_and_returns_first_chunk`, `second_reveal_keeps_the_first_stamp` passed | `backend/tests/test_web_checkpoints.py:383` - `resp.json()["passage"] == CHUNKS[0]`; `:389` - `revealed is not None`; `:404` - `== [200, 200]`; `:405` - `first.json() == second.json()`; `:407` - `scalar_one() == first_stamp`. The web assembly uses `SystemClock` (`dependencies.py:180`), so a second stamp differs. M25 (drop the `coalesce`) was killed at `:407` | PASS |
| C30 | reveal on a recall attempt or after a response → 409, unchanged | pytest `reveal_409_on_recall_or_after_response` passed | `backend/tests/test_web_checkpoints.py:423` - `== (409, 409)`; `:429` - `== [None, None]`. The reveal filter now uses `CheckpointAttemptKind.EXPLAIN` (`repositories.py:3083`) | PASS |
| C31 | revealed → assisted=true, unrevealed → false; the grade route accepts no client `assisted` | pytest `revealed_explain_grade_is_assisted`, `unrevealed_explain_grade_is_unassisted`, `grade_refuses_a_client_assisted_field` passed | `backend/tests/test_application_checkpoints.py:571` - `== [(3, 3, True)]`; `:580` - `== [(3, 3, False)]`; `backend/tests/test_web_checkpoints.py:483` - `== 422`; `:484` - `_log_count(db_conn) == before` | PASS |
| C32 | `SubmitReview` requires `assisted` and stores it; the migration leaves existing rows NULL | pytest `submit_review_requires_assisted_and_stores_it`, `checkpoint_migration_leaves_existing_review_log_unrecorded` passed | `backend/tests/test_application_reviews.py:1105` - `pytest.raises(TypeError)`; `:1116` - `== [(3, 2, True), (1, None, False)]`; `backend/tests/test_migrations.py:4154` - `tuple(row) == (None, None)` (after the rebase: down to `0031_user_locale_preferences`, up to `0032_section_checkpoints`) | PASS |

Every new or strengthened proof resolves to a test this fix added (`git diff --stat 7bffc79..2c69997`: +54, +42 and +107 lines across the three test files).

The fix added two dialog tests that no check names: `a lost session hands over to the sign-in redirect` and `speaks pt-BR when the interface is in Portuguese`. Both ran green, and M27 and M28 were killed by them.

## Coverage

Verified at 2c69997 for the rows whose authority this diff touched: the moved card queries, the response and grade refusals, the dialog's error path, and the migration chain. Every other row is carried from 7bffc79 (round 3), and its proofs re-ran green at 2c69997.

| Set (size) | Recomputed from | Member -> proof | Unproven |
| --- | --- | --- | --- |
| create statuses (5) | plan Surface (carried) | 201 C8 · 401/403 C42 · 404 C8 · 422 C8 | - |
| response statuses (8) | plan Surface (carried) | 200 C9 · 401/403 C42 · 404 C12 · 409 C10 · 422 C11 · 429/503 C25 | - |
| reveal statuses (5) | plan Surface (carried) | 200 C29 (first and repeat, `test_web_checkpoints.py:404`) · 401/403 C42 · 404 C12 · 409 C30 | - |
| grade statuses (6) | plan Surface; `application/checkpoints.py:519-521` adds a 404 before the claim | 200 C16/C18 · 401/403 C42 · 404 foreign/missing C12, deleted card C15 `:502` · 409 C15/C16 · 422 C18, C31 | - |
| refused transitions (6) | Landing door 1 + this diff's two new refusals | respond-twice C10 · respond lost to a concurrent claim C10 `test_application_checkpoints.py:553` · grade-unresponded C15 · grade on a deleted card C15 `:506` · grade-twice C16/C17 · reveal-after-response C30 | - |
| explain claim order (claim before provider) | `application/checkpoints.py:420-440` (claim `:422`, then generate, then `_store` `:436`/`:440`) | no provider call for a loser C10 `:553` (M20 killed) · feedback stored after generate C19 `:318` (M24 killed) | - |
| recall card selection filters (6) | moved query `repositories.py:2000-2016` | owner C5 `:180`/`:185` (M22 killed) · source and anchor C5 (foreign source, `ch2.xhtml`) · stale C5 · flagged C5 · checkpoint origin C5 | - |
| checkpoint-card reuse lookup filters (5) | moved query `repositories.py:2019-2034`; AC 20 "the caller's active checkpoint card on that source and anchor" | reuse when present C20 `test_application_checkpoints.py:359` | owner (M23 survived) · other anchor · other source · inactive status. `add_card(..., origin=CHECKPOINT)` appears once in the suite (`test_application_checkpoints.py:173`), in a start test that never grades |
| dialog error copy per budget refusal (2) | C25's new clause "in both cases … for that status" | 429 → `status.rateLimited` copy, detail hidden, draft kept: `checkpoint-dialog.test.tsx:237`, `:240`, `:245` (M26 killed) | 503 → `status.server` copy (no dialog test; M26b survived) |
| dialog 401 routing (1) | plan Observable "unauthorised state - the reader's `onRequireAuth` 401 path" | dialog side: `checkpoint-dialog.test.tsx:270` (M27 killed), not named by a check | reader passes `onRequireAuth` to the dialog (`chapter-reader.tsx:1006`): no test (M33 survived); no check owns it |
| attempt states (4) | plan domain term (carried) | created C5 · revealed C29 · responded C9 · graded C14 | - |
| attempt kinds (2) | `kind IN ('recall','explain')` (carried) | recall C14 · explain C18 | - |
| prediction values (4) | Landing door 6 (carried); labels now from the catalog | 1/2/3/null C4 `:140` | - |
| confidence button → value (3) | Landing door 6; `CONFIDENCES` key table, `checkpoint-dialog.tsx` | 1/2/3 C27 `:448` (M29 killed) | - |
| explain self-assessment → rating (3) | Landing door 6 (carried) | 1/2/3 C27 `:419` | - |
| dialog explain-step states (2) | AC 28–29 (carried) | unrevealed C28 `:298`/`:306` · revealed C28 `:332-339` | - |
| explain generation outcomes (5) | AC 21–24 (carried) | grounded C21 · ungrounded/not-found/raise C23 · blank C24 | - |
| minted card passage source (2) | AC 19 (carried) | first citation C19 `:318` · first-chunk fallback C19 `:349` | - |
| budget refusals, backend (2) | AC 25 | exhausted `test_web_checkpoints.py:361` · paused `:362`, both leave `responded_at` NULL `:368` | - |
| assisted values written (3) | Landing door 2 (carried) | true/false C31 · pre-cycle NULL C32 | - |
| 404 indistinguishability | AC 12 (carried) | C12 `test_web_checkpoints.py:260` | - |
| migration chain (1 head) | `backend/migrations/versions/0032_section_checkpoints.py:34-35` (`0032` revises `0031_user_locale_preferences`) | C32 `test_migrations.py:4127` onward, down/up between `0031` and `0032` | - |
| doors (6) | plan Landing (carried) | 1 C5/C17 · 2 C31/C32 · 3 C19/C20 · 4 C21 · 5 C8/C12 · 6 C4, C27 | - |
| startup config: checkpoint router mounted (2 assemblies) | read each assembly | `backend/app/main.py:134` · `quiz_client` via `create_app` (`tests/conftest.py:259`) | - |

## Test policy rows

Every row classifies a file this diff touched, except `web/checkpoints.py`, so three rows were re-judged at 2c69997.

| Row | Files it classifies | Required proof | Expectation met |
| --- | --- | --- | --- |
| Decides: card selection, guards, assisted, evidence order, fallback, mint-or-reuse | `backend/app/application/checkpoints.py` | own layer vs Postgres and real FSRS, present | yes for the members its Coverage rows list. The new claim-order and deleted-card branches are asserted (`test_application_checkpoints.py:553`, `test_web_checkpoints.py:506`). The reuse lookup's owner exclusion is the coverage gap above, not a row the checks priced |
| Entry point: validation, status mapping | `backend/app/infrastructure/web/checkpoints.py` | HTTP boundary, present | yes (carried from 7bffc79; file untouched) |
| Repository conditional updates | `SqlAlchemyCheckpointRepository.claim_response`, `claim_grade`, `reveal` | two-connection race, plus once-only stamps | yes - `test_repositories_checkpoints.py:77`; the reveal's keep-first is now asserted at `test_web_checkpoints.py:407` |
| Step machine: what is visible when | `frontend/app/components/checkpoint-dialog.tsx` | component test, present | yes - every step's visible/hidden contract is asserted. The new recalled→next-attempt transition is at `:211-217` and the error state at `:237-246`. The 503 error copy is a member gap, recorded under Coverage |

Swept `existing` rows re-read: the observability row's logger warning is still emitted on the fallback path (`application/checkpoints.py:430-434`). The plan's Observable "unauthorised state → the reader's `onRequireAuth` path" is now wired (`chapter-reader.tsx:1006`, `checkpoint-dialog.tsx:117-119`).

## Faults injected

Verified at 2c69997. Isolation worked like this:

- a scratch `git worktree add --detach <scratchpad>/verify-wt HEAD`
- a fresh `uv sync --extra dev`, with `app` confirmed to import from the scratch path
- frontend `node_modules` symlinked
- a separate DB, `learny_test_checkpoint_verify`

The scratch baseline was green: the two checkpoint backend files gave 49 passed, and the dialog file gave 21 passed.

Each mutant was an exact-anchor replacement that had to match exactly once. It ran against only its covering test file, then was reverted with `git checkout`.

The real tree's `git status --porcelain` was empty before and empty after. When the runs finished, only the symlink was removed, the scratch worktree was removed and pruned (`git worktree list` shows no `verify-wt`), and the DB was dropped.

The brief required at least six surfaces, so the five-mutant cap was exceeded on purpose. Each row below exercises a different surface.

| Mutation | Location | Killed |
| --- | --- | --- |
| M20 generate before claim (the claim before `generate` removed; both `_store` calls back to `_claim(..., feedback)`) | `backend/app/application/checkpoints.py:422`, `:436`, `:440` | yes - `explain_lost_to_a_concurrent_response_never_calls_the_provider` failed at `test_application_checkpoints.py:553` (one generate call recorded) |
| M21 the deleted-card refusal moved back after `claim_grade` | `backend/app/application/checkpoints.py:519-520` → else-branch | yes - `grade_on_a_deleted_card_is_404…` failed at `test_web_checkpoints.py:506` (`graded_at` stamped) |
| M22 drop `quiz_items.user_id == user_id` in `QuizItemRepository.recall_cards` | `backend/app/infrastructure/db/repositories.py:2007` | yes - `start_selects_due_first_owned_active_cards_on_anchor` failed at `test_application_checkpoints.py:185` |
| M23 drop `quiz_items.user_id == user_id` in `QuizItemRepository.active_checkpoint_card` | `backend/app/infrastructure/db/repositories.py:2025` | no - survived: `test_application_checkpoints.py`, `test_web_checkpoints.py` and `test_repositories_checkpoints.py` gave 50 passed |
| M24 `store_feedback` never called (`_store` returns early) | `backend/app/application/checkpoints.py:378-381` | yes - `minted_card_shape_and_owner_on_sample` failed at `test_application_checkpoints.py:318` (fell back to `CHUNKS[0]`) |
| M25 reveal overwrites the stamp (`coalesce` removed) | `backend/app/infrastructure/db/repositories.py:3086` | yes - `second_reveal_keeps_the_first_stamp` failed at `test_web_checkpoints.py:407` |
| M26 the dialog renders the backend `detail` when present | `frontend/app/components/checkpoint-dialog.tsx:121` | yes - `a refused explanation shows catalog copy…` failed (`:237`) |
| M26b the dialog renders the backend `detail` only for status ≥500 (the paused 503) | `frontend/app/components/checkpoint-dialog.tsx:121` | no - survived: 21 passed |
| M27 the 401 → `onRequireAuth` branch removed | `frontend/app/components/checkpoint-dialog.tsx:117-120` | yes - `a lost session hands over to the sign-in redirect` failed (`:270`) |
| M28 pt-BR `checkpoint.ask.justExplain` set back to English | `frontend/messages/pt-BR.json` | yes - `speaks pt-BR when the interface is in Portuguese` failed (`:287`); `i18n-parity` stayed green, as expected |
| M29 en mapping: `CONFIDENCES` keys `notSure`/`fairlySure` swapped | `frontend/app/components/checkpoint-dialog.tsx` `CONFIDENCES` | yes - 3 failed: `is sent as` 1 and 2 (`:448`) and `recall answer appears only after…` (`:165`) |
| M31 the draft is kept when advancing (`setDraft("")` removed) | `frontend/app/components/checkpoint-dialog.tsx:128` | yes - `grading a recall moves on…` failed at `:217` |
| M33 the reader stops passing `onRequireAuth` to the dialog | `frontend/app/components/chapter-reader.tsx:1006` | no - survived: `chapter-reader.test.tsx` gave 76 passed. No check claims this wiring |

Not tabled: M30 changed the en catalog's `checkpoint.ask.position` from `{position} of {total}` to `{total} of {total}`, and it survived. No check claims the position counter. The only assertion on it, `:213` `"2 of 2"`, uses a case where position equals total. This is a test-precision note, not a check gap.

## Gate

Verified at 2c69997.

- Batch-1 named proofs: 52 passed (backend) and 21 passed (frontend), 0 failed.
- Touched-module regression in the real tree: `pytest tests/test_application_checkpoints.py tests/test_web_checkpoints.py tests/test_repositories_checkpoints.py tests/test_application_reviews.py` gave 91 passed, 0 failed. `vitest run tests/checkpoint-dialog.test.tsx tests/chapter-reader.test.tsx tests/i18n-parity.test.ts` gave 100 passed, 0 failed.
- Lint on the touched files: `ruff check` and `ruff format --check` were clean on `application/checkpoints.py`, `domain/ports.py`, `db/repositories.py` and the two backend test files. `tsc --noEmit` (frontend) was clean.
- Full gate: not re-run here, because of the memory budget. The orchestrator's baseline at 2c69997 is backend green except the 2 environmental `test_deploy_topology` failures, and frontend 1003 passed.

## Ranked gaps

1. **The checkpoint-card reuse lookup's owner filter is unproven** (C18; also bears on C19 "including on the shared sample" and C20). The location is `backend/app/infrastructure/db/repositories.py:2025`, a query this diff moved. M23 survived. On the shared sample, a learner whose classmate already holds a checkpoint card for that section would be handed the classmate's card. `_owned_item` would then 404 their grade, so they could never grade an explanation. The source, anchor and status filters in the same query are equally unexercised: no test seeds a checkpoint card the lookup must skip. Fix: seed another learner's active checkpoint card on the same sample source and anchor, grade an explanation, and assert a new card owned by the caller is minted. Optionally do the same for an other-anchor card and an archived card.
2. **C25's dialog clause is proven for 429 only.** `frontend/tests/checkpoint-dialog.test.tsx:226` stubs only 429. The claim says "in both cases … the catalog copy for that status", and 503 maps to a different key (`status.server`, `frontend/app/lib/errors.ts:115`). M26b survived. Fix: parametrize the test over 429 → `status.rateLimited` and 503 → `status.server` copy, each asserting the detail is absent and the draft is kept.
3. **The reader → dialog `onRequireAuth` wiring is untested** (`frontend/app/components/chapter-reader.tsx:1006`). M33 survived. No check claims it. The plan's Observable lands the unauthorised state on the existing reader path, and the dialog half is pinned by an unnamed test (`checkpoint-dialog.test.tsx:270`). Fix: either add a reader test (a 401 from the dialog's start calls the reader's `onRequireAuth`), or record in checks.md that this wiring is unchecked by decision.

Notes, none of which fail the round:

- Two new dialog tests, the 401 hand-over (`:251`) and pt-BR (`:274`), are proofs of no check. They ran and killed M27 and M28. Interface language is a plan decision, not an obligation, so no check is owed.
- The comment in `test_grade_on_a_deleted_card_is_404_and_leaves_the_attempt_ungraded` (`backend/tests/test_web_checkpoints.py:490-492`) still describes the old order ("the grade claim stamps the attempt before the card is resolved … must roll that stamp back"). The code now refuses before the claim. The assertions are correct; the comment is stale.
- The four new `errors.operation.checkpoint*` copies are reached only for statuses outside the shared classes, such as 409, 404 and 422. No test shows one, but no check claims them either.
- Carried from rounds 2–3: M8 and M9 were killed by a downstream crash, not a clean 422. C28's "keeps … confidence buttons" is asserted through `Sure` alone.
- The amended checks (C10, C13, C15, C25, C29) only add to the originals: each keeps its original claim and proof verbatim and appends a clause plus a proof. Every new clause is proven except C25's 503 dialog member (gap 2).
