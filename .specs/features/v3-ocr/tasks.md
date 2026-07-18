# v3-ocr Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement with the `tlc-spec-driven` skill (Execute flow + Critical Rules). If it cannot be activated, STOP.

**Design**: `.specs/features/v3-ocr/design.md` · **Status**: Approved (auto, ship-cycle)

## Test Coverage Matrix

> Guidelines: house patterns — pure-unit tests beside application code, `pytest.importorskip("docling")` for live suites, DB-gated integration via `LEARNY_TEST_DATABASE_URL`, golden regression files, Dockerfile/compose text asserts.

| Code Layer | Test Type | Coverage Expectation | Location | Run Command |
|---|---|---|---|---|
| Parser retry logic (`DoclingPdfParser.parse`) | unit, stubbed `_convert` | 1:1 to OCR-01..05 + docling-error edge; CI-safe (no docling) | `backend/tests/test_ingestion_docling_mapping.py` (or sibling `test_ingestion_pdf_ocr.py`) | `uv run pytest tests/test_ingestion_pdf_ocr.py -q` |
| Settings + langs parsing | unit | OCR-07 + malformed-langs edge | same file / `test_config.py` pattern | same |
| Dockerfile bake | unit (text) | OCR-06: `with_easyocr=True` on the executed `download_models` line | `backend/tests/test_compose_topology.py` | `uv run pytest tests/test_compose_topology.py -q` |
| `detect_language` | unit | 1:1 to OCR-09/10/12 + mixed/short edges (en, pt, mixed, tiny fixtures) | `backend/tests/test_language_detection.py` | `uv run pytest tests/test_language_detection.py -q` |
| BuildCorpus language wiring | unit + DB-gated integration | OCR-10/11: EPUB untouched; detected pt persists + chunks get `portuguese` search_config | existing corpus test modules | `uv run pytest tests/test_corpus*.py -q` |
| Normalization tables | unit + golden regression | OCR-13..16: PT fixtures; neutral row unchanged; existing goldens byte-identical | `backend/tests/test_normalization*.py`, `test_golden_*.py` | `uv run pytest tests/test_normalization*.py tests/test_golden_fixtures.py -q` |
| Live OCR end-to-end | live (importorskip docling) | OCR-17: scanned ingests; blank fails | `backend/tests/test_ingestion_docling_live.py` | in-image (Phase D) |
| ADR | none | build gate only | — | — |

## Parallelism Assessment

| Test Type | Parallel-Safe? | Evidence |
|---|---|---|
| all backend pytest | No — single process | CI runs `uv run pytest -q` |

## Gate Check Commands

(cwd `backend/`; uv `/home/augusto/myenv/bin/uv`; docker CLI `docker.exe`)

| Gate | When | Command |
|---|---|---|
| Quick | per task | `uv run pytest <touched files> -q` |
| Full | phase boundary | `uv run pytest -q` + `uv run ruff check` (baseline 711 passed / 350 skipped; new tests add to passed) |
| Image (Phase D only) | live proof | `docker.exe build --target pdf-worker` + in-image live suite |

## Execution Plan (4 phases, sequential, one Opus worker each)

Phase A: T1 → T2 → T3   (selective OCR)
Phase B: T4 → T5        (language detection)
Phase C: T6 → T7        (PT normalization)
Phase D: T8 → T9        (live proof + ADR)

## Task Breakdown

### T1: OCR settings
**What**: `pdf_ocr_enabled: bool = True`, `pdf_ocr_langs: str = "en,pt"` in Settings + parsed-langs helper (normalize, fallback on empty) + `.env.example` / `backend/.env.production.example` entries + unit tests (incl. malformed-langs edge).
**Where**: `backend/app/core/config.py`, env examples, tests · **Depends**: none · **Req**: OCR-07 + edge
**Tests**: unit · **Gate**: quick · **Commit**: `feat(ingestion): add settings for selective pdf ocr`

### T2: Parser selective retry
**What**: restructure `_convert(..., do_ocr: bool)` (text guard moves to `parse()`); single OCR retry with `EasyOcrOptions` langs (**verify docling 2.112 API via WebFetch first — never guess**); constructor params wired from settings via the existing factory/worker pattern; CI-safe stubbed-converter tests for OCR-01..05 + docling-error edge.
**Where**: `backend/app/infrastructure/ingestion/docling_pdf.py`, `factory.py`, `app/worker/tasks.py` (wiring only), new `backend/tests/test_ingestion_pdf_ocr.py` · **Depends**: T1 · **Req**: OCR-01..05, OCR-08
**Tests**: unit · **Gate**: quick · **Commit**: `feat(ingestion): retry textless pdfs with ocr before failing`

