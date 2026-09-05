# safe-to-open-the-doors Specification (RFC-0007 Cycle F / Bet 6)

## Problem Statement

The hosted instance cannot take a stranger's account. Rate limits share one Next.js-proxy IP, there is no per-user AI spend cap, uploads are unbounded, register is open, MinIO objects survive account deletion, and there is no mail port for verify or reset. RFC-0007 Cycle F is the registration gate: shared limiter, caps, invite, Turnstile, legal pages, deletion, and EmailPort.

## Goals

- [ ] Authenticated expensive routes throttle per `user_id` across API processes; auth routes throttle per trusted-proxy client IP.
- [ ] A learner who hits the daily AI budget or the operator kill switch sees a hard stop with honest copy; conversations are not deleted.
- [ ] A learner cannot exceed two owned books, 256 MiB stored, or one in-flight ingest.
- [ ] Register on a hosted instance requires a valid invite, rejects disposable domains, and checks Turnstile when the siteverify secret is configured; ToS is accepted on that form.
- [ ] A learner can delete their account and that removes their MinIO objects and Postgres rows. Legal pages name a DMCA contact.
- [ ] Verify and password-reset mail go through a Learny `EmailPort`.

---

## Out of Scope

| Feature | Reason |
|---|---|
| RFC Cycle G (effort=low, teach cache, OpenAI-compatible fallback) | Separate letter; needs an ADR-0020 amendment |
| Guest Ask / uncapped public Ask | RFC conflict 2: only after this cycle is green |
| Checkout, plans, Stripe/Paddle | RFC exclusion: caps yes, payment later |
| New generation or embedding provider SDKs; Resend/Postmark/SES; LiteLLM/OpenRouter | ADR-0007 / 0009 / 0019 / 0020 |
| Cloudflare Python/JS official SDK | Siteverify is httpx behind a Learny port; the widget is a script tag |
| EU representative, ZDR as a blocker, publisher hash-scanning, Kubernetes | RFC Cycle F out |
| Opt-in due digest | EmailPort this letter; digest is a later small cycle |
| Embedding-model swap | ADR-0019 stands |
| Public sharing of book bytes or book-derived cards | RFC exclusion; unchanged |

---

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
|---|---|---|---|
| Cycle split | This PR is RFC F / Bet 6 only | ROADMAP grouped F–G; G is model work | auto (AD-324) |
| Turnstile | Invite when the flag is on **and** Turnstile when the secret is set **and** disposable-domain blocking | RFC Cycle F body lists Turnstile as the opening step; empty secret skips so CI stays network-free | auto (AD-325) |
| Email adapter | `EmailPort` + SMTP settings; log adapter in tests | No ESP SDK | auto (AD-326) |
| Invite vs verify | Valid invite mints a session immediately. Verify mail is sent. Invited users may use Ask/upload before `email_verified_at` | Cycle E first session must still work | auto (AD-327) |
| Due digest | Out of this PR | EmailPort ships; digest is a later small cycle | auto (AD-328) |
| Spend meter | $0.50/UTC day USD ledger plus 8 Ask, 1 Teach start, 2 owned sources, 256 MiB, 1 in-flight ingest. Sample excluded from count and bytes | 80 MiB would block a legal 100 MiB PDF | auto (AD-329) |
| Invite flag | `LEARNY_INVITE_REQUIRED` default false (self-host/CI). Production example true | Existing register tests have no code | auto (AD-333) |
| Redis down | Limited routes return 503 | Fail-open reopens the proxy hole | auto (AD-330) |
| Client IP | Caddy stamps `X-Real-IP`; Next copies it and strips inbound `X-Forwarded-For`; FastAPI reads it only from a trusted hop | Never trust client XFF | auto (AD-330) |
| Spend debit | After a successful provider call; check-before-call uses the ledger | Two overlapping Asks may overshoot by one call | auto |
| What counts as spend | Generation (Ask, Teach, quiz deck) and embeddings on ingest. Reviews/FSRS are $0 | rq10 | auto |
| Local adapters | Record 0 USD unless a test fixture supplies usage | Offline suite | auto |
| Disposable block | Deny-list; allow `duck.com`, iCloud Hide My Email, SimpleLogin | Privacy aliases are not throwaway inboxes | auto |
| ToS checkbox | `accepted_tos: true` required | Legal pages are not optional | auto |
| Legal copy | Committed markdown; privacy names OpenAI, Anthropic, and Cloudflare; does not claim ZDR | Brazil operator; RFC outs EU rep | auto |
| DMCA contact | `LEARNY_DMCA_CONTACT_EMAIL` on `/copyright` | Operator mailbox | auto |
| Deletion | List caller keys, storage delete, then user CASCADE. Storage fault does not delete the user | AD-283 | auto (AD-331) |
| Reset enumeration | Unknown and known email both 204 | Auth dimension | auto |
| Mail failure | Register still creates the invited session | Best-effort this letter | auto |
| Honest copy | Cap: `You've reached today's AI limit. It resets at 00:00 UTC.` Kill: `Learny's AI is temporarily paused. Your library and review still work.` Invite: `This instance is invite-only.` | RFC; pin in tests | auto |
| Turnstile failure | WHEN the secret is set, siteverify timeout/5xx fails closed (no user) | Same class as Redis fail-closed | auto |

