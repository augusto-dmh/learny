# v4-identity-foundation Design

**Spec**: `.specs/features/v4-identity-foundation/spec.md`
**Status**: Approved (ship-cycle auto-decision; visual reference = approved "Learny Identity Prototype" artifact + rq05 Direction B)

---

## Architecture Overview

Pure frontend theming cycle. Everything lands in four surfaces:

1. `frontend/app/globals.css` — the Iron Gall token sweep (light + dark), highlight
   tokens, the `.prose-reading` component class, and the Paper appearance layer.
   All component styling continues to flow through the existing shadcn semantic
   tokens, so no component changes for color (rq05 finding: every surveyed
   component styles via tokens).
2. `frontend/app/layout.tsx` — Source Serif 4 bound via `next/font/google` as
   `--font-serif`, beside the existing Geist `--font-sans` binding.
3. `frontend/app/components/section-reader.tsx` + `frontend/app/components/citations.tsx`
   — the only component edits: apply `.prose-reading` to the reader prose wrapper
   and the citation popover snippet.
4. `frontend/tests/` — a mechanical WCAG-AA contrast test over the committed CSS,
   CSS-scoping tests for the Paper layer, class-presence component tests, and a
   corpus-text pass-through (no smart-quote rewriting) test.

No backend, no schema, no IA change (spec Out-of-scope). The ink-line signature
system, running head, streaming caret, and annotation/citation restyle are
explicitly deferred to Cycles B–D/F.

## Code Reuse Analysis

| Component | Location | How to Use |
|---|---|---|
| shadcn token bridge (`@theme inline`) | `frontend/app/globals.css:7-48` | Keep as-is; only `:root`/`.dark` values change. Add `--font-serif` + `--color-highlight-*` mappings so `font-serif` / `bg-highlight-*` utilities exist |
| Geist font binding pattern | `frontend/app/layout.tsx:15` | Mirror exactly for Source Serif 4 (`--font-source-serif` → `--font-serif` via the same `fontVars` style object) |
| `MessageResponse` (Streamdown) | `frontend/components/ai-elements/message.tsx:326` | Untouched. Verified: no typographer/smartypants plugin — corpus punctuation already passes through; IDF-06 pins this with a test |
| Static file-content test pattern | `frontend/tests/prod-image.test.ts` | Reuse for the WCAG contrast test, Paper-scoping test, and layout font-binding test (jsdom cannot resolve external stylesheets, so CSS assertions read `globals.css` as text) |
| Component test conventions | `frontend/tests/sources-screen.test.tsx`, `section-reader.test.tsx`, `citations.test.tsx` | Extend existing suites with class-presence assertions (vitest + Testing Library, `routedFetch` stubs) |

## Components

### Iron Gall token sweep (IDF-01)

- **Location**: `frontend/app/globals.css` `:root` / `.dark`
- Spec-pinned values (hex, verbatim per IDF-01): bg `#F6F7F6`/`#0F161B`, surface
  `#FFFFFF`/`#172128`, ink `#1B2733`/`#D9E2E8`, muted ink `#5D6B76`/`#7F93A0`,
  border `#DDE2E4`/`#263340`, primary `#22557A`/`#6FA9CC`, primary-fg
  `#F4F8FA`/`#0E1A22`; `--radius: 0.25rem`.
