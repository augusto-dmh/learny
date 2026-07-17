# v2-active-recall Tasks

## Execution Protocol (MANDATORY — do not skip)

Implement these tasks with the `tlc-spec-driven` skill: activate it by name and follow its
Execute flow and Critical Rules (tests from ACs, gate per task, one atomic commit per task,
fresh Verifier at the end). Ship-cycle mode: one worker per phase, sequential; all phases
**Opus** (each carries a correctness invariant — see design.md Phase sketch); Verifier Opus.

**Worker environment notes (pass to every worker):**
- Branch: `feat/v2-active-recall` (already checked out by the orchestrator).
- `uv` is at `/home/augusto/myenv/bin/uv` (not on default PATH). Backend commands run from `backend/`.
- DB-backed tests need `LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test` and the `db` container running (`docker.exe compose up -d db` — bare `docker` unavailable in this WSL distro).
- Frontend commands run from `frontend/` (`npx vitest run`, `npx tsc --noEmit`, `npm run build`).
- Commits: Conventional Commits, plain language, **no internal IDs (QUIZ-NN/AD-NNN/task ids), no AI attribution**.
- Never weaken/skip/delete existing tests; expected suite floors: backend 656 passed / 10 skipped, frontend 130 passed before this cycle.

**Design**: `.specs/features/v2-active-recall/design.md`
**Status**: Done — all 19 tasks committed (d9f6880..0b651b6), Verifier PASS (25/25 ACs, 6/6 mutants killed; see validation.md)

---

## Test Coverage Matrix

> Guidelines found: `CLAUDE.md` (golden fixtures principle, citations/eval as core), CI `.github/workflows/ci.yml` (backend pytest vs live Postgres+Redis, frontend vitest+tsc+build), `backend/pyproject.toml` markers (`live`, `eval`). Existing suite sampled: flat `backend/tests/test_<layer>_<area>.py`, `tests/fakes.py`, `requires_db` gating, fetchImpl/jsdom conventions (AD-071).

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
|---|---|---|---|---|
| Domain entities/QC helpers | unit | All branches; 1:1 to QUIZ-06/07 semantics + content_key stability | `backend/tests/test_domain_quiz.py` | `uv run pytest tests/test_domain_quiz.py -q` |
| Migration | integration | upgrade→downgrade→upgrade round-trip incl. 0008 | `backend/tests/test_migrations.py` | `uv run pytest tests/test_migrations.py -q` |
| Repositories | integration (requires_db) | upsert-preserves-scheduling, due query incl. cross-user isolation, job transitions, log append | `backend/tests/test_repositories_quiz.py` | `uv run pytest tests/test_repositories_quiz.py -q` |
| Adapters (quiz local/anthropic, fsrs, export) | unit (fake client / fuzz-off) | every AC branch: batch begin/collect/pending/errors, factory fail-fast, FSRS monotonic behavior, GUID stability | `backend/tests/test_quiz_*.py`, `test_scheduling_fsrs.py`, `test_export_anki.py` | `uv run pytest tests/<file> -q` |
| Application services | unit + requires_db where stateful | 1:1 to QUIZ-02..09, 11..17 ACs + listed edge cases | `backend/tests/test_application_quiz.py`, `test_application_reviews.py` | `uv run pytest tests/<file> -q` |
| Worker tasks | integration (eager-style per existing worker tests) | happy + retry + timeout + idempotent re-run + reconcile matrix | `backend/tests/test_worker_quiz.py` | `uv run pytest tests/test_worker_quiz.py -q` |
| Routers | integration (TestClient fixtures) | every route: happy + 401/404/409/422/429 | `backend/tests/test_web_quiz.py` | `uv run pytest tests/test_web_quiz.py -q` |
| Eval (deterministic) | integration | 100% groundedness invariants + poisoned-candidate discrimination | `backend/tests/eval/test_quiz_groundedness.py` | `uv run pytest tests/eval/test_quiz_groundedness.py -q` |
| Eval (judge) | live+eval marked | answerability round-trip, skipped offline | `backend/tests/eval/test_quiz_answerability.py` | skipped in PR suite by marker |
| Frontend clients | unit (fetchImpl-injected) | every client fn: success + error mapping | `frontend/tests/quiz-client.test.ts` | `npx vitest run tests/quiz-client.test.ts` |
| Frontend screens | component (jsdom) | queue→reveal→grade→advance→summary, empty, error, cloze render, deck polling states | `frontend/tests/review-screen.test.tsx`, `library-screen.test.tsx` | `npx vitest run tests/<file>` |
| Config/entities/ADR | none | build gate only | — | build gate |

