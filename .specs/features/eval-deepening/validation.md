# Eval Deepening Validation

**Date**: 2026-07-21
**Spec**: `.specs/features/eval-deepening/spec.md`
**Diff range**: `main...feat/eval-deepening` (implementation commits `b97add6, dcc7921, 0ff1911, 775d348, 2fcd7e7, aadde11, 124986f, d7432c3, 383f7be, dc30318` + .specs commits)
**Verifier**: independent sub-agent (author ≠ verifier); evidence-or-zero. No provider calls were made: all study ACs verified from committed artifacts, local git-ignored artifacts, and recomputation with the real `ab.py` functions over the real result lines.

---

## Task Completion

| Task | Status | Notes |
| --- | --- | --- |
| T1 (`b97add6`) | ✅ Done | ignore rule + 4 hygiene tests |
| T2 (`dcc7921`) | ✅ Done | loader + 14 tests |
| T3 (`0ff1911`) | ✅ Done | resolver + 6 integration tests |
| T4 (`775d348`) | ✅ Done | exec/writer/runner + 17 tests |
| T5 (`2fcd7e7`) | ✅ Done | rubric + constant + pin + doc, atomic in one commit |
| T6 (`aadde11`) | ✅ Done | aggregates + tests |
| T7 (`124986f`) | ✅ Done | agreement/verdicts + tests |
| T8 (local) | ✅ Done | 12 cases / 6 books / 5 PT + 7 EN, all 12 resolve runnable vs app DB (verified live, read-only) |
| T9 (`d7432c3`) | ✅ Done | 72 tracked golden lines + 48 local silver lines; see note N2 |
| T10 (`383f7be`, `dc30318`) | ✅ Done | research doc + ROADMAP row; judge switch isolated in `dc30318` |

---

## Spec-Anchored Acceptance Criteria

All numeric study claims below were independently recomputed by running `app.eval.ab.aggregate` / `judge_agreement` / `judge_verdict` / `generation_verdict` over the actual 72 tracked golden lines + 48 local silver lines; every figure in the research doc reproduced exactly.

