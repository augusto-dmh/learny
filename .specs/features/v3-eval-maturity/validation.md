# v3-eval-maturity Validation

**Date**: 2026-07-18
**Spec**: `.specs/features/v3-eval-maturity/spec.md`
**Diff range**: `main..HEAD` (`5b85c39..661a8a0`, 6 commits on `feat/v3-eval-maturity`)
**Verifier**: independent sub-agent (author ≠ verifier); offline only, no provider keys in env (verified before running anything)

Keyed ACs (EVAL-03 AC2, EVAL-04 AC2) were verified by inspection of recorded evidence — committed snapshots, the judge.py derivation comment, `docs/ops/eval-calibration.md`, and the untracked seed JSONL under `evals/results/` — never by executing keyed tests.

---

## Task Completion

| Task | Status | Evidence |
| ---- | ------ | -------- |
| T1 — model default | ✅ Done | commit `5b85c39`; `backend/app/core/config.py:166`, `backend/.env.example:53` |
| T2 — record snapshots | ✅ Done | commit `5ffffb2`; 12 files under `backend/tests/eval/snapshots/` |
| T3 — seed keyed baselines | ✅ Done (no commit by design) | untracked `evals/results/2026-07-18-5b85c39.jsonl` + `2026-07-18-5ffffb2.jsonl` (5 judge-tier lines, 30 answerability lines) |
| T4 — calibrate thresholds | ✅ Done | commit `b34a125`; `backend/app/eval/judge.py:44-54` |
| T5 — nightly gate + OpenAI arm | ✅ Done | commit `07960e8`; `.github/workflows/eval.yml` only |
| T6 — calibration runbook | ✅ Done (link sub-clause: see gaps) | commit `e3c631a`; `docs/ops/eval-calibration.md` |
| T7 — RFC-004 accepted | ✅ Done | commit `661a8a0`; one status line |

---

## Spec-Anchored Acceptance Criteria

