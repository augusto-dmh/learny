# Tasks — v5-eval-dashboard (RFC-005 Cycle D)

3 phases, 9 atomic tasks — under the sub-agent threshold (>3 phases), so Execute runs inline.
One atomic commit per task; the task's gate must be green before it is done.

Gate commands: backend `cd /home/augusto/projects/learny/backend && uv run pytest <module>` per task and the
full suite at each phase boundary; frontend `cd /home/augusto/projects/learny/frontend && npm test`;
`make lint` before publishing. Baselines to beat: backend 1946 passed / 11 skipped, frontend 744 passed.
(A local HNSW flake is pre-existing and reproduces on clean `main`; it is green in CI.)

---

## Phase 1 — The reader (`backend/app/eval/results.py`, pure)

### T1 — Discover result files and parse them tolerantly
**Requirements:** EVDASH-01, EVDASH-02 (parsing half)
**Deliverable:** `discover_result_files(root)` and `parse_lines(path)` in the new `app/eval/results.py`.
**Must hold:**
- A recursive walk finds `.jsonl` files at any depth under `root`.
- The same basename appearing under several directories is counted **once**, the lexicographically greatest
  path winning (AD-240) — this is the nightly's re-uploaded-seed case, not a hypothetical.
- A missing or empty directory yields no runs and no exception.
- A malformed line is skipped and counted, and the surrounding valid lines still parse.
**Gate:** `uv run pytest tests/test_eval_results.py`

### T2 — Partition families and assemble run summaries
**Requirements:** EVDASH-02 (partition half), EVDASH-03, EVDASH-07 (case records), EVDASH-10 (data half)
**Deliverable:** `partition_families`, `CaseRecord`, `RunSummary`, `load_runs(root)`.
**Must hold:**
- Generation lines (`case_id`) and answerability lines (`item_id`) are separated **before** any aggregation.
  **Trap:** `ab.aggregate` reads `line["faithfulness"]`/`line["citation_valid"]` unguarded (`ab.py:142-144`) and
  an answerability line has neither key while defaulting `found` to `True` — it raises `KeyError`. Every real
  nightly file mixes the two families. Aggregation must never receive a mixed list.
- Generation aggregation goes through `ab.aggregate`, so ADR-0028's decline handling is inherited, not re-derived.
- Runs order newest-first by latest record timestamp, with a deterministic fallback when timestamps are absent.
- Records missing any optional field (`git_sha`, `judge_model`, `prompt_hash`, `tier`, `status`, `run_index`,
  `source`, `expected_not_found`) still produce a run — the five committed files carry four distinct shapes.
- Answerability lines yield a count and mean score, never folded into the generation metrics.
**Gate:** `uv run pytest tests/test_eval_results.py`

### T3 — Derive the gate verdict, provably equal to the gate
**Requirements:** EVDASH-04
**Deliverable:** `gate_outcome(generation_lines) -> (verdict, failures)`.
**Must hold:**
- The rule mirrors `judge._assert_aggregates` (`judge.py:428-439`) in all **three** conditions: the
  `citation_valid` invariant over *every* line including declines; then the two means over answered lines only.
- A run with generation lines but no answered line skips the means exactly as the gate does — it is not `fail`,
  and the means are reported absent rather than 0.0.
- A run with no generation lines at all is `not-evaluated`, distinct from `pass`.
- `FAITHFULNESS_MIN` / `RELEVANCY_MIN` are **imported** from `app.eval.judge`; a threshold literal must not
  appear in this module (AD-241).
- **Required sensor:** a test feeding identical line sets to `gate_outcome` and to `_assert_aggregates`
  (catching `AssertionError`) and asserting the two agree, covering pass, fail-on-faithfulness,
  fail-on-relevancy, fail-on-citation, all-declined, and empty.
**Gate:** `uv run pytest tests/test_eval_results.py`

**Phase 1 boundary:** full backend suite green.

---