## Parallelism Assessment

| Test Type | Parallel-Safe? | Isolation Model | Evidence |
|---|---|---|---|
| Backend DB-backed | No | shared `learny_test` DB, per-test rolled-back txn on one conn | `backend/tests/conftest.py:43-57` |
| Backend pure-unit | Yes (but suite runs sequentially in CI) | no shared state | existing suite runs `pytest -q` single-process |
| Frontend vitest | Yes | jsdom per file | `vitest.config.ts` |

All execution is sequential (one worker per phase); `[P]` marks order-free tasks within a phase only.

## Gate Check Commands

| Gate Level | When to Use | Command (from `backend/` / `frontend/`) |
|---|---|---|
| Quick | per task | `uv run pytest tests/<touched module(s)> -q` |
| Full backend | phase boundary (A–D, F) | `uv run pytest -q` + `uv run ruff check .` |
| Full frontend | phase E boundary | `npx vitest run` + `npx tsc --noEmit` + `npm run build` |
| Pre-finalize | after last phase | both fulls |

---

## Execution Plan

```
Phase A (worker A): A1 → A2 → A3          schema/domain foundation
Phase B (worker B): B1 → B2 [P] → B3 [P]  repos + generation adapters
Phase C (worker C): C1 → C2 → C3          deck pipeline + reconcile
Phase D (worker D): D1 → D2 → D3 → D4     scheduling + HTTP + export
Phase E (worker E): E1 → E2 [P] → E3 [P]  frontend
Phase F (worker F): F1 [P] → F2 [P] → F3 [P]  evals + ADR
then: fresh Verifier (Opus, always)
```

## Task Breakdown

### Phase A — foundation

**A1: Dependencies + settings**
**What**: Add `fsrs>=6,<7` + `genanki` (pin current minor at install) to `backend/pyproject.toml`, lock; add settings `quiz_model`, `quiz_max_items_per_section`, `quiz_min_section_chars`, `quiz_dedup_threshold`, `quiz_batch_timeout_s`, `quiz_batch_poll_interval_s`, `fsrs_desired_retention`, `fsrs_fuzzing` with design defaults.
**Where**: `backend/pyproject.toml`, `backend/app/core/config.py`, settings test file (extend existing).
**Depends on**: none. **Requirement**: QUIZ-05/11 (settings substrate).
**Done when**: defaults asserted in settings test; `uv run pytest tests/<settings test> -q` green; imports of `fsrs`/`genanki` succeed. **Tests**: unit. **Gate**: quick. **Commit**: `chore(quiz): add scheduling and deck generation settings and deps`

**A2: Migration 0008_quiz_schema**
**What**: 4 tables per design DDL (constraints, named indexes, CHECK rating 1–4, unique `(source_id, content_key)`, `embedding vector(1536) NULL`), down_revision `0007_language_aware_fts`, clean downgrade.
**Where**: `backend/migrations/versions/0008_quiz_schema.py`, `backend/tests/test_migrations.py`.
**Depends on**: A1. **Requirement**: QUIZ-01.
**Done when**: round-trip test green including new revision. **Tests**: integration. **Gate**: quick (migrations module) . **Commit**: `feat(quiz): add quiz schema migration`

**A3: Domain entities, ports, QC helpers**
**What**: Entities/constants/ports per design §Domain + pure QC helpers (`normalize_text`, `content_key`, `quote_in_text`, cloze validity) with 1:1 AC tests (QUIZ-06/07 semantics, content_key includes item_type, handle payload round-trip).
**Where**: `backend/app/domain/entities.py`, `backend/app/domain/ports.py`, new QC module per design, `backend/tests/test_domain_quiz.py`.
**Depends on**: A1. **Requirement**: QUIZ-03/06/07/10/11 (contracts).
**Done when**: tests green; no framework imports in domain; full backend gate green at phase end. **Tests**: unit. **Gate**: quick + full backend (phase boundary). **Commit**: `feat(quiz): add quiz domain contracts and grounding checks`

### Phase B — repos + generation adapters

