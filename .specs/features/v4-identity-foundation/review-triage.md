# PR #36 review triage — v4-identity-foundation

Review: 6 lanes (security, requirements, test-coverage, architecture, regression,
performance). Security/performance/architecture/regression: zero findings.
Comments get deleted at cleanup; this file is the surviving record.

| # | Source | Finding (file:line) | Verdict | Action | Rationale |
|---|---|---|---|---|---|
| 1 | inline `3609513774` (tests lane) | `.prose-reading` declarations unguarded — only class presence tested (`frontend/app/globals.css:175`) | REAL | **FIX** | The file-content gate pins every token but not the class body, so dropping `font-family: var(--font-serif)` (the cycle's core move) would fail nothing. IDF-04's requirement text itself defines serif/19px/1.6/65ch, so a `cssBlock(".prose-reading")` assert is spec-anchored, cheap, and matches the established pattern. |
| 2 | requirements comment `5013556836` | IDF-01 "surface" only half-pinned: `--card` in PINNED, `--popover` only AA-pair-covered | REAL | **FIX** | Spec's surface token maps to both `--card` and `--popover`; one-line addition to the PINNED table closes it. |
| 3 | requirements comment | "No runtime third-party font request" asserted by construction, not by served-bundle test | REAL (observation) | WON'T FIX | `next/font/google` self-hosts at build time by construction; a CI-reproducible bundle grep requires running `next build` inside vitest (slow, network-dependent, duplicates the CI build job). The author's served-bundle inspection confirmed zero `fonts.g*` refs and `/_next/static/media` woff2s; spec AC wording ("build-time self-host") is satisfied by the binding assert. |
| 4 | requirements comment | IDF-07 visual-legibility leg author-manual, not independently demonstrated | REAL (observation) | WON'T FIX | jsdom applies no stylesheets — the leg is inherently manual. Served-bundle inspection was performed; the RFC-004 Cycle F 14-day dogfood gate is the standing visual sensor. Nothing further automatable at reasonable cost. |
| 5 | requirements comment (Notes) | Reader wrapper "loses" Tailwind Typography element styling (`prose prose-sm dark:prose-invert` removed) | FALSE (as regression) | NO ACTION | No typography plugin exists on `main` or in this PR — no dependency, no `@plugin`, no config (verified by grep; regression lane independently confirmed). The removed classes produced zero CSS, so no styling existed to lose. Element-level reading styling is future reader work (Cycles B/D). |
| 6 | requirements comment (Notes) | `globals.css` missing trailing newline | REAL (nit) | **FIX** (rides in #1's commit) | One-byte POSIX hygiene. |
| 7 | requirements comment | Portuguese diacritics covered via subset assert (proxy) | REAL (observation) | WON'T FIX | Spec AC1 literally requires "latin subset incl. Portuguese diacritics coverage"; Google's latin subset includes Portuguese diacritics and `latin-ext` adds insurance. The assert matches the spec's own wording. |
| 8 | architecture lane note (report-only) | 19px serif snippet inside the 320px popover worth a design look | BY DESIGN | NO ACTION | Spec IDF-04 explicitly applies `.prose-reading` to the citation popover snippet; rq05 Direction B styles the snippet as a serif block quotation. |

**Counts:** 8 findings/notes → 3 real-and-fixed (1 finding + 1 gap + 1 nit),
4 real-observations won't-fix with rationale, 1 false (misread of dead CSS),
1 by-design. Zero security/critical/performance/warning findings.