| Criterion | Spec-defined outcome | Evidence (`file:line` + assertion / artifact) | Result |
| --------- | -------------------- | --------------------------------------------- | ------ |
| **EVAL-01 AC1** — snapshot per case | one `*.json` per case id in `cases.yaml` | 12 case ids at `backend/tests/eval/cases.yaml:12-45`; 12 matching files in `backend/tests/eval/snapshots/` (names = case ids, verified 1:1); every file's `"model": "claude-sonnet-5"` | ✅ PASS |
| **EVAL-01 AC2** — offline replay, zero snapshot-absence skips | `pytest tests/eval -q` offline runs replay assertions, no "no snapshots" skips | Ran offline: `tests/eval` → 10 passed, 4 skipped — skip reasons are key/DB-URL absence only. `backend/tests/eval/test_replay_harness.py:165-175` (`test_committed_snapshots_roundtrip_or_skip`) ran (not skipped); `backend/tests/test_generation_invariants.py:110-122` parametrized over the 12 snapshots, all passed; `:127` skip reason is "snapshots are committed", not absence | ✅ PASS |
| **EVAL-02 AC1** — default is `claude-sonnet-5` | `Settings.generation_model == "claude-sonnet-5"`; default-asserting tests updated | `backend/app/core/config.py:166` — `generation_model: str = "claude-sonnet-5"`; `backend/tests/test_config.py:45` — `assert settings.generation_model == "claude-sonnet-5"`. Remaining `claude-sonnet-4-6` occurrences in tests are explicit constructor args (behavior tests, correctly untouched per T1), not default assertions — verified by grep | ✅ PASS |
| **EVAL-02 AC2** — offline suite green | full offline suite passes | `cd backend && .venv/bin/pytest -q` (no keys): **790 passed, 401 skipped, 0 failed**; `ruff check .` clean | ✅ PASS |
| **EVAL-03 AC1** — calibrated constants + derivation comment, provisional wording gone | comment cites observed aggregates + derivation rule; values = mean − margin (2dp faithfulness / 1dp relevancy) | `backend/app/eval/judge.py:44-54` — comment cites "five keyed seed runs… observed faithfulness 1.0 and relevancy 3", rule "mean − (0.10, 0.5)", pointer to the runbook; `FAITHFULNESS_MIN = 0.90` (= 1.0 − 0.10, 2dp), `RELEVANCY_MIN = 2.5` (= 3 − 0.5, 1dp). "Provisional/literature defaults" wording removed (grep: no match in judge.py). Consistent with the AD-116 amendment (floor clause dropped; literature values moved to the doc as context) | ✅ PASS |
| **EVAL-03 AC2** — gated replay of seed runs would pass | `LEARNY_EVAL_GATE=1` would not have failed any seed run | Inspected `evals/results/*.jsonl`: 5 judge-tier `live-tides` lines (2 @ sha 5b85c39, 3 @ 5ffffb2), each `faithfulness 1.0, relevancy 3, citation_valid true, generation_model claude-sonnet-5`. Against `_assert_aggregates` (`judge.py:407-419`): 1.0 ≥ 0.90 ✓, 3.0 ≥ 2.5 ✓, all citations valid ✓ — every run passes the gate. Spec asked for 3 runs; 5 were seeded (exceeds) | ✅ PASS (by inspection — keyed) |
| **EVAL-04 AC1** — observed keyed retrieval metrics + model identity in doc | doc lists observed recall@1/recall@5/MRR with model identity | `docs/ops/eval-calibration.md:20-31` — baselines table: recall@1 = 1.0, recall@5 = 1.0, MRR = 1.0 over "42 labeled pairs" with `text-embedding-3-large@1536` (`:21-22`). Pair count independently confirmed: `len(LABELED_PAIRS) == 42` | ✅ PASS |
| **EVAL-04 AC2** — keyed arm passes thresholds on the observation run | observed metrics clear the test thresholds | Thresholds at `backend/tests/test_eval_retrieval_metrics.py:48-50` (`_MIN_RECALL_AT_1 = 0.9`, `_MIN_RECALL_AT_5 = 1.0`, `_MIN_MRR = 0.93`), asserted for the keyed arm at `:164-166`. Recorded observation 1.0/1.0/1.0 clears all three. Note: the only machine artifact of the retrieval observation is the doc table (the JSONL holds judge/answerability lines only) — accepted as the designated evidence for this offline verification | ✅ PASS (by inspection — keyed) |
| **EVAL-05 AC1** — gate env + OpenAI secret in eval.yml, green-skip style | `LEARNY_EVAL_GATE=1`; OpenAI secret wired with green-skip guard style | `.github/workflows/eval.yml:84` — `LEARNY_EVAL_GATE: "1"`; `:83` — `LEARNY_OPENAI_API_KEY: ${{ secrets.LEARNY_OPENAI_API_KEY }}` on the run step; `:49-63` — same check-step style as the Anthropic secret (env-mapped, notice on absence; retrieval arm self-skips via `test_eval_retrieval_metrics.py:123-126` skipif). Collection proof: offline `pytest -m "live and eval" --collect-only` collects 6 tests including `TestOpenAIRetrievalMetrics::test_metrics_meet_thresholds` — the arm joins the nightly selection via the new `@pytest.mark.eval` (`test_eval_retrieval_metrics.py:122`). Both repo secrets confirmed present (`gh secret list`: `LEARNY_ANTHROPIC_API_KEY`, `LEARNY_OPENAI_API_KEY`, created 2026-07-18) — the workflow's secret rename is backed | ✅ PASS |
| **EVAL-05 AC2** — ci.yml untouched | empty diff | `git diff main..HEAD -- .github/workflows/ci.yml` → 0 lines | ✅ PASS |
| **EVAL-06 AC1** — calibration doc: five items + link | commands, cost, derivation rule, observed baselines (gen + retrieval), re-derivation procedure; linked from `evals/README.md` or ops docs index | `docs/ops/eval-calibration.md`: commands `:56-79`, cost `:90-95`, derivation rule `:81-86` + table Derivation column, observed baselines gen+retrieval `:19-34`, re-derivation procedure `:51-88`. **Link sub-clause**: `evals/README.md` does not exist and no ops docs index exists — the doc is referenced only from a code comment (`backend/app/eval/judge.py:48`), not from any docs surface | ⚠️ Minor gap (link clause vacuous/unmet; five content items fully covered) |
| **EVAL-07 AC1** — RFC-004 status flip, one-line diff | `Accepted (2026-07-18)` | `docs/rfc/0004-student-experience-roadmap.md:3` — status line is the sole change (1 modified line in the diff) | ✅ PASS |

