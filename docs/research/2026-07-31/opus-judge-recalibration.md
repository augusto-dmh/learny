# Opus judge recalibration — flip decision (RFC-005 Cycle B)

**Date**: 2026-07-31 · **Decision**: **FLIP** — `LEARNY_JUDGE_MODEL` default
moves `claude-haiku-4-5` → `claude-opus-4-8` · **Evidence**:
`evals/results/2026-07-31-059cb763.jsonl` (36 lines, three seeded runs)

## Context

The 2026-07-21 judge A/B (`docs/research/2026-07-21/eval-deepening-ab.md`)
returned `switch` to Opus but was deferred on two conditions: (1) settle the
decline-faithfulness semantics — Opus scored declined answers 0.0 where the
gate's convention assumed a vacuous 1.0 — and (2) re-derive the gate baselines
under Opus per the calibration runbook. This cycle discharged both: ADR-028
excludes declines from all aggregate means (they are never judge-called; their
line scores are `null`; not-found discipline carries them), and the nightly
judged tier was widened to the 12 committed replay snapshots so the gate runs
on the distribution its thresholds derive from.

## Method

Three seeded runs of the live judge tier
(`tests/test_eval_judge.py::test_live_judge_scores_replay_snapshots`) with
`LEARNY_JUDGE_MODEL=claude-opus-4-8`, gate off, generation frozen at the
committed snapshots (`claude-sonnet-5`-recorded). `prompt_hash`
`211d9d8c…` verified against the runbook pin before the first paid call —
the rubric had not drifted. Each run: 12 cases, 9 answered → 18 judge calls,
3 declines → 0 calls (ADR-028).

## Results (answered-only means, 9 cases per run)

| Run | mean faithfulness | mean relevancy | citations |
|---|---|---|---|
| 1 | 1.0000 | 3.5556 | all valid |
| 2 | 1.0000 | 3.4444 | all valid |
| 3 | 1.0000 | 3.6667 | all valid |
| **grand mean** | **1.0000** | **3.5556** | — |
| range | 0.0000 | 0.2222 | — |

The decline-faithfulness clash is fully resolved by ADR-028: with declines
excluded, Opus faithfulness is a flat 1.0 across all 27 scored answered cases —
the RFC-005 assumption ("excluding declines restores an Opus mean above the
0.90 floor") held at the ceiling, not merely above the floor. Opus relevancy
runs ~0.25 above the anchored Haiku baseline (3.556 vs ~3.3) with comparable
stability (range 0.22 vs Haiku's historical 0.22 over 3.44/3.22/3.22).

## Derivation (runbook rule: mean − margin)

- `FAITHFULNESS_MIN` = 1.0 − 0.10 = **0.90** (unchanged)
- `RELEVANCY_MIN` = 3.556 − 0.5 = 3.056 → **3.1** (one decimal; was 2.8)

## Flip-or-stay rule evaluation (spec RECAL-08, fixed before the runs)

Default FLIP unless any trigger fires:

| Trigger | Threshold | Observed | Fired? |
|---|---|---|---|
| Instability | faithfulness range > 0.10 or relevancy range > 0.5 | 0.00 / 0.22 | No |
| Degeneracy | derived FAITHFULNESS_MIN < 0.50 or RELEVANCY_MIN ≤ 1.0 | 0.90 / 3.1 | No |
| Budget | projected nightly Opus judge cost > $0.50/night | ~$0.10 (see below) | No |

No trigger fired → **FLIP**. The twice-deferred switch closes.

## Spend report (runbook budget protocol)

- Ceiling: $10 for the cycle (operator, 2026-07-31). Pre-flight estimate:
  54 calls ≤ $2.20 (conservative).
- Actual: 54 Opus calls; measured input ≈ 10.7k tokens/run ≈ 32k total;
  outputs are small JSON (claims list / one integer). Realistic actual ≈
  **$0.31**; even pricing every call at the full 1024-token output cap bounds
  the three runs at ~$1.55. Estimate-vs-actual: estimate was ~7× actual —
  next pre-flight can trust the size-based model above.
- Projected nightly: 18 calls ≈ $0.10 realistic; $0.51 only if every call
  maxed its output cap (observed outputs are ~10–20× smaller).

## Consequences

- Constants re-pinned (`FAITHFULNESS_MIN = 0.90`, `RELEVANCY_MIN = 3.1`) in the
  same commit as the derivation comment, pin test, and runbook table.
- The quiz answerability tier also reads `LEARNY_JUDGE_MODEL` and follows the
  flip. It is report-only (never gated, AD-080), its historical 1/18
  judge-variance tolerance is unchanged, and its nightly cost on Opus stays
  small (short prompts, ~cents).
- The committed snapshots predate the v6 answer-format change (inline `[^n]`
  markers, 4096-token budget, thinking). Recorded in the runbook: the next
  snapshot re-record must trigger a full threshold re-derivation.
- Haiku remains one env var away (`LEARNY_JUDGE_MODEL=claude-haiku-4-5`) for
  ad-hoc comparison; its baselines are preserved in the runbook history.
