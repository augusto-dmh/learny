# Validation — `v6-page-unit`

**Verdict: PASS**, with two surviving mutants (both presentation-only, no invariant compromised).

- **Diff verified:** `main..HEAD` on `feat/page-unit` — 12 commits, 45 files
  (`20e96b3b..88e6c7b3`).
- **Verifier:** independent of the authoring phases; coverage re-derived from `spec.md` and
  `approved-artifact-spec.md`, not from commit messages or test names.

## Gates (run by the verifier, not reported)

| Gate | Result |
| --- | --- |
| `backend $ uv run pytest` | 1785 passed, 11 skipped, **1 failed** — `test_eval_retrieval_metrics.py::TestDeterministicRetrievalMetrics::test_metrics_meet_thresholds`, the documented local-only pgvector HNSW recall variance. Matches baseline exactly. |
| `backend $ ruff check .` | All checks passed |
| `backend $ ruff format --check .` | 245 files already formatted |
| `frontend $ npm test` | 604 passed across 61 files. Matches baseline exactly. |
| `frontend $ npx tsc --noEmit` | clean (exit 0) |
| `git status` after all mutations reverted | clean except `.specs/.ship-status` (written by the ship-cycle lead, not by this verification) |

## Per-requirement evidence

`file::test` names are abbreviated to the test function/`it()` name.

### The unit (backend)

| Req | Status | Evidence |
| --- | --- | --- |
| PAGE-01 | COVERED | `backend/tests/test_config.py::test_words_per_page_default`, `::test_words_per_page_env_override` — default 275, `LEARNY_WORDS_PER_PAGE` override. Documented in `backend/.env.example`. |
| PAGE-02 | COVERED | `backend/tests/test_web_reading.py::test_get_chapter_carries_the_page_size_from_settings` — asserts the response value *changes* when the setting changes, which a duplicated client constant could not do. Field presence pinned by `::test_get_chapter_returns_200_with_shape_and_sections`. |
| PAGE-03 | COVERED | `backend/tests/test_reading_pure.py` — `test_page_at_starts_at_page_one_at_the_first_word`, `test_page_at_advances_one_page_per_quantum`, `test_page_at_follows_the_quantum_it_is_given`, `test_page_at_does_not_depend_on_the_length_of_the_book`, `test_page_at_degrades_to_page_one_for_a_non_positive_quantum`. Pure module import, no DB, no HTTP. |
| PAGE-04 | COVERED | `test_page_at_continues_the_books_numbering_into_a_later_chapter` (unit) + `backend/tests/test_web_reading.py::test_get_chapter_page_size_accompanies_the_chapters_word_offset` (chapter 2 opens on page 3 from `words_before_chapter=600`). |

### Per-day reading volume (backend)

| Req | Status | Evidence |
| --- | --- | --- |
| PAGE-05 | COVERED | `backend/tests/test_migrations.py::test_migration_0016_adds_reading_volume_without_touching_the_corpus` — NOT NULL, pre-existing row takes 0 with no backfill, fresh row defaults 0, downgrade drops the column and keeps rows. Chained off `0015_study_days` (`0016_reading_volume.py:34`). |
| PAGE-06 | COVERED | `backend/tests/test_repositories_study.py::test_record_stores_the_words_advanced_it_is_given`, `::test_record_accumulates_words_advanced_across_a_days_saves`, `::test_record_without_words_leaves_the_days_volume_untouched` — real Postgres, ON CONFLICT increment path. |
| PAGE-07 | COVERED | Unit: `test_reading_pure.py::test_words_credited_is_the_ground_covered_since_the_prior_position`, `..._is_zero_when_the_reader_moves_backwards`, `..._is_zero_for_a_save_at_the_same_place`, `..._is_zero_without_a_prior_position`, `..._is_zero_when_the_prior_anchor_no_longer_resolves`, `..._resolves_a_prior_anchor_by_alias`. Service: `test_application_reading.py::test_save_reading_position_credits_the_ground_covered_since_the_last_save`, `..._first_ever_save_credits_no_words`, `..._moving_backwards_credits_no_words`, `..._credits_each_advance_from_the_new_baseline`, `..._stale_prior_anchor_credits_zero_and_still_saves`. |
| PAGE-08 | COVERED | `backend/tests/test_web_reading.py::test_put_reading_position_rejected_save_stores_and_credits_nothing` — 404, no `reading_positions` row, **no `study_days` row at all** (not a zero-word row). Fake-level: `test_application_reading.py::test_save_reading_position_bad_anchor_credits_no_study_day`. |
| PAGE-09 | COVERED | `backend/tests/test_web_study.py::test_study_days_serves_pages_derived_from_the_stored_words` (274→0, 550→2, and the response key set is exactly `{day, reviews_count, reading_updates, pages}` — the raw words never reach the wire), `::test_study_days_pages_follow_the_settings_quantum`. Floor pinned by `test_reading_pure.py::test_pages_from_words_counts_whole_pages_and_floors_the_remainder`. |
| PAGE-10 | COVERED | `backend/tests/test_web_study.py::test_study_days_reading_volume_leaves_the_shading_counters_alone` — two days with identical counters and wildly different volume report identical `reviews_count`/`reading_updates`. Plus `test_repositories_study.py::test_record_without_words_leaves_the_days_volume_untouched`. |

