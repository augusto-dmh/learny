# Context — v3-eval-maturity auto-decisions (ship-cycle protocol)

- **AD-115 — Bump default generation model to `claude-sonnet-5` in this cycle.**
  Options: (a) bump the settings default (chosen) — eval snapshots, nightly
  gate, and fresh deploys measure the model the product actually runs (the
  author's stack runs Sonnet 5 via env since 2026-07-18); why-not: touches
  5 test files asserting the old default. (b) Set the model only in `eval.yml`
  — smaller diff; why-not: leaves the committed default measuring a
  previous-generation model and diverges eval from deploy defaults. (c) Record
  baselines on the old default — zero code churn; why-not: calibrates
  thresholds against a model the product no longer uses, guaranteeing a
  recalibration cycle immediately after. Provider unchanged; ADR-0020
  explicitly keeps the model name in config, so no new decision record needed.
- **AD-116 — Calibration derivation rule: mean of 3 fresh keyed seed runs minus
  a safety margin (faithfulness −0.10, relevancy −0.5), floored at the old
  literature defaults only if observations land below them.** Options:
  (a) mean − margin (chosen) — simple, documented, reproducible on model swap;
  why-not: 3 runs is a small sample, margins are judgment. (b) Min of observed
  runs — tighter to evidence; why-not: N=3 min is noisy and brittle for a
  nightly gate. (c) Wait for 2 weeks of nightly history — statistically nicer;
  why-not: re-parks the cycle the RFC explicitly said to unpark via fresh runs.
- **AD-117 — Calibration doc lives at `docs/ops/eval-calibration.md`** beside
  the other operational runbooks (backups, monitoring, deploy). Option
  `evals/README.md` rejected: evals/ holds result data, not procedures; ops/
  is where a future operator will look.

- **AD-116 amendment (during T3/T4).** The floor clause ("floored at the old
  literature defaults") is dropped: observed relevancy is a stable 3 on the
  single-case judge smoke, below the 4.0 literature default — flooring would
  fail every nightly by construction. The gate constants derive from observed
  baselines only (regression detection); the literature values move to the
  calibration doc as aspirational context. Also recorded: the judge tier is
  currently one synthetic smoke case — the doc must flag that widening the
  tier to real pipeline cases requires re-derivation, and that the
  answerability tier showed 1/18 judge-variance flake (not gated, noted).

## Deferred Ideas

- Eval-deepening follow-up (silver set over real books, rubric anchoring, judge
  and generation A/Bs vs Opus 4.8) — recorded as a roadmap candidate
  (`.specs/project/ROADMAP.md` → Recorded candidates), scheduled after RFC-004
  Cycle A. Product generation default deliberately stays `claude-sonnet-5`
  until the A/B research doc says otherwise.
