# RQ11 — Product architecture / information architecture

- **Status:** Complete
- **Date:** 2026-09-03
- **Question:** Is Learny's current product shape right for a public audience, and if not, how should it restructure?
- **Method:** Audit of the live Next.js route tree and shell (`frontend/app`), cross-checked against RFC-004 / RFC-006 / ADR-0027 / ADR-0029, then compared to the IA of NotebookLM (now Gemini Notebook), Readwise Reader, RemNote, and Anki. No code or docker changes.

## TL;DR

The **shape is already right**: a reading-first book workspace plus a small global shell (Home / Library / Review / Notes). That is the pattern that wins the "read → ask → note → review" loop. **The execution is not yet public-ready.** The library still presents Ask / Teach / Read as peer destinations (Ask and Teach are tombstone redirects into the same reader). "Sources" leaks through the URL and empty-state copy. Teach is a sibling dock tab even though ADR-0029 already made it a reply *mode*. Vault export, Anki export, and highlights have no obvious home. Home answers "what now?" but treats the due queue as a peer card instead of the daily ritual a stranger will actually form.

**Recommend Option A — tighten the hybrid, do not invert it.** Keep the four-item shell and the book as the unit of work. Collapse Ask+Teach into one Chat dock. Make opening a book the only library CTA. Rename the remaining engineer-speak. Put exports on Account. Leave Review and Notes as dual-scoped surfaces (global page + in-book dock) — that duplication is the RemNote/Readwise pattern, not a bug.

---

## Current-IA audit

### Real route tree (2026-09-03)

Authenticated chrome (`frontend/app/(app)/layout.tsx`) is a left sidebar plus header. Nav items, in order, from `app-sidebar.tsx`:

| Nav label | Route | Job |
|---|---|---|
| Home | `/home` | Continue-reading hero + due-reviews card + 12-week heatmap |
| Bookshelf | `/sources` | Upload + source cards with status and per-book verbs |
| Review | `/review` | Cross-book FSRS queue (`?source_id=` optional) |
| Notes | `/notes` | Cross-book notes list, tag + book filters, vault zip |

Header (not nav): theme toggle, **Account** (`/account` — email + logout only), Log out.

Full tree:

```
/                          public landing (title + tagline + Create account / Log in)
/login  /register          email+password; success → /home
/home                      signed-in desk
/sources                   bookshelf (URL still "sources")
/sources/[id]/read         book workspace; ?anchor=  ?panel=ask|teach|notes|review
/sources/[id]/ask          tombstone → /read?panel=ask
/sources/[id]/teach        tombstone → /read?panel=teach
/review                    global due queue
/notes                     global notes + "Export vault"
/notes/[id]                note editor, anchors, backlinks, card suggestions
/account                   identity only
/dev/evals                 unlinked eval dashboard (not a student surface)
```

The reader is the real product. `ChapterReader` is a three-column workspace: TOC rail, chapter-flow prose, and a non-modal dock. Selection offers Highlight / Note / Explain / Ask / Create card. The dock strip is Ask | Teach | Notes | Review. Conversations persist (ADR-0029); the list is per-book, shown on Ask and Teach; last-turn mode decides which tab a thread resumes into.

### What the current IA actually is

RFC-004 locked **Home / Reader / Review** and demoted the library to a bookshelf. RFC-006 then made the reader the hub and re-scoped `/notes` and `/review` as *cross-book* surfaces. What shipped is a **hybrid**:

1. **Book-centric workspace** — one book, one screen, tools beside the page.
2. **Global-activity shell** — four destinations that are *not* the book.

That hybrid is coherent. The public problem is the **leftover feature-shaped layer** sitting on top of it.

### Duplicated surfaces — which are real, which are ghosts

