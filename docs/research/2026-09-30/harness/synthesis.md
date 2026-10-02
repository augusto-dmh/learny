---
id: harness-synthesis
title: Synthesis — reshape Learny's delivery loop before v8
question: Is Learny's cycle model (tlc-spec-driven wrapped by learny-ship-cycle) the right harness for the v8 roadmap, and what should change first?
date: 2026-09-30
status: final
overall_confidence: medium-high
---

# Synthesis — reshape the loop, keep the orchestrator

## TL;DR

**Keep the loop of cycles, but change its shape.** The ship-cycle orchestrator and fresh-context review are the parts of the harness that work. Learny's orchestrator takes a roadmap row to merge with three owner messages ([rq03 F2](rq03-learny-harness-audit.md)). It removes the manual handoff bridge that the owner's other projects rank as friction #1 (rq02 F2). Review plus triage yields about 11.5 real findings per cycle, including unwired main paths ([rq03 F4](rq03-learny-harness-audit.md)).

The problem is what sits inside and around that loop:
- **Too much paperwork:** a `tlc-spec-driven` cycle writes about 900 lines of `.specs/` per row, with `tasks.md` growing 2.5× since September, a 247 KB `STATE.md`, and a lessons layer that has never promoted a lesson.
- **One fixed size:** the only unit is "roadmap row = full cycle = one PR of about 4.7k lines".
- **Sensors that lie:**
  - a Verifier PASS with 940 tests skipped;
  - a nightly that has been red for 66 runs;
  - rules that exist only in prose, so model policy and commit trailers leak.

The owner has already moved every other repo to `tlc-spec-lean`: 30 sessions on lean against 3 on driven since 09-15 ([rq04 A2.3](rq04-local-research-and-tlc.md)). The TLC authors call the parts of driven that lean dropped "babysitting", and their own benchmark shows lean matching or beating driven at 10–30% fewer tokens ([rq05 F1](rq05-external-practice.md)).

**Recommendation:** before v8 row 1, run one `harness-reset` cycle that:
1. Makes the sensors honest and mechanical.
2. Cuts the paperwork.
3. Rewires `learny-ship-cycle` onto `tlc-spec-lean` (profile `standard`), with two lanes, small and feature, chosen by rule.
4. Pilots the result on the first two v8 rows against a scorecard.

**Confidence:** High on the shape. Medium on lean, until the pilot.

## The diagnosis in one table

| Harness part | Verdict | Evidence |
|---|---|---|
| `learny-ship-cycle` orchestration (stages, heartbeat, continuation contract, single merge gate) | **Keep.** It is Learny's advantage | rq03 F1–F2 (3 owner messages per cycle, down from 25+ nudges); rq02 F2; rq01 implication 6 |
| Fresh-context `pr-review` + triage | **Keep, retune** | rq03 F4 (231 findings, 86% fixed); C1 in the gap critique |
| Independent Verifier | **Keep, make honest** | rq01 F4, rq02 F7, rq03 F5 (PASS with 940 skips) |
| `tlc-spec-driven` Specify→Design→Tasks→Execute | **Replace with `tlc-spec-lean`** | rq04 B2–B9, rq05 F1.2–F1.5, rq02 F7 |
| One size for every change | **Replace with two lanes** | rq01 F2, rq05 F2–F3, rq03 F3 |
| `STATE.md` AD row per auto-decision | **Drop the practice; archive the file** | rq03 F3, rq04 B8; TLC issue #176 |
| Lessons layer | **Drop** | Gap-critique C5 (0 confirmed in 4 projects) |
| Vendored `tlc-spec-driven` 3.1.0 | **Drop.** It is shadowed and dead | rq03 F8, rq04 B1; lead-verified `Base directory` |
| About 10 never-used project skills | **Drop** | rq03 F8 |
| Prose-only rules (commit types, trailers, model policy, skip-tolerant verify) | **Replace with hooks and CI gates** | Gap-critique C6, K3; rq05 F3.8 |
| Deleting PR review comments | **Keep (owner decision D4).** `review-triage.md` stays the record | Gap-critique K2 (visibility trade-off accepted) |
| Nightly eval, red since 07-27 | **Disable the schedule, keep manual dispatch, record the reason (D5)** | rq03 F9 |
| Model policy table | **Rewrite to the owner's real practice** | Gap-critique K7 |

## Target harness

### Two lanes, chosen by rule (not by model judgement)

The lane is chosen at Stage 0, from the roadmap row or the request. The model may propose a lane, but it cannot downgrade one on its own, because lean dropped auto-sizing for exactly that reason: "the model sized itself and skipped phases" ([rq05 F1.2](rq05-external-practice.md)).

**Lane S (small).**
- **Trigger:** the diff fits in one sentence, about 3 files or fewer, no migration, no new ADR, no new route or screen, no one-way door.
- **What runs:** lean's `checks.md` with only `## Intent` (or no `.specs` folder at all) → build → `make check` → finalize → PR → review with 1–2 lanes picked from the diff → merge gate.

