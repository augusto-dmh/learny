# Golden Fixtures Tasks

## Execution Protocol (MANDATORY — do not skip)

Implement these tasks with the `tlc-spec-driven` skill: activate it by name and follow its Execute flow and Critical Rules. If the skill cannot be activated, STOP.

**Design**: `.specs/features/golden-fixtures/design.md`
**Status**: Done — A1/A2/B1/C1 committed (`eb12808`, `a4f7eaa`, `fe3026b`, `53f4848`) plus two prerequisite isolation fixes (`570e52e`, `0fa6cd3`); Verifier PASS (`validation.md`, 453 passed, 10/10 EVAL, 3/4 mutants killed + 1 characterized non-defect)

---

## Test Coverage Matrix

> Guidelines found: `CLAUDE.md` (golden-fixture/eval direction, ADR-016), existing suite conventions in `backend/tests/*` (floor: `test_retrieval.py`, `test_fixtures_epub.py`, `test_ingestion_epub_parser.py`). Strong defaults applied on top.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| --- | --- | --- | --- | --- |
| Golden fixture data (EPUB bytes + expected values) | unit (self-consistency) | fixtures build + parse; expected internally consistent; case anchors ⊆ fixture anchors | `backend/tests/test_golden_fixtures.py` | backend quick |
| Ingestion golden (pure pipeline) | unit (real parser + fake corpus repo) | metadata/structure/chunks/counts vs golden, per fixture | `backend/tests/test_golden_ingestion.py` | backend quick |
| Retrieval recall golden | integration (pgvector DB) | expected anchors within top-k (positive); disjoint (negative); source-scoping | `backend/tests/test_golden_retrieval.py` | backend full |
| Citation grounding golden | integration (pgvector DB) | answered+bounded citations; unsupported → grounded not-found | `backend/tests/test_golden_citations.py` | backend full |
| Harness (`eval_runner.py`) | none (exercised by the suites above) | build gate only | — | backend build |

## Parallelism Assessment

| Test Type | Parallel-Safe? | Isolation Model | Evidence |
| --- | --- | --- | --- |
| backend unit (pure) | Yes | in-memory fakes, deterministic bytes | `test_fixtures_epub.py` |
| backend integration | No | shared `learny_test` DB, per-test rolled-back `db_conn` | `tests/conftest.py`, `test_retrieval.py` |

Tasks run sequentially within each phase regardless.

## Gate Check Commands

| Gate Level | When to Use | Command |
| --- | --- | --- |
| Quick | pure/unit-only tasks | `cd backend && /home/augusto/myenv/bin/uv run pytest tests/<file> -q` |
| Full | integration tasks | `cd backend && /home/augusto/myenv/bin/uv run pytest -q` |
| Build (backend) | last task of a backend phase | full + `/home/augusto/myenv/bin/uv run ruff check .` |

Integration tests need: `docker.exe compose up -d db minio` and
`LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test`
(tests skip if unset — a skipped integration suite does NOT count as a passing
full gate for tasks whose tests are integration-level; the DB must be up and the
env var set for B1/C1).

---

## Execution Plan

```
Phase A (sequential): A1 → A2
Phase B (sequential): B1
Phase C (sequential): C1
```

3 phases → executed inline (≤3, no per-phase sub-agent offer). Fresh Verifier
runs after C1.

## Task Breakdown

### A1: Golden fixture corpus + expected values + self-consistency

**What**: New topically-rich synthetic EPUB `golden_corpus.py` (built as code, distinct disjoint prose per section, one chunk per section) with `golden_book()` + `EXPECTED_GOLDEN_*`; `golden_expected.py` with `ExpectedCorpus`/`ExpectedCorpusSection`/`RetrievalCase`/`CitationCase`/`GoldenFixture` types, the `GOLDEN_FIXTURES` registry (golden book + reused `fixtures_epub` builders for ingestion structure coverage), and `RETRIEVAL_CASES`/`CITATION_CASES`; self-consistency test.
**Where**: `backend/tests/golden_corpus.py`, `backend/tests/golden_expected.py`, `backend/tests/test_golden_fixtures.py`
**Depends on**: None. **Requirement**: EVAL-09 (versioned golden data + drift guard).
**Done when**: `test_golden_fixtures.py` asserts each fixture builds + parses, expected values are internally consistent (unique anchors, chunk_count == Σ chunk_texts), and every case's anchors ⊆ its fixture's section anchors; quick gate.
**Tests**: unit. **Gate**: quick.
**Commit**: `test(evaluation): add golden fixture corpus and expected values`

