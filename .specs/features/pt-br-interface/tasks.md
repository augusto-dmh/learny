# pt-br-interface Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. If the skill cannot be activated, STOP and tell the user.

**Design**: `.specs/features/pt-br-interface/design.md`
**Status**: Approved (auto-decided, ship-cycle) — not started

---

## Test Coverage Matrix

> Generated from codebase + guidelines. Guidelines found: `CLAUDE.md` (verification vocabulary, `make infra` prerequisite, `jq` absent), root `Makefile` (`lint`/`check` targets), `backend/pyproject.toml` (pytest markers), `frontend/vitest.config.ts` (node default, per-file jsdom docblock), `backend/scripts/check_boundaries.py`, `backend/tests/test_readme_truth.py`.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
|---|---|---|---|---|
| Backend domain (`locale.py`) | unit | All branches; 1:1 to I18N-01/04/08 negotiation + effective-locale + response-language ACs; malformed/absent/`q=0` headers | `backend/tests/test_locale.py` | `cd backend && uv run pytest tests/test_locale.py` |
| Backend repository + migration | integration (db) | upsert/get/delete, cascade on user delete, unknown stored value reads as unset; migration up/down single head | `backend/tests/test_locale_preference_repository.py`, `test_migrations.py` | `cd backend && uv run pytest tests/<file>` (after `make infra`) |
| Backend web (`/me/locale`, `/me`) | integration (TestClient) | PUT happy/422/401/403, DELETE idempotent 204, `/me` carries `locale`, ownership isolation | `backend/tests/test_web_locale.py` | `cd backend && uv run pytest tests/test_web_locale.py` |
| Backend adapters (Anthropic/compat/local/routing) + application | unit (fake client) | Request built with/without language; system block byte-identical; user-turn note position; `en` adds nothing; sentinel unchanged; use case threads the kwarg; router derives effective locale from stored + header | `backend/tests/test_answering_*.py`, `test_conversations*.py`, `test_web_conversations.py` | `cd backend && uv run pytest tests/<files>` |
| Backend golden (Portuguese) | integration (db) + pure | Ingestion structure + `search_config=portuguese`; retrieval top-3 for inflected terms; citations ⊆ evidence | `backend/tests/test_golden_*.py`, `golden_pt_corpus.py` | `cd backend && uv run pytest tests/test_golden_*.py` |
| Frontend i18n core (`i18n/*`, `lib/locale.ts`, `lib/errors.ts`) | unit (node) | Every negotiation vector incl. cookie precedence/invalid/`q`/malformed; error mapping status-first then operation; cookie writer attributes | `frontend/tests/i18n-*.test.ts`, `errors.test.ts` | `cd frontend && npx vitest run tests/<file>` |
| Frontend components (screens, Account, switcher, sync) | unit (jsdom) | Each migrated surface family renders in `pt-BR` (key landmarks, a plural) and `en` (unchanged copy); selector save/failure/Automatic; sync reconcile; no unsent-input loss on refresh | `frontend/tests/*.test.tsx` | `cd frontend && npx vitest run tests/<file>` |
| Frontend sensors | unit (node) | Parity + hard-coded sensors each fail on a deliberate break (shown, then reverted); ratchet fails on stale entries | `frontend/tests/i18n-parity.test.ts`, `i18n-hardcoded.test.ts` | `cd frontend && npx vitest run tests/i18n-*.test.ts` |
| Config / docs / catalogs | none | build gate only (`tsc`, `next build`, drift tests) | — | `make lint` |

Baselines: record `uv run pytest --collect-only -q | tail -1` and `npm test` totals at each phase start; counts must not silently drop.

## Parallelism Assessment

| Test Type | Parallel-Safe? | Isolation Model | Evidence |
|---|---|---|---|
| Backend pytest | No (one invocation, shared DB) | Shared DB fixtures | `Makefile` `test-backend`; CLAUDE.md |
| Frontend vitest | Yes | Per-file jsdom, hand-rolled fetch stubs | `vitest.config.ts` |