### The reading column (frontend)

| Req | Status | Evidence |
| --- | --- | --- |
| PAGE-11 | COVERED | `frontend/tests/reading-column.test.tsx::sets the column on one measure with paragraph rhythm and foot room`, `::gives the chapter a quiet running title in the book's own serif`, `::renders the chapter title at the head of the reading column`, `::keeps the warm paper surface on the reading column only`. |
| PAGE-12 | COVERED | `reading-column.test.tsx::hands the reader's chosen type size and spacing to the column`, `::reads its type size and line height from the reading variables` (asserts the stylesheet never pins `18.5px` and that `.book-column` declares no `font-size`/`line-height`). |
| PAGE-13 | COVERED | `frontend/tests/page-rules.test.tsx::draws a rule at each page boundary, between paragraphs and never inside one`, `::never rules off the end of the section`, `::carries the remainder across boundaries instead of restarting the count`, `::hides the rules from assistive technology`, `::defers a boundary that falls on a list or a heading to the next paragraph`, `::never breaks inside a fenced code block`, `::leaves a section with no boundary in it exactly as it was served`. |
| PAGE-14 | COVERED | `page-rules.test.tsx::labels each rule with the page that starts below it`, `::continues the book's numbering rather than restarting for the chapter`, `::keeps numbering running across the chapter's sections`. |
| PAGE-15 | COVERED | `frontend/tests/reader-chrome.test.tsx::reserves exactly the sticky chrome's height above every section` — asserts equality between the chrome's laid-out height and every section's `scrollMarginTop`, so the two cannot drift. |
| PAGE-16 | **PARTIAL** | Continuity, monotonicity and the section-end ceiling are covered by `frontend/tests/chapter-reader.test.tsx::moves the percentage as the reader scrolls within one section`. The spec's explicit **"clamped to 0..100"** is unsensed — see gap 1. |
| PAGE-17 | COVERED | Same test: asserts the literal string `"25% read · 2 min left"` and that `ink-line-fill` width is `25%` from the same live value. |
| PAGE-18 | COVERED | `chapter-reader.test.tsx::keeps the position save carrying the anchor alone` — the payload is asserted `toEqual({ anchor: S2 })` *after* the shown percentage has been interpolated to 25%. |

### The study heatmap (frontend)

| Req | Status | Evidence |
| --- | --- | --- |
| PAGE-19 | COVERED | `frontend/tests/study-heatmap.test.tsx::lays the cells on a fixed column track instead of stretching to the card` (asserts `gridAutoColumns: 15px`, explicitly `not "auto"`, `repeat(7, 15px)`, `gap 4px`, `justifyContent: start`), `::hangs both axes off the same tracks as the cells`. |
| PAGE-20 | COVERED | `::places each month's label over the column its first day lands in`, `::does not label the final column, which has no column left to carry it`, `::names the weekday rows Mon/Wed/Fri and hides the axis from assistive tech`. |
| PAGE-21 | COVERED | `::names the five levels with a Less→More key and labels the window`. |
| PAGE-22 | COVERED | `::shows the day's reviews, pages, and date on hover`, `::shows the same readout on keyboard focus, not only on hover`, `::counts of one read in the singular`, `::takes the readout away on mouse leave, on blur, and on scroll`, `::leaves empty days silent: no readout, no title, and no way to focus one`, `::keeps the readout out of the tab order and off the focused cell`. |
| PAGE-23 | **PARTIAL** | Empty-cell hairline covered by `::gives real cells a hairline edge and leaves placeholders blank`. Today's **ring** is asserted only through `data-today` (`::rings today's cell and only today's`), not through the visual treatment — see gap 2. |
| PAGE-24 | COVERED | `::sets the adherence figures in tabular mono without touching the sentence` (`textContent === "Studied 11 of the last 14 days"`, figure carries `font-mono`/`tabular-nums`), `::totals the window's reviews and its pages beside the adherence figure`. |
| PAGE-25 | COVERED | `::totals the window's reviews and its pages beside the adherence figure` — 9+24+7 = 40 pages, figures deliberately unrelated to the counters so a client-side derivation would disagree. `::reads zero for both totals when the window is empty`. |
| PAGE-26 | COVERED | `::keeps the existing test hooks and the 84-day window` (`study-heatmap` testid, 84 `heatmap-cell`s, `data-day`, `data-level`, `data-placeholder`), plus the untouched pre-existing `StudyStats hide toggle (HOME-14)` block. |

