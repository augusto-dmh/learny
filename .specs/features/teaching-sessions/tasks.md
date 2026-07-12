# Teaching Sessions Tasks

## Execution Protocol (MANDATORY — do not skip)

Implement these tasks with the `tlc-spec-driven` skill: activate it by name and follow its Execute flow and Critical Rules. If the skill cannot be activated, STOP.

**Design**: `.specs/features/teaching-sessions/design.md`
**Status**: Done — all 15 tasks committed (58fac91..2487efa), Verifier PASS

---

## Test Coverage Matrix

> Guidelines found: `CLAUDE.md` (golden-fixture/eval direction), existing suite conventions in `backend/tests/*` and `frontend/tests/*` (floor). Strong defaults applied on top.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| --- | --- | --- | --- | --- |
| Migration/metadata | integration | Tables/constraints exist post-upgrade (mirror `test_migrations.py`) | `backend/tests/test_migrations.py` | backend full |
| Domain entities/ports/settings | none | build gate only (frozen dataclasses/Protocols) | — | backend build |
| Retrieval adapter (anchors filter) | integration | filtered + unfiltered paths, cross-arm behavior, no cross-source leakage | `backend/tests/test_retrieval.py` | backend full |
| Repositories (session/turn) | integration | round-trip, ordering, citation snapshot, unique-violation translation | `backend/tests/test_repositories.py` or new file | backend full |
| Application services | unit (fakes) | 1:1 to TEACH ACs; every listed edge case | `backend/tests/test_application_teaching.py` | backend quick |
| Grounding helper + QA delegation | unit | helper branches; existing `test_application_qa.py` stays green unchanged | `backend/tests/test_application_qa.py`, `test_answering_local.py` | backend quick |
| Teaching adapter | unit | deterministic output, grounded-by-construction, empty evidence | `backend/tests/test_answering_local.py` | backend quick |
| Web routers | integration (TestClient) | every endpoint: happy + each documented error path (404/409/422/429/502) + auth/CSRF | `backend/tests/test_web_teaching.py` | backend full |
| Frontend client | unit (vitest) | each function: success + error mapping per status | `frontend/tests/teaching-client.test.ts` | frontend |
| Frontend screens | unit (vitest) | flow: pick target → start → send → cited render; resume; not-found; each error state | `frontend/tests/teach-screen.test.tsx`, `sources-screen.test.tsx` | frontend |

## Parallelism Assessment

| Test Type | Parallel-Safe? | Isolation Model | Evidence |
| --- | --- | --- | --- |
| backend unit (fakes) | Yes | in-memory fakes (`tests/fakes.py`) | `test_application_qa.py` |
| backend integration | No | shared `learny_test` DB, table cleanup in fixtures | `tests/conftest.py` |
| frontend vitest | Yes | jsdom per file, mocked fetch | `vitest.config.ts` |

Tasks run sequentially within each phase regardless ([P] = order-free only).

## Gate Check Commands

| Gate Level | When to Use | Command |
| --- | --- | --- |
| Quick | unit-only tasks | `cd backend && /home/augusto/myenv/bin/uv run pytest tests/<file> -q` |
| Full | integration/web tasks | `cd backend && /home/augusto/myenv/bin/uv run pytest -q` |
| Build (backend) | last task of backend phase | full + `/home/augusto/myenv/bin/uv run ruff check .` |
| Frontend | frontend tasks | `cd frontend && npm test` + `npx tsc --noEmit` |

Integration tests need: `docker.exe compose up -d db minio` and
`LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test`
(tests skip if unset — a skipped integration suite does NOT count as a passing full gate for tasks whose tests are integration-level).

---

## Execution Plan

```
Phase A (sequential): A1 → A2 → A3
Phase B (sequential): B1 → B2
Phase C (sequential): C1 → C2 → C3 → C4, C5 [P] (order-free vs C2-C4, after C1)
Phase D (sequential): D1 → D2 → D3
Phase E (sequential): E1 → E2 → E3
```

5 phases → one sub-agent worker per phase (ship-cycle auto-accepted; Verifier runs fresh after E3).

## Task Breakdown

### A1: Teaching schema migration + metadata

