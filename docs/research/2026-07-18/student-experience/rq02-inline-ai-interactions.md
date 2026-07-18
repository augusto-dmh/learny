# RQ-02 — Inline AI Interactions: Ask/Explain Inside the Text, and Citations as Passages

- **Status:** Complete
- **Date:** 2026-07-18 (all sources accessed 2026-07-18)
- **Question:** How do the best AI-reading tools surface ask/explain inside the text without breaking reading flow — and how should citations be presented as passages rather than chunks?

## Method

Surveyed the AI-in-the-reading-surface UX of Readwise Reader (Ghostreader), Google NotebookLM, Amazon Kindle (Ask This Book / Recaps / Story So Far), Recall, Adobe Acrobat AI Assistant, and Matter (AI Co-Reader). Primary sources (official docs, help centers) were fetched where available; Kindle's UI is app-only and paywalled behind purchase, so reputable press coverage and hands-on reviews are used and marked as secondary. Also read Learny's current implementation — `frontend/app/components/ask-screen.tsx` (standalone Ask page, chat transcript, prompt input) and `frontend/app/components/citations.tsx` (numbered chips → popover with breadcrumb + snippet + "Open in book" link) — as the baseline being replaced.

## Per-Product Findings

### Readwise Reader (Ghostreader) — keyboard-first selection AI, output merged into a chat sidebar

