# Tasks — Cycle 2: Source Storage

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user — do not proceed without it.**

---

**Design**: `.specs/features/source-storage/design.md`
**Status**: Draft — writing complete, NOT executed (branch `feat/source-storage` not yet created)

> 8 tasks / 4 phases. >3 phases → at Execute, offer one sub-agent per phase (offer-then-confirm). `[P]` = order-free within a phase. One atomic commit per task; gate green before done. AC refs trace to spec.

---

## Test Coverage Matrix

> Generated from codebase, project guidelines, and spec — confirm before Execute. Guidelines found: `CLAUDE.md`, `.specs/codebase/CONVENTIONS.md` (ruff `E,F,I,UP,B`, line 100; pytest `testpaths=["tests"]`, `asyncio_mode=auto`; vitest). Cycle-1 tests sampled: `backend/tests/test_application_identity.py`, `test_repositories.py`, `test_web_auth.py`, `test_migrations.py`, `frontend/tests/proxy-forwarding.test.ts`, `auth-screens.test.tsx`.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| ---------- | ------------------ | -------------------- | ---------------- | ----------- |
| Domain entity / port (`Source`, `SourceRepository`) | unit | Entity invariants (no secret leakage in summary path); 1:1 where behavior exists | `backend/tests/test_domain_sources.py` | `cd backend && uv run pytest` |
| Application services + validation (`CreateSource`, `ListSources`, `GetSource`, `validate_source_upload`) | unit | All branches; 1:1 to spec ACs; every listed reject/edge case | `backend/tests/test_application_sources.py` | `cd backend && uv run pytest` |
| Repository (`SqlAlchemySourceRepository`) | integration | Key query paths (add, list newest-first + owner scope, get_by_id) + unique/constraint errors | `backend/tests/test_repositories.py` (extend) | `cd backend && uv run pytest` (live DB) |
| Storage adapter (`S3StorageAdapter`) | integration | put/get roundtrip, ensure-bucket idempotent, missing-object error | `backend/tests/test_storage_s3.py` | `cd backend && uv run pytest` (live MinIO; skip-if-unavailable) |
| Web router (`/api/sources`) | integration | Every route: happy + each validation reject + auth/CSRF + cross-user 404 + malformed 422 | `backend/tests/test_web_sources.py` | `cd backend && uv run pytest` (live DB + MinIO/fake) |
| Migration `0002` | integration | Applies up/down; schema (FK, index, unique object_key) matches design | `backend/tests/test_migrations.py` (extend) | `cd backend && uv run pytest` (live DB) |
| Frontend proxy + client (`/app/api/sources/**`, `lib/sources.ts`) | unit (vitest) | Forwards method/cookie/CSRF/multipart; client hits same-origin only | `frontend/tests/sources-proxy.test.ts`, `sources-client.test.ts` | `cd frontend && npm test` |
| Frontend screen (`/sources`, `SourcesPanel`) | unit (vitest) | Empty-state, add-on-success, error surface on reject, unauth redirect (UX-only) | `frontend/tests/sources-screen.test.tsx` | `cd frontend && npm test` |
| Config / `pyproject` / compose / `.env.example` | none | — (build gate only) | — | build gate only |

## Parallelism Assessment

> Generated from codebase — confirm before Execute.

| Test Type | Parallel-Safe? | Isolation Model | Evidence |
| --------- | -------------- | --------------- | -------- |
| Backend unit (fakes) | Yes | Pure fakes, no shared store | `backend/tests/fakes.py`, `test_application_identity.py` use in-memory fakes |
| Backend integration (DB/MinIO) | No | Shared test DB + shared MinIO bucket; cleanup between tests | `backend/tests/conftest.py` shares one engine/DB across tests (Cycle-1 pattern) |
| Frontend (vitest) | Yes | Per-test mocked fetch, no shared backend | `frontend/tests/proxy-forwarding.test.ts` mocks the upstream |

**Consequence:** tasks whose required test type is integration (T2, T3, T4, T6) run their tests sequentially — no `[P]`. Unit/vitest tasks may carry `[P]` when code-independent.

## Gate Check Commands

> Generated from codebase — confirm before Execute.

