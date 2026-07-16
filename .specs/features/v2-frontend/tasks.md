# v2-frontend Tasks

## Execution Protocol (MANDATORY — do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow
its Execute flow and Critical Rules.** The skill is the source of truth for the per-task
cycle, sub-agent delegation, adequacy review, Verifier, and discrimination sensor.

**If the skill cannot be activated, STOP and tell the user — do not proceed without it.**

---

**Design**: `.specs/features/v2-frontend/design.md`
**Status**: In Progress — Phase A ✅ (A1 `7504e45`, A2 `203bf3d`, A3 `741007b`, A4 `fb1f52c`; 97 vitest, tsc+build green; deviations in context.md — Phases D/E consume `MessageResponse`/`Spinner`/`Shimmer`, not `Response`/`Loader`) · Phase B ✅ (B1 `dd6e202`, B2 `98eac28`, B3 `2163af9`, B4 `0d2d313`, B5 `804a264`; backend 656 passed + ruff clean, frontend 104 passed; deviations in context.md) · Phase C ✅ (C1 `3e14ebc`, C2 `ff02e21`, C3 `b90d0a8`, C4 `030c11a`, C5 `4de4c94`; 118 vitest, tsc+build green; deviations in context.md — SourcesPanel removal deferred to Phase D) · Phase D ✅ (D1 `e7a6bd4`, D2 `367a885`, D3 `e85cfa9`, D4 `e2551a3`; 123 vitest, tsc+build green; SPEC_DEVIATION on citations composition + deviations in context.md) · Phase E ✅ (E1 `8e4098b`, E2 `0c68f33`; frontend 130 passed/22 files + tsc + build, backend 656 passed + ruff clean; raw-HTML inertness proven). All 20 tasks done — **Verifier PASS** (22/22 ACs matched, 6/6 sensor mutants killed, 0 gaps; two non-blocking edge-case notes in `validation.md`).

---

## Test Coverage Matrix

> Generated from codebase + guidelines. Guidelines found: `CLAUDE.md` (citations/eval as core, golden-fixture-first), `.github/workflows/ci.yml` (gate commands), existing conventions in `frontend/tests/*` and `backend/tests/*`.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| --- | --- | --- | --- | --- |
| Frontend `app/lib/*` clients + streaming transport helpers | unit (node env, injected `fetchImpl`) | 1:1 to spec ACs for the client; URL/method/headers/body + error mapping branches | `frontend/tests/*-client.test.ts`, `streaming.test.ts` | `cd frontend && npx vitest run tests/<file>` |
| Frontend screens/components (shell, ask, teach, reader, library) | unit (jsdom, testing-library, `routedFetch`/stream fixtures) | Every FE AC + every listed edge case for the surface; happy + not-found + error + disabled states | `frontend/tests/*.test.tsx` (`// @vitest-environment jsdom`) | `cd frontend && npx vitest run tests/<file>` |
| Proxy translation | unit (direct fn calls) | FE-22: SSE chunk relay + header preservation/strip | `frontend/tests/proxy-*.test.ts` | `cd frontend && npx vitest run tests/proxy-forwarding.test.ts` |
| Vendored shadcn/ui + AI Elements source, config, tokens | none (build gate only, AD-071) | — | `frontend/components/**` | build gate |
| Backend repository (`get_section`) | integration (`requires_db`, skips w/o `LEARNY_TEST_DATABASE_URL`) | hit + miss (unknown anchor) + cross-source isolation | `backend/tests/test_repositories*.py` pattern | `cd backend && uv run pytest <file> -q` |
| Backend service + web route (section endpoint) | unit/web (fake repos per existing web tests) | FE-14 fully: 200 shape, 404 missing/non-owner/no-corpus/unknown-anchor, 401, 422 empty anchor | `backend/tests/test_sources_web*.py` pattern (mirror structure-endpoint tests) | `cd backend && uv run pytest <file> -q` |

## Parallelism Assessment

> Generated from codebase.

