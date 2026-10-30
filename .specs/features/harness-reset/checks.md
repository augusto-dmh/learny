# harness-reset — PR A checks

Mutations: 3
Build: cd backend && uv run ruff check .; cd backend && uv run ruff format --check .; cd backend && python scripts/check_boundaries.py
Profile: standard
Plan: `.specs/features/harness-reset/plan.md`

24 checks in 7 slices · 3 one-way doors · 0 open

## Checks

Commands run from `backend/` unless they start with `cd`. Database-backed proofs use `LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test_harness`. PR B rewrote the PR A proofs to be machine-independent (pytest sensors in `tests/test_harness_skills.py` replace the Linux-worktree shell proofs; the claims are unchanged except C22, which no longer pins the PR B row's status, and C25, whose gate-script count now matches the ten scripts its criterion enumerates).

### S1 - A run that skips the database suite cannot pass · 3 files · 6 KB · ~2k

**C1** - With `LEARNY_REQUIRE_DB=1` and no `LEARNY_TEST_DATABASE_URL`, pytest exits non-zero before any test runs and its output names `LEARNY_TEST_DATABASE_URL` (AC 1)
Proof: `cd backend && uv run pytest -q tests/test_require_db.py -k refuses_a_run_without_a_database`

**C2** - Without the flag and without the URL, a database test is reported skipped and the run exits 0 (AC 2)
Proof: `cd backend && uv run pytest -q tests/test_require_db.py -k still_skips_without_the_flag`

**C3** - CI's `backend-test` pytest step sets `LEARNY_REQUIRE_DB: "1"` (AC 3)
Proof: `cd backend && uv run pytest -q tests/test_ci_workflow.py -k require_db`

### S2 - Commit messages are checked by CI · 4 files · 14 KB · ~4k

**C4** - CI declares a `commits` job that runs only on `pull_request`, checks out with `fetch-depth: 0`, and runs `backend/scripts/check_commits.py` over `github.event.pull_request.base.sha..github.event.pull_request.head.sha` (AC 4)
Proof: `cd backend && uv run pytest -q tests/test_ci_workflow.py -k commits_job`

**C5** - A header outside the Conventional pattern, or with a type outside the 11 allowed, makes the checker exit 1 naming the SHA; each of the 11 types passes (AC 5)
Proof: `cd backend && uv run pytest -q tests/test_check_commits.py -k header`

**C6** - A commit with no `Assisted-by: Claude Code` trailer line makes the checker exit 1 naming the SHA; a near-miss (`Assisted-by: Claude`, the text outside the trailer block) also fails (AC 6)
Proof: `cd backend && uv run pytest -q tests/test_check_commits.py -k assisted_by`

**C7** - A `Co-authored-by:` trailer naming any of the 10 agent names (any case), or any `Made-with:` trailer, makes the checker exit 1 naming the SHA; a human `Co-authored-by:` passes (AC 7)
Proof: `cd backend && uv run pytest -q tests/test_check_commits.py -k agent_trailer`

**C8** - Over a real git range, the checker skips merge commits and `[bot]`-authored commits, checks every other commit, and lists every failing SHA before exiting 1 (AC 4, 8)
Proof: `cd backend && uv run pytest -q tests/test_check_commits.py -k range`

**C9** - `make lint` runs the checker over `origin/main..HEAD` (AC 9)
Proof: `cd backend && uv run pytest -q tests/test_ci_workflow.py -k make_lint_checks_commits`

### S3 - CI builds what the repo pinned · 12 files · 40 KB · ~10k

**C10** - Every upstream image reference in tracked Dockerfiles (`FROM`, `COPY --from=<registry image>`), Compose files (`image:`) and workflow `services.*.image` matches `<name>:<tag>@sha256:<64 hex>`; repo-owned `ghcr.io/augusto-dmh/` images and build-stage names are exempt (AC 10)
Proof: `cd backend && uv run pytest -q tests/test_image_pins.py`

**C11** - `docs/adr/0032-*.md` exists, is Accepted, names the `@sha256:` pin rule, the bump procedure, and links ADR-0031 (AC 11)
Proof: `cd backend && uv run pytest -q tests/test_image_pins.py -k adr`

### S4 - The nightly eval stops pretending to run · 4 files · 40 KB · ~10k

**C12** - `eval.yml`'s `on` has `workflow_dispatch` with `generation_profiles` and no `schedule` (AC 12)
Proof: `cd backend && uv run pytest -q tests/test_eval_workflow.py -k no_schedule`

**C13** - `eval.yml`, `CLAUDE.md` and `README.md` each state the schedule is off because the provider key is unfunded and runs are manual dispatch (AC 13)
Proof: `cd backend && uv run pytest -q tests/test_eval_workflow.py -k schedule_off_reason`

### S5 - The harness loads only what it uses · ~30 files (mostly deletions) · ~8k

**C14** - `.specs/project/archive/STATE-v1-v7.md` equals the pre-cycle `STATE.md` byte for byte, and the live `STATE.md` has exactly the `##` sections `Handoff` and `Open decisions` (AC 14)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k state_archive`

**C15** - Neither `.specs/LESSONS.md` nor `.specs/lessons.json` exists (AC 15)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k lessons_files_gone`

**C16** - None of the 8 removed skill directories exists under `.claude/skills/` (AC 16)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k removed_skills_absent`

**C17** - All 15 kept skills still have a `SKILL.md` (AC 16)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k kept_skills_present`

**C18** - No removed skill name appears in `SKILLS.md`, `.claude/skills/README.md`, `skills-lock.json` or `.agents/.skill-lock.json` (if present) (AC 17)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k removed_skills_unlisted`

**C19** - `learny-ship-cycle` carries the five synthesis model rows and no longer says "never Sonnet" or names Haiku as a pipeline tier (AC 18)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k model_table`

**C20** - `.claude/settings.json` has `attribution == {"commit": "Assisted-by: Claude Code", "pr": ""}` and no `includeCoAuthoredBy` (AC 19)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k attribution_setting`

**C21** - `learny-finalize` requires `Assisted-by: Claude Code`, names it as the override of tlc-spec-lean's no-trailer rule, forbids `Co-authored-by`/`Made-with` agent trailers and PR-body attribution, and no longer says "Never add authorship or tooling attribution to commits" (AC 20)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k finalize_trailer_rule`

### S6 - The cycle is on the roadmap · 1 file · 18 KB · ~5k

**C22** - `ROADMAP.md` has a `## Harness` section whose table has a `harness-reset` PR A row and a PR B row (AC 21; PR B dropped the `Not started` status pin - the wrap commit marks the row done, and a status pin would keep the proof red on `main` forever)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k roadmap_harness_rows`

### S7 - The Verifier cannot pass over a skipped database suite (added after Verifier round 1) · 2 files · ~2k

**C23** - The `learny-ship-cycle` hygiene rules require every Verifier run to use `LEARNY_REQUIRE_DB=1` and start the test database with `make infra` first (AC 22)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k verifier_requires_db`

**C24** - A range git cannot read makes the checker exit 2 with the range named on stderr (AC 23)
Proof: `cd backend && uv run pytest -q tests/test_check_commits.py -k cannot_read`

## Coverage

| Set (size) | Member -> proof | Unproven |
| --- | --- | --- |
| commit types (11) | C5, table-driven over all 11 | - |
| agent names rejected in `Co-authored-by` (10) | C7, table-driven over all 10 | - |
| other rejected trailer (1) | `Made-with` C7 | - |
| commits skipped by the range walk (2) | merge C8 · `[bot]` author C8 | - |
| checker exit codes (3) | 0 C8 · 1 C8 · 2 C24 | - |
| upstream image reference kinds (4) | Dockerfile `FROM` C10 · `COPY --from` C10 · Compose `image:` C10 · workflow `services.*.image` C10 | - |
| places that must run pytest with the flag (2) | CI `backend-test` C3 · Verifier brief (`learny-ship-cycle` hygiene) C23 | - |
| places that run the commit checker (2) | CI `commits` job C4 · `make lint` C9 | - |
| places that state the nightly reason (3) | `eval.yml` C13 · `CLAUDE.md` C13 · `README.md` C13 | - |
| removed skills (8) | `tlc-spec-driven` C16, C18 · `redis-observability` C16, C18 · `redis-security` C16, C18 · `domain-analysis` C16, C18 · `skill-architect` C16, C18 · `grilling` C16, C18 · `grill-me` C16, C18 · `create-technical-design-doc` C16, C18 | - |
| kept skills (15) | `learny-ship-cycle` C17 · `learny-finalize` C17 · `pr-review` C17 · `fastapi` C17 · `pgvector-hybrid-search` C17 · `celery-workers` C17 · `epub-ingestion` C17 · `create-adr` C17 · `uv` C17 · `ruff` C17 · `vercel-composition-patterns` C17 · `vercel-react-best-practices` C17 · `web-design-guidelines` C17 · `modular-design-principles` C17 · `redis-core` C17 | - |
| in-repo one-way doors (2) | commit contract C4, C5, C6, C7, C8 · pin format C10, C11 | - |

- Door 1 (the `main` ruleset) is an outward GitHub setting applied after merge on the owner's yes; it is not in the diff, so it carries no check here. Its proof is a `gh api repos/augusto-dmh/learny/rulesets` readback recorded in the Stage 8 report.
- No other check claims more than the single case its proof exercises.

## Test policy

The repo's tests already prove workflow YAML and docs with parse-and-assert tests (`test_eval_workflow.py`, `test_deploy_workflow.py`, `test_readme_truth.py`); the new checker is a stdlib script like `check_boundaries.py`, which has no test of its own, so these rows set the bar here.

| Code | Required proofs | Coverage expectation |
| --- | --- | --- |
| `check_commits.py` message rules (decides) | at its own layer, pure function | one asserted case per header rule, per type, per rejected trailer name |
| `check_commits.py` range walk (decides: merge/bot skip, aggregation) | at the boundary - a real temporary git repository | merge skipped, bot skipped, multiple failures all named |
| `conftest.py` flag guard (decides) | at the boundary - a pytest subprocess | flag on + URL unset fails; flag off + URL unset skips |
| Workflow YAML, Compose, Dockerfiles (configuration) | parse-and-assert sensor | every member of the set, not a sample |

Evidence:

- `backend/scripts/check_commits.py`: header pattern, type list (11), trailer presence, agent-trailer list (10 + `Made-with`), merge skip, bot skip -> decides
- `backend/tests/conftest.py`: one guard (flag × URL) -> decides
- closest analogue: `backend/tests/test_eval_workflow.py` (YAML parse-and-assert per contract item)

Cost: 3 new test modules plus additions to 2 existing ones.

## Swept

- validation: C5, C6, C7
- failure modes: C1, C8
- idempotency: n/a - the checker and the image sensor only read; rerunning gives the same verdict
- authorization: n/a - no app authorization changes; the `main` ruleset (door 1) is an outward setting applied after merge and read back via the API
- concurrency: n/a - four lanes merge in any order; the ruleset leaves "require branches up to date" off (Landing door 1)
- data lifecycle: C14, C15
- dependency failure: C10, C11
- state transitions: n/a - no stateful entity changes
- observability: C1 (names the missing variable), C8 (names every failing SHA)

## Handoff

- S1–S6 ≈ 2k + 4k + 10k + 10k + 8k + 5k = ~39k, under the 150k budget - one builder (inline, this session); Verifier is a fresh Opus sub-agent over `d43402b..HEAD` with `LEARNY_REQUIRE_DB=1`

---

# PR B — the loop checks

18 checks in 5 slices · 3 one-way doors · 0 open

File-level lines live at the top of this file (`Mutations: 3`, the `Build:` lint commands). Commands run from `backend/` unless they start with `cd`. The PR B sensors live in `tests/test_harness_skills.py`.

## PR B Checks

### S8 - The lean spec skill is vendored with its deviations · ~50 files · ~30 KB vendored · ~2k

**C25** - The vendored tree is complete: `SKILL.md`, the 6 reference files, the 10 gate scripts and the 4 fixture files exist under `.claude/skills/tlc-spec-lean/`, and `SKILL.md` names the skill `tlc-spec-lean` (AC 24)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k vendored_tree`

**C26** - The vendored `SKILL.md` carries a Learny deviations section naming both recorded deviations: the per-batch Verifier (decision D2) and the `Assisted-by: Claude Code` trailer overriding lean's no-trailer rule (decision D3) (AC 25)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k vendored_deviations`

**C27** - The vendored `references/build.md` requires the `Assisted-by: Claude Code` trailer on every commit and names it as this repo's exception to the skill's no-agent-trailer rule (AC 26)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k vendored_build_override`

**C28** - The vendored commit gate runs on this interpreter: each of the repo's 11 commit types exits 0 and a disallowed type exits 1 (AC 27)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k vendored_commit_gate`

**C29** - The skills README records the vendored copy's source, version 2.1.0, the two deviations, and the owner action that makes the project copy load (remove/rename the user-level copy, then confirm from the client's `Base directory` line) (AC 28)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k vendored_provenance`

### S9 - The ship cycle runs on the lean skill with two lanes and the door gate · 1 file · ~3k

**C30** - The ship-cycle skill names the vendored `tlc-spec-lean` (profile `standard`, budget 150k) in its description, intro and Stage 1 title, and the string `tlc-spec-driven` appears nowhere in it (AC 29)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k shipcycle_lean`

