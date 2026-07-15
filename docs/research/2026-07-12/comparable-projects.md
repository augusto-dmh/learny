# Learny v2 research — comparable-projects

Generated 2026-07-12 by a web-research agent (v2 planning research fleet). Sources/dates inline; verify load-bearing claims before implementation.

---

# Comparable Projects Research — What Learny Should Learn From Them

*Research date: 2026-07-12. Sources fetched live from GitHub/official docs; dates noted per fact.*

## TL;DR — Actionable Conclusions

1. **Nobody in the OSS landscape combines all three of: structure-preserving citations, guided teaching, and built-in spaced repetition.** Chat-with-docs tools (Kotaemon, Khoj, Onyx) do citations but no study loop; flashcard tools (AnkiGPT, md2anki) generate cards but outsource scheduling to Anki and have no citations back to source structure; SRS apps (Anki, Skola) don't ingest books. Learny's angle is genuinely open.
2. **Adopt FSRS via `py-fsrs`** (github.com/open-spaced-repetition/py-fsrs, MIT-community-maintained, Python-native) instead of inventing a scheduler — it's the modern, benchmark-backed successor to SM-2 and fits a Learny-owned port cleanly.
3. **The single highest-value UI feature to copy is Kotaemon's citation preview**: clicking a citation opens the source passage highlighted in context, with relevance score. Learny already has anchors — rendering the cited section is the payoff.
4. **Anki export (.apkg or CSV) is a cheap, high-credibility feature** every flashcard-gen project ships; it makes Learny interoperable with the dominant SRS ecosystem without scope creep.
5. **For portfolio credibility, README + ARCHITECTURE.md + demo GIF + disciplined releases matter more than features.** Imitate linkding (solo-maintainer polish) and rust-analyzer's architecture doc (matklad's pattern).

---

## Comparison Table

| Project | What it does | Stack | Citations? | Teaching? | SRS? | Maturity signals (2026) |
|---|---|---|---|---|---|---|
| **Kotaemon** (github.com/Cinnamon/kotaemon) | RAG UI for chatting with documents | Python, Gradio; multi-LLM; Docling/Azure DI parsers; GraphRAG options | **Yes — best-in-class**: in-browser PDF viewer w/ highlights + relevance scores | No | No | 25.5k★, 69 releases (v0.12.0 May 2026), Apache-2.0, HF Spaces demos, lite/full Docker, user+dev guides |
| **Khoj** (github.com/khoj-ai/khoj) | Self-hostable "AI second brain": docs+web QA, agents, research mode | Python (Django) backend, pgvector, Next.js; local or API LLMs | Basic source references, not passage-anchored | No | No | 35.7k★, 173 releases (2.0.0-beta.28 Mar 2026), AGPL-3.0, docs.khoj.dev, demo GIF, 5k+ commits |
| **Onyx** (ex-Danswer, github.com/onyx-dot-app/onyx) | Enterprise AI chat/search over connectors (Slack, Drive…) | Python/FastAPI-family backend, Vespa/hybrid BM25+embeddings, Redis, MinIO, Postgres | Inline source citations | No | No | Very active, VC-backed (TechCrunch Mar 2025), MIT core + EE dual license, heavy Docker/K8s deploy docs |
| **Open WebUI** (docs.openwebui.com/features/workspace/knowledge/) | Self-hosted LLM chat; "Knowledge" collections w/ RAG | Python + Svelte | Yes — cited snippets sorted by relevance; Focused-Retrieval vs Full-Context toggle | No | No | One of the largest self-hosted AI UIs; very fast release cadence |
| **Calibre-Web-Automated** (github.com/crocodilestick/Calibre-Web-Automated) | Automated ebook library server: auto-import, format conversion (28→EPUB), metadata enforcement, KOReader sync | Python/Flask (Calibre-Web fork), Docker-first | n/a (no AI) | No | No | Active releases, strong README, big self-hosting community |
| **Storyteller** (gitlab.com/storyteller-platform/storyteller) | Self-hosted ebook+audiobook forced alignment; synced narration via EPUB3 Media Overlays | Self-hosted backend + mobile apps | n/a | No | No | MIT, docs site, HN-launched Dec 2023, standards-based (EPUB3) — credibility via open specs |
| **AnkiGPT** (github.com/nilsreichardt/AnkiGPT) | Lecture slides (PDF/text) → AI flashcards → Anki export | Dart/Flutter web, GPT | No source anchoring | No | No (delegates to Anki) | 183★, honest-limitations README, AGPL-3.0; 3.3M cards generated (self-reported) |
| **md2anki** (github.com/lucagrippa/md2anki) | Markdown notes → AI Anki cards | Next.js, Vercel AI SDK, GPT-4o-mini, Langfuse | No | No | No (Anki export) | Small but clean modern AI-SDK stack |
| **Anki + FSRS ecosystem** (github.com/open-spaced-repetition) | The reference SRS; FSRS is its modern DSR-model scheduler, w/ py-fsrs, ts-fsrs, optimizer, benchmark | Rust/Python/TS | n/a | No | **Yes — gold standard** | Academic backing, awesome-fsrs list, multi-language implementations |
| **RemNote** (remnote.com, commercial) | Notes+PDFs → AI flashcards, quizzes, summaries; integrated SRS | Closed | Links cards to note context, not book structure | Partial (explanations) | Yes | Commercial polish benchmark for "document→study" UX |
| **Readwise Reader / Ghostreader** (docs.readwise.io/reader/guides/ghostreader) | Read-later app; AI generates study Qs/flashcards from highlights, feeds daily SRS review | Closed | Highlights tied to reading position | No | Yes (lightweight daily review) | The commercial UX target: highlight → auto-drafted card → daily review loop |

