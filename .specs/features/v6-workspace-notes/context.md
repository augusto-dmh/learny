# `v6-workspace-notes` — decisions

RFC-006 Cycle D, second half (the notes/review axis). Decisions are auto-made under the
`learny-ship-cycle` autonomy contract: each states the options with why-recommend and
why-not, the choice, and the consequence. Nothing here should need the conversation to
be understood later.

---

## D-1 — The dock's tab model widens; `PanelMode` does not

**Context.** `reader-panel.tsx:36` declares `PanelMode = "ask" | "teach"`. That union
does triple duty: it labels the tablist, and it keys two `Record<PanelMode, …>` maps
holding per-surface conversation state (`activeIds`, `revisions`, `reader-panel.tsx:96,101`),
and it is the `?panel=` URL value (`lib/read-url.ts:15`). Notes and Review are tabs in
the same strip but have no conversation state at all.

| Option | Why | Why not |
| --- | --- | --- |
| **A. New `DockTab = PanelMode \| "notes" \| "review"`; `PanelMode` stays the conversation subset** ✅ | The conversation maps keep a key space where every key means something; `ConversationList` renders only while the active tab is a `PanelMode`, which is the actual rule | One more type to hold in your head |
| B. Widen `PanelMode` to four values | One type, fewer names | Gives `activeIds`/`revisions` two keys that can never hold a conversation, and makes "is this a conversation surface?" an implicit convention instead of a type |
| C. Keep two separate strips (conversations vs tools) | No type change | Contradicts the artifact — it is one four-tab strip — and doubles the chrome in a 26rem column |

**Chosen: A.** *Consequence:* `?panel=` accepts four values; an unknown value must still
fall back exactly as it does today rather than throwing.

---

## D-2 — Provenance is enforced on the server, and the anchored path absorbs the fallback

**Context.** Two creation routes exist: `POST /api/notes` (title/body/tags — no anchor,
`web/notes.py:259`) and `POST /api/sources/{source_id}/highlights` (note + anchor,
atomically, `web/notes.py:396`). The rootless route has exactly two callers:
`notes-screen.tsx:82` (the title-only form the RFC names) and the **fallback** inside
`saveAnswerAsNote` (`lib/answer-notes.ts:95-100`), which creates an anchorless note
carrying an "Open in book" link when the citation yields no quote **or** when capture
returns 409 `stale_capture`.

That fallback is why "retire title-only creation" is not a one-line deletion: removing
the rootless route without touching it would turn a rare-path safety net into a lost
answer.

| Option | Why | Why not |
| --- | --- | --- |
| **A. Make the quote optional on the anchored capture, re-point the fallback there, delete the rootless route** ✅ | Every note ends up with an anchor, which is the RFC's literal words ("both carry anchors"); the fallback keeps working and gets *better* (anchored instead of rootless); leaves exactly one creation path | Requires `CaptureHighlight` to skip block-binding when there is no quote — a real change to a correctness-critical service |
| B. Delete the rootless route, surface the 409 as an error, no fallback | Smallest change | Loses the one-click save in precisely the flaky case the fallback exists for |
| C. Enforce provenance in the UI only | Cheapest; zero backend risk | The invariant gets no sensor and one `curl` re-opens it — the spec rejected this on those grounds |
| D. Accept "anchor **or** source reference" as provenance | Keeps the fallback untouched | Invents a second provenance kind and weakens "every note keeps the passage it came from" to "every note remembers a book" |

**Chosen: A.** An anchor-only capture on a section whose text moved is exactly the
**orphaned anchor** ADR-0026 already designs for — kept forever, rendered from whatever
snapshot it has, resurrectable by a later reconcile. So the honest record is a
section-level anchor, not a rootless note.

*Consequence, stated plainly:* **a book-independent note can no longer be created.**
Every note is born attached to a book. Notes created before this change keep working
untouched (spec P3 AC 4). If the second-brain direction later needs standalone synthesis
notes, that is a new decision, not a regression of this one — and it is surfaced at the
merge gate rather than buried here.

---

## D-3 — The Review tab renders the shipped review screen, scoped

**Context.** `ReviewScreen` (`components/review-screen.tsx:60,63,85`) already takes an
optional `sourceId` and forwards it to `getDueReviews`. `GET /api/reviews/due` already
accepts `source_id` and returns `total_due` (`web/quiz.py:364-378`).

