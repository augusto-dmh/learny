# Ingestion Breadth Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. If the skill cannot be activated, STOP and tell the user.

**Design**: `.specs/features/v2-ingestion-breadth/design.md`
**Status**: Approved (auto, ship-cycle) | In Progress

**Environment notes (from STATE.md):** `uv` lives at `/home/augusto/myenv/bin/uv`; run backend commands from `backend/`. DB-gated tests need `LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test` and the `db` container (`docker.exe compose up -d db minio` — bare `docker` unavailable in this WSL distro). CI runs without docling installed — the full suite must stay green without it.

---

## Test Coverage Matrix

> Guidelines found: `CLAUDE.md` (citations/eval are core, deterministic offline CI), `backend/pyproject.toml` markers (`live`, `eval`), `backend/tests/conftest.py` `requires_db` pattern, `.github/workflows/ci.yml` (backend job = pytest + ruff, no docling).

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| ---------- | ------------------ | -------------------- | ---------------- | ----------- |
| Normalization (pure application logic) | unit | All branches; 1:1 to ING-01..08 + every listed edge case; idempotency property on every fixture | `backend/tests/test_normalization.py` | `uv run pytest tests/test_normalization.py` |
| Docling mapping (pure) | unit | All mapping rules (sections, depths, opening section, blocks, page spans, anchors, no-headings); determinism | `backend/tests/test_ingestion_docling_mapping.py` | `uv run pytest tests/test_ingestion_docling_mapping.py` |
| Docling real conversion | integration (skip w/o docling) | Happy path + corrupt/encrypted/empty terminal errors | `backend/tests/test_ingestion_docling_live.py` (`pytest.importorskip("docling")`) | same file |
| Repositories (replace/get_section/section_texts/expand_anchors) | integration (`requires_db`) | Alias write/readback, alias fallback lookup incl. canonical-wins + duplicate-order regression | `backend/tests/test_db_repositories*.py` pattern | `uv run pytest tests/<file>` |
| Application services (BuildCorpus, reconcile, teaching expansion, validation, enqueue routing) | unit | 1:1 to their ING ACs; fakes per existing repo conventions | `backend/tests/test_application_*.py`, `test_reconcile_quiz.py`, `test_validation.py` | per file |
| Migration 0009 | integration (`requires_db`) | upgrade/downgrade round-trip per existing `test_migrations.py` pattern | `backend/tests/test_migrations.py` | `uv run pytest tests/test_migrations.py` |
| Compose / Dockerfile topology | unit (file assertions) | worker-pdf flags, worker `--queues celery`, prod overlay parity | `backend/tests/test_compose_topology.py` (repo-root YAML parse) | per file |
| Golden fixtures | unit + integration | ING-08 clean-book-unchanged is the sensor; noisy-book expectations hand-authored | existing `test_golden_*.py` | per file |
| Entities / settings / ADR / env examples | none | — build gate only (ruff + import) | — | build gate |

## Parallelism Assessment

| Test Type | Parallel-Safe? | Isolation Model | Evidence |
| --------- | -------------- | --------------- | -------- |
| unit (pure/fakes) | Yes | no shared state | existing suite runs single-process anyway |
| `requires_db` integration | No | shared `learny_test` DB, table cleanup | `backend/tests/conftest.py` shared engine fixture |

All phases run sequentially (one worker per phase); `[P]` used only as order-free information inside a phase.

## Gate Check Commands

| Gate Level | When to Use | Command (from `backend/`) |
| ---------- | ----------- | ------------------------- |
| Quick | after a task touching one module | `/home/augusto/myenv/bin/uv run pytest tests/<affected files> -q` |
| Full | phase boundary + before any push | `/home/augusto/myenv/bin/uv run pytest -q && /home/augusto/myenv/bin/uv run ruff check .` |
| Build | config/docs-only tasks | `/home/augusto/myenv/bin/uv run ruff check .` + full suite at phase boundary |

Expected baseline: **833 passed, 11 skipped** before this cycle; counts only go up. No frontend tasks → frontend gates unchanged (run once in finalize).

---

## Execution Plan

```
Phase A (T1→T2)  domain rename + normalization core        [Opus]
Phase B (T3→T4→T5) migration + persistence + consumers     [Opus]
Phase C (T6→T7)  docling adapter + dispatch                 [Opus]
Phase D (T8→T9)  upload validation + enqueue routing        [Opus]
Phase E (T10)    Dockerfile + compose + env examples        [Opus]
Phase F (T11)    ADR-0022                                   [Haiku]
A → B → C → D → E → F (sequential; B needs A's entities; C needs A's port; D needs C's factory; E needs C/D names; F cites all)
```

