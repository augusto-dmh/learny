# safe-to-open-the-doors Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user — do not proceed without it.**

---

**Design**: `.specs/features/safe-to-open-the-doors/design.md`
**Status**: Approved

---

## Test Coverage Matrix

> Guidelines: `CLAUDE.md`. Do not implement Turnstile. AD-325.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| ---------- | ------------------ | -------------------- | ---------------- | ----------- |
| Limiter | unit + integration | shared Redis window; user_id vs IP; spoofed XFF ignored; 429 Retry-After; Redis down 503 | `backend/tests/test_web_rate_limit_validation.py` | `cd backend && uv run pytest tests/test_web_rate_limit_validation.py` |
| Proxy / Caddy | unit | X-Real-IP forwarded; inbound XFF stripped; Caddyfile stamps header | `frontend/tests/proxy.test.ts` | `cd frontend && npm test -- proxy` |
| Budget / kill | integration | ninth Ask 429 keeps conversation; Teach second start 429; USD cap; review not debited; kill 503 | `backend/tests/test_application_budget.py` | `cd backend && uv run pytest tests/test_application_budget.py` |
| Quotas | integration | third source 403; sample excluded; byte 413; in-flight 409 | `backend/tests/test_web_sources.py` | `cd backend && uv run pytest tests/test_web_sources.py` |
| Invite / disposable | integration | missing invite 403 when flagged; one-use; disposable 422; duck.com allowed; tos 422; flag off still registers | `backend/tests/test_web_auth.py` | `cd backend && uv run pytest tests/test_web_auth.py` |
| Deletion | integration | objects gone; sample remains; storage fault 502 leaves user | `backend/tests/test_application_identity.py` | `cd backend && uv run pytest tests/test_application_identity.py` |
| EmailPort | integration | verify send; token once; reset 204 no mail for unknown; SMTP fail still registers | `backend/tests/test_application_email.py` | `cd backend && uv run pytest tests/test_application_email.py` |
| Legal / register UI | unit (jsdom) | invite + tos; legal titles; no Turnstile widget | `frontend/tests/legal-pages.test.tsx` | `cd frontend && npm test -- legal-pages` |

---

## Gate Check Commands

> Prefix `LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test LEARNY_GENERATION_PROVIDER=local LEARNY_EMBEDDING_PROVIDER=local`. Reset `learny_test` if `test_migrations.py` ran in-process after a mid-migration schema.

| Gate Level | When to Use | Command |
| ---------- | ----------- | -------- |
| Quick | After a backend unit task | `cd /home/augusto/projects/learny/backend && uv run pytest <touched module>` |
| Full | After HTTP, Redis, migration, or frontend tasks | touched backend module and/or `cd /home/augusto/projects/learny/frontend && npm test -- <file>` |
| Build | Phase boundary | `cd /home/augusto/projects/learny && make lint` plus the cycle's backend + frontend suites |

---

## Execution Plan

```mermaid
graph TD
    T1 --> T2 --> T3 --> T4
    T4 --> T5 --> T6 --> T7 --> T8 --> T9
    T9 --> T10 --> T11 --> T12
    T12 --> T13 --> T14
    T14 --> T15 --> T16
```

Four sequential phases, one Opus worker each. No Haiku. No Turnstile. Verifier after T16.

---

## Task Breakdown

### Phase 1: Shared limiter and trusted IP

#### T1: Redis RateLimiter adapter

**What**: Implement `RateLimiter` with pooled Redis `INCR`/`EXPIRE`. Raise a typed unavailable error when Redis is down.
**Where**: `backend/app/infrastructure/web/redis_rate_limit.py`
**Depends on**: None
**Reuses**: `RateLimiter` protocol
**Requirement**: DOOR-01, DOOR-05

**Tools**:

- MCP: NONE
- Skill: redis-connections

**Done when**:

- [x] Two processes sharing a key share one window
- [x] A dead Redis fails closed (exception, not allow)

**Tests**: integration
**Gate**: quick
**Commit**: `feat(api): share rate limits across workers`

---

#### T2: Compose Redis limiter

**What**: Production API uses the Redis limiter; tests may still inject the in-memory one. Map limiter-unavailable to 503.
**Where**: `backend/app/main.py`
**Depends on**: T1
**Reuses**: `set_rate_limiter`
**Requirement**: DOOR-05

**Tools**:

- MCP: NONE
- Skill: fastapi

**Done when**:

- [x] Default app construction uses Redis when the URL is set
- [x] A limited route returns 503 if Redis is unreachable

**Tests**: integration
**Gate**: quick
**Commit**: `feat(api): fail closed when the limiter is down`

---

#### T3: Trusted client IP

