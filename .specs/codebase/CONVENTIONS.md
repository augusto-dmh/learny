# Codebase Conventions

Tooling conventions established during Cycle 1 (Scaffold + Identity). These are
LOCKED defaults for the repo unless a follow-up decision changes them.

## Backend (`/backend`) — Python / FastAPI (ADR-004)

- **Language runtime:** Python `>=3.13` (pinned via `backend/.python-version` → `3.13`).
- **Package / environment manager:** [`uv`](https://docs.astral.sh/uv/).
  - Dependencies declared in `backend/pyproject.toml`; resolved lock in `backend/uv.lock` (committed).
  - Install/sync: `uv sync --extra dev`. Run anything: `uv run <cmd>`.
  - `uv` is installed via the official installer to `~/.local/bin` (system pip is
    PEP-668 externally-managed, so `pip install uv` is not used here).
- **Build backend:** `hatchling` (package = `app`).
- **Web framework:** FastAPI + uvicorn (ASGI).
- **Config:** `pydantic-settings`, env-prefixed `LEARNY_`; secrets via env only
  (`.env` is git-ignored; `backend/.env.example` is the contract).
- **DB access / migrations:** SQLAlchemy 2.x + psycopg v3 driver
  (`postgresql+psycopg://…`); Alembic for migrations (`backend/migrations`).
- **Test runner:** `pytest` (+ `pytest-asyncio`, `httpx` for `TestClient`).
  - Run: `uv run pytest`. Config in `pyproject.toml` (`testpaths=["tests"]`,
    `pythonpath=["."]`, `asyncio_mode=auto`).
- **Lint / format:** `ruff` (`uv run ruff check .`, `uv run ruff format .`);
  line length 100; rule sets `E,F,I,UP,B`.
- **Layering (ADR-007/009):** `app/{domain,application,infrastructure,core}`.
  `domain` imports nothing from infrastructure/FastAPI/SDKs; adapters depend
  inward only. The `infrastructure/web` package is the HTTP composition root.

## Frontend (`/frontend`) — React / Next.js (ADR-004)

- **Node version:** Node `>=20` (developed against Node 24 in this environment);
  pinned via `frontend/.nvmrc`.
- **Package manager:** `npm` (lockfile `frontend/package-lock.json`, committed).
- **Framework:** Next.js App Router + TypeScript.
- **Test runner:** `vitest` (`npm test`).
- **Proxy boundary (ADR-017):** `frontend/app/api/*` thin same-origin proxy to
  FastAPI; no domain logic in the proxy.

## Local stack (`docker compose`)

`docker-compose.yml` (repo root) brings up six services: `db`
(postgres+pgvector), `redis`, `minio`, `api` (FastAPI, runs `alembic upgrade
head` then uvicorn), `worker` (Celery), `web` (Next.js). Start: `docker compose
up -d --build`.

Smoke check (AC-1), all verified in this environment:
- `curl localhost:8000/healthz` → `{"status":"ok"}`
- `curl localhost:8000/readyz` → `{"status":"ready","database":"ok"}`
- `curl localhost:3000/` → HTTP 200; proxy round-trip `localhost:3000/api/...`
  reaches FastAPI (`server: uvicorn`).
- `docker exec learny-worker-1 celery -A app.worker.celery_app:celery_app inspect ping` → pong.
- db/redis/minio/api/worker report `(healthy)`. `web` has no compose healthcheck
  (node:slim has no curl; Next dev has no health route) — liveness is proven by
  the HTTP 200 + proxy round-trip instead.

## Cross-cutting

- **Commits:** Conventional Commits; one atomic commit per spec task.
- **Secrets:** never committed; env-only. `.env.example` files document the contract.
