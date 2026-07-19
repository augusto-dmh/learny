# v4-identity-foundation Validation

**Date**: 2026-07-18
**Spec**: `.specs/features/v4-identity-foundation/spec.md`
**Diff range**: `7ed3976^..HEAD` (7ed3976, 037a7f4, 7ca964c, 50edc19, 2ad33ad)
**Verifier**: independent sub-agent (author ≠ verifier); evidence-or-zero

---

## Task Completion

| Task | Status | Notes |
| ---- | ------ | ----- |
| T1 Iron Gall token sweep + highlight tokens + WCAG test | ✅ Done | `7ed3976` |
| T2 Source Serif 4 binding | ✅ Done | `037a7f4` |
| T3 `.prose-reading` class + application | ✅ Done | `7ca964c` |
| T4 Paper appearance layer | ✅ Done | `50edc19` |
| T5 Micro-typography pass | ✅ Done | `2ad33ad` |
| T6 Suite integrity + visual sanity | ✅ Done | gate-only; visual leg = author manual check (served CSS bundle) |

---

## Spec-Anchored Acceptance Criteria

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| IDF-01 AC1 — light & dark carry exact hexes | bg `#F6F7F6`/`#0F161B`, surface `#FFFFFF`/`#172128`, ink `#1B2733`/`#D9E2E8`, muted `#5D6B76`/`#7F93A0`, border `#DDE2E4`/`#263340`, accent(primary) `#22557A`/`#6FA9CC`, accent-fg `#F4F8FA`/`#0E1A22`; `--radius:0.25rem` | `theme-tokens.test.ts:69` — `expect(token(light,name)).toBe(lightHex)` / `expect(token(dark,name)).toBe(darkHex)` over the 7-pair PINNED table (`:50-58`); radius `theme-tokens.test.ts:75` — `expect(token(light,"radius")).toBe("0.25REM")` | ✅ PASS |
| IDF-01 AC2 — every ink-on-bg & accent-fg-on-accent pair ≥ AA, both modes, committed check | contrast ratio ≥ 4.5:1 | `theme-tokens.test.ts:104` — `expect(contrast(fgHex,bgHex)).toBeGreaterThanOrEqual(4.5)` over AA_PAIRS (`:81-93`, incl. `foreground/background` and `primary-foreground/primary`) × light+dark (`:95-98`) | ✅ PASS |
| IDF-02 AC1 — serif bound, latin subset (pt diacritics), build-time self-host (no runtime font req) | Source Serif 4 via `next/font/google`, latin subset, `--font-serif` exposed | `theme-tokens.test.ts:144` import assert, `:147` `subsets:["latin","latin-ext"]`, `:148` `variable:"--font-source-serif"`, `:152` `"--font-serif":"var(--font-source-serif)"`, `:159` theme bridge | ✅ PASS (self-host is a by-construction property of `next/font/google`; served-bundle woff2 leg verified manually by author) |
| IDF-03 AC1 — highlight tokens both modes; no raw hex elsewhere | `--highlight-{yellow,cyan,violet,green}` light/dark; no other file references raw hex | `theme-tokens.test.ts:164` — `expect(token(light,name)).toBe(...)`/`token(dark,...)` over HIGHLIGHTS (`:61-66`); `:175-203` filesystem walk asserts `offenders).toEqual([])` | ✅ PASS |
| IDF-04 AC1 — reader prose AND citation snippet render under `.prose-reading` | class present on both surfaces | reader: `section-reader.test.tsx:164` — `container.querySelector(".prose-reading")` not null; citation: `citations.test.tsx:70` — `snippet.closest("blockquote").className).toContain("prose-reading")` | ✅ PASS |
| IDF-05 AC1 — paper tokens scoped; chrome outside reader unaffected | warm Direction-A hexes only under `html:not(.dark) [data-appearance="paper"]`; absent from `:root`/`.dark` | `theme-tokens.test.ts:122` — `cssBlock('html:not(.dark) [data-appearance="paper"]')` + `token(paper,name)).toBe(hex)` over PAPER (`:113-120`); `:129-134` — `expect(light).not.toContain(hex)`/`dark` | ✅ PASS |
| IDF-06 AC1 — no transformation of corpus text (rendered == served) | served straight quotes/`--`/`...`/apostrophes render verbatim | `section-reader.test.tsx:147` — `expect(document.body.textContent).toContain(punctuation)` where `punctuation` = `She said "so-called 'algorithms'" -- then paused... twice.` (`:134`) | ✅ PASS |
| IDF-07 — suite + tsc green; visual sanity | 0 failures, tsc clean | Verifier ran gates (below); visual leg = author manual check | ✅ PASS |

**Status**: ✅ All 7 requirements covered with located, spec-matching assertions.

---

## Discrimination Sensor

Lightweight fault-injection, 6 behavior-level mutations across all high-risk new
surfaces (palette hex, WCAG math, paper scoping guard, class application, highlight
token, serif binding). Each mutation applied to a scratch edit, relevant file run,
then reverted via `git checkout --`. Tree confirmed clean afterward.

