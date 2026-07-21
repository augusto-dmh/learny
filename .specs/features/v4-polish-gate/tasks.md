# v4-polish-gate — Tasks

3 phases, executed inline (≤3 phases → no workers). One atomic commit per task;
tests derive from spec ACs; scoped gate per commit (`theme-tokens` / touched
suites), full frontend suite + tsc + build at each phase boundary.

## Phase 1 — Tokens + WCAG gate (POL-01..08)

- [x] **T1** Chart ramp: `--chart-1..5` → Iron Gall hex ramp, both modes (tops at mode primary). Tests: pinned hexes; strict monotonic luminance over `--chart-2..5` (darker-with-level light, lighter-with-level dark); `--chart-5` vs `--background` ≥ 3:1 both modes. Heatmap component/tests untouched. (POL-01..04)
- [x] **T2** Destructive: stock oklch → Iron Gall-compatible hex, both modes; gate pair `--destructive` on `--background` ≥ 4.5:1 per mode + pins. Check the button destructive variant still reads. (POL-07)
- [x] **T3** Ground coverage: AA pairs for Paper (fg on bg/card/popover, muted-fg on bg) + ink-on-highlight on light/paper/dark grounds. If a shipped value fails a new pair, retune the token (never the threshold) and note it. No existing assertion removed. (POL-05, POL-06, POL-08)

## Phase 2 — Ink-line signature (POL-09..11)

- [x] **T4** Extract shared `InkLine` (static rule + optional fill percent; testids `ink-line`/`ink-line-fill` preserved); reader consumes it; reader tests pass unmodified. (POL-09)
- [x] **T5** Home hero progress fill from the existing `percent`; no fill when continue state is null. (POL-10)
- [x] **T6** Static header rules on Home, Bookshelf, Review, Notes screen headers; screen tests assert presence. (POL-11)

## Phase 3 — Papercuts (POL-12..13)

- [x] **T7** `--overlay` token (light ink-tinted, dark stronger) + `--color-overlay` bridge; `dialog.tsx`/`sheet.tsx` scrims use it; pin test; `bg-black/10` gone from `components/ui`. (POL-12)
- [x] **T8** Fix stale Paper comment in `globals.css` (Aa toggle shipped). (POL-13)

## Dependencies

T1–T3 independent of Phase 2/3. T5, T6 depend on T4. T7, T8 independent.