| Gate Level | When to Use | Command |
| ---------- | ----------- | ------- |
| Quick | After unit-only tasks (T1, T5) | `cd backend && uv run pytest tests/test_domain_sources.py tests/test_application_sources.py` |
| Full | After integration tasks (T2, T3, T4, T6) | `cd backend && uv run pytest` (requires live DB + MinIO from `docker compose up -d db minio`) |
| Frontend | After frontend tasks (T7, T8) | `cd frontend && npm test` |
| Build | After phase completion / config-only changes | `cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest && cd ../frontend && npm test` |

---

## Execution Plan

### Phase 1: Foundation (schema, storage, domain)

```
T1 ─┐
T2 ─┼─→ T3
T4 ─┘        (T4 order-free; T3 needs T1 + T2)
```

### Phase 2: Application (Sequential)

```
T1 ──→ T5
```

### Phase 3: Web (Sequential)

```
{T3, T4, T5} ──→ T6
```

### Phase 4: Frontend (Sequential)

```
T6 ──→ T7 ──→ T8
```

---

## Task Breakdown

### T1 — Domain `Source` entity + `SourceRepository` port

**What**: Add the `Source` frozen dataclass and the `SourceRepository` Protocol (`add`, `list_by_user`, `get_by_id`).
**Where**: `backend/app/domain/entities.py`, `backend/app/domain/ports.py`
**Depends on**: None
**Reuses**: dataclass + `runtime_checkable` Protocol + None-on-missing conventions from existing `entities.py`/`ports.py`
**Requirement**: SRC-06 (fields incl. opaque `object_key`), supports SRC-01/08/09

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] `Source` defined with all design fields; no framework/SDK imports (import-boundary respected)
- [ ] `SourceRepository` protocol defined with the three methods
- [ ] Quick gate passes: `cd backend && uv run pytest tests/test_domain_sources.py`
- [ ] Test count: ≥2 tests pass (no silent deletions)

**Tests**: unit — `Source` carries expected fields; summary path exposes no `object_key`/`checksum` leakage (asserted at service/web layer in T5/T6)
**Gate**: quick

---

### T2 — `sources` table metadata + migration `0002`

**What**: Define the `sources` table under the shared `MetaData` and add reversible Alembic migration `0002_sources_schema.py`.
**Where**: `backend/app/infrastructure/db/metadata.py`, `backend/migrations/versions/0002_sources_schema.py`
**Depends on**: None (schema is standalone; ordered before T3)
**Reuses**: `NAMING_CONVENTION`/`metadata` and `0001_identity_schema.py` migration pattern
**Requirement**: SRC-12 (FK→users cascade, index on user_id, unique object_key)

**Tools**: MCP: NONE · Skill: `uv` (run alembic)

**Done when**:
- [ ] `sources` table matches design (columns, types, `server_default 'uploaded'`, timestamps)
- [ ] `alembic upgrade head` then `downgrade` both succeed against live DB
- [ ] Full gate passes: `cd backend && uv run pytest` (migration test asserts table + constraints)
- [ ] Test count: existing migration tests + ≥1 new pass

**Tests**: integration — migration applies; `sources` has FK, `ix` on user_id, unique `object_key`
**Gate**: full

---

### T3 — `SqlAlchemySourceRepository`

**What**: Connection-injected repository implementing `SourceRepository` against the `sources` table.
**Where**: `backend/app/infrastructure/db/repositories.py`
**Depends on**: T1, T2
**Reuses**: `SqlAlchemyUserRepository` structure (Connection in ctor, Core `insert`/`select`)
**Requirement**: SRC-08 (owner-scoped list newest-first), supports SRC-01/09

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] `add` inserts and returns the entity; unique `object_key` violation propagates
- [ ] `list_by_user` returns only that user's rows, `created_at` DESC
- [ ] `get_by_id` returns entity or `None`
- [ ] Full gate passes: `cd backend && uv run pytest`
- [ ] Test count: ≥4 new repository tests pass (no silent deletions)

**Tests**: integration — add/get roundtrip; list scoped + newest-first; two-user isolation; duplicate object_key rejected
**Gate**: full

---

### T4 — `S3StorageAdapter` (boto3) + config + dependency + compose/env

