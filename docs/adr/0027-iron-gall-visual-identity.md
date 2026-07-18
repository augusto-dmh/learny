# ADR-027: Iron Gall Visual Identity With A Paper Reading Appearance

- **Date**: 2026-07-18
- **Status**: Accepted (2026-07-18)
- **Deciders**: Augusto, Claude
- **Tags**: design, identity, typography, frontend, reader, product

## Context and Problem Statement

The student-experience research (reports and synthesis in
`docs/research/2026-07-18/student-experience/`) locked a reading-first product
direction with a bookish-scholarly identity envelope, then specified four
concrete visual directions in `rq05-design-identity.md`: A "Marginalia" (warm
scholarly, Literata, library green), B "Iron Gall" (cool inky scholarly-press,
Source Serif 4, Prussian blue), C "Tipografia" (Iberian humanist, Alegreya
superfamily, oxblood and gold), and D "Typescript" (studio minimal, Newsreader
plus a duospace utility face). The current UI is stock shadcn neutral with Geist
everywhere, so book prose is typographically indistinguishable from chrome — the
core gap every direction fixes. All four directions were rendered against a real
Portuguese-language chapter from the author's corpus in an interactive prototype
(all surfaces: reader, ask panel, citation popover, home cards; light and dark),
and the author chose against real text rather than specimens.

## Decision Drivers

- Reading-first: the identity must make the book the aesthetic and survive
  hours-long reading sessions, including nightly dark-mode study (the 14-day
  dogfood gate is won in evening sessions).
- Anti-default guard: the identity must not collapse into the generic
  AI-generated aesthetic (cream + display serif + terracotta) nor anonymous
  SaaS minimalism.
- Evolution, not rip-out: the shadcn token system and Geist chrome stay; the
  swap must be mostly a token rewrite plus a reading-face binding.
- The author's own taste, exercised on the prototype — the identity is worn
  daily by its one real user.

## Considered Options

- Direction A — "Marginalia" alone
- Direction B — "Iron Gall" alone
- Direction C — "Tipografia"
- Direction D — "Typescript"
- Direction B primary + Direction A as a scoped reading appearance (hybrid)

## Decision Outcome

Chosen option: **Iron Gall (B) as Learny's one identity, with Marginalia (A)
retained as an optional "Paper" reading appearance scoped to the reader
surface** — the author's call on the prototype, matching the research
recommendation (B primary, A runner-up) while keeping A's old-paper reading
mood available where it matters most.

Concretely:

- **Iron Gall is the app.** Source Serif 4 as the reading serif, Geist chrome
  unchanged, the rq05 Iron Gall palette (iron-gall blue-black ink, Prussian
  blue accent, cool rag-paper grounds) as the full shadcn token sweep in light
  and dark, `--radius: 0.25rem`, and the ink-line rule system as the signature
  (header rules, section-heading rules, and the reading-progress fill). Chips,
  popovers, cards, Home, Review — everything wears Iron Gall.
- **"Paper" is a reading appearance, not a second identity.** The reader's
  appearance control (the `Aa` popover, on the two-axis model the reading
  research documented) offers Default (Iron Gall surfaces) and Paper —
  Marginalia's warm paper ground, warm ink, and optionally Literata for prose —
  applied to the reading column only. App chrome, annotation apparatus, and
  every non-reader surface stay Iron Gall in both appearances. Dark mode
  remains the Iron Gall night palette regardless of appearance.
- **Adopted flourishes from the research:** warm marker highlight tokens
  (`--highlight-*`, direction-independent so annotation data never encodes a
  theme, and warm even on the cool field) and Typescript's streaming caret for
  Ask/Teach answers.

### Positive Consequences

- Strongest dark mode of the four directions carries the nightly study
  sessions the dogfood gate depends on.
- Smallest implementation delta of the strong candidates: token rewrite +
  `--font-serif` binding + `.prose-reading` + rule utilities; Geist and the
  component library stay.
- The signature ink-line is functional (reading progress), not decorative, so
  the identity reinforces the reading-first IA instead of decorating it.
- The Paper appearance gives the warm old-paper reading mood without the cost
  of maintaining two full identities.

### Negative Consequences

- Two reading-surface palettes (Default and Paper) must both pass contrast
  checks against highlights and inline annotations — a real, if small,
  ongoing QA surface.
- If Paper also swaps the prose face to Literata, two serif families ship in
  the bundle; if it does not, Paper is palette-only and loses some of
  Marginalia's character. The build cycle decides after weighing font payload.
- A cool, restrained identity depends on execution discipline; under-executed
  it risks reading as generic minimalism (flagged in the research as B's
  failure mode).

## Pros and Cons of the Options

### B primary + A as Paper appearance ✅ Chosen

- ✅ One identity to maintain; two reading moods where reading actually happens
- ✅ Matches the surveyed two-axis appearance model of serious reading apps
- ❌ Slightly more token machinery than B alone (a reader-scoped palette layer)

### B alone

- ✅ Simplest possible sweep
- ❌ Loses the warm paper reading mood the author explicitly wants available

### A alone

- ✅ Warmest scholarly mood, Literata is an excellent reading face
- ❌ Weaker dark mode; adjacent to the warm-paper AI default it must out-execute

### C "Tipografia"

- ✅ Most characterful; honors the Portuguese-language corpus
- ❌ UI font swap (Alegreya Sans) forces a QA pass over every screen; highest
  cost for the most taste-dependent payoff

### D "Typescript"

- ✅ Lowest color effort; the two-voice concept is genuinely novel
- ❌ Most restrained — under-executed it is indistinguishable from stock; the
  duospace voice serves note-heavy work better than reading itself

## Links

- `docs/research/2026-07-18/student-experience/rq05-design-identity.md` — the
  four direction specifications (palettes, faces, treatments, effort)
- `docs/research/2026-07-18/student-experience/synthesis.md` — fleet synthesis
  and provisional cycle scoping this decision unblocks
- ADR-026 — notes & second-brain domain model (highlight rendering this
  identity styles)
