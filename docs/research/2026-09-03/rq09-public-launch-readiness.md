# RQ09 — Public-launch readiness

*Fleet research, 2026-09-03. Maps operational, legal, and trust work that must be true before strangers can register on a hosted Learny. Not legal advice; counsel should review ToS, privacy, and copyright wording before go-live.*

Learny today: FastAPI + Celery + PostgreSQL/pgvector + MinIO, Next.js same-origin proxy, one VPS Compose stack behind Caddy (ADR-0008/0023). Auth is backend-owned HttpOnly cookies, CSRF, Argon2id, owner-scoped 404s (ADR-0015). AI spend is OpenAI embeddings + Anthropic Claude generation (ADR-0019/0020). There is **no public sharing of book content**; recommendations keep it that way.

---

## TL;DR

- **Do not open registration on the current abuse surface.** Rate limits exist but are process-local, keyed by the Next.js proxy’s IP, and duplicated per uvicorn worker (`--workers ${LEARNY_API_WORKERS:-2}`). There is no per-user quota, no daily AI-spend cap, no email verification, no captcha, no source-count limit, and `POST /api/sources/{id}/ingestion` is unthrottled.
- **The cost bomb is generation, not embeddings.** ~$0.04/book to embed (`text-embedding-3-large@1536`); ~$0.02–0.03 per cited answer on Sonnet 4.6. Uncapped Q&A/teach/quiz at even 100 daily-active users is a four-figure monthly bill; one scripted account can spend it in an afternoon.
- **Copyright is defensible only as a private library.** Readwise, BookFusion, and Google Play Books uploads all use the same shape: user warrants they have rights, files stay private, DMCA/notice-and-takedown exists, no public distribution of uploaded books. Learny must not add sharing. “I own the EPUB” is a ToS allocation of risk, not a settled exception under Brazil’s Lei 9.610/98 Art. 46, II (private copy = *pequenos trechos*).
- **Privacy is LGPD-mandatory (operator in Brazil) and GDPR-conditional.** GDPR Art. 3(2) fires if Learny *offers* the service to people in the EU. Open registration + English/Portuguese marketing is enough. Standard API traffic is **not** used for training; default retention is ~30 days (OpenAI abuse logs) and ~7 days (Anthropic API logs). Zero-data-retention is sales-gated, not a launch prerequisite — disclose it.
- **Cheapest honest launch is invite-only + Redis per-user caps + legal pages + account deletion**, still on Compose. Full open signup wants an `EmailPort` (verification + password reset) that RFC-005 correctly parked. Opening the form without those is how the VPS and the Anthropic invoice die.

---

## 0. What the stack actually has

