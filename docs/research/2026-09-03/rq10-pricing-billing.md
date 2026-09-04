# RQ10 — Pricing & billing (secondary)

*Fleet research, 2026-09-03. Prices and tax rules change; treat numbers as a snapshot, not a contract. This is so public launch is not blocked on billing — it is not a mandate to charge on day one.*

## TL;DR

**Do not put a paywall in front of the first public hosted instance.** Charge later, once the cited-Q&A + teach + FSRS loop actually works for a stranger (the 2026-09-03 walkthrough still has a real-provider 400 that deletes the conversation). When you do charge:

- **Product shape:** one hosted **Freemium + Pro** SKU at **$12/mo or $99/yr**. Free keeps the wow (one real book, cited answers, one teach session, one quiz deck, unlimited FSRS). Pro raises AI caps. Self-host (Apache-2.0) stays free forever.
- **Unit economics:** a ~100k-word book costs **~$0.02 to embed**. A cited Sonnet 5 answer at medium effort is **~$0.03–0.04**. An 8-turn teach session is **~$0.18 with the existing 1h prompt cache**. A Haiku 4.5 batched quiz deck is **~$0.20**. Light/medium/heavy hosted users cost about **$0.40 / $2.50 / $9/month** in AI. At $12 Pro, medium usage is fine; heavy needs a cap or BYOK.
- **Billing stack:** **Paddle as Merchant of Record** (5% + $0.50, no monthly fee). Polar does **not** list Brazil as a seller-payout country. Lemon Squeezy is the fallback (PayPal payouts). Stripe-as-merchant is cheaper on paper and available to a Brazilian CNPJ, but EU digital-services VAT starts on sale #1 and you file it — a solo-dev trap.
- **Integration:** webhook adapter → Postgres entitlement flags. No billing SDK in `domain/` or `application/` (ADR-0007).
- **BYOK:** complement for power users after Pro exists, not a launch substitute.

**Primary recommendation:** Freemium + $12/$99 Pro, billed through Paddle. **Fallback product:** RemNote-style monthly AI credits if the heavy tail appears. **Fallback billing:** Lemon Squeezy via PayPal if Paddle onboarding stalls.

---

## Competitor pricing (USD, checked 2026-09-03)

What each product **gates** matters more than the sticker. Learny's costly surface is generation (Ask / Teach / quiz decks). Reading, highlights, notes, and FSRS reviews are almost free.

