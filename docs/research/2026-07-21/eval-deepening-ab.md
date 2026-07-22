# Eval deepening: judge and generation A/B studies

Date: 2026-07-21 (studies run 2026-07-21/22 UTC). Anchored relevancy rubric,
`prompt_hash 211d9d8c8db49ac171a4ee398627023177fa76fa03697275c21eadfcc9928870`.
Embeddings `text-embedding-3-large@1536`. This document records two A/B studies
and the two product-default decisions they drive. All verdicts below are the
output of the pure decision functions in `backend/app/eval/ab.py`
(`generation_verdict`, `judge_verdict`), not a human read of the numbers.

## What was measured

- **Generation A/B**: `claude-sonnet-5` vs `claude-opus-4-8` answering an
  identical case set over identical per-case evidence — the 12 committed golden
  cases (evidence taken from the committed replay snapshots so both arms see the
  same passages) and 12 silver cases retrieved once from the real corpus and
  reused across both arms. Both arms' outputs are scored by the anchored judge.
- **Judge A/B**: `claude-haiku-4-5` (the current default, primary) vs
  `claude-opus-4-8` scoring the identical set of outputs — every generation-A/B
  output (48) plus the 12 committed replay snapshots (60 judged items), both
  judges, same anchored rubric.

The silver set is 12 hand-authored question→passage cases over 6 real books
(5 Portuguese, 7 English; all answerable by design), keyed by source checksum +
section anchor. The silver cases, snippets, and silver result lines are
git-ignored (copyrighted); only synthetic golden result lines are committed.

### Run manifest

| Item | Value |
|---|---|
| Generation arms | claude-sonnet-5, claude-opus-4-8 |
| Judges | claude-haiku-4-5 (primary), claude-opus-4-8 |
| Cases | 12 golden + 12 silver (24), × 2 arms = 48 outputs; + 12 replay snapshots = 60 judged items |
| Generation calls | 48 (0 errors) |
| Judge scorings | 120 (60 items × 2 judges), 240 underlying calls (faithfulness + relevancy), 0 errors |
| prompt_hash | 211d9d8c… (anchored rubric) |
| Golden result lines | 72 → `evals/results/` (tracked; synthetic only) |
| Silver result lines | 48 → `evals/silver/results/` (git-ignored) |

Cost is **modeled, not metered** (token usage was not captured on the line).
Modeled from call counts at published per-token rates: generation ≈ $1.5
(24 Sonnet + 24 Opus), Haiku judge ≈ $0.3 (120 calls), Opus judge ≈ $4.0
(120 calls, dominated by faithfulness over large silver evidence) — clean-run
total ≈ **$5.8**. An earlier full attempt died mid-judge on credit exhaustion
(all 48 generations + ~37 judge scorings landed before 400s); that partial
dataset was discarded and is not part of these results. Single-run: every number
below is one observation per (case, arm, judge); treat ±1 relevancy point as
noise (see limitations).

## Generation A/B — Sonnet 5 vs Opus 4.8

Metrics from `aggregate()`, primary judge = Haiku, split golden/silver. Relevancy
means exclude declined answers (a decline scores relevancy 1 by construction);
faithfulness keeps declines (vacuously faithful). Silver has no not-found cases by
design, so silver not-found discipline is `None` (incomparable) and does not drive
the verdict.

| Metric | Sonnet golden | Opus golden | Sonnet silver | Opus silver |
|---|---|---|---|---|
| Mean faithfulness | 1.000 | 1.000 | **0.991** | 0.986 |
| Mean relevancy (answered) | 3.111 | 2.889 | 4.917 | **5.000** |
| Citation-valid rate | 1.000 | 1.000 | 1.000 | 1.000 |
| Not-found discipline | 1.000 (3/3) | 1.000 (3/3) | None | None |
| Scored / answered | 12 / 9 | 12 / 9 | 12 / 12 | 12 / 12 |

Cost per answer (modeled): Sonnet ≈ $0.02, Opus ≈ $0.04 — Opus is ~2× the
generation cost per answer here (short answers; the ratio widens with output
length).

**Verdict (`generation_verdict`): `stay` — the default remains `claude-sonnet-5`.**
On the silver tier that drives the decision (AD-166: move only if Opus is strictly
better on ≥2 of faithfulness/relevancy/not-found-discipline and worse on none),
Opus wins relevancy (5.000 vs 4.917) but **loses faithfulness** (0.986 vs 0.991),
and discipline is incomparable. Opus is worse on one metric, so the move condition
is not met. Both models cite validly everywhere and decline all three golden
not-found cases correctly; on real-book questions both are strong (silver relevancy
≈ 5 for both). There is no evidence that paying ~2× per answer buys better answers —
if anything Opus's marginally lower silver faithfulness is the only separation, and
it favors staying. `backend/app/core/config.py:generation_model` is **untouched**.

## Judge A/B — Haiku 4.5 vs Opus 4.8

Paired by (case_id, generation_model) over the 60 judged items (replay snapshots
carry a distinct `replay-` case id so they pair cleanly and never collide with the
fresh Sonnet golden outputs).

| Agreement metric | Value |
|---|---|
| Paired n | 60 |
| Exact relevancy agreement | 0.683 |
| Within-1 relevancy agreement | 0.967 |
| Gate flips (disagree on per-case pass/fail) | 8 |

Relevancy score distributions (all 60 items):

| Score | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| Haiku | 10 | 5 | 12 | 9 | 24 |
| Opus | 9 | 2 | 8 | 13 | 28 |

The judges agree exactly 68% of the time and within one point 97% of the time —
high agreement, and Opus skews about half a point more generous (more 4s and 5s,
fewer 2s and 3s). The disagreements are almost entirely ±1 at the middle of the
scale, e.g. a mechanism-omitting or partial answer that one judge puts at 3 and the
other at 4.

