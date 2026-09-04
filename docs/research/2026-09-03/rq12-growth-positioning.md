# RQ12 — Growth & positioning

*How Learny becomes attractive and discoverable to the public. Evidence gathered 2026-09-03. Does not modify product code; recommendations are cycle-sized, not a GTM rewrite.*

## TL;DR

The stranger's question is not "why Learny vs RemNote?" It is **"why not upload my book to ChatGPT / Gemini Notebook?"** That is the obvious alternative (April Dunford: start from what buyers actually do if you do not exist). Google rebranded NotebookLM to Gemini Notebook on 16 Jul 2026, claims 30M+ users and 600k+ orgs, and now ships source-grounded flashcards/quizzes plus Audio/Video Overviews. Source-grounded Q&A is table stakes. Learny wins only where the incumbents structurally will not: **a durable FSRS memory, your notes cited distinctly from the book, and data you can take with you (Anki `.apkg`, Obsidian vault, Apache-2.0 self-host).**

**Beachhead:** technical autodidacts and PKM/Anki power users who already read books — not med students, not bar/CPA, not language learners, not book clubs. Those niches are larger, but they already have locked-in tools (AnKing/AnkiHub, Barbri, Duolingo) and a different job-to-be-done.

**First growth motion:** a landing page that *shows* a cited answer on a public-domain book (no signup), then a Show HN + r/selfhosted launch that treats the GitHub README as the real landing page. Public shared decks of book content are a copyright trap, not a growth loop. Share *user-authored* notes and cards later; never share the book.

Today's public surface is a title, a tagline, and two links (`frontend/app/page.tsx`, RFC-004 Cycle E HOME-20). That is not a product story.

---

## 1. Positioning statement options

### The competitive set that actually matters

