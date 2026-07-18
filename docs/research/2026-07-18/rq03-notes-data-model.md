# RQ-03 — Notes Data Model for Learny (PostgreSQL only)

- Date: 2026-07-18 (research executed 2026-07-17)
- Status: Research report (input to a future notes-cycle RFC/ADR; nothing here is binding)
- Question: How should Learny model notes in PostgreSQL only — whole documents (Obsidian file model) vs blocks/outliner (Logseq/RemNote block model)? How should links/backlinks/tags, ordering, and nesting be represented without a graph DB? How do the quiz-item snapshot semantics (no corpus FK, `content_key` upsert, never lose user state on re-ingest) translate to notes anchored to books?

## 1. Findings

### 1.1 The document model in the wild: Obsidian

Obsidian stores every note as a Markdown-formatted plain-text file in a local vault folder; the app is explicitly a viewer/editor over files the user owns ("files over app"). Links, backlinks, graph view, and outline are **not** stored alongside the notes — they are powered by a locally maintained **metadata cache**, a derived index that Obsidian keeps synchronized with the vault and that can be rebuilt when it drifts out of sync ([How Obsidian stores data](https://obsidian.md/help/data-storage), accessed 2026-07-17; [Vault developer docs](https://docs.obsidian.md/Plugins/Vault), accessed 2026-07-17).

The transferable lesson is the split of responsibilities, not the filesystem: **the note body is the single source of truth; links/backlinks/tags are a disposable derived index re-extracted from the body**. In PostgreSQL terms that is a `notes` table holding the full Markdown body plus derived side tables (`note_links`, `note_tags`) that are dropped and re-populated whenever a note is saved. Backlinks are then just a reverse query on the derived link table — no graph store involved.

Costs of the document model, visible in Obsidian itself: references are note-granular (heading/block references exist but are addressed by fragile in-body `^block-id` markers), there is no transclusion-with-identity, and any block-level feature (e.g., per-paragraph SRS) has to invent its own addressing scheme on top.

### 1.2 The block model in the wild: Logseq — and what its DB migration teaches

Logseq is the most instructive case because it ran both models in production and migrated from a Markdown-file-backed outliner to a database version (SQLite persistence with an in-memory DataScript graph) ([logseq/docs db-version.md](https://github.com/logseq/docs/blob/master/db-version.md), accessed 2026-07-17). In the DB version:

- Pages and blocks unify into **nodes** ("a node is a new term for a page or block because the two now behave similarly").
- Hierarchy is a plain parent pointer: `:block/parent` is an indexed ref; `:block/page` is an indexed ref to the containing page; references are `:block/refs`, a cardinality-many ref ([schema.cljs in logseq/logseq `deps/db`](https://github.com/logseq/logseq/blob/master/deps/db/src/logseq/db/frontend/schema.cljs), accessed 2026-07-17). This is exactly an adjacency list plus a link table — nothing a relational DB cannot express.
- **Sibling ordering changed from a linked list to an ordering key**: "the attribute `:block/left` no longer exists and has been replaced by `:block/order`" ([db-version-changes.md](https://github.com/logseq/docs/blob/master/db-version-changes.md), accessed 2026-07-17). Logseq maintains its own fractional-indexing library ([logseq/clj-fractional-indexing](https://github.com/logseq/clj-fractional-indexing), a Clojure port of rocicorp/fractional-indexing, accessed 2026-07-17); secondary sources describe `:block/order` as a fractional index key, and the schema marks it `:db/index true` with no further comment (fractional-index wiring of `:block/order` specifically: (unverified) against a primary statement, though the maintained library and the `:block/left` removal make it strongly implied).
- Properties became first-class typed entities and tags became database relationships, enabling queries the Markdown files could not support.

Two lessons: (a) a serious outliner at scale abandoned prev-pointer linked-list ordering — linked lists make "read children in order" a recursive walk and make corruption (broken chains) possible, which Logseq's file version was known for; (b) the block model's payoff is block-identity features (block refs, embeds, per-block properties, real-time collaboration granularity), and it was expensive enough that Logseq needed a multi-year re-architecture to do it properly.

### 1.3 The block model in the wild: RemNote

RemNote is an outliner where the universal unit is the **Rem**; the plugin API operates almost entirely on Rem objects with parent/children navigation, and documents/folders are roles a Rem can play rather than separate types ([Rem API docs](https://plugins.remnote.com/advanced/rem_api), accessed 2026-07-17; the stronger claim "every bullet is a Rem and documents are just Rems" is consistent with the API surface but not stated verbatim in the pages fetched — (unverified)). RemNote's signature feature is that **flashcards attach to blocks**: any Rem can carry SRS cards, and hierarchy provides card context ([RemNote help: structuring content](https://help.remnote.com/en/collections/3939579-structuring-content), accessed 2026-07-17).

Relevance to Learny: block-level SRS is the single strongest argument for a block model — and Learny already has it, differently. SRS state lives in `quiz_items` + `quiz_item_scheduling` (FSRS snapshot per item), deliberately decoupled from the corpus and from any note structure. Learny does not need notes to be blocks to get block-granular repetition; it needs notes to be able to *cite* passages, which the anchor system already provides.

### 1.4 Links, backlinks, tags without a graph DB

- **Adjacency tables are the standard answer.** A `note_links(from_note_id, target_...)` table gives forward links; backlinks are the same table queried by target with an index on the target column. Logseq's own `:block/refs` (cardinality-many ref) is semantically identical to a two-column link table (schema.cljs above).
- **Unresolved links need a text column, not a FK.** Obsidian and Logseq both support linking to pages/notes that do not exist yet ("unlinked/Unlinked References" in [db-version.md](https://github.com/logseq/docs/blob/master/db-version.md)). Model: `target_note_id` nullable + `target_text` always populated; a save/rename pass resolves text targets to ids.
- **Multi-hop traversal is `WITH RECURSIVE`.** PostgreSQL 16 supports recursive CTEs with a built-in `CYCLE col SET is_cycle USING path` clause and `SEARCH BREADTH|DEPTH FIRST` ordering, which covers "notes within N hops", cycle-safe graph walks, and tree flattening without a graph database ([PostgreSQL 16: WITH queries](https://www.postgresql.org/docs/16/queries-with.html), accessed 2026-07-17). Note graphs are cyclic by nature, so the CYCLE clause (or an explicit path array) is mandatory, and hop-limited traversal (depth column in the CTE) keeps worst cases bounded.
- **Tags**: a `tags` table plus `note_tags` join table (rather than a text[] on notes) so tags can be renamed, merged, and counted with plain SQL; this mirrors tags becoming first-class relationships in Logseq DB.
- **Hierarchies (folders/notebooks or an outline)**: adjacency list + recursive CTE is the default; `ltree` materialized paths with GiST-indexed ancestor/descendant operators (`@>`, `<@`) are available but constrain labels to `A-Za-z0-9_-` (≤1000 chars/label) ([PostgreSQL 16: ltree](https://www.postgresql.org/docs/16/ltree.html), accessed 2026-07-17) — Learny anchors and titles do not fit that alphabet without a slug layer, and note trees are shallow, so `ltree` buys little here.

### 1.5 Ordering and nesting mechanics

Three ordering schemes for siblings, with production evidence:

| Scheme | Mechanism | Evidence | Fit |
|---|---|---|---|
| Integer `position` | Renumber siblings on insert/move (single UPDATE over the affected range, or rewrite-all like Learny's atomic corpus replace) | Learny's own `corpus_sections(document_id, position)` and `corpus_blocks.position` | Simple, unique-constrained, ideal for single-writer and rewrite-on-save |
| Fractional index (string key) | New key lexicographically between neighbors; single-row writes; keys grow with pathological insert patterns; concurrent inserts can collide and need server-side tie-breaking | Figma multiplayer ([Realtime editing of ordered sequences](https://www.figma.com/blog/realtime-editing-of-ordered-sequences/), accessed 2026-07-17); Logseq `:block/order` + [clj-fractional-indexing](https://github.com/logseq/clj-fractional-indexing) | The right tool for concurrent/collaborative reordering — a problem single-user Learny does not have |
| Linked list (prev/next pointer) | Each row points at its left sibling | Logseq **removed** it (`:block/left` → `:block/order`, [db-version-changes.md](https://github.com/logseq/docs/blob/master/db-version-changes.md)) | Anti-recommended: ordered reads require traversal, chains can break |

For nesting: parent FK + depth is sufficient; Learny's corpus already models TOC nesting as `position` + `depth` columns rather than a parent FK and it has been adequate for rendering and citation paths.

### 1.6 Translating quiz-item snapshot semantics to notes anchored to books

Learny's shipped quiz schema (`backend/app/infrastructure/db/metadata.py`, `quiz_items`) establishes the house pattern for user-state that must survive corpus replacement:

1. **No FK into corpus tables.** `quiz_items` snapshot `anchor`, `section_path`, `source_excerpt`, and `chunk_hash`; re-ingest atomically replaces `corpus_sections/blocks/chunks` and regenerates chunk ids, and the snapshots keep every citation renderable regardless. Teaching sessions do the same (`target_anchor` + snapshot of path/title).
2. **Anchors are the reconciliation currency, not row ids.** Anchors are stable by construction (EPUB href-based; PDF `pdf:{slug-path}/b{ordinal}-{sha256[:16]}`), and `corpus_sections.anchor_aliases` keeps anchors merged during normalization resolvable "so no saved citation dangles after a re-ingest" (AD-085, comment in `metadata.py`). A post-re-ingest reconcile pass re-resolves each snapshot anchor against `anchor`/`anchor_aliases` and flips a `status` field (`active | stale | orphaned`) — content is never mutated or deleted.
3. **`content_key` upsert is a *generated-content* identity, not a user-content identity.** `UNIQUE(source_id, content_key)` where `content_key = sha256(item_type ␟ norm(question) ␟ norm(answer))` exists so that *regenerating* a deck upserts instead of minting duplicates, while FSRS scheduling rows (keyed by `quiz_item_id`) survive. The mechanism protects user state (review history) attached to machine-generated rows.

Translation to notes:

- **User-authored note text needs no `content_key`.** A note is not regenerated by a pipeline; its identity is its own primary key and its content is authoritative. The `content_key` pattern should be reserved for any *derived* note artifacts Learny might generate later (AI summaries, auto-extracted highlights), where regeneration must upsert rather than duplicate.
- **What notes borrow is #1 and #2**: a note's link to a book passage is a snapshot row — `source_id` + `anchor` + `section_path` snapshot + quoted `excerpt` — with **no FK to `corpus_sections`/`corpus_blocks`/`corpus_chunks`**, plus a reconcile status maintained by the same re-ingest pass that reconciles quiz items.
- **Lifetime rule differs from quiz items.** `quiz_items` cascade-delete with their source (regenerable). Notes are irreplaceable user writing: deleting a book must not delete notes. The book-anchor rows can cascade (they are meaningless without the source), or better, be kept `orphaned` with the source title snapshotted; the note row itself must never be in any corpus- or source-triggered cascade path. (Design stance derived from the "never lose user state" requirement; no external source.)

### 1.7 Retrieval and export fit (Learny-internal)

A document-model note drops directly into existing machinery: one `tsvector` per note (language-aware via the `search_config` pattern from chunks) for lexical search, optional note-level or paragraph-chunk embeddings behind the existing `EmbeddingPort` if notes later join hybrid retrieval, and Anki/export remains a projection (genanki) exactly as for quiz items. A block model would force chunking, FTS, and citation logic to operate per-block from day one for no current feature gain.

## 2. Options

| # | Option | Summary |
|---|---|---|
| A | **Documents + derived index tables (Obsidian-in-Postgres)** — recommended | `notes` holds full Markdown body (source of truth); `note_links`, `note_tags` re-derived on save; `note_anchors` snapshot rows for book citations |
| B | Blocks/outliner (Logseq/RemNote-in-Postgres) | Every paragraph a row: `note_blocks(parent_id, order_key, content)`; links/tags/anchors at block granularity |
| C | Hybrid: documents now, addressable spans inside | Document body + optional stable span markers (`^id`) that anchor rows can point into |

### Option A — Notes as whole documents with derived link/tag/anchor tables (recommended)

**Shape (prose, not DDL):**

- `notes` — id, user_id, title, `body_markdown` (source of truth), nullable `notebook_id`, language/`search_config`, generated `search_vector`, timestamps. Optionally a nullable `embedding` (1536, same pgvector extension) if notes join retrieval.
- `notebooks` (optional, if grouping is wanted) — id, title, nullable `parent_id` (adjacency list), integer `position` per sibling; traversed with `WITH RECURSIVE` (shallow, cycle-guarded).
- `note_anchors` — id, `note_id` (FK, cascade from note), `source_id` (FK to `sources`), `anchor` (text snapshot), `section_path` (jsonb snapshot), `excerpt` (quoted text snapshot), `chunk_hash`/content hash of the cited region, `status` (`active | stale | orphaned`), `source_title` snapshot. **No FK to any corpus table.** Reconciled by the same re-ingest pass as quiz items via `anchor`/`anchor_aliases`.
- `note_links` — id, `from_note_id` (FK, cascade), `target_note_id` (nullable FK, `ON DELETE SET NULL`), `target_text` (always populated; supports unresolved links and re-resolution on rename), derived wholly from `body_markdown` on save; delete-and-reinsert per save. Backlinks = index on `target_note_id`.
- `tags` + `note_tags` — first-class tag rows so rename/merge are UPDATEs; `note_tags` derived from body (`#tag`) and/or explicit UI.
- Ordering: notes within a notebook by integer `position` (unique per notebook), renumbered on move — single-writer makes this trivial; no fractional indexing machinery.

**Why recommend:** matches the proven Obsidian split (authoritative body + rebuildable derived index — [data-storage](https://obsidian.md/help/data-storage)); reuses Learny's shipped patterns verbatim (snapshot anchors like `quiz_items`/teaching sessions, integer positions like corpus tables, `search_config`-aware tsvector, pgvector column); note editing is one-row read/write, which suits Markdown textarea/editor UX and SSE-streamed AI assistance; export and backup are trivial (each note is already a document); smallest schema and migration surface for a v-next cycle; block-level SRS — the block model's killer feature — is already covered by `quiz_items`.

**Why not:** references are note-granular — no block refs, no transclusion-with-identity; `note_anchors` tie a whole note (or a user-selected excerpt) to a passage rather than tying each paragraph individually; if Learny later wants outliner editing or per-paragraph backlinks, that is a real migration (Logseq's file→DB move shows it is doable but costly); derived tables must be re-extracted on every save (negligible at single-user scale, but it is a consistency job to own — Obsidian's cache "can occasionally become out of sync").

### Option B — Blocks/outliner model

**Why recommend (if chosen):** block identity enables paragraph-level backlinks, embeds/transclusion, per-block anchors to book passages, and fine-grained future collaboration; Logseq DB and RemNote prove the shape works and its relational encoding is well-understood (parent ref + page ref + refs link table + `:block/order`-style key — [schema.cljs](https://github.com/logseq/logseq/blob/master/deps/db/src/logseq/db/frontend/schema.cljs)); it never needs a "split this note" migration later.

**Why not:** highest cost for zero currently-planned features — Learny's SRS is quiz-side, its citations are anchor-side, and no transclusion feature exists in the roadmap; every read becomes a recursive assembly and every save a tree diff; ordering wants fractional indexing (string keys, growth and collision edge cases — [Figma](https://www.figma.com/blog/realtime-editing-of-ordered-sequences/)) or constant renumbering; Markdown import/export and full-note FTS/embedding all require reassembly; Logseq needed a dedicated multi-year re-architecture to land this model well, a poor size match for a single-user app's notes cycle.

### Option C — Documents with optional in-body span markers

**Why recommend (if chosen):** keeps Option A's simplicity while allowing `note_anchors`-style rows *into* a note (e.g., a quiz item or another note citing a specific paragraph of a note) via Obsidian-style `^span-id` markers stored inline in the Markdown; cheap incremental step from A; markers survive edits because they travel with the text.

**Why not:** in-body markers are user-visible syntax noise and are only as stable as user editing discipline (deleting a marker silently orphans referents — same fragility Obsidian accepts); nothing in the current roadmap needs note-internal addressing, so it is speculative surface area; it can be added to Option A later without migration (markers are just text plus one more derived table), so choosing it *now* buys nothing.

## 3. Recommendation

**Adopt Option A: notes as whole Markdown documents in a `notes` table (body as single source of truth), with derived `note_links`/`note_tags` index tables rebuilt on save, first-class `tags`, optional `notebooks` adjacency list with integer sibling positions, and `note_anchors` snapshot rows for book citations that copy the quiz-item pattern — `source_id` + anchor + section-path + excerpt snapshots, no FK into corpus tables, `active|stale|orphaned` status reconciled through `anchor_aliases` by the existing re-ingest pass.** Backlinks and graph queries are adjacency-table queries plus `WITH RECURSIVE` (with the CYCLE clause) — no graph DB, honoring the PostgreSQL-only constraint. Do **not** reuse `content_key` upsert identity for user-authored notes (their identity is their own id and they must never be machine-upserted); reserve that pattern for future *generated* note artifacts. Unlike quiz items, keep notes out of every source/corpus cascade path: a book deletion or re-ingest may orphan a note's anchors but must never touch the note. Revisit the block model only if a concrete transclusion/outliner or per-paragraph-backlink feature is accepted into the roadmap; Option C's span markers remain available as a compatible later increment.

## 4. Open issues

1. Whether notes should join hybrid retrieval (and Q&A citations) in the same cycle — if yes, decide note-level vs paragraph-chunk embeddings and how note citations are anchored (note id vs span marker), which pulls Option C's markers forward.
2. Exact lifetime policy for `note_anchors` when a source is deleted: cascade the anchor rows vs keep them `orphaned` with the snapshotted `source_title` (report leans to the latter; needs a product decision).
3. Whether the re-ingest reconcile pass should also re-verify `excerpt`/`chunk_hash` drift (content changed under a still-resolvable anchor) and how that maps to `stale` for notes.
4. `:block/order` being a fractional index in Logseq DB is strongly implied by the maintained clj-fractional-indexing library and the `:block/left` removal, but no primary sentence states the wiring — (unverified); does not affect the recommendation (fractional indexing is anti-recommended here anyway).
5. Concurrency assumption: the integer-position ordering choice assumes the single-user, single-writer deployment holds; if Learny ever adds multi-device concurrent editing, revisit ordering (fractional keys) and body-level conflict handling.

## 5. Sources

- Obsidian Help, "How Obsidian stores data" — https://obsidian.md/help/data-storage (accessed 2026-07-17)
- Obsidian Developer Docs, "Vault" — https://docs.obsidian.md/Plugins/Vault (accessed 2026-07-17)
- Logseq official docs, "DB Version" — https://github.com/logseq/docs/blob/master/db-version.md (accessed 2026-07-17)
- Logseq official docs, "DB version changes" — https://github.com/logseq/docs/blob/master/db-version-changes.md (accessed 2026-07-17)
- Logseq DataScript schema — https://github.com/logseq/logseq/blob/master/deps/db/src/logseq/db/frontend/schema.cljs (accessed 2026-07-17)
- Logseq fractional indexing library — https://github.com/logseq/clj-fractional-indexing (accessed 2026-07-17)
- RemNote Plugin Docs, "The Rem API" — https://plugins.remnote.com/advanced/rem_api (accessed 2026-07-17)
- RemNote Help Center, "Structuring Content" — https://help.remnote.com/en/collections/3939579-structuring-content (accessed 2026-07-17)
- Figma Engineering, "Realtime editing of ordered sequences" — https://www.figma.com/blog/realtime-editing-of-ordered-sequences/ (accessed 2026-07-17)
- PostgreSQL 16 Documentation, "WITH Queries (Common Table Expressions)" — https://www.postgresql.org/docs/16/queries-with.html (accessed 2026-07-17)
- PostgreSQL 16 Documentation, "F.23. ltree" — https://www.postgresql.org/docs/16/ltree.html (accessed 2026-07-17)
- Learny repo (internal): `backend/app/infrastructure/db/metadata.py` — `quiz_items`, `quiz_item_scheduling`, `corpus_sections.anchor_aliases`, teaching-session `target_anchor` (read 2026-07-17)
