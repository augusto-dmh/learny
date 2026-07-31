# v5-opus-judge-recalibration Specification

RFC-005 Cycle B — Opus judge recalibration + the decline-faithfulness contract.

## Problem Statement

The nightly judge gate's aggregate semantics contradict their own derivation: `_assert_aggregates` averages faithfulness and relevancy over **all** lines, while the pinned thresholds (`FAITHFULNESS_MIN = 0.90`, `RELEVANCY_MIN = 2.8`) were derived over the **9 answered** of 12 replay snapshots. The clash is latent only because the nightly judged tier is a single answered synthetic case — which is itself drift: the gate never runs on the distribution its thresholds came from. The 2026-07-21 A/B study returned `switch` to `claude-opus-4-8` but was deferred on two conditions: settle the decline-faithfulness semantics (Opus scores declines 0.0, contradicting the vacuous-1.0 convention), and re-derive Opus baselines per the calibration runbook. This cycle discharges both conditions and closes the twice-deferred judge switch with a decidable flip-or-stay.

## Goals

- [ ] ADR-0028 accepted: one decline-semantics convention, enforced by both the nightly gate and the A/B study aggregate.
- [ ] Nightly judged tier = the 12 committed replay snapshots (gate runs on the distribution the thresholds derive from).
- [ ] ≥3 live `claude-opus-4-8` judge runs over that tier; thresholds derived per the runbook rule; evidence committed.
- [ ] Flip-or-stay decision recorded with evidence, applying the pre-stated decision rule (RECAL-08).
- [ ] Total live spend ≤ $10 (operator cap), estimated pre-flight and reported actual.

## Out of Scope

| Feature | Reason |
|---|---|
| Generation A/B re-run (Sonnet vs Opus) | RFC-005 Cycle C — depends on this cycle's settled judge |
| Budget/checkpoint/resume *code* | RFC-005 Cycle C deliverable; this cycle follows the runbook's procedural protocol (per-case JSONL append is the existing checkpoint) |
| Eval dashboard | RFC-005 Cycle D |
| Rubric/prompt edits | Would change `prompt_hash` and force a second recalibration; prompts frozen this cycle |
| Re-recording replay snapshots | Same-inputs comparison vs the Haiku-derived baselines is the clean experiment; post-v6-E answer-format drift is a recorded follow-up (see Assumptions) |
| Silver-tier gating | Silver stays advisory evidence (AD-164) |
| New provider SDKs | ADR-0019/0020 locked; Opus runs use the existing Anthropic adapter path |

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
|---|---|---|---|
| Calibration inputs | The 12 committed snapshots as-is (no re-record) | Haiku thresholds were derived on them; judging the judge requires identical inputs. v6-E changed live answer format (inline `[^n]` markers, 4096 tokens) — snapshot re-record is a follow-up flagged in the runbook, not a confound to add mid-experiment | auto (AD-231) |
| Decline treatment in aggregates | Answered-only means for faithfulness AND relevancy, in gate and study | Matches the thresholds' actual derivation and the study's relevancy precedent; removes the judge-model-dependent vacuous-1.0 vs 0.0 ambiguity from aggregates entirely | auto (AD-230) |
| Judge calls on declined cases | Skipped; scores recorded as `null` | Asking a judge to score an empty answer is spend for a value the aggregate discards; the per-case vacuous-1.0 convention survives at `FaithfulnessResult` level for callers that do score | auto (AD-232) |
| Not-found discipline in the nightly gate | Not added; stays a study-level metric (ab.py) | On a frozen replay tier discipline is definitionally constant — zero information; gating it awaits live-generation nightly cases (documented in ADR-0028) | auto (AD-230) |
| Seed-run invocation | Direct file target `pytest tests/test_eval_judge.py -m "live and eval"` | The bare `-m "live and eval"` selection also triggers the paid silver runner and retrieval arm — a cost trap | auto |
| Budget ceiling | $10 for all live runs this cycle | Operator decision at Cycle B start (RFC-005 OQ-3); estimate ~$1 | user 2026-07-31 |

