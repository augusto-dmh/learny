# safe-to-open-the-doors Design

**Spec**: `.specs/features/safe-to-open-the-doors/spec.md`
**Status**: Approved

---

## Architecture Overview

Keep FastAPI authoritative. Redis implements the existing `RateLimiter` port at the API composition root. Daily budget, quotas, invites, and mail are Learny application services behind ports; adapters stay in `infrastructure/`. The Next.js proxy stays transport-only: it forwards a Caddy-stamped client IP and never interprets invites or spend.

Do not introduce Cycle G's thinking-token `SpendPort`. This letter's ledger is a daily budget table plus integer counters.

Rejected alternatives that deliver the same RFC slice:

| Approach | Why not |
|---|---|
| LiteLLM budgets in front of generation | Would orchestrate (ADR-0009) |
| Turnstile instead of invites | Hosted stays invite-only; AD-325 defers Cloudflare |
| ESP SDK (Resend/Postmark) | New provider package; SMTP behind `EmailPort` is enough |
| Soft-delete accounts | Not honest LGPD erase |
| 80 MiB stored quota | Blocks the existing 100 MiB PDF upload cap |

```mermaid
graph TD
  Browser --> Caddy
  Caddy -->|X-Real-IP remote_host| NextProxy
  NextProxy -->|X-Real-IP, strip inbound XFF| FastAPI
  FastAPI --> RedisLimiter
  FastAPI --> DailyBudget
  FastAPI --> InviteRepo
  FastAPI --> EmailPort
  FastAPI --> StoragePort
  DailyBudget --> Postgres
  InviteRepo --> Postgres
```

---

## Code Reuse Analysis

### Existing Components to Leverage

| Component | Location | How to Use |
|---|---|---|
| `RateLimiter` protocol + deps | `backend/app/infrastructure/web/rate_limit.py` | Redis adapter implements `hit`; change key builders |
| `set_rate_limiter` | same | Composition root + tests |
| `redis_url` | `backend/app/core/config.py` | Shared with Celery; pooled client |
| Register/login | `backend/app/application/identity.py`, `web/auth.py` | Invite + tos + disposable before `RegisterUser` |
| Cascade FKs | `backend/app/infrastructure/db/metadata.py` | User delete wipes PG; objects need explicit storage delete |
| `sources.byte_size` | same | SUM for byte quota; no MinIO list |
| Same-origin proxy | `frontend/app/lib/proxy.ts` | Forward trusted IP; strip client XFF |
| Cookie/CSRF/origin | existing auth | Deletion and reset are CSRF writes |
| Sample `is_sample` | sources | Excluded from quotas and deletion |
| Anthropic usage log | `backend/app/infrastructure/answering/anthropic.py` | Map `usage` onto a Learny usage DTO for USD micros |

### Integration Points

| System | Integration Method |
|---|---|
| Redis | `INCR` + `EXPIRE` on first increment; key `learny:rl:{policy}:{subject}` |
| Postgres | migration `0024` budget/invites/tokens/user columns |
| MinIO | `delete_object` via boto3 inside the storage adapter |
| SMTP | stdlib in `infrastructure/email/smtp.py` |
| Caddy | `header_up X-Real-IP {remote_host}` on `reverse_proxy web:3000` |

---

## Components

### RedisRateLimiter

- **Purpose**: Shared fixed-window `RateLimiter` across API workers.
- **Location**: `backend/app/infrastructure/web/redis_rate_limit.py`
- **Interfaces**: `hit(key) -> (allowed, retry_after)`; constructor takes a redis client and per-policy `max_attempts`/`window_seconds`. Redis errors raise `LimiterUnavailable`; the dependency maps to 503.
- **Dependencies**: redis-py connection pool (not one TCP per request).
- **Reuses**: `RateLimiter` protocol. In-memory limiter stays for unit tests via `set_rate_limiter`.

### Client IP + key policy

- **Purpose**: Auth buckets use trusted IP; expensive buckets use `user_id`.
- **Location**: `rate_limit.py` key helpers; `frontend/app/lib/proxy.ts`; `deploy/Caddyfile`
- **Interfaces**: `trusted_client_ip(request) -> str` reads `X-Real-IP` only when the peer is a configured trusted hop (loopback + compose `web`). Proxy sets `X-Real-IP` from Caddy and deletes inbound `x-forwarded-for`.
- **Reuses**: existing deps; ingest-start joins `rate_limit_upload` or a dedicated ingest dependency with the same user-id policy.

### DailyBudget

- **Purpose**: Check and debit daily USD + integer Ask/Teach counters. Not Cycle G `SpendPort`.
- **Location**: `backend/app/application/budget.py` + SQL repo
- **Interfaces**: `assert_generation(user_id, *, kind)`; `record(user_id, *, usd_micros, kind)`; kinds `ask` / `teach_start` / `generation` / `embed`.
- **Dependencies**: price catalog in settings (USD micros per million input/output/embed tokens); kill switch short-circuits before the provider.
- **Reuses**: conversation turn path and quiz deck start, after authz, before provider; debit after success.

### Quotas