| Test Type | Parallel-Safe? | Isolation Model | Evidence |
| --- | --- | --- | --- |
| vitest (node + jsdom) | Yes | Per-file workers; fetch stubbed per test w/ `cleanup()`/`restoreAllMocks` | `tests/ask-screen.test.tsx:103-106` |
| pytest unit/web | Yes (within one run) | Fake repos, no shared state | existing web tests |
| pytest integration | No | Shared `learny_test` DB | `backend/tests/conftest.py` (`LEARNY_TEST_DATABASE_URL`) |

`[P]` below = order-free within the phase for the single phase worker; it never means parallel sub-agents.

## Gate Check Commands

> `uv` lives at `/home/augusto/myenv/bin/uv`; DB/MinIO via `docker.exe compose up -d db minio`; integration tests need `LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test`.

| Gate Level | When to Use | Command |
| --- | --- | --- |
| Quick-FE | After each frontend task | `cd frontend && npx vitest run <affected files>` |
| Full-FE | Frontend phase boundary | `cd frontend && npx vitest run && npx tsc --noEmit` |
| Build-FE | Phase A/C/D/E boundary | `cd frontend && npx vitest run && npx tsc --noEmit && npm run build` |
| Quick-BE | After each backend task | `cd backend && uv run pytest <affected module> -q` |
| Full-BE | Phase B boundary + Phase E close | `cd backend && uv run pytest -q && uv run ruff check .` |

---

## Execution Plan

5 phases (>3 ⇒ one worker per phase, sequential — context.md D-8). Every phase worker inherits the session model (the cost-discipline ceiling tier); Verifier likewise — no downshifts (each phase carries stack-setup, correctness, or streaming-contract weight).

```
Phase A (sequential): A1 → A2 → A3 → A4
Phase B: B1 → B2 ; B3 [P], B4 [P], B5 [P] (after nothing — frontend-only, order-free)
Phase C: C1 [P], C2 [P] → C3 (needs C2) ; C4 [P] → C5 (needs C4)
Phase D: D1 → D2 [P], then D3, D4 (need D1; D3/D4 order-free after D2)
Phase E: E1 → E2
```

Recommended skills per worker: Phase B backend tasks → `fastapi`; Phases A/C/D/E → `vercel-react-best-practices` (+ `vercel-composition-patterns` for D). MCP: NONE (research doc + installed package types are the API source of truth).

---

## Task Breakdown

### Phase A — Foundation (FE-01, FE-02)

#### A1: Tailwind v4 baseline
**What**: Add `tailwindcss@^4` + `@tailwindcss/postcss`, `postcss.config.mjs`, `app/globals.css` (`@import "tailwindcss"`), import in root layout.
**Where**: `frontend/package.json`, `frontend/postcss.config.mjs`, `frontend/app/globals.css`, `frontend/app/layout.tsx`
**Depends on**: None · **Reuses**: existing layout · **Requirement**: FE-01
**Done when**: build compiles Tailwind utilities (a class visibly emitted in CSS); Build-FE passes; existing 13 test files still pass (count ≥ current).
**Tests**: none (config) · **Gate**: Build-FE · **Commit**: `feat(web): add tailwind v4 styling baseline`

#### A2: shadcn/ui init + base primitives
**What**: `npx shadcn@latest init` (CSS-variables mode) + add `sidebar button input badge collapsible dropdown-menu popover card skeleton separator tooltip`; tokens land in `globals.css`; `components.json`, `lib/utils.ts`.
**Where**: `frontend/components/ui/**`, `frontend/components.json`, `frontend/app/globals.css`, `frontend/lib/utils.ts`
**Depends on**: A1 · **Requirement**: FE-01
**Done when**: vendored source passes `tsc --noEmit` + `next lint`-level compile; Build-FE passes.
**Tests**: none (vendored, AD-071) · **Gate**: Build-FE · **Commit**: `feat(web): vendor shadcn/ui primitives`

