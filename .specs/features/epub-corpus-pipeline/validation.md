# EPUB Corpus Pipeline Validation

**Date**: 2026-07-11
**Spec**: `.specs/features/epub-corpus-pipeline/spec.md` (CORP-01..14)
**Diff range**: `05df554..a4dacb7` (13 commits, `main..HEAD` on `feat/epub-corpus-pipeline`)
**Verifier**: independent sub-agent (author ≠ verifier), evidence-or-zero, read-only over the real tree (sensor mutations reverted)

**Verdict**: ✅ **PASS** — 14/14 ACs traced to spec-matching assertions; all listed edge cases covered; 0 spec-precision gaps; 6/6 sensor mutants killed; all four gates green.

---

## Spec-Anchored Acceptance Criteria

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| CORP-01 exactly one corpus doc; title/authors/language nullable; schema version 1 | one doc; `schema_version==1`; nulls when OPF absent | `test_application_corpus.py:144` `call["schema_version"] == 1` + `:141-143` title/authors/language; nulls `test_ingestion_epub_parser.py:52-57` `book.title is None / authors == () / language is None`; single-doc `test_repositories.py:664` `pytest.raises(IntegrityError)` on 2nd `corpus_documents` insert | ✅ PASS |
| CORP-02 spine reading order; section_path; anchor | linear-only spine order; root-to-node TOC path; `href[#frag]` | order `test_ingestion_epub_parser.py:75-82`; path `:92-97`; anchor `:107-108` (`"chap1.xhtml"`, `"chap1.xhtml#sec-2"`); ordered read `test_repositories.py:761-764` | ✅ PASS |
| CORP-03 each block: preserved HTML + type + reading-order position; exact fixture sequence | global positions `0..11`; preserved outer HTML; golden equality | `test_ingestion_epub_parser.py:118` `[b.position...] == list(range(12))`, `:119-132` block_type list, `:135` `list_block.html_fragment == "<ul><li>alpha</li><li>beta</li></ul>"`; whole-structure `:66` `== list(fx.EXPECTED_VALID_SECTIONS)` | ✅ PASS |
| CORP-04 Markdown derived from blocks (A-6), all text, not re-parsed from EPUB | markdown = `\n\n`-join of per-block converter output | `test_application_corpus.py:153` `first.markdown == "md:H0\n\nmd:P0"`; A-6 element set `test_ingestion_markup.py:17-79`; never-dropped `:79` `to_markdown("<aside>Footnote text.</aside>") == "Footnote text."` | ✅ PASS |
| CORP-05 no cross-section chunk; carries path/anchor/null page_span/order; non-empty; ≤ max; concat contains all block text | ≤ `LEARNY_CHUNK_MAX_CHARS`; contiguous indices; null page_span | inclusive cap `test_application_chunking.py:41-47`; oversized sentence split `:56-61`; hard slice + no text loss `:64-70` `"".join(...) == "x"*25`; skip empty `:73-82`; anchors/null span `:85-92`; contiguous `:95-99`; per-section (called per section) `application/corpus.py:92` | ✅ PASS |
| CORP-06 invalid EPUB → terminal, redacted summary, source failed, no corpus rows | parser raises `InvalidEpubError`; `last_error == "Ingestion processing failed."`; 0 corpus rows | parse `test_ingestion_epub_parser.py:216-223`; end-to-end `test_worker_tasks.py:409-416` `job.status == FAILED`, `last_error == _REDACTED`, source `failed`, `_read_structure(...) is None`, `corpus_documents count == 0` | ✅ PASS |
| CORP-07 transient storage fault → `RetryableIngestionError` | `ClientError`/`BotoCoreError` → retryable | `test_ingestion_step.py:92-100` `pytest.raises(RetryableIngestionError)`; worker retry path `test_worker_tasks.py:286-300` (retry called, job RUNNING, redacted) | ✅ PASS |
| CORP-08 build failure → no partial corpus; prior corpus intact | rollback: 0 new rows; old corpus readable | unit `test_application_corpus.py:231-232` / `252-253` `replace_calls == [] and events == []`; tx rollback after replace `test_worker_tasks.py:466-474` prior 5-section corpus survives | ✅ PASS |
| CORP-09 re-run success → exactly one corpus (replaced) | one doc, no duplicate sections/blocks | `test_repositories.py:636-648` single doc, old gone, blocks/chunks==0 then New A/B; worker `test_worker_tasks.py:437-439` documents==1, sections==5, blocks==12 | ✅ PASS |
| CORP-10 events include section/block/chunk counts | message `sections=N blocks=M chunks=K` | `test_application_corpus.py:187` `event.message == "sections=2 blocks=2 chunks=1"`; integration `test_worker_tasks.py:392` `"sections=5 blocks=12 chunks=5"` + ordering `:393-398` | ✅ PASS |
| CORP-11 (API) owner → metadata + nested tree; 404 missing/non-owner/no-corpus; 401 unauth | 200 nested tree; 404 all three not-found; 401 | `test_web_corpus.py:118-145` nested values; 401 `:170`; missing 404 `:176`; non-owner 404 `:189`; no-corpus 404 `:201`; unit `test_application_corpus.py:334-366` | ✅ PASS |
| CORP-12 (FE) ready row offers "View structure" → renders metadata + nested tree | control only on `ready`; nested render | `sources-screen.test.tsx:371` one control on ready row, `:377-381` none on up/proc/fail; nested render `:401-416` | ✅ PASS |
| CORP-13 (FE) fetch fail → error; in flight → disabled | alert w/ backend detail; button disabled+Loading… | in-flight `sources-screen.test.tsx:465-475` `loading.disabled == true`, single GET; error `:498-505` alert text + re-enabled | ✅ PASS |
| CORP-14 source delete → corpus cascade (no orphans) | FK cascade removes all corpus rows | `test_repositories.py:713-716` all four tables count 0 after source delete; migration FKs `test_migrations.py:200-249` `ondelete CASCADE` on all four | ✅ PASS |