**Near-misses found (flagged, lower confidence — seen only in search snippets, not verified in-repo):** *Skill-Anything* (github.com/SYuan03/Skill-Anything) converts any source into a study package with quizzes+flashcards+SRS via a CLI pipeline — closest in spirit, but batch-CLI, not a served product with passage-anchored citations; *Quanta* and *ZKMemo* claim citation-linked cards / FSRS+incremental reading respectively — worth a 10-minute look but appeared early-stage. Quivr (github.com/QuivrHQ/quivr) has pivoted from "second brain app" to an opinionated RAG *framework* (Megaparse + core + evaluation "Le Juge") — a cautionary tale about scope drift, and less relevant now.

---

## Features to Adopt (books+study scope only)

**From Kotaemon (highest priority):**
- **Click-through citation preview**: citation chip → opens the cited section rendered with the passage highlighted + relevance score. Learny's canonical corpus with anchors makes this cheaper than Kotaemon's PDF-viewer approach.
- **Lite vs full Docker Compose variants** — lowers evaluation friction for portfolio reviewers.
- **Hosted demo** (HF Spaces / short video) so nobody must run Compose to see it work.

**From the FSRS ecosystem:**
- **Use `py-fsrs` behind a Learny-owned SchedulingPort** — don't hand-roll SM-2. FSRS is the current state of the art (Anki adopted it), academically benchmarked (github.com/open-spaced-repetition/awesome-fsrs).
- Store review logs durably (Postgres) in FSRS-compatible shape — enables future per-user parameter optimization via fsrs-optimizer.