**Verdict (`judge_verdict`): `switch` — driven by the 8 gate flips.** Exact
(0.683 ≥ 0.60) and within-1 (0.967 ≥ 0.90) both clear their thresholds; the switch
is triggered solely by AD-165's "any gate-verdict flip" rule. Anatomy of the 8
flips:

- **6 are the relevancy gate (2.8) bisecting a 2-vs-3 disagreement**: the anchored
  `RELEVANCY_MIN = 2.8` sits between 2 and 3, so wherever Haiku says 2 and Opus says
  3+ (or vice-versa) on a marginal answer, the per-case pass/fail flips even though
  the raw scores differ by one point. These are boundary artifacts of where the gate
  is pinned, not deep disagreement about answer quality.
- **2 are faithfulness disagreements on one real silver answer**
  (`go-errors-are-values`, both arms): Haiku extracted one unsupported claim
  (ratio 0.833 / 0.889, below `FAITHFULNESS_MIN = 0.90` → fail) where Opus marked
  every claim supported (1.0 → pass). A genuine faithfulness disagreement on a
  borderline answer.

### A judge-behavior finding that bears on the switch

On the 9 declined/empty answers (the not-found golden cases across arms + replay),
**Opus scored faithfulness 0.0 while Haiku scored 1.0**. Haiku matches the
codebase's own convention — `FaithfulnessResult.supported_ratio` treats an answer
with no claims as vacuously faithful (1.0), exactly as the gate and the calibration
assume. Opus instead treats the decline itself as an unsupported assertion and
returns 0.0. These declines fail the gate on relevancy regardless (empty answer →
relevancy 1), so they produce **no** gate flips and do not change the verdict — but
they show Opus disagreeing with Learny's documented faithfulness semantics on
declines. That is a point in Haiku's favor, not Opus's.

## Decisions

1. **Generation default: stays `claude-sonnet-5`.** The silver tier does not show
   Opus strictly better; Opus's only separation is *lower* silver faithfulness, at
   ~2× the per-answer cost. `generation_verdict` = `stay`. No config change.

2. **Judge default: switch to `claude-opus-4-8`, per `judge_verdict`.** The function
   returns `switch` because 8 of 60 paired items flip the per-case gate, which
   AD-165 defines as material disagreement. Applied in its own commit
   (`backend/app/core/config.py:judge_model`, with the default-pin test updated in
   the same commit) so the merge gate can point at exactly that change and the
   maintainer can strip it before merge if they disagree — which the evidence here
   makes a live option, for three reasons stated plainly:
   - Headline agreement is high (exact 68%, within-1 97%); the switch rests entirely
     on gate flips, 6 of which are the `RELEVANCY_MIN = 2.8` boundary catching
     one-point disagreements, not quality divergence.
   - Opus mis-scores declines (faithfulness 0.0 vs the codebase's vacuous-1.0
     convention), so adopting Opus as the gating judge would require revisiting the
     not-found faithfulness semantics.
   - Opus judging is ~5× the per-score cost and the nightly gate pays it forever.

   An equally defensible reading of this same evidence is that the flips are a
   threshold-placement artifact and the cheap judge is fine — but that is a *human*
   override of a correctly-functioning verdict, so it is surfaced here for the
   merge decision rather than silently applied.

### Required follow-up if the judge switch is kept

The gate constants (`FAITHFULNESS_MIN = 0.90`, `RELEVANCY_MIN = 2.8`) were
calibrated against **Haiku** (docs/ops/eval-calibration.md, 2026-07-21). Opus's
relevancy distribution runs about half a point higher, so `RELEVANCY_MIN = 2.8`
remains a safe regression floor (it will not false-fail), but it is no longer the
calibrated baseline for the judge in force. If the switch survives merge,
re-derive the baselines against Opus per the calibration runbook and re-pin. This
cycle does not recalibrate (the calibration corpus and spend were scoped to Haiku).

## Evidence quality and limitations (recorded honestly)

- **Single run.** Every number is one observation per (case, arm, judge). Treat ±1
  relevancy as noise; the generation verdict rests on a 0.005 faithfulness gap on
  silver, which a second run could move. The verdict functions are deterministic
  given the lines; the lines are not.
- **Silver not-found is unmeasurable.** All silver cases are authored answerable, so
  silver not-found discipline is `None` and cannot enter the generation verdict —
  faithfulness and relevancy carry it. Not-found discipline is measured only on the
  3 synthetic golden cases (both arms: 3/3).
- **Golden is synthetic and both models ace it** (faithfulness 1.0, correct
  declines) — it discriminates little, which is exactly why the silver tier exists.
- **Judge A/B robustness.** Agreement is measured on the outputs that matter (the
  A/B set) plus the historical replay snapshots, one anchored rubric, no separate
  scoring pass (AD-167).

## Short attributed quotes (≤25 words each)

Illustrating that silver questions target specific real passages:

- "A seam is a place where you can alter behavior in your program without editing
  in that place." — Feathers, *Working Effectively with Legacy Code*, ch. 4.
- "An architecture quantum is an independently deployable artifact with high
  functional cohesion, high static coupling, and synchronous dynamic coupling." —
  Ford & Richards, *Software Architecture: The Hard Parts*, ch. 2.
- "As notas … são uma espécie de memória exterior, uma 'memória de papel'." —
  Sertillanges, *A Vida Intelectual*, "Como anotar".
- "A primeira disfunção é a falta de confiança entre os membros da equipe." —
  Lencioni, *Os 5 desafios das equipes*, "Uma visão geral do modelo".
