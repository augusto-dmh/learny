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
13. The system SHALL state in `.github/workflows/eval.yml`, `CLAUDE.md` and `README.md` that the schedule is off because the CI provider key is unfunded and that runs are manual dispatch

**Independent test:** parse `.github/workflows/eval.yml`; `on` has `workflow_dispatch` and no `schedule`.

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

### S7: The Verifier cannot pass over a skipped database suite (P1) - added after Verifier round 1

**Acceptance Criteria**

22. The `learny-ship-cycle` skill SHALL require every Verifier run to use `LEARNY_REQUIRE_DB=1` with the test database started (`make infra`) first
23. IF `git log` cannot read the requested range THEN the commit checker SHALL exit 2 and name the range, never 0

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
| `web-design-guidelines`, listed by rq03 F8 as never referenced | keep it | the owner's brief for this cycle names it among the skills running cycles use; the v8 rows now in flight (`pt-br-interface`, installable launch) are UI work | y |
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
| command `check_commits.py` | output format and exit codes | AC 5, 6, 7 (exit 1 naming SHAs), AC 23 (exit 2 naming the range when git cannot read it); 0 otherwise |
| command `check_commits.py` | flags and defaults | AC 9 (range defaults to `origin/main..HEAD`) |
| command `check_commits.py` | what it prints when it fails halfway | every commit is checked and all failures listed before exit (AC 5–7) |
| command `pytest` under `LEARNY_REQUIRE_DB=1` | output and exit code on failure | AC 1 |
| document `eval.yml` / CLAUDE.md / README | what the reader does next | AC 13 (fund the key, dispatch manually) |
| document `learny-finalize` / ship-cycle | structure and what the agent does next | AC 18, 20 |
| screen, API | n/a - no product surface changes |  n/a - harness-only PR |

## Sources

- `docs/research/2026-09-30/harness/synthesis.md` - sensors 1–5, paperwork diet, model table, Moves 1–2, owner decisions D1–D6
- `docs/research/2026-09-30/harness/rq03-learny-harness-audit.md` F5, F7, F8, F9 - evidence and the prune list

---

# PR B — the loop

**Approved**: 2026-10-29 - user: "Go autonomously until completing everything"

## PR B Problem

PR A made the sensors honest; the loop inside them still runs on a skill the repo does not ship. `learny-ship-cycle` Stage 1 names `tlc-spec-driven`, which PR A removed from the repo — a fresh clone of the harness instructs a session to invoke a skill that exists only at user level. The owner has standardised on `tlc-spec-lean` everywhere else (rq04 A2.3: 30 lean sessions against 3 driven), and owner decisions D1–D6 (2026-10-02) prescribe the target shape: one door-only plan gate waivable in auto mode, one PR per batch with a Verifier scoped to each batch, and the `Assisted-by: Claude Code` trailer overriding lean's no-trailer rule.

Four things block that shape today:

- No vendored lean copy. The synthesis (paperwork diet) says vendor `tlc-spec-lean` and confirm which copy loads — and the repo has been burned before: the vendored `tlc-spec-driven` was shadowed by the user-level copy for months, so its fixes never loaded (rq03 F8, lead-verified).
- Ship-cycle Stage Detection reads driven artifacts (`tlc Execute/Verifier incomplete`, `context.md`) that a lean cycle never produces; per rq04 B11 it needs rows for `plan.md` without `checks.md`, `checks.md` without `verification.md`, and a PASS defined as `validate_verification.py <cycle> --root <repo>` exiting 0. It has one fixed size for every change; the synthesis's two rule-chosen lanes (S, F) and the D1 door gate are absent.
- `pr-review` Track A reads `spec.md`, `tasks.md`, `validation.md` and `FR-*` ids — none of which a lean cycle writes — so reviews of lean PRs would report "no matching spec". The ~50 legacy driven folders must still review coherently (rq04 B10).
- `learny-finalize` forbids driven task ids but not lean slice/check ids; `SKILLS.md` and `.claude/skills/README.md` still describe the rewiring as future work; `CLAUDE.md` has no `## tlc-spec-lean` profile block and its Workflow section still names the removed skill. `.worktrees/` — the parallel-lane convention STATE.md prescribes — is untracked noise in every `git status`.

