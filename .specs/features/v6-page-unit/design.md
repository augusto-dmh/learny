# Design — `v6-page-unit`

## Shape

Three slices, in dependency order. A is the only one that touches schema and the wire; B and C
are independent of each other and both consume A.

```
A  backend      the quantum + per-day words counter + pages on the wire
    │
    ├── B  frontend reader    typography · page rules · header offset · live percent
    └── C  frontend heatmap   grid fix · axes · legend · tooltips · pages total
```

## A — The unit and the counter (backend)

**The quantum.** A `words_per_page` setting (default 275) joins the existing `LEARNY_*` settings.
It is the sole definition; both the page-rule label on the reader and the per-day pages figure
resolve to it, and it reaches the reader through the chapter response (PAGE-02) so no client
duplicates the number.

**Page derivation** is pure and lives beside `percent_at` in `app/application/reading.py`, which
already owns the "words before a point" idiom (`percent_at` at `reading.py:92`,
`words_before_chapter` at `reading.py:217`). Page 1 begins at the book's first word; the page
containing a point is a function of the words before it and the quantum. Because
`words_before_chapter` is already in the chapter payload, the reader's first rule continues the
book's numbering without a new endpoint.

**The counter.** `study_days` (metadata.py:711) gains one integer column beside `reviews_count`
and `reading_updates`, added by a migration chained off `0015_study_days`, `NOT NULL` with a
server default so existing rows need no backfill. `StudyDay` (entities.py:1030) and
`StudyDayRepository.record` (ports.py:1208) grow the matching field/parameter; the SQL upsert
(`repositories.py:2078`) increments it exactly like the existing counters — the AD-153 atomic
`INSERT … ON CONFLICT DO UPDATE` pattern, unchanged in kind.

**The credit** is computed in `SaveReadingPosition.__call__` (`reading.py:259`), which already
resolves the anchor against the chapter index and already writes the study day on the same
connection. It gains one read — the prior stored position — and derives the advance from the two
rows' word offsets. The arithmetic is deliberately conservative (see AD-184/AD-185): floored at
zero, and zero whenever there is no usable baseline.

**On the wire**, `StudySummaryView` (web/study.py:35) gains a per-day pages figure derived
server-side from the stored words and the quantum. The stored words stay an implementation
detail of the rollup.

## B — The reading column (frontend)

`ChapterFlow` (`chapter-reader.tsx:282`) already renders the prose article with the Aa controls'
`--reading-size`/`--reading-leading` bound inline (`:715-724`), and `.prose-reading`
(`globals.css:178`) holds the typographic base. The approved column spec is applied **through**
those variables, never over them (AD-186).

**Page rules** are inserted between paragraphs while walking a section's rendered blocks,
accumulating words with a carry across boundaries. The insertion is presentational scaffolding:
`aria-hidden`, non-selectable, and it must never split a paragraph, which is what makes
"between blocks, never inside one" the sensor-worthy property rather than the pixel styling.

**The header offset.** Today `FlowSection` carries a literal `scroll-mt-16` (`:837`) that must
match the sticky bar's real height (`:662-701`, content-driven `py-2`). The two can drift
independently — that is finding 3's "prose slides under the header". One shared value must feed
both the bar's height and the sections' scroll margin.

**Live progress.** Today `bookPercent` (`:391`) is a step function: it sums whole sections before
`currentAnchor`, so it only moves when the observed section changes — exactly finding 4. The fix
adds a fractional term for how far the viewport has travelled *through* the current section (see
AD-187), keeping the existing section-boundary values exact. `chapterMinutesLeft` (`:397`) and
`InkLine` (`:703`) consume the same value, and the display string at `:691` is unchanged.

## C — The heatmap (frontend)

`study-heatmap.tsx` keeps its data contract, its fetch, and `buildCells`' densification. The
change is presentational, as the artifact's own footer states.

**The defect** is at `:143`: `grid-flow-col grid-rows-[repeat(7,minmax(0,1fr))]` declares rows
but no column track, so implicit `auto` columns stretch. Fixed-width implicit columns plus
start alignment is the fix.

**The ramp needs no new colours.** `LEVEL_CLASS` (`:47`) maps levels 1–4 onto `bg-chart-2..5`,
and those tokens are byte-identical to the artifact's `--lv1..lv4` in both themes
(`globals.css:82-85` light, `:122-125` dark). Level 0 stays `bg-muted`. AD-188 keeps the existing
classes rather than duplicating the ramp as new variables.

**Axes, key, and tooltips** are additive scaffolding around the same cells. The tooltip replaces
today's `title` attribute (`:154`) — which only appears on hover and never on keyboard focus —
with an element shown on both, still only for active days, so I-7's silent grace survives intact.

**The readout** wraps its digits in styled spans without changing `textContent` (I-PU-8), and
gains reviews and pages totals summed from the same window rows.

## Decisions

Recorded as AD-183..AD-190 in `context.md` and `.specs/project/STATE.md`.

## Risks

- **Credit arithmetic is the correctness-critical surface.** It sits on a write path that already
  commits two things atomically; a wrong sign or a missing floor silently inflates a durable
  counter that nothing else recomputes. Hence I-PU-4/5/6 each carry a sensor.
- **The byte-identical sentence** is an existing green assertion that must not be edited. Any
  markup change to the adherence line risks it; the test itself is the sensor.
- **Interpolation crossing into persistence** would violate I-PU-3 quietly — the save payload
  shape is the sensor.
