# v5-generation-denoise Validation

**Date**: 2026-07-31
**Spec**: `.specs/features/v5-generation-denoise/spec.md`
**Diff range**: `main...feat/generation-denoise` (d3f589e8..08e9fc6f)
**Verifier**: independent sub-agent (author ≠ verifier), evidence-or-zero

---

## Verdict: FAIL ❌

The offline layers (pure verdict, study runner, silver alignment, budget config) are fully covered and discriminating — 5/5 mutants killed. The live study, however, was **judged by `claude-haiku-4-5`, not `claude-opus-4-8`**: all 125 judged lines in both artifacts record `"judge_model": "claude-haiku-4-5"` (the local `backend/.env:55` pins `LEARNY_JUDGE_MODEL=claude-haiku-4-5`, and the entrypoint reads `settings.judge_model`). This violates DENOISE-10 verbatim ("all judged by `claude-opus-4-8`") and makes the research doc's claim "The judge is the Cycle B-settled `claude-opus-4-8`" factually false (DENOISE-12). The Cycle B thresholds (0.90/3.1) were derived under the opus judge, so the study's silver metrics come from a different scoring distribution than the pre-registered rule assumed.

---

## Task Completion

| Task | Status | Notes |
|---|---|---|
| T1–T7 (pure layer, silver alignment, runner, config, entrypoint) | ✅ Done | All offline gates green; evidence below |
| T8 (live study) | ❌ Defective | Ran under the wrong judge (haiku via `.env` leak) |
| T9 (research doc + verdict) | ⚠️ Partial | Doc structurally complete and numerically accurate to the artifacts, but misstates the judge identity |

---

## Spec-Anchored Acceptance Criteria

### P1: Noise-aware multi-run verdict (DENOISE-01..03)

| Criterion | Spec outcome | Evidence | Result |
|---|---|---|---|
| Spread exposes per-run values/mean/min/max/range per metric/tier/arm | exact stats | `backend/tests/eval/test_ab.py:404` — `spread.values == (0.90, 0.95, 0.85)`, `mean approx 0.90`, `min == 0.85`, `max == 0.95`, `range approx 0.10`; golden tier at `:443` | ✅ PASS |
| None-runs excluded, never coerced | values omit None run | `test_ab.py:418` — `spread.values == (0.90,)` | ✅ PASS |
| All-None / empty spread visibly empty, never 0.0 | all stats `None` | `test_ab.py:427` — `mean/min/max/range is None`; `:436` all-None runs | ✅ PASS |
| move iff ≥2 metrics strictly better (min(opus) > max(sonnet)) and none worse | `"move"` | `test_ab.py:491` — `== "move"`; `:549` single-better `== "stay"` | ✅ PASS |
| Overlap (incl. touching, incl. identical constants) = neither better nor worse | `"stay"` | `test_ab.py:497` (overlap), `:505` (touching = strictly-greater required), `:520` (ceiling-flat) — all `== "stay"` | ✅ PASS |
| All-None metric incomparable, never worse | not counted | `test_ab.py:528` — `== "move"` despite None discipline; `:536` one-sided | ✅ PASS |
| <2 better / any worse / empty arm → stay | `"stay"` | `test_ab.py:512` (worse metric), `:543` (both empty-arm orders) | ✅ PASS |

### P1: Study runner (DENOISE-04..09, 14)

