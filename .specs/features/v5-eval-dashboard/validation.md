# Validation — v5-eval-dashboard (RFC-005 Cycle D)

Independent verification, 2026-08-02. Verifier did not author the implementation.

- **Verdict: PASS**
- Diff range: `main..HEAD` on `feat/eval-dashboard` (6 commits, `382bd94b..3eac0dc1`)
- Baselines at start: backend 57/57 for the three touched test files, frontend 14/14 for
  `eval-dashboard.test.tsx` (full-suite baselines — backend 2049 passed / 12 skipped, frontend 758
  passed, `make lint` clean — verified upstream; the HNSW-threshold failure in
  `test_eval_retrieval_metrics.py` is pre-existing on clean `main` and green in CI).
- Mutation campaign: **18/18 killed** (9 reader, 4 web, 5 frontend). Every mutation was reverted with
  `git checkout --` and `git status --porcelain` is empty at the end.

## Real-data checks (run directly, not just via tests)

- `load_runs(evals/results)` → 5 runs, 0 unparsable lines (four distinct record shapes).
- `load_runs(<checkout of eval-results branch>)` → 27 `.jsonl` files dedupe to **11 distinct runs**;
  each seed basename counted once. Matches AD-245 exactly: 9 of 11 render `fail`, all on `relevancy`,
  all judged by `claude-haiku-4-5` (the pre-recalibration judge), so the stale-judge marker has real
  work to do.

## Per-AC evidence table

| AC | Spec-defined outcome | Sensor (test) | Status |
| --- | --- | --- | --- |
| P1.1 | One run per basename, newest first by latest record ts | `test_same_basename_across_snapshots_counts_once`, `test_runs_are_ordered_newest_first`, `test_undated_runs_sort_after_dated_ones` | ✓ (R5, R6, R8 killed) |
| P1.2 | Means over answered lines only; citation rate over all generation lines | `test_declines_stay_out_of_the_quality_means`; citation-rate-over-all-lines is inherited via `ab.aggregate` and pinned upstream in `tests/eval/test_ab.py::test_citation_valid_rate_is_the_fraction_valid` | ✓ (note N1) |
| P1.3 | Thresholds read from the gate's constants, never re-typed | `test_thresholds_are_imported_rather_than_retyped` (AST scan of `results.py`), `test_payload_carries_the_gate_thresholds` | ✓ with gap G1 |
| P1.4 | Verdict pass iff every gate condition holds | 9-case parametrized `test_derived_verdict_agrees_with_the_nightly_gate` running the **real** `_assert_aggregates`; `test_verdicts_distinguish_the_passing_run_from_the_failing_one` | ✓ (R1, R7 killed) |
| P1.5 | No answered line → means absent, not `fail` | `test_all_declined_run_passes_on_the_citation_invariant_alone`, `test_all_declined_run_reports_absent_means_not_zeros`, equivalence case `all declined` | ✓ (R2 killed) |
| P1.6 | Page renders id, timestamp, verdict, means, citation rate | frontend `renders each run with its verdict and headline metrics` — asserts id, verdict, both means, citation rate | ✓ with gap G2 (timestamp rendered but unasserted) |
| P2.1 | Per-case records with id, scores, citation validity, answered state | `test_cases_are_included_for_the_drill_down`, `test_declined_case_renders_with_absent_scores_not_zeros` | ✓ |
| P2.2 | Decline renders with absent scores, never zero | backend case-record test + frontend `renders a decline as a decline…` (asserts `0.000` absent, `—` present) | ✓ (F1 killed) |
| P2.3 | Citation-invalid case marked as the invariant violation | frontend `marks the case that violated the citation invariant` | ✓ (F5 killed) |
| P2.4 | Expand reveals cases, collapse hides them | frontend `reveals and hides the cases behind a run` | ✓ (F4 killed) |
| P3.1 | Metric with ≥2 runs drawn with threshold reference line | frontend `draws the trend against the threshold the server sent` (non-default 0.77 proves the server value is used), `omits a trend that has fewer than two points` | ✓ (F2 killed; note N2) |
| P3.2 | Answerability count + mean, distinct from generation | `test_answerability_lines_are_summarized_separately`, web `test_answerability_records_are_reported_separately`, frontend `reports the answerability records…` | ✓ |
| P3.3 | Answerability-only run listed, generation absent | `test_answerability_lines_are_summarized_separately` (generation `None`, verdict `not-evaluated`), frontend `distinguishes a run that gated nothing` | ✓ (R3 killed) |

Edge cases: all eight have direct sensors — missing/empty dir (`test_missing_directory_yields_no_runs`,
`test_empty_directory_yields_no_runs`, web empty-dir 200), malformed line counted
(`test_malformed_line_is_counted_and_the_run_survives`, R9 killed), mixed families
(`test_mixed_family_file_aggregates_without_raising`, R4 killed), absent optional fields
(`test_optional_provenance_fields_may_all_be_absent` + the committed-files test), duplicate basename
(R5/R6 killed), flag off → 404 + absent from OpenAPI, production + flag → 404 + refusal logged
(caplog-asserted), unauthenticated → 401 (W1–W3 killed).