- Derived values (D-3, feature-local — adjustable if the AA test says otherwise;
  spec-pinned values are not):

  | Token | Light | Dark |
  |---|---|---|
  | `--card` / `--popover` | `#FFFFFF` | `#172128` |
  | `--card-foreground` / `--popover-foreground` | `#1B2733` | `#D9E2E8` |
  | `--secondary` | `#E9EEF1` | `#1E2B34` |
  | `--secondary-foreground` | `#1B2733` | `#D9E2E8` |
  | `--muted` | `#EDF0F1` | `#1C2830` |
  | `--accent` (hover wash) | `#E3ECF2` | `#223546` |
  | `--accent-foreground` | `#1B2733` | `#D9E2E8` |
  | `--input` | `#DDE2E4` | `#263340` |
  | `--ring` | `#22557A` | `#6FA9CC` |
  | `--sidebar` | `#F1F3F3` | `#131C22` |
  | `--sidebar-foreground` | `#1B2733` | `#D9E2E8` |
  | `--sidebar-primary` / `--sidebar-ring` | `#22557A` | `#6FA9CC` |
  | `--sidebar-primary-foreground` | `#F4F8FA` | `#0E1A22` |
  | `--sidebar-accent` | `#E3ECF2` | `#223546` |
  | `--sidebar-accent-foreground` | `#1B2733` | `#D9E2E8` |
  | `--sidebar-border` | `#DDE2E4` | `#263340` |

- `--destructive` and `--chart-*` keep their current oklch values — the spec's
  re-derive list excludes them (D-3).

### WCAG AA contrast test (IDF-01 AC2)

- **Location**: `frontend/tests/theme-tokens.test.ts`
- Parses `globals.css` as text, extracts the light/dark token blocks, computes
  WCAG relative-luminance contrast ratios in-test (~15 lines, no new dependency),
  and asserts ≥ 4.5:1 for every ink-on-background and fg-on-field pair in both
  modes: `foreground/background`, `card-foreground/card`,
  `popover-foreground/popover`, `primary-foreground/primary`,
  `secondary-foreground/secondary`, `accent-foreground/accent`,
  `muted-foreground/background`, `muted-foreground/muted`,
  `sidebar-foreground/sidebar`, `sidebar-primary-foreground/sidebar-primary`,
  `sidebar-accent-foreground/sidebar-accent`.
- Also asserts the spec-pinned hexes are literally present in both blocks (AC1)
  and `--radius: 0.25rem`.

### Reading serif binding (IDF-02)

- **Location**: `frontend/app/layout.tsx`, `frontend/app/globals.css`
- `Source_Serif_4({ subsets: ["latin", "latin-ext"], variable: "--font-source-serif" })`
  from `next/font/google` (build-time self-host — no runtime third-party font
  request by construction; Google's latin subset covers Portuguese diacritics,
  latin-ext added for safety). `fontVars` gains
  `"--font-serif": "var(--font-source-serif)"`; `<html>` className gains the
  font's `.variable`. `@theme inline` gains `--font-serif: var(--font-serif)` so
  the `font-serif` utility resolves. Geist chrome untouched.
- Test: static assertions over `layout.tsx` source (import, subsets incl. latin,
  variable binding) — the file-content pattern, since RootLayout renders `<html>`
  and cannot be mounted under Testing Library.

### Highlight tokens (IDF-03)

- **Location**: `frontend/app/globals.css`
- `--highlight-yellow #EFE3A0/#4E4620`, `--highlight-cyan #C2DEE8/#1F3F4A`,
  `--highlight-violet #D6D0EC/#37315D`, `--highlight-green #C9DFCF/#26412F`
  in `:root`/`.dark` + `--color-highlight-*` bridge entries in `@theme inline`.
  No component consumes them yet (annotation restyle is Cycle D/F); the token
  test asserts presence in both modes and that no other frontend file references
  the raw hexes (AC1).

### `.prose-reading` (IDF-04)

- **Location**: `frontend/app/globals.css` (`@layer components`), applied in
  `section-reader.tsx` (prose wrapper div, kept alongside its existing classes)
  and `citations.tsx` (popover snippet `<blockquote>`).
- `font-family: var(--font-serif); font-size: 19px; line-height: 1.6;
  max-width: 65ch; text-align: left; hyphens: none;` (ragged-right = default
  left alignment, never justify; `lang`-aware hyphenation off by default per
  spec).
- Component tests assert class presence on both surfaces (AC1 — class presence,
  not pixels).

### Paper appearance scaffolding (IDF-05)

