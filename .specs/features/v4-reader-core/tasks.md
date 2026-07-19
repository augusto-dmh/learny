# v4-reader-core Tasks

## Execution Protocol (MANDATORY — do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. If the skill cannot be activated, STOP.

**Design**: `.specs/features/v4-reader-core/design.md`
**Status**: Approved (auto-decision mode per learny-ship-cycle)

---

## Test Coverage Matrix

> Guidelines found: `CLAUDE.md` (citations/eval are core, golden-fixture stance), `.specs/STATE.md` AD-071 (fetchImpl-injected client tests; jsdom `routedFetch` component tests), AD-118 (CSS pins parse committed `globals.css`), `frontend/vitest.config.ts` (node default, per-file `@vitest-environment jsdom`), `.github/workflows/ci.yml` (`uv run pytest -q`, ruff, vitest, tsc, build).

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| --- | --- | --- | --- | --- |
| Pure application logic (partition/locate/percent, findQuoteOffset) | unit | All branches; 1:1 to spec ACs; every listed edge case | `backend/tests/test_reading_pure.py`, `frontend/tests/highlight-paint.test.ts` | `uv run pytest -q tests/test_reading_pure.py` / `npm test -- highlight-paint` |
| Use cases (ReadChapter, SaveReadingPosition, ListSourceHighlights) | unit (fakes) | All branches incl. ownership collapse, resume fallback, alias writes | `backend/tests/test_application_reading.py` | `uv run pytest -q tests/test_application_reading.py` |
| API routes (chapter, reading-position, highlights) | integration (auth_client, DB-gated) | Happy + every edge + error path per route | `backend/tests/test_web_reading.py`, `test_web_notes.py` | `uv run pytest -q tests/test_web_reading.py tests/test_web_notes.py` |
| Migration / schema | integration | Backfill semantics, shape, cascade | `backend/tests/test_migrations.py` | `uv run pytest -q tests/test_migrations.py` |
| Corpus build change (word_count) | unit + golden | Build persists counts; zero-block sections = 0 | `backend/tests/test_application_corpus.py` | `uv run pytest -q tests/test_application_corpus.py` |
| FE API clients | unit (fetchImpl-injected, node env) | Happy + 404 + error mapping per function | `frontend/tests/reading-client.test.ts` | `npm test -- reading-client` |
| FE components/hooks | jsdom (`routedFetch`) | Every AC of the story the component carries; injected observers/timers | `frontend/tests/*.test.tsx` | `npm test -- <file>` |
| CSS tokens/typography pins | unit (parse globals.css) | Changed `.prose-reading` declarations re-pinned w/ fallbacks; new classes pinned | `frontend/tests/theme-tokens.test.ts` (+ existing pin test) | `npm test -- theme-tokens` |
| Views/entities/config | none | — (build gate only) | — | build gate |

## Parallelism Assessment

| Test Type | Parallel-Safe? | Isolation Model | Evidence |
| --- | --- | --- | --- |
| Backend pytest (all) | No (sequential run) | Function-scoped `db_conn` on one engine; offline subset skips DB | `backend/tests/conftest.py:44-78` |
| Frontend vitest | Yes (per-file) | Per-file env, no shared state | `frontend/vitest.config.ts` |

`[P]` below = order-free within the phase (informational; phases execute sequentially by one worker each).

## Gate Check Commands

| Gate Level | When to Use | Command (from repo, not invented) |
| --- | --- | --- |
| Quick (backend) | After a backend task | `cd backend && uv run pytest -q tests/<touched test files>` |
| Quick (frontend) | After a frontend task | `cd frontend && npm test -- <touched test files>` |
| Full backend | Phase A boundary | `cd backend && uv run pytest -q && uv run ruff check` |
| Full frontend | Phase B/C/D boundaries | `cd frontend && npm test && npx tsc --noEmit` |
| Build | Final phase boundary | `cd frontend && npm run build` (backend has no build step) |

---

## Execution Plan

```
Phase A (backend, sequential): A1 → A2 → A3 → A4 → A5 → A6
Phase B (reader flow):         B1 → B2 → B3 → B4
Phase C (controls & nav):      C1 → C2 [P] / C3 [P] → C4
Phase D (highlights + gate):   D1 → D2 → D3
```

## Task Breakdown

### A1: Migration 0011 + metadata (word_count, reading_positions)