**What**: Auth limiter keys on `X-Real-IP` only from a trusted peer. Next proxy sets that header from Caddy and strips inbound `X-Forwarded-For`. Caddy stamps `X-Real-IP` from the TCP client.
**Where**: `backend/app/infrastructure/web/rate_limit.py`
**Depends on**: T2
**Reuses**: `_client_key`, `buildProxyRequest`
**Requirement**: DOOR-03, DOOR-06

**Tools**:

- MCP: NONE
- Skill: fastapi

**Done when**:

- [x] A spoofed `X-Real-IP` from an untrusted peer is ignored
- [x] The proxy outbound request has no client `x-forwarded-for`
- [x] Caddyfile forwards `X-Real-IP`

**Tests**: unit
**Gate**: quick
**Commit**: `feat(api): key auth limits on the trusted client IP`

---

#### T4: User-id keys for expensive routes

**What**: Conversations, quiz generation, and upload/ingest-start limiters key on authenticated `user_id`.
**Where**: `backend/app/infrastructure/web/rate_limit.py`
**Depends on**: T3
**Reuses**: `_route_template_key`
**Requirement**: DOOR-02, DOOR-04

**Tools**:

- MCP: NONE
- Skill: fastapi

**Done when**:

- [ ] Two users behind one IP both complete an Ask under the per-user cap
- [ ] Exceeding returns 429 with Retry-After

**Tests**: integration
**Gate**: full
**Commit**: `feat(api): rate-limit AI routes per learner`

---

### Phase 2: Spend, kill switch, library quotas

#### T5: Daily spend table

**What**: Migration adds `ai_spend_days` with `(user_id, day_utc)` PK and counter columns. Upgrade then downgrade is clean.
**Where**: `backend/migrations/versions/0024_safety_rails.py`
**Depends on**: T4
**Reuses**: `0023_starter_quiz_origin.py` head
**Requirement**: DOOR-07

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Two increments of the same day accumulate
- [ ] Downgrade drops the table

**Tests**: integration
**Gate**: full
**Commit**: `feat(billing): record daily generation spend`

---

#### T6: Spend catalog and assertions

**What**: Settings hold USD/day cap and per-million prices. Application asserts remaining budget before a provider call and debits after success. Local adapters debit 0 USD unless a test fixture supplies usage. FSRS review does not debit.
**Where**: `backend/app/application/spend.py`
**Depends on**: T5
**Reuses**: generation/quiz call sites
**Requirement**: DOOR-08, DOOR-09, DOOR-13, DOOR-14

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Crossing the USD cap returns 429 and skips the provider
- [ ] A successful call increases `usd_micros`
- [ ] Review submit does not increase spend

**Tests**: integration
**Gate**: quick
**Commit**: `feat(billing): cap daily generation spend`

---

#### T7: Ask and Teach daily integers

**What**: Free-tier 8 Ask/UTC-day and 1 Teach-session start. Honest 429 copy. Conversation row is kept.
**Where**: `backend/app/application/conversations.py`
**Depends on**: T6
**Reuses**: spend day row
**Requirement**: DOOR-10, DOOR-11

**Tools**:

- MCP: NONE
- Skill: fastapi

**Done when**:

- [ ] The ninth Ask is 429 with remaining=0 copy
- [ ] A second Teach start the same UTC day is 429

**Tests**: integration
**Gate**: quick
**Commit**: `feat(ask): cap daily asks and teach starts`

---

#### T8: Kill switch

**What**: `LEARNY_AI_KILL_SWITCH` true → 503 on Ask/Teach/quiz generate and embedding ingest before any provider SDK. Review still succeeds.
**Where**: `backend/app/core/config.py`
**Depends on**: T7
**Reuses**: settings cache
**Requirement**: DOOR-12, DOOR-13

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Switch on: 503, zero provider calls
- [ ] Review submit still 200

**Tests**: integration
**Gate**: quick
**Commit**: `feat(api): add a generation kill switch`

---

#### T9: Source count, bytes, in-flight ingest

**What**: Reject owned-source count >2 (403 before put), byte sum + upload >256 MiB (413 before put), and a second in-flight ingest (409). Sample excluded from count and bytes. Allowed ingest start still hits the user-id limiter.
**Where**: `backend/app/application/ingestion.py`
**Depends on**: T8
**Reuses**: `is_sample`
**Requirement**: DOOR-15, DOOR-16, DOOR-17, DOOR-18, DOOR-19

**Tools**:

- MCP: NONE
- Skill: epub-ingestion

**Done when**:

- [ ] Third owned book is 403
- [ ] Sample plus two owned books still uploads
- [ ] Oversized stored sum is 413
- [ ] Second concurrent ingest is 409

**Tests**: integration
**Gate**: full
**Commit**: `feat(library): cap owned books and ingest concurrency`

---

### Phase 3: Invite, legal, deletion

#### T10: Invite codes

