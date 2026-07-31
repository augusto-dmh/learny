# v5-opus-judge-recalibration Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** If the skill cannot be activated, STOP.

**Design**: `.specs/features/v5-opus-judge-recalibration/design.md`
**Status**: Done — T1 `a2331d4f`, T2 `4df71d5d`, T3 `5ea1813a`, T4 `059cb763`, T5 `d2797002`, T6 `ac1080de`, T7 `c3d36131`. Decision: FLIP to `claude-opus-4-8`. Note: T7's ROADMAP/RFC row updates ride the publish commit (house convention — the PR number exists only at publish). Full-suite failures during gates: only the pre-existing local HNSW retrieval flake (reproduced identically on clean `main`; green in CI).

---

## Test Coverage Matrix

> Guidelines found: `CLAUDE.md` (Makefile verification vocabulary; ruff + tsc lint gates), existing eval suites `backend/tests/test_eval_judge.py` (17), `backend/tests/eval/` (81).

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
|---|---|---|---|---|
| `app/eval/judge.py` (gate semantics) | unit (fake client, no network) | All branches; 1:1 to spec ACs (P1-1 AC 2,3,5,6); all-declined + backward-compat edges | `backend/tests/test_eval_judge.py` | `cd backend && uv run pytest tests/test_eval_judge.py -q` |
| `app/eval/ab.py` (study aggregate) | unit | Answered-only faithfulness branch + None-mean edges (P1-1 AC 4) | `backend/tests/eval/test_ab.py` | `cd backend && uv run pytest tests/eval/test_ab.py -q` |
| `tests/eval/harness.py` (snapshot→EvalInput) | unit (offline) | Mapping 1:1 to P1-2 AC 1: found flags on `notfound-*`, citation containment, evidence join | `backend/tests/eval/test_replay_harness.py` | `cd backend && uv run pytest tests/eval/test_replay_harness.py -q` |
| Live tier test (markers/skip wiring) | offline guard tests | Marker enrollment + skip-without-key asserted offline | `backend/tests/test_eval_judge.py` | same as judge |
| ADR/runbook/research docs, config default | none — build gate only | — | `docs/**`, `app/core/config.py` (pin tests exist: `tests/test_config.py`) | `make lint` |

## Parallelism Assessment

| Test Type | Parallel-Safe? | Isolation Model | Evidence |
|---|---|---|---|
| backend pytest | No (run sequentially, single command) | Shared test DB for `requires_db`; suite runs as one `uv run pytest` | `Makefile` `test-backend`; no xdist config |

All tasks run sequentially; `[P]` marks order-freedom only.

## Gate Check Commands

| Gate Level | When to Use | Command |
|---|---|---|
| Quick | After T2/T3/T4 (module scope) | `cd backend && uv run pytest tests/test_eval_judge.py tests/eval -q` |
| Full | Phase boundary | `make test-backend` (needs `make infra` first; baseline 1929 passed / 11 skipped, +new) |
| Build | Before publish | `make check` |

---

## Execution Plan

```
Phase 1 (offline):   T1 → T2 → T3 [P] , T4 [P]
Phase 2 (keyed):     T5 → T6 → T7
Verifier: fresh subagent after T7
```

---

## Task Breakdown

### T1: ADR-0028 — decline answers in judge aggregates

**What**: Write `docs/adr/0028-decline-answers-in-judge-aggregates.md` (Accepted, 2026-07-31) per design §ADR-0028.
**Where**: `docs/adr/0028-decline-answers-in-judge-aggregates.md`
**Depends on**: None
**Reuses**: ADR house style (`docs/adr/0027-*.md` et al.)
**Requirement**: RECAL-01

**Done when**:
- [ ] Documents: answered-only means in gate + study; per-case vacuous-1.0 retained; not-found discipline as decline carrier (gate adoption deferred, with trigger); all-declined edge; the Opus-0.0 observation as motivation.
- [ ] `make lint` clean.

**Tests**: none (doc) | **Gate**: build
**Commit**: `docs: adopt one decline convention for judge aggregates`

### T2: Gate semantics — `EvalInput.found`, decline skip, answered-only asserts

**What**: judge.py per design §judge.py; update/extend `tests/test_eval_judge.py` per matrix.
**Where**: `backend/app/eval/judge.py`, `backend/tests/test_eval_judge.py`
**Depends on**: T1
**Reuses**: `ab._mean` None-on-empty precedent
**Requirement**: RECAL-02, RECAL-03, RECAL-10

**Done when**:
- [ ] ACs P1-1 2/3/5/6 each have an asserting test; declines make zero judge calls (asserted via fake client call count).
- [ ] Quick gate passes; no existing assertion weakened.

**Tests**: unit | **Gate**: quick
**Commit**: `feat(eval): exclude declined answers from judge gate aggregates`

### T3: Study aggregate unification [P]

**What**: `ab._tier_aggregate.mean_faithfulness` → answered-only; docstrings; `test_ab.py` expectations re-derived by hand.
**Where**: `backend/app/eval/ab.py`, `backend/tests/eval/test_ab.py`
**Depends on**: T2 (line schema carries `found`)
**Reuses**: existing `answered` list (ab.py:130)
**Requirement**: RECAL-04

**Done when**:
- [ ] AC P1-1 4 asserted; 28 test_ab tests still pass (values updated deliberately, count not reduced).
- [ ] Quick gate passes.

**Tests**: unit | **Gate**: quick
**Commit**: `feat(eval): align study faithfulness aggregate with the decline convention`

### T4: Widen the nightly judged tier to the replay snapshots [P]

