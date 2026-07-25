# App Instrumentation Runbook

How to find out *why* a request was slow, using the in-process instrument shipped
with the application (RFC-006 Cycle A). This is a **development diagnosis tool**,
not a monitoring stack: it has no alerting, no retention, and no cross-process
aggregation. Host and per-container health live in
[monitoring.md](monitoring.md) (Netdata, ADR-0024); the two answer different
questions and neither replaces the other.

> Local invocation used throughout this doc: a plain `docker compose <cmd>`,
> which auto-loads `docker-compose.override.yml`. That override is what enables
> the surface; production never loads it (AD-042).

## The three producers

Everything the instrument knows comes from one of three places, and only the
first two reach the surface at all:

| Producer | Where it lands | Notes |
|---|---|---|
| Every completed HTTP request | in-process recorder + `http.request` access log | Keyed on the **route template** (`/api/sources/{source_id}`), never the raw path |
| Slow SQL statements on the application engine | in-process recorder + `db.slow_query` log record | Statement text only; bound parameter values are never read |
| Every Celery task attempt | `task.duration` log record **only** | The worker is a different process — see "What it does not cover" |

## Read the surface

The route is `GET /api/dev/instrument`. Reach it through the Next.js proxy so the
browser sends your session cookie:

```
http://localhost:3000/api/dev/instrument
```

Three independent gates guard it, and all must hold:

- `LEARNY_DEV_INSTRUMENT_ENABLED` must be true. The route is *mounted* only when
  it is, so with the flag off the path matches nothing (**404**) and does not
  appear in `/openapi.json`. `docker-compose.override.yml` sets it for the local
  `api` service; nothing in the production overlay does.
- The process must not be production. `LEARNY_ENVIRONMENT=production` refuses the
  mount even with the flag set, and logs a `WARNING` on
  `app.instrument` (`instrument.surface.refused`) so a set-but-ignored flag is
  visible rather than silent. See "Why it is not exposed in production" below.
- You must be signed in. An enabled surface with no valid session answers
  **401**. Turning the flag on does not remove the need to authenticate.

The response is JSON:

| Field | Meaning |
|---|---|
| `scope` | A sentence stating what these numbers do *not* cover. Read it before quoting them |
| `capacity` | Samples retained per buffer, from `LEARNY_INSTRUMENT_CAPACITY` |
| `endpoints[]` | One row per `(method, route template)`: `count`, `mean_ms`, `max_ms`, `p95_ms` |
| `slow_queries[]` | Captured statements, newest first: `statement`, `duration_ms` |

`endpoints` is ordered by descending `p95_ms`, then by descending `max_ms`. p95
is nearest-rank — the ascending-sorted duration at index `ceil(0.95 * n) - 1` —
so with a handful of samples it is simply the slowest one. **Read `count` before
believing a ranking**: an endpoint hit twice sits at the top on one bad request.

An idle process answers 200 with both collections empty. That is not an error; it
means nothing has been recorded since the last restart.

## Read the browser's own split

With the instrument enabled, every response the application produces carries
`Server-Timing: app;dur=<ms>`, visible in the browser devtools network panel. It
survives the Next.js proxy.

The header ships on the same switch as the surface — `LEARNY_DEV_INSTRUMENT_ENABLED`,
refused on a production process — so **there is no server-timing split in
production**. It is the only part of the instrument that leaves the process and
the only one an anonymous caller can read: `/api/auth/*` maintains uniform login
timing in application code (a dummy password hash on the missing-account path),
and a microsecond server-side reading with network jitter already removed is
exactly the signal that defence exists to withhold. In production the log is the
instrument, and it reports the same number as `response_start_ms`.

That number is the **time to response start** — the server's own share, which is
all a browser can attribute to us. It is deliberately *not* the same number as
the access log's `duration_ms`:

| Number | Where | Measures |
|---|---|---|
| `Server-Timing: app;dur=` | response header | Time from receiving the request to starting the response |
| `response_start_ms` | `http.request` access record | The same measurement, so the header is traceable to a log line |
| `duration_ms` | `http.request` access record | The **whole** request, streamed body included |

The recorder ranks on `duration_ms`, not on the header's number. Ask and Teach
stream by design, and the generation time behind a streamed answer is the point
of measuring at all — so a streaming endpoint ranks by what it actually costs,
and the gap between the two numbers *is* the streaming time.

## Read the logs

The surface is a convenience; the logs are the substrate, and the only thing that
crosses process boundaries.

```bash
docker compose logs api      | grep db.slow_query
docker compose logs worker   | grep task.duration
```