**From AnkiGPT/md2anki:**
- **Anki export** (.apkg via `genanki`, or CSV) — one endpoint, huge interop credibility.
- **Editable cards before commit**: users review/edit/delete generated cards before they enter the SRS deck (AnkiGPT's core UX loop).
- **Honest limitations section in README** (AnkiGPT does this well; reviewers notice).

**From Readwise Ghostreader (commercial inspiration):**
- **Highlight/passage → "generate study question"** as an in-context action while reading, not just book-level batch generation.
- **Daily review queue** as the home-screen habit loop: "N cards due today across your books."

**From Onyx / Open WebUI:**
- **Focused-retrieval vs full-section context toggle** per question (Open WebUI's pattern) maps neatly onto Learny's existing RAG-vs-long-context-fallback decision.
- Onyx's deploy docs discipline (resource requirements per profile) — good model for Learny's VPS docs.

**From Calibre-Web-Automated / Storyteller:**
- **Watch-folder auto-import** for EPUBs is a beloved self-hoster feature (cheap with existing Celery pipeline) — optional, low priority.
- Storyteller's lesson: **lean on open standards** (it uses EPUB3 Media Overlays) — Learny citing EPUB CFI-like or spine+fragment anchors is a credibility story worth telling in docs.

**Anti-adoption notes:** Khoj's agents/automations/WhatsApp sprawl and Quivr's framework pivot are both scope-drift warnings — Learny's locked "consuming books + studying them" scope is a differentiator in itself. Also, several big players are AGPL (Khoj, AnkiGPT); if OSS-readiness matters, Learny picking MIT/Apache-2.0 is a friendlier portfolio signal.

---

## Differentiation Verdict

**No verified project does all three of Learny's pillars.** The landscape splits cleanly:

- **Citations without study**: Kotaemon, Onyx, Open WebUI, Khoj — great grounded QA, zero retention loop, and citations point at *chunks/pages*, not preserved book structure (chapters/sections/anchors).
- **Study without citations**: AnkiGPT, md2anki, RemNote, Readwise — cards are generated then *orphaned from source structure*; you can't click a card back to the exact passage and its surrounding section.
- **Books without AI**: Calibre-Web-Automated, Storyteller — strong ingestion/library UX, no intelligence layer.

**Learny's defensible wedge:** the *closed loop* — structured corpus → cited answer/teaching → citation-grounded quiz card → FSRS review → click any card back to the exact passage in its chapter context. The specific novel artifact is a **flashcard that carries a structural citation** (book → chapter → section → anchor), which requires exactly the structure-preserving corpus Learny already built. Pitch it that way in the README ("every card is a receipt"). Secondary differentiators: hexagonal ports with swappable deterministic/network-free AI adapters (great for OSS contributors and CI), and Postgres-only hybrid retrieval (no vector-DB dependency). Watch-list: Skill-Anything and Quanta are converging on citation-grounded cards — move before this is commoditized, and verify those two repos before claiming "first."

---

## README / Architecture Exemplars to Imitate

1. **linkding — Sascha Issbrücker** (github.com/sissbruecker/linkding, checked 2026-07): solo-maintainer gold standard. Screenshot above the fold, live demo instance, separate docs site (linkding.link), 88 disciplined releases (v1.45.0 Jan 2026), MIT, Docker one-liner install. This is the *shape* Learny's README should have: what it is in one sentence → screenshot → demo → install → docs link.
2. **rust-analyzer's ARCHITECTURE.md — matklad's pattern** (rust-analyzer.github.io/book/contributing/architecture.html; rationale: matklad.github.io/2021/02/06/ARCHITECTURE.md.html): the canonical "codemap" doc — entry points, module map, invariants, cross-cutting concerns, deliberately ~short. Learny's hexagonal layout (ports/adapters, worker pipeline, corpus model) deserves exactly this one-page treatment; matklad also published a 2026 follow-up on architecture learning (matklad.github.io/2026/05/12/software-architecture.html).
3. **Kotaemon** (github.com/Cinnamon/kotaemon): best AI-app repo presentation in this space — animated demo, hosted playgrounds, split user-guide vs developer-guide, lite/full Docker images, 69 tagged releases. For an AI product specifically, "try it in 60 seconds without an API key" (Learny's deterministic adapters enable this!) is the killer onboarding move.
   *(Honorable mention: github.com/matiassingers/awesome-readme and github.com/noahbald/awesome-architecture-md as curated pattern lists.)*

**Concrete repo checklist distilled from the credible ones:** one-sentence value prop + demo GIF; hosted or zero-key demo mode; ARCHITECTURE.md with diagram; CI badge + tagged releases with changelogs; lite/full Compose profiles with stated resource needs; honest limitations section; permissive license; CONTRIBUTING.md.

**Sources:** [Kotaemon](https://github.com/Cinnamon/kotaemon) · [Khoj](https://github.com/khoj-ai/khoj) · [Onyx](https://github.com/onyx-dot-app/onyx) · [Onyx/TechCrunch](https://techcrunch.com/2025/03/12/why-onyx-thinks-its-open-source-solution-will-win-enterprise-search/) · [Open WebUI Knowledge](https://docs.openwebui.com/features/workspace/knowledge/) · [Open WebUI RAG](https://docs.openwebui.com/features/chat-conversations/rag/) · [Calibre-Web-Automated](https://github.com/crocodilestick/Calibre-Web-Automated) · [Storyteller docs](https://storyteller-platform.gitlab.io/storyteller/) · [Storyteller HN](https://news.ycombinator.com/item?id=38747710) · [AnkiGPT](https://github.com/nilsreichardt/AnkiGPT) · [md2anki](https://github.com/lucagrippa/md2anki) · [py-fsrs](https://github.com/open-spaced-repetition/py-fsrs) · [awesome-fsrs](https://github.com/open-spaced-repetition/awesome-fsrs) · [Ghostreader docs](https://docs.readwise.io/reader/guides/ghostreader/overview) · [RemNote](https://www.remnote.com/) · [Quivr](https://github.com/QuivrHQ/quivr) · [Skill-Anything](https://github.com/SYuan03/Skill-Anything) · [linkding](https://github.com/sissbruecker/linkding) · [matklad ARCHITECTURE.md](https://matklad.github.io/2021/02/06/ARCHITECTURE.md.html) · [rust-analyzer architecture](https://rust-analyzer.github.io/book/contributing/architecture.html) · [awesome-readme](https://github.com/matiassingers/awesome-readme) · [awesome-architecture-md](https://github.com/noahbald/awesome-architecture-md)