**What**: boto3 adapter implementing `StoragePort` (put/get, ensure-bucket, `ObjectNotFound`); add storage settings, the `boto3` dependency, and MinIO env to compose/`.env.example`.
**Where**: `backend/app/infrastructure/storage/s3.py` (+ `__init__.py`), `backend/app/core/config.py`, `backend/pyproject.toml`, `backend/.env.example`, `docker-compose.yml`
**Depends on**: None
**Reuses**: `StoragePort` (unchanged, `ports.py:142`); `Settings` env-prefix pattern
**Requirement**: SRC-07, supports SRC-06 (key handling)

**Tools**: MCP: `context7` (boto3 S3 client API) · Skill: `uv` (add boto3)

**Done when**:
- [ ] `put_object`/`get_object` roundtrip works against MinIO; `_ensure_bucket` idempotent
- [ ] `get_object` on missing key raises `ObjectNotFound` (boto3 `ClientError` mapped, does not leak)
- [ ] Settings: `LEARNY_STORAGE_ENDPOINT/ACCESS_KEY/SECRET_KEY/BUCKET/REGION` + `LEARNY_EPUB_MAX_BYTES` (default 52428800); `.env.example` + compose `api` env updated
- [ ] Full gate passes: `cd backend && uv run pytest` (adapter test skips cleanly if MinIO absent)
- [ ] Test count: ≥3 adapter tests pass

**Tests**: integration — put/get roundtrip, ensure-bucket idempotent, missing→`ObjectNotFound`
**Gate**: full

---

### T5 — Application services + upload validation

**What**: `validate_source_upload`, `CreateSource`, `ListSources`, `GetSource`, and application errors (`InvalidSourceUpload`, `SourceNotFound`, `StorageUnavailable`).
**Where**: `backend/app/application/sources.py`, `backend/app/application/validation.py` (extend), `backend/app/application/errors.py` (extend), `backend/tests/fakes.py` (fake source repo + fake storage)
**Depends on**: T1
**Reuses**: `AuthorizeOwnership` (`identity.py:242`); existing `validation.py`/`errors.py` modules; fake-port test style
**Requirement**: SRC-01, SRC-02, SRC-03, SRC-04, SRC-06, SRC-09

**Tools**: MCP: NONE · Skill: `ruff`

**Done when**:
- [ ] `validate_source_upload` rejects: non-`.epub` ext, wrong content-type, `>max_bytes`, empty/whitespace/`>500` title, zero-byte file — each with the right `kind`
- [ ] `CreateSource` validates → `put_object` (opaque `sources/{user_id}/{uuid}.epub`, no title/email) → `add`; on storage error raises `StorageUnavailable` and does not call `add`
- [ ] `GetSource`: owner→entity; non-owner→`SourceNotFound`; missing→`SourceNotFound` (maps `NotAuthorized`→404 semantics)
- [ ] `ListSources` delegates to `list_by_user`
- [ ] Quick gate passes: `cd backend && uv run pytest tests/test_domain_sources.py tests/test_application_sources.py`
- [ ] Test count: ≥10 unit tests pass (no silent deletions)

**Tests**: unit (fake ports) — 1:1 to spec ACs (SRC-01/02/03/04/09) incl. opaque-key assertion and non-owner→404
**Gate**: quick

---

### T6 — `/api/sources` router + wiring + error mappings

**What**: FastAPI router (`POST`/`GET`/`GET {id}`), `SourceSummary`, composition-root deps, `main.py` include, `rate_limit_upload` hook, and error-handler mappings (415/413/422/404/503).
**Where**: `backend/app/infrastructure/web/sources.py`, `backend/app/infrastructure/web/dependencies.py` (extend), `backend/app/infrastructure/web/rate_limit.py` (extend), `backend/app/infrastructure/web/error_handlers.py` (extend), `backend/app/main.py`
**Depends on**: T3, T4, T5
**Reuses**: `get_authenticated_user`, `get_db_connection`, `enforce_csrf`/`enforce_origin`, `UserSummary` pattern, error-handler registration
**Requirement**: SRC-01, SRC-02, SRC-03, SRC-04, SRC-05, SRC-08, SRC-09, SRC-10

