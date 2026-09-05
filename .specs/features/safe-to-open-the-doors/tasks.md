# safe-to-open-the-doors Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user - do not proceed without it.**

---

**Design**: `.specs/features/safe-to-open-the-doors/design.md`
**Status**: Approved

---

## Test Coverage Matrix

> Generated from codebase, project guidelines, and spec. Guidelines: `CLAUDE.md`.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| ---------- | ------------------ | -------------------- | ---------------- | ----------- |
| Schema / migration | integration | upgrade/downgrade; unique invite; daily budget PK | `backend/tests/test_migrations.py` | `cd backend && uv run pytest tests/test_migrations.py` |
| Limiter | unit + integration | shared Redis window; user_id vs IP; spoofed XFF; 429; Redis down 503 | `backend/tests/test_web_rate_limit_validation.py` | `cd backend && uv run pytest tests/test_web_rate_limit_validation.py` |
| Budget / kill switch | unit + DB | ninth Ask 429; Teach second start; USD cap; review not debited; kill 503 | `backend/tests/test_application_budget.py` | `cd backend && uv run pytest tests/test_application_budget.py` |
| Quotas | unit + HTTP | third source 403; sample excluded; byte 413; in-flight 409 | `backend/tests/test_application_quotas.py` | `cd backend && uv run pytest tests/test_application_quotas.py` |
| Invite / Turnstile / disposable | unit + HTTP | invite 403; one-use; disposable 422; tos 422; Turnstile skip vs fail | `backend/tests/test_application_identity.py` | `cd backend && uv run pytest tests/test_application_identity.py tests/test_web_auth.py` |
| Deletion | unit + HTTP + storage | objects gone; sample remains; storage fault leaves user | `backend/tests/test_application_identity.py` | `cd backend && uv run pytest tests/test_application_identity.py tests/test_storage_s3.py` |
| EmailPort | unit | verify send; token once; reset 204 unknown; SMTP fail still registers | `backend/tests/test_application_email.py` | `cd backend && uv run pytest tests/test_application_email.py` |
| Proxy / Caddy | unit | X-Real-IP forwarded; inbound XFF stripped | `frontend/tests/proxy.test.ts` | `cd frontend && npm test -- proxy` |
| Register / legal / delete UI | unit (jsdom) | invite + tos + Turnstile widget; legal titles; delete confirm | `frontend/tests/auth-screens.test.tsx` | `cd frontend && npm test -- auth-screens legal-pages` |
| ADR | none | document the mail port | `docs/adr/0031-email-port.md` | build gate |

## Gate Check Commands

| Gate Level | When to Use | Command |
| ---------- | ----------- | -------- |
| Quick | After a backend unit/integration module | `cd /home/augusto/projects/learny/backend && uv run pytest <touched tests>` |
| Full | After HTTP, Redis, migration, or frontend tasks | touched backend module and/or `cd /home/augusto/projects/learny/frontend && npm test -- <file>` |
| Build | Phase boundary or ADR | `cd /home/augusto/projects/learny && make lint` plus the cycle's backend + frontend suites |

---

## Execution Plan

Phases are ordered and run sequentially. Packed as Phase 1+2, 3+4, 5, 6+7. Quiet-failure invariants are not Haiku units. Verifier after T32.

### Phase 1: Shared limiter

```
T1 -> T2 -> T3 -> T4 -> T5
```

### Phase 2: Daily budget

```
T6 -> T7 -> T8 -> T9 -> T10
```

### Phase 3: Library quotas

```
T11 -> T12 -> T13
```

### Phase 4: Account deletion

```
T14 -> T15 -> T16 -> T17
```

### Phase 5: Invite gate

```
T18 -> T19 -> T20 -> T21 -> T22 -> T23
```

### Phase 6: Mail port

```
T24 -> T25 -> T26 -> T27 -> T28
```

### Phase 7: Legal and account UI

```
T29 -> T30 -> T31 -> T32
```