### A2: Ingestion golden checks + pure runner

**What**: `eval_runner.py::run_ingestion(epub) -> BuiltCorpus` (real `EbooklibEpubParser` + `Bs4MarkupConverter` + `BuildCorpus` over `FakeStorage`/`FakeCorpusRepository`/fake events, deterministic id counter, `chunk_max_chars` from settings); `test_golden_ingestion.py` parametrized over `GOLDEN_FIXTURES`.
**Where**: `backend/tests/eval_runner.py`, `backend/tests/test_golden_ingestion.py`
**Depends on**: A1. **Requirement**: EVAL-01, EVAL-02, EVAL-03, EVAL-04, EVAL-10 (offline).
**Done when**: for each fixture the pure run asserts metadata (EVAL-01), ordered `(section_path, anchor, depth)` (EVAL-02), per-section chunk texts + `page_span is None` + count keyed by anchor (EVAL-03), and block/chunk totals (EVAL-04); runs with no DB/network; backend build gate (last task of phase A).
**Tests**: unit. **Gate**: build (backend).
**Commit**: `test(evaluation): add ingestion golden checks`

### B1: Retrieval recall golden checks + DB runner

**What**: `eval_runner.py` DB helpers — `build_corpus_in_db(db_conn, source, epub)` (real `SqlAlchemyCorpusRepository`), `embed_source(db_conn, source_id)` (deterministic), `retrieve(db_conn, source_id, query, anchors=None)` (real hybrid `SqlAlchemyRetrievalRepository` + deterministic query embedding, settings-sourced tuning); `test_golden_retrieval.py` (`requires_db`) parametrized over `RETRIEVAL_CASES`.
**Where**: `backend/tests/eval_runner.py`, `backend/tests/test_golden_retrieval.py`
**Depends on**: A1. **Requirement**: EVAL-05, EVAL-06, EVAL-10.
**Done when**: build+embed golden book in the test DB; answerable cases assert expected anchors ⊆ top-k anchors (EVAL-05); non-answerable cases assert disjoint anchors and all evidence source-scoped (EVAL-06); full gate with the integration suite actually running against pgvector.
**Tests**: integration. **Gate**: full.
**Commit**: `test(evaluation): add retrieval recall golden checks`

### C1: Citation grounding golden checks + answer runner

**What**: `eval_runner.py::answer(db_conn, user, source, question) -> QuestionAnswer` (wire `AskQuestion` with real `SqlAlchemySourceRepository` + `AuthorizeOwnership` + `RetrieveEvidence` over the real retrieval repo + `DeterministicAnswerAdapter`, `evidence_top_k` from settings); `test_golden_citations.py` (`requires_db`) parametrized over `CITATION_CASES`.
**Where**: `backend/tests/eval_runner.py`, `backend/tests/test_golden_citations.py`
**Depends on**: B1. **Requirement**: EVAL-07, EVAL-08, EVAL-10.
**Done when**: build+embed golden book; answerable cases assert `answered` + non-empty citations + citation anchors/section_path ⊆ allowed set (EVAL-07); non-answerable case asserts `not_found_in_source` + empty citations (EVAL-08); backend build gate (last backend task — full + ruff).
**Tests**: integration. **Gate**: build (backend).
**Commit**: `test(evaluation): add citation grounding golden checks`

---

## Diagram-Definition Cross-Check

| Task | Depends On (body) | Diagram | Status |
| --- | --- | --- | --- |
| A1 | none | phase A start | ✅ |
| A2 | A1 | A1 → A2 | ✅ |
| B1 | A1 | phase B (needs fixtures + cases) | ✅ |
| C1 | B1 | phase C (reuses DB build/embed/retrieve seam) | ✅ |

## Test Co-location Validation

| Task | Layer | Matrix Requires | Task Says | Status |
| --- | --- | --- | --- | --- |
| A1 | golden data | unit (self-consistency) | unit | ✅ |
| A2 | ingestion golden | unit (pure) | unit | ✅ |
| B1 | retrieval golden | integration | integration | ✅ |
| C1 | citation golden | integration | integration | ✅ |
