# App Instrumentation — Tasks

One atomic commit per task. Each task's tests derive from the spec's acceptance
criteria, never from the implementation. The gate is green before a task is done.

**Gate command** (`uv` is off PATH on this machine — use the venv interpreter):

```
cd backend && LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test \
  LEARNY_REDIS_URL=redis://localhost:6379/0 .venv/bin/python -m pytest <scope> -q
```

Scoped module per intermediate commit; full backend suite once at each phase boundary.
Baseline to beat: **1655 passed / 1 known pre-existing failure / 11 skipped** (backend),
**563 passed** (frontend, `cd frontend && npx vitest run`). Ruff: `.venv/bin/python -m ruff check .`
and `format --check` — note 10 Cycle-1 files fail `format --check` on `main` already
(recorded known gap); do not reformat them.

---

## Phase A — The recorder (OBS-01..05)

| Task | Outcome | Requirements |
| --- | --- | --- |
| A1 | A recorder module holds request samples and slow-query entries in bounded storage, exposes a record API for each, and a snapshot/ranking API returning per-`(method, route)` count, mean, max and nearest-rank p95, ordered by p95 desc then max desc. Safe under concurrent recording. Never stores path parameters, query strings, headers, or bodies. | OBS-01..06 |
| A2 | The four settings fields exist with their defaults and env names, and `backend/.env.example` documents them in a new observability section. | OBS-23 |

Phase boundary: full backend suite + ruff.

## Phase B — Request timing on the wire (OBS-07..10)

| Task | Outcome | Requirements |
| --- | --- | --- |
| B1 | Every completed request is recorded through the recorder from the existing middleware timing, keyed on the route template, with unmatched requests under one constant placeholder; a recorder failure leaves the response untouched. | OBS-01, 02, 07 |
| B2 | Every response carries `Server-Timing` with an `app` metric whose `dur` matches the access log's duration, including when the handler raises. | OBS-08, 10 |
| B3 | A frontend test pins that `Server-Timing` survives `relayResponse`, so a future denylist change cannot silently drop it. | OBS-09 |

Phase boundary: full backend suite + ruff + frontend vitest.

## Phase C — Query and task instrumentation (OBS-11..18)

| Task | Outcome | Requirements |
| --- | --- | --- |
| C1 | Statements on the application engine that meet the threshold produce one structured log record and one recorder entry carrying statement text and duration; faster statements produce neither; captured text carries no bound parameter values and is truncated to the cap; a listener failure leaves the database operation intact. | OBS-11..15 |
| C2 | Every Celery task emits one duration record on completion carrying task name, terminal state and duration — success and failure distinguished, retries counted separately, with no per-task code and the existing per-task `duration_ms` records unchanged. | OBS-16..18 |

Phase boundary: full backend suite + ruff.

## Phase D — The surface (OBS-19..24)

| Task | Outcome | Requirements |
| --- | --- | --- |
| D1 | A dev-only route returns ranked endpoints and recent slow queries: 404 when the flag is off, 401 when unauthenticated, 200 with the documented shape when both hold, and 200 with empty collections when nothing has been recorded. The response states that it covers one process. | OBS-19..22 |
| D2 | The dev compose override enables the flag; the production compose does not. An ops note explains how to read the surface and what it deliberately does not cover. | OBS-23, 24 |
| D3 | `ROADMAP.md` gains the v6 section with the five RFC-006 cycles and this row marked done; RFC-006's action items for the pause record and Cycle A are updated; `STATE.md` carries `AD-170`..`AD-177` and the cycle handoff. | — |

Phase boundary: full backend suite + ruff + frontend vitest.

---

## Verification

After D3, a fresh Verifier (author ≠ verifier, Opus) runs automatically: spec-anchored
outcome check across OBS-01..24, discrimination sensor with behaviour-level mutations,
and `validation.md`. Surviving mutants become fix tasks, bounded to 3 iterations.
