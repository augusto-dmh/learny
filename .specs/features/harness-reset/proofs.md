# harness-reset proofs

**HEAD**: 88c5a77
**Tree**: clean
**Result**: 45 pass, 0 fail; mutations 3 killed, 0 not

| Check | Proof | Ran | Passed | Result |
| --- | --- | --- | --- | --- |
| C1 | `cd backend && uv run pytest -q tests/test_require_db.py -k refuses_a_run_without_a_database` | 1 | 1 | pass |
| C2 | `cd backend && uv run pytest -q tests/test_require_db.py -k still_skips_without_the_flag` | 1 | 1 | pass |
| C3 | `cd backend && uv run pytest -q tests/test_ci_workflow.py -k require_db` | 1 | 1 | pass |
| C4 | `cd backend && uv run pytest -q tests/test_ci_workflow.py -k commits_job` | 3 | 3 | pass |
| C5 | `cd backend && uv run pytest -q tests/test_check_commits.py -k header` | 20 | 20 | pass |
| C6 | `cd backend && uv run pytest -q tests/test_check_commits.py -k assisted_by` | 7 | 7 | pass |
| C7 | `cd backend && uv run pytest -q tests/test_check_commits.py -k agent_trailer` | 13 | 13 | pass |
| C8 | `cd backend && uv run pytest -q tests/test_check_commits.py -k range` | 6 | 6 | pass |
| C9 | `cd backend && uv run pytest -q tests/test_ci_workflow.py -k make_lint_checks_commits` | 1 | 1 | pass |
| C10 | `cd backend && uv run pytest -q tests/test_image_pins.py` | 20 | 20 | pass |
| C11 | `cd backend && uv run pytest -q tests/test_image_pins.py -k adr` | 1 | 1 | pass |
| C12 | `cd backend && uv run pytest -q tests/test_eval_workflow.py -k no_schedule` | 1 | 1 | pass |
| C13 | `cd backend && uv run pytest -q tests/test_eval_workflow.py -k schedule_off_reason` | 1 | 1 | pass |
| C14 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k state_archive` | 1 | 1 | pass |
| C15 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k lessons_files_gone` | 1 | 1 | pass |
| C16 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k removed_skills_absent` | 1 | 1 | pass |
| C17 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k kept_skills_present` | 1 | 1 | pass |
| C18 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k removed_skills_unlisted` | 1 | 1 | pass |
| C19 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k model_table` | 1 | 1 | pass |
| C20 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k attribution_setting` | 1 | 1 | pass |
| C21 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k finalize_trailer_rule` | 1 | 1 | pass |
| C22 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k roadmap_harness_rows` | 1 | 1 | pass |
| C23 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k verifier_requires_db` | 1 | 1 | pass |
| C24 | `cd backend && uv run pytest -q tests/test_check_commits.py -k cannot_read` | 1 | 1 | pass |
| C25 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k vendored_tree` | 1 | 1 | pass |
| C26 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k vendored_deviations` | 1 | 1 | pass |
| C27 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k vendored_build_override` | 1 | 1 | pass |
| C28 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k vendored_commit_gate` | 12 | 12 | pass |
| C29 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k vendored_provenance` | 1 | 1 | pass |
| C30 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k shipcycle_lean` | 1 | 1 | pass |
| C31 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k shipcycle_stage_detection` | 1 | 1 | pass |
| C32 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k shipcycle_lanes` | 1 | 1 | pass |
| C33 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k shipcycle_door_gate` | 1 | 1 | pass |
| C34 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k shipcycle_decisions` | 1 | 1 | pass |
| C35 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k shipcycle_batches` | 1 | 1 | pass |
| C36 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k shipcycle_cost_discipline` | 1 | 1 | pass |
| C37 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k review_track_a` | 1 | 1 | pass |
| C38 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k finalize_internal_refs` | 1 | 1 | pass |
| C39 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k skills_docs` | 1 | 1 | pass |
| C40 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k claude_profile` | 1 | 1 | pass |
| C41 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k gitignore_worktrees` | 1 | 1 | pass |
| C42 | `cd backend && uv run pytest -q tests/test_harness_skills.py -k proofs_portable` | 1 | 1 | pass |
| Build | `cd backend && uv run ruff check .` | - | - | pass |
| Build | `cd backend && uv run ruff format --check .` | - | - | pass |
| Build | `cd backend && python scripts/check_boundaries.py` | - | - | pass |

## Mutations

| Mutation | Location | Killed |
| --- | --- | --- |
| Stage Detection: lean Plan row condition plan.md-without-checks.md -> checks.md-without-plan.md | `.claude\skills\learny-ship-cycle\SKILL.md:37` | yes |
| lane rule: roadmap rows included in Lane F -> excluded (run as Lane S) | `.claude\skills\learny-ship-cycle\SKILL.md:53` | yes |
| vendored commit gate: allowed type list drops fix | `.claude\skills\tlc-spec-lean\scripts\check_commit.py:36` | yes |
