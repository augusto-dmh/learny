# Validation — Cycle 1: Scaffold + Identity Foundation

**Overall: PASS**

Independent verifier pass (author ≠ verifier). Coverage re-derived from `spec.md`
(AC-1..AC-8) using evidence-or-zero. Full Docker Compose stack was built and run
(not just `docker compose config`), and a real browser-like flow was exercised
through the live Next.js proxy on port 3000.

Diff range covered: `07cc25d..15bf93f` (cycle commits A1..D2).

```
15bf93f feat(identity): minimal register/login/logout auth screens (D2)
a68f375 feat(identity): same-origin auth proxy forwarding cookie and csrf (D1)
1a9c620 feat(identity): logging redaction for sensitive fields (C4)
36a0b03 feat(identity): rate-limit hook + boundary validation (C3)
8656a83 feat(identity): session-bound CSRF protection (C2)
11e6591 feat(identity): auth routers with cookie sessions (C1)
253957e feat(identity): application services register/login/logout/current-user/authorize (B4)
62d04dc feat(identity): PostgreSQL repositories for users, credentials, sessions (B3)
36644c7 feat(identity): Argon2id password hasher adapter (B2)
d89466f feat(identity): domain entities and ports (B1)
7337b56 feat(scaffold): docker compose topology for six services (A3)
d384394 feat(scaffold): alembic migration tooling + identity schema (A4)
058438d feat(scaffold): frontend skeleton with same-origin proxy stub (A2)
07cc25d feat(scaffold): backend skeleton with health endpoints (A1)
```

## Gate results

- Backend: `uv run pytest -q` → **69 passed, 0 skipped** (DB tests ran against live
  Postgres; `LEARNY_TEST_DATABASE_URL` set). `uv run ruff check .` → **All checks passed!**
- Frontend: `npm test` (vitest) → **19 passed** across 4 files.
- Compose: `docker compose build api web` → both **Built**; `docker compose up -d` →
  db, redis, minio, api, worker report **(healthy)**; web is **Up** (no healthcheck
  defined — see gaps).

## Part 1 — Spec-anchored outcome check (per AC)

| AC | Verdict | Evidence |
|---|---|---|
| AC-1 | PASS (minor gap) | Full stack built and run. `docker compose ps`: `db/redis/minio/api/worker` all `(healthy)`; api `/healthz` and worker celery `inspect ping` pass. `web` is `Up` but has **no** healthcheck, so it can't report "healthy" — AC-1 wording says "all six to healthy". Functionally up; see Gap-1. |
| AC-2 | PASS | Live `POST :3000/api/auth/register` → 201; `Set-Cookie: learny_session=...; HttpOnly; Path=/; SameSite=lax` relayed through the Next proxy; curl jar records `#HttpOnly_localhost`. Response body carries only `{id,email,created_at}` — no token. (`test_register_sets_httponly_cookie_and_returns_summary`, `proxy-forwarding.test.ts`.) |
| AC-3 | PASS | Live: `GET /api/auth/me` → 200 with user summary + `csrf_token`; after CSRF-valid logout (204), `GET /api/auth/me` → 401. (`test_full_register_me_logout_flow`, `test_me_unauthenticated_returns_401`.) |
| AC-4 | PASS | Live DB: `user_credentials.password_hash` = `$argon2id$v=19$m=65536,t=3,p=4$...`; `count(*) WHERE password_hash LIKE '%<plaintext>%'` = 0. (`test_register_creates_user_credential_and_session` asserts hashed, not plaintext.) |
| AC-5 | PASS | Live: logout without `X-CSRF-Token` → 403; with valid token → 204. (`test_write_without_csrf_token_is_rejected`, `test_write_with_invalid_csrf_token_is_rejected`, `test_write_with_valid_csrf_token_is_accepted`, plus untrusted-Origin → 403.) |
| AC-6 | PASS (precision note) | `AuthorizeOwnership` allow/deny proven by `test_authorize_allows_owner` / `test_authorize_denies_non_owner` (raises `NotAuthorized` for non-owner). The primitive exists and is tested, but is **not yet wired into any HTTP endpoint** because user-owned resources (sources) are deferred to a later cycle — so the spec's "cannot access a resource owned by user B" is verified only at the application/unit level this cycle. Consistent with FR-AUTH-008 ("primitive exists"); see Gap-2. |
| AC-7 | PASS | Live: 13 rapid `POST /api/auth/login` → `401×10, 429×3` (default `max_attempts=10`); 429 carries `Retry-After`. (`test_repeated_login_attempts_hit_rate_limit`, `test_repeated_register_attempts_hit_rate_limit`.) |
| AC-8 | PASS | Live `docker compose logs api`/`worker`: 0 occurrences of the plaintext password, the issued raw session token, or the CSRF token. (`test_configure_logging_redacts_emitted_output` + `SensitiveDataFilter` unit tests.) |

## Part 2 — Discrimination sensor (mutation testing)

6 behavior-level faults injected one at a time, relevant tests run, then reverted.
**6/6 killed, 0 survived.**

| # | Mutation | Result | Killing test(s) |
|---|---|---|---|
| a | `AuthorizeOwnership` always allows | KILLED | `test_authorize_denies_non_owner` (DID NOT RAISE NotAuthorized) |
| b | CSRF token check always passes | KILLED | `test_write_without_csrf_token_is_rejected`, `test_write_with_invalid_csrf_token_is_rejected` |
| c | Password `verify` returns True unconditionally | KILLED | `test_verify_false_on_mismatch`, `test_verify_returns_false_not_raises_on_garbage`, `test_login_wrong_password_returns_401` |
| d | Drop `HttpOnly` from session cookie | KILLED | `test_register_sets_httponly_cookie_and_returns_summary` |
| e | `/me` returns a user without a valid session (fabricate principal on auth failure) | KILLED | `test_me_unauthenticated_returns_401`, `test_logout_unauthenticated_returns_401`, `test_unauthenticated_write_is_401_not_403` |
| f | Redaction filter is a no-op | KILLED | `test_filter_masks_top_level_sensitive_keys`, `test_filter_masks_nested_structures`, `test_filter_masks_mapping_args`, `test_configure_logging_redacts_emitted_output` |

Post-mutation: working tree clean (no tracked changes), `pytest -q` → 69 passed,
`ruff check .` → All checks passed.

## Ranked gaps (non-blocking)

1. **Gap-1 (low) — `web` service has no compose healthcheck.** AC-1 says "all six
   services to healthy"; `web` is only `Up`, so compose can never mark it healthy.
   Add a Next.js healthcheck (e.g. `curl -fsS http://localhost:3000/`) for a true
   six-of-six green and to let `depends_on: web: condition: service_healthy` work.
2. **Gap-2 (informational) — AC-6 not wired to an endpoint.** Expected this cycle
   (sources deferred). When the first user-owned resource lands, add an integration
   test proving user A gets 403/404 on user B's resource via `AuthorizeOwnership`.

## Method / environment notes

- Ran the **full compose stack** (build + up), exercised register → /me → logout
  through the live Next proxy (port 3000) with curl, and inspected the live DB and
  live container logs — did not fall back to integration tests only.
- Final `git status`: clean for tracked files (only untracked `.omc/` and
  `.specs/` artifacts present). Suite green (69 backend, 19 frontend). All 6
  mutations reverted.
