# v4-polish-gate — Context & Decisions

Cycle: RFC-004 Cycle F, polish half. The dogfood gate itself (14 consecutive days
of real study + retrospective) is calendar-bound and excluded from this PR; it
opens when this PR merges.

All decisions below were auto-decided per the learny-ship-cycle contract
(recommended option chosen, options + rationale recorded here; none met the
escalation rule — no product-direction change, no new provider/dependency).

## D-1 — Heatmap identity: restyle global chart tokens (AD-157)

- **Options**: (a) give `--chart-1..5` Iron Gall hex ramps in both modes — recommended: the tokens exist exactly for this, the heatmap is their only consumer, and any future chart inherits the identity for free; why-not: chart tokens are nominally categorical in shadcn, and we redefine them as a sequential ramp. (b) add a dedicated `--heatmap-*` ramp and leave `--chart-*` grayscale — why-recommend: preserves categorical semantics; why-not: leaves stock grayscale tokens shipping in the identity (the exact gap this cycle closes) and duplicates token machinery for one consumer.
- **Chosen**: (a). The ramp tops out at the mode's primary (`#22557A` light / `#6FA9CC` dark) so the signature accent anchors the scale; heatmap keeps its existing `chart-2..5` level mapping and `data-level` thresholds (recolor only — Cycle E's pinned threshold tests stay untouched).

## D-2 — Annotation restyle completion = contrast-proofing, not color wiring (AD-158)

- **Options**: (a) wire cyan/violet/green highlight tokens into `.reader-highlight`/margin-rail as selectable colors — why-recommend: completes the four-token set visibly; why-not: highlights carry no color field in the domain (ADR-026), so this needs schema + API + capture-UI changes — a feature, not polish, and a polish PR must not amend the annotation domain model. (b) keep the three unused tokens as direction-independent scaffolding and complete the restyle as *legibility proof*: prose-ink-on-highlight contrast asserted on every ground that can render a highlight (light, Paper, dark) — recommended.
- **Chosen**: (b). ADR-027's negative consequence ("both palettes must pass contrast against highlights") becomes a committed test instead of a QA intention.

## D-3 — WCAG re-verification scope (AD-158 cont.)

The Cycle A gate (`theme-tokens.test.ts` AA_PAIRS, both modes) is extended, never weakened: Paper-appearance text pairs, highlight legibility pairs (D-2), `--destructive` normalized from stock shadcn oklch red to Iron Gall-compatible hex in both modes and entered into the gate, chart-ramp pins + monotonic-luminance + 3:1 top-vs-background. Rationale: the gate only knows tokens Cycle A knew; every token family added since (paper, highlight consumers, charts) is currently unguarded.

## D-4 — Ink-line signature system shape (AD-159)

- **Options**: (a) CSS utility class only — why-recommend: cheapest; why-not: the fill variant needs a percent prop and testids, which CSS can't carry, so the reader keeps a divergent private copy. (b) shared `InkLine` component (static rule + optional progress fill), adopted on the ADR-027 surfaces: reader progress (existing, moved), Home hero progress fill (functional — reuses the `percent` the hero already displays as text), and static header rules on the four top-level screens (Home, Bookshelf, Review, Notes) — recommended. (c) also add decorative primary "tick" fills to static rules — why-not: ADR-027 says the signature is functional, not decorative; a fill must encode real progress.
- **Chosen**: (b), explicitly rejecting (c)'s decorative fills. Reader behavior and testids (`ink-line`, `ink-line-fill`) stay byte-identical to keep existing reader tests unmodified.

## D-5 — Dialog/sheet scrim token (AD-160)

- **Options**: (a) keep `bg-black/10` — why-recommend: zero work; why-not: it is the tree's only default-palette leftover, and a 10% black scrim over the `#0F161B` night palette is nearly invisible — a real dark-mode papercut for the nightly-study sessions the identity was chosen for. (b) theme-aware `--overlay` token (ink-tinted scrim in light, materially stronger black in dark), bridged via `--color-overlay`, used by `dialog.tsx`/`sheet.tsx`, pinned in the gate — recommended.
- **Chosen**: (b).

## D-6 — Execution shape

Medium sizing: frontend-only, 3 phases (tokens+gate / ink-line / papercuts), ≤3 phases → executed inline by the orchestrator per tlc auto-sizing (no worker offer). Verifier runs as the mandatory fresh subagent afterward. Model: session model (Fable) inline; Verifier per ship-cycle cost table.
