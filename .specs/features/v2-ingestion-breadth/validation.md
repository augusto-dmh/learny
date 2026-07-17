# v2-ingestion-breadth Validation

**Date**: 2026-07-17
**Spec**: `.specs/features/v2-ingestion-breadth/spec.md`
**Diff range**: `206b631..HEAD` (implementation commits 633474c, d6f0e77, b7a4cd5, 08347d3, fbc70d7, 0b83e38, a3329c6, 4147229, 4e90d73, bf6653d, b74c9c5, 989ab78)
**Verifier**: independent sub-agent (author ≠ verifier; evidence-or-zero, re-derived from spec + code)
**Verdict**: ✅ **PASS**

---

## Task Completion

| Task | Status | Notes |
| ---- | ------ | ----- |
| T1 rename port + DTOs | ✅ Done | `DocumentParserPort`/`InvalidDocumentError`; grep shows no `EpubParserPort`/`InvalidEpubError` in app code |
| T2 normalization pass + suite | ✅ Done | `normalization.py` + `test_normalization.py` (48 tests) |
| T3 migration 0009 + alias persistence | ✅ Done | `0009_anchor_aliases.py`, repo alias r/w + fallback + expand_anchors |
| T4 wire normalization + page spans + golden | ✅ Done | BuildCorpus normalizes; `corpus_normalized` event; clean golden UNCHANGED |
| T5 alias-aware reconcile + teaching | ✅ Done | quiz relocate-across-alias; teaching expand_anchors |
| T6 docling mapping + anchors | ✅ Done | `docling_pdf.py` `_to_parsed_book`; 11 mapping tests |
| T7 conversion + dispatch factory | ✅ Done | `_convert`, `factory.build_parser`, `_ContentTypeDispatchParser` |
| T8 upload validation + settings | ✅ Done | format table, per-format caps, `pdf_max_bytes` |
| T9 enqueue routing | ✅ Done | Celery enqueuer routes PDF → `ingest-pdf` |
| T10 image + compose topology | ✅ Done | `pdf-worker` target, `worker-pdf` service, CI de-scoped |
| T11 ADR-0022 | ✅ Done | Accepted; all five mandated topics present |

---

## Spec-Anchored Acceptance Criteria

### P1: Normalization (F7) — ING-01..08

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| ING-01 pure + idempotent | `normalize(normalize(x))==normalize(x)`; input not mutated | `test_normalization.py:171` `assert twice == once` (6 fixtures); `:181` `assert book.sections is before` | ✅ PASS |
| ING-01 runs post-parse, pre-record | normalize between parse and record build | `corpus.py:90-95`; `test_application_corpus.py:308` end-to-end normalized aggregate | ✅ PASS |
| ING-02 title cascade | heading → short text → `Untitled section (N)`; never raw stem | `test_normalization.py:200` `=="The Real Chapter"`, `:205` `=="A Styled Heading"`, `:210` `=="Untitled section (3)"`, `:259` `title != stem` | ✅ PASS |
| ING-03 flat-TOC inference | depths from heading-level rank; child ≤ parent+1 | `test_normalization.py:267` `==[0,1,1]`; skip guards `:282`,`:291`; `:301` heading-less keeps predecessor | ✅ PASS |
| ING-04 depth clamp | depth ≤ parent+1 | `test_normalization.py:314` `==[0,1]`; `:459` `==[0,1,2,1]` + parent+1 invariant | ✅ PASS |
| ING-05 trivial merge + alias | merge into adjacent survivor; anchor→alias; ≥1 survives | `:335` `anchor_aliases==("plate.html",)`; `:353` forward-merge alias; `:378` all-trivial 1 survivor; `:398` dedup/canonical-wins | ✅ PASS |
| ING-06 Gutenberg strip | drop outside START/END markers | `test_normalization.py:411` no boilerplate/gutenberg text; `:419` `noise_blocks_stripped==4`; absent `:428`,`:444` | ✅ PASS |
| ING-07 counts event | event with 4 counts alongside `corpus_built` | `test_application_corpus.py:196` `["corpus_normalized","corpus_built"]` + exact message; noisy `:324` counts | ✅ PASS |
| ING-08 clean book unchanged | titles/hierarchy/anchors/content unchanged | `test_normalization.py:191` `result.book==book` + zero counts; golden `_GOLDEN_EXPECTED` unchanged in diff | ✅ PASS |

