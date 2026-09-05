# safe-to-open-the-doors Specification (RFC-0007 Cycle F / Bet 6)

## Problem Statement

The hosted instance cannot take a stranger's account. Rate limits share one Next.js-proxy IP, there is no per-user AI spend cap, uploads are unbounded, register is open, MinIO objects survive account deletion, and there is no mail port for verify or reset. RFC-0007 Cycle F is the registration gate: shared limiter, caps, invite, legal pages, deletion, and EmailPort.

## Goals

- [ ] Authenticated expensive routes throttle per `user_id` across API processes; auth routes throttle per trusted-proxy client IP.
- [ ] A learner who hits the daily AI budget or the operator kill switch sees a hard stop with honest copy; conversations are not deleted.
- [ ] A learner cannot exceed two owned books, 80 MiB stored, or one in-flight ingest.
- [ ] Register requires a valid invite and rejects disposable domains; ToS is accepted on that form.
- [ ] A learner can delete their account and that removes their MinIO objects and Postgres rows. Legal pages name a DMCA contact.
- [ ] Verify and password-reset mail go through a Learny `EmailPort`.

---

## Out of Scope

| Feature | Reason |
|---|---|
| RFC Cycle G (effort=low, teach cache, OpenAI-compatible fallback) | Separate letter; needs ADR-0020 amendment |
| Turnstile / Cloudflare siteverify | Invite XOR captcha (rq09); invite-only until open registration |
| Guest Ask / uncapped public Ask | RFC conflict 2: only after this cycle is green |
| Checkout, plans, Stripe/Paddle | RFC exclusion: caps yes, payment later |
| New provider SDKs on the request path (Resend, LiteLLM, OpenRouter) | ADR-0007 / 0009 |
| EU representative, ZDR as a blocker, publisher hash-scanning, Kubernetes | RFC Cycle F out |
| Opt-in due digest | EmailPort this letter; digest is a later small cycle |
| Embedding-model swap | ADR-0019 stands |
| Public sharing of book bytes or book-derived cards | RFC exclusion; unchanged |

---

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
|---|---|---|---|
| Cycle split | This PR is RFC F / Bet 6 only | ROADMAP grouped F–G; G is model work | auto (AD-324) |
| Turnstile | Deferred; invite code required | rq09 XOR; RFC action item | auto (AD-325) |
| Email adapter | `EmailPort` + SMTP settings; log adapter in tests | No ESP SDK | auto (AD-326) |
| Invite vs verify | Invite mints a session; verify mail is sent but not a wall | Cycle E first session must still work | auto (AD-327) |
| Due digest | Out | Caps/deletion/mail already fill the letter | auto (AD-328) |
| Daily USD cap | `$0.50` per UTC day (`LEARNY_DAILY_AI_SPEND_USD`) | Backstop above 8×$0.029 Ask | auto (AD-329) |
| Integer Free caps | 8 Ask/day, 1 Teach session/day, 2 owned sources, 80 MiB, 1 in-flight ingest | rq10 Free row; sample source excluded from count and bytes | auto (AD-329) |
| Kill switch | `LEARNY_AI_KILL_SWITCH` true → 503 on generation/embed/quiz-gen with honest copy | Operator stop without a deploy of code | auto |
| Redis down | Limited routes return 503 | Shared fate with Celery; fail-open would reopen the proxy hole | auto |
| Client IP | Next.js proxy copies Caddy's `X-Real-IP` (or the single trusted hop) onto the upstream request and strips a browser-supplied `X-Forwarded-For` | rq09; never trust client XFF | auto (AD-330) |
| Expensive-route key | `user_id` for Ask/Teach turns, quiz deck POST, upload, ingest start | RFC; unauthenticated never reach these | auto (AD-330) |
| Auth-route key | trusted-proxy IP + route template | Credential stuffing | auto |
| Spend debit | After a successful provider call, in the same request as the response; check-before-call uses the ledger | Two overlapping Asks may both pass the check; unique daily row + increment keeps the overshoot to one extra call | auto |
| What counts as spend | Generation (Ask, Teach, quiz deck) and embeddings on ingest | Reviews/FSRS are $0 (rq10) | auto |
| Invite table | `code` unique, `remaining_uses` int, `expires_at` nullable | CLI mints; register decrements | auto |
| Disposable block | Deny-list of throwaway domains; allow privacy aliases (`duck.com`, iCloud Hide My Email, SimpleLogin) | rq07/rq09 | auto |
| ToS checkbox | Register body includes `accepted_tos: true`; false → 422 | Legal pages are not optional on the hosted form | auto |
| Legal copy | Static routes with required headings; body is committed markdown, not model-generated at request time | A lying policy is worse than a short one | auto |
| DMCA contact | `LEARNY_DMCA_CONTACT_EMAIL` rendered on `/copyright` | Operator-owned mailbox | auto |
| Deletion | List the caller's object keys, `StoragePort` delete, then delete the user (CASCADE). Sample is not the caller's | AD-283 | auto (AD-331) |
| Reset enumeration | Unknown email and known email return the same 204 | Auth dimension | auto |
| Mail rate limit | Verify-resend and reset POSTs use the auth limiter (IP) | Abuse of EmailPort | auto |
| Input bounds | Invite code 8–64 charset-safe chars; reset/verify tokens hashed at rest like sessions | Injection/auth | auto |
| Observability | Spend increment and kill-switch trips log INFO without book text | AD-041 | auto |
| Backups checklist | Out of product tests; ops already has ADR-0024 drills | rq09 nice-to-have vs this letter's code | auto |

