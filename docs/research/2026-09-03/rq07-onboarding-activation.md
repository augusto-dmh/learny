# RQ07 — Onboarding & activation

*How a stranger reaches a first cited answer (or first review) as fast as possible. 2026-09-03.*

## TL;DR

Learny’s first-run today is **register → empty Home → empty Bookshelf → upload → wait → hope Ask works**. The aha is gated behind owning an EPUB *and* a multi-minute ingest. That is the opposite of product-led activation.

**Aha moment (provisional, to be validated against D7 retention):** a streamed answer that cites a real passage, which the user can click into the book. Secondary aha: completing one FSRS review whose card cites a passage. Do **not** treat “account created” or “book uploaded” as activation.

**Fastest path to wow:** skip the empty library. Ship a **shared, pre-ingested sample book** (Standard Ebooks *The Art of War*, ~24k words) with a canned first question and a pre-built 5-card starter deck. Optional **capped guest Ask** on that sample (generation cost only; embeddings paid once). Register to persist and to upload *your* book. **Do not** add an email-verification wall before the aha. **Do not** ship a product tour.

While the user’s own book ingests, they should keep using the sample. Surface the pipeline Learny already logs (`queued → started → corpus_normalized → corpus_built → embeddings_built → succeeded`) instead of a mute `processing` chip.

**Do not ship activation UX until the real-provider Ask path is reliable.** The 2026-09-03 walkthrough saw Anthropic 400 + deleted conversation on a tiny fixture. A faster funnel into a red error is worse than today’s empty Home.

---

## Evidence

### Current first-run (this repo, 2026-09-03)

From [project-brief.md](project-brief.md) and the live UI:

- Landing (`frontend/app/page.tsx`): title + tagline + Create account / Log in. No demo, screenshots, or sample.
- Register: email + password, **no verification**, redirect to `/home`.
- Home empty: “You have no book in progress yet” → Pick a book.
- Bookshelf empty: upload form + “No sources yet.” File picker still says “EPUB file” though PDF is supported.
- Ingest wait: status chip `processing`, 3s poll. `ingestion_events` already record stages (`corpus_normalized`, `corpus_built`, `embeddings_built`) but the library UI does not show them; only the latest **failure** message is fetched.
- Ask empty state: three generic prompts (“Summarize the key ideas…”). Review empty: “Nothing due right now.”
- Observed failure: OpenAI embed 200 → Anthropic `POST /v1/messages` 400 → “Answer generation failed” and the conversation deleted.

That is a **cold-start tax** on every stranger: they must already have a DRM-free book *and* wait minutes before the product can prove itself.

### Activation, TTV, aha (PLG)