## Task Breakdown

### T1: Rename parser port + extend boundary DTOs

**What**: `EpubParserPort`→`DocumentParserPort`, `InvalidEpubError`→`InvalidDocumentError` (all raisers/handlers/tests; no back-compat alias); add `ParsedSection.anchor_aliases: tuple[str, ...] = ()`, `ParsedBlock.page_span: tuple[int,int] | None = None`, `ReconcileSection.anchor_aliases: tuple[str, ...] = ()`.
**Where**: `backend/app/domain/ports.py`, `entities.py`, `infrastructure/ingestion/epub.py`, `infrastructure/worker/steps.py`, `application/corpus.py`, affected tests.
**Depends on**: None. **Requirement**: ING-15 (foundation), ING-21 (DTO), ING-12 (DTO).
**Done when**: rename complete (grep shows no `EpubParserPort`/`InvalidEpubError`); defaults keep all existing behavior; full suite green unchanged counts.
**Tests**: existing suites updated (rename only — no semantic change). **Gate**: Full.
**Commit**: `refactor(ingestion): make the parser port format-agnostic`

### T2: Normalization pass + unit suite

**What**: `app/application/normalization.py` exactly per design §2 (pipeline order, thresholds, `NormalizationResult`/`NormalizationCounts`); comprehensive unit suite constructing `ParsedBook` DTOs directly: title cascade (each cascade rung + generic-pattern family), flat-TOC inference (incl. not-firing when any depth>0 or <2 heading levels), depth clamp, trivial merge (backward, first-section-forward, aliases accumulate/dedup, everything-merges survivor), Gutenberg strip (present/absent/only-START), counts, idempotency property, clean-book passthrough (ING-08).
**Where**: `backend/app/application/normalization.py`, `backend/tests/test_normalization.py`.
**Depends on**: T1. **Requirement**: ING-01..08.
**Done when**: every ING-01..08 AC + spec edge cases has a discriminating test; idempotency asserted per fixture; quick gate green.
**Tests**: unit. **Gate**: Quick + Full at phase boundary.
**Commit**: `feat(corpus): normalize parsed structure before corpus build`

### T3: Migration 0009 + alias persistence

**What**: `anchor_aliases TEXT[] NOT NULL DEFAULT '{}'` on `corpus_sections` (up/down); repository `replace` writes aliases; `get_section` alias fallback with canonical-first ordering (+ duplicate-anchor order regression test); `section_texts` populates `ReconcileSection.anchor_aliases`; new `expand_anchors`.
**Where**: `backend/migrations/versions/0009_*.py`, `backend/app/infrastructure/db/repositories.py`, `app/domain/ports.py` (CorpusRepository additions), DB tests.
**Depends on**: T2. **Requirement**: ING-21 (persistence half), ING-05.
**Done when**: migration round-trips in `test_migrations.py`; alias write/readback + fallback lookup + canonical-wins covered under `requires_db`; full suite green.
**Tests**: integration (`requires_db`). **Gate**: Full.
**Commit**: `feat(corpus): persist section anchor aliases`

### T4: Wire normalization into BuildCorpus + page-span chunking + golden updates

**What**: `BuildCorpus` calls `normalize_book` post-parse; appends `corpus_normalized` counts event; `pack_chunks` gains optional per-block page spans (chunk = min/max roll-up; EPUB → `None`, asserted byte-identical output for span-less input); golden/noisy fixture updates: new noisy EPUB fixture (gutenberg markers + `part0034` titles + caption-anchor trivial sections) with hand-authored expectations; golden clean book expectations unchanged (D-9 policy).
**Where**: `backend/app/application/corpus.py`, `chunking.py`, `backend/tests/fixtures_epub.py`, `test_application_corpus.py`, `test_application_chunking.py`, golden files.
**Depends on**: T3. **Requirement**: ING-01, ING-07, ING-08, ING-12 (chunk half).
**Done when**: noisy fixture end-to-end (parser→normalize→BuildCorpus over fake repo) shows heading-derived titles/nesting/no boilerplate/aliases; `corpus_normalized` event asserted; golden clean tests pass **without** expectation edits; full suite green.
**Tests**: unit + existing golden. **Gate**: Full.
**Commit**: `feat(corpus): run structure normalization during ingestion`

### T5: Alias-aware quiz reconcile + teaching anchor expansion