**Status**: ✅ 12/13 AC clauses matched; 1 minor gap (EVAL-06 link clause).

---

## Discrimination Sensor

All mutations applied in scratch state (direct edit → targeted run → `git checkout --` restore; tree verified clean after each). Offline runner: `backend/.venv/bin/pytest`, no keys.

| # | Mutation | File:line | Result |
| - | -------- | --------- | ------ |
| M1 | Corrupt committed snapshot **answer text** (`tides-moon-gravity.json`) | snapshot `answer.text` | ❌ **SURVIVED** — 25 passed. By design: the replay assertions are citation/structural invariants + roundtrip; free text has no ground truth to compare against (exact-text assertions would fail every legitimate re-record). Documented, not counted as a weak test |
| M1b | Corrupt same snapshot's **cited_chunk_ids** to a stray UUID | snapshot `answer.cited_chunk_ids` | ✅ **KILLED** — `test_generation_invariants_hold_over_snapshots[tides-moon-gravity]` fails (invariant a) |
| M2a | `FAITHFULNESS_MIN = 0.90` → `1.05` (gate impossible to pass) | `backend/app/eval/judge.py:53` | ❌ **SURVIVED** — 19 passed. No offline test pins the calibrated constant values or a sane range; a typo'd threshold ships undetected (too-high fails every nightly by construction; too-low silently disarms regression detection) → fix task |
| M2b | Flip faithfulness comparison only (`>=` → `<`) in `_assert_aggregates` | `backend/app/eval/judge.py:414` | ❌ **SURVIVED** — 9 passed. The gate tests use a single case failing *both* thresholds, so the intact relevancy assertion still raises and masks the flip; the tests cannot attribute which threshold fired → fix task |
| M2c | Flip **both** comparisons (fully inverted gate) | `judge.py:414,417` | ✅ **KILLED** — `test_gate_on_asserts_aggregate_thresholds` + `test_gate_defaults_to_env_flag` fail |
| M3 | Revert default `generation_model` to `claude-sonnet-4-6` | `backend/app/core/config.py:166` | ✅ **KILLED** — `test_config.py::test_generation_settings_defaults` fails |
| M4 | Remove `@pytest.mark.eval` from `TestOpenAIRetrievalMetrics` | `backend/tests/test_eval_retrieval_metrics.py:122` | ✅ **KILLED** (collection-level sensor, documented as such) — `pytest -m "live and eval" --collect-only` drops 6 → 5, the retrieval arm leaves the nightly selection. No offline test fails; the kill is observable only at collection |

**Sensor depth**: extended lightweight (7 behavior-level mutations)
**Result**: 4 killed / 2 genuine survivors (M2a, M2b) / 1 by-design survivor (M1) — surviving mutants → fix tasks below.

---

## Gate Check

- **Full-offline gate** (tasks.md): `cd backend && pytest -q` (no keys in env) → **790 passed, 401 skipped, 0 failed** (skips = DB-URL/key/docling absence, all justified); `ruff check .` → clean.
- **Targeted**: `pytest tests/eval -q` → 10 passed, 4 skipped (no snapshot-absence skips); `pytest tests/test_generation_invariants.py -q` → 15 passed (incl. 12 snapshot-parametrized), 2 skipped.
- **Test integrity**: no test deletions in the diff; delta = +12 parametrized snapshot invariant instances (from committed snapshots) + 1 marker addition; `test_config.py` assertion updated to the new spec-defined default (not weakened).

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code / surgical changes (20 files, all in task scope) | ✅ |
| No scope creep (`ci.yml` untouched; no new SDKs; provider direction per ADR-0019/0020) | ✅ |
| Matches patterns (green-skip guard style, JSONL convention, runbook beside other ops docs per AD-117) | ✅ |
| Spec-anchored outcome check (asserted values match spec outcomes) | ✅ |
| Every diff-surface test maps to a spec AC | ✅ |
| Documented guidelines followed | ✅ (tasks.md gate commands; AD-115/116/117 + amendment honored) |