**C31** - Stage Detection maps a feature folder with `plan.md` but no `checks.md` to Stage 1 (lean Plan), one with `checks.md` but no `verification.md` to Stage 1 (lean Build/Verify), and defines a Verifier PASS as `validate_verification.py <cycle> --root <repo>` exiting 0 (AC 30)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k shipcycle_stage_detection`

**C32** - Stage 0 chooses the lane by a checkable rule - Lane S for a one-sentence diff (about 3 files or fewer, no migration, no new ADR, no new route or screen, no one-way door), Lane F for everything else including every roadmap row - and the cycle cannot downgrade a lane on its own (AC 31)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k shipcycle_lanes`

**C33** - Stage 1 stops at the D1 door gate: one question listing the plan's one-way doors and unconfirmed assumptions, waivable in `auto` mode with the waiver recorded in the plan (AC 32)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k shipcycle_door_gate`

**C34** - Stage 1's auto-decision rule writes decisions to `plan.md` `## Assumptions` with `Confirmed? n`, doors to `Landing`, and an `AD-NNN` row only for decisions binding other cycles (AC 33)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k shipcycle_decisions`

**C35** - Over the 150k budget, Stage 1 pre-answers lean's mechanism ask with handoff and splits at slice boundaries into sequential batch PRs, with the Verifier scoped to each batch's checks before its PR and over every check before the last batch's PR (decision D2) (AC 34)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k shipcycle_batches`