| Product | Price | Free / trial | What pay unlocks | Source |
|---|---|---|---|---|
| **Readwise + Reader** | Full **$9.99/mo annual** ($119.88/yr) or **$12.99/mo**. Lite **$5.59/mo annual** (no Reader). Academic 50% off. | 30-day trial, then paid. **No permanent free tier.** | Full: Reader app, Ghostreader AI, Obsidian/Notion export, tagging. Lite: highlight resurfacing only. | [readwise.io/pricing](https://readwise.io/pricing), [readwise.io/pricing/reader](https://readwise.io/pricing/reader) |
| **Recall** (recall.it, not recall.ai meetings) | Plus **$10/mo billed yearly**; Max **$38/mo billed yearly**. Monthly ~$12 / $48. Student 20% off. | **Forever free:** unlimited saves + notes, **10 AI summaries/month**. | Plus: unlimited AI summaries, chat, TTS, knowledge graph, quizzes/SRS, bulk import. Max: pick ChatGPT/Claude/Gemini, bulk AI, 1:1 onboarding. “Unlimited” is fair-use. | [recall.it/pricing](https://www.recall.it/pricing) |
| **RemNote** | Pro **$8/mo** ($96/yr) or **$10/mo monthly**. Pro with AI **$18/mo** ($216/yr) or **$20/mo**. | **Forever free:** unlimited notes + flashcards, 3 annotated PDFs, **250 AI credits/mo**. | Pro: PDFs/occlusion/backups + **1,000 credits**. Pro+AI: tutor/PDF-to-cards + **20,000 credits**. Extra pack $10 / 20k. | [remnote.com/pricing](https://www.remnote.com/pricing), [AI credits](https://help.remnote.com/en/articles/9416169-ai-credits) |
| **Shortform** | **$24/mo** or **$197/yr** (~$16.42/mo). | 5-day trial; **no lasting free library**. | Whole product (guides, audio, AI chat on guides). Content library, not your books. | [shortform.com](https://www.shortform.com/) (Aug 2026 figures via [Shortform Hub](https://www.shortform.com/blog/hub/product/is-shortform-worth-it/)) |
| **Blinkist** | Promo-heavy. Premium ~**$80–100/yr**; Pro ~**$140–175/yr** (AI); Platinum ~**$200–286/yr** (events). Region/platform vary. | **1 preselected Blink/day**. | Premium: full summary library + offline. Pro: Blinkist AI on outside articles/PDFs. Not your EPUB corpus. | [blinkist.com](https://www.blinkist.com/) (Aug 2026 ranges via [Nibble](https://nibble-app.com/blog/blinkist-vs-shortform), [Headway](https://makeheadway.com/blog/is-blinkist-worth-it/)) |
| **Matter** | Web **$8/mo or $60/yr**. iOS **$7.99/mo or $79.99/yr** (App Store tax). | **Generous free:** unlimited library, parsing, tags. | Premium: HD TTS, AI Co-Reader, newsletters/RSS, unlimited highlights + PKM export, Send to Kindle. | [App Store listing](https://apps.apple.com/us/app/matter-reading-app/id1501592184); web rates via [Gleamr](https://gleamr.io/blog/matter-app-pricing-2026) |
| **NotebookLM** (rebranded **Gemini Notebook**, Jul 2026) | Not sold standalone. Bundled in Google AI: Plus **~$4.99/mo**, Pro **~$19.99/mo**, Ultra **$99.99 / $199.99**. Official plan page does not print USD in static HTML — dollars from Jun–Aug 2026 writeups. | **Real free:** ~100 notebooks, **50 sources/notebook**, **~50 chats/day**, a few Audio/Video Overviews. | Paid mostly **raises caps** (Plus ~100 sources / 200 chats; Pro ~300 sources / 500 chats), not a different product. Google subsidizes inference. | [notebooklm.google/plans](https://notebooklm.google/plans), [one.google.com AI plans](https://one.google.com/about/google-ai-plans/), [FelloAI](https://felloai.com/notebooklm-pricing/) |
| **Anki** | Desktop / AnkiDroid / AnkiWeb **free**. AnkiMobile iOS **~$24.99 one-time**. | The whole study loop is free except native iOS. | Nothing on desktop. iOS pays for Anki’s development, not AI. | [docs.ankiweb.net/syncing](https://docs.ankiweb.net/syncing.html); US App Store ~$24.99 (Aug 2026) |

**Landscape takeaways for Learny**

1. **$8–12/mo annual** is the adult-learner cluster (Readwise, Recall Plus, RemNote Pro, Matter). Shortform/Blinkist Pro are content libraries at $16–24 equivalent — different job.
2. **Permanent free beats 30-day-then-cliff** if the free thing is complete enough to form a habit. Readwise’s trial-only model converts because the daily review is already addictive; Learny’s wow is a *first cited answer on your book*, which a stranger must reach before any trial clock matters.
3. **AI is what gets metered** (RemNote credits, Recall’s 10 summaries, NotebookLM daily chats). FSRS/reviews stay free everywhere they exist.
4. **NotebookLM’s free tier is not a price to match.** Google is selling Gemini + storage; Learny pays OpenAI + Anthropic at list. Competing on “50 chats/day free” would bankrupt a VPS product.
5. **OSS Anki is the cultural ceiling for “I already have an algorithm.”** Charge for grounded generation and a hosted corpus, not for reviewing cards.

---

## Cost-model arithmetic

Prices as of 2026-09-03:

- OpenAI `text-embedding-3-large`: **$0.13 / 1M tokens** (Batch $0.065). Official model page: [developers.openai.com … text-embedding-3-large](https://developers.openai.com/api/docs/models/text-embedding-3-large). Learny uses `dimensions=1536` (ADR-0019); that does not change the token price.
- Claude **Sonnet 5** (current `LEARNY_GENERATION_MODEL`): **$2 / $10 per MTok** in/out. 1h cache write **$4 / MTok**, cache hit **$0.20 / MTok**. Official: [platform.claude.com pricing](https://platform.claude.com/docs/en/about-claude/pricing). The $2/$10 intro rate is now permanent (the Sep 2026 bump to $3/$15 was cancelled).
- Claude **Haiku 4.5** (current `LEARNY_QUIZ_MODEL`): **$1 / $5**. Batch API **50% off**.
- Thinking tokens are **billed as output**. Config: `generation_effort=medium`, `generation_max_tokens=4096` (thinking + answer share that cap). Teaching already sets `cache_control` TTL **1h** (`backend/app/infrastructure/answering/anthropic.py`).
- Chunking: `chunk_max_chars=2000`, **no overlap** (`pack_chunks`). FSRS reviews hit Postgres only — **$0 AI**.

### One ~100k-word book, embed once

English ≈ 1.3 tokens/word → **130,000 tokens**. No overlap, so no extra.

```
130,000 / 1,000,000 × $0.13 = $0.0169  ≈  $0.017 / book
```

Query embeddings (~100 tokens/question) are noise: 60 questions × 100 × $0.13/1M ≈ **$0.0008**. Portuguese tokenizes a bit worse; budget **$0.02 / book**. ADR-0019’s “~$0.04/book” assumed a longer book (~320k tokens). Batch API would halve this; skip it until libraries are large.

### One cited answer (Sonnet 5, medium effort)

8 evidence chunks × 2,000 chars ≈ 4,000 tok of documents, plus system + question. Sonnet 5’s tokenizer is ~30% hungrier than 4.x (ADR-0020). Round to **6,500 input**. Output: ~1,000 thinking + ~600 prose = **1,600 output** (well under the 4096 cap).

```
input:  6,500 / 1e6 × $2  = $0.0130
output: 1,600 / 1e6 × $10 = $0.0160
                          = $0.029  per answer
```

Haiku 4.5 same shape: 6,500×$1 + 1,600×$5 = **$0.0145** — fine as a cheap/free-tier model, worse at grounded synthesis (ADR-0020). Opus 5 at $5/$25: **$0.0725**. Keep Sonnet 5 for paid Ask/Teach.

**Worst case** (hits 4096 output): 6,500×$2 + 4,096×$10 = **$0.054**. Cap `generation_max_tokens` is already a cost fuse.

### One teach session (8 turns, 1h cache)

Turn 1 ≈ an answer, plus a 1h cache **write** on the frozen prefix (~6,500 tok × $4/MTok = **$0.026** write, which *replaces* the base input on that prefix):

```
turn 1 ≈ $0.013 in + $0.026 cache write + $0.016 out  ≈ $0.055
turns 2–8: cache hit 6,500 × $0.20/1e6 = $0.0013
           + ~300 new tok × $2/1e6     = $0.0006
           + 1,600 out × $10/1e6       = $0.0160
           ≈ $0.018 / turn × 7         = $0.126
session total                          ≈ $0.18
```

Cache miss (gap > 1h): ~8 × $0.029 = **$0.23**. Still cheap relative to $12.

### One quiz deck (Haiku 4.5, Message Batches, 50% off)

One batch request **per section**, up to `quiz_max_items_per_section=6`. A 100k-word book → roughly **40–60 sections**. Use 50:

```
input  50 × 3,000 tok = 150,000 × $0.50/1M (batch) = $0.075
output 50 × 1,000 tok =  50,000 × $2.50/1M         = $0.125
                                                   = $0.20 / deck
```

A 200-section textbook ≈ **$0.80** batched. Online (no batch) ≈ **2×**.

### Three user-months (hosted, Learny keys)

| | Light | Medium | Heavy |
|---|---|---|---|
| Books ingested / re-embedded | 1 × $0.02 | 3 × $0.02 | 8 × $0.02 |
| Cited questions | 15 × $0.029 = $0.44 | 40 × $0.029 = $1.16 | 120 × $0.029 = $3.48 |
| Teach sessions (8 turns) | 2 × $0.18 = $0.36 | 6 × $0.18 = $1.08 | 20 × $0.18 = $3.60 |
| Quiz decks | 1 × $0.20 | 2 × $0.20 | 6 × $0.20 |
| FSRS reviews | $0 | $0 | $0 |
| **AI COGS / month** | **~$0.82** | **~$2.50** | **~$9.24** |

VPS, Postgres, MinIO, backups are almost entirely **fixed**. At tens of users they dominate; at hundreds, generation dominates. A $12 Pro subscriber at **medium** leaves ~$9.50 before MoR fees (~$1.10 on $12) and Brazilian income tax (carnê-leão or PJ — yours either way). A **heavy** user on uncapped Pro is a loss leader unless you cap, move them to Haiku, or BYOK.

**Free-tier expected COGS** (caps below): 2 books + 8 Q/day × 30 × $0.029 is $6.96 if every free user maxes Ask. They will not. Design for **p95**, not the average: if 10% of free users hit the daily cap every day, blended free COGS is closer to **$1–2/user-month**. That is the number that can kill a hobby VPS — hence hard caps, not “unlimited with fair use” on generation.

---

## Recommended model

### Primary: hosted Freemium + one Pro SKU ($12/mo or $99/yr)

| | Free | Pro ($12 / $99) |
|---|---|---|
| Cloud-embedded books | **2** at a time (replace OK; old embeddings dropped) | **20 ingest jobs / month**, then a wait or BYOK |
| Cited Ask | **8 / day** (Sonnet 5; after cap, show the last answer + “come back tomorrow” — do not delete the conversation) | **80 / day** |
| Teach | **1 session / day**, 8 turns | **8 sessions / day** |
| Quiz decks | **1 deck / book** | Unlimited within the ingest cap |
| Reader, highlights, notes, FSRS, Anki `.apkg`, vault export | **Unlimited** | Unlimited |
| Fair-use | Hard 429 on AI, with a retry-after. No silent conversation delete. | Soft ceiling; email before kill-switch |

**Why this, not something else**

- **Why-recommend:** Matches the $8–12 cluster without pretending to be Google. Two books + eight cited answers is enough to feel the product (the money path in `docs/media/`) without gifting NotebookLM’s 50 chats/day. One SKU keeps FastAPI entitlements a boolean + integer counters — no credit ledger, no usage-based invoices. $99 annual (~$8.25/mo) is what you should put in the checkout default: MoR’s $0.50 flat fee is 5.5% of $99 vs 9.2% of $12, and Paddle asks for a custom rate on products **under $10**, so do not price at $8. Unlimited reviews/export on free is the Anki/Obsidian trust move; gating memory would cheapen the product (RQ08/RQ09 territory).
- **Why-not:** $12 will look expensive next to Gemini Notebook Plus at ~$5 for a Google-subsidized cousin. Heavy users can still blow $9 of COGS. You will need a written fair-use line in ToS even on Pro. Brazilian Pix buyers want BRL; Paddle can price in BRL, but you then hold FX risk.

**Free-tier wow, explicitly preserved:** upload a real EPUB/PDF → Ask with passage citations → one Teach on a chapter → Generate quiz → review a card. If you drop below **one book + five cited answers + one deck**, you have gutted the reason to register.

### Fallback product: monthly AI credits (RemNote shape)

If p95 free users slam 8 Q/day, or Pro heavies cluster at $9 COGS, replace the daily counters with a single **credit pool** (e.g. Free 200, Pro 4,000; Ask=8, Teach turn=8, quiz section=3).

- **Why-recommend as fallback:** one meter, surplus packs ($5 / 2,000), no new SKU explosion.
- **Why-not as launch:** credit UX is a support sink; Learny’s hexagonal app has no billing domain yet. Ship integer caps first.

### Rejected alternatives

| Option | Why-not |
|---|---|
| **Readwise trial-then-paywall** | Learny’s habit loop is not yet proven; a 30-day clock before the first successful cited answer (today: Anthropic 400) is a refund machine. |
| **Usage-based ($0.05/answer)** | Honest COGS, terrible conversion, invoice complexity, and it advertises “we are a wrapper.” |
| **Haiku-only free / Sonnet Pro** | Tempting (~2× cheaper). Risks a bait-and-switch on the citation quality the landing page will claim. Prefer **same model, fewer calls**. |
| **Seat / team plans** | No team product. Skip. |
| **Lifetime** | Model prices move; a 2024 lifetime is how you fund someone else’s 2027 Opus bill. |
| **Charge for FSRS or export** | Trains users to leave. Anki is free; vault export is the portability promise (ADR-0026). |
| **BYOK as the only paid plan** | Shifts COGS off Learny but dumps key-phishing UX, encryption, and “my key got 401” support on a solo. Also does not help users who just want a book tutor. |
| **Match NotebookLM free caps** | 50 chats/day × $0.03 = **$1.50/user-day** = $45/user-month. Instant insolvency. |

---

## Billing-stack recommendation

A solo developer in Brazil selling a global B2C digital service has **two tax problems**. MoR only solves the second.

1. **Brazilian income tax** (carnê-leão on PF foreign receipts, or PJ/Simples on a CNPJ) — yours on Stripe *and* on Paddle. Not optional. Talk to a contador before the first dollar; this research is not tax advice.
2. **Customer-country consumption tax** — EU/UK VAT on B2C digital services from **sale #1** (no OSS threshold for non-EU suppliers), plus US economic nexus ($100k / 200 transactions in most states). Stripe Tax **calculates**; you still **register and file**. A Merchant of Record is the legal seller and remits VAT/sales tax.

### Primary: Paddle (MoR)

[paddle.com/pricing](https://www.paddle.com/pricing): **5% + $0.50 / checkout**, no monthly fee. Tax registration, filing, remittance, fraud, dunning, buyer billing support included. Pix for BRL-priced one-time items ([Paddle Pix](https://developer.paddle.com/concepts/payment-methods/pix)). Account verification has three phases; **business verification is not required for individuals or sole traders** ([Paddle account verification](https://www.paddle.com/help/start/account-verification/what-is-account-verification)). CNPJ format is already in their tax-ID table.

On a $12 sale: fee **$1.10** (9.2%). On $99: **$5.45** (5.5%).

- **Why-recommend:** Only option in the requested set that is a mature SaaS MoR **and** can pay a Brazilian seller without pretending Polar’s Connect-Express list includes BR (it does not — see below). Hexagonal fit is a webhook. Under-$10 products need a custom Paddle rate — another reason Pro is $12 not $8.
- **Why-not:** Onboarding is a review (domain + identity), slower than Stripe. You give up being the legal seller (refunds/ToS sit with Paddle). No volume discount until you are large. Pix-for-subscriptions was still early-access when last documented.

### Fallback billing: Lemon Squeezy

[lemonsqueezy.com/pricing](https://www.lemonsqueezy.com/pricing): **5% + $0.50**, MoR, no monthly fee. **Bank payouts omit Brazil** ([supported countries](https://docs.lemonsqueezy.com/help/getting-started/supported-countries)); **PayPal payouts cover 200+ countries**, which is the Brazilian path. Stripe acquired LS in 2024; 2026 commentary is that new energy is going to **Stripe Managed Payments**, with LS in maintenance. Use if Paddle rejects or stalls — do not bet the company on LS’s five-year roadmap.

### Rejected: Polar as primary

Polar Starter is **5% + $0.50** ([polar.sh fees](https://polar.sh/docs/merchant-of-record/fees)), developer-native webhooks, FastAPI examples in `polar-sdk`. **Seller payouts use Stripe Connect Express. Brazil is not on the published country list** ([polar.sh supported countries](https://polar.sh/docs/merchant-of-record/supported-countries) — Botswana → Brunei, no Brazil). Checkout copy may be translated for Brazilian *customers*; that is not a payout. Revisit only if Polar adds BR recipients. International cards add **+1.5%**, so Polar is also the most expensive of the four on a $12 foreign-card sale (~$1.28).

### Rejected as first merchant: Stripe (plus Stripe Tax)

Stripe **is** available to Brazilian accounts (CNPJ/CPF, KYC). Domestic cards **3.99% + R$0.39**; international **+2%** ([stripe.com/en-br pricing](https://stripe.com/en-br/pricing/local-payment-methods)). Stripe Tax is **+0.5%** and does not file EU OSS for you. Non-EU suppliers collect EU VAT from the first B2C digital sale ([Stripe Tax](https://stripe.com/tax)). That is the launch-blocker, not the 4% processing fee.

Keep Stripe in mind **after** an accountant and a CNPJ, if most volume is BR-domestic Pix (invite-only on BR Stripe today) or you incorporate somewhere Stripe Tax filings are turnkey. Not the cheapest *credible* global setup for a solo on week one.

Fee sketch vs “just Stripe,” $1k/mo US+EU mix:

| | Paddle/LS | Stripe + Tax DIY |
|---|---|---|
| Processing | ~$55–70 | ~$40–55 |
| VAT/sales-tax filing | included | OSS + US states: hundreds of $/mo in time or a firm |
| You are liable for customer VAT | no (MoR is) | yes |

### FastAPI integration shape (hexagonal)

Authoritative state stays in PostgreSQL (same as jobs). Billing vendor is an **infrastructure adapter**.

```
POST /api/billing/webhook          → infrastructure/web/billing.py
                                     verify HMAC on raw body; 401 on bad sig
                                     persist billing_events (idemp by vendor event id)
                                     map vendor status → EntitlementPort.update(...)
GET  /api/billing/checkout         → application starts a session via BillingPort
                                     adapter HTTP-calls Paddle; returns hosted URL
GET  /api/auth/me                  → already returns the user; add plan + remaining caps
```

- **Domain:** `Plan` (`free` \| `pro`), `Entitlement` (counters, period end). No `paddle` import.
- **Application:** `EntitlementPort` — `is_pro(user_id)`, `consume_ask(user_id) -> remaining | CapExceeded`. Increment in the same transaction as the conversation turn enqueue.
- **Infrastructure:** `PaddleBillingAdapter` (httpx + webhook verifier). Optional `polar_sdk` / Paddle SDK **only inside this module**, same rule as `openai` / `anthropic` (ADR-0007). Prefer verify-HMAC-yourself: Paddle `Paddle-Signature` (`ts` + `h1` HMAC-SHA256 over `{ts}:{raw_body}`); Polar Standard Webhooks (`webhook-id` `.` `timestamp` `.` `body`).
- **Tables (names to confirm in `metadata.py` when implementing):** `billing_customers(user_id, vendor, vendor_customer_id)`, `entitlements(user_id, plan, current_period_end, asks_used, teaches_used, ingests_used, period_start)`, `billing_events(vendor_event_id PK, type, payload, processed_at)`.
- **Webhook events to honor:** subscription activated / renewed → `plan=pro`; canceled / past_due / refunded → `plan=free` at period end; never trust the browser return URL alone.
- **Checkout:** FastAPI builds a Paddle transaction with `custom_data.user_id` (or Polar `external_customer_id`), Next.js only redirects. Same-origin proxy already forwards cookies (ADR-0017); the webhook must be a **Caddy-exposed path that does not need a session cookie**.
- **Caps:** enforce in application services on Ask / Teach / ingest / quiz enqueue — not in the Next.js UI as the source of truth.

### BYOK (complement, not launch)

Recall Max already sells “pick Claude/GPT/Gemini.” Cursor-class tools encrypt user keys and bill the product separately.

- **When:** Pro users who would hit the 20-book / 80-Q caps, or who already have spend with Anthropic/OpenAI.
- **How it fits hexagonally:** same `EmbeddingPort` / `GenerationPort`; composition root reads `user_provider_key` from an encrypted vault instead of `LEARNY_*_API_KEY`. **Do not** add a third SDK. Decrypt in-process only for the upstream call; AES-256-GCM envelope with a master key **not** in Postgres; AAD bind to `user_id`; never log `authorization`.
- **Product:** keep charging **Pro** (software + corpus + FSRS). BYOK zeroes *Learny’s* inference COGS; it does not make the account free. Optional later: a cheaper “Pro BYOK” if support load stays low.
- **Risks:** a leaked customer key is an incident; provider ToS on “resale of API access” is why the user must be the API customer; two keys (OpenAI embed + Anthropic generate) or you break ADR-0019/0020; phishing UX (“paste sk-ant-…”). **Defer until after hosted Pro exists.** Self-hosters already BYOK via env vars — that path stays.

---

## Cycle-sized moves

Quality-first: none of this is the next product cycle unless a public instance is actually going live. When it is:

1. **Caps without billing (public-launch hygiene, pairs with RQ09).** `entitlements` row defaulting every user to Free limits. `consume_ask` / `consume_teach` / ingest quota in the existing conversation and ingestion services. Clear 429 + retry-after. Stop deleting failed conversations (that is a product bug, not a pricing feature). Ship this **before** any checkout.
2. **Cost telemetry, no dashboard.** Log `input_tokens`, `output_tokens`, `cache_*`, `effort` (the answering adapter already logs these). Nightly sum → estimated USD. Know p50/p95 COGS before you pick $12 vs $15.
3. **Paddle sandbox + webhook adapter.** One `BillingPort`, hosted checkout URL, `billing_events` idempotency, `plan` flag. No UI beyond Settings → “Upgrade” / “Manage billing” (Paddle customer portal). Verify with sandbox + a signed fixture test; no live charges in CI.
4. **Free/Pro copy and ToS fair-use.** One pricing page. State the numeric caps. Academic 20–50% off is a later email process (Readwise-style), not a SheerID project.
5. **Only if p95 COGS is ugly:** Haiku for Free Ask (keep Sonnet on Pro), or the credit-meter fallback. **Only if a user asks in anger:** BYOK vault behind the existing ports.

Out of scope for the first billing cycle: teams, usage invoices, Polar, Stripe Tax, lifetime, App Store (Matter’s $60 vs $79.99 is why you sell on the web), PIX subscriptions, and changing ADR-0019/0020 providers to chase a cheaper embed.
