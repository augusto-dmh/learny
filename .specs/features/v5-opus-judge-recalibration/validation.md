# v5-opus-judge-recalibration Validation

**Date**: 2026-07-31
**Spec**: `.specs/features/v5-opus-judge-recalibration/spec.md`
**Diff range**: `main...HEAD` (`feat/opus-judge-recalibration`, 7 commits `a2331d4f..c3d36131`)
**Verifier**: independent sub-agent (author ≠ verifier); evidence-or-zero, mutations in scratch only

**Verdict**: ✅ **PASS** — 21/21 acceptance criteria carry `file:line` evidence matching the spec-defined outcome (3 flagged as spec-precision gaps), 9/10 mutants killed, build gate clean apart from a declared pre-existing flake.

---

## Task Completion

| Task | Status | Notes |
| --- | --- | --- |
| T1 ADR-0028 | ✅ Done | `a2331d4f`, doc only |
| T2 Gate semantics | ✅ Done | `4df71d5d` |
| T3 Study aggregate | ✅ Done | `5ea1813a` |
| T4 Tier = snapshots | ✅ Done | `059cb763` |
| T5 Seeded Opus runs | ✅ Done | `d2797002`, 36 JSONL lines = 3 complete 12-case runs |
| T6 Derive + pin | ⚠️ Done, red in isolation | `ac1080de` carries constants+comment+pin+runbook (AC met), but left `tests/eval/test_ab.py` failing — see Code Quality |
| T7 Flip + records | ⚠️ Done, 1 item open | `c3d36131`; ROADMAP/RFC rows deferred to the publish commit (house convention, declared in tasks.md) |

---

## Spec-Anchored Acceptance Criteria

### P1-1: One decline-semantics convention (ADR-0028)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| AC1 — ADR documents the convention | answered-only means (gate+study); per-case vacuous-1.0 retained; not-found discipline as decline carrier; all-declined edge; Accepted, dated before the re-derivation commit | `docs/adr/0028-decline-answers-in-judge-aggregates.md:39-47` (gate), `:48-50` (study), `:56-59` (vacuous-1.0 retained), `:60-66` (discipline + deferral), `:81-84` (all-declined edge); Status `:4` "Accepted (2026-07-31)"; committed `a2331d4f` which precedes the re-derivation commit `ac1080de` | ✅ PASS |
| AC2 — falsy `found` ⇒ answered-only means, citation over ALL lines | means over `found` lines only; `citation_valid` asserted for every line | impl `backend/app/eval/judge.py:426` `assert all(line["citation_valid"] for line in lines)` then `:427` `answered = [line for line in lines if line.get("found", True)]`, `:430-431` means over `answered`; test `backend/tests/test_eval_judge.py:246` — `assert [line["found"] for line in lines] == [True, False, False]` under `gate=True` (a gated run with 2 declines + 1 answered relevancy-5 line passes only if means are answered-only; mutant M1 confirms) | ✅ PASS |
| AC3 — all lines declined ⇒ threshold asserts skipped, citation still runs | no mean exists ⇒ skip; citation invariant runs | impl `judge.py:428-429` `if not answered: return` placed **after** the citation assert; tests `tests/test_eval_judge.py:258-259` — `assert len(lines) == 1` / `assert client.messages.calls == []` on a gated all-declined run, and `:266-273` — `with pytest.raises(AssertionError, match="citation")` on a declined line with `citation_valid=False` | ✅ PASS |
| AC4 — `_tier_aggregate.mean_faithfulness` answered-only | averages answered lines only, mirroring `mean_relevancy` | impl `backend/app/eval/ab.py:142` `mean_faithfulness=_mean(float(line["faithfulness"]) for line in answered)`; tests `backend/tests/eval/test_ab.py:167` — `assert agg.silver.mean_faithfulness == 1.0  # only the answered line`, and `:179-181` null-score decline does not crash the aggregate | ✅ PASS |
| AC5 — `found=False` ⇒ zero judge calls, null scores | no judge calls; line `faithfulness: null, relevancy: null, found: false` | impl `judge.py:333-341` (`if item.found:` … `else: faithfulness = None; relevancy = None`), `:354` `"found": item.found`; test `tests/test_eval_judge.py:215` — `assert len(client.messages.calls) == 2` for 1 answered + 1 declined, `:217-219` — `assert declined["found"] is False` / `["faithfulness"] is None` / `["relevancy"] is None` | ✅ PASS |
| AC6 — no explicit `found` ⇒ `found: true`, judged as today | backward compatibility preserved | impl `judge.py:169` `found: bool = True`; test `tests/test_eval_judge.py:229-230` — `assert lines[0]["found"] is True` / `assert len(client.messages.calls) == 2`; schema test `:173` includes `"found"` in the required key set | ✅ PASS |

