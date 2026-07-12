# Production-Like Readiness Design

**Spec:** `.specs/features/production-readiness/spec.md`
**Context:** `.specs/features/production-readiness/context.md`
**Decisions:** AD-040..AD-044

Provider-neutral by construction: no new runtime dependency, no metrics/monitoring/TLS/proxy vendor.
Standard library only for the observability code; PyYAML (already present in the backend env) only in tests.

---

## 1. Architecture Overview

Three independent slices, no shared runtime coupling:

```
Phase A  Observability hooks (backend, stdlib only)
  app/core/tracing.py        ← ContextVar trace store + TraceContextFilter + request-id helpers
  app/core/logging.py        ← + JsonFormatter, log-format toggle, attach TraceContextFilter (redaction preserved)
  app/infrastructure/web/middleware.py  ← RequestContextMiddleware (pure ASGI): bind request_id, echo header, access log
  app/main.py                ← install middleware
  app/infrastructure/web/dependencies.py ← resolve_current binds user_id into trace
  app/worker/tasks.py        ← bind job_id/source_id trace + duration_ms on terminal logs
  app/core/config.py         ← LEARNY_LOG_FORMAT setting

Phase B  Production deployment shape (config)
  docker-compose.prod.yml    ← overlay (ports/restart/images/env/commands hardening)
  frontend/Dockerfile        ← + production build+start target/stage; next.config.ts output: 'standalone'
  backend/.env.production.example, frontend/.env.production.example

Phase C  Operator runbooks (docs)
  docs/ops/backups.md, docs/ops/rollback.md
```

---

## 2. Phase A — Observability

### 2.1 Trace context (`app/core/tracing.py`)

- `_TRACE: ContextVar[dict[str, str] | None] = ContextVar("learny_trace", default=None)`.
- `bind_trace(**fields) -> None`: get the current dict (create a fresh one and `set` it if `None`), update it in place with stringified non-`None` values. Mutating the per-context dict means fields bound later in the request (e.g. `user_id` at auth) are visible to every subsequent log record.
- `current_trace() -> dict[str, str]`: return a shallow copy of the current dict (or `{}`).
- `new_trace_scope() -> Token`: `set` a **fresh** dict and return the token; `reset_trace(token)` restores. Used by the middleware and the worker so each request/task starts clean and no state leaks across them.
- `new_request_id() -> str`: `uuid4().hex`.
- `sanitize_request_id(raw: str | None) -> str | None`: return `None` if empty; else keep only a safe charset (`[A-Za-z0-9._-]`) and truncate to `_MAX_REQUEST_ID_LEN = 128`. Prevents log injection / unbounded IDs (PROD-18).
- `class TraceContextFilter(logging.Filter)`: on `filter`, for each key/value in `current_trace()` that isn't already a real attribute, `setattr(record, key, value)`; always return `True`. Outside a request/task the store is `None` → nothing injected (PROD-20).

**Concurrency:** each request/task runs in its own copied context (uvicorn/anyio + Celery worker), and the middleware/worker `set` a fresh dict per scope, so mutation is context-local — no cross-request leakage.

### 2.2 Logging (`app/core/logging.py`)

- Add `class JsonFormatter(logging.Formatter)`: `format` builds a dict — `timestamp` (ISO from `record.created`), `level`, `logger`, `message` (`record.getMessage()`), plus every non-reserved record attribute (the trace fields + any `extra=`), and `exc_info`/`exc_text` rendered to a string when present — then `json.dumps(..., default=str, ensure_ascii=False)` as one line.
- Rework `configure_logging(level, log_format)`:
  - default `log_format` from `get_settings().log_format` (`"human"` | `"json"`).
  - Build/replace a single root `StreamHandler`; set `JsonFormatter` when `json`, else the existing human `Formatter`.
  - Attach BOTH `SensitiveDataFilter` **and** `TraceContextFilter` to the handler and to the root logger.
  - Idempotent: guard with `_CONFIGURED`; re-invocation must not duplicate handlers/filters or drop the redaction filter (PROD edge: idempotent). Redaction runs before the formatter serializes (filters precede formatting), so JSON output is redacted (PROD-13).

### 2.3 Middleware (`app/infrastructure/web/middleware.py`)

Pure ASGI middleware (no `BaseHTTPMiddleware` — avoids its contextvar task-hop pitfalls; the endpoint and its dependencies run in the **same** context the middleware set, so `user_id` bound in `resolve_current` is visible to handler logs).

