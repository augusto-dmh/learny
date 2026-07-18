# v3-ocr Specification (RFC-003 Cycle C, run before Cycle B per AD-103)

## Problem Statement

Scanned (image-only) PDFs terminally fail ingestion today: `do_ocr=False` plus the empty-text guard raise `InvalidDocumentError` for any PDF without a text layer. Separately, `normalize_book` is locale-blind — its heading/noise heuristics are English-centric module constants — even though the author's library is largely Portuguese and the FTS layer already understands `pt`. PDFs additionally never carry a language (`DoclingPdfParser` sets `language=None`), so they get the `simple` FTS config and would miss any localized normalization.

## Goals

- [ ] A scanned PDF ingests successfully via selective OCR (born-digital PDFs keep the current fast path; a PDF with no text after OCR still fails cleanly).
- [ ] PDFs get a detected language (en/pt initially) feeding both the language-aware FTS config and normalization.
- [ ] `normalize_book` heuristics become table-driven per language with a Portuguese entry; behavior for existing English/neutral inputs is unchanged.
- [ ] The decision set is recorded as ADR-0025.

## Out of Scope

| Feature | Reason |
|---|---|
| Per-upload OCR flag (schema/API/frontend change) | Auto-detection needs no user knowledge of the source; sources table stays untouched (D-1) |
| OCR engines beyond the chosen one; OCR quality tuning | One engine, default models; quality tuning is open-ended (RFC bound) |
| Languages beyond en/pt in detection + heuristics tables | Tables are additive by design; author's corpus is pt/en |
| Committed binary PDF fixtures | House convention: fixtures generated in code |
| Re-ingestion/backfill of existing PDF corpora | Operator can re-upload; no migration of stored corpus rows |
| worker-pdf resource re-sizing | Keep conc=1/mem 4g; only verify OCR fits (assumption below) |

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
|---|---|---|---|
| OCR trigger | Automatic retry: fast path `do_ocr=False`; on no-extractable-text, retry once with OCR; still empty → terminal error (D-1) | context.md | auto (ship-cycle) |
| OCR engine | EasyOCR via Docling (torch already in the image), models baked at build, langs from `LEARNY_PDF_OCR_LANGS` default `en,pt` (D-2) | context.md | auto (ship-cycle) |
| OCR kill-switch | `LEARNY_PDF_OCR_ENABLED` default true; disabled → current behavior exactly | context.md | auto (ship-cycle) |
| PDF language | Pure stopword-ratio detector (en/pt tables), fills `ParsedBook.language` only when confident, else None (D-3) | context.md | auto (ship-cycle) |
| Localization mechanism | `normalize_book` reads `book.language` (no signature change); per-language heuristics table with neutral fallback (D-4) | context.md | auto (ship-cycle) |
| Scanned "golden" | Live-gated (docling importorskip) synthetic scanned-PDF end-to-end test + CI-safe stubbed-converter unit tests; `GOLDEN_FIXTURES` itself unchanged (D-5) | context.md | auto (ship-cycle) |
| OCR fits worker limits | EasyOCR at concurrency 1 stays within `mem_limit: 4g` | Verified in the live test environment during the cycle; flagged in ADR if tight | auto |

**Open questions:** none — all resolved or logged above.

## User Stories

### P1: Scanned PDFs ingest ⭐ MVP

1. (OCR-01) WHEN a PDF with a text layer is parsed THEN the parser SHALL use the existing non-OCR pipeline (no OCR attempt) and produce the same `ParsedBook` as today.
2. (OCR-02) WHEN a PDF yields no extractable text on the fast path AND `LEARNY_PDF_OCR_ENABLED` is true THEN the parser SHALL retry the conversion exactly once with OCR enabled (engine per D-2, languages from `LEARNY_PDF_OCR_LANGS`).
3. (OCR-03) WHEN the OCR retry yields extractable text THEN the parser SHALL return the mapped `ParsedBook` (same anchor scheme and DTO mapping as the non-OCR path).
4. (OCR-04) WHEN the OCR retry still yields no extractable text THEN the parser SHALL raise `InvalidDocumentError` naming the file, as today.
5. (OCR-05) WHEN `LEARNY_PDF_OCR_ENABLED` is false THEN behavior SHALL be byte-identical to today: no retry, no-text PDFs raise `InvalidDocumentError`.
6. (OCR-06) WHEN the pdf-worker image is built THEN the OCR models SHALL be baked at build time alongside layout/tableformer (no runtime downloads), asserted in the Dockerfile test.
7. (OCR-07) WHEN settings are inspected THEN `pdf_ocr_enabled: bool = True` and `pdf_ocr_langs` (default `"en,pt"`) SHALL exist with `LEARNY_`-prefixed env names, documented in `.env.example` and `backend/.env.production.example`.
8. (OCR-08) WHEN docling is not installed (CI, plain worker) THEN all OCR-path unit tests SHALL still run via a stubbed conversion seam, and live end-to-end tests SHALL skip, preserving the docling-free CI invariant.