**Open questions:** none — all resolved or logged above.

---

## User Stories

### P1: Shared limiter ⭐ MVP

**User Story**: As the operator, I want rate limits to follow the learner (or the real client IP on login), so one actor cannot 429 everyone behind the Next.js proxy.

**Why P1**: rq09 documents the current limiter as a launch blocker.

**Acceptance Criteria**:

1. (DOOR-01) WHEN two API processes share Redis THEN a limiter `hit` on one SHALL count toward the window on the other for the same key.
2. (DOOR-02) WHEN an authenticated caller hits Ask/Teach turn, quiz deck POST, upload, or ingest-start THEN the system SHALL key the limiter on that caller's `user_id` and route template, not on `request.client.host`.
3. (DOOR-03) WHEN register or login is called THEN the system SHALL key the limiter on the trusted-proxy client IP and route, never on a client-supplied `X-Forwarded-For` chain.
4. (DOOR-04) IF the window is exceeded THEN the system SHALL respond 429 with `Retry-After`.
5. (DOOR-05) IF Redis is unavailable THEN limited routes SHALL respond 503.

**Independent Test**: Two processes or a Redis-backed fake share a key; a spoofed XFF does not mint a fresh auth budget.

---

### P1: Spend cap and kill switch ⭐ MVP

**User Story**: As the operator, I want a hard per-user daily AI stop and a global kill switch, so a farmed account cannot run an unbounded Anthropic bill.

**Why P1**: RFC Cycle F spend ledger; rq10 caps without billing.

**Acceptance Criteria**:

1. (DOOR-06) The system SHALL persist per-user per-UTC-day AI spend in USD micros on a Postgres ledger.
2. (DOOR-07) IF the caller's day spend is at or above `LEARNY_DAILY_AI_SPEND_USD` THEN Ask/Teach generation and quiz deck POST SHALL return 429 with honest exhausted copy and SHALL NOT call the provider.
3. (DOOR-08) WHEN a provider call succeeds THEN the system SHALL add that call's USD (from the adapter usage × price catalog) to the day's ledger.
4. (DOOR-09) IF the caller has already used 8 Ask turns this UTC day THEN a further Ask turn SHALL return 429 with come-back-tomorrow copy and SHALL NOT delete the conversation.
5. (DOOR-10) IF the caller has already started 1 Teach session this UTC day THEN a further Teach start SHALL return 429 with the same honest class of copy.
6. (DOOR-11) WHILE `LEARNY_AI_KILL_SWITCH` is true the system SHALL return 503 on Ask/Teach generation, quiz deck POST, and embedding-producing ingest steps, with operator-pause copy.
7. (DOOR-12) FSRS review submit SHALL NOT debit the AI ledger.

