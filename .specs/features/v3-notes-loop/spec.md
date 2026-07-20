# v3-notes-loop Specification (RFC-003 Cycle F; bound by ADR-0026 decisions 4–6, scope 7)

## Problem Statement

Cycle E shipped capture + organize: highlights and notes exist, anchored and reconciled, but they are inert — they never inform an answer, never become review material without manual card-writing, and cannot leave the app. Cycle F closes the second-brain loop: notes join retrieval, notes feed active recall, and the whole corpus of personal knowledge exports to an Obsidian vault. This completes RFC-003 and versions the product 0.3.0.

## Goals

- [ ] Cited Q&A can draw on and distinctly cite the user's own notes, behind an "include my notes" toggle.
- [ ] A note can be promoted to review cards in one action; editing the note never disturbs a card's schedule.
- [ ] Notes + highlights export as a deterministic, Obsidian-compatible Markdown vault.
- [ ] v3 closes: README refresh, v3 retrospective, version 0.3.0.

## Out of Scope

| Feature | Reason |
| --- | --- |
| Paragraph-level note chunking for retrieval | ADR-0026 d4: v1 embeds whole notes; chunking is the recorded upgrade |
| Fuzzy re-anchoring, graph UI, CodeMirror editor, block/outliner model | ADR-0026 scope 7 defers beyond v3 |
| Vault sync / import / round-trip | ADR-0026 d6: export is a one-way projection, never a sync |
| Notes in *teaching* retrieval defaulting on | ADR-0026 d4: off for teaching until proven |
| MCQ, FSRS optimizer, eval dashboard, BYOK, vector DB | RFC-003 exclusions stand |
| Demo media capture (screen recordings) | User-gated since v2 Cycle G; not a build artifact |
| Auto-creating *new* cards when an edited note grows | AD-144: regenerate-and-match only updates matched items; re-promotion is the explicit path to new cards |

---

## Assumptions & Open Questions

All gray areas auto-decided per the ship-cycle auto-decision rule; full option sets in `context.md` (AD-143..AD-148).

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| Which notes are in scope for a source-scoped Q&A (AD-143) | All the user's notes (cross-source), RRF relevance filters | Second-brain value is cross-book synthesis; anchored-only would exclude most notes | auto |
| When regenerate-and-match runs (AD-144) | Only for notes with note-derived items ("promoted"), async on save; updates matched items in place, flags unmatched, never creates/deletes | ADR d5 edit-stability; unpromoted notes have nothing to match | auto |
| Note deletion vs note-derived items (AD-145) | Items survive (`note_id` SET NULL); provenance reads by join and is absent once severed, item renders from its own stored text | Inverse-cascade + AD-136 join-provenance precedents | auto |
| Export delivery (AD-146) | Single `GET /api/export/vault` zip download, fixed zip timestamps for determinism | Matches Anki-export seam; determinism testable byte-for-byte | auto |
| Toggle transport (AD-147) | Request flag `include_notes`; server defaults on for Q&A, off for teaching; client persists preference locally | Smallest change; no server-side prefs table for one boolean | auto |
| Note-derived item linkage (AD-148) | New `origin='note'` value + `note_id` FK (SET NULL) + provenance snapshot columns reused | Third identity mode alongside deck/highlight; minted row id is the stable identity per ADR d5 | auto |

**Open questions:** none — all resolved or logged above.

---

## User Stories

### P1: Ask my books *and* my notes ⭐ MVP

**User Story**: As a reader, I want Q&A answers to draw on my own notes and cite them distinctly, so my accumulated thinking compounds instead of sitting inert.

**Acceptance Criteria**:

1. WHEN a note is created or its body updated THEN the system SHALL (asynchronously) store a whole-note embedding (`vector(1536)`, model recorded) and maintain a tsvector over title+body, without the note ever entering `corpus_chunks`. (NL-01)
2. WHEN a Q&A question is asked with notes included (the default) THEN retrieval SHALL fuse note candidates into the existing hybrid query as two additional RRF arms (note-semantic, note-lexical) with a notes weight and smaller per-arm limits than the book arms, and the fused ranking SHALL be deterministic for fixed inputs. (NL-02)
3. WHEN the generated answer cites a note THEN the citation SHALL be visibly distinct from book citations ("your note" presentation, note title, link to the note detail), while book citations render unchanged. (NL-03)
4. WHEN `include_notes` is false THEN no note content SHALL appear in evidence, prompt context, or citations; WHEN the flag is absent THEN Q&A SHALL default it true and teaching SHALL default it false. (NL-04)
5. WHEN retrieval runs THEN only the requesting user's notes SHALL be candidates — never another user's, regardless of source ownership. (NL-05)
6. WHEN a note has an empty body THEN it SHALL be excluded from both note arms; WHEN a note's embedding is not yet written (async lag) THEN the lexical note arm SHALL still function and the query SHALL not error. (NL-06)
7. WHEN a note is deleted THEN it SHALL stop appearing in retrieval immediately (index rows die with the note). (NL-07)

**Independent Test**: Create a note containing a distinctive fact absent from the book; ask about it with the toggle on → answer cites "your note"; toggle off → NOT_FOUND path or book-only citations.

---

### P1: Promote a note to review, edit without fear ⭐ MVP

**User Story**: As a learner, I want one action that turns a note into scheduled review cards, and I want editing my note to never wreck those cards' schedules.

**Acceptance Criteria**:

1. WHEN the user triggers "add to review" on a note THEN the system SHALL generate card suggestions from the note body through the existing quiz-generation port with groundedness QC verified against the note body (the note IS the source), carrying book-anchor context when the note is anchored. (NL-08)
2. WHEN a suggested card is accepted THEN the stored item SHALL have `origin='note'`, a creation-minted stable identity (its row id), a rewritable `content_key` fingerprint (no uniqueness collision with deck-card semantics), note provenance (note id, title snapshot, excerpt), and FSRS scheduling starting fresh — and it SHALL appear in the due queue like any other card. (NL-09)
3. WHEN a promoted note's body is saved THEN an async regenerate-and-match step SHALL update matched items' question/answer in place under their existing item id, and the items' scheduling rows and review-log rows SHALL be unchanged by the edit (byte-equal before/after). (NL-10)
4. WHEN regenerate-and-match cannot match an existing item to the edited note THEN the item SHALL be marked note-changed (not deleted, not rescheduled). (NL-11)
5. WHEN a note-derived item is presented at review after its note changed (matched-update or unmatched flag) since the item was last reviewed or created THEN the review UI SHALL show a "your note changed" badge with the note linked; the badge SHALL offer an explicit schedule-reset action, and reset SHALL occur only through that action. (NL-12)
6. WHEN a note-derived item is reviewed THEN provenance (note title + excerpt, linking to the note) SHALL show at review time, mirroring highlight-card provenance. (NL-13)
7. WHEN a promoted note is deleted THEN its items SHALL survive and keep their schedules, remaining renderable from their own stored text; the note-title provenance line is absent once severed (join-based, AD-136 precedent). (NL-14)
8. WHEN "add to review" is triggered on a note with existing note-derived items THEN the flow SHALL offer suggestions again without duplicating accepted items (dedup against live items for this note). (NL-15)

**Independent Test**: Promote a two-fact note → accept 2 cards → review one → edit the note → the reviewed card's due date/stability unchanged, badge shows on next review, explicit reset works.

---

### P1: Take my knowledge with me (Obsidian vault export) ⭐ MVP

**User Story**: As a note-taker wary of lock-in, I want a one-click export of all my notes and highlights as an Obsidian vault so my knowledge is mine, forever, offline.

**Acceptance Criteria**:

1. WHEN the user requests a vault export THEN the system SHALL return a zip containing a `Learny/` folder with one Markdown file per book that has highlights and one file per note. (NL-16)
2. WHEN a book file is rendered THEN each highlight SHALL appear as a `> [!quote]` callout titled with its section path + page span, carrying a stable `^lh-<id>` block anchor, ordered by position in the book; orphaned highlights SHALL render from their quote snapshots in a clearly-labeled trailing section. (NL-17)
3. WHEN a note file is rendered THEN it SHALL carry Obsidian Properties frontmatter using only namespaced `learny-*` keys (id, created, updated, tags, source titles for anchored notes) and the body SHALL be the stored Markdown verbatim — wikilinks untouched; note anchors SHALL render as links to the owning book file's `^lh-<id>` block when the anchor is exported as a highlight, else as a cited quote. (NL-18)
4. WHEN the same data is exported twice THEN the two zips SHALL be byte-identical (fixed zip timestamps, stable file ordering, deterministic filenames with collision suffixes). (NL-19)
5. WHEN the export runs THEN it SHALL contain only the requesting user's notes and highlights. (NL-20)
6. WHEN a filename would collide or contain characters invalid in Obsidian/OS paths THEN the exporter SHALL sanitize and de-collide deterministically. (NL-21)