**Open questions:** none — all resolved or logged above.

## User Stories

### P1: One decline-semantics convention (ADR-0028) ⭐ MVP

**User Story**: As the eval-stack owner, I want a single documented convention for declined answers in judge aggregates so that a judge-model swap can never silently change what the gate measures.

**Acceptance Criteria**:

1. WHEN ADR-0028 is read THEN it SHALL document: answered-only aggregate means (faithfulness + relevancy) in the nightly gate and the A/B study; the per-case vacuous-1.0 convention retained at `FaithfulnessResult` level; not-found discipline as the decline-carrying metric at study level; and the all-declined edge (threshold asserts skip, citation invariant remains). Status SHALL be Accepted, dated before the baseline re-derivation commit.
2. WHEN `_assert_aggregates` receives lines with a falsy `found` THEN the faithfulness and relevancy means SHALL be computed over `found` lines only, and the `citation_valid` invariant SHALL still be asserted over ALL lines.
3. WHEN every line in a gated run is a decline THEN the threshold asserts SHALL be skipped (no mean exists) and the citation invariant SHALL still run.
4. WHEN `_tier_aggregate` (ab.py) computes `mean_faithfulness` THEN it SHALL average answered lines only, mirroring its existing `mean_relevancy` semantics.
5. WHEN `run_eval` processes an `EvalInput` with `found=False` THEN it SHALL make no judge calls for that case and SHALL write its line with `faithfulness: null`, `relevancy: null`, `found: false`.
6. WHEN `run_eval` processes an `EvalInput` without an explicit `found` THEN the line SHALL carry `found: true` and be judged as today (backward compatibility).

**Independent Test**: unit suite over `_assert_aggregates`/`run_eval`/`_tier_aggregate` with mixed answered/declined fakes; no network.

### P1: The gate runs on its own baseline distribution ⭐ MVP

**User Story**: As the eval-stack owner, I want the nightly judged tier to be the 12 committed replay snapshots so that the gate and its thresholds can never drift apart, and so re-derivation is a committed, repeatable run instead of ad-hoc scripting.

**Acceptance Criteria**:

1. WHEN the nightly selection `-m "live and eval"` runs with a key THEN the judge tier SHALL build one `EvalInput` per committed snapshot (12 today) via `load_snapshots()`, carrying each snapshot's `answer.found` and citation validity, and score them through `run_eval` (max_cases still applies).
2. WHEN the same selection runs without `LEARNY_ANTHROPIC_API_KEY` THEN the tier SHALL skip (CI stays offline/green).
3. WHEN the offline suite (`make test-backend`, no keys) runs THEN it SHALL remain green with no live calls.

**Independent Test**: the live test is skip-guarded; its input-construction logic is unit-testable offline (snapshot → EvalInput mapping, found flags on the 3 `notfound-*` cases).

### P1: Opus baselines re-derived and pinned ⭐ MVP

**User Story**: As the eval-stack owner, I want ≥3 seeded Opus judge runs over the tier with thresholds derived by the documented rule so that a flip decision rests on distribution evidence, not a single observation.

**Acceptance Criteria**:

1. WHEN the seed runs execute THEN there SHALL be ≥3 completed `claude-opus-4-8` runs (via `LEARNY_JUDGE_MODEL` env override) over all 12 snapshots, with per-run JSONL evidence under `evals/results/` and per-run answered-only means recorded in the research doc.
2. WHEN thresholds are derived THEN new values SHALL equal (mean of the ≥3 run means) − margin (faithfulness −0.10 rounded to 2 decimals, relevancy −0.5 rounded to 1 decimal) per AD-116 as amended (no literature floor).
3. WHEN constants change THEN `FAITHFULNESS_MIN`/`RELEVANCY_MIN`, the derivation comment in judge.py, the pinning test, and the runbook baseline table SHALL change in the same commit.
4. WHEN the first paid call is about to run THEN a pre-flight cost estimate SHALL exist and be under the $10 ceiling; WHEN the runs finish THEN actual spend (call counts × pricing) SHALL be reported against the estimate in the research doc.