**What**: Migration `0006_teaching_schema.py` + `db/metadata.py` tables per design Data Models (3 tables, CASCADE FKs, `chunk_id` no-FK, UNIQUEs, indexes).
**Where**: `backend/migrations/versions/0006_teaching_schema.py`, `backend/app/infrastructure/db/metadata.py`, `backend/tests/test_migrations.py`
**Depends on**: None. **Requirement**: TEACH-01/05/07/20 (schema).
**Done when**: upgrade head creates the 3 tables with constraints (asserted in test_migrations style); downgrade drops them; full gate passes with integration suite actually running.
**Tests**: integration. **Gate**: full.
**Commit**: `feat(teaching): add teaching sessions schema`

### A2: Domain entities, ports, settings

**What**: `TeachingSession`, `TeachingTurn`, `HistoryTurn`, `TeachingSessionSummary` entities; `TeachingSessionRepository`, `TeachingTurnRepository`, `TeachingGenerationPort` ports; `RetrievalPort.search` gains `anchors: Sequence[str] | None = None`; settings `LEARNY_TEACHING_MESSAGE_MAX_CHARS=2000/TEACHING_EVIDENCE_TOP_K=8/TEACHING_HISTORY_TURNS=6`.
**Where**: `backend/app/domain/entities.py`, `backend/app/domain/ports.py`, `backend/app/core/config.py`
**Depends on**: None. **Requirement**: TEACH-01/07/12 (contracts).
**Done when**: contracts match design §Components verbatim; build gate passes (all existing tests + ruff).
**Tests**: none (contracts). **Gate**: build.
**Commit**: `feat(teaching): add teaching domain contracts and settings`

### A3: Anchor-scoped hybrid retrieval

**What**: `SqlAlchemyRetrievalRepository` applies `AND cc.anchor = ANY(:anchors)` in the `scoped` CTE when `anchors` is not None; `RetrieveEvidence` passes `anchors` through.
**Where**: `backend/app/infrastructure/db/retrieval.py`, `backend/app/application/retrieval.py`, `backend/tests/test_retrieval.py`, `backend/tests/test_application_retrieval.py`
**Depends on**: A2. **Requirement**: TEACH-09 (AD-031).
**Done when**: integration tests prove: filtered search returns only in-anchor chunks (both arms), unfiltered behavior unchanged, no cross-source leakage with filter; unit test proves pass-through; full gate passes.
**Tests**: integration + unit. **Gate**: full (backend build — last task of phase).
**Commit**: `feat(retrieval): support anchor-scoped hybrid search`

### B1: Teaching session repository

**What**: `SqlAlchemyTeachingSessionRepository` (`add`, `get_by_id`, `list_for_source` newest-first with `turn_count`).
**Where**: `backend/app/infrastructure/db/repositories.py`, `backend/tests/test_repositories.py`
**Depends on**: A1, A2. **Requirement**: TEACH-01/05/21.
**Done when**: round-trip + ordering + turn_count integration tests pass; full gate.
**Tests**: integration. **Gate**: full.
**Commit**: `feat(teaching): add teaching session repository`

### B2: Teaching turn repository with citation snapshots

**What**: `SqlAlchemyTeachingTurnRepository` (`add` inserts turn + citation rows, translates the `(session_id, turn_index)` unique violation to `TeachingTurnConflict`; `list_for_session` turn_index-asc with citations). Requires the `TeachingTurnConflict` error type (add to `application/errors.py` here).
**Where**: `backend/app/infrastructure/db/repositories.py`, `backend/app/application/errors.py`, `backend/tests/test_repositories.py`
**Depends on**: B1. **Requirement**: TEACH-07/14/17/20.
**Done when**: round-trip with citations (rank order), duplicate-index raises `TeachingTurnConflict`, citations survive corpus-row deletion (snapshot proof) — integration tests; backend build gate (last of phase).
**Tests**: integration. **Gate**: build (backend).
**Commit**: `feat(teaching): add teaching turn repository with citation snapshots`

### C1: Shared grounding helper

**What**: Extract AD-027 guard into `app/application/grounding.py::ground(generated, evidence)`; `AskQuestion._answer` delegates; behavior identical.
**Where**: `backend/app/application/grounding.py`, `backend/app/application/qa.py`, `backend/tests/test_application_qa.py` (unchanged, must stay green)
**Depends on**: None. **Requirement**: TEACH-10 (reuse seam).
**Done when**: helper unit-tested for its branches (found=false / blank / ungrounded / partial-grounding order+dedupe); ALL existing QA tests pass unchanged; quick gate.
**Tests**: unit. **Gate**: quick.
**Commit**: `refactor(qa): extract answer grounding into a shared helper`

