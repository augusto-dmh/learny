---
id: synthesis
title: Public-launch arc — candidate RFC-0007
question: Given rq01–rq15 and the gap critique, what prioritized arc takes Learny from v0.3.0 to a public multi-tenant launch — more intelligent, more attractive, quality-first, monetization secondary?
date: 2026-09-03
sources_accessed: 2026-09-03
status: complete
overall_confidence: high
primary_sources_count: 15 (RQ reports) + gap-critique spot-checks
---

# Synthesis — public-launch arc (candidate RFC-0007)

Written by the fleet orchestrator from the files on disk (fifteen `rqNN` reports + [gap-critique.md](gap-critique.md)), not from chat memory. Costs follow the critique's canonicalization (rq15 method, live `claude-sonnet-5` at $2/$10). RFC numbering: 0001–0006 exist; this arc is **RFC-0007**.

## TL;DR

Learny already owns a loop no competitor ships end-to-end: structure-preserving book → click-to-passage citations → section-scoped teaching → FSRS review → notes-as-evidence → Anki/Obsidian export ([rq01](rq01-competitive-landscape.md)). The public-launch work is not new pillars; it is making that loop **trustworthy for a stranger** (the observed Anthropic 400 that deletes a conversation is named a blocker by six reports), **complete as a reading product** (figures render, chrome recedes, phones work), **pedagogically honest** (a tutor that elicits before it tells; cards with a formulation bar; a finishable daily session), **reachable in one session** (shared public-domain sample, honest first-run), and **safe to open** (user-keyed rate limits, per-user AI spend caps, legal pages, deletion). Cost engineering (thinking diet, a real teach cache, a spend ledger) cuts the typical active learner from ~$1.16 to ~$0.86/month before any model change (rq15). Pricing stays out of the launch arc — caps yes, checkout later (rq10).

Seven bets below; Bet 1 (trustworthy Ask) gates everything; Bet 6 (safety rails) gates open registration. Main limitation: cost rows rest on estimated thinking tokens until the ledger exists, and the aha definition (first cited answer) is provisional until D7 data exists.

## Method

Inputs: the fifteen RQ reports, the gap critique's coverage map / claim matrix / conflict log, and the two meta reports for structure. This document adopts the critique's conflict resolutions verbatim where they were factual (costs, current-state errors) and decides the product tensions it deliberately left open (launch sequence, chat merge, Home weighting). No new web research was performed. Every bet row traces to RQ sections; the union of the fifteen cycle lists (≈100 items) was **not** concatenated — the critique's duplicate-work table picked canonical owners.

---

## Summary of findings — the seven launch bets