**What**: `0011_reader_progress.py` — add `corpus_sections.word_count` (nullable → SQL backfill via `array_length(regexp_split_to_array(trim(markdown),'\s+'),1)` with blank→0 → SET NOT NULL) and create `reading_positions` (PK (user_id, source_id), FKs users/sources ON DELETE CASCADE, anchor TEXT NOT NULL, percent NUMERIC(5,2) NOT NULL, updated_at timestamptz NOT NULL); mirror both in `db/metadata.py`.
**Where**: `backend/migrations/versions/0011_reader_progress.py`, `backend/app/infrastructure/db/metadata.py`
**Depends on**: None · **Reuses**: 0010 house style, NAMING_CONVENTION
**Requirement**: RD-15, RD-16 (schema half), AD-123/124
**Done when**: migration test proves backfilled counts match `len(markdown.split())` on seeded rows (incl. blank→0), table shape + cascade delete asserted; chain applies clean up+down.
**Tests**: integration (`test_migrations.py`) · **Gate**: quick backend
**Commit**: `feat(db): add section word counts and reading positions`

### A2: Word counts at corpus build

**What**: `CorpusSectionRecord.word_count` (`len(markdown.split())` in `BuildCorpus`), persisted by `repositories.replace`.
**Where**: `backend/app/domain/entities.py`, `app/application/corpus.py`, `db/repositories.py`
**Depends on**: A1 · **Reuses**: `_content_hash` per-record computation shape
**Requirement**: RD-14, RD-16
**Done when**: build test asserts persisted per-section counts on a fixture book (non-zero, zero-block section = 0); golden corpus untouched byte-wise except new column.
**Tests**: unit + golden (`test_application_corpus.py`) · **Gate**: quick backend
**Commit**: `feat(ingest): persist per-section word counts at corpus build`

### A3: Pure reading module + entities

**What**: `app/application/reading.py` pure core — `WORDS_PER_MINUTE=220`, `Chapter`, `partition`, `locate` (canonical-first/alias/position-tiebreak mirror of `get_section`), `percent_at` (2dp, zero-total→0); entities `ChapterIndexRow`, `ChapterSection`, `ChapterContent`, `ReadingPosition`.
**Where**: `backend/app/application/reading.py`, `app/domain/entities.py`
**Depends on**: None · **Reuses**: `get_section` matching semantics (repositories.py:492)
**Requirement**: AD-121, RD-16, spec edges (alias, flat book, depth>0 start, single chapter)
**Done when**: unit tests cover every branch: depth-0 boundaries, flat book, book starting at depth>0, alias vs canonical collision, duplicate anchors, zero totals, percent quantization.
**Tests**: unit (`test_reading_pure.py`) · **Gate**: quick backend
**Commit**: `feat(reader): add pure chapter partitioning and progress math`

### A4: Repository read models + upsert

**What**: `CorpusRepository.get_chapter_index` / `get_sections_span` (+ SQL impls); `ReadingPositionRepository` port + PG impl (`INSERT..ON CONFLICT DO UPDATE`); `NoteRepository.anchors_for_source` + `SourceHighlight` entity.
**Where**: `backend/app/domain/ports.py`, `app/domain/entities.py`, `db/repositories.py`
**Depends on**: A1, A3 · **Reuses**: existing flat-read query style
**Requirement**: RD-01 (data), RD-08, RD-12, RD-28 (data)
**Done when**: DB-gated repo tests: index ordering incl. aliases+counts, span ordering, upsert overwrite (last-write-wins), anchors_for_source scoping to (user, source).
**Tests**: integration · **Gate**: quick backend
**Commit**: `feat(db): add chapter index, section span, and reading-position repositories`

### A5: Use cases

**What**: `ReadChapter` (anchor | None resume w/ unresolvable→first-chapter fallback, embeds stored position), `SaveReadingPosition` (locate→404, canonical-anchor store, percent), `ListSourceHighlights` — all `authorized_source`-first.
**Where**: `backend/app/application/reading.py`, `app/application/notes.py` (list use case if house style puts it there)
**Depends on**: A3, A4 · **Reuses**: `ReadSection` template, fakes in `tests/fakes.py`
**Requirement**: RD-01/02/08/09/10/12, RD-28
**Done when**: fake-based tests: ownership collapse (missing = non-owner = 404 path), alias write stores canonical, resume with/without stored row, stale stored anchor falls back leaving row untouched, empty corpus → CorpusNotFound.
**Tests**: unit (`test_application_reading.py`) · **Gate**: quick backend
**Commit**: `feat(reader): add chapter read and reading-position use cases`