```
class RequestContextMiddleware:
    def __init__(self, app): self.app = app
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http": return await self.app(scope, receive, send)
        request_id = sanitize_request_id(<X-Request-ID from scope headers>) or new_request_id()
        token = new_trace_scope()
        bind_trace(request_id=request_id, method=scope["method"], path=scope["path"])
        start = time.perf_counter()
        status_holder = {"code": 500}          # default if response never starts
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
                headers = MutableHeaders(raw=message["headers"])
                headers["X-Request-ID"] = request_id     # echo on every started response
            await send(message)
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            dur_ms = round((time.perf_counter() - start) * 1000, 3)
            logging.getLogger("app.request").info(
                "http.request",
                extra={"status_code": status_holder["code"], "duration_ms": dur_ms},
            )  # method/path/request_id come from the trace filter
            reset_trace(token)
```

- Route/path: use `scope["path"]` (raw path). The FastAPI route template is only known after routing; raw path is sufficient and avoids coupling. (Cardinality is an operator concern for the deferred metrics layer, not this cycle.)
- Header parse: read `scope["headers"]` (list of `(bytes, bytes)`); case-insensitive match on `b"x-request-id"`.
- Access log emitted exactly once in `finally` → fires for success, handled errors, and unhandled 500 (PROD-11, edge cases). Header injected for every response whose `http.response.start` passes through us — i.e. all handled responses (PROD-07/08). Truly unhandled 500s are produced by Starlette's outermost `ServerErrorMiddleware` (outside us): access log still fires, header not guaranteed — documented in the module (accepted gap).

### 2.4 Wiring

- `main.py`: `app.add_middleware(RequestContextMiddleware)` (added once; it becomes the outermost user middleware, wrapping the exception-handling middleware so handled error responses get the header).
- `dependencies.py` `resolve_current`: after `current_user(...)` succeeds, `bind_trace(user_id=str(user.id))` (PROD-10). Bind only on success — an anonymous/failed request carries no `user_id`.
- `config.py`: `log_format: str = "human"` (env `LEARNY_LOG_FORMAT`).

### 2.5 Worker (`app/worker/tasks.py`)

- At `run_ingestion` entry: `token = new_trace_scope(); bind_trace(job_id=job_id, source_id=source_id)`; wrap body in `try/finally: reset_trace(token)`.
- `start = time.perf_counter()`; on each terminal log (succeeded / failed / failed-retries-exhausted) add `duration_ms` to `extra` (PROD-14). Retry log keeps job/source fields (now via trace) — no secret leakage (ING-08 preserved).
- `configure_logging()` is called once in the worker too (Celery `worker_process_init` or lazily at task start) so worker logs are structured + filtered. Verify the celery app already configures logging; if not, call `configure_logging()` at module import of `tasks.py` (idempotent).

---

## 3. Phase B — Deployment shape

### 3.1 `docker-compose.prod.yml` overlay (applied `-f docker-compose.yml -f docker-compose.prod.yml`)

Per service, override **only** prod-specific keys:

| Service | Overrides |
|---|---|
| `db` | drop `ports` (use `ports: []`? — Compose merges lists by append, so instead **do not** publish; achieve "no host port" by NOT re-adding and by binding to `127.0.0.1` is not enough). See §3.2. `restart: unless-stopped`; `image: pgvector/pgvector:pg16` (already tag-pinned). `env_file: [./secrets/db.env]` for `POSTGRES_PASSWORD`. |
| `redis` | no host port; `restart: unless-stopped`; `image: redis:7.4-alpine` (pin minor). |
| `minio` | no host port; `restart: unless-stopped`; `image: minio/minio:RELEASE.2024-…` (pin from `:latest`); creds via `env_file`. |
| `api` | `restart: unless-stopped`; `env_file: [./secrets/api.env]`; env `LEARNY_ENVIRONMENT=production`, `LEARNY_SESSION_COOKIE_SECURE=true`, `LEARNY_LOG_FORMAT=json`; command `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${LEARNY_API_WORKERS:-2}` after migrate. |
| `worker` | `restart: unless-stopped`; `env_file`; `LEARNY_LOG_FORMAT=json`. |
| `web` | `restart: unless-stopped`; `build.target: prod`; command runs the built app (`node server.js` for standalone, or `npm run start`); `LEARNY_LOG_FORMAT` n/a. |

**Host-port hardening (PROD-01):** Compose **merges** the `ports` list (append), so an overlay cannot remove a base port by redefining `ports`. Resolution: move the host-published `ports` for `db`/`redis`/`minio` OUT of the base file into a **`docker-compose.override.yml`** (the file Compose auto-loads for local dev), leaving the base file port-free for those three. Then the prod invocation (`-f base -f prod`, no override) publishes no host ports for them, while local `docker compose up` (base + auto override) keeps them. `api`/`web` keep their published ports in the base (they are the public surface). This keeps local aligned (ADR-0008 §3) and is the idiomatic Compose pattern.
  - **Migration cost:** create `docker-compose.override.yml` with the `db`/`redis`/`minio` `ports`; remove those three `ports:` blocks from `docker-compose.yml`. `api`/`web` ports stay in base.

