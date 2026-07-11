# EPUB Corpus Pipeline Specification

Cycle 4 — TDD-001 Phase 5. Replaces the `NoOpIngestionStep` stub (AD-012) with a real
EPUB parsing step that builds the canonical corpus (ADR-0002), derives Markdown and
retrieval chunks from it, and exposes the parsed book structure to the owning user.
User decisions for gray areas live in [context.md](context.md) (D-1..D-5).

## Problem Statement

Ingestion today drives the full job lifecycle but produces nothing: the step body is a
stub, so a "ready" source has no corpus and nothing downstream (retrieval, cited Q&A,
teaching) can exist. This cycle turns an uploaded EPUB into a durable, structured,
citable corpus — the substrate every later phase depends on.

## Goals

- [ ] A valid uploaded EPUB, once ingested, has a canonical corpus in PostgreSQL:
      document metadata, spine-ordered sections with TOC-derived section paths and
      stable anchors, preserved HTML block fragments, derived Markdown, and
      structure-first retrieval chunks.
- [ ] The owning user can see the parsed book structure (metadata + section tree) in
      the web app once ingestion succeeds.
- [ ] Invalid or unreadable EPUBs fail the job terminally with a redacted failure
      summary and leave no partial corpus.

## Out of Scope

| Feature | Reason |
|---|---|
| Embeddings, tsvector/full-text fields, retrieval indexes/queries | TDD Phase 6 |
| Cited Q&A, teaching sessions | TDD Phases 7–8 |
| PDF/DOCX/HTML/scan ingestion | Deferred by ADR-0011; EPUB only |
| Corpus versioning/history | D-3: atomic replace; versioning needs a future ADR |
| Image binary extraction/storage | Images recorded as references (href + alt) only |
| Real published-book fixtures, Ragas, eval dashboard | Phase 9 / ADR-0016 |
| Source deletion + corpus cleanup UX | No source delete endpoint exists in MVP; DB-level cascade only (CORP-14) |
| Ingestion progress UI beyond existing status badge | Cycle 3 scoped out polling; unchanged |

---

## Assumptions & Open Questions

| # | Assumption / decision | Chosen default | Rationale | Confirmed? |
|---|---|---|---|---|
| A-1 | Section granularity | A **section** corresponds to a TOC (nav) entry. Content blocks are assigned to the deepest TOC entry whose anchor precedes them in reading order. A spine document with no TOC entry forms its own section (see A-2 for its title). | TOC entries are what humans cite ("Chapter 3 › Section 2"); deepest-preceding assignment gives every block exactly one home. | y (gate) |
| A-2 | Section title fallback when the TOC has no entry for a spine document | Use the document's first heading element's text; if none, the href filename without extension. `section_path` is then that single title. | Real EPUBs (covers, colophons) often miss TOC entries; parsing must not fail on them. | y (gate) |
| A-3 | Non-linear spine items (`linear="no"`) | Excluded from the corpus in MVP. | They are auxiliary content by EPUB spec; including them would pollute reading order. | y (gate) |
| A-4 | Anchor format | `href` of the containing spine document, plus `#fragment` when the section's TOC entry targets an in-document `id` (e.g. `chapter03.xhtml#sec-2`); bare `href` otherwise. Chunks carry their section's anchor. | Matches epub-ingestion skill / ADR-0003 traceability fields; deterministic and source-verifiable. | y (gate) |
| A-5 | Chunk size bounds | Config `LEARNY_CHUNK_MAX_CHARS`, default **2000**. Packing: append whole blocks while the chunk stays ≤ max; a single block longer than max is split at sentence boundaries into pieces each ≤ max. Every chunk is non-empty; no minimum size. | D-4 needs concrete, testable numbers; 2000 chars ≈ 500 tokens, a sane retrieval unit. | y (gate) |
| A-6 | Markdown derivation coverage | Headings → `#`-levels, paragraphs → text, ordered/unordered lists, blockquotes, code blocks, tables → GitHub pipe tables, images → `![alt](href)`, everything else degrades to its plain text content. Text content is never silently dropped. | Bounded MVP conversion; "never dropped" is the testable guarantee. | y (gate) |
| A-7 | Structure read endpoint shape | `GET /api/sources/{source_id}/structure`. Returns 404 when the source does not exist, is not owned by the caller, **or has no corpus yet** (mirrors Cycle 2/3 ownership-as-404 pattern). No new rate limit: read-only endpoint under existing session auth. | One consistent not-found behavior; FE gates the control on `status === "ready"` anyway. | y (gate) |
| A-8 | Corpus schema version | Constant `1` stored on the corpus document record. | ADR-0002 requires versioning discipline; a constant is enough until a migration exists. | y (gate) |
| A-9 | `page_span` reserved field | Chunks carry a nullable `page_span`, always NULL for EPUB. | ADR-0003/0011: reserved for future PDF citations. | y (gate) |
| A-10 | Upload size bounds | None added here; the parser processes whatever the Cycle 2 upload flow accepted. | Input size limits belong to the upload boundary, not the parser. | y (gate) |

