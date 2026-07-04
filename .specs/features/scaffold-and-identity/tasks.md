# Tasks — Cycle 1: Scaffold + Identity Foundation

Atomic tasks, grouped in 4 phases. `[P]` = parallelizable with siblings. Each task: one atomic commit;
gate must pass before done. AC refs trace to spec acceptance criteria.

## Status

| Task | Status | Commit | Gate (verified by orchestrator) |
|---|---|---|---|
| A1 | ✅ done | 07cc25d | `pytest` 5 passed / 1 skipped |
| A2 | ✅ done | 058438d | `vitest` 4 passed |
| A4 | ✅ done | d384394 | migration test 2 passed (live db) |
| A3 | ✅ done | 7337b56 | `docker compose config` valid; db service boots |
| B1 | ✅ done | d89466f | unit (entities/ports) green |
| B2 | ✅ done | 36644c7 | unit (Argon2id hash/verify) green |
| B3 | ✅ done | 62d04dc | integration (repos, live db) green |
| B4 | ✅ done | 253957e | unit (services, fakes) green — 45 total |
| C1 | ✅ done | 11e6591 | integration (register→me→logout, 401/409) green |
| C2 | ✅ done | 8656a83 | integration (CSRF reject/accept, Origin) green |
| C3 | ✅ done | 36a0b03 | integration (rate-limit, validation) green |
| C4 | ✅ done | 1a9c620 | unit (redaction) green — 69 total |
| D1 | ✅ done | a68f375 | vitest proxy-forwarding (cookie+csrf+origin) green |
| D2 | ✅ done | 15bf93f | vitest auth-screens green — 19 frontend total |
| Verifier | ✅ PASS | validation.md | full compose stack + 8/8 AC + 6/6 mutants killed |

## Phase A — Scaffold foundation

### A1 — Backend skeleton + health
- **What:** FastAPI app, layered dirs (domain/application/infrastructure/core), config loader, `/healthz` (liveness) + `/readyz` (db check), pytest harness with one passing test.
- **Where:** `/backend`
- **Depends on:** —
- **Reuses:** —
- **Done when:** app boots; `/healthz` 200; pytest runs green.
- **Tests:** unit — health route returns ok; config loads from env.
- **Gate:** `pytest` passes. | **AC:** AC-1

### A2 [P] — Frontend skeleton + proxy stub
- **What:** Next.js app, `/app/api` same-origin proxy route stub (ADR-017), test harness with one passing test.
- **Where:** `/frontend`
- **Depends on:** —
- **Done when:** dev server boots; proxy stub forwards to a configurable API base; frontend test runs green.
- **Tests:** frontend — proxy stub forwards method/path/headers.
- **Gate:** frontend test runner passes. | **AC:** AC-1 (web up)

### A3 — Docker Compose topology
- **What:** `docker-compose.yml` with `api`, `web`, `db` (postgres+pgvector), `redis`, `worker` (Celery, no tasks), `minio` (AD-008); healthchecks for db/redis/minio.
- **Where:** `/docker-compose.yml`
- **Depends on:** A1, A2
- **Done when:** `docker compose up` brings all six services healthy.
- **Tests:** smoke — documented compose health check (CI or manual) hitting `/healthz` + `/readyz`.
- **Gate:** all services report healthy. | **AC:** AC-1

### A4 — Migration tooling + identity schema
- **What:** wire DB migration tool; initial migration creating `users`, `user_credentials`, `sessions` (design §4).
- **Where:** `/backend/migrations`
- **Depends on:** A1
- **Done when:** migrate up/down works against `db`; tables exist with constraints (unique email, unique token_hash).
- **Tests:** integration — migration applies; schema matches design.
- **Gate:** migration test passes. | **AC:** AC-1 (db ready), supports AC-2..AC-8

## Phase B — Identity domain + application

### B1 — Domain entities + ports
- **What:** `User`, `PasswordCredential`, `Session`; ports `UserRepository`, `CredentialRepository`, `SessionRepository`, `PasswordHasher`, `Clock`, `StoragePort`. No framework/SDK imports.
- **Where:** `/backend/app/domain`
- **Depends on:** A1
- **Done when:** entities + port protocols defined; import-boundary respected.
- **Tests:** unit — entity invariants (e.g., no plaintext on User).
- **Gate:** `pytest` passes. | **AC:** supports AC-4/AC-6

### B2 [P] — Argon2id hasher adapter
- **What:** `PasswordHasher` adapter using Argon2id (pwdlib/argon2-cffi, AD-006); hash + verify, never log material.
- **Where:** `/backend/app/infrastructure`
- **Depends on:** B1
- **Done when:** hash is Argon2id; verify true/false; rehash-on-params-change hook.
- **Tests:** unit — hash≠plaintext, verify matches, wrong password fails.
- **Gate:** `pytest` passes. | **AC:** AC-4