### 3.2 Frontend production image

- `frontend/next.config.ts`: add `output: "standalone"`.
- `frontend/Dockerfile`: convert to multi-stage —
  - `base`/`deps`: `npm ci`.
  - `build`: `npm run build` → produces `.next/standalone` + `.next/static`.
  - `prod` target: copy standalone output, run `node server.js` on port 3000 (non-root user), no dev server.
  - keep a `dev` path or leave base compose using the existing dev command; the prod overlay selects `build.target: prod`.
- Gate: `npm run build` must succeed (real check). Structural test asserts the Dockerfile has a build stage and a non-dev start command.

### 3.3 Env examples

- `backend/.env.production.example`: production-oriented values — `LEARNY_ENVIRONMENT=production`, `LEARNY_SESSION_COOKIE_SECURE=true`, `LEARNY_LOG_FORMAT=json`, `LEARNY_CSRF_TRUSTED_ORIGINS=https://<your-domain>`, placeholders for injected DB/storage secrets, `LEARNY_API_WORKERS`.
- `frontend/.env.production.example`: `LEARNY_API_BASE_URL=http://api:8000`, `LEARNY_APP_ORIGIN=https://<your-domain>`.

---

## 4. Phase C — Runbooks

- `docs/ops/backups.md`: what to back up (PostgreSQL `learny` DB, MinIO/object-storage bucket, secrets/env, Compose files); PostgreSQL logical backup (`pg_dump -Fc` via `docker compose exec`) + restore (`pg_restore`); object-storage bucket backup/restore (`mc mirror` both directions, provider-neutral S3 tooling); a restore-drill checklist; retention/offsite as an operator TODO tied to OQ #10.
- `docs/ops/rollback.md`: reproduce the TDD **operational rollback triggers** table; independent revert of `api`/`worker`/`web` images (re-pin the prior tag, `up -d <svc>`); migration reversibility (`alembic downgrade -1`) + the forward-only exception path; the corpus **atomic-replace / no-versioning** implication (AD-018) — a rollback of the corpus/index build re-runs ingestion, it does not restore a prior corpus version; the two-`-f` prod invocation reminder.
- Light `tests/test_ops_docs.py`: both files exist and contain required section headings / key commands / the triggers.

---

## 5. Testing Strategy

| AC | Test | Kind |
|---|---|---|
| PROD-07/08/18 | `TestClient` GET a route; assert `X-Request-ID` generated / echoed / sanitized | unit (web) |
| PROD-09/10 | caplog on a route; assert `request_id` on records; authenticated route adds `user_id` | unit (web) |
| PROD-11/19 | assert exactly one `http.request` access record with method/path/status/duration; handled-error path keeps header + logs; unhandled path (`raise_server_exceptions=False`) logs 500 | unit (web) |
| PROD-12/13 | format a record via `JsonFormatter`; assert single-line JSON + trace fields; sensitive extra REDACTED | unit (logging) |
| idempotent | call `configure_logging()` twice; assert single handler, both filters present | unit (logging) |
| PROD-20 | `TraceContextFilter` outside a scope injects nothing; two sequential scopes don't bleed | unit |
| PROD-14 | call `run_ingestion` with fakes (as existing worker tests do); assert `job_id`/`source_id` on records + `duration_ms` on terminal | unit (worker) |
| PROD-01..05 | load base+overlay YAML with `yaml.safe_load`; assert no host ports for db/redis/minio, restart policies, no `:latest`, secure/env/json env on api, secrets via env_file | unit (config) |
| PROD-06 | assert `frontend/Dockerfile` has a build stage + non-`dev` start; `next.config` has `output: standalone`; `npm run build` gate | build gate + static |
| PROD-15/16/17 | `test_ops_docs.py` presence/content | unit |

All backend tests deterministic, no network. Gate per task: `uv run pytest` (backend), `uv run ruff check .`, `npm run build`/`tsc`/`vitest` for frontend touches.

---

## 6. Risks & Mitigations

- **BaseHTTPMiddleware contextvar pitfall** → use pure ASGI middleware (§2.3).
- **Compose list-merge can't remove ports** → move dev ports to `docker-compose.override.yml` (§3.1); verified by YAML tests against the exact prod invocation.
- **Redaction regression under JSON** (L-005 territory: logging config is fragile) → explicit test that a sensitive extra is redacted in JSON output, and that double `configure_logging()` keeps the filter.
- **Next.js standalone build breakage** → `npm run build` is a hard gate; if `output: standalone` surfaces issues, fix in the same task before commit.
- **Worker logging not configured** → ensure `configure_logging()` runs in the worker process (idempotent call at `tasks.py` import if Celery doesn't).
