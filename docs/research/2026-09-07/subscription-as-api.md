# Subscription plans used as an API: terms, risks, and legitimate alternatives

*Research date: 2026-09-07. Scope: whether Learny's public multi-tenant backend could serve generation traffic through a consumer/coding subscription (Z.AI GLM Coding Plan, Claude Pro/Max OAuth bridges, ChatGPT Plus unofficial APIs, Gemini free tiers) to avoid API usage costs — what the terms actually say, what enforcement looks like, what breaks mid-semester if the path dies, and which ToS-clean cheap tiers come closest to the same cost. Companion to RQ15 (legitimate cost levers — effort levels, prompt caching, 50% batch API — are covered there and not repeated) and RQ14 (GLM/Z.AI and DeepSeek API pricing rows, accessed 2026-09-03). Evidence is marked inline: **[quoted]** = verbatim from an official page fetched 2026-09-07; **[official]** = official page, paraphrased; **[community]** = blog/Reddit/HN signal, not vendor-confirmed.*

---

## TL;DR

**Verdict: no subscription-as-API route is legitimate — or even operationally sane — for a public multi-tenant Learny.** The GLM Coding Plan, the only subscription that advertises an API-shaped endpoint, names our exact use case as prohibited in its legal Subscription Terms: *"You shall not use the GLM Coding Plan quota for general-purpose API access or any scenarios outside such tools, including but not limited to directly invoking model APIs from your own applications, bots, websites, SaaS products or other systems"* **[quoted]**, and separately bans serving model capabilities to third parties and any use outside a single natural person's account **[quoted]**. Anthropic bans OAuth-bridge use of Claude Pro/Max and did so at scale in 2025–2026 **[community enforcement, official terms]**. OpenAI's terms prohibit programmatic extraction of ChatGPT outputs **[quoted]**. Google's Gemini API free tier is ToS-clean but tiny, SLA-less, trains on your users' book text, and is not allowed for EEA end users **[quoted]**.