Notes: the eval.yml Anthropic secret reference was renamed (`secrets.ANTHROPIC_API_KEY` → `secrets.LEARNY_ANTHROPIC_API_KEY`) — beyond the literal AC text but verified safe: both renamed secrets exist in the repo (created 2026-07-18). The judge.py comment says "five keyed seed runs" vs the spec's "three" — the JSONL confirms 5 seed lines; exceeding the spec minimum, consistent.

---

## Fix Plans

### Fix 1 (Minor→Major): pin the calibrated gate constants offline (from M2a)
- **Root cause**: no offline assertion on `FAITHFULNESS_MIN` / `RELEVANCY_MIN` values; a corrupted constant is invisible until the nightly.
- **Fix task**: in `backend/tests/test_eval_judge.py`, assert `FAITHFULNESS_MIN == 0.90` and `RELEVANCY_MIN == 2.5` (the calibrated baseline, mirroring how `test_config.py` pins the model default), or at minimum range-sanity (`0 < FAITHFULNESS_MIN <= 1.0`, `1 <= RELEVANCY_MIN <= 5`).
- **Verify**: re-run M2a — mutation must be killed.

### Fix 2 (Minor): per-threshold gate discrimination (from M2b)
- **Root cause**: `test_gate_on_asserts_aggregate_thresholds` uses one case failing both thresholds; either single comparison can be inverted undetected.
- **Fix task**: split into two cases — good faithfulness + bad relevancy, and bad faithfulness + good relevancy — each expecting `AssertionError` (match on the message prefix to attribute the threshold).
- **Verify**: re-run M2b — single-flip mutation must be killed.

### Fix 3 (Minor): link the calibration runbook from a docs surface (from EVAL-06 AC1)
- **Root cause**: the spec's link targets (`evals/README.md`, ops docs index) don't exist; the doc is only referenced from a code comment.
- **Fix task**: add a link from `README.md`'s ops-runbook sentence (line ~194) or create a one-line `evals/README.md` pointing to `docs/ops/eval-calibration.md`.
- **Verify**: `grep -rn "eval-calibration" README.md evals/` non-empty.

---

## Requirement Traceability Update

| Requirement | Status |
| ----------- | ------ |
| EVAL-01 | ✅ Verified |
| EVAL-02 | ✅ Verified |
| EVAL-03 | ✅ Verified (AC2 by inspection of recorded evidence); sensor found offline pin/discrimination gaps → Fix 1, Fix 2 |
| EVAL-04 | ✅ Verified (AC2 by inspection of recorded evidence) |
| EVAL-05 | ✅ Verified |
| EVAL-06 | ⚠️ Needs Fix (link clause) → Fix 3 |
| EVAL-07 | ✅ Verified |

---

## Summary

**Overall**: ✅ PASS (flipped from FAIL (narrow) by re-verification iteration 1 — see below)

**Spec-anchored check**: 12/13 AC clauses matched (1 minor: EVAL-06 link clause)
**Sensor**: 7 mutations — 4 killed, 2 genuine survivors (M2a, M2b), 1 by-design survivor (M1, documented)
**Gate**: 790 passed, 0 failed offline; ruff clean

**What works**: all seven requirements are substantively implemented with real recorded evidence; the calibrated values arithmetically match the AD-116 (amended) derivation against the seed JSONL; the nightly gate wiring is complete and backed by real repo secrets; the offline suite replays all 12 snapshots with zero snapshot-absence skips.

