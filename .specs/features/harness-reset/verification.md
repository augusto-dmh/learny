# harness-reset PR A verification

**Verdict**: PASS
**Profile**: standard
**Diff range**: d43402b..e1ce4804edb563f4883c3cf85d8232a22e31a54d (fix diff a53464e..e1ce480)
**Round**: 2 - scoped
**Verifier**: independent sub-agent (author != verifier)

Round 1 (at a53464e) returned FAIL on three gaps. The fix commit `e1ce480` closes each one:

1. **Verifier brief had no proof.** Fixed by AC 22 (`plan.md:121`) and C23 (`checks.md:92`). The member now has a grep proof against `.claude/skills/learny-ship-cycle/SKILL.md:159`, and a fault on that line fails the proof.
2. **Checker exit 2 had no proof.** Fixed by AC 23 (`plan.md:122`), C24 (`checks.md:95`) and `backend/tests/test_check_commits.py:250-251`. A fault that turns `return 2` into `return 0` is now killed.
3. **`web-design-guidelines` kept with no recorded reason.** The plan now carries an owner-confirmed Assumption row recording why it stays (`plan.md:138`). An Assumption marked `y` is approved policy, so C17 no longer contradicts a decision.

The fix touched no production file. It changed only `backend/tests/test_check_commits.py`, `plan.md` and `checks.md`. `check_commits.py`, `conftest.py`, the workflows, the Dockerfiles and the skills are byte-identical to a53464e, so every carried section below still describes the same code.

## Binding sources

Carried from a53464e, with the two rows the fix touched verified at e1ce480.

| Source | Opened | Contradiction | Uncovered |
| --- | --- | --- | --- |
| `synthesis.md` "Sensors that cannot lie" 1-5 | yes - `docs/research/2026-09-30/harness/synthesis.md:69-78` | none (door-1 note below); verified at e1ce480: sensor 1's "Verifier brief" and "`make infra` precondition" are now covered by C23 | - |
| `synthesis.md` "Paperwork diet" + rq03 F8 prune list | yes - `synthesis.md:87-92`, `rq03-learny-harness-audit.md:163` | none (verified at e1ce480: keeping `web-design-guidelines` is now an owner-confirmed exception at `plan.md:138`) | - |
| `synthesis.md` "Model policy" | yes - `synthesis.md:94-104` | none: C19 matches the 5 rows verbatim (carried from a53464e) | - |
| `synthesis.md` "Owner decisions" D1-D6 | yes - `synthesis.md:140-151` | none (carried from a53464e) | - |

Observations that do not fail anything (carried from a53464e):

- Synthesis sensor 3 says "forbid direct pushes". The plan's door-1 ruleset keeps a Repository-admin bypass set to `always` so Stage 8 can push wrap commits. The owner approved this deviation, and the ruleset is not in the diff.
- "Delegation default: inline" is implemented at `learny-ship-cycle/SKILL.md:130`, but no check names it.
- The synthesis names lean's `check_commit.py`. The plan uses a stdlib `check_commits.py` that enforces the same rules.

## Checks

Verified at e1ce480. Proofs were re-run in full at the new HEAD in two batched runs:

- **Pytest:** `env -u LEARNY_TEST_DATABASE_URL -u LEARNY_REQUIRE_DB uv run pytest -v` over `test_require_db.py`, `test_ci_workflow.py`, `test_check_commits.py`, `test_image_pins.py` and `test_eval_workflow.py`. Result: 89 passed, 0 failed, with each named test listed individually.
- **Shell:** the C14-C23 proofs ran verbatim and every one exited 0.

Citations were refreshed only for the file the fix touched (`test_check_commits.py`). Its existing lines did not move, because the new test was appended at the end of the file.

