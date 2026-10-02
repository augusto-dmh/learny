---
id: rq03-learny-harness-audit
title: Learny harness audit — what the cycle model costs and buys (delta since 2026-07-24)
question: "What does Learny's harness cost and buy today? Skills, ship-cycle, .specs/ artifacts, lessons, PR/commit shape, CI and nightly, and which of the 2026-07-24 recommendations were adopted."
date: 2026-09-30
status: final
overall_confidence: Medium-High (repo, git and GitHub numbers are complete; transcript evidence covers only one ship cycle)
---

# rq03 — Learny harness audit (delta since 2026-07-24)

## TL;DR

About 10.5 of the 12 items in the 2026-07-24 plan landed, almost all in one PR (#50, 2026-07-25). The repo harness has barely changed since. The owner no longer acts as watchdog: the one transcribed cycle (PR #72) went from prompt to merge in about 1h45m with three owner messages. It still cost $95.

The value sits in one stage, fresh-context review plus triage. Over the 20 cycles since the baseline it produced 231 findings, ~97% judged real and ~86% fixed, including functional bugs a Verifier PASS let through.

The cost sits in ceremony:
- about 900 lines of `.specs/` per cycle (17% of PR lines);
- a `STATE.md` doubled to 247 KB, near the 256 KB Read cap;
- 31 lessons recorded, 0 ever promoted;
- deleted PR comments, so no PR shows any review on GitHub.

Weak sensors:
- the nightly eval has failed 66 runs in a row since 2026-07-27;
- one Verifier passed with 940 database-gated tests skipped;
- the user-level `tlc-spec-driven` shadows the project copy that got the 07-24 fixes.

PRs are not "small": median 4.7k changed lines, 50 files.

## Method

- **Brief and baseline:** `/home/augusto/projects/learny/docs/research/2026-09-30/harness/project-brief.md` and `/home/augusto/projects/learny/docs/research/2026-07-24/ai-harness-session-analysis.md`, read in full.
- **Harness files:** `/home/augusto/projects/learny/CLAUDE.md` (82 lines, 9.6 KB) and `/home/augusto/projects/learny/SKILLS.md`. `.claude/settings.json` and `settings.local.json`. `.claude/commands/ship-status.md`. All 25 project skills (descriptions measured), with `learny-ship-cycle`, `pr-review`, `learny-finalize` and `tlc-spec-driven` read in full or grepped. `/home/augusto/projects/learny/Makefile`, `backend/scripts/check_boundaries.py`, and the three workflows in `.github/workflows/`.
- **`.specs/`:** all 50 feature folders measured per file with line counts and first-commit dates. `ROADMAP.md`, `STATE.md` (sections, AD counts, size at baseline vs now), `LESSONS.md` and `lessons.json`, including their history across 6 commits. All 45 `review-triage.md` files were parsed by regex for verdict and action. For the 20 cycles since the baseline, every `validation.md` was grepped for FAIL, surviving mutants and skipped-test notes.
- **Git:** 64 merge commits on `main` (all `--merge` style), 1,162 commits. Per-PR commit counts and Conventional Commit types come from `git log M^1..M^2`. Post-open commits are commits whose committer date falls after the PR's `createdAt`. LOC per path category comes from `git diff --numstat M^1 M`.
- **GitHub:** `gh pr list --state all --limit 100` returned 72 PRs. `gh run list --limit 1000` returned 502 runs (CI 222, Deploy 189, Nightly eval 76, Dependabot 15). `gh run view --json jobs` was run on all 18 CI failures since 2026-07-25 and on one success to get job durations.
- **Transcripts:** `~/.claude/projects/-home-augusto-projects-learny/`. Only **4** non-current sessions exist on disk:
  - `e99403fd` (2026-08-09, 1 min);
  - `adf439d2` (2026-09-27, the `portfolio-truthful` ship cycle, PR #72, plus 15 subagent transcripts);
  - `0a9ab4e2` (2026-09-30, local QA run);
  - `45641d2f` (2026-09-30, v8 product research, 8 subagents).

  The 30 July transcripts that the baseline used are gone. So are all transcripts for PRs #48–#71. They were mined with a streaming Python extractor for typed user messages, Skill calls and the paths they resolved to, Agent calls, tool errors and denials, gaps over 15 minutes, models, tokens and `cost-state`. The current session `beb194cd` was excluded.

## Findings

### F1 — Adoption of the 2026-07-24 plan: ~10.5 of 12 items, all in one PR the next day

Nearly everything landed in PR #50 ("chore: harden the agent harness, verification gates, and backend formatting", merged 2026-07-25 13:38), with follow-up commits the same day (`4e40db0`, `1ab58e9`, `8a55bfc`, `69d65d8`, `5577ffc`, `88cc391`, `2906ec4`, `eab23ff`, `575cf33`, `a840f59`, `41a48b4`, `3d9a109`). After that, the repo harness changed only twice:
- `7a6504d` (2026-09-26), which refreshed CLAUDE.md state;
- `9905b18` (2026-09-04), which added the Makefile `seed-sample` target.

`.claude/skills/` has not been modified since 2026-07-28.

| # | 07-24 recommendation | Status | Evidence |
|---|---|---|---|
| 1 | Fix `lessons.py` path; generalize the 15 stuck lessons | **Partial** | The path was fixed in project `references/lessons.md:5,19` and `SKILL.md:88`, and an "altitude test" rule was added (`lessons.md:59`). The 15 candidates were never reviewed or promoted; they expired under `window_days=45` (F6). The fix is now moot because the project copy is shadowed (F8). |
| 2 | `.claude/settings.json`: allowlist, `includeCoAuthoredBy:false`, env | **Adopted** (PATH omitted) | `/home/augusto/projects/learny/.claude/settings.json` has 30 allow rules, including `gh api -X DELETE repos/augusto-dmh/learny:*`, plus `includeCoAuthoredBy:false` and `env.LEARNY_TEST_DATABASE_URL`. There is no PATH entry, and no `uv: command not found` errors appear in the 2026-09 transcripts. |
| 3 | Ship-cycle reliability: continuation contract, idle protocol, limit degradation, `.ship-status` heartbeat and resume, CI-wait incantation, read-before-write, wrap report with next row, model and tokens | **Adopted (all 7)** | `/home/augusto/projects/learny/.claude/skills/learny-ship-cycle/SKILL.md` v1.2.0, lines 13–19 and 113–123. `.ship-status` is gitignored (`.gitignore:17-18`). |
| 4 | CLAUDE.md operational section | **Adopted** | "Working in This Repo (Operational)": quickstart URLs, `make` vocabulary, Docker/WSL, no `jq`, cwd resets, schema lookup, AskUserQuestion rule, outage rule. The task→doc table exists as "Progressive Documentation Loading". |
| 5 | Root Makefile as the verification vocabulary | **Adopted and used** | `/home/augusto/projects/learny/Makefile`. In `adf439d2`, the orchestrator ran `make lint`/`lint-backend`/`test-backend` 9 times, and reviewers and the Verifier ran `make lint`. |
| 6 | `pr-review`: diff splitting, issue-comment summaries, completion contract, compact reports | **Adopted** | `/home/augusto/projects/learny/.claude/skills/pr-review/SKILL.md:20,53-55,119,257`. All 72 PRs show `reviews: 0` (no undeletable reviews). |
| 7 | Finalize: no hard-wrap; ship-cycle `once`/`auto`/`until` | **Adopted** | `learny-finalize/SKILL.md:44`; ship-cycle "Run modes". |
| 8 | PostToolUse `ruff format` hook | **Not adopted (substituted)** | No hook exists (the only hooks in `settings.local.json` are Houston telemetry). It was replaced by a format step in finalize (`SKILL.md:88`) and a CI `ruff format --check` (`ci.yml:98-102`). One CI lint failure followed (run 33225855797, 2026-08-29). |
| 9 | Model policy table | **Adopted, not followed** | ship-cycle "Cost discipline". F2 covers the deviation. |
| 10 | Provider-SDK boundary fitness script in CI | **Adopted** | `backend/scripts/check_boundaries.py` (70 lines), run in the CI `lint` job and `make fitness`. |
| 11 | Live-run budget protocol | **Adopted** | `LEARNY_EVAL_BUDGET_USD` in `backend/tests/eval/study.py` and `docs/ops/eval-calibration.md`. |
| 12 | `/ship-status`, cycle lockfile, `.bench/` self-benchmark | **Partial** | `.claude/commands/ship-status.md` exists. The heartbeat doubles as the in-flight lock (Stage Detection). No `.bench/`. |
| P12 | "ToolSearch-load deferred tools" line | Not adopted | Absent from all project skills and CLAUDE.md. |

### F2 — Cost of one fully observed cycle (`portfolio-truthful`, PR #72, session `adf439d2`, 2026-09-27)

All times are UTC. This is the only post-baseline cycle with a transcript.

- **Wall clock, about 1h45m from first prompt to merge:**
  - 01:32 prompt;
  - 01:39 owner picks "opção A", then `learny-ship-cycle` and `tlc-spec-driven` load;
  - 01:43 plan committed (`30520e1`);
  - about 01:46–02:13 Execute, run inline with no phase workers;
  - 02:14–02:45 Verifier, 31 min on Opus: first pass FAIL with 3 real docs/test fixes, then PASS, then a T10 addendum;
  - 02:30 PR open;
  - 02:31–03:00 review, 29 min across 2 rounds;
  - 02:55 merge gate asked, answered 03:07 (12 min of owner latency);
  - 03:14 merged;
  - 03:17 wrap.
- **Owner interventions:** 3 typed messages: the kickoff, the option pick, and the merge-gate answer. There were no nudges, no "continue", and no status questions. The baseline window had 25+ watchdog messages. The heartbeat and continuation contracts appear to work, but this rests on n=1.
- **Subagents: 15.** One Verifier (Opus, 14.5k output tokens). One reviewer orchestrator (29 min) that spawned 13 lane subagents: 6 lanes × 2 rounds (initial plus delta) and 1 consolidation, each about 9–10 min and 2.4k–6.3k output tokens.
- **Money and tokens:** `cost-state.totalCostUSD = 95.15` for the session. The main thread produced 549k output tokens and 97M cache-read tokens, all on `claude-fable-5-1`, for a docs-heavy PR (+1,692/−402, of which only 116 changed lines are non-test, non-docs code).
- **Model policy deviation:** ship-cycle says "Default model is Opus" and Fable is "never a blanket default". It also says the `pr-review` Security lane should "Never" run on Fable. In practice the orchestrator, Execute and all 13 review subagents ran on Fable 5.1, including Security (`subagents/agent-ad963bd254c17cf32.jsonl`, `agent-a0750b9159e41794d.jsonl`). In the same session the owner noted a perceived quality drop when cheaper models were used: *"Talvez as últimas sejam piores do que as passadas, porque nas passadas muitas delas eu usei Claude Code e utilizando o plano Max … esses últimos PRs eles estão utilizando um modelo uh, mais barato."*
- **Throughput when chained:** five RFC-0007 cycles merged on 2026-09-04 (PRs #63–#67, merge commits at 10:00, 12:50, 16:24, 19:05 and 21:33 −03). That is about 2.5–3.5h per full cycle, including spec and review.

### F3 — Artifact cost per cycle (`.specs/`)

- **Totals:** `.specs/` holds 3.4 MB and 40,100 Markdown lines over 50 feature folders.
- **The 20 cycles since the baseline:** 18,594 lines of artifacts, median **~900 lines per cycle**. Median per file: spec 195, design 164, tasks 169, context 99, validation 175, review-triage 29.
- **tasks.md growth:** in the 10 September cycles, which all ran the user-level `tlc-spec-driven` installed on 2026-09-02 (F8), median `tasks.md` is **426 lines**: `first-session-converts` 555, `cheaper-intelligence` 539, `safe-to-open-the-doors` 468, `portfolio-truthful` 423. Before that the median was ~169. The new template adds a mandatory "Execution Protocol", a "Test Coverage Matrix" and "Gate Check Commands" tables to every tasks file (`/home/augusto/projects/learny/.specs/features/portfolio-truthful/tasks.md:1-35`).
- **Share of PR lines** (cycle PRs #49–#72, n=20): `.specs` 17%, tests 51%, non-test code 25%, docs 6%. Median `.specs` per PR is about 760–1,200 lines.
  - In small PRs, `.specs` outweighs the code: #72 has 1,216 `.specs` lines against 116 code lines, and #70 has 762 against 183.
  - Before the baseline (cycle PRs #4–#47), `.specs` was 14%.
- **`STATE.md`:** 125 KB at the baseline commit `9bf5dae`, **247 KB** now (464 lines, most of them multi-KB single lines). The decision log grew from AD-169 to AD-362, about 9.6 auto-recorded decisions per cycle. The Handoff section keeps two bullets per cycle (BUILT, then MERGED) at 1–5 KB each.
  - The file is at 96% of the 256 KB Read cap that broke reviewers in the baseline (P10).
  - It holds stale content: "Known Gaps" still says CI's lint gate "is `ruff check` only" and that format drift is "deliberately not fixed" (`STATE.md:380-389`), but CI has enforced `ruff format --check` since 2026-07-25.
- **Retrospectives:** `docs/retrospectives/` has only `2026-07-learny-v2.md` and `2026-07-learny-v3.md`. There are none for v4–v7, although CLAUDE.md points readers there.

### F4 — What review and triage buy (the value center)

The 45 `review-triage.md` files were parsed by regex, so the counts below are approximate.
- **Volume:**
  - 20 cycles since the baseline: **231 findings, 225 judged real (97%), 198 fixed (86%), 29 won't-fix, 6 false**, or about 11.5 findings per cycle.
  - Earlier cycles: 124 findings, 118 real, 95 fixed (about 4.8 per cycle).

  The yield per cycle more than doubled after the baseline.
- **Findings that mattered**, all caught after a Verifier PASS and before merge:
  - `first-session-converts` (#67): "Starter POST is never called from Home or Review". The feature's main path was not wired.
  - `v6-workspace-conversations` (#53): F10 🚨, where the client reintroduced the scope→mode inference that AD-205 had removed from the backend.
  - `house-profiles` (#71): finding 1 found that CI `backend-test` never ran pytest because the `minio/minio` image pull was denied, so all database-gated evidence was unexecuted. Once CI ran, 4 tests failed on their first execution and needed 3 more CI rounds (`/home/augusto/projects/learny/.specs/features/house-profiles/review-triage.md:24-75`).
  - `portfolio-truthful` (#72): a missing `-f` on a healthcheck, so a 503 counted as healthy.
- **Fix churn:** in cycle PRs since the baseline, **161 of 496 commits (32%) landed after the PR opened** (median 7.5 per PR); earlier the figure was 128/532 (24%). Of those 161, 50 are `fix:`, 23 `test:` and 37 `docs:`.
- **Self-judging bias:** triage is done by the authoring orchestrator, not an independent party. The 97% "real" rate cannot tell agreement apart from acceptance bias.
- **Comment deletion (Stage 6):** every one of the 72 PRs shows `comments: 0, reviews: 0` on GitHub. The only record of review is `review-triage.md` inside `.specs/`. The project memory `learny-portfolio-goal.md` says presentation is first-class for interview use, and a visitor sees no review activity on any PR.

### F5 — Verifier: high mutant-kill scores, weak independent signal

- **Kill scores:** in 18 of 20 post-baseline cycles, `validation.md` reports kill rates of 100% or close to it (for example 24/24, 18/18, 10/10). Only `portfolio-truthful` records a first-pass FAIL.
- **What it misses:** review then finds about 11 real issues per cycle that the Verifier did not flag (F4).
- **Blind spot:** the discrimination sensor only mutates branches that existing tests already reach. `learny-ship-cycle/SKILL.md` admits this ("sensor-blind gaps slip").
- **`house-profiles` (#71):** the Verifier issued PASS with **"2030 passed, 940 skipped (all db-gated: no Docker/Postgres in session)"**. It marked 4 of 13 mutants "killed-by-CI (static verify)" (`/home/augusto/projects/learny/.specs/features/house-profiles/validation.md:11,17,48-60`). CI then could not run pytest at all, and 4 of those tests failed on first execution. `backend/tests/conftest.py:23` skips quietly with `requires_db = pytest.mark.skipif(TEST_DB_URL is None …)`.

### F6 — Lessons layer: still not working

- **Promotion:** 31 lessons recorded ever (`next_id: 32`), **0 ever promoted to Confirmed**. Count history in `lessons.json`:
  - 15 at `9bf5dae` (2026-07-24);
  - 16, 20 and 22 through 2026-08-02;
  - 11 at `f57120f` (2026-09-06), after the 45-day window pruned the July set;
  - 9 now, all `candidate` with `recurrence: 1`.
- **Coverage:** only 3 of the 20 post-baseline cycles recorded any lesson (`safe-to-open-the-doors`, `v5-spoiler-safe-retrieval`, `portfolio-truthful`).
- **Phrasing:** the altitude rule added on 2026-07-25 did not change how lessons are written. Current texts embed internal IDs and incident specifics, for example L-023 "(DOOR-40)…caplog assertion" and L-027 "percent=0.00" (`/home/augusto/projects/learny/.specs/LESSONS.md`). Exact-match dedup means such texts cannot recur.
- **Net effect:** no confirmed guidance has been loaded at Specify or Design in the project's lifetime.

### F7 — PR and commit shape: not "small and reviewable"

| | Cycle PRs #4–#47 (n=30) | Cycle PRs #49–#72 (n=20) |
|---|---|---|
| Median changed lines | 3,570 | **4,731** (p75 8,727; max 16,406, #53) |
| PRs > 1,000 lines | — | 20/20 (8 are > 5,000) |
| Median files | 39.5 | 50.5 |
| Median commits | 18.5 | 23 |
| Median hours open | 1.0 | 1.0 (outliers: #62 at 630h, #71 at 41h) |

- **Merge style:** merge commits (`gh pr merge --merge`), which keep every atomic commit.
- **Conventional Commits:** compliance is near-total, with one exception. PR #69 carries **9 untyped review-fix commits** ("Keep the shared translator free of transport imports", "Memoize the budget's profile catalogs per process", …). `check_commit.py` runs only when the agent chooses to call it (13 calls in `adf439d2`), and no CI commit-lint exists.
- **Author identity:** 21 commits on 2026-09-26 carry the owner's corporate (work) email. The owner caught it at the merge gate (*"why does all the commits are receiving as author augusto-henriques (my corporate email) instead of the personal one?"*), which led to the memory `git-identity-personal-email.md`.
- **Human review in practice:** one AskUserQuestion at the merge gate. No owner reads the diff before merge; the 1-hour median time open is mostly CI and agent review.

### F8 — Skills: what loads and what is dead weight

- **Invoked** in the 4 surviving transcripts:
  - `learny-ship-cycle`, `learny-finalize`, `pr-review` (inside the reviewer subagent), each loaded from the project path;
  - `tlc-spec-driven`, which loaded from **`/home/augusto/.claude/skills/tlc-spec-driven`, the user-level copy** installed 2026-09-02, not the project copy;
  - `anthropic-skills:deep-research`, from user-level `synced/`.
- **Shadowing:** the user-level `tlc-spec-driven` ran its own scripts (`validate_spec.py` ×4, `validate_tasks.py` ×5, `check_commit.py` ×13, `validate_state.py` ×7, `lessons.py` ×4). The project copy at `/home/augusto/projects/learny/.claude/skills/tlc-spec-driven` has only `lessons.py`, and every reference file differs (`diff -rq`). That project copy is where the 07-24 path and altitude fixes were applied. It is now shadowed, so it is effectively dead.
- **Never referenced in any `.specs/features/*` file and not observed in transcripts:** `redis-core`, `redis-observability`, `redis-security`, `web-design-guidelines`, `domain-analysis`, `modular-design-principles`, `skill-architect`, `grilling`, `grill-me`, `create-technical-design-doc`. Together their descriptions are about 4.5k chars (~1.1k tokens).
- **Referenced in specs at least once:** `fastapi` (17 features), `celery-workers` (10), `pgvector-hybrid-search` (7), `vercel-react-best-practices` (6), `epub-ingestion` and `vercel-composition-patterns` (5 each).
- **Duplicates:** `tlc-spec-driven`, `create-adr`, `create-rfc`, `modular-design-principles`, `grilling` and `grill-me` exist at both project and user level. The user-level `grilling` and `grill-me` are symlinks into `workA`.
- **Always-loaded context:** CLAUDE.md is 9.6 KB (~2.4k tokens). The 25 project skill descriptions total 11.5k chars (~2.9k tokens). The 25 user-level skill descriptions add 11.0k chars (~2.75k tokens), and plugin skills come on top. `tlc-spec-driven`'s description is the longest at 984 chars.

### F9 — CI as an agent sensor

- **Speed:** jobs run in parallel and finish in about 3 min of wall time (one success sample: backend-test 2.9, frontend 2.7, compose-smoke 2.1, lint 0.1 min). Median CI wall time was 1.9 min before the baseline and 2.6 min since (p90 3.0). Total since 2026-07-13: ~485 CI minutes, 308 Deploy minutes and 150 Nightly minutes.
- **Coverage:**
  - pytest against real Postgres and MinIO (~2,958 tests by 2026-09-13);
  - `ruff check`, `ruff format --check` and the boundary script;
  - vitest, `tsc` and `next build`;
  - a full compose topology boot with backup, restore and WAL checks.

  There is no browser end-to-end test (no Playwright) and no commit-message lint.
- **Failure rate since 2026-07-25:** 18 of 84 completed non-cancelled runs failed (26% on the PR event). Another 19 runs were cancelled by `cancel-in-progress`. Classification of the 18 failures:
  - **upstream/infra rot, 5:** "Start MinIO", "Initialize containers" and the compose boot or backup image build. Docker Hub withdrew `minio/minio` and `dl.min.io` returned 410. This broke CI on 2026-09-13 (#71) and again on 2026-09-27 (#72), each time fixed inside a feature PR;
  - **frontend vitest, 7:** including **2 on `main`** on 2026-09-07, plus the known teach-panel flake;
  - **pytest, 5:** 3 of them the blind-authored #71 tests;
  - **ruff, 1;**
  - **Dependabot branches, 3.**
- **Nightly eval:** it has failed **66 consecutive runs (every night since 2026-07-27)**; the last success was 2026-07-26. Per CLAUDE.md, the cause is an unfunded provider key. Meanwhile the routing and profile cycles shipped without any live-provider signal: `cheaper-intelligence` (#69) and `house-profiles` (#71). The 2026-09-27 README had claimed the streak was 5 days; the Verifier/review corrected it to two months, recorded as lesson L-030. The CLAUDE.md candidate "promote the economy profile after a green candidate nightly" is blocked on that same red run.

### F10 — Friction in the recent sessions that the baseline did not record

1. **Skill shadowing and drift between user-level and project skills** (F8). Fixes go into a copy that no longer loads.
2. **Upstream image rot** (`minio/minio` and `dl.min.io`) cost two cycles a mid-cycle detour. The orchestrator tried `bitnami`, `rustfs` and a quay repoint before building a `learny-minio` image (ADR-0031) (`adf439d2`, 02:09–02:10).
3. **Low-memory reaping of background CI and deploy watchers.** Two `gh … --watch` tasks were killed overnight ("stopped because the system is running low on memory", `adf439d2` 18:03Z), and the wrap had to re-query.
4. **Limit deaths now come from model quotas, not only session limits.** `45641d2f` 23:56Z: the `report-writer` teammate failed with "You've reached your Fable limit". The owner switched `/model` and typed *"Continue, you have beein interrupted out of blue"*. The ship-cycle degradation policy does not cover non-ship work. STATE Handoff records limit deaths in about 5 of the 20 post-baseline cycles (for example `v6-page-unit`, `v6-workspace-conversations`, `v5-worker-recovery-hardening`, `reader-people-read-in`).
5. **Local QA by the owner is unsupported.** In `0a9ab4e2` ("I want you to open this project in my machine so I can QA it"):
   - Redis's host port 6379 clashed with another project's stack, which led to the uncommitted `docker-compose.override.yml` port parameterization;
   - the owner had to ask *"Is there a login that I can use?"*;
   - the session ran on Sonnet 5.5 (`/model`), which ship-cycle cost discipline forbids for pipeline work.
6. **Classifier denials persist** but are now rare: 3 in total. They hit `docker pull … && docker tag` and a `git add … && git commit` chain (flagged "[Git Destructive]") in `adf439d2`, and a `docker volume rm` sequence in `0a9ab4e2`.
7. **Corporate git identity on 21 commits** (F7).

## Implications for Learny

1. **Keep fresh-context review and triage as the core quality stage, and keep its record visible.**
   - **Why recommend:** it is the only stage with a measured yield (about 11.5 findings per cycle, 86% fixed) and it caught functional bugs that the Verifier passed (F4). Deleting comments removes the most interview-visible proof of process on a portfolio repo (F4, portfolio memory).
   - **Why not:** about 30 min and 13 subagents per cycle, at Fable pricing in practice. Visible comments also expose internal IDs unless they are cleaned.
   - **Confidence:** High for the value; Medium for un-deleting (it is a presentation choice).
2. **Slim the planning artifacts. A lean spec in the `tlc-spec-lean` style fits this evidence.**
   - **Why recommend:** about 900 artifact lines per cycle and 17% of PR lines. In small PRs `.specs` is 4–10× the code. `tasks.md` grew about 2.5× with the September template. The auto-decision log adds about 10 AD rows per cycle that no stage reads back (F3).
   - **Why not:** the artifacts feed the Verifier's AC tracing and the review's Requirements lane. Dropping them without a replacement obligation list could lower review yield. Every cycle in the measurement used the heavy format, so there is no lean comparison.
   - **Confidence:** Medium.
3. **Make the sensors honest before adding v8 work:**
   - the Verifier cannot PASS while DB-gated tests skip, so `make infra` or green CI becomes a precondition (F5);
   - fund the nightly eval or disable it with a recorded reason (F9);
   - pin or self-host the upstream images (F9).
   - **Why recommend:** a PASS with 940 skips, and a nightly ignored for 66 runs, are false signals that review had to catch by luck.
   - **Why not:** funding costs money. A strict skip gate slows sessions that have no Docker.
   - **Confidence:** High.
4. **Retire or redesign the lessons layer.**
   - **Why recommend:** 0 of 31 lessons promoted in three months; 22 expired unread; only 3 of 20 cycles recorded any (F6). Review triage already produces general, codebase-grounded rules that could feed `CONVENTIONS.md` directly.
   - **Why not:** the layer is cheap when it is skipped, and fuzzy matching might yet make it work.
   - **Confidence:** High that it is not working; Medium on the replacement.
5. **Resolve the skill shadowing and prune unused skills.** Either delete the project `tlc-spec-driven` copy or make a deliberate choice of which copy is authoritative. Drop the ~10 never-referenced skills.
   - **Why recommend:** fixes are landing in dead files (F8), and the unused descriptions cost about 1.1k tokens of always-loaded context.
   - **Why not:** vendored skills are cheap insurance if Redis or UI work recurs in v8 (for example the PWA row).
   - **Confidence:** Medium-High.
6. **Archive `STATE.md` per roadmap now.**
   - **Why recommend:** at 247 KB it is about 2 cycles from the Read cap, it has doubled in two months, and it holds stale sections (F3).
   - **Why not:** none of substance; it is a mechanical split.
   - **Confidence:** High.
7. **Make PR size and commit hygiene match the stated policy.** Options: drop "small and reviewable" from CLAUDE.md, split cycles into stacked PRs, or add `check_commit.py` as a CI step.
   - **Why recommend:** median 4.7k lines and 50 files (F7). The 9 untyped commits in #69 passed with no gate. The merge gate is the only human review.
   - **Why not:** for a solo agent-driven repo, large atomic-commit PRs reviewed by agents may be the right trade, and stacking adds orchestration cost.
   - **Confidence:** Medium.
8. **Reconcile the model policy with practice.**
   - **Why recommend:** the written policy (Opus default; Fable never blanket; never Fable for the Security lane; never Sonnet) was violated in every observed 2026-09 session. The owner also suspects a quality drop on cheaper models (F2, F10).
   - **Why not:** model choice tracks plan quotas, which change faster than skill text.
   - **Confidence:** Low-Medium (n=1 ship cycle).

## Limitations

- **Transcript coverage is thin.** Only one post-baseline ship cycle (#72) has a transcript. Cycles #48–#71 are evidenced only through git, GitHub, `STATE.md` and `.specs/`. Owner-intervention and wall-clock figures for those cycles cannot be measured, and "3 owner messages per cycle" rests on n=1.
- **Triage counts are approximate.** They come from a regex over table rows, and triage formats vary across the 45 files. The 97% real rate is the author's own judgment.
- **PR line categories are path heuristics.** Paths are bucketed as `.specs/`, `*.md`/`docs/`, test paths and lock files; everything else counts as code.
- **CI timings** use `updatedAt − startedAt` per run, and job durations come from a single sample. `gh run view --log-failed` returned no log for the latest nightly, so the unfunded-key cause comes from CLAUDE.md and lesson L-030, not from a log line.
- **Session cost** comes from one `cost-state` record ($95.15) and may exclude or double-count subagent spend.
- **Out of scope here:** whether `tlc-spec-lean` would perform better (rq04/rq05), and other repos' harnesses (rq01/rq02).

## Sources

**Cited**
- `/home/augusto/projects/learny/docs/research/2026-09-30/harness/project-brief.md`; `/home/augusto/projects/learny/docs/research/2026-07-24/ai-harness-session-analysis.md`
- `/home/augusto/projects/learny/CLAUDE.md`; `/home/augusto/projects/learny/SKILLS.md`; `/home/augusto/projects/learny/Makefile`; `/home/augusto/projects/learny/.gitignore`
- `/home/augusto/projects/learny/.claude/settings.json`; `/home/augusto/projects/learny/.claude/settings.local.json`; `/home/augusto/projects/learny/.claude/commands/ship-status.md`
- `/home/augusto/projects/learny/.claude/skills/learny-ship-cycle/SKILL.md`; `/home/augusto/projects/learny/.claude/skills/pr-review/SKILL.md`; `/home/augusto/projects/learny/.claude/skills/learny-finalize/SKILL.md`; `/home/augusto/projects/learny/.claude/skills/tlc-spec-driven/` (SKILL.md, references/lessons.md, scripts/); `/home/augusto/.claude/skills/tlc-spec-driven/` (comparison only)
- `/home/augusto/projects/learny/.specs/project/STATE.md`; `/home/augusto/projects/learny/.specs/project/ROADMAP.md` (committed and the uncommitted v8 diff, 12 rows); `/home/augusto/projects/learny/.specs/LESSONS.md`; `/home/augusto/projects/learny/.specs/lessons.json` (and history at `9bf5dae`, `a023443`, `69c74db`, `5e1f227`, `f57120f`)
- `/home/augusto/projects/learny/.specs/features/*/` (all 50; specifically `house-profiles/review-triage.md`, `house-profiles/validation.md`, `teach-becomes-tutor/review-triage.md`, `first-session-converts/review-triage.md`, `v6-workspace-conversations/review-triage.md`, `portfolio-truthful/tasks.md`)
- `/home/augusto/projects/learny/.github/workflows/ci.yml`, `deploy.yml`, `eval.yml`; `/home/augusto/projects/learny/backend/scripts/check_boundaries.py`; `/home/augusto/projects/learny/backend/tests/conftest.py`; `/home/augusto/projects/learny/docker-compose.override.yml` (uncommitted diff)
- `/home/augusto/projects/learny/docs/retrospectives/` (2 files)
- Git: `git log` on `main` (64 merges, 1,162 commits); PR #50 body (`gh pr view 50`)
- GitHub: `gh pr list --state all` (72 PRs); `gh run list --limit 1000` (502 runs); `gh run view --json jobs` for 18 failed CI runs and 1 successful one
- Transcripts: `~/.claude/projects/-home-augusto-projects-learny/adf439d2-4595-49e8-a333-0ed61f185249.jsonl` (+ `subagents/`, 15 agents), `0a9ab4e2-2b4a-4555-8283-7ab9b1757153.jsonl`, `45641d2f-b44b-4f59-85fc-277346afd655.jsonl`, `e99403fd-1c12-471a-814b-93b660c7ffe6.jsonl`; memory index `~/.claude/projects/-home-augusto-projects-learny/memory/MEMORY.md`

**Consulted, not cited**
- `/home/augusto/projects/learny/.specs/codebase/CONVENTIONS.md`; `/home/augusto/projects/learny/.claude/skills/README.md`; remaining project skill SKILL.md frontmatter (descriptions measured); `45641d2f` subagent transcripts (product research, out of harness scope); `docs/ops/eval-calibration.md`; `backend/tests/eval/study.py`