---

## Task Breakdown

### Phase 1: Shared limiter

### T1: Implement a Redis rate limiter adapter

**What**: Implement RateLimiter with pooled Redis INCR/EXPIRE. Raise a typed unavailable error when Redis is down.
**Where**: `backend/app/infrastructure/web/redis_rate_limit.py`
**Depends on**: None
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-01, DOOR-05

**Tools**:

- MCP: NONE
- Skill: redis-connections

**Done when**:

- [ ] Two clients sharing a key share one window; dead Redis fails closed.

**Tests**: integration
**Gate**: quick
**Commit**: `feat(api): share rate limits across workers`

---

### T2: Wire the Redis limiter at the API root

**What**: Production API uses the Redis limiter; tests may inject in-memory. Map limiter-unavailable to 503.
**Where**: `backend/app/main.py`
**Depends on**: T1
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-05

**Tools**:

- MCP: NONE
- Skill: fastapi

**Done when**:

- [ ] Default app uses Redis when URL is set; limited route 503 if Redis is unreachable.

**Tests**: integration
**Gate**: quick
**Commit**: `feat(api): fail closed when the limiter is down`

---

### T3: Key expensive routes by user and auth by trusted IP

**What**: Auth limiter keys on trusted X-Real-IP. Ask/Teach/quiz/upload/ingest-start key on user_id plus route. 429 includes Retry-After.
**Where**: `backend/app/infrastructure/web/rate_limit.py`
**Depends on**: T2
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-02, DOOR-03, DOOR-04

**Tools**:

- MCP: NONE
- Skill: fastapi

**Done when**:

- [ ] Two users do not share an Ask bucket; spoofed XFF ignored; 429 Retry-After.

**Tests**: integration
**Gate**: quick
**Commit**: `feat(api): throttle learners instead of the proxy`

---

### T4: Stamp the client IP at the edge

**What**: Caddy sets X-Real-IP from the TCP client on the reverse proxy to the web service.
**Where**: `deploy/Caddyfile`
**Depends on**: T3
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-06

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] A topology or file test pins header_up X-Real-IP from remote_host.

**Tests**: unit
**Gate**: quick
**Commit**: `feat(deploy): forward the real client address`

---

### T5: Forward the stamped IP and drop inbound XFF

**What**: The Next proxy copies Caddy X-Real-IP upstream and deletes inbound x-forwarded-for.
**Where**: `frontend/app/lib/proxy.ts`
**Depends on**: T4
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-06

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Proxy tests show X-Real-IP forwarded and inbound XFF stripped.

**Tests**: unit
**Gate**: full
**Commit**: `feat(web): stop trusting forwarded-for from the browser`

---

### Phase 2: Daily budget

### T6: Add the safety-rail schema

**What**: Alembic 0024 adds ai_spend_days, invite_codes, email_tokens, and nullable email_verified_at / accepted_tos_at. Confirm head is 0023.
**Where**: `backend/migrations/versions/0024_safety_rails.py`
**Depends on**: T5
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-07, DOOR-21, DOOR-35

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Upgrade/downgrade tests pass; spend PK and invite uniqueness hold.

**Tests**: integration
**Gate**: full
**Commit**: `feat(db): store daily spend invites and mail tokens`

---

### T7: Add budget, invite, mail, and captcha settings

**What**: Settings for daily USD, Ask/Teach caps, source/byte/in-flight caps, kill switch, invite required, Turnstile keys, DMCA, SMTP, price catalog.
**Where**: `backend/app/core/config.py`
**Depends on**: T6
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-08, DOOR-12, DOOR-20, DOOR-41, DOOR-42

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Defaults match the spec; production example sets invite required true.

**Tests**: unit
**Gate**: quick
**Commit**: `feat(config): add caps invite and mail settings`

---

### T8: Enforce the daily USD ledger

