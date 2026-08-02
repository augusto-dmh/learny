# Eval-Results Dashboard Specification

RFC-005 Cycle D. Feature slug: `v5-eval-dashboard`. Requirement prefix: `EVDASH`.

## Problem Statement

The nightly eval writes JSONL result lines and nothing renders them. `.github/workflows/eval.yml:88` says so
outright — "git history / the artifact is the eval dashboard (research §5 — no UI)". Reading a run today means
opening a raw JSONL file and computing the means by hand, then comparing them against threshold constants that
live in a third file. Cycle B re-derived those thresholds and Cycle C produced multi-run evidence, so there is
now accumulated output with no legible surface — and the recurring process lesson (long backend-only streaks
delay end-to-end feedback) has no cheaper fix than making that output visible.

## Goals

- [ ] A read-only surface renders every discovered eval run with its headline metrics and its **derived** gate verdict.
- [ ] The rendered verdict is provably the same verdict the nightly gate asserts for the same lines — one shared source of thresholds and one shared decision rule, so the dashboard can never drift from `_assert_aggregates`.
- [ ] The surface is invisible to the dogfooding author (RFC-005's sequencing constraint for Cycles A–E) and absent from production entirely.
- [ ] Heterogeneous, partial, and duplicated result files render without crashing.

## Out of Scope

| Feature | Reason |
| --- | --- |
| Writing, re-running, or triggering evals from the UI | Read-only is the whole cycle; a write path would put provider spend behind a button |
| Fetching the `eval-results` branch over the network at request time | Puts git + credentials in the request path; the configurable results directory (EVDASH-01) lets an operator point at a checkout instead |
| Persisting eval results to PostgreSQL | Files are the source of truth today (`evals/README.md`); a schema is a separate decision |
| Adding a charting dependency | AD-244 — this is the RFC's explicitly "most cuttable" cycle; a new runtime dep is not worth one dev-only page |
| Any student-facing entry point, nav item, or link | RFC-005 requires Cycles A–E to stay off surfaces the dogfooding author sees |
| Judge/generation A/B study rendering (`ab.py` verdicts, `MetricSpread`) | Cycle C's output is a committed research doc; re-rendering it is not this cycle's deliverable |
| Authoring new eval cases or tiers | Unrelated to legibility |

---

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| Data source (AD-239) | Read a configurable results directory, recursively; default = the judge's own `RESULTS_DIR` | Zero new infrastructure and it works locally; the recursive read plus the setting lets an operator `git worktree add` the `eval-results` branch and render the full nightly history without runtime git | y (auto) |
| Run identity + duplicate snapshots (AD-240) | A run is identified by its result **file basename**; when a basename appears under several directories, the lexicographically greatest path wins | The nightly copies *all* of `evals/results/*.jsonl` into each snapshot dir, so the same seed file appears in all 8 dirs; the judge only ever appends, so the newest copy is a superset of the older ones | y (auto) |
| Gate verdict (AD-241) | Derived, mirroring `_assert_aggregates` exactly — all three conditions, importing the same constants | No verdict is written into the JSONL, and a re-implemented rule would silently drift from the gate it claims to show | y (auto) |
| Mixed record families (AD-242) | Partition lines into the generation family and the answerability family before aggregating | `ab.aggregate` reads `line["faithfulness"]` unguarded and raises `KeyError` on answerability lines — verified against `evals/results/2026-07-18-5b85c39.jsonl` | y (auto) |
| Surface gating (AD-243) | Mirror the instrument precedent: mounted only when a dev flag is set AND the process is not production; authenticated once mounted | RFC-005 requires A–E to be invisible during the dogfood window, so gating is a requirement here rather than a convention | y (auto) |
| Visualization (AD-244) | Hand-rolled inline SVG using the existing `--color-chart-*` tokens; no charting library | Keeps the cuttable cycle dependency-free and theme-correct; the data volume (single-digit runs) does not justify a chart runtime | y (auto) |
| Which metrics are "headline" | Generation family drives the page (faithfulness, relevancy, citation-valid rate, gate verdict); the answerability family renders as a secondary summary | The RFC names the generation metrics; answerability lines share the files and must not be silently dropped | y (auto) |

**Open questions:** none — all resolved or logged above.

---

## User Stories

### P1: See every eval run and whether it passed ⭐ MVP

**User Story**: As the operator, I want a single page listing every eval run with its metrics and pass/fail, so that I can read the eval history without hand-computing means from raw JSONL.

**Why P1**: This is the cycle's entire reason to exist and the smallest complete vertical slice (reader → aggregate → endpoint → page).

**Acceptance Criteria**:

1. WHEN the results directory holds one or more `.jsonl` files THEN the system SHALL return one run entry per distinct result-file basename, ordered newest first by the run's latest record timestamp.
2. WHEN a run's generation lines are aggregated THEN the system SHALL report mean faithfulness and mean relevancy over **answered** lines only, and citation-valid rate over **all** its generation lines.
3. WHEN a run's aggregates are computed THEN the system SHALL report the threshold values in force (faithfulness 0.90, relevancy 3.1) read from the same constants the nightly gate asserts, never as literals re-typed in dashboard code.
4. WHEN a run satisfies every gate condition THEN the system SHALL report its verdict as `pass`; WHEN it violates any one of them THEN the system SHALL report `fail`.
5. WHEN a run has generation lines but none of them answered THEN the system SHALL report the two means as absent and SHALL NOT report `fail` on account of the absent means — matching the gate, which skips those asserts.
6. WHEN the operator opens the dashboard page THEN the page SHALL render each run's identifier, timestamp, verdict, both means, and citation-valid rate.

**Independent Test**: Point the reader at a fixture directory containing two crafted run files (one passing, one failing) and confirm the endpoint returns both with the expected verdicts, and the page renders both rows.

---

### P2: Drill into the cases behind a run

**User Story**: As the operator, I want to expand a run and see its individual cases, so that when a run fails I can see which case caused it rather than only that the mean dropped.

**Why P2**: The aggregate answers "did it pass"; only the per-case view answers "why". Named in the RFC's deliverable list, but the run list is demo-able without it.

**Acceptance Criteria**:

1. WHEN a run entry is requested THEN the system SHALL include its per-case records with case identifier, faithfulness, relevancy, citation validity, and answered/declined state.
2. WHEN a case declined (`found` is false) THEN the system SHALL render it as a declined case with absent scores, not as a zero-scoring case.
3. WHEN a case's citation validity is false THEN the page SHALL mark that case as the citation-invariant violation.
4. WHEN the operator expands a run on the page THEN the page SHALL reveal that run's case rows and hide them again on collapse.

**Independent Test**: Expand the failing fixture run and confirm the offending case is visible and marked.

---

### P3: Read the trend and the answerability tier

**User Story**: As the operator, I want the run-over-run trend drawn against the threshold lines, plus the answerability lines summarized, so that a drift toward the gate is visible before it trips and no records in the files are silently unrendered.

**Why P3**: Pure legibility on top of data already returned by P1/P2; the page is useful without it.

**Acceptance Criteria**:

1. WHEN two or more runs carry a given metric THEN the page SHALL draw that metric's per-run series with its threshold drawn as a reference line.
2. WHEN a run contains answerability records THEN the system SHALL report their count and mean score, distinct from the generation metrics.
3. WHEN a run contains only answerability records THEN the run SHALL still be listed, with its generation metrics reported as absent.

---

## Edge Cases

- WHEN the results directory does not exist or holds no `.jsonl` file THEN the system SHALL return an empty run list with a success status, never an error.
- WHEN a line in a result file is not valid JSON THEN the system SHALL skip that line, count it as unparsable on the run, and still return the run.
- WHEN a file mixes generation and answerability records THEN the system SHALL aggregate each family independently and SHALL NOT raise.
- WHEN a record lacks optional fields (`git_sha`, `judge_model`, `prompt_hash`, `tier`, `status`, `run_index`) THEN the system SHALL render the run with those fields absent rather than failing — the five committed files carry four different record shapes.
- WHEN the same result-file basename exists under several directories THEN the system SHALL count it once (AD-240).
- WHEN the dev flag is unset THEN the endpoint SHALL match no route (404) and SHALL be absent from the OpenAPI schema.
- WHEN the process is configured as production THEN the endpoint SHALL match no route even if the flag is set, and the refusal SHALL be logged.
- WHEN the endpoint is mounted and the caller is unauthenticated THEN the system SHALL respond 401.

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| --- | --- | --- | --- |
| EVDASH-01 | P1: run discovery, recursive + configurable dir, dedup | Design | Pending |
| EVDASH-02 | P1: tolerant JSONL parsing + family partition | Design | Pending |
| EVDASH-03 | P1: per-run aggregation over the generation family | Design | Pending |
| EVDASH-04 | P1: derived gate verdict mirroring `_assert_aggregates` | Design | Pending |
| EVDASH-05 | P1: read-only endpoint, gated + authenticated | Design | Pending |
| EVDASH-06 | P1: dashboard page renders the run list | Design | Pending |
| EVDASH-07 | P2: per-case records in the payload | Design | Pending |
| EVDASH-08 | P2: per-case drill-down on the page | Design | Pending |
| EVDASH-09 | P3: threshold-referenced trend series | Design | Pending |
| EVDASH-10 | P3: answerability summary | Design | Pending |

**Coverage:** 10 total, mapped at Tasks.

---

## Success Criteria

- [ ] Pointing the reader at the committed `evals/results/` renders all five real files without error, despite their four distinct record shapes.
- [ ] Pointing it at a checkout of the `eval-results` branch renders the nightly history with each seed file counted once, not eight times.
- [ ] A test asserts the derived verdict equals the gate's own outcome for the same lines, including the no-answered-line case.
- [ ] The endpoint 404s with the flag off, 404s in production with the flag on, and 401s unauthenticated.
- [ ] `make check` green; no new frontend runtime dependency.
