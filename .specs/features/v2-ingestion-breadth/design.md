# Ingestion Breadth Design

**Spec**: `.specs/features/v2-ingestion-breadth/spec.md`
**Context**: `.specs/features/v2-ingestion-breadth/context.md` (AD-082..AD-089 locked)
**Research**: `docs/research/2026-07-12/pdf-docling-epub.md` (load-bearing; verify docling API details against the installed version — pinned research date 2026-07-12, docling v2.112.0)
**Status**: Approved (auto, ship-cycle)

---

## Architecture Overview

Two seams change; everything downstream stays put.

1. **Parse seam**: `EpubParserPort` becomes `DocumentParserPort`; a format-dispatch factory at the worker composition root picks `EbooklibEpubParser` or `DoclingPdfParser` from `source.content_type`. Both return the same `ParsedBook`.
2. **Normalize seam (new)**: `BuildCorpus` calls `normalize_book(parsed)` between `parser.parse()` (corpus.py:84) and record building (corpus.py:86-108). The pass is pure and returns a normalized `ParsedBook` whose sections may carry `anchor_aliases`, plus counts for the job event.

```mermaid
graph TD
    U[Upload .epub/.pdf] --> V[validate_source_upload<br/>per-format table]
    V --> S[(S3 object key .epub/.pdf)]
    E[StartIngestion] -->|content_type| Q{enqueuer routing}
    Q -->|epub| W[worker: default queue]
    Q -->|pdf| WP[worker-pdf: ingest-pdf queue<br/>conc 1, mem 4g, max-tasks 1]
    W --> P[factory: EbooklibEpubParser]
    WP --> P2[factory: DoclingPdfParser<br/>do_ocr=False, tables on]
    P --> N[normalize_book — pure pass]
    P2 --> N
    N --> BC[BuildCorpus records + aliases]
    BC --> DB[(corpus_* + anchor_aliases TEXT[])]
    DB --> C1[get_section: alias fallback]
    DB --> C2[quiz reconcile: alias → canonical relocate]
    DB --> C3[teaching retrieval: anchor set expansion]
```

## Code Reuse Analysis

| Component | Location | How to Use |
| --------- | -------- | ---------- |
| `ParsedBook/ParsedSection/ParsedBlock/SectionChunk` DTOs | `backend/app/domain/entities.py:203-266` | Extend: `ParsedSection.anchor_aliases: tuple[str, ...] = ()`, `ParsedBlock.page_span: tuple[int, int] | None = None`; `SectionChunk.page_span` already reserved |
| `EbooklibEpubParser` | `backend/app/infrastructure/ingestion/epub.py:65` | Unchanged parsing; implements renamed port; its `_fallback_title` stays (normalization overrides generic titles later) |
| `BuildCorpus` | `backend/app/application/corpus.py:50` | Insert normalize call; append `corpus_normalized` event next to `corpus_built` (corpus.py:118) |
| `pack_chunks` | `backend/app/application/chunking.py:21` | Extend to accept per-block page spans; roll min/max into `SectionChunk.page_span` |
| `SqlAlchemyCorpusRepository.replace/get_section/section_texts` | `backend/app/infrastructure/db/repositories.py:352,470,498` | Write/read `anchor_aliases`; alias fallback lookup |
| `ReconcileQuizItems` | `backend/app/application/quiz.py:470-497` | Add alias→canonical resolution before keep/stale/relocate/orphan (AD-078 semantics preserved) |
| `EpubCorpusIngestionStep` terminal/retryable split | `backend/app/infrastructure/worker/steps.py:36` | Same classification for `InvalidDocumentError`; rename EPUB-specific names |
| `IngestionEnqueuer` port + Celery adapter (AD-016) | worker/infrastructure | Additive queue routing keyed on content type inside the **adapter**; Celery never enters application code |
| Settings pattern + `get_settings()` | `backend/app/core/config.py:81-90` | New `pdf_max_bytes`; group with epub caps |
| EPUB test builders | `backend/tests/epub_builder.py`, `fixtures_epub.py` | New noisy fixtures (gutenberg/flat-TOC/caption-anchor) built as code |
| Provider factory precedent (AD-052/AD-059) | `app/infrastructure/ai/*` factories | Same shape for the parser dispatch factory |

### Integration Points

| System | Integration Method |
| ------ | ------------------ |
| Ingestion job events | New `corpus_normalized` event type, same append path as `corpus_built` (`corpus.py:118`) |
| Migration chain | `0009_anchor_aliases` after `0008_quiz_schema`: `ALTER TABLE corpus_sections ADD COLUMN anchor_aliases TEXT[] NOT NULL DEFAULT '{}'` |
| Compose | New `worker-pdf` service in base + prod overlay; existing `worker` untouched |
| CI | Unchanged — docling never installed in CI; `docling-core` joins the dev group (pydantic-only, light) |