### C2: Start/read/list session services + errors

**What**: `TeachingSessionNotFound`, `InvalidTeachingTarget`, `TeachingTargetGone` errors; `StartTeachingSession`, `ReadTeachingSession`, `ListTeachingSessions` per design.
**Where**: `backend/app/application/errors.py`, `backend/app/application/teaching.py`, `backend/tests/test_application_teaching.py`
**Depends on**: A2. **Requirement**: TEACH-01..06, 15, 21.
**Done when**: unit tests (fakes) cover: create happy (snapshot fields), 404-collapse (missing + non-owner), not-ready, unknown anchor, read with ordered turns, list newest-first; quick gate.
**Tests**: unit. **Gate**: quick.
**Commit**: `feat(teaching): add session start, read, and list services`

### C3: PostTeachingTurn service

**What**: The turn orchestration per design §PostTeachingTurn (subtree resolve, bounded history, scoped retrieval, short-circuit, generation, grounding via C1, persist, conflict, content-free log).
**Where**: `backend/app/application/teaching.py`, `backend/tests/test_application_teaching.py`
**Depends on**: C1, C2. **Requirement**: TEACH-07, 09..17, 19, 24.
**Done when**: unit tests (fakes) cover every listed AC incl. edge cases (descendant scoping, history bound > stored turns, target-gone, 502-no-persist, not-found persisted, empty-evidence port-not-invoked, log line content-free); quick gate.
**Tests**: unit. **Gate**: quick.
**Commit**: `feat(teaching): add cited teaching turn service`

### C4: Deterministic teaching adapter [P with C2/C3 after C1]

**What**: Extract shared extractive helper in `answering/local.py`; add `DeterministicTeachingAdapter` (`model="local-extractive"`, implements `TeachingGenerationPort`); `DeterministicAnswerAdapter` behavior unchanged.
**Where**: `backend/app/infrastructure/answering/local.py`, `backend/tests/test_answering_local.py`
**Depends on**: A2, C1. **Requirement**: TEACH-24 (AD-032).
**Done when**: adapter tests (determinism, top-snippet composition, cites exactly selected chunks, empty evidence found=False); existing answer-adapter tests green; backend build gate (last of phase).
**Tests**: unit. **Gate**: build (backend).
**Commit**: `feat(teaching): add deterministic teaching generation adapter`

### D1: Error mappings + teaching rate limit

**What**: error-handler mappings (`TeachingSessionNotFound`→404, `InvalidTeachingTarget`→422, `TeachingTargetGone`→409, `TeachingTurnConflict`→409) + `rate_limit_teaching` (same policy as questions).
**Where**: `backend/app/infrastructure/web/error_handlers.py`, `backend/app/infrastructure/web/rate_limit.py`, `backend/tests/test_web_rate_limit_validation.py`
**Depends on**: C2 (errors exist; `TeachingTurnConflict` from B2). **Requirement**: TEACH-18 + error contract.
**Done when**: mapping unit/integration tests per existing error-handler test style; quick/full per file; gate passes.
**Tests**: unit. **Gate**: quick.
**Commit**: `feat(teaching): map teaching errors and add turn rate limit`

### D2: Sessions endpoints + wiring

**What**: `web/teaching.py` router — `POST /api/teaching-sessions` (201, rate-limited, CSRF/Origin), `GET /api/teaching-sessions/{id}`, `GET /api/sources/{source_id}/teaching-sessions`; Pydantic views; `dependencies.py` providers; `main.py` include.
**Where**: `backend/app/infrastructure/web/teaching.py`, `web/dependencies.py`, `app/main.py`, `backend/tests/test_web_teaching.py`
**Depends on**: B1, B2, C2, D1. **Requirement**: TEACH-01..06, 21, 23.
**Done when**: TestClient tests: create happy (201 + body shape) / 404 / 409 / 422 / 429 / auth-required / CSRF-enforced; get happy + 404; list happy + 404; full gate.
**Tests**: integration (TestClient). **Gate**: full.
**Commit**: `feat(teaching): add teaching session endpoints`

### D3: Turns endpoint