When this ships, a fresh clone runs a full roadmap cycle end-to-end with only repo-local skills, the cycle stops at a door gate before checks (waived in auto mode with the waiver recorded), the lane is chosen by a rule a reviewer can check, review reads the lean artifacts with a legacy fallback, and the PR A checks in this folder re-run green on any checkout.

## PR B Out of scope

| Excluded | Why |
| --- | --- |
| The pilot and its scorecard (synthesis Move 3) | next cycles, measured on the new loop |
| Migrating or pruning the ~50 legacy driven folders under `.specs/features/` | rq04 B10: they stay, inert; validators resolve one feature by name |
| Stop-hook "grind" (sensor 6) | synthesis: only after sensors 1–5 land and with should-fire tests |
| Pinning GitHub Actions `uses:` to SHAs | recorded candidate in STATE.md, not this row |
| The `main` ruleset and any GitHub setting | PR A's door; applied by the owner, not by code |
| Any app/product code | delivery-harness PR: skills, docs, sensors only |

## PR B Assumptions

| Assumption | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| How the vendored copy avoids the shadowing that killed the vendored `tlc-spec-driven` | vendor under the same name at `.claude/skills/tlc-spec-lean/`, and record the owner action — remove or rename the user-level `C:\Users\augus\.claude\skills\tlc-spec-lean` — as an operator item in STATE.md, confirming afterwards which copy loads from the client's `Base directory` line | rq03 F8 (lead-verified): on the owner's client the user-level copy shadowed the same-named project copy, so precedence cannot be relied on; a distinct project name would leave two skills answering the same triggers while every doc and the research name `tlc-spec-lean`; after the owner removes the user-level copy exactly one copy loads | n |
| Alternatives for the shadowing decision | (a) rename the vendored copy (e.g. `learny-spec-lean`) — rejected: the user-level copy still answers "plan feature" triggers and every reference would fork; (b) rely on project-over-user precedence — rejected: the observed behaviour on the owner's client is the opposite; (c) vendor nothing and keep using the user-level skill — rejected: PR A removed the vendored driven copy precisely because an unloaded copy rots, and the D2/D3 deviations must live in the copy that loads | recorded here as the why-not for each door | n |
| Vendored version | `2.1.0`, the current user-level copy, not the `1.1.0` the synthesis names | the synthesis number was current at research time (2026-09-30); vendoring an older release would drift from what the owner runs on day one; the deviations, not the version, are what the row requires | n |
| PR A check proofs are rewritten with the rewiring | C1–C13 and C24 pytest proofs gain a `cd backend &&` prefix; C14–C23's Linux-path shell proofs become pytest sensors in `backend/tests/test_harness_skills.py`; C22's claim keeps the Harness-section PR B row but drops the `Not started` status pin | the lean gates run every proof in this folder's checks.md at HEAD on any checkout; the originals hard-code `/home/augusto/...` paths and bash-only syntax, and the `Not started` pin goes permanently red the moment this PR's wrap marks the row done — a sensor that lies | n |
| The door gate under run mode auto | waived; the standing authorization is recorded verbatim on this plan's `**Approved**` line | D1 makes the door gate waivable in auto mode; the 2026-10-29 standing instruction is the waiver, and the plan lists its doors and unconfirmed assumptions for audit anyway | n |
| Mutations count for this folder | `Mutations: 3` (the lean default) in checks.md | no project block declared a count before this PR; the new CLAUDE.md profile block pins profile `standard`, budget 150k, and the default count | n |
| `tlc-spec-driven` stays absent | the vendored copy is `tlc-spec-lean` only; AC 16 keeps holding | the driven skill is retired; the legacy folders keep their driven artifacts on disk without the skill | y |

**Open questions:** none - all resolved or logged above.

## PR B Landing