**What**: `ReconcileQuizItems` resolves alias→canonical before the AD-078 table (alias+excerpt → relocate to canonical, active; scheduling/log untouched — assert); teaching turn service expands target+descendant anchors via `expand_anchors` before `RetrievalPort.search`.
**Where**: `backend/app/application/quiz.py`, teaching turn service module, `test_reconcile_quiz.py`, teaching tests.
**Depends on**: T3. **Requirement**: ING-22, ING-23, ING-16.
**Done when**: alias-relocate, canonical-untouched, scheduling-preserved, and teaching-alias-evidence cases each have a discriminating test; full suite green.
**Tests**: unit (fakes per existing conventions). **Gate**: Full (phase boundary).
**Commit**: `feat(quiz): reconcile items across merged section anchors` (+ separate `feat(teaching): retrieve through anchor aliases` if cleaner — worker's call, both plain-language)

### T6: Docling mapping + PDF anchors (pure half)

**What**: `pdf` optional extra (`docling>=2.112,<3`) + `docling-core` in dev group; `docling_pdf.py` `_to_parsed_book` per design §4 (sections from SectionHeaderItem levels, opening-section synthesis, minimal-HTML blocks, TableItem HTML export, furniture dropped, page spans from prov, AD-086 anchors with slug rules); **verify every docling-core symbol against the installed package before use** (research is a sketch). Mapping unit suite incl. determinism, no-headings single section, repeated-heading uniqueness.
**Where**: `backend/pyproject.toml`, `backend/app/infrastructure/ingestion/docling_pdf.py`, `backend/tests/test_ingestion_docling_mapping.py`.
**Depends on**: T2 (entities/normalization exist). **Requirement**: ING-10, ING-11, ING-12, ING-13.
**Done when**: mapping ACs discriminated in CI-runnable tests (docling-core only); anchors match the AD-086 format regex; quick gate green.
**Tests**: unit. **Gate**: Quick.
**Commit**: `feat(ingestion): map docling documents to the parsed book model`

### T7: Docling conversion + parser dispatch factory

**What**: `_convert` (DocumentStream, `do_ocr=False`, tables on, exception/zero-text → `InvalidDocumentError`), `factory.py` `build_parser(content_type)` (epub/pdf/unknown-terminal; lazy pdf import with terminal-not-retry on missing docling), `tasks.py` `_build_step` wired to the factory; docling-gated tests (`importorskip`): tiny generated PDF happy path, corrupt bytes, encrypted, empty → typed terminal.
**Where**: `backend/app/infrastructure/ingestion/docling_pdf.py`, `factory.py`, `backend/app/worker/tasks.py`, `backend/tests/test_ingestion_docling_live.py`, `test_ingestion_step.py` additions.
**Depends on**: T6. **Requirement**: ING-10, ING-14, ING-15, ING-16.
**Done when**: factory dispatch + terminal classification unit-tested without docling; docling-gated file skips cleanly in a docling-less env (prove: full suite green without docling); full suite green.
**Tests**: unit + gated integration. **Gate**: Full (phase boundary).
**Commit**: `feat(ingestion): parse pdf sources with docling`

### T8: Upload validation format table + settings

**What**: validation per design §6 (format table, extension↔MIME agreement, per-format caps, existing kinds preserved); object key extension from filename; handler read bound `max(caps)+1`; `pdf_max_bytes` setting + `backend/.env.example` + prod env example entries.
**Where**: `backend/app/application/validation.py`, `sources.py`, `app/infrastructure/web/sources.py`, `app/core/config.py`, env examples, `test_validation.py`, `test_web_sources.py`.
**Depends on**: T7 (content types exist as constants). **Requirement**: ING-09, ING-20 (settings half).
**Done when**: pdf accept, mismatch reject (both directions), oversize pdf reject, epub behavior byte-identical — each tested; full suite green.
**Tests**: unit. **Gate**: Full.
**Commit**: `feat(sources): accept pdf uploads`

### T9: Enqueue routing to ingest-pdf

**What**: Celery `IngestionEnqueuer` adapter routes `application/pdf` → `queue="ingest-pdf"` (else default), additive port input per design §6; routing unit tests (both formats, AD-016 commit-then-enqueue untouched).
**Where**: enqueuer adapter + port + `StartIngestion` call site + tests.
**Depends on**: T8. **Requirement**: ING-17.
**Done when**: queue selection asserted per content type; existing enqueue failure-compensation tests still green; full suite green.
**Tests**: unit. **Gate**: Full (phase boundary).
**Commit**: `feat(worker): route pdf ingestion to a dedicated queue`

### T10: PDF worker image + compose topology

**Scope addition (routed from Phase C blocker):** `.github/workflows/ci.yml:70` currently runs `uv sync --locked --all-extras`, which after the new `pdf` extra would install docling (torch, ~GB, model downloads) into CI and run the live tests — contradicting AD-089/CI-parity. Change it to sync dev without the pdf extra (e.g. `uv sync --locked --extra dev`) and assert in the topology test file that the workflow does not use `--all-extras`.

**What**: `backend/Dockerfile` gains a `pdf-worker` target (uv sync `--extra pdf`, bake models via the docling model-downloader — verify helper name against installed docling); compose base `worker-pdf` service (`--queues ingest-pdf --concurrency 1 --max-tasks-per-child 1`, `mem_limit: 4g`, health/env/depends per `worker`); existing `worker` command gains explicit `--queues celery`; prod overlay parity; `test_compose_topology.py` asserting both services' queue flags, concurrency, mem_limit, max-tasks-per-child in base + prod merge.
**Where**: `backend/Dockerfile`, `docker-compose.yml`, `docker-compose.override.yml` (if worker env needed), `docker-compose.prod.yml`, `backend/tests/test_compose_topology.py`.
**Depends on**: T9. **Requirement**: ING-18, ING-19, ING-20.
**Done when**: `docker.exe compose -f docker-compose.yml -f docker-compose.prod.yml config` validates; topology tests green; full suite + ruff green.
**Tests**: unit (file assertions). **Gate**: Full.
**Commit**: `feat(deploy): isolate pdf ingestion in a dedicated worker`

### T11: ADR-0022

**What**: `docs/adr/0022-pdf-ingestion-via-docling-and-corpus-normalization.md` per spec ING-24 and design §8, following 0019–0021 conventions (Status Accepted, Context/Decision/Alternatives/Consequences, research cross-refs). No internal IDs, no AI attribution.
**Where**: `docs/adr/`. **Depends on**: T10. **Requirement**: ING-24.
**Done when**: file exists, covers all five mandated topics, ruff/gates unaffected.
**Tests**: none (matrix: docs). **Gate**: Build.
**Commit**: `docs(adr): record pdf ingestion via docling and corpus normalization`

---

## Task Granularity Check

| Task | Scope | Status |
| ---- | ----- | ------ |
| T1 | one rename + 3 DTO fields | ✅ (mechanical, cohesive) |
| T2 | one module + its suite | ✅ |
| T3 | one migration + one repo's alias surface | ✅ |
| T4 | one integration seam + chunker param + fixtures | ✅ (cohesive: all corpus-build output) |
| T5 | two consumers of one new field | ✅ (may split into 2 commits) |
| T6 | one adapter's pure half | ✅ |
| T7 | adapter IO half + factory + wiring | ✅ (cohesive: dispatch seam) |
| T8 | one validation module + settings | ✅ |
| T9 | one adapter routing rule | ✅ |
| T10 | image + compose topology | ✅ (one deploy seam) |
| T11 | one document | ✅ |

## Diagram-Definition Cross-Check

| Task | Depends On (body) | Diagram | Status |
| ---- | ----------------- | ------- | ------ |
| T1 | None | phase A start | ✅ |
| T2 | T1 | A: T1→T2 | ✅ |
| T3 | T2 | A→B | ✅ |
| T4 | T3 | B: T3→T4 | ✅ |
| T5 | T3 | B: T4→T5 sequenced in-phase (dep is T3) | ✅ |
| T6 | T2 | B→C sequencing (superset of dep) | ✅ |
| T7 | T6 | C: T6→T7 | ✅ |
| T8 | T7 | C→D | ✅ |
| T9 | T8 | D: T8→T9 | ✅ |
| T10 | T9 | D→E | ✅ |
| T11 | T10 | E→F | ✅ |

## Test Co-location Validation

| Task | Layer | Matrix Requires | Task Says | Status |
| ---- | ----- | --------------- | --------- | ------ |
| T1 | entities/port rename | none (existing suites) | existing updated | ✅ |
| T2 | application (normalization) | unit | unit | ✅ |
| T3 | migration + repository | integration | integration | ✅ |
| T4 | application + golden | unit + golden | unit + golden | ✅ |
| T5 | application (quiz/teaching) | unit | unit | ✅ |
| T6 | docling mapping | unit | unit | ✅ |
| T7 | adapter IO + factory | unit + gated integration | same | ✅ |
| T8 | validation/web/settings | unit | unit | ✅ |
| T9 | enqueuer | unit | unit | ✅ |
| T10 | compose/Dockerfile | file-assertion unit | same | ✅ |
| T11 | docs | none | none | ✅ |

## Tools per task

MCP: none available/needed. Skills: workers may consult project-local `celery-workers`, `epub-ingestion`, `pgvector-hybrid-search`, `uv`, `ruff` skills where relevant. No web access needed except T6/T7/T10 verifying installed docling APIs locally (`uv run python -c "import docling..."` in the pdf extra env).
