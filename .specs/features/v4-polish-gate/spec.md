# v4-polish-gate (polish half) Specification

RFC-004 Cycle F, polish half only. The 14-day dogfood gate and its retrospective are
calendar-bound and explicitly out of this PR (see Out of Scope).

## Problem Statement

The Iron Gall identity shipped across Cycles A–E, but finishing seams remain: the
study heatmap runs on grayscale stock chart tokens, the ink-line signature exists
only as a single private reader component, `--destructive` is still stock shadcn
red outside the WCAG gate, and the contrast gate written in Cycle A never learned
about the Paper appearance, highlight legibility, or chart tokens. The dogfood
gate should start on a finished surface with the contrast machinery re-verified.

## Goals

- [ ] Every color token carries Iron Gall values (no stock/grayscale leftovers) in both modes.
- [ ] The WCAG gate covers every ground the app can render: Default light, dark, and Paper.
- [ ] The ink-line is a reusable signature applied per ADR-027 (header rules + progress fill), not a one-off.
- [ ] Known code papercuts closed (stale comment, near-invisible dark dialog scrim).

## Out of Scope

| Feature | Reason |
| --- | --- |
| 14-day dogfood gate + retrospective | Calendar-bound; runs after this PR merges; closes the RFC in a later session |
| Highlight color selection (wiring cyan/violet/green as product behavior) | Highlights have no color field in the domain (ADR-026 owns that model); tokens stay as direction-independent scaffolding |
| Visual/taste judgments needing a human eye (bookshelf look, landing look, heatmap geometry) | Sensor-blind from Cycle E; the dogfood gate is the instrument for these |
| Literata as a Paper prose face | Paper shipped palette-only in Cycle A; unchanged here |
| Any backend change | Presentation-only cycle |

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| Exact ramp/overlay/destructive hex values | Chosen at implementation to satisfy the contrast ACs, then pinned in `theme-tokens.test.ts` | ACs define the properties (monotonicity, ratios); pinning freezes the taste call once made | auto (ship-cycle) |
| "Intensity" metric for the heatmap ramp | WCAG relative luminance, strictly monotonic — decreasing with level in light mode, increasing in dark | Perceptually defensible and already computable by the existing test helpers | auto |
| Header-rule surfaces | Top-level screen headers: Home, Bookshelf, Review, Notes | ADR-027 names "header rules" as part of the signature; top-level screens are the bounded, enumerable set | auto |

**Open questions:** none — all resolved or logged above.

**Implicit-dimension sweep (Medium):** presentation-only cycle — no new inputs,
persistence, auth surface, concurrency, or external calls. Remaining dimensions
N/A for this scope.

## User Stories

### P1: The study heatmap wears Iron Gall ⭐ MVP

**User Story**: As the student, I want the Home heatmap rendered in the identity's ink ramp so the adherence surface I look at daily doesn't read as an unstyled default.

**Acceptance Criteria**:

1. (POL-01) WHEN `globals.css` is parsed THEN `--chart-1..5` SHALL be hex Iron Gall ramp values defined in both `:root` and `.dark`, with different values per mode.
2. (POL-02) WHEN the ramp tokens for heatmap levels 1→4 (`--chart-2..5`) are compared THEN their relative luminance SHALL be strictly monotonic in the mode-appropriate direction (darker with level in light, lighter with level in dark).
3. (POL-03) WHEN the top ramp value (`--chart-5`) is compared with `--background` THEN contrast SHALL be ≥ 3:1 in both modes (non-text UI component threshold), and all five hexes SHALL be pinned in `theme-tokens.test.ts`.
4. (POL-04) WHEN the existing heatmap tests run THEN the `data-level` thresholds and level mapping SHALL be unchanged (recolor only).

**Independent Test**: theme-tokens suite asserts pins + monotonicity + 3:1; study-heatmap suite stays green untouched.

### P1: The WCAG gate covers every ground the app renders

**User Story**: As the maintainer, I want the committed contrast gate to cover Paper, highlights, and destructive so a future token edit cannot silently break legibility on any surface.

