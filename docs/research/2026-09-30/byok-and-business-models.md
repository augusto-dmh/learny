# BYOK, local models, and business models for an indie/OSS AI study app (Learny)

Research date: 2026-09-30. All claims dated where the source gives a date; "as of" dates otherwise refer to the fetch date (2026-09-30). Secondary/aggregator sources are labelled; primary docs preferred. Provider *pricing* deliberately not re-researched (prior 2026-09-07 research covers it).

Note on tool budget: the session-wide WebSearch quota was exhausted near the end; a handful of secondary claims (Khoj Cloud status, Immich sales figures, Cal.com revenue, Open WebUI embedding re-index docs) could not be confirmed against primary sources and are listed under Gaps.

---

## Key Question 1 — What are the dominant BYOK key-storage architectures in shipped products, and their trade-offs?

### Takeaway
Three architectures dominate: (A) client-only keys that never touch a vendor server (TypingMind, Open WebUI "Direct Connections", Jan/Chatbox/Cherry Studio desktop apps, Cline via OS keychain, Obsidian Copilot via Obsidian keychain, Continue.dev via local .env), (B) server-side encrypted per-user keys (LibreChat with AES-256 via CREDS_KEY/CREDS_IV; OpenRouter/Vercel gateway BYOK), and (C) pass-through/proxy where the key lives on the client but each request transits the vendor's server without being persisted (Cursor, Lobe Chat client-DB mode). Instance-level keys in .env (AnythingLLM, Perplexica, Khoj, default Open WebUI) are the operator-pays pattern, not per-user BYOK.

### Cited Findings