Activation is the first experience of **core value**, and it is the highest-leverage PLG metric; retention, expansion, and virality sit downstream ([Mixpanel, 2026](https://mixpanel.com/blog/product-led-growth/)). Mixpanel’s 2026 State of Digital Analytics (12,000+ companies) treats product as the primary growth channel; 58% of companies run some PLG motion.

How to *define* the aha (do not guess):

1. Cohort retained vs churned users.
2. Find the **first week-1 action** that most strongly predicts return ([Amplitude — new user activation](https://amplitude.com/blog/understand-new-user-activation); [Amplitude — aha moment](https://amplitude.com/blog/aha-moment)).
3. Instrument that as **one** server-side event, fired once, stamped with time-since-signup. Do not reconstruct activation from five events at report time ([Aha-Moment Playbook](https://vmobify.com/blog/app-activation-aha-moment)).
4. Report **activation rate per acquisition cohort** *and* the **TTV distribution** (share in first session / first day / first week). Mean TTV is skewed by a long tail.

Classic calibrated examples (habit thresholds, not first-session ahas): Facebook “7 friends in 10 days”; Slack ~2,000 team messages. Learny’s *first-session* aha should be closer to Shazam naming a song: one complete cited Q&A, not “used the product 2,000 times.”

TTV under ~5 minutes is repeatedly cited as a 3× activation lift vs TTV >15 minutes in practitioner write-ups ([SaaS Factor](https://www.saasfactor.co/blogs/what-steps-should-your-signup-and-onboarding-include-to-reduce-drop-off)); treat the 3× as directional, not a Learny measurement. Mixpanel also documents a photo-editing product that **removed an email-activation step causing 27% of signups to never enter the product**, after which upgrades rose.

### Tours vs product-led empty states

[NN/G — Onboarding Tutorials vs. Contextual Help](https://www.nngroup.com/articles/onboarding-tutorials/) (Laubheimer, 2023): launch-time walkthroughs are **push revelations**. Users skip them (paradox of the active user), forget them (out of context), and they interrupt the task. Prefer **pull revelations** (help at the moment of use). Tours are appropriate mainly for novel interaction paradigms (e.g. AR), which Learny is not.

Empty-library pattern: seed 1–2 example records so the UI is alive ([AuditBuffet AB-002340](https://auditbuffet.com/patterns/ab-002340); [LogRocket empty states](https://blog.logrocket.com/ux-design/empty-states-ux-examples/); Pinterest interest-seeding). Benefit-led copy + **one** primary CTA, not “No sources yet.”

### NotebookLM (now Gemini Notebook) first-run

Official product: [notebooklm.google](https://notebooklm.google/) (rebrand July 2026; same product). Flow:

1. **Zero new identity** if you already have a Google account.
2. Marketing landing shows the wow (citations, Audio Overview) *before* a blank workspace.
3. **Featured public notebooks**: “If you don’t know where to start, try out one of these public notebooks. Ask questions, generate summaries…”
4. New notebook immediately prompts **Add sources**. Empty notebook cannot answer. **Discover sources** (web / Drive) removes “I didn’t bring a file.”
5. After sources land: suggested questions + Studio (Audio Overview is their viral wow). Answers are source-grounded with quote citations.

Learny analog: featured sample *book*, not featured *notebook*; Discover-sources analog is a public-domain catalog, not web search (copyright). Learny’s differentiator vs NotebookLM is **one book, structure-preserving, lasting recall** — the first session should prove citations *and* hint at review, not mimic Audio Overview.

Independent walkthroughs confirm first-use is an empty dashboard until “Create” + sources ([tech-insider 2026 guide](https://tech-insider.org/au/how-to-use-notebooklm-2026/); [Discover sources help](https://support.google.com/gemininotebook/answer/16215270)).

### Readwise / Reader first-run

- Signup: email or Amazon, **30-day trial, no credit card** ([readwise.io/read](https://readwise.io/read)).
- Library is **never empty**: a default document **“Getting Started with Reader”** is inserted on activation ([Reader FAQs](https://docs.readwise.io/reader/docs/faqs)). Instruction lives *inside* a real document, not a modal tour.
- Per-type sidebars (“if you read PDFs, click PDF…”) are pull revelations.
- Aha for Readwise-the-product is closer to **first highlight that shows up in daily review**; Reader’s aha is **first saved article that looks better than the web**.
- Readwise themselves recommend **Standard Ebooks** for public-domain EPUBs ([Adding Content](https://docs.readwise.io/reader/docs/faqs/adding-new-content)).

### Ingestion-wait UX

Learny ingest for a real book is **minutes** (parse → normalize → corpus → chunk → embed). Nielsen/Tiger guidance:

- **>10s** needs percent-done or a **step list**, not a spinner ([NN/G — long waits](https://www.nngroup.com/articles/designing-for-waits-and-interruptions/); [UX Tigers / Nielsen on progress](https://www.uxtigers.com/post/progress-indicators)).
- Count in **user units** (“embedded 412 / ~800 chunks”) not a lying bar. Never stall, reset, or lie.
- **Do not trap** the user on a wait screen. Run the job in the background; let them do something else.
- Warn *before* they commit: “A 300-page EPUB usually takes a few minutes.”
- Optimistic UI: Instagram started the upload during captioning (Krieger). Learny analog: let **Read** unlock at `corpus_built` (structure is there) while embeddings finish; Ask waits for `embeddings_built` (lexical-only Ask is a later experiment).

Learny already appends `corpus_normalized`, `corpus_built` (`sections=… blocks=… chunks=…`), `embeddings_built` between `started` and `succeeded` (`backend/tests/test_worker_tasks.py`). The data for a step UI exists; the library card does not render it.

### Guest / trial before signup, given per-user AI cost

OpenAI opened ChatGPT **without signup** in April 2024 to broaden reach; guests get limited history, extra content filters, and a prompt to sign in for persistence (summarized in [Grokipedia: Guest vs signup in AI products](https://grokipedia.com/page/Guest_Access_vs_Immediate_Signup_in_AI_Products)).

The cost side is not optional for Learny (OpenAI `text-embedding-3-large@1536` + Anthropic Claude, ADR-0019/0020):

- Stripe: on AI products a “free” account burns **real tokens**; 200 farmed accounts × 10k tokens is 2M tokens of spend ([Stripe — free-trial abuse](https://stripe.com/in/resources/more/how-to-prevent-free-trial-abuse-in-saas-and-ai-products), May 2026).
- Farmed accounts evade per-user rate limits; identity scoring belongs **at signup**, before credits ([Shield Labs](https://shieldlabs.ai/blog/how-to-prevent-free-trial-abuse-ai)).
- Roll out controls gradually: monitor → bot/disposable-email → fingerprint → verify/card. Measure **cost-per-trial-account** alongside conversion.

**Implication:** guest **Ask on a shared pre-embedded sample** is cheap (generation only, hard cap). Guest **upload** is expensive (embed a whole book) and is a copyright/abuse hole. Require an account to upload.

### Email verification friction

- 15–30% of users never click the verify link if it walls the product ([Mantlr](https://mantlr.com/blog/onboarding-40-percent-step-3)).
- Mixpanel’s 27% “never entered the product” story was an email-activation step.
- Practitioner consensus: let people in, verify **asynchronously**, hard-gate only risky actions (export, billing, API) ([Medium — verify later](https://medium.com/@garoono/kill-the-inbox-detour-let-users-in-verify-later-c323714d36be); [SaaS Factor](https://www.saasfactor.co/blogs/what-steps-should-your-signup-and-onboarding-include-to-reduce-drop-off)).
- Learny today has **no** verification. Do not add a wall for public launch. Pair with RQ09 (abuse, disposable email, DMCA). Soft banner after first wow; hard-gate vault export + billing.

---

## Proposed first-session flow

**North star:** a stranger who did not bring a file still sees a cited answer in the first session, in well under five minutes of *their* time (ingest of *their* book may still take minutes in the background).

0. **Landing (anonymous).** One sentence of value, one still/GIF of a citation jump, two CTAs: **Try a sample** (primary) and Create account. No carousel tour.
1. **Try a sample.** Opens the reader on a **system-owned, already-ready** copy of *The Art of War* (shared corpus; not cloned per visitor). Dock Ask is open. One book-specific suggested question is highlighted, e.g. *What does Sun Tzu mean by “all warfare is based on deception”?* Generic “summarize this book” is demoted — it is a weak wow.
2. **First cited answer (aha).** Streamed answer, ≥1 citation. Clicking a citation scrolls to the passage (this is the “see the source” beat NotebookLM advertises). Fire `first_cited_answer` **server-side** when the turn succeeds with citations. Guest cap: 3 questions / 24h / IP+device; then “Create a free account to keep going.”
3. **Soft register.** Email + password (or later magic link). Session cookie immediately; **no inbox detour**. Attach the guest conversation to the new user if one exists. Home is **not empty**: sample is already on the shelf; Continue reading points at it.
4. **Second beat, same session (optional but scripted).** “Try a 60-second review” → 5 **pre-generated** cards from the sample, due now. Completing one card fires `first_review`. This is the recall differentiator vs NotebookLM; do not block aha on it.
5. **Upload your book (parallel, never blocking).** Honest copy: “Usually a few minutes.” Start ingest; do **not** trap on a spinner. Keep using the sample. Library card shows the real stage list + chunk counts. When `corpus_built`, enable Read. When `embeddings_built` / `succeeded`, toast “Your book is ready — ask it something” + book-specific suggested prompts from the TOC.
6. **Verify later.** Slim banner after step 2, not before. Resend in-product. Hard-gate `GET /api/export/vault` and any future billing until verified (RQ09).

**Anti-goals:** Appcues-style 6-step tour; cloning Origin of Species embeddings per signup; requiring an EPUB before wow; quiz-deck generation that “succeeds” in 0.02s with zero cards (current fixture failure) as the first review.

---

## Sample-content shortlist (licensing)

**Source of files: Standard Ebooks, not raw Project Gutenberg.**

| Title | Why it demos Learny | Length (SE) | URL |
|---|---|---|---|
| **Sun Tzu, *The Art of War*** (Giles) | **Default first book.** 13 named chapters, universally known, short ingest if ever cloned, perfect “explain this maxim + jump to passage.” | 24,005 words | [SE](https://standardebooks.org/ebooks/sun-tzu/the-art-of-war/lionel-giles) |
| **Marx & Engels, *The Communist Manifesto*** (Moore) | Shortest argumentative treatise (4 chapters). Strong citation demo; politically charged — catalog item, not the anonymous default. | 13,179 words | [SE](https://standardebooks.org/ebooks/karl-marx_friedrich-engels/the-communist-manifesto/samuel-moore) |
| **Machiavelli, *The Prince*** (Marriott) | Short treatise, named sections, “is he advising cruelty?” questions. | 34,990 words | [SE](https://standardebooks.org/ebooks/niccolo-machiavelli/the-prince/w-k-marriott) |
| **Douglass, *Narrative of the Life of Frederick Douglass*** | Chaptered memoir + argument; learning/history audience; readable. | 40,415 words | [SE](https://standardebooks.org/ebooks/frederick-douglass/narrative-of-the-life-of-frederick-douglass) |
| **Russell, *The Problems of Philosophy*** (1912) | **Learning-audience flagship.** Intro textbook, chaptered arguments, “what is the problem of induction?” | 42,740 words | [SE](https://standardebooks.org/ebooks/bertrand-russell/the-problems-of-philosophy) |
| **Marcus Aurelius, *Meditations*** (Long) | Aphoristic → excellent FSRS cards; weaker linear argument than Russell. | 45,608 words | [SE](https://standardebooks.org/ebooks/marcus-aurelius/meditations/george-long) |
| **Mill, *On Liberty*** | Canonical argument, chaptered; slightly longer. | 50,855 words | [SE](https://standardebooks.org/ebooks/john-stuart-mill/on-liberty) |
| **Darwin, *On the Origin of Species*** (6th ed.) | Impressive TOC/structure; **too long (~200k words) for per-user ingest.** Shared-catalog only, never the first-session default. | 199,940 words | [SE](https://standardebooks.org/ebooks/charles-darwin/the-origin-of-species) |

Launch with **one** pre-ingested default (*Art of War*) plus **two** catalog picks (Russell for Ask, Meditations for Review). More titles are cheap if they stay **shared**.

### Licensing evidence

**Standard Ebooks** ([About](https://standardebooks.org/about); [Uncopyright example](https://standardebooks.org/ebooks/mark-twain/the-adventures-of-huckleberry-finn/text/uncopyright)):

- Underlying text/artwork believed **U.S. public domain**.
- SE volunteers dedicate *their* work (markup, typography, covers, metadata) under **CC0 1.0**, so the **entire ebook file** is released to the public domain for U.S. purposes.
- **Non-U.S. users must check local law** — SE makes no representation outside the United States. Learny’s public instance should geo-notice this on the sample catalog (RQ09).
- Collections policy: U.S. PD via expiration, generally published before 1931 ([policy](https://standardebooks.org/contribute/collections-policy)).

**Why not Gutenberg files as the bytes we ingest:** PG texts are two parts — unrestricted book text + **PG trademark/license**. Redistributing *with* the PG name has extra rules (verbatim, royalties if you charge). Strip the trademark and the U.S. text is unrestricted ([PG License](https://www.gutenberg.org/policy/license.html)). EPUB *quality* is the practical issue: SE documents missing curly quotes, auto-generated EPUBs, uneven TOC/footnotes vs their style guide ([What makes SE different](https://standardebooks.org/about/what-makes-standard-ebooks-different)). Learny’s citations and reader depend on clean structure — use SE compatible EPUBs.

**Do not** preload Carnegie, modern textbooks, or anything still in copyright. Sample content is a **licensing surface**, not a growth hack.

### Architecture (so this is cheap)

Do **not** clone embeddings per new user. Own samples as **system sources** (shared `corpus_*` / chunks / embeddings; ACL: world-readable Ask/Read/Teach; no delete/re-ingest by users). Conversations and highlights stay user-scoped. Embeddings paid **once**. Generation billed per Ask (guest cap + auth rate limit). Pre-build the starter quiz deck once; attaching due cards to a new user is a cheap FSRS-state insert, not a Claude job.

---

## Activation funnel + metrics

Provisional aha = **first cited answer**. Validate in week 4 of public beta by segmenting D7 return on `first_cited_answer` vs `first_review` vs `book_available`; keep the event that actually predicts return.

| Step | Event (server-side unless noted) | Success definition | Notes |
|---|---|---|---|
| 0. Visit | `landing_viewed` (page) | Unique visitor | UTM/source on the event. |
| 1. Sample opened | `sample_opened` | Reader+Ask on system source | Guest or authed. |
| 2. Register | `signup_completed` | `POST /api/auth/register` 201 | Also `signup_started` on form focus if you need drop-off. |
| 3. Book available | `book_available` | Own or sample source `ready` | Sample users skip the wait; still fire so the funnel is comparable. |
| 4. **Activated (aha)** | `first_cited_answer` **once** | Successful answer turn with `citations.length ≥ 1` | Stamp `ttv_seconds` from `signup_completed` (or from `landing_viewed` for guests). Failed Ask must **not** fire; keep the conversation (fix the 400-delete bug). |
| 5. First review | `first_review` | First rated FSRS item | Secondary; report separately. Empty “succeeded” decks with 0 items must not count. |

**Headline KPIs**

- **Activation rate** = `first_cited_answer` / `signup_completed` (and a parallel guest funnel: aha / `sample_opened`).
- **TTV p50 / p90** for activated users (distribution, not mean).
- **Step conversion** 0→1→2→3→4→5; the largest drop-off is the next cycle.
- **Guardrails:** cost per activated user (embed+generate), Anthropic 4xx/5xx rate on first Ask, % of first Asks with zero citations, ingest p50 for *user* books, % of signups that never leave Home.

**Instrumentation notes**

- Fire activation **in FastAPI** when the answer is persisted with citations — not in the React client (adblock, abandoned tabs).
- Learny today has request-timing rings (`app/core/instrumentation.py`), not product events. Smallest cycle: append-only `product_events` table (`user_id` nullable for guests, `name`, `properties` jsonb, `created_at`) + a `/internal` or PostHog dual-write later. Do not block public launch on Amplitude.
- Session replay (optional, post-launch) on the Ask dock only; books are user content — be privacy-conservative (RQ09).

**Target (directional, not a contract):** ≥40% of signups reach `first_cited_answer` in the first session once sample+Ask are reliable; p50 TTV < 3 minutes for the sample path. Today’s path cannot hit this: empty library + ingest + fragile Ask.

---

## Cycle-sized moves

Each item is one spec-driven cycle. Ordered for a public-launch arc.

### 1. Make first Ask trustworthy (blocker, not optional)

**Why recommend:** The walkthrough’s Anthropic 400 + deleted thread means the aha *cannot fire*. Activation UX that dumps people into that error will *lower* retention. Citations are a core requirement (ADR-0003).

**Why not:** If RQ05/RQ03 already own the 400, don’t duplicate; still treat “first Ask success rate” as an activation gate, not a nice-to-have.

### 2. Shared sample book + first-run empty states (highest activation leverage)

**Why recommend:** Removes the empty-library cold start (Readwise starter doc; NotebookLM featured notebooks; AuditBuffet seed pattern). Shared corpus = embeddings paid once. Home/Bookshelf become “open *The Art of War*” instead of “No sources yet.” Book-specific suggested prompt beats the three generic ones.

**Why not:** Extra ACL (“system source, world-readable”) and a geo/copyright notice. A *cloned* per-user sample would multiply embed cost — do not do that. One title is enough; a 20-book catalog is a later cycle.

### 3. Capped guest Ask on the sample (optional, after 2)

**Why recommend:** Cuts the signup wall that currently sits *before* any value (Baymard-style friction; ChatGPT guest). Cost is generation-only and cap-able (3 Qs). Converts on demonstrated wow (“save this answer”).

**Why not:** Abuse and prompt-injection on a public Ask endpoint; guest session design vs current cookie-auth (ADR-0015); RQ09 must land rate limits first. Skip guest and still win most of the value by putting the sample *after* the existing (already-short) register.

### 4. Ingest-wait transparency + “use the sample while you wait”

**Why recommend:** Real books take minutes. NN/G: >10s needs steps; don’t trap. Events already exist. Unlock Read at `corpus_built`. Toast when ready.

**Why not:** Finer ETA (“3 min left”) will lie on first PDF/Docling jobs — prefer steps + counts, not a fake bar. Don’t spend a cycle on wait UX before the sample exists; the sample makes wait *optional* for aha.

### 5. Pre-built 5-card starter deck on the sample

**Why recommend:** Today’s first review is “Nothing due” until a slow/fragile deck job. A pre-built deck makes the *second* wow (recall) available in the same session — Learny’s wedge vs NotebookLM.

**Why not:** FSRS state is per-user; attaching cards without disturbing the shared item text needs a careful insert (ADR-0021). Don’t generate decks at signup (Claude cost × N). Don’t lead the session with Review; Ask-with-citation is the aha.

### 6. Deferred email verification (soft banner, hard-gate export)

**Why recommend:** Verification walls drop 15–30% before value; Mixpanel 27% never-enter story. Learny currently has no verify — adding a wall would be a regression. Needed eventually for recovery mail and abuse (RQ09).

**Why not:** Unverified accounts + disposable mail farm guest-or-free Ask. Don’t build a full verify product before sample+Ask work. Don’t collect a card “just to verify” at launch (pricing is secondary).

### 7. Landing proof (one citation still + 90s path)

**Why recommend:** Current landing cannot create intent. NotebookLM sells “see the source” on the marketing page. The repo already has a demo slot (`docs/media/`).

**Why not:** Growth/positioning (RQ12) owns full marketing. One still + working Try CTA is enough; a brand site is not an activation cycle.

### Explicitly out of scope for activation cycles

- Interactive product tours / coach-mark sequences (NN/G).
- Per-user clone of long PD books (*Origin of Species*).
- Guest **upload**.
- Forcing quiz generation as the first action.
- Amplitude/Mixpanel as a launch dependency (Postgres events first).