**Lane F (feature).**
- **Trigger:** everything else, which includes every v8 row.
- **What runs:**
  - `tlc-spec-lean` Plan → **door gate** → Checks → Build → Verifier → PR → scoped review → triage → merge gate.
  - Profile `standard` by default, `ui` for rows whose binding source is a design. Budget 150k.
  - Hard caps: 3 Verifier rounds, and a checks budget. Over budget, split the row into slices instead of growing `checks.md`. rq01 F3 is the warning here: 151 checks and 8 rounds.

### Sensors that cannot lie (mechanical, in CI or hooks)

1. **No PASS while database tests are skipped.**
   - `LEARNY_REQUIRE_DB=1` turns the `requires_db` skip into a failure. It is set in CI and in the Verifier brief.
   - `make infra` becomes a precondition for the Verifier (rq03 F5).
2. **Commit-message gate in CI:** `check_commit.py` over every PR commit, plus a trailer check: require `Assisted-by: Claude Code`, reject `Co-authored-by`/`Made-with` agent trailers (D3; rq03 F7, gap-critique K3).
3. **A ruleset on `main`:** require CI green and forbid direct pushes. **[lead-verified]** `main` is currently unprotected.
4. **Pin every upstream image by digest:** extend ADR-0031's approach, after rot broke CI twice (rq03 F9).
5. **Nightly eval:** drop the `schedule` trigger, keep `workflow_dispatch`, and record the reason (unfunded key) in `eval.yml`, CLAUDE.md and the README (D5). A permanently red signal teaches everyone to ignore red.
6. **Optional, second wave:** a Stop-hook "grind" (lint and tests on stop), as in TLC `harness-toolkit` ([rq05 F1.6](rq05-external-practice.md)). Add it only after 1–5 are in, and with should-fire and should-not-fire tests.

### Review, retuned

- **Lanes picked from the diff.** No LGPD or i18n lane on a backend-only PR. Name the model on every lane.
- **Reviewers reproduce a finding before reporting it.** This follows Anthropic's warning that reviewers asked to find gaps will invent them.
- **Comment cleanup stays as is (D4).** Stage 6 keeps deleting PR comments; `review-triage.md` in `.specs/` remains the review record.
- **Optional:** a one-line note from the Verifier on each triage verdict, so the author is no longer the only judge of the 97% "real" rate (gap-critique §3).

### Paperwork diet

- **`STATE.md`:** archive the current file to `.specs/project/archive/STATE-v1-v7.md`. The live `STATE.md` keeps only the Handoff block plus open cross-cycle decisions. Per-cycle auto-decisions go to `plan.md` `## Assumptions` (`Confirmed? n`), and real architecture goes to an ADR (rq04 B8, I8).
- **Lessons:** delete `LESSONS.md` and `lessons.json`; lean says the flow is unaffected. Durable rules found in triage go straight into `.specs/codebase/CONVENTIONS.md` or a CI check.
- **Skills:** remove the vendored `tlc-spec-driven` and vendor `tlc-spec-lean` 1.1.0. Then confirm which copy loads, from the `Base directory` line. Prune the ~10 never-referenced skills; they are recoverable from git if a v8 row needs one.
- **Retrospectives:** none exist for v4–v7. Replace them with the harness review below, which produces one short retro per roadmap.

### Model policy (rewritten to practice)

| Role | Model |
|---|---|
| Plan and door gate (main thread) | Fable or Opus |
| Build | Opus |
| Verifier | Opus, never the cheapest tier |
| Review lanes | Sonnet for mechanical lanes, Opus for correctness, security and architecture |
| Sub-agents | Never Fable |

Delegation default: inline. Sub-agents only for the Verifier, the review lanes, or genuinely context-swamping work (rq02 implication 2, rq01 F5).

### Harness review loop

Run one mined-transcript review per roadmap, or monthly, whichever comes first.
- **Input:** the Learny transcripts, which are now retained for 365 days.
- **Default output:** deletion.
- **Method:** reuse Houston's harness-review method (13 of 17 recall at about US$ 7) rather than another manual round ([rq04 A2.2](rq04-local-research-and-tlc.md)).
- **Validation:** check proposed prunes against observed behaviour, not judge-only scoring. The workA lesson: "tu nem testou em tela né?" (rq01 F6).

## Moves (sequenced)