**Issues found**: three small fix tasks (constant pin, per-threshold gate test, doc link) — none require keyed re-runs or re-recording.

**Next steps**: apply Fix 1–3 (offline-only, ~15 min), re-run sensor M2a/M2b, flip verdict to PASS.

---

## Re-verification (iteration 1)

**Date**: 2026-07-18
**Fix commits**: `51c63cc` (test(eval): pin calibrated thresholds and split the gate cases — `backend/tests/test_eval_judge.py` +28, `evals/README.md` new), `51f59b0` (lessons record only, no product code)
**Method**: same offline discipline as the original pass — `backend/.venv/bin/pytest`, no provider keys in env (verified: only `CONTEXT7_API_KEY` present, unrelated); mutants injected in scratch state via direct edit → targeted run → `git checkout --` restore; tree confirmed clean after each.

### Gap 1 — constant pin (M2a re-run)

- Pin present: `backend/tests/test_eval_judge.py:250-253` — `test_gate_constants_pin_the_calibrated_baselines` asserts `FAITHFULNESS_MIN == 0.90` and `RELEVANCY_MIN == 2.5` exactly (values at `backend/app/eval/judge.py:53-54`).
- M2a re-injected (`FAITHFULNESS_MIN = 1.05` at `judge.py:53`): `pytest tests/test_eval_judge.py -q` → **2 failed**, 10 passed — `test_gate_constants_pin_the_calibrated_baselines` fails at `:252` (plus `test_gate_trips_on_relevancy_alone` collaterally, as 1.0 < 1.05 now trips faithfulness first). ✅ **KILLED**. Restored.

### Gap 2 — per-threshold gate discrimination (M2b re-run, both directions)

- Dedicated cases present: `test_gate_trips_on_faithfulness_alone` (`test_eval_judge.py:228-235`, relevancy passes at 5, expects `AssertionError` matching `"faithfulness"`) and `test_gate_trips_on_relevancy_alone` (`:238-245`, faithfulness passes at 1.0, expects match `"relevancy"`).
- Faithfulness flip only (`judge.py:414`, `>=` → `<`): → **2 failed** — `test_gate_trips_on_faithfulness_alone` fails (attributes faithfulness specifically; the relevancy-alone case also catches the now-tripping faithfulness assert). ✅ **KILLED**. Restored.
- Relevancy flip only (`judge.py:417`, `>=` → `<`): → **1 failed** — `test_gate_trips_on_relevancy_alone` fails, sole failure, attributing relevancy specifically. ✅ **KILLED**. Restored.

### Gap 3 — EVAL-06 link clause

- `evals/README.md` exists (created in `51c63cc`) and links the runbook: `[docs/ops/eval-calibration.md](../docs/ops/eval-calibration.md)` (last line). Link target `docs/ops/eval-calibration.md` exists. Verifier's Fix 3 verify command (`grep -rn "eval-calibration" evals/`) is non-empty. ✅ **CLOSED** — EVAL-06 AC1 now fully met.

### Full offline gate (post-fix)

- `cd backend && .venv/bin/pytest -q` (no keys): **793 passed, 401 skipped, 0 failed** (delta vs. original pass: +3, exactly the three new gate tests; skips unchanged in kind).
- `.venv/bin/ruff check .` → clean.
- Baseline `pytest tests/test_eval_judge.py -q` un-mutated: 12 passed, 1 skipped (keyed live smoke, justified).
- Tree left clean after all mutant restores (only the pre-existing untracked `.specs/features/v3-eval-maturity/` and seed `evals/results/*.jsonl` remain, both expected).

### Updated tallies

- Spec-anchored ACs: **13/13** matched (EVAL-06 link clause closed).
- Sensor: M2a ✅ killed, M2b ✅ killed in both single-flip directions (M1 remains the documented by-design survivor).
- Requirement traceability: EVAL-03 → ✅ Verified (pin + discrimination gaps closed); EVAL-06 → ✅ Verified.

**Iteration 1 verdict**: ✅ PASS — all three gaps closed, full offline gate green.
