# Golden Fixtures Specification

Cycle 8 — TDD-001 Phase 9. Deterministic golden-fixture evaluation that
regression-protects the source-grounding path end to end: fixture EPUBs,
versioned expected values, and fixture-driven checks for ingestion output,
retrieval recall, and citation grounding.

## Problem Statement

Phases 5–8 built the grounding path — EPUB → canonical corpus → embeddings →
hybrid retrieval → grounded cited answers/teaching. Each phase is unit- and
integration-tested against hand-built inputs, but nothing exercises the *whole*
path from real EPUB bytes through to grounded citations against a **fixed,
versioned set of expected outputs**. A regression in the parser, chunker,
embedding, or retrieval query could silently degrade grounding quality without
any existing test noticing, because today's tests each assert a single stage's
behaviour on inputs they themselves construct. ADR-016 and TDD Phase 9 require
golden fixtures as the MVP evaluation floor before any metric scoring or
dashboard.

## Goals

- [ ] A versioned golden-fixture set (EPUB bytes + expected values) covers the source-grounding path for ingestion, retrieval, and citations.
- [ ] A deterministic, offline harness runs each fixture through the real pipeline (EPUB → corpus → embed → retrieve → answer) and compares actual output to the golden expectations.
- [ ] Any drift in ingestion output, retrieval recall, or citation grounding fails a regression check with a readable diff.

## Out of Scope

