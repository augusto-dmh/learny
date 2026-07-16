---
name: learny-ship-cycle
description: 'End-to-end orchestrator for one Learny roadmap PR: pick the next cycle from the roadmap, run a tlc-spec-driven cycle auto-selecting recommended options, publish the PR with learny-finalize, run pr-review in a fresh-context subagent, triage every review finding against the code, apply accepted fixes, delete all PR comments, and merge after a single user approval. Use when asked to "ship the next PR", "run the ship cycle", "do the next roadmap cycle end-to-end", or to resume a partially shipped cycle. Not for ad-hoc edits, standalone reviews (use pr-review), or publishing-only work (use learny-finalize).'
license: CC-BY-4.0
metadata:
  author: Learny contributors
  version: 1.1.0
---

# Learny Ship Cycle — Orchestration Protocol

Runs one roadmap cycle from "what's the next PR?" to merged, replacing the previous three manual sessions (tlc build → pr-review → triage/cleanup/merge) with one orchestrated pipeline. This skill owns only the glue; the work itself is delegated to `tlc-spec-driven`, `learny-finalize`, and `pr-review` unchanged.

**Autonomy contract:** the pipeline runs without user prompts except at exactly one gate — merge approval (Stage 7) — plus the escalation rule in Stage 1. Everything else proceeds on the recommended option, logged for audit.

## Stage Detection (always run first)

The pipeline is resumable. Determine the current stage before doing anything:

| Observation | Resume at |
|---|---|
| Clean `main`, ROADMAP next phase "Not started" | Stage 0 |
| Cycle branch exists, tlc Execute/Verifier incomplete (`.specs/features/<cycle>/`) | Stage 1 (tlc resume) |
| Verifier PASS on branch, no open PR | Stage 2 |
| PR open, no `<!-- learny-review:` comments on it | Stage 3 |
| PR has review comments, no `.specs/features/<cycle>/review-triage.md` | Stage 4 |
| `review-triage.md` exists, accepted fixes not yet pushed | Stage 5 |
| Fixes pushed, PR comments still present | Stage 6 |
| PR comment-free, unmerged | Stage 7 |

Announce the detected stage and the cycle/PR it applies to before proceeding.

## Stage 0 — Preflight

1. Require a clean working tree. If dirty, stop and report — never stash or discard.
2. `git checkout main && git pull`.
3. Read `.specs/project/ROADMAP.md` and the Handoff section of `.specs/project/STATE.md`. The next cycle is the first ROADMAP row not started; its scope comes from the mapped TDD phases in `docs/tdd/0001-mvp-architecture.md`.
4. State the chosen cycle, its TDD phase(s), and the intended slice in one short paragraph, then continue — no approval needed.

## Stage 1 — Plan & Build (tlc-spec-driven)

Invoke `tlc-spec-driven` for the cycle (Specify → Design → Tasks → Execute per its auto-sizing).

**Auto-decision rule** (replaces the human answering Discuss questions): at every decision point, formulate the options — each with why-recommend AND why-not — pick the recommended one, and record option set, choice, and rationale in the cycle's `context.md` and as an `AD-NNN` row in `.specs/project/STATE.md`. The decision must be auditable later without the conversation.

**Escalation rule** — ask the user (AskUserQuestion) instead of auto-deciding only when:
- the decision changes product direction or MVP scope beyond the cycle,
- it locks in an external dependency/provider that CLAUDE.md or an ADR says needs its own decision, and no clear recommendation exists, or
- no option is defensible as recommended.

Execute honors the full tlc contract (tests from acceptance criteria, gate per task, atomic commits, mandatory fresh Verifier). A Verifier FAIL stops the pipeline with the report — do not continue to Stage 2.

When Execute runs one worker per phase, set each worker's model per the **Cost discipline** section (Opus for any phase with a design decision or correctness invariant; Haiku only for a chore dispatched as its own unit; Verifier always Opus), and give each worker scoped gate commands (affected module per commit, full suite at phase boundary).

## Stage 2 — Publish (learny-finalize)

Invoke `learny-finalize` for branch, commit hygiene, verification notes, and the PR. Include the cycle's planning artifacts (`.specs/features/<cycle>/*`, STATE.md, ROADMAP.md row update) in the PR as in previous cycles. Capture the PR number for all later stages.

## Stage 3 — Review (fresh context, author ≠ reviewer)

Spawn ONE subagent via the Agent tool (`general-purpose`, fresh context) with a prompt containing only: the repo, the PR number, and the instruction to invoke the project-local `pr-review` skill for that PR and follow it exactly.

**Do not** pass implementation context, spec content, or this session's reasoning into the subagent — the reviewer's independence is the point of the fresh context (this reproduces the old separate `/pr-review` session). Wait for it to finish; its deliverable is comments on the PR, not text returned to you.

## Stage 4 — Triage

