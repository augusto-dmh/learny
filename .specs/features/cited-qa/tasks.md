# Cited Q&A Tasks (`cited-qa`)

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name
and follow its Execute flow and Critical Rules.** Do not search for skill files
by filesystem path. The skill is the source of truth for the full flow
(per-task cycle, sub-agent delegation, adequacy review, Verifier,
discrimination sensor).

**If the skill cannot be activated, STOP and tell the user — do not proceed
without it.**

---

**Design**: `.specs/features/cited-qa/design.md`
**Status**: Done — Verifier PASS (22/22 ACs, 6/6 mutants killed; `validation.md`) — Phase A (A1 ddf67a2, A2 915d340, A3 3cb45d7); Phase B (B1 2bcdc2d, B2 b2a95ab; +8 +13 tests) + orchestrator contract fix 7ba63e8 (`model: str` on the port — see context.md Deviations); Phase C (C1 c12390b, C2 a474b7a; +1 +15 tests); Phase D (D1 947f7bf, D2 97285e1; +7 +5 tests). Build gate: backend 351 passed + ruff clean, frontend 60 passed + tsc clean.

---

## Test Coverage Matrix

> Generated from codebase, project guidelines, and spec — confirm before
> Execute. Guidelines found: `CLAUDE.md` (evaluation/citations are core, golden
> fixtures later), `backend/pyproject.toml` (pytest config), existing test
> conventions sampled from `backend/tests/test_application_retrieval.py`,
> `test_web_retrieval.py`, `test_embeddings_local.py`,
> `frontend/tests/sources-client.test.ts`, `sources-screen.test.tsx`.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
|---|---|---|---|---|
| Domain DTOs / port protocol / errors / settings | none | build gate only (no logic) | — | build gate |
| Answer adapter (`infrastructure/answering`) | unit | All branches; determinism, grounding, empty-evidence; every listed edge case | `backend/tests/test_answering_local.py` | `uv run pytest` |
| Application service (`application/qa.py`) | unit (fakes, framework-free) | 1:1 to spec ACs QA-01,03..05,07,08,12..17 at service level; all listed edge cases | `backend/tests/test_application_qa.py` | `uv run pytest` |
| Web router / handlers / rate limit | integration (FastAPI TestClient, overrides) | Every route in scope: happy + every edge + every error path (200 answered / not-found, 401, 403, 404, 409, 422×2, 429, 502) | `backend/tests/test_web_questions.py` (+ `test_web_rate_limit_validation.py`) | `uv run pytest` |
| Frontend client (`lib/questions.ts`) | unit (vitest) | All fetch paths: success, not-found, error-detail mapping, CSRF header, same-origin | `frontend/tests/questions-client.test.ts` | `npm test` |
| Frontend screen (`AskPanel` + page) | unit (vitest + testing-library) | Answered render (citations), not-found render, error render, form-usable-after-error | `frontend/tests/ask-screen.test.tsx` | `npm test` |

## Parallelism Assessment

> Generated from codebase — confirm before Execute.

| Test Type | Parallel-Safe? | Isolation Model | Evidence |
|---|---|---|---|
| Backend unit (fakes) | No (run sequentially) | pytest has no xdist config; single process | `backend/pyproject.toml` has no `-n` addopts |
| Backend web integration | No | Shared app dependency-overrides + module-level rate limiter singleton | `set_rate_limiter` global in `rate_limit.py`; override pattern in `test_web_*` |
| Frontend vitest | Yes (vitest default) but tasks run sequentially anyway | Per-file isolation | `frontend/vitest.config.ts` |

All tasks execute sequentially; `[P]` marks order-freedom only.

## Gate Check Commands

> Generated from codebase — confirm before Execute. (`uv` is at
> `/home/augusto/myenv/bin/uv`; run backend commands from `backend/`,
> frontend from `frontend/`.)

| Gate Level | When to Use | Command |
|---|---|---|
| Quick (backend) | After backend unit-test tasks | `uv run pytest tests/<new test file> && uv run pytest` |
| Full (backend) | After web/integration tasks | `uv run pytest && uv run ruff check .` |
| Quick (frontend) | After frontend tasks | `npm test` |
| Build (cycle close) | After final task | `cd backend && uv run pytest && uv run ruff check . && cd ../frontend && npm test && npx tsc --noEmit` |

Baseline test counts (no silent deletions): backend **314 passed** on `main`;
frontend vitest suites all green on `main`.

---

## Execution Plan

### Phase A — Contracts (sequential)

```
A1 → A2 → A3
```

### Phase B — Adapter & service (sequential)

```
A3 complete, then: B1 → B2
```

### Phase C — Web surface (sequential)

```
B2 complete, then: C1 → C2
```

### Phase D — Frontend slice (sequential)