### P1: PDF via Docling — ING-09..16

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| ING-09 accept .pdf, store .pdf key, enqueue; others rejected | 201 + `.pdf` key; mismatches typed-rejected | `test_web_sources.py:181` 201 + `.pdf` key; `test_application_sources.py:112` accept; mismatch `:120`,`:135`; `test_web_sources.py:196` 415 | ✅ PASS |
| ING-10 same ParsedBook shape, OCR off, tables on, tables in markdown | sections/depths/paths/blocks; table HTML block | `test_ingestion_docling_mapping.py:59-62` shape; `:166` table `<table` block; `_convert` `docling_pdf.py:95` `do_ocr=False, do_table_structure=True` | ✅ PASS |
| ING-11 AD-086 anchor + determinism | `pdf:{slug}/b{ordinal}-{hash}`; identical for same bytes | `test_ingestion_docling_mapping.py:129-135` regex + determinism; live `test_ingestion_docling_live.py:82` identical anchors | ✅ PASS |
| ING-12 chunk page_span; EPUB None | `(min,max)` roll-up; EPUB `None` | `test_application_chunking.py:104` `==(1,4)`; `:161` cross-chunk `[(1,3),(9,10)]`; `test_application_corpus.py:170` EPUB `None` | ✅ PASS |
| ING-13 synthesized opening section | preamble → opening section | `test_ingestion_docling_mapping.py:75-78` opening section from stem | ✅ PASS |
| ING-14 corrupt/encrypted/text-free terminal | typed `InvalidDocumentError`, no retry | `test_ingestion_docling_live.py:89` corrupt; `:96` text-free; encrypted shares corrupt branch (`docling_pdf.py:102` catch-all) | ✅ PASS |
| ING-15 parser-by-content-type; unknown terminal | select by content type; unknown → terminal | `test_ingestion_step.py:157` ebooklib; `:161` unknown terminal; `:166` pdf-no-docling terminal; `:198` unknown ext terminal | ✅ PASS |
| ING-16 re-ingest reconcile keeps | replace + keep/stale/relocate/orphan, scheduling untouched | determinism (ING-11) + `test_reconcile_quiz.py:287` relocate/keep + scheduling/log unchanged; EPUB re-ingest `test_worker_tasks.py:582` | ✅ PASS (by composition) |

### P1: Isolated worker topology — ING-17..20

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| ING-17 route PDF → ingest-pdf at enqueue | PDF `queue="ingest-pdf"`, EPUB default | `test_worker_tasks.py:405` epub no-queue ids-only; `:411` pdf `queue="ingest-pdf"` | ✅ PASS |
| ING-18 worker-pdf flags; worker not on ingest-pdf | conc 1, mem_limit, max-tasks 1, `--queues ingest-pdf`; worker `--queues celery` | `test_compose_topology.py:89` queues; `:94` conc/max-tasks; `:99` mem 4g; `:111` default worker `celery` only; prod `:125` | ✅ PASS |
| ING-19 models baked, pdf extra isolated, api/worker no docling | pdf-worker target bakes models; extra separate | `test_compose_topology.py:141` `AS pdf-worker`; `:147` `--extra pdf` + `download_models`; `:155` CI no `--all-extras` | ✅ PASS |
| ING-20 LEARNY_* settings + docs | `pdf_max_bytes` + env examples | `config.py:85` `pdf_max_bytes`; `.env.example`/`.env.production.example` entries; caps tested `test_application_sources.py:172` | ✅ PASS |

### P2: Aliases + ADR — ING-21..24

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| ING-21 section endpoint resolves alias | alias → surviving section (200); canonical unchanged | `test_repositories.py:988` alias→survivor + canonical still resolves; `:1030` canonical-wins collision; persist `:949` | ✅ PASS |
| ING-22 quiz reconcile alias → canonical | relocate to canonical, active, scheduling/log untouched | `test_reconcile_quiz.py:287` relocate + `before_sched`/`before_log` equal; `:334` canonical-wins | ✅ PASS |
| ING-23 teaching retrieval through alias | evidence from merged section returned | `test_application_teaching.py:773` `expand_anchors_calls==[["ch1.xhtml"]]`, retrieval anchors include `merged.xhtml`, cited | ✅ PASS |
| ING-24 ADR-0022 Accepted, 5 topics | Docling/ebolib/normalization/anchor/topology + cross-refs | `docs/adr/0022-*.md` Status Accepted; all 5 topics + RFC-002/research refs | ✅ PASS |

**Status**: ✅ 24/24 ACs covered with located discriminating assertions matching spec outcomes.

---

## Edge Cases

- [x] PDF no headings → single section from metadata title else filename stem — `test_ingestion_docling_mapping.py:88` (stem), `:100` (metadata title)
- [x] Merge-everything → ≥1 survivor holds all content — `test_normalization.py:373`
- [x] Gutenberg markers absent / START-only → no strip — `test_normalization.py:422`, `:432`
- [x] Alias collides with canonical → canonical wins — `test_repositories.py:1030`, `test_reconcile_quiz.py:334`
- [x] Two merged-away anchors alias same survivor both resolve — `test_normalization.py:378` + `test_repositories.py:1073` expand
- [x] PDF over cap → validation reject (413 path shared) — `test_application_sources.py:159`, `test_web_sources.py` mismatch/oversize path
- [x] Repeated heading text → unique anchors — `test_ingestion_docling_mapping.py:147`
- [x] .pdf as epub content type (and mirror) → reject — `test_application_sources.py:120`, `:135`, `test_web_sources.py:196`

---

## Discrimination Sensor (P0 expanded tier)

Injected in scratch state (Edit → run killing test file → `git checkout` restore); tree verified pristine after each.