| # | File:line | Mutation | Test run | Killed? |
| - | --------- | -------- | -------- | ------- |
| 1 | `globals.css:68` | `--primary #22557A` → `#22557B` | `theme-tokens.test.ts` | ✅ Killed — pinned-hex assert (`:71`) |
| 2 | `globals.css:74` | `--accent #E3ECF2` → `#2A3A48` (dark, kills accent-fg contrast; non-pinned token, isolates the AA math) | `theme-tokens.test.ts` | ✅ Killed — `accent-foreground on accent >= 4.5:1` (`:104`) |
| 3 | `globals.css:145` | drop `html:not(.dark)` guard from paper selector | `theme-tokens.test.ts` | ✅ Killed — scoped-selector block lookup (`:123`) |
| 4 | `section-reader.tsx:263` | remove `prose-reading` from reader wrapper class | `section-reader.test.tsx` | ✅ Killed — class-presence (`:164`) + 5 dependent capture tests |
| 5 | `globals.css:134` | delete `--highlight-violet` from `.dark` | `theme-tokens.test.ts` | ✅ Killed — dark highlight presence (`:164`) |
| 6 | `layout.tsx:27` | `--font-serif` bound to `var(--font-geist-sans)` instead of serif | `theme-tokens.test.ts` | ✅ Killed — serif binding assert (`:152`) |

**Sensor depth**: lightweight (theming cycle, no P0 path)
**Result**: 6/6 killed — ✅ PASS. Tests are discriminating for palette exactness, WCAG contrast, paper scoping, reading-typography application, highlight tokens, and serif binding.

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code / no scope creep | ✅ Only the 4 spec surfaces touched (globals.css, layout.tsx, section-reader.tsx, citations.tsx) + 3 test files |
| Surgical changes | ✅ Component edits are class-swap + one UI-copy glyph only |
| Matches patterns | ✅ File-content test pattern (`prod-image.test.ts`), Geist binding mirror, existing vitest+RTL suites extended |
| Spec-anchored outcome check | ✅ Every asserted value matches a spec-pinned hex / ratio / class / string |
| Per-layer coverage met | ✅ Theme tokens 1:1 to IDF-01/03/05 ACs; components cover class presence + corpus pass-through |
| Every test maps to a requirement | ✅ No unclaimed new tests |
| Documented guidelines | CLAUDE.md (traceability core), CI `ci.yml` frontend job (vitest→tsc→build), spec exec notes (vitest+RTL) — followed |
| Out-of-scope honored | ✅ No ink-line system, no `Aa` toggle UI, no backend/IA change (spec Out-of-scope) |

---

## Gate Check

- **Gate command**: `cd frontend && npx vitest run && npx tsc --noEmit` (Build-level `npm run build` skipped — author-proven at cycle end + CI-covered by `ci.yml` frontend job)
- **vitest**: 31 files, **253 passed, 0 failed, 0 skipped**
- **tsc --noEmit**: exit 0
- **Test count**: +~15 net new assertions across theme-tokens.test.ts (new, 41 cases), section-reader.test.tsx (+3 cases: reading-typography, corpus pass-through, existing capture unchanged), citations.test.tsx (+prose-reading assert). No tests deleted; no assertions weakened.

---

## Spec-Precision Notes (low severity, non-blocking)

1. **Surface/popover exact hex** — IDF-01 lists a single "surface" value (`#FFFFFF`/`#172128`). The pin test asserts the exact hex for `--card` but not for `--popover` (the other surface token); `--popover` is only exercised through the AA contrast pair. The CSS sets popover correctly, and AA covers legibility, so this is a completeness note, not a gap. A pinned-hex assert on `popover` would close it.
2. **IDF-02 "no runtime third-party font request"** — asserted by construction (use of `next/font/google` guarantees build-time self-host) rather than by a direct network/served-bundle assertion; the served-bundle leg (self-hosted woff2, no `fonts.g*` refs) is a documented author manual check, not automated. Acceptable for a theming cycle; a build-output grep test would make it reproducible in CI.
3. **IDF-02 Portuguese diacritics** — covered indirectly via `latin`+`latin-ext` subset assertion; no direct glyph-coverage assertion (inherent to the subset, reasonable proxy).

---

## Requirement Traceability

| Requirement | New Status |
| ----------- | ---------- |
| IDF-01 | ✅ Verified |
| IDF-02 | ✅ Verified |
| IDF-03 | ✅ Verified |
| IDF-04 | ✅ Verified |
| IDF-05 | ✅ Verified |
| IDF-06 | ✅ Verified |
| IDF-07 | ✅ Verified |

---

## Summary

**Overall**: ✅ Ready

**Spec-anchored check**: 7/7 requirements covered with located, spec-matching assertions; 3 low-severity precision notes flagged (none blocking).
**Sensor**: 6/6 mutations killed.
**Gate**: 253 passed, 0 failed; tsc exit 0.

**What works**: Iron Gall palette pinned exactly in both modes with a committed WCAG-AA contrast gate; Source Serif 4 self-hosted and exposed as `--font-serif`; highlight tokens defined both modes with a no-leak scan; `.prose-reading` applied to reader prose and citation snippet; paper appearance scaffolded under a light-only scoped selector proven not to leak into chrome; corpus punctuation pass-through pinned.

**Issues found**: None blocking. Optional hardening: pin `--popover` hex; add a build-output font-self-host grep test (precision notes 1–2).

**Next steps**: PASS — no fix tasks required.