### P1: PDFs get a language

9. (OCR-09) WHEN a parsed book has ≥ a minimum sample of text AND the stopword detector is confident THEN `ParsedBook.language` SHALL be set to the detected primary subtag (`en` or `pt`); WHEN below sample size or ambiguous THEN it SHALL remain None.
10. (OCR-10) WHEN a book already carries a language (EPUB OPF) THEN detection SHALL NOT override it.
11. (OCR-11) WHEN a PDF's detected language is `pt` THEN the persisted corpus document SHALL carry `language='pt'` and its chunks SHALL get the `portuguese` FTS config via the existing trigger (integration-tested through the corpus build path).
12. (OCR-12) WHEN the detector runs THEN it SHALL be pure (no I/O, no settings, table-driven stopword sets) living in the application layer.

### P1: Portuguese-aware normalization

13. (OCR-13) WHEN `normalize_book` runs on a book with `language='pt'` THEN Portuguese heading keywords (e.g. Capítulo, Parte, Prefácio, Sumário, Índice, Apêndice) SHALL drive the flat-hierarchy inference and generic-title recognition tables; WHEN language is None/unknown THEN the current neutral/English behavior SHALL apply unchanged.
14. (OCR-14) WHEN normalization heuristics are consulted THEN they SHALL come from a per-language table (`en`, `pt`, neutral default) so further languages are additive data, not code changes; the module SHALL remain pure (no I/O, no settings).
15. (OCR-15) WHEN the existing golden fixtures (English/neutral EPUBs) are normalized THEN all existing golden expected values SHALL be unchanged (regression guard).
16. (OCR-16) WHEN a Portuguese fixture with a flat TOC and PT front-matter noise is normalized THEN hierarchy/titles SHALL reflect the PT tables (dedicated unit fixtures, CI-safe).

### P1: Proof + record

17. (OCR-17) WHEN the live docling suite runs (pdf extra installed) THEN a synthetic scanned PDF (image-only pages generated in code, no committed binaries) SHALL ingest end-to-end through `DoclingPdfParser` with OCR, producing non-empty sections with valid anchors; the same suite SHALL prove OCR-04 with a blank-image PDF.
18. (OCR-18) WHEN the cycle completes THEN ADR-0025 SHALL record the selective-OCR policy (trigger, engine, languages, kill-switch, baked models), the language-detection approach, the localized-normalization table design, and the Cycle C-before-B reorder context; STATE/ROADMAP updates ride at finalize.

## Edge Cases

- WHEN the OCR retry raises any docling error THEN it SHALL surface as `InvalidDocumentError` (existing wrap), not crash the worker.
- WHEN a PDF has some pages with text and some scanned THEN the fast path already yields text → no OCR retry (accepted: partial coverage; recorded in ADR).
- WHEN `LEARNY_PDF_OCR_LANGS` is malformed (empty items, spaces) THEN parsing SHALL normalize/ignore empties and fall back to the default list if none remain.
- WHEN detector input mixes languages THEN confidence thresholding SHALL yield None rather than a wrong tag (asserted with a mixed fixture).

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
|---|---|---|---|
| OCR-01..08 | P1 scanned PDFs | A | Pending |
| OCR-09..12 | P1 language detection | B | Pending |
| OCR-13..16 | P1 PT normalization | C | Pending |
| OCR-17..18 | P1 proof + record | D | Pending |

**Coverage:** 18 total, mapped to phases A–D.

## Success Criteria

- [ ] Live suite: synthetic scanned PDF ingests end-to-end with OCR; blank PDF still fails cleanly.
- [ ] CI (docling-free) fully green with all new unit tests running.
- [ ] Existing golden expected values byte-identical (no regression for current corpora).