### P1-2: The gate runs on its own baseline distribution

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| AC1 — nightly judge tier = one `EvalInput` per committed snapshot via `load_snapshots()`, carrying `answer.found` + citation validity, scored via `run_eval` (max_cases applies) | 12 inputs today; found flags on the 3 `notfound-*`; citation containment | impl `backend/tests/eval/harness.py:135-154` (`snapshot_eval_inputs`, `citation_valid=set(cited) <= {retrieved}`, `found=snapshot.answer.found`); live test `tests/test_eval_judge.py:429-433` — `inputs = snapshot_eval_inputs(load_snapshots())`, `run_eval(inputs, judge=judge, max_cases=settings.eval_max_cases)`, `:436-446` asserts declines carry null scores and answered lines score in range; offline coverage `tests/eval/test_replay_harness.py:204-211` (field mapping + evidence join), `:216` (`citation_valid is False` for an out-of-evidence citation), `:222-223` (decline carried), `:231-236` — declined set == `notfound-*` set over the real committed snapshots | ✅ PASS |
| AC2 — no key ⇒ tier skips | CI stays offline/green | skipif `tests/test_eval_judge.py:411-414`; observed in the gate run: `SKIPPED [1] tests/test_eval_judge.py:413`; marker guard `:452-453` — `assert {"live", "eval"} <= marker_names` | ✅ PASS |
| AC3 — offline suite green, no live calls | `make test-backend` green with no keys | `make test-backend`: 1946 passed / 11 skipped, only the declared pre-existing HNSW flake failing (see Gate Check); all live tiers reported SKIPPED | ✅ PASS |

### P1-3: Opus baselines re-derived and pinned

| Criterion | Spec-defined outcome | Evidence | Result |
| --- | --- | --- | --- |
| AC1 — ≥3 `claude-opus-4-8` runs over all 12 snapshots, JSONL evidence, per-run means recorded | ≥3 complete runs; per-run answered-only means in the research doc | `evals/results/2026-07-31-059cb763.jsonl`: 36 lines = 3 × 12 unique case ids, every line `judge_model=claude-opus-4-8`, `generation_model=claude-sonnet-5`, `git_sha=059cb763`; 27 answered / 9 declined, nulls appear on declines only. Verifier recomputation of answered-only means: run1 F=1.0000 R=3.5556, run2 F=1.0000 R=3.4444, run3 F=1.0000 R=3.6667 — identical to `docs/research/2026-07-31/opus-judge-recalibration.md:33-35` | ✅ PASS |
| AC2 — thresholds = (mean of run means) − margin, F −0.10 @2dp, R −0.5 @1dp | derived values reproducible from the JSONL | Verifier recomputation: grand F = 1.0 → `round(1.0-0.10, 2) = 0.9`; grand R = 3.5555555… → `round(3.0555…, 1) = 3.1`. Matches `backend/app/eval/judge.py:59-60` `FAITHFULNESS_MIN = 0.90` / `RELEVANCY_MIN = 3.1` and the derivation comment `:49-58` (quotes 3.56/3.44/3.67, grand mean 3.556 — all confirmed) | ✅ PASS |
| AC3 — constants + comment + pin test + runbook in the same commit | one commit | `ac1080de` touches exactly `backend/app/eval/judge.py` (constants + comment), `backend/tests/test_eval_judge.py` (pin), `docs/ops/eval-calibration.md` (baseline table `:26-30`). Pin assertions `tests/test_eval_judge.py:369-370` — `assert FAITHFULNESS_MIN == 0.90` / `assert RELEVANCY_MIN == 3.1` | ✅ PASS |
| AC4 — pre-flight estimate under $10, actual reported against it | both recorded | `docs/research/2026-07-31/opus-judge-recalibration.md:65-71` — estimate 54 calls ≤ $2.20, actual ≈ $0.31 (worst-case bound ~$1.55), both under the $10 ceiling. Call count is consistent with the evidence (3 runs × 9 answered × 2 calls = 54) | ⚠️ Spec-precision gap — the estimate exists only inside the post-hoc research doc; no artifact timestamps it *before* the first paid call, so "a pre-flight estimate SHALL exist" is attested rather than independently verifiable |

