# Design — v5-eval-dashboard (RFC-005 Cycle D)

Read-only render of the accumulating nightly eval JSONL. Decisions AD-239..AD-244 (`context.md`) are binding
here and are not relitigated.

## Shape

```
evals/results/*.jsonl ─┐
                       ├─> app/eval/results.py  (pure: discover → parse → partition → aggregate → verdict)
eval-results checkout ─┘            │
                                    │ consumes app/eval/ab.py::aggregate  (ADR-0028 decline handling)
                                    │ consumes app/eval/judge.py::FAITHFULNESS_MIN / RELEVANCY_MIN
                                    ▼
              app/infrastructure/web/evals.py  (GET /api/dev/evals — gated + authenticated)
                                    ▼
              frontend/app/(app)/dev/evals/  (server-rendered list + client drill-down, inline SVG)
```

Layering: `app/eval/results.py` imports nothing from `app.infrastructure` (the fitness check forbids it,
`backend/scripts/check_boundaries.py:13`) and takes its directory as a parameter. The web layer is the only
place that reads settings. No database, no provider SDK, no network — the whole feature is a file read.

## Components

### 1. `backend/app/eval/results.py` (new, pure)

The entire domain of this cycle. Sketch of the seams it must expose — names are the contract the router and
tests bind to; internals are the implementer's call.

```python
GENERATION_KEY = "case_id"        # judge.py:347 writes this family
ANSWERABILITY_KEY = "item_id"     # judge.py:393 writes this family

@dataclass(frozen=True)
class RunSummary:
    run_id: str                   # the result-file basename without suffix (AD-240)
    path: str                     # repo-relative source path, for provenance
    latest_ts: str | None         # newest record timestamp; ordering key
    git_sha: str | None
    generation_model: str | None  # None when the run's records disagree or omit it
    judge_model: str | None
    prompt_hash: str | None
    unparsable: int
    generation: ModelAggregate | None      # from ab.aggregate, over generation lines only
    answerability_count: int
    answerability_mean_score: float | None
    verdict: str                  # "pass" | "fail" | "not-evaluated"
    failures: tuple[str, ...]     # which gate conditions failed, for the UI
    cases: tuple[CaseRecord, ...]

def discover_result_files(root: Path) -> dict[str, Path]: ...   # basename -> winning path (AD-240)
def parse_lines(path: Path) -> tuple[list[dict], int]: ...      # records, unparsable count
def partition_families(lines) -> tuple[list[dict], list[dict]]: ...  # (generation, answerability) — AD-242
def gate_outcome(generation_lines) -> tuple[str, tuple[str, ...]]: ...  # AD-241
def load_runs(root: Path) -> list[RunSummary]: ...              # newest first
```

**The verdict rule (AD-241) must mirror `judge.py:428-439` exactly — three conditions, in this order:**

1. No generation lines at all → `not-evaluated` (nothing was gated).
2. Any line with `citation_valid` false → `fail` (this invariant covers **every** line, declines included).
3. No answered line (`found` false everywhere) → `pass` on the citation invariant alone; the means are
   **skipped**, exactly as the gate skips them. Report both means as absent — never as 0.0, and never `fail`.
4. Otherwise mean faithfulness over answered lines `>= FAITHFULNESS_MIN` **and** mean relevancy over answered
   lines `>= RELEVANCY_MIN` → `pass`, else `fail`, naming which one fell short in `failures`.

Thresholds are imported from `app.eval.judge`, never retyped (`ab.py:58` sets this precedent).

**Trap — the reason `partition_families` exists.** `ab.aggregate` reads `line["faithfulness"]` and
`line["citation_valid"]` unguarded (`ab.py:142-144`). An answerability line has neither key and defaults
`found` to `True`, so it enters the answered list and raises `KeyError`. Reproduced against the real
`evals/results/2026-07-18-5b85c39.jsonl`, which mixes 12 answerability rows with 2 generation rows — as does
every nightly file. Aggregation must never see a mixed list.

