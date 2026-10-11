# section-checkpoint-and-calibration verification

**Verdict**: FAIL
**Profile**: standard
**Diff range**: d43402b..47d200e
**Round**: 1 - batch 1 of 2
**Verifier**: independent sub-agent (author != verifier)

Batch scope: C1–C32, C42. C33–C41 are batch 2, verified before its PR.

Batch 1 is mostly sound: 26 of 33 checks are proven with located assertions, and every named test exists and passed at `47d200e`. It fails on four surviving mutants and three claim clauses that no test asserts. Ranked gaps are at the end.

## Binding sources

Step 1 (`ui`) does not apply under `standard`. The plan's binding sources are the ROADMAP v8 row and research synthesis row #6 with its do-not-build list. They set scope and non-goals, not a UI design. No check contradicts them: there is no score, streak, XP or answer-before-attempt flow, and C22 pins the "no grade" wording.

## Checks

Backend proof run (one invocation, all 33 batch-1 backend names): `cd backend && LEARNY_TEST_DATABASE_URL=…/learny_test_checkpoint uv run pytest tests/test_application_checkpoints.py tests/test_web_checkpoints.py tests/test_repositories_checkpoints.py tests/test_application_reviews.py tests/test_migrations.py -v -k "<33 names>"` gave 43 passed, 76 deselected, exit 0. Every named test appears individually, parametrized cases included.
Frontend proof run (one invocation): `cd frontend && npx vitest run tests/chapter-reader.test.tsx tests/checkpoint-dialog.test.tsx -t "<8 names>"` gave 11 passed, 74 skipped, exit 0. Every name appears.

