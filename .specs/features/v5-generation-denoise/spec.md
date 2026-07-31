# Generation-Verdict De-Noise (RFC-005 Cycle C) Specification

## Problem Statement

The product's generation default (`claude-sonnet-5`) rests on a single-observation A/B: the 2026-07-21 study ran each arm once, and its STAY verdict hinged on a lone 0.005 silver-faithfulness gap — indistinguishable from sampling noise. That study also ran through an ad-hoc, uncommitted driver (recorded as an evidence limitation), and a prior full attempt died mid-judge on credit exhaustion with no way to resume. Cycle B settled the judge (`claude-opus-4-8`, thresholds 0.90/3.1), so the generation question can now be re-asked properly: multiple runs, per-metric variance, a pre-registered noise-aware decision rule, and a committed, checkpointed, resumable runner.

## Goals

- [ ] The Sonnet-vs-Opus generation verdict is re-derived from ≥3 full generate+judge runs per arm with per-metric variance recorded, and the resulting stay/move decision is applied (config flip on move, documented stay otherwise).
- [ ] The study runner is committed code with per-unit checkpointing and resume — the uncommitted-driver and credit-exhaustion limitations of the 2026-07-21 study are both closed.

## Out of Scope

| Feature | Reason |
|---|---|
| Judge A/B or judge model changes | Settled by Cycle B (ADR-0028, flip to opus); not re-opened |
| New eval metrics (Ragas etc.) | Deferred by ADR-0016; the three existing metrics drive |
| Eval dashboard / JSONL rendering | RFC-005 Cycle D |
| Statistical significance testing (t-tests, CIs) | n=3 runs cannot support it honestly; range-based rule instead (AD-231) |
| Actual-spend (billed-dollar) metering | The cap is enforced against *modeled* unit costs (AD-234, honoring AD-230); reconciling against billed spend stays a runbook step in the spend report |
| New provider SDKs or generation adapters | ADR-0019/0020 lock providers; both arms run through the existing Anthropic adapter |
| Nightly workflow changes | The study is operator-triggered only; the nightly tier is untouched |

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
|---|---|---|---|
| Noise rule for "strictly better/worse" per metric | Non-overlapping per-run ranges: better iff min(opus runs) > max(sonnet runs); worse iff max(opus) < min(sonnet); any overlap = tie | Honest for n=3; a 0.005 gap inside a wider spread reads as tie → stay, which is the RFC's "leave unchanged on ambiguity" | auto (AD-231) |
| What varies per run | Full generate+judge pass per arm per run (not judge-only re-scoring) | The generation verdict's noise includes generation sampling; judge-only variance was characterized by Cycle B | auto (AD-232) |
| Evidence handling | Evidence fixed per case across arms and runs (golden: committed snapshot evidence; silver: resolved once per study) | Isolates generation quality from retrieval; identical inputs across arms is the point of an A/B | auto (AD-233) |
| Budget ceiling | $10 default, enforced in code: `LEARNY_EVAL_BUDGET_USD` settings field; the runner stops before any unit whose modeled cost would exceed the ceiling (clean, resumable stop). Pre-flight estimate + spend report stay in the research doc per the runbook | AD-230 explicitly deferred `LEARNY_EVAL_BUDGET_USD` code enforcement to this cycle; ceiling value carried from Cycle B (OQ3) | auto (AD-234) |
| Run count | Exactly 3 runs per arm | Meets the RFC's ≥3 floor at bounded cost; more runs add spend without changing the range-based rule's honesty | auto (AD-235) |
| Verdict tier | Silver drives, golden reported (existing AD-166 bar unchanged) | RFC says "hold the existing bar"; silver has no expected-not-found cases so discipline is incomparable there and the verdict decides on faithfulness + relevancy | auto (AD-236) |
| Move consequence includes threshold re-derivation | If the verdict is move, `FAITHFULNESS_MIN`/`RELEVANCY_MIN` are re-derived from the study's opus-arm golden runs per the runbook rule | Cycle B pinned thresholds to sonnet generations; judge.py says re-derive whenever the generation model changes | auto (AD-237) |

**Open questions:** none — all resolved or logged above.

## User Stories

### P1: Noise-aware multi-run verdict (pure layer) ⭐ MVP