Execution is sequential, one worker per phase.

## Gate Check Commands

| Gate Level | When to Use | Command |
|---|---|---|
| Quick (backend) | Per task | `cd backend && uv run pytest tests/<affected files>` |
| Quick (frontend) | Per task | `cd frontend && npx vitest run tests/<affected files>` plus `npx tsc --noEmit` |
| Full | Phase boundary | `make test-backend` and/or `make test-frontend` (`make infra` first for backend) |
| Build | Phase boundary + before push | `make lint` (ruff + format check + tsc + boundaries); `cd frontend && npm run build` for phases touching layout/config |

---

## Execution Plan

Phases are ordered and run sequentially; tasks within a phase run in order. Phase 1 is independent of Phase 2 in content (ordering only).

```
Phase 1 (backend preference):      T1 → T2 → T3
Phase 2 (frontend foundation):     T4 → T5 → T6 → T7
Phase 3 (shared client plumbing):  T8 → T9 → T10
Phase 4 (surface migration):       T11 → T12 → T13 → T14 → T15 → T16 → T17
Phase 5 (AI output language):      T18 → T19
Phase 6 (fixture and closing):     T20 → T21
```

6 phases → one Opus worker per phase, sequential; fresh Opus Verifier after T21. The ratchet sensor (T7) keeps every commit green while surfaces migrate; each Phase 4 task removes its files from `PENDING_FILES`, and T17 leaves it empty. Cross-phase prerequisites (content, not ordering): T10 needs T3 (API); T18 needs T1; T19 needs T3; T20 needs T2; T21 needs T17, T19 and T20. A split point for the PR exists after Phase 4 (AD-373).
---

## Task Breakdown

## Phase 1: Backend preference

### T1: Backend locale rules

**What**: Pure `domain/locale.py`: `SUPPORTED_LOCALES`, `negotiate_locale`, `effective_locale`, `response_language_for`.
**Where**: `backend/app/domain/locale.py`, `backend/tests/test_locale.py`
**Depends on**: None
**Reuses**: `application/language.py` style (pure module)
**Requirement**: I18N-01, I18N-08

**Tools**: MCP: NONE · Skill: NONE

**Done when**:

- [ ] `negotiate_locale`: `pt`/`pt-*` before any `en` → `pt-BR`; `q` honored (`q=0` ignored); absent/malformed → `en`
- [ ] `effective_locale(stored, accept)`: supported stored wins, unsupported stored treated as unset, else negotiated
- [ ] `response_language_for("en") is None`, `("pt-BR") == "pt-BR"`
- [ ] Same vectors as the frontend `negotiateLocale` tests (shared table in the test docstring)
- [ ] Quick gate passes; boundaries check clean (domain imports nothing from infra)

**Tests**: unit
**Gate**: quick

**Commit**: `feat(domain): add locale negotiation and response-language rules`

---

### T2: Locale preference persistence

**What**: Entity, port, table, migration `0030_user_locale_preferences`, SQLAlchemy repository, in-memory fake.
**Where**: `backend/app/infrastructure/db/repositories.py` (plus `domain/entities.py`, `domain/ports.py`, `db/metadata.py`, migration, `tests/fakes.py`)
**Depends on**: T1
**Reuses**: `SqlAlchemyAiPreferenceRepository` (`repositories.py:162`), `0029_user_ai_preferences.py`
**Requirement**: I18N-04

**Tools**: MCP: NONE · Skill: `fastapi`

**Done when**:

- [ ] `LocalePreferenceRepository.get_by_user/upsert/delete -> bool`; upsert is ON CONFLICT on `user_id`
- [ ] Migration creates the table with FK cascade; down-migration drops it; single alembic head
- [ ] Repository tests: round-trip, overwrite, delete idempotent, cascade when the user row is deleted, unknown stored value read through the entity as-is (the web layer treats it as unset)
- [ ] `test_migrations.py` updated; full backend gate passes (`make infra` first)