**Status**: ✅ All 14 ACs covered with spec-matching assertions.

---

## Edge Cases

- [x] No TOC/nav → A-2 fallback, still succeeds — `test_ingestion_epub_parser.py:170-177` (`no_toc_book`, titles `"Introduction"`, `"body"`)
- [x] TOC entry href absent from spine → ignored, no failure — `test_ingestion_epub_parser.py:194-199` (`"missing.xhtml"` not in anchors, 5 sections)
- [x] Spine doc with no TOC entry → own section — `test_ingestion_epub_parser.py:159-167` (`cover.xhtml`)
- [x] Single block > cap → sentence split; sentence-free → hard slice — `test_application_chunking.py:56-70`
- [x] Empty body → zero-block section, still succeeds — parser `test_ingestion_epub_parser.py:205-210`; build persists zero-block section `test_application_corpus.py:163-166`
- [x] OPF lacks title/creator/language → NULL, never a parse failure — `test_ingestion_epub_parser.py:52-57`
- [x] Missing object key (permanent) → terminal redacted (CORP-06 behavior) — step propagates `ObjectNotFound` terminal `test_ingestion_step.py:108-110`; terminal→failed+redacted proven by `test_worker_tasks.py:243-269`
- [x] (CORP-14) DB-level source delete → FK cascade — `test_repositories.py:677-716`

---

## Discrimination Sensor

Lightweight fault-injection (6 mutations, one at a time, scratch state; each reverted with `git checkout --` and tree confirmed clean).