**Open questions:** none — all resolved or logged above.

---

## User Stories

### P1-A: EPUB becomes a canonical corpus ⭐ MVP

**User Story**: As a reader, I want my uploaded EPUB parsed into a structured,
citable corpus when I start ingestion, so that later Q&A and teaching can reference
exact passages of my book.

**Why P1**: This is the entire point of Phase 5; every later phase consumes it.

**Acceptance Criteria**:

1. (CORP-01) WHEN ingestion completes on a valid EPUB THEN the system SHALL persist
   exactly one corpus document for the source recording book title, authors, language
   (each nullable when absent from OPF metadata), and corpus schema version `1`.
2. (CORP-02) WHEN the corpus is built THEN sections SHALL be ordered by spine reading
   order (linear items only, A-3) and each section SHALL carry its `section_path`
   (root-to-node TOC titles, per A-1/A-2) and its anchor (per A-4).
3. (CORP-03) WHEN the corpus is built THEN each content block SHALL be persisted with
   its preserved HTML fragment, its block type, and its position in reading order,
   such that the fixture EPUB yields its expected block sequence exactly.
4. (CORP-04) WHEN the corpus is built THEN every section SHALL have a Markdown view
   derived from its canonical blocks (per A-6) — including all block text content —
   and not parsed independently from the EPUB.
5. (CORP-05) WHEN chunks are derived THEN no chunk SHALL cross a section boundary,
   every chunk SHALL carry its section's `section_path`, anchor, a nullable
   `page_span` (A-9), and its order within the section, every chunk SHALL be
   non-empty and ≤ `LEARNY_CHUNK_MAX_CHARS` characters (A-5), and the concatenated
   chunk text of a section SHALL contain all of that section's block text content.
6. (CORP-06) WHEN the source bytes are not a valid EPUB (non-EPUB bytes, corrupt
   archive, unresolvable spine) THEN the step SHALL fail terminally (no retry), the
   job SHALL record a redacted failure summary (Cycle 3 behavior), the source SHALL
   end `failed`, and no corpus rows SHALL be persisted.
7. (CORP-07) WHEN reading source bytes from object storage fails transiently THEN the
   step SHALL signal a retryable failure (`RetryableIngestionError`), preserving the
   existing retry path.
8. (CORP-08) WHEN a corpus build fails at any point THEN no partial corpus SHALL be
   visible to any reader (the build is transactional), and any previously existing
   corpus for the source SHALL remain intact and readable.
9. (CORP-10) WHEN ingestion succeeds THEN the job's events SHALL include the counts
   of persisted sections, blocks, and chunks.

**Independent Test**: Run ingestion on the committed fixture EPUB via the worker
path; assert the persisted corpus matches the fixture's expected metadata, section
paths, anchors, block sequence, Markdown, and chunk bounds; assert malformed fixtures
fail terminally with no corpus rows.

---

### P1-B: Owner sees the parsed book structure ⭐ MVP

**User Story**: As a user, I want to see my book's structure (title, authors, table
of contents) after ingestion succeeds, so that I know Learny understood my book.

**Why P1**: The vertical-slice proof (AD-010, D-2) that structure preservation
worked, and the first user-visible payoff of ingestion.

**Acceptance Criteria**:

1. (CORP-11) WHEN the owning, authenticated user requests
   `GET /api/sources/{source_id}/structure` for a source with a corpus THEN the
   system SHALL return the book metadata (title, authors, language) and the ordered
   section tree (titles, section paths, anchors) nested per the TOC hierarchy.
2. (CORP-11) WHEN the source does not exist, belongs to another user, or has no
   corpus THEN the system SHALL return 404 (A-7); WHEN the caller is unauthenticated
   THEN 401 per the existing auth boundary.
3. (CORP-12) WHEN a source row shows status `ready` on the sources screen THEN it
   SHALL offer a "View structure" control that fetches the structure through the
   same-origin proxy and renders the book metadata and nested section tree.
4. (CORP-13) WHEN the structure fetch fails THEN the screen SHALL show an error
   message consistent with the existing sources-screen error pattern, and WHEN the
   fetch is in flight THEN the control SHALL be disabled.

**Independent Test**: Ingest the fixture EPUB, log in as its owner, open `/sources`,
activate "View structure", and see the fixture's known TOC tree; a second user's
request for the same source returns 404.

---

### P2: Re-ingestion atomically replaces the corpus

**User Story**: As a user, I want restarting ingestion to cleanly rebuild my book's
corpus, so that parser improvements or fixed uploads reprocess without duplicates or
downtime.

**Why P2**: The restart control already exists (Cycle 3); replace semantics (D-3)
must hold for it, but the MVP demo works without exercising it.

**Acceptance Criteria**:

1. (CORP-09) WHEN ingestion re-runs on a source that already has a corpus and
   succeeds THEN exactly one corpus SHALL exist for the source afterward, reflecting
   the new run's parse (old rows replaced in the same transaction).
