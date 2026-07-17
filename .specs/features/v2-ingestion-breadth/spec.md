# Ingestion Breadth (PDF via Docling + Corpus Normalization) Specification

**Cycle:** RFC-002 Cycle F (`v2-ingestion-breadth`)
**Research basis:** `docs/research/2026-07-12/pdf-docling-epub.md`

## Problem Statement

Real-world EPUBs produce noisy corpora: filename-derived section titles (`part0034`, `wrap0000`), flat trees, and text attached to caption-level anchors while file-level sections own nothing (QA finding F7). Separately, Learny only ingests EPUB — PDF, the most common book format users actually have, is unsupported. Cycle F fixes both: a format-agnostic corpus normalization pass that cleans structure for every format, and a Docling-backed PDF parser behind the existing ingestion port, isolated in its own memory-bounded worker.

## Goals

- [ ] A Gutenberg-style noisy EPUB ingests into a corpus with human-meaningful section titles, sane hierarchy, and no boilerplate — F7 closed.
- [ ] A born-digital PDF uploads and ingests end-to-end (structure, chunks, embeddings, cited Q&A, teaching, quizzes) with page-aware citations.
- [ ] PDF parsing runs on a dedicated queue/worker with bounded memory; a pathological PDF cannot starve or crash EPUB ingestion or the API.
- [ ] ADR-0022 records the Docling adoption + normalization pass decision.

## Out of Scope

| Feature | Reason |
| ------- | ------ |
| OCR / scanned PDFs | `do_ocr=False` per RFC-002; ~60% of CPU runtime; born-digital books are the v2 target. Per-source opt-in is a later cycle. |
| Docling for EPUB | Docling's EPUB backend strips anchor IDs (docling issue #2929) — fatal for citations. ebooklib stays (ADR-0011). |
| VLM/Granite-Docling pipeline | GPU-oriented, unneeded for born-digital text. |
| Docling chunkers | Learny's corpus-derived chunker stays so EPUB and PDF chunk identically (ADR-0009 keeps Docling at the edge). |
| New frontend surfaces | Upload UI, library, reader, ask/teach/quiz screens are already format-agnostic; no frontend feature ships (AD-082). |
| PDF viewer / bbox highlight | Anchors store no bboxes; reader renders corpus markdown. Native-PDF display is out of v2. |
| Migration re-ingest of already-ingested sources | Normalization applies on next (re-)ingest; no forced backfill. |
| Localized (non-English) heading-pattern heuristics | English pattern family first (Calibre parity); languages later. |
| Other formats (mobi, djvu, docx) | RFC-002 scope is PDF only. |

---

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --------------------- | --------------- | --------- | ---------- |
| Backend+worker+compose slice, no frontend feature | Ship without new UI | Existing UI is format-agnostic (frontend has no upload accept filter; screens read corpus/API shapes unchanged) | auto (AD-082) |
| Port evolution | Rename `EpubParserPort` → `DocumentParserPort`; `InvalidEpubError` generalizes to `InvalidDocumentError`; format dispatch by `content_type` at worker composition root | RFC says "behind the existing ingestion port"; two parallel ports would duplicate the corpus step | auto (AD-083) |
| Normalization placement | Pure, deterministic, idempotent pass on `ParsedBook` between parse and corpus record building, shared by all formats | Research §4 conclusion; the only seam both parsers flow through | auto (AD-084) |
| Alias persistence | Merged-away anchors persist as aliases on the surviving corpus section; alias-aware section lookup | Citations/quiz items/teaching targets must never dangle after normalization merges | auto (AD-085) |
| PDF anchor scheme | `pdf:{heading-path-slug}/b{ordinal:04d}` + page span fields + 16-hex content hash | Research §3; deterministic for same bytes + parser version | auto (AD-086) |
| Worker topology | Route PDF ingestion to `ingest-pdf` queue at enqueue; dedicated compose service, concurrency 1, mem_limit, `worker_max_tasks_per_child=1`; docling in an optional uv extra; models baked into a separate image | RFC-002 line 82 verbatim; research §1 memory guidance | auto (AD-087) |
| PDF failure semantics | Corrupt/encrypted/text-free PDFs fail terminally (typed, no retry); resource kills contained by mem_limit + child recycling and surface as failed jobs via existing redelivery accounting | Matches existing terminal-vs-retryable step classification | auto (AD-088) |
| Docling testing | Adapter split: pure DoclingDocument→ParsedBook mapping unit-tested against constructed docling-core documents; real-conversion tests skip when docling isn't installed (CI default: not installed) | Keeps CI offline/fast like `live` marker precedent | auto (AD-089) |
| Existing golden fixtures | Golden expected values updated deliberately where normalization changes output; clean structures must pass through byte-identical | Normalization must not degrade already-clean books | auto (D-9, context.md) |