| Check | Claim | Proof run | Evidence | Result |
| --- | --- | --- | --- | --- |
| C1 | flag=1, no URL: non-zero exit before any test, and the message names the variable | `test_the_flag_refuses_a_run_without_a_database_url` PASSED | `backend/tests/test_require_db.py:44` - `returncode == pytest.ExitCode.USAGE_ERROR`; `:45` - `"LEARNY_TEST_DATABASE_URL" in output`; `:47-48` - neither `skipped` nor `passed` appears | PASS |
| C2 | no flag, no URL: the DB test skips and the run exits 0 | `test_a_database_test_still_skips_without_the_flag` PASSED | `backend/tests/test_require_db.py:54` - `ExitCode.OK`; `:55` - `"1 skipped" in output` | PASS |
| C3 | CI `backend-test` pytest step sets `LEARNY_REQUIRE_DB: "1"` | `test_backend_test_runs_pytest_with_require_db` PASSED | `backend/tests/test_ci_workflow.py:30` - `.get("LEARNY_REQUIRE_DB") == "1"` | PASS |
| C4 | `commits` job: PR-only, fetch-depth 0, runs the checker over base..head | 3 `commits_job` tests PASSED | `backend/tests/test_ci_workflow.py:35` - `if` is pull_request; `:42` - `fetch-depth == 0`; `:47-50` - script and base.sha..head.sha | PASS |
| C5 | a bad header or a type outside the list fails and names the SHA; all 11 types pass | 19 `header` tests PASSED | `backend/tests/test_check_commits.py:73` - `== []` for each type; `:90` - `any("header" in e ...)`; exit 1 and the SHA named at `:211`, `:213` | PASS |
| C6 | a missing trailer fails, and so do near-misses and a trailer outside the trailer block | 6 `assisted_by` tests PASSED | `backend/tests/test_check_commits.py:108`, `:117`, `:124` | PASS |
| C7 | an agent `Co-authored-by` (10 names, any case) or a `Made-with` trailer fails; a human co-author passes | 13 `agent_trailer` tests PASSED | `backend/tests/test_check_commits.py:140`, `:146`, `:151`, `:156` | PASS |
| C8 | the range walk skips merges and bots and names every failing SHA | 6 `range` tests PASSED | `backend/tests/test_check_commits.py:211-214`, `:221`, `:234`, `:242-243` | PASS |
| C9 | `make lint` runs the checker over `origin/main..HEAD` | `test_make_lint_checks_commits_over_the_branch` PASSED | `backend/tests/test_ci_workflow.py:64-65` | PASS |
| C10 | every upstream image ref is pinned by digest | 16 parametrized cases plus the scan guard PASSED | `backend/tests/test_image_pins.py:97` - `_PINNED.match(ref)`; `:88-92` - every source kind is reached | PASS |
| C11 | ADR-0032 is Accepted and records the rule, the bump command and a link to 0031 | `test_adr_records_...` PASSED | `backend/tests/test_image_pins.py:105-108` | PASS |
| C12 | `eval.yml` has no `schedule`, and `workflow_dispatch` keeps `generation_profiles` | `test_no_schedule_trigger_keeps_manual_dispatch` PASSED | `backend/tests/test_eval_workflow.py:197-198` | PASS |
| C13 | eval.yml, CLAUDE.md and README give the reason and say runs are manual | `test_schedule_off_reason_is_stated_where_people_look` PASSED | `backend/tests/test_eval_workflow.py:207-208` | PASS |
| C14 | the archive is byte-identical, and the live STATE has exactly 2 sections | shell exit 0 | `.specs/project/STATE.md:5`, `.specs/project/STATE.md:12`; `git diff --exit-code` is empty | PASS |
| C15 | the lessons files are gone | shell exit 0 | deleted in the diff (`.specs/LESSONS.md` -75, `.specs/lessons.json` -171) | PASS |
| C16 | the 8 removed skill dirs are gone | shell exit 0 | `.claude/skills/README.md:1` index; `ls .claude/skills/` lists 17 dirs, none of the 8 | PASS |
| C17 | all 15 kept skills have a `SKILL.md` | shell exit 0 | `.claude/skills/web-design-guidelines/SKILL.md:2` and the 14 others | PASS |
| C18 | no removed skill name appears in the skill indexes or lock files | shell exit 0 | grep finds nothing in `SKILLS.md`, `.claude/skills/README.md` or `skills-lock.json` (all 3 exist); `.agents/.skill-lock.json` is deleted | PASS |
| C19 | the 5 model rows are present; no "never Sonnet" and no Haiku | shell exit 0 | `.claude/skills/learny-ship-cycle/SKILL.md:124-128` | PASS |
| C20 | the `attribution` setting is correct and there is no `includeCoAuthoredBy` | python exit 0 | `.claude/settings.json:2-5` | PASS |
| C21 | the finalize trailer rule and override are present, and the old sentence is gone | shell exit 0 | `.claude/skills/learny-finalize/SKILL.md:45`, `.claude/skills/learny-finalize/SKILL.md:48` | PASS |
| C22 | the ROADMAP `## Harness` section has the PR A row and a PR B row marked `Not started` | python exit 0 | `.specs/project/ROADMAP.md:186`, `.specs/project/ROADMAP.md:192`, `.specs/project/ROADMAP.md:193` | PASS |
| C23 | the ship-cycle hygiene rules require `LEARNY_REQUIRE_DB=1` and `make infra` for every Verifier run | grep exit 0 | `.claude/skills/learny-ship-cycle/SKILL.md:159` - "Every Verifier run uses `LEARNY_REQUIRE_DB=1` with the test database up (`make infra` first)" | PASS |
| C24 | a range git cannot read makes the checker exit 2 and name the range on stderr | `test_range_that_git_cannot_read_exits_two_not_zero` PASSED | `backend/tests/test_check_commits.py:250` - `result.returncode == 2`; `:251` - `"no-such-ref..HEAD" in result.stderr` | PASS |

