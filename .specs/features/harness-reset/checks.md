# harness-reset — PR A checks

Profile: standard
Plan: `.specs/features/harness-reset/plan.md`

22 checks in 6 slices · 3 one-way doors · 0 open

## Checks

Commands run from `backend/` unless they start with `cd`. Database-backed proofs use `LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test_harness`.

### S1 - A run that skips the database suite cannot pass · 3 files · 6 KB · ~2k

**C1** - With `LEARNY_REQUIRE_DB=1` and no `LEARNY_TEST_DATABASE_URL`, pytest exits non-zero before any test runs and its output names `LEARNY_TEST_DATABASE_URL` (AC 1)
Proof: `uv run pytest -q tests/test_require_db.py -k refuses_a_run_without_a_database`

**C2** - Without the flag and without the URL, a database test is reported skipped and the run exits 0 (AC 2)
Proof: `uv run pytest -q tests/test_require_db.py -k still_skips_without_the_flag`

**C3** - CI's `backend-test` pytest step sets `LEARNY_REQUIRE_DB: "1"` (AC 3)
Proof: `uv run pytest -q tests/test_ci_workflow.py -k require_db`

### S2 - Commit messages are checked by CI · 4 files · 14 KB · ~4k

**C4** - CI declares a `commits` job that runs only on `pull_request`, checks out with `fetch-depth: 0`, and runs `backend/scripts/check_commits.py` over `github.event.pull_request.base.sha..github.event.pull_request.head.sha` (AC 4)
Proof: `uv run pytest -q tests/test_ci_workflow.py -k commits_job`

**C5** - A header outside the Conventional pattern, or with a type outside the 11 allowed, makes the checker exit 1 naming the SHA; each of the 11 types passes (AC 5)
Proof: `uv run pytest -q tests/test_check_commits.py -k header`

**C6** - A commit with no `Assisted-by: Claude Code` trailer line makes the checker exit 1 naming the SHA; a near-miss (`Assisted-by: Claude`, the text outside the trailer block) also fails (AC 6)
Proof: `uv run pytest -q tests/test_check_commits.py -k assisted_by`

**C7** - A `Co-authored-by:` trailer naming any of the 10 agent names (any case), or any `Made-with:` trailer, makes the checker exit 1 naming the SHA; a human `Co-authored-by:` passes (AC 7)
Proof: `uv run pytest -q tests/test_check_commits.py -k agent_trailer`

**C8** - Over a real git range, the checker skips merge commits and `[bot]`-authored commits, checks every other commit, and lists every failing SHA before exiting 1 (AC 4, 8)
Proof: `uv run pytest -q tests/test_check_commits.py -k range`

**C9** - `make lint` runs the checker over `origin/main..HEAD` (AC 9)
Proof: `uv run pytest -q tests/test_ci_workflow.py -k make_lint_checks_commits`

### S3 - CI builds what the repo pinned · 12 files · 40 KB · ~10k

**C10** - Every upstream image reference in tracked Dockerfiles (`FROM`, `COPY --from=<registry image>`), Compose files (`image:`) and workflow `services.*.image` matches `<name>:<tag>@sha256:<64 hex>`; repo-owned `ghcr.io/augusto-dmh/` images and build-stage names are exempt (AC 10)
Proof: `uv run pytest -q tests/test_image_pins.py`

**C11** - `docs/adr/0032-*.md` exists, is Accepted, names the `@sha256:` pin rule, the bump procedure, and links ADR-0031 (AC 11)
Proof: `uv run pytest -q tests/test_image_pins.py -k adr`

### S4 - The nightly eval stops pretending to run · 4 files · 40 KB · ~10k

**C12** - `eval.yml`'s `on` has `workflow_dispatch` with `generation_profiles` and no `schedule` (AC 12)
Proof: `uv run pytest -q tests/test_eval_workflow.py -k no_schedule`

**C13** - `eval.yml`, `CLAUDE.md` and `README.md` each state the schedule is off because the provider key is unfunded and runs are manual dispatch (AC 13)
Proof: `uv run pytest -q tests/test_eval_workflow.py -k schedule_off_reason`

### S5 - The harness loads only what it uses · ~30 files (mostly deletions) · ~8k

**C14** - `.specs/project/archive/STATE-v1-v7.md` equals the pre-cycle `STATE.md` byte for byte, and the live `STATE.md` has exactly the `##` sections `Handoff` and `Open decisions` (AC 14)
Proof: `cd /home/augusto/projects/learny/.worktrees/harness-reset && git diff --exit-code d43402b:.specs/project/STATE.md HEAD:.specs/project/archive/STATE-v1-v7.md && test "$(grep '^## ' .specs/project/STATE.md | tr '\n' '|')" = "## Handoff|## Open decisions|"`

