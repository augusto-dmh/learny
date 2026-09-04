# RFC-0007: Public-Launch Roadmap

- **Status**: Draft — proposed 2026-09-03
- **Date**: 2026-09-03
- **Driver**: Augusto
- **Approvers**: Augusto
- **Impact**: HIGH — defines the arc from v0.3.0 (single-user dogfood) to a hosted instance strangers can register on, thaws two caps set by RFC-004/RFC-006, and schedules an ADR-0020 amendment
- **Due Date**: cycle-by-cycle; no calendar deadline
- **Resources**: [2026-09-03 research folder](../research/2026-09-03/) (fifteen RQ reports + [gap critique](../research/2026-09-03/gap-critique.md)), [synthesis](../research/2026-09-03/synthesis.md), [RFC-006](0006-reading-first-ux-overhaul.md), [RFC-005](0005-evidence-gated-hardening-roadmap.md)

## Background

**Current state.** v0.3.0 ships the loop end to end: structure-preserving ingestion, hybrid retrieval, cited Ask, section-scoped Teach, FSRS review, notes-as-evidence, Anki/Obsidian export, and the reading-first workspace RFC-006 delivered across Cycles A–E. RFC-005 is paused after Cycle E (worker liveness and point-in-time recovery, PR #62); its Cycle F stays queued. The app has exactly one user, and the hosted instance has never been offered to anyone else.

**Problem.** A 2026-09-03 walkthrough on the live stack with real provider keys produced the blocker: Ask embeds successfully at OpenAI, then fails at Anthropic `POST /v1/messages` with **400 Bad Request**. The UI shows "Answer generation failed. Please try again." and **the conversation disappears**. Six of the fifteen research reports name this independently. Nothing downstream survives it: the activation event the funnel is built on (`first_cited_answer`) cannot fire, the landing page has no honest demo to point at, and the one question a stranger asks first is the one that vanishes.

The blocker is the acute case of a general condition. Learny is a product for one person who already knows how it works. Fifteen reports converge on the same five deficits for a stranger: the loop is not **trustworthy** (the 400; citations that name a chunk instead of a sentence), the reader is not **complete** (figures do not render, chrome does not recede, phones do not work), the tutor **tells before it elicits**, the first session has **no on-ramp** (no sample book, no honest ingest wait), and the instance is **not safe to open** (the rate limiter keys on a proxy IP, there is no spend cap, no ToS, no account deletion, no email port).

**Why now.** RFC-006 closed with Cycle E. There is no next unstarted roadmap row, so the next cycle either starts an arc or is an orphan. The research that would justify that arc already exists on disk and was written against the running product, not from memory.

**What happens if we don't decide.** The 400 stays open, which by [rq12](../research/2026-09-03/rq12-growth-positioning.md) Move 4 forbids any launch motion. Work continues by taste rather than by evidence that is three weeks fresh and will age. Two caps set by earlier RFCs (no notifications, no marketing landing) get contradicted silently by whatever cycle happens to need them, instead of being thawed on the record.

## Assumptions

| # | Assumption | Confidence | Invalidation Trigger |
|---|------------|------------|----------------------|
| 1 | The observed 400 is fixable inside the existing adapter — a request-shape or parameter problem, not a model or provider problem | Medium — Citations ⊕ `output_config.format` is a documented 400 class, but the live dump has not been captured yet | A dump showing the rejection is about the model, the account, or a capability Claude no longer offers with citations |
| 2 | The Citations API returns `cited_text` with character offsets into the exact `source.data` we send, so claim-level spans need an adapter change and no second provider call | High — the response objects already carry the fields; the adapter drops them | Offsets that do not index the submitted string (a different normalization, a different encoding) |
| 3 | Cost per active learner is ~$1.16/month at live Sonnet 5 pricing, ~60% of a cited answer being thinking tokens | Medium — [rq15](../research/2026-09-03/rq15-ai-cost-optimization.md) arithmetic on estimated thinking tokens; nothing measures it today | The spend ledger (Bet 7) reporting a materially different figure |
| 4 | `first_cited_answer` is the activation event worth optimizing | Medium — provisional; no D7 retention data exists | D7 data showing `first_review` predicts retention better |
| 5 | Invite-only is an acceptable opening state for the hosted instance; a public uncapped demo is not required to validate the loop | High — driver's call, and the alternative requires Bet 6 to land first anyway | A launch opportunity that requires open registration before Bet 6 is green |
| 6 | Provider locks hold for the arc: OpenAI embeddings (ADR-0019) and Anthropic generation (ADR-0020), the latter **amended** rather than replaced by Bet 7's outage-only fallback | High | Sustained Anthropic unavailability, or a repricing that breaks the cost model |
| 7 | The author remains the only committed user through Bets 1–5; no data migration is owed to third parties until registration opens | High | Any invited user before Bet 6 |

## Decision Criteria

Stated before options. The chosen arc must:

| Priority | Criterion | Description | Weight |
|----------|-----------|-------------|--------|
| 1 | **Trust before reach** | Nothing that brings people in ships before the loop stops losing their first question | Must-have |
| 2 | **Safety gates registration** | Open registration is blocked until user-keyed limits, a spend cap, legal pages, and deletion exist | Must-have |
| 3 | **Evidence-anchored cycles** | Every cycle traces to a named RQ section, not to taste; cost claims become measurements once the ledger exists | Must-have |
| 4 | **Reviewable cycles** | One cycle is one PR-sized ship-cycle; no cycle mixes a migration with an IA rework | High |
| 5 | **Caps thawed on the record** | Any contradiction of an RFC-004/RFC-006 exclusion is written into this RFC as an amendment, never assumed | High |
| 6 | **Quality before monetization** | Checkout is out of the arc; free-tier-shaped caps are in it | High |
| 7 | **No new pillars** | The arc completes and hardens the loop that exists; it does not add a sixth product surface | Must-have |

## Relevant Data

From the [synthesis](../research/2026-09-03/synthesis.md) and the [gap critique](../research/2026-09-03/gap-critique.md), both written from the fifteen reports on disk:

| # | Finding | Source |
|---|---------|--------|
| 1 | Live Ask fails at Anthropic with 400; the UI deletes the conversation. Named a launch blocker by six reports | Walkthrough; rq01 §8 item 4; rq07 Move 1; rq12 Move 4; rq13 Cycle 1; rq05 §10 |
| 2 | Citation marks name a whole chunk. The API already returns the cited sentence and its offsets; the adapter discards them | [rq13](../research/2026-09-03/rq13-ai-integration-patterns.md) Cycle 1 |
| 3 | No competitor ships the full loop (structure-preserving ingest → click-to-passage citations → scoped teaching → FSRS → notes-as-evidence → export). Gemini Notebook's flashcards are session practice, not a scheduler | [rq01](../research/2026-09-03/rq01-competitive-landscape.md); verified in the critique |
| 4 | EPUB figures do not render; the reading column loses its measure against the dock; phones are unusable | [rq06](../research/2026-09-03/rq06-reading-experience.md) P0 1–3 |
| 5 | Teach tells before it elicits; Khanmigo evidence says a separate tutor tab gets skipped, so the tutor must speak first | [rq03](../research/2026-09-03/rq03-ai-tutor-pedagogy.md); [rq02](../research/2026-09-03/rq02-learning-science.md) #2 |
| 6 | Review has no empty-deck honesty, no undo, no formulation gates, and no bounded daily session | [rq04](../research/2026-09-03/rq04-active-recall-quality.md) Moves 1–4; [rq08](../research/2026-09-03/rq08-motivation-retention.md) Cycles 1–2 |
| 7 | First run has no sample book, no ingest-wait story, and no server-side activation events | [rq07](../research/2026-09-03/rq07-onboarding-activation.md); [rq11](../research/2026-09-03/rq11-product-architecture.md) Cycles 1, 3–6 |
| 8 | The rate limiter is broken behind the proxy, there is no per-user AI spend cap, no ToS/privacy/copyright pages, no account deletion, and no `EmailPort` | [rq09](../research/2026-09-03/rq09-public-launch-readiness.md) Cycles A–D |
| 9 | ~$0.020 per cited answer (thinking ≈ 60%), ~$1.16 per typical active learner-month; a thinking diet, a real teach cache, and Haiku selection-Explain take it to ~$0.86 before any model change | [rq15](../research/2026-09-03/rq15-ai-cost-optimization.md); critique C1 |
| 10 | The 1h cache breakpoint sits in front of a prefix usually below Sonnet 5's 1,024-token minimum while ~4k evidence tokens sit after it: "cache exists" is not "savings exist" | critique C4 |
| 11 | Pricing decision (Paddle as merchant of record; Polar cannot pay a Brazilian seller) is recorded and deferred — no checkout in this arc | [rq10](../research/2026-09-03/rq10-pricing-billing.md) |

## Options Considered

### Option 1: Seven bets, trust first, safety gates the doors ⭐ (Recommended)

**Description.** Group the ~100 candidate items into seven bets by the deficit they close, not by the report they came from. Ship Bet 1 first as the gate. Parallelize Bets 2–5 and 7 by surface. Hold open registration until Bet 6 is green. Launch motion after 1 + 5 + 6.

**Pros:**
- Satisfies criteria 1, 2, and 7 by construction: the trust fix is first, safety is a hard gate, and no bet adds a product pillar.
- Each bet has a single owning deficit, so a cycle's scope argument is settled by the bet it belongs to.
- The duplicate-work table in the critique already assigned canonical owners, so the ~100-item union collapses without re-litigating overlaps.

**Cons:**
- Bet 1 delays every visible improvement by one cycle.
- Seven bets is a long arc; the later bets will be re-scoped against evidence they were not written for.

**Estimated cost**: 18–23 cycles total (1: 1–2 · 2: 3 · 3: 2–3 · 4: 3–4 · 5: 3 · 6: 3–4 · 7: 3). Risk: MEDIUM, concentrated in Bet 6 (the only bet whose failure is externally visible).

### Option 2: Safety first — open the doors, then improve in public

**Description.** Ship Bet 6 first, open registration, then work the product bets with real users watching.

**Pros:**
- Real usage data arrives at the start of the arc instead of near the end, so Bets 2–5 are prioritized against strangers rather than against research.
- The riskiest bet lands while the blast radius is one user.

**Cons:**
- Violates criterion 1 outright. Registration would open onto an Ask that deletes the first question — the single worst first impression available.
- Every activation number measured in that window is uninterpretable, because the funnel's own gate is broken.

**Estimated cost**: same total, worse ordering. Risk: HIGH on reputation. **Rejected.**

### Option 3: Cost and models first (Bet 7 leads)

**Description.** Build the spend ledger and the fallback adapter first, on the argument that no arc should be planned on estimated numbers.

**Pros:**
- Turns the arc's softest assumption (#3) into measurement immediately.
- The outage-only fallback would also blunt Anthropic-side failures during the rest of the arc.

**Cons:**
- The ledger measures a loop that currently loses conversations; the first month of data would describe a broken product.
- Bet 7's own gate is the nightly judge thresholds, which is quality infrastructure that exists — this bet is genuinely independent and therefore does not need to be first, only to be before any model change.

**Estimated cost**: same total. Risk: MEDIUM. **Rejected as an ordering**; Bet 7 stays in the parallel band.

### Option 4: Do nothing — keep dogfooding, no launch arc

**Pros:** zero coordination cost; the author keeps shipping what he notices.

**Cons:** the 400 is a defect regardless of whether anyone else ever registers, and it survives only because nobody wrote it down as a blocker. The research ages, the two thaws happen implicitly, and the seven deficits get addressed in whatever order they annoy the author, which is not the order in which they block a stranger.

**Estimated cost**: SMALL upfront, LARGE in wasted research. **Rejected.**

## Options Comparison

| Criterion | Opt 1 (recommended) | Opt 2 | Opt 3 | Opt 4 |
|---|---|---|---|---|
| Trust before reach | ✅ | ❌ | ⚠️ (delayed one bet) | ❌ |
| Safety gates registration | ✅ | ✅ (as the opener) | ✅ | — |
| Evidence-anchored cycles | ✅ | ✅ | ✅ | ❌ |
| Reviewable cycles | ✅ | ✅ | ✅ | ⚠️ |
| Caps thawed on the record | ✅ | ✅ | ✅ | ❌ |
| Quality before monetization | ✅ | ✅ | ✅ | ✅ |
| No new pillars | ✅ | ✅ | ✅ | ✅ |

## Proposed Roadmap

Seven bets, one per cycle group. Ordering: **A first**, then {B, C, D, E, G} in parallel by surface, then **F** before registration opens, then launch motion.

### Cycle A — Trustworthy cited Ask (Bet 1) — *gate for the whole arc*

- A failed generation never deletes the conversation or the user's message. The thread shows the error in place and offers retry; the failed turn persists so a reload still shows the question.
- Both Anthropic request shapes are pinned by offline tests: the answering request sends citations-enabled documents and no `output_config.format`; quiz and judge requests send a JSON schema and no citation documents. A regression that mixes them fails CI without a key.
- Provider 4xx logs the request shape, HTTP status, and `request_id` — never prompt bodies or document data.
- Claim-level citation spans: the adapter maps `cited_text` and its character offsets onto a Learny-owned `CitedSpan`, computed against the exact string sent as that document's `source.data`. Hovering a mark shows the cited sentence; "Show in book" highlights that span.
- The live 400 is reproduced from a real request dump during the cycle, and the fix follows the dump rather than the hypothesis.
- **Explicitly out of this cycle:** model or provider changes, Haiku routing, a sufficient-context autorater, retrieval `top_k` changes, streaming-protocol redesign, the `first_cited_answer` event, and abstention-copy polish. Those belong to Bets 5 and 7 or to rq05's own gated cycle.
- Depends on: nothing. Unblocks: everything.

### Cycle B — A reader people read in (Bet 2)

- Safe figures: extract EPUB images to MinIO, serve them same-origin through an allowlisted prefix, re-encode on ingest. EPUB HTML is never iframed and never given script rights.
- Immersive long-form chrome on `/read` with `[` and `]` toggles; the 65ch measure survives the dock.
- A phone-usable column: bottom-sheet dock, touch capture for highlights.
- Out: native apps, pagination, multi-color highlights, intra-section resume.
- Traces: rq06 P0 1–3 and its cycles; unblocks dual coding (rq02 §8) and any future vision work (rq13).

### Cycle C — Teach becomes a tutor (Bet 3)

- A frozen teach playbook (pump → hint → prompt → assert), one move per turn, session closes after an unaided check.
- The tutor opens the session with section-first retrieval instead of waiting to be asked.
- Ask and Teach merge into one Chat dock (Answer | Tutor), with the empty state naming both modes.
- A passed check offers exactly one FSRS card.
- Out: new tutor models or LearnLM (ADR-0020 holds), knowledge tracing, forbidding direct answers ("just explain" stays one tap).
- Must-be-true: the system prompt stays byte-stable (cache + ADR-0020) and hint-ladder state is application-owned, never model memory.

### Cycle D — Review worth returning to (Bet 4)

- Empty-deck honesty with discard reason codes; deterministic formulation gates (one fact per card, no stopword clozes, no set dumps) plus a prompt rewrite.
- Review undo as a compensating event, interval labels, in-session learning-step requeue, flag/edit on due cards.
- A bounded "today's session" with a Done-for-today state that links back into the current book.
- Out: MCQ, a second scheduler, a per-user FSRS optimizer (volume-gated per ADR-0021), an LLM card-critique pass.
- Must-be-true: content edits never rewrite scheduling or `review_log` rows.

### Cycle E — A first session that converts (Bet 5)

- A shared pre-ingested Standard Ebooks sample (*The Art of War*) as one system source — embeddings paid once, never cloned per user — with a canned cited question and a five-card starter deck.
- Ingest-stage transparency ("use the sample while you wait"); library honesty (one **Open** per book, EPUB/PDF copy, overflow verbs); a naming pass (Library, Tutor, Download notes).
- A landing page with proof above the fold.
- Server-side activation events, `first_cited_answer` among them, fired only on success.
- Out: product tours, guest upload, a catalog, third-party analytics SDKs.
- **Thaw:** RFC-006 capped marketing surfaces. The landing page is an explicit amendment, recorded here.

### Cycle F — Safe to open the doors (Bet 6) — *gate for registration*

- A Redis shared limiter keyed by `user_id` for expensive routes and trusted-proxy IP for auth routes.
- A per-user daily AI-spend cap on a Postgres ledger, with an operator kill switch and honest copy at the stop.
- Source count and byte quotas, plus a per-user in-flight ingestion cap.
- An invite gate (Turnstile and disposable-domain blocking as the opening step), ToS / privacy / copyright pages with a DMCA contact, account deletion that removes MinIO objects and cascades Postgres, and an `EmailPort` (verify + reset) live the day the form opens.
- Out: an EU representative unless the EU is targeted, ZDR as a blocker, publisher hash-scanning, Kubernetes.
- Until this cycle is green the hosted instance stays invite-only, and there is no uncapped public Ask at any point.

### Cycle G — Cheaper intelligence, same trust (Bet 7)

- A cost ledger behind a Learny `SpendPort` persisting tokens (thinking included) and USD.
- `effort=low` on Ask, judge-gated; teach evidence moved before the 1h cache breakpoint with `cache_read_input_tokens` measured, not assumed; Haiku for selection-Explain.
- An OpenAI-compatible fallback adapter aimed at US-hosted open weights, outage-only, behind rq14's promotion gate.
- Out: an embedding-model swap (ADR-0019 stands), semantic answer caching, BYOK, a model-picker UI.
- Must-be-true: every optimization is judge-gated against the nightly thresholds (faithfulness ≥ 0.90, relevancy ≥ 3.1, `citation_valid` 12/12); fallback fires only on transport errors, never on a grounded not-found.
- **Amendment:** ADR-0020 currently names Anthropic as the sole generation provider. The fallback adapter requires an accepted amendment to ADR-0020 before Cycle G's fallback work begins.

### Launch motion

After A + E + F: Show HN with the self-host path and the sample-book path, per rq12's staggered sequence. If Bet 6's caps slip, the public demo degrades to a recorded loop plus `docker compose up` — never to an uncapped public Ask.

## Conflict Resolutions Adopted

The critique left several tensions open; this RFC decides them:

1. **Cost numbers.** rq15's method on live Sonnet 5 pricing is canonical. rq09's figure predates thinking tokens; rq10's TL;DR contradicts its own table. Both are discarded for planning. Every cost claim here becomes a measurement once Cycle G's ledger ships.
2. **Invite-only vs try-without-signup.** Sequence, not either/or: invite-only first, capped guest Ask only after Cycle F.
3. **Teach cache.** A cache breakpoint is not a saving. Cycle G moves the stable section documents in front of it and measures.
4. **Haiku.** Already shipped on quiz. The cheap-Claude slot goes to selection-Explain, with a judge-gated Haiku Ask A/B as a later experiment.
5. **Chat merge vs tutor visibility.** Both: one Chat dock, and the tutor opens the session. Discoverability comes from behavior, not from a tab.
6. **Home weighting.** The first session is Ask-first; the returning Home leads with due cards when due > 0 and links back into the book when the session closes.
7. **Retrieval budget.** Raising `top_k` is a quality cycle owned by rq05 behind its own ruler, allowed only with the ledger showing the delta. Cutting `k` for cost is forbidden without a reranker.

## Exclusions (bind for the life of this RFC)

- No checkout, no subscription plans, no billing integration. Caps yes, payment later.
- No new provider SDK on the request path (ADR-0007/0009); LiteLLM and OpenRouter stay off it.
- No vector database, no LangChain, no LlamaIndex.
- No gamification: streaks, XP, badges, leaderboards, and freeze shops stay out.
- No public surface carrying book bytes or book-derived cards.
- No per-user clones of the sample corpus embeddings.
- No CN first-party inference over user books; a US-hosted fallback only, and only behind the rq14 gate.
- No sixth product pillar. The arc completes the five that exist.

## Thawed Caps

Two exclusions from earlier RFCs are deliberately and narrowly reversed here, on the record:

| Cap | Set by | Thaw |
|---|---|---|
| No notifications of any kind | RFC-004 | An **opt-in** due digest only, inside Cycle D. No streak nagging, no default-on email. |
| No marketing landing page | RFC-006 | A proof-above-fold landing page inside Cycle E, required by the launch motion. |

## Watch Items

- **Gemini Notebook shipping a real scheduler** would weaken the FSRS wedge (not the portability/self-host one). Refresh rq01 §7 if it happens.
- **Anthropic repricing or a Sonnet 6** reruns rq15's arithmetic and the judge baselines.
- **Fireworks US premium pricing** must be re-fetched before Cycle G quotes dollars.
- **Polar adding Brazil payouts** would reopen the billing choice.
- **The ~7-day Anthropic commercial log TTL is unverified**; confirm before the privacy policy states a number.
- **D7 data vs the provisional aha.** If `first_review` predicts retention better than `first_cited_answer`, re-weight Cycle E's funnel.

## Action Items

| Action | Owner | Status |
|--------|-------|--------|
| Accept or amend this RFC | Augusto | NOT STARTED |
| Run Cycle A (`trustworthy-cited-ask`) | Augusto | IN PROGRESS — this PR |
| Capture and record the live Anthropic 400 dump (status, `request_id` class, shape sent) | Augusto | IN PROGRESS — Cycle A |
| Draft the ADR-0020 amendment before Cycle G's fallback work | Augusto | NOT STARTED |
| Decide the RFC-005 Cycle F resumption point relative to this arc | Augusto | NOT STARTED |
| Cycles B–G in the stated order | Augusto | NOT STARTED |

## Open Questions

1. **Does Bet 4 need four cycles or three?** Its item list is the longest in the arc and the undo work is the only piece with an invariant risk. Decide at spec time for that bet, not now.
2. **Where does the sample corpus live operationally?** A system-owned user, a nullable owner, or a dedicated ACL flag — a Cycle E design decision with a small schema consequence.
3. **Does the invite gate need Turnstile on day one,** or does an invite code alone carry it until registration is genuinely open? Cycle F spec decision.

## Outcome

**Decision**: _pending — drafted 2026-09-03 from the same-day research folder; Cycle A started under it. Formal acceptance to follow review._

**Decision Date**: —

**Decided By**: —

**Rationale**: —