**Open questions:** none — all resolved or logged above.

### Implicit-requirement dimensions

| Dimension | Resolution |
|---|---|
| Input validation & bounds | Invite, ToS, disposable list, Turnstile token, source/byte/in-flight caps, spend integers |
| Failure / partial-failure | Redis 503; storage delete 502 without user delete; SMTP log + session still created; siteverify fail-closed when secret set |
| Idempotency / retry | Mail tokens consume once; missing object delete is success |
| Auth boundaries & rate limits | This feature's limiter, invite, and deletion CSRF |
| Concurrency / ordering | Overlapping Asks may overshoot by one paid call; next call 429s |
| Data lifecycle / expiry | Invite `expires_at`; mail token TTL; account delete |
| Observability | Mail failure logs without the raw token |
| External-dependency failure | Redis, SMTP, Turnstile siteverify |
| State-transition integrity | Invite `remaining_uses`; token `consumed_at`; `email_verified_at` |

---

## User Stories

### P1: Shared limiter ⭐ MVP

**User Story**: As the operator, I want rate limits to follow the learner (or the real client IP on login), so one actor cannot 429 everyone behind the Next.js proxy.

**Why P1**: rq09 documents the current limiter as a launch blocker.

**Acceptance Criteria**:

1. (DOOR-01) WHEN two API processes share Redis THEN a limiter `hit` on one SHALL count toward the window on the other for the same key.
2. (DOOR-02) WHEN an authenticated caller hits Ask/Teach turn, quiz deck POST, upload, or ingest-start THEN the system SHALL key the limiter on that caller's `user_id` and route template, not on `request.client.host`.
3. (DOOR-03) WHEN register, login, password-reset request, or verify-resend is called THEN the system SHALL key the limiter on the trusted-proxy client IP and route, never on a client-supplied `X-Forwarded-For` chain.
4. (DOOR-04) IF the window is exceeded THEN the system SHALL respond 429 with `Retry-After`.
5. (DOOR-05) IF Redis is unavailable THEN limited routes SHALL respond 503.
6. (DOOR-06) The system SHALL stamp `X-Real-IP` at Caddy from the TCP client, forward that value through the Next.js proxy, and strip a browser-supplied `X-Forwarded-For` before FastAPI.

**Independent Test**: Two processes or a Redis-backed fake share a key; a spoofed XFF does not mint a fresh auth budget.

---

### P1: Spend cap and kill switch ⭐ MVP

**User Story**: As the operator, I want a hard per-user daily AI stop and a global kill switch, so a farmed account cannot run an unbounded Anthropic bill.

**Why P1**: RFC Cycle F spend ledger; rq10 caps without billing.

**Acceptance Criteria**:

1. (DOOR-07) The system SHALL persist per-user per-UTC-day AI spend in USD micros on a Postgres ledger.
2. (DOOR-08) IF the caller's day spend is at or above `LEARNY_DAILY_AI_SPEND_USD` THEN Ask/Teach generation and quiz deck POST SHALL return 429 with honest exhausted copy and SHALL NOT call the provider.
3. (DOOR-09) WHEN a provider call succeeds THEN the system SHALL add that call's USD (from the adapter usage × price catalog) to the day's ledger.
4. (DOOR-10) IF the caller has already used 8 Ask turns this UTC day THEN a further Ask turn SHALL return 429 with come-back-tomorrow copy and SHALL NOT delete the conversation.
5. (DOOR-11) IF the caller has already started 1 Teach session this UTC day THEN a further Teach start SHALL return 429 with the same honest class of copy.
6. (DOOR-12) WHILE `LEARNY_AI_KILL_SWITCH` is true the system SHALL return 503 on Ask/Teach generation, quiz deck POST, and embedding-producing ingest steps, with operator-pause copy.
7. (DOOR-13) WHEN the caller submits an FSRS review THEN the system SHALL NOT debit the AI ledger.
8. (DOOR-14) The system SHALL record 0 USD for local deterministic adapters unless a test fixture supplies usage.

**Independent Test**: Fake generation that records usage; ninth Ask is 429 and the conversation row remains; review still grades under the kill switch.

---

### P1: Library quotas ⭐ MVP

**User Story**: As the operator, I want source count, stored bytes, and in-flight ingest capped per user, so disk and the worker queue cannot be filled by one account.