**What**: DailyBudget checks the UTC-day ledger before generation and debits after success. Local adapters record 0 unless a fixture supplies usage.
**Where**: `backend/app/application/budget.py`
**Depends on**: T7
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-07, DOOR-08, DOOR-09, DOOR-14

**Tools**:

- MCP: NONE
- Skill: fastapi

**Done when**:

- [ ] Crossing the USD cap returns 429; successful call increases usd_micros.

**Tests**: integration
**Gate**: quick
**Commit**: `feat(billing): cap daily generation spend`

---

### T9: Cap daily Ask turns and Teach starts

**What**: Free-tier 8 Ask/UTC-day and 1 Teach start. Honest 429 copy. Conversation row is kept. Quiz deck POST uses the same generation check.
**Where**: `backend/app/application/conversations.py`
**Depends on**: T8
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-10, DOOR-11

**Tools**:

- MCP: NONE
- Skill: fastapi

**Done when**:

- [ ] Ninth Ask is 429; second Teach start is 429; conversation remains.

**Tests**: integration
**Gate**: quick
**Commit**: `feat(ask): cap daily asks and teach starts`

---

### T10: Add the generation kill switch

**What**: LEARNY_AI_KILL_SWITCH true returns 503 on Ask/Teach/quiz generate and embedding ingest. Review still succeeds and is not debited.
**Where**: `backend/app/application/budget.py`
**Depends on**: T9
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-12, DOOR-13

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Switch on: 503 zero provider calls; review submit 200 and not debited.

**Tests**: integration
**Gate**: quick
**Commit**: `feat(api): add a generation kill switch`

---

### Phase 3: Library quotas

### T11: Cap owned source count

**What**: Reject a third owned non-sample upload with 403 before put_object. Sample does not count.
**Where**: `backend/app/application/quotas.py`
**Depends on**: T10
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-15, DOOR-16

**Tools**:

- MCP: NONE
- Skill: epub-ingestion

**Done when**:

- [ ] Third owned book is 403; sample plus two owned books still uploads.

**Tests**: integration
**Gate**: quick
**Commit**: `feat(library): cap how many books a learner owns`

---

### T12: Cap stored bytes

**What**: Reject upload when owned stored byte_size plus the new file would exceed 256 MiB, with 413, before put_object.
**Where**: `backend/app/application/quotas.py`
**Depends on**: T11
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-17

**Tools**:

- MCP: NONE
- Skill: epub-ingestion

**Done when**:

- [ ] Oversized stored sum is 413; sample bytes do not consume the quota.

**Tests**: integration
**Gate**: quick
**Commit**: `feat(library): cap how many bytes a learner stores`

---

### T13: Cap in-flight ingest

**What**: Second ingest start while a job is queued or running returns 409. Allowed start still hits the user-id Redis limiter.
**Where**: `backend/app/application/quotas.py`
**Depends on**: T12
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-18, DOOR-19

**Tools**:

- MCP: NONE
- Skill: celery-workers

**Done when**:

- [ ] Second concurrent ingest is 409; allowed start is still rate-limited per user.

**Tests**: integration
**Gate**: full
**Commit**: `feat(library): allow only one ingest at a time`

---

### Phase 4: Account deletion

### T14: Add object delete to the storage port

**What**: StoragePort gains delete_object. Missing keys are success.
**Where**: `backend/app/domain/ports.py`
**Depends on**: T13
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-30

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Protocol includes delete; fakes implement it.

**Tests**: unit
**Gate**: quick
**Commit**: `feat(storage): describe deleting an object`

---

### T15: Delete objects in the S3 adapter

**What**: Adapter maps delete_object through boto3. Faults become StorageUnavailable. Missing keys succeed.
**Where**: `backend/app/infrastructure/storage/s3.py`
**Depends on**: T14
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-32

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Put then delete then get raises not-found; fault is StorageUnavailable.

**Tests**: integration
**Gate**: quick
**Commit**: `feat(storage): delete objects in minio`

---

### T16: Delete the caller's objects then the user

