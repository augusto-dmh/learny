# v4-identity-foundation Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user — do not proceed without it.**

---

**Design**: `.specs/features/v4-identity-foundation/design.md`
**Status**: Done — T1 `7ed3976`, T2 `037a7f4`, T3 `7ca964c`, T4 `50edc19`, T5 `2ad33ad`, T6 gate-only (253 vitest + tsc + build green; served-bundle proof: self-hosted woff2, no fonts.g* refs, paper selector compiled)

---

## Test Coverage Matrix

> Generated from codebase, project guidelines, and spec. Guidelines found: `CLAUDE.md` (evaluation/traceability core), CI `ci.yml` frontend job (vitest → tsc → build), spec execution notes (vitest + Testing Library, follow `sources-screen.test.tsx` patterns).

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| ---------- | ------------------ | -------------------- | ---------------- | ----------- |
| Theme tokens (`globals.css`) | static/unit (file-content, jsdom can't apply stylesheets) | 1:1 to IDF-01/03/05 ACs: pinned hexes present both modes, all AA pairs ≥4.5:1, paper block scoped, highlight hexes unreferenced elsewhere | `frontend/tests/theme-tokens.test.ts` | `npx vitest run tests/theme-tokens.test.ts` |
| Font binding (`layout.tsx`) | static/unit (file-content — RootLayout renders `<html>`, unmountable) | IDF-02 AC1: Source Serif 4 import, latin subset, `--font-serif` binding present | `frontend/tests/theme-tokens.test.ts` | same |
| Components (`section-reader.tsx`, `citations.tsx`) | unit (jsdom + Testing Library) | IDF-04 AC1 class presence on both surfaces; IDF-06 AC1 rendered text == served text | `frontend/tests/section-reader.test.tsx`, `frontend/tests/citations.test.tsx` | `npx vitest run tests/section-reader.test.tsx tests/citations.test.tsx` |
| Suite integrity | full | IDF-07: whole suite + tsc green | `frontend/tests/**` | `npx vitest run && npx tsc --noEmit` |

## Parallelism Assessment

> All frontend tests are parallel-safe (per-test jsdom isolation, fetch stubbed per test file — evidence: entire existing suite runs under default vitest parallel workers). `[P]` allowed everywhere; ordering below is by code dependency only.

| Test Type | Parallel-Safe? | Isolation Model | Evidence |
| --------- | -------------- | --------------- | -------- |
| vitest unit/component | Yes | per-file jsdom env, stubbed fetch | `frontend/tests/*` all run parallel in CI today |

## Gate Check Commands

| Gate Level | When to Use | Command |
| ---------- | ----------- | ------- |
| Quick | after each task | `cd frontend && npx vitest run tests/<touched>.test.ts[x]` |
| Full | phase boundary | `cd frontend && npx vitest run && npx tsc --noEmit` |
| Build | end of cycle (IDF-07) | `cd frontend && npx vitest run && npx tsc --noEmit && npm run build` |

---

## Execution Plan

### Phase 1: Tokens & fonts (sequential)

T1 → T2

### Phase 2: Reading typography (T3/T4/T5 order-free after T1/T2)

T2 ──┬→ T3 [P]
     ├→ T4 [P]
     └→ T5 [P]

### Phase 3: Suite integrity (sequential)

T3,T4,T5 → T6

---

## Task Breakdown

### T1: Iron Gall token sweep + highlight tokens + WCAG test

**What**: Replace `:root`/`.dark` palettes in `globals.css` with the Iron Gall values (spec-pinned + design D-3 derived), set `--radius: 0.25rem`, add `--highlight-{yellow,cyan,violet,green}` both modes + `--color-highlight-*` bridge entries in `@theme inline`; add `frontend/tests/theme-tokens.test.ts` with hex-presence asserts (IDF-01 AC1, IDF-03 AC1), in-test WCAG contrast math over the design's pair list both modes (IDF-01 AC2), and a no-raw-highlight-hex-elsewhere scan.
**Where**: `frontend/app/globals.css`, `frontend/tests/theme-tokens.test.ts`
**Depends on**: None
**Reuses**: existing `@theme inline` bridge; `prod-image.test.ts` file-content pattern
**Requirement**: IDF-01, IDF-03
**Done when**: pinned hexes literal in both blocks; all listed pairs ≥ 4.5:1 (test computes, not eyeballs); highlight tokens in both modes; quick gate passes.
**Tests**: static/unit · **Gate**: quick
**Commit**: `feat(ui): adopt the Iron Gall palette with a contrast gate`

### T2: Source Serif 4 binding

**What**: Bind `Source_Serif_4` (`next/font/google`, subsets `latin`+`latin-ext`, variable `--font-source-serif`) in `layout.tsx` beside Geist; map `--font-serif` in `fontVars` and `@theme inline`; extend `theme-tokens.test.ts` with the layout file-content asserts (IDF-02 AC1).
**Where**: `frontend/app/layout.tsx`, `frontend/app/globals.css`, `frontend/tests/theme-tokens.test.ts`
**Depends on**: T1 (same test file)
**Reuses**: Geist `fontVars` binding pattern (`layout.tsx:15`)
**Requirement**: IDF-02
**Done when**: layout binds the variable + subset asserts pass; quick gate passes.
**Tests**: static/unit · **Gate**: quick
**Commit**: `feat(ui): bind Source Serif 4 as the reading serif`

### T3: `.prose-reading` class + application [P]

**What**: Define `.prose-reading` in `globals.css` `@layer components` (serif 19px, 1.6, 65ch, left-aligned, hyphens none); apply on the section-reader prose wrapper (replacing `prose prose-sm max-w-none`, design D-5) and the citation popover snippet blockquote; component tests assert class presence on both (IDF-04 AC1).
**Where**: `frontend/app/globals.css`, `frontend/app/components/section-reader.tsx`, `frontend/app/components/citations.tsx`, `frontend/tests/section-reader.test.tsx`, `frontend/tests/citations.test.tsx`
**Depends on**: T2
**Reuses**: existing section-reader/citations test suites
**Requirement**: IDF-04
**Done when**: both surfaces carry the class in tests; quick gate passes.
**Tests**: unit · **Gate**: quick
**Commit**: `feat(ui): set book prose in reading typography`

### T4: Paper appearance layer [P]

**What**: Add the `html:not(.dark) [data-appearance="paper"]` token block (Direction-A warm surface values per spec IDF-05) to `globals.css`; extend `theme-tokens.test.ts`: block exists with the hexes, scoped under the guarded selector, paper hexes absent from `:root`/`.dark` (IDF-05 AC1). No toggle, no consumer.
**Where**: `frontend/app/globals.css`, `frontend/tests/theme-tokens.test.ts`
**Depends on**: T2
**Reuses**: T1's CSS-parsing helpers
**Requirement**: IDF-05
**Done when**: scoping + hex asserts pass; quick gate passes.
**Tests**: static/unit · **Gate**: quick
**Commit**: `feat(ui): scaffold the paper reading appearance`

### T5: Micro-typography pass [P]

**What**: Component test proving corpus markdown punctuation renders verbatim (straight quotes/apostrophes/`--`/`...` in served markdown appear unchanged — IDF-06 AC1); curly-apostrophe/ellipsis pass over author-owned UI copy in the files this cycle touches (AD-120), updating any test strings in step.
**Where**: `frontend/tests/section-reader.test.tsx`, `frontend/app/components/section-reader.tsx`, `frontend/app/components/citations.tsx`
**Depends on**: T3 (same files)
**Reuses**: section-reader test fixtures
**Requirement**: IDF-06
**Done when**: pass-through test green; touched UI copy typographic; quick gate passes.
**Tests**: unit · **Gate**: quick
**Commit**: `test(ui): pin corpus punctuation pass-through`

### T6: Suite integrity + visual sanity

**What**: Full frontend gate (vitest, tsc, build) plus running-app visual sanity: money-path screens (library, reader, ask, review, notes) render legibly in light and dark (IDF-07).
**Where**: no new files (fixes only if the gate surfaces them)
**Depends on**: T3, T4, T5
**Requirement**: IDF-07
**Done when**: `npx vitest run` + `npx tsc --noEmit` + `npm run build` green; both modes visually sane in the running app.
**Tests**: full suite · **Gate**: Build
**Commit**: none unless fixes needed (`fix(ui): …`)

---

## Diagram-Definition Cross-Check

| Task | Depends On (body) | Diagram Shows | Status |
| ---- | ----------------- | ------------- | ------ |
| T1 | None | Phase-1 start | ✅ |
| T2 | T1 | T1 → T2 | ✅ |
| T3 | T2 | T2 → T3 [P] | ✅ |
| T4 | T2 | T2 → T4 [P] | ✅ |
| T5 | T3 | T3 → T5 (listed [P] within phase for T4-independence; sequenced after T3) | ✅ (T5 ∥ T4 only) |
| T6 | T3, T4, T5 | all → T6 | ✅ |

Note: T5 depends on T3 (same files), so within Phase 2 the true order is T3 → T5, with T4 free-floating. `[P]` marks T4 ∥ {T3→T5}.

## Test Co-location Validation

| Task | Layer | Matrix Requires | Task Says | Status |
| ---- | ----- | --------------- | --------- | ------ |
| T1 | theme tokens | static/unit | static/unit | ✅ |
| T2 | font binding | static/unit | static/unit | ✅ |
| T3 | components | unit | unit | ✅ |
| T4 | theme tokens | static/unit | static/unit | ✅ |
| T5 | components | unit | unit | ✅ |
| T6 | suite | full | full | ✅ |