- **Location**: `frontend/app/globals.css`
- Selector: `html:not(.dark) [data-appearance="paper"]` (D-2) overriding
  `--background #F4EFE5`, `--card`/`--popover #FCF9F2`, `--foreground`/
  `--card-foreground`/`--popover-foreground #27211A`, `--muted-foreground
  #6F6455`, `--border`/`--input #E2DACA` — token overrides cascade only within
  the attributed container, and the `html:not(.dark)` guard makes dark mode
  ignore the layer entirely (ADR-027: dark stays Iron Gall).
- No UI toggle and no consumer this cycle (the `Aa` popover is Cycle B). Proven
  by a CSS test: the paper block exists, carries the Direction-A hexes, is
  scoped under `html:not(.dark) [data-appearance=`, and its hexes appear
  nowhere in the unscoped `:root`/`.dark` blocks (AC1: chrome unaffected).

### Micro-typography (IDF-06)

- Corpus text: a component test renders `SectionReader` with served markdown
  containing straight quotes, apostrophes, `--`, and `...`, asserting the
  rendered text carries them verbatim (rendered == served; pins the verified
  no-smartypants behavior).
- UI copy: apply typographic punctuation only to author-owned strings in the
  files this cycle already touches (curly apostrophes, real ellipsis — e.g.
  `We couldn’t find that section.`); no repo-wide copy sweep (D-6).

## Error Handling Strategy

Not applicable — no runtime logic paths change; all states in touched components
are preserved as-is.

## Risks & Concerns

| Concern | Location | Impact | Mitigation |
|---|---|---|---|
| jsdom does not apply external stylesheets, so no component test can observe computed colors/scoping | `frontend/tests/*` | CSS regressions invisible to component tests | CSS assertions run as file-content tests over `globals.css` (established `prod-image.test.ts` pattern); visual sanity is IDF-07's running-app check |
| Reader prose wrapper already carries `prose prose-sm max-w-none`; `.prose-reading` adds a 65ch measure | `section-reader.tsx:263` | conflicting `max-width` (`max-w-none` vs 65ch) | `.prose-reading` sets `max-width: 65ch` in `@layer components`; drop the `max-w-none`/`prose-sm` utilities from the wrapper when applying the class so one source of truth remains |
| Derived token values are design-chosen, not spec-pinned | `globals.css` | an AA-failing derived pair | The contrast test gates them; derived values may be nudged, spec-pinned ones may not |
| Existing tests may assert copy strings that the punctuation pass touches | `frontend/tests/section-reader.test.tsx` | broken string asserts | Update the affected test strings in the same commit as the copy change |

## Tech Decisions (feature-local; project-level rows go to STATE.md as AD-118..120)

| Decision | Choice | Rationale |
|---|---|---|
| D-1 (AD-118) | WCAG check = committed vitest test parsing `globals.css`, not a standalone script | Runs in the existing frontend gate on every PR; a script would need separate CI wiring. Why-not: a script is runnable outside the test env — but nothing needs that |
| D-2 (AD-119) | Paper layer scoped `html:not(.dark) [data-appearance="paper"]` | Container-level var override + light-mode guard in one selector; dark ignores paper with zero extra rules. Why-not considered: `.dark [data-appearance="paper"]` re-override block — duplicates every token and drifts |
| D-3 | Derived (non-spec-pinned) token values as tabled above; `--destructive`/`--chart-*` untouched | Spec re-derive list excludes them; smallest diff. Why-not: re-deriving destructive risks AA regressions on error surfaces for zero spec value |
| D-4 | Serif = `Source_Serif_4` with `latin`+`latin-ext` subsets, `--font-source-serif` → `--font-serif` | Mirrors the Geist binding exactly; both subsets guarantee Portuguese diacritics. Why-not single `latin`: covers pt but the second subset is free insurance |
| D-5 | `.prose-reading` replaces `prose prose-sm max-w-none` on the reader wrapper | One measure/typography source of truth; avoids utility-vs-class specificity fights |
| D-6 (AD-120) | UI-copy punctuation pass limited to files this cycle touches | "Where cheap" per IDF-06; a repo-wide sweep is unreviewable noise in a theming PR |