```
C2 complete, then: D1 → D2
```

---

## Task Breakdown

### A1: Add `GeneratedAnswer` + `QuestionAnswer` domain DTOs

**What**: Two frozen dataclasses in the entities module per design §Data/DTOs.
**Where**: `backend/app/domain/entities.py` (modify)
**Depends on**: None
**Reuses**: `Evidence`, existing frozen-dataclass conventions/docstrings
**Requirement**: QA-05 (Learny-owned result types)

**Tools**: MCP: NONE / Skill: NONE

**Done when**:

- [ ] `GeneratedAnswer(text, cited_chunk_ids: tuple[UUID, ...], model, found)` and `QuestionAnswer(status, text, citations: tuple[Evidence, ...], evidence_count, model)` exist, frozen, docstring'd with the status contract
- [ ] Gate: `uv run pytest && uv run ruff check .` (no behavior change; 314 pass)

**Tests**: none (matrix: DTOs) — **Gate**: full (backend)
**Commit**: `feat(qa): add answer domain result types`

---

### A2: Add `AnswerGenerationPort` protocol

**What**: The generation port protocol with contract docstring (found=False vs raise semantics).
**Where**: `backend/app/domain/ports.py` (modify)
**Depends on**: A1
**Reuses**: `EmbeddingPort`/`RetrievalPort` protocol conventions
**Requirement**: QA-05

**Tools**: MCP: NONE / Skill: NONE

**Done when**:

- [ ] `AnswerGenerationPort.generate(*, question: str, evidence: Sequence[Evidence]) -> GeneratedAnswer` protocol, `@runtime_checkable`, docstring states found/raise contract and no-SDK rule
- [ ] Gate: `uv run pytest && uv run ruff check .` (314 pass)

**Tests**: none — **Gate**: full (backend)
**Commit**: `feat(qa): define answer generation port`

---

### A3: Add QA errors and settings

**What**: `SourceNotReady`, `AnswerGenerationFailed` exceptions; `qa_question_max_chars: int = 2000`, `qa_evidence_top_k: int = 8` settings (comment: server-controlled, keep ≤ `retrieval_max_top_k`).
**Where**: `backend/app/application/errors.py`, `backend/app/core/config.py` (modify)
**Depends on**: None
**Reuses**: existing exception docstring style; `LEARNY_` settings conventions
**Requirement**: QA-08, QA-10, QA-17 (contracts), AD-029

**Tools**: MCP: NONE / Skill: NONE

**Done when**:

- [ ] Both exceptions defined with handler-facing docstrings; both settings present with defaults
- [ ] Gate: `uv run pytest && uv run ruff check .` (314 pass)

**Tests**: none — **Gate**: full (backend)
**Commit**: `feat(qa): add question errors and settings`

---

### B1: Deterministic answer adapter + unit tests

**What**: `DeterministicAnswerAdapter` (model `"local-extractive"`, `_MAX_SNIPPETS = 3`) per design; new package `app/infrastructure/answering/`.
**Where**: `backend/app/infrastructure/answering/__init__.py`, `backend/app/infrastructure/answering/local.py`, `backend/tests/test_answering_local.py`
**Depends on**: A1, A2
**Reuses**: `DeterministicEmbeddingAdapter` module/docstring conventions (`infrastructure/embeddings/local.py`)
**Requirement**: QA-06

**Tools**: MCP: NONE / Skill: NONE

**Done when**:

- [ ] Implements the port; empty evidence → `found=False` empty result; else answer composed from top `min(3, n)` snippets, cited ids exactly those chunks, `found=True`
- [ ] Tests: identical output for identical input (run twice); cited ids ⊆ evidence ids; ≤3 snippets used with 5 evidence items; 1 evidence item works; empty evidence → found=False; no network/SDK import (grep-style assertion or import check)
- [ ] Gate: `uv run pytest tests/test_answering_local.py && uv run pytest` (314 + new pass)

**Tests**: unit — **Gate**: quick (backend)
**Commit**: `feat(qa): add deterministic local answer adapter`

---

### B2: `AskQuestion` application service + unit tests

**What**: The orchestrating service per design §AskQuestion (readiness, retrieve, short-circuit, generate-with-wrap, grounding filter, completion log).
**Where**: `backend/app/application/qa.py` (new), `backend/tests/test_application_qa.py` (new; extend `backend/tests/fakes.py` if needed)
**Depends on**: A1, A2, A3, B1 (port shape proven)
**Reuses**: `authorized_source`, `RetrieveEvidence` (injected), `fakes.py` fake repositories/ports, `test_application_retrieval.py` test style
**Requirement**: QA-01, QA-03, QA-04, QA-05, QA-07, QA-08, QA-12, QA-13..QA-17

**Tools**: MCP: NONE / Skill: NONE

