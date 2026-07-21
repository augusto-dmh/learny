# v4-home-ia Validation

**Date**: 2026-07-21
**Spec**: `.specs/features/v4-home-ia/spec.md`
**Diff range**: `847b5fb..HEAD` (branch `feat/v4-home-ia`; planning `9dcf126` + T1–T8 + two orthogonal test fixes `34b798b`, `c0aa7c4`)
**Verifier**: independent sub-agent (author ≠ verifier; evidence-or-zero)

---

## Task Completion

| Task | Status | Notes |
| ---- | ------ | ----- |
| T1 — study_days schema + repos | ✅ Done | migration `0015`, `StudyDay` entity, `SqlAlchemyStudyDayRepository`, `most_recent_for_user` |
| T2 — activity hooks + local-day | ✅ Done | `local_day`, in-txn rollup in `SubmitReview`/`SaveReadingPosition`, tz header pass-through |
| T3 — study + continue endpoints | ✅ Done | `GetStudySummary`, `ContinueReading`, `web/study.py`, registered in `main.py` |
| T4 — study client + tz header | ✅ Done | `app/lib/study.ts`; tz header attached in reading/quiz writers |
| T5 — /home hero + due card + redirects | ✅ Done | `home-screen.tsx`, `(app)/home`, login/register → /home |
| T6 — heatmap + streak + hide | ✅ Done | `study-heatmap.tsx`, `use-home-settings.ts` |
| T7 — nav collapse + bookshelf | ✅ Done | `app-sidebar.tsx` (4 items), `/sources` re-presented |
| T8 — landing face-lift | ✅ Done | `app/page.tsx` identity-styled |

---