## Mutation table

| # | Mutation (behaviour injected) | Result | Killing test(s) |
| --- | --- | --- | --- |
| R1 | Citation invariant checks answered lines only (declines exempt) | KILLED | `test_citation_violation_fails_even_on_a_decline`, equivalence `citation violated on a decline` |
| R2 | Run with no answered line reports `fail` | KILLED | `test_all_declined_run_passes…`, `…reports_absent_means…`, equivalence `all declined` (4 tests) |
| R3 | `not-evaluated` collapsed into `pass` | KILLED | `test_no_generation_lines_is_not_evaluated`, `test_answerability_lines_are_summarized_separately` |
| R4 | Answerability lines leaked into generation aggregation | KILLED | `KeyError: 'faithfulness'` in 3 tests incl. `test_the_committed_result_files_all_parse` |
| R5 | Dedup keeps lexicographically least path (oldest snapshot wins) | KILLED | `test_duplicate_basename_resolves_to_the_newest_snapshot` |
| R6 | No basename dedup (runs keyed by full path) | KILLED | `test_same_basename_across_snapshots_counts_once` + 4 others |
| R7 | Faithfulness compared against `FAITHFULNESS_MIN + 0.05` (threshold drift) | KILLED | equivalence `exactly at both thresholds` |
| R8 | Runs sorted oldest first | KILLED | `test_runs_are_ordered_newest_first`, `test_undated_runs_sort_after_dated_ones` |
| R9 | Malformed line skipped without being counted | KILLED | `test_malformed_line_is_counted_and_the_run_survives` |
| W1 | Production refusal removed — flag alone mounts the surface | KILLED | `test_production_process_refuses_the_flag` (200 != 404) |
| W2 | Instrument flag also mounts the dashboard (coupled switches) | KILLED | `test_instrument_alone_does_not_expose_the_dashboard` |
| W3 | Auth dependency removed from the route | KILLED | `test_mounted_surface_refuses_an_unauthenticated_read` (200 != 401) |
| W4 | Configured `eval_results_dir` ignored (always `RESULTS_DIR`) | KILLED | 6 tests incl. `test_payload_names_the_directory_it_read` |
| F1 | Null score rendered as `0.000` | KILLED | `renders a decline as a decline rather than a zero score` |
| F2 | Faithfulness threshold hardcoded `0.9` client-side | KILLED | `draws the trend against the threshold the server sent` |
| F3 | 404 treated as an error, not the disabled state | KILLED | `explains a disabled surface instead of reporting an error` |
| F4 | Collapse is a no-op (`setExpanded(true)`) | KILLED | `reveals and hides the cases behind a run` |
| F5 | Citation-invalid case rendered `valid` | KILLED | `marks the case that violated the citation invariant` |

## Gaps (none blocking) — both closed after the report

- **G1 (minor, spec precision) — CLOSED.** The no-re-typed-thresholds sensor AST-scanned `app/eval/results.py` only. `app/infrastructure/web/evals.py` also publishes the thresholds; it imports the constants, but its sensor was value-equality, so a literal re-typed there at today's value would have survived until the next recalibration. The test is now parametrized over both modules (`THRESHOLD_FREE_MODULES`). Confirmed as a real sensor, not decoration: re-typing `faithfulness_min=0.90` in `evals.py` fails the `[app.infrastructure.web.evals]` case, and the mutation was reverted.
- **G2 (minor, spec precision) — CLOSED.** P1 AC6 names the timestamp among the fields the page must render; it was rendered but unasserted, so blanking it would have passed. The run-list test now asserts the formatted timestamp, and a second case pins the undated run to `"undated"` rather than an invalid date.

Post-fix gates: backend `tests/test_eval_results.py` 32 passed, frontend 759 passed, `make lint` clean.
- **N1 (note).** The "citation-valid rate over all generation lines" half of P1 AC2 is pinned upstream in `tests/eval/test_ab.py` (pre-existing Cycle B/C coverage), not in this cycle's files — intentional under T2's "inherited, not re-derived" rule.
- **N2 (note).** Only the faithfulness trend's threshold is directly asserted; relevancy rides the same `MetricTrend` component with its own server-sent prop.

## Non-relitigated divergences

`gate_outcome`'s two documented divergences from `_assert_aggregates` (missing `citation_valid` counts
as violation; answered line with null score excluded from the mean) apply only to shapes the judge
cannot write — the gate would crash on them, a renderer may not. Confirmed unreachable on all 27 real
files. Consistent with AD-241; not a drift.