| If Learny did not exist, they would… | What that alternative is good at | What it structurally will not do |
|---|---|---|
| Paste chapters into ChatGPT / Claude Study Mode | Flexible tutoring, analogies, open-ended quiz | Passage-faithful citations; a memory that survives the chat; notes as first-class evidence; export |
| Upload the PDF to [Gemini Notebook](https://notebooklm.google/) (ex-NotebookLM) | Source-grounded answers, press-grade citations, Audio Overview, Studio flashcards | FSRS schedule; Anki/Obsidian export; self-host; your notes cited *as notes*; leaving Google |
| Highlight in [Readwise Reader](https://readwise.io/read) + Daily Review | Capture + resurfacing highlights | Active recall (they resurface, they don't test); cited Q&A; teaching |
| Notes→cards in [RemNote](https://www.remnote.com/) or Anki | Serious SR; exam-day decks | Book-structure corpus; cited answers that resolve to anchors |
| Save everything in [Recall](https://www.recall.it/) | One-click web/video PKM + quizzes | Book-first reader; structure-preserving ingestion; OSS |

Gemini Notebook's own FAQ now owns "see the source, not just the answer." ChatGPT/Claude own "interactive tutor." Readwise owns "don't lose your highlights." RemNote owns "notes that become cards." **Learny's unique intersection is the loop: read a structured book → ask with clickable citations → capture a note that is retrieved as evidence → promote to FSRS → export.** No incumbent sells that loop as one product, and Google cannot sell "export and self-host" without undermining Gemini.

How challengers beat a free incumbent (same pattern, different categories):

- **Plausible vs Google Analytics** — name the incumbent in the H1 ("Easy to use and privacy-friendly Google Analytics alternative"), show a live demo, open-source the code, charge for hosted convenience. [plausible.io](https://plausible.io/)
- **Cal.com vs Calendly** — self-host is the trust asset that *justifies* the paid cloud, not a charity track. [Cal.com funnel teardown](https://unlocksaas.com/funnel-teardown/cal-com)
- **Linear vs Jira** — opinionated craft for a segment the incumbent cannot serve without breaking its core (configurability). [Linear case](https://tools.davidshadrake.com/case-studies/growth-hacking/linear)
- **Cursor vs Copilot** — purpose-built environment vs a plugin on the thing you already have; they never claimed "we are a better autocomplete." [Cursor vs Copilot](https://zapier.com/blog/cursor-vs-copilot/)

Learny should copy the *shape*: name the obvious alternative, own one trade-off, do not try to be Gemini-with-podcasts.

### Statement options (pick one for launch; keep the others as audience variants)

**A — Recommended (product truth, works on HN and the landing page)**

> For people who read books to keep them, Learny is book intelligence with citations you can trust and a memory that lasts. Unlike ChatGPT or Gemini Notebook, every answer resolves to a passage in *your* book, your notes stay in the loop as cited evidence, and review is scheduled by FSRS — then you can leave with an Anki deck, an Obsidian vault, or a self-hosted instance.

**Why A:** Matches the README thesis, names the real alternative, and lists capabilities incumbents cannot copy. **Why not as the only line:** too long for a hero; use the first sentence as H1, the rest as subhead.

**B — PKM-native (r/ObsidianMD, r/Anki, Linking Your Thinking)**

> Learny is the book layer for your second brain: structure-preserving ingestion, notes that retrieve next to the source, FSRS cards, one-click Obsidian/Anki export.

**Why B:** Speaks the beachhead's language. **Why not as the public H1:** "second brain" is insider jargon; it loses the ChatGPT-default visitor.

**C — Confrontational (good comment, bad headline)**

> Don't upload your book to ChatGPT. ChatGPT will sound sure. Learny will show you the page.

**Why C:** Memorable; matches 2026 student writing that NotebookLM wins on *verifiability* ([AI Native Student](https://ainativestudent.com/blog/notebooklm-vs-chatgpt-studying/), [Coursiv](https://coursiv.io/blog/notebooklm-vs-chatgpt)). **Why not as H1:** punches ChatGPT, ignores Gemini Notebook (now the closer competitor), and sounds like a rant on Product Hunt.

**D — Rejected: "open-source NotebookLM"**

Names Google's category and invites a feature bake-off Learny will lose (Audio Overview, Video Overview, 30M users, Play Books). Open source is a *channel and trust proof*, not the category.

### What *not* to claim

- "Better AI" / "smarter tutor than Claude." Generation is Claude behind a port (ADR-0020); the product is the loop, not the model.
- "We have flashcards too." Gemini Notebook already does. The wedge is **FSRS + Anki export + cards that survive re-ingest**, not "a quiz in the Studio panel."
- Category creation ("book intelligence" as a new market). Dunford: start in a category buyers already understand ([Obviously Awesome method](https://aprildunford.substack.com/p/a-quickstart-guide-to-positioning)). Category: **AI study workspace for books**, differentiated on trust + memory + portability.

---

## 2. Landing-page blueprint

**Current state:** centered title "Learny", tagline "Turn your books into cited answers and lasting recall.", Create account / Log in. No screenshot, no demo, no "unlike", no proof. Comment in `frontend/app/page.tsx` says this is intentional (HOME-20, "no marketing sections"). For a public launch it is insufficient: 2025–26 AI landing practice is **proof above the fold**, because visitors do not believe AI claims ([Behind the Launch](https://behindthelaunchh.substack.com/p/nobody-trusts-your-ai-product-yet); [TheKitBase anatomy](https://thekitbase.app/blog/anatomy-ai-saas-landing-page)).

### What adjacent pages actually do

| Product | Hero move | Proof | CTA |
|---|---|---|---|
| [Readwise](https://readwise.io/) / [Reader](https://readwise.io/read) | Pain question ("finish a book, forget it two weeks later") + named audience ("power readers") | Named founders (Rahul Vohra, Packy McCormick); "bootstrapped since 2017"; full export | 30-day trial; student discount |
| [RemNote](https://www.remnote.com/) | Outcome ("study faster… higher grades") + PDF drop zone | "1,000,000+ students"; named med/CS students | Start learning in seconds (upload) |
| [Recall](https://www.recall.it/) | Live-looking chat over *your* sources with citations | "700,000+ professionals"; 4.7/5; privacy + Markdown export | Install extension / join |
| [Gemini Notebook](https://notebooklm.google/) | "Understand Anything" + press quotes (WSJ, Karpathy) | 30M users (blog); "we don't train on your data" | Try / Get the app |
| [Plausible](https://plausible.io/) | Names Google in the H1; live stats | 20k paying; DHH / Hugging Face quotes; OSS | Trial + self-host |

Pattern: **show the product working, name who it is for, put one trust strip under the hero, one primary CTA.** RemNote and Recall lead with an interactive artifact (PDF drop, chat). Readwise leads with a scientifically named habit (Daily Review). Learny should lead with **a cited answer you can click into a passage**.

### Proposed above-the-fold (one cycle)

1. **H1 (statement A, first sentence):** "Book intelligence with citations you can trust — and a memory that lasts."
2. **Subhead:** "Upload an EPUB or PDF. Ask. Click the passage. Review with FSRS. Export to Anki or Obsidian. Or run it yourself."
3. **Primary CTA:** "Try it on *On Liberty*" (or another public-domain book — **no account**). Secondary: "Self-host with Docker" → GitHub README. Tertiary: Create account.
4. **Hero visual:** silent 8–12s loop (or the already-scripted ≤90s money-path in `docs/media/README.md`) of: question → streaming answer → citation chip → reader jumps to the anchor. Poster = `screenshot-ask.png`. Do **not** use generative "AI hero video" that warps UI text; record the real UI ([Seedance guidance](https://www.seedance.tv/blog/seedance-website-hero-videos-2026) itself says use a real capture when the UI *is* the proof).
5. **Trust strip (no fake logos):** Apache-2.0 · Docker Compose · FSRS · Anki `.apkg` · Obsidian vault · "deterministic adapters, no keys required to try locally." Integration marks beat empty "trusted by" when you have no customers ([TheKitBase](https://thekitbase.app/blog/anatomy-ai-saas-landing-page)).

### Below the fold (scroll, not a novel)

- **Three-beat loop, not a feature grid:** Cite → Remember → Leave. One screenshot each (ask with citation, review queue, vault/Anki export).
- **Skepticism section** (required for AI): "Why this is not a ChatGPT wrapper" — canonical corpus, citations as a retrieval output (ADR-0003), FSRS state that survives re-ingest, notes on a parallel index, export is one-way by design (ADR-0026).
- **Unlike table** (three columns: ChatGPT, Gemini Notebook, Learny). Honest: they have Audio Overviews and 30M users; we have FSRS, export, self-host.
- **Social proof v0:** GitHub stars, "runs with `docker compose up`", one technical walkthrough. Named user quotes come after launch, not invented.
- **FAQ:** copyright (you upload books you have the right to); what is exported; what is *not* shared; BYOK later.
- One primary CTA repeated after the unlike table and the FAQ.

Do not: dark-mode-only "AI SaaS" chrome that fights Iron Gall (ADR-027); a pricing wall before a working demo; "Watch Demo" as the *only* CTA (HN will bounce).

---

## 3. Beachhead audience (one, with evidence)

### Candidates scored

| Niche | Community size (approx., late Aug / early Sep 2026) | Pain | Willingness to adopt a *new* book-AI app | Fit to shipped Learny | Verdict |
|---|---|---|---|---|---|
| **PKM / Anki autodidacts (technical + serious nonfiction readers)** | [r/ObsidianMD 359k](https://gummysearch.com/r/ObsidianMD/); [r/Anki 205k](https://gummysearch.com/r/Anki/) (+20.6% YoY); [r/PKMS 78k](https://gummysearch.com/r/PKMS/); [r/Zettelkasten 40k](https://gummysearch.com/r/Zettelkasten/); [r/selfhosted ~725k–830k](https://gummysearch.com/r/selfhosted/); LYT YouTube ~360k, newsletter 45k ([thoughtleaders.io](https://app.thoughtleaders.io/youtube/linking-your-thinking), [LYT newsletter](https://newsletter.linkingyourthinking.com/posts/please-copy-my-example-of-notemaking)) | Finish a book, forget it; highlights rot; ChatGPT answers they cannot verify | High: they already switch tools for local-first, export, plugins | Exact: EPUB/PDF corpus, notes-in-loop, FSRS, Obsidian/Anki export, Compose self-host | **Pick** |
| Med students | [r/medicalschool 811k](https://gummysearch.com/r/medicalschool/); [r/medicalschoolanki 197k](https://gummysearch.com/r/medicalschoolanki/); AnKing Step Deck 100k+ subscribers / 300k+ downloads ([AnkiHub](https://www.ankihub.net/step-deck); [Wikipedia/Anki](https://en.wikipedia.org/wiki/Anki)) | Enormous, high-stakes | Low *switch* cost: Anki is religion; they need image occlusion, UWorld tags, shared decks | Weak: no image occlusion; quiz quality on tiny books is already a known miss (project brief); textbooks are copyright landmines | Do not beachhead |
| Bar / CPA | [r/barexam ~64k–73k](https://redpulse.io/subreddit-search/r/barexam/); [r/CPA 125k](https://gummysearch.com/r/CPA/) | High-stakes exams | They buy Barbri / Themis / Becker, not OSS book readers | Weak: commercial outlines, not personal EPUBs | Later vertical |
| Language learners | [r/languagelearning 3.4M](https://gummysearch.com/r/languagelearning/) | Vocab + input | Anki/Duolingo/LingQ already own it; books are a *method*, not the unit | Weak: Learny is not a sentence miner | Ignore for launch |
| Book clubs | Diffuse (Goodreads, r/books) | Social discussion | Low need for FSRS or citations | Social loop Learny does not have | Ignore |
| Generic "students" | [r/studytips 272k](https://gummysearch.com/r/studytips/) | Grades | RemNote already speaks this H1 | Too broad; positioning for everyone lands nowhere ([Seeto](https://seeto.ai/blog/competitive-positioning-strategy)) | Do not target |

### Why this beachhead, not the biggest pond

1. **Job match.** The pain "I read books and they don't stay" is exactly Readwise's H1 — and that audience already pays $10/mo for *passive* resurfacing. Learny is the active-recall upgrade plus cited Q&A. Med students' job is "pass Step 1 with AnKing," which Learny does not do.
2. **Distribution match.** Show HN, r/selfhosted, r/ObsidianMD, and r/Anki are where an Apache-2.0 Compose app is *welcome*. r/medicalschool will treat an AI card generator as a threat to Anki hygiene unless the cards are as good as AnKing (they are not, yet).
3. **Willingness.** PKM users already export, self-host, and try plugins. AnKing has 154k hub subscribers vs ~29k on the MCAT deck ([Anki ownership note](https://drgore.substack.com/p/ankis-ownership-is-changing)) — that is a monopoly, not an opening.
4. **Expansion path.** After the PKM beachhead, the *same story* (cite → remember → leave) extends to serious nonfiction readers (Readwise's "founders, professionals, academics") without a rewrite. Med/bar would require a different product (image occlusion, exam dates, shared official decks).

**Single sentence ICP:** A developer or knowledge worker who already uses Obsidian and/or Anki, reads technical or nonfiction books as EPUBs/PDFs, distrusts ChatGPT on specifics, and will try a Docker app on a Saturday.

---

## 4. Channel plan

### Launch sequence (do not hit all of these on the same day)

OSS launches that work treat **GitHub as the landing page**, stagger channels, and answer comments for hours ([OSS distribution playbook](https://www.linkedin.com/posts/shantanu-das-devops_oss-launch-distribution-playbook-activity-7486259158183325696-01ja); [Postiz $17k/mo playbook](https://stackstarts.com/open-source-playbook-how-nevo-built-postiz-17k-mrr/)).

| Order | Channel | Why it fits Learny | Realistic outcome | Anti-pattern |
|---|---|---|---|---|
| 0 | **Working demo without signup** + README one-command | [Show HN rules](https://news.ycombinator.com/showhn.html): "easy to try, ideally without barriers such as signups" | Qualifies the rest | Landing-page-only Show HN (explicitly off-topic) |
| 1 | **Show HN** (Tue–Thu morning US, or Sun evening per [King 2026 analysis](https://danfking.github.io/blog/2026/04/23/show-hn-by-the-numbers/)) | Self-hostable, hexagonal, citations-as-core — HN catnip | Front page: ~5k–30k visits, 50–400 signups for a dev tool ([Causo](https://hub.causo.ai/guides/show-hn-launch-playbook-technical-founders-2026)); ~1.4 GitHub stars per upvote in 48h; half-life ~24h | Marketing adjectives; "friends please upvote"; linking only the marketing site |
| 2 | **r/selfhosted** (same 48h window, *not* the same hour) | 725k–830k, +42% YoY; Docker Compose is the native dialect | High-quality self-hosters; issue reports that are actual QA | Screenshot dump with no compose file |
| 3 | **r/ObsidianMD, r/Anki, r/PKMS** | Beachhead lives here | Workflow posts outperform product posts ([Obsidian Reddit culture](https://www.aitooldiscovery.com/guides/obsidian-reddit)) | Drive-by link; ignore 9:1 contribution. Read live rules; modmail first ([Reddit promo 2026](https://www.readyt.ai/blog/reddit-self-promotion-rules/)) |
| 4 | **Product Hunt** (Tue/Wed 12:01 PT, *after* the landing page exists) | Secondary; PH is a badge + backlinks | Dev-tool top-5 day: ~500–2,000 signups, not a hockey stick ([Pristren](https://pristren.com/blog/product-hunt-launch-guide-developer-tools/)) | Launching PH before there is a hero demo (current page will bounce) |
| 5 | **PKM YouTube / newsletters** | LYT ~360k YT / 45k email; adjacent: Nicole van der Hoeven, Keep Productive | One deep "book → vault → Anki" tutorial beats ten launch posts | Paid spray before a polished export |

Title that would survive HN: `Show HN: Learny – open-source book reader with cited Q&A and FSRS (Docker Compose)`. First comment: why (ChatGPT was sure and wrong about a book), how (canonical corpus, hybrid RRF, FSRS port), what is not done (no Audio Overview, quiz quality still improving), invite: try the public-domain book or `docker compose up`.

### Open source as the growth channel

Learny is already Apache-2.0 with a one-command Compose path. The proven model is **self-host free + hosted paid** (Plausible, Cal.com, Umami, PostHog, Postiz): the repo is the outer funnel; hosting, support, and convenience are the commercial layer ([PLG Handbook OSS flywheel](https://plghandbook.com/open-source/); [Cal.com pricing teardown](https://unlocksaas.com/pricing-teardown/cal-com)). Most self-hosters never pay; they are the QA and the word of mouth. The 10% who hate running Redis+Celery+MinIO fund the hosted instance.

Do **not** open-core the citations or FSRS (those *are* the product). If anything is gated later, gate hosted AI quota and multi-user convenience — not export (killing export kills the positioning).

### SEO / content (compounding, not launch week)

Paid keyword tools were not queried; classify by **SERP competition and Google volume buckets** ([Authoritas buckets](https://www.authoritas.com/blog/understanding-googles-search-volume-buckets-a-deep-dive-into-how-search-volumes-really-work): 100–1K medium, 1K–10K high).

- **Head informational cluster (likely 1K–10K bucket, high KD):** "how to remember what you read." SERP is packed with Farnam Street–style essays and adjacent-product blogs ([Chapterly](https://chapterly.ai/blog/how-to-remember-what-you-read), [Notesmakr](https://notesmakr.com/blog/how-to-remember-what-you-read)). A new domain will not rank this in month one. Write it anyway as the **pillar** — it is the job-to-be-done in searcher language, and it matches Readwise's proven H1.
- **Medium / long-tail (100–1K, actually winnable):** "FSRS vs Anki SM-2", "export highlights to Obsidian", "NotebookLM vs Anki", "cite ChatGPT answers from a PDF", "self-host spaced repetition", "how to turn a book into Anki cards without typing."
- **Branded / comparison (write at launch):** "Learny vs NotebookLM", "Learny vs Readwise" — these convert, they do not get traffic until the name exists.
- **Do not chase:** "best AI tutor", "ChatGPT for studying" (Gemini/OpenAI occupy those).

One deep use-case tutorial at launch > ten generic posts (OSS playbook above). Structure for AI retrieval (`llms.txt`, honest comparisons) because LLMs will recommend tools from docs before humans find the landing page.

### Shareable surfaces: evidence for / against

**For a growth loop (later, constrained):**

- Anki's shared-deck culture *is* a real acquisition engine: AnKing 300k+ downloads; 86% of surveyed US med students used Anki ([Wikipedia](https://en.wikipedia.org/wiki/Anki)). Private `.apkg` sharing (email, Drive) is first-class in [Anki's own manual](https://docs.ankiweb.net/contrib).
- Obsidian Publish / digital gardens show that **public notes** can attract search traffic without being a social network ([Obsidian Publish](https://obsidian.md/publish)). User-authored notes, not book text.

**Against as a launch feature:**

- AnkiWeb imposes a **24h delay** so rights holders can kill decks before they go live ([Anki forums](https://forums.ankiweb.net/t/how-is-my-shared-deck-checked-by-copyright-holders/66227); [terms](https://ankiweb.net/account/terms) require asserting originality or a license). Quizlet runs full DMCA takedowns ([help article](https://help.quizlet.com/hc/en-us/articles/360030632972-Why-was-my-content-removed-for-copyright)) and has been in AI+copyright litigation ([Thompson Coburn on *Barkley v. Quizlet*](https://www.thompsoncoburn.com/insights/education-platform-liability-in-the-ai-era-divergent-outcomes-for-quizlet-and-course-hero/)).
- AnKing had to **strip textbook images** they did not license ([AnkiHub thread](https://community.ankihub.net/t/ankihub-removing-copyrighted-images-if-it-aint-broke-dont-fix-it/1640)). Learny cards are generated *from book passages* — a public deck is a high-probability verbatim leak.
- Gemini Notebook already warns that Play Books sources may **block flashcard download**. Publishers are watching this exact surface.
- Book clubs / public notebooks sharing *the book* would make Learny a piracy host. RQ09 (public-launch readiness) owns DMCA process; growth must not create the incident.

**Rule:** share **user-authored notes and user-edited cards** (no stored book snippets in the public payload). Never share corpus text, highlights that quote the book, or auto-generated cards that contain cloze of copyrighted sentences. Invite-only study groups are safer than a public gallery. Export-to-Anki *for the owner* is the growth feature that already exists; a marketplace is not.

---

## 5. Cycle-sized moves

Each item is one spec-driven cycle (or smaller). Ordered by "do before asking strangers to visit."

### Move 1 — Positioning lock + landing page v1 (hero demo, unlike table, dual CTA)

- **Why-recommend:** The current page cannot convert PH or HN traffic. AI visitors need to *see* a cited answer. Statement A + public-domain demo is the whole launch dependency. HOME-20 already reserved this surface.
- **Why-not:** Costs design/engineering that could go to quiz quality (brief: decks can succeed with zero cards). A pretty page on a broken Ask path (observed Anthropic 400) will *increase* bounce. Do not ship the page until the money-path on a fixture book is green.

### Move 2 — Try-without-signup on one public-domain book

- **Why-recommend:** Show HN guidelines require it. RemNote/Recall/NotebookLM all let you start in seconds. Removes the "create account to see if citations are real" tax.
- **Why-not:** Abuse and AI-cost surface (RQ09). Must be a fixed book, rate-limited, no arbitrary upload on the anonymous path. If cost caps are not ready, ship a **recorded** loop plus `docker compose` instead, and say so honestly on HN.

### Move 3 — README as HN landing (already half-done; finish the demo media)

- **Why-recommend:** `docs/media/README.md` already scripts the ≤90s path; binaries are gitignored. HN and r/selfhosted click the repo, not learny.app. Stars in 48h correlate with HN score ([King](https://danfking.github.io/blog/2026/04/23/show-hn-by-the-numbers/)).
- **Why-not:** Capturing demo GIFs is not a product cycle if the live demo (Move 2) exists. Don't block launch on polish if compose-up works.

### Move 4 — Staggered launch: Show HN → r/selfhosted → niche subs → Product Hunt

- **Why-recommend:** Same post on the same day wastes every trust layer. PH needs the landing from Move 1; HN needs the try-path from Move 2.
- **Why-not:** Launch theater before Ask/quiz are trustworthy will poison the only first impression HN gives you (24h half-life). If the observed generation 400 is still open, **do not launch**.

### Move 5 — One pillar essay + 3 long-tails (not a blog engine)

- **Why-recommend:** "How to remember what you read" is the search-shaped job; long-tails (FSRS, Obsidian export, vs NotebookLM) are the winnable cluster. One tutorial is the OSS content playbook.
- **Why-not:** SEO is a 6–12 month game on a zero-DA domain. Do not staff a content calendar instead of the demo. Do not publish affiliate-style "best AI study tools" listicles.

### Move 6 — Export as marketing (already shipped; surface it)

- **Why-recommend:** Portability *is* the anti-Google claim. Put Anki/Obsidian export on the landing and in every HN comment. Killing or gating export later would contradict positioning.
- **Why-not:** Don't build bidirectional vault sync (ADR-0026 deferred) just to have a "vs Readwise" checkbox. One-way export is enough for the story.

### Move 7 — Private share links for *notes* (not books, not auto-cards)

- **Why-recommend:** Digital-garden / "look at my notes on X" is a real PKM habit; invite-only is how Anki already recommends group sharing.
- **Why-not:** A public deck gallery is a DMCA machine (AnkiWeb delay, Quizlet takedowns, AnKing image purge). Do not build UGC search, comments, or SEO pages of cards derived from books.

### Move 8 — Hosted public instance as the paid convenience track (after OSS traction)

- **Why-recommend:** Cal.com/Plausible pattern: repo builds trust; hosted converts people who will not run Celery. Aligns with the fleet goal (multi-tenant public app) without making OSS a lie.
- **Why-not:** Hosting is an ops+billing cycle (RQ09, RQ10). Launching hosted *before* self-host proof wastes the HN story. Don't wait for billing to do Moves 1–4.

### Explicitly not cycles (for growth)

- **Med-school GTM / AnKing competitor.** Wrong job, copyright-max, quality bar Learny has not met.
- **Audio Overview clone.** That is Gemini Notebook's viral loop; chasing it surrenders the memory/portability wedge.
- **Fake social proof or waitlist theater.** PKM and HN audiences punish it; Readwise's actual proof is named people and 8 years of bootstrap.

---

## Sources (primary)

- Product pages: [Learny landing (current)](https://github.com/augusto-dmh/learny) via `frontend/app/page.tsx`; [Gemini Notebook](https://notebooklm.google/); [rebrand post, 16 Jul 2026](https://blog.google/innovation-and-ai/products/gemini-notebook/notebooklm-gemini-notebook/); [Notebook flashcards help](https://support.google.com/gemininotebook/answer/16958963); [Readwise](https://readwise.io/); [Readwise Reader](https://readwise.io/read); [RemNote](https://www.remnote.com/); [Recall](https://www.recall.it/); [Plausible](https://plausible.io/)
- Incumbent study comparisons: [XDA](https://www.xda-developers.com/tested-notebooklm-gemini-claude-and-chatgpt-for-studying/); [Coursiv](https://coursiv.io/blog/notebooklm-vs-chatgpt); [AI Native Student](https://ainativestudent.com/blog/notebooklm-vs-chatgpt-studying/)
- Positioning method: [Dunford quickstart](https://aprildunford.substack.com/p/a-quickstart-guide-to-positioning); [AI product positioning vs ChatGPT](https://udit.co/blog/raw/ai-product-positioning); [Linear vs Jira](https://tools.davidshadrake.com/case-studies/growth-hacking/linear); [Cursor vs Copilot](https://zapier.com/blog/cursor-vs-copilot/); [Cal.com funnel](https://unlocksaas.com/funnel-teardown/cal-com)
- Landing craft: [TheKitBase](https://thekitbase.app/blog/anatomy-ai-saas-landing-page); [Nobody trusts your AI product](https://behindthelaunchh.substack.com/p/nobody-trusts-your-ai-product-yet)
- Communities: GummySearch / Hive Index / RedPulse pages linked in §3; [AnkiHub Step Deck](https://www.ankihub.net/step-deck); [LYT](https://app.thoughtleaders.io/youtube/linking-your-thinking)
- Launch: [Show HN guidelines](https://news.ycombinator.com/showhn.html); [Show HN by the numbers](https://danfking.github.io/blog/2026/04/23/show-hn-by-the-numbers/); [PH guide](https://pristren.com/blog/product-hunt-launch-guide-developer-tools/); [OSS flywheel](https://plghandbook.com/open-source/)
- Copyright / sharing: [AnkiWeb terms](https://ankiweb.net/account/terms); [Anki copyright delay](https://forums.ankiweb.net/t/how-is-my-shared-deck-checked-by-copyright-holders/66227); [Quizlet DMCA](https://help.quizlet.com/hc/en-us/articles/360030632972-Why-was-my-content-removed-for-copyright); [AnKing image purge](https://community.ankihub.net/t/ankihub-removing-copyrighted-images-if-it-aint-broke-dont-fix-it/1640)
