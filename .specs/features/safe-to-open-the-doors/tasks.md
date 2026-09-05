# safe-to-open-the-doors Tasks

**Spec**: `.specs/features/safe-to-open-the-doors/spec.md`
**Design**: `.specs/features/safe-to-open-the-doors/design.md`
**Status**: Approved

---

## Test Coverage Matrix

| Requirement | Test Type | Coverage Strategy |
|---|---|---|
| DOOR-01 Redis shared window | Integration | Two clients; second exceeds |
| DOOR-02 Redis down | Integration | 503 on limited route |
| DOOR-03 Auth IP | Unit | X-Real-IP from trusted peer; spoof ignored |
| DOOR-04 Proxy strip | Unit | Outbound has no client XFF |
| DOOR-05 User-id AI keys | Integration | Same IP different users both succeed |
| DOOR-06 429 Retry-After | Integration | Header present |
| DOOR-07–13 Spend/Ask/Teach | Integration | Cap then 429; no provider |
| DOOR-14 Kill switch | Integration | 503 |
| DOOR-15–18 Quotas | Integration | 403/409; sample excluded |
| DOOR-19–22 Invite/tos | Integration | 403/422; session minted |
| DOOR-23–25 Legal | Frontend | Routes render |
| DOOR-26–28 Deletion | Integration | Objects gone, user 401, sample lives |
| DOOR-29–34 Mail | Integration | Token hash, 204 reset, SMTP fail still 201 |

---

## Gate Check Commands

**Quick**: `cd /home/augusto/projects/learny/backend && LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test LEARNY_GENERATION_PROVIDER=local LEARNY_EMBEDDING_PROVIDER=local uv run pytest tests/<module> -q`
**Frontend**: `cd /home/augusto/projects/learny/frontend && npm test -- --run <file>`
**Full**: `cd /home/augusto/projects/learny && make lint` then backend pytest (reset `learny_test` if mixed with `test_migrations.py`) then `cd frontend && npm test -- --run`
**Lint**: `cd /home/augusto/projects/learny && make lint`

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

---

## Parallel Execution Strategy

Four sequential phases (limiter, spend/quotas, invite/legal/delete, mail). One Opus worker per phase. No Haiku: auth, spend, deletion, and tokens fail quietly.

---

## Task Breakdown

### Phase 1: Shared limiter and trusted IP

#### T1: Redis RateLimiter adapter

**What**: Implement `RateLimiter` with pooled Redis `INCR`/`EXPIRE`. Raise a typed unavailable error when Redis is down.
**Where**: `backend/app/infrastructure/web/redis_rate_limit.py`
**Depends on**: None
**Reuses**: `RateLimiter` protocol
**Requirement**: DOOR-01, DOOR-02

**Tools**:

- MCP: NONE
- Skill: redis-connections

**Done when**:

- [ ] Two processes sharing a key share one window
- [ ] A dead Redis fails closed (exception, not allow)

**Tests**: integration
**Gate**: quick
**Commit**: `feat(api): share rate limits across workers`

---

#### T2: Compose Redis limiter

**What**: Production API uses the Redis limiter; tests may still inject the in-memory one. Map limiter-unavailable to 503.
**Where**: `backend/app/main.py`
**Depends on**: T1
**Reuses**: `set_rate_limiter`
**Requirement**: DOOR-02

**Tools**:

- MCP: NONE
- Skill: fastapi

**Done when**:

- [ ] Default app construction uses Redis when the URL is set
- [ ] A limited route returns 503 if Redis is unreachable

**Tests**: integration
**Gate**: quick
**Commit**: `feat(api): fail closed when the limiter is down`

---

#### T3: Trusted client IP

**What**: Auth limiter keys on `X-Real-IP` only from a trusted peer. Next proxy sets that header from Caddy and strips inbound `X-Forwarded-For`.
**Where**: `backend/app/infrastructure/web/rate_limit.py`
**Depends on**: T2
**Reuses**: `_client_key`, `buildProxyRequest`
**Requirement**: DOOR-03, DOOR-04

**Tools**:

- MCP: NONE
- Skill: fastapi

**Done when**:

- [ ] A spoofed `X-Real-IP` from an untrusted peer is ignored
- [ ] The proxy outbound request has no client `x-forwarded-for`

**Tests**: unit
**Gate**: quick
**Commit**: `feat(api): key auth limits on the trusted client IP`

---

#### T4: User-id keys for expensive routes

**What**: Conversations, quiz generation, and upload/ingest-start limiters key on authenticated `user_id`.
**Where**: `backend/app/infrastructure/web/rate_limit.py`
**Depends on**: T3
**Reuses**: `_route_template_key`
**Requirement**: DOOR-05, DOOR-06

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

**What**: Settings hold USD/day cap and per-million prices. Application asserts remaining budget before a provider call and debits after success. Local adapters debit fixture micros when tests ask.
**Where**: `backend/app/application/spend.py`
**Depends on**: T5
**Reuses**: generation/quiz call sites
**Requirement**: DOOR-07, DOOR-08, DOOR-09

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Crossing the USD cap returns 429 and skips the provider
- [ ] A successful call increases `usd_micros`

