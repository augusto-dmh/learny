# `v6-workspace-notes` — Design

Decisions and their rejected alternatives live in `context.md` (D-1…D-7). This file is
the architecture: seams, contracts, invariants, and the phase split.

## Shape of the change

Nothing new is stored. `note_anchors` already carries everything the two new surfaces
need — `source_id`, `source_title`, `anchor`, `section_path`, `quote_exact`, `status`,
`created_at` (`infrastructure/db/metadata.py:617-645`) — and `GET /api/reviews/due`
already answers the Review tab. **This cycle adds no migration.**

The work is: one creation path instead of two, one list endpoint that can be scoped to a
book, and two dock tabs that consume them.

## Seams

| Seam | Location |
| --- | --- |
| Rootless create (to be deleted) | `infrastructure/web/notes.py:259` `create_note` |
| Anchored create (to absorb it) | `infrastructure/web/notes.py:396` `capture_highlight` → `application/notes.py:274` `CaptureHighlight` |
| Notes list (to gain `source_id`) | `infrastructure/web/notes.py:290` `list_notes` → `application/notes.py:248` `ListNotes` → `repositories.py:1782` `list_summaries` |
| Notes list read model | `domain/entities.py:1175` `NoteSummary` (note, tags, anchor_statuses) |
| Page derivation | `application/reading.py:119` `page_at`, `:92` `words_before_row` |
| Due queue (unchanged) | `infrastructure/web/quiz.py:364` — already `source_id` + `total_due` |
| Dock | `components/reader-panel.tsx:36` `PanelMode`, `:96/:101` per-surface maps, `:176` tablist |
| Dock URL param | `lib/read-url.ts:15` `panel` |
| Reader host | `components/chapter-reader.tsx:325,611,828` |
| Review UI (reused as-is) | `components/review-screen.tsx:60,63,85` — already takes `sourceId` |
| Answer→note | `lib/answer-notes.ts:56` `saveAnswerAsNote`, fallback at `:95-100` |
| Title-only form (to be retired) | `components/notes/notes-screen.tsx:82` |
| Notes client | `lib/notes.ts:119` `createNote`, `:141` `listNotes`, `:242` `captureHighlight` |

## Contracts after this cycle

**`POST /api/sources/{source_id}/highlights`** — `quote_exact` becomes optional
(defaulting to `""`). With a quote, behaviour is unchanged: the selection is bound
against the section's blocks and a mismatch is `StaleCaptureTarget` → 409. Without a
quote, block binding is skipped, `block_hash`/`block_ordinal`/`start_offset`/`end_offset`
stay NULL, and the anchor is section-level. Section resolution and ownership are
unchanged in both cases.

**`POST /api/notes`** — deleted (AD-204 precedent: outright, no deprecation window).

**`GET /api/notes?source_id=&tag=`** — `source_id` optional. When present: the caller
must own the source or the response is **404** (D-5), and the list returns only notes
with ≥1 anchor on that source, each carrying a representative anchor. Ordering stays
`updated_at DESC, id` — already total.

**`NoteSummary`** gains a nullable representative anchor (the note's **earliest-created**
anchor on the filtered source: `anchor`, `section_path`/section title, `quote_exact`,
`status`, and a derived `page`). It is populated only under a `source_id` filter —
unfiltered `/notes` has no single book to resolve a page against.

## Invariants (each needs a sensor; the test's shape is the worker's call)

- **I-1** A note can no longer be created without an anchor — no route accepts it.
- **I-2** A capture without a quote still creates note **and** anchor atomically; a failure persists neither.
- **I-3** Notes created before this cycle, having no anchor, still list, open, edit, and delete.
- **I-4** A note anchored twice to one book appears **once** in that book's list.
- **I-5** `source_id` the caller does not own → 404, byte-identical to an unknown source's response.
- **I-6** An orphaned anchor still yields a row rendered from its quote snapshot, with no page number, and is never dropped.
- **I-7** The notes list order is total and unchanged (`updated_at DESC, id`).
- **I-8** Page numbers come from `page_at`/`words_before_row` — book-global (AD-189), never recomputed client-side, never derived from percent.
- **I-9** Switching to Notes/Review does not disturb the ask/teach conversation state, and `?panel=` with an unknown value falls back exactly as today.
- **I-10** The due count is a queue inventory only — no streak, badge, or fallen-behind copy (I-7 gamification cap).

## Traps

Knowledge a worker cannot derive from the seams:

1. **`note_anchors.quote_exact` is `NOT NULL`** (`metadata.py:641`). "Optional quote" means storing `""`, not NULL. The block-binding columns are *already* nullable for the unresolved case — an empty quote plus NULL binding is the schema's existing shape for a section-level anchor, which is why this needs no migration.
2. **`saveAnswerAsNote` has a fallback that must be re-pointed, not deleted** (`lib/answer-notes.ts:95-100`). It fires when the citation yields no first paragraph *or* on a 409 `stale_capture`. Re-point it at the anchor-only capture. Deleting it silently loses an answer in the exact case it was written for. It also carries a live `SPEC_DEVIATION` comment about the error kind (`"stale_capture"`, not `"stale"`) — keep that behaviour.
3. **`list_summaries` builds tags and statuses with separate `IN` queries after the main select** (`repositories.py:1782-1824`). The representative anchor must follow that established shape; do not turn the list into a row-per-anchor join, which is exactly what would break I-4.
4. **`PanelMode` is not just a label** — it keys `activeIds`/`revisions` (`reader-panel.tsx:96,101`) and is the `?panel=` value. Widening it instead of adding `DockTab` puts keys in those maps that can never hold a conversation (D-1).
5. **`ReviewScreen` was laid out for a full page.** It is reused as-is inside a 26rem dock; any layout fix belongs to the shared component, not a dock-only fork (D-3).
6. **Ownership failures must stay indistinguishable** — the neighbouring source reads collapse missing and non-owner to the same 404 (`web/notes.py:433`). An empty list would leak existence.

## Phases

| Phase | Delivers | Requirements |
| --- | --- | --- |
| **A** | Optional quote on capture; `POST /api/notes` deleted; legacy anchorless notes preserved | WSN-08, WSN-09, WSN-12, WSN-16 |
| **B** | `source_id` filter, representative anchor + derived page, 404 rule, dedup, ordering | WSN-01, WSN-02, WSN-03, WSN-10, WSN-11, WSN-13, WSN-14, WSN-15 |
| **C** | `DockTab`, Notes tab, Review tab, counts, empty states, `?panel=` | WSN-01…WSN-07 (frontend), WSN-05, WSN-06, WSN-07 |
| **D** | `/notes` book filter; title-only form retired; `createNote` client removed | WSN-04 (copy), WSN-10 (UI), P4 |

Sequencing: A removes the route D's form depends on; B builds the list C and D both
read; C proves the dock consumes it; D retires the old surface last — the same
"retire only once the replacement is proven" ordering as AD-209.