**Pattern A — client-only, key never reaches the app vendor**
- TypingMind: "Your API key is stored locally in your browser's local storage and is never sent to TypingMind's servers. TypingMind is a static app — there is no backend that could intercept your key"; requests go browser→provider directly; optional AES encryption of the key with a user password — [TypingMind General FAQs](https://docs.typingmind.com/general-faqs); [TypingMind Privacy Policy](https://docs.typingmind.com/security-and-compliance/privacy-policy)
- Open WebUI "Direct Connections" (admin must enable globally): "the browser communicates directly with the API provider. Users can use their own personal API keys without storing them on the Open WebUI server (keys are stored in the browser's local storage)"; user enters Base URL + API key under User Settings > Connections — [Open WebUI Direct Connections docs](https://docs.openwebui.com/features/chat-conversations/direct-connections/)
- Cline (VS Code extension): uses VS Code `context.secrets` (OS keychain: macOS Keychain, Windows Credential Manager, libsecret on Linux); caveat: standalone/CLI mode stores secrets in plain JSON at `~/.cline/data/secrets.json` — [Cline discussion #2904](https://github.com/cline/cline/discussions/2904); [agent-safehouse Cline analysis](https://agent-safehouse.dev/docs/agent-investigations/cline) (secondary)
- Obsidian Copilot v4.0.0+: "API keys are now stored in Obsidian's built-in Keychain so they never touch data.json"; per-device keychain so keys must be re-entered on each device; the older "Enable Encryption" toggle (which encrypted keys inside data.json) was retired — [obsidian-copilot releases](https://github.com/logancyang/obsidian-copilot/releases); [issue #2162 requesting native secret storage](https://github.com/logancyang/obsidian-copilot/issues/2162)
- Continue.dev: `apiKey: ${{ secrets.OPENAI_API_KEY }}` resolved from `~/.continue/.env` or a workspace `.env`; IDE extensions cannot read shell env vars — [Continue config.yaml reference](https://docs.continue.dev/reference); [Continue FAQ](https://docs.continue.dev/faqs)
- Raycast: desktop v1.100 (June 2025) added BYOK for Anthropic, Google, OpenAI; iOS (May 2026) added OpenRouter too; "Send as many AI messages as you want, at your own cost, without a Pro subscription" — [Raycast on X (iOS BYOK)](https://x.com/raycast/status/2060093250137153721); [AlternativeTo, June 2025](https://alternativeto.net/news/2025/6/raycast-now-lets-users-connect-their-own-ai-provider-accounts-anthropic-google-and-openai); [5typos, 2025-06-14](https://5typos.net/2025/06/14/raycast-ai-now-supports-your-own-api-keys) (secondary; where Raycast stores the key not confirmed)
- Zed: "Use API Access" lets any plan (Free, Pro, Student, Business) configure own keys; Personal plan is free with unlimited use of own keys; Zed-hosted models bill provider list price +10% on Pro — [Zed Plans & Pricing](https://zed.dev/docs/account/plans-and-pricing); [costbench summary](https://costbench.com/software/ai-coding-assistants/zed-ai/) (secondary)
- Jan (Menlo Research): desktop, Apache-2.0 with attribution request; no Pro tier — [janhq/jan LICENSE](https://github.com/janhq/jan/blob/main/LICENSE)
- Chatbox: BYOK guide exists; "With BYOK, you only pay for tokens actually used" — [Chatbox BYOK guide](https://chatboxai.app/en/guide/byok)
- Cherry Studio: desktop client, AGPL-3.0 community edition — [Cherry Studio License Agreement](https://docs.cherry-ai.com/cherry-studio-wen-dang/en-us/contact-us/business-cooperation/cherry-studio-license-agreement)

**Pattern B — server-side encrypted per-user keys**
- LibreChat: setting a provider key to `user_provided` (e.g. `OPENAI_API_KEY=user_provided`, `ANTHROPIC_API_KEY=user_provided`) makes the UI prompt each user for their own key; `CREDS_KEY` is a 32-byte key (64 hex) and `CREDS_IV` a 16-byte IV (32 hex) that "encrypt supported credentials stored in the database"; docs advise fixed unique values shared across replicas; algorithm not named in the docs page (secondary sources say AES-256) — [LibreChat dotenv docs](https://www.librechat.ai/docs/configuration/dotenv); [Chainguard LibreChat image page](https://images.chainguard.dev/directory/image/librechat/overview) (secondary, "AES-256")
- LibreChat license: MIT — [LibreChat GitHub](https://github.com/danny-avila/LibreChat)
- OpenRouter BYOK: provider keys are "securely encrypted and used for all requests routed through the specified provider"; keys belong to a workspace and can be restricted by model, API key or team member — [OpenRouter BYOK docs](https://openrouter.ai/docs/use-cases/byok)
- Vercel AI Gateway BYOK: available on paid tier only; "With BYOK, there is no markup or fee from AI Gateway"; failed BYOK requests are retried on Vercel's credentials and charged to your balance — [Vercel AI Gateway Pricing (updated 2026-09-08)](https://vercel.com/docs/ai-gateway/pricing)
- Google Cloud KMS envelope-encryption reference pattern: a per-object DEK encrypts the secret, a KEK (in KMS) wraps the DEK, "Do NOT store a plaintext DEK", store wrapped DEK next to ciphertext, "generate a new DEK every time you write the data" so only KEKs need rotation — [Google Cloud KMS envelope encryption](https://docs.cloud.google.com/kms/docs/envelope-encryption)

**Pattern C — client-held key, pass-through via vendor server (not persisted)**
- Cursor: supports OpenAI, Anthropic, Google, Azure OpenAI, AWS Bedrock keys; the key "is not stored on our servers" but "all requests are routed through Cursor's servers for final prompt building"; Tab completion still uses Cursor's models; "Cursor's Zero Data Retention policy does not apply when you use your own API keys" — [Cursor: Bring your own API key](https://cursor.com/help/models-and-usage/api-keys)
- Cursor free plan: a user reported on 2026-03-10 that BYOK did not work on the Free plan ("only Auto model choice is valid"); another user on 2026-04-24: "confused why they killed this feat"; a separate request "New $5 plan for BYOK allowance" (2026-04-13); no staff reply — [Cursor forum: Own API KEY in Free Plan](https://forum.cursor.com/t/own-api-key-in-free-plan/154357). Contradiction: the help page lists Pro/Pro+/Ultra/Teams/Enterprise for custom keys and does not mention Free.
- Lobe Chat (client-DB mode): "API keys are stored on the client side, but the OpenAI request service is initiated on the server side, so the API key must be sent from the client to the server... API keys sent from the client are not saved or recorded" — [lobehub discussion #561](https://github.com/lobehub/lobehub/discussions/561); server-DB mode uses `OPENAI_API_KEY` + `ACCESS_CODE` env vars — [lobehub .env.example](https://github.com/lobehub/lobehub/blob/main/.env.example)

**Instance-level keys (operator pays), not per-user**
- AnythingLLM: embedder/LLM provider configured instance-wide; changing it forces re-embedding — [AnythingLLM embedder docs](https://docs.anythingllm.com/setup/embedder-configuration/overview)
- Perplexica: `config.toml` holds OpenAI/Groq/Anthropic/Gemini keys; env vars override; an open issue asks for key encryption — [Perplexica issue #765](https://github.com/ItzCrazyKns/Perplexica/issues/765)
- Khoj: AGPL-3.0; server-side admin config; README still points to hosted app.khoj.dev and "Khoj Enterprise" — [khoj-ai/khoj README](https://github.com/khoj-ai/khoj)
- Msty: free desktop tier (local + remote chat, Knowledge Stacks RAG); paid Aurum $149/user/yr or $349 lifetime (2-device), Teams $300/user/yr; prices rose Dec 2025 from $129/$249 — [promptquorum Msty review](https://www.promptquorum.com/power-local-llm/msty-review) (secondary; msty.ai pricing page not fetchable)

### Inferences
- Client-only storage is the safest default for a *desktop or static* app, but does not fit Learny: its answer pipeline (retrieval, citation assembly, Celery workers) runs server-side, so the key must at least transit the server. That pushes Learny toward Pattern B (encrypted-at-rest, per-user) with an explicit "we never log or export your key" policy, or Pattern C (key sent per-request, held only in memory) for the generation call.
- Pattern C avoids at-rest encryption but forces the browser to hold the key (localStorage exposure to XSS) and does not work for background workers (embedding jobs) that run without a browser session. For Learny's worker pipeline, Pattern B is the practical choice; envelope encryption (per-row DEK wrapped by an app KEK from env/secret manager) is the reference pattern.
- Every serious product isolates BYOK from the vendor's own ZDR/privacy promises (Cursor states this explicitly). Learny should state that BYOK traffic is governed by the user's own provider agreement.

### Gaps
- Where Raycast stores BYOK keys (client keychain vs Raycast servers) was not confirmed from Raycast's own docs.
- LibreChat's exact cipher and IV-handling (fixed IV vs per-record IV) was not verified from source; docs only give key/IV sizes.
- Msty official pricing page could not be fetched (site redirect); figures come from a review.

---

## Key Question 2 — Which products allow arbitrary base_url, how do they mitigate relay/abuse, and which restrict to an allow-list?

### Takeaway
Most OSS chat UIs accept arbitrary OpenAI-compatible base URLs (Open WebUI, Lobe Chat, LibreChat custom endpoints, Continue, Cline, Jan, Chatbox, Cherry Studio, AnythingLLM), and this has repeatedly produced SSRF and server-key exfiltration CVEs; mitigation in practice is either "the request originates in the browser, not the server" (Direct Connections) or admin-only configuration. Commercial gateways (Vercel, OpenRouter) restrict BYOK to a catalog of known providers and charge for team-wide allow-lists. Cursor and Raycast restrict to a fixed provider list.

### Cited Findings
- Lobe Chat GHSA-p36r-qxgx-jq2v (published 2024-06-17, CVSS 5.7): an authenticated user could set the Base URL to their own server, making the backend send the *server's* real API key in request headers; root cause "allows setting the Base URL" without an "outbound traffic whitelist"; fixed in 0.162.25 — [Lobe Chat advisory](https://github.com/lobehub/lobe-chat/security/advisories/GHSA-p36r-qxgx-jq2v)
- Open WebUI CVE-2024-7959: `/openai/models` in 0.3.8 let an attacker change the OpenAI URL to any URL, an SSRF that could reach internal services and instance secrets — [GHSA-x757-hv69-jr45](https://github.com/advisories/GHSA-x757-hv69-jr45); a later SSRF, CVE-2025-65958, in web retrieval — [GHSA-c6xv-rcvw-v685](https://github.com/advisories/GHSA-c6xv-rcvw-v685)
- Open WebUI ships `ENABLE_RAG_LOCAL_WEB_FETCH` as an SSRF guard ("a malicious user could provide URLs that appear external but resolve to internal addresses, potentially exposing internal services, cloud metadata endpoints") and semicolon-separated `OPENAI_API_BASE_URLS` set by admins — [Open WebUI env configuration](https://docs.openwebui.com/reference/env-configuration/)
- Open WebUI Direct Connections is the user-supplied-base_url path: admin-gated, browser-to-provider, key in browser storage (never on server) — [Direct Connections docs](https://docs.openwebui.com/features/chat-conversations/direct-connections/)
- Vercel AI Gateway: BYOK "for any provider listed in our catalog"; a team-wide provider allowlist costs $0.10 per 1,000 successful requests (Pro/Enterprise), per-request `only` filter is free — [Vercel AI Gateway Pricing](https://vercel.com/docs/ai-gateway/pricing)
- OpenRouter: BYOK keys must respect the account's data policies (incl. ZDR); regional endpoints generally unavailable to BYOK; fallback to shared capacity can be disabled ("Never use shared capacity") — [OpenRouter BYOK docs](https://openrouter.ai/docs/use-cases/byok)
- Cursor restricts BYOK to OpenAI, Anthropic, Google, Azure OpenAI, AWS Bedrock (no arbitrary URL) — [Cursor API keys help](https://cursor.com/help/models-and-usage/api-keys)
- Raycast restricts BYOK to Anthropic, Google, OpenAI (+ OpenRouter on iOS) — [Raycast on X](https://x.com/raycast/status/2060093250137153721)
- LibreChat "Custom Endpoints" accept any OpenAI-compatible baseURL configured by the admin in librechat.yaml — [LibreChat custom endpoints](https://www.librechat.ai/docs/quick_start/custom_endpoints)

### Inferences
- The two real security failure modes with user-supplied base_url are (1) SSRF against the host network/metadata and (2) exfiltration of *the operator's* key when user-supplied URLs are mixed with operator credentials. Learny's stated risk (turning the app into an open relay for copyrighted book text) is a third, product-level risk; none of the surveyed products address it explicitly, because in chat UIs the user already owns the text.
- The mitigation that shipped products converge on is not "validate the URL" but "do not let the server make the call to an arbitrary host". For a server-side pipeline like Learny's, the equivalent is a signed/static allow-list of provider hosts (api.openai.com, api.anthropic.com, generativelanguage.googleapis.com, openrouter.ai, plus an explicit "local runtime" option for self-hosters only).
- Because Learny copies retrieved passages of user-uploaded books into prompts, a self-hosted deployment where the operator sets base_url (Ollama/LM Studio/vLLM) is low risk; a *hosted* Learny letting *any* user set base_url is where relay risk appears. The split (operator-level base_url; user-level keys only for allow-listed providers) matches how LibreChat and Open WebUI split admin vs user powers.

### Gaps
- No product was found that documents a "signed allow-list" of base URLs; the closest is Vercel's paid team-wide provider allowlist.
- No public write-up found of a BYOK product being abused as a content relay; the relay concern is Learny-specific and unverified as an observed attack.

---

## Key Question 3 — Do provider terms permit end-user BYOK in third-party apps? (exact clauses)

### Takeaway
Anthropic explicitly permits customers to provision their own API keys for use in third-party tools "provided the resulting usage is billed to the key owner under their agreement with Anthropic" and is not resold or intermediated, while banning any use of Claude.ai subscription/OAuth credentials in third-party apps. OpenAI's public terms forbid buying, selling or transferring keys and its help center says keys are "intended to be used by you"; a staff-moderated forum thread says BYOK apps are "not strictly prohibited" but discouraged. Google's Gemini API terms contain no BYOK restriction but make free-tier data trainable by Google. "Bring your own subscription" (routing a consumer ChatGPT/Claude plan through a third-party app) is prohibited by Anthropic in writing and is not a legitimate pattern anywhere surveyed.

### Cited Findings

**Anthropic**
- Claude Code "Authentication and credential use" policy (as fetched 2026-09-30): "Anthropic does not permit third-party developers to offer Claude.ai login into their own applications, or to route requests through Free, Pro, or Max plan credentials on behalf of their users. Moreover, developers may not collect, store, or intermediate Claude.ai credentials or session tokens." And: "This does not restrict how customers provision and manage their own API keys or third-party inference provider credentials — for example, configuring an API key in a development environment, secrets manager, or machine image for use by the customer's own authorized users — provided the resulting usage is billed to the key owner under their agreement with Anthropic (or the applicable provider) and is not resold or intermediated as described above." — [Claude Code legal and compliance](https://code.claude.com/docs/en/legal-and-compliance)
- Same page, for products that embed Claude Code: "Customers may not pay for, resell, or intermediate Claude usage on their end users' behalf. Each end user must authenticate with their own Anthropic API key, Claude subscription plan credentials, or 3P inference provider credential" — [Claude Code legal and compliance](https://code.claude.com/docs/en/legal-and-compliance)
- Anthropic Commercial Terms (effective 2025-06-17): "Customer is responsible for all activity under its account" (D.5); "Customer may not and must not attempt to (a) access the Services to build a competing product or service, including to train competing AI models or resell the Services except as expressly approved by Anthropic" (D.4); no clause specifically addressing third-party apps using a customer's key — [Anthropic Commercial Terms](https://www.anthropic.com/legal/commercial-terms)
- Community reporting of the early-2026 enforcement against third-party harnesses using Claude subscription OAuth (OpenClaw etc.) — [HN: Anthropic officially bans using subscription auth for third party use](https://news.ycombinator.com/item?id=47069299); [HN: Anthropic blocks third-party use of Claude Code subscriptions](https://news.ycombinator.com/item?id=46549823) (secondary discussion)

**OpenAI**
- OpenAI Terms of Use, Section 2(c) as quoted by a search summary: "You may not… (vi) buy, sell, or transfer API keys without our prior consent" (openai.com/policies returned HTTP 403 to direct fetch; quote is from search-result text, treat as near-primary) — [OpenAI Terms of Use](https://openai.com/policies/terms-of-use/)
- OpenAI help center: "Your API key is intended to be used by you"; recommends unique keys per team member (page returned 403 on fetch; quoted from search summary) — [Best Practices for API Key Safety](https://help.openai.com/en/articles/5112595-best-practices-for-api-key-safety)
- OpenAI Developer Community, thread "Bring Your Own Key policy" (last updated Dec 2025): a moderator states "Bring your own key applications are not strictly prohibited, but it is strongly suggested that users do not use their API keys outside of their own private infrastructure"; no explicit prohibition exists; acceptable pattern cited is locally-hosted, inspectable apps where keys never reach a third-party server — [OpenAI community: Bring Your Own Key policy](https://community.openai.com/t/bring-your-own-key-policy/446168); related older threads [Is this allowed? (BYOK)](https://community.openai.com/t/is-this-allowed-this-bring-your-own-key-usage/161185) and [proxying OpenAI without user keys](https://community.openai.com/t/is-it-legal-to-host-a-proxy-of-openai-api-that-allows-third-parties-to-use-openai-api-without-providing-their-own-api-key/299854)

**Google**
- Gemini API Additional Terms (effective 2026-03-23, updated 2026-04-28): "When you use Unpaid Services, including, for example, Google AI Studio and the unpaid quota on Gemini API, Google uses the content you submit to the Services and any generated responses to provide, improve, and develop Google products and services"; "human reviewers may read, annotate, and process your API input and output"; Paid Services: "Google doesn't use your prompts or responses to improve our products". No clause restricting key sharing or third-party apps — [Gemini API Terms](https://ai.google.dev/gemini-api/terms)

**Bring-your-own-subscription**
- Anthropic: prohibited in writing (see above). OpenAI/Google: no product in the survey (TypingMind, Chatbox, Msty, Raycast, Zed, Cursor, Cline, Open WebUI, LibreChat) routes a consumer ChatGPT/Gemini subscription; all BYOK is API-key based — inference from the product docs cited in Q1 (no source states a legitimate BYOS path).

### Inferences
- For Learny: per-user API-key BYOK with usage billed to the key owner is compliant with Anthropic's written policy and is tolerated (not endorsed) by OpenAI. Learny must not collect or proxy Claude.ai/ChatGPT logins, must not pool or resell keys, and should never route one user's requests through another user's key.
- The OpenAI moderator's preferred pattern ("keys never reach a third-party server") argues for making the self-hosted Docker Compose deployment the primary BYOK story, with the hosted instance as a second, clearly disclosed path.
- Gemini free-tier keys are attractive for Brazilian students but the training clause means Learny should warn users that uploaded book passages sent under an unpaid Gemini key may be used by Google.

### Gaps
- Could not fetch openai.com terms or help center directly (HTTP 403); Section 2(c) quote should be re-verified before citing in an ADR.
- No written Google clause on third-party BYOK found either way.

---

## Key Question 4 — What free/paid ratios, price points and outcomes do OSS AI/knowledge tools report? What worked and what failed?

### Takeaway
Publicly reported patterns: "free with your key / paid with ours or for convenience" (TypingMind lifetime licences reaching ~$130–160k/month revenue by Oct 2025; Chatbox $3.99–$39.99/mo credits; Msty $149/yr; Raycast Pro vs free BYOK; Zed free BYOK vs $10 Pro with +10% markup), open-core/hosted (Plausible ~$1M ARR by 2022, Ghost ~$7.5M/yr non-profit on MIT, Cal.com AGPL + /ee), voluntary licences (Immich $24.99/$99.99 lifetime with zero paywalled features), and sponsorware (Porzio: $573→$1,560/mo in two days; $1M+ cumulative). Generic COSS conversion is reported at well under 1% of downloaders, 0.5–3% for OSS SaaS. Failures/retreats: Cursor curtailing free-plan BYOK (2026), Open WebUI's licence change to protect branding (April 2025), Khoj Cloud reportedly sunset (2026, unverified), Cerebras and GitHub Models tightening free tiers (mid-2026, secondary).

### Cited Findings

**Free-with-your-key / paid-for-convenience**
- TypingMind: one-time licences Standard $39, Extended $79, Premium $99, Bulk $395/10 users; "The lifetime license does not include model usage: you supply the API keys" — [diyai.io TypingMind review](https://diyai.io/ai-tools/productivity/reviews/typingmind-review/) (secondary); [TypingMind home](https://www.typingmind.com/home)
- TypingMind revenue: Tony Dinh posted "$148k revenue last month. All-time high for TypingMind" (April 2025) — [Tony Dinh on X](https://x.com/tdinh_me/status/1908345028327727335); Oct 2025 newsletter: ~$130–160k/month with B2B Teams >50% of monthly revenue — [Oct 2025 Updates](https://news.tonydinh.com/p/oct-2025-updates-code-money-and-travel)
- Chatbox: Free $0 (10,000 daily compute points), Lite $3.99/mo, Pro $19.99/mo, Pro+ $39.99/mo; BYOK documented separately as pay-per-token — [Chatbox pricing](https://chatboxai.app/en/pricing); [Chatbox BYOK](https://chatboxai.app/en/guide/byok)
- Msty: free desktop tier; Aurum $149/user/yr or $349 lifetime; Teams $300/user/yr, 5-seat min; Dec 2025 price increase — [promptquorum Msty review](https://www.promptquorum.com/power-local-llm/msty-review) (secondary)
- Zed: free Personal plan incl. 2,000 edit predictions/mo and unlimited own-key use; Pro $10/user/mo with $5 token credit then list price +10% — [Zed plans](https://zed.dev/docs/account/plans-and-pricing); [costbench](https://costbench.com/software/ai-coding-assistants/zed-ai/) (secondary)
- Raycast: BYOK removes need for Pro for AI messages (June 2025 desktop, May 2026 iOS) — [Raycast on X](https://x.com/raycast/status/2060093250137153721)
- Cursor: BYOK restricted to paid individual/team plans per docs; Free-plan users report it is blocked (Mar–Apr 2026) — [Cursor forum](https://forum.cursor.com/t/own-api-key-in-free-plan/154357); [Cursor docs](https://cursor.com/help/models-and-usage/api-keys)
- Lobe Hub Cloud: 450,000 free credits at signup; Starter $9.9/mo (5M credits), Premium $19.9/mo (15M) — [LobeChat review](https://www.promptquorum.com/local-llms/lobechat-review) (secondary)

**Open-core, source-available, hosted-paid**
- Open WebUI: from v0.6.6 (2025-04-19) BSD-3 plus a branding clause; branding must be kept for deployments with 50+ users (30-day aggregate); ≤50-user deployments may rebrand; CLA required for new contributions; enterprise licence available for white-label — [Open WebUI License](https://docs.openwebui.com/license/); [HN discussion of the change](https://news.ycombinator.com/item?id=43901575)
- Cherry Studio: AGPL-3.0 community edition; commercial licence "for organizations with more than 10 individuals, or users needing to avoid AGPLv3 obligations" — [Cherry Studio License Agreement](https://docs.cherry-ai.com/cherry-studio-wen-dang/en-us/contact-us/business-cooperation/cherry-studio-license-agreement)
- LibreChat: MIT, GitHub Sponsors, no paid tier in README — [LibreChat GitHub](https://github.com/danny-avila/LibreChat)
- Jan: Apache-2.0 with attribution request — [janhq/jan LICENSE](https://github.com/janhq/jan/blob/main/LICENSE)
- Plausible: AGPL Community Edition; SaaS subscriptions are the only funding; $1M ARR announced June 2022 (bootstrapped) — [Plausible Community Edition](https://plausible.io/blog/community-edition); [Plausible self-hosted page](https://plausible.io/self-hosted-web-analytics); [Wikipedia](https://en.wikipedia.org/wiki/Plausible_Analytics)
- Ghost: non-profit foundation, MIT licence; ~$7.5M annual revenue, profitable 12 years; Ghost(Pro) from $9/mo; "The majority of Ghost websites in the world do not use Ghost(Pro)" — [Ghost about](https://ghost.org/about/); [John O'Nolan, Democratising publishing](https://john.onolan.org/democratising-publishing/)
- Cal.com: AGPLv3 core with a commercial licence for enterprise features in /ee ("99% open, 1% commercial"); Cal.diy fork is MIT with no /ee — [Boris Mann on Cal.com](https://bmannconsulting.com/notes/cal-com/) (secondary); [calcom/cal.com README (Cal.diy)](https://github.com/calcom/cal.com)
- Outline: BSL 1.1, converts to Apache-2.0 in July 2030 — [opensourcealternatives.to](https://www.opensourcealternatives.to/alternative-to/notion) (secondary)
- Anytype: "Any Source Available License" 1.0, free for non-commercial use — same source (secondary)
- Logseq: AGPL-3.0; raised ~$4.1M seed (Collison, Lütke, Friedman) — [Logseq Crunchbase](https://www.crunchbase.com/organization/logseq); [Logseq Open Collective](https://opencollective.com/logseq)
- AFFiNE: Free forever, Pro ~$6.75–7.99/mo, Team $10–12/seat, Believer $499.99 lifetime — [AFFiNE pricing](https://affine.pro/pricing) (figures via aggregators, secondary)
- Obsidian: closed-source, free for personal use, revenue from Sync ($4/mo) and Publish ($8/mo) plus $50/yr commercial licence; kepano: "Revenue primarily comes from optional paid services that have free alternatives"; third-party estimates ~$25M ARR / $350M valuation (2026) — [kepano on X](https://x.com/kepano/status/1965449590641230252); [OperatorBook on estimate spread $2M–$25M](https://www.operatorbook.dev/stories/obsidian-revenue-estimates-2m-to-25m) (secondary)
- Readwise: closed; $9.99/mo annual or $12.99 monthly; Lite $5.59/mo; no permanent free tier, 30-day trial — [toolradar Readwise pricing](https://toolradar.com/tools/readwise/pricing) (secondary)
- Immich (AGPL, FUTO-funded since 2024): optional Server licence $99.99 lifetime and Individual licence $24.99 lifetime; "there will never be any paywalled features"; announcement 2024-07-18 — [Immich licensing announcement](https://github.com/immich-app/immich/discussions/11186); [Immich joins FUTO](https://immich.app/blog/immich-joins-futo)
- Khoj: AGPL-3.0; README still lists app.khoj.dev and "Khoj Enterprise"; a 2026 review claims Khoj Cloud was sunset — conflict, see Gaps — [khoj README](https://github.com/khoj-ai/khoj); [promptquorum Khoj review](https://www.promptquorum.com/power-local-llm/khoj-ai-second-brain-review) (secondary)

**Sponsorware / sponsors**
- Caleb Porzio: sponsorware raised GitHub Sponsors from $573/mo to $1,560/mo in two days (2020); later $100k/yr; crossed $1M cumulative, of which $725k from Livewire premium screencasts, $200k company logo sponsorships, $20k Sushi early access — [Introducing Sponsorware](https://calebporzio.com/sponsorware); [$100k/yr post](https://calebporzio.com/i-just-hit-dollar-100000yr-on-github-sponsors-heres-how-i-did-it); [$1M post](https://calebporzio.com/i-just-cracked-1-million-on-github-sponsors-heres-my-playbook)

**Conversion ratios**
- "Open source SaaS companies typically see lower conversion rates, often between 0.5-3%"; "the vast majority of commercial open-source companies experience a conversion ratio (percentage of downloaders who buy something) well below 1%" — [Monetizely on OSS conversion](https://www.getmonetizely.com/articles/whats-the-optimal-conversion-rate-from-free-to-paid-in-open-source-saas) (secondary, cites OpenView)
- Linux Foundation/COSSA/Serena 2025 report: COSS companies achieve 7x greater valuations at IPO and 14x at M&A vs closed peers — [Linux Foundation press release](https://www.linuxfoundation.org/press/linux-foundation-cossa-and-serena-report-shows-venture-investment-in-open-source-outperforms-proprietary-counterparts-and-benefits-communities)

**Brazil pricing & payments**
- ParityDeals claims PPP pricing yields 20–70% more sales from lower-PPP regions and a typical ~53% discount for Brazil; supports Stripe, Lemon Squeezy, Paddle, Razorpay, PayPal — [ParityDeals SaaS page](https://www.paritydeals.com/solution/saas/) (vendor claim); [ParityDeals blog: +15% revenue](https://www.paritydeals.com/blog/how-i-increased-revenue-by-15-just-by-offering-purchasing-power-parity-pricing/)
- Stripe Pix: one-time and recurring (Pix Automático) payments; BRL presentment; Stripe accounts in US/EU/UK/etc. can accept Pix with settlement in their currency; **Brazilian Stripe accounts get one-time Pix only, "O Pix Automático não está disponível no Brasil"**; per-transaction limit R$0.50–R$3,000; a customer cannot exceed US$10,000/month with one business; 3.5% IOF applies to cross-border purchases, collected by Stripe's partner Ebanx — [Stripe Pix docs](https://docs.stripe.com/payments/pix)
- Paddle: Pix at checkout (2025) and Pix Automático recurring (2026; weekly/quarterly/semi-annual/annual, no daily, no unscheduled charges) — [Paddle changelog: Pix Automático](https://developer.paddle.com/changelog/2026/pix-automatico/); [Paddle Pix concept](https://developer.paddle.com/concepts/payment-methods/pix/)
- Lemon Squeezy: no Pix; open feedback request — [Lemon Squeezy feedback: Brazil payment options](https://lemonsqueezy.nolt.io/583)

### Inferences
- The only BYOK-first indie business with public revenue at scale is TypingMind, and its growth came from (a) one-time licences on top of free BYOK and (b) a Teams tier that later exceeded half of revenue. That is the closest analogue for Learny: free/self-host + BYOK, paid convenience tier, and later a group/education tier.
- Tools that let free users BYOK and then restrict it (Cursor) generate visible backlash; tools that add BYOK to expand the free tier (Raycast, Zed) present it as goodwill. Learny launching BYOK-first avoids the retreat problem.
- For a portfolio-grade OSS product, the licence signal matters: MIT/Apache (LibreChat, Jan) maximises adoption; AGPL (Plausible, Immich, Khoj, Cherry) keeps hosted-service optionality; source-available (Outline, Anytype) and Open WebUI's branding clause draw criticism.
- Brazil: PPP pricing is standard practice; Pix support depends on where the Stripe/Paddle entity is registered, and IOF adds 3.5% to cross-border purchases, so a Brazilian-domiciled account simplifies local pricing but loses Stripe Pix Automático recurring.

### Gaps
- No published free→paid conversion figure for any BYOK-first AI chat product (TypingMind, Msty, Chatbox) was found.
- Immich licence sales counts, Cal.com revenue, and Khoj Cloud's status could not be verified (search budget exhausted; Khoj README and a 2026 review conflict).
- Open WebUI enterprise pricing not verified from primary source.

---

## Key Question 5 — How do indie tools handle embeddings when the user brings a key (re-embedding, provider mismatch)?

### Takeaway
The dominant pattern is to keep embeddings *operator/instance-level and local by default* (Smart Connections, AnythingLLM's built-in embedder, Open WebUI's default local model, Khoj) and treat the generation key as the user-facing BYOK surface; changing the embedding provider after indexing is treated as a destructive operation requiring full re-embedding (AnythingLLM warns and clears vectors). No surveyed product does per-user embedding BYOK.

### Cited Findings
- AnythingLLM: "Once you select your embedding model provider and begin uploading and embedding documents it is best to not change it"; changing "can result in broken queries and needing to re-embed uploaded and stored documents"; a bug (issue #6460) shows the intended behaviour: other embedders "warn first and then clear the embedded documents and vectors" — [AnythingLLM embedder overview](https://docs.anythingllm.com/setup/embedder-configuration/overview); [issue #6460](https://github.com/Mintplex-Labs/anything-llm/issues/6460); [issue #1182 switching embedding model](https://github.com/Mintplex-Labs/anything-llm/issues/1182)
- Dimension mismatch is the concrete failure: OpenAI 1536-d vs Hugging Face 384/768-d vectors cannot be compared — [AnythingLLM issue #2745](https://github.com/Mintplex-Labs/anything-llm/issues/2745)
- Smart Connections (Obsidian): "A local embedding model powers semantic search. Zero setup. No API key."; plugin auto-indexes the vault with a built-in local model on install — [obsidian-smart-connections README](https://github.com/brianpetro/obsidian-smart-connections); [Smart Environment settings](https://smartconnections.app/smart-environment/settings/)
- Ollama exposes an OpenAI-compatible API at `http://localhost:11434/v1`; the Feb 2024 announcement covered chat completions with embeddings listed as planned — [Ollama OpenAI compatibility](https://ollama.com/blog/openai-compatibility)
- LM Studio exposes `/v1/embeddings` alongside `/v1/chat/completions` at `http://localhost:1234/v1` — [LM Studio OpenAI-compatible endpoints](https://lmstudio.ai/docs/app/api/endpoints/openai)
- Cursor: BYOK applies to chat models only; Tab completion (Cursor's own models) is not BYOK — [Cursor API keys](https://cursor.com/help/models-and-usage/api-keys)
- Learny locked embeddings to OpenAI `text-embedding-3-large@1536` (ADR-0019) and generation to Anthropic (ADR-0020) — project CLAUDE.md (internal)

### Inferences
- Embedding BYOK is a poor first target: it multiplies index variants (one vector space per provider/model/dimension), breaks shared corpora, and re-embedding whole books is the expensive path. Products avoid it by making embeddings an operator concern.
- For Learny, the practical split is: generation key = per-user BYOK; embedding = operator-level (hosted: Learny's own key or a free local model; self-host: operator chooses once). If a user-level embedding key is ever offered, it must be scoped per corpus with the model/dimension recorded on the corpus row and a forced re-embed on change, mirroring AnythingLLM's reset.
- A deterministic local embedding option (already Learny's offline default) is the cheapest way to keep hosted BYOK users at zero embedding cost, at some retrieval-quality cost.

### Gaps
- Open WebUI's RAG/embedding docs page could not be fetched (404 on two paths); its default local embedding model and re-index behaviour are unverified here.
- No product was found that stores multiple embedding spaces per document to allow provider switching without re-embedding.

---

## Key Question 6 — Which local models in 2026 are good enough for pt-BR cited Q&A on a laptop, and what do free-tier APIs actually allow?

### Takeaway
Credible 2026 sources point to Qwen3 (8B/14B) and Gemma 3/4 mid-size models as the practical laptop choices for Brazilian Portuguese, with Tucano 2 (0.5–3.7B, USP, March 2026) as the strongest *Portuguese-native* small model; Sabiá-3 is API-only (Maritaca), not open weights. No source directly benchmarks *cited* RAG answers in pt-BR on consumer hardware. Free API tiers are shrinking or come with training clauses: Gemini unpaid tier is used for training with human review; Mistral's free tier trains by default (opt-out); Cerebras replaced its free tier with a $5/30-day trial (July 2026, secondary); GitHub Models is prototyping-only with small daily quotas (and one tracker claims it was retired 2026-07-30, unverified); Groq's free plan does not retain data by default and allows ZDR.

### Cited Findings

**Local/open-weight models for Portuguese**
- Tucano 2 (arXiv 2603.03543, submitted 2026-03-03): 0.5–3.7B Base/Instruct/Think models trained on GigaVerbo-v2; post-training data covers "retrieval augmented generation, coding, tool use, chain-of-thought"; claims "state-of-the-art performance on several Portuguese-language modeling benchmarks" and to "outperform similarly sized multilingual models"; notes that Qwen3-4B "allocate[s] substantial capacity to Portuguese" — [Tucano 2 abstract](https://arxiv.org/abs/2603.03543); [Tucano 2 HTML](https://arxiv.org/html/2603.03543v1) (result tables not extractable via fetch; PDF exceeded fetch size limit)
- Open Portuguese LLM Leaderboard (eduagarcia, Hugging Face) evaluates ENEM, BLUEX, OAB Exams (3-shot) among others — [lm-evaluation-harness-pt](https://github.com/eduagarcia/lm-evaluation-harness-pt); leaderboard at https://huggingface.co/spaces/eduagarcia/open_pt_llm_leaderboard (Gradio app, not fetchable)
- CLARIN-PT-LDB (arXiv 2603.12872, 2026-03-13) targets *European* Portuguese; Gervásio 70B, Llama 70B, Mistral 24B top its table (MMLU 82.04 / 81.67 / 71.02); does not cover Gemma/Qwen/Tucano — [CLARIN-PT-LDB](https://arxiv.org/html/2603.12872)
- Sabiá-3 (Maritaca, launched July 2024): "accuracy comparable to GPT-4o in 64 Brazilian exams, including OAB, Enem"; offered via API — [Maritaca on X](https://x.com/MaritacaAI/status/1809212778957164970); [Maritaca API page](https://www.maritaca.ai/en/api/); Ollama issue requesting Sabiá confirms no Ollama distribution — [ollama issue #14533](https://github.com/ollama/ollama/issues/14533). A promptquorum review (Aug 2026) claims Sabiá-3 is a "~7B" HuggingFace download — contradicted by Maritaca's API-only positioning; treat as unreliable — [promptquorum Best local LLMs for Brazilian Portuguese 2026](https://www.promptquorum.com/local-llms/best-local-llms-portuguese-language-2026) (secondary)
- Same promptquorum page (updated 2026-08-28): recommends Qwen3 8B (~7 GB VRAM Q4), Qwen3 14B (~9 GB), Llama 3.1 8B (~7 GB), Gemma 4 31B (~19 GB); cites PoETa v2 as a Portuguese benchmark but gives no scores; states "there is no single standardized Brazilian Portuguese benchmark" — (secondary; no primary numbers)
- Qwen3 pretrained on ~36T tokens across 119 languages; Gemma 3 spans 270M–27B with 128K context and 140+ languages; Falcon 3 (1–10B) trained on English/Spanish/Portuguese/French — [Vellum open LLM leaderboard page](https://www.vellum.ai/open-llm-leaderboard) and [Codersera 2026 landscape](https://codersera.com/blog/open-source-llms-landscape-2026/) (secondary summaries)

**Integration patterns**
- Ollama: OpenAI-compatible `http://localhost:11434/v1`, `api_key` "required, but unused" — [Ollama blog](https://ollama.com/blog/openai-compatibility)
- LM Studio: `http://localhost:1234/v1` with `/v1/models`, `/v1/chat/completions`, `/v1/completions`, `/v1/embeddings`, `/v1/responses` — [LM Studio docs](https://lmstudio.ai/docs/app/api/endpoints/openai)
- Msty bundles Ollama by default, direct llama.cpp since Nov 2025, MLX since Mar 2026 — [promptquorum Msty review](https://www.promptquorum.com/power-local-llm/msty-review) (secondary)

**Free-tier APIs and fine print**
- Gemini unpaid tier: content used "to provide, improve, and develop Google products" with human review; paid tier not used for improvement — [Gemini API Terms (eff. 2026-03-23)](https://ai.google.dev/gemini-api/terms)
- Groq: does not retain customer data by default; logs only for troubleshooting/abuse up to 30 days; not permitted to train on inputs/outputs; ZDR toggle available to all customers — [Groq: Your Data in GroqCloud](https://console.groq.com/docs/your-data); Free plan limits vary per model (10–30 RPM, 100–14,400 RPD, 1.2K–15K TPM); "Upgrade to Developer plan to access higher limits" — [Groq rate limits](https://console.groq.com/docs/rate-limits)
- Cerebras: always-free tier (1M tokens/day, no card) replaced in July 2026 by a $5, 30-day trial requiring a verified payment method; trial limits 5 req/min, 1M tokens/day — [agentdeals Cerebras](https://agentdeals.dev/vendor/cerebras) (secondary); [agentdeals PR #1909](https://github.com/robhunter/agentdeals/pull/1909) (secondary)
- GitHub Models free tier: 15 RPM/150 RPD (low), 10 RPM/50 RPD (high), 8K in/4K out tokens per request; terms bar production use — [getaitools GitHub Models](https://getaitools.dev/service/github-models) (secondary); one tracker records GitHub retiring it on 2026-07-30 — [agentdeals issue #1672](https://github.com/robhunter/agentdeals/issues/1672) (secondary, unverified)
- Mistral: free tier "opted in to training by default, with the ability to opt out individually in Settings" (Sept 2026 reporting) — [aipricing.guru, Sept 2026](https://www.aipricing.guru/news/mistral-user-data-training-default-opt-out-september-2026/) (secondary); Mistral's own Sept 2024 announcement of the free tier — [Mistral: AI in abundance](https://mistral.ai/news/september-24-release/)
- OpenRouter's own comparison of free LLM APIs (2026) — [OpenRouter blog: free LLM APIs compared](https://openrouter.ai/blog/tutorials/free-llm-apis-compared/)

### Inferences
- For a laptop with 8–16 GB RAM, Qwen3 8B (Q4) is the defensible default for pt-BR chat with citations; Tucano 2 Instruct (≤3.7B) is the option for weak hardware and is explicitly post-trained for RAG. Gemma 3 12B / Qwen3 14B need ~9–12 GB VRAM. Quality for *grounded, cited* answers is unmeasured in public pt-BR benchmarks; Learny's own golden fixtures would be the first such measurement.
- Free tiers should be presented as "bring your own free key" options with a per-provider privacy badge (Gemini unpaid = trains; Mistral free = trains unless opted out; Groq = no retention by default), not as a Learny-operated free tier.

### Gaps
- No public benchmark of citation faithfulness for Portuguese RAG on small open models; Tucano 2's numeric tables not retrievable here.
- Cerebras/GitHub Models/Mistral free-tier changes rely on secondary trackers dated mid-2026; verify on provider pages before writing them into a roadmap.

---

## Key Question 7 — Recommendation set for Learny: safe BYOK architecture, sequencing, business model

### Takeaway
Ship BYOK first, in the order self-host → hosted-with-your-key → hosted-with-our-key, using server-side envelope-encrypted per-user keys, a fixed provider allow-list (no user-supplied base_url on the hosted instance; operator-level base_url for self-hosters), per-user adapter construction keyed on a key fingerprint instead of the process-wide lru_cache, and cost display from provider usage fields. Business model: MIT or AGPL core, free self-host with BYOK/local models, a paid hosted tier that includes Learny-managed keys and convenience features, PPP pricing for Brazil via Stripe/Paddle with Pix, and optional supporter licences in the Immich style.

### Cited Findings (evidence reused from Q1–Q6; new items cited)
- Envelope encryption (DEK per secret, KEK from KMS/env, never store plaintext DEK, rotate KEK) — [Google Cloud KMS](https://docs.cloud.google.com/kms/docs/envelope-encryption)
- LibreChat per-user `user_provided` keys encrypted with CREDS_KEY/CREDS_IV — [LibreChat dotenv](https://www.librechat.ai/docs/configuration/dotenv)
- Base-URL SSRF/key-exfiltration precedents — [Lobe Chat GHSA-p36r-qxgx-jq2v](https://github.com/lobehub/lobe-chat/security/advisories/GHSA-p36r-qxgx-jq2v); [Open WebUI CVE-2024-7959](https://github.com/advisories/GHSA-x757-hv69-jr45)
- Anthropic permits customer-provisioned keys billed to the key owner; bans subscription-credential intermediation — [Claude Code legal](https://code.claude.com/docs/en/legal-and-compliance)
- Gateways as an alternative to per-provider adapters: OpenRouter BYOK 5% fee after $25k/month list-price allowance; Vercel AI Gateway BYOK 0% fee but paid tier required and fallback to Vercel credentials on failure; LiteLLM proxy free/self-hosted with paid enterprise; Portkey MIT gateway + free Developer tier, $49/mo Production — [OpenRouter BYOK](https://openrouter.ai/docs/use-cases/byok); [Vercel pricing](https://vercel.com/docs/ai-gateway/pricing); [TrueFoundry LiteLLM pricing](https://www.truefoundry.com/blog/litellm-pricing-guide) (secondary); [TrueFoundry Portkey pricing](https://www.truefoundry.com/blog/portkey-pricing-guide) (secondary)
- Cost display precedent: Zed shows +10% over list; Vercel offers per-key/per-member budgets; OpenRouter charges BYOK fee from credits — sources above
- Cursor's Free-plan BYOK restriction and user backlash — [Cursor forum](https://forum.cursor.com/t/own-api-key-in-free-plan/154357)
- Immich's optional supporter licence with no paywalled features — [Immich announcement](https://github.com/immich-app/immich/discussions/11186)
- TypingMind: free BYOK + lifetime licences + Teams tier → $130–160k/month (Oct 2025) — [Tony Dinh newsletter](https://news.tonydinh.com/p/oct-2025-updates-code-money-and-travel)
- Brazil payments: Stripe Pix (one-time for BR accounts; Pix Automático only for non-BR accounts), Paddle Pix Automático, Lemon Squeezy no Pix; ParityDeals ~53% Brazil discount — [Stripe Pix](https://docs.stripe.com/payments/pix); [Paddle Pix Automático](https://developer.paddle.com/changelog/2026/pix-automatico/); [Lemon Squeezy feedback](https://lemonsqueezy.nolt.io/583); [ParityDeals](https://www.paritydeals.com/solution/saas/)

### Inferences (the recommendation)

**A. Key storage and encryption**
1. Store per-user provider keys server-side, encrypted with envelope encryption: random 32-byte DEK per secret (AES-256-GCM, random nonce), DEK wrapped by a KEK loaded from an env/secret manager (`LEARNY_SECRETS_KEK`), wrapped DEK + nonce + ciphertext + key fingerprint (SHA-256 prefix) + provider + created_at on a `user_provider_credentials` row. Never log plaintext; never return it via API (show last 4 chars only). Provide a KEK-rotation job that re-wraps DEKs without touching ciphertext.
2. Do not adopt TypingMind-style browser-only storage: Learny's Celery pipeline and cited-answer assembly need the key server-side, and localStorage keys are exposed to XSS.
3. Disclose, Cursor-style, that BYOK traffic is governed by the user's own provider agreement and that Learny's privacy commitments about provider retention do not apply.

**B. Adapter cache**
4. Replace the process-wide `lru_cache` adapter factory with a cache keyed on `(provider, model, key_fingerprint)` with bounded size and TTL, built per request/task from the decrypted key; house profiles remain operator-keyed entries in the same cache. Workers decrypt at task start and never serialise the key into Celery payloads (pass credential row id instead).

**C. Provider policy and relay risk**
5. Hosted instance: fixed allow-list of providers with hard-coded hosts (Anthropic, OpenAI, Google Gemini, OpenRouter, optionally Groq/Mistral), no user-editable base_url. This removes both SSRF and the "open relay for book text" vector: a user can only send their own uploads to a first-party provider under their own key.
6. Self-hosted instance: operator-level `base_url` (Ollama/LM Studio/vLLM) set via env, marked "operator-only" in the UI. If a user-level custom endpoint is ever wanted, gate it behind an operator flag and enforce an egress allow-list at the network layer (deny RFC1918/link-local/metadata), mirroring Open WebUI's SSRF guard.
7. Per-user rate limits and per-source concurrency caps on BYOK calls (the user's key, but Learny's reputation with the provider), and a per-corpus cap on prompt tokens per hour to make bulk extraction of a whole book through the app uneconomic.

**D. Embeddings**
8. Keep embeddings operator-level (ADR-0019 model on hosted; deterministic/local model on self-host). Record `embedding_model` + `dimension` on each corpus; changing it triggers a re-embed job and blocks queries until done (AnythingLLM pattern). Do not offer per-user embedding BYOK in the first BYOK cycle.

**E. Cost display**
9. Show per-answer and per-session token counts from provider usage fields and an estimated cost from a static per-model price table the operator maintains (no live pricing calls). Show a monthly running total per user and let users set a soft budget that pauses BYOK calls (Vercel budgets pattern).

**F. Sequencing**
10. Order: (1) self-host BYOK + local models (already close: adapters behind ports; needs per-user keys, encryption, cache fix); (2) hosted BYOK with allow-list and cost display; (3) hosted paid tier with Learny-managed keys (house profiles) and convenience features (sync, larger corpora, priority workers). BYOK before paid hosted, because it removes Learny's inference cost from the free tier, matches Anthropic's written policy, and avoids the Cursor-style retreat if BYOK were introduced later as a downgrade.

**G. Business model for a portfolio-grade OSS product (Brazil + global)**
11. Licence: AGPL-3.0 for the core (keeps hosted optionality like Plausible/Immich/Khoj) or MIT if maximum adoption/portfolio reach matters more than protecting a future hosted service; avoid source-available/branding clauses (Open WebUI backlash). Recommendation: AGPL-3.0 with a plain CLA-free policy, stated in an ADR.
12. Revenue: (a) hosted "Learny Cloud" subscription where the paid tier bundles managed keys via house profiles plus convenience features, priced ~US$8–12/month globally with PPP (~50% for Brazil) in BRL via Pix; (b) optional supporter licence for self-hosters (Immich pattern, US$25–30 one-time, no paywalled features); (c) later, a Teams/education tier for cursinhos and universities (TypingMind's Teams tier became >50% of revenue).
13. Expect free→paid well under 3% (OSS SaaS norm); design the hosted tier so the free BYOK cohort costs Learny only storage/compute, not inference.
14. Payments: use Paddle (merchant of record, Pix + Pix Automático, handles Brazilian tax) or Stripe (Pix one-time for a BR-registered account; recurring Pix only from a non-BR account); avoid Lemon Squeezy for Brazil until it ships Pix.

### Gaps
- No public data on how much revenue a Brazil-focused PPP tier produces for an indie AI tool; ParityDeals numbers are vendor claims.
- Whether Anthropic's API allows per-user keys for a hosted third-party product to be used *by students without an Anthropic org* (key ownership by individuals) is covered in principle by "billed to the key owner", but no explicit consumer-key guidance was found.
- The relay-abuse threat (bulk extraction of copyrighted text via BYOK) has no documented precedent in surveyed products; the rate-limit numbers in (7) are design suggestions, not evidence-based thresholds.
