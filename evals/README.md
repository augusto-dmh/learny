# Evals

`results/` receives the JSONL lines the LLM-judge appends per evaluated case
(`evals/results/<date>-<git-sha>.jsonl`). Locally the files are throwaway seed
data; in CI the nightly workflow uploads them as an artifact and persists them
to the dedicated `eval-results` branch, which is the long-lived eval history.

How the thresholds that gate the nightly run were derived — and how to
re-derive them on any model swap — is documented in the calibration runbook:
[docs/ops/eval-calibration.md](../docs/ops/eval-calibration.md).
