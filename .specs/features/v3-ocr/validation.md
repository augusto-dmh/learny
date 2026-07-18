# v3-ocr Validation

**Date**: 2026-07-17
**Spec**: `.specs/features/v3-ocr/spec.md`
**Diff range**: `c5981f5..d388bc7` (10 commits, `main...HEAD` on `feat/v3-ocr`)
**Verifier**: standalone fallback — the orchestrator ran `validate.md` as a fresh-eyes pass itself, per the user's explicit no-sub-agent instruction after a worker died on the account session limit. **Author ≠ verifier separation was NOT available this cycle**; the discrimination sensor and an executed in-image proof compensate but do not fully substitute. Flagged for the PR reviewer's attention.
**Verdict**: ✅ PASS — 18/18 ACs evidenced, 6/6 sensor mutants killed, in-image OCR proof executed for real.

## Gate

Full backend suite **738 passed / 350 skipped / 0 failed**; `ruff check` clean. CI stays docling-free: every new CI-path test runs without docling (faked modules / pure fixtures); the live suite `importorskip`-skips (verified: 1 skipped locally pre-image).

## Spec-Anchored Coverage (evidence-or-zero)

| AC | Evidence (`backend/tests/…`) | Outcome matched |
|---|---|---|
| OCR-01 fast path, no OCR attempt | `test_ingestion_pdf_ocr.py:99` — `fake.calls[0].do_ocr is False`, single call, mapped book | ✅ |
| OCR-02 exactly one retry, enabled+textless only | `test_ingestion_pdf_ocr.py:111` — `[calls.do_ocr] == [False, True]` | ✅ |
| OCR-03 OCR output maps identically | `test_ingestion_pdf_ocr.py:111` — mapped sections/blocks asserted; live parity at `test_ingestion_docling_live.py:171` (pdf: anchors) | ✅ |
| OCR-04 still textless → terminal | `test_ingestion_pdf_ocr.py:127` — `InvalidDocumentError` match `'scan.pdf' has no extractable text`; live blank at `:93` | ✅ |
| OCR-05 kill-switch = byte-identical behavior | `test_ingestion_pdf_ocr.py:136` — single call, pre-OCR error shape; live `:189` | ✅ |
| OCR-06 models baked at build | `test_compose_topology.py::test_pdf_worker_bakes_the_easyocr_models` — `with_easyocr=True` on the executed RUN line | ✅ |
| OCR-07 settings + env docs | `test_config.py::test_pdf_ocr_settings_*` (defaults, override, trim, empty-fallback); `.env.example` + `.env.production.example` entries in diff | ✅ |
| OCR-08 CI-safe without docling | `test_ingestion_pdf_ocr.py` fakes `sys.modules` docling; suite green in the docling-free venv (738 passed run) | ✅ |
| OCR-09 confident detection sets subtag | `test_language_detection.py:22,26` (en/pt); gates at `:30` (short→None) | ✅ |
| OCR-10 never override declared language | `test_application_corpus.py:373` — `language == "en"` despite PT prose | ✅ |
| OCR-11 detected pt persists → portuguese FTS | `test_application_corpus.py:355` (`replace language == "pt"`) chained with pre-existing `test_repositories.py:546` (pt→portuguese trigger, DB-gated) | ✅ |
| OCR-12 pure, table-driven detector | `app/application/language.py` — no I/O/settings imports (inspected); stopword tables data-only | ✅ |
| OCR-13 PT keywords drive inference + titles | `test_normalization_pt.py:50` (depths `[0,0,1,1,0,1]`, rebuilt paths), `:92` (stem title replaced) | ✅ |
| OCR-14 per-language table, additive, pure | `normalization.py` `LanguageHeuristics`/`_HEURISTICS`; boundary guard `test_normalization_pt.py:75,114` (unknown/None language → neutral) | ✅ |
| OCR-15 existing goldens unchanged | T6 committed with zero edits to `test_normalization.py`/`test_golden_*` — 79 passed pre-PT-row, full suite green after | ✅ |
| OCR-16 PT fixtures CI-safe | `test_normalization_pt.py` (6 tests, pure) | ✅ |
| OCR-17 live scanned proof | `test_ingestion_docling_live.py:171,189` + **executed in the built image** (below) | ✅ |
| OCR-18 ADR-0025 | `docs/adr/0025-selective-ocr-and-localized-normalization.md` — records trigger/engine/detection/table/reorder + real proof outcome | ✅ |

Edge cases: docling error never retried (`test_ingestion_pdf_ocr.py:146`); malformed langs (`test_config.py` trim/fallback); mixed/foreign detection → None (`test_language_detection.py:35,40` — the foreign case caught a real gap during authoring and forced the density gate); all-chapters PT book stays flat (`test_normalization_pt.py:60`).

## Discrimination Sensor — 6 injected, 6 killed, 0 survived

| Mutant | Killed by |
|---|---|
| M1 retry ignores the kill-switch (`and self._ocr_enabled` dropped) | `test_ingestion_pdf_ocr.py` FAIL |
| M2 OCR pass loses the EasyOCR language payload | `test_ingestion_pdf_ocr.py` FAIL (payload assert) |
| M3 detection density gate neutralized | `test_language_detection.py` FAIL (foreign case) |
| M4 detection overrides declared language | `test_application_corpus.py` FAIL |
| M5 `parte` dropped from the pt keyword row | `test_normalization_pt.py` FAIL (depth shape) |
| M6 `with_easyocr` flipped off in the Dockerfile | `test_compose_topology.py` FAIL |

All mutations applied via sed in the working tree and reverted with `git checkout --`; final `git status` shows only the sanctioned `.specs` entries.

## Executed In-Image Proof (OCR-17, real environment)

`docker build --target pdf-worker` succeeded after two real packaging fixes the attempt itself surfaced (easyocr is not bundled by our docling → explicit `pdf`-extra dep; opencv chain needs `libgl1`/`libglib2.0-0`/`libxcb1`). Proof script run in the built image under `-m 4g` (the compose limit):

- scanned bitmap-font PDF → ingested via the OCR retry in **47.5 s**, recognized text contains `capitulo`, `pdf:` anchors ✅
- same bytes with `ocr_enabled=False` → terminal in 2.6 s ✅
- blank page with OCR enabled → terminal after the retry (7.7 s) ✅
- no runtime model downloads (weights loaded from the baked cache) ✅; image size ~7.0 GB (pre-existing torch weight + OCR models)

## Notes / accepted deviations

- The `en` heuristics row equals the neutral row by design (the historical constants are the English family) — spec's OCR-13 "en row" satisfied without behavior change, protecting OCR-15.
- `noise_markers`/front-matter fields sketched in design.md were not implemented as separate table fields: front-matter titles live in `part_keywords` (they are top-level ranks), and no PT-specific noise marker exists yet (Gutenberg markers are English on PG's PT books). No spec AC required them; test-necessity rule kept them out.
- The live blank-page test now exercises the OCR retry (comment updated); its pre-OCR meaning is preserved by the kill-switch case.
