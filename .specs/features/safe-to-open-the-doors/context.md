# safe-to-open-the-doors Context

**Gathered:** 2026-09-05
**Spec:** `.specs/features/safe-to-open-the-doors/spec.md`
**Status:** Ready for execute

---

## Feature Boundary

RFC-0007 Cycle F / Bet 6 as one ship-cycle PR: Redis limiter keyed by `user_id` on expensive routes and by trusted-proxy client IP on auth; per-user daily AI-spend ledger plus operator kill switch; source count/bytes quotas and one in-flight ingest; invite codes plus Turnstile (when secret set) plus disposable-domain block; ToS/privacy/copyright pages with a DMCA contact; account deletion that removes MinIO objects and cascades Postgres; `EmailPort` for verify and password reset.

Not in this PR: RFC Cycle G; guest Ask; billing/checkout; EU representative; ZDR as a blocker; publisher hash-scanning; Kubernetes; opt-in due digest; new generation/embedding providers; ESP SDKs.

---

## Implementation Decisions

### ROADMAP F–G split

- **Chosen:** This PR is RFC letter F / Bet 6 only. ROADMAP's combined F–G row splits into `safe-to-open-the-doors` (F) and a still-unstarted Bet 7 row.
- **Why recommend:** Cycle G needs an ADR-0020 amendment and judge-gated model work. Mixing it with auth/quota would hide the registration gate.
- **Why-not (rejected):** One PR that also ships Cycle G — larger blast radius, two bets, one review.

### Turnstile (RFC open question 3)

- **Options:**
  1. Invite XOR captcha (rq09): invite code only until registration is genuinely open.
  2. Invite **and** Turnstile when `LEARNY_TURNSTILE_SECRET` is set **and** disposable-domain blocking.
- **Chosen:** Option 2.
- **Why recommend:** The RFC Cycle F body and this ship-cycle WHAT list Turnstile as the opening bot brake. Invite codes leak in screenshots and chat; the form still needs a bot check. An empty secret skips siteverify so CI and self-host stay network-free. httpx siteverify behind a Learny port is not a generation/embedding SDK.
- **Why-not (rejected option 1):** Drops the RFC opening step while the hosted instance is still the thing being gated. Cloudflare is a US subprocessor (name it on `/privacy`); that is accepted cost, not a reason to skip the check.
- **Why-not (escalation):** This does not add a new gen/embed provider, does not start Cycle G, and does not open guest Ask.

### Email provider

- **Chosen:** Learny `EmailPort` (send). Adapters: SMTP from settings for deployed mail; in-memory/log adapter for tests and local default. No Resend/Postmark/SES SDK.
- **Why recommend:** Matches existing port/adapter shape; stdlib SMTP is enough the day the form opens.
- **Why-not:** New ESP SDK (ADR-0007).

### Verify vs invite

- **Chosen:** A valid invite mints a session immediately. Verification email is sent. Invited users may use Ask/upload before `email_verified_at` is set.
- **Why recommend:** Cycle E's first session must still work on invite day.
- **Why-not:** Verify-before-session for invited users.

### Due digest (AD-304)

- **Chosen:** Out of this PR. EmailPort exists; the digest is a later small cycle once mail is proven.
- **Why recommend:** Deletion, spend, and invite already fill the letter.
- **Why-not:** Shipping the RFC-004 thaw digest in the same PR.

### Spend meter

- **Chosen:** Postgres daily USD ledger (micros) plus integer Free-tier counters: 8 Ask/day, 1 Teach session/day, 2 owned sources, **256 MiB** stored bytes, 1 in-flight ingest. Hard stop with honest copy. Operator kill switch is a settings flag that 503s AI routes. Do not name this ledger `SpendPort` (Cycle G owns thinking-token SpendPort).
- **Why recommend:** 256 MiB fits two 100 MiB PDFs plus margin. USD ledger is the farmed-account brake; integers are the honest Free shape.
- **Why-not:** Credits/SKU explosion. LiteLLM in front of GenerationPort. **80 MiB** stored quota (blocks a legal 100 MiB PDF).

### Invite flag

- **Chosen:** `LEARNY_INVITE_REQUIRED` defaults false so self-host and CI keep existing register tests. Production `.env.example` sets it true.
- **Why-not:** Always-on invite in every environment.

### Limiter keys

- **Chosen:** Redis fixed-window via the existing `RateLimiter` protocol. Auth: trusted-proxy `X-Real-IP`. Expensive authenticated routes: `user_id`. Caddy stamps `X-Real-IP`; Next strips inbound `X-Forwarded-For`. Redis down → 503.
- **Why-not:** Process-local IP buckets. Read the full XFF chain.

### Deletion

- **Chosen:** Delete caller-owned keys then the user row (CASCADE). Sample is not deleted. Storage failure must not delete the user (502).
- **Why-not:** Soft-delete. Leaving MinIO orphans.

### Legal copy

- **Chosen:** Static committed pages. No EU representative. Privacy names OpenAI, Anthropic, and Cloudflare (Turnstile) as subprocessors. No ZDR claim.
- **Why-not:** Generated policy; claiming Anthropic ZDR as a launch blocker.

### Agent's Discretion

- Exact 429/403/400 copy as long as the three honest strings above are pinned and reset does not leak whether an email exists.
- Disposable-domain list as a frozen committed set plus alias allow-list.
- SMTP via stdlib `smtplib` in a thin adapter.
- Invite CLI shape (`learny invite mint`).
- Turnstile widget via Cloudflare's hosted script, not an npm SDK.

### Declined / Undiscussed Gray Areas → Assumptions

Ship-cycle auto-decision (user away, standing auto). Pace: Guided defaults recorded here. No option required escalating MVP beyond Cycle F.

---

## Specific References

- RFC-0007 Cycle F body; conflict 2 (guest Ask after F); open question 3 (Turnstile day one — decided AND).
- rq09 Cycles A–D; rq10 Free caps; rq15 Cycle 1 ledger shape.
- AD-007 CSRF/Origin; AD-017 same-origin proxy; AD-029 in-memory limiter; AD-283 MinIO GC; AD-304 digest; AD-324..AD-333.
- `rate_limit.py` already implements `RateLimiter.hit` and documents the proxy-IP collapse. `deploy/Caddyfile` does not yet stamp `X-Real-IP`. `StoragePort` is put/get only. Alembic head is `0023_starter_quiz_origin` (next file `0024`).

---

## Deferred Ideas

- Opt-in due digest.
- Guest capped Ask.
- RFC Cycle G spend optimizations and fallback adapter.
- Requiring `email_verified_at` before upload once registration is public.
- Official Cloudflare SDK (not needed; httpx + script tag).