| One-way door | Literal shape | Alternative rejected |
| --- | --- | --- |
| 1. Which skill copy loads on the owner's machine | the project copy at `.claude/skills/tlc-spec-lean/` is authoritative; the owner removes or renames `C:\Users\augus\.claude\skills\tlc-spec-lean` (operator item added to STATE.md in the wrap), then confirms the loaded copy from the client's `Base directory` line showing the project path | keeping both same-named copies - the user-level copy shadowed the vendored `tlc-spec-driven` for months, and the D2/D3 deviations would sit in a copy that never loads |
| 2. Verifier scope per batch (D2) | one Verifier per PR batch, scoped to that batch's checks before its PR, and over every check before the last batch's PR; ship-cycle pre-answers lean's over-budget mechanism ask with "handoff" | lean's single feature-wide Verifier - a multi-batch row would merge early PRs over checks no Verifier ran |
| 3. Attribution trailer (D3) | the vendored `references/build.md` requires every commit to end with the trailer `Assisted-by: Claude Code`, stated as this repo's exception to lean's no-agent-trailer rule; CI's `commits` job enforces it | lean's no-agent-trailer rule as written - CI's `commits` job would reject every commit this loop makes |

Nothing else here is hard to reverse: the rewired skills and docs are git-tracked text, the sensors are tests, and `.gitignore` is one line.

## PR B Criteria

### S8: The lean spec skill is vendored with its deviations (P1)

**Acceptance Criteria**

24. The system SHALL contain `.claude/skills/tlc-spec-lean/` with `SKILL.md`, the six reference files (`build.md`, `checks.md`, `memory.md`, `plan.md`, `verify.md`, `verify-screens.md`), the ten gate scripts (`check_commit.py`, `check_proofs.py`, `lean_config.py`, `lessons.py`, `mutate.py`, `runners.py`, `selftest.py`, `validate_checks.py`, `validate_plan.py`, `validate_verification.py`) and the four fixture files under `scripts/fixtures/`
25. The vendored `SKILL.md` SHALL carry a Learny deviations section stating both recorded deviations: the per-batch Verifier scope (owner decision D2) and the `Assisted-by: Claude Code` trailer as the override of lean's no-trailer rule (owner decision D3)
26. The vendored `references/build.md` SHALL state that this repo requires the `Assisted-by: Claude Code` trailer on every commit, naming it as the exception to the skill's no-agent-trailer rule
27. WHEN run as `python .claude/skills/tlc-spec-lean/scripts/check_commit.py --message "feat(x): add validation"` THEN the vendored script SHALL exit 0, and WHERE the message has a disallowed type THEN it SHALL exit 1
28. The vendored copy's provenance in `.claude/skills/README.md` SHALL record the source, the version, the deviations, and the owner action that makes the project copy the one that loads (remove/rename the user-level copy, then confirm from the client's `Base directory` line)

### S9: The ship cycle runs on the lean skill with two lanes and the door gate (P1)

**Acceptance Criteria**

29. The `learny-ship-cycle` skill SHALL name the vendored `tlc-spec-lean` (profile `standard`, budget 150k) in its description, its intro, and Stage 1's title, and SHALL NOT contain the string `tlc-spec-driven` anywhere
30. The Stage Detection table SHALL map a feature folder with `plan.md` but no `checks.md` to Stage 1 (lean Plan) and one with `checks.md` but no `verification.md` to Stage 1 (lean Build/Verify), and SHALL define a Verifier PASS as `validate_verification.py <cycle> --root <repo>` exiting 0
31. Stage 0 SHALL choose the lane by rule: Lane S when the change fits in one sentence (about 3 files or fewer, no migration, no new ADR, no new route or screen, no one-way door), Lane F for everything else including every roadmap row, and the cycle SHALL NOT downgrade a lane on its own judgement
32. WHEN Stage 1 reaches the end of a lean Plan THEN it SHALL stop at a door gate exactly as decision D1 prescribes: one question listing the plan's one-way doors and unconfirmed assumptions, waivable in `auto` mode with the waiver recorded in the plan
33. WHERE a decision point appears, Stage 1's auto-decision rule SHALL record decisions in the cycle's `plan.md` `## Assumptions` with `Confirmed? n` (never `y` for a default nobody saw), one-way doors in `Landing`, and an `AD-NNN` row only for a decision that binds other cycles
34. WHEN the checks' `## Handoff` arithmetic exceeds the 150k budget THEN Stage 1 SHALL pre-answer the lean mechanism ask with "handoff" and split at slice boundaries into sequential batches, each its own PR, with the Verifier scoped to each batch's checks before its PR and over every check before the last batch's PR (decision D2)
35. The cost-discipline section SHALL keep the five model-policy rows of the synthesis verbatim and SHALL require one coherent piece per commit with its check marked in `checks.md` in the same commit