### T3: Bake OCR models
**What**: `with_easyocr=True` in the Dockerfile `download_models` line + `test_compose_topology.py` assert on the executed line (L-010 style).
**Where**: `backend/Dockerfile`, `backend/tests/test_compose_topology.py` · **Depends**: T2 · **Req**: OCR-06
**Tests**: unit (text) · **Gate**: full (phase end) · **Commit**: `build(ingestion): bake the ocr models into the pdf worker image`

### T4: detect_language
**What**: pure `app/application/language.py` with EN/PT stopword tables, min-sample + confidence-ratio gating; unit tests (en, pt, mixed→None, short→None).
**Where**: new module + `backend/tests/test_language_detection.py` · **Depends**: none (within phase B) · **Req**: OCR-09, OCR-12 + edges
**Tests**: unit · **Gate**: quick · **Commit**: `feat(corpus): detect document language from text`

### T5: Wire detection into corpus build
**What**: `BuildCorpus` fills `language` via bounded sample when None (never overrides EPUB OPF); unit tests + DB-gated integration asserting persisted `language='pt'` and chunk `search_config='portuguese'`.
**Where**: `backend/app/application/corpus.py`, corpus tests · **Depends**: T4 · **Req**: OCR-10, OCR-11
**Tests**: unit + integration · **Gate**: full (phase end) · **Commit**: `feat(corpus): apply detected language to pdf corpora`

### T6: Heuristics table
**What**: `LanguageHeuristics` dataclass + `_HEURISTICS` (neutral row == today's constants; en; pt rows) consulted by the passes; refactor is behavior-preserving for neutral/None (existing normalization tests + goldens must pass unmodified).
**Where**: `backend/app/application/normalization.py`, existing tests untouched · **Depends**: none (within phase C) · **Req**: OCR-14, OCR-15
**Tests**: unit + golden regression · **Gate**: quick + goldens · **Commit**: `refactor(corpus): make normalization heuristics a per-language table`

### T7: Portuguese heuristics
**What**: PT row content (Capítulo/Parte/Prefácio/Sumário/Índice/Apêndice keywords, PT generic-title pattern, PT noise markers) + dedicated PT fixtures (flat TOC → inferred hierarchy; PT front-matter) as CI-safe unit tests.
**Where**: `normalization.py`, `backend/tests/test_normalization_pt.py` · **Depends**: T6 · **Req**: OCR-13, OCR-16
**Tests**: unit · **Gate**: full (phase end) · **Commit**: `feat(corpus): normalize portuguese books with localized heuristics`

### T8: Live OCR proof
**What**: live-gated tests — code-generated image-only scanned PDF ingests end-to-end (non-empty sections, valid anchors); blank-image PDF still raises; then attempt the in-image run: build pdf-worker target, execute the live docling suite inside it, record pass/fail + peak memory observation. If the build is prohibitive here, record the gap honestly (no fake results) for T9.
**Where**: `backend/tests/test_ingestion_docling_live.py`, image build (no repo change) · **Depends**: phases A–C merged locally · **Req**: OCR-17
**Tests**: live · **Gate**: full + image attempt · **Commit**: `test(ingestion): prove scanned pdf ocr ingestion end to end`

### T9: ADR-0025
**What**: record selective-OCR policy, engine, detection, heuristics table, C-before-B reorder, 4g-fit evidence or gap.
**Where**: `docs/adr/0025-*.md` · **Depends**: T8 · **Req**: OCR-18
**Tests**: none · **Gate**: build (full + ruff) · **Commit**: `docs(adr): record the selective ocr and localization decision`

## Diagram-Definition Cross-Check

| Task | Depends (body) | Diagram | Status |
|---|---|---|---|
| T1 none · T2 T1 · T3 T2 | A: T1→T2→T3 | ✅ |
| T4 none · T5 T4 | B: T4→T5 | ✅ |
| T6 none · T7 T6 | C: T6→T7 | ✅ |
| T8 A–C · T9 T8 | D: T8→T9 | ✅ |

## Test Co-location Validation

| Task | Layer | Matrix requires | Task says | Status |
|---|---|---|---|---|
| T1 settings | unit | unit | ✅ |
| T2 parser | unit (stubbed) | unit | ✅ |
| T3 Dockerfile | text | text | ✅ |
| T4 detector | unit | unit | ✅ |
| T5 wiring | unit+integration | unit+integration | ✅ |
| T6 refactor | unit+golden | unit+golden | ✅ |
| T7 PT rows | unit | unit | ✅ |
| T8 live | live | live | ✅ |
| T9 ADR | none | none | ✅ |
