---
id: gap-critique
title: Fleet completeness, conflicts, and source quality
question: Are the fifteen 2026-09-03 RQ reports complete, consistent, and evidence-bound enough to synthesize a public-launch RFC-004, and what must the synthesizer not paper over?
date: 2026-09-03
sources_accessed: 2026-09-03
status: complete
overall_confidence: high
primary_sources_count: 15
---

# Gap critique — 2026-09-03 public-launch fleet

One-line constraint: critic ≠ author; this file reconciles `rq01`–`rq15` against the brief. It does not rewrite those reports (no load-bearing primary refuted a claim hard enough to warrant a `## Verification corrections` appendix). It does not write `synthesis.md`.

## TL;DR

All fifteen brief questions are answered. The fleet is ready to synthesize RFC-004 without a second research wave.

The reports converge on a launch shape: **Gemini Notebook** (NotebookLM until 16 Jul 2026) is the competitive frame; Learny’s wedge is the *book* loop — click-to-passage citations, FSRS, notes-as-evidence, export — not Audio Overviews. Teach must elicit first (Khanmigo / Bastani). Quiz work is formulation + honest empty decks, not a new scheduler. Retrieval stays pgvector; first intelligence move is structural headers. Public ops need shared rate limits, per-user AI caps, and invite-or-Turnstile before open signup. Pricing is secondary: caps first, Paddle later.

The synthesizer must **resolve**, not average, four real tensions: (1) **COGS** — canonicalize on rq15’s Sonnet 5 + thinking arithmetic (~$0.02/Ask; ~$1.16 typical MAU); treat rq09’s $0.0225 as July Sonnet 4.6 folklore that omitted thinking; treat rq10’s $0.03–0.04 as a conservative commercial buffer. Product default is `claude-sonnet-5` ($2/$10), not Sonnet 4.6. (2) **Invite-only (rq09) vs try-without-signup (rq07/rq12)** — both evidenced; pick a sequence. (3) **Teach cache** — rq13 lists 1h caching as shipped; rq15 shows the breakpoint currently caches a prefix often below the 1,024-token minimum and leaves evidence *after* it. Prefer rq15. (4) **Haiku-on-quiz** — rq14’s Move 1 is already the default (`LEARNY_QUIZ_MODEL=claude-haiku-4-5`); do not re-ship it.

No follow-up memos. Twelve load-bearing URLs were fetched and support the cited claims. Do not concatenate the fifteen cycle lists. Limitation: rq09’s ~7-day Anthropic log TTL is unverified on the retention page; SEO checkout prices were not re-audited.

## Method

**Role.** Independent critic. Did not author any `rqNN` file. One fleet-level pass (meta-fleet-process §5.2), not fifteen prose reviews.

**Rubric.** Coverage of the brief’s 15 RQ sentences; claim matrix on predicted collision zones (§3.4) plus rq13/rq14/rq15; conflict log only for genuine disagreements; source-quality flags; true-gap bar = “would RFC-004 ship the wrong thing without this”; spec conformance against meta-output-conventions’ 14-point checklist, scored against the **older house template the workers were briefed on** (TL;DR → evidence → implications with why-not → cycle-sized moves). Missing YAML front matter / named Method / Limitations is **flagged, not failed**.

**What was read.** `project-brief.md`; all fifteen `rqNN-*.md`; in-repo defaults (`backend/app/core/config.py` generation/quiz models; `AnthropicGenerationAdapter._build_request` cache breakpoints; Ask/Teach `include_notes` surface defaults).

**Spot-checks (fetched 2026-09-03).** Anthropic pricing; Sonnet 5 launch post; prompt-caching minimums; API data-retention page; Gemini Notebook product + 16 Jul 2026 rebrand; NotebookLM chat-citation and flashcard help; Chalkbeat Khanmigo study; Sal Khan 2026-07-15 note; OpenAI `text-embedding-3-large`; Fireworks US-only serverless; Polar seller-payout countries; Paddle pricing; Standard Ebooks *Art of War*. Web fetches were citation audits only — no new landscape research.

**What was not done.** No re-crawl of competitors. No rewrite of worker reports. No `synthesis.md`. No averaging of conflicting dollar figures.

**Confidence labels (GRADE-style ordinals).** High = multiple primaries agree (or in-repo code + a primary). Medium = one primary or consistent secondaries. Low = absence-inference, aggregator, or unresolved conflict.

---

## Coverage map

The brief has one-sentence RQs, not exclusive Owns lines. Status is against that sentence.