## Phase 2 — The surface

### T4 — Settings and conditional mounting
**Requirements:** EVDASH-05 (gating half)
**Deliverable:** `dev_eval_dashboard_enabled` + `eval_results_dir` in `config.py`;
`eval_dashboard_surface_exposed(settings)` and the conditional `include_router` in `main.py`.
**Must hold:**
- Mount requires the flag set **and** a non-production `environment`; a flag set on a production process is
  refused and the refusal is logged, mirroring `instrument_surface_exposed` (`main.py:38-62`).
- The two dev surfaces switch independently — enabling one must not expose the other.
- `eval_results_dir` unset resolves to the judge's `RESULTS_DIR`.
**Gate:** `uv run pytest tests/test_web_evals.py tests/test_web_instrument.py`

### T5 — The read-only endpoint
**Requirements:** EVDASH-05, EVDASH-06 (payload half), EVDASH-07
**Deliverable:** `app/infrastructure/web/evals.py` — `GET /api/dev/evals` returning `EvalDashboardView`.
**Must hold:**
- Authenticated via `get_authenticated_user` as a route dependency, matching `instrument.py:108`.
- Unmounted ⇒ 404 **and** absent from `openapi.json`; mounted + unauthenticated ⇒ 401; mounted + authenticated ⇒ 200.
- The payload carries the thresholds in force, so the client never holds its own copy.
- The payload names the directory that was read, so a default-configured process cannot be mistaken for one
  rendering the full nightly history.
- Per-case records are included for drill-down, with declines distinguishable from zero scores.
**Gate:** `uv run pytest tests/test_web_evals.py`

**Phase 2 boundary:** full backend suite green + `make lint`.

---

## Phase 3 — The page

### T6 — Dashboard page and run list
**Requirements:** EVDASH-06
**Deliverable:** `frontend/app/(app)/dev/evals/page.tsx` fetching through the existing catch-all proxy.
**Must hold:**
- Each run renders its id, timestamp, verdict, both means, and citation-valid rate.
- A 404 from the endpoint renders a plain "not enabled on this process" state, not an error — the flag being
  off is the normal case.
- No nav entry and no link from any student-facing surface (AD-243); the route is reachable by URL only.
**Gate:** `npm test`

### T7 — Per-case drill-down
**Requirements:** EVDASH-08
**Must hold:** expanding a run reveals its cases and collapsing hides them; a declined case shows as declined
with absent scores; a citation-invalid case is marked as the invariant violation.
**Gate:** `npm test`

### T8 — Threshold-referenced trend and answerability summary
**Requirements:** EVDASH-09, EVDASH-10 (render half)
**Must hold:** each metric with two or more runs draws a per-run series with its threshold as a reference line,
using inline SVG and the existing `--color-chart-*` tokens — **no new dependency** (AD-244); the series carries
an accessible name so it is assertable under jsdom; answerability count and mean score render distinctly from
the generation metrics.
**Gate:** `npm test`

### T9 — Documentation
**Requirements:** —
**Must hold:** `evals/README.md` points at the dashboard and says how to render the `eval-results` branch via
`eval_results_dir`; `.env.example` carries both new settings with accurate names; the stale
"git history / the artifact is the eval dashboard … no UI" comment at `.github/workflows/eval.yml:88` is
corrected. Verify every env-var name against `config.py` before writing it.
**Gate:** `make lint`

**Phase 3 boundary:** `make check` green.

---

## Traceability

| Requirement | Tasks |
| --- | --- |
| EVDASH-01 | T1 |
| EVDASH-02 | T1, T2 |
| EVDASH-03 | T2 |
| EVDASH-04 | T3 |
| EVDASH-05 | T4, T5 |
| EVDASH-06 | T5, T6 |
| EVDASH-07 | T2, T5 |
| EVDASH-08 | T7 |
| EVDASH-09 | T8 |
| EVDASH-10 | T2, T8 |

10 requirements, all mapped.