**Open questions:** none — all resolved or logged above.

---

## User Stories

### P1: Clean corpus structure from noisy EPUBs (F7) ⭐ MVP

**User Story**: As a reader ingesting a real-world (Gutenberg/commercial) EPUB, I want section titles and hierarchy that reflect the book's actual structure so that the teach target picker, reader, and citations are usable.

**Why P1**: F7 is the oldest open QA finding; it degrades every downstream surface (teach picker, citations, quiz section eligibility).

**Acceptance Criteria**:

1. **ING-01** WHEN any source (EPUB or PDF) is ingested THEN the system SHALL apply a format-agnostic normalization pass to the parsed structure after parsing and before corpus records are built, and the pass SHALL be pure (no I/O) and idempotent (normalizing already-normalized output changes nothing).
2. **ING-02** WHEN a section's title is generic (matches the filename-stem/`part0034` pattern family or is empty) THEN the system SHALL replace it via the title-inference cascade — first heading text in the section, else first short (<80 chars) styled text, else `Untitled section (N)` — and SHALL never surface a raw filename stem as a title.
3. **ING-03** WHEN the TOC yields a flat tree (all sections depth 0) but section headings carry distinct levels THEN the system SHALL re-derive section depths from heading levels in reading order, and child depth SHALL never exceed parent depth + 1.
4. **ING-04** WHEN parsed section depths jump levels (e.g. 0 → 2) THEN the system SHALL clamp each section's depth to at most its parent's depth + 1, and derived markdown heading levels SHALL stay within h1–h6.
5. **ING-05** WHEN a section owns no meaningful content (< 30 words and no heading of its own, or only an image/caption) THEN the system SHALL merge it into the adjacent surviving section, and the merged section's anchor SHALL become an alias of the surviving section.
6. **ING-06** WHEN a Project Gutenberg book contains the standard `*** START OF THE PROJECT GUTENBERG EBOOK … ***` / `*** END OF … ***` markers THEN the system SHALL exclude content outside the markers from the corpus body.
7. **ING-07** WHEN normalization completes THEN the ingestion job SHALL record a normalization counts event (titles replaced, sections merged, depths adjusted, noise blocks stripped) alongside the existing `corpus_built` event.
8. **ING-08** WHEN an already-clean book (e.g. the golden fixture) is ingested THEN normalization SHALL leave titles, hierarchy, anchors, and content unchanged.

**Independent Test**: Ingest a constructed Gutenberg-style noisy EPUB fixture; assert corpus sections have heading-derived titles, nested depths, no boilerplate, and that merged anchors resolve via alias.

---

### P1: PDF ingestion via Docling ⭐ MVP

**User Story**: As a user, I want to upload a PDF book and get the same corpus-backed experience (structure, cited answers, teaching, quizzes) as EPUB, with page numbers in citations.

**Why P1**: PDF is the dominant real-world book format; RFC-002 Cycle F's headline capability.

**Acceptance Criteria**:

1. **ING-09** WHEN a user uploads a file ending `.pdf` with content type `application/pdf` within `LEARNY_PDF_MAX_BYTES` THEN the system SHALL accept it, store it under an object key ending `.pdf`, and enqueue ingestion; EPUB validation behavior SHALL remain unchanged; any other extension/content-type combination SHALL still be rejected with the existing typed validation errors.
2. **ING-10** WHEN a PDF ingestion job runs THEN a Docling-backed parser implementing the document parser port SHALL produce the same `ParsedBook` shape EPUB produces (sections with titles, depths, section paths, anchors, typed blocks), with OCR disabled and table structure enabled, and tables SHALL appear in section markdown as text.
3. **ING-11** WHEN a PDF is parsed THEN every section anchor SHALL follow the scheme `pdf:{heading-path-slug}/b{ordinal}` with a content-hash suffix, and parsing the same bytes twice SHALL yield identical anchors, section paths, and chunks.
4. **ING-12** WHEN PDF corpus chunks are built THEN each chunk's `page_span` SHALL carry the page range of its source blocks, and section reads/citations SHALL expose page information (EPUB chunks keep `page_span = None`).
5. **ING-13** WHEN a PDF contains text before the first detected heading THEN the system SHALL synthesize an opening section for it (parity with EPUB's opening-section rule).
6. **ING-14** WHEN an uploaded PDF is corrupt, encrypted/password-protected, or yields zero non-empty text blocks THEN ingestion SHALL fail terminally (no retry) with a typed error kind surfaced in job events.
7. **ING-15** WHEN the worker starts an ingestion job THEN it SHALL select the parser by the source's stored content type, and a source whose content type maps to no registered parser SHALL fail terminally with a typed error.
8. **ING-16** WHEN a previously ingested PDF is re-ingested (restart) THEN corpus replace SHALL run as today and quiz items SHALL reconcile through the existing keep/stale/relocate/orphan flow with scheduling state untouched (deterministic anchors → keeps).

**Independent Test**: Ingest a small generated PDF end-to-end (docling installed); assert corpus sections/chunks with page spans, then ask a question and receive a citation carrying the pdf anchor.

---

### P1: Isolated PDF worker topology ⭐ MVP

**User Story**: As the operator, I want PDF parsing (CPU/memory heavy, minutes per book) isolated from the main worker so that EPUB ingestion, embedding, and quiz generation never queue behind or die with a pathological PDF.

**Why P1**: Docling needs ~2–4 GB RAM headroom; without isolation one bad PDF takes down all ingestion.

**Acceptance Criteria**:

1. **ING-17** WHEN a PDF source's ingestion is enqueued THEN the task SHALL be routed to the dedicated `ingest-pdf` queue; EPUB ingestion and all other tasks SHALL keep using the default queue; routing SHALL be decided at enqueue time from the source's content type.
2. **ING-18** WHEN the compose stack runs THEN a `worker-pdf` service SHALL consume only the `ingest-pdf` queue with concurrency 1, a memory limit, and `worker_max_tasks_per_child=1`, in both local and prod compose files; the existing `worker` service SHALL NOT consume `ingest-pdf`.
3. **ING-19** WHEN the PDF worker image is built THEN Docling and its models SHALL be baked into that image (no model download at task time; conversion works without network egress), the `docling` dependency SHALL live in an optional dependency extra, and the api/worker images SHALL NOT install it.
4. **ING-20** WHEN PDF-related settings are needed THEN they SHALL follow the `LEARNY_*` settings pattern (at minimum `LEARNY_PDF_MAX_BYTES`) and be documented in `backend/.env.example` and the prod env examples.

**Independent Test**: `docker compose config` shows the `worker-pdf` service with the required flags/limits; enqueue routing unit test asserts queue selection by content type.

---

### P2: Citation continuity via anchor aliases

**User Story**: As a user with existing citations, teaching sessions, and quiz items, I want anchors that normalization merged away to keep resolving so that nothing I saved dangles after a re-ingest.

**Why P2**: Continuity matters only after a re-ingest under the new normalizer; the alias map ships with P1 (ING-05) — this story makes consumers alias-aware.

**Acceptance Criteria**:

1. **ING-21** WHEN `GET /api/sources/{id}/section?anchor=` is called with an anchor that is an alias of a surviving section THEN the system SHALL return that surviving section (200), and canonical anchors SHALL keep resolving exactly as today.
2. **ING-22** WHEN quiz reconciliation runs after a corpus replace THEN an item whose anchor is now an alias SHALL reconcile to the surviving section's canonical anchor (relocate/keep, not orphan), with scheduling and review history untouched.
3. **ING-23** WHEN teaching-scoped retrieval filters by a target anchor that is an alias THEN evidence from the surviving section SHALL be returned.

**Independent Test**: Build corpus where normalization merges a section; call the section endpoint with the merged-away anchor and assert the surviving section returns.

---

### P2: ADR-0022 — PDF ingestion via Docling + corpus normalization

**User Story**: As a future maintainer, I want the Docling adoption, its license/governance rationale, the rejected alternatives, and the normalization-pass architecture recorded.

**Acceptance Criteria**:

1. **ING-24** WHEN the cycle ships THEN `docs/adr/0022-*.md` SHALL exist (Accepted), covering: Docling for PDF (MIT/LF, CPU-viable), ebooklib retained for EPUB (anchor-stripping rejection), the format-agnostic normalization pass with anchor aliasing, the PDF anchor scheme, and the isolated worker topology — cross-referencing RFC-002 and the research evidence.

---

## Edge Cases

- WHEN a PDF has no detected headings at all THEN the corpus SHALL be a single section titled from PDF metadata title, else the uploaded filename stem passed through the title cascade (never empty).
- WHEN normalization would merge every section (pathologically sparse book) THEN at least one section SHALL always survive holding all content.
- WHEN Gutenberg START/END markers are absent THEN no content SHALL be stripped by the marker rule (rule only fires on marker presence).
- WHEN two merged-away anchors alias the same surviving section THEN both SHALL resolve to it; WHEN an alias collides with a canonical anchor in the same document THEN the canonical anchor SHALL win lookups.
- WHEN a PDF exceeds `LEARNY_PDF_MAX_BYTES` THEN upload SHALL be rejected with the existing 413/validation semantics.
- WHEN the same heading text repeats across sections THEN PDF anchors SHALL remain unique (ordinal + hash disambiguate).
- WHEN a `.pdf` file is uploaded with content type `application/epub+zip` (or vice versa) THEN validation SHALL reject the mismatch.

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| -------------- | ----- | ----- | ------ |
| ING-01..08 | P1: Normalization (F7) | Design | Pending |
| ING-09..16 | P1: PDF via Docling | Design | Pending |
| ING-17..20 | P1: Worker topology | Design | Pending |
| ING-21..23 | P2: Anchor aliases | Design | Pending |
| ING-24 | P2: ADR-0022 | Design | Pending |

**Coverage:** 24 total, 0 mapped to tasks, 24 unmapped ⚠️ (mapping happens in tasks.md)

---

## Implicit-Requirement Dimensions Sweep (Large — all dimensions)

| Dimension | Resolution |
| --------- | ---------- |
| Input validation & bounds | ING-09 (extension/MIME/size), ING-14 (corrupt/encrypted/empty), existing title/size rules unchanged |
| Failure / partial-failure | ING-14 terminal classification; corpus replace stays transactional (all-or-nothing per step); ING-18 contains resource kills |
| Idempotency / retry / duplicates | ING-01 (idempotent pass), ING-11 (deterministic anchors), ING-16 (re-ingest reconciliation); corpus replace already idempotent |
| Auth boundaries & rate limits | N/A new — PDF rides the existing upload endpoint, ownership, and rate limits; no new endpoints |
| Concurrency / ordering | ING-17/18 (queue isolation, concurrency 1); existing per-source job claiming unchanged |
| Data lifecycle / expiry | Aliases live and die with corpus replace (delete-then-insert cascade); no new retention rules |
| Observability | ING-07 normalization counts event; existing structured logs/trace fields apply to the new worker unchanged |
| External-dependency failure | Docling is local/in-process; ING-19 removes network dependence (baked models); no circuit breaker needed |
| State-transition integrity | Existing ingestion job state machine reused untouched (ING-15/16 map to failed/completed) |

---

## Success Criteria

- [ ] Noisy-EPUB fixture ingests with zero filename-derived titles and a nested (depth > 0 somewhere) tree; golden clean fixture unchanged (ING-08).
- [ ] A real PDF ingests end-to-end locally (docling installed) and a cited answer returns a `pdf:` anchor with a page span.
- [ ] Full backend suite + ruff green with docling **not** installed (CI parity); docling-gated tests skip cleanly.
- [ ] `docker compose config` validates both worker services with the required isolation flags.
