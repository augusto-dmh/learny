# safe-to-open-the-doors Context

**Gathered:** 2026-09-05
**Spec:** `.specs/features/safe-to-open-the-doors/spec.md`
**Status:** Ready for execute

---

## Feature Boundary

RFC-0007 Cycle F / Bet 6 as one ship-cycle PR: Redis limiter keyed by `user_id` on expensive routes and by trusted-proxy client IP on auth; per-user daily AI-spend ledger plus operator kill switch; source count/bytes quotas and one in-flight ingest; invite codes plus disposable-domain block; ToS/privacy/copyright pages with a DMCA contact; account deletion that removes MinIO objects and cascades Postgres; `EmailPort` for verify and password reset.

Not in this PR: RFC Cycle G (cheaper intelligence, OpenAI-compatible fallback, ADR-0020 amendment); Turnstile; guest Ask; billing/checkout; EU representative; ZDR; publisher hash-scanning; Kubernetes; opt-in due digest.

---

## Implementation Decisions

### ROADMAP F–G split

- **Chosen:** This PR is RFC letter F / Bet 6 only. ROADMAP's combined `*(Bets 6–7)*` row splits into `safe-to-open-the-doors` (F) and a still-unstarted Bet 7 row.
- **Rejected:** One PR that also ships Cycle G. G needs an ADR-0020 amendment and judge-gated model work; mixing it with auth/quota would hide the registration gate.

### Turnstile

- **Chosen:** Invite code required at register. No Cloudflare Turnstile widget or siteverify call.
- **Rejected:** Turnstile as the opening bot brake (RFC bullet). Why-not: third-party US subprocessor and a widget on the only signup path while the hosted instance stays invite-only. rq09 Cycle C is invite XOR Turnstile; invite wins until registration is genuinely open (RFC action item).

### Email provider

- **Chosen:** Learny `EmailPort` (send). Adapters: SMTP from settings for deployed mail; in-memory/log adapter for tests and local default. No Resend/Postmark/SES SDK.
- **Rejected:** New ESP SDK (ADR-0007). EmailPort is still live the day the form opens: verify and reset tokens are hashed like sessions and actually sent through the port.

### Verify vs invite

- **Chosen:** A valid invite mints a session immediately. Verification email is sent. Invited users may use Ask/upload before `email_verified_at` is set. A later setting can require verification once registration is public.
- **Rejected:** Verify-before-session for invited users (blocks the first session Cycle E just shipped). Open register without invite (rq09: no).

### Due digest (AD-304)

- **Chosen:** Out of this PR. EmailPort exists; the digest is a later small cycle once mail is proven.
- **Rejected:** Shipping the RFC-004 thaw digest in the same PR as deletion and spend caps.

### Spend meter

- **Chosen:** Postgres daily USD ledger (micros) plus integer Free-tier counters from rq10: 8 Ask/day, 1 Teach session/day, 2 owned sources, 80 MiB stored bytes, 1 in-flight ingest. Hard stop with honest copy. Operator kill switch is a settings flag that 503s AI routes.
- **Rejected:** Credits/SKU explosion (rq10 fallback). LiteLLM in front of GenerationPort (ADR-0009). USD-only with no source quota (disk still unbounded).

### Limiter keys

- **Chosen:** Redis fixed-window via the existing `RateLimiter` protocol. Auth/register/login: trusted-proxy `X-Real-IP` (strip inbound `X-Forwarded-For` from the browser). Authenticated expensive routes (Ask/Teach turns, quiz deck, upload, ingest start): `user_id`. Next.js proxy sets `X-Real-IP` from the hop Caddy sent, never from a client-supplied chain.
- **Rejected:** Keep process-local IP buckets (rq09 documented hole). Read the full XFF chain.

### Deletion

- **Chosen:** `StoragePort.delete_prefix` (or delete listed keys) then `DELETE /api/auth/account` which deletes the user row (existing CASCADE). Sample objects and the sample source are not owned by the caller and are not deleted. Idempotent: a second delete is 401.
- **Rejected:** Soft-delete. Leaving MinIO orphans (AD-283 parked this letter).

### Agent's Discretion

- Exact 429/403 copy as long as it is honest (come back tomorrow / invite required / spend exhausted) and does not leak whether an email exists on reset.
- Disposable-domain list source (frozen file vs small Python set) with alias allow-list (`duck.com`, iCloud Hide My Email, SimpleLogin).
- SMTP library: stdlib `smtplib` in a thin adapter is enough; no new SDK.
- Invite CLI shape (`learny invite mint`).

### Declined / Undiscussed Gray Areas → Assumptions

Ship-cycle auto-decision (Quick pace; user away, standing auto). Every spec Assumptions row is the signed-off default. Turnstile was not escalated: RFC action item plus rq09 XOR already recommend invite-only until open registration. Email adapter was not escalated: port + SMTP is the ADR-0007-compatible recommendation; an ESP SDK would need its own ADR.

---

## Specific References

- RFC-0007 Cycle F; conflict 2 (guest Ask after F); exclusions (no billing, no new request-path SDK).
- rq09 Cycles A–D checklist; rq10 Free caps; rq15 Cycle 1 ledger shape.
- AD-007 CSRF/Origin; AD-017 same-origin proxy; AD-029 in-memory limiter limitation; AD-283 MinIO GC; AD-304 digest deferred onto EmailPort; ADR-0007/0009 ports.
- `rate_limit.py` already implements `RateLimiter.hit` so Redis is a wiring change plus key policy.

---

## Deferred Ideas

- Turnstile when invite-only lifts.
- Opt-in due digest.
- Guest capped Ask.
- RFC Cycle G spend optimizations and fallback adapter.
- EU representative / ZDR.