| Brief RQ | Status | What is answered | Residual (not a true gap) |
|---|---|---|---|
| 1 Competitive landscape | **Answered** | Four-cluster map; Gemini Notebook / Readwise / Recall / RemNote / Anki / Study Mode; table-stakes vs differentiators; do-not-build (podcasts, RSS) | Aggregator Reddit synthesis for “what users love” |
| 2 Science of learning | **Answered** | Dunlosky mapping; successive relearning, retrieval-first tutor, pretest, generation; explicit non-recs (no MCQ, no second scheduler) | Some publisher PDFs timed out (labeled) |
| 3 AI tutor pedagogy | **Answered** | AutoTutor ladder + Khanmigo/Claude/Study Mode/LearnLM; critique of four-sentence prompt; playbook + state machine; tutor-opens | No Learny learning-gain data (correctly deferred) |
| 4 Active-recall quality | **Answered** | Formulation rubric, empty-deck copy, preview vs silent mint, review undo / learning-step requeue; FSRS-6 kept | Optimizer parked until volume |
| 5 Retrieval intelligence | **Answered** | Technique fit table under ADR-0006; headers + top_k; ruler; parent expansion; long-context as unimplemented ADR-0001 | No labeled real-book retrieval set yet (called out) |
| 6 Reading experience | **Answered** | Kindle/Readwise/Matter/Apple Books bench; figures/CSP; immersive chrome; phone; resume grain; a11y | Intra-section resume encoding needs a spike, not a memo |
| 7 Onboarding & activation | **Answered** | Aha = first cited answer; shared SE sample; guest cap; ingest stages; activation events | Aha definition is provisional pending D7 (labeled) |
| 8 Motivation & retention | **Answered** | SDT filter; keep heatmap; avoid streaks/PBL; load shaping; opt-in digest; no social decks | Duolingo A/Bs are DAU not learning (labeled) |
| 9 Public-launch readiness | **Answered** | Redis/user caps, spend ledger, quotas, invite/Turnstile, ToS/privacy/DMCA, deletion, Compose scale | Anthropic default log TTL hedged; not a blocker if disclosed |
| 10 Pricing & billing (secondary) | **Answered** | Competitor meters; Freemium+$12; Paddle MoR; hexagonal webhooks; BYOK later | Light-user $0.40 TL;DR vs $0.82 table (internal; see conflict log) |
| 11 Product architecture | **Answered** | Hybrid IA audit; Option A vs B/C; Chat merge; dual Review/Notes kept | `/library` URL deferred |
| 12 Growth & positioning | **Answered** | Statement A; beachhead PKM/Anki autodidacts; landing blueprint; Show HN sequence; no public book decks | SEO volume buckets are unclassified (labeled) |
| 13 AI integration patterns | **Answered** | Peer weave patterns; capability inventory; claim-level citations; Haiku Explain; ingest briefs | 400 root cause hypothesized, not reproduced |
| 14 Multi-provider models | **Answered** | 2026 landscape table; CN 1P vs Fireworks US; ports not LiteLLM; eval gate; matrix | Move 1 (Haiku quiz) already shipped — current-state error, not a coverage hole |
| 15 AI cost optimization | **Answered** | Driver inventory from code; cache mechanics; thinking diet; ledger; typical-MAU model | Thinking-token volume is an estimate until the ledger exists |

**Fleet verdict:** 15/15 answered. 0 missing. Partials are measurement/ops leftovers, not unanswered Owns.

---

## Claim matrix

Atomic claims asserted by **two or more** reports. Collision zones from meta-fleet-process §3.4 plus rq13–rq15.

