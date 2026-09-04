# RQ14 — Multi-provider strategy and the 2026 model landscape

*Research date: 2026-09-03. Scope: whether Learny should diversify beyond OpenAI embeddings + Anthropic generation, with which models, hosted where, and behind which architecture — without making LangChain/LiteLLM the product core (ADR-0009). Prices are USD per 1M tokens (in / out) unless noted. Snapshot; re-check vendor pages before an RFC lands.*

## TL;DR

**Diversify generation, not embeddings, and not via Chinese first-party APIs.** GLM-5.3 is real (Z.AI flagship, 1M context, `$1.40` / `$4.40`). The cheap Chinese-origin models (DeepSeek V4 Flash, GLM-5.3-Flash, MiniMax M2.7/M3) are often **~8–20× cheaper** than Claude Sonnet 4.6 (`$3` / `$15`) on cache-miss tokens. **Kimi K3 is not cheap** (`$3` / `$15`, same sticker as Sonnet 4.6 and *above* Sonnet 5’s now-permanent `$2` / `$10`). Learny’s product is **cited answers you can click**; Claude’s native Citations API plus the existing grounding intersect (ADR-0020 / ADR-0003) is still the right primary for Ask/Teach. A cheap model that fabricates citations is a product-killer — gate every new model on the nightly judged eval (faithfulness ≥ 0.90, relevancy ≥ 3.1, `citation_valid` = 100% on the 12 snapshots). **Do not** send user book text to `api.z.ai` / `api.deepseek.com` / `api.moonshot.ai` / DashScope / MiniMax-CN for a public multi-tenant instance. **Do** use US-hosted open-weight inference (Fireworks US-only, Together) as the economy/fallback path. Architecture: keep Learny-owned ports; add a thin OpenAI-compatible adapter; **do not** put LiteLLM, OpenRouter, or Portkey in the composition root. First cycle-sized win is **within Anthropic** (Haiku 4.5 for quiz / drafts) — no new SDK, same citations shape.

---

## 1. Model landscape (verified 2026-09-03)