### A6: Web routes + views + dependencies

**What**: `GET /api/sources/{id}/chapter` (optional `anchor`) → `ChapterView` (+`reading_position`), `PUT /api/sources/{id}/reading-position` (CSRF/Origin like notes mutations) → `ReadingPositionView`; `GET /api/sources/{id}/highlights` → `list[SourceHighlightView]` in notes router; providers in `dependencies.py`.
**Where**: `backend/app/infrastructure/web/sources.py`, `web/notes.py`, `web/dependencies.py`
**Depends on**: A5 · **Reuses**: `/section` 404 mapping, notes CSRF stack
**Requirement**: RD-01/02/08/09, RD-28
**Done when**: auth_client tests per route: happy, non-owner 404, unknown anchor 404, alias 200, no-anchor resume (with and without stored position), PUT bad anchor 404 + nothing stored, PUT alias stores canonical, highlights owner-scoped. **Phase gate**: full backend suite + ruff — count ≥ current 793 passed, no deletions.
**Tests**: integration (`test_web_reading.py`, `test_web_notes.py`) · **Gate**: full backend
**Commit**: `feat(api): serve chapters, reading positions, and source highlights`

### B1: Frontend reading client

**What**: `lib/reading.ts` — `getChapter` (found/not_found/throw mirror of `sections.ts`), `saveReadingPosition`, `listHighlights`, `minutesLeft` (220 wpm ceil), types per design Data Models.
**Where**: `frontend/app/lib/reading.ts`
**Depends on**: A6 (contract) · **Reuses**: `sections.ts` idiom (AD-071)
**Requirement**: RD-01 (client), RD-07 (client call), RD-28 (client)
**Done when**: fetchImpl-injected tests: URL/encoding (single `encodeURIComponent`), 404 mapping, error throw, PUT body/CSRF header, minutesLeft rounding + zero.
**Tests**: unit (`reading-client.test.ts`) · **Gate**: quick frontend
**Commit**: `feat(reader): add chapter and reading-position API clients`

### B2: ChapterFlow rendering + deep-link scroll

**What**: `ChapterReader` found-state rendering: `.prose-reading` article; per-section `<section id={anchor} data-section-anchor>` + heading + memoized `MessageResponse`; deep-link effect (section scroll + heading-fragment reuse of transient `data-highlight` treatment); capture popover ported (mouseup → containing wrapper → its markdown → `deriveCaptureSelection` unchanged).
**Where**: `frontend/app/components/chapter-reader.tsx` (new)
**Depends on**: B1 · **Reuses**: `section-reader.tsx` fragments/capture wiring, `message.tsx:326`
**Requirement**: RD-03, RD-04
**Done when**: jsdom tests: all sections render in order with anchor ids, `?anchor=` scrolls to wrapper + transient highlight, heading fragment path works, capture selection still resolves against the right section's markdown (ported capture tests green).
**Tests**: jsdom (`chapter-reader.test.tsx`) · **Gate**: quick frontend
**Commit**: `feat(reader): render chapters as one continuous article`

### B3: Load orchestration + page wiring

**What**: Parallel `fetchAuthState()` + `getChapter(id, anchorOrNull)` (no sequential chain), states loading(skeleton)/signed-out/not-found/error/found; `read/page.tsx` renders `ChapterReader`; `section-reader.tsx` deleted; obsolete tests replaced.
**Where**: `chapter-reader.tsx`, `app/(app)/sources/[id]/read/page.tsx`
**Depends on**: B2 · **Reuses**: existing 401→login redirect behavior
**Requirement**: RD-10 (client), RD-26, RD-27
**Done when**: fetch-order test proves both requests dispatched before either resolves; 401 redirects as today; skeleton (not bare text) during load; no-anchor URL renders resumed chapter scrolled to stored anchor.
**Tests**: jsdom · **Gate**: quick frontend
**Commit**: `feat(reader): load auth and chapter in parallel with a reading skeleton`

### B4: Scroll position tracking + progress display