## Spec-Anchored Acceptance Criteria

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| HOME-01 continue returns most-recent position w/ fields | `source_id, source_title, chapter_title, percent, updated_at` for the latest position | `backend/tests/test_web_study.py:283-297` — `body` key set == those 5 fields; `chapter_title=="Chapter 0"`, `percent==30.0`, `updated_at==when`; repo `test_repositories_reading.py` most_recent join | ✅ PASS |
| HOME-02 no positions → null 200 + empty hero | 200 `null`; hero pick-a-book links bookshelf | `test_web_study.py:305` `resp.json() is None`; `frontend/tests/home-screen.test.tsx:106-108` Pick-a-book href `/sources` | ✅ PASS |
| HOME-03 hero shows title/chapter/percent; resume → reader | `/sources/{id}/read` (no anchor) | `home-screen.test.tsx:83-92` hero-title/chapter/percent + Resume href `/sources/s1/read` | ✅ PASS |
| HOME-04 other user's source never returned (SQL-scoped) | never returned | `test_web_study.py:326-327` caller's source only; `test_repositories_reading.py` `..never_returns_another_users_position`; sensor M4 | ✅ PASS |
| HOME-05 due>0 → count + review CTA | count shown, CTA → `/review` | `home-screen.test.tsx:127-130` due-count contains 5, Review href `/review` | ✅ PASS |
| HOME-06 due==0 → calm done-for-today | no celebration/badge/popup | `home-screen.test.tsx:144-149` due-done present; no count/CTA/`role=status` | ✅ PASS |
| HOME-07 review → +reviews_count, same txn | `reviews_count += 1` in review-log txn | `test_application_reviews.py:...same_transaction` (day,1,0); `test_web_quiz.py:...credits_a_study_day` `[(1,0)]`; sensors M1/M4 | ✅ PASS |
| HOME-08 position save → +reading_updates, same txn | `reading_updates += 1` | `test_application_reading.py:...credits_a_reading_study_day` `record_calls==[(user,date(2026,7,19),0,1)]`; `test_web_reading.py:...credits_a_reading_study_day` `[(0,1)]` | ✅ PASS |
| HOME-09 valid tz → local date; absent/invalid → UTC, never error | UTC fallback, no 4xx/5xx | `test_study_pure.py:17-56` (7 cases); `test_web_quiz.py:...garbage_timezone` 200 + UTC day; `test_web_reading.py:...garbage_timezone`; sensor M3 | ✅ PASS |
| HOME-10 N same-day events → 1 row, counters=totals (incl concurrent) | one row, exact totals | `test_repositories_study.py:55-69` `(2,1)`; `:137-171` concurrent `(2,0)`; sensor M1 | ✅ PASS |
| HOME-11 study/days window + studied_last_14; default 84, 7..365 else 422 | window rows to local today + count; 422 out of bounds | `test_web_study.py:158-187` rows+count; `:190-196` `[6,0,366,400]→422`; `:199-205` `[7,84,365]→200`; `test_application_study.py:112-124` tz today; sensor M2 | ✅ PASS |
| HOME-12 streak line from endpoint value; no stored/consecutive streak | "Studied X of the last 14 days" verbatim | `study-heatmap.test.tsx:116-118` renders "Studied 9…" from server (rows would give 1); `test_application_study.py:95-109` adherence independent of window=7 | ✅ PASS |
| HOME-13 week-aligned grid; zero-days plain; active shaded | grid, empty cells level 0, shaded by count | `study-heatmap.test.tsx:76-86` 84 cells, data-level 2/1; `:93-95` empty day level 0, title null; sensor M5. Visual geometry = sensor-blind (jsdom) | ✅ PASS |
| HOME-14 hide toggle persists localStorage; default visible | hidden after toggle, survives reload, default shown | `study-heatmap.test.tsx:143-170` default visible → hide → `localStorage {showStats:false}` → remount stays hidden; sensor M6 | ✅ PASS |
| HOME-15 other user's study days never appear | never returned | `test_web_study.py:208-225`; `test_repositories_study.py:109-122` scoped in SQL; sensor M4 (window) | ✅ PASS |
| HOME-16 sidebar exactly 4 items; Library group gone; brand → /home | Home/Bookshelf/Review/Notes in order, nothing else | `app-sidebar.test.tsx:62-71` labels `==["Home","Bookshelf","Review","Notes"]`; `:74-80` brand `/home`; `:82-86` no Library; sensor M7 | ✅ PASS |
| HOME-17 login/register → /home | `router.push("/home")` | `home-redirects.test.tsx:50,65` `push` called with `/home` | ✅ PASS |
| HOME-18 /sources presents as bookshelf; route unchanged | title reads bookshelf, shelf of tiles | `bookshelf-page.test.tsx:72-73` heading "Your bookshelf"; `:88-89` shelf tile "Iron Gall" | ✅ PASS |
| HOME-19 deep links intact; /account from header not sidebar | routes keep working; account off sidebar | Sidebar-absence tested (4-item exactness, HOME-16); deep-link preservation carried by unchanged routes + green regression suite (citation-reader-loop, chapter-reader, route-redirects, notes). No direct assertion of "/account reachable from header" in the diff surface | ⚠️ Spec-precision gap (see below) |
| HOME-20 landing: name, value prop, both CTAs, identity tokens, no marketing | name + one-liner + Log in / Create account | `landing.test.tsx:24-29` name "Learny" + value prop; `:35-36` Create account→`/register`; `:43-44` Log in→`/login`. Iron Gall tokens + light/dark = sensor-blind | ✅ PASS |

### Invariants

