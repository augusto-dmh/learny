# NotebookLM (now Gemini Notebook) and Google's learning stack — competitor profile as of 2026-09-30

Scope note: NotebookLM was renamed **Gemini Notebook** on 2026-07-16; this file uses both names. Enterprise variant is "Gemini Notebook Enterprise" (formerly NotebookLM Enterprise). Reddit is blocked to the research crawler, so Reddit sentiment is reported second-hand only (see Gaps in Q6).

## Q1. What exactly does Gemini Notebook offer in Sept 2026, on which tiers, with which limits?

### Takeaway
Gemini Notebook is a source-grounded research/study workspace (chat with citations plus a "Studio" of generated artifacts: Audio/Video Overviews, Mind Maps, reports, slide decks, infographics, data tables, flashcards, quizzes, interactive learning overviews) with 30M+ users, EPUB support since March 2026, Play Books integration since Aug 2026, and, since 2026-09-02, compute-based usage budgets instead of fixed daily caps. Free tier: 50 sources/notebook, 100 notebooks; Plus/Pro/Ultra scale to 100/300/500–600 sources and 2x/4x/5–20x usage.

### Cited Findings

**Identity, scale, rebrand**
- On 2026-07-16 Josh Woodward (VP Google Labs, Gemini app & AI Studio) announced "NotebookLM is now Gemini Notebook", citing 30 million+ users and 600,000+ organizations, and shipping a "secure cloud computer" in every notebook for native code execution "grounded in your sources"; code execution went first to AI Ultra and Workspace AI Ultra/Expanded Access, then rolling to all Pro users on web. — [blog.google](https://blog.google/innovation-and-ai/products/gemini-notebook/notebooklm-gemini-notebook/); also [TechCrunch 2026-07-16](https://techcrunch.com/2026/07/16/google-continues-its-renaming-streak-by-turning-notebooklm-to-gemini-notebook/); [Workspace Updates](https://workspaceupdates.googleblog.com/2026/07/notebooklm-now-gemini-notebook.html)
- URL moved to notebook.google.com in late July / early August 2026 with automatic redirects; existing notebooks were preserved. — [notebooklm-guide changelog](https://notebooklm-guide.com/notebooklm-updates/); [Glasp 2026 guide](https://glasp.co/articles/notebooklm-2026)
- Wikipedia timeline: Project Tailwind (May 2023), Audio Overviews (Sept 2024), out of experimental (2024-10-17), NotebookLM Plus (Dec 2024), Plus to consumers via Google One AI Premium (2025-02-10), Video Overviews (2025), infographics and slide decks on Nano Banana Pro (Nov 2025), Data Tables (Dec 2025), rebrand + code execution (2026-07-16), Short Video Overviews (July 2026). — [Wikipedia](https://en.wikipedia.org/wiki/NotebookLM)

**Dated feature launches, Sept 2025 → Sept 2026** (changelog site cross-checked with Google primary posts where possible)
- 2025-09-08: student features — flashcards & quizzes (customizable topic/difficulty, "Explain" with citations), upgraded Reports (study guides, briefing docs, blog posts), **Learning Guide** conversational tutor mode ("probing, open-ended questions" instead of answers), OpenStax academic notebooks, Audio Overview formats Brief/Critique/Debate, educator assignment via Canvas/Schoology/Classroom. — [blog.google](https://blog.google/innovation-and-ai/models-and-research/google-labs/notebooklm-student-features/); [Chrome Unboxed 2025-09-09](https://chromeunboxed.com/massive-notebooklm-update-adds-ai-powered-flashcards-quizzes-and-a-personal-tutor-mode/)
- 2025-10-13: Video Overviews got six visual styles and a Brief format. 2025-10-29: chat context expanded to 1M tokens on all plans; custom goals/voices/roles for all; saved chat history. — [notebooklm-guide changelog](https://notebooklm-guide.com/notebooklm-updates/); [FelloAI](https://felloai.com/notebooklm-update-1m-token-chat-goals-saved-history/)
- 2025-11-13: **Deep Research** agent (builds a cited source list / multi-page report from the open web) plus Google Sheets, Word (.docx), Drive PDFs, images as sources. — [notebooklm-guide changelog](https://notebooklm-guide.com/notebooklm-updates/); [Glasp](https://glasp.co/articles/notebooklm-2026)
- 2025-12-18/19: Data Tables (exportable to Sheets); engine upgraded to Gemini 3. — [notebooklm-guide changelog](https://notebooklm-guide.com/notebooklm-updates/); [Glasp](https://glasp.co/articles/notebooklm-2026)
- 2026-01-27: Workspace users can add notebooks as sources inside Gemini conversations. 2026-02-05: "AI Expanded Access" Workspace add-on for higher limits. — [notebooklm-guide changelog](https://notebooklm-guide.com/notebooklm-updates/)
- 2026-03-04: Cinematic Video Overviews (English-first; Glasp says Ultra-only at launch; the Workspace post of 2026-03-20 lists Business Standard/Plus, Enterprise, AI Pro/Ultra). — [Glasp](https://glasp.co/articles/notebooklm-2026); [Workspace Updates 2026-03-20](https://workspaceupdates.googleblog.com/2026/03/new-ways-to-customize-and-interact-with-your-content-in-NotebookLM.html)
- 2026-03-10 (consumer coverage) / 2026-03-20 (Workspace post): **EPUB support for all users**, PPTX export, slide revisions, 10 infographic styles, flashcards/quizzes with progress saved across sessions, "Got it / Missed it", shuffle, rerun-missed screen, saved conversation history, artifact creation from chat. — [Workspace Updates](https://workspaceupdates.googleblog.com/2026/03/new-ways-to-customize-and-interact-with-your-content-in-NotebookLM.html); [gHacks 2026-03-10](https://www.ghacks.net/2026/03/10/google-adds-epub-support-to-notebooklm-making-it-more-useful-for-students/); [Phandroid 2026-03-10](https://phandroid.com/2026/03/10/you-can-now-drop-an-e-book-straight-into-notebooklm/)
- 2026-04-08: full notebooks workspace inside the Gemini app with cross-product sync. 2026-04-13: Education Plus / Teaching & Learning add-on customers get higher source and output limits. 2026-04-27: higher-ed students can create personal class notebooks from Classroom materials. — [notebooklm-guide changelog](https://notebooklm-guide.com/notebooklm-updates/)
- 2026-05-12: "Ask NotebookLM" step in Workspace Studio automations. 2026-05-26: Drive sources auto-sync; Schoology materials via Gemini LTI. — [notebooklm-guide changelog](https://notebooklm-guide.com/notebooklm-updates/)
- 2026-06-08: "agentic research" with the secure cloud computer (charts, spreadsheets); Glasp dates Gemini 3.5 becoming default the same day (FelloAI says Gemini 3.5 Flash in May 2026 — conflicting). — [notebooklm-guide changelog](https://notebooklm-guide.com/notebooklm-updates/); [Glasp](https://glasp.co/articles/notebooklm-2026); [FelloAI](https://felloai.com/notebooklm-update-1m-token-chat-goals-saved-history/)
- 2026-06-25: **Study notebooks** in the Gemini app (adaptive lessons, diagnostic quiz, progress dashboard), syncing sources with NotebookLM. — [blog.google](https://blog.google/innovation-and-ai/products/gemini-app/gemini-study-notebooks/)
- 2026-08-04: Classroom materials sync to Gemini Notebook expanded. 2026-08-07: Workspace Studio can auto-add sources via recurring workflows. 2026-08-17: full notebook copying. 2026-08-19: notebooks in AI Mode in Search across 180+ countries (Glasp: English, excludes EEA). — [notebooklm-guide changelog](https://notebooklm-guide.com/notebooklm-updates/); [Glasp](https://glasp.co/articles/notebooklm-2026)
- 2026-08-27: **"Expert Intelligence"**: purchased Google Play Books titles can be added as citable sources in Gemini Notebook; 100,000+ titles at launch from Bloomsbury, De Gruyter Brill, Johns Hopkins UP, Macmillan, O'Reilly, Penguin Random House; eligible titles are marked "Available for Gemini Notebook"; US residents get some free book access for a limited time; Google plans to extend to the Gemini app, AI Mode, third-party subscriptions, research reports, and textbooks. — [9to5Google 2026-08-27](https://9to5google.com/2026/08/27/gemini-notebook-play-books/); [Library Journal infoDOCKET](https://www.infodocket.com/2026/08/27/google-announces-launch-of-expert-intelligence-feature-for-gemini-notebook/); [Thurrott](https://www.thurrott.com/a-i/google-gemini-a-i/340803/google-brings-e-books-to-gemini-notebook)
- 2026-09-02: **compute-based usage limits** replace fixed daily caps (see Q4). — [9to5Google 2026-08-28](https://9to5google.com/2026/08/28/gemini-notebook-usage-limits/)
- 2026-09-15: real-time voice chat, mobile audio recorder, Interactive Learning Overviews, new quiz formats, Short Video Overviews in 80+ languages, student pricing (see Q4). — [blog.google](https://blog.google/innovation-and-ai/products/gemini-notebook/new-study-tools-september-2026/)
- Mind Maps launched 2025-03-19 (rollout to 15 days), customizable by prompt from 2025-05-05. — [9to5Google 2025-03-27](https://9to5google.com/2025/03/27/notebooklm-mind-map/); [Learn Prompting](https://learnprompting.org/blog/notebooklm-interactive-mind-maps)

**Source types and per-source limits (official help page, current)**
- Supported sources: audio files (MP3, WAV, others; transcribed at import), Google Docs, Sheets (100k-token limit), Slides (max 100 slides), Word, text, Markdown, PDF, CSV, PowerPoint, images (avif, bmp, gif, heic, heif, ico, jp2, jpeg, png, tiff, webp), **ePub**, **Play Books ebooks**, web URLs (text only; images/embedded video/nested pages not imported), public YouTube videos with captions (uploaded ≥72h ago), Gemini Chats, pasted text, Drive sources with auto-sync. — [Google Help: Add or discover new sources](https://support.google.com/notebooklm/answer/16215270?hl=en)
- Each source: up to 500,000 words or 200MB uploaded; free notebooks: up to 50 sources; higher tiers per the AI Plans page. Help UI available in 50+ languages. — [Google Help](https://support.google.com/notebooklm/answer/16215270?hl=en)
- Copy-protected (DRM) PDFs cannot be imported (third-party summary of limits). — [Sourclip](https://www.sourclip.com/blog/notebooklm-source-limits) (unverified against Google's page)

**Tier table (third-party compilations; Google's own AI Plans page gives multipliers, not counts)**
- Free: 100 notebooks, 50 sources/notebook, baseline usage. Plus ($4.99/mo): 200 notebooks, 100 sources, 2x. Pro ($19.99/mo): 500 notebooks, 300 sources, 4x, code execution. Ultra ($99.99/mo 20TB; $199.99/mo 30TB): 500/600 sources, 5x–20x Pro, code execution, voice chat first. — [Glasp](https://glasp.co/articles/notebooklm-2026); [FelloAI](https://felloai.com/notebooklm-update-1m-token-chat-goals-saved-history/); [aiproductivity.ai](https://aiproductivity.ai/pricing/notebooklm/)
- Older per-day counts (Pro 500 chats/day; Ultra 2,500–5,000) predate the 2026-09-02 compute model and should be treated as obsolete. — [FelloAI pricing](https://felloai.com/notebooklm-pricing/)
- Feature gating summary (per Glasp): Cinematic video, native code execution, and voice chat are gated to Pro/Ultra; shared notebooks don't appear in AI Mode. — [Glasp](https://glasp.co/articles/notebooklm-2026)

**Platforms**
- iOS and Android apps; browser extensions for Chrome, Safari, Firefox, Edge; notebooks sync with the Gemini app and AI Mode in Search. — [Glasp](https://glasp.co/articles/notebooklm-2026)
- Mobile app got flashcards, quizzes, temporary source selection on 2025-11-06. — [notebooklm-guide changelog](https://notebooklm-guide.com/notebooklm-updates/)

### Inferences
- Since March 2026 the "you can't upload an EPUB" gap that book-first apps could exploit is closed; since August 2026 Google additionally owns a licensed-book supply channel (Play Books) that a small app cannot replicate.
- The product's centre of gravity is artifact generation (podcasts, videos, slides, infographics) plus grounded chat. Every 2026 launch adds output formats or Google-ecosystem sync; none adds a reading surface.
- The compute-budget model (Q4) makes heavy per-book study sessions less predictable on the free tier than the old fixed daily counts.

### Gaps
- Google does not publish exact notebook/source counts per tier on a single official page I could fetch; tier counts above are from third-party compilations that agree with each other.
- Exact Cinematic Video tier gating at launch conflicts between sources (Ultra-only vs Pro+).
- Which Gemini model version currently powers the product (3.5 Flash vs 3.5) is inconsistently reported.

## Q2. Whole-book reading, persistent learner progress, spaced repetition, tutoring loop: what is missing for a "study home"?

### Takeaway
Gemini Notebook has no reader experience for a whole book, no cross-notebook learner model, and no spaced-repetition scheduler; its "progress" is per-deck flashcard state (since March 2026) and, in the separate Gemini-app "study notebooks" (June 2026), a per-goal skills dashboard with adaptive lessons. Tutoring exists as a per-chat "Learning Guide" style and (Sept 2026) live voice, not as a persistent loop across sessions.

### Cited Findings
- Flashcards/quizzes save progress across sessions, support "Got it"/"Missed it", shuffle, delete cards, and a results screen to rerun missed cards (2026-03-20). — [Workspace Updates](https://workspaceupdates.googleblog.com/2026/03/new-ways-to-customize-and-interact-with-your-content-in-NotebookLM.html)
- A student who used NotebookLM for a full semester concluded it lacks an automated, adaptive spaced-repetition scheduler; workarounds are manual Day 1/3/7/21 review schedules or external SRS tools. — [Medium: "I let NotebookLM manage my studies for a semester"](https://harsh-gautam.medium.com/i-let-googles-notebooklm-manage-my-studies-for-a-semester-here-are-the-results-ef4e70fa3fc5); [Medium: 5 NotebookLM hacks for retention](https://medium.com/@kombib/5-notebooklm-hacks-for-better-memory-retention-203acabd574a)
- Learning Guide (2025-09-08) is a conversational style that asks probing questions and breaks down problems step by step; coverage does not describe persistent tutoring state or stored progress. — [blog.google](https://blog.google/innovation-and-ai/models-and-research/google-labs/notebooklm-student-features/); [Chrome Unboxed](https://chromeunboxed.com/massive-notebooklm-update-adds-ai-powered-flashcards-quizzes-and-a-personal-tutor-mode/)
- Interactive Learning Overviews (2026-09-15, rolling out over weeks) organize material into sections with a table of contents and recommend mind maps/flashcards/quizzes per section; XDA (2026-09-28) says this fixed the "fragmented, stitch-your-own-study-session" problem, but the review does not describe citations inside overviews or any progress tracking. — [blog.google](https://blog.google/innovation-and-ai/products/gemini-notebook/new-study-tools-september-2026/); [XDA 2026-09-28](https://www.xda-developers.com/tested-notebooklms-new-interactive-learning-overviews-fixed-biggest-problem/)
- Gemini-app **study notebooks** (2026-06-25): diagnostic quiz sets a baseline; Gemini breaks a goal into 100+ learning objectives grouped into topics; dashboard labels "Strengths / Focus areas / Not started" update as quizzes are completed; bite-sized adaptive lessons; exam prep (SAT, JEE, NEET, ENEM, ACT, GRE); sources sync with NotebookLM for flashcards/Video Overviews. Rolled out globally on web for personal accounts 18+; school accounts and mobile "in the coming weeks / summer 2026". No spaced review or reminders mentioned. — [blog.google Gemini app](https://blog.google/innovation-and-ai/products/gemini-app/gemini-study-notebooks/); [blog.google Education ISTE 2026](https://blog.google/products-and-platforms/products/education/iste-students-2026/)
- Notebooks are isolated silos: no cross-notebook search, no connection mapping, no recent-activity feed, no task/follow-up layer. — [Glasp](https://glasp.co/articles/notebooklm-2026); [XDA 2026-02-17](https://www.xda-developers.com/notebooklm-limitations/)
- Citations open the source passage in a source viewer with the cited text highlighted (i.e., there is a text pane per source, not a reader). — [Learn Prompting guide](https://learnprompting.org/blog/notebooklm-guide); [Codecademy](https://www.codecademy.com/article/how-to-use-notebooklm)
- Play Books integration coverage does not state that the book text can be read inside Notebook; it describes asking questions and generating artifacts. — [Thurrott](https://www.thurrott.com/a-i/google-gemini-a-i/340803/google-brings-e-books-to-gemini-notebook)
- Sept 2026 voice chat: "talk through tough concepts in your notebooks" with step-by-step guidance; Ultra 18+ on mobile first. — [blog.google](https://blog.google/innovation-and-ai/products/gemini-notebook/new-study-tools-september-2026/)

### Inferences
- Structural gaps a "study home" could own: (1) a reading surface for a whole book with position/progress and structure-aware navigation; (2) a learner model that persists across books and sessions (Notebook's state is per-artifact; Gemini's study-notebook dashboard is per goal and lives in a different app); (3) scheduled long-term review (SRS); (4) a tutoring loop that remembers what was taught and what was missed; (5) cross-notebook/cross-book knowledge linking.
- Google's answer to "progress" is being built in the Gemini app (study notebooks), not in Notebook; the split across two products with different privacy models (see Q5) is itself a weakness for a single study home.
- Interactive Learning Overviews and study notebooks show Google is moving toward guided sequences, so the gap is narrowing on "structure a session" but not on "remember the learner over months".

### Gaps
- No primary source confirms or denies a reading-mode UI for EPUB/Play Books sources; I could not test the product.
- Whether study notebooks now support school accounts and mobile (promised for "summer 2026") is unverified as of 2026-09-30.

## Q3. How good are the citations, and what do critics say about faithfulness?

### Takeaway
Citations are inline numbered markers that click through to the exact highlighted passage in the source, which is strong for verification, but they lack page/paragraph references usable in formal work and the model still hallucinates or leaks general knowledge; the Audio/Video artifacts carry no citations at all.

### Cited Findings
- Every response includes inline numbered citations; clicking one opens the original passage in the source with the cited text highlighted; citations are direct quotes intended for checking accuracy. — [Learn Prompting](https://learnprompting.org/blog/notebooklm-guide); [Codecademy](https://www.codecademy.com/article/how-to-use-notebooklm)
- Flashcards and quizzes have an "Explain" option with citations back to sources (2025-09-08). — [blog.google](https://blog.google/innovation-and-ai/models-and-research/google-labs/notebooklm-student-features/)
- XDA (2026-02-17): citations "lack page numbers or paragraph references needed for formal papers", there is no export that preserves citations as links, and copying responses loses them. — [XDA](https://www.xda-developers.com/notebooklm-limitations/)
- XDA on Audio Overviews: they "sound so human, you'll believe the misinformation"; the podcast format has no citations and can propagate errors from sources. — [XDA](https://www.xda-developers.com/notebooklm-audio-overviews-sound-human-believe-misinformation/)
- Peer-reviewed/preprint critique: Reuter, Philippone, Benton & Dilley (arXiv 2505.01955, May 2025) argue NotebookLM "presently poses clinical and technological risks" for patient-education podcasts and literature synthesis (qualitative evidence). — [arXiv](https://arxiv.org/abs/2505.01955)
- HN, July 2026 rebrand thread: one user says it excels at "not hallucinating compared to claude and chatgpt"; others report hallucination complaints are common on the subreddit ("there's a lot of these in their sub") and that backend changes after the rebrand increased hallucinations. — [Hacker News](https://news.ycombinator.com/item?id=48936451)
- A September 2026 practitioner write-up warns against "treating citations as proof". — [blog.mean.ceo](https://blog.mean.ceo/notebooklm-news-september-2026/)

### Inferences
- Passage-level click-through is at parity with or better than what a small app can offer in raw verifiability; the exploitable difference is *stable, structure-aware anchors* (chapter/section/location) that survive export and can be cited in prose, which Notebook lacks.
- Faithfulness criticism concentrates on generated artifacts (audio/video/reports), not on the grounded chat; a book-first app that keeps every teaching output citation-bound differentiates on exactly that surface.

### Gaps
- I found no quantitative 2026 benchmark of NotebookLM citation precision/recall. A search summary mentioned a study in which NotebookLM invented "muddy financial institutions and canoe docking facilities" and admitted using "general knowledge", but I could not locate and verify the primary source (possibly a Zenodo record 18043672); treat as unverified.
- Reddit threads could not be fetched directly (crawler blocked).

## Q4. What has Google shipped or announced since 2026-09-03?

### Takeaway
Two Notebook releases fall in the window: the compute-based usage limits that took effect 2026-09-02 (announced 08-28), and the 2026-09-15 "study tools" release (real-time voice chat, mobile audio recorder, Interactive Learning Overviews, new quiz formats, Short Video Overviews in 80+ languages, free AI Plus/Pro year for students). Interactive Learning Overviews were still rolling out as of 2026-09-28.

### Cited Findings
- 2026-09-02 (announced 08-28): usage limits refresh every five hours up to a weekly ceiling and are computed from prompt complexity, chat length, number of sources, and features used; Free = standard, Plus = 2x, Pro = 4x, Ultra = 5x or 20x Pro; status indicators, an expected-cost bar under Studio generations, alternative-output suggestions, and a "Generate later" option that defers Video Overviews/slide decks until the limit resets. — [9to5Google](https://9to5google.com/2026/08/28/gemini-notebook-usage-limits/); [Android Police](https://www.androidpolice.com/gemini-notebook-ditching-daily-limits-more-complicated/)
- 2026-09-15 (Trond Wuellner, Director of PM, Gemini Notebook): (1) real-time voice conversations in nearly 100 languages on Android/iOS, grounded in sources, Ultra 18+ first, Pro "soon"; (2) audio recorder for lectures/thoughts on mobile, notes stored beside sources, all ages, English output required; (3) Interactive Learning Overviews under Reports combining summaries, infographics, quizzes, flashcards, all users over the next few weeks; (4) quiz formats: short answer, multiple select, fill-in-the-blank; (5) Short (~60s) Video Overviews in 80+ languages; (6) US college students get 1 year of AI Pro free and students in 140+ other markets get 1 year of AI Plus free, redeem by 2026-12-31 (excludes US, Bolivia, Albania, Canada, Macau, Hong Kong, Tunisia for the Plus offer). — [blog.google](https://blog.google/innovation-and-ai/products/gemini-notebook/new-study-tools-september-2026/); [Android Authority](https://www.androidauthority.com/gemini-notebook-new-features-september-2026-3711726/)
- 2026-09-28 review of Interactive Learning Overviews (sections + table of contents + per-section recommended Studio tools). — [XDA](https://www.xda-developers.com/tested-notebooklms-new-interactive-learning-overviews-fixed-biggest-problem/)
- Just before the window: 2026-08-27 Expert Intelligence / Play Books sources (Q1); 2026-08-19 notebooks in AI Mode in Search (Q1).
- Also in the window but adjacent: Googlebooks (Android/Gemini laptops) preorders, in stores 2026-10-04 from $899, bundling 12 months of Google AI Pro; no Brazil pricing/date announced. — [NC News 2026-09-21](https://ncnews.com.br/2026/09/21/google-lanca-notebook-com-ia-gemini-para-disputar-mercado-com-macbook-preco-parte-de-us-899/); [Showmetech](https://www.showmetech.com.br/googlebooks-android-gemini-precos-modelos/)

### Inferences
- The September release targets exactly the student use case (lecture capture, guided study sequences, voice tutoring) and gives students a free paid year through end-2026, which raises the bar for any paid student-facing competitor during the 2026-27 academic year.
- Compute budgets shift the free tier from "N generations/day" to opaque quotas; Android Police calls it "more complicated", a possible irritation point for heavy studiers.

### Gaps
- No Gemini-app "Guided Learning" release note dated after 2026-09-03 was found; the changelog site had no September entries and the September news roundup listed none beyond the above.

## Q5. Pricing and availability (Brazil, Portuguese), privacy/training policy, API

### Takeaway
Brazil gets the same product with local pricing (Plus R$24,99, Pro R$96,99, Ultra from R$779,90) and a free Plus year for students; Portuguese (pt-BR/pt-PT) Audio/Video Overviews are native. Google states it does not train on Notebook data, with a feedback-triggered human-review exception on personal accounts that Workspace/Education accounts avoid. There is no consumer API; an Enterprise API exists in Preview.

### Cited Findings

**Pricing / Brazil**
- Google AI Plus R$ 24,99/mês; Google AI Pro R$ 96,99/mês; Google AI Ultra from R$ 779,90/mês, R$ 999,90 option with 20x higher limits; Plus/Pro described as "5x mais Resumos em Áudio, notebooks e outros benefícios"; "Estudantes: ganhe um plano Plus sem custo financeiro por um ano". — [gemini.google/br/subscriptions](https://gemini.google/br/subscriptions/?hl=pt-BR)
- US prices: Plus $4.99, Pro $19.99, Ultra $99.99/$199.99. — [Glasp](https://glasp.co/articles/notebooklm-2026)
- Brazilian tech press covered the rename (Tecnoblog) and the Gemini-app Notebooks rollout to free users (Canaltech). — [Tecnoblog](https://tecnoblog.net/noticias/google-muda-nome-do-notebooklm-para-gemini-notebook/); [Canaltech](https://canaltech.com.br/apps/gemini-ganha-um-dos-melhores-recursos-do-notebooklm/)

**Portuguese**
- Google's pt-BR blog announced Audio Overviews in Brazilian Portuguese (post exists; exact date not captured — see Gaps). — [blog.google pt-BR](https://blog.google/intl/pt-br/produtos/notebooklm-agora-oferece-resumos-em-audio-em-portugues-brasileiro/)
- Non-English Audio Overviews expanded to 80 languages on 2025-08-25; Short Video Overviews in 80+ languages (Sept 2026); voice chat in ~100 languages (Sept 2026); output-language selector lets users pick generated-text language. — [Glasp](https://glasp.co/articles/notebooklm-2026); [blog.google Sept 2026](https://blog.google/innovation-and-ai/products/gemini-notebook/new-study-tools-september-2026/); [Hashtag Treinamentos](https://www.hashtagtreinamentos.com/novidades-do-notebooklm-ia)
- Brazilian training sites state videos/podcasts are generated natively in PT-BR and PT-PT (not translated), 3–15 min, explainer/summary/debate formats. — [Zently](https://www.zently.com.br/blog/notebooklm-2026-guia-completo-pesquisa-produtividade) (third-party claim)
- ENEM practice tests ("Akira ENEM") for students in Brazil and Brazil's curriculum frameworks in the Classroom standards pilot. — [blog.google ISTE 2026](https://blog.google/products-and-platforms/products/education/iste-students-2026/); [EdTech Innovation Hub BETT 2026](https://www.edtechinnovationhub.com/news/bett-2026-google-announces-major-ai-updates-to-gemini-and-google-classroom)

**Privacy / training**
- Google: "Gemini Notebook does not use your data to train its AI models." Personal accounts: if you submit feedback, Google "may review the full context of that interaction, including your queries, uploads, and the model's responses" (retention up to 3 years). Workspace/Education accounts: uploads, chats, outputs "won't be reviewed by human reviewers or used to improve generative AI models". — [Google Help answer 17004255](https://support.google.com/notebooklm/answer/17004255) as summarized by [notebooklm-guide](https://notebooklm-guide.com/is-notebooklm-safe/); Workspace terms [support.google.com/a/answer/15239506](https://support.google.com/a/answer/15239506)
- Gemini Notebook is not listed as a HIPAA-covered service. — [notebooklm-guide](https://notebooklm-guide.com/is-notebooklm-safe/) citing [support.google.com/a/answer/1492253](https://support.google.com/a/answer/1492253)
- The Gemini-app Notebooks feature "splits the privacy model in ways that matter for professional users" (Gemini app vs Notebook data handling). — [Smith Stephen newsletter](https://www.smithstephen.com/p/googles-new-notebooks-feature-connects) (opinion)
- Legal: former NPR host David Greene sued over AI-voice reproduction in Audio Overviews (Feb 2026). — [Wikipedia](https://en.wikipedia.org/wiki/NotebookLM) citing Washington Post

**API**
- No self-serve consumer API. Gemini Notebook Enterprise APIs (Preview) cover notebook create/get/list/delete/share, sources, audio overviews, queries; require a Google Cloud project and Gemini Enterprise or Gemini Education Premium license; VPC-SC and CMEK supported. A standalone Podcast API is deprecated and not allowlisting new customers. — [Google Cloud docs: notebooks API](https://docs.cloud.google.com/gemini/enterprise/notebooklm-enterprise/docs/api-notebooks); [Overview](https://docs.cloud.google.com/gemini/enterprise/notebooklm-enterprise/docs/overview); [autocontentapi status post](https://autocontentapi.com/blog/does-notebooklm-have-an-api)
- Unofficial Python/CLI client `notebooklm-py` (updated 2026-09-30) reverse-engineers undocumented endpoints; HN users cite lack of an API as a reason to leave. — [GitHub teng-lin/notebooklm-py](https://github.com/teng-lin/notebooklm-py); [Hacker News](https://news.ycombinator.com/item?id=48936451)

**Education availability**
- Gemini in Classroom (30+ features) free for all Workspace for Education educators (ISTE 2025); BETT 2026 (Jan 2026) added Classroom-aware Gemini, Writing Coach with Khan Academy, SAT practice, audio/video feedback recording, standards tagging. — [blog.google Classroom AI](https://blog.google/products-and-platforms/products/education/classroom-ai-features/); [blog.google BETT 2026](https://blog.google/products-and-platforms/products/education/bett-2026-gemini-classroom-updates/)
- Education Plus / Teaching & Learning add-on customers received higher Notebook limits (2026-04-13); Classroom → Notebook sync for students (2026-04-27, 2026-08-04). — [notebooklm-guide changelog](https://notebooklm-guide.com/notebooklm-updates/)

### Inferences
- For a Brazilian learner, Google's free tier plus a free Plus year makes price a non-differentiator in 2026; differentiation must come from product shape (reading, progress, retention), not cost.
- Privacy is a neutral-to-strong point for Google on consumer accounts unless the learner submits feedback; a self-hosted/BYO-key app can only beat it on data locality, not on training policy.

### Gaps
- Exact date of the pt-BR Audio Overviews post not captured (Portuguese was in the April 2025 50-language expansion per my recollection, unverified).
- Could not fetch Google's own help page 17004255 directly; wording is via a secondary that quotes it.
- Whether Gemini Notebook Enterprise / Gemini Education Premium are sold in Brazil was not verified.

## Q6. What do power-user students actually do with it, and where do they complain?

### Takeaway
Typical workflows: upload course PDFs/slides/lecture audio → Audio Overview on commute → flashcards/quizzes → Learning Guide tutoring → study guide reports; since Sept 2026, record lectures in-app and use Interactive Learning Overviews. Complaints cluster on export/lock-in, siloed notebooks, missing page-level citations, opaque usage limits, hallucinations in generated artifacts, no API, and podcast-format annoyances.

### Cited Findings
- Google's six student workflows (2025-09-08): flashcards/quizzes, reports/study guides, Learning Guide tutoring, OpenStax notebooks, Audio Overview formats, teacher-assigned notebooks via Canvas/Schoology/Classroom. — [blog.google](https://blog.google/innovation-and-ai/models-and-research/google-labs/notebooklm-student-features/)
- Teacher-focused 2026 features: Classroom → Notebook creation from Classwork, Google Classroom integration, transparent reasoning shown before answers. — [chrmbook.com](https://www.chrmbook.com/notebooklm-advanced-features-teachers/); [Teachercast April 2026](https://teachercast.net/edtech/google-notebook-lm-updates-april-2026/)
- XDA "5 basic things" (2026-02-17): no export preserving citations; no cross-notebook linking; no task/follow-up layer; citations lack page/paragraph refs; no global search/rediscovery so old notebooks get abandoned. — [XDA](https://www.xda-developers.com/notebooklm-limitations/)
- HN (July 2026): "too much friction… several minutes to make a podcast, and they disappear after a while"; podcast interrupt feature "super-janky"; no API; can't ingest code repos; fear of Google killing/renaming the product; some report more hallucinations after backend changes. Praise: comprehending corpora too large to read; codebase understanding on commutes. — [Hacker News](https://news.ycombinator.com/item?id=48936451); [earlier HN thread](https://news.ycombinator.com/item?id=42954025)
- Android Police on Sept 2026 limits: "ditching its simple daily limits for a more complicated model". — [Android Police](https://www.androidpolice.com/gemini-notebook-ditching-daily-limits-more-complicated/)
- Semester-long student review: excellent for structure and synthesis across media types, weak for long-term retention without external SRS. — [Medium](https://harsh-gautam.medium.com/i-let-googles-notebooklm-manage-my-studies-for-a-semester-here-are-the-results-ef4e70fa3fc5)
- Reddit (second-hand via search summaries): routine reliability complaints; one user documented confident wrong answers about their own company data corrected only after manual source checks. — search-summary only, primary Reddit page not fetchable; see Gaps
- Kindle/DRM friction: users convert Kindle books via OCR or DRM removal to get them into Notebook; EPUB works when unprotected. — [textmuncher](https://textmuncher.com/blog/kindle-books-notebooklm)

### Inferences
- The recurring complaint pattern (siloed notebooks, no memory across projects, no export with anchors, no long-term review) maps directly to a "home for autonomous study" positioning: persistent structure, durable anchors, and retention scheduling.
- Product-longevity anxiety ("killedbygoogle") is a real, if soft, switching motivator among power users.

### Gaps
- Reddit r/notebooklm could not be crawled (403 for the research tool); all Reddit sentiment is second-hand. Product Hunt and YouTube reviewer breakdowns were not reached within the call budget.

## Q7. Gemini Guided Learning / LearnLM, Gemini for Education, Classroom AI, Illuminate: claims and evidence

### Takeaway
Guided Learning (Gemini app, launched 2025-08-06, free) is Google's Socratic "study mode", powered by LearnLM, and it is the only Google learning feature with RCT evidence: a preregistered Sierra Leone trial (N=1,763, 8 weeks) reported +0.258 SD ITT in math (2026-06-09). LearnLM is now folded into Gemini rather than a separately shipped model; Illuminate's 2026 status could not be verified.

### Cited Findings
- Guided Learning announced 2025-08-06: "a personal learning companion" using probing questions and step-by-step breakdowns, multimodal (images, diagrams, videos, quizzes), powered by LearnLM ("a family of models fine-tuned for learning"), shareable by teachers via a Classroom link; no efficacy study cited at launch. — [blog.google](https://blog.google/products-and-platforms/products/education/guided-learning/); [blog.google Gemini](https://blog.google/products-and-platforms/products/gemini/guided-learning-google-gemini/)
- Guided Learning is free in the Gemini app; 2026 coverage says it rolled out wider with more visuals/YouTube video integration. — [Tech & Learning](https://www.techlearning.com/how-to/geminis-guided-learning-mode-from-google-ai-what-educators-need-to-know); [tamzidulhaque.com](https://tamzidulhaque.com/google-gemini-guided-learning-2026/) (secondary)
- LearnLM research lineage: "LearnLM: Improving Gemini for Learning" (arXiv 2412.16429, Dec 2024) and "Evaluating Gemini in an arena for learning" (arXiv 2505.24477, May 2025); Google publishes a LearnLM prompt guide. — [Pith review of 2412.16429](https://pith.science/paper/2412.16429); [arXiv 2505.24477](https://arxiv.org/pdf/2505.24477); [LearnLM prompt guide PDF](https://services.google.com/fh/files/misc/learnlm_prompt_guide.pdf)
- Sierra Leone RCT (DeepMind blog 2026-06-09; report PDF "learnLM_sierraleone_may26"): 1,763 junior-secondary students, 48 math classrooms, 12 schools, Port Loko District, 8 weeks, ~12 hours target; ITT +0.258 SD (p=0.029) ≈ 1.2–1.7 years of typical progress; TOT +0.380 SD (69% met the 12-hour target); stronger-baseline students benefited most; future preregistered RCTs planned globally. — [DeepMind blog](https://deepmind.google/blog/measuring-the-impact-of-learning-with-ai-in-sierra-leone-and-beyond/); [Technical report PDF](https://storage.googleapis.com/deepmind-media/LearnLM/learnLM_sierraleone_may26.pdf); [arXiv 2607.08849](https://arxiv.org/pdf/2607.08849); [blog.google](https://blog.google/products-and-platforms/products/education/measuring-the-impact-of-ai-on-teaching-and-learning/)
- Gemini for Education / Classroom: Gemini in Classroom free for Workspace for Education educators; BETT 2026 added Classroom-context Gemini, Khan Academy Writing Coach, SAT practice, recording tools, standards tagging (pilot includes Brazil); ISTE June 2026 added study notebooks assignable by teachers with insight reports, GRE/ACT practice tests (Princeton Review), Akira ENEM for Brazil, Read Along. — [blog.google BETT 2026](https://blog.google/products-and-platforms/products/education/bett-2026-gemini-classroom-updates/); [blog.google ISTE students 2026](https://blog.google/products-and-platforms/products/education/iste-students-2026/); [blog.google ISTE educators 2026](https://blog.google/products-and-platforms/products/education/iste-2026-educator-updates/); [EdTech Innovation Hub](https://www.edtechinnovationhub.com/news/hvigc521raw9i9d8seefh1gzbgiv0n)
- Google's "study mode" equivalents: Guided Learning (Gemini app), Learning Guide (Notebook, Sept 2025), study notebooks (Gemini app, June 2026), Interactive Learning Overviews and voice tutoring (Notebook, Sept 2026). — sources above

### Inferences
- Google's evidence base is for Socratic tutoring in a classroom-integrated math setting, not for self-directed book study; nothing published tests Notebook's flashcards/quizzes or study notebooks for retention.
- LearnLM appears to be a training/fine-tuning program inside Gemini rather than a product a competitor must match by name; the "learning science" claim is now backed by one RCT, which competitors should expect Google to cite heavily.

### Gaps
- Illuminate (illuminate.google.com, the Labs paper-to-audio experiment): searches returned nothing dated 2026; status unverified, likely superseded by Audio Overviews.
- The Google Cloud LearnLM page was truncated; whether LearnLM is exposed on Vertex/Gemini API as a selectable model in 2026 is unverified.
- No independent replication of the Sierra Leone result; the arena paper's "outperforms other models on learning-science principles" is Google-run evaluation.