**C36** - The cost-discipline section keeps the five synthesis model rows verbatim and asks for one coherent piece per commit with its check marked in `checks.md` in the same commit; the `LEARNY_REQUIRE_DB=1` + `make infra` Verifier rule lives in the skill's Hygiene section, pinned by C23 (AC 35)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k shipcycle_cost_discipline`

### S10 - Review and finalize speak lean, with a legacy fallback · 4 files · ~2k

**C37** - `pr-review` Track A reads `plan.md`, `checks.md` and `verification.md` with numbered criteria and `C`-ids for lean cycles, and keeps the legacy `spec.md`/`tasks.md`/`validation.md` + `FR-*` path for the driven folders that remain (AC 36)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k review_track_a`

**C38** - `learny-finalize` forbids slice and check ids (`S2`, `C4`) alongside task and phase ids in permanent history, and names `checks.md` (not `tasks.md`) as where internal traceability lives (AC 37)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k finalize_internal_refs`

**C39** - `SKILLS.md` and `.claude/skills/README.md` describe `tlc-spec-lean` as vendored into `.claude/skills/`, with no user-level-skill wording and no promise of the rewiring in a future cycle (AC 38)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k skills_docs`

**C40** - `CLAUDE.md` carries a `## tlc-spec-lean` block pinning `profile: standard` and the 150k budget, and its Workflow section names the vendored `tlc-spec-lean`, with `tlc-spec-driven` gone (AC 39)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k claude_profile`

