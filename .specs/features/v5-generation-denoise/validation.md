# v5-generation-denoise Validation

**Date**: 2026-07-31 (iteration 2 — fix→re-verify)
**Spec**: `.specs/features/v5-generation-denoise/spec.md` (incl. "Recorded deviations" section)
**Diff range**: `main...feat/generation-denoise` (d3f589e8..7ef55cac)
**Verifier**: independent sub-agent (author ≠ verifier), evidence-or-zero

---

## Verdict: PASS ✅ (with one recorded, operator-approved deviation)

Iteration 1 found a blocker: the live study was judged by `claude-haiku-4-5` via a stale `.env` pin. Iteration 2 re-verified all four gaps against commits c2bf2375 and 7ef55cac. The judge is now hard-pinned, the study re-ran under `claude-opus-4-8`, and every offline gap gained a discriminating test. The one remaining shortfall — 7 of 144 units unscored after credit exhaustion, operator chose to halt — is recorded as a SPEC_DEVIATION in spec.md and AD-238 in `.specs/project/STATE.md`, with the verdict cross-checked on the two complete runs; per the deviation record it does not block.

---

## Iteration-2 gap re-verification

### Gap 1 (Blocker — wrong judge): FIXED ✅

- **Pin**: `backend/tests/eval/test_generation_study.py:34` — `STUDY_JUDGE_MODEL = "claude-opus-4-8"` (constant, not settings); used at `:99` (`Judge(api_key=..., model=STUDY_JUDGE_MODEL)`) and `:190` (`load_recorded(..., judge_model=STUDY_JUDGE_MODEL)`).
- **Pin test**: `backend/tests/eval/test_study_runner.py:548` `test_study_judge_is_the_recalibrated_opus_judge` — asserts the constant equals `"claude-opus-4-8"` AND `Settings(_env_file=None).judge_model`.
- **Artifacts re-verified by recount** (last-wins dedupe on unit key): 72 golden + 79 silver raw lines = 151 → 144 unique units; statuses 137 `ok` / 7 `error`; **all 117 judged lines carry `judge_model: claude-opus-4-8`** and prompt_hash `211d9d8c…` (117 = 137 ok − 20 declines, consistent with ADR-028). Old haiku-judged golden artifact deleted from the repo; its silver counterpart renamed `.discarded` inside the wholly git-ignored `evals/silver/results/` (no hygiene issue).
- **Verdicts recomputed independently**: `denoised_generation_verdict` over `per_run_aggregates` of both artifacts prints `stay` on all lines AND `stay` on complete runs only (run_index 0–1, 96/96 units) — both match the doc's literal quotes.

### Gap 2 (progress line, DENOISE-09 AC8): FIXED ✅

`test_study_runner.py:562` `test_runner_emits_a_progress_line_per_unit` — asserts one line per unit with unit identity + status for both a recorded-skip and a scored unit. Discriminating (mutant 6 killed).

### Gap 3 (spend report): FIXED ✅ (judged against the deviation record)

`docs/research/2026-07-31/generation-denoise-ab.md` spend table now carries: ceiling $10, pre-flight estimate $8.64, modeled-at-halt $9.07 (recomputed: $8.64 + $0.43 error-unit re-attempt billing — matches), the discarded haiku pass acknowledged as real wasted spend, actual = provider console as billed authority with 400s billing nothing, and remaining ≈$0.45 modeled for the 7 resumable units. The original "actual ≤ $10 with ratio recorded" success criterion is superseded by the recorded deviation (credits exhausted → console reconciliation impossible mid-halt); AD-238 covers this.

### Gap 4 (broken-status resume skip, DENOISE-05): FIXED ✅

`test_study_runner.py:582` `test_resume_skips_a_recorded_broken_unit` — a recorded `broken` unit is never re-scored. Discriminating (mutant 7 killed).

---

## Spec-Anchored Acceptance Criteria (final)

### P1: Noise-aware multi-run verdict (DENOISE-01..03) — all ✅ (unchanged from iteration 1)

| Criterion | Evidence | Result |
|---|---|---|
| Spread values/mean/min/max/range; None-runs excluded; empty visibly `None` | `backend/tests/eval/test_ab.py:404,418,427,436,443,471` | ✅ |
| move iff ≥2 strictly better (min(opus) > max(sonnet)) and none worse | `test_ab.py:491,549` | ✅ |
| Overlap / touching / ceiling-flat = tie | `test_ab.py:497,505,520` | ✅ |
| All-None metric incomparable | `test_ab.py:528,536` | ✅ |
| <2 better / any worse / empty arm → stay | `test_ab.py:512,543` | ✅ |

### P1: Study runner (DENOISE-04..09, 14) — all ✅