| # | Bet | What ships | Confidence | Traces | Size |
|---|---|---|---|---|---|
| 1 | **Trustworthy cited Ask** (gate for all) | Fix the real-provider 400 (keep the thread, show retry, never delete); claim-level citation spans from `cited_text` (hover quote + exact-span highlight); calm "not in this book" abstention path | High | Brief walkthrough; rq01 §8 items 1+4; rq13 Cycle 1; rq05 §10; rq07 Move 1 | 1–2 cycles |
| 2 | **A reader people read in** | Safe figures (extract to MinIO, allowlisted same-origin `<img>`, re-encode, never iframe EPUB HTML); immersive long-form chrome on `/read` (`[` `]` toggles); phone-usable column with bottom-sheet dock + touch capture | High | rq06 P0 1–3 + cycles; rq02 §8 (dual coding unblocked); rq13 (vision unblocked) | 3 cycles |
| 3 | **Teach becomes a tutor** | Frozen teach playbook (pump→hint→prompt→assert, one move/turn, close after an unaided check); tutor-opens with section-first retrieval; Ask+Teach merged into one Chat dock (Answer \| Tutor); check-pass → offer one FSRS card | High on design, Medium on learning gains | rq03 Cycles 1–4; rq02 #2 (Bastani guardrails); rq11 Option A item 2; critique C8 | 2–3 cycles |
| 4 | **Review worth returning to** | Empty-deck honesty + discard reason codes; deterministic formulation gates + prompt rewrite (one fact, no stopword clozes, no set dumps); review undo + interval labels + in-session learning-step requeue; flag/edit on due cards; bounded "today's session" with Done-for-today; opt-in due digest later | High | rq04 Moves 1–4; rq08 Cycles 1–2; rq02 #1/#4 (criterion session, retrieval-first empty states) | 3–4 cycles |
| 5 | **First session that converts** | Shared pre-ingested Standard Ebooks sample (*The Art of War*) as a system source with a canned cited question + 5-card starter deck; ingest-stage transparency ("use the sample while you wait"); library honesty (one **Open** per book, EPUB/PDF copy, overflow verbs); naming pass (Library, Tutor, Download notes); landing page with proof above the fold; server-side activation events (`first_cited_answer`) | High | rq07 flow + funnel; rq11 Cycles 1, 3–6; rq12 Moves 1–3; rq01 on-ramp | 3 cycles |
| 6 | **Safe to open the doors** (gate for registration) | Redis shared limiter keyed by user (proxy-aware IP for auth routes); per-user daily AI-spend cap on a Postgres ledger + operator kill switch; source count/bytes quotas + per-user in-flight ingestion cap; invite-only gate (Turnstile+disposable-block as the opening step); ToS/privacy/copyright pages + DMCA contact; account deletion incl. MinIO objects; `EmailPort` (verify+reset) the day the form opens | High | rq09 Cycles A–D + checklist; rq15 Cycle 1 (ledger); rq10 "caps without billing"; rq07 §verification | 3–4 cycles |
| 7 | **Cheaper intelligence, same trust** | Cost ledger behind a `SpendPort` (persist tokens incl. thinking + USD); `effort=low` on Ask judge-gated; move teach evidence before the 1h cache breakpoint; Haiku selection-Explain (fast, no thinking); OpenAI-compatible fallback adapter aimed at US-hosted open weights, outage-only, behind the §4 rq14 eval gate | High on mechanics, Medium on judge outcomes | rq15 Cycles 1–3 + savings table; rq13 Cycle 2; rq14 Moves 2–4 + promotion checklist; critique C1/C4/C5 | 3 cycles |

**Sequencing.** Bet 1 first — activation (5), landing (5), and any launch motion (rq12 Move 4: "if the 400 is still open, do not launch") are gated on it. Bets 2–5 and 7 parallelize by surface (reader / tutor / review / activation / adapters). Bet 6 must be green before strangers can register; until then the hosted instance is invite-only. Launch motion after 1+5+6: Show HN with self-host + the sample path, per rq12's staggered sequence.

**Pricing (explicitly secondary, per the brief):** no checkout in this arc. Free-tier-shaped caps land inside Bet 6; the Paddle/Freemium decision (rq10: $12/$99 Pro, Paddle MoR — Polar cannot pay a Brazilian seller) is recorded and deferred until the loop is proven publicly.

---

## Conflict resolutions

Numbered; each names the winner and why. C-numbers follow [gap-critique.md](gap-critique.md).