**Done when**:

- [ ] Service implements the design flow exactly (order: authorize → readiness → retrieve → short-circuit → generate → guards → result)
- [ ] Tests map 1:1 to service-level ACs: answered result with grounded, evidence-rank-ordered, deduped citations (QA-01/02/03); result carries evidence_count + model (QA-04); missing/non-owned → `SourceNotFound` (QA-07); not-ready → `SourceNotReady`, retrieval NOT called (QA-08); empty evidence → not-found, port NOT invoked (QA-13); found=False → not-found (QA-14); out-of-evidence citations discarded / all-invalid → not-found (QA-15); blank text + found=True → not-found (QA-16); port raise → `AnswerGenerationFailed` (QA-17); one log record with source_id/outcome/evidence_count/model and no question text (QA-12, caplog); zero-chunk edge (empty evidence path)
- [ ] No FastAPI/SQLAlchemy/SDK import in `app/application/qa.py`
- [ ] Gate: `uv run pytest tests/test_application_qa.py && uv run pytest` (all pass, count grows)

**Tests**: unit — **Gate**: quick (backend)
**Commit**: `feat(qa): add cited question answering service`

---

### C1: Questions rate limit + error mappings

**What**: `rate_limit_questions` dependency; handler entries `SourceNotReady`→409, `AnswerGenerationFailed`→502 (generic body per design).
**Where**: `backend/app/infrastructure/web/rate_limit.py`, `backend/app/infrastructure/web/error_handlers.py` (modify), `backend/tests/test_web_rate_limit_validation.py` (extend)
**Depends on**: A3
**Reuses**: `rate_limit_upload` shape (incl. KNOWN LIMITATION reference), existing handler registration pattern
**Requirement**: QA-22, QA-08, QA-17 (transport mapping)

**Tools**: MCP: NONE / Skill: NONE

**Done when**:

- [ ] Dependency + mappings exist; limiter test extended for the questions key (429 + `Retry-After` after window exceeded, per existing test style)
- [ ] Gate: `uv run pytest && uv run ruff check .`

**Tests**: integration (existing file) — **Gate**: full (backend)
**Commit**: `feat(qa): throttle questions endpoint and map its errors`

---

### C2: Questions router + composition wiring + endpoint tests

**What**: `POST /api/sources/{source_id}/questions` router (request validation, response views reusing `EvidenceView`), `get_answer_generation` (process-wide `DeterministicAnswerAdapter`, test-overridable) + `get_ask_question` in the composition root, router registration in `main.py`.
**Where**: `backend/app/infrastructure/web/questions.py` (new), `backend/app/infrastructure/web/dependencies.py`, `backend/app/main.py` (modify), `backend/tests/test_web_questions.py` (new)
**Depends on**: B2, C1
**Reuses**: `web/retrieval.py` router/validator/view patterns, `get_retrieve_evidence` wiring, `test_web_retrieval.py` client/override fixtures
**Requirement**: QA-01, QA-02, QA-04, QA-09, QA-10, QA-11, QA-13, QA-17, QA-22 (route level)

**Tools**: MCP: NONE / Skill: NONE

**Done when**:

- [ ] Route registered with `enforce_origin`/`enforce_csrf`/`rate_limit_questions`/auth deps; validator strips + bounds question (trimmed value passed on); response shape exactly per design JSON (both outcomes carry `retrieval` + `model`)
- [ ] Tests cover: 200 answered (citation fields QA-02, diagnostics QA-04); 200 not-found (empty citations); 401 unauthenticated; 403 bad CSRF/Origin; 404 missing AND non-owned (identical bodies); 409 not-ready; 422 blank + over-long; exactly-max-chars accepted; 502 on port raise (generic body); 429 pathway
- [ ] Gate: `uv run pytest && uv run ruff check .` (all pass)

**Tests**: integration — **Gate**: full (backend)
**Commit**: `feat(qa): add cited questions endpoint`

---

### D1: Frontend questions client + tests

**What**: `askQuestion(sourceId, question, csrfToken, fetchImpl?)` returning `AnswerView` (mirrors backend response), error mapping via backend `detail`.
**Where**: `frontend/app/lib/questions.ts` (new), `frontend/tests/questions-client.test.ts` (new)
**Depends on**: C2 (contract fixed)
**Reuses**: `lib/sources.ts` patterns (`credentials: "same-origin"`, `X-CSRF-Token`, `toSourceError`-style mapping), `sources-client.test.ts` style
**Requirement**: QA-21, QA-20 (client half)

**Tools**: MCP: NONE / Skill: NONE

**Done when**:

- [ ] Client POSTs through the proxy path with credentials + CSRF header; returns parsed `AnswerView` for answered AND not-found; non-OK → `Error` with backend detail, readable fallback
- [ ] Tests cover: success payload passthrough, not-found passthrough, error-detail mapping (409/429/502), header/credentials assertions
- [ ] Gate: `npm test` (all suites pass)