**What**: `harness.snapshot_eval_inputs()`; replace `test_live_judge_scores_one_case` with `test_live_judge_scores_replay_snapshots`; offline mapping tests; keep markers/skip/results-dir behavior; marker-guard tests stay green.
**Where**: `backend/tests/eval/harness.py`, `backend/tests/eval/test_replay_harness.py`, `backend/tests/test_eval_judge.py`
**Depends on**: T2
**Reuses**: `load_snapshots`, citation-containment rule from `test_generation_invariants.py`, live-smoke skip pattern
**Requirement**: RECAL-05, RECAL-10

**Done when**:
- [ ] P1-2 ACs 1–3: mapping unit-tested offline (3 `notfound-*` → `found=False`; citation containment; evidence join); live test carries `live`+`eval` markers + skipif.
- [ ] Full gate passes offline with no live calls (phase boundary).

**Tests**: unit + offline guards | **Gate**: full (phase boundary)
**Commit**: `feat(eval): judge the committed replay snapshots as the nightly tier`

### T5: Seeded Opus judge runs (evidence)

**What**: Pre-flight: verify `prompt_hash()` matches the runbook pin and estimate cost vs the $10 ceiling; then 3× `LEARNY_JUDGE_MODEL=claude-opus-4-8 uv run pytest tests/test_eval_judge.py -m "live and eval" -q` (gate off locally); commit the appended `evals/results/*.jsonl`.
**Where**: `evals/results/` (tracked)
**Depends on**: T4
**Reuses**: runbook budget protocol (eval-calibration.md:143-165)
**Requirement**: RECAL-06

**Done when**:
- [ ] ≥3 complete 12-case Opus runs in the JSONL (`judge_model` on every line); per-run answered-only means computed; spend actual-vs-estimate recorded (goes into T7's research doc).
- [ ] Never the bare `-m "live and eval"` selection (silver/retrieval cost trap).

**Tests**: none (evidence artifact) | **Gate**: none (no code)
**Commit**: `chore(eval): record opus judge seed runs over the replay tier`

### T6: Derive and pin thresholds

**What**: Apply mean−margin rule to T5 means; update `FAITHFULNESS_MIN`/`RELEVANCY_MIN` + derivation comment (judge.py:44-61), pinning test (test_eval_judge.py:269), runbook baseline table + step-2 command (file-targeted) + snapshot-staleness flag (AD-228).
**Where**: `backend/app/eval/judge.py`, `backend/tests/test_eval_judge.py`, `docs/ops/eval-calibration.md`
**Depends on**: T5
**Requirement**: RECAL-07

**Done when**:
- [ ] P1-3 AC 2/3: derivation arithmetic reproducible from committed JSONL; constants+comment+pin+runbook in ONE commit.
- [ ] Quick gate passes.

**Tests**: unit (pin) | **Gate**: quick
**Commit**: `feat(eval): recalibrate judge gate thresholds from opus baselines`

### T7: Flip-or-stay + research record

**What**: Evaluate RECAL-08 rule on T5/T6 data; if FLIP: `config.py` `judge_model` default → `claude-opus-4-8` + `test_config.py` pins (same commit as constants stays satisfied — T6 constants already Opus-derived; if STAY, revert constants decision per rule). Write `docs/research/2026-07-31/opus-judge-recalibration.md` (runs, arithmetic, rule evaluation, decision, spend). Update ROADMAP Cycle B row + RFC-005 Cycle B status.
**Where**: `backend/app/core/config.py`, `backend/tests/test_config.py`, `docs/research/2026-07-31/`, `.specs/project/ROADMAP.md`, `docs/rfc/0005-*.md`
**Depends on**: T6
**Requirement**: RECAL-08, RECAL-09

**Done when**:
- [ ] Rule mechanically evaluated against recorded means; outcome applied; docs updated; full gate + `make lint` pass.

**Tests**: unit (config pins) | **Gate**: full + build
**Commit**: `feat(eval): switch the nightly judge to opus` (or `docs: record the judge stay decision with opus baselines`)

---

## Task Granularity Check

| Task | Scope | Status |
|---|---|---|
| T1 | 1 doc | ✅ |
| T2 | 1 module + its test file | ✅ |
| T3 | 1 function + its test file | ✅ |
| T4 | 1 helper + 1 test replacement (cohesive tier change) | ✅ |
| T5 | 1 evidence artifact | ✅ |
| T6 | 1 constants change + its doc/pin | ✅ |
| T7 | 1 decision + its records | ✅ |

## Diagram-Definition Cross-Check

| Task | Depends On (body) | Diagram | Status |
|---|---|---|---|
| T1 | None | start | ✅ |
| T2 | T1 | T1→T2 | ✅ |
| T3 | T2 | T2→T3 [P] | ✅ |
| T4 | T2 | T2→T4 [P] | ✅ |
| T5 | T4 | T4→T5 | ✅ |
| T6 | T5 | T5→T6 | ✅ |
| T7 | T6 | T6→T7 | ✅ |

T3 and T4 share no files and no dependency on each other → valid `[P]` (executed sequentially anyway per Parallelism Assessment).

## Test Co-location Validation

| Task | Layer | Matrix Requires | Task Says | Status |
|---|---|---|---|---|
| T1 | docs | none | none | ✅ |
| T2 | judge.py | unit | unit | ✅ |
| T3 | ab.py | unit | unit | ✅ |
| T4 | harness + live wiring | unit + offline guards | unit + guards | ✅ |
| T5 | evidence data | none | none | ✅ |
| T6 | constants (+pin test) | unit | unit | ✅ |
| T7 | config default (+pin test) | unit | unit | ✅ |
