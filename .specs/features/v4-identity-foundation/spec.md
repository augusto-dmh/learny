# Spec — v4-identity-foundation (RFC-004 Cycle A: Iron Gall tokens, fonts, reading typography)

Scope source: RFC-004 Cycle A; binding design decision ADR-027 (Iron Gall
primary + "Paper" reading appearance scoped to the reader); exact palettes,
faces, and treatments in docs/research/2026-07-18/student-experience/
rq05-design-identity.md (Direction B, stealing B's warm markers and D's
streaming caret) — the rendered prototype the user approved is the visual
reference. This cycle ships the direction-independent floor plus the Iron Gall
token sweep; the ink-line *signature system* and annotation/citation restyle
land later with their host surfaces (synthesis tension #3/#4 — do NOT build
them here).

## Requirements

- **IDF-01 — Iron Gall token sweep.** `frontend/app/globals.css` replaces the
  stock-neutral shadcn palette with rq05 Direction B, light AND dark: bg
  #F6F7F6/#0F161B, surface #FFFFFF/#172128, ink #1B2733/#D9E2E8, muted
  #5D6B76/#7F93A0, border #DDE2E4/#263340, accent (primary) #22557A/#6FA9CC,
  accent-fg #F4F8FA/#0E1A22; `--radius: 0.25rem`. All existing semantic tokens
  (`--background --foreground --card --popover --primary --secondary --muted
  --accent --border --input --ring --sidebar-*`) re-derived from these; no
  component files change for color.
  - AC1: light and dark blocks both carry the exact hex values above.
  - AC2: every ink-on-background and accent-fg-on-accent pair passes WCAG AA
    (4.5:1 text) in both modes — verified by a committed check (script or test),
    not by eye.
- **IDF-02 — Reading serif binding.** Source Serif 4 self-hosted via
  `next/font/google` in `app/layout.tsx`, exposed as `--font-serif` beside the
  existing Geist `--font-sans`; Geist chrome unchanged.
  - AC1: layout binds the font with latin subset incl. Portuguese diacritics
    coverage; no runtime third-party font requests (build-time self-host).
- **IDF-03 — Highlight tokens (direction-independent).** New `--highlight-yellow
  #EFE3A0/#4E4620`, `--highlight-cyan #C2DEE8/#1F3F4A`, `--highlight-violet
  #D6D0EC/#37315D`, `--highlight-green #C9DFCF/#26412F` (light/dark) — warm
  markers on the cool field per rq05; annotation data never encodes a theme.
  - AC1: tokens exist in both modes; nothing else references raw highlight hex.
- **IDF-04 — `.prose-reading`.** A reading-typography class applied to the
  existing section reader's prose AND the citation popover snippet: serif 19px,
  max-width ~65ch, line-height 1.6, ragged-right, `lang`-aware hyphenation off
  by default.
  - AC1: section-reader prose and citation snippet render under the class
    (component test asserts the class presence, not pixels).
- **IDF-05 — Paper appearance scaffolding.** A reader-scoped token layer
  (`[data-appearance="paper"]` or equivalent) carrying rq05 Direction A's warm
  reading surface (bg #F4EFE5, surface #FCF9F2, ink #27211A, muted #6F6455,
  border #E2DACA) applied ONLY within the reading surface container; dark mode
  ignores it (ADR-027: dark stays Iron Gall). No UI toggle yet — the `Aa`
  popover ships in Cycle B; this cycle proves the layer works via a test.
  - AC1: tokens scoped so app chrome outside the reader is unaffected.
- **IDF-06 — Micro-typography pass.** Corpus-derived Markdown rendering applies
  typographic punctuation discipline where cheap (quotes/dashes already in
  corpus text pass through untouched; no smart-quote rewriting of book text —
  discipline applies to UI copy only).
  - AC1: no transformation of corpus text content (explicit test: rendered
    text equals served text).
- **IDF-07 — Suite integrity.** Frontend tests + tsc green; visual sanity via
  the running app (money-path screens render legibly under both modes).

## Out of scope (explicit)

Ink-line rule system + running-head/progress (Cycle B, ships with the reader),
streaming caret (Cycle C), annotation/citation restyle beyond `.prose-reading`
(Cycle D/F), the `Aa` popover UI (Cycle B), any backend change, any IA change.

## Execution notes for the next session

- Branch exists: `feat/v4-identity-foundation`. Resume ship-cycle at Stage 1.
- The approved prototype (Claude artifact "Learny Identity Prototype") is the
  visual reference; rq05 has the full spec including shadcn-token override list.
- Verify WCAG pairs mechanically (small script over the hex pairs) — rq05
  claims AA but the committed check is the AC.
- `frontend/tests/` conventions: vitest + Testing Library; follow
  sources-screen.test.tsx patterns.