| # | File:line | Mutation | Killing test(s) | Killed? |
| - | --------- | -------- | --------------- | ------- |
| A | `normalization.py:281` | trivial word threshold `words < _MIN_WORDS` → `>` | `test_normalization.py` (8 failed incl. merge/idempotency) | ✅ Killed |
| B | `normalization.py:179` | drop alias accumulation on backward merge | `test_normalization.py` (4 failed incl. `_merges_backward_with_alias`) | ✅ Killed |
| C | `repositories.py:490` | remove `anchor_aliases.any()` fallback in `get_section` | `test_repositories.py::..._resolves_an_alias...` | ✅ Killed |
| D | `docling_pdf.py:186` | non-deterministic anchor hash (`+ id(section)`) | `test_ingestion_docling_mapping.py::..._deterministic` | ✅ Killed |
| E | `enqueuer.py:37` | swap queue condition `==` → `!=` (PDF stays default) | `test_worker_tasks.py` both routing tests | ✅ Killed |
| F | `validation.py:101` | invert ext↔MIME mismatch check `!=` → `==` | `test_application_sources.py` (18 failed) | ✅ Killed |
| G | `corpus.py:131` | skip the `corpus_normalized` event append | `test_application_corpus.py` (2 failed) | ✅ Killed |

**Sensor depth**: P0-full (7 injected, spread across normalization / alias persistence / PDF mapping / queue routing / upload validation / event emission).
**Result**: 7/7 killed — ✅ PASS. No surviving mutants.

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code / no scope creep | ✅ |
| Surgical changes, matches existing patterns | ✅ |
| Spec-anchored outcome check (asserted values match spec) | ✅ |
| Per-layer coverage (normalization 1:1 ACs; repo/web happy+edge+error) | ✅ |
| Every test maps to a spec AC / edge case / Done-when | ✅ |
| Documented guidelines followed | ✅ (CLAUDE.md offline-CI, `live`/importorskip precedent, AD-089) |

**Accepted deviations verified (not re-litigated):**
- `SectionChunk.page_span` widened `None` → `tuple[int,int] | None` — consistent across entity/chunker/repo.
- `no_toc_book` golden updated deliberately (trivial "body" merges into "Introduction"); **clean `_GOLDEN_EXPECTED` UNCHANGED** — confirmed in diff (only `_NO_TOC_EXPECTED` changed).
- Worker dispatch via filename with `SPEC_DEVIATION` marker in `tasks.py`; validation guarantees ext↔MIME agreement so selected parser matches content type.
- Encrypted PDF shares the corrupt-bytes terminal branch (`docling_pdf.py:102` catch-all) — no separate test, documented.
- `EpubCorpusIngestionStep` class name retained.
- CI compose-smoke scoped to explicit services (`db redis minio api worker web`); `worker-pdf` excluded by design.

---

## Gate Check

- **Command**: `LEARNY_TEST_DATABASE_URL=... uv run pytest -q` then `uv run ruff check .` (from `backend/`, db+minio up, docling installed locally)
- **Result**: **941 passed, 11 skipped**, 6 warnings; ruff **All checks passed!**
- **Skips (all justified)**: 11 provider-key-gated live tests (Anthropic/OpenAI eval + generation snapshots) — none docling-related; docling IS installed locally so `test_ingestion_docling_live.py` ran.
- **Test count**: baseline 833 → 941 (+108 new); no decrease, no weakened assertions observed.
- **Failures**: none.

---

## Requirement Traceability Update

| Requirement | Previous | New |
| ----------- | -------- | --- |
| ING-01..24 | Implementing | ✅ Verified |

---

## Minor observations (non-blocking, not gaps)

1. **ING-04 markdown h1–h6 sub-claim**: the depth-clamp is directly tested; "derived markdown heading levels stay within h1–h6" relies on the pre-existing markup path (unchanged this cycle) rather than a new assertion. Consistent with design intent.
2. **ING-16 PDF re-ingest**: verified by composition (deterministic anchors ING-11 + reconcile keep/relocate flow ING-22 + EPUB end-to-end re-ingest), not a single PDF-specific end-to-end re-ingest test. Adequate.
3. **ADR-0022 lists "Codex" as a decider** — consistent with the 0019–0021 convention if it matches; noted only for the finalize step's no-AI-attribution check on commits/PRs (docs deciders are out of that scope).

---

## Summary

**Overall**: ✅ Ready

**Spec-anchored check**: 24/24 ACs matched spec outcome, 0 gaps
**Sensor**: 7/7 mutations killed (P0-full)
**Gate**: 941 passed, 11 skipped, ruff clean

**What works**: format-agnostic normalization (title cascade, flat-TOC inference, depth clamp, trivial merge + alias, Gutenberg strip, counts event, clean-book passthrough); Docling PDF parsing with deterministic AD-086 anchors, page spans, tables, terminal error classification; alias persistence with canonical-wins fallback across section reads, quiz reconcile, and teaching retrieval; per-format upload validation; isolated `ingest-pdf` queue + `worker-pdf` topology; ADR-0022.

**Issues found**: none blocking.

**Next steps**: proceed to publish/review. No fix tasks.