**B1: Quiz repositories**
**What**: `SqlAlchemyQuizItemRepository` (upsert content-only on conflict; list/counts; due query joined via sources; scheduling get/update; log append; reconciliation reads/updates) + `SqlAlchemyQuizJobRepository` (create/get-active/transition) + DB tests: **upsert preserves scheduling+log**, due excludes other users/non-active/future, job single-active guard query.
**Where**: `backend/app/infrastructure/db/repositories.py`, `backend/tests/test_repositories_quiz.py`.
**Depends on**: A2, A3. **Requirement**: QUIZ-02/13/17.
**Done when**: repo tests green vs live test DB. **Tests**: integration. **Gate**: quick. **Commit**: `feat(quiz): add quiz item, scheduling and job repositories`

**B2: Deterministic quiz adapter [P]**
**What**: `DeterministicQuizAdapter` per design (inline begin/collect, eligibility rules, 1 free_recall + 1 cloze per section, grounded by construction).
**Where**: `backend/app/infrastructure/quiz/local.py`, `backend/tests/test_quiz_local.py`.
**Depends on**: A3. **Requirement**: QUIZ-05 (local path), QUIZ-10.
**Done when**: determinism (same input → same output), eligibility, groundedness asserted. **Tests**: unit. **Gate**: quick. **Commit**: `feat(quiz): add deterministic quiz generation adapter`

**B3: Anthropic quiz adapter + factory [P]**
**What**: `AnthropicQuizAdapter` (Batch API begin/collect with injected fake client; per-section json_schema with chunk-id enum; per-request error mapping; **verify real SDK batch param names + output_config-in-batch support at install**, apply documented fallback if unsupported and record in ADR notes) + `build_quiz_adapter` factory (local default, anthropic fail-fast, unknown ValueError).
**Where**: `backend/app/infrastructure/quiz/anthropic.py`, `__init__.py`, `backend/tests/test_quiz_anthropic.py`, `test_quiz_factory.py`.
**Depends on**: A3. **Requirement**: QUIZ-05/10.
**Done when**: fake-client tests cover begin (N requests, schema shape), collect pending/complete/errors; factory tests mirror `test_answering_factory.py`; full backend gate at phase end. **Tests**: unit. **Gate**: quick + full backend. **Commit**: `feat(quiz): add anthropic batch quiz adapter and provider factory`

### Phase C — deck pipeline + reconcile

**C1: Deck application services + QC/dedup pipeline**
**What**: `PlanDeckGeneration` (ready-check, single-in-flight → `QuizDeckConflict`, job create, enqueue-after-commit port), `RunDeckGeneration` (own-UoW transitions; sections from corpus; QC → embedding dedup ≥ threshold vs in-run + persisted; content_key upsert; `SchedulingPort.initial()` rows for new items; counts; complete/fail), `ListQuizItems`; new error types.
**Where**: `backend/app/application/quiz.py`, `backend/app/domain/errors.py` (or existing error module), `backend/tests/test_application_quiz.py`.
**Depends on**: B1, B2. **Requirement**: QUIZ-02/03/04/06/07/08/09.
**Done when**: AC-mapped tests incl. edge cases (zero eligible sections → succeed w/ 0; poisoned quote discarded; dedup at threshold boundary; re-run idempotent, scheduling untouched). **Tests**: unit + requires_db. **Gate**: quick. **Commit**: `feat(quiz): add deck generation services with grounding and dedup`

**C2: Celery deck tasks**
**What**: `generate_quiz_deck` + `poll_quiz_deck` (self-reschedule w/ countdown, deadline → fail timeout; local path finalizes inline; retries via `_retry_countdown`; trace scoping; `CeleryQuizDeckEnqueuer`).
**Where**: `backend/app/worker/tasks.py`, `backend/app/infrastructure/worker/enqueuer.py`, `backend/tests/test_worker_quiz.py`.
**Depends on**: C1, B3. **Requirement**: QUIZ-05/09 + batch edge cases.
**Done when**: eager-style tests cover local end-to-end persist, pending→reschedule, deadline timeout → failed job, idempotent re-delivery. **Tests**: integration. **Gate**: quick. **Commit**: `feat(quiz): add celery deck generation and batch polling tasks`

**C3: Re-ingest reconciliation**
**What**: `ReconcileQuizItems` + step wired into `run_ingestion` after corpus replace (no-op fast path when no items).
**Where**: `backend/app/application/quiz.py` (or sibling), ingestion service/task wiring, `backend/tests/test_worker_quiz.py` or dedicated file.
**Depends on**: C1. **Requirement**: QUIZ-16/17.
**Done when**: matrix tests keep/stale/relocate/orphan; scheduling+log rows byte-identical after reconcile; existing ingestion test modules still green; full backend gate at phase end. **Tests**: integration. **Gate**: quick (incl. existing ingestion modules) + full backend. **Commit**: `feat(quiz): reconcile quiz items on re-ingestion`

