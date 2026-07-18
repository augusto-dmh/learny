# RQ-03 — The Highlight → Note → Card Capture Pipeline

- **Status:** Complete
- **Date:** 2026-07-18
- **Question:** What is the best-practice capture pipeline from highlight to note to spaced-repetition card — and how does it map onto Learny's shipped notes domain?

## Method

Surveyed the capture pipelines of Readwise + Readwise Reader (highlight → daily review), RemNote (highlight/Rem → flashcard, FSRS), the Anki ecosystem (note/card identity conventions, source-field patterns, Markdown-sync bridges), Obsidian + SRS plugins (obsidian-spaced-repetition card syntax), and SuperMemo incremental reading (the maximalist reference). Primary sources — product docs, help centers, plugin docs — fetched 2026-07-18; claims from secondary sources or inference are marked **(unverified)**. Then mapped the findings onto Learny's shipped notes domain via `docs/adr/0026-notes-and-second-brain-domain-model.md`, `docs/research/2026-07-18/rq02-highlight-anchoring.md`, and `docs/research/2026-07-18/rq06-note-to-quiz.md`, all read in-repo.

For each product, four lenses: (1) how a highlight becomes a durable note; (2) how notes become cards, manual vs AI; (3) friction — actions from selection to saved artifact; (4) how review outcomes link back to source context.

## Per-Product Findings

### Readwise + Reader — zero-friction capture, keyboard-first, weak card semantics