### S10: Review and finalize speak lean, with a legacy fallback (P1)

**Acceptance Criteria**

36. The `pr-review` Track A SHALL read `plan.md`, `checks.md`, and `verification.md` (numbered criteria and `C`-ids) for lean cycles, and SHALL keep the legacy path reading `spec.md`, `tasks.md`, and `validation.md` with `FR-*` ids for the driven feature folders that remain
37. The `learny-finalize` internal-reference rule SHALL forbid slice and check ids (for example `S2`, `C4`) alongside task and phase ids, and SHALL name `checks.md` as where internal traceability lives instead of `tasks.md`
38. The `SKILLS.md` and `.claude/skills/README.md` skill indexes SHALL describe `tlc-spec-lean` as vendored into `.claude/skills/` and SHALL NOT describe it as a user-level skill or promise the rewiring in a future cycle
39. The `CLAUDE.md` context file SHALL carry a `## tlc-spec-lean` block pinning `profile: standard` and the 150k budget, and its Workflow section SHALL name the vendored `tlc-spec-lean` and SHALL NOT name `tlc-spec-driven`

### S11: Local worktrees stop being noise (P3)

**Acceptance Criteria**

40. The repo `.gitignore` SHALL contain a `.worktrees/` entry

### S12: The PR A checks re-run on any checkout (P1)

**Acceptance Criteria**

41. WHERE a `Proof:` line appears in `.specs/features/harness-reset/checks.md` it SHALL name a machine-independent command containing no absolute filesystem path, so the lean proof gates can run the whole set wherever the repo is cloned

## Shape (PR B)

single module - the delivery harness itself (`.claude/skills/*`, `SKILLS.md`, `CLAUDE.md`, `.gitignore`, and the backend sensor tests that pin them); nothing under `backend/app` or `frontend/` changes.

Changes underneath: `.claude/skills/learny-ship-cycle/SKILL.md` (Stage Detection, Stage 0, Stage 1, cost discipline), `.claude/skills/pr-review/SKILL.md` (Track A), `.claude/skills/learny-finalize/SKILL.md` (internal-reference list, traceability pointer), `SKILLS.md`, `.claude/skills/README.md`, `CLAUDE.md` (profile block, Workflow), `.gitignore`, `.specs/features/harness-reset/checks.md` (portable proofs for C1–C24), and the new `backend/tests/test_harness_skills.py`. Existing and new: the vendored skill tree lands beside the kept skills; every edited file already exists and changes in place.

Data: none - no stored data touched; the only state is git-tracked text.

## PR B Sources

- `docs/research/2026-09-30/harness/synthesis.md` - Move 2, two lanes, door gate, owner decisions D1–D6, paperwork diet (vendoring and confirming which copy loads)
- `docs/research/2026-09-30/harness/rq04-local-research-and-tlc.md` B1, B10, B11 - shadowing evidence, legacy-folder migration path, the coupling table this rewiring follows
- `docs/research/2026-09-30/harness/rq03-learny-harness-audit.md` F8 - the shadowed vendored driven copy
- `C:\Users\augus\.claude\skills\tlc-spec-lean` - the vendored source (version 2.1.0)
