# ADR-022: PDF Ingestion Via Docling And Corpus Normalization

- **Date**: 2026-07-17
- **Status**: Accepted
- **Deciders**: Augusto, Codex
- **Tags**: architecture, ingestion, pdf, epub, structure, normalization, docling, citations, worker

## Context and Problem Statement

Learny ingests and teaches from EPUB books with cited Q&A and quizzes (ADR-0010/0020/0021),
but real-world books exist primarily as PDFs — the majority of a typical reader's library.
Separately, production EPUB ingestion reveals structure quality issues (QA finding F7):
commercially distributed and Project Gutenberg EPUBs carry filename-derived section titles
(`part0034`, `wrap0000`), flat or mis-nested hierarchies where the table of contents
reports no depth but section headings show distinct levels, and meaningful content attached
to caption-level anchors while section boundaries own nothing. These issues degrade every
downstream surface: the teaching target picker, cited answers, and quiz section eligibility.

RFC-002 Cycle F addresses both concerns: a format-agnostic structure normalization pass
that cleans parsed EPUB and PDF documents before corpus records are built, and a Docling-backed
PDF parser behind the existing ingestion port, isolated in a dedicated worker queue with
bounded memory to prevent pathological PDFs from starving EPUB ingestion or the API.

The decisions to make are: which PDF parsing library; whether to keep ebooklib for EPUB
or use the same adapter for both; where to place the normalization logic; how to handle
anchors that normalization merges away; what PDF anchor scheme enables re-ingest stability;
and how to isolate PDF parsing without duplicating the ingestion corpus pipeline.

Research evidence: `docs/research/2026-07-12/pdf-docling-epub.md`.

## Decision Drivers

- Eliminate F7: every ingested book has human-meaningful section titles, sane hierarchy,
  and no boilerplate noise in its corpus.
- Enable PDF ingestion end-to-end (upload, structure parse, corpus build, embedding,
  cited Q&A, teaching, quizzes) with the same quality guarantees as EPUB.
- Keep PDF parsing (CPU/memory heavy, minutes per book) isolated so a pathological PDF
  cannot starve EPUB ingestion or crash the API worker.
- Ensure citations and quiz items remain valid after corpus normalization or re-ingest;
  anchor merges must not break saved sessions or items.
- Keep the parser SDK and model orchestration behind Learny-owned ports (ADR-0007/0009);
  keep CI and local development offline and key-free by default.
- Choose a parser with permissive open-source licensing and active governance fit for
  an OSS-ready portfolio project.

## Considered Options

### Parser Selection
- Docling 2.112+ (MIT, Linux Foundation hosted)
- marker (GPL-3 code + revenue-capped model weights)
- PyMuPDF4LLM (AGPL)
- unstructured (Apache 2.0, open-core focus)

### EPUB Strategy
- Keep ebooklib, replace with Docling for both formats
- Use Docling for EPUB and PDF

### Normalization Placement
- Format-agnostic application-layer pass on `ParsedBook` (post-parse, pre-corpus)
- Per-adapter cleanup inside each parser
- SQL-side cleanup post-persist

### Anchor Handling for Merged Sections
- Persist merged-away anchors as aliases on the surviving section
- No persistence, resolve at normalize time only
- Separate alias table

### PDF Anchor Scheme
- Composite: heading-path slug + page span + content hash
- Page-number-only anchors
- Document-global block index

### Worker Topology
- Dedicated ingest-pdf queue, separate compose service with bounded memory
- Same worker, higher memory limit
- Separate run_pdf_ingestion task with static routing

## Decision Outcome

Chosen option: **Docling 2.112+ (MIT, Linux Foundation–hosted) for PDF; ebooklib retained
for EPUB; a pure format-agnostic normalization pass applied post-parse and pre-corpus-build;
merged-away anchors persisted as aliases on corpus sections; a composite PDF anchor scheme
with heading-path, ordinal, and content hash; and a dedicated ingest-pdf Celery queue routed
at enqueue time with an isolated worker service (concurrency 1, 4 GB memory limit, one task
per child process), docling in an optional dependency extra, and models pre-baked into the
worker image at build time.**