#### A3: AI SDK + AI Elements
**What**: Add `ai` + `@ai-sdk/react` (current major; research: ^7) + `npx ai-elements@latest` vendoring `conversation message response prompt-input inline-citation sources loader` (+ CLI-required peers).
**Where**: `frontend/components/ai-elements/**`, `frontend/package.json`
**Depends on**: A2 · **Requirement**: FE-01
**Done when**: vendored components compile under strict tsc; Build-FE passes; **verify `DefaultChatTransport.prepareSendMessagesRequest` exists in installed types** (record any API drift from design in phase summary).
**Tests**: none (vendored) · **Gate**: Build-FE · **Commit**: `feat(web): vendor ai elements and add ai sdk`

#### A4: Fonts, ThemeProvider, route groups
**What**: `geist` font in root layout (fallback: Inter via `next/font/google`); `next-themes` `ThemeProvider` (`attribute="class"`, system default, `suppressHydrationWarning`); move shelled pages to `app/(app)/…` and auth pages to `app/(auth)/…` (URLs unchanged); minimal `(auth)` centered layout.
**Where**: `frontend/app/layout.tsx`, `frontend/app/components/theme-provider.tsx`, `frontend/app/(app)/**`, `frontend/app/(auth)/**`
**Depends on**: A2 · **Requirement**: FE-02, FE-03 (routing substrate)
**Done when**: theme class toggles on `<html>` and persists (jsdom test w/ next-themes); all existing screen tests updated for new paths and green; Build-FE passes.
**Tests**: unit (jsdom: theme persistence) · **Gate**: Build-FE · **Commit**: `feat(web): add fonts, theme provider, and route groups`

### Phase B — Seams (FE-14, FE-18, FE-22)