**Tests**: integration
**Gate**: full

**Commit**: `feat(db): store a per-user locale preference`

---

### T3: Locale preference API and `/me` field

**What**: `PUT`/`DELETE /api/me/locale` and `locale` on `GET /api/me`.
**Where**: `backend/app/infrastructure/web/locale.py` (plus `web/auth.py` `MeResponse`, `web/dependencies.py`, app router wiring)
**Depends on**: T2
**Reuses**: `web/ai.py` (`enforce_csrf`, dependency trio), `MeResponse.ai_profile_id`
**Requirement**: I18N-04

**Tools**: MCP: NONE · Skill: `fastapi`

**Done when**:

- [ ] PUT 200 returns `{locale}` and persists; 422 for a value outside `{en, pt-BR}` and nothing stored; 401 unauthenticated; 403 without CSRF
- [ ] DELETE returns 204 and is idempotent
- [ ] `GET /api/me` returns `locale` (`null` when unset or stored value unsupported)
- [ ] Learners cannot read or change each other's preference (ownership test)
- [ ] OpenAPI response models present; full backend gate and `make lint` pass

**Tests**: integration
**Gate**: full

**Commit**: `feat(api): let a learner choose their interface language`

---

## Phase 2: Frontend foundation

### T4: next-intl foundation

**What**: Install `next-intl`, `i18n/config.ts` + `i18n/request.ts`, plugin in `next.config.ts`, typed `global.d.ts`, `messages/{en,pt-BR}.json` seeded with `meta`, `common`, `errors`, async root layout (`<html lang>`, `NextIntlClientProvider`, translated metadata), Vitest `setupFiles` binding.
**Where**: `frontend/i18n/config.ts` (plus `request.ts`, `next.config.ts`, `global.d.ts`, `messages/*`, `app/layout.tsx`, `tests/setup-intl.ts`, `vitest.config.ts`, `package.json`/lock)
**Depends on**: None
**Reuses**: `app/layout.tsx` fonts/theme wiring
**Requirement**: I18N-01, I18N-02

**Tools**: MCP: NONE · Skill: `vercel-react-best-practices`

**Done when**:

- [ ] `resolveLocale`/`negotiateLocale`/`isLocale` unit-tested with the T1 vector table (cookie precedence, invalid cookie ignored, `q`, malformed, `pt-PT`→`pt-BR`)
- [ ] `<html lang>` follows the locale; a layout test renders the real provider for `pt-BR` and `en` and asserts `lang`, title and one translated string
- [ ] The Vitest setup makes existing component tests render the `en` catalog with real ICU; `setTestLocale("pt-BR")` works
- [ ] Adding a third locale needs a catalog file + one `LOCALES` entry (asserted by a test over `LOCALES` ↔ `messages/*.json`)
- [ ] `npx vitest run` (full frontend), `tsc --noEmit` and `npm run build` pass (standalone output intact; `prod-image.test.ts` still green)

**Tests**: unit
**Gate**: build

**Commit**: `feat(web): add next-intl with cookie and Accept-Language locale negotiation`

---

### T5: ADR-0032 and README count

**What**: Record the decision (library, no-prefix routing, preference slice, cookie cache, sensor limits) and keep the README drift test green.
**Where**: `docs/adr/0032-ui-internationalization.md` (plus `README.md` ADR count)
**Depends on**: T4
**Reuses**: `create-adr` skill, ADR-0020 format
**Requirement**: I18N-01, I18N-07

**Tools**: MCP: NONE · Skill: `create-adr`

**Done when**:

- [ ] ADR states context, decision, alternatives (prefix routing, i18next, hand-rolled), consequences (dynamic rendering, full-catalog client payload), the hard-coded-string heuristic limits, and the answer-language rule
- [ ] README ADR count bumped to 32; `test_readme_truth` passes
- [ ] Doc gate: `make lint` passes