**What**: `useScrollPosition` (injectable IntersectionObserver; topmost visible section; 2s scroll-idle + changed-anchor → fire-and-forget `saveReadingPosition`, silent retry next idle); live book-percent + chapter minutes-left in the top bar area (client math per design).
**Where**: `frontend/app/hooks/use-scroll-position.ts` (or components/ per house style), `chapter-reader.tsx`
**Depends on**: B3
**Requirement**: RD-07, RD-11, RD-13
**Done when**: injected-observer tests: idle debounce (no write storm), no write when anchor unchanged, silent retry after failure, percent/minutes update as observed section changes. **Phase gate**: full frontend (`npm test && npx tsc --noEmit`).
**Tests**: jsdom (fake timers) · **Gate**: full frontend
**Commit**: `feat(reader): track reading position on scroll idle and show progress`

### C1: Reading settings hook + CSS vars

**What**: `useReadingSettings` (versioned `learny.reading.v1` localStorage, clamp invalid, in-memory fallback); `.prose-reading` → `font-size: var(--reading-size, 19px); line-height: var(--reading-leading, 1.6)`; container applies vars + `data-appearance`.
**Where**: `frontend/app/hooks/use-reading-settings.ts`, `globals.css`, `chapter-reader.tsx`
**Depends on**: B3 · **Reuses**: AD-119 paper layer
**Requirement**: RD-18, RD-21 (persistence), RD-06 defaults
**Done when**: hook tests (persist/reload, clamp, storage-throw fallback); pin tests updated to var-with-fallback forms (fallbacks asserted = 19px/1.6); WCAG token test still green.
**Tests**: jsdom + CSS pins · **Gate**: quick frontend
**Commit**: `feat(reader): add device-local reading settings`

### C2: Aa popover [P]

**What**: `reading-controls.tsx` — size 17/19/21/23, spacing 1.5/1.6/1.8, appearance Default/Paper (dark-mode note, control never hidden), theme Light/Dark/System via next-themes; trigger in reader top bar.
**Where**: `frontend/app/components/reading-controls.tsx`, `chapter-reader.tsx`
**Depends on**: C1 · **Reuses**: vendored Popover, `useTheme`
**Requirement**: RD-17, RD-19, RD-20, RD-21 (no-flash apply)
**Done when**: jsdom tests: each control mutates settings/theme; paper sets `data-appearance` on reader container only; dark + paper leaves `.dark` palette authoritative (attribute present, guarded selector inert — assert attribute + class states).
**Tests**: jsdom (`reading-controls.test.tsx`) · **Gate**: quick frontend
**Commit**: `feat(reader): add the reading controls popover`

### C3: TOC panel + position context [P]

**What**: `toc-panel.tsx` — structure via `fetchSourceStructure`+`flattenSections`; current chapter/section marked from scroll state; click → same-chapter smooth scroll or cross-chapter `router.push`, URL always updated; ≥lg persistent, below lg behind top-bar toggle.
**Where**: `frontend/app/components/toc-panel.tsx`, `chapter-reader.tsx`
**Depends on**: B4 (scroll state) · **Reuses**: `tree.ts`, sidebar fetch caching idiom
**Requirement**: RD-22, RD-23, RD-25
**Done when**: jsdom tests: current-position marking follows scroll state; same-chapter click scrolls without refetch; cross-chapter click pushes new anchor; collapsed state toggles.
**Tests**: jsdom (`toc-panel.test.tsx`) · **Gate**: quick frontend
**Commit**: `feat(reader): add an in-reader table of contents with position context`

### C4: Return chip + receding chrome + ink-line

**What**: `ReturnChip` (set on TOC/deep-link jump away from live position; return + dismiss-on-use/scroll-threshold); `useRecedingChrome` (hide top bar scrolling down, show scrolling up, `motion-reduce` safe); `InkLine` (token-only hairline + percent fill, stays when bar recedes).
**Where**: `chapter-reader.tsx`, `frontend/app/hooks/use-receding-chrome.ts`, `globals.css`
**Depends on**: C2, C3 · **Reuses**: Cycle A ink-line rule utilities, identity tokens
**Requirement**: RD-24, RD-30, RD-31
**Done when**: jsdom tests: chip lifecycle (appear/return/dismiss paths); chrome hidden/shown by scroll direction; ink fill width tracks percent; no raw hexes (leak scan green). **Phase gate**: full frontend.
**Tests**: jsdom + CSS pins · **Gate**: full frontend
**Commit**: `feat(reader): add jump-back, receding chrome, and the ink-line progress rule`

### D1: Highlight quote matching (pure)