**What**: `POST /api/teaching-sessions/{id}/turns` (201 TurnView with citations, message validator trim/1..max, rate-limited, CSRF) wired to `PostTeachingTurn`.
**Where**: `backend/app/infrastructure/web/teaching.py`, `web/dependencies.py`, `backend/tests/test_web_teaching.py`
**Depends on**: C3, C4, D2. **Requirement**: TEACH-07/08/13/16/18/23/24.
**Done when**: TestClient tests: answered turn (body incl. citations/model/turn_index), not-found turn, 422 bounds, 404, 409 not-ready, 409 target-gone, 502 (port raise → no row persisted), 429, CSRF; backend build gate (last backend phase).
**Tests**: integration. **Gate**: build (backend).
**Commit**: `feat(teaching): add cited teaching turn endpoint`

### E1: Teaching browser client

**What**: `app/lib/teaching.ts` — `startTeachingSession`, `getTeachingSession`, `listTeachingSessions`, `postTeachingTurn` (mirror `questions.ts` error mapping incl. 409/422/429/502 readable messages).
**Where**: `frontend/app/lib/teaching.ts`, `frontend/tests/teaching-client.test.ts`
**Depends on**: D3 (contract fixed). **Requirement**: TEACH-22.
**Done when**: client tests: each function success + per-status error mapping; frontend gate.
**Tests**: unit. **Gate**: frontend.
**Commit**: `feat(teaching): add teaching sessions browser client`

### E2: Teach screen

**What**: `TeachPanel.tsx` (target picker from structure endpoint, previous-sessions resume list, conversation view: messages, citations with section-path breadcrumb + snippet, explicit not-found callout, per-error banners, composer) + `app/sources/[id]/teach/page.tsx`.
**Where**: `frontend/app/components/TeachPanel.tsx`, `frontend/app/sources/[id]/teach/page.tsx`, `frontend/tests/teach-screen.test.tsx`
**Depends on**: E1. **Requirement**: TEACH-22.
**Done when**: screen tests: pick target → start → send → cited response renders; resume renders history via GET; not-found state; 409/422/429/502 states; frontend gate.
**Tests**: unit. **Gate**: frontend.
**Commit**: `feat(teaching): add teach screen with target picker and cited turns`

### E3: Sources list Teach link

**What**: "Teach" link on ready rows in `SourcesPanel.tsx` (next to Ask).
**Where**: `frontend/app/components/SourcesPanel.tsx`, `frontend/tests/sources-screen.test.tsx`
**Depends on**: E2. **Requirement**: TEACH-22.
**Done when**: sources-screen test asserts link for ready rows only; frontend gate + `npx tsc --noEmit` clean (last task).
**Tests**: unit. **Gate**: frontend (build-equivalent: vitest + tsc).
**Commit**: `feat(teaching): link ready sources to the teach screen`

---

## Diagram-Definition Cross-Check

| Task | Depends On (body) | Diagram | Status |
| --- | --- | --- | --- |
| A1 | none | phase start | ✅ |
| A2 | none | after A1 (sequential phase order only) | ✅ |
| A3 | A2 | A2 → A3 | ✅ |
| B1 | A1, A2 | phase B after A | ✅ |
| B2 | B1 | B1 → B2 | ✅ |
| C1 | none | phase C start | ✅ |
| C2 | A2 | after C1 (phase order) | ✅ |
| C3 | C1, C2 | C2 → C3 | ✅ |
| C4 | A2, C1 | [P] after C1 | ✅ (no dep on C2/C3) |
| D1 | C2, B2 | phase D start | ✅ |
| D2 | B1, B2, C2, D1 | D1 → D2 | ✅ |
| D3 | C3, C4, D2 | D2 → D3 | ✅ |
| E1 | D3 | phase E start | ✅ |
| E2 | E1 | E1 → E2 | ✅ |
| E3 | E2 | E2 → E3 | ✅ |

## Test Co-location Validation

| Task | Layer | Matrix Requires | Task Says | Status |
| --- | --- | --- | --- | --- |
| A1 | migration | integration | integration | ✅ |
| A2 | entities/ports/config | none | none (build) | ✅ |
| A3 | retrieval adapter + service | integration + unit | integration + unit | ✅ |
| B1/B2 | repositories | integration | integration | ✅ |
| C1 | app service (refactor) | unit | unit | ✅ |
| C2/C3 | app services | unit | unit | ✅ |
| C4 | adapter | unit | unit | ✅ |
| D1 | web infra | unit | unit | ✅ |
| D2/D3 | web routers | integration | integration | ✅ |
| E1 | frontend client | unit | unit | ✅ |
| E2/E3 | frontend screens | unit | unit | ✅ |
