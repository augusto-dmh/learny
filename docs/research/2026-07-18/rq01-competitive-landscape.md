# RQ-01 — Competitive Landscape: Anchored Highlights + AI Teaching + Cited Q&A + Spaced Repetition + Notes

- **Status:** Complete
- **Date:** 2026-07-18 (all sources accessed 2026-07-17)
- **Question:** Does any product combine anchored book highlights + AI teaching + cited Q&A + spaced repetition + notes — and is Learny's niche (structure-preserving citations + teaching + FSRS + notes on a self-hosted corpus) still open? Which capabilities are table stakes for Learny's notes feature?

## Method

Surveyed RemNote, Readwise + Readwise Reader, Obsidian (core + SRS/AI/annotation plugins), Recall, Logseq, Zettlr, Matter, plus adjacent products found during search: NotebookLM, Heptabase, SuperMemo, Anki, Polar. Primary sources (product docs, help centers, GitHub repos, official wikis) were fetched where available; claims that could only be sourced from aggregators/reviews are marked **(unverified)**.

## Per-Product Findings

### RemNote — closest single competitor

- **Ingestion:** PDF and web-page annotation with highlights, plus AI flashcard generation from PDFs ([remnote.com](https://www.remnote.com/), [PDF-to-cards page](https://www.remnote.com/pdf_to_cards), accessed 2026-07-17). No EPUB ingestion found on product pages (unverified as a hard absence).
- **Anchoring model:** Highlights become "Rems" linked to a location in the stored PDF copy. No documented stable-anchor scheme, no aliasing, no re-ingest story; internals are proprietary (unverified — not documented publicly).
- **SRS:** Real and modern. FSRS v6 is integrated as a first-class scheduler alongside Anki SM-2, with configurable desired retention ([help.remnote.com FSRS article](https://help.remnote.com/en/articles/9124137-the-fsrs-spaced-repetition-algorithm), [remnote.com/feature/fsrs](https://www.remnote.com/feature/fsrs), [announcement](https://x.com/remnote/status/1787968400758587890), accessed 2026-07-17).
- **AI:** "Personal AI Tutor" chat, flashcard/quiz generation from selected text in notes/PDFs/webpages, AI explanations per question ([AI study tool page](https://www.remnote.com/feature/ai-study-tool), accessed 2026-07-17). The product pages do **not** claim the AI cites specific source passages — no passage-cited Q&A.
- **Citation fidelity:** Highlight → note linkage exists; AI output → source passage linkage is not documented (unverified as absent, but unadvertised).
- **Export/lock-in:** Markdown export plus a proprietary "RemNote (Complete)" round-trip format; local knowledge bases are desktop-only; forum reports of exports with broken references ([help.remnote.com exporting](https://help.remnote.com/en/articles/7898019-exporting-notes), [forum thread](https://forum.remnote.io/t/how-to-export-entire-knowledge-base/1035), accessed 2026-07-17). Cloud SaaS; no self-hosting.

### Readwise + Readwise Reader — best ingestion + export, weakest teaching

- **Ingestion:** EPUB, PDF, articles, RSS, YouTube transcripts, newsletters, Twitter threads ([readwise.io/read](https://readwise.io/read), accessed 2026-07-17). The broadest format coverage in this survey.
- **Anchoring model:** Highlighting is "a first-class feature" on Reader's own parsed copy of each document; anchoring internals are proprietary and highlights live against Reader's copy, not a user-owned corpus (unverified internals).
- **SRS:** Two-tier: Daily Review resurfaces unprocessed highlights **stochastically (at random)**; only "Mastery" cards get true spaced repetition, using a proprietary exponential-decay/half-life algorithm — explicitly *not* SuperMemo-style scheduling and not FSRS ([Readwise docs: reviewing highlights](https://help.readwise.io/article/26-how-does-the-readwise-spaced-repetition-algorithm-work), [Mastery guide](https://docs.readwise.io/readwise/guides/mastery), accessed 2026-07-17).
- **AI:** Ghostreader — in-document summarize, define, simplify, Q&A ([readwise.io/read](https://readwise.io/read), accessed 2026-07-17). No passage-level citations on AI answers documented (unverified as absent).
- **Citation fidelity:** Highlights carry document/location metadata into exports; AI answers do not cite anchors.
- **Export/lock-in:** Excellent — Markdown/CSV/original-file downloads and sync to Obsidian, Notion, Logseq, Evernote, Roam ([readwise.io/read](https://readwise.io/read), accessed 2026-07-17). But cloud-only subscription; no self-hosting.

### Obsidian (core + plugins) — the assemble-it-yourself stack

- **Ingestion/annotation:** Core Obsidian has a PDF viewer; EPUB+PDF annotation comes from community plugins, chiefly [obsidian-annotator](https://github.com/elias-sundqvist/obsidian-annotator) (Hypothes.is-based, saves annotations into local Markdown; repo has open issues through Dec 2025 but unclear maintenance cadence — accessed 2026-07-17).
- **Anchoring model:** Per-plugin and fragile. Annotator stores Hypothes.is-style annotation data in Markdown; there is no vault-wide canonical corpus, no anchor aliasing, and re-adding a modified PDF/EPUB has no reconciliation story (unverified detail on selector format).
- **SRS:** [obsidian-spaced-repetition](https://github.com/st3v3nmw/obsidian-spaced-repetition) supports **FSRS or SM-2** with inline card syntax (`Question::Answer`, cloze via highlights) (accessed 2026-07-17). Newer AI+FSRS plugins exist: [Spaced Repetition AI](https://github.com/ai-learning-tools/obsidian-spaced-repetition-ai) (FSRS + OpenAI card generation), HiNote and LearnKit (FSRS-6) per [obsidianstats roundup](https://www.obsidianstats.com/posts/2025-05-01-spaced-repetition-plugins) (accessed 2026-07-17; roundup is secondary).
- **AI:** [Copilot for Obsidian](https://www.obsidiancopilot.com/en) advertises vault Q&A with inline citations *to notes*; [Smart Connections](https://github.com/brianpetro/obsidian-smart-connections) does local-embedding semantic search (accessed 2026-07-17). Citations resolve to note files, not to book passages/locations.
- **Citation fidelity:** Note-level, not passage-level; nothing preserves book structure.
- **Export/lock-in:** Best-in-class — plain local Markdown, fully self-hostable by nature.
- **Net:** Every capability exists somewhere as a plugin, but no coherent pipeline (highlight → anchored citation → teaching → FSRS item that survives re-ingest); the integration burden and fragility are the user's problem.

### Recall (getrecall.ai) — AI summaries + quiz SRS, no anchoring

- **Ingestion:** Articles, YouTube (≤10 h), podcasts, PDFs (≤300 pages) summarized into "cards" ([recall.it](https://www.recall.it/), accessed 2026-07-17; page-limit figure via aggregator, unverified).
- **Anchoring model:** None — the unit is the AI summary card, not an anchored passage. Review items link back to cards, not to source locations ([docs.recall.it review guide](https://docs.recall.it/getting-started/6-review-content), accessed 2026-07-17).
- **SRS:** Quizzes in 7 formats (MCQ, cloze, matching, ordering, …) on a spaced schedule with a 5-stage progression (New → Mastered, ~3-month max interval); algorithm unspecified — no FSRS claim ([docs.recall.it](https://docs.recall.it/getting-started/6-review-content), accessed 2026-07-17).
- **AI:** Summarization, chat over saved content, auto-tagging; MCP server and API mentioned in docs.
- **Citation fidelity:** Weak — summaries with timestamps for video; no passage-anchored citations documented.
- **Export/lock-in:** Manual Markdown export of cards; users request better Obsidian sync ([feedback board](https://feedback.getrecall.ai/feature-requests/p/obsidian-plugin), accessed 2026-07-17). Cloud-only.

### Logseq — free/local PDF annotation + built-in (aging) SRS

- **Ingestion/annotation:** Built-in PDF annotation; highlights become linkable blocks in the graph ([Logseq forum/docs](https://discuss.logseq.com/t/about-the-annotations-in-pdf-file-in-logseq/15038), accessed 2026-07-17). No native EPUB (unverified as hard absence).
- **Anchoring model:** Highlight → block reference into notes; annotation data stored locally alongside the asset. No corpus-level stable anchors or re-ingest reconciliation.
- **SRS:** Built-in `#card` flashcards using an SM-5-derived algorithm; community bug reports call the implementation faulty and FSRS is a still-open feature request ([issue #8890](https://github.com/logseq/logseq/issues/8890), [FSRS request](https://discuss.logseq.com/t/implement-fsrs-as-updated-srs-algorithm/21586), accessed 2026-07-17).
- **AI:** None built into the classic version; the in-progress DB version adds an optional MCP server for external AI apps ([Logseq DB announcements, May 2026](https://discuss.logseq.com/t/whats-new-with-logseq-db-may-16th-2026/35020), accessed 2026-07-17). The multi-year DB rewrite (release planned May/June 2026) is a maintenance-risk signal.
- **Export/lock-in:** Local plain files, open source — minimal lock-in.

### Zettlr — academic writing, not learning

Markdown editor with Zotero/CSL citation integration and 30+ Pandoc export formats ([zettlr.com/features](https://www.zettlr.com/features), accessed 2026-07-17). No book ingestion, no highlight anchoring, no SRS, no meaningful AI. Not a competitor; relevant only as the bar for bibliographic citation UX in writing tools.

### Matter — read-later with polish, no retention loop

Articles, PDFs, newsletters, YouTube/podcast transcription; frictionless highlighting; TTS; highlight sync to PKM apps ([getmatter.com](https://www.getmatter.com/), accessed 2026-07-17). Premium (~$60/yr) adds an "AI Co-Reader" and unlimited highlighting (pricing/AI via aggregators, unverified). No spaced repetition, no cited Q&A, no EPUB books documented, cloud-only.

### Heptabase — PDF highlights → cards + built-in SRS (rising adjacent competitor)

- PDF import with text and **area** highlights; each highlight becomes a "Highlight Card" that links back to the original location, usable on whiteboards; same model extended to note cards in 2026 ([wiki.heptabase.com/pdf-annotation](https://wiki.heptabase.com/pdf-annotation), [2026-03-24 newsletter](https://wiki.heptabase.com/newsletters/2026-03-24), accessed 2026-07-17).
- Built-in spaced-repetition flashcards (algorithm unspecified; not FSRS-documented) (secondary sources, unverified).
- AI: auto-insights for web articles/videos with links back to original content; podcast transcription. No passage-cited Q&A over books documented.
- eBooks only via Readwise highlight import, not native EPUB. Cloud subscription; export options not documented on the cited pages (unverified).

### NotebookLM (Google) — the cited-Q&A benchmark

- Ingests PDF, **EPUB**, DOCX, Markdown, audio, URLs, YouTube; up to 500k words / 200 MB per source, 50+ sources ([Google support](https://support.google.com/notebooklm/answer/16215270), accessed 2026-07-17).
- Every answer carries inline numbered citations that open the exact source passage — the strongest citation UX surveyed; however citations lack page/paragraph references usable in formal writing, and there is no export or public API ([atlasworkspace limitations writeup](https://www.atlasworkspace.ai/blog/notebooklm-limitations), secondary, accessed 2026-07-17).
- Reported flashcards/quiz generation features (unverified against Google docs). No spaced-repetition scheduling, no durable notes system, no anchoring model exposed to users, no self-hosting, total lock-in (content is not exportable in structured form).

### SuperMemo, Anki, Polar — the ancestors

- **SuperMemo** is the only product that ever deeply unified reading and SRS: incremental reading turns imported articles into extracts and clozes managed by a priority queue and SM-family scheduling ([help.supermemo.org incremental reading](https://help.supermemo.org/wiki/Incremental_reading), [super-memory.com](https://www.super-memory.com/help/read.htm), accessed 2026-07-17). Windows-only, HTML-centric (poor PDF/EPUB), no AI, proprietary format, notoriously steep learning curve.
- **Anki** has FSRS built in since 23.10 across all platforms ([docs.ankiweb.net deck options](https://docs.ankiweb.net/deck-options.html), accessed 2026-07-17) — FSRS is now a commodity, not a moat by itself. Anki has no reading surface or anchored citations.
- **Polar** (getpolarized.io) attempted exactly this niche — PDF annotation + incremental reading + flashcards + Anki sync ([getpolarized.io docs](https://getpolarized.io/docs/incremental-reading.html), accessed 2026-07-17) — but all discoverable activity dates to ~2019–2021; the project appears dormant (unverified — no authoritative shutdown notice found).

## Capability Matrix

| Product | Book ingestion (EPUB/PDF) | Anchored highlights | SRS | FSRS | AI teaching | Cited Q&A (passage-level) | Notes | Self-hosted | Export/no lock-in |
|---|---|---|---|---|---|---|---|---|---|
| **Learny (target)** | EPUB + PDF, structure-preserving | Stable anchors + aliases, survive re-ingest | Yes | **Yes** | Yes | **Yes (anchor-mapped)** | planned | **Yes** | projection exports (Anki) |
| RemNote | PDF (no EPUB) | to stored PDF copy | Yes | **Yes (v6)** | AI tutor, quizzes | No | Yes | No | Markdown, flaky refs |
| Readwise Reader | **EPUB + PDF** | to Reader's copy | Mastery only; rest random | No (proprietary decay) | Ghostreader (no teaching loop) | No | highlight notes only | No | **Excellent** |
| Obsidian + plugins | via plugins | fragile, per-plugin | plugin | plugin (FSRS) | plugin (cites notes) | note-level only | **Yes** | **Yes** | **Plain Markdown** |
| Recall | PDF summaries | No (card-level) | quiz SRS | unspecified | summaries/chat | No | light | No | manual Markdown |
| Logseq | PDF (no EPUB) | highlight → block | built-in SM-5-ish (buggy) | No | No (MCP coming) | No | **Yes** | **Yes (local)** | **Plain files** |
| Zettlr | No | No | No | No | minimal | bibliographic only | Yes | local app | Pandoc |
| Matter | articles/PDF | in-app | No | No | Co-Reader (unverified) | No | light | No | highlight sync |
| Heptabase | PDF (EPUB via Readwise) | highlight cards → location | built-in | unspecified | insights | No | Yes | No | limited (unverified) |
| NotebookLM | **EPUB + PDF** | No user-facing anchors | No | No | studio outputs | **Yes (best-in-class UX)** | minimal | No | **None** |
| SuperMemo | HTML-centric | extracts in-app | **Yes (SM-18)** | No | No | No | in-tree | local app | proprietary |

## Answer: Is the niche open?

**Yes.** No surveyed product combines all five capabilities, and none does so self-hosted:

1. Products with strong SRS (RemNote, Anki, SuperMemo, Obsidian plugins) lack passage-cited AI Q&A over a structure-preserving book corpus.
2. The product with the best cited Q&A (NotebookLM) has no SRS, no durable notes, no export, and no self-hosting.
3. Products with the best highlight capture and export (Readwise Reader) have no true teaching loop and only partial, proprietary SRS.
4. Nobody has Learny's re-ingest-safe anchor model (stable anchors + aliases + corpus-FK-free quiz items reconciled by content key). Every competitor anchors to *their stored copy* of a document; replacing the file breaks or orphans annotations.
5. Self-hosting is essentially conceded territory: only the Obsidian/Logseq file-based world offers it, at the price of plugin assembly and no coherent corpus.

The two products to watch: **RemNote** (already has FSRS v6 + AI tutor + PDF annotation; if it adds passage-cited Q&A and EPUB it covers most of the loop, minus self-hosting) and **Heptabase** (rapidly shipping highlight-card + SRS features; minus AI citations, FSRS, and self-hosting).

## Table Stakes for Learny's Notes Feature

Derived from what every credible competitor already offers:

1. **Highlight → note capture from the reading view** (RemNote, Reader, Logseq, Heptabase all do this) — a note must be creatable directly on a passage, inheriting its anchor.
2. **Bidirectional linkage**: note ↔ anchored passage ↔ any quiz items derived from it; jump-back to the exact corpus location (Heptabase's "locate back to original content" and Logseq's highlight → block refs set the expectation).
3. **Notes survive re-ingest** — Learny's differentiator, but for notes it is table stakes internally: reuse the quiz-item pattern (snapshot text + anchor, reconcile via content key, anchor_aliases).
4. **Markdown export of notes with citations resolved** to human-readable locators (chapter/section/page span) — Readwise/Obsidian users treat plain-text export as non-negotiable; export = projection, consistent with the Anki-export stance.
5. **Note-to-flashcard promotion** — one action from note to FSRS-scheduled item (RemNote's core loop; Obsidian SR's inline-card syntax; Polar's annotation→flashcard).
6. **Search across notes + corpus together** (hybrid retrieval should index notes as first-class documents so cited Q&A can quote the user's own notes with the same anchor discipline).
7. **Lightweight organization** (tags or per-book grouping) — every competitor has at least tags; full backlink graphs (Obsidian/Logseq) are *not* table stakes for v1.

## Recommendation

| Option | Recommended |
|---|---|
| A. Build notes as anchor-native annotations on the corpus | **Yes — recommended** |
| B. Integrate with external PKM (Obsidian-first export/sync) instead of native notes | No |
| C. Skip notes; double down on teaching/quiz differentiation | No |

**Option A — Build notes natively as anchor-native annotations (recommended).**
*Why recommend:* The niche is open precisely at the seam notes close: no competitor ties notes, citations, teaching, and FSRS to one durable, re-ingest-safe, self-hosted corpus. Learny already has every primitive needed (stable anchors, anchor_aliases, content-key reconciliation, hybrid retrieval); notes reuse the proven quiz-item pattern rather than inventing new machinery. Native notes also feed cited Q&A and teaching with the user's own thinking — something Readwise/NotebookLM structurally cannot do. Meeting the seven table stakes above (especially anchor inheritance, re-ingest survival, and Markdown export) makes the notes feature defensible rather than a me-too checkbox.
*Why not:* Notes are a crowded, mature category; users with an Obsidian habit will not migrate their whole vault, so Learny's notes must stay scoped to book-study annotations or risk unwinnable competition with dedicated PKM tools. It is also new UI surface with real maintenance cost.

**Option B — Export/sync to external PKM instead of native notes.**
*Why recommend:* Zero new note-editing UI; respects that Obsidian/Logseq already won plain-text PKM; a Readwise-style export earns goodwill and matches the "export = projection" philosophy already proven with Anki.
*Why not:* Exported highlights lose the live anchor linkage the moment they leave the corpus — exactly the fidelity Learny exists to preserve; the teaching loop and cited Q&A could not read the user's notes back; and Readwise already does this integration better than a single-developer project ever will. It surrenders the differentiating seam instead of occupying it. (A Markdown export of native notes — table stake 4 — captures most of this option's value anyway.)

**Option C — Skip notes; deepen teaching/quizzes.**
*Why recommend:* Teaching + FSRS + cited Q&A is already the moat; effort spent there compounds; smallest scope.
*Why not:* Notes are the connective tissue the research question exposes as universally present in competitors (RemNote, Logseq, Heptabase, Obsidian all pair annotation with notes); without them, users must keep a second tool open while studying, which pushes them toward RemNote/Heptabase whose loops are almost complete. The absence of notes also caps the value of highlights: a highlight without a place to think about it is Readwise, and Readwise is cloud-only commodity territory.

## Open Issues

- RemNote's and Heptabase's internal highlight-anchoring formats are undocumented; the claim that no competitor survives file re-ingest is inferred from absence of any documented reconciliation feature, not from a positive statement (unverified).
- NotebookLM's flashcard/quiz features were reported by secondary sources and not verified against Google documentation; if Google adds scheduling (SRS) to NotebookLM, the competitive picture changes materially.
- Polar's dormancy is inferred from stale sources; no authoritative shutdown notice was found (unverified).
- Matter's AI Co-Reader details and pricing came from aggregators, not getmatter.com (unverified).
- Recall's spaced-repetition algorithm and PDF page limits are not specified in its own docs (algorithm unverified beyond the 5-stage description).

## Verification corrections

Adversarial verification against primary sources (2026-07-17) refuted two claims above; corrections:

1. **NotebookLM — "no durable notes, no export/API" is wrong.** NotebookLM has a first-class notes feature: users can write notes, save chat responses (with clickable inline citations preserved) to notes (up to 1,000 per notebook), and convert notes back into sources ([Google support: Create & add notes](https://support.google.com/notebooklm/answer/16262519)). Notes and Studio outputs are exportable to Google Docs/Sheets from the Studio panel (same support article), Workspace admins have a documented data-export path ([Export NotebookLM data](https://support.google.com/a/answer/16054396)), and Google Cloud now publishes an official **NotebookLM/Gemini Notebook Enterprise API** (create/retrieve/list/delete/share notebooks, manage sources) ([Google Cloud docs](https://docs.cloud.google.com/gemini/enterprise/notebooklm-enterprise/docs/api-notebooks)) — enterprise-only, no consumer API. The "total lock-in / content not exportable in structured form" framing in the NotebookLM section and capability matrix overstates the lock-in. Still true as of 2026-07-17: no spaced-repetition scheduling (flashcards/quizzes exist in Studio with retake-missed only, no scheduler — [Google support: Flashcards/Quizzes](https://support.google.com/notebooklm/answer/16958963)) and no self-hosting.

2. **Logseq — FSRS is no longer an unshipped request.** The official DB-version documentation states flashcards have been "re-implemented to use a new algorithm", linking to open-spaced-repetition's FSRS ([logseq/docs db-version.md](https://github.com/logseq/docs/blob/master/db-version.md)), and the Logseq 2.0 (DB version) beta is publicly available, with FSRS-specific fixes shipping in weekly updates ([What's New with Logseq DB, May 16 2026](https://discuss.logseq.com/t/whats-new-with-logseq-db-may-16th-2026/35020): "the FSRS cloze macro now renders cleanly…"). The classic (file-based) release still uses the SM-5-derived scheduler with open bug reports ([issue #8890](https://github.com/logseq/logseq/issues/8890), still open), so the matrix row is correct only for classic Logseq; the DB beta closes the FSRS gap.