| Criterion | Spec outcome | Evidence | Result |
|---|---|---|---|
| One JSONL line per unit, appended immediately, never buffered | lines on disk after mid-study kill | `backend/tests/eval/test_study_runner.py:118` (2 units → 2 lines); `:141` — KeyboardInterrupt leaves `["g1","g2"]` on disk | ✅ PASS |
| Line schema = ab.py contract + run_index/judge_model/prompt_hash/git_sha/ts | all fields present | `test_study_runner.py:118` (case_id/tier/generation_model/run_index/git_sha/ts/faithfulness/relevancy/citation_valid/found/expected_not_found); `:381` — `fields["judge_model"] == _JUDGE`, `fields["prompt_hash"] == _PHASH` | ✅ PASS |
| Declined units make no judge calls, null scores (ADR-028) | `judge.calls == []`, nulls | golden: `test_study_runner.py:402` — `judge.calls == []`, `faithfulness/relevancy is None`, no `judge_model`; silver: `backend/tests/eval/test_silver_run.py:130` — RaisingJudge + `status == "ok"` proves no call | ✅ PASS |
| Resume skips ok/skipped/broken, re-attempts error | scorer call list | `test_study_runner.py:182` — calls `== ["g3","g4"]` (ok/skipped skipped, error re-attempted); `:196` — complete study → zero calls | ⚠️ PASS (note: `broken` skip path relies on `_COMPLETE_STATUSES`; no test uses a recorded `broken` status for the *skip* leg — `:339` covers its billing only) |
| prompt_hash / judge_model drift → refuse before spend | `StudyMismatchError` | `test_study_runner.py:235`, `:255` — `pytest.raises(StudyMismatchError)`; `:275` no-identity lines tolerated | ✅ PASS |
| Provider failure → error line, study continues | statuses `["error","ok"]` | `test_study_runner.py:155` — error line with message, null scores, `report.scored == 2` | ✅ PASS |
| Artifact split: tracked golden / ignored silver | files + git state | `test_study_runner.py:171` (split); procedural: `git ls-files` tracks `evals/results/2026-07-31-e9d9fbab-generation-denoise.jsonl`, `git check-ignore` confirms silver path ignored; silver lines carry only ids/scores/flags (no book text keys) | ✅ PASS |
| Never nightly-collected; opt-in flag only | `live` mark, no `eval` mark; skip without flag/key | `test_study_runner.py:481` — `"live" in marker_names`, `"eval" not in marker_names`; `:494`/`:503`/`:511` skip-reason matrix; bare run observed: `1 skipped` | ✅ PASS |
| Progress line per unit (unit identity + status) | printed line | implementation exists (`backend/tests/eval/study.py:204,210-214,241`) but **no test asserts progress output** — all tests pass `progress=lambda message: None` (`test_study_runner.py:88`) | ❌ GAP (minor) |
| Budget stop before crossing unit; recorded lines bill exactly once | stop point + meter | `test_study_runner.py:308` — exactly 2 of 5 score, `modeled_spent_usd approx 0.04`, checkpoint on disk; `:321` — exactly one more unit under resume (double-billing would score none); `:339` — skipped/broken bill nothing | ✅ PASS |
| `LEARNY_EVAL_BUDGET_USD` default 10.0 + override | 10.0 / 2.5 | `backend/tests/test_config.py:80` — `== 10.0`; `:103` — `== 2.5`; `.env.example` row present | ✅ PASS |

### P1: Live study, verdict, consequence (DENOISE-10..13) — procedural

| Criterion | Spec outcome | Evidence | Result |
|---|---|---|---|
| 2 arms × 3 runs × both tiers, **all judged by `claude-opus-4-8`** | opus judge | Arms/runs/tiers: both artifacts, 72+72 = 144 lines, 24 per (arm, run) — verified by recount. Judge: **FAIL** — 125/125 judged lines record `"judge_model": "claude-haiku-4-5"` (53 golden + 72 silver); `backend/.env:55` pins `LEARNY_JUDGE_MODEL=claude-haiku-4-5` | ❌ FAIL |
| Modeled estimate first, proceed under $10, spend report (ceiling, estimate, actual, ratio) | doc table | `docs/research/2026-07-31/generation-denoise-ab.md` spend table: ceiling $10, estimate $8.64, modeled-at-completion $8.64. **No actual billed figure and no estimate-vs-actual ratio recorded** (success criterion "ratio recorded" unmet; deferred to "provider console") | ⚠️ Partial |
| Research doc: pre-registered rule, manifest, variance tables, literal verdict, spend report, limitations | all sections | All sections present; variance tables independently recomputed from artifacts and **match exactly** (silver sonnet faith [0.9951, 0.9931, 1.0], etc.); verdict recomputed via `denoised_generation_verdict` over `per_run_aggregates` of both artifacts → prints `stay`, matching the doc. **But** the doc's judge-identity claim is false | ❌ FAIL (factual accuracy) |
| stay → no config or threshold change | unchanged | `backend/app/core/config.py:210` — `generation_model: str = "claude-sonnet-5"`; `backend/app/eval/judge.py:59-60` — `FAITHFULNESS_MIN = 0.90`, `RELEVANCY_MIN = 3.1`; `judge.py` absent from diff | ✅ PASS (mechanically; evidentiary basis compromised by the judge defect) |
| move → flip + threshold re-derivation | n/a | verdict is stay | N/A |

**Status**: ❌ Gaps present — 1 blocker (judge identity), 1 minor test gap (progress lines), 2 partials.

---

## Edge Cases

- [x] Ceiling-flat metric both arms → tie: `test_ab.py:520`
- [x] All-error run contributes no values; zero metric-bearing runs → stay: composed from `test_ab.py:418/427/543` (aggregate excludes error lines per existing `ab.py` tests)
- [x] Resume of complete artifact → zero provider calls: `test_study_runner.py:196`
- [ ] Silver unavailable → golden-only with surfaced skip reason: implemented in the entrypoint (`test_generation_study.py:123-151`) but no offline test; procedural-only, not exercised in the live run (silver was available)
- [x] Golden not-found answered/declined discipline: `test_study_runner.py:402` (`expected_not_found is True` on decline) + existing `ab.py` discipline aggregation tests

---

## Gate Check