- **Highlight → durable note:** In Reader, **auto-highlighting converts selected text into a highlight immediately — zero extra actions**; it is a toggle (`Shift+H` to disable) for users who prefer select-then-decide. `H` highlights a focused paragraph; `N` attaches a note to a highlight; `T` tags it; `Shift+N`/`Shift+T` operate at document level. Notes are annotations *on* the highlight, not standalone documents ([Reader docs: highlights/tags/notes](https://docs.readwise.io/reader/docs/faqs/highlights-tags-notes), accessed 2026-07-18).
- **Note → card:** Weakest link. Highlights flow into Daily Review, which resurfaces 5–15 highlights **probabilistically** (chance proportional to a document's share of your library, recently-shown suppressed) — this is passive re-exposure, not recall testing. Only pressing **Master** (`m`) converts a highlight into a question-format flashcard on true spaced repetition — a proprietary recall-probability half-life model (7/14/28-day initial half-lives; resurface when recall probability ≤ 50%), not FSRS ([Readwise docs: reviewing highlights](https://docs.readwise.io/readwise/docs/faqs/reviewing-highlights), accessed 2026-07-18). No AI card generation from highlights in Daily Review.
- **Friction:** Best-in-class capture: selection→highlight = 0 actions; highlight→note = 1 keystroke + typing; every review action is a single key (`d` discard, `m` master, `t` tag, `n` note, `e` edit).
- **Review → source:** During review, a down-arrow menu offers "View in [Source]", returning to the original location in the document ([same docs page](https://docs.readwise.io/readwise/docs/faqs/reviewing-highlights)). One menu-dive away, not one click.
- **Lesson for Learny:** the capture half (auto-highlight, single-key note, single-key vocabulary throughout) is the friction bar to meet; the review half (random resurfacing, no FSRS, buried jump-back) is the part Learny already beats.

### RemNote — the closest full pipeline: highlight → Rem → FSRS card with pin-back

- **Highlight → durable note:** In the RemNote Reader, creating a PDF highlight (with optional Auto Highlight on mouse release, Snap-to-Word, and Ctrl-drag area highlights) **copies a reference to the clipboard and jumps the cursor into the Notes pane**; pasting (`Ctrl+V`) inserts a linked reference with formatting choices — *Pin* (icon-only jump-back), *Text with Pin* (editable text + link), *Text*, *Source* (inline citation) ([RemNote Help: Learning from PDFs](https://help.remnote.com/en/articles/6690975-learning-from-pdfs-and-files-with-the-remnote-reader), accessed 2026-07-18). The note (Rem) and the highlight are linked from birth — the anchor is inherited, never re-entered by hand.
- **Note → card, manual:** Any Rem becomes a flashcard with inline syntax: type `>>` or `==` between prompt and response ([RemNote Help: Creating Flashcards](https://help.remnote.com/en/articles/6025481-creating-flashcards), accessed 2026-07-18). Card authoring is note editing — no separate app or form.
- **Note → card, AI:** Clicking an existing highlight reveals an **AI Cards** button showing suggested flashcards; **one click adds a suggestion to your notes**; "Bulk Create More AI Cards" expands the set; the Summary tab bulk-generates per document section ([same PDF-reader article](https://help.remnote.com/en/articles/6690975-learning-from-pdfs-and-files-with-the-remnote-reader)). AI proposes, the human accepts — generation is never silent.
- **Friction:** highlight = 0–1 actions; highlight→linked note = 1 paste; highlight→AI card = 2 clicks (AI Cards, then pick a suggestion); manual card = inline typing.
- **Review → source:** Generated cards automatically carry **a pin citing the source; clicking the pin opens the original sentence in the PDF** during review — the tightest review-to-passage loop surveyed. Scheduling is FSRS v6 (per RQ-01) and is bound to the Rem ID, so edits never disturb it; reset is explicit (per RQ-06).
- **Lesson for Learny:** this is the reference pipeline shape — anchor inherited automatically at every hop, AI-suggest-with-accept at the highlight, pin-back at review. Learny's ADR-0026 already replicates the identity/scheduling invariants; what RemNote demonstrates is the *surface*: the highlight popover and the pin.

### Anki ecosystem — no capture surface; identity discipline and source-as-convention

- **Highlight → durable note:** Anki has no reading surface; capture always happens elsewhere (Readwise-to-Anki export, Obsidian sync bridges, manual entry). The durable unit is the Anki *note* (fields), from which *cards* are generated; scheduling lives on cards ([Anki manual: editing](https://docs.ankiweb.net/editing.html), accessed 2026-07-18).
- **Note → card:** Manual by default. The ecosystem's identity rule is the one every bridge converges on (per RQ-06): match by **GUID**, update in place, preserve scheduling ([Anki manual: text import](https://docs.ankiweb.net/importing/text-files.html), accessed 2026-07-18). Third-party AI generators (StudyCards, AnkiBrain, etc.) exist but are not first-party (unverified as a class).
- **Friction:** highest of the survey — capture requires an app switch and (in bridge workflows) a sync step; the documented failure mode of skipped syncs is drift and orphaned scheduling (RQ-06, yanki-obsidian).
- **Review → source:** none natively. Best practice is a **convention**: a hidden `Source` field on the card template holding book/page/hyperlink, and an `Extra` field for context, so a failed card can be traced ("First Aid p.142") by *editing* the card ([LessWrong opinionated Anki guide](https://www.lesswrong.com/posts/7Q7DPSk4iGFJd8DRk/an-opinionated-guide-to-using-anki-correctly); [Control-Alt-Backspace: precise cards](https://controlaltbackspace.org/precise/), accessed 2026-07-18; community best practice, not vendor docs). There is no clickable jump to a passage — the source is a citation string, not a link.
- **Lesson for Learny:** Anki proves that source linkage left to user convention degrades into a text field nobody opens. Provenance must be structural (an anchor the review UI can resolve), which Learny's snapshot+anchor model already makes possible.

### Obsidian + SRS plugins — cards as text syntax inside notes; note-level linkage only

- **Highlight → durable note:** No native book highlighting; annotation plugins (obsidian-annotator) write Hypothesis-style data into Markdown, fragile and per-plugin (per RQ-01). In practice the "highlight" for most users is pasted text (often via Readwise export).
- **Note → card:** obsidian-spaced-repetition parses inline syntax from notes: `Question::Answer` for basic cards, `==highlighted text==` as the default cloze delimiter (bold and curly-brace variants configurable); multiple clozes in one line yield sibling cards; scheduling state is written back as an HTML comment adjacent to the card text ([plugin docs: cloze cards](https://stephenmwangi.com/obsidian-spaced-repetition/flashcards/cloze-cards/); [repo](https://github.com/st3v3nmw/obsidian-spaced-repetition), accessed 2026-07-18). The `==cloze==` collision with Markdown's highlight syntax generates *accidental* cards — a real complaint ([discussion #244](https://github.com/st3v3nmw/obsidian-spaced-repetition/discussions/244), accessed 2026-07-18).
- **Friction:** card creation = typing syntax while note-writing (low, for syntax-fluent users); but the pipeline upstream of the note (getting book text in with location metadata) is entirely manual assembly.
- **Review → source:** review opens the containing *note file*; there is no passage-level jump into a book. Identity-by-adjacency of the scheduling comment breaks when text is reorganized (RQ-06, unverified inference from storage format).
- **Lesson for Learny:** inline card syntax inside notes is powerful for fluent users but collides with formatting and gives content-positional identity. Learny's decision (RQ-06/ADR-0026) to generate cards *from* the note via the quiz pipeline with minted IDs — rather than parse card syntax out of the note body — avoids both failure modes. Do not add card-markup syntax to Learny notes.

### SuperMemo incremental reading — the maximalist reference: everything is one keystroke, and references propagate

- **Highlight → durable note:** The pipeline is **article → extract → cloze**. Select text, `Alt+X` creates an *extract* — an independent mini-element entering the learning queue, i.e., highlight and note are the same object ([super-memory.com: incremental reading](https://www.super-memory.com/help/read.htm), accessed 2026-07-18).
- **Note → card:** Select a keyword inside an extract, `Alt+Z` creates a *cloze deletion* — the keyword becomes `[...]`. Fully manual, no AI; formulation is itself incremental (cloze more keywords later as understanding grows).
- **Friction:** one keystroke per hop (`Alt+X`, `Alt+Z`), plus priority management (`Alt+P`) — minimal per-action cost, but the *system* has a famously steep curve: the docs themselves warn it "may seem complex at first" with mastery over "months and years" ([help.supermemo.org: incremental reading](https://help.supermemo.org/wiki/Incremental_reading), accessed 2026-07-18 via search excerpt; page returned 403 on direct fetch).
- **Review → source:** the strongest structural answer surveyed: **references (title, source, link) propagate automatically from element to element** through every extract and cloze, rendered at the bottom of each item, and the knowledge tree lets you walk any cloze back through its extraction lineage to the source article ([super-memory.com/help/read.htm](https://www.super-memory.com/help/read.htm), accessed 2026-07-18).
- **Lesson for Learny:** two principles worth stealing, minus the complexity: (1) every downstream artifact inherits source context *automatically* — the user never re-cites; (2) each pipeline stage is exactly one action. And one anti-lesson: making review itself the reading queue (incremental reading's core move) is a lifestyle, not a feature — Learny's reading-first IA should keep reading and review as distinct modes joined by jump-back.

## The Converged Pipeline Pattern

Across five ecosystems, the successful pipeline has the same shape; products differ only in which stages they automate and how much friction each hop costs:

| Stage | Best-in-class | Friction bar | Who sets it |
|---|---|---|---|
| Select → highlight | auto-highlight on selection (toggleable) | **0 actions** | Readwise Reader |
| Highlight → note | anchor-inheriting note, single keystroke | **1 action** (`N` / paste-pin) | Reader, RemNote |
| Highlight/note → card | AI-suggest, human accepts each card | **2 actions** (trigger + accept) | RemNote AI Cards |
| Manual card | inline authoring where the note lives | typing only, no app switch | RemNote `>>`, Obsidian `::` |
| Card → source at review | pin/reference resolving to the exact passage | **1 click** | RemNote pin; SuperMemo references |

Two invariants hold in every system that works:

1. **Anchor inheritance is automatic.** RemNote's clipboard reference, SuperMemo's propagating references, Reader's highlight metadata — the user never re-enters *where* something came from. Systems that leave source linkage to convention (Anki's hidden field) end up with dead citation strings.
2. **Every stage is optional and one action away.** A highlight need not become a note; a note need not become a card; but each promotion is a single gesture from where the user already is. The moment promotion requires an app/context switch (Anki bridges, Obsidian assembly), users batch it, then skip it.

And one invariant from the identity side (RQ-06, confirmed here): scheduling binds to a stable ID minted at creation; edits update content under the ID; reset is explicit. Learny's ADR-0026 already encodes this.

## Learny's Shipped Domain: What Exists vs What the Reader Must Add

**Already built (ADR-0026, Cycles E–F):**

- **Highlight anchoring** — layered value-based anchor (section anchor + path snapshot, block hash + ordinal, char offsets, quote + 32-char context), 4-tier exact reconcile cascade, orphans kept forever and resurrectable (decision 1 / RQ-02).
- **Notes** — whole-Markdown `notes` table, `note_anchors` carrying the full anchor payload, tags, notebooks, backlinks; user prose never cascade-deleted (decision 2).
- **Note → quiz** — generation from note bodies through the existing quiz pipeline; creation-minted stable item IDs; regenerate-and-match on debounced save updating items in place; FSRS state never touched by edits; "your note changed" drift badge with explicit reset; provenance (note title + excerpt) at review; groundedness QC against the note body with chained book anchors (decision 5 / RQ-06).
- **Quiz pipeline** — candidate generation, verbatim-quote groundedness gate, cosine dedup, FSRS scheduling, review logs, reconcile — all source-agnostic machinery.
- **One-action promotion** note→review and the Obsidian projection export (Cycle F table stakes).

In other words: **the entire back half of the converged pipeline — durable note, card identity, scheduling, drift handling, provenance data — is shipped. What does not exist yet is the front half: the in-reader capture surface and the review-to-reader jump.** The domain model was designed exactly for this surface (ADR-0026 explicitly flags "highlight↔note cardinality and margin UX" as open for design).

**What the Reader must add (all frontend + thin student-workflow state, within the RFC-004 boundary):**

1. **Selection → highlight**, minting the full layered anchor payload from the rendered corpus blocks. Reader-style behavior: instant highlight on a deliberate gesture, toggleable auto-highlight, `H` on a focused block.
2. **A highlight popover/margin affordance** with exactly three escalations — *Note*, *Make cards*, *Ask/Teach about this* — each one action, each inheriting the anchor automatically (the RemNote clipboard-reference flow, minus the manual paste: Learny controls both sides, so the note's `note_anchors` row is created for the user).
3. **AI card suggestion at the highlight**, calling the existing quiz-generation pipeline scoped to the highlighted passage (anchor + quote as the grounding context), presented as accept/edit/discard chips — the RemNote AI Cards interaction on top of Learny's already-shipped QC gate.
4. **Review provenance rendered as a pin**: every card face shows its typed provenance ("*Book*, §3.2" or "your note *Title*") and one click opens the Reader at the anchor (or the note detail). This is the locked reading-first principle applied to review — the direct analog of citations resolving to passages.
5. **A margin/notes rail** in the Reader listing the current section's highlights and notes, giving the reverse direction (reading → my past thinking) and the orphan surfacing UI the anchor model requires.

## Implications for Learny

1. **The Reader's capture flow should be: select → highlight (≤1 action) → popover with Note / Make cards / Ask — nothing else.** Every surveyed success keeps promotion single-gesture and in-place; every failure (Anki bridges, Obsidian assembly) inserts a context switch. The popover is the whole capture UX; there is no separate "create note" or "create card" page reachable from reading.
2. **Notes attached from the Reader are margin notes on the shipped notes domain, not a new object.** A popover "Note" creates a `notes` row (or appends to a per-book reading note — a Cycle-E-flagged design choice) with a `note_anchors` row minted from the highlight's anchor payload. Anchor inheritance must be automatic and invisible; the user types prose only.
3. **AI card generation plugs in at two existing seams — and only those two.** (a) At the highlight: the quiz pipeline generates candidates grounded in the highlighted quote + its chunk, shown as suggestions the user accepts one-by-one (RemNote's proven interaction; the verbatim-quote QC gate already prevents hallucinated cards). (b) At the note: the shipped debounced note-save regenerate-and-match loop (RQ-06 decision) — no new machinery. Do **not** add silent bulk auto-generation on highlight; every surveyed product with AI cards keeps a human accept in the loop, and unreviewed card floods are the documented failure of auto-generators.
4. **Do not adopt inline card syntax in notes.** Obsidian's `==cloze==` collisions and identity-by-adjacency breakage are the cautionary tale; Learny's minted-ID generation path is strictly better and already decided.
5. **The pin is the review feature that closes the loop.** RemNote's click-pin-to-open-the-original-sentence is the single interaction that makes cards feel anchored rather than orphaned; Learny has every datum needed (anchor + quote snapshot + status). Readwise burying jump-back in a menu, and Anki reducing it to a text field, are the two failure grades below it.
6. **Adopt Readwise's single-key review vocabulary for the desktop-web persona.** One key per action during review (grade keys, `n` note-on-card, `o` open source) matches the keyboard-first study sessions the 14-day success gate implies.
7. **Skip SuperMemo's priority queue and incremental-reading model entirely.** Its per-action costs are already matched (one gesture per hop) without its months-long curve; FSRS + due-today on Home covers scheduling. Reading stays reading; review stays review; the pin and the margin rail connect them.

## Recommendations

1. **Ship the highlight popover as the only capture surface**: select text in the Reader → highlight saved on one deliberate action (with an auto-highlight toggle default-off, matching a books-not-articles reading style) → popover offering Note / Make cards / Ask-Teach. Friction budget, enforced in design review: highlight ≤1 action; anchored note = 1 keystroke + typing; AI card = 2 actions (suggest, accept); jump-back = 1 click.
2. **Wire "Make cards" to the existing quiz-generation pipeline scoped to the highlight's anchor and quote**, rendering suggestions as accept/edit/discard chips inline; accepted cards are minted with stable IDs and typed provenance per ADR-0026 decision 5. No new generation code paths; no unsupervised bulk generation.
3. **Render every card's provenance as a clickable pin at review** that opens the Reader positioned at the anchor (book items) or the note detail (note items), with the shipped drift badge alongside for note-derived items. This is mandatory for the reading-first principle — treat a card without a working pin as a broken citation.
4. **Add the margin rail** (per-section highlights + anchored notes, orphans included with their quote snapshots) as the Reader's second panel, giving bidirectional navigation and the orphan-surfacing UI the anchor cascade requires.
5. **Adopt single-key shortcuts across capture and review** (`H` highlight, `N` note, `C` cards, grade keys, `O` open source), documented in a `?` overlay — the Readwise pattern, cheap to add early and defining for a daily-driver study tool.
6. **Explicitly exclude**: inline card syntax in note bodies, a standalone card-authoring page, silent auto-generation of cards on highlight, and any priority-queue/incremental-reading mechanics. Each is a surveyed failure mode or complexity trap that Learny's shipped domain already routes around.

## Sources

- Readwise docs, Reviewing Your Highlights — https://docs.readwise.io/readwise/docs/faqs/reviewing-highlights (accessed 2026-07-18)
- Readwise Reader docs, Highlights/Tags/Notes FAQ — https://docs.readwise.io/reader/docs/faqs/highlights-tags-notes (accessed 2026-07-18)
- RemNote Help, Learning from PDFs and Files with the RemNote Reader — https://help.remnote.com/en/articles/6690975-learning-from-pdfs-and-files-with-the-remnote-reader (accessed 2026-07-18)
- RemNote Help, Creating Flashcards — https://help.remnote.com/en/articles/6025481-creating-flashcards (accessed 2026-07-18)
- Anki Manual, Adding/Editing and Text Import — https://docs.ankiweb.net/editing.html, https://docs.ankiweb.net/importing/text-files.html (accessed 2026-07-18)
- LessWrong, An Opinionated Guide to Using Anki Correctly — https://www.lesswrong.com/posts/7Q7DPSk4iGFJd8DRk/an-opinionated-guide-to-using-anki-correctly (accessed 2026-07-18; community best practice)
- Control-Alt-Backspace, Rules for Designing Precise Anki Cards — https://controlaltbackspace.org/precise/ (accessed 2026-07-18; community best practice)
- obsidian-spaced-repetition docs, Cloze Cards — https://stephenmwangi.com/obsidian-spaced-repetition/flashcards/cloze-cards/ and repo https://github.com/st3v3nmw/obsidian-spaced-repetition (accessed 2026-07-18)
- obsidian-spaced-repetition discussion #244 (accidental clozes from `==` highlights) — https://github.com/st3v3nmw/obsidian-spaced-repetition/discussions/244 (accessed 2026-07-18)
- SuperMemo, Incremental Reading — https://www.super-memory.com/help/read.htm (accessed 2026-07-18); https://help.supermemo.org/wiki/Incremental_reading (403 on direct fetch; details via search excerpt, shortcuts corroborated by super-memory.com)
- Learny in-repo: `docs/adr/0026-notes-and-second-brain-domain-model.md`, `docs/research/2026-07-18/rq02-highlight-anchoring.md`, `docs/research/2026-07-18/rq06-note-to-quiz.md`, `docs/research/2026-07-18/rq01-competitive-landscape.md` (read 2026-07-18)