| Criterion | Evidence | Result |
|---|---|---|
| Per-unit checkpoint append, never buffered | `test_study_runner.py:118,141` | ✅ |
| Full line schema incl. judge identity; declines never judge-called, null scores | `test_study_runner.py:118,381,402`; `test_silver_run.py:130,152,165` | ✅ |
| Resume skips ok/skipped/**broken**, re-attempts error | `test_study_runner.py:182,196,582` | ✅ |
| prompt_hash / judge_model drift refusal | `test_study_runner.py:235,255,275` | ✅ |
| Error line + continue | `test_study_runner.py:155` (and live: 7 real error lines with the study continuing) | ✅ |
| Artifact split tracked/ignored + hygiene | `test_study_runner.py:171`; `git ls-files` tracks golden, `git check-ignore` confirms silver; silver lines carry ids/scores/flags only | ✅ |
| Opt-in only, never nightly-collected | `test_study_runner.py:481,494,503,511`; bare run = 1 skipped | ✅ |
| **Progress line per unit** | `test_study_runner.py:562` | ✅ |
| Budget stop before crossing; recorded lines bill once | `test_study_runner.py:308,321,339` | ✅ |
| `eval_budget_usd` default 10.0 / override | `backend/tests/test_config.py:80,103` | ✅ |
| **Study judge pinned to opus** | `test_study_runner.py:548` + `test_generation_study.py:34,99,190` | ✅ |

### P1: Live study, verdict, consequence (DENOISE-10..13) — procedural

| Criterion | Evidence | Result |
|---|---|---|
| 2 arms × 3 runs × both tiers, judged by `claude-opus-4-8` | 144 unique units planned; 137 scored (runs 1–2 complete 96/96; run 3 golden 24/24, silver 17/24); 117/117 judged lines = opus + Cycle B prompt hash | ✅ with recorded deviation (SPEC_DEVIATION in spec.md; AD-238) |
| Budget protocol + spend report | doc spend table (ceiling/estimate $8.64/modeled-at-halt $9.07/actual statement/remaining $0.45); modeled figures independently recomputed and matching | ✅ |
| Research doc: rule, method+coverage, variance tables, literal verdict + complete-runs cross-check, spend, limitations | all sections present; **every variance value, error split (3 sonnet / 4 opus, all silver run 3, 400s), decline count (20 = 18 not-found + 2 opus answerable), and citation-valid rate 1.0 independently reproduced from the artifacts**; discarded first pass honestly documented | ✅ |
| stay → no config or threshold change | `backend/app/core/config.py:210` `generation_model = "claude-sonnet-5"`; `backend/app/eval/judge.py:59-60` `0.90`/`3.1`; zero diff on both files across the fix commits | ✅ |
| move consequence | n/a — verdict stay | N/A |

**Status**: ✅ All ACs covered; 1 deviation recorded where claimed (spec.md "Recorded deviations", STATE.md AD-238, research doc coverage + limitations sections).

---

## Discrimination Sensor (cumulative)

All mutations in scratch state, each reverted via `git checkout --`; final `git status` clean.

| # | File | Mutation | Killed? |
|---|---|---|---|
| 1 | `app/eval/ab.py` | verdict `>` → `>=` | ✅ (2 tests) |
| 2 | `app/eval/ab.py` | empty `MetricSpread.range` → `0.0` | ✅ |
| 3 | `tests/eval/study.py` | judge-drift check disabled | ✅ |
| 4 | `tests/eval/study.py` | recorded lines billed twice | ✅ |
| 5 | `tests/eval/silver.py` | declined answers judged again | ✅ |
| 6 | `tests/eval/study.py` | scored-unit progress line removed | ✅ (new test) |
| 7 | `tests/eval/study.py` | `broken` dropped from complete statuses | ✅ (new test) |
| 8 | `tests/eval/test_generation_study.py` | `STUDY_JUDGE_MODEL` drifted to haiku | ✅ (pin test) |

**Result**: 8/8 killed ✅

---

## Gate Check

- Targeted: `uv run pytest tests/eval/test_study_runner.py tests/eval/test_ab.py tests/eval/test_silver_run.py tests/eval/test_silver_hygiene.py tests/test_config.py -q` → **135 passed, 0 failed** (+3 tests since iteration 1)
- Bare `tests/eval/test_generation_study.py` → 1 skipped (opt-in flag message) — correct
- `ruff check` + `ruff format --check` on changed files: clean
- Full suite (author-reported, consistent with targeted evidence): 1997 passed / 12 skipped + the pre-existing local HNSW retrieval flake (reproduced on clean main; not a cycle defect)

---

## Remaining notes (non-blocking)

1. 7 error units (~$0.43 modeled) remain resumable whenever credits exist — tracked by AD-238; one `--generation-study` re-invocation completes the study.
2. Cosmetic: `test_generation_study.py:5` module docstring still says "judged by the settings judge" — stale wording contradicted by the pin at `:34`; worth a one-line tidy in a future touch, not a defect.

---

## Requirement Traceability (final)

| Requirement | Status |
|---|---|
| DENOISE-01..09, 14 | ✅ Verified |
| DENOISE-10 | ✅ Verified (2 complete runs + partial run 3 per recorded SPEC_DEVIATION / AD-238) |
| DENOISE-11 | ✅ Verified (spend report per deviation record) |
| DENOISE-12 | ✅ Verified (doc reproduces from artifacts; verdict is the pure function's literal output, cross-checked) |
| DENOISE-13 | ✅ Verified (stay → zero config/threshold change) |

---

## Summary

**Overall**: ✅ Ready

**Spec-anchored check**: 14/14 requirements verified; 1 recorded deviation (AD-238) honored as specified
**Sensor**: 8/8 mutants killed (cumulative)
**Gate**: 135 targeted passed / full suite green per baseline

The de-noised generation verdict is `stay`, computed by `denoised_generation_verdict` over opus-judged multi-run artifacts, reproduced independently by this verification both over all lines and over the two complete runs; the generation default remains `claude-sonnet-5` and thresholds remain 0.90/3.1.
