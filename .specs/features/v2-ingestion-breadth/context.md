# Ingestion Breadth Context

**Gathered:** 2026-07-17 (auto-decided under learny-ship-cycle orchestration; no user prompts — escalation rule not triggered: no product-direction change, the external dependency (Docling) was locked by accepted RFC-002 + research evidence, and every decision below has a defensible recommendation)
**Spec:** `.specs/features/v2-ingestion-breadth/spec.md`
**Status:** Ready for design

---

## Feature Boundary

RFC-002 Cycle F verbatim: format-agnostic corpus normalization pass (F7), DoclingPdfParser behind the existing ingestion port with isolated `ingest-pdf` worker topology, PDF anchor scheme + re-ingest reconciliation, ADR-0022. Nothing else.

---

## Implementation Decisions (auto-decided, option sets recorded)

### D-1 → AD-082: Slice shape — backend+worker+compose, no frontend feature

- **Chosen:** Ship without new UI surfaces.
- Options: (a) **backend-only slice** — recommended: the frontend has no upload accept filter and all screens consume format-agnostic API shapes, so PDF "just appears"; why-not: departs from AD-010 full-slice cadence (4th such departure — flag at merge gate). (b) add PDF-specific UI (format badge, page-span rendering in citations popover) — why-recommend: visible polish; why-not: page spans already flow through existing citation text fields, and RFC-002 line 80-83 scopes no frontend work; adding it risks the cycle's size budget.

### D-2 → AD-083: Port evolution — rename to `DocumentParserPort`

- **Chosen:** Rename `EpubParserPort` → `DocumentParserPort` (same `parse(source_bytes, *, filename) -> ParsedBook` shape); `InvalidEpubError` → `InvalidDocumentError` (kept as alias-free rename; call sites updated); a small format-dispatch factory at the worker composition root (`tasks.py:_build_step`) selects the adapter by `source.content_type`.
- Options: (a) **rename/widen** — recommended: RFC says "behind the existing ingestion port"; one port + dispatch keeps `BuildCorpus` untouched; why-not: rename ripples through ~6 files and tests (mechanical, low risk). (b) parallel `PdfParserPort` + second corpus step — why-recommend: zero touch on EPUB path; why-not: duplicates BuildCorpus wiring and forks the corpus semantics the normalization pass must share. (c) keep the EPUB name, register PDF under it — why-recommend: smallest diff; why-not: leaves a lying name at a domain boundary the ADR will document.

### D-3 → AD-084: Normalization = pure application-layer pass on `ParsedBook`

- **Chosen:** `app/application/normalization.py`: `normalize_book(book: ParsedBook) -> NormalizationResult` (normalized `ParsedBook` + anchor-alias map + counts), called inside `BuildCorpus` between `parser.parse()` and record building. Pure, deterministic, idempotent. Heuristics per research §4: title-inference cascade (generic pattern `^(part|split|index|text|wrap|ch(apter)?)?[_-]?\d+$` or file-stem match), flat-TOC hierarchy re-derivation from heading levels, depth clamping to parent+1, trivial-section merge (<30 words, no own heading, or image/caption-only), Gutenberg START/END marker stripping.
- Options: (a) **application-layer pass** — recommended: the single seam both parsers flow through; testable pure; format-agnostic per research §4 conclusion; why-not: golden fixture expected values need deliberate updates. (b) per-adapter cleanup inside each parser — why-recommend: adapters own their format's quirks; why-not: duplicates every heuristic across formats, exactly what F7's research rejects. (c) SQL-side cleanup post-persist — why-recommend: no parser changes; why-not: aliases and merges would mutate persisted rows outside the transaction that built them; untestable without DB.

### D-4 → AD-085: Anchor aliases persisted on corpus sections

