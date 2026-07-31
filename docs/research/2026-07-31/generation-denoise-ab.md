# Generation A/B de-noised: Sonnet 5 vs Opus 4.8, three seeded runs

**Date** 2026-07-31 · **Decision** STAY on `claude-sonnet-5` (de-noised) · **Evidence** `evals/results/2026-07-31-e9d9fbab-generation-denoise.jsonl` (golden, tracked) + `evals/silver/results/2026-07-31-e9d9fbab-generation-denoise.jsonl` (silver, git-ignored)

## Context

The 2026-07-21 generation A/B ran each arm once and produced STAY on a lone
0.005 silver-faithfulness gap — a single observation, recorded then as an
evidence limitation, alongside an uncommitted driver script. This study
re-asks the question with the machinery RFC-005 Cycle C built: a committed,
checkpointed, budget-capped study runner (`backend/tests/eval/study.py`),
three full generate+judge passes per arm, and a decision rule fixed before
any spend. The judge is the Cycle B-settled `claude-opus-4-8` with the
anchored rubric (`prompt_hash` `211d9d8c…`, verified unchanged pre-spend).

## Pre-registered decision rule (fixed before the runs)

`denoised_generation_verdict` (`app/eval/ab.py`): over the three silver-tier
metrics — mean faithfulness, mean relevancy, not-found discipline — a metric
counts as **better** for Opus only when the arms' per-run ranges are disjoint
in Opus's favor (min of Opus's three runs > max of Sonnet's three), **worse**
symmetrically, and any overlap — including identical constant values — is a
tie. MOVE requires ≥2 better and 0 worse; everything else is STAY. This holds
the recorded single-run bar (silver drives, golden reported) while making a
sub-noise gap unable to move the default. Recorded as AD-231/235/236.

## Method

One invocation of the committed entrypoint:

```
uv run pytest tests/eval/test_generation_study.py --generation-study -q -s
```

144 units = (12 golden replay cases + 12 silver cases) × 2 arms
(`claude-sonnet-5`, `claude-opus-4-8`) × 3 runs. Golden generations ran over
the frozen committed-snapshot evidence (identical inputs across arms and
runs); silver cases resolved once against the local corpus with retrieval
memoized per case. Declines were never judge-called (ADR-028). All 144 units
scored `ok` — zero errors, zero skips — in 21m26s. Every line's citation
invariant held (citation-valid rate 1.0 on all four arm×tier combinations).

## Results — per-metric variance

Golden tier (12 cases: 9 answerable + 3 expected-not-found; answered-only means):

| Metric | Arm | run0 | run1 | run2 | mean | range |
|---|---|---|---|---|---|---|
| faithfulness | sonnet-5 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| faithfulness | opus-4-8 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| relevancy | sonnet-5 | 3.444 | 3.444 | 3.444 | 3.444 | 0.0 |
| relevancy | opus-4-8 | 3.500 | 3.333 | 3.667 | 3.500 | 0.333 |
| not-found discipline | sonnet-5 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| not-found discipline | opus-4-8 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |

Silver tier (12 real-book cases, all authored answerable — discipline is
structurally `None` and incomparable):

| Metric | Arm | run0 | run1 | run2 | mean | range |
|---|---|---|---|---|---|---|
| faithfulness | sonnet-5 | 0.9951 | 0.9931 | 1.0 | 0.9961 | 0.0069 |
| faithfulness | opus-4-8 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| relevancy | sonnet-5 | 5.0 | 4.917 | 5.0 | 4.972 | 0.083 |
| relevancy | opus-4-8 | 4.917 | 5.0 | 4.833 | 4.917 | 0.167 |

## Rule evaluation

| Silver metric | Sonnet range | Opus range | Disjoint? | Counts as |
|---|---|---|---|---|
| mean faithfulness | [0.9931, 1.0] | [1.0, 1.0] | No — Opus's min equals Sonnet's max (strictly-greater required) | tie |
| mean relevancy | [4.917, 5.0] | [4.833, 5.0] | No — ranges overlap | tie |
| not-found discipline | none (no expected-not-found silver case) | none | — | incomparable |

Better: 0 · Worse: 0 → **Verdict (`denoised_generation_verdict`): `stay`** —
the literal output of the pure function over the study artifacts, not a human
read of the numbers.

The single-run study's 0.005 silver-faithfulness gap reproduced in direction
(Sonnet dipped below 1.0 in two of three runs; Opus stayed flat) but its
magnitude sits inside Sonnet's own cross-run range (0.0069) — precisely the
"one observation, indistinguishable from noise" case this cycle existed to
make undecidable-by-accident and decidable-by-rule. The de-noised verdict
confirms the original STAY on multi-run evidence: the generation default
remains `claude-sonnet-5`, and no config or threshold changes.

## Spend report (runbook budget protocol)

| Item | Value |
|---|---|
| Ceiling | $10 (`LEARNY_EVAL_BUDGET_USD` default, AD-234 — enforced in code by the runner) |
| Pre-flight modeled estimate | $8.64 (144 units; sonnet $0.05/unit, opus $0.07/unit incl. judge) |
| Modeled at completion | $8.64 (all units ran; no budget stop) |
| Billed authority | provider console; the model deliberately over-budgets (Cycle B's modeled-vs-actual ratio was ~3×, and declines skip judge calls), so billed spend is expected well below modeled |
| Projected re-run cost | same order; the runner resumes, so a partial failure re-bills only unfinished units |

## Consequences

- Generation default **stays `claude-sonnet-5`** — third consecutive
  data-backed STAY (2026-07-21 single-run, its merge-gate confirmation, and
  this de-noised study). The single-run caveat on the verdict is closed.
- `FAITHFULNESS_MIN`/`RELEVANCY_MIN` are untouched: they pin the sonnet
  generation × opus judge distribution the nightly gate actually runs.
- The study runner is now committed and reusable: any future re-ask (new
  Sonnet/Opus versions) is one `--generation-study` invocation plus this
  doc's template. Artifacts recorded under a different judge or rubric are
  refused at load time, so stale comparisons cannot mix in silently.
- RFC-005 Cycle D (eval dashboard) is unblocked — it depended on Cycle B's
  thresholds and this cycle's confirmed generation default.

## Evidence quality and limitations (recorded honestly)

- **Ceiling effects dominate.** Faithfulness is at 1.0 nearly everywhere and
  silver relevancy sits at 4.8–5.0 under the anchored rubric; disjoint-range
  wins are nearly impossible at ceiling. The bar therefore effectively asks
  "is Opus visibly better than a near-perfect Sonnet?" — no, and STAY is the
  right conservative reading. If a future model change is expected to matter,
  harder silver cases (authored to discriminate) are the lever, not more runs.
- **Golden prompt-title nuance.** Snapshot evidence stores no `section_path`,
  so golden-arm documents were titled by anchor rather than section title —
  identical across both arms (the comparison stays fair) but slightly
  different from production prompts. Silver, which drives the verdict, used
  full production retrieval.
- **One spurious Opus decline.** In run0, Opus declined one answerable golden
  case (8/9 answered; excluded from means per ADR-028, discipline unaffected
  as the case was not expected-not-found). Sonnet answered 9/9 in all runs —
  a small robustness point in Sonnet's favor, consistent with STAY.
- Judge sampling noise is visible where scores are off-ceiling (golden
  relevancy: Opus arm range 0.333 across runs; Sonnet arm happened to land
  identical means each run). n=3 bounds what the ranges can resolve; the
  pre-registered rule treats that honestly as ties.