| Surface | Global | In-book | Verdict |
|---|---|---|---|
| Ask | Ghost route (redirect) | Dock tab | Ghost. Bookshelf still links it as a peer of Read. |
| Teach | Ghost route (redirect) | Dock tab | Ghost as a page; **real** as a second conversation UI. ADR-0029 already said mode is per-turn, not a destination. The dock still splits one conversation list across two tabs and auto-switches tabs on resume (`reader-panel.tsx`). |
| Review | `/review` (all books, or `?source_id=`) | Dock tab (this book's due, same `ReviewScreen`) | **Intentional dual.** RemNote's global Practice vs document Practice. Keep. |
| Notes | `/notes` + `/notes/[id]` | Dock tab (this book's list; jumps to passage or `/notes/[id]`) | **Intentional dual.** Capture is in-book; browse/export/edit is global. Keep. |
| Highlights | none | Painted in the chapter + capture popover | **Missing surface.** Apple Books' "Bookmarks & Highlights" panel is table stakes; Learny has paint, not a list. |
| Conversations | none | Per-book list in the dock | Underexposed. No "your threads" anywhere in the shell. |
| Quiz / Anki | "Generate quiz deck" + "Export to Anki" on the bookshelf card | Create-card on selection; Review dock | Power-user verbs live on the library, not in the book or Account. |
| Vault export | "Export vault" on `/notes` only | none | Buried. A stranger looking for "get my data out" will open Account and find logout. |

### Home's job

`HomeScreen` is explicitly "what should I do right now": continue-reading + due count, independent fetches, calm "all caught up" copy, heatmap below the fold with a hide-stats toggle (`learny.home.v1`). That is the RFC-004 two-card desk, and it is the right job.

Gaps versus the 2026-07-18 re-entry research (`student-experience/rq04-home-reentry-ritual.md`):

- Continue-reading is "most recent position," not Readwise's honesty rule (`progress__gt:5`). Opening a book and bouncing still steals the hero.
- Due card has a count, not an estimated minutes, not a one-tap that *starts* review from Home without a second page (it links `/review`).
- Two equal cards. For a returning learner with cards due, the duty (Anki/RemNote) should outrank the pull (Kindle) — or at least not look optional. Today both cards have the same visual weight.
- No "also in progress" row. Fine at one-user scale; a public library of several books will need it.
- Home never mentions notes, exports, or "your last conversation." Correct restraint — don't turn it into a dashboard — but the *daily* hook is therefore only resume + due.

### Bookshelf → per-book actions vs how learners work

Learners do not "Ask a source." They open a book and then ask, highlight, or review *from the page*. Every peer that mixes reading with tools agrees (see below). Learny's bookshelf still looks like a **feature launcher**:

- Ready card: Ask / Teach / Read (three peers) + Generate quiz deck + Re-ingest + (once a deck exists) item counts, per-source Review, Export to Anki.
- Upload form: label **"EPUB file"** even though PDF is supported; empty list copy **"No sources yet."** / "Loading your sources…"
- Route: `/sources`. Nav says Bookshelf. Domain and API still say `source`.

A public visitor who taps Teach from the card is redirected into the reader with a panel open — a bait-and-switch. The honest CTA is **Open**, with operator verbs (re-ingest, generate deck, export) in an overflow.

### Naming / copy audit (stranger test)

| Term | Who understands it | Public replacement |
|---|---|---|
| Sources | Engineers; NotebookLM users (where a notebook *contains* many sources) | **Library** (nav) / **book** (object). Keep `source` in the API. |
| Bookshelf | Warm, correct | Keep as the page title; align the URL later (`/library` or `/books`). |
| Teach | Ambiguous: "I teach" vs "teach me" | Mode label **Tutor** or **Guide me** inside Chat; do not use it as a nav destination. |
| Review | Anki users yes; others hear "book review" | Keep **Review** with a subtitle ("cards due"). Do not rename to Quiz. |
| Home | Fine if the page *is* the desk | Keep. |
| Notes | Fine | Keep. |
| Export vault | Obsidian users only | **Download notes (Obsidian)** |
| Re-ingest | Operators | **Rebuild book** (overflow, with the existing confirm) |
| Generate quiz deck | Internal | **Make review cards** (in-book, not a library primary) |

Landing (`/`): "Turn your books into cited answers and lasting recall." No loop diagram, no screenshot, no "then you review." The product *shape* is invisible at the door — that is RQ12's problem, but it is an IA failure too: a stranger cannot form a mental model of Home / book / Review before signing up.

### Underexposed / missing surfaces

- **Vault export** — only `/notes`. Account has no data-out.
- **Anki `.apkg`** — only after a deck exists, on the bookshelf card.
- **Highlights** — no per-book list, no global list. Margin rail exists conceptually in RFC-004 Cycle D; the capture popover is the only highlight UX besides paint.
- **Account** — not a settings/exports hub. Hide-stats lives on the heatmap, not here.
- **Teach as differentiator** — two hops from Home, then a redirect, then a target picker. The flagship tutor is easier to miss than "Generate quiz deck."
- **Conversations** — persisted, unlisted globally. Power users will want "continue last chat" from Home or the book header.

---

## Peer-pattern evidence

The loop is **read → ask → note → review**. Products that own a *piece* of that loop cluster into four IA families.

### NotebookLM / Gemini Notebook — notebook-centric, tools in one frame

Google's Dec 2024 redesign ([official post](https://blog.google/innovation-and-ai/models-and-research/google-labs/notebooklm-new-features-december-2024/)) is explicit: "move effortlessly from asking questions to reading your sources to capturing your own ideas" in **one notebook**. Three panels: **Sources** (the corpus for *this* project), **Chat** (cited conversation), **Studio** (study guides, audio, quizzes as *outputs of the notebook*). Chat citations hover the quote and navigate to the passage ([Gemini Notebook Help](https://support.google.com/notebooklm/answer/16179559)). The library of notebooks is a launcher; work happens inside one notebook.

**Win:** one unit of work, tools are modes of that unit, "Sources" makes sense because a notebook *has many*.  
**Miss for Learny:** no durable FSRS queue, no reading-progress ritual, no cross-notebook due. Learny's unit is a **book**, not a project folder of PDFs. Copying NotebookLM's word "Sources" onto a book library is a category error.

### Readwise Reader — library / reading / review as three jobs

Reader's library is configurable (Inbox/Later/Archive, or Shortlist, or Classic) ([library configuration](https://docs.readwise.io/reader/guides/workflows/library-configuration)). The default **Continue reading** view is honest: `progress__gt:5 AND last_opened__after:"1 week ago"` ([default views](https://docs.readwise.io/reader/guides/filtering/default-views)). Ghostreader hangs off selection — AI is a reading mode, not a route. Daily Review is a **separate product surface** (email + in-app), bounded, with Review Mode vs Scroll Mode ([reviewing highlights](https://docs.readwise.io/readwise/docs/faqs/reviewing-highlights)). Jump-back is "View in [Source]".

**Win:** split the three jobs (pick something / read it / recall it) without pretending they are one screen. Shortlist separates must-read from might-read.  
**Miss:** Readwise review is highlight resurfacing, not FSRS-from-the-book. Learny's Review is closer to Anki than to Daily Review — but the *split* is the lesson.

### RemNote — documents + a first-class queue

Documents are the workspace (notes, cards in the prose). **Flashcard Home** is a different sidebar item: today's goal, Practice [X] Cards (global queue), then documents with per-doc Practice ([Flashcard Home](https://help.remnote.com/en/articles/7925835-the-flashcard-home); [getting started](https://help.remnote.com/en/articles/6022755-getting-started-with-spaced-repetition)). Same cards, two doors: study everything due, or stay inside one document. Priorities tell the global queue what matters.

**Win:** this is the closest analog to Learny's `/review` vs dock Review, and `/notes` vs dock Notes. Dual-scoped surfaces are how serious study tools scale.  
**Miss:** RemNote is document-first, not book-first. There is no "continue reading a chapter." Learny must keep Kindle's resume *and* RemNote's queue.

### Anki — the queue is the home

Deck list with New / Learn / Due; click a deck → overview → Study Now; "finished for now" when today's cards run out ([Anki manual — Studying](https://docs.ankiweb.net/studying.html)). No reading surface. Heatmap is an add-on because even this audience wants a calm calendar.

**Win:** one-tap duty, bounded day, deck as the organizing object for *memory*.  
**Miss:** making Learny's Home look like a deck browser would bury the book — the thesis.

### Pattern that actually wins the full loop

| Pattern | Who | Maps to Learny |
|---|---|---|
| Unit of work is one container; tools are panels | NotebookLM | The **book workspace** (already built) |
| Library ≠ reader ≠ review | Readwise | Shell vs `/read` vs `/review` |
| Global queue *and* in-document practice | RemNote | `/review` *and* dock Review |
| Due-count-first daily open | Anki, RemNote Flashcard Home | Home's Review card, currently under-weighted |
| Resume the unfinished artifact | Kindle, Readwise Continue | Home's continue-reading hero |

Nobody credible makes Ask or Teach a top-level app destination. RFC-004 already killed those pages; the bookshelf links are the remaining lie.

---

## Restructure options

### Option A — Tighten the hybrid (book workspace + activity shell)

**Keep:** nav Home / Library / Review / Notes; reader as the only per-book destination; dual-scoped Review and Notes.

**Change:**

1. Bookshelf card: one primary **Open** → `/sources/{id}/read`. Status chip stays. Overflow: rebuild, make cards, export Anki, export notes for this book.
2. Dock: merge Ask + Teach into **Chat**, with a per-turn (or per-composer) **Answer | Tutor** control — ADR-0029 made literal. One conversation list. Teach target picker appears when Tutor is selected (scope invariant unchanged).
3. Home: when `total_due > 0`, Review is the lead card ("N cards · ~M min" → starts `/review`); continue-reading is second. When caught up, continue-reading leads. Apply a >5% (or "opened in the last week") honesty rule.
4. Notes stay global for browse/export/editor; dock Notes stays a jump-list. Add a per-book **Highlights** list inside the Notes dock (or a fifth strip item only if Chat is one tab and there is room).
5. Account becomes the **exports + prefs** hub: vault zip, hide stats, later email/verification. Copy: Library not Sources; book file not EPUB file.

**Trade-offs:** Smallest shippable delta; honors RFC-004/006; still four nav items (a stranger can learn them in one session). Does not produce a viral "notebook" metaphor. Tutor is a mode, so it can be missed unless Chat empty-state teaches it.

### Option B — Pure book-centric (NotebookLM-shaped)

Nav collapses to **Library** (and maybe Review as a badge). Opening a book *is* the app: TOC + prose + Chat/Notes/Review dock. Home disappears, or becomes the library with a continue pin. `/notes` and `/review` become filters *inside* the current book, or a modal over the library.

**Trade-offs:** One concept to explain ("your books"). Matches NotebookLM's cognitive model and Learny's reading-first thesis at maximum. **Loses the daily ritual.** FSRS only works if the learner opens a book that has due cards — Anki/RemNote evidence says the queue must be reachable without picking a document. Cross-book notes (the second-brain loop ADR-0026 shipped) become second-class. Wrong for public retention.

### Option C — Activity-centric shell (queue-first)

Home *is* RemNote Flashcard Home / Anki deck list: due first, then documents-with-counts, then continue-reading below. Nav: Today / Library / Notes. The reader is where you *make* cards and notes, not where you live. Teach/Ask are Studio-like outputs from Today or from a document row.

**Trade-offs:** Strongest habit loop (Anki). Makes Review the product. **Contradicts the thesis** ("book intelligence," Iron Gall reading-first, RFC-004). Kindles the Kindle Home failure mode in reverse: the vendor's metric (cards) outranks the reader's book. Teach-as-tutor has no natural home. Attractive to Anki migrants, alien to "I just want to finish this chapter."

---

## Recommendation

**Ship Option A.** Why-recommend:

- The full loop needs **two hooks**: a pull (unfinished chapter) and a duty (due cards). Readwise + RemNote already prove the split; Learny already built it. Inverting to B or C throws away one hook.
- ADR-0029 already decided Teach is a mode. The IA should stop arguing with the domain model.
- Dual Review/Notes is not duplication to delete; it is how learners actually work (stay in the book vs clear the day vs search all notes).
- Public launch is a *stranger* problem: naming, one obvious CTA per object, exports findable. That is copy and grouping, not a new architecture.
- Cycle-sized: each move below is one PR-shaped cycle against frozen backend ports.

**Why-not (take these seriously):**

- Option B would photograph better against NotebookLM in RQ12's positioning fight — "a notebook per book" is easier to screenshot than a four-item shell. A is less viral, more correct.
- Collapsing Teach into Chat can hide the tutor differentiator that RQ03 cares about. Mitigate with Chat empty-state ("Ask the book, or tutor this section") and a selection verb **Tutor** later — not a fifth nav item.
- Option C would likely raise D1 retention among SRS natives. Rejecting it means Home must *weight* the due card when N>0, or A fails the Anki test without becoming Anki.

Do **not** resurrect standalone Ask/Teach pages. Do **not** add a fifth primary nav item (Highlights, Chat, Decks). Do **not** put Studio-style generators (quiz, vault, re-ingest) on the library face.

---

## Cycle-sized moves

Sized to the repo's ship-cycle style. Order is dependency, not importance.

1. **Library honesty (S).** One **Open** on a ready book. Ask/Teach/Read links go away (routes stay as redirects for bookmarks). Upload accept + label = EPUB or PDF. Empty copy = "No books yet." Overflow: Rebuild, Make review cards, Export to Anki. No URL migration required this cycle (`/sources` can linger).

2. **Chat dock (M).** Merge Ask and Teach tabs into Chat; composer mode `answer | teach`; keep the teaching-anchor invariant and `not_found_in_scope`. One conversation list. Empty state names both modes. Selection **Explain** / **Ask** still open Chat in answer mode; add **Tutor this section** as an overflow later if RQ03 needs a louder entry.

3. **Home as ritual (S).** If due > 0, Review card is visually first and includes ~minutes; Resume stays. Honesty rule on continue-reading. Optional "Also reading" row only when a second book has progress. No new gamification.

4. **Exports hub (S).** Account: Download notes (Obsidian), and a line that Anki export lives on each book. Notes page keeps the vault button. Bookshelf overflow keeps `.apkg`. Same endpoints, new doors.

5. **Highlights list (S–M).** Per-book list in the Notes dock (quote, section, jump). No new domain; `GET /api/sources/{id}/highlights` already exists. Global highlights page: defer.

6. **Copy pass (S).** Nav remains Bookshelf or becomes Library — pick one word and use it in the H1, empty states, and upload form. "Teach" → "Tutor" in the Chat control only. "Export vault" → "Download notes (Obsidian)." Landing loop explanation belongs to RQ12; this cycle only fixes in-app nouns.

7. **Defer.** `/library` URL alias; global conversation inbox; NotebookLM-style Studio; queue-first Home (Option C); deleting `/notes` or `/review`. Those are inversions, not polish.
