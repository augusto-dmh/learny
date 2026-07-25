# App Instrumentation — Decision Context

RFC-006 Cycle A. Decisions taken under the ship-cycle auto-decision rule: each was
formulated as an option set with why-recommend and why-not, the recommended option
was taken, and the reasoning is recorded here so it survives without the conversation.
Mirrored as `AD-170`..`AD-177` in `.specs/project/STATE.md`.

---

## D-1 (AD-170) — Where recorded samples live

**Options**

1. **In-process bounded ring buffer** ⭐ chosen.
   *Why:* no migration, no new dependency, no I/O in the request path; a bounded
   `deque` append is negligible next to the work it measures; deleting it later costs
   nothing. *Why not:* per-process — with `--workers 2` in production the surface sees
   one worker's slice, and everything is lost on restart.
2. **A PostgreSQL table.** *Why:* survives restarts, aggregates across processes,
   matches Laravel Pulse's actual design. *Why not:* a migration inside a cycle that
   RFC-006 criterion 4 wants schema-free, plus a write amplification of one row per
   request against the very database whose slowness is under investigation.
3. **Redis.** *Why:* already in the stack as the Celery broker; shared across API
   workers and the Celery worker, so the surface could show tasks too. *Why not:*
   the HTTP request path has never touched Redis — even rate limiting is deliberately
   in-memory (`InMemoryFixedWindowRateLimiter`) — so this adds a network dependency,
   and a new failure mode, to every request, in order to measure latency.

**Chosen:** option 1. The cycle is explicitly dev-first and sized S; the measurement
must not become a load-bearing subsystem.

## D-2 (AD-171) — Consequences of the in-process choice, stated rather than hidden

Celery task durations cannot appear in the API surface — different process. They ship
as uniform structured log records instead, which is the cross-process substrate AD-041
already established. The surface itself states that it reports one process's samples,
so a reader cannot mistake a partial view for a total one.

## D-3 (AD-172) — Gating the surface

**Options:** derive from the existing `debug` setting (*why:* no new knob; *why not:*
`debug` is overloaded and its meaning would silently grow to include "exposes timing
data"); a dedicated `dev_instrument_enabled` flag defaulting false ⭐ (*why:* explicit,
greppable, single-purpose, safe by default, testable in both states; *why not:* one
more setting to document); no flag, auth only (*why:* simplest; *why not:* the RFC says
dev-only, and an always-registered diagnostic route is a standing surface).

**Chosen:** the dedicated flag, default false. Enabled in the dev compose override,
absent from the production compose.

## D-4 (AD-173) — Collection is always on; only exposure is gated

Gating collection behind the flag would mean a production process cannot be diagnosed
without a restart that discards the very evidence being chased. The cost of collection
is a bounded append; the risk is exposure. So the flag guards the route, not the
recorder.

## D-5 (AD-174) — Authentication on the dev route in addition to the flag

Defense in depth at negligible cost, reusing `get_authenticated_user`. The browser
reaches the route through the existing Next.js proxy carrying the session cookie, so
this costs no developer convenience.

## D-6 (AD-175) — Slow-query threshold default of 200 ms

Above local noise, below the band the dogfood finding describes ("four seconds").
Configurable per environment; a threshold of zero or below deliberately captures every
statement so tests can exercise the path without sleeping.

## D-7 (AD-176) — Celery durations are additive, not a refactor

The uniform record comes from `task_prerun`/`task_postrun` signals, which cover every
registered task with no per-task code. The existing hand-rolled `_elapsed_ms` logs stay
exactly as they are: they carry domain fields the signal cannot know, and live tests
already assert them. Removing them would be churn with a sensor cost and no benefit.

## D-8 (AD-177) — Execution shape

Four phases, one worker per phase, all on Opus: every phase carries a correctness
invariant (redaction, path-parameter leakage, prod-safe gating, middleware behaviour
under exceptions, engine-event safety), which fails the ship-cycle Haiku-safe test.
The tlc sub-agent offer is auto-accepted under the ship-cycle autonomy contract, whose
only user gate is merge approval. Verifier on Opus, never downshifted.

---

## Pre-existing condition recorded before any code changed

`tests/test_eval_retrieval_metrics.py::TestDeterministicRetrievalMetrics::test_metrics_meet_thresholds`
fails **locally** on `main` before this cycle touched anything: `recall@1` 0.857 against
a 0.9 gate over 42 labeled pairs.

Evidence gathered: CI on the same commit (`cbc296d8`) runs the identical test and passes
(1656 passed / 11 skipped vs. local 1655 passed / 1 failed / 11 skipped — identical
totals, so no selection difference); the local test database holds zero rows; Alembic is
at head (`0015_study_days`); the HNSW index definition is the standard one; and every
retrieval value in `backend/.env` equals the code default. The remaining explanation is
approximate-nearest-neighbour recall varying with HNSW graph construction.

**Not fixed here, deliberately.** RFC-006's exclusions reserve eval-stack ground for the
paused RFC-005. It is carried as a known baseline and raised at the merge gate.

**Gate definition for this cycle:** no new failures against the baseline
`1655 passed / 1 known pre-existing failure / 11 skipped` (backend, local stack up) and
`563 passed` (frontend).

---

## D-9 (AD-178) — Splitting the two timing consumers, mid-cycle

Phase B discovered that the spec's original OBS-08 ("the header's `dur` equals the access
log's `duration_ms`") is only satisfiable by measuring at response *start*, which silently
redefines a shipped observable: a streamed response's `duration_ms` would stop including
the streamed body.

**Options**

1. Accept the redefinition. *Why:* one number, no ambiguity, already implemented.
   *Why not:* Ask and Teach stream by design, and RFC-006 Cycle E's latency claims will
   cite exactly those endpoints. The instrument would go blind precisely where the "app
   feels slow" complaint originates.
2. Let header and log diverge silently. *Why:* no code change. *Why not:* two numbers with
   one name is how observability lies.
3. **Split them deliberately and say so** ⭐ chosen. The header carries time-to-response-start
   (the server's own share — all a browser can attribute anyway); the access log and the
   recorder keep whole-request duration, preserving the pre-cycle meaning of `duration_ms`
   and keeping streaming endpoints rankable by their true cost. *Why not:* two fields to
   understand rather than one, and a second measurement point in the middleware.

**Chosen:** option 3. Spec AC amended in place with the reasoning recorded, not rewritten
to match what was built.

## D-10 (AD-179) — OBS-10 was unsatisfiable as written

A pure-ASGI middleware cannot put a header on a response produced by Starlette's
`ServerErrorMiddleware`, which is always outermost. `X-Request-ID` has always had this
same gap and it is documented in the middleware's own docstring. The AC now states the
real boundary; Phase B pinned both headers' absence in one test so they cannot be fixed
apart. Closing it for real means wrapping the app outside `ServerErrorMiddleware` — a
change to `create_app`'s contract, deliberately not made inside an S-sized cycle.

## D-11 (AD-180) — The settings were inert; Phase D owns the wiring

Phase B found that nothing calls `set_recorder(...)` at app assembly, so
`LEARNY_INSTRUMENT_CAPACITY` and `LEARNY_SLOW_QUERY_STATEMENT_CHARS` had no effect. Neither
Phase A (told to wire nothing) nor Phase B (told not to touch app assembly) owned it — a
gap in the task breakdown, not in anyone's execution. Added to the spec as OBS-26 and
assigned to Phase D, which already touches `create_app` for the dev route.