| Inv | Outcome | Evidence | Result |
| --- | --- | --- | --- |
| I-1 review+credit atomic | failed credit rolls back review | `test_application_reviews.py:...rolls_back_the_review_when_the_study_credit_fails` — `_FailingStudyDayRepository` → 0 review-log rows, 0 study-day rows | ✅ PASS |
| I-2 N same-day → 1 row incl concurrent | `test_repositories_study.py:137-171` concurrent `(2,0)`; sensor M1 | ✅ PASS |
| I-3 bad/absent tz → UTC, never error | `test_study_pure.py`; sensor M3 | ✅ PASS |
| I-4 nothing derived stored; recomputed | `test_web_study.py:237-259` two reads identical, row count unchanged; `study-heatmap.test.tsx:105-118` streak from server value | ✅ PASS |
| I-5 reads user-scoped in SQL | window + most_recent scoping tests; sensors M4 | ✅ PASS |
| I-6 response byte-identical w/o header | `test_web_reading.py:...body_is_unchanged_by_the_timezone_header`; `test_web_quiz.py:...credits_a_study_day` asserts SchedulingView key set unchanged | ✅ PASS |
| I-7 no gamification affordance in new surfaces | `home-screen.test.tsx:147-149` no `role=status`; `study-heatmap.test.tsx:96-101` no warning text/status/alert | ✅ PASS (absence-asserted; scoped to the two new surfaces) |

**Status**: ✅ 20/20 HOME ACs + 7/7 invariants covered; 1 spec-precision gap flagged (HOME-19, non-blocking).

---

## Discrimination Sensor

Scratch-state fault injection (Edit → run covering file → `git checkout --` restore). Tree restored byte-identical. Expanded pass (7 mutations) for the risk core.

| # | File:line | Description | Killed? |
| - | --------- | ----------- | ------- |
| M1 | `repositories.py` `SqlAlchemyStudyDayRepository.record` | Drop the `+` in ON CONFLICT set → overwrite instead of increment | ✅ Killed — `test_repositories_study.py` `same_day_events_sum` (`1 != 2`) + concurrency test |
| M2 | `application/study.py:66` | `_ADHERENCE_WINDOW_DAYS - 1` → `_ADHERENCE_WINDOW_DAYS` (15-day window) | ✅ Killed — `test_application_study.py` `studied_last_14_excludes_days_older_than_14` (`3 != 2`) |
| M3 | `application/study.py:39` | `if tz_name:` → `if not tz_name:` (invert tz gate) | ✅ Killed — `test_study_pure.py` valid-zone + none-fallback (3 fail) |
| M4 | `repositories.py` `most_recent_for_user` | `user_id == user_id` → `!= user_id` (break user scoping) | ✅ Killed — `test_web_study.py` continue tests + `test_repositories_reading.py` (6 fail) |
| M5 | `study-heatmap.tsx:106` | densify loop `< HEATMAP_WINDOW_DAYS` → `- 1` (83 cells) | ✅ Killed — `study-heatmap.test.tsx` cell-count 84 (2 fail) |
| M6 | `use-home-settings.ts:27` | `HOME_DEFAULTS.showStats true` → `false` | ✅ Killed — `use-home-settings.test.tsx` + `study-heatmap.test.tsx` default-visible (7 fail) |
| M7 | `app-sidebar.tsx` `NAV_ITEMS` | Remove the Notes item (3-item nav) | ✅ Killed — `app-sidebar.test.tsx` exact-order + count (2 fail) |

**Sensor depth**: P0-full (7 mutations, ≥5 required) — covers upsert increment, tz fallback, adherence window arithmetic, user-scoping, heatmap densify, hide-stats default, nav exactness.
**Result**: 7/7 killed — PASS ✅

---

## Code Quality

| Principle | Status |
| --- | --- |
| Minimum code (no scope creep) | ✅ additive; existing bodies untouched (I-6) |
| Surgical changes / only-required files | ✅ |
| Matches patterns/style | ✅ mirrors `use-reading-settings`, existing repo/router idioms |
| Spec-anchored outcome check (asserted values match spec) | ✅ (1 spec-precision note, HOME-19) |
| Per-layer coverage (domain 1:1 ACs; routes happy+edge+error) | ✅ pure/unit/integration/route layers all present |
| Every test maps to a spec requirement — no unclaimed tests | ✅ |
| Documented guidelines followed | ✅ CLAUDE.md, CI gate commands; ADR-007/009 framework-free core respected |