### P1-4: Flip-or-stay, decided and recorded

| Criterion | Spec-defined outcome | Evidence | Result |
| --- | --- | --- | --- |
| AC1 — decision rule applied (instability / degeneracy / budget) | FLIP unless a trigger fires | Verifier recomputation from the JSONL: faithfulness range 0.0000 (≤ 0.10), relevancy range 0.2222 (≤ 0.5) ⇒ no instability; derived 0.90 ≥ 0.50 and 3.1 > 1.0 ⇒ no degeneracy; projected nightly 18 calls ≈ $0.10 ≤ $0.50 ⇒ no budget trigger. Rule table `docs/research/2026-07-31/opus-judge-recalibration.md:55-59` reproduces the same numbers | ⚠️ Spec-precision gap — "projected nightly cost" is undefined as realistic-vs-worst-case; the doc's own worst case ($0.51, `:72-73`) sits just over the $0.50 trigger. Realistic projection is the reasonable reading and the margin is not decision-changing, but the rule's wording admits both |
| AC2 — FLIP ⇒ `settings.judge_model` default = `claude-opus-4-8` + config pins updated | default flipped, pin test updated | `backend/app/core/config.py:213` `judge_model: str = "claude-opus-4-8"`; pin `backend/tests/test_config.py:78` — `assert settings.judge_model == "claude-opus-4-8"`. `.github/workflows/eval.yml` sets no `LEARNY_JUDGE_MODEL`, so the nightly picks up the new default | ✅ PASS |
| AC3 — STAY branch | n/a (decision was FLIP) | — | n/a |
| AC4 — research doc records runs/arithmetic/rule/decision/spend; ROADMAP + RFC Cycle B rows updated | all five doc elements + both rows | Doc: runs `:29-37`, derivation `:46-49`, rule `:51-59`, decision `:3-5`/`:61`, spend `:63-73` — all present. **Rows not updated**: `.specs/project/ROADMAP.md:105` still reads "Paused (queued behind RFC-006)" and `docs/rfc/0005-*.md:47` (Cycle B) carries no completion status | ⚠️ Partially open — declared in `tasks.md:8` as riding the publish commit (house convention: the PR number exists only at publish). Not a code defect; must land before the cycle closes |

**Status**: ✅ 21/21 criteria carry evidence; 3 flagged (2 spec-precision, 1 deferred-by-convention). No criterion is uncovered.

---

## Discrimination Sensor

Sensor depth: lightweight+ (10 behavior-level mutations, one per load-bearing invariant). Each mutation was written into the real file, its covering tests run, and the file restored unconditionally in a `finally` block; `git status --porcelain backend/` verified CLEAN after every batch.