| Requirement | Spec-defined outcome | Evidence + assertion | Result |
| --- | --- | --- | --- |
| DEEP-01 | Runner resolves checksum+anchor, runs retrieve/generate/judge, appends one JSONL line per case under `evals/silver/results/` | `backend/tests/eval/silver.py:218-275` (resolve), `:341-383` (run); `backend/tests/eval/test_silver_resolution.py:121-133` — `assert isinstance(resolved, ResolvedCase)` + source/chunk ids; `backend/tests/eval/test_silver_run.py:86-111` — full ok-line schema asserted field-by-field; live runner `backend/tests/eval/test_silver.py:43-109`; real 48-line file exists at `evals/silver/results/2026-07-22T001350-124986f-ff077281.jsonl` | ✅ PASS (see N2) |
| DEEP-02 | Missing book → per-case skip with reason, run continues | `silver.py:236-240` returns `SkippedCase(reason=…)`; `test_silver_resolution.py:136-148` — `assert isinstance(result, SkippedCase)` + checksum in reason; `test_silver_run.py:225-257` — `skipped["reason"] == "book absent"`, distinct status | ✅ PASS |
| DEEP-03 | Absent data → clean pytest skip, no provider call attempted | `test_silver.py:36-38` module-level skip before any provider import; `test_silver_run.py:315-328` — `pytest.raises(pytest.skip.Exception)` on import AND `"anthropic" not in sys.modules` / `"openai" not in sys.modules`; full-gate run shows `SKIPPED tests/eval/test_silver.py:38` with data present but key unset | ✅ PASS |
| DEEP-04 | 10–20 cases, ≥3 books, both languages, all required fields | Local `evals/silver/cases.yaml`: 12 cases, 6 distinct checksums (books), languages {portuguese: 5, english: 7}, snippets ≤20 words; loader validated it and all 12 resolved `ResolvedCase` against the app DB (verifier's read-only run); schema enforcement `test_silver_loader.py:85-136` | ✅ PASS |
| DEEP-05 | Nothing under `evals/silver/` tracked or staged | `git check-ignore -v` → `.gitignore:15 evals/silver/` for cases + results; `git ls-files evals/` shows no silver path; `git log main..HEAD --name-only -- evals/` touches only the tracked golden file; `git status --porcelain` clean with data on disk; `test_silver_hygiene.py:38-55` (incl. golden-stays-tracked guard) | ✅ PASS |
| DEEP-06 | One exemplar per score 1–5; `prompt_hash()` changes | `backend/app/eval/prompts/relevancy.md` diff adds `### Score 1–5 example` blocks; verifier recomputed hashes: main bytes → `7a1437…`, HEAD → `211d9d…` (matches calibration doc exactly); `test_eval_judge.py:290-303` — `assert exemplified == [1, 2, 3, 4, 5]` | ✅ PASS |
| DEEP-07 | New relevancy baseline recorded with the 2026-07-18 derivation (baseline − margin) | `docs/ops/eval-calibration.md` §"Relevancy re-derivation (2026-07-21)": per-case 12×3 table; verifier recomputed answered-case means from that table: 3.444/3.222/3.222 → ~3.3; 3.3 − 0.5 = 2.8 ✓; old/new prompt_hash recorded | ✅ PASS |
| DEEP-08 | `RELEVANCY_MIN` + pinning test updated in the same commit | `judge.py:61` `RELEVANCY_MIN = 2.8`; `test_eval_judge.py:287` `assert RELEVANCY_MIN == 2.8`; `git show 2fcd7e7 --stat` contains both files (plus rubric + doc) in one commit; gate semantics otherwise untouched | ✅ PASS |
| DEEP-09 | Deterministic suite green without provider keys | Full gate (providers `local`, no keys in env): **1649 passed, 11 skipped**, exit 0; ruff clean, exit 0 | ✅ PASS |
| DEEP-10 | Both judges score identical outputs (12 replayed + silver), persisted golden→`evals/results/`, silver→`evals/silver/results/` | Tracked file: 72 lines, judge counts {haiku: 36, opus: 36}; silver file: 48 lines, {haiku: 24, opus: 24}; recomputed pairing n = 60 (24 A/B golden + 12 replay + 24 silver items), all lines `prompt_hash 211d9d…` | ✅ PASS |
| DEEP-11 | Doc has per-judge distributions, exact + within-1 agreement, keep/switch recommendation | `docs/research/2026-07-21/eval-deepening-ab.md:81-133`; recomputed from lines: exact 0.6833, within-1 0.9667, flips 8, distributions Haiku {1:10, 2:5, 3:12, 4:9, 5:24} / Opus {1:9, 2:2, 3:8, 4:13, 5:28} — all match the doc exactly; explicit switch recommendation present | ✅ PASS (see N1) |
| DEEP-12 | `judge_model` stays haiku absent material disagreement | Material disagreement present per AD-165 (8 gate flips; recomputed `judge_verdict` = `"switch"`), so the AC's condition does not bind; switch isolated in `dc30318` (`config.py` + `test_config.py:47` only) with rationale + human-override option surfaced in the doc | ✅ PASS |
| DEEP-13 | Both models answer identical case set over identical evidence, judged by anchored judge | Recomputed: identical golden fresh case sets across arms (12=12) and identical silver case sets (12=12); all 120 scorings carry the anchored hash; evidence-identity per case is not re-derivable from the persisted lines (no evidence ids recorded) — accepted from the doc's method statement; single write timestamp consistent with one driver run | ✅ PASS (bounded, N3) |
| DEEP-14 | Doc under `docs/research/2026-07-21/` with per-model faithfulness/relevancy/citation/not-found split golden vs silver, cost-per-answer, explicit decision | Doc metric table `:58-64` — every cell reproduced by `aggregate()` (e.g. Sonnet silver faith 0.9907 vs Opus 0.9861, relevancy 4.917 vs 5.000, nfd 3/3 both); modeled cost stated; explicit decisions §Decisions | ✅ PASS |
| DEEP-15 | Config default matches the decision; flip in own commit referencing the doc | `generation_verdict` recomputed = `"stay"` → `generation_model = "claude-sonnet-5"` unchanged in `config.py:173`; judge flip (per `"switch"`) in own commit `dc30318` whose config comment cites the research doc path; no internal IDs in the commit | ✅ PASS |
| DEEP-16 | No copyrighted passages beyond ≤25-word attributed quotes in tracked files | Tracked golden JSONL: max field length 64 chars (the hash) — ids/scores/flags only, tier all `golden`, only synthetic + `replay-` case ids; research doc quotes counted: 18/19/12/13 words, each attributed; silver test fixtures use invented sentences | ✅ PASS |
| DEEP-17 | Malformed judge output → visible error line, never silently scored | `silver.py:368-369` catch → `{"status": "error", "error": …}`; `test_silver_run.py:147-178` — `line["status"] == "error"`, `"faithfulness" not in line`; load-leg analog `SilverCaseError` `test_silver_loader.py:76-153` | ✅ PASS |
| DEEP-18 | Broken anchor → broken, distinct from skip | `silver.py:268` returns `BrokenCase` naming the anchor + source id; `test_silver_resolution.py:193-220` — `isinstance(result, BrokenCase)`, `result.anchor == "ch99.xhtml"`, source id present; four-distinct-statuses test `test_silver_run.py:225-257` | ✅ PASS |
| DEEP-19 | Empty retrieval → still generated + judged, `retrieved_empty` on the line | `silver.py:381` sets the flag; `test_silver_run.py:130-141` — `status == "ok"` and `retrieved_empty is True` | ✅ PASS |
| DEEP-20 | Completed results survive mid-run provider failure; rerun writes a new file, never corrupts a prior one | Provider failure → per-case error line, run continues (`test_silver_run.py:181-194` — `"529" in line["error"]`); fresh-file-per-run with exclusive-create `"x"` (`silver.py:417-418`); `test_silver_run.py:263-279` — second run same date+sha yields a distinct file and the first file's bytes are unchanged | ✅ PASS (see N4) |

**Status**: ✅ All 20 ACs covered; 0 spec-precision gaps; 4 bounded/precision notes (N1–N4, none blocking).

### Notes

- **N1 (minor doc imprecision, non-blocking).** The flip anatomy in the research doc says the 6 relevancy-gate flips have "raw scores differ by one point". Recomputation shows 4 of the 6 differ by one (2↔3) and 2 differ by two (Haiku 2 vs Opus 4: `printing-spread-books`/opus-arm and `tides-spring-alignment`/sonnet-arm — exactly the two pairs behind within-1 = 58/60). All flips are correctly relevancy-gate bisections (one judge ≤2, other ≥3), the counts, rates, and both verdicts are exact, and the doc's own "disagreements are almost entirely ±1" remains true. Wording nit only.
- **N2 (bounded without spend).** The 48-line silver results file carries the Phase D study driver's line shape (`found`/`expected_not_found` per the T9 producer contract) rather than `run_silver_case`'s exact ok-line schema (`source_id`/`retrieved_empty`/`expected_chunk_hit` absent). So the live silver smoke ran through the A/B driver, not the committed pytest runner; the committed runner's behavior is fully verified deterministically (fakes + integration), and its self-skip is verified in the real gate run, but no on-disk artifact evidences a live invocation of `test_silver.py` itself. Consistent with T9's "the sonnet arm is also the silver smoke" reading; re-running it live would cost provider spend and was out of verification scope.
- **N3 (bounded without spend).** "Identical retrieved evidence per case" (DEEP-13) cannot be re-derived from the persisted lines (evidence ids are not recorded). Verified instead: identical case sets per arm in both tiers, one anchored prompt_hash everywhere, one write timestamp per results file. The doc's method statement (golden evidence from committed snapshots; silver retrieved once and reused) is accepted as the remaining link.
- **N4 (mechanism note).** DEEP-20's parenthetical says "append-per-case"; the committed runner accumulates lines in memory and writes once per run (fresh exclusive-create file). The spec-defined *outcome* holds for the stated trigger — a provider failure becomes an error line and never aborts the run, and reruns can never corrupt a prior file — but a hard process kill mid-run would lose completed in-memory lines. tasks.md records fresh-file-per-run as an accepted deviation.
- **Verdict-arithmetic verification.** Both product decisions were reproduced mechanically: `generation_verdict(sonnet_agg, opus_agg)` → `"stay"` (Opus worse on silver faithfulness 0.9861 < 0.9907, discipline incomparable `None`), `judge_verdict(agreement)` → `"switch"` (exact 0.683 ≥ 0.60 and within-1 0.967 ≥ 0.90 clear; 8 gate flips trigger AD-165). The Opus-scores-declines-0.0 finding also reproduced: 9 declined answers, Haiku faithfulness all 1.0, Opus all 0.0.
- **Run-manifest consistency.** 72 tracked golden lines = (12 fresh golden × 2 arms + 12 replay) × 2 judges; 48 silver lines = 12 cases × 2 arms × 2 judges; 120 scorings total; every line `status: "ok"`; replay lines tagged `source: "replay"` and sonnet-only, `replay-` case-id prefix prevents pairing collisions. Cost ($5.8) is modeled from call counts, not metered — not independently verifiable, stated as such in the doc.

---

## Discrimination Sensor

Expanded tier (eval-integrity feature — the tests are the product). All mutations applied to scratch copies of tracked files, targeted test file run, file restored via `git checkout` immediately after; `git status --porcelain` clean at the end.

| # | Mutation (behavior level) | File:line | Killed by | Result |
| --- | --- | --- | --- | --- |
| M1 | Broken anchor classified as skipped (`BrokenCase` → `SkippedCase`) | `backend/tests/eval/silver.py:268` | `test_silver_resolution.py::test_unresolvable_anchor_is_broken_not_skipped` + `test_partial_anchor_miss…` (2 failed) | ✅ Killed |
| M2 | Duplicate checksum resolves to oldest (`desc()` → `asc()`) | `backend/tests/eval/silver.py:233` | `test_silver_resolution.py::test_duplicate_checksum_resolves_to_latest_created_at` | ✅ Killed |
| M3 | Relevancy mean includes declined (not-found) lines (`answered` → `lines`) | `backend/app/eval/ab.py:145` | `test_ab.py::test_relevancy_mean_excludes_declined_lines` | ✅ Killed |
| M4 | Within-1 verdict boundary broken at exactly 0.90 (`<` → `<=`) | `backend/app/eval/ab.py:261` | `test_ab.py::test_judge_verdict_keeps_at_within_1_threshold` | ✅ Killed |
| M5 | Writer silently appends into an existing results file (drop uuid, `"x"` → `"a"`) | `backend/tests/eval/silver.py:417-418` | `test_silver_run.py::test_writer_never_mutates_a_prior_results_file` | ✅ Killed |
| M6 | Score-3 exemplar band removed from the rubric (heading defaced) | `backend/app/eval/prompts/relevancy.md` (Score 3 heading) | `test_eval_judge.py::test_relevancy_rubric_carries_one_worked_exemplar_per_score` | ✅ Killed |
| M7 | `evals/silver/` un-ignored (rule deleted from `.gitignore:15`) | `.gitignore:15` | `test_silver_hygiene.py` (3 of 4 failed) | ✅ Killed |
| M8 | Generation verdict ignores a worse metric (`better >= 2 and worse == 0` → `better >= 2`) | `backend/app/eval/ab.py:293` | `test_ab.py::test_generation_stays_when_opus_worse_on_any_metric` | ✅ Killed |

**Sensor depth**: expanded (8 mutations)
**Result**: 8/8 killed — PASS ✅

---

## Code Quality

| Principle | Status |
| --- | --- |
| Minimum code (no driver/CLI beyond plan; ab.py pure; no SDK at module level) | ✅ |
| Surgical changes (only rubric/constant/config touched outside new files) | ✅ |
| No scope creep (faithfulness prompt untouched; gate semantics unchanged) | ✅ |
| Matches patterns (self-skip idiom, JSONL line schema, lazy provider imports, pin tests) | ✅ |
| Spec-anchored outcome check (asserted values match spec) | ✅ |
| Per-layer Coverage Expectation met (loader/resolver/exec/ab per test-coverage matrix) | ✅ |
| Every new test maps to a DEEP requirement or listed edge case — no unclaimed tests | ✅ |
| Documented guidelines followed: `CLAUDE.md` (citations/eval core), `pyproject.toml` markers, CI workflows (deterministic, key-free) | ✅ |

---

## Edge Cases

- [x] Malformed judge output → visible error line (DEEP-17)
- [x] Broken anchor distinct from skip (DEEP-18)
- [x] Empty retrieval still generated + judged, flagged (DEEP-19)
- [x] Mid-run provider failure → error line, run continues; rerun → fresh file, prior immutable (DEEP-20, mechanism note N4)

---

## Gate Check

- **Gate command**: `cd backend && LEARNY_GENERATION_PROVIDER=local LEARNY_EMBEDDING_PROVIDER=local LEARNY_TEST_DATABASE_URL=… .venv/bin/pytest -q && .venv/bin/ruff check .`
- **Result**: 1649 passed, 0 failed, 11 skipped; ruff "All checks passed!" (real exit codes checked: 0/0)
- **Test count before feature** (tasks.md Phase A baseline): 1580 passed / 10 skipped
- **Test count after**: 1649 / 11 — **delta +69 passed, +1 skip** (additive; nothing deleted, pin assertions updated only with their recalibration/switch commits)
- **Skipped (all justified)**: 8 pre-existing live/keyed skips (Anthropic ×5, OpenAI ×2 incl. retrieval metrics, docling import), 1 `--record-generation` guard, 1 committed-snapshot guard, and the new `test_silver.py:38` self-skip — which is itself DEEP-03's required behavior, exercised here with data present but the key env var unset

---

## Requirement Traceability Update

All 20 requirements DEEP-01..20: `Design/Pending` → **✅ Verified**. (Left recorded here; spec.md statuses not edited by the verifier — the tree is left unmutated apart from this report.)

---

## Summary

**Overall**: ✅ Ready

**Spec-anchored check**: 20/20 ACs matched spec outcomes; 0 spec-precision gaps; 4 non-blocking notes (N1 doc wording nit, N2/N3 no-spend verification bounds, N4 accepted mechanism deviation)
**Sensor**: 8/8 mutations killed (expanded tier)
**Gate**: 1649 passed / 11 skipped, ruff clean

**What works**: silver tier (loader/resolver/runner/hygiene) fully test-backed and git-clean with real data on disk; anchored rubric + recalibrated gate pinned atomically with recomputed-correct derivation; both A/B verdicts reproduce mechanically from the persisted lines via `ab.py`; both default decisions applied exactly per the encoded thresholds, judge switch isolated for the merge gate with the Opus recalibration follow-up flagged.

**Issues found**: none blocking. For the merge gate: the judge switch (`dc30318`) rests entirely on the 8 gate flips (6 of them `RELEVANCY_MIN = 2.8` boundary bisections), Opus contradicts the codebase's vacuous-faithfulness convention on declines, and keeping the switch requires the flagged Opus re-calibration — the research doc surfaces all of this honestly; stripping the commit is a documented, defensible option.

**Next steps**: merge-gate decision on `dc30318`; if kept, run the Opus baseline re-derivation follow-up.