| Control | Today | Gap vs public multi-tenant |
|---|---|---|
| Auth cookies / CSRF / Origin / Argon2id / owner 404s | Shipped (ADR-0015, README security model) | Password reset and email verification were explicit follow-ups in ADR-0015; still unbuilt. RFC-005 listed them **out** pending public abuse risk. |
| Rate limits | `InMemoryFixedWindowRateLimiter` (10 / 60s default) on auth, upload, conversations, quiz, notes | Documented KNOWN LIMITATION: `request.client.host` is the Next.js proxy for every browser (`rate_limit.py`). Prod API is **two uvicorn workers**, so counters are not even shared across processes. Protocol is already Redis-swappable; nothing wires it. |
| Upload size | 50 MiB EPUB / 100 MiB PDF; 500 MiB uncompressed EPUB | No per-user **count** or **bytes-stored** quota. |
| Ingestion fairness | Partial unique index: one active job **per source**; PDF isolated (`ingest-pdf`, `--concurrency 1`, `mem_limit: 4g`) | Default `celery` queue is FIFO. One user can enqueue many sources. `POST .../ingestion` has **no** `rate_limit_*` (called out as a cheap follow-up in worker-foundation design). |
| AI spend | Provider keys on the VPS; no ledger | No token accounting, no daily cap, no kill-switch per user. |
| Bot / signup | Email+password → instant session | No verification, captcha, disposable-email check, invite gate, or `EmailPort`. |
| Account deletion / DSAR | `ON DELETE CASCADE` on `users.id` FKs; vault export for notes | No `DELETE /api/auth/account`. `StoragePort` is put/get only — MinIO objects would orphan. |
| Legal / T&S | None in the product | No ToS, privacy policy, subprocessor list, DMCA/notice page, or breach runbook. |
| Edge | Caddyfile is `encode` + `reverse_proxy web:3000` | No edge rate limit. Stock Caddy image has no `rate_limit` module (would need `xcaddy` + [mholt/caddy-ratelimit](https://github.com/mholt/caddy-ratelimit), not official). |
| Ops | Nightly dump + WAL/PITR + offsite mirror (ADR-0024); Netdata on loopback | Sized for author-scale (~8 GB RAM). Backups exist; abuse/cost do not. |

---

## 1. Abuse and cost control

### 1.1 Rate limits must become per-user (and actually see the client)

The limiter protocol is the right shape (`hit(key) → (allowed, retry_after)`, 429 + `Retry-After`). The key is wrong for production:

1. Browser traffic is Caddy → Next.js → FastAPI. FastAPI’s peer is `web`, so every stranger shares one bucket — a single actor 429s **everyone** on that route, and a distributed botnet is invisible. The file already says to use a proxy-set `X-Real-IP`, never the client-supplied `X-Forwarded-For` chain ([FastAPI-Redis guidance](https://redis.github.io/fastapi-redis-sdk/guide/rate-limiting/); same spoofing warning).
2. In-memory state dies across the two prod uvicorn workers and on restart. Redis is already in Compose as the Celery broker (ADR-0014). A Redis adapter is the wiring change the module was written for — not a new SDK.
3. Authenticated expensive routes (turns, stream, quiz deck, note-card suggest) must key on **`user_id`**, not IP. IP remains for `register`/`login` only.

**Do not** rebuild Caddy with a third-party rate-limit plugin as the primary control. ADR-0023 pins a stock Caddy alpine image; `xcaddy` forks that. Edge IP limits are a later belt; they cannot express per-user AI budgets.

Suggested starting numbers (tune after a week of logs): register/login **5 / 15 min / IP**; upload **10 / hour / user**; conversation turns (incl. stream) **30 / hour / user**; quiz-deck POST **3 / hour / user**; ingestion start **6 / hour / user**.

### 1.2 Daily AI-spend caps (the actual launch blocker)

Embeddings are cheap: prior Learny research priced `text-embedding-3-large@1536` at **~$0.04 per typical book** ([embeddings.md](../2026-07-12/embeddings.md); [OpenAI embeddings pricing](https://developers.openai.com/api/docs/models/text-embedding-3-large)). Generation is not: Sonnet 4.6 is **$3 / $15 per MTok** ([Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing)); cited Q&A was estimated **~$0.0225/answer** and a 10-turn teach **~$0.12** ([anthropic-generation.md](../2026-07-12/anthropic-generation.md)).

Worked example at 500 registered users, 100 daily-active, no caps: 20 answers/user/day × $0.0225 × 100 ≈ **$45/day generation** (~$1.3k/month) *if everyone is polite*. A single script hitting `/turns/stream` as fast as the (broken) limiter allows can exceed that in hours. Quiz-deck generation and note-card suggest are the same Anthropic port.

**What to build:** a Postgres ledger (`user_id`, `day`, `embed_tokens`, `gen_input_tokens`, `gen_output_tokens`, `usd_micros`) written after each adapter call (and reserved *before* the call with a conservative estimate). Hard fail with 429/402-style JSON when the daily USD cap is hit. Caps live in settings (`LEARNY_USER_DAILY_AI_USD_MICROS`), default tight (e.g. **$0.50–1.00/user/day** ≈ 20–40 answers, or a handful of quiz decks). Operator kill-switch: `LEARNY_PUBLIC_AI_ENABLED=false`.

Keep providers behind existing ports (ADR-0007). The ledger is Learny-owned, not an OpenAI/Anthropic billing SDK.

### 1.3 Upload size/count quotas

Byte caps already exist (50/100 MiB). Missing is **how many** and **how much stored**:

- Max sources per user (start at **20**; Google Play Books historically allowed 1,000 personal uploads — that is a hyperscaler number, not a 40–80 GB VPS number).
- Max stored bytes per user (start at **1–2 GiB**).
- Reject over-quota with 413/409 before `put_object`.

Without count quotas, the PDF worker (`concurrency=1`, 30 min time limit) is a 500-user bottleneck even if bytes are capped.

### 1.4 Ingestion queue fairness

Today: one active job per *source* (ING-03), PDF isolated from EPUB/embed/quiz, `prefetch=1` + `acks_late` (good for long tasks; [Celery prefetch docs](https://docs.celeryq.dev/en/v5.5.3/userguide/optimizing.html)). Redis+Celery FIFO still means user A’s 40 EPUBs occupy the default worker while user B waits. Per-user Celery queues do not scale (queue explosion; [Hatchet on Celery fairness](https://hatchet.run/blog/problems-with-celery)).

**Cheap fairness that fits Postgres-as-SoT:** refuse `StartIngestion` when the user already has **N** jobs in `{queued, running}` (N=1 or 2). That is a `COUNT(*)` in the same transaction as the partial unique index, not a new broker. Optional later: split `celery` into `ingest-epub` vs `embed` vs `quiz` queues so a quiz-deck job is not stuck behind a book parse — still Compose, still one worker image, extra `--queues` services.

### 1.5 Bot / scripted-signup defenses

Open `POST /api/auth/register` with no proof-of-human and no mailbox is a credit-card for the Anthropic key.

| Defense | Fit | Trade-off |
|---|---|---|
| **Invite-only** (code in Postgres, ADR-0012/0015 already reserved the door) | Best first public surface. No email. Caps blast radius to people you chose. | Growth-hostile; operational toil handing codes. |
| **Email verification** | Real anti-disposable once mail is delivered. Needs Learny-owned `EmailPort` + provider (Resend/Postmark/SES) + ADR. RFC-005 parked this for that reason. | Largest net-new dependency. Password reset rides the same port. |
| **Disposable-domain block** | Local list (`mailchecker` / similar) at register, **allow** privacy aliases (SimpleLogin, `duck.com`, iCloud Hide My Email) — [don't conflate aliases with throwaways](https://emailalias.io/blog/how-to-detect-disposable-emails/). | Lists rot; determined attackers buy aged domains. Defense in depth, not a gate. |
| **Cloudflare Turnstile** | Invisible, free, no Google ads graph, no third-party tracking cookies. Server-verify the token in FastAPI on register (and maybe login). [Turnstile vs hCaptcha 2026](https://prosopo.io/blog/hcaptcha-vs-cloudflare-turnstile/). | US processor (IP + browser signals); disclose in privacy policy. hCaptcha catches more farms but shows puzzles and is worse UX for a learning app. reCAPTCHA is the worst privacy fit. |
| **hCaptcha** | Stronger catch-rate, Enterprise EU residency. | Friction on every signup; paid cliff; still US control plane on free/pro. |

**Recommendation:** invite-only **or** Turnstile+disposable-block to open a waitlist; do not offer unrestricted registration until `EmailPort` + verification + password reset exist. Turnstile is a widget + one verify call, not a new AI SDK (ADR-0019/0020 stay closed).

---

## 2. Copyright reality

Learny stores full EPUB/PDF bytes in MinIO, derived corpus + embeddings in Postgres, and sends **retrieved passages** to Anthropic (and chunk text to OpenAI embeddings). That is reproduction and (for generation) the making of a derivative. There is no public corpus, no shared library, no “bonus highlights from other people’s books.” Keep it that way.

### 2.1 What comparable services actually do

- **Readwise / Reader** — users may upload personal PDFs/EPUBs; DRM-store books are refused; “if you upload a PDF to Reader, no one will ever see that PDF but you” ([privacy FAQ](https://docs.readwise.io/faqs/privacy)). ToS: user warrants rights to User Content; no upload of infringing files; **full DMCA agent, takedown, counter-notice, repeat-infringer termination** ([readwise.io/tos](https://readwise.io/tos), Copyright Complaints). They also take a broad license to operate the service — Learny should take the *narrower* license: host, parse, embed, retrieve, generate **for that user only**, revoke on deletion.
- **BookFusion** — DRM-free personal library; they state they do not scan private libraries; **public** sharing is the line where they assume the user owns distribution rights ([MobileRead clarification](https://www.mobileread.com/forums/showthread.php?p=4337254)). Copyright policy is notice-and-takedown to `legal@bookfusion.com` ([copyright page](https://www.bookfusion.com/copyright)).
- **Google Play Books uploads** — personal PDF/EPUB library, historically capped (~1,000 files), **private to the Google account**, DRM-free uploads only ([Ebook Friendly](https://ebookfriendly.com/how-to-upload-own-ebooks-to-google-play/)). Publisher/partner policies are a different product (store distribution).

Pattern: **private locker + user warranty + notice-and-takedown + no public copies.** None of them claim “fair use / private copy” as a published legal theory covering cloud OCR + LLM. They contract the risk to the user and keep distribution off the table.

### 2.2 Private-use defensibility (Brazil + US)

- **Brazil Lei 9.610/98 Art. 46, II** permits reproduction of *pequenos trechos* in a single copy for the copier’s private, non-profit use — not a full ebook into a third-party cloud ([Copyright Atlas / Brazil](http://www.copyrightatlas.com/details?slug=br&type=country); [Planalto L9610](https://www.planalto.gov.br/ccivil_03/leis/l9610.htm)). Penal Code Art. 184 §4 excludes *criminal* liability for a single private copy without profit ([Wikipedia summary of the 2003 amendment](https://en.wikipedia.org/wiki/Copyright_law_of_Brazil)) — that is not a civil safe harbor for a hosted AI product.
- **US**: personal-use copies of works you bought are a common consumer practice; they are not a clean 17 U.S.C. §107 fair-use slam dunk once a commercial service reproduces the whole work and sends passages to a model. Safe harbor for *user-uploaded* infringement, if it applies at all, is **§512(c) hosting**, not “users are allowed to upload books.”

Learny’s honest position in ToS: you may upload works you have the right to use privately; Learny does not grant you extra copyright; Learny will not publish, sell, or share the file; Learny will disable access on a valid notice. Do **not** add social sharing, public shelves, or “export this chapter as a link.” Vault/Anki export is the user’s own notes and cards — keep book body out of any shared artifact.

### 2.3 DMCA / notice-and-takedown (must-have pages, even for a Brazil operator)

**US 17 U.S.C. §512** ([Copyright Office 512 resources](https://www.copyright.gov/512/index.html); [DMCA agent directory](https://copyright.gov/dmca-directory/)): to claim hosting safe harbor you need (1) a designated agent registered with the Copyright Office (~$6, renew every 3 years), (2) the same contact **on the website**, (3) expeditious removal of identified material, (4) a counter-notice path, (5) a repeat-infringer policy. §512 does not require scanning private libraries. A Brazil-only operator still meets US users and US providers (OpenAI, Anthropic); registering an agent is cheap insurance.

**Brazil:** copyright already sat outside Marco Civil Art. 19’s old court-order-only rule (case law notice-and-takedown). The STF’s 2025 Art. 19 decision moved *general* intermediary liability toward notice-and-takedown ([GNI explainer](https://globalnetworkinitiative.org/from-shield-to-scrutiny-brazils-supreme-court-redefines-platform-liability/); [Licks](https://techregulationbr.lickslegal.com/publicacoes/brazilian-supreme-court-concludes-trial-reshaping-osps-civil-liability-for-third-party-content)). A published `legal@` / `/copyright` flow that deletes or disables the named source (DB row + MinIO object + derived corpus) is the operational requirement, not a court-ticket queue.

**Takedown flow mapped to Learny:** public form/email → operator verifies the §512 elements → `DELETE` source for that user (needs the missing delete-source/account path) → confirm to complainant. No automated “hash every EPUB against a publisher list” at this scale. Repeat infringer = terminate account (CASCADE + object delete).

---

## 3. Privacy (GDPR + LGPD)

Augusto operates from Brazil. **LGPD (Lei 13.709/2018) applies.** GDPR applies **if** Learny offers the service to people in the EU (Art. 3(2) — payment not required). English UI + open signup is commonly treated as an offer; a Brazil-only waitlist with no EU targeting is a weaker Art. 3(2) case. There is **no SME exemption** from territorial scope ([Legiscope](https://www.legiscope.com/blog/gdpr-applies-outside-eu.html)).

### 3.1 Data the product already holds

Account email; Argon2id hash (not the password); session hashes; uploaded books; canonical corpus; embeddings; conversations/turns; quiz items + FSRS state; notes/highlights; reading progress; study heatmap. Logs: `user_id` + redaction filter (README). Subprocessors on the live AI path: **OpenAI** (chunk text), **Anthropic** (retrieved passages + user questions). VPS host + MinIO (or future R2) store bytes.

### 3.2 Rights you must actually implement

| Right | LGPD / GDPR | Learny mapping |
|---|---|---|
| Access / portability | LGPD Art. 18 V; GDPR Art. 15/20 | Extend beyond `GET /api/export/vault`: JSON (or zip) of account, sources metadata, notes, conversations, review log. Original EPUB/PDF bytes are user-supplied — include them or a re-download of stored objects. 15 calendar days is a reasonable ATPP-scale SLA. |
| Deletion | LGPD Art. 18 VI; GDPR Art. 17 | `DELETE /api/auth/account` (auth + CSRF): delete MinIO keys **then** `DELETE FROM users` (CASCADE). Today `StoragePort` has no `delete_object` — add it. Sessions die with the row. |
| Correction | Art. 18 I / GDPR 16 | Email change can wait; password change needs reset or authenticated update. |
| Information | LGPD Art. 9; GDPR Art. 13–14 | Privacy policy (below). |

**DPO / Encarregado:** ANPD Res. 2/2022 (ATPP) can exempt small agents from appointing an encarregado **if** a public contact channel exists and processing is not high-risk ([Machado Meyer](https://www.machadomeyer.com.br/pt/inteligencia-juridica/publicacoes-ij/direito-digital/empresas-de-pequeno-porte-podem-ser-dispensadas-de-ter-dpo)). GDPR Art. 27 EU representative is **not** excused by size: the “occasional” exemption does not fit an always-on SaaS ([EDPB-aligned explainers](https://www.engagecompliance.co/do-i-need-an-eu-representative)). If you target the EU, budget a representative service; if you do not, say so and don’t market there.

**Breach:** GDPR Art. 33 = **72 hours** to a supervisory authority when risk exists. LGPD + ANPD Res. 15/2024 = notify ANPD in **three business days** (high-risk). Need a one-page ops runbook: rotate keys, invalidate sessions (`DELETE FROM sessions`), notify. ADR-0024 backups are the restore half; they are not an incident plan.

### 3.3 Privacy policy contents (minimum)

Identity and contact (and Encarregado/EU representative if designated); what data; purposes; **legal bases** (LGPD has more than GDPR — typically *execução de contrato* / contract for the account+library, *legítimo interesse* for security logs, consent only if you ever add non-essential analytics); retention; sharing; international transfers (US subprocessors — OpenAI/Anthropic DPAs + SCCs; Brazil Res. 19/2024 SCCs if you need a Brazil-specific instrument); user rights and how to exercise them; cookies (session is HttpOnly essential — not a marketing pixel); security overview; children’s exclusion (do not onboard under-13 / under-18 without a separate cycle — ECA Digital Lei 15.211/2025); subprocessor list with role + region.

### 3.4 Subprocessors: OpenAI and Anthropic (2026)

**OpenAI API** ([Data controls](https://developers.openai.com/api/docs/guides/your-data); [Business data](https://openai.com/business-data/)): **not used for training by default.** `/v1/embeddings` (Learny’s path): no training, **30-day abuse-monitoring retention**, no application-state store, **ZDR-eligible**. ZDR is **approval + sales**, not a dashboard toggle. Default Learny = 30-day provider-side logs of chunk text.

**Anthropic API** ([API and data retention](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention); [Privacy Center](https://privacy.claude.com/en/articles/7996875-can-you-delete-data-that-i-sent-via-api)): commercial API inputs/outputs **not used for training** unless a contrary agreement. ZDR = no prompts/responses at rest after the response; **sales-enable per organization**. Messages API is the ZDR-eligible path Learny uses. Some “Covered Models” (Fable/Mythos 5.x) **require 30-day retention and reject ZDR** — stay on Sonnet 4.6 / Haiku 4.5 as locked. Default retention outside ZDR: commercial policy (7-day API logs widely reported after the 2025 cut; confirm the live commercial retention page at publish time). Flagged abuse content can be retained **even under ZDR**.

**Launch implication:** do not block launch on ZDR. Do: (1) sign both vendors’ DPAs, (2) name them on `/privacy` with “not used for training; retained up to N days for abuse monitoring unless ZDR is granted,” (3) never send more book text than retrieval already sends, (4) never log prompt bodies in Learny’s own JSON logs (redaction already exists — keep it).

---

## 4. Trust & safety minimums

- **Terms of service:** account rules; “you warrant rights to uploads”; narrow license to Learny; no sharing; acceptable use (no malware, no scraping others’ accounts, no resale of generated output as the book); AI-output disclaimer (answers can be wrong; citations are the product); limitation of liability; Brazilian law + forum (or a stated alternative); DMCA/notice pointer; termination including repeat copyright infringement.
- **Account deletion:** in-app, not “email the founder.” Same cascade as §3. Confirm MinIO empty for that prefix. 15-day processing is fine if the button enqueues a worker; better if synchronous for a small library.
- **Password reset:** blocked on `EmailPort`. Until then, invite-only + “lost password → operator deletes session and issues a new invite” is ugly but honest. Do not ship open registration without reset.
- **Breach readiness:** session wipe SQL, provider-key rotation, user email (needs `EmailPort` or a status page), ANPD/GDPR clocks, restore from ADR-0024. Practice once.
- **Minors / T&S:** block under-13 in ToS; don’t build UGC between users (there is none). No public book quotes on a landing page that aren’t your rights.
- **Operator hygiene already good:** Caddy-only 80/443, secrets on the VPS, log redaction, owner 404s. Don’t punch Netdata off loopback (ADR-0024).

---

## 5. Operational scale sanity (~500 users, Compose stays)

Assumptions: 500 accounts, ~100 weekly-active, ~10 books/active user → ~1,000–2,500 corpora; 8 GB / 4 vCPU VPS, 40–80 GB disk ([followup-vps-sizing](../2026-07-12/followup-vps-sizing.md)).

**What breaks first**

1. **MinIO disk.** 2,500 × 20 MiB ≈ 50 GiB of originals alone, plus Postgres (chunks + `vector(1536)` + HNSW). 80 GB is tight once images (~8–10 GiB, fat pdf-worker) and WAL/backups share the box. **This is the first physical wall.**
2. **`worker-pdf` throughput.** One PDF at a time, up to 30 minutes, OCR-capable. A class of students uploading scans serializes for days. EPUB/`celery` worker is better (default concurrency ≈ CPU count) but still FIFO.
3. **AI invoice.** Uncapped generation (see §1.2) outruns disk as a *business* failure mode.
4. **Postgres RAM / HNSW.** ~400 chunks × 1536 × 4 B ≈ 2.5 MiB vectors/book; 2,500 books ≈ 6 GiB raw vectors **before** HNSW overhead. Shared_buffers on an 8 GB host cannot hold that; queries spill to disk and get slow, not instantly corrupt. pgvector stays the engine (ADR-0006); the escape hatch (reranker / dedicated vector DB) is not the 500-user move.
5. **In-memory limiter + 2 API workers.** Availability bug under load, not just abuse (global 429s).
6. **Redis** as broker is fine at this size (transport only). Don’t backup it.

**Cheap headroom that keeps ADR-0008/0023**

- Quotas + spend caps + ingestion concurrency-per-user (software; no new hosts).
- Bigger disk or **S3-compatible off-box object store** (Cloudflare R2 / Backblaze B2 / Hetzner Object Storage). ADR-0013 already treats MinIO as “any S3 API”; prod overlay can point `LEARNY_STORAGE_ENDPOINT` off the VPS without Kubernetes.
- Second Compose `worker` replica on the default queue (`--scale` or a copied service) before touching k8s.
- Split queues: `ingest-epub` / `embed` / `quiz` so interactive quiz-gen isn’t behind a 20-minute parse.
- Redis rate-limiter + `X-Real-IP` from the trusted proxy hop.
- Stay on 8 GB until pdf-worker OOM/queue delay shows in Netdata; then 16 GB same Compose, not a platform rewrite.

Do **not**: build on the VPS (already forbidden), expose API ports, or put Caddy in front of `api:8000` (ADR-0017).

---

## Launch-blocker checklist

**Must-have before strangers can create accounts on a hosted instance**

- [ ] Redis (or equivalent shared) limiter; client IP from trusted proxy hop; **user_id** keys on generation/upload/quiz.
- [ ] Per-user daily AI USD (or token) cap with a hard stop; operator global kill-switch.
- [ ] Per-user source **count** + stored-bytes quota; ingestion: max N in-flight jobs per user; rate-limit ingestion POST.
- [ ] Signup gate: **invite-only** and/or Turnstile + disposable-domain block. Unverified open register is a no.
- [ ] ToS + privacy policy + subprocessor list + copyright/notice-and-takedown page (agent contact). Register a US DMCA agent if any US users are expected.
- [ ] In-app account deletion that removes DB **and** MinIO objects (`StoragePort.delete`).
- [ ] Confirm backups/offsite actually run on that VPS (ADR-0024 is designed; launch is not the time to discover `LEARNY_BACKUP_REMOTE_*` unset).
- [ ] No public sharing of book bytes, corpus, or generated answers that quote the book outside the owner’s session.

**Nice-to-have (same season, not a gate if invite-only)**

- [ ] `EmailPort` + verification + password reset (becomes must-have the day registration is open).
- [ ] Signed OpenAI/Anthropic DPAs; ZDR request in the background.
- [ ] EU representative / Encarregado named (must-have if actively targeting EU).
- [ ] DSAR zip beyond vault export.
- [ ] Queue split (embed/quiz vs ingest); object storage off-VPS; 16 GB RAM.
- [ ] Caddy custom rate-limit image; Cloudflare in front of Caddy.
- [ ] Automated publisher-hash scanning; geo-block EU; children’s product compliance.

---

## Cycle-sized moves

Each is one spec-driven cycle. Hexagonal rules: no new AI SDK; email/captcha sit behind Learny ports.

### Cycle A — Shared limiter + quotas + spend cap (M)

Wire Redis `RateLimiter`, `X-Real-IP` from Next.js (strip inbound XFF), user_id keys, ingestion throttle, source count/bytes quotas, per-user in-flight ingestion cap, daily AI ledger on embedding + generation + quiz ports.

- **Why recommend:** Closes the documented proxy-IP hole and the generation-bill hole with code that already anticipated a Redis swap. Highest blast-radius reduction per line. Fits Compose.
- **Why-not:** Spend accounting needs honest token fields from adapters; a too-tight cap makes dogfood miserable. Two-worker in-memory status quo is “fine” for a private invite of five friends — this cycle is for *strangers*.

### Cycle B — Legal pages + account deletion + DMCA mailbox (S–M)

Static `/terms`, `/privacy`, `/copyright`; ToS checkbox on register; `StoragePort.delete` + `DELETE /api/auth/account`; operator runbook for notice-and-takedown; register Copyright Office agent if serving the US.

- **Why recommend:** Non-optional to take user books. Deletion is an LGPD/GDPR right and the takedown mechanism. Mostly docs + one destructive use case the schema already CASCADEs.
- **Why-not:** Counsel time, not code time. A privacy policy that lies about retention is worse than none. Don’t generate ToS from a blog template and ship.

### Cycle C — Signup gate: invite codes XOR Turnstile (S)

Invite table (code, remaining uses, created_by) **or** Turnstile siteverify on register/login. Optional local disposable-domain deny-list with alias allow-list.

- **Why recommend:** Without email, this is the only proportional bot brake. ADR-0012 already wanted invite-compatibility. Turnstile is one HTTP POST, not Cloudflare-on-the-whole-site.
- **Why-not:** Invites cap growth (RQ12’s problem). Turnstile adds a US subprocessor (disclose). Doing **open** register here without Cycle D still burns money.

### Cycle D — `EmailPort` + verify + password reset (M)

ADR + Resend/Postmark/SES adapter; verify-before-session (or session with `email_verified_at` gate on upload/AI); reset tokens hashed like sessions.

- **Why recommend:** Required for real open registration; RFC-005’s parked item; also the channel for breach notice.
- **Why-not:** Largest new dependency, deliverability, and abuse of the mail endpoint itself (must rate-limit). Skip while invite-only.

### Cycle E — Compose headroom without a platform rewrite (S)

Point prod storage at R2/B2 *or* enlarge VPS disk; optional second `worker` service; optional queue names for embed/quiz; Netdata alert on `worker-pdf` queue depth / disk %.

- **Why recommend:** 500 users hit disk and the PDF serial queue before they hit Kubernetes. ADR-0013/0008 already allow this.
- **Why-not:** Moving object storage is an ops drill (credentials, mirror, restore). Don’t split queues until Cycle A caps exist or you’ll just fair-share unlimited work.

### Cycle F — EU posture (S, policy-heavy)

Either: (1) privacy policy + representative + Art. 3(2) acceptance, or (2) explicit non-EU waitlist / no EU marketing. Sign vendor DPAs. Decide ZDR (request, don’t wait).

- **Why recommend:** Avoids accidental GDPR by English open signup. Cheap if the product stays Brazil/US-waitlist first.
- **Why-not:** Representative is a recurring fee. Geo-blocking is leaky (VPN) and hostile to Portuguese speakers in the EU. Don’t pretend “we’re small” is an Art. 27 exemption.

**Suggested order:** A → B → C on the public host; D when opening the form; E when Netdata says so; F when any EU user is invited on purpose.