**Why P1**: rq09 Cycle A; RFC F bullet.

**Acceptance Criteria**:

1. (DOOR-15) IF the caller already owns 2 non-sample sources THEN upload SHALL return 403 with a quota copy, before `put_object`.
2. (DOOR-16) The sample source SHALL NOT count toward the caller's source count or stored-byte quota.
3. (DOOR-17) IF the caller's owned stored `byte_size` sum plus the new file would exceed 256 MiB THEN upload SHALL return 413, before `put_object`.
4. (DOOR-18) IF the caller already has an ingestion job in `{queued, running}` THEN start-ingest SHALL return 409 with an in-flight copy.
5. (DOOR-19) WHEN ingest start is allowed THEN it SHALL still pass the user-id Redis limiter (DOOR-02).

**Independent Test**: Third owned EPUB 403; sample still lists; second concurrent ingest 409.

---

### P1: Invite-only register ⭐ MVP

**User Story**: As the operator, I want new hosted accounts to require an invite, a real-looking email, and a bot check when configured, so bots cannot mint unlimited sessions.

**Why P1**: RFC signup gate; rq09 Cycle C.

**Acceptance Criteria**:

1. (DOOR-20) WHERE `LEARNY_INVITE_REQUIRED` is true, WHEN register is called without a valid invite code THEN the system SHALL return 403 with invite-required copy and SHALL NOT create a user.
2. (DOOR-21) WHERE invite codes are required, WHEN register is called with a valid invite THEN the system SHALL create the user, decrement remaining uses, and start a session.
3. (DOOR-22) IF remaining uses hit 0 or `expires_at` is in the past THEN a further register with that code SHALL return 403.
4. (DOOR-23) IF the email domain is on the disposable deny-list THEN register SHALL return 422 with the same generic invalid-email copy used for malformed addresses.
5. (DOOR-24) WHEN the email is a documented privacy alias (`duck.com`) THEN register SHALL NOT reject it as disposable.
6. (DOOR-25) IF `accepted_tos` is not true THEN register SHALL return 422.
7. (DOOR-26) WHERE `LEARNY_INVITE_REQUIRED` is false THEN register without an invite code SHALL still create a user, subject to ToS, disposable, and Turnstile rules.
8. (DOOR-41) WHERE `LEARNY_TURNSTILE_SECRET` is set, IF the Turnstile token is missing or siteverify rejects it THEN register SHALL return 400 and SHALL NOT create a user.
9. (DOOR-42) WHERE `LEARNY_TURNSTILE_SECRET` is empty THEN register SHALL skip siteverify.

**Independent Test**: Mint a one-use invite with the flag on; first register 201; second 403; `mailinator.com` 422; empty secret skips captcha; set secret rejects a bad token.

---

### P1: Legal pages and account deletion ⭐ MVP

**User Story**: As a learner, I want to read the rules and erase my account, including files in object storage.

**Why P1**: RFC legal + deletion; LGPD/GDPR erase.

**Acceptance Criteria**:

1. (DOOR-27) WHEN an unauthenticated caller opens `/terms`, `/privacy`, or `/copyright` THEN the system SHALL respond 200 with those document titles.
2. (DOOR-28) WHEN `/copyright` is served THEN the page SHALL include the configured DMCA contact email.
3. (DOOR-29) WHEN `/privacy` is served THEN the page SHALL name OpenAI and Anthropic as subprocessors and SHALL NOT claim zero-data-retention.
4. (DOOR-30) WHEN the owner `DELETE /api/auth/account` with CSRF THEN the system SHALL delete that user's MinIO objects for their sources (not the sample), then delete the user so Postgres FKs CASCADE.
5. (DOOR-31) WHEN the owner has deleted their account THEN GET `/api/auth/me` with the old cookie SHALL be 401, and the sample source SHALL still exist.
6. (DOOR-32) IF `StoragePort` delete fails THEN the system SHALL NOT delete the user row and SHALL respond 502.
7. (DOOR-33) IF a non-owner object key would be deleted THEN the system SHALL NOT delete it.

**Independent Test**: Put an object, delete account, get_object raises; sample row still in DB; injected storage fault leaves the user.

---

### P1: Email verify and reset ⭐ MVP

**User Story**: As a learner, I want a verification mail and a password reset, so the form that opens is not a dead letter.

**Why P1**: RFC EmailPort the day the form opens.

**Acceptance Criteria**:

1. (DOOR-34) WHEN register succeeds THEN the system SHALL send one verify message through `EmailPort` containing a single-use token.
2. (DOOR-35) WHEN that token is submitted THEN the system SHALL set `email_verified_at` and SHALL NOT consume the token twice.
3. (DOOR-36) WHEN password-reset is requested THEN the system SHALL return 204 whether or not the email exists, and SHALL send mail only when a user exists.
4. (DOOR-37) WHEN a valid reset token is submitted with a new password THEN the system SHALL update the hash and invalidate the token.
5. (DOOR-38) IF Redis/auth limiter is exceeded on reset or verify-resend THEN the system SHALL return 429.
6. (DOOR-39) WHEN an invited user has no `email_verified_at` THEN the system SHALL still allow Ask and upload.
7. (DOOR-40) IF SMTP send fails THEN register SHALL still create the invited session and SHALL log the failure without the raw token.

**Independent Test**: Fake EmailPort captures the token; reset unknown email is 204 and send was not called.

---

## Edge Cases

- IF two overlapping Ask calls both pass the spend check THEN the system SHALL still persist both debits; a later call in the same day that would exceed the cap SHALL 429.
- WHEN the kill switch is on, reads (library, review due, chapter) SHALL still succeed.
- IF Redis `INCR` fails THEN the request SHALL 503, not skip the limiter.
- IF Turnstile siteverify times out WHILE the secret is set THEN register SHALL fail closed.

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
|---|---|---|---|
| DOOR-01 | P1: Shared limiter | Tasks | In Tasks |
| DOOR-02 | P1: Shared limiter | Tasks | In Tasks |
| DOOR-03 | P1: Shared limiter | Tasks | In Tasks |
| DOOR-04 | P1: Shared limiter | Tasks | In Tasks |
| DOOR-05 | P1: Shared limiter | Tasks | In Tasks |
| DOOR-06 | P1: Shared limiter | Tasks | In Tasks |
| DOOR-07 | P1: Spend cap | Tasks | In Tasks |
| DOOR-08 | P1: Spend cap | Tasks | In Tasks |
| DOOR-09 | P1: Spend cap | Tasks | In Tasks |
| DOOR-10 | P1: Spend cap | Tasks | In Tasks |
| DOOR-11 | P1: Spend cap | Tasks | In Tasks |
| DOOR-12 | P1: Spend cap | Tasks | In Tasks |
| DOOR-13 | P1: Spend cap | Tasks | In Tasks |
| DOOR-14 | P1: Spend cap | Tasks | In Tasks |
| DOOR-15 | P1: Library quotas | Tasks | In Tasks |
| DOOR-16 | P1: Library quotas | Tasks | In Tasks |
| DOOR-17 | P1: Library quotas | Tasks | In Tasks |
| DOOR-18 | P1: Library quotas | Tasks | In Tasks |
| DOOR-19 | P1: Library quotas | Tasks | In Tasks |
| DOOR-20 | P1: Invite-only register | Tasks | In Tasks |
| DOOR-21 | P1: Invite-only register | Tasks | In Tasks |
| DOOR-22 | P1: Invite-only register | Tasks | In Tasks |
| DOOR-23 | P1: Invite-only register | Tasks | In Tasks |
| DOOR-24 | P1: Invite-only register | Tasks | In Tasks |
| DOOR-25 | P1: Invite-only register | Tasks | In Tasks |
| DOOR-26 | P1: Invite-only register | Tasks | In Tasks |
| DOOR-27 | P1: Legal pages | Tasks | In Tasks |
| DOOR-28 | P1: Legal pages | Tasks | In Tasks |
| DOOR-29 | P1: Legal pages | Tasks | In Tasks |
| DOOR-30 | P1: Legal pages | Tasks | In Tasks |
| DOOR-31 | P1: Legal pages | Tasks | In Tasks |
| DOOR-32 | P1: Legal pages | Tasks | In Tasks |
| DOOR-33 | P1: Legal pages | Tasks | In Tasks |
| DOOR-34 | P1: Email | Tasks | In Tasks |
| DOOR-35 | P1: Email | Tasks | In Tasks |
| DOOR-36 | P1: Email | Tasks | In Tasks |
| DOOR-37 | P1: Email | Tasks | In Tasks |
| DOOR-38 | P1: Email | Tasks | In Tasks |
| DOOR-39 | P1: Email | Tasks | In Tasks |
| DOOR-40 | P1: Email | Tasks | In Tasks |
| DOOR-41 | P1: Invite-only register | Tasks | In Tasks |
| DOOR-42 | P1: Invite-only register | Tasks | In Tasks |

**Coverage:** 42 total, 42 mapped to T1–T32.

---

## Success Criteria

- [ ] A second API worker shares limiter state via Redis.
- [ ] Ninth Ask in a UTC day is 429 and the thread remains.
- [ ] Third owned upload is 403; sample still readable.
- [ ] Register without invite is 403 when the flag is on; one-use invite works once; bad Turnstile token is 400 when the secret is set.
- [ ] Account deletion removes the caller's objects and leaves the sample.
- [ ] Fake EmailPort receives verify and reset messages; unknown reset is 204.
