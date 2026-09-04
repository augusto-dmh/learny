# RQ01 — Competitive landscape: book-grounded AI learning (2025–2026)

*Research date: 2026-09-03. Scope: who else does book-grounded AI learning / reading intelligence, what is table stakes for a public launch, and where Learny should double down vs catch up. Claims below are cited; third-party review numbers are labeled as such.*

## TL;DR

By mid-2026 the “chat with my book” category is no longer a startup niche. Google’s NotebookLM (renamed **Gemini Notebook**, July 2026) is the default free, source-grounded study studio with clickable citations, EPUB support, flashcards/quizzes, and Audio Overviews. Readwise Reader is the default power-reader + highlight → Obsidian pipeline. Recall (`recall.it`, formerly getrecall.ai) is the default “save anything, summarize, quiz later” knowledge base. RemNote and Anki own serious spaced repetition. ChatGPT Study Mode and Claude Learning Mode own generic tutoring. Nobody ships Learny’s full intersection: **structure-preserving book corpus + passage-level citations in a real reader + FSRS + section-scoped teaching + notes fused into Q&A + deterministic Obsidian vault**. Public launch does not require beating NotebookLM at podcasts or Readwise at RSS. It does require matching table-stakes trust UX (click-to-passage, no silent AI failure, a reader that looks like reading) and doubling down on the loop peers split across three apps.

---

## 1. How the field actually segments

Four overlapping clusters, not one “book AI” market:

| Cluster | Job-to-be-done | Typical peers |
|---|---|---|
| **Study studio** | Upload sources → synthesize, quiz, listen | Gemini Notebook, Otio, commodity ChatPDF/Humata |
| **Power reading** | Read, highlight, listen, export | Readwise Reader, Matter |
| **Remember** | Cards + schedule, sometimes notes | Anki/AnkiWeb, RemNote, Recall quizzes |
| **Generic tutor** | Socratic help on *any* topic | ChatGPT Study Mode, Claude Learning, Khanmigo |
| **Summary library** (adjacent) | Consume *their* books, not yours | Blinkist, Shortform; Snipd for podcasts |

Learny sits at the intersection of studio + reading + remember, scoped to **the user’s own books**. That is rare. The threat is not a clone; it is a stranger already having “good enough” cited Q&A in NotebookLM plus review in Anki, for $0.