Hosting shorthand: **1P** = vendor’s own API; **OR** = OpenRouter; **FW** = Fireworks (global + [US-only](https://docs.fireworks.ai/serverless/us-only-serverless)); **TG** = Together AI; **GQ** = Groq.

| Model | Maker | Hosting | Price in/out $/MTok | Context | Strengths / caveats | Sources |
|---|---|---|---|---|---|---|
| `claude-sonnet-5` | Anthropic | 1P, Bedrock, Vertex, OR | **2 / 10** (intro made permanent 2026-08-10) | 1M | Current Learny default (`LEARNY_GENERATION_MODEL`). Native Citations API. New tokenizer ≈ +30% tokens vs 4.6. | [pricing](https://platform.claude.com/docs/en/about-claude/pricing), [Sonnet 5](https://www.anthropic.com/news/claude-sonnet-5), ADR-0020 |
| `claude-sonnet-4-6` | Anthropic | 1P, clouds, OR | **3 / 15** | 1M, no long-ctx surcharge | ADR-0020 chosen model. Cache hits `$0.30`. | [pricing](https://platform.claude.com/docs/en/about-claude/pricing) |
| `claude-haiku-4-5` | Anthropic | 1P, clouds, OR | **1 / 5** | 200K | Same SDK + Citations API. Best *first* cheap tier. | [pricing](https://platform.claude.com/docs/en/about-claude/pricing) |
| `claude-opus-4-8` | Anthropic | 1P, clouds | **5 / 25** | 1M | Quality ceiling; already the nightly **judge**. | [pricing](https://platform.claude.com/docs/en/about-claude/pricing), `docs/ops/eval-calibration.md` |
| `text-embedding-3-large@1536` | OpenAI | 1P | **0.13** (embed-only) | 8K | Fits `vector(1536)`; MIRACL 54.9. Keep until a retrieval A/B wins. | [model](https://developers.openai.com/api/docs/models/text-embedding-3-large), ADR-0019 |
| `glm-5.3` | Zhipu / Z.AI | 1P (`api.z.ai`), FW (`glm-5p3`, **US** `glm-5p3-us`), OR | **1.40 / 4.40** (cache `$0.26`) | 1M (max out 128K) | **Exists.** Forced thinking; OpenAI-compatible. Coding/agent-strong; *not* 5–20× cheaper than Sonnet 5. | [Z.AI pricing](https://docs.z.ai/guides/overview/pricing), [GLM-5.3](https://docs.z.ai/guides/llm/glm-5.3), [FW US](https://docs.fireworks.ai/serverless/us-only-serverless) |
| `glm-5.3-flash` | Z.AI | 1P, FW US `glm-5p3-flash-us` | **0.15 / 0.50** (promo 50% off until 2026-09-09 24:00 UTC+8) | 1M | Real cheap GLM. Forced thinking. | [Z.AI pricing](https://docs.z.ai/guides/overview/pricing) |
| `glm-4.7` / `glm-4.6` / `glm-4.5` | Z.AI | 1P, OR | **0.60 / 2.20** | up to 1M (4.7+) | Still listed. Air: `$0.20` / `$1.10`. Flash tiers **free** (rate limits unpublished). | [Z.AI pricing](https://docs.z.ai/guides/overview/pricing) |
| `kimi-k3` | Moonshot | 1P (`api.moonshot.ai`), FW **US** `kimi-k3-us` ($3.30 / $16.50), OR, open weights | **3.00 / 15.00** (cache `$0.30`) | 1,048,576 | 2.8T MoE, native multimodal. **Same $ as Sonnet 4.6.** Weights: [MoonshotAI/Kimi-K3](https://github.com/MoonshotAI/Kimi-K3). | [K3 pricing](https://platform.moonshot.ai/docs/pricing/chat-k3), [FW pricing](https://docs.fireworks.ai/serverless/pricing) |
| `kimi-k2.6` | Moonshot | 1P, FW, OR | **0.95 / 4.00** | 256K | Previous flagship; actually the cheap Kimi. | [BenchLM snapshot](https://benchlm.ai/moonshot/api-pricing) |
| `deepseek-v4-flash` (0731) | DeepSeek | 1P `api.deepseek.com`; FW `$0.22` / `$0.66` + **US**; TG US (`$0.14` / `$0.28` listed); OR; Vertex MaaS | 1P off-peak **0.22 / 0.66**, peak **0.44 / 1.32** (cache hit `$0.007` off-peak); 1M ctx, 384K max out | Workhorse. `deepseek-chat` / `deepseek-reasoner` **retired 2026-07-24**. OpenAI *and* Anthropic-compatible 1P. | [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/), [V4 news](https://api-docs.deepseek.com/news/news260424/), [Together DeepSeek](https://www.together.ai/models-providers/deepseek) |
| `deepseek-v4-pro` (0813) | DeepSeek | 1P, FW `$1.32` / `$3.96`, TG, OR | 1P off-peak **0.66 / 1.98**, peak **1.32 / 3.96** | 1M | Closer to GLM-5.3 price, still under Opus. | [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/) |
| Qwen3-Max | Alibaba | DashScope, OR | **0.78 / 3.90** | 262K | Closed flagship; multilingual + RAG-oriented marketing. | [OpenRouter](https://openrouter.ai/qwen/qwen3-max) |
| `qwen/qwen3-235b-a22b-2507` | Alibaba | OR, US hosts | **0.09 / 0.55** | 262K | Open-weight instruct; ~30× cheaper than Sonnet 4.6. | [OpenRouter pricing](https://openrouter.ai/qwen/qwen3-235b-a22b-2507/pricing) |
| Qwen3-Embedding-8B | Alibaba | HF, DeepInfra, Cloudflare, Novita | ~**0.01–0.02** embed; self-host cheaper | 32K; native **4096-d**, **MRL** (custom dims) | Official MTEB multilingual **70.58, #1 as of 2025-06-05**. PT-friendly. Dim mismatch unless MRL@1536 is eval’d. | [GitHub](https://github.com/QwenLM/Qwen3-Embedding) |
| MiniMax-M2.7 | MiniMax | 1P `api.minimax.io` (OpenAI + Anthropic-compat), OR, Groq Enterprise, TG | **0.30 / 1.20** (cache read `$0.06`) | 204,800 combined | Cheap agentic/coding. Anthropic-compat useful. | [MiniMax paygo](https://platform.minimax.io/docs/guides/pricing-paygo.md), [API overview](https://platform.minimax.io/docs/api-reference/api-overview) |
| MiniMax-M3 | MiniMax | 1P, TG, OR | **0.30 / 1.20** (≤512k in, promo); **0.60 / 2.40** above | 1M | Current M-series frontier. | [paygo](https://platform.minimax.io/docs/guides/pricing-paygo.md), [Together M3](https://www.together.ai/models/minimax-m3) |
| GPT-5 (API) | OpenAI | 1P, Azure, OR | ~**1.25 / 10** | 400K | Already an embedding vendor. No Claude-shaped Citations API (ADR-0020 rejected this). | aggregators 2026-09-02; confirm [OpenAI pricing](https://openai.com/api/pricing) before RFC |
| Groq MiniMax M2.7 / Qwen 3.6–3.8 27B | Groq | GQ (US LPUs) | MiniMax Enterprise (sales); Qwen3.6-27B **0.60 / 3.00** | 131K | Fast; **not** full DeepSeek V4 / Kimi K3 / GLM-5.3. Distills ≠ frontier. | [Groq models](https://console.groq.com/docs/models) |

**Illustrative cost vs Sonnet 4.6** for a typical cited turn (~8k in / 800 out, cache miss): Sonnet 4.6 ≈ `$0.036`; Sonnet 5 ≈ `$0.024` before tokenizer inflation; Haiku 4.5 ≈ `$0.012` (~3×); DeepSeek V4 Flash off-peak ≈ `$0.0023` (~15×); GLM-5.3-Flash list ≈ `$0.0016` (~22×); MiniMax M2.7 ≈ `$0.0034` (~10×); **Kimi K3 ≈ `$0.036` (no savings)**; GLM-5.3 ≈ `$0.015` (~2×, in Sonnet 5’s band). Prompt caching (Claude 90% hit discount; DeepSeek cache hit `$0.007`) dominates teaching-turn economics more than the headline 5–20× claim.

**GLM series, verified:** GLM-4.5 / 4.6 / 4.7 still sold; GLM-5, 5.1, 5.2, **5.3** and **5.3-Flash** are the 2026 flagship line. There is no “GLM-5.3” vaporware.

---

## 2. Privacy: Chinese 1P vs US-hosted open weights

This is the decision that matters more than which MoE wins a coding bench.

| Path | Where inference runs | Send Learny book text? |
|---|---|---|
| Z.AI `api.z.ai` / `open.bigmodel.cn`, Moonshot `api.moonshot.ai`, DeepSeek `api.deepseek.com`, DashScope, MiniMax CN | China / vendor-controlled Asia. PIPL, unclear DPA for a public EU/US tenant, copyrighted books as prompts. | **No** for the hosted multi-tenant product. Optional later as an explicit “route to CN” power-user toggle with consent copy — not a default. |
| Fireworks **US-only** (`https://us.api.fireworks.ai`): Kimi K3, DeepSeek V4 Flash 0731, GLM 5.2/5.3 + Flash | US. From 2026-09-01, new US-only SKUs are **+50%** vs global (Kimi K3 US already +10%: `$3.30` / `$16.50`). Default ZDR for open models. | **Yes**, after eval. This is the intended cheap/fallback host. [US-only](https://docs.fireworks.ai/serverless/us-only-serverless), [ZDR](https://docs.fireworks.ai/guides/security_compliance/data_handling) |
| Together AI DeepSeek / MiniMax M3 | US infra, SOC 2 Type II, HIPAA, no retention by default. | **Yes**, second US host. [Together DeepSeek](https://www.together.ai/models-providers/deepseek) |
| Groq | US LPUs. MiniMax M2.7 Enterprise + Qwen small; DeepSeek **distills** historically, not V4 Flash full. | Latency lab, not a citation-faithfulness primary. |
| OpenRouter default routing | **Unknown downstream host** unless `provider.only` / `zdr` / `data_collection: deny` / enterprise in-region. 5.5% credit fee; BYOK after 1M req/mo is 5% of catalog cost. | **Eval shopping and OSS demos only**, never the production default for books. [provider routing](https://openrouter.ai/docs/guides/routing/provider-selection), [sovereign AI](https://openrouter.ai/docs/guides/features/sovereign-ai) |

Geopolitics is not a vibe: user EPUBs are copyrighted works. Routing them to a CN 1P is a different product promise than routing weights hosted in the US. Treat those as two different providers even when the model card is identical.

---

## 3. Multi-provider architecture (no LangChain core)

Learny already has the right shape: `GenerationPort` / `EmbeddingPort` / `QuizGenerationPort` in `backend/app/domain/ports.py`, adapters selected at the composition root, grounding as a **single post-generation intersect** (ADR-0003/0020). Multi-provider is **decision-gated**, not architecturally blocked.

| Option | What it is | Evidence | Fit for Learny |
|---|---|---|---|
| **A. Thin extra adapters + task router (recommended)** | New `OpenAICompatibleGenerationAdapter` (`base_url` + `model` + key). Application service picks adapter by task (answer vs quiz vs fallback). Same grounding. | How v2 already swapped providers (ADR-0007). Vercel’s *idea* of a registry — aliases, not a framework — maps cleanly: [createProviderRegistry](https://ai-sdk.dev/docs/reference/ai-sdk-core/provider-registry). | **Yes.** No new orchestration core. One adapter covers Fireworks, Together, Groq, MiniMax 1P, DeepSeek 1P, OpenRouter-for-eval. |
| **B. LiteLLM proxy in Compose** | Self-hosted OpenAI-compatible gateway: YAML routes, retries, fallbacks, virtual keys, budgets. | [Fallbacks](https://docs.litellm.ai/docs/proxy/reliability), [routing](https://docs.litellm.ai/docs/routing-load-balancing). ~46k★ OSS. | **Edge-only, later.** Useful if BYOK + per-user spend caps arrive. Putting it *in front of* the ports makes LiteLLM the orchestrator (ADR-0009 smell). Do not import `litellm` in `application/`. |
| **C. OpenRouter as the only SDK** | One key, 400+ models, built-in fallbacks, `provider.order` / `ignore` / `zdr`. | [Provider routing](https://openrouter.ai/docs/guides/routing/provider-selection). | **Lab, not prod.** Extra hop sees every book chunk. Default load-balancer can pick a logging host. Cursor/Poe-shaped catalog is the wrong UX. |
| **D. Portkey OSS gateway** | Apache-2.0 gateway, fallbacks, guardrails; SaaS dashboard optional. | [Portkey-AI/gateway](https://github.com/Portkey-AI/gateway), [fallbacks](https://portkey.ai/docs/product/ai-gateway/fallbacks). | Same as LiteLLM: extra process. Stronger observability SaaS; weaker reason to add it before product-level routing exists. |
| **E. Vercel AI SDK in Next.js** | TS provider registry + streaming. | [Provider management](https://ai-sdk.dev/docs/ai-sdk-core/provider-management). | Frontend already uses UI Message Stream. Generation must stay **FastAPI-owned** (ADR-0017). Steal the *registry metaphor*, not the SDK as backend core. |

**How big products present models (steal the pattern, not the zoo):**

- **Cursor** — power-user picker; 2026 UI moved *effort* above the raw model list and users hated losing the model name ([forum](https://forum.cursor.com/t/model-selector-in-chat-is-worse-with-new-update/167298)). Learners are not IDE users. If Learny ever shows a control, show **Quality / Balanced / Economy**, not `glm-5p3-us`.
- **Perplexity** — small curated sheet, not 200 SKUs ([interaction pattern](https://60fps.design/shots/perplexity-model-selection-sheet-morph-interaction)).
- **Poe** — catalog-as-product. Wrong. Learny’s differentiator is grounded books, not model tourism.
- **Readwise Ghostreader** — default cheap included model, **BYOK** for stronger ones ([docs](https://docs.readwise.io/reader/docs/faqs/ghostreader)). Closest analogue for a later cycle.

**What multi-provider actually buys Learny**

1. **Cost tiering.** Quiz deck gen and teach-turn drafts are high-volume and already QC’d (verbatim containment, embedding dedup). Haiku or a gated Flash model can take that load; cited Ask stays on Sonnet.
2. **Outage fallback.** The 2026-09-03 walkthrough already saw Anthropic `400` wipe a conversation. A second adapter that is *eval-gated* and grounding-enforced beats a retry loop on a dead 1P.
3. **BYOK (later).** Self-hosters and power users bring Anthropic/OpenAI/Fireworks keys. Store encrypted, never log (existing redaction filter). Not a public-launch blocker.
4. **Quality vs cost setting.** Product copy, not a model menu. Maps to the matrix below.

It does **not** buy better citations by default. That is the risk section.

### What Learny already has (do not rebuild)

- **Ports:** `EmbeddingPort`, `GenerationPort`, `QuizGenerationPort` in `backend/app/domain/ports.py`. v6 collapsed answer/teaching into one `GenerationPort`. Quiz stays a separate port — that is the seam for Haiku-vs-Sonnet without a boolean `is_quiz` on the answer adapter.
- **Composition root:** `LEARNY_GENERATION_PROVIDER` / `LEARNY_EMBEDDING_PROVIDER` (`local` | `anthropic` | `openai`). Unrecognized values fail loud. Default generation model in config is already `claude-sonnet-5`.
- **Grounding:** cited ids ∩ retrieved evidence; empty set → `not_found_in_source`. Provider citation JSON must not leak into domain (ADR-0020).
- **Eval:** golden fixtures (ADR-0016), nightly live judge + keyed retrieval arm, `/dev/evals` dashboard, `ab.py` A/B. Thresholds live in `backend/app/eval/judge.py` (`FAITHFULNESS_MIN = 0.90`).
- **Embedding versioning:** `corpus_chunks.embedding_model` like `text-embedding-3-large@1536`; stale vectors are skipped by the semantic arm (ADR-0019).

The missing piece is not a gateway. It is (a) a second generation adapter that speaks Chat Completions, (b) a task→adapter map in the application service, (c) an eval promotion checklist.

### Worked token economics (order-of-magnitude)

Assume one cited Ask: 8,000 input tokens of system + evidence documents + 800 output tokens, cache miss. Teaching with a warm 90% Claude cache is cheaper; quiz items are shorter.

| Path | Input $ | Output $ | Turn $ | vs Sonnet 4.6 |
|---|---|---|---|---|
| Sonnet 4.6 `$3/$15` | 0.024 | 0.012 | **0.036** | 1.0× |
| Sonnet 5 `$2/$10` (ignore tokenizer) | 0.016 | 0.008 | **0.024** | 0.67× |
| Sonnet 5 + ~30% more tokens | ~0.021 | ~0.010 | **~0.031** | ~0.86× |
| Haiku 4.5 `$1/$5` | 0.008 | 0.004 | **0.012** | 0.33× |
| GLM-5.3 `$1.40/$4.40` | 0.011 | 0.004 | **0.015** | 0.42× |
| Kimi K3 `$3/$15` | 0.024 | 0.012 | **0.036** | 1.0× |
| DeepSeek V4 Flash off-peak `$0.22/$0.66` | 0.0018 | 0.0005 | **0.0023** | 0.06× |
| GLM-5.3-Flash list `$0.15/$0.50` | 0.0012 | 0.0004 | **0.0016** | 0.04× |
| MiniMax M2.7 `$0.30/$1.20` | 0.0024 | 0.0010 | **0.0034** | 0.09× |
| Fireworks Kimi K3 US `$3.30/$16.50` | 0.026 | 0.013 | **0.040** | 1.1× |

At hobby scale these cents do not matter (ADR-0020 already called ~`$0.02`/answer a non-factor). At a **public multi-tenant** instance, quiz-deck generation × N books × N users does. That is why Haiku-on-quiz is the first move and Flash-on-Ask is the last.

---

## 4. Citation-faithfulness risk (product-killer)

Learny’s whole pitch is trustworthy passage-level citations (ADR-0003). Three failure modes, empirically distinct:

1. **Invented citation ids / titles.** Cheap instruct models, given “cite your sources,” will emit `[^3]` or a chapter name that was never in evidence. Learny already **intersects** cited chunk ids with retrieved evidence and drops the rest; if none survive → `not_found_in_source`. That saves the product from *dangling* citations. It does **not** save it from a fluent paragraph that *looks* cited while the surviving citations are the wrong passages.
2. **Post-rationalization.** [Correctness is not Faithfulness in RAG Attributions](https://arxiv.org/pdf/2412.18004) (2024): models attach citations that *happen to* support a claim they would have made anyway. Up to **57%** of citations in that study failed a faithfulness (actual-use) test even when “correct.” Command-R+-class RAG models still did this. A cheaper 2026 model with no native attribution API is not safer.
3. **Prompt-only attribution vs Citations API.** ADR-0020 chose Claude because document blocks + `document_index` map 1:1 onto Learny chunks. OpenAI-compatible Chat Completions have **no equivalent**. The adapter would prompt for chunk ids and rely on grounding + the judge. That is acceptable for quiz/drafts; it is a **higher bar** for Ask.

**Existing gate (use it; do not invent a new one):** nightly `eval.yml` with `LEARNY_EVAL_GATE=1` ([runbook](../../ops/eval-calibration.md)):

| Metric | Threshold | Notes |
|---|---|---|
| Judge faithfulness (answered mean) | ≥ **0.90** | Opus 4.8 judge; declines excluded (ADR-0028) |
| Judge relevancy (answered mean) | ≥ **3.1** | 1–5 rubric |
| `citation_valid` | **all** scored lines | Deterministic invariant |
| Retrieval recall@1 / @5 / MRR | 0.9 / 1.0 / 0.93 | OpenAI embed arm; irrelevant to a *generation* swap |

**A new generation model may ship to a task only if:**

1. Adapter maps outputs into the existing `GeneratedAnswer` (chunk ids Learny owns — never provider citation JSON in domain).
2. Grounding intersect unchanged.
3. Live judge over the **12 committed replay snapshots** passes the three generation conditions (3 keyed runs, same protocol as 2026-07-31).
4. A book-scale A/B via `app/eval/ab.py` vs `claude-sonnet-5` on at least one real EPUB (Portuguese-primary preferred) shows faithfulness not worse than −0.05 absolute and no increase in “fluent but wrong passage” qualitative samples.
5. Quiz path: answerability is **not gated** today — do not put a new cheap model on deck generation without adding a minimum answerability floor or keeping the verbatim-quote QC as a hard fail.

**Promotion checklist (copy into the RFC):**

- [ ] Adapter under `infrastructure/answering/` (or `quiz/`); SDK import only there; lazy client.
- [ ] Prompt asks for Learny chunk ids; thinking/reasoning tokens stripped before persist/stream.
- [ ] `citation_valid` 12/12 on snapshots × 3 runs; faithfulness mean ≥ 0.90; relevancy mean ≥ 3.1.
- [ ] Manual pass: 10 Ask turns on a real book — every inline `[^n]` click-jumps; zero invented titles.
- [ ] `not_found` sentinel still fires on the three committed not-found snapshots (no “helpful” hallucination).
- [ ] Host is US (Fireworks US-only or Together) **or** Anthropic/OpenAI 1P — CN 1P requires an explicit RFC exception.
- [ ] Failure mode on fallback: original error is logged with `request_id`; user sees retry, not a silent model swap that changes citation style mid-thread.

**Embedding switch cost (ADR-0019 already solved the mechanics, not the bill):** each chunk stores `embedding_model` (`text-embedding-3-large@1536`). Mixed state → lexical-only, not vector soup. Switching to Qwen3-Embedding-8B native 4096-d **requires a column + HNSW rebuild** (pgvector HNSW limit 2000-d unless `halfvec`). MRL to 1536 *might* fit the column — **unproven on Learny’s Portuguese golden retrieval set**. Cost of re-embed is tiny (`$0.13`/MTok; ADR-0019 ≈ `$0.04`/book). Cost of a silent retrieval regression is the product. Do not dual-run two embedding spaces in one query.

---

## 5. Recommended provider matrix and adoption path

**Principle:** primary = citation-native + eval-proven; fallback = US-hosted, OpenAI-compatible, eval-gated; never CN 1P as default.

| Task | Primary | Fallback (same request, after 5xx/429/timeout — not after a grounded `not_found`) | Economy (explicit user/setting) |
|---|---|---|---|
| Cited Ask | `claude-sonnet-5` (Anthropic Citations API) | `claude-opus-4-8` *or* Fireworks-US DeepSeek V4 Flash **only after it passes the gate** | Fireworks-US `glm-5p3-flash-us` or DeepSeek V4 Flash, gated |
| Teach turns | Sonnet 5 + existing prompt cache | Same as Ask | Haiku 4.5 (same citations) first; Flash only after teach-snapshot eval |
| Quiz / note-card suggest | Haiku 4.5 | Sonnet 5 | Gated Flash / MiniMax M2.7 on FW/TG |
| LLM judge (nightly) | `claude-opus-4-8` | Do not cheapen the judge | — |
| Embed query + corpus | `text-embedding-3-large@1536` | none (lexical arm already degrades) | Qwen3-Embedding MRL@1536 **only after retrieval A/B** |
| Long-context whole-book (future, not default RAG) | Sonnet 5 1M | Kimi K3 or GLM-5.3 on **Fireworks US** (1M ctx) | DeepSeek V4 Flash 1M US |

**Do not** use Kimi K3 as the economy model. Use it only if a long-context synthesis eval beats Sonnet 5 at similar price.

### Adoption path (decision artifacts)

1. **RFC (v4 cycle, not a stealth settings tweak):** “Task-tiered generation behind existing ports.” Records the matrix, the US-host constraint, and the eval gate as merge criteria. Amends the “multi-provider / BYOK” bullet already listed as future work in `README.md`.
2. **ADR amending ADR-0020** (do not silently replace it): Claude remains the cited-answer primary; additional adapters are allowed; `LEARNY_GENERATION_PROVIDER` grows (`anthropic` \| `openai_compat` \| `local`) without leaking model ids into domain. Optionally a one-pager ADR “US-hosted open weights only for default book inference.”
3. **Do not amend ADR-0019** until a retrieval RFC with MRL@1536 numbers on the golden Portuguese set. Voyage-4 remains the named alternative (still no 1536-d).
4. **Eval calibration runbook** (`docs/ops/eval-calibration.md`): add a “promoting a new generation adapter” section — 3× snapshot gate + ab.py arm + qualitative citation audit. Re-derive thresholds if snapshots are re-recorded (already flagged as owed).
5. **No new provider SDK** until the RFC is accepted (current lock). The OpenAI Python client already in-tree can talk to Fireworks/Together/Groq `base_url`s — that is an adapter, not a new SDK. A dedicated `fireworks`/`together` package is unnecessary.

**Suggested RFC shape (one cycle, not a platform rewrite):**

- Settings: `LEARNY_GENERATION_FALLBACK_PROVIDER`, `LEARNY_GENERATION_FALLBACK_BASE_URL`, `LEARNY_GENERATION_FALLBACK_MODEL`, `LEARNY_QUIZ_GENERATION_MODEL` (Haiku).
- Factory: if primary raises a classified transport error, call fallback once; do not recurse.
- Stream path: fallback must speak the same SSE / UI Message Stream contract or not be offered on `/turns/stream`.
- Privacy copy for the public instance: “Book text is sent to Anthropic (US/global) for answers. Economy mode uses US-hosted open-weight inference (Fireworks/Together), not Chinese vendor APIs.”
- Out of scope for that RFC: BYOK UI, user model picker, embedding swap, LiteLLM sidecar, OpenRouter in prod.

---

## 6. Cycle-sized moves

Each item is one spec-driven PR-sized cycle.

### Move 1 — Haiku 4.5 on `QuizGenerationPort` (and optional teach-draft)

**Why recommend:** Same Anthropic SDK and Citations/grounding path already in tree. `$1` / `$5` is ~3× cheaper than Sonnet 4.6 with **zero new vendor, zero CN data path, zero new citation scheme**. Quiz items already have verbatim-quote QC. Highest ROI for public-launch token burn. Settings already have `LEARNY_GENERATION_MODEL`; quiz can take its own setting.

**Why not:** Haiku 200K vs Sonnet 1M (irrelevant for chunked RAG). Faithfulness can drop on chatty prompts ([RAGLab-style result](https://github.com/sabinbobu/RAGLab): Haiku 0.97 → 0.85 when the prompt got conversational). Must pass the quiz QC + a small judged sample before flipping the default. Does not fix Anthropic 1P outages.

### Move 2 — `OpenAICompatibleGenerationAdapter` + Fireworks US DeepSeek V4 Flash as **outage fallback**

**Why recommend:** One adapter, many hosts. Fireworks US has the exact SKU (`deepseek-v4-flash-0731-us`) and ZDR. Together is a second US vendor at `$0.14` / `$0.28`. Fallback only on transport/5xx, never on `not_found`. Directly addresses the observed “Anthropic 400 → conversation deleted” failure. Still hexagonal.

**Why not:** No native Citations API — prompt-id scheme + grounding only. Must pass the §4 gate or it ships as “sorry, try again” worse than today’s error. Adds a second key and a residency runbook. Do not silently swap the Ask primary to Flash to save money.

### Move 3 — Product control: Quality vs cost (not a model picker)

**Why recommend:** Matches Perplexity/Readwise, not Poe/Cursor. Maps onto Move 1–2. Honest copy: Economy may refuse more and cite more conservatively because grounding is stricter on weak models.

**Why not:** Premature if only one real generation adapter exists. Invites “why isn’t GLM in the menu?” support load. Skip until Move 2 is gated green.

### Move 4 — OpenRouter (or LiteLLM) **eval harness only**

**Why recommend:** Fast A/B of Flash vs MiniMax vs Qwen-235B-instruct on the 12 snapshots without N vendor accounts. LiteLLM fallbacks docs are the reference implementation of “retry then next model” ([reliability](https://docs.litellm.ai/docs/proxy/reliability)).

**Why not:** Production book traffic through OpenRouter is a third-party processing disclosure. LiteLLM-in-Compose is another moving part on a VPS that already runs Caddy+Celery. Keep it off the request path.

### Move 5 — BYOK

**Why recommend:** Self-hosters (Compose on a VPS) already hold keys; public-cloud tenants who care about residency will demand it. Readwise proved the pattern. Virtual keys / budgets are why people later add LiteLLM.

**Why not:** Encryption-at-rest, per-user key UX, abuse (user’s key vs Learny’s), and support. Not a launch blocker. After Moves 1–2.

### Move 6 — Qwen3-Embedding MRL@1536 retrieval A/B

**Why recommend:** Official multilingual MTEB lead (70.58, Jun 2025); Portuguese is a first-class Qwen language; MRL might avoid a column migration; ADR-0019 versioning makes a switch operationally safe. Reranker sibling (Qwen3-Reranker-8B) is the recorded pgvector escape hatch.

**Why not:** Unproven 1536-d quality vs `large@1536`. Instruction-aware embeddings change query/document symmetry (Voyage was rejected partly for `input_type`). Re-embed the library. **Do not** couple this to generation diversification.

### Move 7 — GLM-5.3 or Kimi K3 as Ask primary via Z.AI / Moonshot 1P

**Why recommend:** Strong long-context/coding marketing; GLM-5.3 is cheaper than Opus; Kimi K3 matches Sonnet 4.6 price with 1M ctx and open weights.

**Why not:** **Default CN inference of user books.** Kimi K3 is not an economy win. Neither has Claude’s Citations API. Fireworks US exists for the weights — if we ever try GLM-5.3 on Ask, it is `glm-5p3-us` after the gate, not `api.z.ai`.

### Move 8 — Promote DeepSeek V4 Flash (US) to Economy Ask default

**Why recommend:** ~15× cheaper; 1M context; US host; Anthropic-compatible 1P exists if we ever accept CN (we should not). Biggest cost lever at public scale.

**Why not:** Citation-faithfulness unknown on Learny’s snapshots. Thinking-mode latency and leaked chain-of-thought in the UI. Peak/off-peak 1P pricing is operationally annoying (FW/TG flatten this). Only after Move 2’s gate is green *and* a real-book qualitative audit.

---

## Bottom line for RFC-004

Diversify **tasks and hosts**, not “add a model zoo.” Keep Claude on the cited money path; use Haiku inside the same port for quiz; add one OpenAI-compatible adapter aimed at **Fireworks US / Together**; gate every new generation SKU on the existing nightly judge; leave embeddings on OpenAI until retrieval math says otherwise; treat Chinese 1P and US-hosted open weights as different products. That is the quality-first public-launch posture. They are not the same provider just because the weights share a name.

## Primary sources (re-check before RFC)

- Anthropic list prices: https://platform.claude.com/docs/en/about-claude/pricing
- Z.AI GLM prices + GLM-5.3: https://docs.z.ai/guides/overview/pricing · https://docs.z.ai/guides/llm/glm-5.3
- DeepSeek V4: https://api-docs.deepseek.com/quick_start/pricing/ · retirement note https://api-docs.deepseek.com/news/news260424/
- Kimi K3: https://platform.moonshot.ai/docs/pricing/chat-k3 · weights https://github.com/MoonshotAI/Kimi-K3
- MiniMax paygo: https://platform.minimax.io/docs/guides/pricing-paygo.md
- Fireworks US-only + ZDR: https://docs.fireworks.ai/serverless/us-only-serverless · https://docs.fireworks.ai/guides/security_compliance/data_handling · https://docs.fireworks.ai/serverless/pricing
- Together DeepSeek (US, SOC2/HIPAA): https://www.together.ai/models-providers/deepseek
- Qwen3-Embedding: https://github.com/QwenLM/Qwen3-Embedding
- OpenRouter routing/ZDR: https://openrouter.ai/docs/guides/routing/provider-selection · https://openrouter.ai/docs/guides/features/sovereign-ai
- LiteLLM fallbacks: https://docs.litellm.ai/docs/proxy/reliability
- Portkey gateway: https://github.com/Portkey-AI/gateway
- Vercel AI SDK registry: https://ai-sdk.dev/docs/reference/ai-sdk-core/provider-registry
- Citation faithfulness vs correctness: https://arxiv.org/pdf/2412.18004
- Learny: ADR-0009, ADR-0019, ADR-0020; `docs/ops/eval-calibration.md`
