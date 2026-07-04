# Design — Cycle 1: Scaffold + Identity Foundation

Specializes TDD-001 to Cycle 1. Architecture, boundaries, data model, API contract, and flows are
inherited from TDD-001 and the ADRs (not re-decided). This doc adds only: repo layout, the Identity
module internals, and how AD-006/007/008 are wired.

## 1. Repository layout (FR-SCAF-003/004)

Monorepo, two deployables + shared infra:

```
/backend            FastAPI app (ADR-004) — layered per ADR-007/009
  /app
    /domain         entities + value objects + ports (NO framework/SDK imports)
    /application    use-case services (register, login, logout, current-user, authorize)
    /infrastructure adapters: db repositories, hashing, session store, storage(MinIO), web(FastAPI routers)
    /core           config, logging (with redaction), security primitives
  /migrations       schema migrations (FR-SCAF-006)
  /tests            unit + integration (pytest)
/frontend           Next.js app (ADR-004)
  /app              routes + minimal auth screens
  /app/api          thin same-origin proxy to FastAPI (ADR-017) — no domain logic
  /tests
/docker-compose.yml local topology (FR-SCAF-001)
```

Boundary rule (enforced by review + import-linting in a later cycle): `domain` imports nothing from
`infrastructure`/FastAPI/SDKs; adapters depend inward only.

## 2. Compose topology (FR-SCAF-001/002, AD-008)

Services: `api` (FastAPI+uvicorn), `web` (Next.js), `db` (postgres+pgvector image), `redis`,
`worker` (Celery, minimal — no tasks yet this cycle), `minio` (S3-compatible).
Health: `api` `/healthz` (liveness) + `/readyz` (checks db); `worker` liveness via Celery ping;
compose `healthcheck` for db/redis/minio. Worker exists to prove wiring; ingestion tasks are Phase 4.

## 3. Identity module (TDD Module: Identity And Access)

### Domain
- `User` (id, email, created_at) — no password material on the entity.
- `PasswordCredential` (user_id, hash, algo metadata) — Argon2id (AD-006).
- `Session` (id, user_id, token_hash, csrf_token, expires_at, created_at, last_seen_at) (AD-006/007).
- Ports: `UserRepository`, `CredentialRepository`, `SessionRepository`, `PasswordHasher`, `Clock`, `StoragePort`.

### Application services
- `RegisterUser` → validate input (FR-AUTH-010), ensure email unique, hash password (Argon2id), create user+credential, create session. 
- `AuthenticateUser` (login) → fetch credential by email, verify hash (constant-time/lib-handled), create session on success; uniform failure to avoid user enumeration.
- `Logout` → delete/invalidate the session row (instant revocation).
- `CurrentUser` → resolve session token → user summary, or unauthenticated.
- `AuthorizeOwnership` → primitive: given (user, resource owner_id) allow/deny (FR-AUTH-008).

### Infrastructure / web
- FastAPI routers for the TDD auth contract:
  | Endpoint | Method | Auth |
  |---|---|---|
  | `/api/auth/register` | POST | public |
  | `/api/auth/login` | POST | public |
  | `/api/auth/logout` | POST | required |
  | `/api/auth/me` | GET | required |
- `get_current_session` / `get_current_user` FastAPI dependencies resolve the cookie → session row.
- Cookie attrs (NFR-SEC-002): `HttpOnly`, `Secure`, `SameSite=Lax`, scoped path; opaque token only.
- CSRF (AD-007): session-bound token issued at session creation, returned via `/api/auth/me`; a
  dependency validates an `X-CSRF-Token` header against the session row on POST/PUT/PATCH/DELETE; `Origin`
  checked. GET never mutates.
- Rate-limit hooks (FR-AUTH-009) on register/login (conservative default; pluggable).
- Logging redaction (NFR-SEC-004) in `/core`: filter password, token, secret fields.

## 4. Data model (TDD Identity authoritative state)

| Table | Columns (conceptual) |
|---|---|
| `users` | id (uuid pk), email (unique, citext/lower), created_at |
| `user_credentials` | user_id (fk), password_hash, algo_params, updated_at |
| `sessions` | id (uuid pk), user_id (fk), token_hash (unique), csrf_token, expires_at, created_at, last_seen_at |

Session cookie stores the raw opaque token; only its hash is persisted (`token_hash`).

## 5. Same-origin proxy (ADR-017, FR-AUTH-007)

Next.js `/app/api/*` route handlers forward browser requests to FastAPI server-side, passing the cookie
and `X-CSRF-Token` header through unchanged. The proxy owns no auth/domain logic; FastAPI is authoritative.
Next route protection (redirect unauthenticated users) is UX-only.

## 6. Flows (from TDD "Registration And Authenticated Access")

Register/Login → FastAPI validates, creates session row, sets HttpOnly cookie + returns CSRF token →
browser stores nothing readable except CSRF token (for the header) → subsequent writes carry cookie + CSRF
header through the proxy → FastAPI authorizes. Logout deletes the session row.

## 7. Test strategy (drives Tasks gates; TDD Testing Strategy)

- **Unit:** application services with fake ports (hashing, repos, clock) — register/login/logout/authorize rules.
- **Integration:** FastAPI endpoints against a real test DB — full register→me→logout, 401 paths, CSRF reject, ownership deny, rate-limit hook, log redaction.
- **Frontend:** proxy forwards cookie + CSRF header; unauthenticated redirect is UX-only.
- **Smoke:** `docker compose up` health (AC-1) — may be a documented manual/CI check this cycle.

## 8. Out of scope (inherited from spec)

Sources/ingestion/corpus/retrieval/Q&A/teaching/fixtures, file-upload validation, VPS hardening.
MinIO + worker are stood up but exercised only by health checks this cycle.