- **Purpose**: Owned source count, byte sum, in-flight ingest.
- **Location**: `backend/app/application/quotas.py`
- **Interfaces**: `assert_upload(user, byte_size)`; `assert_ingest_start(user)`.
- **Reuses**: `list_by_user` minus `is_sample`; `ingestion_jobs` active statuses.

### Invite + disposable

- **Purpose**: Gate `RegisterUser` when the invite flag is on.
- **Location**: `backend/app/application/invites.py`, `validation.py`
- **Interfaces**: `consume(code) -> None`; `is_disposable(email) -> bool`.
- **Reuses**: `validate_email` generic invalid copy for disposables (DOOR-23).

### EmailPort

- **Purpose**: Send verify and reset messages.
- **Location**: `backend/app/domain/ports.py` + `infrastructure/email/`
- **Interfaces**: `send(*, to, subject, body) -> None`
- **Reuses**: session token hasher for verify/reset secrets; TTL settings.

### DeleteAccount

- **Purpose**: Object delete then user delete.
- **Location**: `backend/app/application/identity.py`
- **Interfaces**: `__call__(user)`; lists keys from caller-owned sources (`object_key` + `sources/{user_id}/{source_id}/media/`), storage delete, then users.delete. On storage fault, no user delete.
- **Reuses**: CASCADE; sample not in the caller's owned list.

### Legal pages

- **Purpose**: Static terms/privacy/copyright.
- **Location**: `frontend/app/terms/page.tsx` and siblings reading committed markdown.
- **Reuses**: existing signed-out layout; DMCA email from `LEARNY_DMCA_CONTACT_EMAIL` via Next server env (no public config dump of other secrets).

---

## Data Models

### ai_spend_days

`(user_id, day_utc)` PK, `usd_micros BIGINT NOT NULL DEFAULT 0`, `ask_count INT NOT NULL DEFAULT 0`, `teach_starts INT NOT NULL DEFAULT 0`. Increment with `INSERT ... ON CONFLICT DO UPDATE`. FK users CASCADE.

### invite_codes

`code TEXT UNIQUE`, `remaining_uses INT NOT NULL`, `expires_at TIMESTAMPTZ NULL`, `created_at`.

### email_tokens

`id`, `user_id` FK CASCADE, `purpose` (`verify`|`reset`), `secret_hash`, `expires_at`, `consumed_at` NULL.

### users

Add nullable `email_verified_at`, `accepted_tos_at`.

### StoragePort

Add `delete_object(key: str) -> None`. Missing keys are success (idempotent delete). Prefix delete is application-side list of known keys, not S3 `ListObjects` as the source of truth.

---

## Error Handling Strategy

| Error Scenario | Handling | User Impact |
|---|---|---|
| Limiter exceeded | 429 + Retry-After | Wait; copy is generic too-many-attempts |
| Redis down | 503 | Retry; AI/auth writes fail closed |
| Spend / Ask / Teach exhausted | 429 honest copy; no provider call; conversation kept | Come back tomorrow |
| Kill switch | 503 honest pause copy | Library and review still work |
| Source count quota | 403 | Delete a book to upload another |
| Byte quota | 413 | Smaller file or delete a book |
| In-flight ingest | 409 | Wait for the current job |
| Bad/missing invite | 403 | Invite-required copy |
| Disposable / tos | 422 | Generic invalid email / tos required |
| Reset unknown email | 204, no mail | No enumeration |
| Storage delete fails | 502; user remains | Retry delete |
| SMTP send fails | Log; session still created | Resend verify later |

---

## Risks & Concerns

| Concern | Location | Impact | Mitigation |
|---|---|---|---|
| Proxy still forwards spoofed XFF | `frontend/app/lib/proxy.ts` | Shared auth bucket or attacker-chosen IP | Strip XFF; only set X-Real-IP from Caddy |
| Caddy does not stamp X-Real-IP today | `deploy/Caddyfile` | FastAPI still sees `web` | `header_up` this letter; topology test |
| Spend check race | budget increment | One extra paid call | Spec edge; next call 429s |
| SMTP failure blocking register | EmailPort | Invite wasted | Best-effort send; session still created |
| Deleting sample objects | DeleteAccount | Shared book gone | Only keys from caller-owned sources |
| redis-py blocking the event loop | limiter `hit` | Latency under load | One INCR; same sync style as Celery |
| Legal copy quality | static pages | Lying policy | Committed short pages; not generated per request |
| Integer caps vs USD cap | DailyBudget | Two meters to explain | Whichever trips first; same honest copy class |
| Test suite register flood | `LEARNY_INVITE_REQUIRED` | CI red | Default false; production example true |

---

## Tech Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Limiter store | Redis String INCR + EXPIRE | Matches the existing `hit` protocol; colon keys `learny:rl:...` |
| Budget vs Cycle G SpendPort | Separate `ai_spend_days` table this letter | Cycle G still owns thinking-token persistence |
| Captcha | Invite only; no Turnstile | AD-325 |
| Mail | SMTP + log adapter | No ESP SDK |
| Byte quota | 256 MiB | Compatible with 100 MiB PDF max × 2 books |
| Delete order | Objects then user row | Fail closed on storage |

Project-level decisions recorded as AD-324..AD-333 in `.specs/project/STATE.md`.