| # | File:line | Mutation | Killed? | Killed by |
| --- | --- | --- | --- | --- |
| M1 | `backend/app/eval/judge.py:427` | `answered = [… if line.get("found", True)]` → `answered = list(lines)` (declines back into the means) | ✅ Killed | `test_gate_means_exclude_declined_lines`, `test_gate_all_declined_skips_threshold_asserts` |
| M2 | `backend/app/eval/judge.py:426-429` | citation assert moved **after** the all-declined early return | ✅ Killed | `test_gate_all_declined_still_asserts_citation_validity` |
| M3 | `backend/app/eval/judge.py:333` | `if item.found:` → `if True:` (declines judged anyway) | ✅ Killed | `test_run_eval_skips_judge_calls_for_declined_cases` + 3 others |
| M4 | `backend/app/eval/ab.py:142` | `mean_faithfulness` back over all scored lines | ✅ Killed | `test_quality_means_exclude_declined_lines`, `test_declined_lines_with_null_scores_do_not_crash_the_aggregate` |
| M5 | `backend/tests/eval/harness.py:152` | `found=snapshot.answer.found` → `found=True` (decline flag dropped in the tier mapping) | ✅ Killed | `test_snapshot_eval_inputs_carry_the_declined_outcome`, `test_committed_snapshots_map_with_expected_found_flags` |
| M6 | `backend/app/eval/judge.py:427` | `line.get("found", True)` → `line.get("found", False)` (archived-line default flipped) | ❌ **Survived** | — (109 passed, 4 skipped over `tests/test_eval_judge.py tests/eval`) |
| M7 | `backend/app/eval/judge.py:60` | `RELEVANCY_MIN = 3.1` → `2.8` (silently disarm the recalibrated gate) | ✅ Killed | `test_gate_constants_pin_the_calibrated_baselines` |
| M8 | `backend/app/core/config.py:213` | `judge_model` default → `claude-haiku-4-5` (silently un-flip) | ✅ Killed | `test_generation_settings_defaults` |
| M9 | `backend/app/eval/judge.py:169` | `EvalInput.found: bool = True` → `False` (AC P1-1-6 backward compat) | ✅ Killed | `test_run_eval_marks_answered_lines_found_true_by_default` |
| M10 | `backend/app/eval/ab.py:132` | `line.get("found", True)` → `False` in the study aggregate (archived-line readability) | ✅ Killed | `test_quality_means_exclude_declined_lines` |

**Result**: 9/10 killed — ✅ PASS with one Minor fix task.

**M6 analysis (why this is Minor, not a blocking gap)**: `_assert_aggregates` has exactly one caller — `run_eval` at `judge.py:361` — and `run_eval` always writes a `found` key (`judge.py:354`). The `.get("found", True)` default is therefore defensive-only and unreachable from any production path, which is why no test pins it. ADR-028's archived-results claim (`:75-77`) is about reading historical JSONL, and that path lives in `ab.py:132`, where the equivalent mutation (M10) **is** killed. The un-pinned default is a documentation-vs-code drift risk, not a live behavior gap.

---

## Edge Cases

- [x] **`run_eval` with zero inputs** — unchanged: `judge.py:423` `if not lines: return` is untouched by this diff (`git diff main...HEAD` shows no change to that guard). ⚠️ No direct test exists (`run_eval([])` appears nowhere in `tests/test_eval_judge.py`) — a pre-existing coverage hole, not a regression introduced here.
- [x] **Seed run dies mid-pass** — not exercised: all three runs are complete 12-case passes (36 lines, 3 timestamp clusters 16:31:05–16:33:46, 12 unique case ids each). No partial run needed excluding.
- [x] **`prompt_hash` drift blocks derivation** — `prompt_hash()` evaluated live = `211d9d8c8db49ac171a4ee398627023177fa76fa03697275c21eadfcc9928870`, identical to the runbook pin `docs/ops/eval-calibration.md:70` and to every one of the 36 evidence lines. The rubric had not drifted; the experiment is valid.

---

## Code Quality

| Principle | Status |
| --- | --- |
| Minimum code | ✅ — one flag on `EvalInput`, one branch in `run_eval`, one filter in each aggregate |
| Surgical changes | ✅ — files touched match `tasks.md` scope exactly; no unrelated edits in the diff |
| No scope creep | ✅ — no new dependency, no new provider SDK (ADR-0019/0020 respected), prompts frozen (`prompt_hash` unchanged) |
| Matches patterns | ✅ — reuses the existing `ab._mean` None-on-empty precedent and the established live-skip/marker-guard pattern |
| Spec-anchored outcome check | ✅ — asserted values match spec outcomes; 2 spec-precision gaps flagged above |
| Per-layer Coverage Expectation | ✅ — domain logic 1:1 to ACs (`judge.py`, `ab.py`, `harness.py` each have AC-mapped unit tests); no routes in scope |
| Every test maps to a requirement — no unclaimed tests | ✅ — the 12 new/renamed tests map to P1-1 AC2–6, P1-2 AC1–2, P1-3 AC3, P1-4 AC2 |
| Documented guidelines followed | ✅ — `CLAUDE.md` verification vocabulary used; `make lint` (ruff + tsc + boundaries) clean |