| # | Move | Size | Notes |
|---|---|---|---|
| 0 | Commit the uncommitted work separately: the v8 candidate rows, the `docker-compose.override.yml` port parameterisation, and both research drops | trivial | It needs to be in git before any cycle reads `ROADMAP.md` |
| 1 | **`harness-reset` row, PR A: sensors and hygiene.** Sensors 1–5; `STATE.md` archive; retire lessons; retire the vendored driven copy; prune skills; rewrite the model table; `Assisted-by` trailer in settings + finalize | 1 cycle (run on the *current* ship-cycle, deliberately the last driven cycle) | Low risk; pure removals plus CI |
| 2 | **`harness-reset` PR B: the loop.** Vendor `tlc-spec-lean`; rewire ship-cycle Stage Detection and Stage 1 (rq04 B11 table), `pr-review` Track A, `learny-finalize`, `SKILLS.md`, CLAUDE.md profile block; add the two lanes and the door gate | 1 cycle | Keep a legacy fallback in `pr-review` for the 50 driven folders, which lean ignores (rq04 B10) |
| 3 | **Pilot:** ship v8 rows 1–2 (`pt-br-interface`, then one backend row) on the new loop and fill the scorecard | 2 cycles | Kill criterion below |
| 4 | Harness review #1 after the pilot | 1 session | Its default output is deletion |

### Pilot scorecard

The baseline comes from rq03: September driven cycles plus PR #72.

| Metric | Baseline | Pilot target |
|---|---|---|
| `.specs` lines per Lane F cycle | ~900 | ≤ 550 |
| Owner messages per cycle (excluding gates) | 3 (n=1) | ≤ 3 |
| Prompt-to-merge wall clock | 1h45m – 3.5h | ≤ same |
| Session cost | $95 (docs PR, all Fable) | ↓ |
| Review findings judged real and fixed | ~11.5 / ~10 per cycle | not lower by more than ~30% (the quality floor) |
| Defects escaping to `main` (CI red on main, hotfix within 7 days) | 2 frontend reds on main since 07-25 | 0 |
| Verifier PASS with skipped tests | it happened | impossible by construction |

**Kill criterion:** if both pilot cycles lose more than 30% of real review findings *and* show an escaped defect, revert Stage 1 to driven 3.3.0. Keep the sensors and the diet regardless; they do not depend on the skill choice.

## Owner decisions (taken 2026-10-02)

| # | Decision | Chosen | Consequence for the moves |
|---|---|---|---|
| D1 | Lean's plan gate inside ship-cycle | **Door-only gate:** one question listing the plan's one-way doors and unconfirmed assumptions; waivable in `auto` mode | Ship-cycle gains a second stop (doors) before Checks; the merge gate stays |
| D2 | PR size | **One PR per batch of slices.** Under lean's budget, one PR per row. Over budget, ship-cycle pre-answers lean's mechanism ask with "handoff", and each sequential batch (cut at slice boundaries, never mid-slice) becomes its own PR, merged before the next starts. v8 rows are authored smaller | **Deviation from lean:** lean dispatches one Verifier over the whole feature. Here the Verifier runs scoped to the batch's checks before each PR, and in full before the last one |
| D3 | AI attribution | **`Assisted-by: Claude Code` trailer**, set via `attribution` in project settings and required by the CI commit check | **Deviation from lean:** `references/build.md:108` forbids any agent attribution trailer. `learny-finalize` and the vendored lean copy must state the override |
| D4 | Review comments | **Keep deleting them after triage** (status quo) | No change to Stage 6; GitHub keeps showing zero reviews, by choice |
| D5 | Nightly eval | **Disable the schedule, keep manual dispatch, record why** | The "promote the economy profile after a green nightly" candidate waits for a manual funded run |
| D6 | Merge style | **Keep merge commits, add commit lint in CI** | No change to `learny-finalize` merge flags |

Lean deviations to record in the vendored skill or CLAUDE.md block: per-batch Verifier (D2) and the attribution trailer (D3).

## What must be true for this to work

- The ship-cycle keeps its run-without-asking contract, apart from the door gate (D1) and the merge gate.
- The lane trigger is a rule a reviewer can check, not a model's self-assessment.
- A sensor that is red for more than a week is either fixed or removed in the same week.

## Out of scope

- The v8 rows themselves and their order (`../synthesis.md`).
- Provider choices (ADR-0019, ADR-0020).
- Houston as a dependency: Learny stays runnable in plain Claude Code.
- Workflow-tool orchestration: rq05 rates it Low-Medium, and the owner stopped the only run (rq02 F8).
- Cloud routines and `/loop`: the owner does not use them, and nothing here needs them.

## Traceability

| Recommendation | Sources |
|---|---|
| Keep orchestrator and review | rq03 F1–F2, F4; rq02 F2, F9; rq01 implications 5–6, 10 |
| Lean + two lanes | rq04 B2–B11, I1–I3; rq05 F1, F2, F3.1; rq02 F7; rq01 F2–F3 |
| Mechanical sensors | rq03 F5, F7, F9; rq05 F1.6, F3.8; rq02 F9; gap-critique K3 |
| Paperwork diet | rq03 F3, F6, F8; rq04 A2.4, B8, I7–I8; rq01 F6 |
| Model and delegation policy | rq01 F5, implication 8; rq02 F2–F3; rq03 F2; gap-critique K7 |
| Harness review loop and pilot | rq01 F6; rq04 A2.2, I9; rq05 F6, implications 6, 8 |
