# Evals

`results/` receives the JSONL lines the LLM-judge appends per evaluated case
(`evals/results/<date>-<git-sha>.jsonl`). Locally the files are throwaway seed
data; in CI the nightly workflow uploads them as an artifact and persists them
to the dedicated `eval-results` branch, which is the long-lived eval history.

How the thresholds that gate the nightly run were derived — and how to
re-derive them on any model swap — is documented in the calibration runbook:
[docs/ops/eval-calibration.md](../docs/ops/eval-calibration.md).

## Reading the results

`/dev/evals` renders the accumulated runs: per-run mean faithfulness and
relevancy against the calibrated thresholds, citation-valid rate, the derived
gate verdict, and a per-case drill-down. The verdict is *derived* — the JSONL
records no pass/fail — by re-applying the gate's own three conditions with the
gate's own constants, so it moves with a recalibration instead of drifting from
it.

The surface is dev-only: it is mounted only when `LEARNY_DEV_EVAL_DASHBOARD_ENABLED`
is set on a process that is not running as production, and it requires a session
once mounted. `docker compose up` enables it locally via the override file.

By default it reads this directory, which on a normal checkout holds only the
committed result files. To render the real nightly history, check out the
`eval-results` branch alongside the repo and point the reader at it:

```bash
git worktree add ../learny-eval-results eval-results
export LEARNY_EVAL_RESULTS_DIR=../learny-eval-results
```

The directory is walked recursively, so the branch's `results/<date>-<run-id>/`
layout and this flat directory both read the same. Because each nightly run
re-publishes every file it finds, one result file recurs across many snapshot
directories; runs are keyed by file name and counted once.