**Independent Test**: Fake generation that records usage; ninth Ask is 429 and the conversation row remains.

---

### P1: Library quotas ⭐ MVP

**User Story**: As the operator, I want source count, stored bytes, and in-flight ingest capped per user, so disk and the worker queue cannot be filled by one account.

**Why P1**: rq09 Cycle A; RFC F bullet.

**Acceptance Criteria**:

1. (DOOR-13) IF the caller already owns 2 non-sample sources THEN upload SHALL return 403 with a quota copy.
2. (DOOR-14) The sample source SHALL NOT count toward the caller's source count or stored-byte quota.
3. (DOOR-15) IF the caller's owned stored `byte_size` sum plus the new file would exceed 80 MiB THEN upload SHALL return 403.
4. (DOOR-16) IF the caller already has an ingestion job in an active status THEN start-ingest SHALL return 409 with an in-flight copy.
5. (DOOR-17) WHEN ingest start is allowed THEN it SHALL still pass the user-id Redis limiter (DOOR-02).

**Independent Test**: Third owned EPUB 403; sample still lists; second concurrent ingest 409.

---

### P1: Invite-only register ⭐ MVP

**User Story**: As the operator, I want new hosted accounts to require an invite and a real-looking email, so bots cannot mint unlimited sessions.

**Why P1**: RFC signup gate; rq09 Cycle C.

**Acceptance Criteria**:

1. (DOOR-18) WHEN register is called without a valid invite code THEN the system SHALL return 403 with invite-required copy and SHALL NOT create a user.
2. (DOOR-19) WHEN register is called with a valid invite THEN the system SHALL create the user, decrement remaining uses, and start a session (existing cookie auth).
3. (DOOR-20) IF remaining uses hit 0 THEN a further register with that code SHALL return 403.
4. (DOOR-21) IF the email domain is on the disposable deny-list THEN register SHALL return 422 with the same generic invalid-email copy used for malformed addresses (no disposable disclosure).
5. (DOOR-22) WHEN the email is a documented privacy alias (`duck.com`) THEN register SHALL NOT reject it as disposable.
6. (DOOR-23) IF `accepted_tos` is not true THEN register SHALL return 422.

**Independent Test**: Mint a one-use invite; first register 201; second 403; `mailinator.com` 422.

---

### P1: Legal pages and account deletion ⭐ MVP

**User Story**: As a learner, I want to read the rules and erase my account, including files in object storage.

**Why P1**: RFC legal + deletion; LGPD/GDPR erase.

**Acceptance Criteria**:

1. (DOOR-24) Signed-out `/terms`, `/privacy`, and `/copyright` SHALL return 200 with those document titles.
2. (DOOR-25) `/copyright` SHALL include the configured DMCA contact email.
3. (DOOR-26) WHEN the owner `DELETE /api/auth/account` with CSRF THEN the system SHALL delete that user's MinIO objects for their sources (not the sample), then delete the user so Postgres FKs CASCADE.
4. (DOOR-27) AFTER deletion, GET `/api/auth/me` with the old cookie SHALL be 401, and the sample source SHALL still exist.
5. (DOOR-28) IF a non-owner object key would be deleted THEN the system SHALL NOT delete it.

**Independent Test**: Put an object, delete account, get_object raises; sample row still in DB.

---

### P1: Email verify and reset ⭐ MVP

**User Story**: As a learner, I want a verification mail and a password reset, so the form that opens is not a dead letter.

**Why P1**: RFC EmailPort the day the form opens.

**Acceptance Criteria**:

1. (DOOR-29) WHEN register succeeds THEN the system SHALL send one verify message through `EmailPort` containing a single-use token.
2. (DOOR-30) WHEN that token is submitted THEN the system SHALL set `email_verified_at` and SHALL NOT consume the token twice.
3. (DOOR-31) WHEN password-reset is requested THEN the system SHALL return 204 whether or not the email exists, and SHALL send mail only when a user exists.
4. (DOOR-32) WHEN a valid reset token is submitted with a new password THEN the system SHALL update the hash and invalidate the token.
5. (DOOR-33) IF Redis/auth limiter is exceeded on reset or verify-resend THEN the system SHALL return 429.
6. (DOOR-34) Invited, unverified users SHALL still be allowed to Ask and upload (verification is not a wall this letter).

**Independent Test**: Fake EmailPort captures the token; reset unknown email is 204 and send was not called.

---

## Edge Cases

- IF two overlapping Ask calls both pass the spend check THEN the system SHALL still persist both debits; a third call in the same day that would exceed the cap SHALL 429.
- IF invite `expires_at` is in the past THEN register SHALL 403.
- IF SMTP send fails THEN register SHALL still create the invited session (mail is best-effort this letter) and SHALL log the failure without the raw token.
- IF `StoragePort.delete` fails midway THEN the system SHALL NOT delete the user row (account remains so the caller can retry).
- WHEN the kill switch is on, reads (library, review due, chapter) SHALL still succeed.

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
|---|---|---|---|
| DOOR-01 | P1: Shared limiter | Design | Pending |
| DOOR-02 | P1: Shared limiter | Design | Pending |
| DOOR-03 | P1: Shared limiter | Design | Pending |
| DOOR-04 | P1: Shared limiter | Design | Pending |
| DOOR-05 | P1: Shared limiter | Design | Pending |
| DOOR-06 | P1: Spend cap | Design | Pending |
| DOOR-07 | P1: Spend cap | Design | Pending |
| DOOR-08 | P1: Spend cap | Design | Pending |
| DOOR-09 | P1: Spend cap | Design | Pending |
| DOOR-10 | P1: Spend cap | Design | Pending |
| DOOR-11 | P1: Spend cap | Design | Pending |
| DOOR-12 | P1: Spend cap | Design | Pending |
| DOOR-13 | P1: Library quotas | Design | Pending |
| DOOR-14 | P1: Library quotas | Design | Pending |
| DOOR-15 | P1: Library quotas | Design | Pending |
| DOOR-16 | P1: Library quotas | Design | Pending |
| DOOR-17 | P1: Library quotas | Design | Pending |
| DOOR-18 | P1: Invite-only register | Design | Pending |
| DOOR-19 | P1: Invite-only register | Design | Pending |
| DOOR-20 | P1: Invite-only register | Design | Pending |
| DOOR-21 | P1: Invite-only register | Design | Pending |
| DOOR-22 | P1: Invite-only register | Design | Pending |
| DOOR-23 | P1: Invite-only register | Design | Pending |
| DOOR-24 | P1: Legal pages | Design | Pending |
| DOOR-25 | P1: Legal pages | Design | Pending |
| DOOR-26 | P1: Legal pages | Design | Pending |
| DOOR-27 | P1: Legal pages | Design | Pending |
| DOOR-28 | P1: Legal pages | Design | Pending |
| DOOR-29 | P1: Email | Design | Pending |
| DOOR-30 | P1: Email | Design | Pending |
| DOOR-31 | P1: Email | Design | Pending |
| DOOR-32 | P1: Email | Design | Pending |
| DOOR-33 | P1: Email | Design | Pending |
| DOOR-34 | P1: Email | Design | Pending |

**Coverage:** 34 total, 0 mapped to tasks, 34 unmapped.

---

## Success Criteria

- [ ] A second API worker shares limiter state via Redis.
- [ ] Ninth Ask in a UTC day is 429 and the thread remains.
- [ ] Third owned upload is 403; sample still readable.
- [ ] Register without invite is 403; one-use invite works once.
- [ ] Account deletion removes the caller's objects and leaves the sample.
- [ ] Fake EmailPort receives verify and reset messages; unknown reset is 204.