**Tests**: integration
**Gate**: quick
**Commit**: `feat(billing): cap daily generation spend`

---

#### T7: Ask and Teach daily integers

**What**: Free-tier 8 Ask/UTC-day and 1 Teach-session start. Honest 429 copy. Conversation row is kept.
**Where**: `backend/app/application/conversations.py`
**Depends on**: T6
**Reuses**: spend day row
**Requirement**: DOOR-10, DOOR-11, DOOR-12

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

**What**: `LEARNY_AI_KILL_SWITCH` true → 503 on Ask/Teach/quiz generate before any provider SDK.
**Where**: `backend/app/core/config.py`
**Depends on**: T7
**Reuses**: settings cache
**Requirement**: DOOR-13, DOOR-14

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Switch on: 503, zero provider calls
- [ ] Switch off: existing happy path

**Tests**: integration
**Gate**: quick
**Commit**: `feat(api): add a generation kill switch`

---

#### T9: Source count, bytes, in-flight ingest

**What**: Reject owned-source count >2, byte sum + upload >80 MiB, and a second in-flight ingest. Sample excluded from count and bytes.
**Where**: `backend/app/application/ingestion.py`
**Depends on**: T8
**Reuses**: `is_sample`
**Requirement**: DOOR-15, DOOR-16, DOOR-17, DOOR-18

**Tools**:

- MCP: NONE
- Skill: epub-ingestion

**Done when**:

- [ ] Third owned book is 403
- [ ] Sample plus two owned books still uploads
- [ ] Second concurrent ingest is 409

**Tests**: integration
**Gate**: full
**Commit**: `feat(library): cap owned books and ingest concurrency`

---

### Phase 3: Invite, legal, deletion

#### T10: Invite codes

**What**: `invite_codes` table. Register requires a live code; consume decrements remaining uses. Successful invited register mints a session.
**Where**: `backend/app/application/invites.py`
**Depends on**: T9
**Reuses**: `RegisterUser`
**Requirement**: DOOR-19, DOOR-20

**Tools**:

- MCP: NONE
- Skill: fastapi

**Done when**:

- [ ] Missing/bad/exhausted/expired code is 403
- [ ] Valid code returns 201 with session cookies

**Tests**: integration
**Gate**: full
**Commit**: `feat(auth): require an invite code to register`

---

#### T11: Disposable emails and ToS

**What**: Closed disposable-domain list; ToS checkbox required. Failures are generic 422.
**Where**: `backend/app/application/identity.py`
**Depends on**: T10
**Reuses**: `validate_email`
**Requirement**: DOOR-21, DOOR-22

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] A listed disposable domain is 422 with the generic email copy
- [ ] Missing ToS is 422
- [ ] Register form posts invite + accepted_tos

**Tests**: integration
**Gate**: full
**Commit**: `feat(auth): refuse disposable inboxes without a ToS`

---

#### T12: Terms, privacy, copyright

**What**: Public `/terms`, `/privacy`, `/copyright` from committed copy. Copyright page names the DMCA mailbox.
**Where**: `frontend/app/terms/page.tsx`
**Depends on**: T11
**Reuses**: signed-out layout
**Requirement**: DOOR-23, DOOR-24, DOOR-25

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Each route renders a unique title and body
- [ ] Copyright includes the configured contact address

**Tests**: unit
**Gate**: quick
**Commit**: `feat(legal): publish terms, privacy, and copyright pages`

---

#### T13: Storage delete

**What**: `StoragePort` gains delete-by-key (and prefix walk for media). Adapter maps faults to `StorageUnavailable`.
**Where**: `backend/app/domain/ports.py`
**Depends on**: T12
**Reuses**: `S3StorageAdapter`
**Requirement**: DOOR-26

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

**What**: Authenticated CSRF `DELETE /api/auth/account` deletes the caller's objects then the user row. Storage failure leaves the user. Sample survives.
**Where**: `backend/app/application/identity.py`
**Depends on**: T13
**Reuses**: CASCADE FKs
**Requirement**: DOOR-26, DOOR-27, DOOR-28

**Tools**:

- MCP: NONE
- Skill: fastapi

**Done when**:

- [ ] After delete, login 401 and objects gone
- [ ] Injected storage failure leaves the user
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
**Requirement**: DOOR-29, DOOR-34

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

**What**: Hashed verify/reset tokens. Register sends verify without blocking the session. Confirm sets `email_verified_at`. Reset unknown emails 204 with no send. SMTP failure on register still 201.
**Where**: `backend/app/application/identity.py`
**Depends on**: T15
**Reuses**: EmailPort, session hasher
**Requirement**: DOOR-30, DOOR-31, DOOR-32, DOOR-33, DOOR-34

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

- Alembic head after Cycle E is `0023_sample_and_activation` — confirm before writing `0024`.
- `make test-backend` running `test_migrations.py` in-process after a mid-migration schema poisons `learny_test`; reset schema or isolate that module.
- Do not mention invite, spend, or limiter internals in commit messages beyond the product verbs above.
