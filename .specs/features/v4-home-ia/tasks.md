# v4-home-ia Tasks

## Execution Protocol (MANDATORY — do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. If the skill cannot be activated, STOP.

---

**Design**: `.specs/features/v4-home-ia/design.md`
**Status**: Not started

---

## Test Coverage Matrix

> Guidelines: `CLAUDE.md`, CI `.github/workflows/ci.yml` (pytest -q · ruff check · vitest · tsc · next build). Depth sampled from `backend/tests/` (~100 files) and `frontend/tests/` (~50 files).

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| --- | --- | --- | --- | --- |
| Migration 0015 | integration | chain + table/PK/FK/default shape asserts | `backend/tests/test_migrations.py` | `cd backend && uv run pytest tests/test_migrations.py -q` |
| `local_day` helper | unit (pure) | valid tz, DST-adjacent instants, invalid tz, None → UTC | `backend/tests/test_study_pure.py` (new) | `cd backend && uv run pytest tests/test_study_pure.py -q` |
| Application services | unit (fakes) | all branches, 1:1 to HOME ACs and edge cases | `backend/tests/test_application_study.py` (new), `test_application_reviews.py`, `test_application_reading.py` | per-file |
| Repositories | integration (`requires_db`) | upsert-increment, concurrency (two sessions), window bounds, user-scoping negatives, most_recent join/cascade | `backend/tests/test_repositories_study.py` (new), `test_repositories_reading.py` | needs `LEARNY_TEST_DATABASE_URL` |
| Web routes | integration (TestClient) | happy + authz + 422 bounds + tz fallback + txn atomicity (I-1) | `backend/tests/test_web_study.py` (new), `test_web_quiz.py`, `test_web_reading.py` | per-file |
| Frontend clients | unit (node env) | header attach, shapes, error mapping | `frontend/tests/study-client.test.ts` (new) + existing client tests | `cd frontend && npx vitest run <file>` |
| Frontend components | unit (jsdom) | hero data/empty, due count/done, heatmap cells/grace, toggle persist, sidebar items, redirects, landing CTAs | `frontend/tests/home-screen.test.tsx`, `study-heatmap.test.tsx`, `use-home-settings.test.tsx` (new); `app-sidebar.test.tsx`, `route-redirects.test.tsx`, `library-screen.test.tsx` (updated) | per-file |

## Parallelism Assessment

Same model as prior cycles: `[P]` is ordering info only — each phase is one sequential worker, so DB-test serialization is automatic. Backend `requires_db` tests share the session-scoped engine (`conftest.py` truncation model); frontend vitest is per-file isolated.

## Gate Check Commands

| Gate Level | When | Command |
| --- | --- | --- |
| Quick | per-task, affected modules | `cd backend && uv run pytest tests/<affected> -q` / `cd frontend && npx vitest run <files>` |
| Full backend | phase boundary (Phase A) | `cd backend && uv run pytest -q && uv run ruff check` |
| Full frontend | phase boundary (Phases B/C/D) | `cd frontend && npx vitest run && npx tsc --noEmit && npm run build` |
| Build (everything) | before publish + after review fixes | both fulls |

**Verified baseline (v3-F close, current `main`):** backend **1522 passed / 10 skipped** + ruff clean; frontend **494 passed / 50 files** + tsc + build.
**Env facts:** backend gates need `LEARNY_EMBEDDING_PROVIDER=local LEARNY_GENERATION_PROVIDER=local` (backend/.env pins real providers otherwise); DB-marked tests need `LEARNY_TEST_DATABASE_URL` against dev Postgres (Docker Desktop, `learny_test` exists); run backend via `uv` from `backend/`; mutating a migration and reverting the file does NOT revert the schema (use a throwaway DB).

---

## Execution Plan