The implementation model is:

1. **Docling for PDF.** Add `docling>=2.112,<3` as an optional uv dependency group (`pdf`
   extra); import it only inside the adapter module so the API image stays slim. Use the
   standard PDF pipeline with `do_ocr=False` (born-digital text focus; OCR is ~60% CPU cost,
   deferred to per-source opt-in later) and `do_table_structure=True`. Terminal errors
   (corrupt, encrypted, zero-text PDFs) fail the job with a typed `InvalidDocumentError`,
   mapped to existing failure handling (no retry).

2. **ebooklib retained for EPUB.** Docling's EPUB/HTML backend strips anchor IDs and
   internal links (docling issue #2929) — fatal for Learny's anchor-based citations and
   quiz item grounding. Keep ebooklib (ADR-0011) as the EPUB adapter; hardening is applied
   by the shared normalization pass, not per-adapter.

3. **Format-agnostic normalization pass.** `app/application/normalization.py`:
   `normalize_book(book: ParsedBook) -> NormalizationResult` (normalized `ParsedBook` +
   anchor-alias map + event counts). Pure, deterministic, idempotent, called inside
   `BuildCorpus` post-parse and pre-record-building. Heuristics per research §4:
   
   - **Title inference cascade**: Generic title patterns (`^(part|split|index|text|wrap|ch(apter)?)?[_-]?\d+$` or file-stem match) are replaced with the first heading text in the section, else first short (<80 chars) styled text, else `Untitled section (N)`.
   - **Flat-TOC hierarchy re-derivation**: When the TOC yields all sections at depth 0 but section headings carry distinct levels, rebuild section depth from heading levels in reading order.
   - **Depth clamping**: Clamp each section's depth to at most parent depth + 1; keep derived markdown heading levels within h1–h6.
   - **Trivial-section merge**: Merge sections with <30 words and no own heading, or only image/caption, into the adjacent surviving section; merged anchors become aliases of the survivor.
   - **Gutenberg marker stripping**: Exclude content outside the standard `*** START OF THE PROJECT GUTENBERG EBOOK … ***` / `*** END OF … ***` markers when present.
   
   Normalization records a counts event (titles replaced, sections merged, depths adjusted,
   noise blocks stripped) alongside the existing `corpus_built` event. Clean books (golden
   fixture) pass through unchanged (byte-identity verified in the golden ingestion tests).

4. **Anchor aliases persisted on corpus sections.** Add `anchor_aliases: list[str]`
   (`TEXT[]` column, migration 0009) on `corpus_sections`. Repository `replace` writes
   aliases when normalizing. Lookups: `get_section` falls back to `= ANY(anchor_aliases)`;
   quiz reconciliation recognizes aliases so items relocate to the canonical anchor;
   teaching-scoped retrieval expands the target anchor to {canonical + aliases} before
   filtering. Canonical anchors win on collision.

5. **PDF anchor scheme: `pdf:{heading-path-slug}/b{ordinal:04d}-{content-hash16}`.**
   Heading-path slug from normalized heading slugs joined by `/`; ordinal = section index
   within its parent; content hash = first 16 hex digits of SHA256(normalized block text).
   Page span (start, end) persists on chunks (existing `SectionChunk.page_span` field) and
   is surfaced through section/citation reads as the human-facing citation (e.g., "pp. 142–143").
   Deterministic for identical bytes within the same parser version; survives re-ingest
   through hash + path matching and enables reconciliation after parser upgrades.

6. **Isolated worker topology.** Route PDF ingestion to `ingest-pdf` queue at enqueue time
   (apply_async(queue=...)) when source content type is PDF; EPUB and other tasks stay on
   the default queue. New compose service `worker-pdf` (base + prod overlays):
   `--queues ingest-pdf --concurrency 1`, `mem_limit: 4g`, `worker_max_tasks_per_child=1`
   via CLI flag. Docling + models baked into a separate image target via `docling.utils.model_downloader.download_models()` at build. api/worker images unchanged;
   CI-gated tests skip cleanly without docling installed (parity with existing `live` marker
   precedent).

7. **Select the parser at the worker composition root** (`tasks.py:_build_step`) by
   `source.content_type` via a format-dispatch factory that lazily imports the PDF adapter,
   falling back to a terminal error if the content type matches no registered parser.

8. **Rename the port `EpubParserPort` → `DocumentParserPort`** and error `InvalidEpubError` →
   `InvalidDocumentError` (same parse shape; rename reflects format-agnostic scope). No
   back-compat aliases; call sites updated.

This closes the PDF ingestion and structure-quality follow-up (F7 and RFC-002 Cycle F)
in a single integrated change: normalization applies to all ingestions; PDF adds a second
parser behind the existing port; isolation prevents pathological PDFs from disrupting
the product.

### Positive Consequences

- F7 fixed: noisy EPUBs produce corpora with heading-derived titles, nested hierarchy,
  and no boilerplate. Clean books pass through unchanged.
- PDF support closes the format gap for real-world reader libraries; identical corpus,
  citation, teaching, and quiz semantics as EPUB.
- Isolated PDF parsing with bounded memory prevents resource starvation; one pathological
  PDF cannot crash EPUB ingestion or the API.
- Anchors that normalization merges remain valid via alias resolution; existing citations,
  teaching sessions, and quiz items never dangle after re-ingest.
- Deterministic PDF anchors with page-span citations enable stable re-ingest reconciliation
  and reader-friendly page references.
- The parser stays behind ports; swapping PDF libraries later is an adapter + tests exercise,
  not a domain-logic rewrite.
- CI/local stays offline and key-free; docling is optional and tests skip gracefully without it.
- Negligible cost: Docling is CPU-only, models (~1 GB) are pre-baked into the worker image
  (no runtime network), and 400-page books process in 5–20 minutes on typical CPU hardware.

### Negative Consequences

- Normalization heuristics are English-first (pattern families for filenames, chapter detection).
  Localized heading-pattern variants are deferred.
- Golden fixture expected values must be deliberately updated where the normalizer changes
  output; the unchanged clean-book golden fixture is the regression sensor.
- A re-ingest under the new normalizer will relocate quiz items via reconciliation if
  normalization changes section anchors, requiring validation that resolved items remain
  grounded in the new corpus.
- Docling adoption adds a new external dependency with models; a dedicated worker image
  grows ~1 GB. Docling's Linux Foundation governance is low-risk but introduces a new
  vendor relationship.
- Depth-clamping and title-inference heuristics are not perfect (edge cases with unusual
  structure); hand-correction of corpus after ingestion is still necessary for corner cases.

## Pros and Cons of the Options

### Docling 2.112+ for PDF, ebooklib for EPUB ✅ Chosen

- ✅ MIT license + Linux Foundation governance (permissive, active, stable).
- ✅ Best-in-class structured extraction (headings with levels, reading order, tables,
  page provenance) on CPU at ~0.8–3 s/page (400-page book ≈ 5–20 min, acceptable for
  Celery worker).
- ✅ DoclingDocument tree maps 1:1 onto Learny's document/section/block/chunk model.
- ✅ Page provenance (prov.page_no per item) enables stable page-span citations.
- ✅ ebooklib kept for EPUB (Docling's EPUB backend loses anchor IDs).
- ❌ Docling adoption is a new external dependency; models (~1 GB) require pre-bake into
  worker image. OCR disabled (do_ocr=False) for born-digital focus; per-source scanned-PDF
  support is deferred.

### marker for both EPUB and PDF ❌ Rejected

- ✅ Competitive extraction quality (per benchmarks).
- ❌ **GPL-3 code + OpenRAIL-M weights with revenue cap** — license incompatible with
  Learny's OSS-ready goal (MIT license required for portfolio projects).

### PyMuPDF4LLM for PDF ❌ Rejected

- ✅ Fastest CPU option.
- ❌ **AGPL-3 license** — incompatible with OSS goal.
- ❌ Weaker heading hierarchy and table fidelity than Docling; poor fit for structured books.

### unstructured (Apache 2.0) for PDF ❌ Rejected

- ✅ Permissive license; broad format support.
- ❌ Weaker document hierarchy / element typing than Docling; enterprise/tooling focus rather
  than readable document structure (better fit for document databases than book corpora).

### Use Docling for both EPUB and PDF ❌ Rejected

- ❌ Docling's EPUB/HTML backend strips anchor IDs and internal links (docling issue #2929),
  making it impossible to implement Learny's anchor-based citation and quiz grounding.
  Unacceptable; ebooklib must stay.

### Per-adapter normalization (heuristics in each parser) ❌ Rejected

- ✅ Adapters own their format's quirks.
- ❌ Duplicates every heuristic across formats; exactly the anti-pattern research §4 rejects
  for F7. The single seam where both parsers flow is `BuildCorpus` → normalize → persist.

### SQL-side normalization (post-persist cleanup) ❌ Rejected

- ✅ No parser changes needed.
- ❌ Aliases and merges would mutate persisted rows outside the transaction that built them;
  impossible to keep consistent. Untestable without a running DB; violates pure-logic pattern.

### Separate alias table ❌ Rejected

- ✅ Relationally pure, indexable.
- ❌ Another table + FK + repository surface for a small bounded list (dozens of aliases per
  document max). `TEXT[]` column is simpler and aliases are section-owned, replaced atomically
  with the section.

### No alias persistence ❌ Rejected

- ✅ Simpler schema.
- ❌ Aliases must survive in the DB; consumers (section reader, quiz reconcile, teaching
  retrieval) run long after ingestion and must resolve merged anchors. Aliasing at normalize-time
  only is insufficient.

### Page-number-only PDF anchors ❌ Rejected

- ✅ Simple, human-readable.
- ❌ Collide across sections on the same page; break on any re-pagination. Research §3 explains
  layered stability: path + page + hash.

### Document-global block index as PDF anchor ❌ Rejected

- ❌ Shifts wholesale on any parser change; research §3 explicitly rejects. Ordinal within
  section (+ path) is far more stable.

### Same worker, higher memory limit ❌ Rejected

- ❌ Violates RFC-002 line 82: isolation is non-negotiable. Shared workers risk starvation and
  crash propagation. Dedicated queue + bounded service is the design.

### Separate `run_pdf_ingestion` task + static Celery routing ❌ Rejected

- ❌ Duplicates the ingestion body and state machine for a queue name. One task name +
  content-type dispatch at enqueue is cleaner and reuses the existing abstraction.

## References

- [ADR-003: Citations And Evaluation Are Core Requirements](0003-citations-and-evaluation-are-core-requirements.md)
- [ADR-007: Use Learny-Owned Ports For AI Provider Integration](0007-use-learny-owned-ports-for-ai-provider-integration.md)
- [ADR-009: Use Learny-Owned Orchestration With Specialized Edge Libraries](0009-use-learny-owned-orchestration-with-specialized-edge-libraries.md)
- [ADR-011: EPUB Parsing And DOM-Awareness](0011-epub-parsing-and-dom-awareness.md)
- [RFC-002: Learny v2 Roadmap](../rfc/0002-learny-v2-roadmap.md)
- PDF and EPUB ingestion research (2026-07-12): `../research/2026-07-12/pdf-docling-epub.md`
- QA finding F7 (structure quality): `../ops/e2e-qa-report-2026-07-12.md` lines 86–90
- Docling project: https://github.com/docling-project/docling
- Docling PyPI: https://pypi.org/project/docling/
- Docling documentation: https://docling-project.github.io/docling/
- Docling issue #2929 (EPUB anchor stripping): https://github.com/docling-project/docling/issues/2929
- marker project: https://github.com/datalab-to/marker
- PyMuPDF documentation: https://github.com/pymupdf/pymupdf
- Linux Foundation AI & Data: https://lfaidata.foundation/