**Findings (non-blocking):**

1. **`ac1080de` is red in isolation (bisectability).** T6's Done-when claims "Quick gate passes", but the quick gate is `pytest tests/test_eval_judge.py tests/eval -q` and `tests/eval/test_ab.py`'s two gate-flip tests still encoded `RELEVANCY_MIN = 2.8` at that commit; their update rode T7 (`c3d36131`). Reproduced by replaying `test_ab.py@ac1080de` against the (identical) `app/` source at HEAD: **2 failed, 27 passed** — `test_gate_flip_counts_disagreement_on_passing_the_gate` and `test_no_gate_flip_when_both_judges_pass`. HEAD is green; only `git bisect` across this branch is affected.
2. **`backend/.env.example:63` still pins `LEARNY_JUDGE_MODEL=claude-haiku-4-5`.** That file's convention is to mirror the code defaults (`LEARNY_GENERATION_MODEL=claude-sonnet-5`, `LEARNY_EVAL_MAX_CASES=50` both match `config.py`), so after the flip this line contradicts the new default and silently overrides it for anyone who copies the example — this is exactly why `get_settings().judge_model` resolves to `claude-haiku-4-5` on the dev box. Neither the nightly (`.github/workflows/eval.yml` sets no override) nor production (`.env.production.example` has no judge line) is affected. Outside the letter of AC P1-4-2, but inside its intent.

---

## Gate Check

| Gate | Command | Exit | Result |
| --- | --- | --- | --- |
| Scoped (lead-suggested) | `uv run pytest tests/test_eval_judge.py tests/eval tests/test_config.py tests/test_generation_invariants.py -q` | 0 | 162 passed, 5 skipped |
| Build — lint | `make lint` | 0 | ruff check + format clean (246 files), `tsc --noEmit` clean, architecture boundaries clean |
| Build — tests | `make test-backend` | 2 | **1946 passed, 11 skipped, 1 failed** |

- **Test count before feature**: 1929 passed / 11 skipped (baseline recorded in `tasks.md:38`). **After**: 1946 / 11. **Delta: +17 passed**, skips unchanged — no net test deletion; `test_live_judge_scores_one_case` was replaced by the strictly broader `test_live_judge_scores_replay_snapshots`, and `test_relevancy_mean_excludes_declined_lines` was renamed/strengthened to `test_quality_means_exclude_declined_lines`. No assertion was weakened: the two `test_ab.py` threshold-expectation edits track the recalibrated constant, and `test_gate_constants_pin_*` still pins exact values.
- **Failure**: `tests/test_eval_retrieval_metrics.py::TestDeterministicRetrievalMetrics::test_metrics_meet_thresholds` — `assert 0.8571428571428571 >= 0.9` (recall@1). **Not attributable to this cycle**: the file is absent from the diff surface, the failure is in deterministic retrieval recall with no dependency on `judge.py` / `ab.py` / the `judge_model` default, and it was declared pre-existing (local HNSW behavior; green in CI). Reproduced standalone here, so it is deterministic locally rather than intermittent.
- **Skips (all justified)**: 5 live-tier skips gated on absent `LEARNY_ANTHROPIC_API_KEY` / `LEARNY_OPENAI_API_KEY` (the expected offline behavior, and the evidence for P1-2 AC2), 1 snapshot-recorder skip gated on `--record-generation`, plus the pre-existing generation-invariant skip. No live or paid selection was run by this verification.

---

## Fix Plans

### Fix 1 — Pin the archived-line `found` default in the gate (Minor)

- **Root cause**: `_assert_aggregates`'s `line.get("found", True)` (`judge.py:427`) is defensive against archived JSONL lines that predate the `found` field, but its only caller always writes `found`, so no test constrains it — mutant M6 survives.
- **Fix task**: add one unit test calling `_assert_aggregates` directly (or `run_eval` post-processing) with a legacy-shaped line lacking `found` and passing scores, asserting the thresholds are enforced rather than skipped.
- **Priority**: Minor — no reachable behavior change today; protects ADR-028's archived-results claim.

