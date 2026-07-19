# v4-identity-foundation — Decisions (ship-cycle auto-decision record)

Decisions taken under the ship-cycle auto-decision rule (recommended option
selected, options + rationale recorded here and in STATE.md). None met the
escalation criteria: the product direction (Iron Gall, Direction B + stolen
elements) was already locked by the user via ADR-027 and the approved prototype;
no new external dependency beyond the already-sanctioned `next/font/google`
self-hosted face.

- **AD-118 — WCAG AA verification ships as a committed vitest test
  (`frontend/tests/theme-tokens.test.ts`) parsing `globals.css`, not a
  standalone script.**
  - Options: (a) vitest test in the existing frontend gate — *recommended*:
    runs on every PR with zero new CI wiring, fails the build on any future
    token edit that breaks a pair; why-not: contrast math lives in test code,
    not reusable as a CLI. (b) standalone Node script committed under
    `frontend/scripts/` — why-recommend: runnable ad hoc outside vitest;
    why-not: needs its own CI step to actually gate, and nothing else needs a
    CLI. Spec AC only demands "a committed check (script or test)".
  - Chose (a).

- **AD-119 — Paper appearance layer scoped with
  `html:not(.dark) [data-appearance="paper"]`.**
  - Options: (a) single guarded selector — *recommended*: token overrides
    cascade only inside the attributed container AND only in light mode; dark
    ignores Paper (ADR-027) with zero duplicate rules; why-not: slightly higher
    selector specificity to reason about. (b) unguarded
    `[data-appearance="paper"]` plus a `.dark [data-appearance="paper"]` block
    re-asserting Iron Gall dark values — why-recommend: flat specificity;
    why-not: duplicates every dark token, drifts when the dark palette changes.
  - Chose (a).

- **AD-120 — Micro-typography discipline applies only to UI copy in files this
  cycle touches; corpus text pass-through is pinned by test.**
  - Options: (a) touched-files-only copy pass — *recommended*: honors IDF-06
    "where cheap", keeps the theming PR reviewable; why-not: straight
    apostrophes survive elsewhere in the app until those files are next
    touched. (b) repo-wide copy sweep — why-recommend: uniform punctuation
    everywhere at once; why-not: dozens of string diffs + test-string churn in
    a PR that is supposed to be tokens/typography, exactly the noise IDF-06's
    "where cheap" guards against.
  - Chose (a).

Feature-local (no AD row): derived token values table (design D-3),
`Source_Serif_4` subsets `latin`+`latin-ext` (D-4), `.prose-reading` replaces
the reader wrapper's `prose prose-sm max-w-none` utilities (D-5).

Tooling: no MCPs; skills = tlc-spec-driven (this cycle) + learny-finalize at
publish. Executed inline (3 phases).
