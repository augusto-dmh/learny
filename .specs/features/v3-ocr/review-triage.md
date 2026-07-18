# PR #29 Review Triage — v3-ocr

Review: 1 inline + 2 PR-level comments, 6 lanes (security/performance/regression/architecture all zero-finding; behavior-preservation claims independently verified against `main`). Comments are deleted after fixes; this file is the surviving record.

| # | Source | Location | Finding | Verdict | Action | Rationale |
|---|---|---|---|---|---|---|
| F1 | inline (test-coverage lane) | `backend/tests/test_ingestion_pdf_ocr.py:146` | The OCR retry's error leg is untested: a docling error raised during the *second* (OCR) conversion has no case — only a fast-pass error is covered — though design.md lists "OCR retry throws docling error" as its own scenario. A regression swallowing the retry error could pass CI. | **Real** | **Fix** | One stubbed case (`results=[_empty_doc(), RuntimeError(...)]`) closes it; asserts the wrap fires and exactly two conversions ran |
| F2 | requirements comment | process | Author ≠ verifier separation unavailable this cycle (author self-verified via the standalone fallback). | Real (process) | **Won't fix** (recorded) | Already flagged in validation.md and the PR body by design; compensations were the 6/6 discrimination sensor, the executed in-image proof, and this independent 6-lane review — which the user explicitly chose as the fresh-eyes gate |
| F3 | requirements comment | `docling_pdf.py` | Docling OCR API names are stub-asserted only in CI (docling absent). | Real (boundary) | **Won't fix** | The API was verified against the pinned v2.112.0 source before implementation AND executed for real in the built image (scanned page ingested); CI-side stubbing is the designed docling-free invariant |
| F4 | requirements comment | OCR-11 chain | The pt→portuguese chunk-config leg is asserted transitively (unit test proves BuildCorpus persists `language='pt'`; the trigger mapping rides the pre-existing DB-gated repository test). | Real (note) | **Won't fix** | The two links are each directly tested; a combined end-to-end DB test would duplicate `test_repositories.py:546` without new discrimination |

**Counts:** 4 findings — 4 real (1 fix, 3 won't-fix with rationale), 0 false.

**Fix plan:** one commit — `test(ingestion): cover a docling error on the ocr retry pass`.