1. Fetch every comment: inline `gh api repos/{repo}/pulls/{N}/comments --paginate` and PR-level `gh api repos/{repo}/issues/{N}/comments --paginate`.
2. For each finding, check it against the actual code: is it **real or not**? If real, would you **act on it or not, and why**? Judge on the code as it exists, not on the reviewer's authority; findings that misread the code, duplicate an accepted decision (ADR/AD-NNN), or trade against recorded scope decisions are rejected with the reason.
3. Persist the triage to `.specs/features/<cycle>/review-triage.md` before touching anything: one row per finding — source comment, file:line, verdict (real/false), action (fix/won't-fix), rationale. Comments get deleted in Stage 6, so this file is the only surviving record of the review reasoning.

## Stage 5 — Fix

Apply every "fix" finding. Group into atomic Conventional Commits per `learny-finalize` rules (plain-language messages, no internal IDs, no AI attribution). Re-run the cycle's gates (backend tests, frontend tests, ruff, tsc — whatever the cycle used) before pushing. Push to the PR branch.

## Stage 6 — Clean Comments

Delete ALL comments from the PR:

- inline: each id from `repos/{repo}/pulls/{N}/comments --paginate` via `gh api -X DELETE repos/{repo}/pulls/comments/{id}`
- PR-level: each id from `repos/{repo}/issues/{N}/comments --paginate` via `gh api -X DELETE repos/{repo}/issues/comments/{id}`

Re-fetch both endpoints and verify zero remain. If a submitted *review* (not a comment) exists, it cannot be deleted via the API — report it as a leftover artifact instead of retrying.

## Stage 7 — Merge Gate (the one user prompt)

Present a compact ship report: cycle, PR number, Verifier result, triage counts (real/false, fixed/won't-fix), fix commits, gate results, comment cleanup status. Then ask the user (AskUserQuestion): merge now or hold.

On approval: `gh pr merge {N} --merge` (merge commit, matching PRs #4–#9), then `git checkout main && git pull` and delete the local feature branch.

## Stage 8 — Wrap

Confirm the merged ROADMAP row shows the cycle done (it shipped inside the PR; fix on `main` only if it was missed, as a tiny follow-up). Report the cycle closed and name the next roadmap phase. Do not start it automatically — the next run of this skill picks it up.

## Cost discipline — model selection, gates, context (applies across stages)

Default model is **Opus**. Downshift a delegated unit to **Haiku only** — never Sonnet (its per-task output is far larger, erasing the price gap for this pipeline's work). A wrong cheap worker is not free: it costs the bad output *plus* the Verifier catching it *plus* a fix task *plus* re-verification, which can exceed the Opus baseline. So Haiku is a bet on **low slip-probability**, taken only when the task guarantees it.

**Haiku-safe test — downshift a unit only when ALL four hold:**
1. **Fully specified** — exact files, signatures, and steps already in spec/design; no design decision or trade-off left to the worker (it transcribes, it does not invent).
2. **No correctness-critical invariant** — nothing touching idempotency, transaction boundaries, migrations, concurrency, ordering, injection/auth. A weak model fails *quietly* there: passes a thin gate, caught only by the Verifier — or not at all.
3. **A fast local gate catches a slip** — a failing `pytest`/`ruff`/`tsc` surfaces the mistake immediately, so an error is a retry, not a silent defect.
4. **Small blast radius** — few files, no ripple into shared schema/state.

Fail any one → **Opus**. **When unsure → Opus.**

**Per-stage default:**

| Unit | Model |
|---|---|
| Stage 0 preflight · Stage 6 comment cleanup · Stage 8 wrap (pure git/gh/file ops) | Haiku |
| Stage 1 doc-only chores dispatched as their own unit — ADR prose, `.env.example`, settings/deps scaffolding | Haiku |
| Stage 1 phase workers carrying any design decision or correctness invariant (schema/migrations, retrieval, workers, auth, idempotency, ordering) | Opus |
| Stage 1 Verifier | Opus — **never downshift**; it is the confidence backbone, and a weak verifier that misses a surviving mutant defeats the pipeline |
| Stage 3 review | governed by `pr-review` — do not override its models |
| Stage 4 triage (real-vs-false against the code) | Opus — adversarial reasoning |
| Stage 5 fixes | Opus by default; Haiku only for a truly local, fully-specified fix that passes the four-condition test |

A ship-cycle **phase is one worker** even when it mixes scaffolding with a hard kernel (e.g. env+settings alongside a batching algorithm or a sub-batch-ordering edge): the kernel sets the model, so keep the whole phase on Opus. Split a chore to Haiku only when it is dispatched as its own unit. Do **not** treat the Verifier as license to Haiku-ify hard work — its sensor only catches faults it mutates; sensor-blind gaps slip.

**Gate scoping (no quality risk):** run the affected test module/subset per intermediate task commit; run the full suite once per phase boundary and once before pushing fixes. The Verifier's discrimination mutations run only the target test file, not the whole suite per mutation.

**Context hygiene (no quality risk):** delegate the opening codebase survey to an `Explore` agent that returns seams — signatures + `file:line` refs, not bodies — instead of reading many full files into the orchestrator context; scope search globs to `app/**` / `tests/**` and never dump `.venv`.

## Hygiene (applies to every stage)

- No AI/tooling attribution anywhere public (commits, PR, comments).
- No internal IDs (task/AD/FR/cycle/Gate) in commits, PR bodies, or PR comments — they live only under `.specs/`.
- Multiline `gh` bodies go through `--body-file`/`-F body=@file`, never `-f body=@file`.
- Never post PR-level content as a review (`gh pr review`) — reviews cannot be deleted.
