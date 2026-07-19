# Tasks — v3-eval-maturity

3 phases, executed inline (≤3 → no worker delegation). Branch: `feat/v3-eval-maturity`.

## Gate Check Commands

- Quick: `cd backend && uv run pytest <affected files> -q`
- Full-offline: `cd backend && uv run pytest -q` (no keys in env — offline baseline) + `uv run ruff check .`
- Keyed (manual, not CI): env from `backend/.env` + `LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test`

## Phase A — Model alignment + snapshot recording

- **T1 — Default generation model → `claude-sonnet-5`** (EVAL-02)
  - Files: `backend/app/core/config.py`, `backend/.env.example`, test files asserting the old default (`test_config.py`, `test_answering_factory.py`, `test_answering_anthropic.py`, `test_eval_judge.py`, `tests/eval/test_replay_harness.py` — update only assertions on the *default*, keep behavior tests intact).
  - Done when: default is `claude-sonnet-5`; quick gate green on the touched test files.
  - Gate: quick. Commit: `feat(config): default generation to the current sonnet model`.
- **T2 — Record generation snapshots with the real provider** (EVAL-01)
  - Run `uv run pytest --record-generation -m "live and eval"` (keys + learny_test DB); commit the produced `backend/tests/eval/snapshots/*.json`; confirm the offline replay tests execute against them (no "no snapshots" skips).
  - Done when: one snapshot per case in cases.yaml; offline `pytest tests/eval -q` has zero snapshot-absence skips.
  - Gate: quick (tests/eval offline). Commit: `test(eval): record real-provider generation snapshots`.

## Phase B — Calibration + nightly gate

- **T3 — Seed keyed baselines** (EVAL-03/04)
  - Run the live judge suite 3× (keyed) collecting JSONL aggregates; run the keyed retrieval arm once; record raw aggregates into the cycle notes for T4/T6.
  - Done when: 3 generation JSONL files + retrieval metrics observed; keyed retrieval thresholds pass.
  - Gate: the runs themselves. No commit (data feeds T4/T6; JSONL stays out of git per existing convention — results live on the eval-results branch).
- **T4 — Calibrate judge thresholds** (EVAL-03)
  - Files: `backend/app/eval/judge.py` (constants + derivation comment, provisional wording removed), `backend/tests/test_eval_judge.py` if it asserts threshold values.
  - Done when: constants = mean−margin per AD-116; a replay of the three observed runs would pass the gate; offline suite green.
  - Gate: quick. Commit: `feat(eval): calibrate judge thresholds from observed baselines`.
- **T5 — Nightly gate on; OpenAI arm wired** (EVAL-05)
  - Files: `.github/workflows/eval.yml` only.
  - Done when: `LEARNY_EVAL_GATE: "1"` set; `LEARNY_OPENAI_API_KEY` + `LEARNY_TEST_DATABASE_URL` wiring lets the keyed retrieval arm run nightly with the same green-skip guard; `ci.yml` untouched.
  - Gate: yaml parse + full-offline. Commit: `ci(eval): enable the nightly judge gate with real-provider retrieval`.

## Phase C — Docs + rider

- **T6 — Calibration runbook** (EVAL-06)
  - Files: `docs/ops/eval-calibration.md` (new). Commands, cost, derivation rule, observed baselines (generation + retrieval), re-derivation on model swap.
  - Gate: `git diff --check`. Commit: `docs(eval): document the threshold calibration method`.
- **T7 — RFC-004 status → Accepted** (EVAL-07)
  - Files: `docs/rfc/0004-student-experience-roadmap.md` (status line only).
  - Gate: `git diff --check`. Commit: `docs(roadmap): accept the student-experience roadmap`.

Phase boundaries run the full-offline gate. Verifier dispatched after T7.