Demand for “chat with a book” is old and explicit on HN ([item 39719547](https://news.ycombinator.com/item?id=39719547)). Audio Overviews created a second demand spike for *listen-to-the-book* ([item 43848794](https://news.ycombinator.com/item?id=43848794); Karpathy quoted on the product site: [notebooklm.google](https://notebooklm.google/)).

---

## 2. Study studios: Gemini Notebook (NotebookLM) and Otio

### 2.1 Gemini Notebook (formerly NotebookLM)

**What it is.** Source-grounded research/study assistant. Upload PDFs, web, YouTube, Docs, Slides, audio; chat is restricted to those sources; citations are first-class ([product](https://notebooklm.google/), [help](https://support.google.com/notebooklm/answer/16164461)). Rename to Gemini Notebook: July 2026 ([FAQ on product page](https://notebooklm.google/)).

**What it does well (evidence).**

- **Click-to-passage citations.** Hover for the quote; click jumps to the location in the source ([chat help](https://support.google.com/notebooklm/answer/16179559)). This is the user-loved trust mechanic Reddit threads keep repeating ([secondary synthesis of r/notebooklm](https://www.aitooldiscovery.com/guides/notebooklm-reddit)).
- **Study artifacts at one click.** Flashcards and quizzes grounded in sources, with Explain + citations back to the original ([Google blog, 2025-09-08](https://blog.google/innovation-and-ai/models-and-research/google-labs/notebooklm-student-features/); [help](https://support.google.com/notebooklm/answer/16958963)). Progress now persists; cards can be marked Got it / Missed it; missed cards can be rerun; CSV download ([Workspace Updates, 2026-03-20](https://workspaceupdates.googleblog.com/2026/03/new-ways-to-customize-and-interact-with-your-content-in-NotebookLM.html)).
- **Audio Overviews** (Deep Dive podcasts) plus Brief / Critique / Debate formats ([same Google blog](https://blog.google/innovation-and-ai/models-and-research/google-labs/notebooklm-student-features/); [Audio Overview help](https://support.google.com/notebooklm/answer/16212820)). Homeschool/HN users treat them as a *scaffold before deep reading*, not as the book ([HN 43848794](https://news.ycombinator.com/item?id=43848794)).
- **Socratic “Learning Guide”** inside the notebook ([Google blog](https://blog.google/innovation-and-ai/models-and-research/google-labs/notebooklm-student-features/)).
- **EPUB as a source** for all users as of March 2026 ([Workspace Updates](https://workspaceupdates.googleblog.com/2026/03/new-ways-to-customize-and-interact-with-your-content-in-NotebookLM.html)). Independent write-up: EPUB restores chapter boundaries that PDF dumps destroy ([MakeUseOf](https://www.makeuseof.com/stopped-using-notebooklm-but-tiny-epub-feature-dragged-me-back/)).
- **Sharing.** Consumer public notebooks; Enterprise viewer/editor sharing ([Cloud docs](https://cloud.google.com/agentspace/notebooklm-enterprise/docs/share-notebooks)).

**Pricing (brief).** Free Standard: usable, **50 sources per notebook**. Paid is *not* a NotebookLM SKU — it is bundled in Google AI Plus / Pro / Ultra ([official plans](https://notebooklm.google/plans); [Gemini subscriptions](https://gemini.google/subscriptions/)). Caps scale to 100 / 300 / 600 sources per notebook on Plus / Pro / Ultra ([plans](https://notebooklm.google/plans)). Dollar amounts move with Google One: independent 2026 guides put Plus ~$4.99–$9.99/mo and Pro at $19.99/mo ([Fello](https://felloai.com/notebooklm-pricing/), [Google One plans](https://one.google.com/about/plans)); Ultra starts at $99.99/mo ([Gemini subscriptions](https://gemini.google/subscriptions/)).

**What users love.** Groundedness (“it will not pretend to know things outside your sources”); Audio Overviews as a new product format; free tier that is actually usable.

**What it lacks vs Learny.**

- **Not a book reader.** No TOC-anchored reading, highlights-as-corpus, or teach-this-section loop. It is a *studio beside* the file.
- **No FSRS.** Flashcards are session practice with Got it/Missed it, not a memory model ([help](https://support.google.com/notebooklm/answer/16958963); independent: “SRS algorithm: none” ([StudyMethod](https://studytoolguide.com/ai-study-tools/notebooklm-ai-study-tool-guide))).
- **No Obsidian-class vault.** CSV flashcards, Google Docs/Slides export — not a second-brain projection.
- **Notebook isolation.** Cross-notebook query is a long-standing complaint ([Reddit synthesis](https://www.aitooldiscovery.com/guides/notebooklm-reddit)).
- **Audio Overviews can drift** off the source; users are warned not to treat them as citable ([same Reddit synthesis](https://www.aitooldiscovery.com/guides/notebooklm-reddit)).
- **DRM EPUBs** will not ingest ([MakeUseOf](https://www.makeuseof.com/stopped-using-notebooklm-but-tiny-epub-feature-dragged-me-back/)).

### 2.2 Otio (and the ChatPDF commodity layer)

**Otio** is a cited research workspace: PDF/EPUB/web/YouTube, **page- and timestamp-level citations**, highlight-in-source and ask, markdown note export, Zotero/Mendeley, every frontier model on every plan including Free ([pricing, updated 2026-07-07](https://otio.ai/pricing); [book summarizer claims](https://otio.ai/features/ai-book-summarizer); [PDF reader](https://otio.ai/features/ai-pdf-reader)). Lite $7/mo, Go $18/mo, Pro $45/mo (annual −50%). They explicitly pitch “NotebookLM caps sources; we don’t.”

**Commodity PDF chat** (Humata Expert ~$9.99/mo, [humata.ai/pricing](https://www.humata.ai/pricing); AskYourPDF Premium ~$9.99/mo, [review](https://toolchase.com/tool/askyourpdf/); ChatPDF as the no-signup one-shot) trained users to expect *some* page citation. It is table stakes, not a moat. None of these products are a book-learning system.

---

## 3. Power reading: Readwise Reader and Matter

### 3.1 Readwise Reader (+ Readwise Daily Review)

**What it is.** Read-it-later + EPUB/PDF reader + first-class highlighting, with Ghostreader AI and automatic sync into Readwise review and note apps ([readwise.io/read](https://readwise.io/read)).

**Pricing.** 30-day trial, no card. Full subscription **$9.99/mo billed annually or $12.99/mo**; 50% discount for students/educators/etc. by email ([same page](https://readwise.io/read)). Reader is *not* sold without Full Readwise.

**What it does well.**

- **Reader craft:** keyboard navigation, TTS (“lifelike” voices, any article/PDF/ebook), offline, iOS/Android/web/desktop/e-ink ([FAQ on product page](https://readwise.io/read)).
- **EPUB as a first-class book**, not a converted PDF ([product](https://readwise.io/read); [2026 review](https://www.speedreadinglounge.com/readwise-reader-review)).
- **Ghostreader:** in-document Q&A, define/simplify, flashcard-ish prompts; **Global Ghostreader** searches the *whole library* with citations that link to the source ([docs](https://docs.readwise.io/reader/docs/faqs/ghostreader)). Default model GPT-5 Mini included; BYOK for stronger models ([same docs](https://docs.readwise.io/reader/docs/faqs/ghostreader)).
- **MCP** into Claude/ChatGPT/Cursor for grounded answers over the library ([product FAQ](https://readwise.io/read)).
- **Obsidian:** official plugin, continuous append-only sync, Jinja templates ([docs](https://docs.readwise.io/readwise/docs/exporting-highlights/obsidian); [plugin](https://github.com/readwiseio/obsidian-readwise)).
- **Portability:** Markdown highlights, OPML, zip of files ([FAQ](https://readwise.io/read)). Bootstrapped-since-2017 trust pitch after Pocket died.

**What users love.** “Superhuman of reading” testimonials on the product page; highlight → Daily Review → Obsidian as *the* PKM plumbing ([picturingtolearn analysis](https://picturingtolearn.org/readwise-matter-read-it-later/)).

**What it lacks vs Learny.**

- **Daily Review is mostly re-exposure, not FSRS active recall.** Product copy says spaced repetition ([readwise.io/read](https://readwise.io/read)); cognitive-science critique: seeing a highlight again is rereading, not retrieval ([Picturing to Learn](https://picturingtolearn.org/readwise-matter-read-it-later/)). Readwise *can* turn highlights into Q/A and cloze ([Build First Brain](https://buildfirstbrain.com/journal/reader-by-readwise-the-frictionless-trap/)), but that is not a book-section teaching graph.
- **No structure-preserving canonical corpus** for teaching a *chapter*. Ghostreader is document/library RAG, not Learny’s section-path + stable anchors.
- **No FSRS scheduler** as a product primitive (Anki/RemNote/Learny).

### 3.2 Matter

iOS-first read-later: typography, HD TTS, Co-Reader Q&A, newsletters, highlight export. Premium **$8/mo or $60/yr on the web** (App Store ~$79.99/yr) ([2026 pricing write-ups](https://www.readless.app/blog/matter-app-pricing-2026), [ToolChase](https://toolchase.com/tool/matter-app/)). Pocket shutdown (July 2025) pushed migrants here. **Conflicting 2026 reports:** some claim maintenance mode since late 2024 ([DEV](https://dev.to/fisher_shenfisher_1c32/matter-app-alternative-2026-6-read-later-apps-compared-after-matter-stopped-updating-11m0)); App Store history still shows 2026 bugfixes and an iOS 26 Liquid Glass refresh ([iPa4Fun history](https://www.ipa4fun.com/history/619853/)). Either way: **no native SRS, weak Android, not a book tutor.** Learny should steal *reading delight* (Aa, TTS), not Matter’s capture graph.

---

## 4. Capture-and-remember: Recall, RemNote, Anki

### 4.1 Recall (getrecall.ai → [recall.it](https://www.recall.it/pricing))

**What it is.** One-click save of articles, YouTube, podcasts, PDFs → instant AI summary, auto tags, knowledge graph, library-wide chat with citations, quizzes + spaced repetition. Claims **700,000+** lifelong learners ([pricing](https://www.recall.it/pricing)).

**Pricing.** Free: unlimited saves/notes, **10 AI summaries/month**. Plus **$10/mo billed yearly** (unlimited summaries, chat, graph, listen mode, quiz/SRS, bulk import). Max **$38/mo billed yearly** (model choice, bulk AI). 30-day refund; 20% student discount ([pricing](https://www.recall.it/pricing)).

**What users love.** Summaries-on-save; chat across the whole library vs NotebookLM’s per-notebook wall (Recall’s own comparison on the pricing FAQ); quizzes that force retrieval ([Habr hands-on](https://habr.com/en/articles/1016222/); [Medium Quiz 2.0](https://medium.com/@proflead/this-ai-uses-spaced-repetition-to-help-you-remember-more-1b2ed2c4ce13)). Markdown zip export ([review](https://hypertools.so/tool/recall)); API/MCP read access ([Canny](https://feedback.recall.it/feature-requests/p/api-access-to-your-recall-knowledge-base)).

**Complaints.** Auto-created graph links pollute the library ([getrecall.ai Canny](https://feedback.getrecall.ai/feature-requests/p/option-not-to-autocreate-links)); extension performance ([Firefox reviews](https://addons.mozilla.org/en-US/firefox/addon/getrecall/reviews/?score=2)). SRS is productized but **not advertised as FSRS**.

**Vs Learny.** Recall wins capture breadth and “everything I saved is one brain.” Learny wins **book structure, passage citations in a reader, FSRS, teaching, Obsidian vault semantics**. Recall is the closest *product-shape* competitor for “learn what I ingest,” but it is a knowledge-base, not a book.

### 4.2 RemNote

Notes-and-cards in one outliner; **FSRS and SM-2**; cards inherit note context; Exam Scheduler; AI cards from notes/PDFs; Anki import including history ([official SRS page](https://www.remnote.com/feature/spaced-repetition)). FSRS claimed to cut reviews 20–40% vs SM-2 ([same](https://www.remnote.com/feature/spaced-repetition)).

**Pricing (2026 reviews, not a live fetch of checkout):** Free = unlimited notes/cards, **3 annotated PDFs**, ~100 AI credits/mo; Pro ~$8–$10/mo annual; **Pro with AI** ~$18–$20/mo / $216/yr for 20k credits ([tldv 2026](https://tldv.io/blog/remnote/), [MintDeck comparison](https://www.mintdeck.app/blog/mintdeck-vs-remnote)). Loved by med students on the marketing page. Complaints: busy UI, iOS quality, AI credit stinginess.

**Vs Learny.** RemNote is ahead on **card-in-context UX, exam dates, Anki-history import, PDF annotation volume**. Learny is ahead on **cited book Q&A, canonical sections, teaching sessions, vault export**. Do not try to out-RemNote RemNote’s outliner.

### 4.3 Anki / AnkiWeb ecosystem

Still the gravity well for serious memory. **FSRS in Anki since 23.10**; AnkiWeb/AnkiMobile/AnkiDroid all support it ([Anki FAQ](https://faqs.ankiweb.net/what-spaced-repetition-algorithm.html); [deck options manual](https://docs.ankiweb.net/deck-options.html)). Users can target ~90% retention; fewer reviews than SM-2 for the same retention ([FAQ](https://faqs.ankiweb.net/what-spaced-repetition-algorithm.html)). Desktop/Android/AnkiWeb free; iOS one-time ~$24.99 (widely reported, e.g. [Memly comparison](https://memly.ai/en/blog/anki-vs-gizmo)).

Reddit-class consensus in 2025–26: **AI generates cards; Anki/FSRS schedules them** — do not trap cards in a closed all-in-one ([StudyCardsAI roundup of Reddit](https://studycardsai.com/blog/5-best-ai-tools-for-active-recall-to-ace-your)). Learny already ships `.apkg` with stable GUIDs — that is aligned with this culture. Native AI flashcard apps (Gizmo, Flica, Memly) compete on *ease*, not on book-grounded citations.

---

## 5. Generic tutors: ChatGPT, Claude, Khanmigo

These are what a public user will try **before** installing Learny.

**ChatGPT Study Mode** (launched 2025-07-29): Socratic hints, scaffolding, knowledge checks; on **Free, Plus, Pro, Team** ([OpenAI](https://openai.com/index/chatgpt-study-mode/); [feature page](https://chatgpt.com/features/study-mode/)). Powered by custom system instructions; OpenAI admits inconsistency and that it may still dump answers ([same launch post](https://openai.com/index/chatgpt-study-mode/)). Can use uploaded PDFs/images ([2026 FAQ roundup](https://appscribed.com/chatgpt-study-mode/)). **Not source-grounded in Learny’s sense** — citations are not a product invariant.

**Claude Learning mode** (Education launch 2025-04-02; later a style for all users): guide rather than answer, Socratic, templates ([Anthropic](https://www.anthropic.com/news/introducing-claude-for-education)). **Projects** = persistent files + instructions (commonly ~30 files) ([guide](https://claudeguide.io/claude-projects-guide)). API citations exist for PDF/text, but the consumer product is not a book reader. Learny already uses Claude behind a port — the *pedagogy* of Learning mode is the bar for Teach, not the hosting model.

**Khanmigo:** Socratic tutor **on Khan Academy’s library**, $4/mo or $44/yr for US learners/parents; teachers free ([khanmigo.ai/pricing](https://khanmigo.ai/pricing)). **2026 Chalkbeat / Oreopoulos study:** students used it only about a third of Khan days; much off-task or “just give the answer”; Sal Khan: AI tutor was a “non-event” unless woven into the exercise ([Chalkbeat, 2026-08-25](https://www.chalkbeat.org/2026/08/25/ai-tutoring-students-khanmigo-khan-academy-engagement-study/)). Lesson for Learny: **a Teach tab that sits beside the book will be ignored unless the next action is forced by the reading/review loop.**

---

## 6. Adjacent: Blinkist, Shortform, Snipd, Glasp

**Blinkist** — 15-minute summaries of *their* 9,000+ titles. Premium ~$79.99–$99.99/yr intro then higher; Pro adds Blinkist AI on *your* links/PDFs ~$139.99 intro / $174.99 renew ([blinkist.com/pricing](https://www.blinkist.com/pricing), [help](https://support.blinkist.com/en/articles/10033366-what-are-the-different-blinkist-subscription-plans-and-their-benefits)). **Not your book, not citable to a passage you own.**

**Shortform** — long human-written guides + exercises; **$16.42/mo annual or $24/mo** ([shortform.com/pricing](https://www.shortform.com/pricing)). Users praise reading a chapter then the guide ([testimonials on pricing page](https://www.shortform.com/pricing)). Competes with Learny for *time*, not for *your EPUB*.

**Snipd** — headphone-tap snips, chat with episode, **export to Readwise/Notion/Obsidian/Glasp**; daily recap “spaced repetition”; Free vs Premium **$6.99/mo** ([snipd.com/pricing](https://www.snipd.com/pricing)). Proof that **capture-while-consuming + export to the user’s second brain** is a loved loop. Books ≠ podcasts, but the export expectation transfers.

**Glasp** — highlight web/PDF/YouTube, chat with PDF + page citations, export ([tutorial](https://read.glasp.co/p/how-to-chat-with-pdf-on-glasp)). Lightweight PKM, not FSRS/teaching.

---

## 7. Feature matrix vs Learny’s four claimed edges

| Capability | Gemini Notebook | Readwise | Recall | RemNote | Anki | ChatGPT/Claude | **Learny today** |
|---|---|---|---|---|---|---|---|
| Passage-level citations you can jump to | Yes (studio) | Ghostreader cites | Chat cites sources | Weak | n/a | Unreliable | **Yes (Ask/Teach)** |
| Structure-preserving book corpus | Partial (EPUB 2026) | Reader TOC, not canonical DB | Flat cards | Notes tree | n/a | Upload blob | **Yes (canonical + anchors)** |
| FSRS (or equivalent memory model) | No | Leitner-ish Daily Review | Generic SRS | **FSRS + SM-2** | **FSRS** | No | **FSRS** |
| Obsidian | No | **Continuous plugin** | MD zip | MD import/export | Indirect | Projects files | **Deterministic vault zip** |
| In-book reader + docked Ask/Teach/Notes/Review | No | Reader + Ghostreader | No | PDF notes | No | No | **Yes** |
| Section-scoped teaching | Learning Guide (notebook) | No | No | Cards in notes | No | Study/Learning modes | **Yes (needs pedagogy)** |
| Multi-format capture (web/YT/RSS) | Yes | **Best** | **Best** | Weak | No | Yes | No |
| Audio / TTS / podcast overview | **Best** | Strong TTS | Listen Mode | Weak | Add-ons | Voice | Weak/absent |
| Mobile apps | Yes | Yes | Yes | Yes (uneven) | Yes | Yes | Web only |
| Sharing | Yes | Limited | Limited | Yes | Shared decks | Chats | No |

---

## 8. (a) Table stakes before public launch

These are **expectations a 2026 user already has**, formed by NotebookLM + ChatGPT + Readwise, not nice-to-haves:

1. **Click a citation → land on the exact passage in the book**, with the quote visible. Gemini Notebook made this the trust standard ([chat help](https://support.google.com/notebooklm/answer/16179559)). Learny’s architecture supports it; the UI must *feel* as inevitable as NotebookLM’s hover/click.
2. **EPUB and PDF ingest that preserves chapters**, with honest status (“ready / failed / N cards”). EPUB is now a NotebookLM source ([Workspace Updates](https://workspaceupdates.googleblog.com/2026/03/new-ways-to-customize-and-interact-with-your-content-in-NotebookLM.html)); labeling the uploader “EPUB file” while PDF works is below table stakes (project brief).
3. **A reader that looks like reading** (TOC, type size, progress). Chat-only PDF tools are the *commodity*; Readwise/Matter set the floor for people who actually finish books.
4. **Ask that does not silently destroy the conversation** when generation 400s (observed 2026-09-03 walkthrough). ChatGPT and NotebookLM keep the thread.
5. **Flashcards whose progress survives a reload**, with a due queue that is not an empty lie. NotebookLM shipped this in March 2026 ([Workspace Updates](https://workspaceupdates.googleblog.com/2026/03/new-ways-to-customize-and-interact-with-your-content-in-NotebookLM.html)). Generating a deck in 0.02s with zero reviewable items fails this bar (brief).
6. **First-session time-to-cited-answer under a few minutes**, explained on a landing page that is not a bare tagline. NotebookLM’s free on-ramp is the competitor for “I’ll try it tonight.”
7. **Export you can leave with** (Markdown/Anki/Obsidian). Pocket’s death made this non-negotiable; Readwise and Recall market it hard ([Readwise FAQ](https://readwise.io/read); [Recall FAQ](https://www.recall.it/pricing)).
8. **Responsive web that is usable on a phone for review + ask**, even without native apps. Every peer above has a mobile client.
9. **Privacy one-liner** matching Google’s “we don’t train on your notebooks unless you feedback” ([NotebookLM help](https://support.google.com/notebooklm/answer/16164461)) and Recall’s “we do not train on your content” ([pricing FAQ](https://www.recall.it/pricing)).
10. **Copyright/upload honesty** (DRM EPUBs fail everywhere; Google states copyright policy on the same help page). Public launch without a DMCA/abuse story is not competitive; it is operational (RQ09), but users will compare.

**Explicitly not table stakes for v1 public:** Audio Overviews, mind maps, YouTube/RSS, knowledge-graph auto-links, Exam Scheduler, native iOS TTS quality, sharing notebooks.

---

## 9. (b) Differentiators Learny should double down on

1. **Canonical structure + stable anchors as the product, not the pipeline.** NotebookLM only recently gained EPUB chapter awareness ([MakeUseOf](https://www.makeuseof.com/stopped-using-notebooklm-but-tiny-epub-feature-dragged-me-back/)); most RAG apps still flatten. Teach-this-section and citation-to-anchor only work if this stays sacred (ADR-0002/0003).
2. **The in-reader dock: Ask / Teach / Notes / Review on the same page as the text.** Khanmigo evidence says a tutor *beside* content gets skipped ([Chalkbeat](https://www.chalkbeat.org/2026/08/25/ai-tutoring-students-khanmigo-khan-academy-engagement-study/)); Learny already *weaves* AI into the reader — that is the Sal Khan lesson, if Teach/Review are obligatory next steps, not optional tabs.
3. **FSRS with grounded cards (book + note origin) and Anki escape hatch.** NotebookLM quizzes are practice; Readwise Daily Review is re-exposure; Learny can be the only book reader whose review is the same algorithm serious learners already trust ([Anki FAQ](https://faqs.ankiweb.net/what-spaced-repetition-algorithm.html)).
4. **Notes in retrieval, cited as “Your note,” opt-in.** Recall and Readwise chat with *saves/highlights*; they do not distinguish user thought from author text the way ADR-0026 does.
5. **Deterministic Obsidian vault (byte-identical zip) as a *projection*, not a sync war.** Readwise wins continuous sync; Learny can win *reproducible, non-destructive export* for people burned by overwrite plugins. Position it that way; do not silently compete with the official Readwise plugin.
6. **Trust as eval, not marketing.** Golden fixtures + citation-core ADRs are unique among this peer set. A public “every answer is checkable” demo is the anti-ChatGPT-study-mode story.

---

## 10. (c) Gaps where a peer is clearly ahead (with evidence)

| Gap | Who is ahead | Evidence | How dangerous for launch? |
|---|---|---|---|
| **Listen / commute mode** | Gemini Notebook Audio Overviews; Readwise/Matter TTS | [Audio help](https://support.google.com/notebooklm/answer/16212820); [Readwise FAQ](https://readwise.io/read); HN love ([43848794](https://news.ycombinator.com/item?id=43848794)) | High for attractiveness; medium for intelligence. A chapter TTS is enough; do not clone Deep Dive. |
| **Study-artifact factory** (mind map, slides, study guide, infographic) | Gemini Notebook Studio | [Google blog](https://blog.google/innovation-and-ai/models-and-research/google-labs/notebooklm-student-features/) | Medium. Users will still keep NotebookLM for this. Do not spend a cycle matching the studio. |
| **Library-wide chat** | Recall; Readwise Global Ghostreader; Otio | [Recall pricing FAQ](https://www.recall.it/pricing); [Ghostreader docs](https://docs.readwise.io/reader/docs/faqs/ghostreader); [Otio](https://otio.ai/pricing) | Medium. Learny is per-source today; “ask across my shelf” is a natural v1.1. |
| **Capture from the open web / YouTube / RSS** | Readwise, Recall, Snipd | Product pages cited above | Low for *book* launch. Competing here is a different company. |
| **Continuous Obsidian sync + templates** | Readwise Official plugin | [docs](https://docs.readwise.io/readwise/docs/exporting-highlights/obsidian) | Medium for PKM crowd. Vault zip is enough if discoverable; sync is a later cycle. |
| **Socratic tutor quality + memory across sessions** | ChatGPT Study; Claude Learning | [OpenAI](https://openai.com/index/chatgpt-study-mode/); [Anthropic](https://www.anthropic.com/news/introducing-claude-for-education) | High for Teach mode credibility. Learny has the *hook* (section scope); not yet the *pedagogy*. |
| **Card-in-note UX + exam date** | RemNote | [remnote.com/feature/spaced-repetition](https://www.remnote.com/feature/spaced-repetition) | Low for public book learners; high if targeting med school. Stay in books. |
| **Native mobile + offline** | Readwise, Anki, NotebookLM apps | Product pages | High for retention, not for first-weekend wow. Responsive review + PWA is the cycle-sized cut. |
| **Sharing a notebook/deck** | Gemini Notebook public notebooks; Anki shared decks | [plans / product](https://notebooklm.google/plans) | Medium for growth (RQ12). Not required to *use* Learny. |
| **Model choice / BYOK** | Otio (all models all plans); Recall Max; Readwise BYOK | [Otio](https://otio.ai/pricing); [Recall](https://www.recall.it/pricing); [Ghostreader](https://docs.readwise.io/reader/docs/faqs/ghostreader) | Low given ADR-0019/0020. Do not unlock new SDKs for launch. |
| **Free, generous on-ramp** | Gemini Notebook Standard | [plans](https://notebooklm.google/plans) | High for acquisition. A key-free demo path (deterministic or capped Claude) is the response, not matching Google’s cost structure. |

---

## What this means for Learny

### Positioning

**Recommend:** Public sentence: *“NotebookLM is a study studio for files you dump. Learny is the book: read it, ask it, get taught a passage, and remember it on an FSRS schedule — with citations that open the line, not a PDF page guess.”*  
**Why-recommend:** Matches the only gap the giants left; HN already asked for chat-with-a-book ([39719547](https://news.ycombinator.com/item?id=39719547)) and then settled on NotebookLM *because nothing else was a product*.  
**Why-not:** If Teach and FSRS stay thin, this sentence is a lie and users will bounce to NotebookLM + Anki in an afternoon.

### Do not compete on Audio Overviews or RSS

**Recommend:** Skip podcast generation and YouTube ingestion for the public-launch RFC.  
**Why-recommend:** Google productized a new format with Gemini + distribution ([notebooklm.google](https://notebooklm.google/)); Readwise owns capture. Cycles spent here are zero-sum.  
**Why-not:** Commuters are a real audience ([HN 43848794](https://news.ycombinator.com/item?id=43848794)); omitting *all* audio makes Learny desk-only. Mitigate with **chapter/answer TTS**, not two-host shows.

### Make citations tactile before adding intelligence

**Recommend:** Treat click-to-anchor + quote preview as a launch blocker, same severity as auth.  
**Why-recommend:** It is the feature NotebookLM users name when they explain trust ([chat help](https://support.google.com/notebooklm/answer/16179559); [Reddit synthesis](https://www.aitooldiscovery.com/guides/notebooklm-reddit)). Learny’s corpus already has anchors.  
**Why-not:** Over-investing in citation chrome without fixing generation 400s still feels untrustworthy (brief).

### Steal Khanmigo’s negative lesson for Teach

**Recommend:** Teach must be *woven*: e.g. after a chapter, a short Socratic pass is the default next step, or review cards are generated from the section just read — not a dormant dock tab.  
**Why-recommend:** Optional AI tutors go unused ([Chalkbeat](https://www.chalkbeat.org/2026/08/25/ai-tutoring-students-khanmigo-khan-academy-engagement-study/)). Claude/ChatGPT already offer Socratic *chat* ([Anthropic](https://www.anthropic.com/news/introducing-claude-for-education); [OpenAI](https://openai.com/index/chatgpt-study-mode/)); Learny’s edge is *where* in the book.  
**Why-not:** Forced pedagogy can feel nanny-ish; keep a “just let me read” escape.

### Keep Anki as a citizen, not a rival

**Recommend:** Surface `.apkg` export in the review empty-state and after deck generation; document FSRS parity with Anki.  
**Why-recommend:** Power users refuse silos ([Reddit consensus via StudyCardsAI](https://studycardsai.com/blog/5-best-ai-tools-for-active-recall-to-ace-your)); Learny already has genanki + stable GUIDs.  
**Why-not:** Making Anki the only good review path kills the in-app habit that public users need.

### Obsidian: ship the zip loudly; defer sync

**Recommend:** One-click vault download from Home/Notes with a sample screenshot of callouts + wikilinks.  
**Why-recommend:** PKM buyers compare you to Readwise’s plugin ([official docs](https://docs.readwise.io/readwise/docs/exporting-highlights/obsidian)); a hidden `GET /api/export/vault` does not count.  
**Why-not:** Building two-way sync fights ADR-0026 and Readwise on their home field.

### On-ramp vs Google’s free studio

**Recommend:** A public demo book (DRM-free) + capped real-provider Ask, and a landing that shows the four-step loop (upload → cited answer → teach/quiz → review).  
**Why-recommend:** Table-stakes acquisition against [notebooklm.google](https://notebooklm.google/) Standard.  
**Why-not:** Uncapped Claude on a public VPS is an RQ09 cost/abuse problem; do not copy Google’s free-compute economics.

---

## Cycle-sized moves

Small enough for one spec-driven PR each; ordered for public-launch leverage.

1. **Citation jump + quote hover** in Ask/Teach (NotebookLM-parity trust).  
2. **Generation failure UX:** keep the conversation, show a retry, never delete the thread on 400.  
3. **Deck honesty:** after quiz generation, show item count, sample card, and “nothing extractable” reason — kill the 0.02s empty success.  
4. **Landing + demo book:** screenshots of reader dock, one cited Q&A, one FSRS card; replace the bare tagline.  
5. **Uploader copy + PDF/EPUB chips** so ingest matches what NotebookLM users already expect.  
6. **Review UX:** Got it / Again mapped onto FSRS grades; “explain from source” opens the citation (steal NotebookLM Explain without dropping FSRS).  
7. **Export affordances:** “Download Obsidian vault” and “Download Anki deck” on Home and after first highlight/deck.  
8. **Chapter or answer TTS** (browser speech or one provider behind a port) — commute slice, not Audio Overview.  
9. **Teach default-on for a finished chapter** (one Socratic turn, skippable) so the tutor is woven in, per Khanmigo evidence.  
10. **Shelf-level Ask (optional cycle):** one conversation scoped to multiple ready sources — Recall/Ghostreader parity without RSS.  
11. **Responsive review + ask** (phone-usable due queue) before any native app.  
12. **Do-not-build list for RFC-004:** mind maps, Video Overviews, YouTube/RSS, auto knowledge graph, RemNote outliner, new provider SDKs.

---

## Sources (primary, repeated)

- Gemini Notebook: [notebooklm.google](https://notebooklm.google/), [plans](https://notebooklm.google/plans), [chat citations](https://support.google.com/notebooklm/answer/16179559), [flashcards](https://support.google.com/notebooklm/answer/16958963), [EPUB / quiz progress](https://workspaceupdates.googleblog.com/2026/03/new-ways-to-customize-and-interact-with-your-content-in-NotebookLM.html), [student features](https://blog.google/innovation-and-ai/models-and-research/google-labs/notebooklm-student-features/)
- Readwise: [readwise.io/read](https://readwise.io/read), [Ghostreader](https://docs.readwise.io/reader/docs/faqs/ghostreader), [Obsidian](https://docs.readwise.io/readwise/docs/exporting-highlights/obsidian)
- Recall: [recall.it/pricing](https://www.recall.it/pricing)
- RemNote: [spaced repetition](https://www.remnote.com/feature/spaced-repetition)
- Anki: [FSRS FAQ](https://faqs.ankiweb.net/what-spaced-repetition-algorithm.html)
- OpenAI Study Mode: [openai.com/index/chatgpt-study-mode](https://openai.com/index/chatgpt-study-mode/)
- Claude Education: [anthropic.com/news/introducing-claude-for-education](https://www.anthropic.com/news/introducing-claude-for-education)
- Khanmigo: [pricing](https://khanmigo.ai/pricing), [Chalkbeat 2026-08-25](https://www.chalkbeat.org/2026/08/25/ai-tutoring-students-khanmigo-khan-academy-engagement-study/)
- Shortform / Blinkist / Snipd / Otio: [shortform.com/pricing](https://www.shortform.com/pricing), [blinkist.com/pricing](https://www.blinkist.com/pricing), [snipd.com/pricing](https://www.snipd.com/pricing), [otio.ai/pricing](https://otio.ai/pricing)