- **Chosen:** `anchor_aliases: list[str]` on `ParsedSection`→`corpus_sections` (Postgres `TEXT[]`, migration 0009), written by corpus replace. Alias-aware lookups: `get_section` falls back to `= ANY(anchor_aliases)`; quiz reconcile's `ReconcileSection` exposes aliases so alias-matched items relocate to the canonical anchor; teaching-scoped retrieval expands the target anchor to {canonical + aliases} before filtering. Canonical wins on collision.
- Options: (a) **TEXT[] column** — recommended: aliases are section-owned, replaced atomically with the section, no join; why-not: array-membership lookup needs a GIN index only if books produce hundreds of aliases (they won't — dozens at most; index deferred). (b) separate alias table — why-recommend: relationally pure, indexable; why-not: another table + FK + repository surface for a small bounded list. (c) no persistence, resolve at normalize time only — why-not: consumers (section reader, quiz reconcile) run long after ingestion; aliases must survive in the DB.

### D-5 → AD-086: PDF anchor scheme

- **Chosen:** Section anchor = `pdf:{heading-path-slug}/b{ordinal:04d}-{sha256(normalized_section_text)[:16]}`; heading-path slug from normalized heading slugs joined by `/`; ordinal = section index within its parent; `page_span` (start, end) persisted on chunks (existing reserved `SectionChunk.page_span`) and surfaced through section/citation reads. Deterministic for identical bytes + parser version. Block JSON pointers (`#/texts/42`) are NOT anchors (index-fragile).
- Options: (a) **research §3 composite** — recommended: layered stability (path survives re-parse, hash catches content identity, page span is the human citation); why-not: anchors are long/ugly (invisible to users — only citations' page spans surface). (b) page-number-only anchors — why-recommend: simple, human-meaningful; why-not: collide across sections on a page and break on any repagination. (c) document-global block index — why-not: shifts wholesale on any parser change; research explicitly rejects.

### D-6 → AD-087: Worker topology + dependency packaging

- **Chosen:** Route `run_ingestion` to `ingest-pdf` queue at enqueue time (`apply_async(queue=...)`) when the source content type is PDF; EPUB and all other tasks stay on the default queue. New compose service `worker-pdf` (base + prod overlays): `--queues ingest-pdf --concurrency 1`, `mem_limit: 4g` (research §1: 2–4 GB headroom), `worker_max_tasks_per_child=1` via CLI flag `--max-tasks-per-child 1`. `docling` lives in a uv optional extra (`[project.optional-dependencies] pdf`); new Dockerfile stage/target bakes models via `docling.utils.model_downloader.download_models()` at build. api/worker images unchanged.
- Options: (a) **enqueue-time routing** — recommended: one task name, routing decided where content_type is at hand; why-not: routing logic lives in application code rather than Celery `task_routes` config. (b) separate `run_pdf_ingestion` task + static task_routes — why-recommend: declarative routing; why-not: duplicates the whole ingestion body/state machine for a queue name. (c) same worker, higher mem — why-not: violates RFC line 82 and leaves the crash blast radius shared.

### D-7 → AD-088: PDF failure semantics

- **Chosen:** `InvalidDocumentError` (corrupt/encrypted/zero-text) → terminal job failure, no retry — same classification path EPUB uses today (`EpubCorpusIngestionStep` terminal branch). Resource kills (OOM, time limit): contained by mem_limit + `--max-tasks-per-child 1`; job lands in failed via existing redelivery/timeout accounting; `task_time_limit` stays global (1800 s covers ~400-page books at research's ~0.8–3 s/page; revisit only if evidence demands).
- Why-not alternatives: retryable classification for corrupt PDFs would loop a deterministic failure 3×; a PDF-specific longer time limit adds per-queue config for a bound no current book approaches.

### D-8 → AD-089: Docling test strategy

- **Chosen:** Split the adapter: thin `_convert(bytes) -> DoclingDocument` (docling import local to function) + pure `_to_parsed_book(doc) -> ParsedBook` mapping. Mapping unit tests construct `DoclingDocument` trees via `docling-core` (light, pydantic) added to the dev group; real end-to-end conversion tests use a tiny programmatically generated PDF and `pytest.importorskip("docling")` — skipped in CI (docling not installed), runnable locally in the pdf extra env.
- Why-not alternatives: requiring docling in CI adds ~1 GB+ of models and minutes to every run for one adapter; committing binary PDF fixtures violates the repo's reviewable-fixture convention (EPUBs are built in code) — generate the PDF in-test instead.

### D-9: Golden fixture policy (feature-local)

- Normalization changes expected corpus output only where fixtures are deliberately noisy. The golden clean book must pass through unchanged (ING-08 is the regression sensor). Any golden_expected.py change must be hand-reviewed line-by-line in the task that makes it — never regenerated blindly.

### Agent's Discretion

- Exact slugification rules for heading-path slugs, the styled-text heuristic for the title cascade step (d), and normalization counts event field names — design/implementation detail within the ACs.

### Declined / Undiscussed Gray Areas → Assumptions

None — orchestrated auto-decision mode; every gray area above is recorded with its option set in this file and as AD-082..AD-089.

---

## Specific References

- `docs/research/2026-07-12/pdf-docling-epub.md` — load-bearing research (§1 Docling state, §3 anchor scheme, §4 hardening heuristics, §5 alternatives). Calibre heuristics are the pattern family for title/chapter detection.
- QA F7 (`docs/ops/e2e-qa-report-2026-07-12.md:86-90`) — the fixture design target for the noisy-EPUB test.

## Deferred Ideas

- Per-source OCR opt-in for scanned PDFs (research §1 flags the runtime cost; needs UI + settings).
- GIN index on `anchor_aliases` if alias counts ever grow past dozens per document.
- Localized chapter-heading regex families (non-English books).
- Modeling stripped Gutenberg boilerplate as flagged "furniture" records rather than exclusion (research §4.5's stricter suggestion).
