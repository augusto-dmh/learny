# Context — `v6-page-unit`

Decisions taken under the ship-cycle auto-decision rule (no user prompt): each lists the options
considered with why-recommend **and** why-not, the choice, and the rationale, so the call is
auditable without the conversation. None met the escalation bar (no product-direction change, no
provider lock, and every one had a defensible recommendation).

---

## AD-183 — Store words per day; derive pages at read time

- **(a) Store `words_read`, derive pages server-side from the quantum. — CHOSEN**
  *Why:* lossless, so partial pages accumulate across many small saves within a day instead of
  being rounded away on each one; the quantum stays a presentation constant that can change
  without a migration or a rewrite of history.
  *Why not:* the stored number is not the number displayed, so a reader inspecting the DB sees
  words where the UI says pages — one derivation step between storage and screen.
- **(b) Store `pages_read` directly.**
  *Why:* what is stored is what is shown; no derivation.
  *Why not:* each save would floor to whole pages, so a day of short saves could credit zero
  pages despite real reading, and re-defining the quantum would invalidate every stored row.

## AD-184 — The first save for a source credits zero

- **(a) No prior stored position → credit 0. — CHOSEN**
  *Why:* the counter answers "how much ground did you cover today"; with no baseline there is no
  evidence any ground was covered. Resuming a book at 50% must not claim half the book as today's
  reading. Conservative and honest under I-7 (the figure never flatters).
  *Why not:* the genuine first reading session of a brand-new book under-counts by exactly one
  save's worth of advance.
- **(b) Credit `words_before(new anchor)` on the first save.**
  *Why:* captures the first session's real progress when a reader does start at the beginning.
  *Why not:* indistinguishable from opening an already-read book at an arbitrary anchor, which
  fabricates a large day of "reading" from a single click — a durable, uncorrectable inflation.

## AD-185 — Land the counter in this cycle, so the pages figure ships

- **(a) Land it now (PAGE-05..09) and ship the pages total. — CHOSEN**
  *Why:* RFC-006 makes the figure conditional precisely on this; the approved artifact's tooltip
  format ("7 reviews · 9 pages") and totals row both assume it, and deferring means shipping a
  half-populated tooltip and returning to the same four files in a follow-up.
  *Why not:* it adds the cycle's only schema change and its only correctness-critical arithmetic,
  which is where the review risk concentrates.
- **(b) Defer to a follow-up task, per the RFC's fallback.**
  *Why:* smaller cycle, no migration, no write-path change.
  *Why not:* the heatmap ships visibly incomplete and the approved tooltip string has to be
  altered away from the accepted spec.

## AD-186 — Approved typography expresses through the Aa controls, never over them

- **(a) Apply the column spec through `--reading-size`/`--reading-leading`; leave the size and
  leading ladders untouched. — CHOSEN**
  *Why:* the Aa popover is shipped product (`READING_SIZES [17,19,21,23]`, `READING_LEADINGS
  [1.5,1.6,1.8]`, defaults 19/1.6) with persisted per-device settings; hardcoding the artifact's
  18.5px/1.62 would silently disable a control the reader already uses. The artifact's values
  and the shipped defaults differ by a hair, so nothing visual is lost. The genuinely new parts —
  paragraph rhythm, chapter-title treatment, column padding, paper tokens — are orthogonal to the
  ladders and land in full.
  *Why not:* the rendered column will not match the artifact's mockup to the half-pixel.
- **(b) Adopt the artifact's fixed values literally.**
  *Why:* pixel fidelity to the approved design.
  *Why not:* regresses a shipped accessibility-adjacent control, and the artifact never claimed
  authority over the Aa ladder.

## AD-187 — Interpolate within the current section, not across the whole chapter

- **(a) Keep the section-word-offset model and add a fractional term for travel through the
  current section. — CHOSEN**
  *Why:* preserves today's exactness at every section boundary (the value still equals the
  server's `percent_at` there) and makes the number continuous in between — which is precisely
  finding 4's complaint. Degrades safely: if the fraction cannot be measured it falls back to
  today's step behaviour.
  *Why not:* needs the current section's rendered extent, so it is more measurement code than a
  single container-scroll ratio.
- **(b) The artifact's approach: one ratio over the chapter scroll container.**
  *Why:* a few lines, no per-section measurement.
  *Why not:* scroll distance is not proportional to word count across sections of differing
  density, so the figure would drift away from the server's percent and disagree with it at the
  boundaries — trading a visible step for a persistent inaccuracy.

## AD-188 — The heatmap keeps `bg-chart-*`; no new colour variables

- **(a) Keep `LEVEL_CLASS` on `bg-muted` + `bg-chart-2..5`. — CHOSEN**
  *Why:* verified byte-identical to the artifact's `--lv1..lv4` in both themes
  (`globals.css:82-85` light, `:122-125` dark), so the approved ramp already ships. Introducing
  parallel `--lv*` variables would duplicate the ramp and invite drift, and the artifact itself
  says "no new colours".
  *Why not:* the class names read as chart tokens rather than as a heat ramp.
