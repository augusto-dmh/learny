# v3-notes-foundation Tasks

## Execution Protocol (MANDATORY)
Implement with the `tlc-spec-driven` skill (Execute flow + Critical Rules). STOP if unavailable.

**Design**: `.specs/features/v3-notes-foundation/design.md` · **Status**: Approved (auto)

## Test Coverage Matrix
> Guidelines: house patterns (survey §10). DB-gated integration via `LEARNY_TEST_DATABASE_URL`; unit tests colocated per layer; vitest 1:1 with components/clients.

| Layer | Type | Expectation | Location | Command |
|---|---|---|---|---|
| Migration/schema | integration (DB-gated) | tables/constraints/inverse-cascade asserted; source-delete keeps notes | `backend/tests/test_migrations.py` ext or `test_repositories_notes.py` | `uv run pytest tests/test_repositories_notes.py -q` |
| AnchorResolver + derive logic | unit | 1:1 to NF-03/05 + edge cases (multi-block, self-link, case) | `backend/tests/test_notes_anchoring.py`, `test_notes_application.py` | quick |
| Use cases (CRUD/capture/reconcile) | unit + DB-gated | every NF-04..08 AC incl. 4 tiers + orphan + source-delete | same + `test_repositories_notes.py` | quick |
| Router | unit (TestClient w/ fakes per house style) | NF-09/10 happy+edge+auth/CSRF/rate/error paths | `backend/tests/test_web_notes.py` | quick |
| Worker wiring | unit | reconcile step ordering after quiz reconcile | `backend/tests/test_worker_tasks.py` ext | quick |
| lib client | vitest | NF-11 per quiz-client.test.ts depth | `frontend/tests/notes-client.test.ts` | `npx vitest run tests/notes-client.test.ts` |
| Screens + capture | vitest | NF-12..14: popover flow, list/detail, badges, backlinks, jump-back hrefs | `frontend/tests/notes-screen.test.tsx`, `note-detail-screen.test.tsx`, `section-reader.test.tsx` ext | vitest |
| Settings/env docs | unit | cap default + override | `backend/tests/test_config.py` ext | quick |

## Parallelism: backend pytest sequential single-process; vitest per its config. Phases sequential (shared files).

## Gate Check Commands
(cwd noted; uv `/home/augusto/myenv/bin/uv`; NEVER pipe gate commands through tail — check bare exit codes)
| Gate | Command |
|---|---|
| Quick | `uv run pytest <touched files> -q` / `npx vitest run <file>` |
| Phase-end | backend: `uv run pytest -q` then `uv run ruff check` · frontend: `npx vitest run` then `npx tsc --noEmit` |
| Cycle-end (Phase D) | both stacks full |

## Execution Plan (4 phases, one Opus worker each, sequential)
Phase A: T1 → T2      (schema + block hash + resolver)
Phase B: T3 → T4 → T5 (domain/application + reconcile + wiring)
Phase C: T6            (web API)
Phase D: T7 → T8 → T9  (frontend client, capture, screens)

## Task Breakdown

### T1: Migration 0010 + metadata + repo skeletons
**What**: `0010_notes_schema.py` per NF-01 + NF-02 (corpus_blocks.content_hash nullable) copying 0008 patterns with the inverse-cascade rule; `metadata.py` tables; DB-gated tests asserting shapes, inverse cascade (delete source → notes/anchors survive), tag uniqueness per user.
**Where**: `backend/migrations/versions/0010_notes_schema.py`, `backend/app/infrastructure/db/metadata.py`, `backend/tests/test_repositories_notes.py` (schema part) · **Req**: NF-01, NF-02(schema)
**Gate**: quick (DB tests skip without env; shapes also text-asserted) · **Commit**: `feat(notes): add the notes and anchors schema`

### T2: Block hashing + AnchorResolver
**What**: BuildCorpus computes `content_hash` per block at build (normalize+sha256, stored via corpus replace path); pure `anchoring.py` resolver per design; unit tests incl. multi-block-selection edge + NULL-hash tolerance.
**Where**: `backend/app/application/{corpus,anchoring}.py`, corpus repo write path, `backend/tests/test_notes_anchoring.py` + corpus test ext · **Req**: NF-02, NF-03
**Gate**: quick + full backend at phase end · **Commit**: `feat(corpus): hash blocks at build for highlight anchoring`

