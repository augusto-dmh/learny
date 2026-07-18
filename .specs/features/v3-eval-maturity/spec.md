# Spec — v3-eval-maturity (RFC-003 Cycle B: real baselines + judge gate)

Scope source: RFC-003 Cycle B. The eval harness (judge, replay record path,
retrieval metric arms, nightly workflow) shipped in v2 Cycle C and is dormant:
no snapshots committed, thresholds are literature placeholders, the gate flag
is never set. This cycle activates it with real-provider baselines.

## Requirements

- **EVAL-01 — Generation replay snapshots recorded and committed.** Running the
  existing `--record-generation` path with the real Anthropic key produces one
  snapshot per case in `backend/tests/eval/cases.yaml` under
  `backend/tests/eval/snapshots/`; the committed snapshots make the replay
  tests execute offline (no skip) in CI.
  - AC1: `backend/tests/eval/snapshots/*.json` exists, one file per case id.
  - AC2: `uv run pytest tests/eval -q` (offline, no keys) runs the replay
    assertions against the committed snapshots with zero skips attributable to
    "no snapshots committed".
- **EVAL-02 — Generation model default aligned with the product.** The settings
  default and `.env.example` move from the previous-generation Sonnet to
  `claude-sonnet-5`, so snapshots, nightly evals, and fresh deployments measure
  the same model the product runs (provider unchanged per ADR-0020).
  - AC1: `Settings.generation_model` default is `claude-sonnet-5`; tests
    asserting the old default are updated to assert the spec-defined new one.
  - AC2: Offline suite green after the change.
- **EVAL-03 — Judge thresholds calibrated from observed keyed runs.** Three
  fresh keyed runs of the live eval suite seed the baseline; the gate constants
  in `app/eval/judge.py` are re-derived from observed aggregates (mean minus a
  documented safety margin, rounded to one decimal for relevancy / two for
  faithfulness), replacing the "provisional literature defaults" language with
  the derivation.
  - AC1: `FAITHFULNESS_MIN` / `RELEVANCY_MIN` carry a comment citing the
    observed run aggregates and derivation rule; the provisional wording is gone.
  - AC2: A gated replay of the observed runs passes (`LEARNY_EVAL_GATE=1`
    would not have failed any of the three seed runs).
- **EVAL-04 — Retrieval baseline observed and recorded.** The keyed OpenAI
  retrieval arm runs against the live DB; observed recall@1 / recall@5 / MRR
  are recorded in the calibration doc and the test thresholds are confirmed
  (or adjusted with rationale) against the observation.
  - AC1: Calibration doc lists the observed keyed metrics with model identity.
  - AC2: Keyed arm passes its thresholds on the observation run.
- **EVAL-05 — Nightly gate on; PRs stay offline.** `eval.yml` sets
  `LEARNY_EVAL_GATE=1` and supplies `LEARNY_OPENAI_API_KEY` (secret now exists)
  so the keyed retrieval arm joins the nightly run; `ci.yml` is untouched.
  - AC1: `eval.yml` contains the gate env and the OpenAI secret wiring with
    the same green-skip guard style used for the Anthropic secret.
  - AC2: `ci.yml` diff is empty this cycle.
- **EVAL-06 — Calibration method documented.** `docs/ops/eval-calibration.md`
  records: commands, cost, the derivation rule, observed baselines (generation
  + retrieval), and the re-derivation procedure on any model swap.
  - AC1: Doc exists, covers all five items, linked from `evals/README.md` or
    the ops docs index if one exists.
- **EVAL-07 — Rider.** RFC-004's status line flips to
  `Accepted (2026-07-18)`.
  - AC1: One-line diff in `docs/rfc/0004-student-experience-roadmap.md`.

## Out of scope

Eval dashboard (RFC-003 exclusion), Ragas adoption, threshold gates on PR CI,
FSRS/quiz eval, new judge dimensions, prompt changes to the judge.
