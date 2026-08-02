# Generation A/B de-noised: Sonnet 5 vs Opus 4.8, three seeded runs

**Date** 2026-07-31 · **Decision** STAY on `claude-sonnet-5` (de-noised, partial third run) · **Evidence** `evals/results/2026-07-31-c2bf2375-generation-denoise.jsonl` (golden, tracked) + `evals/silver/results/2026-07-31-c2bf2375-generation-denoise.jsonl` (silver, git-ignored)

## Context

The 2026-07-21 generation A/B ran each arm once and produced STAY on a lone
0.005 silver-faithfulness gap — a single observation, recorded then as an
evidence limitation, alongside an uncommitted driver script. This study
re-asks the question with the machinery this cycle built: a committed,
checkpointed, budget-capped study runner (`backend/tests/eval/study.py`),
full generate+judge passes per arm per run, and a decision rule fixed before
any spend.

A first full pass of this study was **discarded**: a stale local env pin
(`LEARNY_JUDGE_MODEL=claude-haiku-4-5`, predating the judge flip) silently
judged all 144 units with Haiku. Independent verification caught it; the
entrypoint now hard-pins the judge (`STUDY_JUDGE_MODEL` in
`test_generation_study.py`, tied to the config default by an offline test)
and the mis-judged artifacts were removed. All evidence below is from the
re-run under the pinned `claude-opus-4-8` judge — every judged line records
that identity — with the anchored rubric (`prompt_hash` `211d9d8c…`, verified
unchanged pre-spend).

## Pre-registered decision rule (fixed before the runs)

`denoised_generation_verdict` (`app/eval/ab.py`): over the three silver-tier
metrics — mean faithfulness, mean relevancy, not-found discipline — a metric
counts as **better** for Opus only when the arms' per-run ranges are disjoint
in Opus's favor (min of Opus's runs > max of Sonnet's), **worse**
symmetrically, and any overlap — including identical constant values — is a
tie. MOVE requires ≥2 better and 0 worse; everything else is STAY. This holds
the recorded single-run bar (silver drives, golden reported) while making a
sub-noise gap unable to move the default.

## Method and coverage

One invocation of the committed entrypoint plus one resume attempt:

```
uv run pytest tests/eval/test_generation_study.py --generation-study -q -s
```

144 planned units = (12 golden replay cases + 12 silver cases) × 2 arms
(`claude-sonnet-5`, `claude-opus-4-8`) × 3 runs. Golden generations ran over
frozen committed-snapshot evidence (identical inputs across arms and runs);
silver resolved once against the local corpus, retrieval memoized per case.
Declines were never judge-called.

**Coverage: 137 of 144 units scored.** The account's API credit balance ran
out during the third run's silver pass; the runner recorded the last 7 units
(4 silver cases: 3 Sonnet-arm, 4 Opus-arm) as visible `error` lines and the
operator elected to halt spend rather than top up — a recorded deviation from
the planned three *complete* runs. Runs 1–2 are complete on both tiers and
both arms (96/96); run 3 is complete on golden (24/24) and 17/24 on silver.
The checkpointed artifacts resume exactly where they stopped: finishing the
7 units is one re-invocation, ~$0.45 modeled, whenever credits exist.

Every scored line's citation invariant held (citation-valid rate 1.0 across
all arm×tier×run combinations).

## Results — per-metric variance (opus-judged)

Golden tier (12 cases: 9 answerable + 3 expected-not-found; answered-only means):

| Metric | Arm | run1 | run2 | run3 | mean | range |
|---|---|---|---|---|---|---|
| faithfulness | sonnet-5 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| faithfulness | opus-4-8 | 1.0 | 0.9688 | 1.0 | 0.990 | 0.031 |
| relevancy | sonnet-5 | 3.667 | 3.667 | 3.444 | 3.593 | 0.222 |
| relevancy | opus-4-8 | 4.125 | 3.875 | 3.556 | 3.852 | 0.569 |
| not-found discipline | sonnet-5 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| not-found discipline | opus-4-8 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |

Silver tier (12 real-book cases, all authored answerable — discipline is
structurally absent and incomparable; run3 covers 9 Sonnet / 8 Opus cases):

| Metric | Arm | run1 | run2 | run3* | mean | range |
|---|---|---|---|---|---|---|
| faithfulness | sonnet-5 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| faithfulness | opus-4-8 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| relevancy | sonnet-5 | 4.917 | 4.917 | 4.889 | 4.907 | 0.028 |
| relevancy | opus-4-8 | 5.0 | 5.0 | 4.875 | 4.958 | 0.125 |

\* run3 silver is partial (credit halt); its means cover the scored cases.