### T3: Entities, ports, repositories
**What**: Note/NoteAnchor/Tag entities + statuses; NoteRepository (+ CorpusRepository `blocks_for_reconcile` addition if needed) Protocols; SqlAlchemy impls; DB-gated repo tests (CRUD, derived-index rewrite, backlinks query, anchors by source).
**Where**: `domain/entities.py`, `domain/ports.py`, `infrastructure/db/repositories.py`, tests · **Req**: NF-04
**Gate**: quick · **Commit**: `feat(notes): add note entities and repositories`

### T4: Use cases (CRUD + capture + derive)
**What**: Create/Update/Delete/Get/List + CaptureHighlight per NF-05/06 with owner scoping, body cap (settings field + env docs + config tests), wikilink/tag derivation, StaleCaptureTarget 409 semantics; unit tests 1:1 to ACs + edges (self-link, case-insensitive resolution, empty body).
**Where**: `application/notes.py`, `application/errors.py`, `core/config.py`, env examples, tests · **Req**: NF-04..06
**Gate**: quick · **Commit**: `feat(notes): create and organize notes with captured highlights`

### T5: ReconcileNoteAnchors + worker wiring
**What**: 4-tier cascade per NF-07 mirroring quiz reconcile structure; wiring at `tasks.py` after quiz reconcile (own txn); source-delete orphaning (NF-08); unit tiers tests + DB-gated end-to-end (ingest→capture→re-ingest→resolved; mutated corpus→orphan) + worker-order test.
**Where**: `application/notes.py`, `worker/tasks.py`, tests · **Req**: NF-07, NF-08
**Gate**: full backend + ruff (phase end) · **Commit**: `feat(notes): reconcile note anchors across re-ingestion`

### T6: Web API
**What**: `web/notes.py` router per NF-09/10, `rate_limit_notes`, error mappings, DI/UoW deps, `main.py` registration; TestClient tests: happy + 401/403-CSRF/404-collapse/409/422/429 per route.
**Where**: `infrastructure/web/{notes,rate_limit,error_handlers,dependencies}.py`, `main.py`, `backend/tests/test_web_notes.py` · **Req**: NF-09, NF-10
**Gate**: full backend + ruff (phase end) · **Commit**: `feat(notes): expose the notes api`

### T7: Frontend client
**What**: `lib/notes.ts` per quiz.ts conventions incl. capture call + typed errors; vitest at quiz-client depth.
**Where**: `frontend/app/lib/notes.ts`, `frontend/tests/notes-client.test.ts` · **Req**: NF-11
**Gate**: quick vitest · **Commit**: `feat(notes): add the browser notes client`

### T8: Reader capture
**What**: selection popover in section-reader (getSelection over prose container; quote+32-char context+offsets computed against served markdown string; "Highlight"/"Highlight + note" actions; success toast/link); component tests with mocked selection.
**Where**: `frontend/app/components/section-reader.tsx` (+ small capture popover component), tests ext · **Req**: NF-12
**Gate**: quick vitest · **Commit**: `feat(notes): capture highlights from the reader`

### T9: Notes screens + shell
**What**: notes list + detail screens per NF-13/14 (textarea + MessageResponse preview toggle, tags chips, backlinks panel, anchors with jump-back + orphan badges), routes under `(app)/notes`, sidebar entry; screen tests per house conventions.
**Where**: `frontend/app/(app)/notes/**`, `components/notes/*`, `components/shell/app-sidebar.tsx`, tests · **Req**: NF-13, NF-14
**Gate**: full frontend (vitest + tsc) + full backend re-run (cycle end) · **Commit**: `feat(notes): add the notes screens`

## Cross-checks
Diagram↔deps: T1→T2 (A), T3→T4→T5 (B), T6 (C), T7→T8→T9 (D) — matches bodies ✅. Test co-location: every code task carries its layer's required tests per the matrix; no deferrals ✅ (T1 schema tests DB-gated by design, house style).