Precision notes, carried from a53464e. None of these fails a check:

- **C13:** the test asserts only the keywords "unfunded" and "manual dispatch". It does not assert "schedule off" in CLAUDE.md or README.
- **C5/C7:** "exit 1 naming the SHA" is proven only by combining the pure-function tests with C8's range test.
- **C18:** the `! grep` form would treat a missing file as a pass.
- **AC 11:** the requirement can also be read as a back-link from ADR-0031, and that back-link is not asserted.
- **Commit scope pattern:** the implementation's kebab-scope regex is stricter than door 2's literal `[a-z0-9-]+`, and no test pins the difference.
- **C23:** the proof is a regex over prose. It proves the rule is written down; it does not prove that a Verifier brief applies it. That is the intended level for a skill document.

## Coverage

Rows the fix touched were verified at e1ce480. The others are carried from a53464e: their authority files are unchanged.

| Set (size) | Recomputed from | Member -> proof | Unproven |
| --- | --- | --- | --- |
| checker exit codes (3) - verified at e1ce480 | `check_commits.py:20` docstring; returns at `:132`, `:147`, `:149`; plan Observable at `plan.md:152` | 0 at `test_check_commits.py:201` · 1 at `:211` · 2 at `:250` | - |
| places that run pytest with the flag (2) - verified at e1ce480 | synthesis sensor 1 (`synthesis.md:72`), `plan.md:121`, `plan.md:132` | CI `backend-test` C3 (`test_ci_workflow.py:30`) · Verifier brief C23 (`learny-ship-cycle/SKILL.md:159`) | - |
| kept skills (15) - verified at e1ce480 | plan AC 16, plus the exceptions at `plan.md:137-138` | each one by C17 | - |
| commit types (11) - carried | `learny-finalize/SKILL.md:22` | all 11 by `test_check_commits.py:71-73` | - |
| header rules (5 + `!`) - carried | `check_commits.py:43` | `test_check_commits.py:79-85`, `:94` | - |
| agent names (10) and `Made-with` (1) - carried | plan AC 7 | `test_check_commits.py:135-140`, `:151` | - |
| commits skipped by the walk (2) - carried | `check_commits.py:112`, `:136` | merge `:234` · bot `:221` | - |
| upstream image refs (16 across 4 kinds) - carried | `git ls-files` plus a grep of each file | each one parametrized at `test_image_pins.py:95-97` | - |
| places that run the commit checker (2) - carried | plan AC 4, 9 | C4 · C9 | - |
| places that state the nightly reason (3) - carried | synthesis sensor 5 and D5 | `test_eval_workflow.py:205-208` | - |
| removed skills (8) - carried | plan AC 16 | C16, C18 | - |
| in-repo one-way doors (2) - carried | plan Landing 2, 3 | C4-C8, C24 · C10, C11 | - |