### Phase D — scheduling + HTTP + export

**D1: FSRS scheduling adapter**
**What**: `FsrsSchedulingAdapter` per design (settings-driven, UTC, fuzz-off in tests, snapshot↔Card mapping).
**Where**: `backend/app/infrastructure/scheduling/fsrs.py`, `backend/tests/test_scheduling_fsrs.py`.
**Depends on**: A3. **Requirement**: QUIZ-11.
**Done when**: initial() due-now Learning; 4 ratings behave monotonically (Again resets short, Easy > Good interval); repeated Good reviews grow interval; all datetimes tz-aware UTC. **Tests**: unit. **Gate**: quick. **Commit**: `feat(quiz): add fsrs scheduling adapter`

**D2: Review application services**
**What**: `GetDueQueue` (cross-source join, filter, limit cap, order due/id) + `SubmitReview` (authorize via source; 409 non-active; atomic scheduling update + log append) + errors.
**Where**: `backend/app/application/reviews.py`, `backend/tests/test_application_reviews.py`.
**Depends on**: D1, B1. **Requirement**: QUIZ-12/13/17 + A-2/A-4.
**Done when**: AC-mapped tests incl. early review allowed, stale/orphaned rejected + excluded, cross-user isolation. **Tests**: unit + requires_db. **Gate**: quick. **Commit**: `feat(quiz): add due queue and review submission services`

**D3: Quiz router + wiring**
**What**: `web/quiz.py` (deck POST 202, overview GET, due GET, reviews POST, export GET route shell), `rate_limit_quiz`, error mappings, `dependencies.py` composition, `main.py` include; TestClient fixture `quiz_client`.
**Where**: `backend/app/infrastructure/web/{quiz.py,rate_limit.py,error_handlers.py,dependencies.py}`, `backend/app/main.py`, `backend/tests/test_web_quiz.py`, `conftest.py`.
**Depends on**: C1, D2. **Requirement**: QUIZ-03/04/12/13/14/18.
**Done when**: every route happy + 401/404-nondisclosure/409/422/429 + CSRF/origin enforced on state-changing. **Tests**: integration. **Gate**: quick. **Commit**: `feat(quiz): add quiz and review endpoints`

**D4: Anki export**
**What**: `build_apkg` (genanki, fixed model/deck IDs, `guid_for(source_id, content_key)`, Basic + Cloze models, citation footnote, tempdir hygiene) + export endpoint behavior (bytes, filename, 404 empty).
**Where**: `backend/app/infrastructure/export/anki.py`, `web/quiz.py`, `backend/tests/test_export_anki.py`.
**Depends on**: D3. **Requirement**: QUIZ-22.
**Done when**: apkg non-empty + GUID stable across two builds; 404 empty; full backend gate at phase end. **Tests**: unit + route test. **Gate**: quick + full backend. **Commit**: `feat(quiz): add anki deck export`

### Phase E — frontend

**E1: quiz client**
**What**: `lib/quiz.ts` per design (5 fns, fetchImpl-injected, error mapping per siblings).
**Where**: `frontend/app/lib/quiz.ts`, `frontend/tests/quiz-client.test.ts`.
**Depends on**: D3. **Requirement**: QUIZ-21.
**Done when**: every fn success + error-mapping tests. **Tests**: unit. **Gate**: quick (vitest file). **Commit**: `feat(web): add quiz api client`

**E2: Review screen [P]**
**What**: `/review` route + `review-screen.tsx` (+card component): queue → reveal → 4-button grade → advance → summary; empty state; cloze `____` rendering; citation footnote + "Open in book"; error state.
**Where**: `frontend/app/(app)/review/page.tsx`, `frontend/app/components/review-screen.tsx`, `frontend/tests/review-screen.test.tsx`.
**Depends on**: E1. **Requirement**: QUIZ-15/19.
**Done when**: jsdom tests cover the full session flow + states. **Tests**: component. **Gate**: quick. **Commit**: `feat(web): add spaced repetition review screen`