2. (CORP-09) WHEN ingestion re-runs and fails THEN the previous corpus SHALL remain
   intact and readable (CORP-08), while the job/source reflect the failure per
   Cycle 3 lifecycle rules.

**Independent Test**: Ingest the fixture twice; assert single corpus, no duplicate
sections/blocks/chunks. Ingest, then re-ingest with bytes swapped to a malformed
fixture; assert the original corpus still reads.

---

## Edge Cases

- WHEN the EPUB has no TOC/nav document THEN sections SHALL be derived per spine
  document with A-2 fallback titles — ingestion still succeeds.
- WHEN a TOC entry targets an href absent from the spine THEN that entry SHALL be
  ignored (no section) without failing ingestion.
- WHEN a spine document has no TOC entry THEN it SHALL form its own section (A-1/A-2).
- WHEN a section contains a single block longer than `LEARNY_CHUNK_MAX_CHARS` THEN it
  SHALL be split at sentence boundaries into chunks each ≤ the cap (A-5).
- WHEN a spine document has an empty body THEN it SHALL yield a section with zero
  blocks and zero chunks, and ingestion SHALL still succeed.
- WHEN OPF metadata lacks title/creator/language THEN the corpus document SHALL store
  NULL for the missing fields (CORP-01) — never a parse failure.
- WHEN the stored object key is missing from object storage (permanent) THEN the step
  SHALL fail terminally with the redacted-summary behavior of CORP-06.
- (CORP-14) WHEN a source row is deleted at the database level THEN its corpus rows
  SHALL be removed by foreign-key cascade — no orphaned corpus data.

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
|---|---|---|---|
| CORP-01 | P1-A: canonical corpus | Execute | ✅ Verified |
| CORP-02 | P1-A: canonical corpus | Execute | ✅ Verified |
| CORP-03 | P1-A: canonical corpus | Execute | ✅ Verified |
| CORP-04 | P1-A: canonical corpus | Execute | ✅ Verified |
| CORP-05 | P1-A: canonical corpus | Execute | ✅ Verified |
| CORP-06 | P1-A: canonical corpus | Execute | ✅ Verified |
| CORP-07 | P1-A: canonical corpus | Execute | ✅ Verified |
| CORP-08 | P1-A: canonical corpus | Execute | ✅ Verified |
| CORP-09 | P2: atomic replace | Execute | ✅ Verified |
| CORP-10 | P1-A: canonical corpus | Execute | ✅ Verified |
| CORP-11 | P1-B: structure view (API) | Execute | ✅ Verified |
| CORP-12 | P1-B: structure view (FE) | Execute | ✅ Verified |
| CORP-13 | P1-B: structure view (FE) | Execute | ✅ Verified |
| CORP-14 | Edge case: lifecycle cascade | Execute | ✅ Verified |

**ID format:** `CORP-NN`. **Status values:** Pending → In Design → In Tasks →
Implementing → Verified.

**Coverage:** 14 total, 14 mapped to tasks, 0 unmapped — all ✅ Verified (validation.md, 2026-07-11).

---

## Implicit-Requirement Dimensions Sweep (Large scope — all dimensions)

| Dimension | Resolution |
|---|---|
| Input validation & bounds | CORP-06 (invalid EPUB terminal); A-10 (size bounds owned by upload boundary). |
| Failure / partial-failure | CORP-08 (transactional build, old corpus survives); CORP-06 (redacted summary). |
| Idempotency / retry / duplicates | CORP-09 (atomic replace makes re-runs idempotent); CORP-07 (retryable classification). |
| Auth boundaries & rate limits | CORP-11 (ownership-as-404, 401 unauthenticated); no new rate limit (A-7: read-only under session auth). |
| Concurrency / ordering | Concurrent builds prevented by Cycle 3's active-job partial unique index (AD-016); readers see the pre-replace corpus until commit (CORP-08); reading order itself is CORP-02/03. |
| Data lifecycle / expiry | CORP-14 (FK cascade). No TTL/archival: N/A because corpus lives as long as its source and no delete flow exists in MVP. |
| Observability | CORP-10 (event counts) on top of Cycle 3's ingestion_events lifecycle. |
| External-dependency failure | CORP-07 (transient storage → retryable); missing object → terminal (edge case). |
| State-transition integrity | N/A beyond Cycle 3: the step keeps the existing terminal/retryable contract (CORP-06/07); lifecycle transitions stay owned by worker-foundation services. |

---

## Success Criteria

- [ ] The committed fixture EPUB ingests deterministically: expected metadata,
      section paths, anchors, block sequence, Markdown, and chunk bounds all assert
      green (TDD-001 success metric "EPUB fixture ingestion").
- [ ] A logged-in owner can view their ready book's TOC tree in the web app.
- [ ] Malformed fixtures produce a `failed` source with a redacted failure summary
      and zero corpus rows.
- [ ] Re-ingesting the fixture leaves exactly one corpus, byte-identical assertions
      passing both times.