---

## Components

### 1. `DocumentParserPort` (rename of `EpubParserPort`)

- **Location**: `backend/app/domain/ports.py:274`
- **Interfaces**: `parse(self, source_bytes: bytes, *, filename: str) -> ParsedBook` — unchanged shape. Raises `InvalidDocumentError` (rename of `InvalidEpubError`; update all raisers/handlers/tests; no alias kept).
- **Reuses**: existing protocol; mechanical rename across ~6 modules + tests.

### 2. `normalize_book` — the normalization pass (ING-01..08)

- **Purpose**: format-agnostic structure cleanup; the F7 fix.
- **Location**: `backend/app/application/normalization.py` (new; pure, no I/O, no settings dependency — thresholds are module constants).
- **Interfaces**:
  - `normalize_book(book: ParsedBook) -> NormalizationResult`
  - `NormalizationResult(book: ParsedBook, counts: NormalizationCounts)` — aliases live on the returned sections' `anchor_aliases`.
  - `NormalizationCounts(titles_replaced: int, sections_merged: int, depths_adjusted: int, noise_blocks_stripped: int)` (frozen dataclass; event payload).
- **Pipeline order (fixed, documented in module docstring)**:
  1. **Gutenberg strip** (ING-06): if any block's text contains the `*** START OF THE PROJECT GUTENBERG EBOOK` marker AND a matching `*** END OF THE PROJECT GUTENBERG EBOOK` marker exists later, drop blocks before/at START and after/at END (marker blocks included). Sections left empty are handled by step 2. No markers → no-op.
  2. **Trivial-section merge + anchor promotion** (ING-05, F7's caption-anchor case): a section is trivial when its own text < 30 words AND it has no `heading` block, OR it contains only image/caption blocks. Merge direction: into the **previous surviving sibling-or-parent** (reading order owner); the document's first section merges **forward**. Merged section's anchor + its existing aliases append to the survivor's `anchor_aliases` (dedup, canonical-wins on collision). At least one section always survives (pathological case: everything merges into one).
  3. **Flat-TOC hierarchy inference** (ING-03): fires only when **all** sections have depth 0 AND ≥ 2 distinct heading levels exist among sections' first heading blocks. New depth = rank of the section's first heading level among the distinct levels (h1→0, next→1, …); sections without headings keep their predecessor's depth. `section_path` rebuilt from the new tree.
  4. **Depth clamp** (ING-04): walk in order; `depth = min(depth, prev_effective_parent_depth + 1)`; rebuild `section_path` accordingly. Markdown heading level derivation stays in the existing markup path (h1–h6 bound already enforced there — verify, else clamp here).
  5. **Title cascade** (ING-02): a title is *generic* when it case-insensitively matches `^(part|split|index|text|wrap|ch(apter)?)?[_\-]?\d+$`, equals the anchor's href stem, or is empty/whitespace. Replacement order: (a) first `heading` block's text in the section; (b) first block text < 80 chars that is the section's only short leading text (styled-heading heuristic — agent discretion per context.md); (c) `Untitled section (N)` where N = 1-based position. `section_path` leaf updated to the new title.
- **Idempotency**: each step is a fixed-point on its own output; unit test asserts `normalize(normalize(x).book).book == normalize(x).book` on every fixture.
- **Dependencies**: none beyond entities. **Reuses**: DTO immutability (rebuild via `dataclasses.replace`).

### 3. Alias persistence + consumers (ING-21..23)

- **Migration**: `backend/migrations/versions/0009_anchor_aliases.py` — `corpus_sections.anchor_aliases TEXT[] NOT NULL DEFAULT '{}'`; no index (AD-085); downgrade drops it.
- **`SqlAlchemyCorpusRepository`**:
  - `replace(...)`: persist `section.anchor_aliases` (repositories.py:427 insert).
  - `get_section(source_id, anchor)` (repositories.py:470): match `anchor = :a OR :a = ANY(anchor_aliases)`, canonical match ordered first, then position (preserves today's duplicate rule).
  - `section_texts(...)` (repositories.py:498): `ReconcileSection` gains `anchor_aliases: tuple[str, ...]` (entity `entities.py:331`).
  - New `expand_anchors(source_id, anchors: Sequence[str]) -> tuple[str, ...]`: returns input ∪ aliases of sections whose canonical anchor is in input ∪ canonical anchors of sections having an input anchor as alias. Used by teaching.
- **`ReconcileQuizItems`** (`quiz.py:470-497`): build `alias_to_canonical` from `ReconcileSection.anchor_aliases`; an item whose `item.anchor` is an alias resolves to the canonical section **before** the AD-078 decision table (then: excerpt present → relocate to canonical anchor + its section_path, stays active). Scheduling/review_log untouched (AD-078 invariant).
- **Teaching scoped retrieval** (AD-031 seam): where target + descendant anchors are resolved in the turn service, pass them through `expand_anchors` before `RetrievalPort.search(anchors=...)`. `RetrievalPort` signature unchanged.

### 4. `DoclingPdfParser` (ING-10..14)

- **Location**: `backend/app/infrastructure/ingestion/docling_pdf.py` (new; the only module importing `docling`/`docling_core`, ADR-0009).
- **Interfaces**: `class DoclingPdfParser` implementing `DocumentParserPort`; ctor takes nothing settings-dependent (artifacts path read from env by docling itself in the baked image).
- **Split (AD-089)**:
  - `_convert(source_bytes, filename) -> DoclingDocument`: `DocumentConverter` with `PdfPipelineOptions(do_ocr=False, do_table_structure=True)`, fed a `DocumentStream` (no temp files). Any converter exception, encrypted-PDF error, or zero-text result → `InvalidDocumentError` with a stable message kind. `docling` imported inside this function only.
  - `_to_parsed_book(doc: DoclingDocument, *, filename: str) -> ParsedBook`: pure mapping, unit-testable with constructed `docling-core` documents:
    - Walk `doc.body` in tree order (reading order). `SectionHeaderItem(level=n)` opens a section; depth from level nesting (normalization clamps later anyway). Preamble before the first heading → synthesized opening section (ING-13), title from `doc` metadata title else filename stem (cascade will clean it).
    - Blocks: text/list items → minimal HTML fragments (`<p>`, `<ul><li>`) so the existing `MarkupConverterPort` path works unchanged; `TableItem` → its HTML export (verify exact docling-core method against the installed version — research sketch, do not trust from memory); pictures → skipped; furniture/page-header/footer/footnote items → dropped.
    - `ParsedBlock.page_span` from item `prov[].page_no` (min, max).
    - **No heading, whole document** → single section (edge case AC).
  - Anchor (AD-086): `pdf:{'/'.join(slug(h) for h in heading_path)}/b{ordinal:04d}-{sha256(normalized_section_text)[:16]}` where ordinal = index among the parent's children and normalized text = whitespace-collapsed section block text. `slug` = lowercase, non-alnum → `-`, collapse repeats, trim, max 40 chars/segment. Determinism test: parse same bytes twice → identical `ParsedBook`.
- **Chunking**: `pack_chunks` gains optional per-block-text page spans; chunk `page_span` = min/max over its blocks (EPUB passes none → `None`).

### 5. Parser dispatch factory (ING-15)

- **Location**: `backend/app/infrastructure/ingestion/factory.py` (new).
- **Interfaces**: `build_parser(content_type: str) -> DocumentParserPort` — `application/epub+zip` → `EbooklibEpubParser(max_uncompressed_bytes=...)`; `application/pdf` → `DoclingPdfParser()` (lazy import inside branch; ImportError → `InvalidDocumentError("pdf support not installed in this worker")` so a misrouted task fails terminally, not retry-loops); unknown → `InvalidDocumentError` (terminal, typed).
- **Wiring**: `tasks.py:95` `_build_step` uses the factory with the job's source content type instead of hard-wiring `EbooklibEpubParser`.

### 6. Upload validation + routing (ING-09, ING-17)

- `validation.py`: replace the EPUB constants with a format table `{".epub": "application/epub+zip", ".pdf": "application/pdf"}`; extension↔content-type must agree; per-format size cap (`epub_max_bytes` / `pdf_max_bytes`); all existing typed `InvalidSourceUpload` kinds preserved; title rules unchanged.
- `sources.py:69`: object key extension from the validated filename extension (`.epub`/`.pdf`).
- Web handler body bound (`web/sources.py:101`): `max(epub_max_bytes, pdf_max_bytes) + 1`; per-format cap enforced in validation.
- **Enqueue routing**: the Celery `IngestionEnqueuer` adapter maps content type → queue (`application/pdf` → `ingest-pdf`, else default) via `apply_async(queue=...)`. The port signature gains the minimal additive input needed (content type or the source), decided at the call site where `StartIngestion` already holds the source (AD-016: Celery stays in the adapter).

### 7. Worker topology + image (ING-18..20)

- **Dockerfile**: new final stage/target `pdf-worker` in `backend/Dockerfile` (multi-target, single file): base steps + `uv sync --frozen --extra pdf` + bake models (`python -c "from docling.utils.model_downloader import download_models; download_models()"` — verify exact helper name against installed docling; research-sourced). Existing default target unchanged.
- **pyproject**: `[project.optional-dependencies] pdf = ["docling>=2.112,<3"]`; dev group adds `docling-core` (mapping tests).
- **Compose base**: `worker-pdf` service — build target `pdf-worker`; `command: celery -A app.worker.celery_app:celery_app worker --loglevel=info --queues ingest-pdf --concurrency 1 --max-tasks-per-child 1`; `mem_limit: 4g`; same env/depends/health pattern as `worker`. Existing `worker` command gains `--queues celery` (explicit default queue only — it must not consume `ingest-pdf`).
- **Compose prod overlay**: mirror `worker` prod entries for `worker-pdf` (`restart: unless-stopped`, `LEARNY_ENVIRONMENT`, `LEARNY_LOG_FORMAT=json`, `env_file: ./secrets/worker.env`).
- **Settings**: `pdf_max_bytes: int = 104857600` (100 MiB) in `config.py` corpus group; documented in `backend/.env.example` + prod env examples.

### 8. ADR-0022 (ING-24)

- `docs/adr/0022-pdf-ingestion-via-docling-and-corpus-normalization.md` — Accepted; contents per spec ING-24; alternatives table from research §5 (marker GPL/revenue-capped, PyMuPDF AGPL, unstructured weaker tree); ebooklib retained (docling #2929); no AI attribution; follows 0019/0020/0021 file conventions.

---

## Data Models

- `ParsedSection.anchor_aliases: tuple[str, ...] = ()` (entities.py:220) — flows into `corpus_sections.anchor_aliases TEXT[]`.
- `ParsedBlock.page_span: tuple[int, int] | None = None` (entities.py:203).
- `SectionChunk.page_span` — already exists; now populated for PDF.
- `ReconcileSection.anchor_aliases: tuple[str, ...] = ()` (entities.py:331).
- `NormalizationCounts` — event payload only, not persisted as a table.

## Error Handling Strategy

| Error Scenario | Handling | User Impact |
| -------------- | -------- | ----------- |
| Corrupt / encrypted / zero-text PDF | `InvalidDocumentError` → terminal step failure (steps.py classification), typed kind in job events | Source shows failed with reason; restart allowed |
| PDF routed to a worker without docling | factory raises `InvalidDocumentError` (terminal) | Failed job with clear operator message, no retry storm |
| Unknown content type at parse | `InvalidDocumentError` terminal | Failed job, typed event |
| PDF over size cap | existing `InvalidSourceUpload` / 413 path | Upload rejected |
| OOM / runaway parse | `mem_limit` + `--max-tasks-per-child 1` recycle; acks_late redelivery accounting → failed | Other queues unaffected |
| Storage fault during PDF read | existing `StorageUnavailable` → retryable (steps.py:36 unchanged) | Retries with backoff |

## Risks & Concerns

| Concern | Location | Impact | Mitigation |
| ------- | -------- | ------ | ---------- |
| Docling API drift vs research (model downloader path, table HTML export, DocumentStream) | `docling_pdf.py` | Adapter breaks at runtime | Phase C worker verifies every docling symbol against the **installed** pinned version before writing code; research is a sketch, not gospel |
| Golden fixture churn from normalization | `golden_expected.py`, `test_golden_*` | Silent weakening of the eval harness | D-9 policy: hand-reviewed diffs only; ING-08 (clean book unchanged) is the regression sensor |
| `get_section` duplicate-anchor order change | repositories.py:470-485 | Reader resolves a different section | Keep canonical-first + position ordering; regression test |
| `pack_chunks` signature ripple | chunking.py:21 + callers/tests | Chunk identity churn for EPUB | Additive optional param; EPUB output asserted byte-identical |
| Normalization vs quiz `content_key` stability | quiz reconcile | Mass stale/orphan after first re-ingest under new normalizer | `content_key` is content-hash (anchor-free, AD-073); title/depth changes don't touch it; merge moves text → excerpt search still finds it (relocate). Called out in ADR |
| Worker `--queues celery` explicitness | compose | Default worker silently consuming `ingest-pdf` | Compose assertion test pins both services' queue flags |

## Tech Decisions (non-obvious, feature-local)

| Decision | Choice | Rationale |
| -------- | ------ | --------- |
| Normalization thresholds | Module constants (30 words, 80 chars, regex family), not settings | Deterministic corpus identity; a settings knob would make corpus output env-dependent |
| Aliases as `TEXT[]` not table | AD-085 | Section-owned, atomic with replace |
| `worker` gains explicit `--queues celery` | Yes | Only way to guarantee it never drains `ingest-pdf` |
| Body bound before per-format cap | `max(caps)+1` read bound, exact cap in validation | Handler can't know format before reading; bound only guards memory |
| docling-core in dev group | Yes | Pure-pydantic model lib enables mapping tests in CI without docling/torch |

Project-level decisions already recorded as AD-082..AD-089 (context.md).