**What**: Application deletes caller-owned source and media keys, then the user row. Sample is skipped. Storage fault does not delete the user.
**Where**: `backend/app/application/identity.py`
**Depends on**: T15
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-30, DOOR-32, DOOR-33

**Tools**:

- MCP: NONE
- Skill: fastapi

**Done when**:

- [ ] Storage failure leaves the user; non-owner keys never deleted; sample remains.

**Tests**: integration
**Gate**: quick
**Commit**: `feat(auth): erase a learner library from object storage`

---

### T17: Expose account deletion over HTTP

**What**: Authenticated CSRF DELETE /api/auth/account. After success, /api/auth/me with the old cookie is 401.
**Where**: `backend/app/infrastructure/web/auth.py`
**Depends on**: T16
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-30, DOOR-31

**Tools**:

- MCP: NONE
- Skill: fastapi

**Done when**:

- [ ] After delete, me is 401; storage failure returns 502 and the user remains.

**Tests**: integration
**Gate**: full
**Commit**: `feat(auth): let a learner delete their account`

---

### Phase 5: Invite gate

### T18: Consume invite codes on register

**What**: When LEARNY_INVITE_REQUIRED is true, register requires a live code and consume decrements remaining uses.
**Where**: `backend/app/application/invites.py`
**Depends on**: T17
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-20, DOOR-21, DOOR-22, DOOR-26

**Tools**:

- MCP: NONE
- Skill: fastapi

**Done when**:

- [ ] Missing/bad/exhausted/expired code is 403 when flagged; flag off still registers.

**Tests**: integration
**Gate**: full
**Commit**: `feat(auth): require an invite code to register`

---

### T19: Block disposable inboxes and require terms

**What**: Closed disposable-domain list; ToS checkbox required. duck.com allowed. Stamp accepted_tos_at.
**Where**: `backend/app/application/validation.py`
**Depends on**: T18
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-23, DOOR-24, DOOR-25

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] mailinator-class domains are 422; duck.com accepted; missing tos is 422.

**Tests**: unit
**Gate**: quick
**Commit**: `feat(auth): refuse disposable inboxes without terms`

---

### T20: Verify Turnstile tokens behind a port

**What**: TurnstilePort.verify(token, ip); httpx siteverify; empty secret skips; set secret fails closed on missing/bad/timeout/5xx.
**Where**: `backend/app/infrastructure/captcha/turnstile.py`
**Depends on**: T19
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-41, DOOR-42

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Empty secret skips HTTP; set secret rejects bad tokens; tests never call Cloudflare.

**Tests**: unit
**Gate**: quick
**Commit**: `feat(auth): check a bot token when the secret is set`

---

### T21: Gate register with invite, terms, and Turnstile

**What**: RegisterUser consumes invite when required, requires accepted_tos, calls Turnstile when secret set, still issues a session.
**Where**: `backend/app/application/identity.py`
**Depends on**: T20
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-21, DOOR-25, DOOR-39, DOOR-41

**Tools**:

- MCP: NONE
- Skill: fastapi

**Done when**:

- [ ] Invited session works before email_verified_at; bad Turnstile does not create a user.

**Tests**: integration
**Gate**: quick
**Commit**: `feat(auth): mint a session on a valid invite`

---

### T22: Accept invite, terms, and Turnstile on register HTTP

**What**: Register JSON includes invite, accepted_tos, and optional Turnstile token. Auth limiter still keys by trusted IP.
**Where**: `backend/app/infrastructure/web/auth.py`
**Depends on**: T21
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-20, DOOR-38, DOOR-41

**Tools**:

- MCP: NONE
- Skill: fastapi

**Done when**:

- [ ] HTTP tests cover missing invite, missing tos, bad Turnstile.

**Tests**: integration
**Gate**: full
**Commit**: `feat(auth): take invite and captcha fields on register`

---

### T23: Collect invite, terms, and Turnstile on the register form