**C15** - Neither `.specs/LESSONS.md` nor `.specs/lessons.json` exists (AC 15)
Proof: `cd /home/augusto/projects/learny/.worktrees/harness-reset && test ! -e .specs/LESSONS.md && test ! -e .specs/lessons.json`

**C16** - None of the 8 removed skill directories exists under `.claude/skills/` (AC 16)
Proof: `cd /home/augusto/projects/learny/.worktrees/harness-reset && for s in tlc-spec-driven redis-observability redis-security domain-analysis skill-architect grilling grill-me create-technical-design-doc; do test ! -e .claude/skills/$s || exit 1; done`

**C17** - All 15 kept skills still have a `SKILL.md` (AC 16)
Proof: `cd /home/augusto/projects/learny/.worktrees/harness-reset && for s in learny-ship-cycle learny-finalize pr-review fastapi pgvector-hybrid-search celery-workers epub-ingestion create-adr uv ruff vercel-composition-patterns vercel-react-best-practices web-design-guidelines modular-design-principles redis-core; do test -f .claude/skills/$s/SKILL.md || exit 1; done`

**C18** - No removed skill name appears in `SKILLS.md`, `.claude/skills/README.md`, `skills-lock.json` or `.agents/.skill-lock.json` (if present) (AC 17)
Proof: `cd /home/augusto/projects/learny/.worktrees/harness-reset && ! grep -nE "tlc-spec-driven|redis-observability|redis-security|domain-analysis|skill-architect|grilling|grill-me|create-technical-design-doc" SKILLS.md .claude/skills/README.md skills-lock.json $(ls .agents/.skill-lock.json 2>/dev/null)`

**C19** - `learny-ship-cycle` carries the five synthesis model rows and no longer says "never Sonnet" or names Haiku as a pipeline tier (AC 18)
Proof: `cd /home/augusto/projects/learny/.worktrees/harness-reset && f=.claude/skills/learny-ship-cycle/SKILL.md && grep -q "| Plan and door gate (main thread) | Fable or Opus |" $f && grep -q "| Build | Opus |" $f && grep -q "| Verifier | Opus, never the cheapest tier |" $f && grep -q "| Review lanes | Sonnet for mechanical lanes, Opus for correctness, security and architecture |" $f && grep -q "| Sub-agents | Never Fable |" $f && ! grep -qiE "never Sonnet|Haiku" $f`

**C20** - `.claude/settings.json` has `attribution == {"commit": "Assisted-by: Claude Code", "pr": ""}` and no `includeCoAuthoredBy` (AC 19)
Proof: `cd /home/augusto/projects/learny/.worktrees/harness-reset && python3 -c "import json,sys; s=json.load(open('.claude/settings.json')); sys.exit(0 if s.get('attribution')=={'commit':'Assisted-by: Claude Code','pr':''} and 'includeCoAuthoredBy' not in s else 1)"`

**C21** - `learny-finalize` requires `Assisted-by: Claude Code`, names it as the override of tlc-spec-lean's no-trailer rule, forbids `Co-authored-by`/`Made-with` agent trailers and PR-body attribution, and no longer says "Never add authorship or tooling attribution to commits" (AC 20)
Proof: `cd /home/augusto/projects/learny/.worktrees/harness-reset && f=.claude/skills/learny-finalize/SKILL.md && grep -q "Assisted-by: Claude Code" $f && grep -q "tlc-spec-lean" $f && grep -q "Made-with" $f && grep -qi "Co-authored-by" $f && ! grep -q "Never add authorship or tooling attribution to commits" $f`

### S6 - The cycle is on the roadmap · 1 file · 18 KB · ~5k

**C22** - `ROADMAP.md` has a `## Harness` section whose table has a `harness-reset` PR A row and a PR B row marked `Not started` (AC 21)
Proof: `cd /home/augusto/projects/learny/.worktrees/harness-reset && python3 -c "import re,sys; t=open('.specs/project/ROADMAP.md').read(); s=t[t.index('## Harness'):]; s=s[:s.find('\n## ',1) if s.find('\n## ',1)>0 else len(s)]; sys.exit(0 if re.search(r'harness-reset.*PR A', s) and re.search(r'harness-reset.*PR B.*Not started', s) else 1)"`

## Coverage

| Set (size) | Member -> proof | Unproven |
| --- | --- | --- |
| commit types (11) | C5, table-driven over all 11 | - |
| agent names rejected in `Co-authored-by` (10) | C7, table-driven over all 10 | - |
| other rejected trailer (1) | `Made-with` C7 | - |
| commits skipped by the range walk (2) | merge C8 · `[bot]` author C8 | - |
| upstream image reference kinds (4) | Dockerfile `FROM` C10 · `COPY --from` C10 · Compose `image:` C10 · workflow `services.*.image` C10 | - |
| places that must run pytest with the flag (1) | CI `backend-test` C3 | - |
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