**Independent Test**: Export with 2 books, 3 highlights, 2 linked notes → unzip → files open in Obsidian with working `[[wikilink]]` and `#^lh-` deep links; re-export → identical bytes.

---

### P2: Close v3

**User Story**: As the project owner, I want the release artifacts current so v3 is a coherent, presentable increment.

**Acceptance Criteria**:

1. WHEN v3 closes THEN README SHALL describe the notes/second-brain feature set (capture → retrieve → reinforce → export) accurately. (NL-22)
2. WHEN v3 closes THEN `docs/retrospectives/` SHALL contain a v3 retrospective following the v2 retrospective's form. (NL-23)
3. WHEN v3 closes THEN `backend/pyproject.toml` and `frontend/package.json` SHALL both read version `0.3.0`. (NL-24)

---

## Edge Cases

- WHEN the notes arms are enabled but the user has zero notes THEN retrieval SHALL behave exactly as book-only (no errors, no empty-arm artifacts).
- WHEN a note body exceeds the embedding provider's input limit THEN embedding SHALL truncate deterministically (recorded) rather than fail the save.
- WHEN regenerate-and-match runs concurrently with a second note save THEN the last-completed regeneration SHALL reflect the newest body (stale regenerations must not clobber newer item text; guard by comparing note `updated_at`).
- WHEN promotion generation fails QC for every suggestion THEN the user SHALL get an explicit empty-suggestions response, not an error.
- WHEN the vault export encounters a note titled identically to another THEN both export with deterministic de-collision suffixes.
- WHEN an anchored note's book was deleted THEN its note file still exports (snapshot titles), and its highlights render from quote snapshots.

## Implicit-Requirement Dimensions (sweep)

| Dimension | Resolution |
| --- | --- |
| Input validation & bounds | Note-arm limits capped server-side; export sanitizes filenames (NL-21); embedding truncation edge case |
| Failure / partial-failure | Async embed/regenerate failures leave prior state intact and retryable (Celery retry conventions); export is a single atomic response |
| Idempotency / retry / duplicates | Re-promotion dedups against live items (NL-15); re-accept identity via minted id; export idempotent by determinism (NL-19); embed task idempotent per note+model |
| Auth boundaries & rate limits | NL-05, NL-20; all new endpoints behind existing auth; promotion reuses quiz throttle conventions |
| Concurrency / ordering | Stale-regeneration guard (edge case); RRF ordering deterministic (NL-02) |
| Data lifecycle / expiry | NL-07 (index dies with note), NL-14 (items survive note deletion), no TTLs |
| Observability | Async tasks log through existing worker/job logging conventions; N/A beyond because no new infra |
| External-dependency failure | Embedding provider failure → retry path, lexical arm still serves (NL-06); generation failure → explicit empty suggestions |
| State-transition integrity | Badge/reset transitions (NL-11/NL-12); scheduling untouched by edits (NL-10) is the core invariant |

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| --- | --- | --- | --- |
| NL-01..NL-07 | P1 notes-in-retrieval | Design | Pending |
| NL-08..NL-15 | P1 note→quiz | Design | Pending |
| NL-16..NL-21 | P1 vault export | Design | Pending |
| NL-22..NL-24 | P2 close v3 | Design | Pending |

**Coverage:** 24 total, 0 mapped to tasks yet.

## Success Criteria

- [ ] A distinctive-fact note is cited as "your note" in a Q&A answer; toggle off removes it.
- [ ] Edit-after-promotion leaves scheduling rows byte-identical; badge + explicit reset work.
- [ ] Exported vault opens in Obsidian with working wikilinks and block deep-links; re-export is byte-identical.
- [ ] Backend + frontend suites green; version 0.3.0.