### S11 - Local worktrees stop being noise · 1 file · <1k

**C41** - `.gitignore` ignores `.worktrees/` (AC 40)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k gitignore_worktrees`

### S12 - The PR A checks re-run on any checkout · 2 files · ~2k

**C42** - Every `Proof:` line in this checks.md is machine-independent: no absolute filesystem path on any of them, so the lean proof gates can run all 42 checks wherever the repo is cloned (AC 41)
Proof: `cd backend && uv run pytest -q tests/test_harness_skills.py -k proofs_portable`

## Coverage (PR B)

| Set (size) | Member -> proof | Unproven |
| --- | --- | --- |
| vendored artifact kinds (4) | SKILL.md C25 · references C25 · scripts C25 · fixtures C25 | - |
| recorded deviations (2) | per-batch Verifier C26, C35 · trailer override C26, C27 | - |
| vendored gate behaviour (2 outcomes) | Conventional header exits 0 C28 · disallowed type exits 1 C28 | - |
| files the rewiring must de-drive (5) | ship-cycle C30 · pr-review C37 · finalize C38 · SKILLS.md C39 · CLAUDE.md C40 | - |
| ship-cycle mechanics rewired (5) | Stage Detection C31 · lane rule C32 · door gate C33 · decision records C34 · batch split C35 | - |
| model rows kept verbatim (5) | plan/door gate C36 · build C36 · Verifier C36 · review lanes C36 · sub-agents C36 | - |
| lean artifacts Track A reads (3) | plan.md C37 · checks.md C37 · verification.md C37 | - |
| legacy artifacts Track A keeps (3) | spec.md C37 · tasks.md C37 · validation.md C37 | - |
| PR A checks re-proven portably (24) | C1-C24, each by its rewritten proof, all green through check_proofs at HEAD | - |
| untracked-noise exclusions (1) | `.worktrees/` C41 | - |

## Swept (PR B)

- validation: C28
- failure modes: C28
- idempotency: n/a - every change is git-tracked text; re-running the sensors gives the same verdict
- authorization: n/a - no app authorization changes; the door gate and merge gate are unchanged
- concurrency: n/a - three sibling lanes merge in any order; this PR touches no workflow requirements
- data lifecycle: n/a - no stored data touched (plan Shape: Data none)
- dependency failure: C25 - a missing vendored file fails the tree check by name
- state transitions: C31 - Stage Detection now names the lean artifact states a cycle actually passes through
- observability: C28 - the vendored gate prints its verdict and the exit code decides

## Handoff (PR B)

- **Settled mid-build:** none - run mode auto; the door gate is waived by the standing authorization recorded on the plan's Approved line
- **Dispatched:** Verifier (independent session) over every check at `b6f9f48` - FAIL: 6 findings, 3 mutations unkilled; closed by `f9342a9`, `40b9515`, `b280ca2`, proofs and mutations green at `b280ca2`
- **Review:** fresh-context `pr-review` (six lanes) over `f12b578` - 18 inline findings + 2 summary comments; triaged in `review-triage-pr-b.md` (16 real, 14 fixed by `1d7dc63`, `0bd3e60`, `9c47037`, 5 won't-fix with reasons); proofs re-run and 3 mutations killed at `9c47037` **through the vendored scripts**, selftest 79 killed
- **Boundary:** C25-C42 closed at `c0a08c5`
- **Abandoned:** none
