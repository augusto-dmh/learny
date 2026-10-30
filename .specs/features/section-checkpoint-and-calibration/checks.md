# section-checkpoint-and-calibration checks

Profile: standard
Plan: `.specs/features/section-checkpoint-and-calibration/plan.md`

42 checks in 7 slices · 6 one-way doors · 1 open (blocks go-live, none block build)

Proof commands run from the worktree root and are written below in their runnable form; they read `LEARNY_TEST_DATABASE_URL` and `LEARNY_REQUIRE_DB` from the environment (the lane's Postgres on port 5432 hosts the `learny_test_checkpoint` database, Redis on 6380). Backend:
`cd backend && uv run pytest <file> -k <name>`. Frontend: `cd frontend && vitest run <file> -t "<name>"`.

Mutations: 5
Build: cd backend && uv run ruff check . && uv run ruff format --check . ; cd frontend && npx tsc --noEmit ; python backend/scripts/check_commits.py origin/main..HEAD

## Checks

### S1 - the reader offers a checkpoint · batch 1

**C1** - A chapter with one section of ≥150 words and one of <150 words renders exactly one checkpoint invitation, placed after the long section's body (AC 1, 2)
Proof: `cd frontend && vitest run tests/chapter-reader.test.tsx -t "checkpoint invitation only after sections of at least 150 words"`

**C2** - Tapping the invitation opens the checkpoint dialog on the prediction step for that section's anchor, and no request is sent before a prediction choice. A 401 inside the dialog hands over to the reader's sign-in redirect (AC 3, 5)
Proof: `cd frontend && vitest run tests/checkpoint-dialog.test.tsx -t "opens on the prediction step without calling the API"`
Proof: `cd frontend && vitest run tests/chapter-reader.test.tsx -t "starts the checkpoint for the section whose invitation was tapped"`
Proof: `cd frontend && vitest run tests/checkpoint-dialog.test.tsx -t "a lost session hands over to the sign-in redirect"`
Proof: `cd frontend && vitest run tests/chapter-reader.test.tsx -t "hands a checkpoint that finds the session gone to the reader's sign-in redirect"`

**C3** - Closing the dialog mid-flow unmounts it, leaves the chapter rendered with the same sections, and sends no further request (AC 4)
Proof: `cd frontend && vitest run tests/checkpoint-dialog.test.tsx -t "closing mid-flow sends nothing more"`

### S2 - predict, then retrieve unaided · batch 1

**C4** - Each prediction choice `Little`/`Some`/`Most`/`Skip` creates the checkpoint with `prediction` 1/2/3/null (AC 5)
Proof: `cd frontend && vitest run tests/checkpoint-dialog.test.tsx -t "prediction choices map to 1, 2, 3 and null"`

**C5** - Create stores `prediction` and returns recall attempts for the caller's active, unflagged, non-checkpoint cards on the exact anchor. There are at most 3, ordered due ascending then id, and they are followed by exactly one `explain` attempt. A stale card, a flagged card, a card on another anchor and another learner's card are all excluded (AC 6)
Proof: `cd backend && uv run pytest tests/test_application_checkpoints.py -k "start_selects_due_first_owned_active_cards_on_anchor"`
Proof: `cd backend && uv run pytest tests/test_application_checkpoints.py -k "start_caps_recall_attempts_at_three"`

**C6** - A section with no eligible cards yields a checkpoint with exactly one attempt, of kind `explain` (AC 6)
Proof: `cd backend && uv run pytest tests/test_application_checkpoints.py -k "start_without_cards_has_only_explain"`

**C7** - The create payload contains no key `answer`, `source_excerpt` or `passage`, and no card answer text appears anywhere in its JSON (AC 7)
Proof: `cd backend && uv run pytest tests/test_web_checkpoints.py -k "create_payload_carries_no_answers"`

**C8** - Create on a missing source, on another learner's source, and on an anchor with no section returns 404 with zero `section_checkpoints` rows written. The shared sample is readable and returns 201. A prediction of 0 or 4, or an empty anchor, returns 422 with zero rows written (AC 8)
Proof: `cd backend && uv run pytest tests/test_web_checkpoints.py -k "create_404_cases_persist_nothing"`
Proof: `cd backend && uv run pytest tests/test_web_checkpoints.py -k "create_on_shared_sample_returns_201"`
Proof: `cd backend && uv run pytest tests/test_web_checkpoints.py -k "create_validation_422"`

**C9** - A recall response with confidence 2 stores `response` and `confidence=2` and returns the card's `answer`, `source_excerpt`, `anchor` and `section_path`. An empty response is accepted (AC 9)
Proof: `cd backend && uv run pytest tests/test_web_checkpoints.py -k "recall_response_reveals_answer_after_storing"`

**C10** - A second response to the same attempt returns 409, and the stored response and confidence equal the first submission. An explanation that loses the claim to a concurrent response is refused without calling the provider (AC 10)
Proof: `cd backend && uv run pytest tests/test_web_checkpoints.py -k "second_response_is_409_and_keeps_first"`
Proof: `cd backend && uv run pytest tests/test_application_checkpoints.py -k "explain_lost_to_a_concurrent_response_never_calls_the_provider"`

**C11** - A response with no confidence, confidence 0, confidence 4, or a 4001-character response returns 422 and leaves `responded_at` NULL (AC 11)
Proof: `cd backend && uv run pytest tests/test_web_checkpoints.py -k "response_validation_422"`

**C12** - `response`, `reveal` and `grade` on another learner's attempt, and on a random uuid, return identical 404 bodies (AC 12)
Proof: `cd backend && uv run pytest tests/test_web_checkpoints.py -k "attempt_routes_404_for_foreign_and_missing"`

**C42** - Each of the four new checkpoint POST routes returns 401 without a session and 403 without the CSRF token, and writes nothing (AC 8, 12; existing auth/CSRF guards)
Proof: `cd backend && uv run pytest tests/test_web_checkpoints.py -k "new_routes_require_session_and_csrf"`

**C13** - In the dialog, a recall step shows the question and no answer text. The answer appears only after a confidence button submits the response and its promise resolves. Grading the recall moves to the next attempt with an empty draft (AC 13)
Proof: `cd frontend && vitest run tests/checkpoint-dialog.test.tsx -t "recall answer appears only after a confidence submit resolves"`
Proof: `cd frontend && vitest run tests/checkpoint-dialog.test.tsx -t "grading a recall moves on to the explanation with an empty draft"`

### S3 - every attempt is scheduled by FSRS · batch 1

**C14** - Grading a responded recall attempt with rating 1 does four things. It changes the card's `quiz_item_scheduling` to what `SchedulingPort.review(snapshot, 1, now)` returns. It appends one `review_log` row with `rating=1`, the attempt's `confidence` and `assisted=false`. It stamps the attempt's `review_log_id`. It increments today's `study_days.reviews_count` by 1 (AC 14)
Proof: `cd backend && uv run pytest tests/test_application_checkpoints.py -k "grade_recall_reviews_card_with_confidence_unassisted"`

**C15** - Grading an attempt with no response returns 409 and appends no `review_log` row. Grading a recall whose card was deleted returns 404, appends no row and leaves the attempt ungraded (AC 15)
Proof: `cd backend && uv run pytest tests/test_web_checkpoints.py -k "grade_before_response_is_409"`
Proof: `cd backend && uv run pytest tests/test_web_checkpoints.py -k "grade_on_a_deleted_card_is_404_and_leaves_the_attempt_ungraded"`

**C16** - Two sequential grades on one attempt leave exactly one `review_log` row, and the second returns 409 (AC 16)
Proof: `cd backend && uv run pytest tests/test_web_checkpoints.py -k "second_grade_is_409_one_log_row"`

**C17** - Two concurrent grade claims on one attempt, on separate connections, produce exactly one winner. The claim is a conditional UPDATE that returns a row once (AC 16)
Proof: `cd backend && uv run pytest tests/test_repositories_checkpoints.py -k "concurrent_grade_claim_has_one_winner"`

**C18** - Grading the explain attempt with 1, 2 or 3 reviews the caller's checkpoint card with that rating, minting one when absent, and returns its `quiz_item_id`. Rating 4 or 0 returns 422. A recall attempt accepts rating 4 and refuses 5 with 422 and no log row (AC 17, 18)
Proof: `cd backend && uv run pytest tests/test_application_checkpoints.py -k "grade_explain_mints_and_reviews_checkpoint_card"`
Proof: `cd backend && uv run pytest tests/test_web_checkpoints.py -k "explain_grade_rating_bounds"`
Proof: `cd backend && uv run pytest tests/test_web_checkpoints.py -k "recall_grade_rating_bounds"`

**C19** - A minted checkpoint card has `origin='checkpoint'`, `item_type='free_recall'` and `user_id` set to the caller, including on the shared sample whose source belongs to the operator. Its question is `Explain "<title>" in your own words.`, it carries the section's anchor and path, and its answer and excerpt are the first feedback citation's quote cut to `quiz_max_card_chars`, else the section's first chunk. It is scheduled `initial()` before being reviewed (AC 19)
Proof: `cd backend && uv run pytest tests/test_application_checkpoints.py -k "minted_card_shape_and_owner_on_sample"`
Proof: `cd backend && uv run pytest tests/test_application_checkpoints.py -k "minted_card_falls_back_to_first_chunk"`

**C20** - When the caller already has an active checkpoint card on that source and anchor, grading a second checkpoint's explain attempt reviews that card. The count of checkpoint cards stays 1 and its question and answer are unchanged. Another learner's checkpoint card on the same section, the caller's stale, other-anchor or other-book checkpoint cards, and the caller's non-checkpoint card on that section, are never reused (AC 20)
Proof: `cd backend && uv run pytest tests/test_application_checkpoints.py -k "second_checkpoint_reuses_existing_card"`
Proof: `cd backend && uv run pytest tests/test_application_checkpoints.py -k "reuse_skips_checkpoint_cards_that_are_not_the_callers_on_this_section"`

### S4 - explain-back gets formative feedback · batch 1

**C21** - A non-blank explanation triggers exactly one `generate` call with `mode='answer'` and evidence capped at 6, ordered fewest-shared-words first. The returned citations are exactly the cited evidence that `ground()` keeps. The call also carries the learner's interface language (`response_language`: the stored locale, else `Accept-Language`, else `None` for English), like every other answer turn (AC 21; appended with the interface-language seam)
Proof: `cd backend && uv run pytest tests/test_application_checkpoints.py -k "explain_calls_answer_mode_once_least_covered_first"`
Proof: `cd backend && uv run pytest tests/test_application_checkpoints.py -k "explain_drops_ungrounded_citations"`
Proof: `cd backend && uv run pytest tests/test_application_checkpoints.py -k "explain_asks_for_the_callers_language"`
Proof: `cd backend && uv run pytest tests/test_web_checkpoints.py -k "explain_feedback_language_follows_the_learner"`

**C22** - The explain response JSON has exactly the keys `feedback` and `citations` (each citation `anchor`, `section_path`, `quote`). The dialog's feedback step renders none of the words `score`, `grade`, `%`, `correct`, `incorrect`, `pass` or `fail` (AC 22)
Proof: `cd backend && uv run pytest tests/test_web_checkpoints.py -k "explain_payload_keys_have_no_score"`
Proof: `cd frontend && vitest run tests/checkpoint-dialog.test.tsx -t "feedback step shows no grade wording"`

**C23** - When the port returns `found=False`, raises, or cites only chunks outside the evidence, the response is 200 with one citation whose quote is the least-covered chunk verbatim. A raise records no spend. A completed call that grounded nothing still debits its reported usage (AC 23, amended: see plan "Amendments")
Proof: `cd backend && uv run pytest tests/test_application_checkpoints.py -k "explain_fallback_on_not_found_raise_or_ungrounded"`

**C24** - A blank explanation (empty or whitespace) makes zero `generate` calls and returns the least-covered chunk as the single citation (AC 24)
Proof: `cd backend && uv run pytest tests/test_application_checkpoints.py -k "blank_explanation_skips_generation"`

**C25** - With the day's spend at the cap, the explain response returns 429. With AI paused it returns 503. In both cases the attempt's `responded_at` stays NULL, and the dialog shows the catalog copy for that status (never the backend's detail) with the draft kept (AC 25)
Proof: `cd backend && uv run pytest tests/test_web_checkpoints.py -k "explain_budget_exhausted_429_paused_503"`
Proof: `cd frontend && vitest run tests/checkpoint-dialog.test.tsx -t "a refused explanation"`

**C26** - A port result reporting usage debits `usage_micros(usage, profile_id)` to the caller's `ai_spend_days` row, as `KIND_GENERATION`, and does not increment `ask_count` (AC 26)
Proof: `cd backend && uv run pytest tests/test_application_checkpoints.py -k "explain_debits_usage_as_generation"`

**C27** - The feedback step renders each citation's quote with its section path, then exactly three self-assessment buttons, `Missed it`, `Partly` and `Got it`, which grade with 1, 2 and 3 (AC 27)
Proof: `cd frontend && vitest run tests/checkpoint-dialog.test.tsx -t "feedback quotes passages then offers three self-assessments"`
Proof: `cd frontend && vitest run tests/checkpoint-dialog.test.tsx -t "self-assessment"`
Proof: `cd frontend && vitest run tests/checkpoint-dialog.test.tsx -t "is sent as"`

### S5 - assisted attempts are recorded as assisted · batch 1

**C28** - On the explain step, the primary submit buttons are the confidence buttons under the textarea, and `Just explain` is a non-primary (link/ghost) button. No request is sent until one of them is used. Using `Just explain` sends one reveal request, shows the returned passage with its section path, removes the action, and keeps the explanation and confidence buttons (AC 28, 29)
Proof: `cd frontend && vitest run tests/checkpoint-dialog.test.tsx -t "just explain is a secondary action on the explain step"`
Proof: `cd frontend && vitest run tests/checkpoint-dialog.test.tsx -t "just explain shows the passage and still asks for the explanation"`

**C29** - `reveal` on an unresponded explain attempt stamps `revealed_at` and returns the section's first chunk as `passage`. A repeated reveal returns the same passage and keeps the first stamp (AC 29)
Proof: `cd backend && uv run pytest tests/test_web_checkpoints.py -k "reveal_stamps_and_returns_first_chunk"`
Proof: `cd backend && uv run pytest tests/test_web_checkpoints.py -k "second_reveal_keeps_the_first_stamp"`

**C30** - `reveal` on a recall attempt, and on an explain attempt that already has a response, returns 409 and leaves `revealed_at` unchanged (AC 30)
Proof: `cd backend && uv run pytest tests/test_web_checkpoints.py -k "reveal_409_on_recall_or_after_response"`

**C31** - Reveal, respond and grade 3 stores `review_log.assisted = true`. Respond and grade 3 without reveal stores `false`. The grade route accepts no client `assisted` field (AC 31)
Proof: `cd backend && uv run pytest tests/test_application_checkpoints.py -k "revealed_explain_grade_is_assisted"`
Proof: `cd backend && uv run pytest tests/test_application_checkpoints.py -k "unrevealed_explain_grade_is_unassisted"`
Proof: `cd backend && uv run pytest tests/test_web_checkpoints.py -k "grade_refuses_a_client_assisted_field"`

**C32** - `SubmitReview` requires `assisted` as a keyword (calling without it raises `TypeError`), and every row it appends has non-null `assisted`. The migration leaves existing `review_log` rows with `assisted IS NULL` and `confidence IS NULL` (AC 32)
Proof: `cd backend && uv run pytest tests/test_application_reviews.py -k "submit_review_requires_assisted_and_stores_it"`
Proof: `cd backend && uv run pytest tests/test_migrations.py -k "checkpoint_migration_leaves_existing_review_log_unrecorded"`

### S6 - review grades capture confidence · batch 2

**C33** - While hidden, a review card shows `Not sure`, `Fairly sure`, `Sure` and `Reveal answer`. Each confidence button reveals the answer (AC 33)
Proof: `cd frontend && vitest run tests/review-screen.test.tsx -t "confidence buttons reveal the answer beside Reveal answer"`

**C34** - Grading after `Sure` sends `confidence: 3`. Grading after `Reveal answer`, or after Space, sends a body with no `confidence` key (AC 34)
Proof: `cd frontend && vitest run tests/review-screen.test.tsx -t "grade carries confidence only when revealed by a confidence tap"`

**C35** - The review route stores `confidence` 1–3 or NULL, and `assisted` from the body (default false). Confidence 0 or 4 returns 422 with no log row (AC 35)
Proof: `cd backend && uv run pytest tests/test_web_quiz.py -k "review_stores_confidence_and_assisted"`
Proof: `cd backend && uv run pytest tests/test_web_quiz.py -k "review_confidence_out_of_range_422"`

**C36** - Opening the editor before revealing, then grading, sends `assisted: true`. Grading without opening the editor sends `assisted: false` (AC 36)
Proof: `cd frontend && vitest run tests/review-screen.test.tsx -t "editor peek before reveal marks the grade assisted"`

### S7 - a per-book calibration view · batch 2

**C37** - Calibration returns exactly 3 rows for confidence 1, 2 and 3. Each row counts the caller's not-undone, `assisted=false` log rows with that confidence on the source's cards, and how many of them have a rating of 2 or more. A row that is undone, a row with `assisted=true`, a row with NULL confidence, and a row on another source are all excluded (AC 37)
Proof: `cd backend && uv run pytest tests/test_web_checkpoints.py -k "calibration_counts_unassisted_not_undone_by_level"`

**C38** - Calibration on a missing source, or on another learner's source, returns 404, and without a session returns 401 (AC 38)
Proof: `cd backend && uv run pytest tests/test_web_checkpoints.py -k "calibration_404_foreign_and_missing"`

**C39** - On the shared sample, learner A's calibration counts only A's reviews while learner B has graded sample cards too (AC 39)
Proof: `cd backend && uv run pytest tests/test_web_checkpoints.py -k "calibration_on_sample_is_per_learner"`

**C40** - The dock Review tab renders "When you felt Sure, you recalled 8 of 10" for a level with attempts, omits levels with zero attempts, and shows no overall percentage (AC 40)
Proof: `cd frontend && vitest run tests/dock-review-tab.test.tsx -t "calibration lines per level with attempts"`

**C41** - With all three levels at zero attempts, the tab shows the empty-state copy and no level lines (AC 41)
Proof: `cd frontend && vitest run tests/dock-review-tab.test.tsx -t "calibration empty state"`

## Coverage

| Set (size) | Member -> proof | Unproven |
| --- | --- | --- |
| `POST /api/sources/{source_id}/checkpoints` statuses (5) | 201 C8 · 401 C42 · 403 C42 · 404 C8 · 422 C8 | - |
| `POST /api/checkpoint-attempts/{attempt_id}/response` statuses (8) | 200 C9 · 401 C42 · 403 C42 · 404 C12 · 409 C10 · 422 C11 · 429 C25 · 503 C25 | - |
| `POST /api/checkpoint-attempts/{attempt_id}/reveal` statuses (5) | 200 C29 · 401 C42 · 403 C42 · 404 C12 · 409 C30 | - |
| `POST /api/checkpoint-attempts/{attempt_id}/grade` statuses (6) | 200 C16 · 401 C42 · 403 C42 · 404 C12 · 409 C15 · 422 C18, C31 | - |
| `POST /api/quiz-items/{item_id}/reviews` added-field statuses (2) | 200 C35 · 422 C35 | - |
| `GET /api/sources/{source_id}/calibration` statuses (3) | 200 C37 · 401 C38 · 404 C38 | - |
| attempt states (4) | created C5 · revealed C29 · responded C9 · graded C14 | - |
| attempt transitions refused (4) | respond-twice C10 · grade-unresponded C15 · grade-twice C16 · reveal-after-response C30 | - |
| attempt kinds (2) | recall C14 · explain C18 | - |
| prediction values (4) | 1 C4 · 2 C4 · 3 C4 · null C4 | - |
| confidence values incl. 2 invalid (5) | 1 C27, C35 · 2 C9, C27 · 3 C14, C27 · 0 C11 · 4 C11 | - |
| explain self-assessment incl. 1 invalid (4) | 1 C18, C27 · 2 C18, C27 · 3 C27, C31 · 4 C18 | - |
| recall card exclusions (5) | stale C5 · flagged C5 · other anchor C5 · other learner C5 · checkpoint origin C5 | - |
| explain generation outcomes (5) | grounded C21 · ungrounded C23 · not-found C23 · raise C23 · blank C24 | - |
| budget refusals (2) | exhausted C25 · paused C25 | - |
| assisted values written (3) | true C31 · false C31 · pre-cycle NULL C32 | - |
| calibration exclusions (4) | undone C37 · assisted C37 · null confidence C37 · other source C37 | - |
| doors (6) | 1 storage C5, C17 · 2 assisted/confidence C31, C32 · 3 checkpoint origin C19, C20 · 4 answer-mode explain C21 · 5 routes C8, C12 · 6 vocabulary C4, C27, C33 | - |
| startup config: checkpoint router mounted (2 assemblies) | `app/main.py` C8 · test client fixture C8 (both built through `create_app`) | - |

- Claims naming a status code, route or response shape: C7–C12, C15, C16, C18, C22, C25, C29, C30, C35, C37–C39. Each has a proof that crosses the HTTP boundary.
- The C17 concurrency claim is proven at the repository with two connections, because a single TestClient cannot race.

## Test policy

| Code | Required proofs | Coverage expectation |
| --- | --- | --- |
| `application/checkpoints.py` (decides: card selection, attempt state guards, assisted decision, evidence ordering, fallback, mint-or-reuse) | at its own layer, against Postgres and the real FSRS adapter, as `test_application_reviews.py` does | one asserted case per member in the Coverage rows above |
| `web/checkpoints.py` (entry point: validation, status mapping) | at the HTTP boundary | accepted input, each rejected input, each error status |
| repository conditional updates (once-only claims) | at the repository, with a two-connection race | one winner |
| `checkpoint-dialog.tsx` (decides: step machine, what is visible when) | component test | each step's visible/hidden contract |

Evidence:

- `application/checkpoints.py` will dispatch over 2 attempt kinds × 4 states, 5 generation outcomes and 2 card paths (mint, reuse). That is about 14 branch points, so it decides.
- Closest analogue: `application/reviews.py` and `application/cards.py:AcceptTutorCard`, proven at the application layer against the live DB (`tests/test_application_reviews.py`, `tests/test_application_cards.py`).
- `web/quiz.py` is proven at the boundary in `tests/test_web_quiz.py`, which follows the same pattern.

Cost: 3 new backend test modules plus additions to 3 existing ones, and 2 new frontend test files plus additions to 3 existing ones. The repo already follows these rows, so none of this goes into its guidelines.

## Swept

- validation: C11, C18, C35
- failure modes: C23 (generation failure falls back, nothing debited), C25
- idempotency: C10, C16, C20
- authorization: C8, C12, C38, C39, C42
- concurrency: C17
- data lifecycle: n/a - checkpoint rows cascade with the user and the source (door 1, the FK shape the account-deletion path already relies on); abandoned checkpoints are kept, small and harmless
- dependency failure: C23
- state transitions: C10, C15, C16, C29, C30
- observability: n/a - no new metric is required; generation failures are logged with the existing logger at warning level next to C23's fallback, and request instrumentation already covers new routes

## Handoff

**Dispatched:** verifier round 6 - independent sub-agent via a dynamic-workflow run (2026-10-30, after 5d087d3)

`wc -c` over the files each slice touches, divided by 4:

- S1–S5 (batch 1) touch the following files. Backend: `metadata.py` 46k, `repositories.py` 118k (read in slices, not whole), `entities.py` 58k, `ports.py` 62k, `reviews.py` 12k, `web/quiz.py` 22k, `dependencies.py` 52k, `main.py`, a new migration, new `application/checkpoints.py`, new `web/checkpoints.py`. Frontend: `chapter-reader.tsx` 44k, new `checkpoint-dialog.tsx`, new `lib/checkpoints.ts`. Tests: 3 new backend files and 2 new frontend files.
- S1–S5 estimate: about 140k tokens, already counting the large files as targeted reads. That is under the 150k budget, but only just.
- S6–S7 (batch 2) touch `review-screen.tsx` 34k, `dock-review-panel.tsx` 4k, `web/quiz.py`, the calibration query and route, and tests. Estimate about 45k tokens.
- Total about 185k, over the 150k budget. The cut is after S5, where the surface changes from reader/checkpoint to review/calibration. That is also where the brief's D2 batches cut.
- Mechanism: handoff, i.e. sequential batches, one PR each, the next started after the previous merges (D2, pre-answered by the brief).