## Invariant sensors (behaviour-level mutants)

Each mutation was injected in the working tree, the target suite run, then reverted.
**12 killed, 2 survived.**

| Invariant | Mutation injected | Result |
| --- | --- | --- |
| I-PU-1 | `0016` also adds `corpus_sections.page_number` | **KILLED** — `test_migration_0016_adds_reading_volume_without_touching_the_corpus` (+ `0015`) |
| I-PU-2 (backend) | `get_source_chapter` returns a literal `275` instead of `settings.words_per_page` | **KILLED** — `test_get_chapter_carries_the_page_size_from_settings` |
| I-PU-2 (client) | `FlowSection` receives `wordsPerPage={275}` instead of `chapter.words_per_page` | **KILLED** — 8 of 12 in `page-rules.test.tsx` |
| I-PU-3 | `saveReadingPosition` body becomes `{ anchor, percent: 25 }` | **KILLED** — `chapter-reader.test.tsx::keeps the position save carrying the anchor alone` |
| I-PU-4 | zero floor removed from `words_credited` | **KILLED** — `test_words_credited_is_zero_when_the_reader_moves_backwards`, `test_save_reading_position_moving_backwards_credits_no_words` |
| I-PU-5 | no prior position credits `words_before_row(index, target_idx)` | **KILLED** — 4 tests across `test_reading_pure.py` + `test_application_reading.py` |
| I-PU-6 (order) | `study_days.record` moved above the anchor-resolution guard | **KILLED** — 9 tests in `test_application_reading.py`, incl. `..._bad_anchor_credits_no_study_day`; and `test_web_reading.py::test_put_reading_position_rejected_save_stores_and_credits_nothing` |
| I-PU-6 (baseline) | prior position read *after* the upsert instead of before | **KILLED** — 4 tests incl. the DB-backed `test_put_reading_position_credits_the_words_covered_since_the_last_save` |
| I-PU-7 | heatmap shading total becomes `reviews_count + reading_updates + pages` | **KILLED** — 2 tests in `study-heatmap.test.tsx` |
| I-PU-8 | `{" "}` dropped after `Studied` so `textContent` loses a space | **KILLED** — 3 tests incl. the pre-existing HOME-12 adherence assertion |
| I-7 | every cell gets `title={activitySummary(cell)}` and `tabIndex={0}` | **KILLED** — 2 tests incl. `::leaves empty days silent` |
| PAGE-13 (mid-para) | boundary splits the paragraph itself at the word offset | **KILLED** — 5 tests; the "every paragraph is whole" assertion catches it |
| PAGE-13 (last) | `&& !last` guard removed | **KILLED** — 7 tests |
| PAGE-09 | `pages_from_words` ceils instead of flooring | **KILLED** — 3 tests |
| PAGE-09 (wire) | `words_advanced` added to `StudyDayView` | **KILLED** — 2 tests (the response key-set assertion) |
| PAGE-15 / AD-190 | section `scrollMarginTop` hardcoded to `64` while the bar stays `56` | **KILLED** — `reader-chrome.test.tsx::reserves exactly the sticky chrome's height` |
| AD-186 | `.book-column` pins `font-size: 18.5px; line-height: 1.62` | **KILLED** — `reading-column.test.tsx::reads its type size and line height from the reading variables` |
| PAGE-16 (continuity) | `useSectionProgress` always returns 0 | **KILLED** — 2 tests in `chapter-reader.test.tsx` |
| **PAGE-16 (clamp)** | `Math.min(100, Math.max(0, …))` removed from `bookPercent` | **SURVIVED** — full frontend suite green, 604/604 |
| **PAGE-23 (ring)** | `cell.today ? " ring-1 ring-muted-foreground" : ""` → `""` | **SURVIVED** — `study-heatmap.test.tsx` green, 26/26 |

## Conformance spot-checks