- **Invocation:** Select text → context-menu option "Chat about this" or press `G`; `Shift + G` runs document-level preset prompts; the same prompts are reachable from the **Chat tab of the right sidebar** ([Ghostreader overview](https://docs.readwise.io/reader/guides/ghostreader/overview), accessed 2026-07-18). On mobile, tapping a highlight reveals a ghost icon in the highlight menu.
- **Selection-length awareness:** The prompt menu adapts to what is selected — 1–3 words offers *Dictionary definition, Encyclopedia lookup, Internal x-ray* (document-specific term explanation), *Translate*; longer selections offer *Explain passage (simplify), Expand passage (elaborate), Pick up where I left off, Translate* ([default prompts](https://docs.readwise.io/reader/guides/ghostreader/default-prompts), accessed 2026-07-18). This is the clearest existing articulation of "explain this passage" as a distinct, one-tap verb rather than free-form ask.
- **Where output lands:** Selection-level responses appear in the Chat sidebar and support follow-ups; *Expand passage* saves its output **as a note attached to the highlight** — AI output becoming a durable annotation on the passage, not ephemeral chat ([default prompts](https://docs.readwise.io/reader/guides/ghostreader/default-prompts), accessed 2026-07-18). Document-level answers on mobile go to the Document Note field.
- **Trajectory worth noting:** Ghostreader began as inline popovers and was later consolidated into the Chat sidebar — Readwise converged on *selection in the text as the trigger, sidebar as the answer surface*, keeping the reading column untouched.
- **Grounding/citations:** Prompts are grounded in the document/selection context, but answers carry **no passage-level citations** back into the text (unverified as a hard absence; not documented anywhere in the Ghostreader docs).

### NotebookLM — the citation-as-passage benchmark, but chat-first

- **Layout:** Three panels — sources, chat, studio. Chat is the primary surface; the source text is a viewer you visit, not a reading home ([Use chat in NotebookLM](https://support.google.com/notebooklm/answer/16179559), accessed 2026-07-18).
- **Citations:** Answers use "direct quotes, text, and images straight from your sources." **Hovering a citation shows the full quoted text immediately; clicking it "automatically navigates to the location of the quote, so you can easily view it in context"** — the source viewer opens scrolled to and highlighting the cited passage (same support page, accessed 2026-07-18). This is the strongest citation UX surveyed: hover = preview, click = navigate-in-context, and the quote is verbatim source text, not a paraphrase.
- **Persistence:** Saving a response to a note preserves "the original format — including tables and clickable inline citations" — citations stay live after leaving chat (same support page).
- **Known weaknesses:** No page/paragraph locators usable in formal writing, and no provenance across conversations ([XDA limitations writeup](https://www.xda-developers.com/notebooklm-limitations/), secondary, accessed 2026-07-18). More importantly for Learny: NotebookLM is the archetype of the **chat-first failure pattern** — the document is subordinate to the conversation; there is no "reading flow" to preserve because sustained reading is not the product's center.

### Amazon Kindle — Ask This Book / Recaps: reading-first AI, weak grounding transparency

- **Invocation:** Highlight any passage → an **"Ask" button appears in the selection menu** → type a prompt → a chat box opens over the page ([Tom's Guide](https://www.tomsguide.com/computing/e-readers/amazon-adds-ai-chatbot-to-the-kindle-app-which-offers-spoiler-free-answers-about-your-ebooks), [Gizmodo](https://gizmodo.com/kindle-ask-this-book-ai-2000699503), secondary, accessed 2026-07-18). Amazon frames it as answering "without disrupting your reading flow"; answers render inside the book UI, not a separate app surface.
- **Spoiler scoping:** Answers are limited to content up to the reader's current position — the single most reading-progress-aware grounding policy surveyed; it treats *reading position as a retrieval boundary* ([Reactor](https://reactormag.com/new-kindle-feature-ai-answer-questions-books-authors/), secondary, accessed 2026-07-18). Hands-on testing found it "mostly avoids spoilers" (small sample) ([Kindlepreneur](https://kindlepreneur.com/amazon-ask-this-book/), secondary, accessed 2026-07-18).
- **Grounding presentation — the anti-pattern:** Answers are paraphrases with **no citations and no navigation back to the text**: "instead of pointing me to a chapter or quoting a line, it gave me a full paragraph describing who the character is" ([Kindlepreneur](https://kindlepreneur.com/amazon-ask-this-book/), secondary). Answers are non-copyable and non-shareable. Kindle proves selection→ask inside the reader is the right invocation, and simultaneously proves that uncited paraphrase answers squander the trust the reading surface could confer.
- **Availability:** iOS app, US only; devices/Android planned for 2026 (secondary sources above).

### Recall — chat over summaries; citations link to cards, not passages

- Chat lives in a Chat tab / browser-extension panel, scoped to saved content; output can be saved to the notebook ([Recall docs: Interact with Content](https://docs.recall.it/getting-started/3-summarize-and-chat-with-content), accessed 2026-07-18).
- Answers carry citations with source links; for audio/video a play button jumps to the exact timestamp — a passage-equivalent for time-media. For text content, citations resolve to Recall's **summary cards**, not to a location in the original text (changelog mentions right-click-to-open on chat citations; no passage-navigation feature documented) ([Recall changelog](https://feedback.recall.it/changelog), accessed 2026-07-18; card-level resolution unverified as a hard limit).
- Recall's lesson is negative for RQ-02: when the unit of knowledge is an AI summary card rather than the source text, citations *cannot* be passages — the grounding fidelity ceiling is set by the corpus model, which validates Learny's structure-preserving corpus as the enabler of passage citations.

### Adobe Acrobat AI Assistant — numbered citations that scroll the document and highlight the spot

- Chat panel beside the PDF; answers include "clickable citations — select a source number to jump to the relevant section of the document," with the location highlighted; citations carry document title, section, and page metadata; multi-citation links open a reference list panel ([Adobe: View citations in responses](https://helpx.adobe.com/acrobat/desktop/explore-pdf-spaces/view-citations.html), [AI Assistant overview](https://experienceleague.adobe.com/en/docs/document-cloud-learn/acrobat-learning/get-started/ai/ai-assistant), accessed 2026-07-18).
- Confirms the same pattern as NotebookLM from a second major vendor: **numbered inline markers → click → scroll-and-highlight in the document itself**, with human-readable locator metadata (page/section) attached. Acrobat additionally shows that a *references list panel* is the right treatment when one answer has many citations.

### Matter (AI Co-Reader) — proactive per-paragraph questions, zero typing

- Premium "AI Co-Reader": **tap a paragraph → see anticipated questions → tap a question → see the answer**; "no typing, no switching apps"; answers are powered by Perplexity and footnoted with (web) sources ([Robert Breen hands-on](https://robertbreen.com/2025/02/27/elevate-your-online-reading-with-matter/), secondary; feature existence confirmed on [App Store listing](https://apps.apple.com/ai/app/matter-reading-app/id1501592184); mechanics unverified against getmatter.com, which does not document the feature).
- Two transferable ideas: (a) the *paragraph* as the tappable AI unit (coarser than selection, zero-friction), and (b) pre-generated question suggestions that remove the blank-prompt problem. Its grounding, however, is web search, not the book — the answers cite Perplexity's sources, not the text being read.

## Cross-Cutting Patterns

### Invocation: a stable taxonomy emerged

| Pattern | Products | Flow cost | Best for |
|---|---|---|---|
| Selection popover → action verbs | Kindle ("Ask"), Reader (`G` menu), Matter (paragraph tap) | Lowest — stays in the text | explain/define/translate on a passage |
| Side panel / chat drawer | Reader Chat tab, NotebookLM, Acrobat, Recall | Medium — text stays visible beside the conversation | free-form ask, follow-ups |
| Keyboard shortcut | Reader (`G`, `Shift+G`) | Lowest for power users | everything, desktop |
| Separate chat page | Recall (app chat), Learny today | Highest — text is gone | nothing reading-related |

Nobody credible uses a **modal dialog** over the text for AI answers; nobody routes selection-level questions to a different page. The consensus stack is: *selection in the text is the trigger; a non-modal side surface is where conversation accumulates; short one-shot verbs (define/explain) may render nearer the selection.*

### Explain-a-passage vs free-form ask are different verbs everywhere

Reader hard-codes the distinction (selection-length-aware preset prompts vs "Chat about this"); Kindle separates highlight-scoped Ask from book-level Recaps/Story So Far; Matter only does the passage-scoped form. The pattern: **"explain" is one tap, takes the selection as its entire input, and needs no composed question; "ask" opens an input and a conversation.** Tools that collapse both into a generic chat box (NotebookLM, Recall) are the tools with no reading flow to protect.

### Citations: verbatim quote + navigate-in-context is the bar

The two best implementations (NotebookLM, Acrobat) agree on every particular: numbered inline markers in the answer text; hover/preview shows the **verbatim quoted passage**; click **opens the source scrolled to and visually highlighting that passage**; locator metadata (section/page) is attached. Kindle (no citations) and Recall (card-level citations) mark the failure floor. Learny's current chip+popover+link already implements a weaker version of this — the gap is that the popover shows a *chunk snippet* (retrieval artifact) rather than the passage as the book presents it, and the chips sit on a standalone Ask page rather than beside the reader.

### Long conversation coexisting with reading

- Reader: conversation accumulates in the persistent right-sidebar Chat tab; the reading column never changes.
- NotebookLM/Acrobat: conversation *is* the primary column; the document is the side surface. Works for interrogation, fails for reading.
- Kindle: chat box overlays the page per-question; no durable transcript surfaced (secondary sources; unverified).
- No surveyed product has a true *tutoring* mode (structured multi-turn teaching on a passage). Reader's "Pick up where I left off" and Kindle's Recaps are the nearest relatives — both are **re-entry aids keyed to reading position**, not teaching. Learny's anchor-scoped Teach sessions have no direct competitor pattern to copy; the closest structural fit is "a session opened from a passage that takes over the side panel."

### Failure patterns catalog

1. **Chat-first, text-buried** (NotebookLM, Recall): the document becomes a citation target rather than a reading surface; incompatible with a reading-first product.
2. **Uncited paraphrase answers** (Kindle): fluent answers with no way back to the text; erodes trust and teaches the reader to leave the book.
3. **Citations to retrieval artifacts** (Recall cards; Learny's current chunk snippets): the cited unit is the system's internal representation, not the author's text — readers are shown machinery.
4. **Modal interruptions:** absent from every surveyed product — the market has already rejected them.
5. **Context loss on navigation** (Learny today): Ask lives on a separate page, so asking a question means leaving the book, and "Open in book" is a one-way trip with no way back to the answer.
6. **Blank-prompt friction:** an empty chat box with no suggested verbs (Learny today); Reader's preset menu and Matter's anticipated questions both exist to kill this.

## Implications for Learny

### 1. Selection-to-ask flow for the Reader

- The Reader should own a **selection popover** with a short verb row: **Highlight · Note · Explain · Ask · Card** (card = quiz-item creation, per the locked IA). This matches Kindle/Reader/Matter and shares one popover with the just-shipped highlight-to-note flow — one selection gesture, all five study verbs, all inheriting the selection's anchor.
- **Explain** is one tap, no input: it sends the anchored passage as the question context with a fixed instruction, and can be selection-length-aware later (Reader's define-vs-explain split). **Ask** focuses an input (in the popover or the panel) pre-scoped to the selection's anchor.
- Answers must land in a **non-modal side panel/drawer** of the Reader (Reader/Acrobat pattern), never a modal and never a route change. The reading column keeps its scroll position; the panel holds the transcript so follow-ups coexist with reading. Free-form ask without a selection also lives in this panel (replacing the standalone Ask page).
- Adopt **suggested prompts** in the empty panel state (Matter's insight, Reader's presets) to kill the blank-prompt problem — "Explain this chapter so far," "Define the selected term," etc.
- Kindle's spoiler-scoping is a genuinely good idea Learny is uniquely positioned to do properly (reading position becomes backend state this cycle): a "no spoilers / up to where I've read" retrieval filter is a natural later enhancement, feasible because chunks carry ordered anchors. Not v1 scope.

### 2. Citation-as-passage-link

- Keep the numbered-chip + popover skeleton in `citations.tsx` — it is directionally right — but upgrade to the NotebookLM/Acrobat bar:
  - **Popover shows the passage as the book presents it** — verbatim text at the anchor, rendered in the reading serif face with the section-path breadcrumb as locator — not the retrieval chunk snippet. If the chunk boundary is ugly (mid-sentence), resolve the anchor to its enclosing block for display. The reader should never see chunk machinery.
  - **Click navigates the Reader in-place**: since Ask now lives inside the Reader, "Open in book" stops being a route change (`/read?anchor=…`) and becomes *scroll-to-anchor + temporary highlight of the cited passage* in the already-open reading column — with the answer still visible in the panel. This single change fixes failure patterns 3 and 5 at once and is the moment the LOCKED principle ("citations resolve to passages opened in the reader") becomes literal.
  - Keep hover/preview cheap (popover) and navigation explicit (click on "show in book"), per NotebookLM's hover-vs-click split.
  - When an answer has many citations, an expandable references list inside the panel (Acrobat pattern) beats a long chip row.
- Human-readable locators (chapter › section, already in `section_path`) should stay on every citation — the concrete gap XDA flags in NotebookLM.

### 3. Where Teach mode lives

- Teach should be **entered from the reading surface, and take over the side panel** — a mode of the same panel Ask uses, not a separate page. Two entry points: the selection popover ("Teach me this") for anchor-scoped sessions on a passage/section, and a panel-level control for section-scoped sessions. This keeps the passage being taught visible in the reading column while the session runs — the entire point of anchor-scoped teaching, and something no competitor offers (RQ-01 confirmed the teaching loop is Learny's open ground).
- Teaching-turn citations use the identical passage-link component: a teach session about §3.2 can scroll the reader to the exact sentence it is discussing. Reader-column + tutoring-panel is the layout no surveyed product has; it falls out naturally once Ask/Teach share the panel.
- Reader's *Expand passage → saved as highlight note* pattern suggests one cheap, high-value addition: a "save to note" action on any Ask/Teach answer, storing it as an anchored note (the notes domain just shipped; NotebookLM's save-to-note with citations preserved validates keeping citation links live in the saved note).

## Recommendations

1. **Kill the standalone Ask page; make Ask a panel mode of the Reader.** `ask-screen.tsx`'s transport, streaming, and message logic port into a Reader side panel largely intact; the page route redirects into the reader. (LOCKED IA already requires this; the survey confirms every reading-first product does it and only chat-first products don't.)
2. **Build one selection popover with five verbs — Highlight, Note, Explain, Ask, Create card — all anchor-inheriting.** Explain = one-tap, fixed prompt over the selection; Ask = opens the panel input scoped to the selection.
3. **Upgrade `citations.tsx` from chunk-snippet to passage presentation:** verbatim anchor-resolved passage in the reading typeface, section-path locator retained, expanding to the enclosing block when chunk boundaries are ragged.
4. **Make citation click an in-reader navigation** — scroll-to-anchor with a transient highlight pulse on the cited passage while the answer stays visible in the panel — instead of a route change. Provide a "back to answer" affordance (the panel itself, still open, is that affordance).
5. **Enter Teach from the selection popover and the panel; run sessions in the panel beside the text.** Reuse the citation-passage-link component for teaching-turn citations.
6. **Add suggested prompts to the empty Ask panel** (3–4 chips, e.g., explain-this-section, define-term, summarize-so-far) to remove blank-prompt friction.
7. **Add "save answer to note"** on Ask/Teach responses, storing an anchored note with citations preserved (NotebookLM save-to-note + Reader highlight-note precedent; rides on ADR-0026 machinery).
8. **Defer, but design anchors for, position-scoped retrieval** ("answer only from what I've read") — Kindle validates demand; Learny's ordered anchors + new reading-position state make it cheap later; keep it out of this cycle's scope per the frozen retrieval boundary.

## Open Issues

- Kindle's UI details (chat sheet layout, transcript persistence, non-copyable enforcement) come from press coverage, not Amazon documentation; Amazon publishes no help-center page detailing the flow (unverified).
- Ghostreader answers carrying no citations is inferred from absence in Readwise's docs, not a positive statement (unverified).
- Matter's Co-Reader mechanics (paragraph tap → suggested questions) are from a hands-on review and App Store copy; getmatter.com itself does not document the feature (unverified).
- Recall's text citations resolving only to summary cards (never to a source location) is inferred from its docs' silence plus its card-centric data model (unverified as a hard limit).
- Whether NotebookLM's click-to-navigate works for EPUB sources as precisely as for PDFs was not verifiable from the support pages (the citation behavior page does not distinguish source types).