**E3: Library deck integration [P]**
**What**: Generate-deck button w/ AD-070 polling of overview until terminal, counts + stale/orphaned badges, due count, `/review` links (per-source + shell entry).
**Where**: `frontend/app/components/library-screen.tsx` (+shell), `frontend/tests/library-screen.test.tsx`.
**Depends on**: E1. **Requirement**: QUIZ-20.
**Done when**: polling start/stop/terminal + failed + counts tested; full frontend gate (vitest+tsc+build) at phase end. **Tests**: component. **Gate**: quick + full frontend. **Commit**: `feat(web): add quiz deck controls to library`

### Phase F — evals + ADR

**F1: Deterministic groundedness eval [P]**
**What**: PR-suite eval per design (golden corpus + local adapter + QC; poisoned-candidate discrimination case).
**Where**: `backend/tests/eval/test_quiz_groundedness.py`.
**Depends on**: C1. **Requirement**: QUIZ-23.
**Done when**: invariants + discrimination case green offline. **Tests**: integration. **Gate**: quick. **Commit**: `test(eval): add deterministic quiz groundedness eval`

**F2: Answerability judge [P]**
**What**: `app/eval/prompts/answerability.md` + `Judge.answerability` (structured outputs, versioned prompt) + `tests/eval/test_quiz_answerability.py` (`live and eval`, `LEARNY_EVAL_MAX_CASES` capped, JSONL results); confirm `eval.yml` picks it up unchanged.
**Where**: `backend/app/eval/judge.py`, prompts dir, tests/eval.
**Depends on**: C1. **Requirement**: QUIZ-24.
**Done when**: offline suite skips it; unit test for prompt loading/schema with fake client. **Tests**: unit + live-marked. **Gate**: quick. **Commit**: `test(eval): add quiz answerability judge`

**F3: ADR-0021 [P]**
**What**: `docs/adr/0021-active-recall-design.md` (Accepted) per design; link from RFC-002 follow-ups if the RFC tracks them.
**Where**: `docs/adr/`.
**Depends on**: none (content from design). **Requirement**: QUIZ-25.
**Done when**: ADR follows house format; full backend gate at phase end (pre-finalize both fulls). **Tests**: none. **Gate**: full backend + full frontend (pre-finalize). **Commit**: `docs(adr): record the active recall design decision`

---

## Diagram-Definition Cross-Check

| Task | Depends On (body) | Diagram | Status |
|---|---|---|---|
| A1 none / A2 A1 / A3 A1 | as listed | A1→A2→A3 (A3 needs only A1; sequential order harmless) | ✅ |
| B1 A2,A3 / B2 A3 / B3 A3 | as listed | B1 → B2[P], B3[P] (B2/B3 independent of B1 and each other) | ✅ |
| C1 B1,B2 / C2 C1,B3 / C3 C1 | as listed | C1→C2→C3 (C3 after C2 harmless; needs only C1) | ✅ |
| D1 A3 / D2 D1,B1 / D3 C1,D2 / D4 D3 | as listed | D1→D2→D3→D4 | ✅ |
| E1 D3 / E2 E1 / E3 E1 | as listed | E1 → E2[P], E3[P] | ✅ |
| F1 C1 / F2 C1 / F3 none | as listed | F1[P], F2[P], F3[P] | ✅ |

## Test Co-location Validation

| Task | Layer | Matrix requires | Task says | Status |
|---|---|---|---|---|
| A1 | config | unit (settings) | unit | ✅ |
| A2 | migration | integration | integration | ✅ |
| A3 | domain | unit | unit | ✅ |
| B1 | repository | integration | integration | ✅ |
| B2/B3 | adapter | unit | unit | ✅ |
| C1 | service | unit+db | unit+db | ✅ |
| C2/C3 | worker | integration | integration | ✅ |
| D1 | adapter | unit | unit | ✅ |
| D2 | service | unit+db | unit+db | ✅ |
| D3 | router | integration | integration | ✅ |
| D4 | adapter+route | unit+route | unit+route | ✅ |
| E1 | client | unit | unit | ✅ |
| E2/E3 | screen | component | component | ✅ |
| F1 | eval | integration | integration | ✅ |
| F2 | eval | unit+live | unit+live | ✅ |
| F3 | docs | none | none | ✅ |

**Tools per phase** (project-local skills workers may load): A/B/C — `celery-workers`, `epub-ingestion` (corpus access patterns), `pgvector-hybrid-search` (vector column conventions); D — `fastapi`; E — `vercel-react-best-practices`; F — `create-adr`. MCPs: none.

**Requirement coverage:** QUIZ-01..25 all mapped (see task Requirement fields); traceability statuses move to In Tasks → Implementing per phase.
