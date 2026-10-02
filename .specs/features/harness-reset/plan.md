# harness-reset — PR A: sensors and hygiene

## Problem

Learny's delivery harness reports green when it has not checked anything, and carries paperwork nobody reads.

- A Verifier issued PASS on PR #71 with "2030 passed, 940 skipped (all db-gated)"; CI then failed 4 of those tests on first execution. `backend/tests/conftest.py:23` skips every database test silently when `LEARNY_TEST_DATABASE_URL` is unset, and nothing can turn that skip into a failure.
- Commit rules live only in prose: PR #69 merged 9 untyped commits, and no CI step reads commit messages. The owner's attribution decision (D3, `Assisted-by: Claude Code`) has no enforcement at all, and `learny-finalize` still forbids every trailer.
- Upstream images float on mutable tags (`redis:7-alpine`, `node:20-slim`, `pgvector/pgvector:pg16`, ...); upstream rot broke CI twice in September (#71, #72).
- The nightly eval has been red for 66 consecutive runs because its provider key is unfunded, so red on `main`'s Actions page means nothing.
- `.specs/project/STATE.md` is 247 KB, `LESSONS.md` has never promoted a lesson, the vendored `tlc-spec-driven` is shadowed by the user-level copy, and seven project skills were never referenced. Every session pays for their descriptions; fixes land in copies that do not load.
- `main` has no ruleset: a red PR can merge and anything can be pushed.

Evidence: `docs/research/2026-09-30/harness/synthesis.md` (Moves 1, sensors 1–5, paperwork diet, model policy) and `rq03` F5–F9; owner decisions D1–D6 (2026-10-02).

When this ships, a skipped database suite cannot pass in CI, a commit without the agreed trailer cannot merge, image rot cannot change what CI builds, the only red workflow is one that ran, and the harness files a session loads are the ones it uses.

## Flow

Reuses the existing CI jobs (`backend-test`, `lint`), the stdlib-script pattern of `backend/scripts/check_boundaries.py`, the `test_*_workflow.py` YAML-pin test style, and the README/CLAUDE.md drift tests; nothing in the app changes.

1. PR opened -> `.github/workflows/ci.yml` (exists) - new `commits` job checks out full history and runs the commit checker over `base.sha..head.sha`
2. `backend/scripts/check_commits.py` (new, no door - placement beside `check_boundaries.py`) - header format + trailer rules per non-merge, non-bot commit; exit 1 names each failing SHA
3. `backend-test` job (exists) - runs pytest with `LEARNY_REQUIRE_DB=1`; `backend/tests/conftest.py` (exists) refuses to start a run that would skip the database suite
4. Docker builds and service containers (exist) - resolve upstream images by the pinned digest, not the tag
5. `.github/workflows/eval.yml` (exists) - runs only on `workflow_dispatch`
6. out: `main` ruleset (door 1) requires the CI jobs green before a PR merges

## Impact

| Front | What changes |
| --- | --- |
| domain | new term: `LEARNY_REQUIRE_DB` - test-run flag; `1` makes a missing test database a run failure instead of a skip. Read only by `backend/tests/conftest.py` |
| harness | `STATE.md` changes meaning: was the full decision log + every cycle's handoff; now only the live Handoff + open cross-cycle decisions. Who reads it today: `learny-ship-cycle` Stage 0 and Stage 1 (AD-row append), the user-level `tlc-spec-driven` scripts (`validate_state.py`) if a sibling cycle still runs driven |
| harness | commit contract changes for every lane: every PR commit now needs `Assisted-by: Claude Code`. The four parallel cycles' PRs run this gate once this merges (pull_request CI uses the merge ref) |
| stored data | nothing to migrate - no app data touched; the old STATE.md content moves to `.specs/project/archive/STATE-v1-v7.md` unchanged |

## Relations

`None - no stored-data shape change`

## Surface

`None - nothing consumed outside`; the only new contract is CI behaviour, recorded under Landing.

## Landing

| One-way door | Literal shape | Alternative rejected |
| --- | --- | --- |
| 1. `main` ruleset (outward GitHub setting, applied after merge on the owner's explicit yes) | branch ruleset `main-guard` on `refs/heads/main`: `pull_request` (0 approvals), `required_status_checks` = `backend-test`, `lint`, `frontend`, `compose-smoke`, `commits` with `strict_required_status_checks_policy: false`, `non_fast_forward`, `deletion`; bypass actor = Repository admin role, `bypass_mode: always` | bypass `pull_request`-only or no bypass - breaks the Stage 8 `docs(specs)` wrap that four running lanes push straight to `main`; strict up-to-date checks - forces a rebase-and-rerun on every sibling merge across four lanes |
| 2. Commit contract enforced in CI | required trailer line `Assisted-by: Claude Code`; rejected `Co-authored-by:` naming an AI agent and any `Made-with:`; header `^(feat\|fix\|docs\|refactor\|test\|chore\|build\|ci\|perf\|style\|revert)(\([a-z0-9-]+\))?!?: [a-z0-9]` (learny-finalize's list); commits authored by `*[bot]` exempt | trailer optional - D3 makes it required; checking the whole history - every pre-D3 commit fails; internal-reference scan in CI - `validate_metadata.py`'s `ADR-` pattern false-positives on commits that legitimately add an ADR |
| 3. Upstream image pin format (precedent every new image copies) | `<image>:<tag>@sha256:<64 hex>` (multi-arch index digest), tag kept for readability; recorded in ADR-0032 extending ADR-0031 | digest without tag - unreadable; Dependabot `docker` updates - opens version-bump PRs the repo turned off for pip/npm and they would hit the commit gate's bot path |

- Nothing else in this change is hard to reverse: every deletion (STATE content, lessons, skills) is recoverable from git, and the nightly `schedule` returns with one YAML line.

## Criteria

### S1: A run that skips the database suite cannot pass (P1)

**Acceptance Criteria**

1. WHERE `LEARNY_REQUIRE_DB=1` is set, IF `LEARNY_TEST_DATABASE_URL` is unset THEN pytest SHALL exit non-zero before running any test, with a message naming `LEARNY_TEST_DATABASE_URL`
2. WHILE `LEARNY_REQUIRE_DB` is unset, the system SHALL keep skipping database tests when `LEARNY_TEST_DATABASE_URL` is unset (local unit-only runs unchanged)
3. The CI `backend-test` job SHALL run pytest with `LEARNY_REQUIRE_DB: "1"`

**Independent test:** `LEARNY_REQUIRE_DB=1 LEARNY_TEST_DATABASE_URL= uv run pytest -q tests/test_readme_truth.py` exits non-zero.

### S2: Commit messages are checked by CI (P1)

**Acceptance Criteria**

4. WHEN a pull request is opened or updated THEN CI SHALL run a `commits` job over every non-merge commit in `base.sha..head.sha`
5. IF a commit header does not match the Conventional Commit pattern with a type from `feat, fix, docs, refactor, test, chore, build, ci, perf, style, revert` THEN the checker SHALL exit 1 and name that commit's SHA
6. IF a commit has no trailer line exactly `Assisted-by: Claude Code` THEN the checker SHALL exit 1 and name that commit's SHA
7. IF a commit carries a `Co-authored-by:` trailer naming an AI agent (case-insensitive: claude, anthropic, cursor, copilot, codex, openai, chatgpt, gemini, devin, aider) or any `Made-with:` trailer THEN the checker SHALL exit 1 and name that commit's SHA
8. WHEN a commit's author name ends in `[bot]` THEN the checker SHALL skip that commit
9. WHEN `make lint` runs THEN it SHALL run the same checker over `origin/main..HEAD`

**Independent test:** a throwaway git repo with one good and one trailer-less commit; the checker exits 1 naming only the second.

### S3: CI builds what the repo pinned (P1)

**Acceptance Criteria**

10. The system SHALL reference every upstream (non-`ghcr.io/augusto-dmh/`) image in tracked Dockerfiles (`FROM`, `COPY --from=<registry image>`), Compose files (`image:`) and workflow `services.*.image` as `<name>:<tag>@sha256:<64 lowercase hex>`
11. The system SHALL record the pin rule and how to bump a digest in `docs/adr/0032-*.md`, linked from ADR-0031's approach

**Independent test:** replace one digest pin with a bare tag; the sensor test fails naming the file.

### S4: The nightly eval stops pretending to run (P1)

**Acceptance Criteria**

12. The `Nightly eval` workflow SHALL declare no `schedule` trigger and SHALL keep `workflow_dispatch` with its `generation_profiles` input
13. The system SHALL state in `eval.yml`, `CLAUDE.md` and `README.md` that the schedule is off because the CI provider key is unfunded and that runs are manual dispatch

**Independent test:** parse `eval.yml`; `on` has `workflow_dispatch` and no `schedule`.

### S5: The harness loads only what it uses (P2)

**Acceptance Criteria**

14. The system SHALL keep the previous `.specs/project/STATE.md` byte-identical at `.specs/project/archive/STATE-v1-v7.md`, and the live `STATE.md` SHALL have exactly the sections `## Handoff` and `## Open decisions`
15. The system SHALL contain neither `.specs/LESSONS.md` nor `.specs/lessons.json`
16. The system SHALL contain no `.claude/skills/tlc-spec-driven` and none of `redis-observability`, `redis-security`, `domain-analysis`, `skill-architect`, `grilling`, `grill-me`, `create-technical-design-doc` under `.claude/skills/`, and SHALL still contain `learny-ship-cycle`, `learny-finalize`, `pr-review`, `fastapi`, `pgvector-hybrid-search`, `celery-workers`, `epub-ingestion`, `create-adr`, `uv`, `ruff`, `vercel-composition-patterns`, `vercel-react-best-practices`, `web-design-guidelines`, `modular-design-principles`, `redis-core`
17. The system SHALL list no removed skill in `SKILLS.md`, `.claude/skills/README.md`, `skills-lock.json` or `.agents/.skill-lock.json`
18. The `learny-ship-cycle` skill SHALL carry the synthesis model table (plan/door gate Fable or Opus; build Opus; Verifier Opus, never the cheapest tier; review lanes Sonnet mechanical, Opus correctness/security/architecture; sub-agents never Fable) and no rule contradicting it
19. The project `.claude/settings.json` SHALL set `attribution.commit` to `Assisted-by: Claude Code` and `attribution.pr` to `""`, and SHALL not set `includeCoAuthoredBy`
20. The `learny-finalize` skill SHALL require the `Assisted-by: Claude Code` trailer on every commit, name it as the project override of tlc-spec-lean's no-trailer rule, and forbid `Co-authored-by`/`Made-with` agent trailers and any attribution in PR bodies

### S6: The cycle is on the roadmap (P1)

**Acceptance Criteria**

21. The roadmap `.specs/project/ROADMAP.md` SHALL have a `Harness` section with a `harness-reset` PR A row (this PR) and a PR B row (`Not started`)

## Out of scope

| Excluded | Why |
| --- | --- |
| PR B: vendoring `tlc-spec-lean`, rewiring ship-cycle Stage Detection/Stage 1, `pr-review` Track A, two lanes, door gate in the skill | next cycle in this lane (Move 2) |
| Stop-hook "grind" (sensor 6) | synthesis: only after sensors 1–5 are in |
| Pinning GitHub Actions by SHA | Dependabot already keeps the action majors current; not in the synthesis' sensor list |
| Any app/product code, provider choices, Houston as a dependency | brief and synthesis out of scope |

## Assumptions

| Assumption | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| Which skills to keep despite rq03 F8 | keep `modular-design-principles` (pr-review loads it by path, `pr-review/SKILL.md:61,168`) and `redis-core` (four kept skills point to it) | pruning them breaks a skill a running cycle uses | y |
| `LEARNY_REQUIRE_DB` scope | database only; Redis and S3 reachability skips stay as they are | the 940-skip incident was DB-gated; Redis/S3 skip 2 modules and are a candidate follow-up | y |
| `make test-backend` default | does not set `LEARNY_REQUIRE_DB`; CI and the Verifier brief do | keeps a fast unit-only local loop; the honest gate is CI + Verifier | y |
| Ruleset timing | applied after this PR merges, so the `commits` check exists on `main` before it is required | a required check that no workflow on `main` reports blocks every PR | y |
| Stage 8 wrap with the ruleset | stays a direct push to `main` (recorded admin bypass); ship-cycle gains "never `gh pr merge --admin`" | going through a PR doubles CI for one-line docs commits across four lanes; `gh pr merge` without `--admin` still refuses a red PR | y |
| Live STATE `## Open decisions` content | D1–D6 with their consequence, AD-360 marked superseded by D5, next AD number pointer | the only cross-cycle decisions still steering work | y |
| Digest freshness | bumped deliberately (ADR-0032 procedure), no automated updater | same trust model as ADR-0031's MinIO pin | y |

**Open questions:** none - all resolved or logged above.

## Observable

| Surface | Decision | Landing |
| --- | --- | --- |
| command `check_commits.py` | output format and exit codes | AC 5, 6, 7 (exit 1 naming SHAs; 0 otherwise) |
| command `check_commits.py` | flags and defaults | AC 9 (range defaults to `origin/main..HEAD`) |
| command `check_commits.py` | what it prints when it fails halfway | every commit is checked and all failures listed before exit (AC 5–7) |
| command `pytest` under `LEARNY_REQUIRE_DB=1` | output and exit code on failure | AC 1 |
| document `eval.yml` / CLAUDE.md / README | what the reader does next | AC 13 (fund the key, dispatch manually) |
| document `learny-finalize` / ship-cycle | structure and what the agent does next | AC 18, 20 |
| screen, API | n/a - no product surface changes |  n/a - harness-only PR |

## Sources

- `docs/research/2026-09-30/harness/synthesis.md` - sensors 1–5, paperwork diet, model table, Moves 1–2, owner decisions D1–D6
- `docs/research/2026-09-30/harness/rq03-learny-harness-audit.md` F5, F7, F8, F9 - evidence and the prune list
