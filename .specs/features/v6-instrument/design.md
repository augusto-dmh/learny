# App Instrumentation — Design

## Shape

One recorder module, three producers, one consumer.

```
                 ┌──────────────────────────────┐
 HTTP request ──▶│ RequestContextMiddleware      │──▶ recorder.record_request()
                 │ (already times the request)   │──▶ Server-Timing header
                 └──────────────────────────────┘
 SQL statement ──▶ engine before/after_cursor_execute ──▶ recorder.record_query()
                                                       └▶ structured log
 Celery task  ──▶ task_prerun / task_postrun signals  ──▶ structured log (other process)

                 ┌──────────────────────────────┐
                 │ dev instrument router (gated) │◀── recorder.snapshot()
                 └──────────────────────────────┘
```

The recorder is the only place that holds state. Producers push; the consumer reads.
No producer knows about the consumer.

## Seams (verified by survey; `file:line` as of `cbc296d8`)

**Request path**
- `RequestContextMiddleware` — `backend/app/infrastructure/web/middleware.py:50`, pure ASGI
  by deliberate choice (docstring at `:3`: `BaseHTTPMiddleware` would break the shared
  contextvar context). `__call__` at `:56`; already calls `time.perf_counter()` at `:68`
  and computes `duration_ms` at `:75`; already emits the `http.request` access log at
  `:76-79`; `_make_send_wrapper` at `:82` already injects `X-Request-ID` into
  `http.response.start` at `:87-90`. Both new behaviours attach here — the timing already
  exists, it is currently only logged.
- App assembly — `create_app()` at `backend/app/main.py:30`; the single `add_middleware`
  at `:37`; routers included `:39-50`.

**Database path**
- `get_engine()` — `backend/app/infrastructure/db/engine.py:23`, `@lru_cache`, single
  `create_engine(...)` at `:36`. A `@event.listens_for(engine, "connect")` hook already
  lives at `:38-45` — the precedent for attaching engine events at build time.
- Repositories take a raw `Connection`; there is no `sessionmaker` and no ORM `Session`.
- Tests build their **own** engine (`backend/tests/conftest.py:19,69`), and Alembic has
  its own. Only the application engine is instrumented; that asymmetry is intentional and
  must be reflected in how the tests reach the listener.

**Worker path**
- `celery_app` — `backend/app/worker/celery_app.py:17-22`; `conf.update(...)` at `:27-39`
  (`worker_hijack_root_logger=False` at `:38` is what lets app-owned logging survive);
  `configure_logging()` at `:41`. **No signal handlers exist today.**
- Hand-rolled timing to leave alone: `_elapsed_ms` at `backend/app/worker/tasks.py:85-87`,
  used at `:286, :295, :304, :376, :503, :515, :608`.

**Logging / trace substrate (reuse, do not rebuild)**
- `configure_logging` — `backend/app/core/logging.py:145`; `JsonFormatter` `:99`;
  `SensitiveDataFilter` `:74`.
- `bind_trace` / `current_trace` — `backend/app/core/tracing.py:66, :82`.
- Access logger `logging.getLogger("app.request")` — `middleware.py:39`.

**Web / auth idiom**
- Routers live in `backend/app/infrastructure/web/`; a typical protected route parameter
  is `user: Annotated[User, Depends(get_authenticated_user)]`
  (`dependencies.py:239`; `resolve_current` at `:211`).
- Settings dependency alias `AppSettings` — `dependencies.py:170`.

**Frontend boundary**
- `relayResponse` — `frontend/app/lib/proxy.ts:115`; response denylist
  `STRIPPED_RESPONSE_HEADERS` at `:60` is `content-encoding` / `content-length` only, so
  `Server-Timing` passes through today. That is a property to pin with a test, not to
  assume forever.

## Configuration

New `Settings` fields (`backend/app/core/config.py:14`, `env_prefix="LEARNY_"`), following
the existing `<area>_<thing>_enabled` / `<area>_max_<unit>` naming:

| Field | Env | Default |
| --- | --- | --- |
| `dev_instrument_enabled` | `LEARNY_DEV_INSTRUMENT_ENABLED` | `false` |
| `instrument_capacity` | `LEARNY_INSTRUMENT_CAPACITY` | bounded sample count |
| `slow_query_ms` | `LEARNY_SLOW_QUERY_MS` | `200` |
| `slow_query_statement_chars` | `LEARNY_SLOW_QUERY_STATEMENT_CHARS` | statement cap |

**Trap:** `LEARNY_LOG_FORMAT` is deliberately *not* a `Settings` field — it is read from
`os.environ` in `configure_logging` (`logging.py:160-164`) because calling `get_settings()`
at import time primed the `lru_cache` and pinned a stale database URL for Alembic's
`env.py` (recorded as lesson L-007). Anything these new settings touch at *import* time
inherits that hazard; anything read per-request or at app-assembly time does not.

## Invariants

1. **No path-parameter values, query strings, headers, or bodies are ever recorded.**
   Ranking keys on the route template; an unmatched request buckets under one constant
   placeholder. A raw path is a data leak into a surface with weaker access control than
   the resources it names.
2. **No bound parameter values reach a captured statement.** Session tokens and password
   hashes travel as bound parameters; the SQL text alone is safe, the parameters are not.
3. **The instrument never changes the outcome of what it measures.** A failure inside the
   recorder, the query listener, or the header path must leave the request's response,
   status code, and the database operation exactly as they would have been.
4. **The surface is unreachable unless deliberately enabled**, and reports honestly that
   it shows a single process's samples.
5. **Existing behaviour is preserved**: the `http.request` access log, `X-Request-ID`,
   the per-task `duration_ms` records, and `worker_hijack_root_logger=False` all keep
   working unchanged.

## Phase boundaries

| Phase | Owns | Depends on |
| --- | --- | --- |
| A | Recorder module + settings + env contract | — |
| B | Request recording + `Server-Timing` + proxy survival test | A |
| C | Slow-query capture + Celery duration signals | A |
| D | Dev-only surface + ops doc + roadmap | A, B, C |

B and C are independent of each other; both consume A's recorder API, which is why A
lands first and alone.
