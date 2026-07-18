# v3-notes-foundation Specification (RFC-003 Cycle E; bound by ADR-0026 decisions 1–3, scope 7)

## Problem Statement

ADR-0026 is accepted but nothing the user thinks while studying leaves a trace: no highlights, no notes, no way to jump from a thought back to the exact passage. Cycle E ships capture + organize on the canonical corpus.

## Goals

- [ ] Select text in the reader → create a highlight (optionally with a note) that survives re-ingestion via the ADR-0026 anchor payload and 4-tier exact reconcile cascade.
- [ ] Notes as whole-Markdown documents with tags, wikilink-derived backlinks, and a list/detail UI (textarea + streamdown preview).
- [ ] Orphaned anchors surfaced, never destroyed; jump-back from any anchored note to the passage.

## Out of Scope

| Feature | Reason |
|---|---|
| Notes in retrieval/RAG, note→quiz, export | Cycle F (ADR-0026 scope 7) |
| Fuzzy re-anchoring, graph UI, CodeMirror, notebooks hierarchy | Deferred by ADR-0026 (notebooks explicitly deferred here — D-1) |
| Editing highlights' selection after creation | Delete + recapture; keeps anchors immutable |
| Backfilling block hashes for existing corpora | Filled on next re-ingest; quote tiers cover unhashed blocks (D-3) |

## Assumptions & decisions (auto, ship-cycle; details context.md → AD-109..114)

| Decision | Default |
|---|---|
| D-1 | `notebooks` table deferred out of E entirely (tags + links suffice; ADR marks it optional) |
| D-2 | Selection→anchor resolution happens SERVER-SIDE at save: client sends section anchor + exact quote + 32-char prefix/suffix + markdown offsets; server locates block, computes hash/ordinal/offsets. Section read API unchanged |
| D-3 | `corpus_blocks.content_hash` (normalized-text sha256) added by migration, computed at build time, nullable; no backfill |
| D-4 | `note_links` derived from `[[wikilink]]` parsing on save (title match, case-insensitive); tags explicit via API field, not inline parsing |
| D-5 | One concept: capture creates a Note (body optional/empty) + one NoteAnchor; a "highlight" is a note with an anchor; notes may hold 0..N anchors (ADR open question resolved for E) |
| D-6 | Anchor statuses reuse quiz vocabulary: active/stale/orphaned (relocation stays active, rewrites anchor) |

## Acceptance Criteria

### P1 Schema + anchoring core (Phase A)
1. (NF-01) Migration creates `notes` (id, user_id FK→users CASCADE, title, body_markdown, timestamps), `note_anchors` (id, note_id FK→notes CASCADE, source_id UUID **no FK**, source_title snapshot, section anchor, section_path JSONB, block_hash nullable, block_ordinal nullable, start_offset/end_offset nullable, quote_exact, quote_prefix, quote_suffix, status default 'active', timestamps), `tags` (id, user_id, name unique per user), `note_tags` (note_id, tag_id PK pair), `note_links` (id, note_id FK CASCADE, target_note_id nullable FK **SET NULL**, target_text) — copying the 0008 snapshot shape; NO FK from note tables to corpus_*/sources; deleting a source never deletes notes/anchors.
2. (NF-02) `corpus_blocks.content_hash` column added; corpus build computes it (normalize_text + sha256) for every block; existing rows stay NULL.
3. (NF-03) Anchor resolution service: given (section anchor, quote, prefix/suffix, offsets-in-markdown) it resolves the owning block (hash, ordinal, in-block offsets) against the stored blocks, falling back to quote-only payload when block resolution fails; pure application logic, unit-tested per ADR tier semantics.

### P1 Domain + application (Phase B)
4. (NF-04) Entities/ports follow house conventions (frozen dataclasses, Protocol repos, Connection-taking implementations); note body length capped by `LEARNY_NOTES_MAX_BODY_CHARS` (default 100000) at validation.
5. (NF-05) CreateNote/UpdateNote/DeleteNote/GetNote/ListNotes use cases: owner-scoped (authorization identical to sources), update rewrites derived links/tags indexes in the same transaction; wikilinks resolve by note-title match (case-insensitive), unresolved keep target_text with NULL target.
6. (NF-06) CaptureHighlight use case: validates the section belongs to an owned source's corpus, resolves the anchor payload (NF-03), creates note+anchor atomically; empty body allowed.
7. (NF-07) ReconcileNoteAnchors runs as an ingestion step immediately after quiz reconcile (sibling wiring in the worker), applying the ADR 4-tier exact cascade: (1) section by anchor/alias + block by hash → active (offsets valid); (2) quote-with-context in resolved section → active (payload rebound); (3) quote across document → active (anchor rewritten to found section, alias-aware); (4) else orphaned — row kept, status only; never touches note bodies; stale when anchor lives but quote gone.
8. (NF-08) WHEN a source is deleted THEN its note_anchors become orphaned (status update via the same reconcile semantics or deletion hook), and notes remain fully readable from snapshots.

### P1 Web API (Phase C)
9. (NF-09) Router: POST /api/notes (create, incl. optional capture payload), GET /api/notes (list w/ tag filter), GET/PATCH/DELETE /api/notes/{id}, POST /api/sources/{source_id}/highlights (capture from reader), GET /api/notes/{id}/backlinks; auth + rate_limit_notes + origin/CSRF on writes; error mappings (NoteNotFound→404 etc.) registered centrally.
10. (NF-10) Views expose anchor status + jump-back data (source_id, anchor, quote) so the UI can render orphan badges and passage links.

### P1 Frontend (Phase D)
11. (NF-11) lib/notes.ts client mirroring quiz.ts conventions (CSRF echo, typed errors); vitest coverage per client convention.
12. (NF-12) Reader selection capture: onMouseUp popover ("Highlight" / "Highlight + note") in section-reader, sending quote + context + offsets; success links to the created note.
13. (NF-13) Notes screens under (app)/notes: list (title, tags, anchor-status badges, tag filter) and detail (textarea editor + streamdown preview toggle, tags editing, backlinks panel, anchored-passages list with jump-back links `read?anchor=`); sidebar gains a Notes entry beside Review.
14. (NF-14) Orphaned anchors render a distinct badge with the quote snapshot shown from the note detail (never hidden).

### Edge cases
- Selection spanning multiple blocks → anchor binds to the first block, quote captures the full selection (documented; reconcile quote tiers handle it).
- Duplicate tag names differing by case → normalized to lowercase, unique per user.
- Wikilink to own note (self-link) → ignored.
- Note deleted → its note_links rows cascade; inbound links from other notes keep target_text with NULL target (SET NULL).
- Capture on a section whose corpus was replaced mid-flight → validation re-reads section; stale anchor input → 409.

## Traceability: NF-01..03 Phase A · NF-04..08 Phase B · NF-09..10 Phase C · NF-11..14 Phase D. Verifier after D.

## Success Criteria
- [ ] Full-cycle demo path: read → select → highlight+note → re-ingest same book → anchor still resolves (integration test) → orphan path proven with a mutated corpus.
- [ ] Backend + frontend suites green (baselines 1040 / 174 tests grow); ruff + tsc clean.