**User Story**: As the operator, I want the stay/move verdict computed from per-run spreads instead of one observation, so that a sub-noise gap can never flip the product default.

**Acceptance Criteria**:

1. WHEN per-run `ModelAggregate`s for both arms are aggregated THEN the system SHALL expose, per metric per tier per arm: the per-run values, their mean, min, max, and range, with runs whose metric is `None` excluded and an all-`None` metric visibly empty (never 0.0).
2. WHEN the multi-run verdict is computed THEN the system SHALL return `"move"` iff, over the three silver metrics (faithfulness, relevancy, not-found discipline), at least 2 are strictly better (min of opus's runs > max of sonnet's runs) and none is worse (max of opus < min of sonnet), else `"stay"`.
3. WHEN a metric's per-run ranges overlap at all (including identical constant values on both sides) THEN the system SHALL count it neither better nor worse.
4. WHEN a metric is `None`-valued on either side for every run (e.g. silver discipline) THEN the system SHALL treat it as incomparable — never better, never worse.
5. WHEN fewer than 2 metrics are better, or any is worse, or either arm has zero runs THEN the verdict SHALL be `"stay"`.

**Independent Test**: pure unit tests over hand-built per-run aggregates covering every boundary (overlap, touch, disjoint, ceiling-flat, all-None, empty arms).

---

### P1: Committed, checkpointed, resumable study runner ⭐ MVP

**User Story**: As the operator, I want the study driver committed with per-unit checkpointing, so that a mid-study failure (credit exhaustion, provider outage) costs only the unfinished unit and a re-invocation finishes the remainder without re-paying for completed work.

**Acceptance Criteria**:

1. WHEN the study runs THEN the runner SHALL iterate units of (tier, case, arm, run_index) and append exactly one JSONL line per unit immediately after that unit is scored — never buffering the whole study in memory before writing.
2. WHEN a study line is written THEN it SHALL carry the full `ab.py` input contract (`case_id`, `generation_model`, `faithfulness`, `relevancy`, `citation_valid`, `tier`, `status`, `found`, `expected_not_found`) plus `run_index`, `judge_model`, `prompt_hash`, `git_sha`, `ts`; declined units (`found=False`) SHALL make no judge calls and carry null scores (ADR-028).
3. WHEN the runner is re-invoked against an existing study artifact THEN units already recorded with status `ok`, `skipped`, or `broken` SHALL be skipped without any generation or judge call, and units recorded as `error` SHALL be re-attempted.
4. WHEN a resume is attempted against lines whose `prompt_hash` or `judge_model` differs from the current configuration THEN the runner SHALL refuse to proceed rather than mix incomparable lines in one artifact.
5. WHEN a unit's provider call fails THEN the runner SHALL record that unit with status `error` (no scores) and continue with the next unit.
6. WHEN the study writes artifacts THEN golden-tier lines SHALL go to a tracked file under `evals/results/` and silver-tier lines to a git-ignored file under `evals/silver/results/`, preserving the silver hygiene invariant (no real-book text tracked).
7. WHEN the nightly `-m "live and eval"` selection runs THEN the study entrypoint SHALL NOT be collected into it — the study runs only by explicit opt-in.
8. WHEN the runner processes a unit THEN it SHALL emit a progress line (unit identity + status) so a live run is observable while it spends.
9. WHEN the next unit's modeled cost would push the modeled running spend past the budget ceiling (`LEARNY_EVAL_BUDGET_USD`, default 10.0) THEN the runner SHALL stop before that unit — a clean checkpoint the resume path can finish later — and report modeled spend vs ceiling; already-recorded units never re-bill on resume (their modeled cost counts as spent only once, at scoring time).

**Independent Test**: fake-adapter tests exercising checkpoint append, resume skip/re-attempt, mismatch refusal, decline handling, error continuation, and artifact split — no network, no DB.

---

### P1: The live study, verdict, and consequence ⭐ MVP

**User Story**: As the operator, I want the de-noised study actually executed and its verdict applied, so that the generation default question is closed on multi-run evidence instead of staying open.

**Acceptance Criteria**:

1. WHEN the live study executes THEN it SHALL cover both arms (`claude-sonnet-5`, `claude-opus-4-8`) × 3 runs over the golden tier (the committed replay cases with snapshot evidence) and the silver tier (locally resolved cases), all judged by `claude-opus-4-8`.
2. WHEN the study is about to spend THEN a modeled cost estimate SHALL be recorded first and the study SHALL proceed only under the $10 ceiling; the research doc SHALL carry a spend report (ceiling, estimate, actual, ratio) per the runbook protocol.
3. WHEN the study completes THEN a research doc under `docs/research/<run-date>/` SHALL record: the pre-registered decision rule (fixed before the runs), the run manifest, per-metric variance tables for both tiers and arms, the verdict as the literal output of the pure verdict function, the spend report, and an honest-limitations section.
4. WHEN the verdict is `stay` THEN no config or threshold SHALL change and the doc SHALL record the de-noised STAY as closing the single-run verdict.
5. WHEN the verdict is `move` THEN `generation_model`'s default SHALL flip to `claude-opus-4-8` (config + pin tests + `.env.example`) AND the gate thresholds SHALL be re-derived from the study's opus-arm golden runs per the runbook rule, committed together with the flip.

**Independent Test**: the research doc exists with all required sections; the verdict line quotes the pure function's output over the study artifact's lines; config state matches the verdict.

---

## Edge Cases

- WHEN both arms score a metric flat at ceiling (e.g. faithfulness 1.0 in every run) THEN ranges are identical points that overlap → tie for that metric (never "better").
- WHEN an entire run yields only `error` lines THEN that run contributes no metric values; the spread over remaining runs still reports, and an arm with zero metric-bearing runs makes the verdict `"stay"`.
- WHEN resume is invoked on a fully complete artifact THEN the runner SHALL make zero provider calls and report the study complete.
- WHEN the silver tier is unavailable (cases file absent / DB down) THEN the runner SHALL surface the skip reason and the study SHALL be reported golden-only — silver-driving metrics absent → verdict `"stay"` by incomparability, recorded as such rather than silently passing.
- WHEN a golden not-found case is answered (discipline miss) or declined THEN `found`/`expected_not_found` on the line SHALL make the existing `ab.py` discipline metric compute correctly per tier.

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
|---|---|---|---|
| DENOISE-01 | P1 pure: per-metric spread aggregation | Design | Pending |
| DENOISE-02 | P1 pure: range-based multi-run verdict (move rule) | Design | Pending |
| DENOISE-03 | P1 pure: overlap/incomparable/degenerate → stay | Design | Pending |
| DENOISE-04 | P1 runner: per-unit checkpoint append + line schema | Design | Pending |
| DENOISE-05 | P1 runner: resume skips completed, re-attempts errors | Design | Pending |
| DENOISE-06 | P1 runner: prompt_hash/judge_model mismatch refusal | Design | Pending |
| DENOISE-07 | P1 runner: error continuation + decline handling (ADR-028) | Design | Pending |
| DENOISE-08 | P1 runner: artifact split (tracked golden / ignored silver) + hygiene | Design | Pending |
| DENOISE-09 | P1 runner: opt-in only, never nightly-collected; progress lines | Design | Pending |
| DENOISE-10 | P1 live: 2 arms × 3 runs × both tiers under opus judge | Design | Pending |
| DENOISE-11 | P1 live: budget protocol (estimate, $10 cap, spend report) | Design | Pending |
| DENOISE-12 | P1 live: research doc with pre-registered rule + variance tables + literal verdict | Design | Pending |
| DENOISE-13 | P1 live: verdict consequence (stay = no change; move = flip + threshold re-derivation) | Design | Pending |
| DENOISE-14 | P1 runner: modeled-cost budget stop (`LEARNY_EVAL_BUDGET_USD`, AD-230 closure) | Design | Pending |

**Coverage:** 14 total, 0 mapped to tasks (pending), 0 unmapped.

## Success Criteria

- [ ] The generation default question is closed on ≥3-run evidence: the research doc's verdict is the pure function's literal output and the config state matches it.
- [ ] A deliberately interrupted fake-adapter study resumes to completion with zero repeated provider calls for completed units (proven by test).
- [ ] Actual spend ≤ $10 with the estimate-vs-actual ratio recorded.