### Fix 2 — Land the ROADMAP + RFC-005 Cycle B row updates (Major, publish-blocking)

- **Root cause**: deliberately deferred to the publish commit (`tasks.md:8`), so AC P1-4-4 is only half-satisfied at verification time.
- **Fix task**: in the publish commit, set `.specs/project/ROADMAP.md:105` off "Paused (queued behind RFC-006)" and mark RFC-005 Cycle B (`docs/rfc/0005-*.md:47`) complete with the PR reference.
- **Priority**: Major — the cycle cannot close without it.

### Fix 3 — Sync `backend/.env.example` to the flipped default (Minor)

- **Root cause**: `.env.example:63` mirrors code defaults by convention but still names `claude-haiku-4-5`, silently overriding the new default for anyone who copies it.
- **Fix task**: update the line to `claude-opus-4-8` (nightly and production are unaffected either way).
- **Priority**: Minor.

---

## Requirement Traceability Update

Proposed `spec.md` status transitions (not applied — the Verifier does not mutate the spec):

| Requirement | Previous | New |
| --- | --- | --- |
| RECAL-01 ADR-0028 | Pending | ✅ Verified |
| RECAL-02 Gate answered-only + all-declined edge | Pending | ✅ Verified |
| RECAL-03 `EvalInput.found` + decline skip + schema | Pending | ✅ Verified |
| RECAL-04 Study aggregate unification | Pending | ✅ Verified |
| RECAL-05 Nightly tier = snapshots | Pending | ✅ Verified |
| RECAL-06 ≥3 seeded runs + evidence + budget | Pending | ✅ Verified (spend estimate attested, not independently timestamped) |
| RECAL-07 Derivation + same-commit pinning | Pending | ✅ Verified (arithmetic independently reproduced) |
| RECAL-08 Flip-or-stay rule + config outcome | Pending | ✅ Verified |
| RECAL-09 Research doc + ROADMAP/RFC rows | Pending | ⚠️ Partial — research doc done; rows pending the publish commit |
| RECAL-10 Compliance (no new SDK, prompts frozen, offline green) | Pending | ✅ Verified |

---

## Lessons (protocol note)

The sensor produced signal (1 surviving mutant, M6) and 2 spec-precision gaps, which under `validate.md` §10 warrants a recorded lesson. The Verifier's brief constrains the working tree to `validation.md` only, and `.claude/skills/tlc-spec-driven/scripts/lessons.py` writes tracked files (`.specs/LESSONS.md`, `.specs/lessons.json`). **No lesson was recorded**; the orchestrator should record it. Proposed text: *"A `.get(key, default)` fallback whose only caller always writes the key is untestable through the public path — either pin it with a direct unit test or delete it, or a mutation of the default survives."*

---

## Summary

**Overall**: ✅ Ready (with 3 non-blocking fix tasks, one of which — the ROADMAP/RFC rows — must land at publish)

**Spec-anchored check**: 21/21 ACs evidenced; 2 spec-precision gaps, 1 deferred-by-convention item
**Sensor**: 9/10 mutations killed
**Gate**: `make lint` exit 0; `make test-backend` 1946 passed / 11 skipped / 1 pre-existing unrelated failure; scoped suite 162 passed exit 0

**What works**: The decline convention is enforced in code rather than assumed in a comment — declines are never judge-called, carry null scores, stay out of both means in both the gate and the study, and the citation invariant still covers them (including on an all-declined run, where the threshold asserts correctly skip). The nightly tier is now the 12 committed snapshots, so gate and thresholds share one distribution. The pinned constants (`0.90` / `3.1`) reproduce exactly from the committed JSONL under the runbook's mean−margin rule, and the flip's decision rule evaluates to FLIP on independently recomputed numbers (ranges 0.0000 / 0.2222).

**Issues found**: (1) M6 — untested defensive `found` default in `_assert_aggregates`; (2) ROADMAP/RFC Cycle B rows not yet updated; (3) `.env.example` still pins the old judge model; (4) `ac1080de` is red in isolation, breaking `git bisect` across this branch.

**Next steps**: land Fix 2 with the publish commit; Fix 1 and Fix 3 are cheap one-liners that can ride the same PR or a follow-up.