- **Command**: `uv run pytest tests/eval/test_ab.py tests/eval/test_silver_run.py tests/eval/test_silver_hygiene.py tests/eval/test_study_runner.py tests/test_config.py -q` → **132 passed, 0 failed**
- Bare `uv run pytest tests/eval/test_generation_study.py -q` → 1 skipped ("pass --generation-study …") — correct opt-in behavior
- `ruff check` + `ruff format --check` over all 10 changed backend files: clean
- New tests: +42 (15 in test_ab.py, 24 in test_study_runner.py, 3 in test_silver_run.py); no deletions or weakened assertions observed in the diff
- Full-suite baseline note: known pre-existing local HNSW flake in `test_eval_retrieval_metrics.py` excluded per baseline; not a cycle defect

---

## Discrimination Sensor

Scratch-state fault injection; every mutation reverted via `git checkout --`; final `git status` clean.

| # | File:line | Mutation | Killed? |
|---|---|---|---|
| 1 | `app/eval/ab.py` (`denoised_generation_verdict`) | `o.min > s.max` → `>=` | ✅ Killed (2 tests: touching-ranges, ceiling-flat) |
| 2 | `app/eval/ab.py` (`MetricSpread.range`) | empty → `0.0` instead of `None` | ✅ Killed (visibly-empty-never-zero) |
| 3 | `tests/eval/study.py` (`load_recorded`) | judge_model drift check disabled | ✅ Killed (judge-drift refusal) |
| 4 | `tests/eval/study.py` (`run_study`) | recorded lines billed twice (`2 * sum`) | ✅ Killed (bill-exactly-once) |
| 5 | `tests/eval/silver.py` (`run_silver_case`) | declined answers judged again (`if answer.found` → `if True`) | ✅ Killed (2 decline tests via RaisingJudge) |

**Sensor depth**: lightweight+ (5 mutations) — **5/5 killed** ✅

---

## Code Quality

| Principle | Status |
|---|---|
| Minimum code / surgical changes / no scope creep | ✅ |
| Matches patterns (injection like silver.py, None-never-0.0 convention) | ✅ |
| Spec-anchored outcomes (offline layers) | ✅ |
| Every test maps to a spec AC or edge case | ✅ (no unclaimed tests found) |
| Documented guidelines | eval-tier conventions followed (silver hygiene, ADR-028 decline semantics) |

---

## Requirement Traceability

| Requirement | Status |
|---|---|
| DENOISE-01..08, 14 | ✅ Verified |
| DENOISE-09 | ⚠️ Verified except progress-line assertion (AC8 untested) |
| DENOISE-10 | ❌ Needs Fix — study judged by haiku, spec demands opus |
| DENOISE-11 | ⚠️ Partial — no actual-spend figure / ratio recorded |
| DENOISE-12 | ❌ Needs Fix — doc misstates judge identity |
| DENOISE-13 | ⚠️ Config state matches "stay" but the verdict's evidence base is invalid until re-judged |

---

## Fix Plans

### Fix 1 (Blocker): Re-run or re-judge the live study under `claude-opus-4-8`
- **Root cause**: the live entrypoint takes `settings.judge_model`, which the git-ignored `backend/.env` overrides to `claude-haiku-4-5` (the known `.env` provider-leak trap); the pre-flight verified only `prompt_hash`, not the judge model, and the mismatch guard compared recorded lines against the *same drifted* setting, so it could not fire.
- **Fix**: run with `LEARNY_JUDGE_MODEL=claude-opus-4-8` into fresh artifacts (the existing haiku artifacts will be refused by `load_recorded`, correctly); add an opus-judge pre-flight assertion (or pin) in the entrypoint so `.env` drift cannot recur; rewrite the doc's judge claim and verdict from the new artifacts; update the tracked artifact.
- **Verify**: every judged line's `judge_model == "claude-opus-4-8"`; recomputed verdict quoted in the doc.

### Fix 2 (Minor): Assert the progress line (DENOISE-09 AC8)
- One test capturing `progress` output for a scored, a skipped, and a budget-stopped unit.

### Fix 3 (Minor): Record actual spend + estimate-vs-actual ratio in the spend report (success criterion), or explicitly amend the spec/success criterion if console access is out of band.

---

## Summary

**Overall**: ❌ Not Ready

**Spec-anchored check**: offline 12/12 ACs matched; live 2/5 failed or partial
**Sensor**: 5/5 mutants killed
**Gate**: 132 passed, 0 failed (targeted); lint clean

**What works**: pure spread/verdict layer, checkpoint/resume/refusal/budget runner, silver ADR-028 decline alignment, artifact split + hygiene, opt-in guards — all evidence-anchored and mutation-discriminating. The doc's numbers and the `stay` verdict are faithful to the artifacts as recorded.

**What fails**: the artifacts themselves were produced under the wrong judge; DENOISE-10/12 cannot pass, and the de-noised STAY is not yet the opus-judged evidence the spec requires.
