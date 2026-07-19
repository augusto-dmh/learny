# Eval calibration runbook

How Learny's nightly evaluation gate got its thresholds, what they mean, and
how to re-derive them when a model changes. Companion to the nightly workflow
(`.github/workflows/eval.yml`) and the judge implementation
(`backend/app/eval/judge.py`).

## What gates what

| Surface | Runs | Gated by |
|---|---|---|
| PR CI (`ci.yml`) | Deterministic suite, replay snapshots, deterministic retrieval arm | Test assertions only — no provider, no keys, no judge gate |
| Nightly (`eval.yml`) | Live judge tier + keyed OpenAI retrieval arm (`pytest -m "live and eval"`) | `LEARNY_EVAL_GATE=1` → aggregate thresholds below fail the run |

Secrets (repository → Actions): `LEARNY_ANTHROPIC_API_KEY` (required — absent
means the whole nightly green-skips with a notice), `LEARNY_OPENAI_API_KEY`
(optional — absent means the retrieval arm self-skips).

## Recorded baselines (2026-07-18)

Generation: `claude-sonnet-5`. Judge: `claude-haiku-4-5`. Embeddings:
`text-embedding-3-large@1536`.

| Metric | Observed | Gate threshold | Derivation |
|---|---|---|---|
| Judge faithfulness (mean) | 1.0 — stable across 5 keyed seed runs | ≥ 0.90 | mean − 0.10 |
| Judge relevancy (mean) | 3 — stable across 5 keyed seed runs | ≥ 2.5 | mean − 0.5 |
| Citation validity | all valid, every run | all must be valid | invariant, no margin |
| Retrieval recall@1 (keyed, 42 labeled pairs) | 1.0 | ≥ 0.9 | test constants, confirmed at ceiling |
| Retrieval recall@5 | 1.0 | ≥ 1.0 | " |
| Retrieval MRR | 1.0 | ≥ 0.93 | " |

Replay snapshots: 12 per-case files under `backend/tests/eval/snapshots/`,
recorded the same day against the same models; PR CI replays them offline.

**Known limitations, recorded honestly:**

- The live judge tier currently scores **one synthetic smoke case**
  (`live-tides`), so its aggregates are narrow. Observed relevancy (3) sits
  below the literature's aspirational 4.0 — the gate is a *regression
  detector against measured behavior*, not a quality bar. If the judge tier
  ever widens to real pipeline cases, the thresholds MUST be re-derived (the
  aggregates will move).
- The answerability tier (quiz eval) showed one judge-variance flake in the
  seed runs (1 of 18 item judgments flipped). Answerability is **not gated**;
  treat isolated flips in the JSONL history as judge noise unless they trend.
- The keyed retrieval arm scores a deliberately lexically-disjoint golden
  corpus at ceiling (1.0 across the board); its thresholds guard against
  total failure and ranking regressions, not fine-grained quality drift.

## Re-derivation procedure (any model swap)

Run whenever `LEARNY_GENERATION_MODEL`, `LEARNY_JUDGE_MODEL`, or the embedding
model/dimensions change:

1. **Re-record replay snapshots** (rewrites `backend/tests/eval/snapshots/`):

   ```bash
   cd backend
   export LEARNY_ANTHROPIC_API_KEY=... LEARNY_OPENAI_API_KEY=...
   export LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test
   uv run pytest tests/eval/test_replay_harness.py --record-generation -q
   ```

   Note: the recorder must be invoked on its test file directly — the
   `-m "live and eval"` nightly selection does not include it.

2. **Seed fresh judge baselines** — run the live tier at least 3 times and
   aggregate the JSONL it appends under `evals/results/`:

   ```bash
   for i in 1 2 3; do uv run pytest -m "live and eval" -q; done
   ```

3. **Observe retrieval metrics** (both arms print their snapshot):

   ```bash
   uv run pytest tests/test_eval_retrieval_metrics.py -q -s | grep tier-2
   ```

4. **Derive**: new threshold = observed mean − margin (faithfulness −0.10,
   relevancy −0.5, rounded to two/one decimals). Citation validity stays an
   invariant. Update `FAITHFULNESS_MIN` / `RELEVANCY_MIN` in
   `backend/app/eval/judge.py` with the observation cited in the comment, and
   the retrieval constants in `backend/tests/test_eval_retrieval_metrics.py`
   only if the observation no longer clears them (record why).
5. **Commit snapshots + constants together** so the recorded baseline and the
   gate that enforces it can never drift apart, and update the table above.

## Cost

The full re-derivation (12-case recording + 3 seed runs + retrieval
observation) measured **well under $1** on 2026-07-18 — the golden corpus is
tiny and the judge runs on the cheap tier. The RFC's $5–15 envelope has ample
headroom for wider judge tiers later.