## Test policy rows

Re-judged the range-walk row, which classifies the touched test file. The other rows are carried from a53464e.

| Row | Files it classifies | Required proof | Expectation met |
| --- | --- | --- | --- |
| `check_commits.py` message rules (decides) - carried | `backend/scripts/check_commits.py:83-106` | pure function, `test_check_commits.py:71-156` | yes |
| `check_commits.py` range walk (decides) - verified at e1ce480 | `backend/scripts/check_commits.py:109-149` | real temporary git repo, `test_check_commits.py:183-251` | yes - merge skipped `:234`, bot skipped `:221`, all failures named `:211-214`, an unreadable range exits 2 `:250` |
| `conftest.py` flag guard (decides) - carried | `backend/tests/conftest.py:61-72` | pytest subprocess, `test_require_db.py:26-62` | yes |
| Workflow YAML, Compose, Dockerfiles (configuration) - carried | ci.yml, eval.yml, compose files, 5 Dockerfiles | parse-and-assert | yes - all 16 of 16 image refs |

## Faults injected

The round-2 faults ran only on the surfaces the fix created, and were verified at e1ce480:

- **Setup:** a scratch `git worktree add --detach` at e1ce480, run with the worktree venv's python. Each fault was reverted before the next.
- **Cleanup:** the scratch worktree was removed with `git worktree remove --force`, and the real tree's `git status --porcelain` matched its baseline.
- **Round-1 faults:** carried from a53464e. Their targets (`conftest.py`, `check_commits.py`, `docker-compose.yml`) are unchanged by the fix.

| Mutation | Location | Killed |
| --- | --- | --- |
| git-failure `return 2` -> `return 0` (verified at e1ce480) | `backend/scripts/check_commits.py:132` | yes - `test_range_that_git_cannot_read_exits_two_not_zero` failed |
| delete "with the test database up (`make infra` first)" from the hygiene line (verified at e1ce480) | `.claude/skills/learny-ship-cycle/SKILL.md:159` | yes - the C23 grep proof exited 1 |
| guard `== "1"` -> `== "yes"` (carried from a53464e) | `backend/tests/conftest.py:68` | yes - `test_require_db.py:44` |
| exact trailer -> case-insensitive prefix (carried) | `backend/scripts/check_commits.py:97` | yes - 2 near-miss cases |
| drop `"aider"` (carried) | `backend/scripts/check_commits.py:56` | yes - `test_check_commits.py:140` |
| bot skip `[bot]` -> `[robot]` (carried) | `backend/scripts/check_commits.py:136` | yes - `test_check_commits.py:221` |
| strip the redis digest (carried) | `docker-compose.yml:98` | yes - `test_image_pins.py:97` names the file |

## Gate

- **Targeted proofs at e1ce480:** 89 passed, 0 failed across the 5 proof modules. The C14-C23 shell proofs all exit 0. `python3 backend/scripts/check_commits.py d43402b..HEAD` reports 9 commits OK and exits 0, so the fix commit passes the new gate.
- **Full backend suite:** the fix added one test file change and no production change, so I did not re-run the suite and carried this from a53464e. The orchestrator log at `LEARNY_REQUIRE_DB=1` shows 3048 passed, 12 skipped (none database-gated) and 2 failed. Both failures are in `tests/test_deploy_topology.py`, and that file passes 29/29 in a clean worktree at HEAD, which confirms the cause is the local skip-worktree edit to `docker-compose.override.yml`.
- **Frontend:** 922 passed, as reported by the orchestrator and carried.
