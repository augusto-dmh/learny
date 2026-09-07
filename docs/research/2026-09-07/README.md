# Research drop 2026-09-07 — cheaper intelligence beyond the API bill

*Trigger: the `cheaper-intelligence` roadmap row (RFC-0007 Cycle G / Bet 7, "effort/cache/fallback; ADR-0020 amendment first") plus an owner provocation from 2026-09-07: cheaper-but-quality providers (GLM-5.3-Flash, Gemini 3.8 Flash, …) as new adapters, the end user choosing their provider, and possibly proxying a subscription as if it were an API. Builds on the 2026-09-03 fleet (`rq14-multi-provider-models.md`, `rq15-ai-cost-optimization.md`) as delta research, not a re-snapshot. All web sources accessed 2026-09-07.*

## The three documents

| File | Question | Verdict in one line |
|---|---|---|
| `provider-landscape-update.md` | What changed in the cheap tier since 09-03; is Gemini a real candidate? | Gemini 3.8 Flash is the one genuinely new viable SKU (only non-Chinese sub-$1 tier, OpenAI-compat, no Citations API, intro price doubles 2027-01-01); GLM-5.3-Flash list $0.15/$0.50 stays the floor; Haiku 4.5 remains the first move. |
| `provider-adapter-architecture.md` | What does multi-provider, operator routing, and end-user choice cost given the actual code? | New adapter: one cycle with a declared-degradation bill; operator routing: one cycle after an error taxonomy + per-profile pricing (+ a provider-pinning bug fix on quiz batch polls); end-user choice: a roadmap of its own — curated house profiles is the one-cycle slice, BYO keys is 3+ cycles. |
| `subscription-as-api.md` | Can a subscription (GLM Coding Plan, Claude Pro/Max, ChatGPT Plus, Gemini free tier) serve product traffic? | No — the GLM Coding Plan's own terms name "websites, SaaS products" invocation as prohibited and its risk control bans for it; Anthropic bans OAuth bridges; quota is sized for one developer anyway. The clean paths are already cheaper than the fantasy. |

## Synthesis — answers to the three provocations

**1. Cheaper providers as new adapters: yes, and now concretely shaped.** The viable ladder for a public Learny is: Haiku 4.5 first (native Citations API, permanent $1/$5, zero new vendor) → Gemini 3.8 Flash as the non-Chinese economy rung ($0.75/$3.75 through 2026 only; plan against $1.50/$7.50 in 2027; `reasoning_effort` floor is `low`; paid tier required for EU tenants and for keeping book text out of training) → GLM-5.3-Flash via Fireworks-US as the price floor (~$0.22/$0.75 with the US surcharge, eval-gated) → DeepSeek/MiniMax unchanged from rq14. Every non-Anthropic rung means prompt-id citations + grounding intersect instead of the Citations API, and every downgrade passes the nightly judged eval (faithfulness ≥ 0.90, relevancy ≥ 3.1, `citation_valid` = 100%) before promotion. Embeddings: closed — nothing beats the incumbent.

**2. End-user-decidable providers: split it.** What is cycle-sized is "the learner picks among operator-curated house profiles" (a per-user preference row + two-tier adapter resolution; budget and rails apply unchanged, priced at the chosen profile). What is NOT cycle-sized is BYO API keys: Learny has no encryption-at-rest anywhere, adapters are built once per process under `lru_cache`, and a user-supplied `base_url` would turn the app into an open relay for copyrighted book text — that flavor is 3+ cycles plus a security review, gated on having a paid tier to sell it to (RQ10). Recommendation recorded in the architecture doc: scope operator routing into Cycle G; record curated profiles as the next cycle; scope BYO out explicitly in the ADR-0020 amendment.

**3. Subscription-as-API: dead end for the product — and unnecessary.** The GLM Coding Plan's Subscription Terms prohibit "directly invoking model APIs from your own applications, bots, websites, SaaS products", reselling "model capabilities as a service to third parties", and any use outside a single natural person's account — with documented rate-limit/freeze/ban enforcement and non-refundable fees; Anthropic's consumer terms ban the OAuth-bridge pattern and enforcement waves are documented; Gemini's free tier trains on submitted content and bars EEA end users. Even capacity-wise, Max-tier credits ≈ one heavy developer, not 50k product turns. The honest comparison: GLM-5.3-Flash pay-as-you-go ≈ **$70/month** at ~50k cited turns, DeepSeek off-peak ≈ $99, Gemini paid ≈ $410 (2026 rate) — vs ~$1,100 list on Sonnet 5 today, ~$630–860 after rq15's already-spec'd levers. The single best ROI move is applying to startup credit programs (Google up to $350k; Anthropic/OpenAI have programs too). Subscriptions stay what they are good at: dev-time coding tools.

## Consequences for the Cycle G roadmap row

Prerequisite order extracted from the architecture doc (each item is small, the order is load-bearing):

1. Learny-owned provider error taxonomy (adapters currently raise untyped).
2. Pin quiz batch polls to the handle's provider (`QuizDeckHandle.provider` exists but poll tasks rebuild from current settings — flipping providers mid-deck would poll vendor B with vendor A's batch id).
3. Per-profile price catalogs (the single `price_*` triple breaks under routing; budget math itself is already provider-agnostic).
4. Routing adapter + settings-declared profile registry (capability flags: "grounded-primary" vs "economy"; Ask never routes to a citation-less profile — it fails honest instead).
5. Eval-gated promotion as process (nightly judge already records the model per case; promotion = registry reorder after a green nightly).
6. Then the rq15 moves land as profile values (effort=diet on Ask, cache breakpoints, Haiku-for-Ask behind the gate).

The ADR-0020 amendment has a ready 12-question checklist with recommended answers in `provider-adapter-architecture.md` §4. One decision the owner may want to make early: whether Cycle G ships as one cycle (rails + router + first economy profile) or splits (G1: taxonomy + pinning + pricing + Haiku moves; G2: OpenAI-compat adapter + Gemini/GLM profiles). The research supports either; the split keeps each cycle's Verifier surface small.
