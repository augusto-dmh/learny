# v5-generation-denoise — Tasks

3 phases, 9 tasks — under the sub-agent threshold → executed inline. Gate per task: the named test subset green; full backend suite + `make lint` at each phase boundary. One atomic commit per task (Conventional Commits, no internal IDs, no attribution).

## Phase 1 — Pure layer + silver alignment

- [ ] **T1** `MetricSpread` + `metric_spread` in `app/eval/ab.py` (DENOISE-01). None-runs excluded; empty spread yields `None` stats, never 0.0. Tests in `tests/eval/test_ab.py`. Gate: `uv run pytest tests/eval/test_ab.py`.
- [ ] **T2** `denoised_generation_verdict` (DENOISE-02/03, AD-231/235/236): range-overlap rule over silver metrics; boundaries covered (disjoint, touching = overlap, ceiling-flat, all-None, empty arm). Gate: same.
- [ ] **T3** Silver decline alignment per ADR-028 (design §2): `run_silver_case` skips the judge on `found=False`, emits `found` + null scores; answered lines emit `found: true`. Update `tests/eval/test_silver_run.py`. Gate: `uv run pytest tests/eval/test_silver_run.py tests/eval/test_silver_hygiene.py`.

**Phase boundary**: full backend suite + `make lint`.

## Phase 2 — Study runner

- [ ] **T4** `Settings.eval_budget_usd` (default 10.0, `LEARNY_EVAL_BUDGET_USD`) + `test_config.py` pin/override + `.env.example` row (DENOISE-14 scaffold). Gate: `uv run pytest tests/test_config.py`.
- [ ] **T5** `tests/eval/study.py` core: unit plan + deterministic order, golden/silver scoring paths (design §3), per-unit checkpoint append, line schema, progress lines, per-unit error continuation (DENOISE-04/07). Tests: new `tests/eval/test_study_runner.py` (fakes, tmp dirs). Gate: `uv run pytest tests/eval/test_study_runner.py`.
- [ ] **T6** Resume + refusal + budget stop (DENOISE-05/06/14): skip ok/skipped/broken, re-attempt error, `StudyMismatchError` on prompt_hash/judge_model drift, `CostModel` stop-before-unit with recorded-lines counted once. Proof includes the interrupted-study-resumes-with-zero-repeat-calls success criterion. Gate: same.
- [ ] **T7** Artifact split (tracked golden / ignored silver, stable names) + `--generation-study` conftest flag + `test_generation_study.py` live entrypoint + offline guards (not nightly-collected, skipped without flag) (DENOISE-08/09). Gate: `uv run pytest tests/eval/test_study_runner.py tests/eval/test_silver_hygiene.py` + a bare `uv run pytest tests/eval/test_generation_study.py` showing the skip.

**Phase boundary**: full backend suite + `make lint`.

## Phase 3 — Live study + evidence

- [ ] **T8** Live study (DENOISE-10/11): pre-flight prompt_hash check + modeled estimate recorded; run both arms × 3 runs × both tiers under the $10 cap (`make infra` + corpus DB up for silver; resume on interruption; status-page rule on 2+ provider 5xx). Evidence: the two study artifacts.
- [ ] **T9** Research doc + verdict + consequence (DENOISE-12/13, AD-237): `docs/research/<run-date>/generation-denoise-ab.md` in the design §5 shape; verdict = literal `denoised_generation_verdict` output; stay → no config change / move → flip + threshold re-derivation committed together; ROADMAP + RFC-005 Cycle C row updates. Gate: full backend suite + `make lint`.

**Then**: fresh Verifier (always-on, Opus-or-better per ship-cycle cost discipline).

## Traceability

| Task | Requirements |
|---|---|
| T1 | DENOISE-01 |
| T2 | DENOISE-02, DENOISE-03 |
| T3 | DENOISE-07 (decline leg), ADR-028 compliance |
| T4 | DENOISE-14 (config) |
| T5 | DENOISE-04, DENOISE-07 |
| T6 | DENOISE-05, DENOISE-06, DENOISE-14 |
| T7 | DENOISE-08, DENOISE-09 |
| T8 | DENOISE-10, DENOISE-11 |
| T9 | DENOISE-12, DENOISE-13 |