| Record | Logger | Level | Carries |
|---|---|---|---|
| `http.request` | `app.request` | INFO | `status_code`, `duration_ms`, `response_start_ms` |
| `db.slow_query` | `app.query` | **WARNING** | `statement`, `duration_ms` |
| `task.duration` | `app.task` | INFO | `task_name`, `task_id`, `state`, `retries`, `duration_ms` |

Slow queries log at WARNING on purpose: a statement over the threshold is a thing
you want to see without raising the log level. The consequence is that **lowering
`LEARNY_SLOW_QUERY_MS` toward zero in dev produces one WARNING per statement** —
useful for a few minutes, unusable for a working day.

The log record carries the statement **untruncated**; the recorder caps it at
`LEARNY_SLOW_QUERY_STATEMENT_CHARS`. That asymmetry is deliberate: a log stream
wants the whole statement, a bounded in-memory buffer must not hold arbitrarily
long strings.

## Configuration

| Variable | Default | Effect |
|---|---|---|
| `LEARNY_DEV_INSTRUMENT_ENABLED` | `false` | Mounts `GET /api/dev/instrument` **and** emits the `Server-Timing` header. Set only in the local override; refused on a `production` process |
| `LEARNY_INSTRUMENT_CAPACITY` | `500` | Samples retained per buffer, per process. Oldest are discarded |
| `LEARNY_SLOW_QUERY_MS` | `200` | A statement counts as slow at or **above** this. Zero or below captures every statement |
| `LEARNY_SLOW_QUERY_STATEMENT_CHARS` | `2000` | Cap on captured statement text (recorder only) |

Collection is always on; only the surface is gated. A process that turns out to
be slow can therefore be diagnosed without a restart that would discard the very
evidence being chased.

## What it does not cover

State these when quoting a number from this tool. Every one of them is a design
consequence, not a defect:

- **One process.** Samples live in that process's memory. Production runs
  `uvicorn --workers ${LEARNY_API_WORKERS:-2}`, so the surface shows roughly one
  worker's slice of traffic. Local compose runs a **single** API worker, where the
  view is complete — which is why this is a dev-first tool.
- **Nothing survives a restart.** There is no table and no file behind it.
- **No Celery task durations.** The worker is a different process with its own
  memory, so ingestion and embedding timings appear as `task.duration` log
  records only, never as rows on the surface.
- **Only the application engine is instrumented.** Alembic and the test suite
  build their own engines; migrations are deliberately not timed.
- **A slow statement that ends in a database error is not captured.**
  SQLAlchemy's `after_cursor_execute` does not fire for a failed statement, so
  capture covers *completed* statements. A query that times out leaves a log
  record from whoever raised, not a slow-query entry.
- **A truly unhandled exception's response carries neither `Server-Timing` nor
  `X-Request-ID`.** Starlette's `ServerErrorMiddleware` is always outermost and
  produces that 500 outside the application's own middleware. This is a
  pre-existing, documented boundary that `X-Request-ID` has always had — not a
  new gap. The request is still access-logged and still recorded with its final
  status, so it is not missing from the ranking.
- **Nothing here is a metric.** No exporter, no scrape endpoint, no thresholds
  (AD-041 deferred those deliberately; ADR-0024 locked the self-hosted stance).

## Why it is not exposed in production

The surface renders SQL statement text and an endpoint inventory to any
authenticated account — there is no admin role to narrow it to. The production
overlay sets neither the flag nor anything that would, and `test_compose_prod.py`
asserts that no production service carries `LEARNY_DEV_INSTRUMENT_ENABLED`, so a
regression there fails CI rather than the deployment.

That omission is not what makes production safe, because it is not the only way
the flag can arrive: the production `api` service also loads an
operator-authored `secrets/api.env`, and `Settings` reads `.env` from the working
directory. So the refusal lives in the application instead. A process running
with `LEARNY_ENVIRONMENT=production` does not mount the route at all, whatever
set the flag, and logs the refusal at `WARNING` so the misconfiguration surfaces.

Collection is unaffected by any of this — only exposure is refused. In
production, the instrument is the structured log (above): it carries the same
durations and every slow statement, and it crosses process boundaries.

## No identifier reaches the surface

The recorder has no parameter that accepts a raw path, a query string, a header,
or a body. Requests are keyed on the route template; a request that matched no
route buckets under a single constant placeholder. Slow-query capture reads the
SQL text and never the `parameters` argument, which is the half that carries
session tokens and password hashes. This is a property of what the recorder can
hold, not a filter applied on the way out.
