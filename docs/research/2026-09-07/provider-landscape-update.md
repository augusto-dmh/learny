# Provider landscape delta — Gemini 3.8 Flash and the post-promo cheap tier

*Research date: 2026-09-07. Delta on docs/research/2026-09-03/rq14-multi-provider-models.md (model landscape, hosting/privacy matrix) and rq15-ai-cost-optimization.md (caching, batch, effort levers) — this file only covers what is new or changed since 2026-09-03. Prices USD per 1M tokens (in / out) unless noted. Every price is marked "official page" (verified on the vendor's own page today) or "aggregator, unverified". Carry-forward rows (Claude family, Kimi, Qwen open-weight, embeddings) are not repeated here; see rq14 §1.*

---

## TL;DR

**The baseline verdict survives contact with Gemini, with one real addition.** Google entered the gap the 2026-09-03 snapshot missed: **Gemini 3.8 Flash** (GA 2026-09-02) is a **$0.75 / $3.75** 1M-context model with an OpenAI-compatible endpoint, batch and caching support, and paid-tier terms that do not train on API data — the **only US-vendor cheap-tier candidate that is not a Chinese 1P**. But it has **no Anthropic-style Citations API** (its File Search citations live inside a Google-managed RAG store, not prompt documents), and its intro price **doubles on 2027-01-01** to $1.50 / $7.50 — above Haiku 4.5's permanent $1 / $5. **GLM-5.3-Flash's 50% promo ends 2026-09-09** (verified: list reverts to $0.15 / $0.50, still the cheapest quality-tier model anywhere); the Z.AI coding-plan subscription **cannot** be used for Learny (coding tools only, verified in the official FAQ). DeepSeek and MiniMax prices are unchanged (MiniMax M3's 50% discount is now marked *permanent*). For Cycle G: nothing displaces **Haiku 4.5 as the first cheap move** (same SDK, native citations); **Gemini 3.8 Flash is the one new SKU worth adding to the eval-gated economy ladder** — via the same OpenAI-compatible adapter planned for Fireworks — while the Chinese flash tiers stay Fireworks-US-only and last.

---

## 1. New/changed entries vs the 2026-09-03 baseline

New or changed rows only. Baseline rows (Claude 5/4.6/Haiku 4.5/Opus 4.8, GLM-5.3, Kimi K3/K2.6, DeepSeek V4 Pro, Qwen3-Max/235B, embeddings) are unchanged unless listed; see rq14 §1 for the carried-forward table.

| Model | Maker | Hosting | Price in/out $/MTok | Context | What changed / new | Price status |
|---|---|---|---|---|---|---|
| `gemini-3.8-flash` | Google | 1P (`generativelanguage.googleapis.com`), Vertex; OpenAI-compat endpoint | **0.75 / 3.75** through 2026-12-31 → **1.50 / 7.50** from 2027-01-01; cache read 0.075 → 0.15; cache storage 0.50 → 1.00 per MTok/hr; batch **0.375 / 1.875** → 0.75 / 3.75 | **1,048,576 in / 65,536 out** | **New to the landscape.** GA 2026-09-02. Thinking (low/med/high; no `minimal`), structured outputs, explicit+implicit caching, Batch API — all via OpenAI-compat. Free tier exists; free-tier content **is** used to improve Google products. | **Official page** |
| `gemini-3.1-flash-lite` | Google | 1P, OpenAI-compat | **0.25 / 1.50**; batch 0.125 / 0.75; cache 0.025 | (not verified) | Cheaper Gemini floor if 3.8 Flash quality is not needed; no free-tier grounding. | **Official page** |
| `gemini-3.5-flash` / `gemini-3.5-flash-lite` | Google | 1P | 1.50 / 9.00 and 0.30 / 2.50 | — | Listed for completeness; undercut by 3.8 Flash at intro pricing. | **Official page** |
| `gemini-embedding-2` | Google | 1P | text **0.20** (embed-only); batch cheaper | multimodal (text/image/audio/video) | New multimodal embedding. Text price is **above** OpenAI `text-embedding-3-large` ($0.13) — no cost case. | **Official page** |
| `glm-5.3-flash` | Z.AI | 1P; FW US `glm-5p3-flash-us` | promo **0.075 / 0.25** (cache 0.015) **until 2026-09-09 24:00 UTC+8**; then list **0.15 / 0.50** (cache 0.03) | 1M | Promo end date **re-verified today** — the page shows struck-through list prices and the exact end timestamp. Post-promo list is the number to plan against. | **Official page** |
| MiniMax-M3 | MiniMax | 1P `api.minimax.io`, TG, OR | **0.30 / 1.20** (≤512k in); 0.60 / 2.40 above — now labeled "**Permanent 50% off**" | 1M | The baseline's "promo" qualifier can be dropped; no end date on the discount. M2.7 unchanged. | **Official page** |
| `deepseek-v4-flash` / `-pro` | DeepSeek | 1P, FW, TG, OR, Vertex MaaS | flash off-peak **0.22 / 0.66**, peak 0.44 / 1.32 (cache hit $0.007); pro off-peak 0.66 / 1.98 | 1M | **No change** since 09-03 (re-verified on the official pricing page). Off-peak windows: 01:00–04:00 and 06:00–10:00 UTC Mon–Fri. | **Official page** |
| `qwen3.8-flash` (DashScope) | Alibaba | DashScope/Model Studio 1P | **not verified** — catalog page lists the model without prices; an aggregator cites "Qwen3.7 Flash $0.03 / $0.13" as the cheapest API overall | — | New Flash tier exists on DashScope; treat any price as **aggregator, unverified** until the Model Studio price table is checked directly. | aggregator, unverified (model existence: **official page**) |
| GLM Coding Plan (Lite ~$18/mo) | Z.AI | subscription | flat monthly, 5-hour quota cycles | — | **Not usable for Learny** — see §3. | **Official page** |

---

## 2. Gemini family (gap 1 — the big addition)

### 2.1 Pricing and mechanics — verified on the official pricing page today

Source: [Gemini Developer API pricing](https://ai.google.dev/gemini-api/docs/pricing) (accessed 2026-09-07).

- **Gemini 3.8 Flash** (GA per the [release notes](https://ai.google.dev/gemini-api/docs/changelog), 2026-09-02): input **$0.75**, output **$3.75** (output price *includes* thinking tokens) — explicitly "through December 31, 2026", then **$1.50 / $7.50** from January 1, 2027. This is a scheduled 2× step-up, not an unspecified promo.
- **Batch API: −50%** ($0.375 / $1.875 in 2026). Batch + structured outputs would map onto the existing `AnthropicQuizAdapter.begin_deck` shape if quiz ever moved off Anthropic.
- **Context caching:** explicit cache read **$0.075** (0.1× input, same ratio as Anthropic) **plus storage $0.50 per 1M tokens per hour** (→ $1.00 in 2027). Note the difference from Anthropic: Gemini bills *hourly storage* on cached content; Anthropic charges a one-time write multiplier. For Learny's 1h-TTL teach-session pattern the economics are similar but not identical — the storage fee makes "cache and abandon" (write, never read) more expensive on Gemini than on Claude. Artificial Analysis lists a **90% cache discount** for implicit caching on this model (aggregator, unverified breakdown).
- **Model card** ([gemini-3.8-flash page](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash), accessed 2026-09-07): context **1,048,576 in / 65,536 out**; caching, batch, structured outputs, function calling, file search all supported; thinking levels low/medium/high (**`minimal` is not supported and returns an error** — relevant if the Cycle-2-style "turn thinking off" lever is ever ported to Gemini; the floor is `low`).
- **Free tier:** 3.8 Flash is listed "Free of charge" with a free tier — but per-model RPM/RPD numbers are **no longer published on the docs** ([rate limits page](https://ai.google.dev/gemini-api/docs/rate-limits), last updated 2026-09-02, defers to the logged-in AI Studio UI). Unpublished here; do not plan capacity on the free tier.

### 2.2 Citations — the product-critical check: **no equivalent of Anthropic's Citations API**

This is the same verdict rq14 reached for every non-Anthropic provider, and Gemini does not change it:

- **Grounding with Google Search** is a web-citations product (5,000 free paid-tier searches/month shared across Gemini 3.x, then $14/1,000 — official page). Wrong tool: Learny grounds in *the user's book*, not the web.
- **File Search tool** ([docs](https://ai.google.dev/gemini-api/docs/file-search), accessed 2026-09-07) is Gemini's RAG offer: Google imports, chunks, embeds, and indexes your documents, then the model's response "may include citations" exposed as `file_citation` annotations (`file_name` + `source`) on the Interactions API. This is **not** Learny-shaped: it means surrendering pgvector/RRF retrieval (ADR-0006, ADR-0020's stable citation anchors), storing user books in a Google-managed store, accepting file-level (not span-level, not chunk-id) citations, and citations on a "may include" basis. Embeddings inside File Search are billed at $0.15/MTok and retrieved tokens as normal input (official pricing page).
- **Practical consequence:** Gemini on Ask/Teach means the same **prompt-for-chunk-ids + grounding intersect** scheme as every other OpenAI-compat provider — acceptable for quiz/economy tiers under the rq14 §4 gate, a higher bar for Ask. Nothing here unseats Claude as the cited-money primary.

### 2.3 OpenAI-compatible endpoint — verified

[OpenAI compatibility docs](https://ai.google.dev/gemini-api/docs/openai) (accessed 2026-09-07): `base_url = https://generativelanguage.googleapis.com/v1beta/openai/` works with the stock OpenAI SDK (`chat.completions.create(model="gemini-3.8-flash", ...)`), supports `reasoning_effort`, and even Batch create/monitor (file upload/download stays on the genai client). **This fits rq14's Move 2 adapter as-is** — Gemini becomes one more `base_url` behind the planned `OpenAICompatibleGenerationAdapter`, not a new SDK.

### 2.4 Data terms — free vs paid (official [Gemini API terms](https://ai.google.dev/gemini-api/terms), accessed 2026-09-07)

| Tier | Google's stated use of your data |
|---|---|
| **Unpaid / free quota** (incl. AI Studio without billing) | Content **is used** "to provide, improve, and develop Google products and services and machine learning technologies"; **human reviewers may read API input and output**; terms explicitly say not to submit confidential or personal information. |
| **Paid** (Cloud Project with active billing) | Prompts and responses are **not used to improve products**; processed under Google's DPA; logged only for a limited period for abuse prevention. |
| **EEA / Switzerland / UK** | Only **Paid Services** may be offered to users there — the paid data terms apply even to free quota. |

For Learny: free-tier Gemini is fine for non-sensitive dev/smoke tests, **never** for real book text. Paid-tier Gemini is on par with the US-host requirement of rq14 §2 (US vendor, contractual no-training, DPA) — a materially cleaner story than any CN 1P. Brazil is not in the EEA clause, but any EU tenant makes paid tier mandatory.

### 2.5 Quality and multilingual

- Artificial Analysis (aggregator, unverified): Gemini 3.8 Flash (high) scores **47** on the AA Intelligence Index (#28 of 202), **280.8 tok/s** output (#4 of 202), TTFT **12.74 s** (high — thinking-heavy), blended $0.58/MTok ([model page](https://artificialanalysis.ai/models/gemini-3-8-flash)). The "(low)" thinking variant exists and is what a Learny economy tier would actually run; its scores were not verified.
- **Portuguese:** on AA's Portuguese language index (Global-MMLU-Lite based), the **Gemini family holds #1** — Gemini 3.1 Pro Preview at 94, ahead of Claude Opus 4.6 variants ([Portuguese ranking](https://artificialanalysis.ai/models/multilingual/portuguese), aggregator). The full table did not render for the cheap models (only the top 5 of 110 were visible to fetching) — **placement of 3.8 Flash / GLM / DeepSeek / MiniMax on Portuguese is unverified**; LMArena's text leaderboard has language categories but numbers were not extractable today. Treat "Gemini is strong multilingual" as family-level evidence, and Learny's own Portuguese snapshot eval as the only ruler that counts (rq14 §4 gate).

---

## 3. GLM-5.3-Flash economics after the promo (gap 2)

Verified today on [Z.AI pricing](https://docs.z.ai/guides/overview/pricing):

- The 50% promo is still live: **$0.075 / $0.25** (cache hit $0.015), and the page states it ends **24:00 on 2026-09-09, UTC+8** — i.e., it has already ended or ends within ~2 days of this writing. After that, list prices apply: **$0.15 in / $0.03 cached / $0.50 out**. All Learny planning should use the list price; the promo is not a basis for unit economics.
- Even at list, GLM-5.3-Flash remains the cheapest 1M-context quality-tier model found: **~$0.0016 per 8k-in/800-out cited turn** (vs Haiku 4.5 $0.012, Gemini 3.8 Flash $0.009 in 2026 / $0.018 in 2027, Sonnet 5 $0.024).
- The US-hosted route stays as rq14 planned it: Fireworks US-only SKUs are +50% vs global ([US-only serverless](https://docs.fireworks.ai/serverless/us-only-serverless)), which would put `glm-5p3-flash-us` around **~$0.22 / $0.75 (estimate, not verified on Fireworks' page today)** — still 2–3× cheaper than Gemini 3.8 Flash's 2026 price and ~5× cheaper than its 2027 price, with a US data story.

**Coding-plan subscription: does not transfer to Learny.** The [GLM Coding Plan FAQ](https://docs.z.ai/devpack/faq) (official, accessed 2026-09-07) is explicit: the plan is "strictly limited to use within officially supported tools and products"; it requires special endpoints — `https://api.z.ai/api/anthropic` (Claude Code/Goose) or `https://api.z.ai/api/coding/paas/v4` (other supported tools) — and only **GLM-5.3 and GLM-5.3-Flash** are callable, on 5-hour quota cycles. That is a coding-tool quota, not a generic API credit; running a study app's production traffic through it would violate the plan's terms. The ~$18/mo Lite tier is irrelevant to Learny's architecture; only pay-as-you-go API spend counts.

---

## 4. Cheap-tier changes since 2026-09-03 (gap 3)

- **DeepSeek: no change.** Official pricing page re-verified today — V4 Flash off-peak $0.22/$0.66, peak $0.44/$1.32, cache hit $0.007; V4 Pro off-peak $0.66/$1.98. Peak windows 01:00–04:00 and 06:00–10:00 UTC Mon–Fri.
- **MiniMax: discount made permanent.** [Pay-go page](https://platform.minimax.io/docs/guides/pricing-paygo.md) now labels M3's 50% off "**Permanent 50% off**" ($0.30/$1.20 ≤512k input; $0.60/$2.40 above; cache read $0.06). Adds a Priority tier at 1.5× standard. No M3.1 or newer LLM listed.
- **Qwen: new Flash tier exists** (`qwen3.8-flash` on the DashScope/Model Studio catalog — model name verified on Alibaba Cloud's page; **price not shown there**). Aggregators (benchlm.ai) call "Qwen3.7 Flash $0.03/$0.13" the cheapest API overall — **aggregator, unverified**; and DashScope is a CN 1P, so it inherits rq14's "not for default book traffic" rule regardless of price.
- **No new non-Chinese entrant under Gemini's price band surfaced** in searches for "cheapest frontier-quality LLM API September 2026": aggregators still name DeepSeek V4 Flash and MiniMax M3 as the value picks, both already in the baseline. The cheap-tier news of the week is Gemini's GA, not a new startup.
- **Kimi:** nothing changed materially since rq14 (K3 still ~$3/$15 — not an economy model). Not re-verified page-by-page today.

---

## 5. Multilingual angle for the shortlist (gap 4)

Evidence is thinner than the topic deserves; what exists:

- **Gemini family leads published Portuguese rankings** (AA Portuguese index: Gemini 3.1 Pro #1 at 94, ahead of Claude Opus 4.6 variants; cheap models not visible in the rendered table — aggregator, unverified placement below the top). Google's Live Translate marketing claims 70+ languages for a different (speech) model; not evidence for text quality.
- **Anthropic** remains the incumbent for Portuguese-primary Ask: Sonnet 5 is the Learny default and the nightly judge measures faithfulness on the real (Portuguese-preferred) snapshots; Haiku 4.5 inherits the same tokenizer/citations path.
- **GLM / DeepSeek / MiniMax / Qwen:** no credible per-model Portuguese generation benchmark surfaced in this pass (Chinese-vendor pages market multilinguality without comparable evals; LMArena language-category numbers were not extractable). The 2024-era MIRACL/MTEB numbers in rq14 cover *retrieval*, not generation.
- **Consequence (unchanged from rq14 §4):** any cheap model serving Portuguese readers goes through the same gate — 12 committed snapshots × 3 runs, faithfulness ≥ 0.90, plus a real-book Portuguese qualitative citation audit. Family-level multilingual marketing is not a gate-passing artifact.

---

## 6. Embeddings on the cheap providers (gap 5)

**Baseline conclusion stands: do not switch embeddings for cost.** New facts since 09-03, both anti-switches:

- **Gemini Embedding 2** (new multimodal model, official pricing page): text **$0.20/MTok** paid — *more expensive* than OpenAI `text-embedding-3-large@1536` ($0.13, batch $0.065). A batch tier exists (price not captured). Dimension compatibility with `vector(1536)` unverified. No cost case, unproven retrieval case.
- **Qwen embedding APIs:** unchanged picture — Qwen3-Embedding-8B remains a self-host/third-party-host play (~$0.01–0.02/MTok via hosts) whose switch cost is a column + HNSW rebuild decision (rq14 §4), not a bill decision.
- File Search's internal embedding ($0.15/MTok) is bundled with the Google-managed RAG store — not comparable as a standalone embedding API and not adoptable without adopting the store.

---

## 7. Implications for Learny Cycle G (cheaper intelligence)

1. **Order of preference is unchanged at the top:** Haiku 4.5 on quiz (and possibly Ask after the judge gate) is still the first, safest move — native Citations API, zero new vendor, permanent $1/$5. Gemini does not beat it on 2027 economics ($0.018 vs $0.012 per cited turn) and cannot match its citation story.
2. **Gemini 3.8 Flash is the one new SKU worth an eval slot** — as the *non-Chinese economy rung* between Haiku and the Fireworks-hosted Chinese flash tiers. It rides the already-planned `OpenAICompatibleGenerationAdapter` (`base_url` swap), supports batch (50% off) for quiz-shaped load, and has the cleanest data terms in the sub-$1 band (US vendor, paid-tier no-training, DPA — with the EEA-only-paid caveat). **Gate it exactly as rq14 §4 requires**, and remember: no citations API, so prompt-id + grounding intersect, and `reasoning_effort` is the effort lever (thinking is billed in the output price; `minimal` is unsupported).
3. **Do not bake the intro price into any pro-forma.** $0.75/$3.75 is contractually a 2026-only rate; the same page states $1.50/$7.50 from 2027-01-01. Model Gemini's value as "half-price-for-2026 Haiku alternative with 4× the context", not as a structural cost win. The cache-storage hourly fee also changes the teach-session caching math slightly vs Anthropic's write-multiplier model — rerun rq15 §1 arithmetic before claiming parity.
4. **GLM-5.3-Flash post-promo list ($0.15/$0.50) is the true cheap floor** — still ~5× under Gemini's 2026 price. Its Learny path remains Fireworks-US (est. ~$0.22/$0.75 with the US-only surcharge), eval-gated, never `api.z.ai` for default traffic. The Z.AI coding plan is off the table (terms + endpoints + model allowlist are coding-tool-specific).
5. **DeepSeek V4 Flash / MiniMax M3 rows carry forward unchanged** (MiniMax's discount now permanent; DeepSeek untouched). They remain rq14's Move 2/Move 8 candidates behind the same gate.
6. **Embeddings: closed.** Gemini Embedding 2 is pricier than the incumbent; nothing challenges "keep `text-embedding-3-large@1536` until a retrieval A/B wins".
7. **Free tiers are dev tooling, not product capacity:** Gemini's free quota trains on content and allows human review; GLM-4.7-Flash free tier is a CN 1P. Neither may see user book text.

---

## Sources (all accessed 2026-09-07)

- Gemini Developer API pricing (official): https://ai.google.dev/gemini-api/docs/pricing — Gemini 3.8 Flash / 3.7 / 3.6 / 3.5 / Flash-Lite / Pro prices, batch, caching, free-tier data-use flags, grounding quotas
- Gemini 3.8 Flash model page (official): https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash — context 1,048,576/65,536, thinking levels, capability list
- Gemini API release notes (official): https://ai.google.dev/gemini-api/docs/changelog — 3.8 Flash GA 2026-09-02
- Gemini OpenAI compatibility (official): https://ai.google.dev/gemini-api/docs/openai — `…/v1beta/openai/` endpoint, `reasoning_effort`, batch compat
- Gemini File Search docs (official): https://ai.google.dev/gemini-api/docs/file-search — managed RAG, `file_citation` annotations, chunking
- Gemini API terms (official): https://ai.google.dev/gemini-api/terms — unpaid vs paid data use, human review, EEA/CH/UK paid-only clause
- Gemini rate limits (official): https://ai.google.dev/gemini-api/docs/rate-limits — per-model quotas no longer published on docs (deferred to AI Studio UI); page updated 2026-09-02
- Z.AI pricing (official): https://docs.z.ai/guides/overview/pricing — GLM-5.3-Flash promo $0.075/$0.25 ending 2026-09-09 24:00 UTC+8; list $0.15/$0.50; full GLM price list
- Z.AI GLM Coding Plan FAQ (official): https://docs.z.ai/devpack/faq — coding-tools-only restriction, `api.z.ai/api/anthropic` and `api.z.ai/api/coding/paas/v4` endpoints, GLM-5.3/-Flash only, 5-hour cycles
- Z.AI Coding Plan overview (official): https://docs.z.ai/devpack/overview — plan structure
- DeepSeek pricing (official): https://api-docs.deepseek.com/quick_start/pricing/ — V4 Flash/Pro, off-peak windows, unchanged since 09-03
- MiniMax pay-as-you-go pricing (official): https://platform.minimax.io/docs/guides/pricing-paygo.md — M3 "Permanent 50% off", M2.7 unchanged, Priority tier
- Alibaba Cloud Model Studio model catalog (official): https://www.alibabacloud.com/help/en/model-studio/models — `qwen3.8-flash` existence (no prices shown)
- Artificial Analysis, Gemini 3.8 Flash (aggregator, unverified): https://artificialanalysis.ai/models/gemini-3-8-flash — II 47, 280.8 tok/s, TTFT 12.74 s, 90% cache discount
- Artificial Analysis, Portuguese language index (aggregator, unverified top-5 only): https://artificialanalysis.ai/models/multilingual/portuguese
- BenchLM LLM pricing comparison (aggregator, unverified): https://benchlm.ai/llm-pricing — "Qwen3.7 Flash $0.03/$0.13" claim
- Fireworks US-only serverless (official, carried from rq14): https://docs.fireworks.ai/serverless/us-only-serverless
- Baseline docs: `docs/research/2026-09-03/rq14-multi-provider-models.md`, `docs/research/2026-09-03/rq15-ai-cost-optimization.md`

**Verification notes / flagged uncertainties:** Gemini free-tier per-model RPM/RPD are not published on the docs (AI Studio UI only). Fireworks US `glm-5p3-flash-us` price is an estimate from the documented +50% US-only rule, not read off Fireworks' page today. The full AA Portuguese table did not render beyond the top 5 — cheap-model placements unverified. `gemini-3.1-flash-lite` and `gemini-3.5-flash` context windows were not individually verified. The benchlm "Qwen3.7 Flash" price is an aggregator claim; DashScope's own price table was not reachable in this pass. Kimi pricing not re-verified today.