**Tools**: MCP: NONE · Skill: `fastapi`

**Done when**:
- [ ] `POST /api/sources` (multipart file+title) → `201` + secret-free `SourceSummary`; row + object persisted
- [ ] Rejects: non-EPUB→`415`, oversize→`413`, missing/empty title or no file or zero-byte→`422`, unauth→`401`, missing/invalid CSRF or bad origin→`403` — each persists nothing
- [ ] `GET /api/sources` → owner-scoped list newest-first, `[]` when none, `401` unauth
- [ ] `GET /api/sources/{id}` → owner `200`; cross-user `404`; missing `404`; malformed UUID `422`
- [ ] Source lifecycle logged with `user_id`/`source_id`, no secrets (SRC-10)
- [ ] Full gate passes: `cd backend && uv run pytest`
- [ ] Test count: ≥12 integration tests pass (no silent deletions)

**Tests**: integration — every route: happy + each reject + auth/CSRF + cross-user 404 + malformed 422
**Gate**: full

**Commit**: `feat(sources): upload, list, and read owned EPUB sources`

---

### T7 — Sources client (same-origin, via existing catch-all proxy)

**What**: `lib/sources.ts` client (`listSources`/`uploadSource`/`getSource`) calling same-origin `/api/sources*`.

> SPEC_DEVIATION (accepted, user-confirmed at Execute): design.md/this task originally called for new dedicated proxy route files (`frontend/app/api/sources/route.ts`, `frontend/app/api/sources/[id]/route.ts`). Discovered during Execute that Cycle 1 already shipped a generic catch-all proxy (`frontend/app/api/[...path]/route.ts`) that forwards method/cookie/`X-CSRF-Token`/raw body (multipart included) for *any* `/api/*` path, already covering `/api/sources` and `/api/sources/{id}` with no new code, and already generically tested. Writing sources-specific proxy files would be pure duplication with zero behavioral difference. Reviewed realistic future divergence (ADR-018 presigned-upload revisit, deferred ingestion-trigger endpoint) — each either stays covered by the catch-all as-is or requires genuinely new logic a stub file wouldn't help with. Decision: skip the dedicated proxy routes; ship only the client.

**Where**: `frontend/app/lib/sources.ts`
**Depends on**: T6
**Reuses**: existing `frontend/app/api/[...path]/route.ts` catch-all proxy (no new proxy code needed); `frontend/app/lib/auth.ts` (CSRF fetch) pattern
**Requirement**: SRC-11 (same-origin boundary)

**Tools**: MCP: NONE · Skill: `vercel-react-best-practices`

**Done when**:
- [ ] `listSources`/`uploadSource`/`getSource` call only same-origin `/api/sources*` (relying on the existing catch-all to reach FastAPI)
- [ ] Frontend gate passes: `cd frontend && npm test`
- [ ] Test count: ≥3 vitest tests pass

**Tests**: unit (vitest) — client uses same-origin paths only, sends multipart correctly, forwards CSRF header per `auth.ts` pattern
**Gate**: frontend

---

### T8 — `/sources` screen + `SourcesPanel`

**What**: The `/sources` page and `SourcesPanel` (list with empty-state, upload form, error surface, UX-only unauth redirect).
**Where**: `frontend/app/sources/page.tsx`, `frontend/app/components/SourcesPanel.tsx`
**Depends on**: T7
**Reuses**: `AccountPanel`/`AuthForm` structure and redirect-on-unauth pattern
**Requirement**: SRC-11

**Tools**: MCP: NONE · Skill: `vercel-composition-patterns`

**Done when**:
- [ ] `/sources` renders the user's sources (empty-state when none) via the proxy
- [ ] Selecting an `.epub` + title and submitting adds the source to the list on success
- [ ] A rejected upload (e.g. 415/413/422) surfaces an error and adds nothing
- [ ] Unauthenticated visit redirects to `/login` (UX only)
- [ ] Frontend gate passes: `cd frontend && npm test`
- [ ] Test count: ≥4 vitest tests pass

**Tests**: unit (vitest) — empty-state, add-on-success, error-on-reject, unauth redirect
**Gate**: frontend

**Commit**: `feat(sources): sources screen with EPUB upload and listing`

---