| Claim (atomic) | RQs asserting | Agree? | Best primary source | Confidence | Action for synthesis |
|---|---|---|---|---|---|
| NotebookLM was renamed **Gemini Notebook** in July 2026; same product | rq01, rq12, rq07, rq11, rq13 | **Agree** (rq12 gives 16 Jul 2026) | [Google, 2026-07-16](https://blog.google/innovation-and-ai/products/gemini-notebook/notebooklm-gemini-notebook/) (fetched 2026-09-03) | **High** | Adopt rq12’s date; use “Gemini Notebook (ex-NotebookLM)” once, then one name |
| Click-to-passage + hover quote is 2026 table-stakes trust UX | rq01, rq06, rq07, rq12, rq13 | **Agree** | [Gemini Notebook chat help](https://support.google.com/notebooklm/answer/16179559) (fetched) | **High** | Launch blocker. Canonical UX write-up: rq01 §8 + rq13 Cycle 1 (`cited_text` spans) |
| Gemini Notebook flashcards are Got-it/Missed-it **session practice, not FSRS** | rq01, rq04, rq12 | **Agree** | [Flashcards help](https://support.google.com/notebooklm/answer/16958963) (fetched: progress persists; no scheduler) | **High** | Positioning wedge. Do not claim “we have flashcards too” (rq12) |
| Do **not** clone Audio Overviews / YouTube-RSS for public launch | rq01, rq12, rq13 | **Agree** | Product pages + rq01 HN 43848794 | **High** | Do-not-build. Optional later: chapter TTS (rq01/rq06/rq13 J), not two-host podcasts |
| Optional tutor-beside-content is skipped; tutor must **start / be woven** | rq01, rq03, rq07, rq13 | **Agree** | [Chalkbeat 2026-08-25](https://www.chalkbeat.org/2026/08/25/ai-tutoring-students-khanmigo-khan-academy-engagement-study/) + [Sal Khan 2026-07-15](https://blog.khanacademy.org/khanmigos-first-chapter-changed-how-i-think-about-ai-a-note-from-sal-khan/) (both fetched) | **High** | Pedagogy owner = rq03; rq01 supplies competitive lesson; do not leave Teach as a silent dock tab |
| Unguarded answer-giving tutors can **harm** later independent performance; hint-first | rq02, rq03 | **Agree** | Bastani et al. 2024 (SSRN 4895486) in rq02; AutoTutor ladder in rq03 | **High** | One Teach policy: elicit → ladder → assert. rq02 owns principle; rq03 owns session machine |
| Endless Socratic with no exit is also a failure | rq03 (Claude Learning Mode); rq02 why-not on Teach | **Agree** | rq03 Mashable + Anthropic Education post | **Medium** | Keep “just explain” as explicit opt-out, not default; CLOSE after a check |
| Empty quiz-deck “success” is a launch defect | rq01, rq04, rq07, brief | **Agree** (walkthrough) | In-repo + brief | **High** | Canonical fix: rq04 move 1 (reason codes + copy) |
| Keep free-recall + FSRS 1–4; do not make MCQ the flagship | rq02, rq04, ADR-0021 | **Agree** | ADR-0021 + Dunlosky/Kang via rq02/rq04 | **High** | Out of scope for RFC-004 |
| New-card / due-pile overload is the Anki-quit path; cap the *day’s job* | rq02, rq04, rq08 | **Agree** | Anki manual + FSRS FAQ (rq08) | **High** | rq08 owns Home/session cap; rq04 owns in-session learning-step requeue; rq02 owns criterion *learn* session — sequence, don’t merge into one PR |
| Retrieval stays **one SQL hybrid RRF**; no Qdrant/LangChain first | rq05, rq14, brief/ADR-0006 | **Agree** | ADR-0006 | **High** | Intelligence cycle 1 = rq05 headers + top_k, not a vector DB |
| Raising evidence `top_k` 8 → 12–20 helps recall and **raises** cost | rq05 (do it), rq15 (don’t as a *cost* move) | **Agree on the physics; different goal** | Anthropic contextual-retrieval post (rq05) | **High** | Quality cycle (rq05) after a ruler; cost ledger (rq15) must show the delta. Do not cut k without a reranker |
| Teach 1h `cache_control` exists; evidence documents sit **after** the breakpoint | rq13 (lists Teach cache as shipped), rq15 (ineffective until prefix ≥ 1,024 and docs move before breakpoint) | **Conflict on effectiveness** | Anthropic [prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) 1,024-tok Sonnet 5 minimum (fetched); in-repo `_build_request` | **High** on mechanics | Prefer **rq15**. Treat rq13 as “marker exists,” not “savings exist” |
| Answer path has **no** system-prompt cache marker | rq13, rq15 | **Agree** | `anthropic.py` (Ask system has no `cache_control`) | **High** | Cheap adapter cycle; single-shot Ask still misses the 1,024 minimum (rq15) |
| Quiz decks already use **Haiku 4.5 + Message Batches (50% off)** | rq13, rq15, config.py; **rq14 Move 1 treats this as a future cycle** | **Conflict on current state** | `quiz_model: str = "claude-haiku-4-5"` | **High** | Ignore rq14 Move 1 as already shipped. Next cheap Claude work is Haiku *Ask/Explain* (rq13/rq15), gated |
| Cited Ask primary stays **Claude Citations API**; cheap models must pass the nightly judge | rq13, rq14, rq15, ADR-0020 | **Agree** | Anthropic Citations docs; eval gate in rq14 | **High** | Do not silently swap Ask to Flash/GLM to save money |
| Do **not** send user books to Chinese 1P APIs by default; US-hosted open weights only after eval | rq14, rq09 (subprocessors) | **Agree** (rq09 names OpenAI/Anthropic only) | Fireworks [US-only](https://docs.fireworks.ai/serverless/us-only-serverless) (fetched: Kimi K3, DeepSeek V4 Flash, GLM 5.3) | **High** | Out of v1 public launch except as a later RFC amending ADR-0020 |
| Generation, not embeddings, is the cost bomb | rq09, rq10, rq13, rq14, rq15 | **Agree** | OpenAI embeddings $0.13/MTok (fetched); Anthropic Sonnet 5 $2/$10 (fetched) | **High** | Caps + thinking diet before embedding-model shopping |
| Per-cited-answer USD | rq09 ~$0.02–0.03 (Sonnet **4.6**, July); rq10 ~$0.03–0.04 (Sonnet **5**); rq14 ~$0.024–0.031; rq15 **~$0.020** including thinking | **Conflict (numbers)** | Anthropic pricing (fetched) + token assumptions | **Low** until ledger | See conflict log C1. Canonicalize on **rq15 method**; do not average |
| Typical hosted user-month AI COGS | rq10 light/medium/heavy $0.82 / $2.50 / $9.24 (table); rq15 typical **$1.16** | **Different personas, not a fight** | Worked arithmetic in each file | **Medium** | Publish both: rq15 = “polite learner”; rq10 medium = heavier. Do not use rq10 TL;DR $0.40 (contradicts its own table) |
| Per-user **daily** AI cap before open registration | rq09 $0.50–1.00/day; rq10 free = 8 Ask/day | **Compatible if sequenced** | Stripe abuse essay (rq07/rq09) | **Medium** | rq09 owns the *must* (hard stop); rq10 owns commercial packaging later |
| Invite-only / Turnstile before unrestricted register | rq09 must; rq07/rq12 want guest or no-signup sample | **Conflict (sequence)** | Show HN rules (rq12); Stripe farmed-account warning (rq07) | **Medium** | Synthesis must pick: invite beta → then sample-with-cap, or recorded demo on HN until caps exist |
| Email verify must **not** wall the aha; needed for open register + reset | rq07, rq09 | **Agree if invite-first** | Mixpanel / NN-g style sources in rq07 | **Medium** | Soft banner after wow; `EmailPort` the day the form opens |
| Shared pre-ingested **Standard Ebooks** sample; do not clone embeddings per user | rq07, rq12, rq01 on-ramp | **Agree** | [SE *Art of War*](https://standardebooks.org/ebooks/sun-tzu/the-art-of-war/lionel-giles) 24,005 words (fetched) | **High** | Canonical sample: rq07. Landing CTA: rq12 |
| No public sharing of book bytes / auto-cards from copyrighted sentences | rq09, rq12, rq08 | **Agree** | Readwise ToS/privacy (rq09); AnkiWeb/Quizlet DMCA (rq12) | **High** | Out of scope. Export-to-owner stays |
| Polar does **not** list Brazil as a seller-payout country | rq10 only, but load-bearing for billing | n/a (single RQ; verified) | [Polar supported countries](https://polar.sh/docs/merchant-of-record/supported-countries) (fetched: no Brazil) | **High** | Adopt. Paddle 5%+$0.50 also fetched |
| Landing is a bare tagline today; proof-above-fold is required | rq01, rq07, rq11, rq12 | **Agree** | `frontend/app/page.tsx` + brief | **High** | Copy/positioning: rq12. Activation path: rq07. Do not ship the page until Ask 400 is fixed (all four) |
| Ask notes toggle **default on**; Teach notes **default off** | brief; rq05 (toggle on); rq03 (AD-147 off for Teach) | **Agree** once disambiguated | `use-include-notes.ts` `SURFACE_DEFAULTS` | **High** | rq01’s “opt-in” means *user-controlled*, not default-off for Ask. Do not flip Ask default off |
| IA: keep book workspace + four-item shell; merge Ask+Teach into Chat | rq11; rq06 wants immersive chrome that hides the shell on `/read` | **Tension, not contradiction** | Peer IA in rq11 | **Medium** | Option A (rq11) + long-form `/read` (rq06) as layout exception. Do not delete Home/Review |
| Heatmap stays; consecutive streaks / XP / leaderboards stay out | rq08, rq12 (“don’t cheapen”), RFC-004 | **Agree** | Ryan & Deci / Sailer meta in rq08 | **High** | rq08 owns mechanics; rq12 owns landing copy (no flame) |
| Generation 400 must **not** delete the conversation | brief, rq01, rq05, rq07, rq10, rq14 | **Agree** | Walkthrough | **High** | Reliability cycle, owner-agnostic. Prerequisite for activation and HN |
| Figures are `[Image blocked]` because binaries never reach MinIO | rq06, rq02 (dual coding), rq13 (vision blocked on RQ06) | **Agree** | Streamdown harden + ingest (rq06) | **High** | Canonical cycle: rq06 Safe figures. Dual-coding cards wait on that |
| BYOK is later, not a launch substitute | rq10, rq14, rq01 (low danger) | **Agree** | Readwise Ghostreader BYOK (rq01/rq14) | **High** | After hosted Pro / fallback adapter |
| LiteLLM / OpenRouter must not become the composition root | rq14, rq15, ADR-0009 | **Agree** | ADR-0009 | **High** | Eval harness only (rq14 Move 4) |

---

## Conflict log

Only **real** disagreements. Complementary splits (rq02 principle / rq03 session / rq04 items) are not listed.

### C1 — Per-answer and per-user COGS (rq09 vs rq10 vs rq15; rq14 as a third arithmetic)

| Source | Unit | Number | What it assumes |
|---|---|---|---|
| rq09 §1.2 | Cited answer | **~$0.02–0.03** | Sonnet **4.6** at **$3/$15**; cites 2026-07-12 `anthropic-generation.md` (~$0.0225). **No thinking-token line.** |
| rq10 TL;DR / §cost-model | Cited answer | **~$0.03–0.04** | Sonnet **5** $2/$10; 6,500 in + 1,600 out (1,000 thinking) |
| rq10 table | Light / medium / heavy **month** | **$0.82 / $2.50 / $9.24** | 15/40/120 Asks + teach + decks |
| rq10 TL;DR | Same light user | **$0.40** | **Contradicts rq10’s own table** |
| rq14 | Cache-miss turn ~8k/800 | Sonnet 5 **$0.024** (ignore tokenizer) / **~$0.031** with ~30% tokenizer | No thinking split |
| rq15 | Cited Ask | **~$0.020** | Code-shaped: ~4,170 in + 1,200 out (**800 thinking estimate**). Typical MAU **$1.16** |

**Resolution rule for synthesis (do not average):** Learny’s live default is `claude-sonnet-5` at **$2 / $10**, confirmed on [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing) (fetched 2026-09-03; intro made permanent 2026-08-10). Sonnet 4.6 still lists **$3 / $15** but is **not** the product default. Prefer **rq15’s method** (include thinking as output; measure `thinking_tokens` in the ledger). Use rq10’s **$0.03–0.04** only as a conservative planning ceiling. Discard rq09’s $0.0225 for RFC math (stale model + omitted thinking — rq15 says this explicitly). Discard rq10 TL;DR **$0.40** light (table is $0.82).

### C2 — Model name scatter (rq09 “Sonnet 4.6” vs rq15 `claude-sonnet-5`)

Verified: both IDs exist. `LEARNY_GENERATION_MODEL` default is **`claude-sonnet-5`**. rq14 correctly lists both. rq09’s cost section is written as if 4.6 were current. **Not** a claim that Sonnet 5 is fictional. Synthesizer language: always `claude-sonnet-5` / Sonnet 5 unless discussing ADR-0020 history.

### C3 — Invite-only vs try-without-signup (rq09 vs rq07 / rq12)

- rq09: do not open registration on the current abuse surface; **invite-only XOR Turnstile** before unrestricted register; guest **upload** is an abuse/copyright hole.
- rq07: capped **guest Ask on a shared sample** (3 Qs / 24h); register to persist.
- rq12: Show HN wants **easy to try without signup**; recorded loop is the honest fallback if caps are not ready.

These are **launch-sequence** conflicts, not facts about Google or Stripe. Evidence for both sides is real. Synthesis must name a winner, e.g. invite-only hosted beta + public-domain demo that is either (a) rate-limited guest Ask after Cycle A caps, or (b) a recorded 90s loop + `docker compose` until then. Do not ship open guest Ask on an uncapped Anthropic key.

### C4 — Teach prompt-cache effectiveness (rq13 vs rq15)

- rq13 capability table: Teach already has 1h cache; Answer has none; “Ask is often single-shot → break-even only with history.”
- rq15: Teach caches the **cheap** prefix (system + history), often **below Sonnet 5’s 1,024-token minimum**; evidence documents are appended **after** the breakpoint. Official docs (fetched): shorter prefixes are a **silent no-op**.

In-repo `_build_request` matches rq15. **Prefer rq15** for any cost cycle. rq13 remains valid for “cache the Answer system prompt” as a small adapter change.

### C5 — Haiku-on-quiz as a “first cycle” (rq14 vs rq13 / rq15 / config)

rq14 Move 1: put Haiku 4.5 on `QuizGenerationPort`. rq13 and rq15: decks **already** batch on `claude-haiku-4-5`. Config default confirms. **rq14 is wrong about current state**, not about Haiku’s price or Citations support. Synthesis: skip Move 1; keep rq14 Moves 2+ (US fallback adapter, eval gate, no CN 1P).

### C6 — Competitive frame: “Gemini Notebook” vs “ChatGPT / Gemini Notebook” (rq01 vs rq12)

**Not a true disagreement.** rq01 segments the market and names Gemini Notebook as the default *free study studio*. rq12 starts from Dunford’s “what they do if you don’t exist” and answers **ChatGPT paste or Gemini Notebook upload**. Both reject “open-source NotebookLM” as the H1. Synthesis can use rq12’s stranger question and rq01’s landscape table without picking a winner.

### C7 — include_notes default

No report says “default the Ask notes toggle off.” Brief + `SURFACE_DEFAULTS`: Ask **on**, Teach **off**. rq01 “Notes in retrieval … opt-in” is **user-controlled**, not default-off. rq05 “second-brain toggle is already on by default” matches Ask. **No flip for RFC-004.**

### C8 — Chat-dock merge vs Teach-as-flagship (rq11 vs rq03)

rq11 Option A merges Ask+Teach into **Chat** with Answer | Tutor. rq03 needs a tutor that **opens** and owns a session. rq11 already records the why-not (Tutor can be missed). This is a **product-tension**, not a factual conflict. Resolution belongs in synthesis: merge the tabs **and** keep tutor-opens / empty-state teaching (rq03 Cycles 1–2). Do not resurrect `/ask` and `/teach` pages.

### C9 — Home duty vs pull (rq11 vs rq08 vs rq07)

rq11: when due > 0, Review card leads. rq08: finishable “today’s job,” then jump to the book. rq07: aha is cited Ask, not first review. Compatible: **first session** = sample Ask (rq07); **returning** Home = due-first when N>0 (rq11/rq08). Do not make Review the activation aha.

---

## Source-quality / unverified flags (by RQ)

Spot-check results (claim → URL support):

| # | Claim | URL | Result |
|---|---|---|---|
| 1 | NotebookLM → Gemini Notebook, July 2026; 30M users | Google rebrand 16 Jul 2026 | **Supports** (date + 30M / 600k orgs) |
| 2 | Hover quote, click jumps to source | Chat help 16179559 | **Supports** |
| 3 | Flashcards: Got it / Missed it; CSV; no FSRS in help | Flashcards help 16958963 | **Supports** (progress persists; still not a memory model) |
| 4 | Sonnet 5 $2/$10 permanent; Sonnet 4.6 $3/$15 | Anthropic pricing + Sonnet 5 post | **Supports** both price rows |
| 5 | Cache minimum 1,024 Sonnet 5; 4,096 Haiku 4.5; silent no-op below | Prompt caching docs | **Supports** rq15 |
| 6 | Embeddings $0.13 / 1M tokens | OpenAI model page | **Supports** |
| 7 | Khanmigo low engagement; “non-event”; must weave | Chalkbeat 2026-08-25; Khan 2026-07-15 | **Supports** rq01/rq03 |
| 8 | Polar payout list omits Brazil | Polar supported-countries | **Supports** rq10 (Botswana…Brunei; no Brazil) |
| 9 | Paddle 5% + $0.50; custom rate under $10 | paddle.com/pricing | **Supports** |
| 10 | SE *Art of War* ~24k words, US PD notice | standardebooks.org | **Supports** rq07 |
| 11 | Fireworks US SKUs include DeepSeek V4 Flash, GLM 5.3, Kimi K3 | Fireworks US-only | **Supports** rq14 host list |
| 12 | Anthropic API “not used for training”; ZDR sales-gated; Covered Models 30-day | API data-retention page | **Supports** rq09’s ZDR/Covered-Model story. **Does not print “7-day commercial logs”** — that figure stays **unverified** (rq09 already hedged) |

**By RQ (flags only):**

| RQ | Flags |
|---|---|
| rq01 | Reddit “user love” via **aitooldiscovery** aggregator; Matter maintenance-mode vs App Store updates already labeled conflicting; RemNote dollar prices from 2026 reviews not live checkout; StudyCardsAI as Reddit consensus (**secondary**). Landscape table itself is primary-heavy. |
| rq02 | Method note: some Sage/Nature PDFs blocked — DOIs given. Bastani cited as SSRN; not re-fetched here. Learning Scientists posts correctly demoted to practitioner overlay. |
| rq03 | Forbes “leaked Study Mode instructions” is **secondary**; OpenAI launch post is the primary. Mashable for Claude endless-Socratic. LearnLM numbers from arXiv (appropriate). |
| rq04 | Neurako/Memrizz/MDSteps cloze tips are community **secondary**; SuperMemo 20 rules + Matuschak are the canon. Expertium/awesome-fsrs for FSRS-6 internals — OK for scheduler, not for product UX. |
| rq05 | LlamaIndex/LangChain cited as *idea sources* then correctly rejected. Cohere/Voyage prices from vendor docs. “bge-m3 within a few nDCG of Cohere” is bake-off **secondary**. |
| rq06 | Kindle Ask-This-Book and Matter Co-Reader: blogs, labeled. Foliate-js CSP is primary-enough for the XSS class. |
| rq07 | Mixpanel “3× TTV” / 27% email-wall via practitioner blogs — rq07 already says directional. Grokipedia guest-access page is **not** OpenAI primary. SE + Gutenberg license pages are solid. |
| rq08 | Duolingo blog A/Bs = vendor DAU, correctly not treated as learning RCTs. “Why people quit Anki” = L. |
| rq09 | **7-day Anthropic API logs** not on the fetched retention page. Brazil private-copy via Copyright Atlas / Wikipedia penal-code note — not counsel. FastAPI-Redis rate-limit blog for XFF spoofing. Turnstile vs hCaptcha via Prosopo (**secondary**). |
| rq10 | NotebookLM USD from FelloAI / Google One writeups (official plans page didn’t print USD in rq10’s fetch). Blinkist/Shortform ranges via Nibble/Headway. **Internal** $0.40 vs $0.82. Polar/Paddle **verified**. |
| rq11 | Strongest in-repo audit; peer URLs are official help. |
| rq12 | GummySearch subreddit counts; Show HN “5k–30k visits” via Causo/King — directional. “Open-source NotebookLM” rejection is judgment, well argued. |
| rq13 | Perplexity citation UX via aiuxplayground/ziptie (**secondary**); Anthropic/OpenAI API rows are primary. 400 = **hypothesis** (citations ⊕ JSON), not a reproduced trace. |
| rq14 | OpenRouter prices for Qwen/GPT-5; GPT-5 API row marked aggregator. Fireworks US list **verified**. Kimi K3 US “+10%” vs Fireworks copy “US-only = +50% from 2026-09-01” is a **pricing-page tension** — re-check before any RFC that quotes US SKU dollars. |
| rq15 | Strongest code-grounded cost file. Thinking 800 tok is **explicitly estimated**. Typical-MAU mix is stated, not measured. |

---

## True gaps

Bar: would RFC-004 **ship the wrong thing** without another memo (July 12: quiz schema, VPS fit, embed dim). “Nice extra detail” is not a gap.

| Candidate | Verdict |
|---|---|
| Exact Anthropic 400 request dump | **Not a research gap.** Reliability cycle + keep-the-thread is already specified. Root-cause is engineering. |
| Paddle vs Lemon Squeezy Brazil payout paperwork | **Not a true gap.** Pricing is secondary; Polar is already ruled out; LS is named fallback. |
| Labeled real-book retrieval set (rq05 ruler) | **Would improve measurement**, not change “headers first, no Qdrant.” Do not block RFC freeze. |
| Measured `thinking_tokens` | Ledger is an **implementation** cycle (rq15), not a missing literature memo. |
| Intra-section resume encoding (CFI vs %) | rq06 already parks a spike inside the cycle. |
| EU representative / ZDR approval | rq09 Cycle F; policy, not missing competitive research. |
| Haiku Ask faithfulness on Learny snapshots | **Eval work after** thinking-diet, not a pre-RFC memo. Gate already exists. |

**True gaps that would change a synthesis decision: none.**

---

## Duplicate work

Ignore overlapping prose in synthesis; cite the **canonical RQ** for the decision.

| Topic | Canonical owner | Also repeats (cite only if needed) |
|---|---|---|
| Competitor feature matrix | **rq01** | rq12 set table; rq11 NotebookLM IA |
| H1 / landing / Show HN / beachhead | **rq12** | rq01 positioning sentence; rq07 landing proof; rq11 “RQ12’s problem” |
| Learning-science principles | **rq02** | — |
| Teach playbook, tutor-opens, phase machine | **rq03** | rq02 #2; rq01 Khanmigo; rq13 pattern M / Cycle 4 placement |
| Card formulation, QC gates, review undo | **rq04** | rq02 successive-relearning *policy*; rq01 deck honesty |
| Hybrid retrieval / headers / parent expand / long-context | **rq05** | rq03 title-as-query; rq13 typeahead + query rewrite |
| Claim-level citation **API fields** | **rq13** | rq01 table-stakes UX; rq05 quote-first prompt |
| Reader figures, chrome, phone, typography | **rq06** | rq02 dual coding; rq11 immersive overlap |
| Sitemap / Chat merge / Home weighting | **rq11** | rq06 long-form; rq07 empty-library copy |
| Sample book, aha event, guest cap, ingest stages | **rq07** | rq12 try-without-signup; rq01 demo book |
| Heatmap / no streaks / digest / today’s-job cap | **rq08** | rq12 “don’t cheapen”; rq04 new-card cap |
| Abuse, Redis limiter, ToS, DMCA, deletion, disk | **rq09** | rq10 “caps without billing”; rq15 SpendPort |
| SKU, Paddle, free/Pro meters | **rq10** | rq15 unit costs; rq09 $0.50–1/day |
| Unused provider APIs, selection verbs, briefs | **rq13** | rq01 Studio; rq05 contextual Haiku |
| Provider matrix, CN vs US, eval promotion | **rq14** | rq15 Haiku Ask A/B (cost lens) |
| Cache breakpoints, thinking diet, cost ledger | **rq15** | rq13 cache row; rq10 COGS tables |

Khanmigo “weave the tutor” appears in rq01, rq03, rq07, rq13 — **one** synthesis paragraph, traced to rq03 + Chalkbeat.

NotebookLM rename appears in almost every file after rq01 — **one** sentence in synthesis.

---

## Follow-up recommendation

**None.** Do not spawn `followup-*.md`. Conflicts above are reconcilable from files already on disk plus the spot-checks in this critique. A 400 reproduction, a retrieval labeled set, and a spend ledger are **build cycles**, not research memos.

---

## Spec conformance

Workers were briefed on the inherited house shape (TL;DR → evidence → implications with why-not → cycle-sized moves), **not** the 2026-09-03 YAML+Method template. Per meta-fleet-process §5: **flag** missing front matter / Method / Limitations; **do not fail** the report for those.

### 14-point checklist (fleet view)

| # | Check | Fleet result |
|---|---|---|
| 1 Front matter | **Flag all 15** — none have YAML `id` / `overall_confidence` | Do not retrofit |
| 2 TL;DR as structured abstract | **Pass** on rq03, rq04, rq05, rq07, rq08, rq11, rq12, rq13, rq14, rq15. rq01/rq06/rq09/rq10 are long but still answer the question. | |
| 3 Findings ≠ recommendations | **Flag most** — old template mixes “Recommend:” into the evidence body (especially rq01 §positioning, rq04 review-UX, rq09 launch checklist). rq11 and rq14 separate options more cleanly. | Synthesizer: treat “Cycle-sized moves” as advice, Findings/Evidence as facts |
| 4 Inline source links | **Pass** on the load-bearing claims that were spot-checked. Weaker on rq01 Reddit, rq07 PLG blogs, rq12 channel playbooks | |
| 5 Primary over secondary | **Pass** core claims. **Flag** aggregator prices (NotebookLM USD, RemNote, Blinkist) | |
| 6 Absence labeled | **Pass** where it matters (rq01 Matter conflict; rq15 thinking estimate; rq09 7-day hedge). **Flag** unlabeled “Gemini Notebook has no FSRS” — supported by help-page silence + secondary “SRS: none,” which is a fair **absence-inference** and should stay hedged |
| 7 Dates on time-sensitive facts | **Pass** generally (2026-09-03). rq09 costs still carry July 2026 model IDs | |
| 8 Ordinal confidence on recommendations | **Flag all** — why-not is present; High/Medium/Low labels mostly absent (rq08 uses H/M/L on *evidence*, closest) | |
| 9 Named Limitations | **Flag** most. Present-enough: rq02 method note, rq06 open issues, rq08 caveats, rq15 sensitivity, rq14 snapshot warning | |
| 10 Why-recommend and why-not | **Pass** on cycle lists across the fleet (the house contract they were given) | |
| 11 Cycle list ≤7 | **Exceeds (flag):** rq01 (12), rq02 (9), rq04 (10), rq05 (9), rq12 (8), rq14 (8). **Within cap:** rq03 (5), rq06 (6), rq07 (7), rq08 (4), rq09 (6), rq10 (5), rq11 (7), rq13 (5), rq15 (5) | Synthesizer SoF ≤7 launch bets; do not paste the union |
| 12 Sources index matches inline | Uneven. rq01/rq12/rq13/rq14 have end lists. Several others are inline-only (acceptable under old template) | |
| 13 Reusable H2 names | **Flag** — almost none use frozen Method / Findings / Implications headings. Cycle-sized moves **are** greppable | |
| 14 Verification stance | **Pass** for in-repo critiques (rq03, rq04, rq05, rq06, rq11, rq15). Weaker where SEO blogs carry competitor prices | |

**Recommendations mixed into findings:** treat as expected under the brief they got. Worst mixers for a synthesizer: rq01 (positioning inside the landscape essay), rq09 (checklist reads like RFC text), rq04 (review-UX “must-have” inside Evidence). Best splits: rq11 options A/B/C; rq14 matrix + why-not on CN 1P.

---

## Implications for the synthesis (what not to paper over)

1. **Canonicalize costs on rq15 + live `claude-sonnet-5`.** Publishing a blended “~$0.025/answer” hides that thinking may be half the bill and that rq09 used a different model.
2. **Name the invite vs demo sequence.** A synthesis that says both “invite-only” and “try without signup” without an order will ship an uncapped public Ask.
3. **Do not treat Teach caching as a done cost win.** Moving evidence before the breakpoint is a real cycle; the marker is not the savings.
4. **Do not re-litigate Haiku-on-quiz.** Spend the cheap-Claude slot on gated Haiku *Explain/Ask*, not on re-enabling a default that exists.
5. **SoF table ≤7 rows.** The union of cycle lists is a backlog, not RFC-004. Pricing may be one row marked secondary.
6. **Keep hexagonal locks.** No report that was in-scope argues otherwise; rq14’s LiteLLM/OpenRouter path is explicitly off the request path.

## Cycle-sized moves (required follow-ups before RFC freeze)

**None** — equivalent to the Follow-up recommendation above. The synthesizer can freeze from this folder.

---

## Limitations and uncertainty

- Spot-checks were ~12 URLs, not a Citation Agent over every footnote. SEO-farm competitor prices (RemNote, Blinkist, NotebookLM USD) were not re-checked at checkout.
- Bastani 2024 and Dunlosky 2013 were not re-downloaded; they are canonical citations, not the collision-zone load-bearers.
- Anthropic commercial log TTL (rq09’s ~7 days) remains **unverified** on the API retention page fetched 2026-09-03.
- Fireworks US-only **dollar** premiums were not re-fetched from the pricing table — only the SKU list and the +50% policy sentence.
- This critic did not run the live Ask path, so the 2026-09-03 400 is taken as a brief fact, not re-observed.
- Granola / meeting context was not queried; this fleet is file-native research, not a meeting decision.

---

## Sources

Cited (fetched 2026-09-03):

1. Anthropic, Claude API pricing — https://platform.claude.com/docs/en/about-claude/pricing
2. Anthropic, “Introducing Claude Sonnet 5” (2026-06-30; pricing edit 2026-08-10) — https://www.anthropic.com/news/claude-sonnet-5
3. Anthropic, Prompt caching (minimums) — https://platform.claude.com/docs/en/build-with-claude/prompt-caching
4. Anthropic, API and data retention — https://platform.claude.com/docs/en/manage-claude/api-and-data-retention
5. Google, “NotebookLM is now Gemini Notebook” (2026-07-16) — https://blog.google/innovation-and-ai/products/gemini-notebook/notebooklm-gemini-notebook/
6. Gemini Notebook product — https://notebooklm.google/
7. Gemini Notebook Help, Use chat (citations) — https://support.google.com/notebooklm/answer/16179559
8. Gemini Notebook Help, Flashcards or Quizzes — https://support.google.com/notebooklm/answer/16958963
9. Chalkbeat, Khanmigo engagement study (2026-08-25) — https://www.chalkbeat.org/2026/08/25/ai-tutoring-students-khanmigo-khan-academy-engagement-study/
10. Sal Khan, Khanmigo note (2026-07-15) — https://blog.khanacademy.org/khanmigos-first-chapter-changed-how-i-think-about-ai-a-note-from-sal-khan/
11. OpenAI, text-embedding-3-large — https://developers.openai.com/api/docs/models/text-embedding-3-large
12. Fireworks, US-only Serverless — https://docs.fireworks.ai/serverless/us-only-serverless
13. Polar, Supported countries — https://polar.sh/docs/merchant-of-record/supported-countries
14. Paddle, Pricing — https://www.paddle.com/pricing
15. Standard Ebooks, *The Art of War* (Giles) — https://standardebooks.org/ebooks/sun-tzu/the-art-of-war/lionel-giles

In-repo (not web): `backend/app/core/config.py` (`generation_model`, `quiz_model`); `backend/app/infrastructure/answering/anthropic.py` (`_build_request`); `frontend/app/components/use-include-notes.ts` (`SURFACE_DEFAULTS`); `docs/research/2026-07-12/anthropic-generation.md` (rq09’s cost ancestor).

### Consulted, not cited

- Web search snippets on NotebookLM vs FSRS (third-party blogs) — used only to see whether official help had silently added a scheduler; it had not.