## Rule evaluation

Over all three runs (partial run3 included as recorded):

| Silver metric | Sonnet range | Opus range | Disjoint? | Counts as |
|---|---|---|---|---|
| mean faithfulness | [1.0, 1.0] | [1.0, 1.0] | No — identical at ceiling | tie |
| mean relevancy | [4.889, 4.917] | [4.875, 5.0] | No — ranges overlap | tie |
| not-found discipline | none | none | — | incomparable |

Better: 0 · Worse: 0 → **Verdict (`denoised_generation_verdict`): `stay`** —
the literal output of the pure function over the study artifacts, not a human
read of the numbers.

**Cross-check on the two complete runs only** (runs 1–2, 96/96 units, no
composition caveat): faithfulness identical at 1.0 (tie); relevancy disjoint
in Opus's favor (min 5.0 > max 4.917) — one metric better, zero worse, below
the ≥2 bar → **`stay`** again. The two views agree; the partial third run
does not change the outcome, it only widens Opus's relevancy range back into
overlap.

The 2026-07-21 single-run 0.005 silver-faithfulness gap did not reproduce
under the Opus judge at all — silver faithfulness is flat 1.0 on both arms in
every run. The one sub-ceiling faithfulness reading anywhere belongs to the
**Opus arm** (golden run2, 0.9688: one unsupported claim), and Opus also
declined one answerable golden case in each of runs 1–2 where Sonnet answered
9/9 in every run — small robustness signals consistent with STAY.

## Spend report (runbook budget protocol)

| Item | Value |
|---|---|
| Ceiling | $10 per study invocation chain (`LEARNY_EVAL_BUDGET_USD`, enforced in code by the runner) |
| Pre-flight modeled estimate | $8.64 (144 units; sonnet $0.05/unit, opus $0.07/unit incl. judge) |
| Modeled at halt | $9.07 (137 scored + error-unit re-attempt bookkeeping; no budget stop) |
| Discarded first pass | a full 144-unit study judged by the wrong model (env drift) — its spend is real and wasted; the judge pin and this doc's method note are the corrective |
| Actual | the account's remaining credit balance was exhausted mid-third-run; the provider console is the billed authority. Failed 400 attempts bill nothing |
| Remaining to complete | 7 units ≈ $0.45 modeled (pennies actual) via the resume path |

## Consequences

- Generation default **stays `claude-sonnet-5`** — third consecutive
  data-backed STAY, now multi-run and Opus-judged. The single-observation
  caveat on the 2026-07-21 verdict is closed on the two complete runs;
  the third run's silver tail is a recorded, cheaply-resumable gap.
- `FAITHFULNESS_MIN`/`RELEVANCY_MIN` are untouched: they pin the sonnet
  generation × opus judge distribution the nightly gate actually runs.
- The study runner is committed and reusable: any future re-ask is one
  `--generation-study` invocation. Artifacts recorded under a different judge
  or rubric are refused at load time, and the judge is pinned in code — the
  drift that wasted the first pass cannot recur.
- The eval account must hold credits for the nightly judged tier; the
  exhaustion that truncated this study will fail the nightly identically.

## Evidence quality and limitations (recorded honestly)

- **Run 3 silver is partial (17/24).** Operator halted spend on credit
  exhaustion; the deviation from three complete runs is recorded above and in
  the cycle's planning artifacts. The complete-runs cross-check reaches the
  same verdict, which bounds the damage, but the pre-registered rule was
  evaluated on a partial third run and this doc says so plainly.
- **Ceiling effects dominate.** Faithfulness is at 1.0 nearly everywhere and
  silver relevancy sits at 4.87–5.0; disjoint-range wins are nearly
  impossible at ceiling, so the bar effectively asks "is Opus visibly better
  than a near-perfect Sonnet?" If a future re-ask should discriminate,
  harder silver cases are the lever, not more runs.
- **The Opus arm's single disjoint edge** (silver relevancy on complete runs,
  5.0 vs 4.917 — about 0.08 on a 5-point scale at ceiling) is real but below
  the ≥2-metric bar by design; a one-metric sliver at ceiling is exactly what
  the rule exists to not act on.
- **Golden prompt-title nuance.** Snapshot evidence stores no `section_path`,
  so golden-arm documents were titled by anchor — identical across both arms
  (the comparison stays fair) but slightly different from production prompts.
  Silver, which drives the verdict, used full production retrieval.
- Judge sampling noise is visible off-ceiling (golden relevancy ranges 0.22
  Sonnet / 0.57 Opus); n=3 bounds what ranges can resolve, and the rule
  treats that honestly as ties.