**Independent Test**: derivation arithmetic is reproducible from the committed JSONL evidence; pinning test enforces constants.

### P1: Flip-or-stay, decided and recorded ⭐ MVP

**User Story**: As the product owner, I want the judge-model decision made by a pre-stated rule and recorded with evidence so that the twice-deferred switch closes decidably either way.

**Acceptance Criteria**:

1. The decision rule SHALL be: **FLIP** to `claude-opus-4-8` unless any of: (a) instability — across the seed runs, the range of per-run answered-only faithfulness means > 0.10 or relevancy means > 0.5 (spread exceeds the safety margins); (b) degeneracy — derived `FAITHFULNESS_MIN` < 0.50 or `RELEVANCY_MIN` ≤ 1.0 (gate cannot discriminate); (c) budget — projected nightly Opus cost > $0.50/night at current tier size. Any trigger ⇒ **STAY** on `claude-haiku-4-5` with existing constants revalidated under ADR-0028 semantics.
2. WHEN the decision is FLIP THEN `settings.judge_model` default SHALL become `claude-opus-4-8` with config test pins updated, committed together with the Opus-derived constants.
3. WHEN the decision is STAY THEN the config default and Haiku constants SHALL remain, with the triggering condition documented.
4. WHEN the cycle completes THEN `docs/research/2026-07-31/opus-judge-recalibration.md` SHALL record: per-run aggregates, derivation arithmetic, rule evaluation, decision, spend report; and the RFC-005 Cycle B row (ROADMAP + RFC) SHALL be updated.

**Independent Test**: rule evaluation is mechanically checkable from the recorded per-run means.

## Edge Cases

- WHEN `run_eval` receives zero inputs THEN behavior is unchanged (silent no-op, no gate failure).
- WHEN a seed run dies mid-pass (credits/network) THEN completed cases persist in the append-only JSONL (existing checkpoint) and the run is resumed/repeated without regenerating committed evidence; partial runs are excluded from derivation and noted.
- WHEN `prompt_hash` at run time differs from the runbook's pinned value THEN derivation MUST NOT proceed (rubric drifted — the experiment is invalid).

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
|---|---|---|---|
| RECAL-01 | ADR-0028 document | 1 | Pending |
| RECAL-02 | Gate answered-only means + all-declined edge (AC 2,3) | 1 | Pending |
| RECAL-03 | `EvalInput.found` + decline skip + line schema (AC 5,6) | 1 | Pending |
| RECAL-04 | Study aggregate unification (AC 4) | 1 | Pending |
| RECAL-05 | Nightly tier = snapshots + offline/keyless behavior | 1 | Pending |
| RECAL-06 | ≥3 seeded Opus runs + evidence + budget protocol | 2 | Pending |
| RECAL-07 | Threshold derivation + same-commit pinning | 2 | Pending |
| RECAL-08 | Flip-or-stay rule applied + config outcome | 2 | Pending |
| RECAL-09 | Research doc + ROADMAP/RFC row updates | 2 | Pending |
| RECAL-10 | Compliance: no new SDK, prompts frozen, offline suite green | 1–2 | Pending |

**Coverage:** 10 total, 10 mapped to phases, 0 unmapped.

## Success Criteria

- [ ] `make test-backend` green offline with no provider keys.
- [ ] Nightly gate enforces ADR-0028 semantics on the snapshot tier.
- [ ] Judge decision closed (flip or stay) with committed evidence; thresholds and tier can no longer drift apart.
- [ ] Actual live spend ≤ $10 and reported.
