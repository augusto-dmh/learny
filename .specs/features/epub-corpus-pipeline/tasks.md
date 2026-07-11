# EPUB Corpus Pipeline Tasks

## Execution Protocol (MANDATORY — do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and
follow its Execute flow and Critical Rules.** Do not search for skill files by
filesystem path. The skill is the source of truth for the full flow (per-task cycle,
sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user — do not proceed without it.**

---

**Design**: `.specs/features/epub-corpus-pipeline/design.md`
**Status**: Done — 13/13 tasks committed (05df554..a4dacb7); Verifier PASS (validation.md)

---

## Test Coverage Matrix

> Generated from codebase, project guidelines, and spec — confirm before Execute.
> Guidelines found: `CLAUDE.md` (golden-fixture direction, citations-as-core),
> `backend/pyproject.toml` (pytest config), prior-cycle test suites sampled
> (`test_domain_*`, `test_application_*`, `test_web_*`, `test_repositories.py`,
> `test_worker_tasks.py`, `frontend/tests/*`).

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
|---|---|---|---|---|
| Domain entities / ports | none | build gate only (frozen dataclasses, no logic) | — | build gate |
| Application services & pure functions (`chunking`, `corpus`) | unit | All branches; 1:1 to spec ACs; every listed edge case | `backend/tests/test_application_*.py` | `uv run pytest -q` (from `backend/`) |
| Infrastructure adapters (parser, markup converter, step) | unit | 1:1 to the ACs they implement + every fixture edge case + error classification | `backend/tests/test_ingestion_*.py`, `test_worker_tasks.py` | `uv run pytest -q` |
| Repositories / migrations | integration | Key query paths + replace/cascade/unique invariants + error paths (skip w/o `LEARNY_TEST_DATABASE_URL`) | `backend/tests/test_repositories.py`, `test_migrations.py` | `LEARNY_TEST_DATABASE_URL=... uv run pytest -q` |
| Web routes | integration (TestClient) | Every new route: happy + 401 + 404 variants + shape assertions | `backend/tests/test_web_*.py` | `uv run pytest -q` |
| Worker task wiring | unit + integration | Lifecycle paths incl. rollback/replace through the real engine where prior cycle did | `backend/tests/test_worker_tasks.py` | `uv run pytest -q` |
| Frontend lib clients | unit (vitest) | Happy + error paths per exported function | `frontend/tests/*-client.test.ts` | `npm test` (from `frontend/`) |
| Frontend components | unit (vitest + RTL) | Happy + edge + error paths per spec ACs | `frontend/tests/*-screen.test.tsx` | `npm test` |

**Note**: `uv` is at `/home/augusto/myenv/bin/uv` (not on default PATH). Test DB:
`postgresql+psycopg://learny:learny@localhost:5432/learny_test`; `db` container via
`docker.exe compose up -d db` (STATE.md Handoff).

## Parallelism Assessment

> Generated from codebase — confirm before Execute.

| Test Type | Parallel-Safe? | Isolation Model | Evidence |
|---|---|---|---|
| Backend unit (fakes) | Yes | In-memory fakes per test (`tests/fakes.py`) | `test_application_ingestion.py` uses fresh fakes per test |
| Backend integration (DB) | No | Shared `learny_test` database, table cleanup between tests | `tests/conftest.py` shared engine fixture |
| Frontend vitest | Yes | jsdom per file, fetch mocked | `frontend/tests/*` |

pytest runs single-process here (no xdist), so `[P]` flags order tasks, not test runs.

## Gate Check Commands

> Generated from codebase — confirm before Execute.

| Gate Level | When to Use | Command |
|---|---|---|
| Quick | Backend tasks with unit tests only | `cd backend && uv run pytest -q && uv run ruff check .` |
| Full | Tasks with DB integration tests | `cd backend && LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test uv run pytest -q && uv run ruff check .` |
| FE | Frontend tasks | `cd frontend && npm test && npx tsc --noEmit` |
| Build | Phase completion | Full + FE |

Baseline counts before this cycle: backend **183 passed**, frontend **39 passed**.
Every gate asserts ≥ baseline + new tests (no silent deletions).

---

## Execution Plan

### Phase A — Contracts & pure logic
```
T1 ──→ T2
```

### Phase B — Schema & persistence
```
T3 [P with T1] ──→ T4 (needs T1, T3)
```

### Phase C — Parsing adapters
```
T5 [P] ──┐
T1 ──────┼──→ T6
T1 ──────┴──→ T7 [P with T6]
```

### Phase D — Build service & worker integration
```
T2 ──┐
T1 ──┼──→ T8 ──→ T9 (needs T4, T6, T7, T8)
```

### Phase E — Structure read path
```
T4 ──→ T10 ──→ T11
```

### Phase F — Frontend slice
```
T12 ──→ T13
```

---

## Task Breakdown

### T1: Corpus domain entities, ports, and use-case errors ✅ (05df554)

**What**: Add the frozen dataclasses (`ParsedBlock`, `ParsedSection`, `ParsedBook`,
`SectionChunk`, `CorpusSectionRecord`, `StructureSection`, `CorpusStructure`) to
`app/domain/entities.py`; the `EpubParserPort`, `MarkupConverterPort`,
`CorpusRepository` protocols to `app/domain/ports.py`; `InvalidEpubError` and
`CorpusNotFound` to `app/application/errors.py`. Exactly per design §Components.
**Where**: `backend/app/domain/entities.py`, `backend/app/domain/ports.py`, `backend/app/application/errors.py`
**Depends on**: None
**Reuses**: existing entity/port/docstring conventions in those files
**Requirement**: CORP-01..05, 11 (contracts)

**Tools**: Skill: `epub-ingestion` (DTO/port shapes)

**Done when**:
- [ ] All entities/ports/errors defined as in design, `@runtime_checkable`, ADR-citing docstrings
- [ ] Gate check passes: quick
- [ ] Test count: ≥183 backend tests pass

**Tests**: none (entities/ports — build gate only, per matrix)
**Gate**: quick
**Commit**: `feat(corpus): add canonical corpus domain model and ports`

---

### T2: Structure-first chunk packing function ✅ (eb248db)

**What**: `pack_chunks(block_texts, *, max_chars, section_path, anchor) -> tuple[SectionChunk, ...]`
— pack whole blocks to ≤ `max_chars` joined by `\n\n`; oversized block → sentence-boundary
split (hard char fallback so the cap is absolute); skip empty; contiguous indices;
`page_span=None`. Plus `chunk_max_chars: int = 2000` on `Settings`.
**Where**: `backend/app/application/chunking.py` (new), `backend/app/core/config.py`
**Depends on**: T1
**Reuses**: `Settings` conventions
**Requirement**: CORP-05

**Tools**: Skill: NONE

**Done when**:
- [ ] Unit tests cover: packing under cap, boundary at exactly max, oversized-block sentence split, sentence-free hard split, empty/whitespace blocks skipped, all-blocks-empty → no chunks, anchor/path/page_span carried, indices contiguous
- [ ] Gate check passes: quick
- [ ] Test count: ≥183 + new chunking tests pass

**Tests**: unit (`backend/tests/test_application_chunking.py`)
**Gate**: quick
**Commit**: `feat(corpus): add structure-first chunk packing`

---

### T3: Corpus tables and migration 0004 [P] ✅ (f9c46ad)

**What**: Add `corpus_documents` (UNIQUE `source_id`), `corpus_sections` (UNIQUE
`(document_id, position)`), `corpus_blocks`, `corpus_chunks` to the shared metadata,
exactly per design §Data Models; generate Alembic migration 0004.
**Where**: `backend/app/infrastructure/db/metadata.py`, `backend/alembic/versions/0004_*.py`
**Depends on**: None
**Reuses**: shared `metadata`/`NAMING_CONVENTION`, migration 0003 as template
**Requirement**: CORP-01..05, 09, 14 (schema)

**Tools**: Skill: `epub-ingestion` (canonical-corpus reference)

**Done when**:
- [ ] Migration upgrades/downgrades cleanly against the test DB (existing `test_migrations.py` pattern extended)
- [ ] Gate check passes: full
- [ ] Test count: ≥183 + migration tests pass

**Tests**: integration (`backend/tests/test_migrations.py`)
**Gate**: full
**Commit**: `feat(corpus): add canonical corpus schema and migration`

---

### T4: SqlAlchemyCorpusRepository + fake ✅ (588f206)

**What**: `SqlAlchemyCorpusRepository(conn)` implementing `replace` (delete document
by `source_id` → cascade → bulk insert aggregate) and `get_structure` (document +
depth/position-ordered flat sections); `FakeCorpusRepository` in `tests/fakes.py`.
**Where**: `backend/app/infrastructure/db/repositories.py`, `backend/tests/fakes.py`
**Depends on**: T1, T3
**Reuses**: `Connection`-per-repository pattern, existing repo test setup
**Requirement**: CORP-09, 11, 14

**Tools**: Skill: NONE

**Done when**:
- [ ] Integration tests cover: replace inserts full aggregate; second replace leaves exactly one corpus (no duplicates); UNIQUE `source_id` enforced; source delete cascades all corpus rows (CORP-14); `get_structure` returns `None` without corpus and ordered sections with one
- [ ] Gate check passes: full
- [ ] Test count: prior + repo tests pass

**Tests**: integration (`backend/tests/test_repositories.py`)
**Gate**: full
**Commit**: `feat(corpus): add corpus repository with atomic replace`

---

### T5: Synthetic EPUB fixtures [P] ✅ (0fb2d01)

**What**: `tests/fixtures_epub.py` building EPUBs as stdlib `zipfile` bytes with
literal OPF/XHTML: `valid_book()` (2-level TOC, multiple spine docs, in-doc `id`
anchors, image, footnote, spine doc absent from TOC, non-linear spine item),
`no_toc_book()`, `broken_spine_book()`, `empty_body_book()`, `not_an_epub()`;
plus its expected-structure constants (titles, section paths, anchors, block sequence).
**Where**: `backend/tests/fixtures_epub.py` (new)
**Depends on**: None
**Reuses**: —
**Requirement**: D-5 (test substrate for CORP-01..06)

**Tools**: Skill: `epub-ingestion` (EPUB package shape)

**Done when**:
- [ ] All five builders return bytes; `valid_book()` zip contains mimetype, container.xml, OPF, nav, spine docs (self-check test)
- [ ] Gate check passes: quick
- [ ] Test count: prior + fixture self-check pass

**Tests**: unit (self-check in `backend/tests/test_fixtures_epub.py`)
**Gate**: quick
**Commit**: `test(corpus): add synthetic EPUB fixtures`

---

### T6: EbooklibEpubParser adapter ✅ (c91563f)

**What**: `EbooklibEpubParser` implementing `EpubParserPort` per design §Components
(OPF metadata; TOC flatten; linear-spine walk; A-1 deepest-preceding section
assignment with A-2 fallbacks; A-4 anchors; block splitting with preserved outer
HTML; every failure wrapped in `InvalidEpubError`). Adds `ebooklib` +
`beautifulsoup4` backend deps via uv.
**Where**: `backend/app/infrastructure/ingestion/epub.py` (new pkg), `backend/pyproject.toml`
**Depends on**: T1, T5
**Reuses**: fixture expectations from T5
**Requirement**: CORP-01, 02, 03, 06 (parse side)

**Tools**: Skill: `epub-ingestion` (parse-epub reference), `uv`

**Done when**:
- [ ] Unit tests assert against T5 expected structures: metadata incl. missing-field NULLs; spine order; section paths & depths; anchors with/without fragments; block sequence + preserved HTML; TOC-fragment section switching; A-2 fallback for un-TOC'd doc; A-3 non-linear exclusion; TOC-href-not-in-spine dropped; empty body → section with zero blocks; `InvalidEpubError` on `not_an_epub`/`broken_spine_book`
- [ ] No ebooklib/bs4 type in any signature outside the module
- [ ] Gate check passes: quick
- [ ] Test count: prior + parser tests pass

**Tests**: unit (`backend/tests/test_ingestion_epub_parser.py`)
**Gate**: quick
**Commit**: `feat(corpus): parse EPUB structure with ebooklib adapter`

---

### T7: Bs4MarkupConverter adapter [P] ✅ (3834474)

**What**: `Bs4MarkupConverter.to_markdown(html)` covering the A-6 element set
(headings, paragraphs, nested lists, blockquote, pre/code, pipe tables, images,
links, em/strong; unknown → `get_text()`, never dropped).
**Where**: `backend/app/infrastructure/ingestion/markup.py`
**Depends on**: T1
**Reuses**: bs4 dep from T6 (add here if T7 runs first)
**Requirement**: CORP-04 (derivation)

**Tools**: Skill: NONE

**Done when**:
- [ ] Unit tests: one per A-6 element type + nesting + unknown-element text preservation + empty input
- [ ] Gate check passes: quick
- [ ] Test count: prior + converter tests pass

**Tests**: unit (`backend/tests/test_ingestion_markup.py`)
**Gate**: quick
**Commit**: `feat(corpus): derive markdown from preserved html fragments`

---

### T8: BuildCorpus application service ✅ (a02efcb)

**What**: `BuildCorpus` per design §Components: storage bytes → parse → per-section
markdown via converter → `pack_chunks` → `corpus.replace(schema_version=1)` →
`corpus_built` event with `sections=N blocks=M chunks=K`. Fakes for parser/converter
added to `tests/fakes.py`.
**Where**: `backend/app/application/corpus.py` (new), `backend/tests/fakes.py`
**Depends on**: T1, T2 (uses T4's fake if present; else defines it)
**Reuses**: `RunIngestion._append_event` pattern, `FakeStorage` if existing
**Requirement**: CORP-01, 04, 05, 08 (orchestration), 10

**Tools**: Skill: NONE

**Done when**:
- [ ] Unit tests: happy path persists aggregate with schema_version 1 and derived markdown joined from converter output; counts event exact; storage/parser exceptions propagate unwrapped; replace receives all sections incl. zero-block ones
- [ ] Gate check passes: quick
- [ ] Test count: prior + service tests pass

**Tests**: unit (`backend/tests/test_application_corpus.py`)
**Gate**: quick
**Commit**: `feat(corpus): build canonical corpus from parsed epub`

---

### T9: EpubCorpusIngestionStep + worker wiring ✅ (9886580)

**What**: `EpubCorpusIngestionStep` (maps `ClientError`/`BotoCoreError` →
`RetryableIngestionError`; `ObjectNotFound`/`InvalidEpubError` propagate terminal);
`_build_run_ingestion` wires the real step with `BuildCorpus`; step block
`get_engine().connect()` → `get_engine().begin()`. `NoOpIngestionStep` stays exported.
**Where**: `backend/app/infrastructure/worker/steps.py`, `backend/app/worker/tasks.py`
**Depends on**: T4, T6, T7, T8
**Reuses**: existing task lifecycle tests, T5 fixtures
**Requirement**: CORP-06, 07, 08, 09 (end-to-end)

**Tools**: Skill: `celery-workers`, `epub-ingestion`

**Done when**:
- [ ] Step unit tests: transient → `RetryableIngestionError`; `InvalidEpubError`/`ObjectNotFound` propagate
- [ ] Task integration tests (test DB): valid fixture → corpus rows + `ready` + counts event; `not_an_epub` → `failed`, redacted summary, zero corpus rows (CORP-06); mid-build failure → rollback, prior corpus intact (CORP-08); re-run on corpus'd source → exactly one corpus (CORP-09)
- [ ] Existing 183-test suite still green (lifecycle untouched)
- [ ] Gate check passes: full
- [ ] Test count: prior + step/task tests pass

**Tests**: unit + integration (`backend/tests/test_worker_tasks.py`, `test_ingestion_step.py`)
**Gate**: full
**Commit**: `feat(corpus): run epub corpus build inside the ingestion step`

---

### T10: ReadSourceStructure application service ✅ (f6c9bd3)

**What**: `ReadSourceStructure` per design: `_authorized_source` reuse; no corpus →
`CorpusNotFound`; returns `CorpusStructure`.
**Where**: `backend/app/application/corpus.py`
**Depends on**: T4 (fake corpus repo), T1
**Reuses**: `_authorized_source` from `app/application/ingestion.py`
**Requirement**: CORP-11

**Tools**: Skill: NONE

**Done when**:
- [ ] Unit tests: owner happy path; missing source → `SourceNotFound`; non-owner → `SourceNotFound` (collapse); no corpus → `CorpusNotFound`
- [ ] Gate check passes: quick
- [ ] Test count: prior + read tests pass

**Tests**: unit (`backend/tests/test_application_corpus.py`)
**Gate**: quick
**Commit**: `feat(corpus): read source structure for its owner`

---

### T11: Structure web endpoint ✅ (040d48b)

**What**: `GET /api/sources/{source_id}/structure` on the sources router; nested-tree
response schema built from flat depth-ordered sections; `CorpusNotFound` → 404 in
error handlers; composition-root wiring in `dependencies.py`.
**Where**: `backend/app/infrastructure/web/sources.py`, `error_handlers.py`, `dependencies.py`
**Depends on**: T10
**Reuses**: existing route/response/DI patterns in `web/sources.py`, `web/ingestion.py`
**Requirement**: CORP-11

**Tools**: Skill: `fastapi`

**Done when**:
- [ ] Route tests: 200 with correct nested shape (children nesting from depths); 401 unauthenticated; 404 missing / non-owner / no-corpus; GET requires no CSRF
- [ ] Gate check passes: full
- [ ] Test count: prior + web tests pass

**Tests**: integration/TestClient (`backend/tests/test_web_corpus.py`)
**Gate**: full
**Commit**: `feat(corpus): expose book structure endpoint`

---

### T12: Frontend structure client [P] ✅ (db589ee)

**What**: `fetchSourceStructure(id)` + `SourceStructure`/`StructureSection` types in
the sources lib, same-origin via proxy, error extraction like `listSources`.
**Where**: `frontend/app/lib/sources.ts`
**Depends on**: None (contract fixed by design)
**Reuses**: `listSources` fetch/error pattern
**Requirement**: CORP-12

**Tools**: Skill: NONE

**Done when**:
- [ ] Client tests: success parses nested payload; non-OK → thrown message
- [ ] Gate check passes: FE
- [ ] Test count: ≥39 + client tests pass

**Tests**: unit (`frontend/tests/sources-client.test.ts`)
**Gate**: FE
**Commit**: `feat(corpus): add browser client for book structure`

---

### T13: SourcesPanel structure view ✅ (a4dacb7)

**What**: "View structure" toggle on `ready` rows; disabled while in flight;
expandable panel with metadata line + recursive section `<ul>` tree; failure → existing
`error` alert.
**Where**: `frontend/app/components/SourcesPanel.tsx`
**Depends on**: T12
**Reuses**: `startingId` row-control pattern, existing error state
**Requirement**: CORP-12, 13

**Tools**: Skill: NONE

**Done when**:
- [ ] Screen tests: control only on `ready` rows; disabled during fetch; renders nested tree (titles at right depths); fetch failure shows alert and re-enables; toggle collapses
- [ ] Gate check passes: FE
- [ ] Test count: prior + screen tests pass

**Tests**: unit (`frontend/tests/sources-screen.test.tsx`)
**Gate**: FE
**Commit**: `feat(corpus): show book structure on sources screen`

---

## Parallel Execution Map

```
Phase A: T1 ──→ T2
Phase B: T3 [P w/ Phase A] ──→ T4 (after T1, T3)
Phase C: T5 [P] ; then T6 (after T1, T5) ── T7 [P w/ T6] (after T1)
Phase D: T8 (after T1, T2) ──→ T9 (after T4, T6, T7, T8)
Phase E: T10 (after T1, T4) ──→ T11
Phase F: T12 [P w/ backend phases] ──→ T13
```

`[P]` = order-free within constraints; informational, not a sub-agent directive.
Integration-test tasks (T3, T4, T9, T11) share the test DB — run sequentially.

## Task Granularity Check

| Task | Scope | Status |
|---|---|---|
| T1 | 3 files, one concept (contracts) | ✅ Cohesive |
| T2 | 1 function + 1 setting | ✅ Granular |
| T3 | 1 schema change + its migration | ✅ Cohesive |
| T4 | 1 repository + its fake | ✅ Granular |
| T5 | 1 test-fixture module | ✅ Granular |
| T6 | 1 adapter | ✅ Granular |
| T7 | 1 adapter | ✅ Granular |
| T8 | 1 service | ✅ Granular |
| T9 | 1 adapter + 2-line wiring change | ✅ Cohesive |
| T10 | 1 service | ✅ Granular |
| T11 | 1 endpoint + handler mapping | ✅ Cohesive |
| T12 | 1 client function | ✅ Granular |
| T13 | 1 component change | ✅ Granular |

## Diagram-Definition Cross-Check

| Task | Depends On (body) | Diagram Shows | Status |
|---|---|---|---|
| T1 | None | root | ✅ |
| T2 | T1 | T1→T2 | ✅ |
| T3 | None | root [P] | ✅ |
| T4 | T1, T3 | T1,T3→T4 | ✅ |
| T5 | None | root [P] | ✅ |
| T6 | T1, T5 | T1,T5→T6 | ✅ |
| T7 | T1 | T1→T7 [P w/ T6] | ✅ |
| T8 | T1, T2 | T1,T2→T8 | ✅ |
| T9 | T4, T6, T7, T8 | same | ✅ |
| T10 | T1, T4 | T1,T4→T10 | ✅ |
| T11 | T10 | T10→T11 | ✅ |
| T12 | None | root [P] | ✅ |
| T13 | T12 | T12→T13 | ✅ |

## Test Co-location Validation

| Task | Code Layer | Matrix Requires | Task Says | Status |
|---|---|---|---|---|
| T1 | entities/ports | none | none | ✅ |
| T2 | application pure fn | unit | unit | ✅ |
| T3 | schema/migration | integration | integration | ✅ |
| T4 | repository | integration | integration | ✅ |
| T5 | test fixture module | unit (self-check) | unit | ✅ |
| T6 | infra adapter | unit | unit | ✅ |
| T7 | infra adapter | unit | unit | ✅ |
| T8 | application service | unit | unit | ✅ |
| T9 | infra adapter + worker | unit + integration | unit + integration | ✅ |
| T10 | application service | unit | unit | ✅ |
| T11 | web route | integration | integration | ✅ |
| T12 | FE lib | unit | unit | ✅ |
| T13 | FE component | unit | unit | ✅ |