## Verifier (always-on, after last task)

Fresh Verifier (author ≠ verifier): spec-anchored outcome check across SRC-01..SRC-12 + discrimination sensor (inject faults: skip ownership check → cross-user read must fail; skip size/type validation → reject tests must fail; break newest-first ordering → list test must fail); writes `validation.md` (PASS/FAIL, per-AC evidence, sensor result, diff range). Gaps → bounded fix loop (≤3). Then `learny-finalize` for the PR.

---

## Pre-Approval Validation

### Task Granularity Check

| Task | Scope | Status |
| ---- | ----- | ------ |
| T1: entity + port | 2 cohesive defs, one module area | ✅ Granular |
| T2: table + migration | 1 schema + its migration | ✅ Granular |
| T3: repository | 1 adapter class | ✅ Granular |
| T4: storage adapter + config | 1 adapter + its settings/deps (cohesive) | ✅ Granular |
| T5: services + validation | services + validation for one resource (cohesive; unit-tested together) | ✅ Granular |
| T6: router + wiring | 1 router + its composition (cohesive) | ✅ Granular |
| T7: proxy + client | 1 proxy pair + client (cohesive) | ✅ Granular |
| T8: screen + panel | 1 page + its panel | ✅ Granular |

### Diagram-Definition Cross-Check

| Task | Depends On (body) | Diagram Shows | Status |
| ---- | ----------------- | ------------- | ------ |
| T1 | None | (root) | ✅ Match |
| T2 | None | (root) | ✅ Match |
| T3 | T1, T2 | T1→T3, T2→T3 | ✅ Match |
| T4 | None | (root, order-free) | ✅ Match |
| T5 | T1 | T1→T5 | ✅ Match |
| T6 | T3, T4, T5 | {T3,T4,T5}→T6 | ✅ Match |
| T7 | T6 | T6→T7 | ✅ Match |
| T8 | T7 | T7→T8 | ✅ Match |

### Test Co-location Validation

| Task | Code Layer Created/Modified | Matrix Requires | Task Says | Status |
| ---- | --------------------------- | --------------- | --------- | ------ |
| T1 | Domain entity/port | unit | unit | ✅ OK |
| T2 | Migration/schema | integration | integration | ✅ OK |
| T3 | Repository | integration | integration | ✅ OK |
| T4 | Storage adapter | integration | integration | ✅ OK |
| T5 | Application services + validation | unit | unit | ✅ OK |
| T6 | Web router | integration | integration | ✅ OK |
| T7 | Frontend proxy + client | unit (vitest) | unit (vitest) | ✅ OK |
| T8 | Frontend screen | unit (vitest) | unit (vitest) | ✅ OK |

All three checks pass — no ❌.

---

## Requirement → Task Coverage

| Requirement | Task(s) |
| ----------- | ------- |
| SRC-01 upload create | T5, T6 (+T3, T4) |
| SRC-02 type/ext validation | T5, T6 |
| SRC-03 size cap | T4 (setting), T5, T6 |
| SRC-04 title validation | T5, T6 |
| SRC-05 auth + CSRF/origin + rate-limit | T6 |
| SRC-06 opaque owner-partitioned key via StoragePort | T1, T5 |
| SRC-07 boto3 adapter + bucket ensure | T4 |
| SRC-08 owner-scoped list newest-first | T3, T6 |
| SRC-09 ownership→404 + storage/DB failure | T5, T6 |
| SRC-10 lifecycle logging, no secrets | T6 |
| SRC-11 web `/sources` via same-origin proxy | T7, T8 |
| SRC-12 migration 0002 | T2 |

**Coverage:** 12/12 requirements mapped to tasks.

## Dependency summary

T1, T2, T4 are roots; T1+T2 → T3; T1 → T5; {T3,T4,T5} → T6 → T7 → T8. Integration-tested tasks (T2, T3, T4, T6) run tests sequentially (shared DB/MinIO). Verifier runs after T8.

## Open pre-Execute item (per Tasks step 6)

Tools/skills per task are pre-filled above (default `filesystem`; `fastapi`/`ruff`/`uv` backend, `vercel-*` frontend, `learny-finalize` at publish). Confirm or adjust at the start of Execute.