**What**: `lib/highlight-paint.ts` — `findQuoteOffset(haystack, quote, prefix, suffix)` (unique → offset; multiple → context filter; ambiguous/zero → null).
**Where**: `frontend/app/lib/highlight-paint.ts`
**Depends on**: None (within D) · **Reuses**: quote-with-context semantics (ADR-0026)
**Requirement**: RD-29 (matching half)
**Done when**: unit tests: unique, duplicate-with-context, duplicate-ambiguous→null, absent→null, quote at string edges, empty prefix/suffix.
**Tests**: unit (`highlight-paint.test.ts`) · **Gate**: quick frontend
**Commit**: `feat(reader): add pure highlight quote matching`

### D2: Paint highlights in the flow

**What**: `paintHighlights(sectionEl, highlights)` (TreeWalker offset→node mapping, `<mark class="reader-highlight" data-note-id>`, unwrap-first idempotent); effect in `ChapterFlow` keyed on (markdown, highlights); `listHighlights` fetched with chapter; `.reader-highlight` styles on `--highlight-yellow`; active-only.
**Where**: `highlight-paint.ts`, `chapter-reader.tsx`, `globals.css`
**Depends on**: D1, C4 · **Reuses**: `--highlight-*` tokens (Cycle A)
**Requirement**: RD-28 (client), RD-29
**Done when**: jsdom tests: active anchor paints in its section only; stale/orphaned never paint; cross-node quote paints all slices; unmatched silent; repaint idempotent; selection/copy structure intact (marks only wrap).
**Tests**: jsdom · **Gate**: quick frontend
**Commit**: `feat(reader): render existing highlights inline`

### D3: Full-suite hardening + status docs

**What**: Full gates everywhere; fixture-scale render sanity (largest fixture chapter through `ChapterFlow` in a test — assertion on render completing, RFC assumption check); tasks.md statuses; ROADMAP row stays "Not started" until Stage 2 publish flips it (per prior cycles the row update rides in the PR).
**Where**: repo-wide
**Depends on**: D2
**Requirement**: spec Success Criteria
**Done when**: `cd backend && uv run pytest -q && uv run ruff check` (≥793 passed, no deletions), `cd frontend && npm test && npx tsc --noEmit && npm run build` (≥256 passed + new), traceability table statuses updated.
**Tests**: all · **Gate**: Build
**Commit**: `docs(specs): record the reader core execution` (statuses only; code commits precede)

---

## Diagram-Definition Cross-Check

| Task | Depends On (body) | Diagram | Status |
| --- | --- | --- | --- |
| A1 none · A2 A1 · A3 none · A4 A1,A3 · A5 A3,A4 · A6 A5 | as listed | A1→A2→A3→A4→A5→A6 sequential (A3 could precede A2; kept sequential — same worker) | ✅ consistent (sequential superset of the DAG) |
| B1 A6 · B2 B1 · B3 B2 · B4 B3 | as listed | B1→B2→B3→B4 | ✅ |
| C1 B3 · C2 C1 · C3 B4 · C4 C2,C3 | as listed | C1 → C2 [P] / C3 [P] → C4 | ✅ (C2∥C3: no mutual dep; both precede C4) |
| D1 none · D2 D1,C4 · D3 D2 | as listed | D1→D2→D3 | ✅ |

## Test Co-location Validation

| Task | Layer | Matrix Requires | Task Says | Status |
| --- | --- | --- | --- | --- |
| A1 migration | migration | integration | integration | ✅ |
| A2 build | corpus build | unit+golden | unit+golden | ✅ |
| A3 pure | pure logic | unit | unit | ✅ |
| A4 repos | repository | integration | integration | ✅ |
| A5 use cases | use case | unit (fakes) | unit | ✅ |
| A6 routes | API | integration | integration | ✅ |
| B1 client | FE client | unit | unit | ✅ |
| B2–B4, C1–C4, D2 | FE components/hooks (+CSS pins where styles change) | jsdom (+pins) | jsdom (+pins) | ✅ |
| D1 pure | pure logic | unit | unit | ✅ |
| D3 | gates only | — | all | ✅ |

No task defers its tests; every style-touching task carries its pin updates.

## Task Granularity Check

All tasks are one component/module/endpoint-group with co-located tests; A6 groups the three routes but they share views/deps wiring and one test file pair — cohesive. B2 is the largest (flow + deep-link + capture port) but is one component's render contract; splitting would leave untestable halves (merge-backward rule).