**What**: `invite_codes` table. When `LEARNY_INVITE_REQUIRED` is true, register requires a live code and consume decrements remaining uses. Successful invited register mints a session. When the flag is false, register without a code still works.
**Where**: `backend/app/application/invites.py`
**Depends on**: T9
**Reuses**: `RegisterUser`
**Requirement**: DOOR-20, DOOR-21, DOOR-22, DOOR-26

**Tools**:

- MCP: NONE
- Skill: fastapi

**Done when**:

- [ ] Missing/bad/exhausted/expired code is 403 when the flag is on
- [ ] Valid code returns 201 with session cookies
- [ ] Flag off still registers without a code

**Tests**: integration
**Gate**: full
**Commit**: `feat(auth): require an invite code to register`

---

#### T11: Disposable emails and ToS

**What**: Closed disposable-domain list; ToS checkbox required. Failures are generic 422. `duck.com` is allowed.
**Where**: `backend/app/application/identity.py`
**Depends on**: T10
**Reuses**: `validate_email`
**Requirement**: DOOR-23, DOOR-24, DOOR-25

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] A listed disposable domain is 422 with the generic email copy
- [ ] Missing ToS is 422
- [ ] Register form posts invite + accepted_tos
- [ ] No Turnstile widget or token field

**Tests**: integration
**Gate**: full
**Commit**: `feat(auth): refuse disposable inboxes without a ToS`

---

#### T12: Terms, privacy, copyright

**What**: Public `/terms`, `/privacy`, `/copyright` from committed copy. Copyright names the DMCA mailbox. Privacy names OpenAI and Anthropic and does not claim ZDR.
**Where**: `frontend/app/terms/page.tsx`
**Depends on**: T11
**Reuses**: signed-out layout
**Requirement**: DOOR-27, DOOR-28, DOOR-29

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Each route renders a unique title and body
- [ ] Copyright includes the configured contact address
- [ ] Privacy names the two AI subprocessors and does not claim ZDR

**Tests**: unit
**Gate**: quick
**Commit**: `feat(legal): publish terms, privacy, and copyright pages`

---

#### T13: Storage delete

**What**: `StoragePort` gains delete-by-key. Adapter maps faults to `StorageUnavailable`. Missing keys are success.
**Where**: `backend/app/domain/ports.py`
**Depends on**: T12
**Reuses**: `S3StorageAdapter`
**Requirement**: DOOR-30

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] A put then delete then get raises not-found
- [ ] A storage fault is `StorageUnavailable`, not a bare boto exception

**Tests**: integration
**Gate**: quick
**Commit**: `feat(storage): delete objects when an account is removed`

---

#### T14: Delete account

**What**: Authenticated CSRF `DELETE /api/auth/account` deletes the caller's objects then the user row. Storage failure leaves the user (502). Sample survives.
**Where**: `backend/app/application/identity.py`
**Depends on**: T13
**Reuses**: CASCADE FKs
**Requirement**: DOOR-30, DOOR-31, DOOR-32, DOOR-33

**Tools**:

- MCP: NONE
- Skill: fastapi

**Done when**:

- [ ] After delete, login 401 and objects gone
- [ ] Injected storage failure leaves the user and returns 502
- [ ] Sample source still exists

**Tests**: integration
**Gate**: full
**Commit**: `feat(auth): let a learner delete their account`

---

### Phase 4: Mail

#### T15: EmailPort

**What**: Port + SMTP adapter + log/in-memory adapter. Settings for host/from. Tests never open a network socket.
**Where**: `backend/app/domain/ports.py`
**Depends on**: T14
**Reuses**: stdlib smtplib inside the adapter only
**Requirement**: DOOR-34, DOOR-40

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] SMTP adapter is the production default when host is set
- [ ] Tests capture messages in memory

**Tests**: unit
**Gate**: quick
**Commit**: `feat(mail): send mail through a Learny email port`

---

#### T16: Verify and reset

**What**: Hashed verify/reset tokens. Register sends verify without blocking the session. Confirm sets `email_verified_at`. Reset unknown emails 204 with no send. SMTP failure on register still 201. Reset/verify-resend use the auth limiter.
**Where**: `backend/app/application/identity.py`
**Depends on**: T15
**Reuses**: EmailPort, session hasher
**Requirement**: DOOR-34, DOOR-35, DOOR-36, DOOR-37, DOOR-38, DOOR-39, DOOR-40

**Tools**:

- MCP: NONE
- Skill: fastapi

**Done when**:

- [ ] Invited register 201 even if SMTP raises
- [ ] Confirm with the raw token marks verified
- [ ] Unknown reset email is 204 and inbox empty

**Tests**: integration
**Gate**: full
**Commit**: `feat(auth): verify email and reset passwords by mail`

---

## Notes

- Alembic head is `0023_starter_quiz_origin`. Confirm before writing `0024`.
- Do not add Turnstile, siteverify, or a captcha widget.
- `make test-backend` running `test_migrations.py` in-process after a mid-migration schema poisons `learny_test`; reset schema or isolate that module.