| # | File:line | Mutation | Killed? |
| - | --- | --- | --- |
| a | `infrastructure/ingestion/epub.py:76` | Neutralize non-linear skip (`linear == "no" and False`) → include `notes.xhtml` | ✅ Killed — `test_ingestion_epub_parser.py` 5 failed (non_linear_excluded, spine order, block sequence, golden equality, dangling-TOC) |
| b | `application/chunking.py:50` | Cap check `<=` → `<` (exclusive) | ✅ Killed — `test_application_chunking.py` 3 failed (exactly_max_inclusive, single_block_at_max, contiguous_indices) |
| c | `infrastructure/db/repositories.py` `replace` | Skip DELETE (append instead of replace) | ✅ Killed — `test_repositories.py::test_corpus_replace_twice...` + `test_worker_tasks.py::test_reingestion_success...` failed |
| d | `infrastructure/worker/steps.py:55` | Classify `(ValueError,)` instead of `(ClientError, BotoCoreError)` | ✅ Killed — `test_ingestion_step.py` 2 failed (client_error/botocore_error not retryable) |
| e | `infrastructure/web/sources.py:186` | Nesting pop guard `>=` → `>` | ✅ Killed — `test_web_corpus.py::test_structure_returns_200_with_nested_tree_and_values` failed (roots count wrong) |
| f | `application/corpus.py:123` | Counts message `blocks={total_chunks}` (wrong var) | ✅ Killed — `test_application_corpus.py::...counts_event...` + `test_worker_tasks.py::...builds_corpus_from_valid_epub` failed |

**Sensor depth**: lightweight (6 mutations across parser / chunking / repository / step-classification / web-tree / counts).
**Result**: 6/6 killed — ✅ PASS. No surviving mutants.

---

## Gate Check

| Gate | Command | Result |
| --- | --- | --- |
| Backend tests | `LEARNY_TEST_DATABASE_URL=... uv run pytest -q` | **263 passed**, 1 warning (pre-existing Starlette deprecation), 0 failed, 0 skipped |
| Backend lint | `uv run ruff check .` | All checks passed (exit 0) |
| Frontend tests | `npm test` (vitest run) | **48 passed** (8 files), 0 failed |
| Frontend types | `npx tsc --noEmit` | exit 0 |

`ruff format --check` intentionally not run (accepted pre-existing gap on 10 Cycle-1 files, per task brief and design Risks).

---

## Code Quality

| Principle | Status |
| --- | --- |
| Minimum code / no scope creep | ✅ Changes match design §Components; no features beyond CORP-01..14 |
| Surgical changes / matches patterns | ✅ Ports+adapters, caller-provided `Connection`, ownership-as-404 reuse, event-append reuse |
| Spec-anchored outcome check (asserted values match spec) | ✅ Redacted text exact, counts message exact, cap inclusive, page_span NULL, 404 uniform |
| Per-layer coverage (domain 1:1 ACs; routes happy+edge+error) | ✅ Chunking/parser/markup unit; corpus/step unit; web integration happy+401+3×404 |
| Every test maps to a spec requirement — no unclaimed tests | ✅ Test docstrings cite CORP/A-#/T# |
| Documented guidelines | ✅ ADR-0002/0003/0009 layering respected; ebooklib/bs4 confined to `infrastructure/ingestion/` |

---

## Requirement Traceability Update

| Requirement | Previous | New |
| --- | --- | --- |
| CORP-01..14 | Pending / Implementing | ✅ Verified |

---

## Summary

**Overall**: ✅ Ready.

**What works**: EPUB → canonical corpus (metadata, spine-ordered sections with TOC paths/anchors, preserved HTML blocks, derived Markdown, structure-first chunks); atomic replace with cascade; terminal vs retryable classification with redacted failure summaries; owner-scoped structure endpoint (200 / 401 / 404×3) and the `ready`-gated "View structure" FE control with in-flight disable and error alert.

**Issues found**: none.

**Next steps**: none for this cycle. Distill-lessons step: clean PASS with no surviving mutants, no spec-precision gaps, no failed/uncovered ACs → no lesson recorded (per validate.md §10).