**What**: Register UI adds invite field, ToS checkbox linking to /terms, and Turnstile widget when the site key is present.
**Where**: `frontend/app/(auth)/register/page.tsx`
**Depends on**: T22
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-25, DOOR-41, DOOR-42

**Tools**:

- MCP: NONE
- Skill: vercel-composition-patterns

**Done when**:

- [ ] Invite and tos fields render; widget mounts only when site key is set.

**Tests**: unit
**Gate**: full
**Commit**: `feat(web): ask for an invite and a bot check to join`

---

### Phase 6: Mail port

### T24: Record the mail port decision

**What**: ADR-0031: Learny EmailPort, SMTP production adapter, log/in-memory tests, no ESP SDK.
**Where**: `docs/adr/0031-email-port.md`
**Depends on**: T23
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-34

**Tools**:

- MCP: NONE
- Skill: create-adr

**Done when**:

- [ ] ADR is accepted and numbered 0031; names SMTP and forbids an ESP SDK.

**Tests**: none
**Gate**: build
**Commit**: `docs(adr): send mail through a learny port`

---

### T25: Add the mail port

**What**: EmailPort.send(to, subject, body) on the domain ports module.
**Where**: `backend/app/domain/ports.py`
**Depends on**: T24
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-34

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Protocol is exported; test fakes implement it.

**Tests**: unit
**Gate**: quick
**Commit**: `feat(mail): describe sending mail`

---

### T26: Send mail over SMTP

**What**: Stdlib SMTP adapter from settings. Log/in-memory adapter for tests. Tests never open a network socket.
**Where**: `backend/app/infrastructure/email/smtp.py`
**Depends on**: T25
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-40

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] SMTP is production default when host is set; tests capture messages in memory.

**Tests**: unit
**Gate**: quick
**Commit**: `feat(mail): send mail through smtp`

---

### T27: Send verify and reset messages

**What**: Register sends a hashed single-use verify token. SMTP failure logs without the raw token and still creates the session.
**Where**: `backend/app/application/identity.py`
**Depends on**: T26
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-34, DOOR-36, DOOR-40

**Tools**:

- MCP: NONE
- Skill: fastapi

**Done when**:

- [ ] Fake port captures verify mail; SMTP raise still creates session; unknown reset does not send.

**Tests**: integration
**Gate**: quick
**Commit**: `feat(auth): email a verify link after register`

---

### T28: Confirm verify and reset over HTTP

**What**: Confirm sets email_verified_at once. Reset updates the hash and invalidates the token. Unknown and known reset request both 204.
**Where**: `backend/app/infrastructure/web/auth.py`
**Depends on**: T27
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-35, DOOR-36, DOOR-37, DOOR-38

**Tools**:

- MCP: NONE
- Skill: fastapi

**Done when**:

- [ ] Confirm cannot replay; unknown reset is 204; limiter 429 on resend.

**Tests**: integration
**Gate**: full
**Commit**: `feat(auth): verify email and reset passwords by mail`

---

### Phase 7: Legal and account UI

### T29: Publish the terms page

**What**: Signed-out /terms returns 200 with a Terms title from committed copy.
**Where**: `frontend/app/terms/page.tsx`
**Depends on**: T28
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-27

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Route renders the terms title without auth.

**Tests**: unit
**Gate**: quick
**Commit**: `feat(legal): publish the terms of service`

---

### T30: Publish the privacy page

**What**: /privacy names OpenAI, Anthropic, and Cloudflare as subprocessors and does not claim zero-data-retention.
**Where**: `frontend/app/privacy/page.tsx`
**Depends on**: T29
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-29

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Page names the three subprocessors and does not claim ZDR.

**Tests**: unit
**Gate**: quick
**Commit**: `feat(legal): publish the privacy notice`

---

### T31: Publish the copyright page

**What**: /copyright includes the configured DMCA contact email.
**Where**: `frontend/app/copyright/page.tsx`
**Depends on**: T30
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-28

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Page includes the configured contact address.

