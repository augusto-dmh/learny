# section-checkpoint-and-calibration proofs

**HEAD**: 3d8d97b
**Tree**: clean
**Result**: 71 pass, 0 fail; mutations 10 killed, 0 not

| Check | Proof | Ran | Passed | Result |
| --- | --- | --- | --- | --- |
| C1 | `cd frontend && vitest run tests/chapter-reader.test.tsx -t "checkpoint invitation only after sections of at le` | 1 | 1 | pass |
| C2 | `cd frontend && vitest run tests/checkpoint-dialog.test.tsx -t "opens on the prediction step without calling th` | 1 | 1 | pass |
| C2 | `cd frontend && vitest run tests/chapter-reader.test.tsx -t "starts the checkpoint for the section whose invita` | 1 | 1 | pass |
| C2 | `cd frontend && vitest run tests/checkpoint-dialog.test.tsx -t "a lost session hands over to the sign-in redire` | 1 | 1 | pass |
| C2 | `cd frontend && vitest run tests/chapter-reader.test.tsx -t "hands a checkpoint that finds the session gone to ` | 1 | 1 | pass |
| C3 | `cd frontend && vitest run tests/checkpoint-dialog.test.tsx -t "closing mid-flow sends nothing more"` | 1 | 1 | pass |
| C4 | `cd frontend && vitest run tests/checkpoint-dialog.test.tsx -t "prediction choices map to 1, 2, 3 and null"` | 4 | 4 | pass |
| C5 | `cd backend && uv run pytest tests/test_application_checkpoints.py -k "start_selects_due_first_owned_active_car` | 1 | 1 | pass |
| C5 | `cd backend && uv run pytest tests/test_application_checkpoints.py -k "start_caps_recall_attempts_at_three"` | 1 | 1 | pass |
| C6 | `cd backend && uv run pytest tests/test_application_checkpoints.py -k "start_without_cards_has_only_explain"` | 1 | 1 | pass |
| C7 | `cd backend && uv run pytest tests/test_web_checkpoints.py -k "create_payload_carries_no_answers"` | 1 | 1 | pass |
| C8 | `cd backend && uv run pytest tests/test_web_checkpoints.py -k "create_404_cases_persist_nothing"` | 1 | 1 | pass |
| C8 | `cd backend && uv run pytest tests/test_web_checkpoints.py -k "create_on_shared_sample_returns_201"` | 1 | 1 | pass |
| C8 | `cd backend && uv run pytest tests/test_web_checkpoints.py -k "create_validation_422"` | 3 | 3 | pass |
| C9 | `cd backend && uv run pytest tests/test_web_checkpoints.py -k "recall_response_reveals_answer_after_storing"` | 1 | 1 | pass |
| C10 | `cd backend && uv run pytest tests/test_web_checkpoints.py -k "second_response_is_409_and_keeps_first"` | 1 | 1 | pass |
| C10 | `cd backend && uv run pytest tests/test_application_checkpoints.py -k "explain_lost_to_a_concurrent_response_ne` | 1 | 1 | pass |
| C11 | `cd backend && uv run pytest tests/test_web_checkpoints.py -k "response_validation_422"` | 4 | 4 | pass |
| C12 | `cd backend && uv run pytest tests/test_web_checkpoints.py -k "attempt_routes_404_for_foreign_and_missing"` | 1 | 1 | pass |
| C42 | `cd backend && uv run pytest tests/test_web_checkpoints.py -k "new_routes_require_session_and_csrf"` | 1 | 1 | pass |
| C13 | `cd frontend && vitest run tests/checkpoint-dialog.test.tsx -t "recall answer appears only after a confidence s` | 1 | 1 | pass |
| C13 | `cd frontend && vitest run tests/checkpoint-dialog.test.tsx -t "grading a recall moves on to the explanation wi` | 1 | 1 | pass |
| C14 | `cd backend && uv run pytest tests/test_application_checkpoints.py -k "grade_recall_reviews_card_with_confidenc` | 1 | 1 | pass |
| C15 | `cd backend && uv run pytest tests/test_web_checkpoints.py -k "grade_before_response_is_409"` | 1 | 1 | pass |
| C15 | `cd backend && uv run pytest tests/test_web_checkpoints.py -k "grade_on_a_deleted_card_is_404_and_leaves_the_at` | 1 | 1 | pass |
| C16 | `cd backend && uv run pytest tests/test_web_checkpoints.py -k "second_grade_is_409_one_log_row"` | 1 | 1 | pass |
| C17 | `cd backend && uv run pytest tests/test_repositories_checkpoints.py -k "concurrent_grade_claim_has_one_winner"` | 1 | 1 | pass |
| C18 | `cd backend && uv run pytest tests/test_application_checkpoints.py -k "grade_explain_mints_and_reviews_checkpoi` | 3 | 3 | pass |
| C18 | `cd backend && uv run pytest tests/test_web_checkpoints.py -k "explain_grade_rating_bounds"` | 4 | 4 | pass |
| C18 | `cd backend && uv run pytest tests/test_web_checkpoints.py -k "recall_grade_rating_bounds"` | 2 | 2 | pass |
| C19 | `cd backend && uv run pytest tests/test_application_checkpoints.py -k "minted_card_shape_and_owner_on_sample"` | 1 | 1 | pass |
| C19 | `cd backend && uv run pytest tests/test_application_checkpoints.py -k "minted_card_falls_back_to_first_chunk"` | 1 | 1 | pass |
| C20 | `cd backend && uv run pytest tests/test_application_checkpoints.py -k "second_checkpoint_reuses_existing_card"` | 1 | 1 | pass |
| C20 | `cd backend && uv run pytest tests/test_application_checkpoints.py -k "reuse_skips_checkpoint_cards_that_are_no` | 1 | 1 | pass |
| C21 | `cd backend && uv run pytest tests/test_application_checkpoints.py -k "explain_calls_answer_mode_once_least_cov` | 1 | 1 | pass |
| C21 | `cd backend && uv run pytest tests/test_application_checkpoints.py -k "explain_drops_ungrounded_citations"` | 1 | 1 | pass |
| C21 | `cd backend && uv run pytest tests/test_application_checkpoints.py -k "explain_asks_for_the_callers_language"` | 1 | 1 | pass |
| C21 | `cd backend && uv run pytest tests/test_web_checkpoints.py -k "explain_feedback_language_follows_the_learner"` | 4 | 4 | pass |
| C22 | `cd backend && uv run pytest tests/test_web_checkpoints.py -k "explain_payload_keys_have_no_score"` | 1 | 1 | pass |
| C22 | `cd frontend && vitest run tests/checkpoint-dialog.test.tsx -t "feedback step shows no grade wording"` | 1 | 1 | pass |
| C23 | `cd backend && uv run pytest tests/test_application_checkpoints.py -k "explain_fallback_on_not_found_raise_or_u` | 3 | 3 | pass |
| C24 | `cd backend && uv run pytest tests/test_application_checkpoints.py -k "blank_explanation_skips_generation"` | 1 | 1 | pass |
| C25 | `cd backend && uv run pytest tests/test_web_checkpoints.py -k "explain_budget_exhausted_429_paused_503"` | 1 | 1 | pass |
| C25 | `cd frontend && vitest run tests/checkpoint-dialog.test.tsx -t "a refused explanation"` | 2 | 2 | pass |
| C26 | `cd backend && uv run pytest tests/test_application_checkpoints.py -k "explain_debits_usage_as_generation"` | 1 | 1 | pass |
| C27 | `cd frontend && vitest run tests/checkpoint-dialog.test.tsx -t "feedback quotes passages then offers three self` | 1 | 1 | pass |
| C27 | `cd frontend && vitest run tests/checkpoint-dialog.test.tsx -t "self-assessment"` | 4 | 4 | pass |
| C27 | `cd frontend && vitest run tests/checkpoint-dialog.test.tsx -t "is sent as"` | 3 | 3 | pass |
| C28 | `cd frontend && vitest run tests/checkpoint-dialog.test.tsx -t "just explain is a secondary action on the expla` | 1 | 1 | pass |
| C28 | `cd frontend && vitest run tests/checkpoint-dialog.test.tsx -t "just explain shows the passage and still asks f` | 1 | 1 | pass |
| C29 | `cd backend && uv run pytest tests/test_web_checkpoints.py -k "reveal_stamps_and_returns_first_chunk"` | 1 | 1 | pass |
| C29 | `cd backend && uv run pytest tests/test_web_checkpoints.py -k "second_reveal_keeps_the_first_stamp"` | 1 | 1 | pass |
| C30 | `cd backend && uv run pytest tests/test_web_checkpoints.py -k "reveal_409_on_recall_or_after_response"` | 1 | 1 | pass |
| C31 | `cd backend && uv run pytest tests/test_application_checkpoints.py -k "revealed_explain_grade_is_assisted"` | 1 | 1 | pass |
| C31 | `cd backend && uv run pytest tests/test_application_checkpoints.py -k "unrevealed_explain_grade_is_unassisted"` | 1 | 1 | pass |
| C31 | `cd backend && uv run pytest tests/test_web_checkpoints.py -k "grade_refuses_a_client_assisted_field"` | 1 | 1 | pass |
| C32 | `cd backend && uv run pytest tests/test_application_reviews.py -k "submit_review_requires_assisted_and_stores_i` | 1 | 1 | pass |
| C32 | `cd backend && uv run pytest tests/test_migrations.py -k "checkpoint_migration_leaves_existing_review_log_unrec` | 1 | 1 | pass |
| C33 | `cd frontend && vitest run tests/review-screen.test.tsx -t "confidence buttons reveal the answer beside Reveal ` | 1 | 1 | pass |
| C34 | `cd frontend && vitest run tests/review-screen.test.tsx -t "grade carries confidence only when revealed by a co` | 1 | 1 | pass |
| C35 | `cd backend && uv run pytest tests/test_web_quiz.py -k "review_stores_confidence_and_assisted"` | 1 | 1 | pass |
| C35 | `cd backend && uv run pytest tests/test_web_quiz.py -k "review_confidence_out_of_range_422"` | 1 | 1 | pass |
| C36 | `cd frontend && vitest run tests/review-screen.test.tsx -t "editor peek before reveal marks the grade assisted"` | 1 | 1 | pass |
| C37 | `cd backend && uv run pytest tests/test_web_checkpoints.py -k "calibration_counts_unassisted_not_undone_by_leve` | 1 | 1 | pass |
| C38 | `cd backend && uv run pytest tests/test_web_checkpoints.py -k "calibration_404_foreign_and_missing"` | 1 | 1 | pass |
| C39 | `cd backend && uv run pytest tests/test_web_checkpoints.py -k "calibration_on_sample_is_per_learner"` | 1 | 1 | pass |
| C40 | `cd frontend && vitest run tests/dock-review-tab.test.tsx -t "calibration lines per level with attempts"` | 1 | 1 | pass |
| C41 | `cd frontend && vitest run tests/dock-review-tab.test.tsx -t "calibration empty state"` | 1 | 1 | pass |
| Build | `cd backend && uv run ruff check . && uv run ruff format --check .` | - | - | pass |
| Build | `cd frontend && npx tsc --noEmit` | - | - | pass |
| Build | `python backend/scripts/check_commits.py origin/main..HEAD` | - | - | pass |

## Mutations

| Mutation | Location | Killed |
| --- | --- | --- |
| the review route accepts an out-of-range confidence | `backend\app\infrastructure\web\quiz.py:123` | yes |
| the review route stores the rating as the confidence | `backend\app\infrastructure\web\quiz.py:504` | yes |
| calibration counts assisted grades as unaided | `backend\app\infrastructure\db\repositories.py:1848` | yes |
| calibration counts undone grades | `backend\app\infrastructure\db\repositories.py:1847` | yes |
| calibration counts another learner's reviews | `backend\app\infrastructure\db\repositories.py:1845` | yes |
| calibration counts another book's reviews | `backend\app\infrastructure\db\repositories.py:1846` | yes |
| a lapse counts as recalled in calibration | `backend\app\infrastructure\db\repositories.py:1841` | yes |
| the review client serializes an absent confidence as null | `frontend\app\lib\quiz.ts:317` | yes |
| the dock shows levels with no attempts | `frontend\app\components\dock-review-panel.tsx:110` | yes |
| every review grade is marked assisted | `frontend\app\components\review-screen.tsx:259` | yes |