The honest cost conclusion: the ToS-clean near-equivalents already beat the subscriptions on volume. At ~50k generation turns/month (~6k input + ~1k output tokens per turn, per RQ15's call shape), paid Flash-class APIs cost **~$70/month (GLM-5.3-Flash API, with the CN-hosting caveat from RQ14)** to **~$410/month (Gemini 3.x Flash, through 2026-12-31)**, versus ~$1,100 on today's Sonnet 5 configuration before RQ15's levers (~$630–860 after). A GLM Coding Plan Max subscription at ~$160/month **[community-reported tier price]** could not legally carry that traffic at all, and its quota (140k credits/week ≈ roughly 90k–175k Learny-style turns, single account, dynamic concurrency caps) is sized for one heavy interactive developer — with no SLA, non-refundable fees, liability capped at one month's spend, and a self-described risk-control system that rate-limits, freezes, and bans accounts. Keep subscriptions for dev-time coding tools; serve the product from metered APIs; chase startup credits (up to $350k Google Cloud / Anthropic and OpenAI programs) instead of ToS risk.

---

## 1. The GLM / Z.AI coding plan specifically

### What it is and what it costs

- "The GLM Coding Plan is a subscription package designed specifically for AI-powered coding." **[quoted]** Usage scenarios listed are all developer/coding scenarios (code generation, completion, debugging, codebase Q&A, automated task handling) **[quoted]**. The plan works in coding tools "such as Claude Code, Cline, and OpenCode" **[quoted]** ([Overview](https://docs.z.ai/devpack/overview)).
- Entry price: "Starting at just 18 USD per month, with Pro and Max plans designed for high-frequency, complex projects" **[quoted]** ([Overview](https://docs.z.ai/devpack/overview)). Community sources report **Lite ≈ $18 / Pro ≈ $72 / Max ≈ $160** per month **[community — aipricing.guru, distk.in, lorphic.com; tier prices beyond the $18 entry could not be verified on z.ai/subscription, which is a JavaScript app and unreadable as static content]**.
- Models callable through the plan: **GLM-5.3 and GLM-5.3-Flash only**; older model ids are silently re-routed to these two **[official]** ([FAQ](https://docs.z.ai/devpack/faq)).
- Plans moved to a **credits-based system on 2026-07-30**; legacy prompt-based plans are no longer sold to new subscribers **[official]** ([Plan Update Announcement](https://docs.z.ai/devpack/notice/usage-revision)).

### Quota mechanics (credits, 5-hour and weekly limits)

Official ([Overview](https://docs.z.ai/devpack/overview)):

| Plan | 5-Hour Credits | Weekly Credits |
|---|---|---|
| Lite | 2,000 | 10,000 |
| Pro | 12,000 | 60,000 |
| Max | 28,000 | 140,000 |

- Credit formula **[quoted]**: "Model credit usage = (Input tokens × Input multiplier + Cached Input tokens × Cached Input multiplier + Output tokens × Output multiplier) / 10,000". Multipliers: GLM-5.3 = 6.9 / 1.7 / 24 (input / cached input / output); GLM-5.3-Flash = 2.3 / 0.56 / 8.
- Off-peak usage is charged at **50% of the credit rate**; peak is Mon–Fri 14:00–18:00 Singapore time **[quoted]**. A current campaign gives paid-plan users unlimited GLM-5.3-Flash via ZCode 23:00–09:00 SGT **[official tip banner]**.
- Legacy plans (pre-2026-07-30) had "prompts per 5-hour" quotas with weekly caps of 5× the 5-hour limit; community figures of ~120/600/2,400 prompts per 5h circulate for Lite/Pro/Max and are consistent with Z.AI's own note that "one prompt is estimated to invoke the model 15–20 times" **[community + official FAQ fragment]**.

### What endpoints it unlocks

- Anthropic-compatible endpoint for Claude Code (and Goose): `https://api.z.ai/api/anthropic`, configured via `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN` in the tool's settings **[quoted]** ([Claude Code integration](https://docs.z.ai/devpack/tool/claude)).
- OpenAI-compatible-style endpoint for other supported tools: `https://api.z.ai/api/coding/paas/v4` **[official]** ([FAQ](https://docs.z.ai/devpack/faq)).
- "Users subscribed to the Coding Plan can only make calls via the plan's quota in supported tools. **API calls outside the plan are not available.**" **[quoted]** — i.e., the subscription does not include normal pay-as-you-go API balance; the pay-as-you-go API (`api.z.ai`, prices in RQ14) is a separate purchase.

### What the terms actually allow — and forbid

The legal Subscription Terms ([Subscriptions, Fees, and Payment](https://docs.z.ai/legal-agreement/subscription-terms)) are unambiguous. §4 "Usage Scenario Restrictions" **[quoted]**:

> "You understand and agree that the usage quota under GLM Coding Plan is only used within officially supported tools. If the system detects usage through unauthorized or unsupported tools (such as **SDK-based access** or other third-party integrations), some subscription benefits may be restricted to ensure fairness and service stability."

> "You shall not use the GLM Coding Plan quota for general-purpose API access or any scenarios outside such tools, including but not limited to **directly invoking model APIs from your own applications, bots, websites, SaaS products or other systems**, unless you have entered into a separate written agreement with Z.ai."

> "Unless otherwise agreed in writing, you may not resell, sub-resell, repackage, aggregate, proxy or otherwise provide the GLM Coding Plan to any third party, whether on a paid or free basis, nor may you use the GLM Coding Plan to provide **model capabilities as a service to third parties**."

§4 "Personal-Use Only" **[quoted]**: the plan "is tied to a single account and is licensed only to the individual natural person associated with such account"; you "shall not share your account or subscription, or allow any other person (including … your colleagues, friends, customers or any organization) to use your GLM Coding Plan quota."

Enforcement is mechanical and escalating ([Usage Policy](https://docs.z.ai/devpack/usage-policy)) **[quoted]**: violations "may trigger risk control measures, including rate limiting, account freezing, or other restrictions. **Accounts with more than three violations may be banned.**" The same page restricts the plan to "[officially supported tools](https://docs.z.ai/devpack/tool/others)" and prohibits account sharing or multi-user access.

### Rate limits and concurrency

- "Rate (concurrency) limits are tied to your plan tier. The platform dynamically adjusts these limits based on resource availability" **[quoted]**; guidance is **Lite: one project at a time; Pro: 1–2 projects; Max: 2+ projects** **[quoted]** ([Usage Policy](https://docs.z.ai/devpack/usage-policy)). No public RPM/TPM numbers exist; there is no published SLA.
- Commercial terms **[quoted]**: all payments are **non-refundable**; Z.ai may unilaterally change features/prices or discontinue auto-renewal; liability is capped at "the total amount you have spent in the most recent calendar month"; refunds are forfeited on violation ([Subscription Terms](https://docs.z.ai/legal-agreement/subscription-terms) §1, §3, §4, §5).

### Verdict for a multi-tenant web backend

**No — twice over.** (1) A FastAPI backend calling `api.z.ai/api/anthropic` is precisely "SDK-based access … from your own applications … websites, SaaS products", which the terms name as prohibited and detectable. (2) Serving users at all is "providing model capabilities as a service to third parties" from a personal, single-natural-person license. Both independently authorize quota restriction, freezing, or bans. Even setting legality aside, Lite's ~6.7k–12.7k Learny-style turns/month (43k credits ÷ 3.4–6.5 credits/turn, using the official formula with RQ15's ~6k-in/1k-out call shape) and the single-account concurrency guidance (one project) would collapse under multi-tenant load; Pro at 60k weekly credits ≈ 40k–76k turns/month is under our 50k target at zero cache misses. The plan is a legitimate dev-time bargain for coding tools — RQ14's ban on CN-hosted `api.z.ai` for user book text applies to the paid API too.

---

## 2. The "subscription-as-API" pattern elsewhere

### Claude Pro / Max via OAuth bridges and proxies

- Plans: Pro (~$20/mo; ~$17/mo annual) and Max 5x (~$100/mo) / Max 20x (~$200/mo) **[community-reported prices; claude.com/pricing is a JS page not readable here]**. Both include Claude Code with 5-hour rolling session limits plus weekly caps **[official]** ([Max plan](https://support.claude.com/en/articles/11049741-what-is-the-max-plan)).
- Terms (Consumer Terms of Service, effective 2025-10-08, [anthropic.com/legal/consumer-terms](https://www.anthropic.com/legal/consumer-terms)) **[quoted]**: "Except when you are accessing our Services via an Anthropic API Key or where we otherwise explicitly permit it, to access the Services **through automated or non-human means**, whether through a bot, script, or otherwise" is a prohibited use. Also prohibited: "To crawl, scrape, or otherwise harvest data or information from our Services"; "To develop any products or services that compete with our Services … or **resell the Services**." "You may not share your Account login information … You also may not make your Account available to anyone else." API use is governed by separate Commercial Terms — a consumer subscription is not an API entitlement.
- Enforcement **[community]**: a documented 2025–2026 crackdown — takedown notices and bans for using subscription OAuth tokens outside official Claude Code (r/Anthropic [thread](https://www.reddit.com/r/Anthropic/comments/1q9eom1/anthropic_sending_out_takedown_notice_to_all_the/), r/ClaudeAI [thread](https://www.reddit.com/r/ClaudeAI/comments/1qa50sq/anthropic_banning_thirdparty_harnesses_while/)); a February 19 documentation update explicitly banning OAuth token use in third-party tools (r/ClaudeAI [thread](https://www.reddit.com/r/ClaudeAI/comments/1r8t6mn/anthropic_just_updated_claude_code_docs_to_ban/), [Ticker News](https://tickernews.co/anthropic-bans-third-party-tools-from-claude-subscriptions/)); silent blocking of subscription OAuth tokens from third-party tools discussed on [Hacker News](https://news.ycombinator.com/item?id=46549823). Reported outcomes include refunded-and-banned organizations **[community]**.
- Tooling exists and is documented: LiteLLM ships a "[Using Claude Code Max Subscription](https://docs.litellm.ai/docs/tutorials/claude_code_max_subscription)" tutorial that forwards your OAuth token through the gateway — with **no ToS warning at all** — and claude-code-router-style proxies do the same. **Documentation presence is not permission**: the same token use is what the terms prohibit and what the ban wave targeted. Stability depends on an undocumented, actively policed surface.

### ChatGPT Plus via unofficial APIs

- ChatGPT Plus (~$20/mo) includes no API credits; the API is billed separately. OpenAI's [Terms of Use](https://openai.com/policies/row-terms-of-use/) **[quoted]** prohibit: "Automatically or programmatically extract data or Output"; "Interfere with or disrupt our Services, including circumvent any rate limits or restrictions or bypass any protective measures"; and sharing "your account credentials or mak[ing] your account available to anyone else." The [Usage Policies](https://openai.com/policies/usage-policies/) reserve the right to "withhold access where we reasonably believe it necessary to protect our service or users."
- Codex usage inside Plus/Pro is the official analog — it runs only inside OpenAI's own surfaces/agents, not as a generic backend endpoint **[official]**.
- Enforcement **[community]**: less publicly documented than Anthropic's, but account deactivations tied to unofficial-API/reverse-proxy use are repeatedly described in secondary write-ups (e.g., [Manifest.build, "This will get you banned from your ChatGPT subscription"](https://manifest.build/blog/banned-from-chatgpt-subscriptions/)); I did not find a first-hand 2026 Reddit ban report specific to Plus-as-API in this pass — absence of evidence is not permission.

### Gemini: AI Studio free tier vs Gemini Code Assist vs Vertex

- The Gemini API **free tier is a real, ToS-clean API** — but the [Gemini API Additional Terms](https://ai.google.dev/gemini-api/terms) (effective 2026-03-23) **[quoted]** say Google "uses the content you submit to the Services and any generated responses to provide, improve, and develop" its products, that "human reviewers may read, annotate, and process your API input and output," and "**Do not submit sensitive, confidential, or personal information to the Unpaid Services.**" Critically for a public product: "**You may use only Paid Services when making API Clients available to users in the European Economic Area**," and the services are "for developers building with Google AI models for professional or business purposes, **not for consumer use**." No SLA attaches to unpaid services. That makes the free tier unusable as Learny's production primary: users' books are exactly the "confidential information" it tells you not to submit, and Learny would have EEA users.
- Free-tier **rate limits are no longer published** on the docs pages — "limits depend on factors like tier; view them in Google AI Studio" **[official paraphrase]**, per project, resetting midnight Pacific. Community reports describe heavy cuts (Flash 250 → ~20 RPD; Gemini 2.5 Pro free tier removed April 2026) **[community — Google AI Devs Forum, usagebox.com]** — i.e., even the free tier is a moving floor, not a capacity plan.
- **Gemini Code Assist** (free individuals edition) is an IDE coding assistant with per-user daily quotas; the current quotas page documents only Standard/Enterprise Cloud quotas (e.g., 6,000 code requests/user/day, 1,500–2,000 agent-mode requests/day) and no longer describes the individuals edition **[official, [quotas](https://docs.cloud.google.com/gemini/docs/quotas)]**. It is not an app-serving API either way.
- **Vertex AI** is the standard metered path (new-cloud trial credits, then list prices); no meaningful free tier.

### Related datapoint

**GitHub Models — the classic "free inference through an existing subscription" path — was fully retired on July 30, 2026** ("The playground, model catalog, inference API, and BYOK are no longer available to any customer") **[quoted]** ([retirement notice](https://docs.github.com/en/github-models/use-github-models/prototyping-with-ai-models)). Free-adjacent paths get shut down; anything built on them inherits the shutdown date.

---

## 3. Legitimate near-subscription alternatives

All rows assume RQ15's call shape (~6,000 input + ~1,000 output tokens per generation turn → 50k turns ≈ 350M in / 50M out tokens per month) and RQ14/RQ15 pricing. "ToS-clean" means: metered or officially-free API terms that permit application/backend serving.

| Option | Monthly cost shape @ ~50k turns | Rate limits / caps | ToS-clean? | Notes |
|---|---|---|---|---|
| Sonnet 5 + RQ15 levers (effort=low, caching, batch where async) | ~$1,100 list → **~$630–860** after packages A/B | Anthropic published usage tiers; high | **Yes** | Citation-native primary; the levers are already spec'd as cycles 1–5 in RQ15 |
| Haiku 4.5 (quiz, suggestions; Ask only if judge-gated) | ~$550 online; **~$275 batch** | Same tiers | **Yes** | Quiz decks already run this path |
| Gemini 3.x Flash paid API ($0.75 in / $3.75 out through 2026-12-31; doubles 2027-01-01) **[official pricing page]** | **~$410** (through 2026) | Free tier: numbers now unpublished/dynamic, community-reported ~20 RPD on Flash **[community]**; paid tiers generous | **Yes** (paid) | No Citations API → prompt-id + grounding intersect; RQ14 eval gate applies. Free tier: ToS-clean but trains on content, no EEA users, no SLA — eval/demos only |
| GLM-5.3-Flash **pay-as-you-go API** ($0.15 / $0.50 list; 50% promo ended 2026-09-09 per RQ14) | **~$70** | Unpublished API rate limits; credits system separate from coding plan | API yes — **but CN 1P** (RQ14: do not send user books to `api.z.ai`; Fireworks US SKU `glm-5p3-flash-us` is the compliant host at a premium) | Cheapest clean tokens; grounding via prompt-ids + gate |
| DeepSeek V4 Flash off-peak ($0.22 / $0.66; peak 2×; RQ14) | **~$99** (off-peak flush of async work) | Peak/off-peak windows; no SLA issues documented | API yes — **but CN 1P**; Fireworks/Together US hosted instead | Best for batch-shaped Celery work |
| OpenRouter `:free` models | $0 | **20 RPM; 50 requests/day** (<10 credits ever purchased) or **1,000/day** (≥ $10 credits) **[quoted, limits doc]** | **Yes** | Random open models, no citation guarantee; prototype/eval shopping only (RQ14), never production books |
| Groq free/Developer tier (gpt-oss-120b, qwen3-27b) | ~$0 | ~30 RPM / ~1,000 RPD / ~200k tokens/day per model **[official docs, Developer-plan base limits; free-plan tab values not published in the docs page]** → ≈ 850 turns/month | **Yes** | 200k TPD is a toy ceiling for us; latency lab (RQ14) |
| GitHub Models free tier | — | — | **Retired 2026-07-30** | Formerly the easy free path; gone |
| Startup / cloud credit programs | **$0 for months** | Program-defined | **Yes** | [Google Cloud AI Startup Program](https://cloud.google.com/startup/ai) up to **$350k** credits; Anthropic "Claude for Startups" (public application, VC funding not required per secondary guides); OpenAI credits mostly via VC partners **[community/secondary]**. The single best ROI move at Learny's stage |

**Reading:** the subscription fantasy saves at most a few hundred dollars/month versus the clean paths — GLM-5.3-Flash or DeepSeek-off-peak on a US host costs less than the $160 Max tier while remaining a real API with real terms — and RQ15's levers close most of the remaining gap on the Sonnet primary. Ask for startup credits before considering anything gray.

---

## 4. Risk summary for a public multi-tenant product

**What happens if a subscription-proxied path dies mid-semester:**

1. **Total, silent, mid-session outage.** One account is one quota pool and one concurrency budget (GLM Lite guidance: *one* project at a time; Claude Max: 5-hour session + weekly caps sized for a single developer). A cohort of learners hitting Ask/Teach at 9 pm burns the 5-hour window in minutes; every user of Learny fails together, with no fallback, because the proxy path is by construction outside any SLA. The provider can also change quota math unilaterally (Z.AI did exactly that on 2026-07-30, and reserves the right to change features/prices "due to … operational strategy" **[quoted]**).
2. **Takedown and ban mechanics are documented, not hypothetical.** Z.AI's own policy pages describe automated risk control that rate-limits, freezes, and bans after three violations, and name "SDK-based access" as the detected pattern **[quoted]**. Anthropic ran takedown notices, abuse filters, and account/organization bans against subscription-OAuth bridges in 2025–2026 **[community, multiple sources]**. Bans come with **no refund** (both vendors' terms make payments non-refundable **[quoted]**) and community reports describe correlated bans across accounts sharing identity/payment signals.
3. **Legal exposure scales with the product.** The GLM subscription terms are a contract that names "websites, SaaS products", reserves the right to "pursue further liability" **[quoted]**, and caps its own liability at one month's fees — the asymmetry is total. Once Learny charges money (or even operates publicly) on a prohibited path, a ToS breach stops being a hobbyist's $18 loss and becomes the product's core supply dependency plus breach-of-contract exposure, at the worst possible time (mid-semester).
4. **A privacy promise you cannot keep.** Consumer plans are not data-processing agreements: Claude consumer terms let Anthropic train on Materials unless the individual opts out **[quoted]**; Gemini's unpaid tier trains on content with human reviewers **[quoted]**; GLM coding-plan routes user books to a CN-hosted endpoint RQ14 already excluded for the *paid* API. Shipping user EPUBs through any of these would contradict the residency/privacy posture every other Learny ADR assumes.
5. **Why a paid product changes the risk profile vs a hobby tool.** A hobby tool can lose its proxy and lose nothing but the owner's evening. A public product with users mid-course faces support collapse, refund/chargeback pressure, and reputational damage from an outage that was (a) foreseeable, (b) self-inflicted, and (c) contractually the operator's fault, not the vendor's. The honest framing: **a subscription is a seat license for one person's interactive use; Learny needs a metered supply contract.** They are different products regardless of how similar the HTTP calls look.

---

## Sources

Accessed 2026-09-07 unless noted. Community links are enforcement/precedent signal, not vendor-confirmed.

**Z.AI / GLM Coding Plan (official):**
- https://z.ai/subscription (JS app; static content unreadable — entry price taken from docs)
- https://docs.z.ai/devpack/overview (plan description, "Starting at just 18 USD per month", credit tables, multipliers, off-peak)
- https://docs.z.ai/devpack/faq (supported models, endpoints, quota reset, "API calls outside the plan are not available", non-refundable)
- https://docs.z.ai/devpack/usage-policy (supported-tools restriction, account sharing, risk control / ban ladder, concurrency guidance)
- https://docs.z.ai/legal-agreement/subscription-terms (§4 usage rules: websites/SaaS prohibition, no resale/model-capabilities-as-a-service, personal-use only; liability cap)
- https://docs.z.ai/devpack/notice/usage-revision (credits transition, 2026-07-30)
- https://docs.z.ai/devpack/tool/claude (Anthropic-compatible endpoint `https://api.z.ai/api/anthropic`)

**Anthropic:**
- https://www.anthropic.com/legal/consumer-terms (Consumer Terms, effective 2025-10-08: automated/non-human access, scraping, resale, account sharing, non-refundable)
- https://support.claude.com/en/articles/11049741-what-is-the-max-plan (5-hour session + weekly limits)
- https://docs.litellm.ai/docs/tutorials/claude_code_max_subscription (OAuth-forwarding tutorial; no ToS warning) [community-documented tooling]
- https://www.reddit.com/r/Anthropic/comments/1q9eom1/anthropic_sending_out_takedown_notice_to_all_the/ [community]
- https://www.reddit.com/r/ClaudeAI/comments/1qa50sq/anthropic_banning_thirdparty_harnesses_while/ [community]
- https://www.reddit.com/r/ClaudeAI/comments/1r8t6mn/anthropic_just_updated_claude_code_docs_to_ban/ [community]
- https://news.ycombinator.com/item?id=46549823 [community]
- https://tickernews.co/anthropic-bans-third-party-tools-from-claude-subscriptions/ (secondary; February 19 docs-update date)
- https://claude.com/pricing (plan prices; JS page — prices marked community-verified only)

**OpenAI:**
- https://openai.com/policies/row-terms-of-use/ (programmatic extraction, rate-limit circumvention, credential sharing)
- https://openai.com/policies/usage-policies/ (withholding access)
- https://manifest.build/blog/banned-from-chatgpt-subscriptions/ [community/secondary]

**Google:**
- https://ai.google.dev/gemini-api/terms (unpaid-services data use, human review, EEA paid-only, not-for-consumer-use)
- https://ai.google.dev/gemini-api/docs/rate-limits (limits dynamic, per-project, unpublished free-tier numbers)
- https://ai.google.dev/gemini-api/docs/pricing (Gemini 3.x Flash $0.75/$3.75 through 2026-12-31, doubling 2027)
- https://docs.cloud.google.com/gemini/docs/quotas (Code Assist Standard/Enterprise quotas)
- https://discuss.ai.google.dev/t/do-they-really-think-we-wouldnt-notice-a-92-free-tier-quota/111262 [community: free-tier cuts]
- https://usagebox.com/articles/gemini-api-billing-free-tier-confusion [community: 2.5 Pro free tier removed 2026-04]

**Other providers / programs:**
- https://openrouter.ai/docs/api-reference/limits (20 RPM; 50/1,000 RPD on `:free` models)
- https://console.groq.com/docs/rate-limits (Developer-plan base limits; free-plan tab values not in docs page)
- https://docs.github.com/en/github-models/use-github-models/prototyping-with-ai-models (GitHub Models retired 2026-07-30)
- https://cloud.google.com/startup/ai (up to $350k credits)
- https://openai.com/business/why-openai/startups/ (VC-partner credits)
- https://fin.ai/learn/ai-credits-for-startups [secondary: Anthropic startup program, no VC requirement]
- https://www.aipricing.guru/z-ai-subscription-pricing/ , https://distk.in/blog/glm-coding-plan-pricing-guide-2026.html , https://lorphic.com/glm-coding-plan-and-zcode/ [community: GLM plan tier prices]
- RQ14 (https://github.com/… repo: docs/research/2026-09-03/rq14-multi-provider-models.md) — GLM-5.3-Flash $0.15/$0.50, DeepSeek V4 Flash off-peak $0.22/$0.66, Fireworks US-only SKUs (official pages accessed 2026-09-03)
- RQ15 (docs/research/2026-09-03/rq15-ai-cost-optimization.md) — call-shape assumptions, per-MAU cost model, batch/caching levers
