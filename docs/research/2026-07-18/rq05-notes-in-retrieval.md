# RQ-05 — User Notes/Highlights in Hybrid Retrieval

- **Date:** 2026-07-18 (sources accessed 2026-07-17)
- **Question:** How should user notes/highlights join Learny's hybrid retrieval — same `corpus_chunks` table with a source-type discriminator, or a parallel notes index unioned at RRF time?
- **Scope:** citation semantics (note vs book), embedding refresh on note edit, retrieval pollution risk, and how existing RAG products blend personal notes with sources.
- **Status:** Research complete; recommendation below (Option B).

---

## 1. Learny constraints that shape the answer (repo facts)

These are read directly from the codebase and are load-bearing for the recommendation:

1. **`corpus_chunks` is structurally a *derived* artifact of a book.** Every chunk has a `NOT NULL section_id` FK into `corpus_sections → corpus_documents` with `ON DELETE CASCADE` (`backend/app/infrastructure/db/metadata.py`, `corpus_chunks` table). The hybrid retrieval statement scopes both arms through that join chain (`backend/app/infrastructure/db/retrieval.py`, `scoped` CTE). A note is not a section of a document; storing it here means either fake sections/documents or nullable FKs that weaken every existing invariant.
2. **Re-ingest replaces the corpus atomically.** The project deliberately gave quiz items **no corpus FK** — they snapshot citation text + anchor and reconcile via `(source_id, content_key)` upsert precisely because corpus rows are disposable. User notes are user-authored durable data; putting them in a table whose rows are deleted and recreated on re-ingest inverts that established lifecycle decision.
3. **Retrieval is one SQL statement with per-arm CTEs fused by RRF** (`1/(k + rank)` summed across arms via `FULL OUTER JOIN`). Adding arms to the fusion step is a local, well-understood change; the statement already demonstrates per-arm `LIMIT`s and a shared `rrf_k`.
4. **The lexical arm is trigger-maintained.** `corpus_chunks.search_vector` is a plain `tsvector` kept fresh by a `BEFORE INSERT OR UPDATE` trigger (migration `0007_language_aware_fts`), with a per-row `search_config`. The same pattern transplants directly onto a notes table, so an edited note is lexically searchable the instant it is saved, independent of embedding latency.
5. **Missing embeddings already degrade gracefully.** The semantic arm skips `embedding IS NULL` rows (RET-15), so "note saved but not yet embedded" needs no new failure handling — it falls back to lexical-only for that row.
6. **Citations are mapped positionally, with per-document metadata available.** The Claude answering adapter builds one citations-enabled `document` block per Evidence chunk, resolves `citation.document_index` back through the ordered `chunk_id` list, and already sends per-document `title` (section-path tail) and `context` (JSON `{chunk_id, anchor}`) (`backend/app/infrastructure/answering/anthropic.py`). Adding a `kind` to that metadata and to `Evidence` is a small, contained change.

## 2. How existing products blend personal notes vs sources