| Feature | Reason |
| --- | --- |
| Persisted `evaluation_fixtures/evaluation_runs/evaluation_results` SQL tables + service/endpoint | ADR-016 defers the evaluation dashboard; no consumer reads persisted runs (AD-025 stateless precedent). The regression protection Phase 9 asks for comes from the checks, not a run store. |
| Ragas / metric scoring / eval dashboard | ADR-016 explicitly sequences these *after* golden fixtures. |
| Real or third-party EPUB binaries in the repo | Licensing/storage (TDD open question #9). Authored synthetic fixtures avoid the question entirely and stay byte-reviewable + deterministic. |
| Frontend surface | Evaluation is a developer/CI regression harness; it has no end-user surface. |
| Teaching-turn end-to-end golden | Teaching reuses the same retrieval + shared grounding guard as Q&A (already the citation seam under test); its extra surface (session persistence) is verified in Cycle 7. Covering the shared seam via the Q&A path is sufficient and non-duplicative. |
| Golden fixtures for PDF/other formats | EPUB-only per ADR-011; other formats are deferred. |

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| Evaluation realization | Versioned deterministic **test harness**, no new schema/service/endpoint | ADR-016 golden-fixtures-before-dashboard; AD-025 no-tables-without-a-consumer | auto (D-1 / AD-036) |
| Fixture EPUB source | Authored synthetic EPUBs — reuse `tests/fixtures_epub.py` builders + one new topically-rich book | Resolves TDD OQ#9 (licensing) by avoiding third-party text; deterministic + reviewable bytes | auto (D-2 / AD-037) |
| Expected-value identity | Stable identity — `anchor`, `section_path`, snippet text; never generated chunk UUIDs | Chunk UUIDs are per-run; anchors/section_path are the stable citation identity (AD-018) | auto (D-3 / AD-038) |
| Ingestion vs retrieval/citation execution | Ingestion golden runs pure (in-memory `FakeCorpusRepository`); retrieval + citation golden run integration against the pgvector test DB, skipping cleanly when `LEARNY_TEST_DATABASE_URL` is unset | Retrieval needs the real hybrid SQL over pgvector; ingestion output is fully observable without a DB. Matches the repo's marker-based unit/integration split | auto (D-3 / AD-038) |
| Slice shape | Backend/test-only — no frontend, no schema, no endpoint | A CI/dev regression harness has no user surface; deliberate flagged departure from AD-010 (precedent AD-023) | auto (D-4 / AD-039) |

**Open questions:** none — all resolved or logged above. TDD open question #9
(fixture EPUB licensing) is resolved by D-2 (authored synthetic fixtures, no
third-party text).

## User Stories

### P1: Ingestion golden checks ⭐ MVP

**User Story**: As a maintainer, I want the real EPUB→corpus pipeline checked
against versioned expected output so a parser/chunker regression fails a test
instead of silently corrupting the corpus.

**Acceptance Criteria**:

1. WHEN each ingestion fixture EPUB is run through the real parser + markup converter + `BuildCorpus` THEN the produced corpus document metadata (title, authors, language) SHALL equal the fixture's golden values (EVAL-01)
2. WHEN a fixture is ingested THEN the ordered sections' `section_path`, `anchor`, and `depth` SHALL equal the golden structure for that fixture (EVAL-02)
3. WHEN a fixture is ingested THEN each section's derived chunks (count, text, `section_path`, `anchor`, `page_span` is None) SHALL equal the golden chunk expectations, expressed by stable identity rather than generated UUIDs (EVAL-03)
4. WHEN a fixture is ingested THEN the persisted section/block/chunk totals SHALL equal the golden counts (EVAL-04)

**Independent Test**: Run each ingestion fixture through the pure harness (no DB); assert metadata, structure, chunks, and counts against `golden_expected`.

### P2: Retrieval recall golden checks ⭐ MVP

**User Story**: As a maintainer, I want fixture queries checked against expected
target sections so a retrieval-query regression that drops the right passage
fails a test.

**Acceptance Criteria**:

1. WHEN a fixture's golden corpus is built + embedded in the test DB and each retrieval case query (whose terms appear only in its target section) is run through the real hybrid retrieval THEN the case's expected target `anchor` SHALL be the top-ranked (rank-1) returned evidence — a both-arm RRF hit outranking every single-arm neighbour (EVAL-05)
2. WHEN the golden corpus is built in source A and a query-matching chunk also exists in a second source B THEN retrieval scoped to A SHALL return no source-B chunk, and every returned `Evidence.source_id` SHALL equal A (source-scoping guards cross-source leakage) (EVAL-06)

**Independent Test**: Build + embed the golden book in the DB; for each `RetrievalCase` assert the expected anchor ∈ top-k anchors; a dedicated scoping test seeds a matching chunk in a second source and asserts it is excluded.

### P3: Citation grounding golden checks ⭐ MVP

**User Story**: As a maintainer, I want fixture questions checked so an answer
that cites outside the allowed source passages, or fails to grant an explicit
not-found, fails a test.

**Acceptance Criteria**:

1. WHEN an answerable citation case is run through the real `AskQuestion` (real retrieval + deterministic extractive adapter + shared grounding guard) THEN `answer_status` SHALL be `answered`, citations SHALL be non-empty, the case's expected target `anchor` SHALL appear among the citations, and every citation's `anchor` SHALL belong to the golden book's section anchors (grounding bound — no citation to a passage outside the source) (EVAL-07)
2. WHEN the golden corpus is present but supplies no evidence for a question (a question whose terms match no chunk against an un-embedded corpus, so hybrid retrieval returns empty) THEN `AskQuestion` SHALL return `answer_status = not_found_in_source` with an empty citation set (the empty-evidence short-circuit; the deterministic extractive adapter cannot itself reject relevant-looking evidence, so grounded not-found is the empty-retrieval outcome) (EVAL-08)

**Independent Test**: Build + embed the golden book; run each `CitationCase` through `AskQuestion` asserting answered + target-cited + citations bounded to source anchors; a dedicated test builds the corpus un-embedded and asks an unmatched question, asserting grounded not-found.

### Cross-cutting

**Acceptance Criteria**:

1. WHEN golden expectations drift from actual pipeline output THEN the corresponding check SHALL fail with a readable assertion, and the golden values SHALL be versioned in-repo alongside the fixtures (EVAL-09)
2. WHEN the harness runs THEN it SHALL be deterministic and offline (no network, provider SDK, S3, or Celery); integration checks SHALL run against the pgvector test DB and skip cleanly when `LEARNY_TEST_DATABASE_URL` is unset, matching the repo convention (EVAL-10)

## Requirements Traceability

| ID | Requirement | Story |
| --- | --- | --- |
| EVAL-01 | Corpus metadata matches golden | P1 |
| EVAL-02 | Section structure (path/anchor/depth) matches golden | P1 |
| EVAL-03 | Derived chunks match golden by stable identity | P1 |
| EVAL-04 | Section/block/chunk totals match golden | P1 |
| EVAL-05 | Expected target anchor within retrieval top-k | P2 |
| EVAL-06 | Source-scoping — no cross-source leakage | P2 |
| EVAL-07 | Answered citations: target cited + bounded to source anchors | P3 |
| EVAL-08 | Empty-evidence question → grounded not-found | P3 |
| EVAL-09 | Versioned golden values; drift fails readably | Cross |
| EVAL-10 | Deterministic, offline; integration skips without test DB | Cross |