**Tests**: none
**Gate**: build

**Commit**: `docs(adr): record the interface-language decision`

---

### T6: Catalog parity sensor

**What**: Test that fails when `en` and `pt-BR` differ in keys or ICU argument names.
**Where**: `frontend/tests/i18n-parity.test.ts`
**Depends on**: T5
**Reuses**: `messages/*.json`
**Requirement**: I18N-06

**Tools**: MCP: NONE · Skill: NONE

**Done when**:

- [ ] Flattened key sets compared both directions; message names key + missing locale
- [ ] ICU argument names (plain, `plural`, `select`) compared per key
- [ ] Deliberate break shown failing for each rule (missing key in `pt-BR`, extra key in `pt-BR`, renamed argument), output pasted in the task report, then reverted
- [ ] Quick gate passes

**Tests**: unit
**Gate**: quick

**Commit**: `test(web): fail when the interface catalogs drift apart`

---

### T7: Hard-coded-string sensor with ratchet

**What**: TypeScript-AST scan of JSX text, user-facing attribute literals, and `new Error("…")`/`new ApiError("…")` in `app/lib`, with allowlist and `PENDING_FILES` ratchet seeded with every unmigrated file.
**Where**: `frontend/tests/i18n-hardcoded.test.ts`
**Depends on**: T6
**Reuses**: `typescript` devDependency
**Requirement**: I18N-07

**Tools**: MCP: NONE · Skill: NONE

**Done when**:

- [ ] Header documents scope and limits exactly as in `context.md` D-7
- [ ] Legal pages excluded by path; `dev/evals` allowlisted with a reason; non-copy tokens allowlisted
- [ ] Ratchet fails when a listed file is already clean (stale) and when an unlisted file has a finding
- [ ] Deliberate break shown failing (`<p>Hello there</p>` in a translated component; a `new Error("Could not …")` in a lib file), output pasted in the task report, then reverted
- [ ] Quick gate passes with all unmigrated files listed

**Tests**: unit
**Gate**: quick

**Commit**: `test(web): flag English strings that bypass the catalog`

---

## Phase 3: Shared client plumbing

### T8: API errors from the catalog (auth, sources, ingestion, sections, profiles)