**Ordering and dedup.** `discover_result_files` walks `root` recursively (`rglob("*.jsonl")`) and keys by
`path.name`; on collision the lexicographically greatest full path wins, because the nightly copies every file
into each `results/<date>-<run_id>/` snapshot and the judge only appends (AD-240). Runs sort by `latest_ts`
descending, falling back to `run_id` when a run has no parsable timestamp.

**Tolerance.** A missing directory yields `[]`. A malformed line increments `unparsable` and is dropped. Every
field except the identity key is optional — the five committed files carry four distinct record shapes.

### 2. Settings (`backend/app/core/config.py`)

Two additions, alongside the instrument block they mirror:

- `dev_eval_dashboard_enabled: bool = False` — the mount gate.
- `eval_results_dir: Path | None = None` — `None` means the judge's own `RESULTS_DIR`; set it to a checkout of
  the `eval-results` branch to render the full nightly history (AD-239).

### 3. `backend/app/infrastructure/web/evals.py` (new)

`router = APIRouter(tags=["evals"])`, one route, mirroring `instrument.py:108` verbatim in shape:

```python
@router.get("/api/dev/evals", dependencies=[Depends(get_authenticated_user)])
def read_eval_runs(settings: AppSettings) -> EvalDashboardView: ...
```

Pydantic views (`EvalDashboardView`, `EvalRunView`, `EvalCaseView`) carry the aggregates plus the thresholds in
force, so the client draws the reference lines from the server's constants rather than its own copy. Include a
`SCOPE_NOTICE`-style string naming which directory was read and that files are the source of truth — the
instrument's precedent for "a reader cannot mistake this slice for the whole deployment" applies equally here,
since a default-configured process shows only the committed golden files, not the nightly history.

### 4. Mounting (`backend/app/main.py`)

Add `eval_dashboard_surface_exposed(settings)` beside `instrument_surface_exposed` — same two-part rule (flag
set AND `settings.environment` is not production), same warning log on a refused flag, its own switch so the
two dev surfaces stay independent (AD-243). Mount conditionally next to the instrument router.

### 5. Frontend (`frontend/app/(app)/dev/evals/`)

- `page.tsx` fetches `/api/dev/evals` through the existing catch-all proxy (`app/api/[...path]/route.ts`); no
  new proxy route. A 404 response renders "the dashboard is not enabled on this process" rather than an error —
  the flag being off is the normal case.
- Run list: one row per run — id, timestamp, verdict badge, both means, citation-valid rate, model/judge.
- Drill-down: a client component toggling that run's case rows; declined cases render as declined with absent
  scores, and a citation-invalid case is marked as the invariant violation (EVDASH-08).
- Trend: hand-rolled inline `<svg>` per metric, points across runs oldest→newest, with the threshold drawn as a
  reference line, coloured from `--color-chart-1..5` (AD-244). No new dependency. Give the series an accessible
  name so Vitest can assert it under jsdom.
- **No nav entry, no link from any student-facing surface** (AD-243 / RFC-005 sequencing). The route is reached
  by URL only.

## Testing

| Area | Approach |
| --- | --- |
| Reader | Fixture directories built in `tmp_path`; crafted runs for pass, fail-on-mean, fail-on-citation, all-declined, empty, malformed-line, mixed-family, duplicate-basename-across-dirs |
| Verdict ⇄ gate equivalence | Feed identical line sets to `gate_outcome` and to `judge._assert_aggregates` (catching `AssertionError`); assert they agree — including the no-answered-line case. This is the invariant that keeps the dashboard honest |
| Real data | One test loads the committed `evals/results/` and asserts it parses with zero unparsable lines and no raise — the four real record shapes are the regression surface |
| Endpoint | `backend/tests/test_web_evals.py` mirroring `test_web_instrument.py`: 404 flag off, 404 production with flag on, 401 unauthenticated, 200 authenticated, and absence from `openapi.json` when unmounted |
| Frontend | `frontend/tests/eval-dashboard.test.tsx` — Vitest + Testing Library: run rows render, verdict badges, drill-down expand/collapse, threshold reference line present, disabled-state message |

Gate commands: `cd backend && uv run pytest` (module subset per task, full suite at phase boundary),
`cd frontend && npm test`, `make lint`.