#### B1: Repository `get_section`
**What**: `get_section(source_id, anchor)` on the corpus read repository — single owner-agnostic SELECT (title, section_path, anchor, markdown) via `corpus_documents.source_id` join; `None` on miss.
**Where**: `backend/app/infrastructure/db/repositories.py` (+ port/protocol where `get_structure`'s is declared)
**Depends on**: None · **Reuses**: `get_structure` (`repositories.py:410-444`) · **Requirement**: FE-14
**Done when**: integration tests: hit returns markdown+path; unknown anchor → None; anchor of a *different* source → None; Quick-BE passes.
**Tests**: integration (`requires_db`) · **Gate**: Quick-BE · **Commit**: `feat(corpus): add single-section read query`

#### B2: `ReadSection` service + `GET /api/sources/{id}/section`
**What**: Owner-scoped service (mirrors `ReadSourceStructure`: source ownership → 404 no-disclosure; no corpus/unknown anchor → 404) + route in `sources.py` with `anchor` query param (`min_length=1`) + `SectionContentView{anchor,title,section_path,markdown}` + DI wiring.
**Where**: `backend/app/application/` (module hosting `ReadSourceStructure`), `backend/app/infrastructure/web/sources.py`
**Depends on**: B1 · **Reuses**: structure endpoint + its web tests · **Requirement**: FE-14
**Done when**: web tests cover 200 shape / 404 missing / 404 non-owner / 404 no-corpus / 404 unknown-anchor / 401 / 422 empty anchor, incl. an anchor containing `#`; Full-BE passes (suite ≥ 645 passed baseline, ruff clean).
**Tests**: unit/web · **Gate**: Full-BE · **Commit**: `feat(api): expose section content by anchor`

#### B3: `lib/ingestion.ts` client [P]
**What**: `getIngestion(sourceId, fetchImpl)` → existing `GET /api/sources/{id}/ingestion`; `IngestionView` type per design.
**Where**: `frontend/app/lib/ingestion.ts`, `frontend/tests/ingestion-client.test.ts` (extend existing file)
**Depends on**: None · **Reuses**: `sources.ts` client pattern · **Requirement**: FE-18
**Done when**: tests assert method/URL/credentials, parsed view, 401/404 error paths; Quick-FE passes.
**Tests**: unit · **Gate**: Quick-FE · **Commit**: `feat(web): add ingestion status client`

#### B4: `lib/sections.ts` client [P]
**What**: `getSection(sourceId, anchor, fetchImpl)` — encodes anchor once, returns `SectionView` or typed not-found on 404.
**Where**: `frontend/app/lib/sections.ts`, `frontend/tests/sections-client.test.ts`
**Depends on**: None (contract fixed by spec FE-14) · **Requirement**: FE-15
**Done when**: tests assert encoded query param (anchor with `/`+`#`), 200 parse, 404 typed result, 401 error; Quick-FE passes.
**Tests**: unit · **Gate**: Quick-FE · **Commit**: `feat(web): add section content client`

#### B5: SSE relay regression test [P]
**What**: Proxy test: streamed `text/event-stream` upstream body relays chunk-by-chunk (first chunk observable before upstream closes), `x-vercel-ai-ui-message-stream`/`cache-control`/`x-accel-buffering` preserved, `content-encoding`/`content-length` stripped.
**Where**: `frontend/tests/proxy-forwarding.test.ts` (extend)
**Depends on**: None · **Reuses**: `relayResponse` tests at `:105-123` · **Requirement**: FE-22
**Done when**: new assertions pass; Quick-FE passes.
**Tests**: unit · **Gate**: Quick-FE · **Commit**: `test(web): prove sse responses relay unbuffered through the proxy`

### Phase C — Shell & library (FE-03..05, FE-19..21)

#### C1: Auth screens on the new stack [P]
**What**: Restyle `AuthForm`/login/register/account inside `(auth)`/`(app)` layouts with shadcn primitives; behavior unchanged.
**Where**: `frontend/app/components/AuthForm.tsx`, `AccountPanel.tsx`, `(auth)` pages
**Depends on**: Phase A · **Requirement**: FE-03, FE-05
**Done when**: `tests/auth-screens.test.tsx` green with intent preserved (submit, error, redirect asserts); Quick-FE.
**Tests**: unit (jsdom) · **Gate**: Quick-FE · **Commit**: `feat(web): restyle auth and account screens`

#### C2: AppSidebar + section tree [P]
**What**: `app-sidebar.tsx` (shadcn `Sidebar`): sources w/ status `Badge`, ready-source `Collapsible` tree (shared `tree.ts` util generalizing `flattenSections`), links to Ask/Teach/Read, tree node → `/sources/{id}/read?anchor=<enc>`; empty-library state.
**Where**: `frontend/app/components/shell/app-sidebar.tsx`, `frontend/app/lib/tree.ts`
**Depends on**: Phase A · **Reuses**: structure client, `TeachPanel.flattenSections` · **Requirement**: FE-04
**Done when**: jsdom tests: sources listed w/ badges, tree expands from structure fixture, links carry encoded anchor, empty state; Quick-FE.
**Tests**: unit (jsdom) · **Gate**: Quick-FE · **Commit**: `feat(web): add library sidebar with book navigation`

#### C3: AuthHeader + `(app)` shell layout
**What**: Header (email from `/api/auth/me`, account link, logout, theme toggle) + `(app)/layout.tsx` composing `SidebarProvider + AppSidebar + AuthHeader`; 401 → `/login`.
**Where**: `frontend/app/components/shell/auth-header.tsx`, `frontend/app/(app)/layout.tsx`
**Depends on**: C2 · **Reuses**: `auth.ts` client, `onRequireAuth` pattern · **Requirement**: FE-03, FE-05, FE-02 (toggle)
**Done when**: jsdom tests: header renders email, logout redirects, theme toggle flips class, 401 redirect; auth pages render shell-free; Quick-FE.
**Tests**: unit (jsdom) · **Gate**: Quick-FE · **Commit**: `feat(web): add app shell with header and navigation`

#### C4: LibraryScreen [P]
**What**: Replace `SourcesPanel`: source cards (badge, Ask/Teach/Read links), upload control (existing multipart contract), failed state showing latest event message + restart control.
**Where**: `frontend/app/components/library-screen.tsx`, `(app)/sources/page.tsx`
**Depends on**: Phase A · **Reuses**: `sources.ts` clients · **Requirement**: FE-20, FE-21
**Done when**: `tests/sources-screen.test.tsx` rewritten w/ intent preserved + failed-state and upload-error asserts; Quick-FE.
**Tests**: unit (jsdom) · **Gate**: Quick-FE · **Commit**: `feat(web): rebuild library screen with upload and status states`

#### C5: Ingestion polling hook
**What**: `use-ingestion-polling.ts`: per-`processing`-source 3 s `setInterval` → `getIngestion`; badge patch on change; clear on terminal + unmount; wire into LibraryScreen (and sidebar badges if shared state is trivial).
**Where**: `frontend/app/components/use-ingestion-polling.ts`, `library-screen.tsx`
**Depends on**: C4 (+B3) · **Requirement**: FE-19
**Done when**: fake-timer jsdom tests: poll fires at 3 s, badge updates processing→ready, stops on terminal, cleans up on unmount, failed tick skipped silently; Build-FE phase gate passes.
**Tests**: unit (jsdom, fake timers) · **Gate**: Build-FE · **Commit**: `feat(web): poll ingestion progress on the library screen`

### Phase D — Streaming surfaces (FE-06..13, FE-16)

#### D1: `lib/streaming.ts` transport module
**What**: `createQuestionTransport`/`createTurnTransport` (DefaultChatTransport, `prepareSendMessagesRequest` → `{question}`/`{message}` latest-message body + `X-CSRF-Token`), `LearnyUIMessage` data-part types, `turnsToUIMessages`, `errorMessageFor` (401/403/404/409/422/429/502/network).
**Where**: `frontend/app/lib/streaming.ts`, `frontend/tests/streaming.test.ts`
**Depends on**: Phase A · **Reuses**: `Citation` type, `teaching.ts` views · **Requirement**: FE-06, FE-12
**Done when**: unit tests: prepared request shape (url/headers/body from a messages array), turn→UIMessage mapping incl. citations part, error mapping branches; Quick-FE.
**Tests**: unit · **Gate**: Quick-FE · **Commit**: `feat(web): add streaming chat transport for learny endpoints`

#### D2: Citation components [P]
**What**: `citations.tsx`: `CitationList` (Sources/InlineCitation composition) + popover (breadcrumb, snippet, "Open in book" → encoded reader href).
**Where**: `frontend/app/components/citations.tsx`
**Depends on**: D1 (types) · **Requirement**: FE-16
**Done when**: jsdom tests: renders breadcrumb+snippet, popover opens, href = `/sources/{id}/read?anchor=<enc>` for `#`-bearing anchor; Quick-FE.
**Tests**: unit (jsdom) · **Gate**: Quick-FE · **Commit**: `feat(web): add citation list and open-in-book popover`

#### D3: AskScreen (streaming)
**What**: Replace `AskPanel` with useChat + AI Elements composition per design; not-found, error, stop, disabled states.
**Where**: `frontend/app/components/ask-screen.tsx`, `(app)/sources/[id]/ask/page.tsx`
**Depends on**: D1, D2 · **Requirement**: FE-06..FE-10
**Done when**: jsdom tests stream a real v1 SSE fixture (`ReadableStream` via stubbed fetch): partial text before finish, citations render, not-found state, error part → banner + partial text + re-enabled input, 429 readable, submit disabled mid-stream, empty input never submits; Quick-FE.
**Tests**: unit (jsdom, SSE fixtures) · **Gate**: Quick-FE · **Commit**: `feat(web): stream cited answers on the ask screen`

#### D4: TeachScreen (streaming)
**What**: Replace `TeachPanel`: target picker (tree util) + resume list; session view seeds `useChat` from `turnsToUIMessages`; turns stream via `createTurnTransport`; Ask-contract states.
**Where**: `frontend/app/components/teach-screen.tsx`, `(app)/sources/[id]/teach/page.tsx`
**Depends on**: D1, D2 · **Reuses**: `teaching.ts` clients unchanged · **Requirement**: FE-11..FE-13
**Done when**: jsdom tests: picker + resume render, resumed history shows turns w/ citations, streamed turn renders deltas, not-found/429/error states; Build-FE phase gate passes.
**Tests**: unit (jsdom, SSE fixtures) · **Gate**: Build-FE · **Commit**: `feat(web): stream teaching turns with session resume`

### Phase E — Reader + closure (FE-15, FE-17)

#### E1: SectionReader + read route
**What**: `section-reader.tsx` + `(app)/sources/[id]/read/page.tsx` (client comp in `<Suspense>`): fetch via `getSection`; markdown via AI Elements `Response`; `scroll-mt` + scrollIntoView + transient highlight; no-anchor empty state; not-found state; raw-HTML-inert test.
**Where**: `frontend/app/components/section-reader.tsx`, `frontend/app/(app)/sources/[id]/read/page.tsx`
**Depends on**: Phase B (B4), Phase A · **Requirement**: FE-15, FE-17
**Done when**: jsdom tests: markdown renders, highlight applied to title block, unknown anchor → not-found, no anchor → empty state, `<script>`/raw HTML in markdown not injected as live DOM; Quick-FE.
**Tests**: unit (jsdom) · **Gate**: Quick-FE · **Commit**: `feat(web): add section reader with anchor highlighting`

#### E2: Citation→reader closure + full gates
**What**: jsdom navigation check (citation popover href loads reader at that anchor — router-level assert), sidebar tree link → reader spot-check, traceability table statuses → Verified-pending, run **all** gates.
**Where**: `frontend/tests/` (extend), `.specs/features/v2-frontend/spec.md` (statuses)
**Depends on**: E1, D2 · **Requirement**: FE-16 closure
**Done when**: Build-FE full (vitest all, tsc, build) + Full-BE (pytest ≥645-passed baseline + new, ruff) all green; test counts reported.
**Tests**: unit (jsdom) · **Gate**: Build-FE + Full-BE · **Commit**: `test(web): close the citation to reader navigation loop`

---

## Task Granularity Check

| Task | Scope | Status |
| --- | --- | --- |
| A1–A4 | 1 config/install/layout concern each | ✅ |
| B1 / B2 | 1 repo method / 1 service+endpoint (cohesive pair per repo web-test convention) | ✅ |
| B3 / B4 / B5 | 1 client fn / 1 client fn / 1 test file | ✅ |
| C1–C5 | 1 surface or hook each | ✅ |
| D1–D4 | 1 module / 1 component / 1 screen / 1 screen | ✅ |
| E1 / E2 | 1 screen / closure+gates | ✅ |

## Diagram-Definition Cross-Check

| Task | Depends On (body) | Diagram | Status |
| --- | --- | --- | --- |
| A1 none · A2←A1 · A3←A2 · A4←A2 | as listed | A1→A2→A3, A2→A4 (A3/A4 sequential in worker order) | ✅ |
| B1 none · B2←B1 · B3/B4/B5 none | as listed | B1→B2; B3/B4/B5 [P] | ✅ |
| C1←A · C2←A · C3←C2 · C4←A · C5←C4,B3 | as listed | C1/C2/C4 [P]; C2→C3; C4→C5 | ✅ |
| D1←A · D2←D1 · D3←D1,D2 · D4←D1,D2 | as listed | D1→D2→{D3,D4} | ✅ |
| E1←B4,A · E2←E1,D2 | as listed | E1→E2 | ✅ |

## Test Co-location Validation

| Task | Layer | Matrix Requires | Task Says | Status |
| --- | --- | --- | --- | --- |
| A1/A2/A3 | config/vendored | none (build gate) | none + Build-FE | ✅ |
| A4 | component (ThemeProvider) | unit jsdom | unit | ✅ |
| B1 | repository | integration | integration | ✅ |
| B2 | service+route | unit/web | unit/web | ✅ |
| B3/B4 | client | unit | unit | ✅ |
| B5 | proxy | unit | unit | ✅ |
| C1–C5 | components/hook | unit jsdom | unit jsdom | ✅ |
| D1 | client module | unit | unit | ✅ |
| D2–D4 | components/screens | unit jsdom | unit jsdom | ✅ |
| E1/E2 | screen/closure | unit jsdom | unit jsdom | ✅ |
