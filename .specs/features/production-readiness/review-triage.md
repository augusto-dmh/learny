# Review Triage — production-readiness (PR #16)

Independent review posted 5 inline findings (1 security, 4 suggestions) + a
requirements summary (20/20 implemented, no blockers) + a consolidated summary.
0 critical / 0 warnings / 0 performance / 0 regression. Each finding judged
against the code as it exists; comments are deleted after fixes land, so this is
the surviving record.

| # | Source comment | file:line | Verdict | Action | Rationale |
|---|---|---|---|---|---|
| 1 | 🔒 security (id 3567325603) | `docker-compose.prod.yml` (db:22, minio:35, api:46, worker:58) | **Real** | **Fix** | Confirmed: base is secret-free and the override (dev creds) is NOT loaded in prod, so a missing `./secrets/*.env` makes `pydantic-settings` fall back to the **in-code defaults** in `config.py` (`storage_secret_key="learny-dev-secret"`, `csrf_trusted_origins="http://localhost:3000"`, dev `database_url`). A hardened prod stack must fail fast, not boot on baked-in dev values. Set `required: true` on all four prod `env_file` entries. The YAML-merge test uses `yaml.safe_load` (not `docker compose config`), so it does not depend on `required: false`. |
| 2 | 💡 tests (id 3567325893) | `backend/app/worker/tasks.py:217` | **Real** | **Fix** | The third terminal branch (`failed (retries exhausted)`) gained `duration_ms` but `test_run_ingestion_retryable_exhausted_fails` does not capture logs, so a dropped `duration_ms`/trace field there is undetected. Extend that test to assert the record under `_capture_worker_logs()`. Cheap, closes a real branch gap. |
| 3 | 💡 tests (id 3567325928) | `backend/app/worker/celery_app.py:38` | **Real** | **Fix** | The worker logging seam (`worker_hijack_root_logger=False` + `configure_logging()`) keeps redaction + trace filters alive in the worker process (a security-relevant seam), yet no test references it — re-enabling the hijack would silently drop worker-log redaction with no gate failure. Add a unit test asserting the flag is `False` and the `_learny` handler carries both filters after import. |
| 4 | 💡 tests (id 3567325947) | `backend/app/main.py:32` | **Real** | **Fix** | Every request-context test builds a throwaway `FastAPI()`; nothing drives the assembled `create_app()`, so deleting `add_middleware(RequestContextMiddleware)` passes all tests. Add one assertion via `create_app()` (e.g. `TestClient(create_app()).get("/healthz")` → `X-Request-ID` present) so the production wiring is covered. Genuine discrimination gap. |
| 5 | 💡 architecture (id 3567326866) | `backend/app/core/config.py:36` | **Real** | **Fix** | `Settings.log_format` is unread — `configure_logging` reads `os.environ["LEARNY_LOG_FORMAT"]` directly (deliberately, to avoid priming the `get_settings` lru-cache that Alembic's `env.py` reads). The field is dead and creates a second source of truth. Remove it and document the intentional env-only read at the read site; `LEARNY_LOG_FORMAT` stays documented in the prod compose overlay + `.env.production.example`. |

## Requirements summary (id 4953163330) & consolidated summary (id 4953174580)

Informational — 20/20 spec + ADR requirements implemented, no blockers. No action;
deleted with the other comments in the cleanup stage.

## Disposition

All 5 findings accepted as **Fix** (1 security, 4 quality/coverage). None rejected —
the review was accurate. Fixes grouped into atomic commits:
- `fix(deploy)` — `required: true` on prod secret env_files + strengthen the compose test.
- `test(observability)` — worker logging-config seam, middleware wiring via `create_app()`, exhausted-retry log assertion.
- `refactor(observability)` — remove the dead `Settings.log_format`, document the env-only read.