| Check | Claim | Proof run | Evidence | Result |
| --- | --- | --- | --- | --- |
| C1 | one invite, only after the ≥150-word section, placed after its body | vitest `checkpoint invitation only after sections of at least 150 words` passed | `frontend/tests/chapter-reader.test.tsx:2239` - `expect(invites).toHaveLength(1)`; `:2242` - `expect(longSection.nextElementSibling).toBe(invites[0])` | PASS |
| C2 | tap opens dialog on prediction step for that section's anchor; no request before a choice | vitest `opens on the prediction step without calling the API` passed | `frontend/tests/checkpoint-dialog.test.tsx:112` - each of Little/Some/Most/Skip present; `:115` - `expect(fetchMock).not.toHaveBeenCalled()`; tap path `frontend/tests/chapter-reader.test.tsx:2251-2252`. **No assertion anywhere checks that the anchor handed to the dialog is the tapped section's.** `chapter-reader.tsx` `setCheckpointSection({anchor: section.anchor…})` is unproven, and the only invite in the fixture sits on the first section | FAIL (clause "for that section's anchor" unproven) |
| C3 | closing mid-flow unmounts, chapter intact, no further request | vitest `closing mid-flow sends nothing more` passed | `frontend/tests/checkpoint-dialog.test.tsx:262` - `expect(onClose).toHaveBeenCalledTimes(1)`; `:263` - `expect(fetchMock).toHaveBeenCalledTimes(1)`; unmount and same sections at `frontend/tests/chapter-reader.test.tsx:2256`, `:2259` - `.toEqual([S1, S2])` | PASS |
| C4 | Little/Some/Most/Skip → 1/2/3/null | vitest `prediction choices map to 1, 2, 3 and null` (4 cases) passed | `frontend/tests/checkpoint-dialog.test.tsx:139` - `expect(bodies).toEqual([{ anchor: "ch1#s1", prediction: expected }])` over `:119-122` | PASS |
| C5 | ≤3 owned active unflagged non-checkpoint cards on the anchor, due asc then id, then one explain; stale/flagged/other-anchor/other-learner excluded | pytest `start_selects_due_first_owned_active_cards_on_anchor`, `start_caps_recall_attempts_at_three` passed | `backend/tests/test_application_checkpoints.py:182` - `assert kinds == [(RECALL, sooner.id), (RECALL, later.id), (EXPLAIN, None)]`; `:192` - `(stored.prediction, stored.anchor) == (2, ANCHOR)`; `:205` - `recalls == [cards[4].id, cards[3].id, cards[2].id]`. **The "other learner" card is seeded on the other learner's own source (`:175-177`), so the source filter alone excludes it.** Removing `quiz_items.c.user_id == user_id` from `recall_cards` survived (F1) | FAIL (other-learner exclusion not discriminated) |
| C6 | no eligible cards → exactly one explain attempt | pytest `start_without_cards_has_only_explain` passed | `backend/tests/test_application_checkpoints.py:215` - `[a.kind …] == [CheckpointAttemptKind.EXPLAIN]` | PASS |
| C7 | create payload has no answer/excerpt/passage keys or text | pytest `create_payload_carries_no_answers` passed | `backend/tests/test_web_checkpoints.py:91` - `"A distinctive secret answer" not in raw`; `:96` - `assert key not in json.dumps(body)` for answer/source_excerpt/passage; `:99` - attempt keys exactly `{attempt_id, kind, question}` | PASS |
| C8 | 404 + nothing persisted for missing/foreign/no-section; sample → 201 | pytest `create_404_cases_persist_nothing`, `create_on_shared_sample_returns_201` passed | `backend/tests/test_web_checkpoints.py:113` - `== [404, 404, 404]`; `:115` - `_checkpoint_count(db_conn) == before`; `:126` - `resp.status_code == 201` | PASS |
| C9 | recall response stores response+confidence=2, returns answer/excerpt/anchor/path; empty accepted | pytest `recall_response_reveals_answer_after_storing` passed | `backend/tests/test_web_checkpoints.py:178-183` - `resp.json() == {"answer": "Eighteen operations", "source_excerpt": …, "anchor": ANCHOR, "section_path": …}`; `:189` - `tuple(stored) == ("", 2)` | PASS |
| C10 | second response 409, first kept | pytest `second_response_is_409_and_keeps_first` passed | `backend/tests/test_web_checkpoints.py:203` - `second.status_code == 409`; `:209` - `tuple(stored) == ("one", 1)` | PASS |
| C11 | no confidence / 0 / 4 / 4001 chars → 422, responded_at NULL | pytest `response_validation_422` (4 cases) passed | `backend/tests/test_web_checkpoints.py:228` - `resp.status_code == 422`; `:234` - `responded is None`; cases `:215-218` | PASS |
| C12 | response/reveal/grade on a foreign attempt and on a random uuid return identical 404 bodies | pytest `attempt_routes_404_for_foreign_and_missing` passed | `backend/tests/test_web_checkpoints.py:252` - `== [404, 404, 404]`; `:253` - `len({r.text for r in responses}) == 1`. That compares the three routes for one id, never foreign against missing. Giving a foreign attempt a distinct 404 message survived (F2) | FAIL ("identical bodies" across foreign vs missing unproven) |
| C42 | four POSTs: 401 without session, 403 without CSRF, nothing written | pytest `new_routes_require_session_and_csrf` passed | `backend/tests/test_web_checkpoints.py:154` - `without_csrf == [403, 403, 403, 403]`; `:155` - `without_session == [401, 401, 401, 401]`; `:156` - checkpoint count unchanged; `:162` - recall attempt `(responded_at, revealed_at) == (None, None)`. The unauthenticated reveal was posted to the **explain** attempt (`:141`, `:150`), but `revealed_at` is read only on the recall attempt. "Writes nothing" for reveal is therefore unasserted, and the statuses still prove the guards | PASS (statuses); writes-nothing on reveal listed under Coverage |
| C13 | recall shows question and no answer; answer only after the confidence submit resolves | vitest `recall answer appears only after a confidence submit resolves` passed | `frontend/tests/checkpoint-dialog.test.tsx:159` - `queryByText(SECRET)).toBeNull()`; `:166` - still null in flight; `:177` - `await screen.findByText(SECRET)` after resolve | PASS |
| C14 | recall grade 1: FSRS advance, one log row (1, conf, assisted=false), review_log_id linked, study day +1 | pytest `grade_recall_reviews_card_with_confidence_unassisted` passed | `backend/tests/test_application_checkpoints.py:234` - `items.get_scheduling(card.id) == expected` (real FSRS `review(before,1,_NOW)`); `:236` - `== [(1, 2, False)]`; `:243` - `linked == log_id`; `:249` - `reviews == 1` | PASS |
| C15 | grade before response 409, no log row | pytest `grade_before_response_is_409` passed | `backend/tests/test_web_checkpoints.py:271` - `== 409`; `:272` - `_log_count(db_conn) == before` | PASS |
| C16 | sequential double grade: one row, second 409 | pytest `second_grade_is_409_one_log_row` passed | `backend/tests/test_web_checkpoints.py:284` - `first.status_code == 200`; `:286` - `second.status_code == 409`; `:290` - `[r.rating for r in rows] == [3]` | PASS |
| C17 | concurrent claim, separate connections, one winner | pytest `concurrent_grade_claim_has_one_winner` passed | `backend/tests/test_repositories_checkpoints.py:77` - `(won_first, won_second) == (True, False)` | PASS |
| C18 | explain 1/2/3 reviews the checkpoint card (minting); 4 or 0 → 422 | pytest `grade_explain_mints_and_reviews_checkpoint_card` [1,2,3], `explain_grade_rating_bounds` [1,3,4,0] passed | `backend/tests/test_application_checkpoints.py:273` - `card.origin == QuizItemOrigin.CHECKPOINT`; `:274` - `[r.rating …] == [rating]`; `backend/tests/test_web_checkpoints.py:304` - `resp.status_code == expected` (200/200/422/422); `:305` - log count +1 only on 200 | PASS |
| C19 | minted card shape, owner on sample, answer = first citation quote cut / else first chunk, scheduled `initial()` before review | pytest `minted_card_shape_and_owner_on_sample`, `minted_card_falls_back_to_first_chunk` passed | `backend/tests/test_application_checkpoints.py:299` - `card.user_id == user.id` (sample); `:300-304` origin/type/question/anchor/path; `:305-306` - `== CHUNKS[2][:_MAX_CARD_CHARS]`; `:323` - `== CHUNKS[0][:_MAX_CARD_CHARS]`. **No assertion on the minted card's scheduling.** The `initial()` clause (`checkpoints.py:571`) is unproven, and the feedback has a single citation, so "first" is not discriminated | FAIL (clause "scheduled `initial()`" unproven) |
| C20 | existing checkpoint card reused, count 1, text unchanged | pytest `second_checkpoint_reuses_existing_card` passed | `backend/tests/test_application_checkpoints.py:333` - same `quiz_item_id`; `:339` - `count == 1`; `:341` - question/answer unchanged; `:342` - `== [1, 3]` | PASS |
| C21 | one answer-mode call, evidence capped at 6, fewest-shared-words first, citations = grounded | pytest `explain_calls_answer_mode_once_least_covered_first`, `explain_drops_ungrounded_citations` passed | `backend/tests/test_application_checkpoints.py:369` - `len(generation.calls) == 1`; `:371` - `call["mode"] == MODE_ANSWER`; `:374` - `len(snippets) == MAX_EXPLAIN_EVIDENCE`; `:377-378` ordering; `:380`, `:400` grounded quotes. The cap is asserted against the implementation's own constant, not 6. `MAX_EXPLAIN_EVIDENCE = 7` survived (F3) | FAIL (cap "6" not pinned) |
| C22 | explain JSON keys exactly feedback/citations(anchor, section_path, quote); dialog shows no grade wording | pytest `explain_payload_keys_have_no_score` + vitest `feedback step shows no grade wording` passed | `backend/tests/test_web_checkpoints.py:325` - `set(body) == {"feedback", "citations"}`; `:328` - citation keys; `:329` - `_GRADE_WORDS.search(...) is None`; `frontend/tests/checkpoint-dialog.test.tsx:248-250` - `dialog.textContent).not.toMatch(/\b(score…|fail(ed)?)\b|%/i)` | PASS |
| C23 | not-found / raise / ungrounded → 200 fallback quoting least-covered chunk; raise debits nothing, completed call debits | pytest `explain_fallback_on_not_found_raise_or_ungrounded` [3] passed | `backend/tests/test_application_checkpoints.py:429` - `[c.quote …] == [CHUNKS[1]]`; `:433` - `row is None` on raise; `:436` - `row.usd_micros == 3000` otherwise. 200 at HTTP: the fallback path is not separately driven over HTTP, but the service returns normally and the route maps it to 200 (`web/checkpoints.py:157-168`) | PASS |
| C24 | blank (empty/whitespace) → no generate call, least-covered chunk | pytest `blank_explanation_skips_generation` passed | `backend/tests/test_application_checkpoints.py:455` - `== [CHUNKS[0]]`; `:457` - `generation.calls == []` | PASS |
| C25 | at cap 429, paused 503, responded_at stays NULL | pytest `explain_budget_exhausted_429_paused_503` passed | `backend/tests/test_web_checkpoints.py:354` - `exhausted.status_code == 429`; `:355` - `paused.status_code == 503`; `:361` - `== [None, None]` | PASS |
| C26 | usage debited as KIND_GENERATION, ask_count untouched | pytest `explain_debits_usage_as_generation` passed | `backend/tests/test_application_checkpoints.py:478` - `row.usd_micros == budget.usage_micros(usage, None) == 2000`; `:479` - `row.ask_count == 0`; `:480` - `teach_starts == 0` | PASS |
| C27 | feedback renders quote + path, then exactly Missed it/Partly/Got it, grading 1/2/3 | vitest `feedback quotes passages then offers three self-assessments` passed | `frontend/tests/checkpoint-dialog.test.tsx:221-222` - quote and `Book I › The Division of Labour`; `:226` - `buttons).toEqual(["Missed it", "Partly", "Got it"])`; `:230` - `grades).toEqual([{ rating: 2 }])`. Only Partly→2 is asserted. Mapping `Got it` to rating 4 survived (F4) | FAIL (Missed it→1, Got it→3 unproven) |
| C28 | Just explain is link/ghost; confidence buttons primary; no request until used | vitest `just explain is a secondary action on the explain step` passed | `frontend/tests/checkpoint-dialog.test.tsx:191` - `getAttribute("data-variant")).toBe("link")`; `:193-195` - confidence buttons `"default"`; `:199` - `toHaveBeenCalledTimes(1)` | PASS |
| C29 | reveal stamps revealed_at, returns first chunk | pytest `reveal_stamps_and_returns_first_chunk` passed | `backend/tests/test_web_checkpoints.py:376` - `resp.json()["passage"] == CHUNKS[0]`; `:382` - `revealed is not None` | PASS |
| C30 | reveal on recall or after response → 409, unchanged | pytest `reveal_409_on_recall_or_after_response` passed | `backend/tests/test_web_checkpoints.py:398` - `== (409, 409)`; `:404` - `== [None, None]` | PASS |
| C31 | revealed → assisted=true, unrevealed → false; grade route accepts no client `assisted` | pytest `revealed_explain_grade_is_assisted`, `unrevealed_explain_grade_is_unassisted` passed | `backend/tests/test_application_checkpoints.py:492` - `== [(3, 3, True)]`; `:501` - `== [(3, 3, False)]` (flipping the decision was killed, F5). **No test sends `assisted` to the grade route** (search: `rg assisted backend/tests/test_web_checkpoints.py` has no hits). The clause rests only on `GradeRequest` (`web/checkpoints.py:108-111`) lacking the field, and pydantic silently ignores extras | FAIL (clause "grade route accepts no client assisted" has no proof) |
| C32 | SubmitReview requires `assisted` keyword, rows non-null; migration leaves old rows NULL | pytest `submit_review_requires_assisted_and_stores_it`, `checkpoint_migration_leaves_existing_review_log_unrecorded` passed | `backend/tests/test_application_reviews.py:1105-1106` - `pytest.raises(TypeError)` without `assisted`; `:1116` - `== [(3, 2, True), (1, None, False)]`; `backend/tests/test_migrations.py:3992` - `tuple(row) == (None, None)`. The only `append_log` caller is `SubmitReview` (`app/application/reviews.py:199`) | PASS |