**Tests**: unit
**Gate**: quick
**Commit**: `feat(legal): publish a copyright and dmca contact`

---

### T32: Confirm account deletion in the account panel

**What**: Signed-in account UI confirms then calls DELETE /api/auth/account.
**Where**: `frontend/app/components/AccountPanel.tsx`
**Depends on**: T31
**Reuses**: neighboring Learny ports and tests
**Requirement**: DOOR-30, DOOR-31

**Tools**:

- MCP: NONE
- Skill: vercel-composition-patterns

**Done when**:

- [ ] Confirm control is required before delete; success signs the learner out.

**Tests**: unit
**Gate**: build
**Commit**: `feat(web): let a learner delete their account from settings`

---

## Phase Execution Map

```
Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 -> Phase 5 -> Phase 6 -> Phase 7

Phase 1:  T1 -> T2 -> T3 -> T4 -> T5
Phase 2:  T6 -> T7 -> T8 -> T9 -> T10
Phase 3:  T11 -> T12 -> T13
Phase 4:  T14 -> T15 -> T16 -> T17
Phase 5:  T18 -> T19 -> T20 -> T21 -> T22 -> T23
Phase 6:  T24 -> T25 -> T26 -> T27 -> T28
Phase 7:  T29 -> T30 -> T31 -> T32
```

Execute packing: Phase 1+2, 3+4, 5, 6+7. Sequential batches. Verifier after T32.

---

## Task Granularity Check

| Task | Scope | Status |
| ---- | ----- | ------ |
| T1 Implement a Redis rate limiter adapter | 1 file | Granular |
| T2 Wire the Redis limiter at the API root | 1 file | Granular |
| T3 Key expensive routes by user and auth by trusted IP | 1 file | Granular |
| T4 Stamp the client IP at the edge | 1 file | Granular |
| T5 Forward the stamped IP and drop inbound XFF | 1 file | Granular |
| T6 Add the safety-rail schema | 1 file | Granular |
| T7 Add budget, invite, mail, and captcha settings | 1 file | Granular |
| T8 Enforce the daily USD ledger | 1 file | Granular |
| T9 Cap daily Ask turns and Teach starts | 1 file | Granular |
| T10 Add the generation kill switch | 1 file | Granular |
| T11 Cap owned source count | 1 file | Granular |
| T12 Cap stored bytes | 1 file | Granular |
| T13 Cap in-flight ingest | 1 file | Granular |
| T14 Add object delete to the storage port | 1 file | Granular |
| T15 Delete objects in the S3 adapter | 1 file | Granular |
| T16 Delete the caller's objects then the user | 1 file | Granular |
| T17 Expose account deletion over HTTP | 1 file | Granular |
| T18 Consume invite codes on register | 1 file | Granular |
| T19 Block disposable inboxes and require terms | 1 file | Granular |
| T20 Verify Turnstile tokens behind a port | 1 file | Granular |
| T21 Gate register with invite, terms, and Turnstile | 1 file | Granular |
| T22 Accept invite, terms, and Turnstile on register HTTP | 1 file | Granular |
| T23 Collect invite, terms, and Turnstile on the register form | 1 file | Granular |
| T24 Record the mail port decision | 1 file | Granular |
| T25 Add the mail port | 1 file | Granular |
| T26 Send mail over SMTP | 1 file | Granular |
| T27 Send verify and reset messages | 1 file | Granular |
| T28 Confirm verify and reset over HTTP | 1 file | Granular |
| T29 Publish the terms page | 1 file | Granular |
| T30 Publish the privacy page | 1 file | Granular |
| T31 Publish the copyright page | 1 file | Granular |
| T32 Confirm account deletion in the account panel | 1 file | Granular |

---

## Diagram-Definition Cross-Check