**What**: `lib/errors.ts` (`ApiError`, `toApiError`), `useErrorMessage`, catalog `errors.*`, convert the first five lib clients and their display sites.
**Where**: `frontend/app/lib/errors.ts` (plus `components/use-error-message.ts`, `lib/auth.ts`, `sources.ts`, `ingestion.ts`, `sections.ts`, `ai-profiles.ts`, consumers' error rendering, `messages/*`, existing client tests)
**Depends on**: T7
**Reuses**: `toAiProfileError`/`AiProfileRequestError` shape, existing `.status` consumers
**Requirement**: I18N-03

**Tools**: MCP: NONE · Skill: NONE

**Done when**:

- [ ] `ApiError{operation,status,detail}`; legacy typed errors extend it so `instanceof`/`status` consumers still work
- [ ] `useErrorMessage`: 401/429/5xx status copy first, then `errors.operation.<op>`, then generic; backend `detail` never rendered (test: a 500 with an English `detail` shows the localized status copy in `pt-BR`)
- [ ] Converted libs contain no English literals; their files leave `PENDING_FILES`
- [ ] Existing client/component tests updated to the catalog copy (`en` text equals today's fallback where the operation matches)
- [ ] Quick gate (affected files + `tsc`) passes

**Tests**: unit
**Gate**: quick

**Commit**: `refactor(web): render request errors from the interface catalog`

---

### T9: API errors from the catalog (quiz, study, reading, notes, conversations, streaming)

**What**: Convert the remaining six lib clients and their display sites to `ApiError` + `useErrorMessage`.
**Where**: `frontend/app/lib/quiz.ts` (plus `study.ts`, `reading.ts`, `notes.ts`, `conversations.ts`, `streaming.ts`, `cards.ts`, consumers, `messages/*`, tests)
**Depends on**: T8
**Reuses**: T8 plumbing; `NoteError` kinds, `StreamRequestError`
**Requirement**: I18N-03

**Tools**: MCP: NONE · Skill: NONE

**Done when**:

- [ ] Same contract as T8 for every remaining client; `NoteError` kinds and `StreamRequestError.status` behavior preserved
- [ ] No `new Error("…")` English literal remains in `app/lib`; those files leave `PENDING_FILES`
- [ ] Quick gate (affected files + `tsc`) passes; full frontend suite passes at phase boundary

**Tests**: unit
**Gate**: full

**Commit**: `refactor(web): finish catalog-backed request errors`

---

### T10: Locale choice, switcher and cookie sync

**What**: `lib/locale.ts` (cookie writer, PUT/DELETE client), `AuthState.user.locale`, anonymous `LocaleSwitcher`, `useLocaleSync`, Account "Language" selector, and the full `AccountPanel` string migration.
**Where**: `frontend/app/components/AccountPanel.tsx` (plus `app/lib/locale.ts`, `app/lib/auth.ts`, `components/locale-switcher.tsx`, `components/use-locale-sync.ts`, `app/(app)/layout.tsx` mount, `messages/*`, tests)
**Depends on**: T9
**Reuses**: `account-ai-profile.test.tsx` fetch stubs, confirm-then-move pattern in `handleChooseProfile`
**Requirement**: I18N-04, I18N-05

**Tools**: MCP: NONE · Skill: NONE

**Done when**:

- [ ] Selecting a locale PUTs with CSRF, writes the cookie only after success, calls `router.refresh()`; failure keeps the old locale and shows a localized Account error
- [ ] "Automatic" DELETEs and clears the cookie to negotiation
- [ ] Sync: `/api/me` `locale` ≠ cookie → cookie rewritten (stored wins) and one refresh; equal or null → no refresh; `/api/me` failure → no-op
- [ ] Anonymous switcher sets the cookie (`path=/`, 1 year, `SameSite=Lax`) without any API call
- [ ] Unsent Chat input survives the refresh (state-preservation test on a stub)
- [ ] `AccountPanel`, `locale-switcher` leave `PENDING_FILES`; quick gate passes

**Tests**: unit
**Gate**: quick

**Commit**: `feat(web): choose the interface language in Account and keep it in sync`

---

## Phase 4: Surface migration

### T11: Landing, auth and legal wrappers

**What**: Migrate landing, login, register, forgot/reset/verify screens, `AuthForm`, auth layout and not-found copy; wrap legal pages in `lang="en"`; mount the anonymous switcher on landing/auth.
**Where**: `frontend/app/page.tsx` (plus `app/components/AuthForm.tsx`, `app/(auth)/**`, `app/(app)/layout.tsx` meta, `components/not-found-notice.tsx`, `app/{terms,privacy,copyright}/page.tsx` wrappers, `messages/*`, tests)
**Depends on**: T10
**Reuses**: `landing.test.tsx`, `auth-screens.test.tsx`, `legal-pages.test.tsx`
**Requirement**: I18N-02

**Tools**: MCP: NONE · Skill: NONE

**Done when**:

- [ ] Every landing/auth string from the catalog; `pt-BR` render test per screen; `en` copy unchanged
- [ ] Legal pages stay English with `lang="en"` on the wrapper (test)
- [ ] Migrated files leave `PENDING_FILES`; parity + hard-coded sensors green; quick gate passes

**Tests**: unit
**Gate**: quick

**Commit**: `feat(web): translate landing and sign-in`

---

### T12: App shell and vendored primitives

**What**: Migrate sidebar, header, theme toggle, nav-pending, shortcuts help, and the English defaults in vendored `components/ui` / `ai-elements` that render to learners.
**Where**: `frontend/app/components/shell/app-sidebar.tsx` (plus `shell/auth-header.tsx`, `nav-pending.tsx`, `use-key-shortcuts.ts`, `components/ui/*`, `components/ai-elements/*`, `messages/*`, tests)
**Depends on**: T11
**Reuses**: `app-shell.test.tsx`, `app-sidebar.test.tsx`
**Requirement**: I18N-02

**Tools**: MCP: NONE · Skill: NONE

**Done when**:

- [ ] Shell and vendored default copy (e.g. sr-only "Close", "Toggle Sidebar") come from the catalog via props/defaults supplied at call sites
- [ ] `pt-BR` shell render test; migrated files leave `PENDING_FILES`; sensors green; quick gate passes

**Tests**: unit
**Gate**: quick

**Commit**: `feat(web): translate the app shell`

---

### T13: Home and Library

**What**: Migrate Home, Library, ingestion status/polling copy and the source list states (empty/error/loading), with locale-aware dates, counts and plurals.
**Where**: `frontend/app/components/library-screen.tsx` (plus `home-screen.tsx`, `use-home-settings.ts`, `use-ingestion-polling.ts`, `app/lib/status.ts`, route pages, `messages/*`, tests)
**Depends on**: T12
**Reuses**: `home-screen.test.tsx`, `library-screen.test.tsx`
**Requirement**: I18N-02

**Tools**: MCP: NONE · Skill: NONE

**Done when**:

- [ ] All strings from the catalog; ICU plurals for counts ("1 livro" / "2 livros"); dates/times via formatters
- [ ] `pt-BR` render tests incl. one plural and one date; `en` copy unchanged
- [ ] Migrated files leave `PENDING_FILES`; sensors green; quick gate passes

**Tests**: unit
**Gate**: quick

**Commit**: `feat(web): translate Home and Library`

---

### T14: Reader chrome

**What**: Migrate the reader, table of contents, reading controls, margin rail, chapter markdown notices and reading shortcuts.
**Where**: `frontend/app/components/chapter-reader.tsx` (plus `reader-panel.tsx`, `toc-panel.tsx`, `reading-controls.tsx`, `margin-rail.tsx`, `chapter-markdown.tsx`, `use-reading-settings.ts`, `use-section-progress.ts`, `app/(read)/**`, `messages/*`, tests)
**Depends on**: T13
**Reuses**: `chapter-reader.test.tsx`, `reader-chrome.test.tsx`, `reading-controls.test.tsx`
**Requirement**: I18N-02

**Tools**: MCP: NONE · Skill: NONE

**Done when**:

- [ ] Reader chrome strings, aria labels and progress text from the catalog; book text and section titles untouched
- [ ] `pt-BR` render tests for chapter header, controls and TOC; `en` copy unchanged
- [ ] Migrated files leave `PENDING_FILES`; sensors green; quick gate passes

**Tests**: unit
**Gate**: quick

**Commit**: `feat(web): translate the reader`

---

### T15: Chat dock (Ask, Tutor, citations)

**What**: Migrate Ask and Tutor panels, cited answers, citations popover, answer phases, failed turns, conversation list, include-notes toggle, save-to-note action and the dock Notes/Review tabs.
**Where**: `frontend/app/components/ask-panel.tsx` (plus `teach-panel.tsx`, `cited-answer.tsx`, `citations.tsx`, `answer-phase.tsx`, `failed-turn.tsx`, `conversation-list.tsx`, `include-notes-toggle.tsx`, `save-to-note-action.tsx`, `dock-notes-panel.tsx`, `dock-review-panel.tsx`, `use-conversation-thread.ts`, `use-include-notes.ts`, `messages/*`, tests)
**Depends on**: T14
**Reuses**: `ask-panel.test.tsx`, `conversation-dock.test.tsx`, `cited-answer.test.tsx`
**Requirement**: I18N-02

**Tools**: MCP: NONE · Skill: NONE

**Done when**:

- [ ] All dock/Chat strings, not-found and failure states from the catalog; the `NOT_FOUND_IN_SOURCE` machine sentinel is never shown and never translated; citation snippets verbatim
- [ ] `pt-BR` render tests for Ask, Tutor opening, a not-found answer and a failed turn; `en` copy unchanged
- [ ] Migrated files leave `PENDING_FILES`; sensors green; quick gate passes

**Tests**: unit
**Gate**: quick

**Commit**: `feat(web): translate the Chat dock`

---

### T16: Review sessions and heatmap

**What**: Migrate the review screen, FSRS interval labels and rating buttons, empty-deck and done-for-today states, quiz polling copy and the study heatmap with locale-aware dates.
**Where**: `frontend/app/components/review-screen.tsx` (plus `study-heatmap.tsx`, `use-quiz-deck-polling.ts`, `app/(app)/review/page.tsx`, `messages/*`, tests)
**Depends on**: T15
**Reuses**: `review-screen.test.tsx`, `friction-budget.test.tsx`
**Requirement**: I18N-02

**Tools**: MCP: NONE · Skill: NONE

**Done when**:

- [ ] Review strings, interval labels (ICU plurals), keyboard hints and heatmap legend/month/weekday names from the catalog/formatters
- [ ] `pt-BR` render tests for a due card, empty deck and done-for-today; `en` copy unchanged
- [ ] Migrated files leave `PENDING_FILES`; sensors green; quick gate passes

**Tests**: unit
**Gate**: quick

**Commit**: `feat(web): translate review`

---

### T17: Notes surfaces and sensor closure

**What**: Migrate notes list/detail, capture popover, card suggestions, anchor badge, ink line; empty `PENDING_FILES`; add a pt-BR cross-surface walk test.
**Where**: `frontend/app/components/notes/notes-screen.tsx` (plus `note-detail-screen.tsx`, `capture-popover.tsx`, `card-suggestions.tsx`, `note-card-suggestions.tsx`, `anchor-status-badge.tsx`, `ink-line.tsx`, `app/(app)/notes/**`, `messages/*`, tests, `tests/i18n-hardcoded.test.ts`)
**Depends on**: T16
**Reuses**: `notes-screen.test.tsx`, `note-detail-screen.test.tsx`
**Requirement**: I18N-02, I18N-07

**Tools**: MCP: NONE · Skill: NONE

**Done when**:

- [ ] Notes strings from the catalog; user note bodies untouched; `pt-BR` render tests for list, detail and capture popover
- [ ] `PENDING_FILES` is empty; the hard-coded sensor passes over the whole tree with only the documented allowlist
- [ ] Full frontend gate: `make test-frontend`, `tsc`, and `npm run build` pass

**Tests**: unit
**Gate**: build

**Commit**: `feat(web): translate notes and close the string migration`

---

## Phase 5: AI output language

### T18: Response language through the generation port

**What**: Optional `response_language` kwarg on `GenerationPort` and its adapters; per-language note constants; user-turn placement in the Anthropic and compat adapters; deterministic adapter accepts and ignores it; routing and fakes forward/record it.
**Where**: `backend/app/infrastructure/answering/anthropic.py` (plus `prompts.py`, `openai_compat.py`, `local.py`, `routing.py`, `domain/ports.py`, `tests/fakes.py`, adapter tests)
**Depends on**: T17
**Reuses**: `ANSWER_SYSTEM_PROMPT`/`TEACHING_SYSTEM_PROMPT` freezing tests, teach envelope at `anthropic.py:566-572`
**Requirement**: I18N-08

**Tools**: MCP: NONE · Skill: `claude-api`

**Done when**:

- [ ] Anthropic: with `pt-BR` the note appears in the user turn (Ask question turn, tutor envelope); `system` block and cache-breakpoint placement byte-identical to the no-language request
- [ ] Compat adapter: note in the user message; `COMPAT_SYSTEM_PROMPT` unchanged
- [ ] `response_language=None` produces requests identical to today (existing snapshots/tests untouched)
- [ ] Sentinel handling unchanged (whole-reply `NOT_FOUND_IN_SOURCE` still maps to `found=False`); deterministic adapter returns identical output for every value; routing forwards the kwarg to each chain member
- [ ] Quick gate and boundaries check pass

**Tests**: unit
**Gate**: quick

**Commit**: `feat(answering): ask providers to answer in the learner's language`

---

### T19: Effective locale on conversation turns

**What**: Thread `response_language` through `PostConversationTurn` and have the conversation routes derive it from the stored preference + `Accept-Language`.
**Where**: `backend/app/application/conversations.py` (plus `web/conversations.py`, `web/dependencies.py`, tests)
**Depends on**: T18
**Reuses**: `PostConversationTurn._generate`/`_generate_stream` (`conversations.py:968,986`), `get_ai_profile_choice` dependency style
**Requirement**: I18N-08

**Tools**: MCP: NONE · Skill: `fastapi`

**Done when**:

- [ ] A recording fake port sees `pt-BR` for a user with stored `pt-BR`, for an unset user with `Accept-Language: pt-BR`, and `None` for stored `en`, unset + English header, and absent header (JSON and `/stream` routes, Ask and tutor origins)
- [ ] Stored preference beats header; header content never reaches the prompt (only the fixed note constants)
- [ ] Ownership/404/409/429/502 behavior unchanged; full backend gate and `make lint` pass

**Tests**: integration
**Gate**: full

**Commit**: `feat(conversations): answer in the learner's interface language`

---

## Phase 6: Fixture and closing

### T20: Portuguese golden fixture

**What**: In-code Portuguese EPUB from public-domain Machado de Assis excerpts, with expectations and cases in the golden set.
**Where**: `backend/tests/golden_pt_corpus.py` (plus `golden_expected.py`, golden tests)
**Depends on**: T19
**Reuses**: `golden_corpus.py`, `epub_builder.py`, `test_golden_ingestion/retrieval/citations.py`
**Requirement**: I18N-09

**Tools**: MCP: NONE · Skill: `epub-ingestion`

**Done when**:

- [ ] Excerpt text fetched from the public source (never from memory), provenance (work, edition id, URL, public-domain basis) in the module docstring
- [ ] Ingestion golden: expected sections/anchors and `search_config=portuguese`; self-consistency gate passes
- [ ] Retrieval golden: at least three questions using inflected forms resolve the expected anchor in the top 3; citation golden: cited chunk ids ⊆ evidence, expected anchors
- [ ] Runs offline with the deterministic adapters; full backend gate passes (`make infra` first)

**Tests**: integration
**Gate**: full

**Commit**: `test(eval): add a Portuguese public-domain golden book`

---

### T21: Docs closure

**What**: README and CLAUDE.md state the pt-BR interface and locale model; ROADMAP row and STATE handoff updated.
**Where**: `README.md` (plus `CLAUDE.md`, `.specs/project/ROADMAP.md`, `.specs/project/STATE.md`, a follow-up row for localized emails/quiz prompts)
**Depends on**: T20
**Reuses**: PR #72 drift-test discipline
**Requirement**: I18N-01..I18N-09

**Tools**: MCP: NONE · Skill: `docs-writer`

**Done when**:

- [ ] README/CLAUDE.md accurate to the shipped state (no claim beyond what ships; legal pages English; emails English; judged pt-BR eval blocked on the funded key)
- [ ] ROADMAP `pt-br-interface` row Done with the shipped summary; new `Not started` follow-up row for localized emails and quiz/card prompts
- [ ] Drift tests and `make check` pass

**Tests**: none
**Gate**: build

**Commit**: `docs: record the pt-BR interface in the readme and roadmap`

---

