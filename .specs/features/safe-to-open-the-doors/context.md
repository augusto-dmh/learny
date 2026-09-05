# safe-to-open-the-doors Context

**Gathered:** 2026-09-05
**Spec:** `.specs/features/safe-to-open-the-doors/spec.md`
**Status:** Ready for execute

---

## Feature Boundary

RFC-0007 Cycle F / Bet 6 as one ship-cycle PR: Redis limiter keyed by `user_id` on expensive routes and by trusted-proxy client IP on auth; per-user daily AI-spend ledger plus operator kill switch; source count/bytes quotas and one in-flight ingest; invite codes plus disposable-domain block; ToS/privacy/copyright pages with a DMCA contact; account deletion that removes MinIO objects and cascades Postgres; `EmailPort` for verify and password reset.

Not in this PR: RFC Cycle G; Turnstile; guest Ask; billing/checkout; EU representative; ZDR; publisher hash-scanning; Kubernetes; opt-in due digest.

---

## Implementation Decisions

### ROADMAP F–G split

- **Chosen:** This PR is RFC letter F / Bet 6 only. ROADMAP's combined `*(Bets 6–7)*` row splits into `safe-to-open-the-doors` (F) and a still-unstarted Bet 7 row.
- **Rejected:** One PR that also ships Cycle G. G needs an ADR-0020 amendment and judge-gated model work; mixing it with auth/quota would hide the registration gate.

### Turnstile

- **Chosen:** Invite code when `LEARNY_INVITE_REQUIRED` is true. No Cloudflare Turnstile widget or siteverify call.
- **Rejected:** Turnstile as the opening bot brake (RFC bullet). Why-not: third-party US subprocessor and a widget on the only signup path while the hosted instance stays invite-only. rq09 Cycle C is invite XOR captcha; invite wins until registration is genuinely open. A later uncommitted draft that added Turnstile was reverted to this decision (AD-325).

### Email provider

- **Chosen:** Learny `EmailPort` (send). Adapters: SMTP from settings for deployed mail; in-memory/log adapter for tests and local default. No Resend/Postmark/SES SDK.
- **Rejected:** New ESP SDK (ADR-0007).

### Verify vs invite

- **Chosen:** A valid invite mints a session immediately. Verification email is sent. Invited users may use Ask/upload before `email_verified_at` is set.
- **Rejected:** Verify-before-session for invited users (blocks the first session Cycle E just shipped).

### Due digest (AD-304)

- **Chosen:** Out of this PR. EmailPort exists; the digest is a later small cycle once mail is proven.
- **Rejected:** Shipping the RFC-004 thaw digest in the same PR as deletion and spend caps.

### Spend meter

- **Chosen:** Postgres daily USD ledger (micros) plus integer Free-tier counters: 8 Ask/day, 1 Teach session/day, 2 owned sources, **256 MiB** stored bytes, 1 in-flight ingest. Hard stop with honest copy. Operator kill switch is a settings flag that 503s AI routes.
- **Rejected:** Credits/SKU explosion. LiteLLM in front of GenerationPort. **80 MiB** stored quota (blocks a legal 100 MiB PDF). AD-329 updated.

### Invite flag

- **Chosen:** `LEARNY_INVITE_REQUIRED` defaults false so self-host and CI keep existing register tests. Production `.env.example` sets it true.
- **Rejected:** Always-on invite in every environment (would break hundreds of register tests).

### Limiter keys

- **Chosen:** Redis fixed-window via the existing `RateLimiter` protocol. Auth: trusted-proxy `X-Real-IP`. Expensive authenticated routes: `user_id`. Caddy stamps `X-Real-IP`; Next strips inbound `X-Forwarded-For`. Redis down → 503.
- **Rejected:** Process-local IP buckets. Read the full XFF chain.

### Deletion

- **Chosen:** Delete caller-owned keys then the user row (CASCADE). Sample is not deleted. Storage failure must not delete the user (502).
- **Rejected:** Soft-delete. Leaving MinIO orphans.

### Agent's Discretion

- Exact 429/403 copy as long as it is honest and does not leak whether an email exists on reset.
- Disposable-domain list as a frozen committed set plus alias allow-list.
- SMTP via stdlib `smtplib` in a thin adapter.
- Invite CLI shape (`learny invite mint`).

### Declined / Undiscussed Gray Areas → Assumptions

Ship-cycle auto-decision (user away, standing auto). Turnstile was not escalated: RFC lists it, rq09 XOR plus AD-325 already chose invite-only. Cloudflare siteverify is an external US dependency; it stays out.

---

## Specific References

- RFC-0007 Cycle F; conflict 2 (guest Ask after F).
- rq09 Cycles A–D; rq10 Free caps; rq15 Cycle 1 ledger shape.
- AD-007 CSRF/Origin; AD-017 same-origin proxy; AD-029 in-memory limiter; AD-283 MinIO GC; AD-304 digest; AD-324..AD-333.
- `rate_limit.py` already implements `RateLimiter.hit`. `deploy/Caddyfile` does not yet stamp `X-Real-IP`.

---

## Deferred Ideas

- Turnstile when invite-only lifts.
- Opt-in due digest.
- Guest capped Ask.
- RFC Cycle G spend optimizations and fallback adapter.
- Requiring `email_verified_at` before upload once registration is public.