Notable: `study.py`↔`reading.py` cycle broken with a documented lazy import inside `_chapter_title` — pragmatic, in-code rationale present.

---

## Edge Cases

- [x] Brand-new user: null hero + done-for-today + all-empty heatmap + "Studied 0…" — `home-screen.test.tsx:214-232`, `study-heatmap.test.tsx:122-139`, `test_application_study.py:127-135`
- [x] Garbage `X-Client-Timezone` → UTC, no 4xx/5xx — `test_study_pure.py`, `test_web_quiz.py`, `test_web_reading.py`
- [x] Deleted most-recent source → next or empty (cascade) — `test_repositories_reading.py:...falls_back_when_top_source_deleted`
- [x] Concurrent same-day commits → no unique violation, counters total — `test_repositories_study.py:137-171`
- [x] `window=6` / `window=400` → 422 — `test_web_study.py:190-196`
- [x] Independent fetch isolation (hero/due/stats) — `home-screen.test.tsx:153-212`

---

## Gate Check

- **Backend**: `cd backend && uv run pytest -q && uv run ruff check`
  - Result: **1580 passed, 10 skipped**, ruff **All checks passed**. (Expected baseline 1579 → +1; the 10 skips are the standing live-provider/docling/replay skips, all justified.)
- **Frontend**: `cd frontend && npx vitest run && npx tsc --noEmit && npm run build`
  - Result: **530 passed / 57 test files**; tsc exit 0; `next build` 11/11 pages (incl. `/home`). (Expected 56 files → +1 file; test count matches.)
- **Test-count delta vs v3-F baseline** (backend 1522 / frontend 494): +58 backend, +36 frontend. No tests removed except surfaces deleted with their feature (sidebar section-tree, sources sidebar stub) — justified in tasks.md, anchor contract preserved elsewhere.

---

## Spec-Precision / Coverage Notes (non-blocking)

1. **HOME-19 — "/account remains reachable from the header"** has no direct positive assertion in the diff surface. The sidebar-exclusion half is proven (4-item exactness); deep-link preservation rides on unchanged routes + the green regression suite. `auth-header.tsx` (the account link) is pre-existing and untouched. Recommend (optional) a one-line assertion that the header still exposes the account/logout link, so the "reachable from header" clause is pinned rather than inferred.
2. **HOME-13 / HOME-20 visual layers** (week-grid geometry, exact chart-token colors, Iron Gall light/dark) are jsdom sensor-blind — author-documented; structure + `data-level` asserted as proxy. Needs a human eye for pixel/color, not an automated gap.
3. **I-7** is proven by absence-assertions scoped to the two new surfaces (home-screen, study-heatmap); adequate for the diff, but inherently a negative invariant.

None change the verdict.

---

## Requirement Traceability Update

| Requirement | New Status |
| --- | --- |
| HOME-01..18, 20 | ✅ Verified |
| HOME-19 | ✅ Verified (⚠️ header-reachability inferred, not directly asserted) |
| I-1..I-7 | ✅ Verified |

---

## Summary

**Overall**: ✅ Ready

**Spec-anchored check**: 20/20 HOME ACs + 7/7 invariants covered; 1 spec-precision gap flagged (HOME-19, non-blocking)
**Sensor**: 7/7 mutations killed (P0-full)
**Gate**: backend 1580 passed / 10 skipped + ruff clean; frontend 530 passed / 57 files + tsc + build (11 pages)

**What works**: full study-days rollup (atomic in-txn upsert-increment, tz-aware day boundary with silent UTC fallback, concurrency-safe), read-time adherence (`studied_last_14`, nothing stored), user-scoped continue + study reads, two-card Home, week-aligned heatmap with silent grace, device-local hide toggle, four-item nav, bookshelf re-presentation, identity landing, entry redirects.

**Issues found**: none blocking. HOME-19 header-reachability is inferred rather than directly asserted — optional one-line test would close it.

**Next steps**: PASS — clear to proceed. Optionally add the HOME-19 header assertion.