**Tests**: unit (vitest) — **Gate**: quick (frontend)
**Commit**: `feat(qa): add browser questions client`

---

### D2: AskPanel + ask page + sources-list link + screen tests

**What**: `AskPanel` client component (form → pending → answered/not-found/error states), page `app/sources/[id]/ask/page.tsx`, "Ask" link for ready sources in `SourcesPanel`.
**Where**: `frontend/app/components/AskPanel.tsx`, `frontend/app/sources/[id]/ask/page.tsx` (new), `frontend/app/components/SourcesPanel.tsx` (modify), `frontend/tests/ask-screen.test.tsx` (new)
**Depends on**: D1
**Reuses**: `SourcesPanel.tsx` component/CSRF-on-mount/error-state conventions, `sources-screen.test.tsx` testing-library style
**Requirement**: QA-18, QA-19, QA-20

**Tools**: MCP: NONE / Skill: NONE

**Done when**:

- [ ] Submitting a question renders answer text + each citation's `section_path.join(" › ")` + snippet; `not_found_in_source` renders the explicit message and no citation list; API errors render readable messages; form remains usable after every terminal state; ready-source rows link to the ask view
- [ ] Tests cover: answered render, not-found render, error render + form-usable-after, link presence for ready sources only
- [ ] Gate: `npm test && npx tsc --noEmit`
- [ ] Cycle-close build gate: `cd backend && uv run pytest && uv run ruff check . && cd ../frontend && npm test && npx tsc --noEmit`

**Tests**: unit (vitest + testing-library) — **Gate**: quick (frontend) + build (cycle close)
**Commit**: `feat(qa): add ask panel for cited questions`

---

## Parallel Execution Map

```
Phase A: A1 → A2 → A3      (A3 could run before A1/A2 — kept sequential, same files region)
Phase B: B1 → B2
Phase C: C1 → C2
Phase D: D1 → D2
```

No `[P]` flags: backend tests are not parallel-safe (shared overrides/limiter
singleton) and each phase's tasks touch adjacent files. 4 phases > 3 → one
sub-agent worker per phase (sequential), per the sub-agent protocol; Verifier
runs fresh after D2.

## Task Granularity Check

| Task | Scope | Status |
|---|---|---|
| A1 | 2 DTOs, one file | ✅ Cohesive |
| A2 | 1 protocol, one file | ✅ Granular |
| A3 | 2 exceptions + 2 settings, two small files | ✅ Cohesive (contract-only) |
| B1 | 1 adapter + its tests | ✅ Granular |
| B2 | 1 service + its tests | ✅ Granular |
| C1 | 1 dependency + 2 handler entries + test extension | ✅ Cohesive |
| C2 | 1 endpoint + wiring + its tests | ✅ Granular (one endpoint) |
| D1 | 1 client module + its tests | ✅ Granular |
| D2 | 1 component + 1 page + 1 link + its tests | ✅ Cohesive (one screen) |

## Diagram-Definition Cross-Check

| Task | Depends On (body) | Diagram Shows | Status |
|---|---|---|---|
| A1 | None | phase A start | ✅ Match |
| A2 | A1 | A1 → A2 | ✅ Match |
| A3 | None (ordered after A2 for file adjacency) | A2 → A3 | ✅ Match (ordering, not dependency) |
| B1 | A1, A2 | A3 complete → B1 | ✅ Match (phase barrier ⊇ deps) |
| B2 | A1, A2, A3, B1 | B1 → B2 | ✅ Match |
| C1 | A3 | B2 complete → C1 | ✅ Match (phase barrier ⊇ deps) |
| C2 | B2, C1 | C1 → C2 | ✅ Match |
| D1 | C2 | C2 complete → D1 | ✅ Match |
| D2 | D1 | D1 → D2 | ✅ Match |

## Test Co-location Validation

| Task | Code Layer | Matrix Requires | Task Says | Status |
|---|---|---|---|---|
| A1 | Domain DTOs | none | none (build gate) | ✅ OK |
| A2 | Port protocol | none | none (build gate) | ✅ OK |
| A3 | Errors/settings | none | none (build gate) | ✅ OK |
| B1 | Answer adapter | unit | unit, co-located | ✅ OK |
| B2 | Application service | unit | unit, co-located | ✅ OK |
| C1 | Web rate limit/handlers | integration | integration (existing file extended) | ✅ OK |
| C2 | Web router/wiring | integration | integration, co-located | ✅ OK |
| D1 | Frontend client | unit | unit, co-located | ✅ OK |
| D2 | Frontend screen | unit | unit, co-located | ✅ OK |