| Check | Result |
| --- | --- |
| TS `pageAt` ≡ backend `page_at` at boundaries | **AGREE.** Both evaluated over `(0,275) (1,275) (274,275) (275,275) (276,275) (549,275) (550,275) (5500,275) (600,200) (1000,0) (-5,275) (100,25)` → `[1,1,1,2,2,2,3,21,4,1,1,5]` on both sides. Covers the book's first word, the exact quantum boundary, a chapter starting mid-page (`100 @ 25` → page 5), a negative offset, and a non-positive quantum. |
| Per-day `pages` floors; raw word counter off the wire | **HOLDS.** `pages_from_words` uses `//` (`reading.py:144`); `StudyDayView` (`web/study.py:38-49`) carries only `day/reviews_count/reading_updates/pages`, asserted as an exact key set. Both mutants killed. |
| Heatmap ramp on `bg-muted` + `bg-chart-2..5`, no new colour vars (AD-188) | **HOLDS.** `LEVEL_CLASS` (`study-heatmap.tsx:61-67`) unchanged; `globals.css` contains no `--lv*`, `--cell-edge`, `--tip-bg`/`--tip-fg`. `--chart-2..5` are byte-identical to the artifact's `--lv1..lv4` in both themes (`globals.css:82-85`, `:122-125`). |
| Aa ladders unchanged and authoritative (AD-186) | **HOLDS.** `use-reading-settings.ts` and `reading-controls.tsx` are not in the diff; `READING_SIZES [17,19,21,23]` / `READING_LEADINGS [1.5,1.6,1.8]` intact. The column spec adds only padding, running title, and paragraph margin — no `font-size`/`line-height`. |
| One shared value feeds bar height and scroll margin (AD-190) | **HOLDS.** `READER_CHROME_HEIGHT` (`chapter-reader.tsx:107`) is the only source, consumed at `:708` (bar) and `:904` (section). Drift mutant killed. |
| No internal IDs in `main..HEAD` commit messages | **HOLDS.** All 12 subjects and bodies are plain language; no task/AD/PAGE/FR/cycle/Gate identifiers. |

## Gaps, ranked

1. **`frontend/app/components/chapter-reader.tsx:431-441` — PAGE-16's "clamped to 0..100" has no
   sensor.** Deleting the `Math.min(100, Math.max(0, …))` wrapper leaves the entire frontend suite
   green (604/604). The clamp is defensive — `useSectionProgress` already clamps its fraction to
   `[0,1]`, so it only fires on inconsistent word sums from the server (e.g. a
   `total_word_count` smaller than `words_before_chapter + chapter_word_count`). It matters
   because that is exactly the case the spec named, and it is the one branch of PAGE-16 that
   nothing would notice regressing.
2. **`frontend/app/components/study-heatmap.tsx:402` — PAGE-23's ring is asserted only through
   `data-today`.** `::rings today's cell and only today's` checks the data attribute and the day
   key, not the visual treatment; removing the `ring-1 ring-muted-foreground` class keeps the
   suite green. "Locatable by a ring" is the requirement's whole content, and the attribute is a
   test hook, not the affordance.
3. **`frontend/app/components/study-heatmap.tsx:332` — the graph wrapper carries `role="group"`
   where `approved-artifact-spec.md` §A specifies `role="img"`.** No test asserts either. Not a
   spec requirement (PAGE-19/20/21 reference §A for the grid tracks, not the wrapper role), and
   `role="group"` with the same `aria-label` is arguably the better choice for a container of
   focusable cells — flagged only so the divergence from the approved artifact is on the record.

Nothing above touches an invariant, a stored value, or the wire contract. Every invariant carries
a sensor that fires.

## Post-verification — gaps 1 and 2 closed

Both surviving mutants were closed by the orchestrator after this report was written; gap 3 was a
decision rather than a defect and is recorded as AD-192.

| Gap | Sensor added | Mutant re-run |
| --- | --- | --- |
| 1 — PAGE-16 clamp unsensored | `chapter-reader.test.tsx::holds the figure at 100% when the server's word sums do not add up` — renders a chapter whose offsets overrun the book total (`words_before_chapter 900 + chapter_word_count 500 > total_word_count 1000`), the clamp's only live branch | **KILLED.** Removing the `Math.min/Math.max` wrapper fails this test and only this test. |
| 2 — PAGE-23 ring asserted only via `data-today` | `study-heatmap.test.tsx::rings today's cell and only today's` extended to assert the ring class on today's cell and its absence on another. Matched on `ring-muted-foreground`, not `ring-1` — every cell already carries `inset-ring-1` for its hairline edge, so the looser match would pass on any cell and sense nothing | **KILLED.** Blanking the conditional class fails this test and only this test. |

Both mutations were injected together, confirmed to fail exactly the two named tests (2 failed /
79 passed), then reverted; `git diff` over `frontend/app/` is empty. Post-fix gate: frontend
**605 passed / 61 files**, `tsc --noEmit` clean.