```
Phase A (backend, sequential):    T1 → T2 → T3
Phase B (frontend, sequential):   T4 → T5        (needs A)
Phase C (frontend, sequential):   T6             (needs A; independent of B's tasks but same worker-tree ordering B→C)
Phase D (frontend, sequential):   T7 → T8        (independent of A–C in content; runs last to absorb nav/redirect churn)
Verifier (fresh, always):         after T8
```

One worker per phase (ship-cycle model). All phases Opus-tier session model; Verifier per ship-cycle upshift policy.

---

## Phase A — study backbone (backend)

### T1 — `study_days` schema + repositories

Migration `0015_study_days` per design contract; `StudyDay` entity; `SqlAlchemyStudyDayRepository` (`record` upsert-increment, `window`); `SqlAlchemyReadingPositionRepository.most_recent_for_user`. Tests per matrix rows 1 & 4 (incl. I-2 concurrency sensor and cascade behavior). **ACs:** HOME-10 (repo half), HOME-04 (scoping), migration shape.
**Commit:** `feat(db): add study_days rollup and cross-source reading position query`

### T2 — activity hooks + local-day boundary

`local_day` pure helper (I-3); `SubmitReview` and `SaveReadingPosition` gain rollup writes in-transaction (I-1 sensor: forced failure after the primary write leaves no study-day row); web layer reads `X-Client-Timezone` and passes through; existing response bodies pinned byte-identical (I-6). **ACs:** HOME-07, 08, 09, 10.
**Commit:** `feat(study): record study days from reviews and reading activity`

### T3 — study + continue endpoints

`application/study.py` `GetStudySummary` + `ContinueReading` (chapter-title resolution via existing locate helpers); `web/study.py` router (`GET /api/study/days`, `GET /api/reading/continue`) registered in `main.py`; I-4 (nothing derived stored) and I-5 (SQL scoping) sensors; 422 bounds; full backend gate. **ACs:** HOME-01, 02 (API), 04, 11, 15.
**Commit:** `feat(api): expose study summary and continue-reading endpoints`

## Phase B — Home core (frontend)

### T4 — study client + tz header

`app/lib/study.ts` (`clientTimezone`, `getContinueReading`, `getStudyDays`); attach `X-Client-Timezone` in the reading-position and review-submission clients. **ACs:** HOME-09 (client half), client shapes.
**Commit:** `feat(web): add study client and client-timezone header`

### T5 — `/home` page: hero + due card + entry redirects

`(app)/home` route + `home-screen.tsx` with `ContinueHero` (data/empty) and `DueCard` (count / calm done-for-today, I-7); login/register redirect → `/home`; independent fetch failure isolation; full frontend gate. **ACs:** HOME-02 (UI), 03, 05, 06, 17.
**Commit:** `feat(home): two-card home with continue hero and due reviews`

## Phase C — adherence stats (frontend)

### T6 — heatmap + streak + hide-stats

`StudyHeatmap` week-aligned grid (silent grace, chart-token shading), streak line from `studied_last_14`, `use-home-settings.ts` (`learny.home.v1`, default show), stats block below the fold with quiet inline error state; I-7 holds; full frontend gate. **ACs:** HOME-12, 13, 14.
**Commit:** `feat(home): study heatmap and adherence streak with hide toggle`

## Phase D — IA rewire (frontend)

### T7 — nav collapse + bookshelf

Sidebar → Home / Bookshelf / Review / Notes, Library group + its fetch removed, brand → `/home`; `/sources` re-presented as Bookshelf (title + shelf grid), route unchanged; deep links pinned (HOME-19). **ACs:** HOME-16, 18, 19.
**Commit:** `feat(shell): collapse navigation and present the library as a bookshelf`

### T8 — landing face-lift

`app/page.tsx`: identity-styled name, one-line value prop, Log in / Create account CTAs; no marketing sections; full frontend gate. **ACs:** HOME-20.
**Commit:** `feat(landing): minimal identity-styled landing page`

---

## Requirement Coverage

24 ACs (HOME-01..20 + I-1..I-7 sensors folded into tasks above); every HOME id appears in exactly the tasks listed; none unmapped.
