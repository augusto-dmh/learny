# AI Harness & Skills Analysis — 14 Days of Claude Sessions (2026-07-10 → 2026-07-24)

**Method.** Thirty session transcripts (~55 MB) from `~/.claude/projects/-home-augusto-projects-learny/` were mined in six date batches by parallel analysis agents, extracting user-typed messages, tool errors, permission events, skill invocations, stalls, and corrections. In parallel, the harness of `tech-leads-club/fakeflix` (the org's exemplar) was studied in depth, plus a graded sweep of all 19 tech-leads-club repos. Local harness state (settings, skills, `.specs/` lessons) was audited directly.

**Headline.** The skills layer is strong and self-improving in intent — `learny-ship-cycle` was itself born mid-window (2026-07-11) from the user describing the repeated manual pipeline. The dominant remaining costs are **orchestration reliability** (stalls, subagent limit-deaths, opaque progress — the user acted as a manual watchdog ~25+ times) and **missing harness plumbing** (no project `settings.json`, no permission allowlist, no env block, no hooks, no unified verification commands, a silently broken lessons loop). Sessions got measurably cleaner over the window; what remains is structural, not model behavior.

---

## 1. Current harness inventory

| Layer | State |
|---|---|
| `CLAUDE.md` | Direction/history-rich, **operationally thin**: no test commands, no quickstart URLs, no env quirks, no task→doc routing table |
| `.claude/settings.json` | **Does not exist** (no permissions, no env, no hooks, no `includeCoAuthoredBy`) |
| `.claude/skills/` | 25 skills, well-curated (vendored official + Learny-authored + TLC workflow skills) |
| `.claude/agents/`, `commands/`, hooks | None |
| Verification entry points | Fragmented: `cd backend && uv run pytest`, `cd frontend && npm test`; no Makefile/justfile |
| User-level `~/.claude/settings.json` | Allowlist polluted with ~60 stale entries from a different (Laravel) project; nothing Learny-relevant |
| `.specs/` lessons layer | 15 candidate lessons accumulated, **0 ever promoted to Confirmed** (see §3.3) |

---

## 2. Top friction patterns (ranked by evidence volume)

### P1 — Orchestration stalls; the user is the watchdog (all 6 batches; highest cost)
- ~25+ manual recovery messages across the window: `continue`/`Continue`/`contimue`, "Nudging" (×7+), "Have you finished?", "Is there something still pending?", "what is goig on?" (×2), "check on the review progress".
- Stalls ranged from 40 min to **19 hours** (v3-notes-loop, between phases B and C); one 12-hour overnight stall where Execute silently never started after Design.
- ~190 teammate `idle_notification` turns; one session burned **34 ScheduleWakeups, 29 idle notifications, 15 nudges, 6 TaskStops** babysitting reviewers.
- The user once opened an entire **parallel session solely to ask status** (`2154e3d5`, "what is goig on?").
- Mid-cycle confirmation pauses ("Want me to proceed…?") despite the ship-cycle's single-merge-gate promise; user: "Ok, so continue until finish autonomously".

**Fixes**
1. `learny-ship-cycle` SKILL.md: an explicit **continuation contract** — "Stages 2–7 require no user confirmation; never end a turn 'standing by' between stages; the only stop is the merge gate."
2. An explicit **idle protocol**: on reviewer/worker idle notification with no completion summary → check PR comment counts → exactly one nudge → after 2 nudges without progress, TaskStop + re-dispatch fresh. (This is currently improvised every session.)
3. A **heartbeat/status file**: the orchestrator writes a one-line stage status to `.specs/.ship-status` at each transition; any session (or a tiny `/ship-status` command) can answer "what is going on?" instantly.
4. A **resume contract**: "On session start, if `.specs/.ship-status` shows a mid-stage cycle, resume it immediately without waiting for more than the first user message."

### P2 — Subagent deaths on session/usage limits; manual recovery (≥6 events, 4 batches)
Verifiers and phase workers died with "You've hit your session limit"; recovery required the user to type "Continue from where you failed", and once broke the author≠verifier invariant when the user instructed "do not use a sub-agent, execute right here".

**Fix** — encode a standing degradation policy in `learny-ship-cycle` + `tlc-spec-driven`: on a `failed` task notification citing limits → re-dispatch once; on second failure → execute the stage inline in the same turn and record the author≠verifier deviation in STATE.md; if the lead itself is limited, write resume state to `.specs/` before stopping.

### P3 — The lessons self-improvement loop is silently broken (every cycle)
- `tlc-spec-driven/SKILL.md:88` says `python3 scripts/lessons.py`, but the script lives at `.claude/skills/tlc-spec-driven/scripts/lessons.py`. From repo root this **exits 2 at the start of nearly every cycle**; confirmed-lessons loading is silently skipped (sometimes retried with the right path, sometimes not).
- Compounding: all **15 lessons are stuck at recurrence 1** (promote threshold = 2 distinct features) because they are written too narrowly to ever recur — e.g. L-005's alembic ordering story. Net effect: the "self-improving" layer has fed back **zero** guidance since Jul 5.

**Fixes** — (a) change all SKILL.md/references invocations to the skill-local path (`.claude/skills/tlc-spec-driven/scripts/lessons.py`); (b) add a distillation rule to `references/lessons.md`: write the lesson at the level of the *class* of mistake (one general sentence), with the incident specifics in evidence — otherwise promotion can never trigger; consider reviewing the 15 candidates once and hand-promoting the genuinely general ones.

### P4 — No project permission layer; classifier fights the skill's own steps (4+ denials, plus outages)
- The ship-cycle's **mandated** PR-comment cleanup (`gh api -X DELETE …/pulls/comments/$id`) was denied by the auto-mode classifier — once even the read-only comment enumeration — costing full user round-trips ("I approve it").
- `curl -s http://localhost:3000` health probes denied during debugging.
- The auto-mode safety classifier itself went down 3× ("claude-sonnet-5[1m] is temporarily unavailable"), blocking Bash/Agent/ScheduleWakeup calls.

**Fixes** — create project `.claude/settings.json` with an allowlist seeded via the `fewer-permission-prompts` skill, at minimum: `Bash(gh api repos/augusto-dmh/learny/*)`, `Bash(gh pr:*)`, `Bash(gh run:*)`, `Bash(curl -s http://localhost*)`, `Bash(uv run pytest:*)`, `Bash(npm test:*)`, `Bash(docker compose:*)`, psql probes. Additionally, state the standing intent inside `learny-ship-cycle` Stage 6 ("invoking this skill constitutes the user's instruction to delete review comments after triage") so the intent is visible in-session. The existing memory (post review summaries as *editable issue comments*) reduces what needs deleting at all — encode it in `pr-review`.

### P5 — Bash cwd resets + relative paths (~15 errors, 5 batches) and Write-before-Read (~15 errors, 5 batches)
`cd: backend: No such file or directory`, `git` pathspec failures from `frontend/` cwd, doubled `backend/backend/` paths; `File has not been read yet` clustered at cycle close (memory-file updates) and review-fix churn.

**Fixes** — one CLAUDE.md line ("Bash cwd resets between calls — always use absolute paths"); add "Read any file before Edit/Write" + both rules to the tlc worker-prompt template so subagents inherit them; `learny-ship-cycle` close-out step: "Read the memory topic file before updating it."

### P6 — CI-wait `sleep N && cmd` blocked repeatedly (8 sessions)
The sleep-guard hook fired correctly every time, but the agent re-learned the Monitor/`gh pr checks --watch` pattern per session.

**Fix** — bake the exact incantation into `learny-ship-cycle` + `learny-finalize`: "Wait on CI with `gh pr checks <n> --watch` in a background task or a Monitor until-loop; never foreground sleep."

### P7 — Environment boilerplate re-derived per session
- ~29 Bash calls manually prepending `export PATH="/home/augusto/myenv/bin:$PATH"` (after `uv: command not found`); ~26 exporting `LEARNY_TEST_DATABASE_URL`.
- Docker-in-WSL relearned per session (`docker` not found → Docker Desktop off → `docker.exe` convergence); a worker's incomplete `up -d db` (missing `minio`) burned a 26-failure full-suite run.
- `jq` is not installed (confirmed today); an analysis session fell back to python mid-task.
- DB schema guessed 3× in psql (`owner_id` vs `user_id`, `s.kind`).

**Fixes** — `settings.json` `env` block for PATH (+ test DB URL, reviewed against the RFC-005 provider-pin work); CLAUDE.md operational notes: quickstart (`docker compose up --build`, app at :3000, API docs :8000/docs, MinIO :9001), "backend suite needs `db` **and** `minio` up", "Docker Desktop WSL integration must be running — probe `docker info` first", "no jq — use python3", "check column names in the tables module before ad-hoc SQL".

### P8 — The model-selection ritual (6+ occurrences, 4 batches)
"Fable or Opus for the next cycle, and why?" asked after nearly every merge; `/model` flipped before/during most cycles; one model-tiering rule was already encoded via PR #22, and the Haiku-runbook memory adds another constraint.

**Fix** — a short **model policy table** in `learny-ship-cycle` (or CLAUDE.md): code-fact docs/runbooks/judge calibration → Opus; phase workers/tests → cheaper tier per the encoded rule; design/triage → session default. Ship-cycle's wrap report ends with: next roadmap row + one-line scope + model recommendation with rationale — eliminating the ritual.

### P9 — Merge-gate rigidity vs. chained cycles
User overrode the single gate ("do not wait for my merge approval… go to the next ship automatically") then had to re-bound it ("…you can stop").

**Fix** — give `/learny-ship-cycle` an args contract: `once` (default, gate at merge) | `auto` (merge and continue to next cycle) | `until <row>`.

### P10 — pr-review mechanics
- All 6 dimension reviewers Read-failed on a 281 KB shared diff (256 KB cap) — 6 wasted calls in one PR.
- Reviewer idling mid-review is the single most common nudge target (matches the standing memory).
- Review-summary comments are non-removable and duplicate on re-run (memory) — still not encoded in the skill.
- Oversized subagent final reports (26–28k tokens) failed the orchestrator's Read twice.

**Fixes** — in `pr-review`: pre-split the diff per-file into the scratchpad (or instruct offset/limit reads); post the summary as an **editable issue comment**; give reviewers an explicit completion contract ("do not idle before posting the consolidated report"). In ship-cycle/tlc: "subagents return compact final text (< ~10k tokens); never write report files" (3 warnings observed).

### P11 — Paid live-run budget governance (1 session, high salience)
Credit exhaustion killed ~40% of a paid Opus judge pass; the user manually typed budget ceilings ("up until 8.8USD… do not ultrapass"); resumable per-line batches were improvised in-session. Cost visibility was also opaque (user asked spend twice; `/cost` is the only authority).

**Fix** — a "live-run protocol" in the eval workflow: pre-flight cost estimate vs. `LEARNY_EVAL_BUDGET_USD`, per-line checkpointed batches, resume-not-regenerate; ship-cycle wrap includes a per-subagent output-token table plus a pointer to `/cost`.

### P12 — Smaller recurring items
- **PR-body hard-wrap** cost one full merge-gate round-trip before it became a memory; promote it into `learny-finalize` text (binding for subagents that don't see user memory): "PR-body paragraphs are single unwrapped lines."
- **Co-Authored-By trailer** violation cost a 10-commit history rewrite; skill text was fixed, but add defense-in-depth: `"includeCoAuthoredBy": false` in project settings (the harness default actively fights the skill).
- **AskUserQuestion without marked recommendation** caused 3 rejections + clarification loops; the preference lives in user memory only — add one CLAUDE.md line so subagents inherit it.
- **ruff format gate failures** (4+): PostToolUse hook running `ruff format <file>` on backend `*.py` edits.
- **Deferred-tool schema guessing** (Monitor `InputValidationError`): one skill line — "ToolSearch-load deferred tools before first use."
- **Duplicate parallel cycle start** (`7cc14913`): a `.specs/` cycle-in-progress lockfile checked at Stage 0.
- **Outage handling**: status-page memories were applied, but blind 10-min blocking polls still happened — encode "on confirmed outage, one long wakeup (15–30 min) + a parked status message, not poll loops."

---

## 3. Fakeflix / tech-leads-club comparison

### What fakeflix does (and Learny doesn't yet)
1. **Thin operational root file with a task→doc routing table** — AGENTS.md is ~125 lines of commands, caveats, and routing; all depth delegated. Learny's CLAUDE.md has the progressive-loading half but is missing the *operational* half (commands, env quirks, quickstart, routing table).
2. **Deny-list permissions** (`git push`, `git commit`, `gh pr create` denied; all else allowed). Learny's ship-cycle needs commit/push, so the transferable idea is the *shape*: a small, intentional project permission file instead of none.
3. **Architecture rules as executable fitness functions** wired into lint + first CI step. Learny's equivalents are prose ADRs — e.g. "no provider SDK imports outside adapters" (ADR-0009/0019/0020) is mechanically checkable with a small script/ruff rule in CI.
4. **One verification vocabulary** in root package.json (`lint:all`, `test:unit:all`…), referenced by name in AGENTS.md, identical in CI. Learny: fragmented `cd` + tool invocations → a root Makefile/justfile (`make test-backend`, `test-frontend`, `lint`, `check`).
5. **Known-issues section in the instruction file** — cheap, saves rediscovery (Learny candidates: Docker Desktop/WSL, db+minio pair, no jq, cwd resets, PATH).
6. **CI-resident `/review`+`/fix` comment agents** with re-injected guardrails — optional for a solo repo; the local `pr-review` subagent flow covers most of it.
7. **`.bench/` self-benchmarking** of competing planning workflows with a frozen PRD + AC baseline and identical evaluator — a natural fit for Learny's eval-maturity thread if the tlc flow is ever in question.

### Does any other org repo match fakeflix?
Graded sweep of all 19 repos: **only `nj-mmo` is comparable**, and it is the *complementary* half — an autonomous-loop harness rather than fakeflix's supervised+review harness. Its steal-worthy deltas, all directly relevant to Learny (whose workflow is the nj-mmo shape):
- **Committed `.specs/` as durable loop memory** (STATE.md decision log, ROADMAP.md with checkbox phases, in-repo LESSONS) — Learny already does this; nj-mmo validates the pattern.
- **Driver-only repo-local skill layered over shared `tlc-spec-driven`** with an explicit "do not duplicate upstream" rule — exactly what `learny-ship-cycle` is; nj-mmo's delta-table format is a cleaner way to express it.
- **Deterministic gates for output tests can't judge** (`visual-gate.mjs`) — analogue for Learny: golden-fixture structural checks already exist; the pattern generalizes to UI/reader work.
- **The 10-second rule**: slow tests framed as an *agent* failure mode ("agents stall and burn cycles waiting on slow suites") — pertinent given the teach-panel flaky-CI loop (3 red runs in one session).

Rest of the org: `agent-skills` = strong meta-layer (CI-validated skill schemas; good workflow doctrine); `fake-erp`, `enterprise-apps-classes` (fakeflix's ancestor), `tlc-floripa-harness-exercises`, `architecture-fit-ai` = instructions-only; remaining ~11 repos = no harness. One caution from the floripa workshop worth keeping in mind while applying everything above: **over-constraint is its own failure mode** — "a harness built for a weak model becomes the bottleneck when the model improves." Prefer few, evidence-backed rules over exhaustive rulebooks.

---

## 4. Prioritized action plan

**Tier 1 — cheap, kills the most observed pain**
1. Fix the `lessons.py` path in `tlc-spec-driven` SKILL.md/references (skill-local path). Review + generalize the 15 stuck candidate lessons.
2. Create `.claude/settings.json`: permission allowlist (seed via `fewer-permission-prompts`), `"includeCoAuthoredBy": false`, `env` block (PATH; test DB URL reviewed against provider-pin work).
3. `learny-ship-cycle` SKILL.md upgrades: continuation contract (no standing-by, single gate), bounded idle/nudge protocol, limit-death degradation policy, `.specs/.ship-status` heartbeat + resume contract, CI-wait incantation, memory-file read-before-write, wrap report = next row + model recommendation + token table.
4. CLAUDE.md operational section: quickstart + URLs, verification commands, known issues (Docker Desktop/WSL, db+minio, no jq, cwd resets, schema lookup before SQL), AskUserQuestion recommendation rule, task→doc routing table.

**Tier 2 — structural, this month**
5. Root Makefile/justfile as the single verification vocabulary; reference targets by name in CLAUDE.md and CI.
6. `pr-review` skill: per-file diff splitting, editable-issue-comment summaries, reviewer completion contract, compact-report rule.
7. `learny-finalize`: PR-body no-hard-wrap line; `learny-ship-cycle` args contract (`once`/`auto`/`until`).
8. PostToolUse hook: `ruff format` on backend Python edits.
9. Model policy table encoding the already-decided tiering rules.

**Tier 3 — when the relevant work recurs**
10. Provider-SDK-leak fitness script in CI (ADR-0009/0019/0020 made executable).
11. Live-run budget protocol for paid evals (`LEARNY_EVAL_BUDGET_USD`, checkpointed batches).
12. `/ship-status` command; `.specs/` cycle lockfile; optional `.bench/`-style workflow self-benchmark.

---

*Evidence base: six batch analyses over 30 transcripts (Jul 10–24), fakeflix deep-dive, 19-repo org sweep, local harness audit. Detailed per-session findings live in the session transcripts; this document records the durable conclusions.*