1. **COGS numbers (C1, C2).** Canonical: **rq15's method** on live `claude-sonnet-5` ($2/$10): ~$0.020/cited answer (thinking ≈ 60% of that), ~$1.16/typical active learner-month. rq09's $0.0225 is July Sonnet-4.6 arithmetic without thinking — discarded for planning. rq10's $0.03–0.04 survives only as a conservative ceiling; its TL;DR $0.40 light-user figure contradicts its own table ($0.82) and is discarded. All synthesis-level cost claims become measurements once Bet 7's ledger ships.
2. **Invite-only vs try-without-signup (C3).** Sequence, not either/or: **invite-only hosted beta first** (rq09 wins the opening state — the current limiter is broken behind the proxy and there is no spend cap), and the public **sample-book demo ships only after Bet 6's caps**, as capped guest Ask (rq07's 3 questions/24h) or, if caps slip, a recorded 90-second loop + `docker compose up` for the HN launch (rq12's honest fallback). No uncapped public Ask, ever.
3. **Teach cache (C4).** **rq15 wins**: the existing 1h breakpoint protects a prefix usually below Sonnet 5's 1,024-token cache minimum while ~4k evidence tokens sit after it. "Cache exists" (rq13) ≠ "savings exist." Bet 7 moves the stable section documents before the breakpoint and measures `cache_read_input_tokens`.
4. **Haiku on quiz (C5).** Already shipped (`LEARNY_QUIZ_MODEL=claude-haiku-4-5`, batched). rq14 Move 1 is dropped; the cheap-Claude slot goes to **Haiku selection-Explain** (rq13) and, later, a judge-gated Haiku Ask A/B (rq15 Cycle 5).
5. **Chat merge vs tutor visibility (C8).** Both: merge Ask+Teach into one Chat dock (rq11) **and** make the tutor open the session with section-first retrieval (rq03), with the Chat empty state naming both modes. The tutor's discoverability is carried by behavior (it speaks first) rather than by a separate tab that Khanmigo evidence says gets skipped.
6. **Home: duty vs pull (C9).** First session is Ask-first (rq07's aha); the *returning* Home leads with the due-cards card when due > 0, showing "~N min" and starting a bounded session (rq11 + rq08). Done-for-today links back into the current book — review is the duty, reading is the pull.
7. **Notes toggle default (C7).** No change: Ask `include_notes` default on, Teach off. rq01's "opt-in" reads as user-controlled, which it already is.
8. **Competitive frame (C6).** rq12's stranger question ("why not ChatGPT / Gemini Notebook?") sets the positioning; rq01's landscape table is the evidence base. Positioning statement A: *book intelligence with citations you can trust and a memory that lasts* — differentiated on FSRS + notes-as-evidence + portability/self-host, never on "better AI" or podcast parity.
9. **Evidence budget: cost vs quality (claim matrix, top_k row).** Raising `top_k` 8→12–20 is a **quality** cycle owned by rq05, allowed only after its "retrieval ruler" exists and with Bet 7's ledger showing the cost delta. It is not part of the launch arc; cutting k for cost is forbidden without a reranker.

---

## Must-be-true / out-of-scope per bet

**Bet 1 — Trustworthy Ask.** Must-be-true: a failed generation leaves the conversation intact with a retry affordance; the two Anthropic request shapes (citations-enabled vs structured-output) are covered by shape tests; citation spans are byte-identical to the snippet sent to the provider (embed headers, if rq05's cycle ever ships, stay out of Citations `document` bodies). Out of scope: switching the Ask primary model; streaming redesign.

**Bet 2 — Reader.** Must-be-true: no EPUB HTML is ever iframed or given script rights; images are re-encoded, owner-scoped, allowlisted by prefix in Learny code (not library defaults); the 65ch measure survives the dock on desktop; capture works by touch. Out of scope: native apps, pagination, multi-color highlights, intra-section resume (follow-on spike per rq06).

**Bet 3 — Tutor.** Must-be-true: the system prompt stays byte-stable (cache + ADR-0020); hint-ladder state is application-owned, not model memory; citations still attach to every claim about the book; "just explain" remains one tap; sessions close after a passed check. Out of scope: new tutor models or LearnLM (ADR-0020 lock), BKT/knowledge tracing, forbidding answers.

**Bet 4 — Review.** Must-be-true: scheduling and `review_log` rows are never rewritten by content edits (the v3 invariant); undo is a compensating event, not a deletion; formulation gates run identically for every adapter; a zero-item deck explains itself. Out of scope: MCQ, a second scheduler, per-user FSRS optimizer (volume-gated per ADR-0021), LLM card-critique pass.

**Bet 5 — First session.** Must-be-true: the sample is one shared system corpus (embeddings paid once, never cloned per user); sample ACL is world-readable Ask/Read/Teach with user-scoped conversations/highlights; activation events fire server-side only on success; no email-verification wall before the aha; SE licensing notice shown. Out of scope: product tours, guest upload, a 20-book catalog, Amplitude/Mixpanel dependencies.

**Bet 6 — Safety rails.** Must-be-true: limits key on `user_id` for expensive routes and trusted-proxy IP for auth; the spend cap is a hard stop with honest copy; deletion removes MinIO objects and cascades Postgres; no public sharing of book bytes or book-derived cards; ToS takes the narrow license (host/parse/embed/retrieve/generate for that user only). Out of scope: EU representative unless the EU is targeted (rq09 Cycle F), ZDR as a blocker, publisher hash-scanning, Kubernetes.

**Bet 7 — Cost.** Must-be-true: every optimization is judge-gated against the nightly thresholds (faithfulness ≥ 0.90, relevancy ≥ 3.1, `citation_valid` 12/12); fallback fires only on transport errors, never on grounded `not_found`; fallback hosts are US-hosted (Fireworks US / Together) — CN first-party APIs require an explicit RFC exception; no LiteLLM/OpenRouter in the request path. Out of scope: embedding-model swap (ADR-0019 stands; Qwen3-Embedding is a later retrieval A/B), semantic answer caching (rejected for a citations product), BYOK, model-picker UI.

---

## Assumption check against locked decisions

| Lock | Status in this arc |
|---|---|
| ADR-0002/0003 (structure canonical; citations core) | Reinforced — Bets 1/3/4 spend on citation tactility and grounded pedagogy |
| ADR-0006 (pgvector hybrid; reranker = escape hatch) | Untouched; rq05's headers/top_k cycles deferred behind its own ruler; no vector DB |
| ADR-0007/0009 (Learny ports; no framework core) | Honored — new capability = adapter or new Learny port (`SpendPort`, later `SpeechPort`); LiteLLM/OpenRouter off the request path |
| ADR-0008/0023 (Compose on VPS, Caddy edge) | Honored — headroom moves are software quotas, off-box object storage, a second worker replica (rq09 Cycle E), not a platform rewrite |
| ADR-0019 (OpenAI embeddings @1536) | Untouched; re-embed rejected as a cost move |
| ADR-0020 (Anthropic generation) | Amended, not replaced, by Bet 7's fallback adapter — requires the RFC + ADR amendment rq14 §5 specifies |
| ADR-0021 (active recall; FSRS; deferred optimizer) | Honored; Bet 4 adds gates and UX, not a new scheduler |
| ADR-0026 (notes model; export one-way) | Untouched; export surfaced louder (Bet 5), never gated |
| RFC-004/0006 caps (no notifications; no marketing landing) | **Deliberately thawed, narrowly**: opt-in due digest (rq08 Cycle 2) and a proof-above-fold landing (rq12) — both must be recorded as amendments in RFC-0007, not silent contradictions |

## Watch-items

- **Gemini Notebook ships a real scheduler.** Today its flashcards are session practice, not FSRS (verified in the critique). If that changes, refresh rq01 §7 and the positioning wedge — the FSRS claim weakens, portability/self-host does not.
- **Anthropic pricing/model changes.** Sonnet 5 $2/$10 is "permanent" as of 2026-08-10; a repricing or a Sonnet 6 reruns rq15's arithmetic and the judge baselines (re-record snapshots per `eval-calibration.md`).
- **Fireworks US premium (+50% policy from 2026-09-01) vs listed SKU prices** — the critique flagged a pricing-page tension; re-fetch before the Bet 7 fallback RFC quotes dollars.
- **Polar adding Brazil payouts** would reopen rq10's billing choice; until then Paddle, fallback Lemon Squeezy.
- **The ~7-day Anthropic commercial log TTL is unverified** — confirm on the live retention page before the privacy policy states a number.
- **D7 data vs the provisional aha.** If `first_review` predicts retention better than `first_cited_answer`, re-weight Bet 5's funnel (rq07 already specifies the validation).

## Do-not-build (consolidated from all fifteen reports)

Audio-Overview/podcast clone; YouTube/RSS capture; MCQ; a second scheduler; consecutive streaks, XP, badges, leaderboards, freeze shops; shared-deck marketplace or any public surface carrying book bytes; vector DB / LangChain / LlamaIndex / LiteLLM-as-core; CN first-party inference of user books; per-user clones of sample embeddings; native mobile apps; multi-color highlights; a raw model-picker; lifetime pricing; charging for FSRS or export.

## Traceability index

Bet 1 → rq13 §Cycle 1, rq01 §8, rq05 §10, rq07 §Move 1 · Bet 2 → rq06 §Cycle 1–3 · Bet 3 → rq03 §Cycle 1–4, rq02 §2, rq11 §Cycle 2 · Bet 4 → rq04 §Move 1–4, rq08 §Cycle 1–2, rq02 §1/§4 · Bet 5 → rq07 §flow/§funnel, rq11 §Cycle 1/3–6, rq12 §Move 1–3 · Bet 6 → rq09 §Cycle A–D, rq15 §Cycle 1, rq10 §move 1 · Bet 7 → rq15 §Cycle 1–3, rq13 §Cycle 2, rq14 §Move 2–4. Conflicts → gap-critique §Conflict log.

## Next step

Materialize this synthesis as **RFC-0007 — public-launch roadmap** (cycles = the seven bets, sequenced 1 → {2,3,4,5,7} → 6 → launch), with the ADR-0020 amendment (fallback adapter) and the RFC-004/0006 thaw notes (digest, landing) recorded inside it. The research folder stays as the evidence base.