### B3 [P] — PostgreSQL repositories
- **What:** adapters for User/Credential/Session repos; session token stored as `token_hash`, raw token returned once.
- **Where:** `/backend/app/infrastructure`
- **Depends on:** B1, A4
- **Done when:** CRUD works against test DB; unique constraints enforced.
- **Tests:** integration — create/fetch user, credential, session; duplicate email rejected.
- **Gate:** integration tests pass. | **AC:** supports AC-2/AC-3

### B4 — Application services
- **What:** `RegisterUser`, `AuthenticateUser`, `Logout`, `CurrentUser`, `AuthorizeOwnership`; input validation (FR-AUTH-010); uniform login failure (no enumeration).
- **Where:** `/backend/app/application`
- **Depends on:** B1, B2, B3
- **Done when:** services pass with fake ports; ownership primitive allows owner / denies non-owner.
- **Tests:** unit — register/login/logout/current-user happy + failure; authorize allow/deny.
- **Gate:** `pytest` passes. | **AC:** AC-3, AC-4, AC-6

## Phase C — Identity web + security

### C1 — Auth routers + cookie sessions
- **What:** FastAPI routers `/api/auth/{register,login,logout,me}`; `get_current_session/user` deps; set HttpOnly+Secure+SameSite=Lax cookie (NFR-SEC-002); opaque token only.
- **Where:** `/backend/app/infrastructure` (web)
- **Depends on:** B4
- **Done when:** register→cookie set; me→summary; logout→session gone; unauth me→401.
- **Tests:** integration — full flow + 401 paths.
- **Gate:** integration tests pass. | **AC:** AC-2, AC-3

### C2 — CSRF (session-bound token)
- **What:** issue session-bound CSRF token at session creation, expose via `/api/auth/me`; dependency validates `X-CSRF-Token` against session row on writes; `Origin` check (AD-007).
- **Where:** `/backend/app/infrastructure` + `/core`
- **Depends on:** C1
- **Done when:** write without valid token → rejected; with valid token → allowed.
- **Tests:** integration — CSRF reject/accept; Origin mismatch rejected.
- **Gate:** integration tests pass. | **AC:** AC-5

### C3 [P] — Rate-limit hooks + validation
- **What:** pluggable rate-limit hook on register/login (conservative default); email/password policy validation (FR-AUTH-009/010).
- **Where:** `/backend/app/infrastructure` + `/core`
- **Depends on:** C1
- **Done when:** rapid repeated attempts hit the hook; invalid input rejected with clear error.
- **Tests:** integration — rate-limit triggers; validation rejects bad email/weak password.
- **Gate:** integration tests pass. | **AC:** AC-7

### C4 [P] — Logging redaction
- **What:** logging filter in `/core` redacting password, session token, secret fields (NFR-SEC-004); secrets server-side only (NFR-SEC-003).
- **Where:** `/backend/app/core`
- **Depends on:** C1
- **Done when:** auth-flow logs contain no plaintext password/token/secret.
- **Tests:** unit — redaction filter masks sensitive keys.
- **Gate:** `pytest` passes. | **AC:** AC-8

## Phase D — Frontend wiring

### D1 — Same-origin proxy
- **What:** Next.js `/app/api/*` forwards browser requests to FastAPI server-side, passing cookie + `X-CSRF-Token` unchanged; no domain logic (ADR-017).
- **Where:** `/frontend/app/api`
- **Depends on:** A2, C1, C2
- **Done when:** browser→proxy→FastAPI round-trip works for auth; cookie + CSRF header forwarded.
- **Tests:** frontend — proxy forwards cookie + CSRF header; no token readable by browser JS.
- **Gate:** frontend tests pass. | **AC:** AC-2

### D2 [P] — Minimal auth screens
- **What:** register/login/logout screens calling the proxy; UX-only redirect for unauthenticated (not the security boundary).
- **Where:** `/frontend/app`
- **Depends on:** D1
- **Done when:** user can register, log in, see logged-in state, log out via UI.
- **Tests:** frontend — screen calls proxy; redirect is UX-only.
- **Gate:** frontend tests pass. | **AC:** AC-2, AC-3

## Verifier (always-on, after last task)

Fresh Verifier (author ≠ verifier): spec-anchored outcome check across AC-1..AC-8 + discrimination
sensor; writes `validation.md` (PASS/FAIL, per-AC evidence, diff range). Gaps → bounded fix loop.

## Dependency summary

A1 → {A3, A4, B1}; A2 → A3; B1 → {B2, B3, B4}; A4 → B3; B4 → C1 → {C2, C3, C4}; {A2,C1,C2} → D1 → D2.
Parallelizable: A2‖A1-after-start; B2‖B3; C3‖C4 (after C1); D2 after D1.