Every proof resolves to a test this diff adds (`git diff --stat d43402b..HEAD` lists all five backend test files and both frontend test files).

## Coverage

Recomputed from `plan.md` `Surface`, `Landing` and `Relations`, and from the code. Batch-2 sets (the review route's added fields, the calibration route, calibration exclusions) are out of this batch's scope.

| Set (size) | Recomputed from | Member -> proof | Unproven |
| --- | --- | --- | --- |
| create statuses (5) | plan Surface; `web/checkpoints.py:53-57` (anchor min_length, prediction 1..3) | 201 C8 `test_web_checkpoints.py:126` · 401/403 C42 `:154-155` · 404 C8 `:113` · 422: checks.md maps it to C11, but C11 drives the *response* route | create 422 (invalid prediction / empty anchor): no test anywhere (`rg 'prediction": [04]'` no hits) |
| response statuses (8) | plan Surface | 200 C9/C22 · 401/403 C42 · 404 C12 · 409 C10 · 422 C11 · 429/503 C25 | - |
| reveal statuses (5) | plan Surface | 200 C29 · 401/403 C42 · 404 C12 · 409 C30 | - |
| grade statuses (6) | plan Surface | 200 C16 `:284` / C18 `:304` (C14, which checks.md cites, is below the boundary) · 401/403 C42 · 404 C12 · 409 C15/C16 · 422 C18 (explain 4, 0) | - |
| grade rating scale by kind (recall 1–4, explain 1–3) | plan Surface `rating (recall 1–4, explain 1–3)`; `checkpoints.py:506`, `web/checkpoints.py:111` | recall 1 C14 · recall 3 C16 · explain 1/2/3 C18 · explain 4/0 → 422 C18 | recall 4 accepted and recall 5 → 422: no proof. An unconditional `rating > 3` guard would pass every test |
| attempt states (4) | plan domain term | created C5 · revealed C29 · responded C9 · graded C14 | - |
| refused transitions (4) | Landing door 1 | respond-twice C10 · grade-unresponded C15 · grade-twice C16/C17 · reveal-after-response C30 (+ reveal-on-recall C30) | - |
| attempt kinds (2) | `kind IN ('recall','explain')` | recall C14 · explain C18 | - |
| prediction values (4) | Landing door 6 | 1/2/3/null C4 (FE) · stored C5 `:192` | - |
| confidence values incl. invalid (5) | Landing door 2 | 1 C10 `:209` · 2 C9 · 3 C31 `:492` · 0/4 C11 | - |
| confidence button → value in the dialog (3) | Landing door 6 `Not sure (1) · Fairly sure (2) · Sure (3)` | Fairly sure→2 C13 `checkpoint-dialog.test.tsx:164` | Not sure→1, Sure→3: clicked (`:218`, `:244`) but the request body is never captured |
| explain self-assessment button → rating (3) | Landing door 6 | Partly→2 C27 `:230` | Missed it→1, Got it→3 (F4 survived) |
| recall card exclusions (5) | AC 6; `repositories.py` `recall_cards` | stale/flagged/other-anchor/checkpoint-origin C5 `:182` | other learner's card on the *same* source (F1 survived) |
| explain generation outcomes (5) | AC 21–24 | grounded C21 · ungrounded/not-found/raise C23 · blank C24 | - |
| explain evidence cap (1) | AC 21 "at most 6" | C21 `:374` asserts `== MAX_EXPLAIN_EVIDENCE` | the value 6 (F3 survived) |
| budget refusals (2) | AC 25 | exhausted/paused C25 | - |
| assisted values written (3) | Landing door 2 | true/false C31 · pre-cycle NULL C32 | - |
| 404 indistinguishability (foreign vs missing) | AC 12, `errors.py` CheckpointAttemptNotFound docstring | status C12 | identical body across foreign and missing (F2 survived) |
| auth-guard "writes nothing" (4 routes) | C42 claim | create `:156` · response `:162` · grade: posted to an unresponded attempt, so it would 409 regardless | reveal: its write is unasserted (`revealed_at` read on the wrong attempt) |
| minted card scheduling (1) | AC 19 `SchedulingPort.initial()` | - | `initial()` scheduling (C19) |
| doors (6) | plan Landing | 1 storage C5/C17, FKs as written `metadata.py:969-1036` · 2 C31/C32 · 3 C19/C20; no partial unique matches `checkpoint` (`metadata.py:552,562,571,581` cover deck/highlight/tutor/starter only) · 4 C21 · 5 C8/C12 · 6 C4, C27 | door 6 mappings above |
| Relations one-way lifecycle (cascade user/source/checkpoint; SET NULL card/log) (5) | plan Relations | Swept `data lifecycle: n/a` (approved policy); FK shapes present at `metadata.py:976,982,1003,1014,1029` | - |
| startup config: checkpoint router mounted (2 assemblies) | read each assembly | `backend/app/main.py:132` `app.include_router(checkpoints_router)` · `backend/tests/conftest.py:269` quiz_client builds via `create_app` | - |

## Test policy rows

| Row | Files it classifies | Required proof | Expectation met |
| --- | --- | --- | --- |
| Decides: card selection, guards, assisted, evidence order, fallback, mint-or-reuse | `backend/app/application/checkpoints.py` | own layer vs Postgres + real FSRS (`FsrsSchedulingAdapter`, `test_application_checkpoints.py:120`), present | no - "one asserted case per member" is unmet for the other-learner exclusion (F1), the evidence cap value (F3) and initial() minting |
| Entry point: validation, status mapping | `backend/app/infrastructure/web/checkpoints.py` | HTTP boundary (`quiz_client`), present | no - rejected inputs missing: create 422 (prediction/anchor), recall rating 5, a client `assisted` on grade |
| Repository conditional updates | `SqlAlchemyCheckpointRepository.claim_grade` | two-connection race | yes - `test_repositories_checkpoints.py:77` |
| Step machine: what is visible when | `frontend/app/components/checkpoint-dialog.tsx` | component test, present | no - nothing tests the post-"Just explain" state (`ask` with `passage`) and only 1 of 3 values is asserted for each button→value mapping (confidence, self-assessment) |

`Swept` rows that resolve to existing code: the CSRF/origin/rate-limit guards are in place (`web/checkpoints.py:50`, applied on all four routes). Generation failures are logged at warning level (`checkpoints.py:422-426`), as the observability n/a says.

## Faults injected

Scratch worktree at `HEAD` (fresh `uv sync --extra dev`, `app` imported from the scratch path, frontend `node_modules` symlinked). Removed afterwards. The real tree's `git status --porcelain` matched the baseline (` M .specs/project/ROADMAP.md`, pre-existing) before and after.

| Mutation | Location | Killed |
| --- | --- | --- |
| drop `quiz_items.c.user_id == user_id` from `recall_cards` | `backend/app/infrastructure/db/repositories.py` `SqlAlchemyCheckpointRepository.recall_cards` | no - survived (C5 proofs 2 passed) |
| foreign attempt raises a different 404 message than a missing one | `backend/app/application/checkpoints.py:200-201` | no - survived (C12 proof passed) |
| `MAX_EXPLAIN_EVIDENCE = 6` → `7` | `backend/app/application/checkpoints.py:84` | no - survived (C21 proofs 2 passed) |
| `Got it` rating 3 → 4 | `frontend/app/components/checkpoint-dialog.tsx:73` | no - survived (C27 proof passed) |
| `assisted = revealed_at is not None` → `is None` | `backend/app/application/checkpoints.py:513` | yes - C31 both proofs failed |

## Gate

- Batch-1 named proofs: 43 passed (backend) and 11 passed (frontend), 0 failed.
- Wider regression run over the touched modules (`test_application_checkpoints`, `test_web_checkpoints`, `test_repositories_checkpoints`, `test_application_reviews`, `test_migrations`, `test_domain_quiz`, `test_application_budget`, `test_web_quiz`): 259 passed, 0 failed. `vitest run tests/chapter-reader.test.tsx tests/checkpoint-dialog.test.tsx`: 85 passed, 0 failed.

## Ranked gaps

1. Recall-card ownership is not discriminated. C5 seeds the other learner's card on their own source, so dropping the `user_id` filter survives. On the shared sample, another learner's cloned card would be recalled. `backend/tests/test_application_checkpoints.py:174-177`
2. A client `assisted` on grade is not proven ignored or refused (C31). The plan rejects client-sent `assisted` as a one-way decision (door 2), and nothing would catch a field added later. `backend/app/infrastructure/web/checkpoints.py:108-111`, no test
3. The create route's 422 is unproven, and the checks' Coverage row misattributes it to C11 (the response route). No evidence.
4. The 404 body is not compared between foreign and missing attempts (C12, F2 survived). `backend/tests/test_web_checkpoints.py:253`
5. The dialog's button→value mappings are proven for one value each (C27: Partly only, F4 survived; confidence: Fairly sure only). `frontend/tests/checkpoint-dialog.test.tsx:230`, `:164`
6. The recall rating scale is incomplete: recall 4 accepted and recall 5 → 422 are unproven. An unconditional `rating > 3` guard would pass. No evidence.
7. The evidence cap is asserted against its own constant (C21, F3 survived). `backend/tests/test_application_checkpoints.py:374`
8. The minted card's `initial()` scheduling is unasserted (C19). `backend/tests/test_application_checkpoints.py:298-306`
9. Invite→dialog anchor wiring is unasserted (C2). `frontend/tests/chapter-reader.test.tsx:2247-2251`
10. The C42 reveal "writes nothing" reads `revealed_at` on the recall attempt, not the explain attempt it posted to. `backend/tests/test_web_checkpoints.py:157-162`