| Task | Depends On (task body) | Diagram Shows | Status |
| ---- | ---------------------- | ------------- | ------ |
| T1 | None | (start) | Match |
| T2 | T1 | T1 -> T2 | Match |
| T3 | T2 | T2 -> T3 | Match |
| T4 | T3 | T3 -> T4 | Match |
| T5 | T4 | T4 -> T5 | Match |
| T6 | T5 | (cross-phase) | Match |
| T7 | T6 | T6 -> T7 | Match |
| T8 | T7 | T7 -> T8 | Match |
| T9 | T8 | T8 -> T9 | Match |
| T10 | T9 | T9 -> T10 | Match |
| T11 | T10 | (cross-phase) | Match |
| T12 | T11 | T11 -> T12 | Match |
| T13 | T12 | T12 -> T13 | Match |
| T14 | T13 | (cross-phase) | Match |
| T15 | T14 | T14 -> T15 | Match |
| T16 | T15 | T15 -> T16 | Match |
| T17 | T16 | T16 -> T17 | Match |
| T18 | T17 | (cross-phase) | Match |
| T19 | T18 | T18 -> T19 | Match |
| T20 | T19 | T19 -> T20 | Match |
| T21 | T20 | T20 -> T21 | Match |
| T22 | T21 | T21 -> T22 | Match |
| T23 | T22 | T22 -> T23 | Match |
| T24 | T23 | (cross-phase) | Match |
| T25 | T24 | T24 -> T25 | Match |
| T26 | T25 | T25 -> T26 | Match |
| T27 | T26 | T26 -> T27 | Match |
| T28 | T27 | T27 -> T28 | Match |
| T29 | T28 | (cross-phase) | Match |
| T30 | T29 | T29 -> T30 | Match |
| T31 | T30 | T30 -> T31 | Match |
| T32 | T31 | T31 -> T32 | Match |

---

## Test Co-location Validation

| Task | Code Layer Created/Modified | Matrix Requires | Task Says | Status |
| ---- | --------------------------- | --------------- | --------- | ------ |
| T1 | in-scope layer | integration | integration | OK |
| T2 | in-scope layer | integration | integration | OK |
| T3 | in-scope layer | integration | integration | OK |
| T4 | in-scope layer | unit | unit | OK |
| T5 | in-scope layer | unit | unit | OK |
| T6 | in-scope layer | integration | integration | OK |
| T7 | in-scope layer | unit | unit | OK |
| T8 | in-scope layer | integration | integration | OK |
| T9 | in-scope layer | integration | integration | OK |
| T10 | in-scope layer | integration | integration | OK |
| T11 | in-scope layer | integration | integration | OK |
| T12 | in-scope layer | integration | integration | OK |
| T13 | in-scope layer | integration | integration | OK |
| T14 | in-scope layer | unit | unit | OK |
| T15 | in-scope layer | integration | integration | OK |
| T16 | in-scope layer | integration | integration | OK |
| T17 | in-scope layer | integration | integration | OK |
| T18 | in-scope layer | integration | integration | OK |
| T19 | in-scope layer | unit | unit | OK |
| T20 | in-scope layer | unit | unit | OK |
| T21 | in-scope layer | integration | integration | OK |
| T22 | in-scope layer | integration | integration | OK |
| T23 | in-scope layer | unit | unit | OK |
| T24 | in-scope layer | none | none | OK |
| T25 | in-scope layer | unit | unit | OK |
| T26 | in-scope layer | unit | unit | OK |
| T27 | in-scope layer | integration | integration | OK |
| T28 | in-scope layer | integration | integration | OK |
| T29 | in-scope layer | unit | unit | OK |
| T30 | in-scope layer | unit | unit | OK |
| T31 | in-scope layer | unit | unit | OK |
| T32 | in-scope layer | unit | unit | OK |

---

## Notes

- Alembic head is `0023_starter_quiz_origin`. Confirm before writing `0024`.
- Pin honest copy in tests: today's AI limit resets 00:00 UTC; AI paused but library and review still work; this instance is invite-only.
- Do not name the daily ledger `SpendPort`.