- **(b) Add `--lv0..--lv4` variables carrying the artifact's hexes.**
  *Why:* names that say what they are; matches the artifact's CSS literally.
  *Why not:* two definitions of one ramp in one stylesheet, which is exactly how themes drift.

## AD-189 — Page numbering is book-global and starts at 1

- **(a) Page 1 at the book's first word; chapters continue the count. — CHOSEN**
  *Why:* matches how a physical book reads and how the approved contents rail displays it
  (`p. 58` for a mid-book chapter); makes a page number a stable, shareable locator.
  *Why not:* a reader who opens a late chapter first meets a large page number with no context.
- **(b) Restart numbering per chapter.**
  *Why:* small numbers, no dependency on the book-level offset.
  *Why not:* "page 3" would then be ambiguous across the book, defeating the point of the unit.

## AD-192 — The heatmap frame is `role="group"`, not the artifact's `role="img"`

Raised as a SPEC_DEVIATION by the phase worker and independently flagged by the Verifier. The
approved artifact specifies `role="img"` with `aria-label="study activity heatmap, last 12 weeks"`
on the graph frame **and** `tabIndex=0` on active cells. Those two cannot both be honoured: ARIA
treats a `role="img"` subtree as presentational, so focusable descendants inside it are an
authoring error — PAGE-22's keyboard path would be built on a subtree assistive tech is told to
flatten.

- **(a) `role="group"`, approved label kept verbatim, each active cell named individually
  (`role="img"` + `aria-label="Mon, Jul 20: 7 reviews · 9 pages"`). — CHOSEN**
  *Why:* keeps every word of the approved label, makes the keyboard affordance real rather than
  nominal, and gives a screen-reader user exactly the content the visual tooltip shows. Empty days
  get neither role nor name, so silent grace (I-7) survives in the accessibility tree too.
  *Why not:* it is a visible divergence from a driver-approved artifact, so it must be surfaced at
  the merge gate rather than buried.
- **(b) Honour `role="img"` literally and drop the cell tab stops.**
  *Why:* literal fidelity to the approved artifact.
  *Why not:* silently deletes PAGE-22's keyboard requirement, which the same artifact asks for.
- **(c) Honour both literally.**
  *Why:* nothing is "changed".
  *Why not:* ships a known-invalid ARIA structure — focusable content inside a presentational
  subtree — which is worse than either coherent choice.

**Consequence, stated for the merge gate:** the shipped markup differs from the approved artifact
at exactly one attribute. No test asserted either role, so nothing was weakened to accommodate it.

## AD-191 — `pages` is a required field on the client mirror type; the protected fixtures widen

Discovered mid-Execute: `frontend/tests/study-heatmap.test.tsx` builds `StudyDayView` fixtures
without `pages` and uses `satisfies StudySummaryView`, so a required new field fails `tsc` on the
very file I-PU-8 protects.

- **(a) Type `pages: number` as required; widen the fixtures; amend I-PU-8 to protect the
  assertions rather than the file's bytes. — CHOSEN**
  *Why:* the client type is a hand-maintained mirror of the wire, and the server always sends
  `pages` (a required Pydantic field). Typing it as maybe-absent would be a small untruth that
  every future consumer inherits, and would silently render 0 if the field ever went missing
  instead of failing the build. I-PU-8's actual content is that the redesigned markup does not
  disturb the adherence sentence — adding a field to a fixture does not weaken that assertion by
  one bit, so the invariant was over-specified when written as "unedited".
  *Why not:* it edits a file the spec named as protected, so the amendment must be explicit
  (done, in `spec.md`) rather than argued after the fact at review.
- **(b) Type `pages?: number` optional and render `?? 0`, leaving the file untouched.**
  *Why:* satisfies the original wording literally; zero edits to the protected test.
  *Why not:* the mirror understates the contract, and the `?? 0` fallback converts a wire
  regression into a silently wrong figure instead of a build failure.

**Bound:** weakening, retargeting, or deleting any assertion in that file remains forbidden.

## AD-190 — One shared header-offset value feeds both the bar and the scroll margin

- **(a) Single source for the sticky header's height, consumed by both the bar and each
  section's scroll margin. — CHOSEN**
  *Why:* the drift between a content-sized bar and a literal `scroll-mt-16` is the actual cause
  of finding 3; tying them together fixes the class of bug rather than the current instance.
  *Why not:* fixes the bar's height where it is currently content-driven.
- **(b) Re-tune the magic number to match today's rendered height.**
  *Why:* one-character change.
  *Why not:* re-breaks the moment the bar's padding, font, or contents change — which Cycle D
  will do when the topbar gains the contents toggle and dock controls.
