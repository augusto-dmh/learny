# Competitive landscape of AI-assisted self-study tools (excluding Google), as of 2026-09-30

Scope note: NotebookLM / Gemini / LearnLM are covered by another researcher; they appear here only as one-line comparators. Brazil market is covered by another researcher; BRL prices are noted only where they surfaced. Every claim is dated where the source dates it. "Secondary" marks aggregator/review-site sources; "unverified" marks claims I could not confirm against a primary source. Star counts and release dates for GitHub repos were pulled live via the GitHub API on 2026-09-30.

## Key question 0: Structured competitor map, product by product (groups a–d)

### Takeaway
Across ~40 products, only a handful ingest whole books and let you read, ask and be taught in one place (Kindle "Ask this Book", Readwise Reader, and indie open-source readers such as ReadAny, BookWith, Lantern and reader3). The purpose-built study apps (Turbo AI, Knowt, StudyFetch, Mindgrasp, Quizlet) own the flashcard/quiz loop but do not host a reader or cite passages, while the general assistants (ChatGPT, Claude, Perplexity, Copilot) own the Socratic "study mode" but treat books as ad-hoc uploads with no structure and no durable learning loop.

### Cited Findings

#### Group (a): general assistants' study modes

**ChatGPT Study Mode / ChatGPT Edu (OpenAI)**
- What it is: a mode that "helps you work through problems step by step instead of just getting an answer", launched 2025-07-29 for Free, Plus, Pro and Team users — [OpenAI, Introducing study mode](https://openai.com/index/chatgpt-study-mode/); [TechCrunch 2025-07-29](https://techcrunch.com/2025/07/29/openai-launches-study-mode-in-chatgpt)
- Expanded to ChatGPT Edu on 2025-08-06 and Enterprise on 2025-08-14; works "with PDFs and images you upload from your coursework"; uses memory when enabled; OpenAI acknowledges it "can make mistakes" and may sometimes give direct answers anyway (secondary) — [Appscribed](https://appscribed.com/chatgpt-study-mode/)
- 2026 changes (secondary; the OpenAI help-center release-notes page returned HTTP 403 to me, so these are unverified against the primary): 2026-08-14 release added "interactive quizzes" and project memory to studying; 2026-08-18 "ChatGPT for Teens" launched with Study Mode, automatic minor routing and opt-in parental controls — [ExplainX (Aug 2026)](https://explainx.ai/blog/chatgpt-for-teens-safety-study-mode-august-2026); [OpenAI release notes (403, not fetched)](https://help.openai.com/en/articles/6825453-chatgpt-release-notes)
- Source ingestion: per-chat file uploads (PDF, images); no book library, no EPUB reader, no preserved structure. Citations: none to uploaded passages beyond model-generated references (my inference from the feature description; no source documents passage-level citations).
- ChatGPT Edu pricing is not published; USC's provost said its ChatGPT Edu subscription costs $3.1 million per year (2026-01-22) — [Daily Trojan](https://dailytrojan.com/2026/01/22/uscs-chatgpt-edu-subscription-costs-3-1-million-per-year-provost-says/); UC Davis's renewed agreement is $144/year per user — [UC Davis IET](https://iet.ucdavis.edu/technews/new-chatgpt-edu-agreement-offers-expanded-features-lower-cost-new-terms); Stanford publishes a rate page — [Stanford UIT](https://uit.stanford.edu/rates/openai-chatgpt-edu)
- Brazil pricing (BRL, localized billing): ChatGPT Go R$39,99/month, Plus R$99,99/month, Pro R$999,90/month (secondary) — [gptprompts.ai pt-BR](https://gptprompts.ai/pt-br/precos-chatgpt); Plus localized to R$99,99 "10% cheaper" after switch to BRL billing — [Canaltech](https://canaltech.com.br/apps/chatgpt-plus-fica-mais-barato-no-brasil-com-nova-cobranca-em-real/)

**Claude "Learning mode" / Claude for Education (Anthropic)**
- Claude for Education launched 2025-04-02 as a university tier with Learning mode — [TechCrunch 2025-04-02](https://techcrunch.com/2025/04/02/anthropic-launches-an-ai-chatbot-tier-for-colleges-and-universities)
- Learning mode extended to all Claude.ai users on 2025-08-14 as a "Learning" option in the style dropdown, plus Learning and Explanatory modes in Claude Code — [Engadget](https://www.engadget.com/ai/anthropic-brings-claudes-learning-mode-to-regular-users-and-devs-170018471.html); [Dataconomy 2025-08-15](https://dataconomy.com/2025/08/15/anthropic-extends-claudes-learning-mode-to-all-users/)
- Official education page (fetched 2026-09-30): learning mode "asks questions that help you find the answers yourself"; partner logos: University of San Francisco, LSE, Northeastern, Champlain, Northumbria, Syracuse, Dartmouth, University of Virginia, University of Pittsburgh; no public pricing; no passage-citation feature described — [claude.com/solutions/education](https://claude.com/solutions/education)
- Pricing: Pro $20/month or $17/month annual; Brazil is billed in USD plus IOF (no BRL localized price), effective cost reported around R$129,9/month (secondary) — [SSD Nodes](https://www.ssdnodes.com/learn/claude-pro-in-brazil-what-you-pay); [eupresa.ia.br](https://eupresa.ia.br/blog/chatgpt-plus-vs-claude-pro-vs-gemini-preco/); India got localized INR pricing in July 2026 while Brazil did not (secondary, unverified) — [Fazm](https://fazm.ai/blog/anthropic-claude-regional-pricing-differences)
- Source ingestion: chat/Project file uploads; no book library, no reader, no spaced review.

**Perplexity (Study Mode, Spaces, Pages, Comet)**
- Study Mode was teased 2025-08-05 ("Get ready for September"), launched for students on 2025-09-05, and opened to everyone with the 2025-10-03 changelog; it "explains the underlying concept in detail, breaking it down step-by-step" and generates "interactive flashcards and quizzes" — [Perplexity changelog 2025-09-05](https://www.perplexity.ai/changelog/what-we-shipped-september-5th) (403 on fetch; content from search snippet); [Perplexity changelog 2025-10-03](https://www.perplexity.ai/changelog/what-we-shipped-october-3rd); [TestingCatalog on X](https://x.com/testingcatalog/status/1952772810528460896?lang=en)
- Comet browser has "built-in flashcards and quizzes" generated from pages you are reading; Comet became available to everyone on 2025-10-03 (secondary for the flashcard claim) — [aitoolsofficial](https://aitoolsofficial.com/ai-tools/perplexity-comet/); [Perplexity changelog 2025-10-03](https://www.perplexity.ai/changelog/what-we-shipped-october-3rd)
- Pricing: Pro $20/month or $200/year; verified students $10/month; Brazil pays USD (≈R$108/month converted) — [horadecodar (pt-BR, secondary)](https://horadecodar.com.br/perplexity-pro-vs-gratis/); [descontosparaestudantes (pt-BR)](https://descontosparaestudantes.com.br/descontos/perplexity-pro-education-br); [suprmind pricing hub (secondary)](https://suprmind.ai/hub/perplexity/pricing/)
- Citations: web-search citations are Perplexity's core; Spaces allow file uploads. I found no source documenting passage-level citations into uploaded books.

**Microsoft Copilot "Study and Learn" agent**
- Generally available 2026-05-13 inside Microsoft 365 Copilot for all education customers "at no additional cost"; students 13+; "Copilot Chat is off by default for students" in K-12 tenants; "optimized and available today in English (United States)" with more languages "in the coming weeks"; principle: "the learner does the thinking"; activities include flashcards, fill-in-the-blanks, quizzes, matching — [Microsoft Education Blog 2026-05-13](https://www.microsoft.com/en-us/education/blog/2026/05/study-and-learn-ai-built-for-your-student/)
- August 2026 back-to-school update added a carousel of web-safe images inside Study and Learn conversations — [Microsoft Tech Community, Aug 2026](https://techcommunity.microsoft.com/blog/educationblog/whats-new-in-microsoft-edu---back-to-school-august-2026/4516292)
- The announcement does not specify accepted content sources (files, PDFs, class materials) — [Microsoft Education Blog](https://www.microsoft.com/en-us/education/blog/2026/05/study-and-learn-ai-built-for-your-student/)
- Positioned as "Understand, Practice, Study" modes by third parties (secondary) — [Windows Forum](https://windowsforum.com/threads/microsoft-copilot-study-and-learn-mode-a-classroom-ready-ai-tutor.378571/)

**Mistral Le Chat (renamed Vibe)**
- "In May 2026, Mistral AI announced the rebrand from Le Chat to Mistral Vibe"; Pro tier $14.99/month introduced Feb 2025 — [Wikipedia: Le Chat (AI)](https://en.wikipedia.org/wiki/Le_Chat_(AI))
- Student/education plan €5.99/month (60% off) for 12 months, verified higher-ed students (secondary) — [aistudentdiscount](https://aistudentdiscount.com/le-chat-student/)
- No study mode, no reader, no spaced review found in any source.

**xAI Grok**
- No education tier equivalent to ChatGPT Edu; "xAI has not shipped an education tier ... with FERPA-aware agreements and age-appropriate guardrails"; Grok is "weaker as a citation source" (secondary) — [Layer3 Labs](https://www.layer3labs.io/guides/grok-4-5-for-education)
- US students get 2 months of SuperGrok free with a .edu email, then $30/month (secondary) — [krater.ai](https://krater.ai/blog/grok-student-discount)
- xAI–El Salvador partnership: Grok to be deployed across 5,000+ public schools to over one million students over two years — [x.ai news](https://x.ai/news/el-salvador-partnership)

**Comparator (one line):** Google shipped new Gemini Notebook study tools (real-time voice with notebooks, lecture audio recorder, interactive learning overviews) in mid-September 2026 — [Google blog, Sept 2026](https://blog.google/innovation-and-ai/products/gemini-notebook/new-study-tools-september-2026/); details are the other researcher's scope.

#### Group (b): purpose-built AI study apps

**Khanmigo (Khan Academy)**
- Learners/parents $4/month or $44/year; teachers free in US and select regions; district "Enterprise Starter" from $10/student/year (secondary) — [SelectHub](https://www.selecthub.com/p/chatbot-software/khanmigo/); [aitoolsbakery May 2026](https://aitoolsbakery.com/blog/khanmigo-updates-2026/)
- Source ingestion: none of your own books; tied to Khan Academy content. No EPUB, no citations to user material.

**Turbo AI (formerly TurboLearn)**
- Product renamed (turbolearn.ai/pricing now 301-redirects to turbo.ai, whose /pricing returned 404 on 2026-09-30); accepts PDFs, .docx, YouTube, audio/lecture recordings; outputs notes, flashcards, quizzes, podcasts; claims "over 10 million learners"; "generous free tier ... upgrade to unlock unlimited" — [turbo.ai](https://www.turbo.ai/)
- Paid price is conflicting across secondary sources: $20/month or $120/year — [toolradar](https://toolradar.com/tools/turbolearn/pricing); vs $9/month annual or $17.99 monthly — [mindomax](https://www.mindomax.com/turbolearn-alternatives). Unverified.
- Complaints: transcription "hallucinated languages speakers never spoke, merged speakers into one, and introduced errors that then filtered into the notes, flashcards, and quizzes" — [tl;dv](https://tldv.io/blog/turbo-ai/); a Reddit user quoted: "Speaking from experience with calculus, turbolearn is pretty terrible tbh" — [AI Tutor blog](https://ai-tutor.ai/blog/best-turbolearn-ai-alternatives/)
- No EPUB, no reader, no passage citations found.

**Knowt**
- Free plan: unlimited flashcard sets and notes; "use every study mode on your own sets including Learn, Practice Test, Spaced Repetition, Match and Flashcards" — [Knowt help center](https://help.knowt.com/en/articles/16905163-what-s-included-in-the-free-plan-for-students)
- Ultra $149.99/year or $24.99/month; adds ad-free, unlimited AI PDF/video/image/PowerPoint summarizer, lecture recording summarizer, AI podcast, AI voice tutor — [knowt.com/plans](https://knowt.com/plans)
- Complaints (Trustpilot): pop-up video ads "every 10 seconds", ads covering submit buttons; a paying user reported quizzes blocked behind further upsells — [Trustpilot knowt.io](https://se.trustpilot.com/review/knowt.io)
- School bulk pricing is FERPA/COPPA-compliant — [knowt.com/schools](https://knowt.com/schools/bulk-pricing)

**StudyFetch (Spark.E tutor)**
- Free; Base $7.99/month ($4.99 annual); Premium $11.99/month ($7.99 annual) (secondary) — [Dupple](https://dupple.com/reviews/study-fetch)
- Spark.E tutor is reachable by iMessage text and by voice call — [StudyFetch: Text Spark.E](https://www.studyfetch.com/features/text-sparke); [Call Spark.E](https://www.studyfetch.com/features/call-sparke)
- "The most common complaint across review platforms is StudyFetch's auto-renewal and cancellation process" — [Dupple](https://dupple.com/reviews/study-fetch)

**Mindgrasp**
- Uploads PDFs, lecture recordings, YouTube, audio, PowerPoint; outputs notes, summaries, flashcards, quizzes, Q&A; founded 2021 (secondary) — [Techshark](https://techshark.io/tools/mindgrasp-ai/)
- Pricing conflicts across secondary sources: Basic $5.99, Scholar $8.99 or $12.99, Premium $10.99/month; 4-day trial — [toolsforhumans](https://www.toolsforhumans.ai/ai-tools/mindgrasp-ai); [fahimai](https://www.fahimai.com/mindgrasp-ai). Unverified.

**Quizlet (Q-Chat, Magic Notes)**
- Q-Chat launched March 2023 on OpenAI's API as a Socratic tutor — [Wikipedia: Quizlet](https://en.wikipedia.org/wiki/Quizlet)
- Plus $7.99/month or $35.99/year; Plus Unlimited $44.99/year removes daily caps on practice tests and Q-Chat; Magic Notes turns uploaded notes into flashcards, tests, summaries (secondary) — [Nibble](https://nibble-app.com/blog/quizlet-cost); [thetoolsverse](https://thetoolsverse.com/tools/quizlet-ai-flashcards-study-games)

**Brainly**
- Plus $9.99/month or $39.99/year (unlimited AI Tutor, ad-free, Scan to Solve); Tutor $29/month or $96/year with up to 20 live expert sessions (secondary) — [fast.io Brainly review](https://fast.io/resources/brainly-ai-review-2026/)
- Positioning is homework Q&A, not book study.

**Chegg (post-AI collapse)**
- 2025-10-29: cut 388 jobs (~45%); Q2 revenue fell to $105.1M; explored a sale, chose to stay independent; Dan Rosensweig returned as CEO; pivot to B2B skills, language learning (Busuu) and AI — [Higher Ed Dive](https://www.highereddive.com/news/chegg-layoffs-strategic-alternatives-google-ai/804192/)
- Earlier May 2025 cut of 22% — [TechRadar](https://www.techradar.com/pro/chegg-announces-move-to-reduce-workforce-by-22-percent-as-students-turn-to-ai)
- A secondary tracker claims a February 2026 cut of ~1,600 jobs (80%) and a pivot to an "AI-powered platform"; it cites no primary source and the numbers conflict with a reported 595 headcount at end-2025 — treat as **unverified/likely wrong** — [aiexposure.org](https://www.aiexposure.org/analysis/company-ai-layoff-announcements-2026); [Founder Reports](https://founderreports.com/ai-layoffs-tracker/)
- Market cap ≈$110M as of July 2026 (secondary) — [Founder Reports](https://founderreports.com/ai-layoffs-tracker/)

**Coursera Coach**
- In-course AI tutor launched 2023; "over 34 million messages with more than 2.4 million learners" (2025-06-23) — [BusinessWire](https://www.businesswire.com/news/home/20250623615727/en/Coursera); [Coursera blog](https://blog.coursera.org/new-products-tools-and-features-2023/)
- Bound to Coursera course content; no own-book ingestion.

**Speechify (listening)**
- Premium $29/month or $139/year; Audiobooks $14.99/month separate; "unlimited PDF/ebook imports", OCR, AI summaries (secondary) — [Costbench](https://costbench.com/software/ai-voice-tools/speechify/)

**Recall (recall.it, formerly getrecall.ai)**
- getrecall.ai/pricing now 301-redirects to recall.it/pricing. Free: 10 AI summaries/month, unlimited saves, API and MCP access; Plus $10/month (annual); Max $38/month (annual); "Generate quizzes from saved content and review them on a schedule designed for long-term retention" (Plus/Max); content types: "articles, YouTube videos, podcasts, and PDFs"; 20% student discount; "700,000+ lifelong learners" — [recall.it/pricing](https://www.recall.it/pricing)
- No EPUB support listed.

**Mem**
- Free ≈25 notes/25 chats/25 PDF pages per month; Pro $12/month; "Proactive" ≈$99/month (secondary) — [Myflexnote](https://myflexnote.com/blog/best-ai-note-taking-apps)

**Heptabase**
- Pro $11.99/month ($8.99 annual, 100 AI credits/month), Premium $23.99 ($17.99 annual, 1,800 credits), Premium+ $71.99 ($53.99 annual, 8,100 credits); no free tier, 7-day trial (secondary) — [spotsaas](https://www.spotsaas.com/product/heptabase/pricing)
- "AI Tutor" agent for structured learning sessions (Premium and above); PDF "Parse" to control AI context; AI Agent upgrade 2026-08-14; ChatGPT plugin released 2026-09-23 — [Heptabase changelog 2026](https://wiki.heptabase.com/changelog/changelog); [Heptabase newsletter 2026-05-29](https://wiki.heptabase.com/newsletters/2026-05-29); [Heptabase Medium](https://medium.com/heptabase/the-best-way-to-use-ai-for-learning-762c3467bdf1)
- No EPUB support found; PDF only.

**Kortex**
- Free: 15 AI requests/month, 5 MB uploads, 5 GB storage; Kore $10/seat/month annual ($14 monthly); Premium $17.50/seat/month annual ($21 monthly) with 500 premium-model requests/month — [kortex.co/pricing](https://www.kortex.co/pricing)

#### Group (c): reading + notes + spaced repetition with AI

**Readwise Reader (closest incumbent to Learny's shape)**
- Pricing: Lite $5.59/month, Full $9.99/month (annual) or $12.99 monthly; Full includes Reader; 30-day trial; 50% student discount — [readwise.io/pricing](https://readwise.io/pricing)
- Reader Public Beta Update #14 (2026-08-06): "Global Ghostreader" chats across your whole library with "cited answers grounded across all saved content" and "links back to the referenced passages"; mobile Chat gives answers that "link directly to the cited text"; Readwise 2.0 mobile rebuild with redesigned Daily Review; MCP server exposing hybrid semantic+full-text search to Claude, ChatGPT, Perplexity and others; EPUB improvements (opens at story start, real print page numbers, chapter names on highlights); BYO OpenAI key for custom Ghostreader prompts ("GPT-5.6 family"); Mastery Cards bug fixes — [Readwise update Aug 2026](https://readwise.io/reader/update-aug2026)
- Citation reliability was explicitly fixed: highlighted passages "now always come from the cited source" (changelog) — [Readwise changelog](https://docs.readwise.io/changelog); [WiseUp vol. 83](https://wiseup.readwise.io/wiseup-vol-83-learn-to-summon-global-ghostreader-recover-your-streak-and-create-a-morning-reading-brief/)
- EPUB import "quietly separates Readwise Reader from most competitors" (secondary) — [speedreadinglounge](https://www.speedreadinglounge.com/readwise-reader-review)

**Anki (+ AI add-ons)**
- Stable 26.09.3 released 2026-09-23; desktop AGPL v3+, AnkiDroid GPL v3; FSRS built in since 23.10 (2023-10-31); "more than 1600 add-ons" — [Wikipedia: Anki (software)](https://en.wikipedia.org/wiki/Anki_(software)); GitHub ankitects/anki: 31,676 stars, release 26.09.3 on 2026-09-23 (GitHub API, 2026-09-30)
- "Anki AI" add-on (ChatGPT/LLM enhancement) last updated 2026-02-26; FSRS Helper updated 2026-05-14 (secondary listing) — [mindomax Anki add-ons](https://www.mindomax.com/best-anki-add-ons); [AnkiWeb add-ons](https://ankiweb.net/shared/addons)

**RemNote**
- Free (unlimited notes/cards, limited AI and PDFs); Pro $8/month annual (1,000 AI credits, PDF annotation); Pro with AI $18/month annual (20,000 credits, AI flashcards/quizzes/summaries from PDFs, AI grading) — [remnote.com/pricing](https://www.remnote.com/pricing)
- PDF, not EPUB.

**Obsidian: Copilot and Smart Connections**
- Copilot for Obsidian: open source, BYOK free ("works without a Copilot license when you use your own ... provider key, or local model"); Copilot Plus paid tier from Brevilabs — [Obsidian plugin page](https://community.obsidian.md/plugins/copilot); GitHub logancyang/obsidian-copilot: 7,773 stars, AGPL-3.0, pushed 2026-09-30 (GitHub API)
- Smart Connections: core free; Pro all-access $30/month or $299/year — [smartconnections.app pricing](https://smartconnections.app/pro-plugins/); GitHub brianpetro/obsidian-smart-connections: 5,476 stars, pushed 2026-09-24 (GitHub API)
- Third Mind Reader (Obsidian EPUB/PDF reader with chat): 109 stars, AGPL-3.0, created 2026-06-25, pushed 2026-09-28 (GitHub API) — [GitHub](https://github.com/Hipst3rMusic/obsidian-third-mind-reader)

**Kindle / Amazon (Recaps, Story So Far, Ask this Book)**
- "Ask this Book" unveiled Sept 2025 alongside "Story So Far"; rolled to the Kindle iOS app (US) in Dec 2025; enabled on "thousands of English-language best-selling Kindle books"; Android and Kindle devices expected by end of 2026 — [Android Central](https://www.androidcentral.com/tablets/kindle/amazons-kindle-app-gets-gen-ai-chatbot-to-ask-books-about-lore-and-characters); [The eBook Reader blog 2025-12-16](https://blog.the-ebook-reader.com/2025/12/16/new-ask-this-book-ai-feature-added-to-kindle-ios-app/); Story So Far reached Kindle devices June 2026 — [BGR](https://www.bgr.com/2192985/kindle-cool-new-feature-story-so-far-june/)
- Mechanics: highlight text, tap "Ask", get an explanation or ask a question; "All responses are generated from the book itself"; spoiler-aware to current location — [Kindlepreneur](https://kindlepreneur.com/amazon-ask-this-book/); [Gizmodo](https://gizmodo.com/kindle-ask-this-book-ai-2000699503)
- Authors Guild statement 2025-12-23 (updated 2026-01-07): "There is no way for publishers or authors to opt their books out"; concern that it "turns books into searchable, interactive products" without compensation — [Authors Guild](https://authorsguild.org/news/statement-on-amazon-kindle-ask-this-book-ai-feature/)
- Amazon told the Guild the feature does not train models or retain content (secondary) — [Android Central](https://www.androidcentral.com/tablets/kindle/amazons-kindle-app-gets-gen-ai-chatbot-to-ask-books-about-lore-and-characters)

**Matter, Omnivore's death and successors**
- Omnivore: team joined ElevenLabs (Oct 2024); hosted service switched off 2024-11-15 — [molodtsov.me](https://molodtsov.me/2024/10/omnivore-is-dead-where-to-go-next/); [yaps.ai](https://www.yaps.ai/blog/omnivore-alternative)
- Successors named: Readwise Reader ($9.99/mo, closest feature match), Matter (free tier + Premium, still on App Store 2026), Wallabag (self-hosted), Karakeep (secondary) — [Readless](https://www.readless.app/blog/omnivore-alternatives-2026); [burn451](https://www.burn451.cloud/blog/matter-app-alternative)
- Wallabag: 12,992 stars, MIT, pushed 2026-09-28; Karakeep: 29,368 stars, AGPL-3.0, v0.33.2 released 2026-08-11 (GitHub API, 2026-09-30)

**Zotero / Elicit / SciSpace (academic reading)**
- Zotero free and open source; storage from $20/year for 2 GB (secondary); GitHub zotero/zotero 15,445 stars, pushed 2026-09-30 (GitHub API) — [readwonders](https://readwonders.com/blog/student-discounts-ai-research-tools)
- Elicit: Basic free; Plus $19/month ($11 annual); Pro $69/month ($39 annual); industry Pro $75/$49 (secondary) — [fast.io Elicit review](https://fast.io/resources/elicit-ai-review-2026/)
- SciSpace: Premium $20/month ($12 annual, 1,200 credits); Advanced $90 ($70); Max $200 ($160) (secondary) — [academianote](https://www.academianote.site/en/scispace/)

**Khoj (open-source second brain)**
- Khoj Cloud sunset 2026-04-15; app.khoj.dev now shows "Service Deprecated"; self-hosting is the only supported path — [app.khoj.dev](https://app.khoj.dev/); [promptquorum](https://www.promptquorum.com/power-local-llm/khoj-ai-second-brain-review)
- GitHub: 37,548 stars, 2,498 forks, AGPL-3.0, latest release 2.0.0-beta.28 (2026-03-26), last push 2026-08-02 (GitHub API, 2026-09-30) — [GitHub khoj-ai/khoj](https://github.com/khoj-ai/khoj)
- Formats: PDF, Markdown, Notion, Word, org-mode, images; EPUB not listed — [GitHub khoj-ai/khoj](https://github.com/khoj-ai/khoj)

**Open WebUI / AnythingLLM / Karakeep**
- Open WebUI: 153,667 stars, v0.11.4 released 2026-09-21, license field "NOASSERTION" (custom license; exact terms unverified here) (GitHub API); supports EPUB among PDF, DOCX, TXT, MD, HTML, CSV (secondary) — [runaihome comparison](https://runaihome.com/blog/anythingllm-vs-open-webui-vs-librechat-2026/)
- AnythingLLM: 66,634 stars, MIT, v1.16.2 released 2026-09-22 (GitHub API); supports PDF, DOCX, TXT, MD, EPUB, HTML, CSV, JSON, websites, audio (secondary) — [aicoolies comparison](https://aicoolies.com/comparisons/anythingllm-vs-open-webui)
- Karakeep: bookmark/read-later manager, 29,368 stars, AGPL-3.0 (GitHub API); no EPUB/book study features found.

#### Group (d): open-source / indie "chat with your books" with traction (GitHub API, 2026-09-30)

| Repo | Stars | License | Created | Last push | Notes |
|---|---|---|---|---|---|
| karpathy/reader3 | 3,876 | none | — | 2025-11-18 | Self-hosted EPUB reader for "reading books together with LLMs"; unmaintained since Nov 2025 — [GitHub](https://github.com/karpathy/reader3) |
| iaflowacademy/reader3 (fork) | 0 | MIT | — | 2026-09-17 | Adds reading progress, highlights, AI chat — [GitHub](https://github.com/iaflowacademy/reader3) |
| codedogQBY/ReadAny | 2,687 | GPL-3.0 (per site) | 2026-02-25 | 2026-09-26 | Cross-platform reader; hybrid vector+BM25 RAG chat; local vector store; TTS; WebDAV sync — [GitHub](https://github.com/codedogQBY/ReadAny); [site](https://codedogqby.github.io/ReadAny/) |
| shutootaki/bookwith | 311 | AGPL-3.0 | 2025-02-20 | 2026-05-10 | Context-aware chat on current page/chapter, AI podcast, memory; Show HN 2025-08-06, 86 points / 61 comments — [HN](https://news.ycombinator.com/item?id=44811387) |
| KlaraGraff/lantern | 1 | MIT | 2026-07-12 | 2026-09-28 | "every answer clicks back to the line it came from"; knows CEFR level and reading position; local-first, BYO AI, MCP server; macOS/Windows — [GitHub](https://github.com/KlaraGraff/lantern) |
| Hipst3rMusic/obsidian-third-mind-reader | 109 | AGPL-3.0 | 2026-06-25 | 2026-09-28 | EPUB/PDF reader inside Obsidian with chat — [GitHub](https://github.com/Hipst3rMusic/obsidian-third-mind-reader) |
| onebirdrocks/ebook-mcp | 395 | Apache-2.0 | — | 2026-01-10 | MCP server exposing EPUB/PDF TOC and chapters to LLMs — [GitHub](https://github.com/onebirdrocks/ebook-mcp) |

- HN discussion of BookWith (2025-08-06): commenters asked for spoiler prevention tied to reading position, mobile sync, Docker install, Calibre integration and OCR; critics worried about AI as a reading "crutch" and about answer accuracy; alternatives named were Edge's Copilot sidebar, NotebookLM and Readboost.io — [HN thread](https://news.ycombinator.com/item?id=44811387)

### Inferences
- The only mass-market product that ships "read the whole book + ask about it in place, grounded only in the book" is Kindle's Ask this Book, and it is limited to Amazon-purchased/borrowed English titles in the US iOS app with no teaching, review or export.
- Readwise Reader is the closest single-app shape to Learny (EPUB reader + library-wide cited chat + Daily Review + MCP + BYOK for prompts), but its "learning loop" is highlight-review, not teaching sessions or book-anchored quizzes, and Ghostreader is a general assistant rather than a tutor.
- The purpose-built study apps compete on quantity of generated artifacts (notes, cards, quizzes, podcasts) from lectures/PDF/YouTube, not on fidelity to a long text; none advertises passage-level citations.
- Indie open-source readers prove demand (reader3 3.9k stars in ~1 year, ReadAny 2.7k stars in 7 months) but stay at "chat about the page" with no retrieval practice or progress model.

### Gaps
- Turbo AI, Mindgrasp and StudyFetch current list prices could not be verified on primary pages (Turbo's pricing page 404s; others only in secondary reviews).
- I found no primary source describing whether ChatGPT/Claude/Perplexity produce verifiable passage-level citations into uploaded books; official pages describe uploads but not citation anchoring.
- Portuguese/pt-BR UI availability was not confirmed for any product in this session except that Copilot Study and Learn was English-only at GA (May 2026) and Kindle Ask this Book is English-books-only. Assume the big assistants have pt-BR UI but treat as unverified here.

## Key question 1: Which products ingest whole books (EPUB) and combine read + ask + teach in one place, and which cite passages verifiably?

### Takeaway
EPUB ingestion is rare: Readwise Reader, Kindle (own store only), the self-hosted RAG shells (AnythingLLM, Open WebUI) and the indie readers accept EPUB; of those, verifiable passage-level citations are claimed only by Readwise's Global Ghostreader (Aug 2026), Kindle's in-book answers, and Lantern's line-level backlinks. Nobody combines all three of reader, cited Q&A and structured teaching.

### Cited Findings
- Readwise Reader: EPUB import with real print page numbers and chapter names on highlights; Global Ghostreader gives "cited answers grounded across all saved content" with "links back to the referenced passages" (2026-08-06) — [Readwise update Aug 2026](https://readwise.io/reader/update-aug2026)
- Kindle Ask this Book: responses "generated from the book itself", spoiler-aware to your location; only for purchased/borrowed titles; "thousands of English-language best-selling Kindle books"; US iOS now, Android/devices by end-2026 — [Kindlepreneur](https://kindlepreneur.com/amazon-ask-this-book/); [Android Central](https://www.androidcentral.com/tablets/kindle/amazons-kindle-app-gets-gen-ai-chatbot-to-ask-books-about-lore-and-characters); [Authors Guild](https://authorsguild.org/news/statement-on-amazon-kindle-ask-this-book-ai-feature/)
- AnythingLLM and Open WebUI list EPUB among ingestible formats (secondary) — [aicoolies](https://aicoolies.com/comparisons/anythingllm-vs-open-webui); [runaihome](https://runaihome.com/blog/anythingllm-vs-open-webui-vs-librechat-2026/)
- Lantern: "every answer clicks back to the line it came from" — [GitHub KlaraGraff/lantern](https://github.com/KlaraGraff/lantern)
- ReadAny: RAG chat with hybrid vector + BM25 retrieval over local EPUBs — [ReadAny site](https://codedogqby.github.io/ReadAny/)
- Khoj formats exclude EPUB; Recall content types exclude EPUB; Heptabase and RemNote are PDF-centric — [GitHub khoj](https://github.com/khoj-ai/khoj); [recall.it/pricing](https://www.recall.it/pricing); [Heptabase changelog](https://wiki.heptabase.com/changelog/changelog); [remnote.com/pricing](https://www.remnote.com/pricing)
- ChatGPT Study Mode works with uploaded PDFs/images from coursework (secondary) — [Appscribed](https://appscribed.com/chatgpt-study-mode/)
- Heptabase has an "AI Tutor" that runs "structured, personalized learning sessions" over your notes/PDFs — [Heptabase Medium](https://medium.com/heptabase/the-best-way-to-use-ai-for-learning-762c3467bdf1)

### Inferences
- "Teaching" (Socratic, structured sessions) lives in the assistants and in Heptabase's AI Tutor; "reading with citations" lives in Readwise/Kindle/indie readers. The intersection with EPUB + preserved structure + citations + teaching is empty in this set.
- Kindle's no-opt-out controversy suggests grounded book Q&A is now expected by mainstream readers, which normalizes Learny's core loop.

### Gaps
- Whether Kindle Ask this Book works on sideloaded/personal EPUB or "Send to Kindle" documents: not found.
- Whether Open WebUI / AnythingLLM preserve EPUB chapter structure for citations (versus flat chunking): not found in sources.

## Key question 2: Which have a real learning loop (retrieval practice, spaced review, progress) rather than just chat?

### Takeaway
Real spaced repetition exists in Anki (FSRS), RemNote, Knowt (free), Recall, Quizlet and Readwise Daily Review/Mastery Cards; the assistants added quizzes and flashcards in 2025–2026 but not scheduled review or progress tracking; no product ties spaced review back to book passages with citations.

### Cited Findings
- Anki FSRS built in since 23.10 (2023-10-31); 26.09.3 on 2026-09-23 — [Wikipedia: Anki](https://en.wikipedia.org/wiki/Anki_(software))
- Knowt free tier includes Spaced Repetition, Learn, Practice Test on own sets — [Knowt help](https://help.knowt.com/en/articles/16905163-what-s-included-in-the-free-plan-for-students)
- Recall Plus/Max: "Generate quizzes from saved content and review them on a schedule designed for long-term retention" — [recall.it/pricing](https://www.recall.it/pricing)
- RemNote: AI flashcards, quizzes, AI grading on Pro with AI — [remnote.com/pricing](https://www.remnote.com/pricing)
- Readwise: Daily Review and Mastery Cards — [Readwise update Aug 2026](https://readwise.io/reader/update-aug2026)
- Perplexity Study Mode generates interactive flashcards and quizzes — [Perplexity changelog 2025-10-03](https://www.perplexity.ai/changelog/what-we-shipped-october-3rd)
- Copilot Study and Learn: flashcards, fill-in-the-blanks, quizzes, matching; "the learner does the thinking" — [Microsoft Education Blog](https://www.microsoft.com/en-us/education/blog/2026/05/study-and-learn-ai-built-for-your-student/)
- ChatGPT: interactive quizzes added 2026-08-14 (secondary, unverified) — [ExplainX](https://explainx.ai/blog/chatgpt-for-teens-safety-study-mode-august-2026)
- Khanmigo: progress monitoring for parents (secondary) — [SelectHub](https://www.selecthub.com/p/chatbot-software/khanmigo/)
- r/GetStudying users criticize tools that "simply summarize material" and prefer tools that "force active recall and retrieval" (secondary synthesis) — [aitooldiscovery](https://www.aitooldiscovery.com/guides/best-ai-study-tools-reddit)

### Inferences
- Progress/motivation models in this set are thin: streaks (Readwise), parent dashboards (Khanmigo), credit meters (Heptabase/RemNote). None report mastery per chapter of a book.
- The big assistants' quizzes are session-bound (no scheduler, no retention curve), which leaves scheduled review as a differentiator for a study-first app.

### Gaps
- No source quantified retention outcomes for any AI study app.
- Quizlet's 2026 AI feature changes (beyond Q-Chat/Magic Notes) not verified on a primary page.

## Key question 3: Pricing norms (free tier limits, $/month) and who offers BYOK/self-host

### Takeaway
The norm is freemium with paid tiers at roughly $8–20/month (annual billing discounts of 30–60%), student discounts of 20–60%, and increasingly credit-metered AI. BYOK/self-host is confined to open-source or developer-adjacent tools (Obsidian Copilot, Smart Connections, Khoj, AnythingLLM, Open WebUI, Lantern, ReadAny, Readwise custom prompts).

### Cited Findings
- Price points (USD/month unless noted): Khanmigo $4 — [SelectHub](https://www.selecthub.com/p/chatbot-software/khanmigo/); Quizlet Plus $7.99 or $35.99/yr — [Nibble](https://nibble-app.com/blog/quizlet-cost); StudyFetch $7.99/$11.99 — [Dupple](https://dupple.com/reviews/study-fetch); RemNote $8/$18 annual — [RemNote](https://www.remnote.com/pricing); Readwise Full $9.99 annual — [Readwise](https://readwise.io/pricing); Brainly Plus $9.99 — [fast.io](https://fast.io/resources/brainly-ai-review-2026/); Recall $10/$38 annual — [recall.it](https://www.recall.it/pricing); Kortex $10/$17.50 annual — [Kortex](https://www.kortex.co/pricing); Mem $12 — [Myflexnote](https://myflexnote.com/blog/best-ai-note-taking-apps); Heptabase $8.99/$17.99/$53.99 annual — [spotsaas](https://www.spotsaas.com/product/heptabase/pricing); Knowt Ultra $24.99 or $149.99/yr — [Knowt](https://knowt.com/plans); Mistral Pro $14.99 — [Wikipedia](https://en.wikipedia.org/wiki/Le_Chat_(AI)); ChatGPT Plus / Claude Pro / Perplexity Pro $20 — [SSD Nodes](https://www.ssdnodes.com/learn/claude-pro-in-brazil-what-you-pay); [suprmind](https://suprmind.ai/hub/perplexity/pricing/); SuperGrok $30 — [krater.ai](https://krater.ai/blog/grok-student-discount); Speechify $29 or $139/yr — [Costbench](https://costbench.com/software/ai-voice-tools/speechify/); Smart Connections Pro $30 — [smartconnections.app](https://smartconnections.app/pro-plugins/)
- Free-tier limits: Recall 10 summaries/month; Kortex 15 AI requests/month; Mem ~25 notes/chats/PDF pages; Heptabase none (trial only); Knowt unlimited study modes but AI summarizer gated — [recall.it](https://www.recall.it/pricing); [Kortex](https://www.kortex.co/pricing); [Myflexnote](https://myflexnote.com/blog/best-ai-note-taking-apps); [spotsaas](https://www.spotsaas.com/product/heptabase/pricing); [Knowt](https://knowt.com/plans)
- Credit metering: RemNote 1,000 vs 20,000 AI credits; Heptabase 100/1,800/8,100 credits; Kortex 500 premium requests — [RemNote](https://www.remnote.com/pricing); [spotsaas](https://www.spotsaas.com/product/heptabase/pricing); [Kortex](https://www.kortex.co/pricing)
- Student discounts: Readwise 50%; Recall 20%; Perplexity $10/month; Mistral €5.99; Grok 2 months free; Google AI Pro 1 year free for US college students — [Readwise](https://readwise.io/pricing); [recall.it](https://www.recall.it/pricing); [descontosparaestudantes](https://descontosparaestudantes.com.br/descontos/perplexity-pro-education-br); [aistudentdiscount](https://aistudentdiscount.com/le-chat-student/); [krater.ai](https://krater.ai/blog/grok-student-discount); [Google back-to-school 2026](https://blog.google/products-and-platforms/products/education/back-to-school-2026/)
- BYOK / self-host: Obsidian Copilot free with own key or local model — [Obsidian plugin](https://community.obsidian.md/plugins/copilot); Readwise custom Ghostreader prompts with own OpenAI key — [Readwise update](https://readwise.io/reader/update-aug2026); Khoj self-host only since 2026-04-15 — [app.khoj.dev](https://app.khoj.dev/); AnythingLLM (MIT) and Open WebUI self-hosted — GitHub API; Lantern "bring your own AI"; ReadAny local vector store — [Lantern](https://github.com/KlaraGraff/lantern); [ReadAny](https://codedogqby.github.io/ReadAny/)
- Institutional: ChatGPT Edu unpublished, negotiated ($144/user/yr UC Davis; $3.1M/yr USC) — [UC Davis](https://iet.ucdavis.edu/technews/new-chatgpt-edu-agreement-offers-expanded-features-lower-cost-new-terms); [Daily Trojan](https://dailytrojan.com/2026/01/22/uscs-chatgpt-edu-subscription-costs-3-1-million-per-year-provost-says/); Copilot Study and Learn at no additional cost for M365 education — [Microsoft](https://www.microsoft.com/en-us/education/blog/2026/05/study-and-learn-ai-built-for-your-student/); Khanmigo districts from $10/student/yr (secondary) — [SelectHub](https://www.selecthub.com/p/chatbot-software/khanmigo/)
- Brazil: ChatGPT localized in BRL (Go R$39,99; Plus R$99,99); Claude and Perplexity billed in USD plus IOF — [gptprompts.ai](https://gptprompts.ai/pt-br/precos-chatgpt); [SSD Nodes](https://www.ssdnodes.com/learn/claude-pro-in-brazil-what-you-pay); [horadecodar](https://horadecodar.com.br/perplexity-pro-vs-gratis/)

### Inferences
- A consumer study app priced above ~$12/month competes directly with the $20 general assistants; a BYOK or self-host option is the main lever to undercut that while avoiding metered credits.
- The Khoj Cloud shutdown (a 37k-star project) is evidence that subscription hosting of an open-source second brain is hard to sustain; self-host-first with an optional hosted tier is the pattern that survived (Wallabag, Karakeep, AnythingLLM).

### Gaps
- No verified pt-BR-localized pricing for any purpose-built study app.
- Turbo AI, Mindgrasp, StudyFetch exact 2026 prices unverified (see above).

## Key question 4: What launched or changed since 2026-09-03 (last ~4 weeks)?

### Takeaway
The September 2026 window was quiet for the non-Google set: incremental releases (Anki 26.09.x, Open WebUI 0.11.4, AnythingLLM 1.16.2, Heptabase's ChatGPT plugin) while Google shipped the headline study features. I could not read OpenAI's or Perplexity's September changelogs (HTTP 403).

### Cited Findings
- Anki 26.09.3 released 2026-09-23 — [Wikipedia: Anki](https://en.wikipedia.org/wiki/Anki_(software)); GitHub release 2026-09-23 (GitHub API)
- Open WebUI v0.11.4 released 2026-09-21; AnythingLLM v1.16.2 released 2026-09-22; Karakeep v0.33.2 on 2026-08-11 (GitHub API, 2026-09-30)
- Heptabase ChatGPT plugin released 2026-09-23 — [Heptabase changelog](https://wiki.heptabase.com/changelog/changelog)
- ReadAny pushed 2026-09-26; Lantern and Third Mind Reader pushed 2026-09-28; iaflowacademy/reader3 fork pushed 2026-09-17 (GitHub API)
- Just before the window: Readwise Reader update #14 on 2026-08-06 (Global Ghostreader, MCP, EPUB fixes) — [Readwise](https://readwise.io/reader/update-aug2026); ChatGPT quizzes/teens 2026-08-14/18 (secondary) — [ExplainX](https://explainx.ai/blog/chatgpt-for-teens-safety-study-mode-august-2026); Microsoft EDU back-to-school update Aug 2026 — [Tech Community](https://techcommunity.microsoft.com/blog/educationblog/whats-new-in-microsoft-edu---back-to-school-august-2026/4516292); Google study tools 2026-08-19 — [TechCrunch](https://techcrunch.com/2026/08/19/google-launches-new-study-tools-for-students-across-search-and-gemini/)
- Comparator: Google Gemini Notebook study tools, mid-September 2026 — [Google blog](https://blog.google/innovation-and-ai/products/gemini-notebook/new-study-tools-september-2026/)

### Inferences
- The self-hosted RAG shells ship weekly; the study apps ship pricing/packaging changes more than learning-loop changes.

### Gaps
- OpenAI release notes (help.openai.com) and Perplexity changelog pages returned HTTP 403; September 2026 entries for both are unverified.
- No September 2026 announcements found for Turbo AI, Knowt, StudyFetch, Quizlet, Mindgrasp, Khanmigo, RemNote, Recall, Mem, Kortex, Speechify, Elicit or SciSpace.

## Key question 5: Where do users complain (hallucinations, no citations, doing the thinking for them, cost, lock-in)?

### Takeaway
The recurring complaints are hallucinated or untraceable study material (fatal for medical students), tools that summarize instead of forcing recall, aggressive ads/upsells and auto-renewal in the study apps, and rights/lock-in concerns for Kindle; "AI as a reading crutch" is the top pushback on HN for LLM e-readers.

### Cited Findings
- Medical students: "hallucinations being considered a dealbreaker rather than a quirk—med students won't trust AI-generated study materials they can't trace back to a source" (secondary Reddit synthesis) — [Scholarly](https://scholarly.so/blog/best-ai-for-studying-reddit-2026)
- r/GetStudying: preference for tools that "force active recall and retrieval rather than passive review" (secondary) — [aitooldiscovery](https://www.aitooldiscovery.com/guides/best-ai-study-tools-reddit)
- Sept 2025 r/ChatGPTPro thread "GPT-5 gets basic facts wrong more than half the time" with 200+ upvotes (secondary) — [Leader Menu](https://leadermenu.com/workplace-systems/the-twelve-real-complaints-about-ai-tools-in-2026-a-reddit-twitter-and-github-sy/)
- Turbo AI: hallucinated transcripts propagating into notes/flashcards/quizzes — [tl;dv](https://tldv.io/blog/turbo-ai/); Reddit: "turbolearn is pretty terrible" for calculus — [AI Tutor blog](https://ai-tutor.ai/blog/best-turbolearn-ai-alternatives/)
- Knowt: intrusive ads, upsells blocking paid features (Trustpilot) — [Trustpilot](https://se.trustpilot.com/review/knowt.io)
- StudyFetch: auto-renewal and cancellation is "the most common complaint" — [Dupple](https://dupple.com/reviews/study-fetch)
- ChatGPT Study Mode "can make mistakes" and sometimes gives direct answers anyway (secondary) — [Appscribed](https://appscribed.com/chatgpt-study-mode/)
- Grok "weaker as a citation source for academic writing" (secondary) — [Layer3 Labs](https://www.layer3labs.io/guides/grok-4-5-for-education)
- Kindle: Authors Guild says no opt-out and no compensation; feature limited to Amazon-purchased titles — [Authors Guild](https://authorsguild.org/news/statement-on-amazon-kindle-ask-this-book-ai-feature/)
- HN on LLM e-readers: concerns about "shortened attention spans and reading as a 'crutch'" and "AI accuracy and reliability"; requests for spoiler-safe answers bound to reading position — [HN thread](https://news.ycombinator.com/item?id=44811387)
- Khoj Cloud users lost the hosted service on 2026-04-15 (lock-in/continuity risk of hosted second brains) — [app.khoj.dev](https://app.khoj.dev/); a GitHub issue reports inability to export chats after end of 2025 — [khoj issue #1299](https://github.com/khoj-ai/khoj/issues/1299)

### Inferences
- "Traceable to a source" is the single most-cited trust requirement, which is Learny's stated core (citations, evaluation, traceability).
- Complaints about ads/upsells in Knowt/StudyFetch suggest a clean, non-metered pricing model is itself a selling point.

### Gaps
- I did not find primary Reddit/App Store threads for Quizlet Q-Chat accuracy complaints; only general ChatGPT-accuracy studies surfaced.
- No G2/Capterra rating numbers were collected for the study apps.

## Key question 6: Which are open-source, with license and traction?

### Takeaway
Open-source traction concentrates in generic RAG shells (Open WebUI 154k, AnythingLLM 67k, Khoj 38k stars) and note/read tools (Anki 32k, Karakeep 29k, Zotero 15k, Wallabag 13k); book-specific readers are small (reader3 3.9k, ReadAny 2.7k, BookWith 311) and mostly single-maintainer.

### Cited Findings (GitHub API, 2026-09-30)
- open-webui/open-webui: 153,667 stars, license NOASSERTION (custom), v0.11.4 (2026-09-21)
- Mintplex-Labs/anything-llm: 66,634 stars, MIT, v1.16.2 (2026-09-22), created 2023-06-04
- khoj-ai/khoj: 37,548 stars, AGPL-3.0, 2.0.0-beta.28 (2026-03-26), last push 2026-08-02 — [GitHub](https://github.com/khoj-ai/khoj)
- ankitects/anki: 31,676 stars, AGPL v3+ (per Wikipedia), 26.09.3 (2026-09-23)
- karakeep-app/karakeep: 29,368 stars, AGPL-3.0, v0.33.2 (2026-08-11)
- zotero/zotero: 15,445 stars; wallabag/wallabag: 12,992 stars, MIT
- logancyang/obsidian-copilot: 7,773 stars, AGPL-3.0; brianpetro/obsidian-smart-connections: 5,476 stars
- karpathy/reader3: 3,876 stars, no license file, last push 2025-11-18 — [GitHub](https://github.com/karpathy/reader3)
- codedogQBY/ReadAny: 2,687 stars, created 2026-02-25, GPL-3.0 (per project site) — [ReadAny](https://codedogqby.github.io/ReadAny/)
- onebirdrocks/ebook-mcp: 395 stars, Apache-2.0; shutootaki/bookwith: 311 stars, AGPL-3.0; Hipst3rMusic/obsidian-third-mind-reader: 109 stars, AGPL-3.0; KlaraGraff/lantern: 1 star, MIT

### Inferences
- The AGPL is the default license for second-brain tools with a hosted ambition (Khoj, Karakeep, Copilot, BookWith); MIT/Apache for shells and MCP servers.
- reader3's ~3.9k stars with zero maintenance shows the "read with an LLM" idea spreads on name recognition; the maintained successors are tiny, so there is room for a maintained, structured, cited alternative.

### Gaps
- Open WebUI's exact license text (the GitHub API reports NOASSERTION) was not fetched; it is known to have moved to a custom license but I did not verify terms in this session.

## Key question 7: Synthesis — table stakes vs differentiators, and the white space

### Takeaway
By September 2026, Socratic study modes, flashcard/quiz generation from uploads, PDF/YouTube/audio ingestion and a freemium $8–20 tier are table stakes; whole-book EPUB ingestion with preserved structure, verifiable passage citations, teaching sessions anchored in the text, scheduled review tied to those passages, and BYOK/self-host are each rare and never combined.

### Cited Findings
- Table stakes evidence: Socratic modes in ChatGPT (2025-07-29), Claude (2025-08-14), Perplexity (2025-09-05), Copilot (2026-05-13) — [OpenAI](https://openai.com/index/chatgpt-study-mode/); [Engadget](https://www.engadget.com/ai/anthropic-brings-claudes-learning-mode-to-regular-users-and-devs-170018471.html); [Perplexity changelog](https://www.perplexity.ai/changelog/what-we-shipped-october-3rd); [Microsoft](https://www.microsoft.com/en-us/education/blog/2026/05/study-and-learn-ai-built-for-your-student/)
- Flashcards/quizzes from uploads are in Turbo AI, Knowt, StudyFetch, Mindgrasp, Quizlet, RemNote, Recall, Perplexity, Copilot — [turbo.ai](https://www.turbo.ai/); [Knowt](https://knowt.com/plans); [RemNote](https://www.remnote.com/pricing); [recall.it](https://www.recall.it/pricing)
- Differentiator evidence: passage-linked citations only in Readwise Global Ghostreader (2026-08-06), Kindle Ask this Book, Lantern — [Readwise](https://readwise.io/reader/update-aug2026); [Kindlepreneur](https://kindlepreneur.com/amazon-ask-this-book/); [Lantern](https://github.com/KlaraGraff/lantern)
- EPUB structure fidelity is a live pain point even for the leader: Readwise only fixed "books open at story start", print page numbers and chapter names on highlights in Aug 2026 — [Readwise](https://readwise.io/reader/update-aug2026)
- MCP exposure of a personal library is emerging (Readwise MCP, Recall MCP, Lantern MCP, ebook-mcp) — [Readwise](https://readwise.io/reader/update-aug2026); [recall.it](https://www.recall.it/pricing); [ebook-mcp](https://github.com/onebirdrocks/ebook-mcp)
- Hosted second brains are fragile: Omnivore (2024-11-15) and Khoj Cloud (2026-04-15) both shut down — [molodtsov.me](https://molodtsov.me/2024/10/omnivore-is-dead-where-to-go-next/); [app.khoj.dev](https://app.khoj.dev/)

### Inferences
- White space for a "single home for autonomous study": (1) own-EPUB library with chapter/section-anchored citations that survive into flashcards and teaching sessions (nobody carries citations past the chat answer); (2) a teaching loop that plans a book (chapter sequence, mastery per section, scheduled review) rather than answering ad-hoc questions; (3) spoiler/position-aware grounding for fiction and progressive-disclosure for textbooks (HN's top ask); (4) BYOK and self-host as first-class so users escape credit meters and hosted-shutdown risk; (5) an MCP surface so the big assistants become clients of the library rather than competitors.
- Against the big players, the defensible claim is fidelity, not model quality: the assistants ingest a book as a flat upload with no durable structure, no scheduled review and no progress model.
- Positioning risks: Readwise could add a tutor mode on top of Global Ghostreader cheaply; Kindle could extend Ask this Book to Send-to-Kindle documents. Both would shrink the gap on read+ask but not on teaching+review+ownership.

### Gaps
- No usage or retention data exists publicly for any of these products to size the white space quantitatively.
- pt-BR support across the purpose-built apps and indie readers is unverified; Copilot Study and Learn was English-only at GA and Kindle's feature is English-books-only, which suggests Portuguese book-grounded study is underserved but this is inferred, not measured.