| Option | Why | Why not |
| --- | --- | --- |
| **A. Render `ReviewScreen sourceId={id}` inside the tab** ✅ | Grading happens without leaving the book — the artifact's promise — and reuses shipped, tested UI; the backend work is zero | The screen was laid out for a full page and must survive a 26rem column |
| B. Show a count + a link to `/review?source_id=` | Trivial | Navigating away is the exact friction the workspace exists to remove |
| C. Build a compact dock-native grader | Fits the column perfectly | Builds the grading UI a second time — criterion 1's "no UI built twice" |

**Chosen: A.** *Consequence:* the review screen gains a narrow-container obligation; any
layout fix belongs to the shared component, not a dock-only fork.

---

## D-4 — Notes-by-source is a `source_id` filter on the notes list, not the highlights list

**Context.** `GET /api/sources/{id}/highlights` is already per-source and already carries
the origin note's title (AD-140) — it is the tempting reuse. But it is **anchor-shaped**:
one row per anchor, ordered by anchor. `GET /api/notes` is note-shaped and ordered
newest-edited-first, but filters only by `tag` (`web/notes.py:290-302`).

| Option | Why | Why not |
| --- | --- | --- |
| **A. Add `source_id` to `GET /api/notes`** ✅ | Note-shaped rows satisfy "a multi-anchored note appears once" (WSN-03) by construction and keep the list's ordering; the same endpoint then serves the dock tab *and* `/notes`' new book filter; mirrors the shipped `reviews/due?source_id=` convention | The summary must start carrying a representative anchor, so the read model grows |
| B. Reuse `GET /api/sources/{id}/highlights` | Zero new backend | A note anchored twice in the book renders twice, and ordering is by anchor — both contradict the spec; and `/notes` still gets no filter, so P4 needs the work anyway |
| C. A new dedicated `/api/sources/{id}/notes` | Clean name | A third list endpoint over the same rows, and `/notes` still needs its own filter |

**Chosen: A.** The representative anchor for a note under a `source_id` filter is its
**earliest-created anchor on that source** — "the passage it came from", which is what
the row claims to show. Page number is derived server-side via the shipped
`page_at(words_before_row(index, row_idx), words_per_page)` (`application/reading.py:119`,
AD-189 book-global numbering), never recomputed on the client.

*Consequence:* an orphaned anchor has no resolvable row index, so its row shows the quote
with **no page** (spec WSN-15) rather than a fabricated one.

---

## D-5 — Ownership failures stay indistinguishable

`GET /api/notes?source_id=<not mine>` must answer **404**, the same as a source that does
not exist — the disclosure rule every other source read already follows
(`get_source_highlights`, `web/notes.py:433`). *Rejected:* returning an empty list, which
silently tells a caller "that source is real, just not yours" on one endpoint while every
neighbour 404s.

---

## D-6 — Counts come from the surfaces that already answer them

Notes tab count = the length of the source-filtered notes list the tab already fetches.
Review tab count = `total_due` from the due query the tab already fetches. **No new count
endpoints.** A zero count renders as no badge rather than "0" (spec edge case), and both
are queue inventories, never streaks or achievement figures (I-7).

---

## D-7 — Execution: four phases, one worker each, all Opus

| Phase | Scope | Model |
| --- | --- | --- |
| A | Provenance: optional quote on capture, rootless route deleted, legacy anchorless notes preserved | Opus — atomicity + authorization + a deletion |
| B | Notes read model: `source_id` filter, representative anchor, page projection, 404 rule, ordering | Opus — ownership disclosure + a total order |
| C | Dock: `DockTab` widening, Notes tab, Review tab, counts, empty states, `?panel=` | Opus — the shared `reader-panel.tsx` seam |
| D | `/notes` cross-book filter + title-only form retirement + client cleanup | Opus — retires the path B and A depend on |

No unit passes the Haiku-safe test: A and B carry correctness invariants, C touches the
panel the previous cycle just reworked, D deletes a shipped path. Verifier is Opus and is
never downshifted. D runs last because deleting the title-only form is only safe once A
has removed the route behind it and C has proven the dock reads the new list.