**Acceptance Criteria**:

1. (POL-05) WHEN the Paper appearance block is parsed THEN paper `--foreground` on paper `--background`, `--card`, and `--popover`, and paper `--muted-foreground` on paper `--background` SHALL each be ≥ 4.5:1.
2. (POL-06) WHEN highlight legibility is checked THEN prose ink on `--highlight-yellow` SHALL be ≥ 4.5:1 on all grounds that can render a highlight: light `--foreground` on light `--highlight-yellow`, paper `--foreground` on light `--highlight-yellow`, and dark `--foreground` on dark `--highlight-yellow`.
3. (POL-07) WHEN `--destructive` is parsed THEN it SHALL be a hex Iron Gall-compatible red in both modes with `--destructive` on `--background` ≥ 4.5:1 per mode (its dominant usage is `text-destructive` error text), pinned in the gate.
4. (POL-08) WHEN the full theme-tokens suite runs THEN every pre-existing pin and AA pair SHALL remain asserted (no weakening or deletion).

**Independent Test**: run `theme-tokens.test.ts` alone; new describe blocks cover Paper/highlight/destructive; git diff shows no removed assertions.

### P2: The ink-line is a signature system

**User Story**: As the student, I want the ink-line rule to appear consistently (screen headers, reading progress, Home hero) so the identity's signature is recognizable rather than a one-off.

**Acceptance Criteria**:

1. (POL-09) WHEN `InkLine` is extracted to a shared component THEN the reader SHALL keep identical rendered behavior and test ids (`ink-line`, `ink-line-fill`), and existing reader tests SHALL pass unmodified.
2. (POL-10) WHEN the Home continue-reading hero renders with a position THEN it SHALL show an ink-line progress fill driven by the same `percent` value already displayed as text.
3. (POL-11) WHEN the Home, Bookshelf, Review, and Notes screen headers render THEN each SHALL carry the ink-line header rule (static rule, no fill — fills appear only where they encode real progress).

**Independent Test**: component tests assert the shared component renders rail+fill from a percent prop; screen tests assert the header rule's presence; reader tests untouched.

### P2: Papercuts closed

**User Story**: As the maintainer, I want the known code papercuts fixed before the dogfood window opens.

**Acceptance Criteria**:

1. (POL-12) WHEN a dialog or sheet overlay renders THEN its scrim SHALL come from a theme-aware `--overlay` token with distinct light/dark values (dark strong enough to separate the dialog from the night palette), pinned in the gate; `bg-black/10` SHALL no longer appear in `components/ui`.
2. (POL-13) WHEN `globals.css` is read THEN the Paper-appearance comment SHALL accurately describe the shipped Aa-popover wiring (stale "no toggle ships yet" text removed).

**Independent Test**: grep for `bg-black/10` returns nothing under `components/ui`; token pin test for `--overlay`; comment fixed in diff.

## Edge Cases

- WHEN the heatmap renders a zero-activity day THEN it SHALL keep `bg-muted` (level 0 is outside the ramp) — existing behavior, untouched.
- WHEN dark mode is active THEN Paper does not apply (light-only scaffolding per Cycle A); highlight-on-paper is therefore asserted under light only.
- WHEN the hero has no reading position (null continue state) THEN no ink-line fill SHALL render (nothing to encode).

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| --- | --- | --- | --- |
| POL-01..04 | P1 heatmap | 1 | Pending |
| POL-05..08 | P1 WCAG gate | 1 | Pending |
| POL-09..11 | P2 ink-line | 2 | Pending |
| POL-12..13 | P2 papercuts | 3 | Pending |

**Coverage:** 13 total, mapped to tasks at Tasks time.

## Success Criteria

- [ ] `theme-tokens.test.ts` gate covers chart, Paper, highlight, destructive, overlay tokens — all green.
- [ ] Full frontend suite + tsc + build green; backend untouched.
- [ ] No grayscale/stock token values remain in `globals.css`.