| Product | Behavior | Source |
|---|---|---|
| **Google NotebookLM** | Notes are **excluded** from chat grounding. Chat answers only from *sources*; a note participates only after an explicit **"Convert to source"** action (single note or "Convert all notes to source", which merges them into one source). | [NotebookLM Help — Create & add notes](https://support.google.com/notebooklm/answer/16262519?hl=en) (accessed 2026-07-17) |
| **Obsidian Smart Connections** | The **opposite pole**: the user's notes *are* the corpus. All vault notes are embedded into a local semantic index; the plugin "listens for Obsidian events so indexing and stats stay in sync with your vault" — i.e. event-driven **incremental re-embedding on note change**, not batch re-index. | [github.com/brianpetro/obsidian-smart-connections](https://github.com/brianpetro/obsidian-smart-connections) README (accessed 2026-07-17) |
| **Obsidian Copilot / community hybrid-search plugins** | Same pattern — whole-vault index; e.g. VaultSearch does BM25 + local embeddings **fused with RRF** over notes. | [github.com/logancyang/obsidian-copilot](https://github.com/logancyang/obsidian-copilot), [github.com/erayaydn0/obsidian-vault-search](https://github.com/erayaydn0/obsidian-vault-search) (accessed 2026-07-17) |
| **Readwise Reader (Ghostreader/Chat)** | Chat is **document-scoped** ("chat with documents as you're reading"); highlight/note search is a separate semantic-search surface, not silently blended into document Q&A. | [docs.readwise.io — Chat with your documents](https://docs.readwise.io/reader/guides/ghostreader/chat) (accessed 2026-07-17) |

**Reading:** mature products either segregate notes from source grounding entirely (NotebookLM, Readwise) or make notes the *only* corpus (Obsidian ecosystem). None of the surveyed products silently pools user notes into the same ranked list as source text without user control — which is evidence that *undifferentiated* blending (Option A's default behavior) is the pattern everyone avoided. (Interpretation ours; the segregation facts are per the primary sources above.)

**Fusion-weighting precedent:** Azure AI Search's hybrid ranking documents exactly the control knob a blended list needs: each parallel query's reciprocal-rank contribution `1/(rank + k)` (k ≈ 60) can be scaled by a per-query **weight multiplier** (default 1.0; 0.5 halves a source's influence, 2.0 doubles it) before summation — i.e. per-source influence is controlled *at RRF time*, per arm, not per row. [Microsoft Learn — Hybrid search scoring (RRF)](https://learn.microsoft.com/en-us/azure/search/hybrid-search-ranking) (accessed 2026-07-17). This maps 1:1 onto Learny's `fused` CTE: `book_terms + w_note * note_terms`.

## 3. Single-table discriminator: what PostgreSQL says about filtered ANN

If notes lived in `corpus_chunks` behind a `kind` column, any query wanting *only* book chunks (or per-kind caps) becomes a **filtered HNSW scan**. pgvector 0.8.0 addressed the known failure mode ("overfiltering" — the index returns its ef_search candidates, the filter discards most, you get too few rows) with **iterative index scans**: `hnsw.iterative_scan = strict_order | relaxed_order` keeps scanning until enough filtered results are found, bounded by `hnsw.max_scan_tuples`. [pgvector 0.8.0 release announcement, postgresql.org](https://www.postgresql.org/about/news/pgvector-080-released-2952/) (accessed 2026-07-17). Partial indexes (`CREATE INDEX ... WHERE kind = 'note'`) are the documented alternative for low-cardinality filters ([pgvector filtering docs via pgEdge](https://docs.pgedge.com/pgvector/development/filtering/), accessed 2026-07-17) — but two partial indexes on one table is operationally the same as two indexes on two tables, minus the schema clarity. So the single-table option is *workable* in PostgreSQL, it just buys nothing at Learny's scale while adding tuning surface (`iterative_scan`, `max_scan_tuples`) to a query that today needs none.

## 4. Embedding refresh on note edit — cost and latency

- **Price (verified):** `text-embedding-3-large` is **$0.13 per 1M input tokens** ($0.065 via Batch API). [developers.openai.com model page](https://developers.openai.com/api/docs/models/text-embedding-3-large) (accessed 2026-07-17).
- **Math at author scale (single user):** a typical note/highlight annotation is ~50–500 tokens. Re-embedding a 500-token note costs **$0.000065**. One hundred note edits/day ≈ 50K tokens/day ≈ **$0.007/day**. A full re-embed of 10,000 notes × 500 tokens = 5M tokens ≈ **$0.65**. Embedding cost is a non-issue at any plausible single-user scale; there is no case for batching, deferral for cost reasons, or embedding-avoidance in the design.
- **Latency:** a single embeddings API call is typically well under a second (unverified — no published latency SLO found), and Learny already routes embedding through a Celery worker rather than request handlers. The right shape is: save note → tsvector trigger makes it lexically retrievable immediately → enqueue a (debounced, per-note) embed task → semantic arm picks it up when `embedding` lands; until then the NULL-embedding skip (RET-15 pattern) applies. Smart Connections' event-driven incremental re-embedding (§2) is the same design executed locally.
- **Consistency guard:** store `embedding_model` and the embedded-text hash on the note row so an edit that races an in-flight embed can detect staleness and re-enqueue (same discipline the corpus embed path uses with `embedding_model`).

## 5. Citation semantics — citing the user's own note vs the book

**API capability (verified):** each Claude `document` block carries its own `title`, optional `context` metadata, and `citations: {enabled: true}`; returned citations include `cited_text`, `document_index`, and `document_title`, with location types for plain-text and custom content. [platform.claude.com — Citations](https://platform.claude.com/docs/en/build-with-claude/citations.md) (accessed 2026-07-17). Learny's adapter already resolves citations positionally via `document_index` and passes `{chunk_id, anchor}` in `context` — so distinguishing note-documents from book-documents requires **no new API surface**, only:

1. **`Evidence.kind: "book" | "note"`** (plus `note_id` for note evidence). The retrieval statement's final SELECT tags each row with its arm's kind.
2. **Prompt side:** note documents get `title = "Reader's note — {section}"` and `context` JSON gains `"kind": "note"`; the system prompt gains an attribution rule: *the book's text is ground truth for what the book says; a reader note is the user's own prior thought — cite it as "your note", never present its content as the book's claim, and prefer book evidence when they conflict.* This matters because a note may be wrong about the book; without the rule the model will happily launder a misremembered note into "the book states…".
3. **UI side:** note citations render as a visually distinct chip (e.g. "Your note · §Section") and click through to the note (and its anchored book location), while book citations keep the existing anchor navigation. Since quiz items snapshot citation text + anchor with no FK, a quiz item generated from note-cited evidence needs its snapshot to record the kind too, so reviewed cards don't misattribute a personal note as book text.
4. **Anchor lifecycle:** notes that annotate a passage store the chunk *anchor string* (not a chunk FK), resolving through `anchor_aliases` after re-ingest — identical to the quiz-item reconciliation model, so note→book navigation survives corpus replacement.

## 6. Retrieval pollution — will notes drown book chunks?

Structural reasons to expect notes to over-rank if pooled into one undifferentiated candidate set:

- **Vocabulary identity:** queries and notes are written by the same person; lexical overlap (and stylistic embedding proximity) between a query and the user's own phrasing is systematically higher than between the query and the book's prose. (Reasoned, unverified — no controlled study found for this exact setting.)
- **Length asymmetry:** notes are short and topically dense; short focused texts sit closer to short queries in embedding space than 300–500-token book chunks that mix the topic with surrounding prose. (Reasoned, unverified.)
- **Self-reference loops:** a note that paraphrases an earlier answer will match the next similar question almost verbatim, progressively displacing primary-source chunks — the RAG analog of citogenesis. (Reasoned, unverified.)

This is exactly why fusion-time control matters: with notes as **separate RRF arms**, pollution is bounded *by construction* — the note arms get their own smaller `LIMIT`s (e.g. 5 vs the book arms' limits), a weight multiplier `w_note ≤ 1.0` on their reciprocal-rank terms (Azure-documented pattern, §2), and, if needed, a final-selection cap ("at most m of top_k evidence rows may be notes"). A pooled single-arm design has none of these levers — rank position is the only signal, and it is the thing being polluted. NotebookLM's exclude-by-default stance (§2) is the strongest product evidence that unmitigated blending was judged unacceptable by the largest team to ship this feature.

---

## 7. Options

| # | Option | Summary |
|---|---|---|
| A | **Discriminator in `corpus_chunks`** | Add `kind` column; notes stored as chunks; one index pair; filtered or pooled queries |
| B | **Parallel notes table, unioned at RRF time** ✅ **(recommended)** | `notes` table with own `embedding`, trigger-fed `search_vector`; two extra CTE arms in the same hybrid statement; per-arm weight + caps |
| C | **Notes excluded; explicit opt-in per question** (NotebookLM model) | Notes never retrieved unless the user explicitly attaches/converts them for a session |

### Option A — same table + source-type discriminator

- **Why recommend:** smallest surface on paper — one HNSW + one GIN index, the existing tsvector trigger and embed pipeline reused verbatim; no new Evidence plumbing if notes masquerade as chunks; a single scoped CTE keeps the query shape unchanged.
- **Why not:** it stores durable user-authored data in a table designed to be atomically deleted and rebuilt on re-ingest — the exact coupling the quiz-item design (no corpus FK) was created to avoid; `section_id NOT NULL` and the `chunks→sections→documents` join chain force fake parent rows or nullable-FK erosion of every invariant; excluding or capping notes at query time turns the semantic arm into a filtered ANN scan needing pgvector 0.8 iterative-scan tuning or per-kind partial indexes (§3), which is two indexes again; and pooled ranking gives no per-source weight/cap lever, leaving the pollution risk (§6) unmitigated.

### Option B — parallel notes table, extra arms fused at RRF time ✅

- **Why recommend:** notes get the lifecycle they actually have — durable, user-owned, untouched by corpus replacement (consistent with the quiz-item precedent and with `anchor_aliases` reconciliation for their book anchors); the schema stays honest (no nullable-FK erosion); each index is small and **unfiltered**, so no iterative-scan tuning; the change to retrieval is local — two more CTEs over a `scoped_notes` set and two more reciprocal-rank terms in `fused`, still **one SQL statement**; pollution is bounded by construction via per-arm limits, an Azure-precedented weight multiplier, and an optional final cap (§6); citation semantics fall out of a small `Evidence.kind` + document-metadata change (§5); embedding refresh is a trivially cheap per-note upsert with instant lexical freshness via the trigger (§4).
- **Why not:** duplicated infrastructure — a second HNSW + GIN index pair, a second tsvector trigger, and embed-task wiring for notes (mitigated by reusing the existing adapter and trigger pattern, and by single-user scale making the second HNSW index tiny); the hybrid statement grows from 2 to 4 arms plus weight/cap parameters, and those parameters (`w_note`, note-arm limits) must be tuned without existing golden fixtures — new eval fixtures are required before the defaults can be trusted.

### Option C — notes excluded by default; explicit opt-in (NotebookLM model)

- **Why recommend:** zero pollution risk and zero retrieval work; matches the most prominent product precedent (NotebookLM's "Convert to source"); trivially explainable to the user; nothing to tune.
- **Why not:** it makes notes inert in the product's core loop — cited Q&A never gets richer as the user's own thinking accumulates, which cuts against Learny's stated second-brain direction; NotebookLM-style conversion produces a *frozen copy* that goes stale as notes evolve; and it forecloses the differentiating UX ("your note on §3.2 said X — the book actually argues Y") that only retrieval-time blending enables. It is, however, the right *default posture to borrow*: Option B should ship with a visible "include my notes" toggle so blending is user-controlled.

---

## 8. Recommendation ✅

**Adopt Option B: a parallel `notes` table with its own `embedding vector(1536)` and trigger-maintained `search_vector`, joined into the existing hybrid retrieval statement as two additional RRF arms (note-semantic, note-lexical), fused with a note-arm weight multiplier and smaller per-arm limits, behind a user-visible "include my notes" toggle.**

Concretely:

1. **Schema:** `notes(id, user_id, source_id FK sources, anchor TEXT NULL, body_md, embedding vector(1536) NULL, embedding_model TEXT NULL, search_config, search_vector via trigger, created_at, updated_at)`. Anchored notes store the anchor *string* and resolve via `anchor_aliases` (quiz-item pattern); re-ingest never touches this table.
2. **Retrieval:** extend `_HYBRID_SQL_TEMPLATE` with `scoped_notes`, `note_semantic`, `note_lexical` CTEs; `fused` becomes `book_terms + :w_note * note_terms` (Azure weighted-RRF pattern) with note-arm limits defaulting to roughly half the book arms'; final SELECT emits `kind`. Skip the note CTEs entirely when the toggle is off.
3. **Citations:** `Evidence.kind` + `note_id`; note documents titled "Reader's note — {section}" with `"kind": "note"` in `context`; system-prompt attribution rule (book = ground truth, note = user's prior thought, cite as "your note"); distinct UI chip; quiz snapshots record kind.
4. **Freshness:** tsvector trigger gives instant lexical retrieval on save; a debounced Celery task embeds/re-embeds the note (≈$0.0001 per edit at $0.13/1M tokens); NULL embedding degrades to lexical-only per the existing RET-15 behavior.
5. **Evaluation before defaults:** add golden fixtures with planted "distractor notes" to tune `w_note` and the note caps, since the pollution magnitudes in §6 are reasoned rather than measured.

This is the only option that simultaneously respects the corpus-replacement lifecycle, keeps PostgreSQL-only retrieval untuned-filter-free, gives explicit fusion-time control over pollution, and produces honest citations that distinguish "the book says" from "your note says".

## 9. Open issues

1. **Tuning without data:** `w_note`, note-arm limits, and any final note cap have no empirical basis yet — requires new golden retrieval fixtures with distractor notes (the pollution claims in §6 are marked unverified).
2. **Scoping notes beyond one book:** the current statement is single-`source_id`; free notes not tied to any source (true second-brain notes) don't fit the `scoped_notes` filter and need a follow-up decision (per-source vs global note retrieval).
3. **Teaching sessions:** whether note arms should participate in anchored/target-subtree teaching retrieval (TEACH-09 scoping) or only in open Q&A is undecided.
4. **Note-derived quiz items:** allowing quiz generation from note-cited evidence risks testing the user on their own (possibly wrong) notes; likely should be book-evidence-only, but not settled.
5. **Latency of embed-on-save:** sub-second single-call latency is assumed (unverified); if the debounced worker path proves too slow for "ask about the note I just wrote", a synchronous embed on the save path is the fallback.

## Verification (inline, 2026-07-18)

The fleet's verification agent for this report died on a session limit; the orchestrator verified the load-bearing claims inline:

1. **corpus_chunks lifecycle** — CONFIRMED in-repo: `section_id` is `nullable=False` with a CASCADE FK chain (`backend/migrations/versions/0004_corpus_schema.py:97,108-115` + `ondelete="CASCADE"` at :60/:86/:111/:136), and corpus replace is atomic — notes stored there would die with the corpus.
2. **Azure RRF per-arm weighting precedent** — spot-checked only (secondary confidence): the recommendation does not collapse without it; fusion-time weighting is the standard hybrid pattern.
3. **Embedding cost negligibility** — substance CONFIRMED, figure unverifiable today: OpenAI's reorganized pricing page no longer lists embedding prices on the main table; even at 10× the cited $0.13/1M, re-embedding 10k notes stays under ~$7 — the economic conclusion (re-embed on edit is fine at author scale) is insensitive to the exact figure.
4. **NotebookLM notes excluded from grounding unless converted to a source** — CONFIRMED, independently corroborated by the rq01 verification correction (Google support: notes can be converted into sources; only sources ground chat).
5. **Citation document blocks carry per-document metadata; adapter maps positionally** — CONFIRMED in-repo: `backend/app/infrastructure/answering/anthropic.py:7,54,66` (`document_index` → chunk mapping).
