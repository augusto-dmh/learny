---
id: harness-gap-critique
title: Gap critique — claim matrix, conflicts and coverage for the harness drop
date: 2026-09-30
status: final
---

# Gap critique

Lead's pass over `rq01`–`rq05` before synthesis. It reconciles overlaps, records conflicts with a resolution, and lists what the fleet could not establish. Lead spot-checks run on 2026-09-30 are marked **[lead-verified]**.

## 1. Claim matrix (load-bearing claims only)

| # | Claim | rq01 | rq02 | rq03 | rq04 | rq05 | Strength |
|---|---|---|---|---|---|---|---|
| C1 | The fresh-context, independent verifier/reviewer is the one heavy gate that reliably earns its cost | ✔ verifier found real gaps in most runs | ✔ lean Verifier rounds caught failures | ✔ review+triage: 231 findings / 20 cycles, 86% fixed | ✔ all folders agree | ✔ Anthropic, TLC, bench | **High** |
| C2 | Ceremony must scale with the change; small diffs should not enter a spec cycle | ✔ two-tier plan skill, ~2 PRs/day | ✔ lean "diff in one sentence → checks only" | ✔ `.specs` 4–10× the code in small PRs (#70, #72) | ✔ lean's single escape | ✔ Anthropic, Spec Kit bug-fix flow, Böckeler | **High** |
| C3 | Sub-agent over-delegation is the owner's sharpest cost complaint; blind review is the delegation he wants | ✔ 29 sessions | ✔ 22 complaints; 17-agent incident from driven 2.0 | ✔ 15 subagents, $95 on a docs PR | ✔ | ~ (multi-agent often underperforms, secondary) | **High** |
| C4 | `tlc-spec-lean` fits better than `tlc-spec-driven` | ~ (works for multi-session; can still balloon) | ✔ 1/3 artifacts, 1/5 owner msgs (confounded) | ~ (supports slimming; no lean data) | ✔ Medium | ✔ TLC bench: ≥ fidelity, 10–30% fewer tokens | **Medium** |
| C5 | The lessons layer produces no value | ✔ 0/7, dropped | ✔ 30 candidates, 0 confirmed | ✔ 31 ever, 0 promoted, 22 expired | ✔ 0 confirmed in 4 projects | — | **High** |
| C6 | Rules living only in prose leak; enforcement must be mechanical | ✔ finalize-refuses-without-verifier moved compliance 9/24 → 6/7 | ✔ Houston/fala scripts | ✔ 9 untyped commits in #69; model policy ignored | ✔ fala 12 | ✔ Stripe, 4–16% rule coverage | **High** |
| C7 | Learny's sensors give false signals | — | — | ✔ PASS with 940 DB tests skipped; nightly red 66 runs; image rot ×2 | — | ✔ "sensors" at Trial | **High** |
| C8 | Learny PRs are not "small and reviewable" | — | ✔ owner prefers consolidated PRs | ✔ median 4.7k lines, 50 files | ✔ fala 12: median 4,540 | ~ no solo-dev evidence | **High (fact) / contested (remedy)** |
| C9 | Harnesses should be pruned periodically, by evidence | ✔ 5 rounds, output = deletion | ✔ Houston routine 13/17 at ~$7 | ✔ Learny harness unchanged since 07-28 | ✔ | ✔ Anthropic dropped sprints | **Medium-High** |
| C10 | Learny's end-to-end orchestrator is an advantage the other repos lack | ✔ workA moving toward one end gate | ✔ removes friction #1 (manual handoff bridge) | ✔ 3 owner msgs, ~1h45m per cycle | — | ~ deterministic outer loop (Low-Med) | **Medium-High** |

## 2. Conflicts and resolutions

**K1 — How much shorter is lean?** rq02: ~530 vs ~1,400 lines (one third). rq04: 515–603 vs Learny's median 754, so 20–35% shorter. rq01: a lean UI feature reached a 13.4k-word `checks.md` with 151 checks and 8 verifier rounds.
*Resolution:* all three are right about different baselines. Against driven 3.3.0 as it actually runs now (Learny's September median `tasks.md` alone is 426 lines; cycles ~900 lines), lean is roughly a third to a half shorter. Against Learny's older 3.1.0 runs it is 20–35% shorter. Lean is **not** self-limiting on UI surfaces — it needs an explicit checks budget and a round cap. The case for lean rests on *what* it drops (task choreography, self-review tables, extra human stops), not on line counts.

**K2 — "0 of 30 PRs formally reviewed" (rq04, citing fala 12) vs "231 review findings" (rq03).**
*Resolution:* both true. Review happens in a fresh subagent and is recorded in `review-triage.md`; Stage 6 then deletes every PR comment, so GitHub shows zero reviews. The defect is visibility, not absence.

**K3 — AI-attribution trailers: "fixed" vs "leaking".** rq04 relays 60 trailers. **[lead-verified]** `git log` since 2026-08-01: 56 commits carry `Co-authored-by: Cursor`, 55 of them on 2026-09-04 (the five-cycle chain day), 1 on 08-28; 4 Claude trailers are from July. `includeCoAuthoredBy:false` fixed the Claude path; the Cursor path leaked because the rule lives in prose. Supports C6.

**K4 — Fault injection: keep (rq04, pin `standard`) vs weak signal (rq03: kill rates ~100%, review still finds ~11 real issues per cycle).**
*Resolution:* the mutation sensor and review catch different classes — mutation proves tests can fail; review catches unwired paths and wrong scope. Keep `standard` (≤5 faults, cheap) but stop treating a high kill rate as the confidence signal; the honest-sensor fixes (C7) matter more.

**K5 — Lean's human plan gate vs ship-cycle's single-gate autonomy.** rq04 I3 frames it as auto-approve vs two gates. Owner evidence: plans are approved fast (17/22 first pass, rq01) and door-by-door in lean repos ("Aprovo as duas portas", rq02); his corrections are about the agent *acting before approval* and choosing things he "haven't said yes for". The v8 rows contain real one-way doors (BYOK ADR, i18n framework, Paddle).
*Resolution:* a door-only plan gate — one question listing the plan's one-way doors and unconfirmed assumptions — waivable in `auto` mode. Owner decision (D1 in synthesis).

**K6 — PR size remedy.** fala 12 recommends ~400-line PRs, squash, stacked above 1,000. The owner repeatedly chooses *fewer, consolidated* PRs (rq02 F5). Learny's portfolio goal values readable atomic history.
*Resolution:* do not impose stacked PRs on a solo repo. Keep one PR per row, but size **rows** smaller at authoring time and split a row into sequential slice-PRs when lean's size arithmetic exceeds budget. Owner decision (D2).

**K7 — Model policy.** Learny's text: Opus default, never Fable blanket, never Fable on Security. Practice: Fable everywhere in PR #72. The owner elsewhere: "plan in Fable, execute in Opus in a fresh session", "do not ever choose fable" for sub-agents.
*Resolution:* rewrite the policy to the owner's own stated practice, not keep a rule nobody follows.

**K8 — CLAUDE.md length.** rq05 says <200 lines and pointer-only; Learny's is 82 lines (9.6 KB) — compliant on length but ~40% history ("Current Status" release ledger). Low priority.

## 3. Coverage gaps

- **No head-to-head driven vs lean on Learny.** External bench is n=2 on one Node PRD with no PR/review stage; internal lean evidence is 4–10 days old and mostly greenfield. Mitigation in synthesis: pilot + scorecard, not a big A/B.
- **Learny transcript coverage is n=1 cycle** (July and #48–#71 transcripts were pruned before `cleanupPeriodDays: 365`). Owner-intervention numbers for Learny rest on PR #72.
- **Triage independence untested.** The 97% "real" rate is the author judging its own reviewers' findings.
- **Hooks in practice.** No owner repo uses quality hooks except Houston (maintainer-authored). Hook upkeep cost for Learny is estimated, not observed.
- **Trunk-based vs PR-per-feature for solo devs:** rq05 found no rigorous source.
- **OpenAI harness-engineering post** returned 403; reconstructed from secondary sources.
- **Uvik "spec-driven benchmark"** excluded as unreliable (dated after its publication).
- **Cost.** Session cost is from `cost-state` only; subagent spend may be double- or under-counted.

## 4. Verdict on the fleet

Coverage is sufficient for a decision on *shape* (High) and on *which skill* (Medium). It is not sufficient to claim lean will raise Learny's quality — only that it removes cost the evidence says buys nothing. The synthesis therefore pairs the switch with a measured pilot.
