# Reader Core Specification (v4-reader-core, RFC-004 Cycle B)

## Problem Statement

The reader is a single-section page behind an auth→section fetch waterfall: no chapter continuity, no memory of where the reader stopped, no reading controls, and captured highlights never re-appear on the page. RFC-004 names the reader the primary product surface; every later cycle (Ask/Teach panel, capture pipeline, Home) hangs off the chapter-flow reader this cycle builds.

## Goals

- [ ] A chapter reads as one continuous scrollable article with working deep links (`?anchor=` scrolls within the flow).
- [ ] Reading position survives leaving: reopening a book resumes where the reader stopped, with percent and minutes-left shown.
- [ ] The reader is configurable via the `Aa` popover on ADR-027's two-axis model (appearance × theme) plus size/spacing.
- [ ] In-reader TOC gives position context and a one-click return after any jump.
- [ ] First contentful render no longer waits for a sequential auth round-trip.

## Out of Scope

| Feature | Reason |
| --- | --- |
| Ask/Teach panel, selection verbs, citations-as-passages | RFC-004 Cycle C |
| Create-card, margin rail, review pins | RFC-004 Cycle D |
| Home surface, streak/heatmap, nav collapse | RFC-004 Cycle E |
| Pagination / page-turn mode | RFC-004 locks scroll, not pagination |
| Virtualized/windowed rendering | RFC-004 assumption: full-chapter render is acceptable; virtualization only if the assumption breaks (then added inside this cycle, not designed up front) |
| Server-side storage of Aa preferences | RFC-004 sanctions only `reading_position` as backend addition; prefs are device-local |
| Highlight editing/deletion in the reader | Capture exists (v3-E); management stays on the Notes screens until Cycle D |
| New highlight capture UX changes | v3-E capture popover ships unchanged; only rendering of existing highlights is in scope |

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| Definition of "chapter" | Depth-0 section + all contiguous following sections of greater depth (up to the next depth-0 section). Flat books (all depth 0) get one-section chapters. | Matches corpus ordering semantics (`position` + `depth`); no schema change needed | auto (AD-121) |
| Words-per-minute constant for minutes-left | 220 wpm, a named constant | Mid-range of published adult silent-reading rates; precision is not the product point | auto (AD-126) |
| Rate limiting on position writes | None beyond auth/CSRF; write is a tiny idempotent upsert debounced client-side | Matches existing pattern (only notes routes are rate-limited); scroll-idle debounce bounds frequency | auto (AD-124) |
| Percent semantics | Whole-book percent, server-computed from cumulative section word counts at the position anchor; stored denormalized | Server-computed keeps the value trustworthy for Home (Cycle E); client cannot forge progress | auto (AD-124) |
| Highlights painted | `active`-status anchors only; `stale`/`orphaned` stay on Notes screens | Stale/orphaned quotes no longer match served text by definition | auto (AD-127) |
| Paper appearance in dark mode | Paper choice persists but has no visual effect in dark (existing guarded selector); popover communicates the axis, never blocks it | ADR-027: dark is always Iron Gall night; AD-119 selector already enforces it | auto (AD-125) |

**Open questions:** none — all resolved or logged above.

## User Stories

### P1: Chapter-flow reading ⭐ MVP

**User Story**: As a reader, I want the whole current chapter as one continuous scrollable article so that reading flows like a book instead of fragmented section pages.

**Why P1**: The reader rebuild is the cycle's reason to exist; every other story renders inside this surface.

**Acceptance Criteria**:

1. WHEN the reader requests `GET /api/sources/{id}/chapter?anchor=<a>` for an anchor (or alias) the user owns THEN the system SHALL return the chapter containing that anchor: an ordered list of all its sections (anchor, title, section_path, markdown, word_count) plus chapter title, chapter index/count, previous/next chapter anchors (null at the edges), and the book-percent at the chapter start.
2. WHEN the anchor does not resolve, or the source is not owned by the caller, THEN the system SHALL return 404 with no existence disclosure (matching `ReadSection` semantics).
3. WHEN a chapter loads THEN the reader SHALL render every section in order inside one scrollable `.prose-reading` article — no per-section navigation clicks — with each section wrapper carrying its anchor as a DOM id.
4. WHEN the URL carries `?anchor=` pointing inside the loaded chapter THEN the reader SHALL scroll to that section (or heading fragment within it) and apply the existing transient highlight treatment.
5. WHEN the reader scrolls THEN the current chapter title SHALL remain visible via a sticky boundary element.
6. WHEN the reader reaches the chapter start or end THEN previous/next chapter controls SHALL navigate to the adjacent chapter (hidden/disabled at book edges).

**Independent Test**: Open a book at a mid-chapter section anchor; the full chapter renders as one article, scrolled to that section with a transient highlight; scrolling reveals sibling sections without navigation.

---

### P1: Reading position & progress ⭐ MVP

**User Story**: As a reader, I want the book to remember where I stopped and show my progress so that I can resume without hunting and see what's left.

**Why P1**: RFC-004's sanctioned backend addition; Home (Cycle E) consumes this state.

**Acceptance Criteria**:

1. WHEN the reader has been scroll-idle THEN the client SHALL PUT `/api/sources/{id}/reading-position` with the topmost visible section anchor exactly once per idle period (debounced; no write storm during active scrolling).
2. WHEN the server accepts a position write THEN it SHALL upsert one row per (user, source) storing the anchor and a server-computed whole-book percent derived from cumulative section word counts, and return the stored view.
3. WHEN the anchor in a position write does not resolve for that source THEN the system SHALL return 404 and store nothing.
4. WHEN the reader opens `/read` without `?anchor=` and a stored position exists THEN the reader SHALL load that position's chapter scrolled to the stored anchor; WHEN none exists THEN it SHALL load the first chapter at the top (replacing the "pick a section" empty state).
5. WHEN a chapter is open THEN the reader SHALL display book percent and chapter minutes-left computed from word counts at 220 wpm, updating as the reader scrolls.
6. WHEN two sessions write positions concurrently THEN last-write-wins by server time; no error is surfaced.
7. WHEN a position write fails THEN the reader SHALL stay usable and silently retry on the next scroll-idle.

**Independent Test**: Scroll mid-chapter, wait for idle write, reload `/read` without anchor — the same passage is on screen and the percent shown matches the server-stored value.

---

### P1: Word counts in the corpus ⭐ MVP

**User Story**: As the system, I need per-section word counts so that percent and minutes-left are derivable without re-parsing markdown per request.

**Why P1**: Both progress ACs depend on it.

**Acceptance Criteria**:

1. WHEN corpus build runs THEN each `corpus_sections` row SHALL be persisted with `word_count` = whitespace-delimited token count of its plain text (markdown stripped of formatting).
2. WHEN the migration runs on an existing database THEN every existing section row SHALL be backfilled with its computed word count (no NULLs remain).
3. WHEN a section has no prose (empty markdown) THEN its word_count SHALL be 0 and downstream percent math SHALL not divide by zero.

**Independent Test**: Ingest a fixture book; section word counts are non-zero and the sum matches an independent count of the fixture's text.

---

### P1: Aa popover — reading controls ⭐ MVP

**User Story**: As a reader, I want to adjust type size, spacing, appearance (Default/Paper), and light/dark from an `Aa` control so that long reading sessions fit my eyes.

**Why P1**: ADR-027 names the two-axis appearance control as part of the shipped identity; the Paper CSS layer is dead code until this control exists.

**Acceptance Criteria**:

1. WHEN the reader opens the `Aa` popover THEN it SHALL offer: type size (4 steps), line spacing (3 steps), appearance (Default / Paper), and theme (Light / Dark / System).
2. WHEN a size or spacing step is selected THEN the reading prose SHALL update immediately via CSS custom properties scoped to the reader (chrome and non-reader surfaces unaffected).
3. WHEN Paper is selected in light mode THEN the reader surface SHALL take the Paper palette (existing `[data-appearance="paper"]` layer); all non-reader chrome SHALL stay Iron Gall.
4. WHEN dark theme is active THEN the night palette SHALL apply regardless of the stored appearance choice (AD-119 selector semantics), and the popover SHALL still show the appearance axis.
5. WHEN the page reloads THEN all four settings SHALL persist (device-local) and re-apply without flash of wrong reading settings.
6. WHEN settings have never been touched THEN defaults SHALL be: size = current `.prose-reading` values (19px), spacing = 1.6, appearance = Default, theme = System.

**Independent Test**: Set XL size + Paper, reload — the chapter renders at XL on the Paper surface; toggle dark — night palette applies; toggle light — Paper returns.

---

### P1: In-reader TOC with position context & back-after-jump ⭐ MVP

**User Story**: As a reader, I want a table of contents beside the text that shows where I am and lets me jump and come back so that navigation never loses my place.

**Why P1**: RFC-004 Cycle B names it; the citation "Open in book" loop (and Cycle C's panel) depend on jump-and-return being safe.

**Acceptance Criteria**:

1. WHEN the reader is open THEN a TOC sidebar SHALL list the book structure (existing `/structure` data), marking the current chapter and current section as reading progresses.
2. WHEN a TOC entry is clicked THEN the reader SHALL navigate to it (in-flow scroll if same chapter; chapter load otherwise) and the URL `?anchor=` SHALL update.
3. WHEN a jump (TOC click or incoming `?anchor=` deep link) moves away from a live reading position THEN a return affordance SHALL offer one-click return to the pre-jump position, and SHALL disappear once used or once the reader resumes scrolling in the new location past a threshold.
4. WHEN the viewport is narrow THEN the TOC SHALL collapse behind a toggle rather than compressing the prose column.

**Independent Test**: While reading chapter 3, click a chapter 1 TOC entry; the reader shows chapter 1 and a return chip; clicking it lands back at the chapter 3 position.

---

### P1: Load-path fix ⭐ MVP

**User Story**: As a reader, I want the book to appear without avoidable waiting so that opening Learny feels like opening a book.

**Why P1**: RFC-004 names the auth→section waterfall a defect.

**Acceptance Criteria**:

1. WHEN the reader page loads THEN the auth-state fetch and the content fetch SHALL start in parallel (no sequential auth→content chain).
2. WHEN the content fetch returns 401 THEN the signed-out path SHALL behave exactly as today (redirect to login).
3. WHEN content is loading THEN the reader SHALL show a reading-surface skeleton instead of bare "Loading…" text.

**Independent Test**: Network log shows `/api/auth/me` and the chapter fetch dispatched together; total time-to-prose ≈ one round-trip, not two.

---

### P2: Highlights render inline

**User Story**: As a reader, I want my existing highlights visible in the text so that captured passages are part of the book, not a separate list.

**Why P2**: RFC-004 Cycle B line item; valuable but the reader functions without it.

**Acceptance Criteria**:

1. WHEN the owner requests `GET /api/sources/{id}/highlights` THEN the system SHALL return the caller's note anchors for that source (anchor, quote_exact, quote_prefix, quote_suffix, status, note id), 404 for non-owners.
2. WHEN a chapter renders and highlight quotes with `active` status match text within their anchored section THEN those ranges SHALL be wrapped in a highlight mark using the `--highlight-*` tokens.
3. WHEN a quote occurs more than once in its section THEN prefix/suffix context SHALL disambiguate; an unmatched quote SHALL simply not paint (no error, no fallback guessing).
4. WHEN highlighted text is rendered THEN the underlying prose markup SHALL be otherwise unchanged (copy/select behavior intact).

**Independent Test**: Capture a highlight (existing popover), reload the chapter — the passage shows the marker wash; a stale anchor paints nothing.

---

### P2: Ink-line signature & receding chrome

**User Story**: As a reader, I want minimal chrome with the ink-line progress mark so that the interface recedes and the signature element carries the identity.

**Why P2**: Identity element with a functional job (ADR-027: functional, not decorative); reader works without it.

**Acceptance Criteria**:

1. WHEN a chapter is open THEN a hairline ink rule SHALL sit at the top of the reader with a fill proportional to whole-book percent, using identity tokens (no raw hexes).
2. WHEN the reader scrolls down THEN non-essential chrome (top bar) SHALL recede; scrolling up SHALL restore it; the ink-line remains.
3. WHEN reduced-motion is requested THEN chrome transitions SHALL not animate.

**Independent Test**: Scroll down — the bar recedes, the ink-line stays and its fill matches the displayed percent; scroll up — the bar returns.

---

## Edge Cases

- WHEN the requested anchor is an `anchor_aliases` entry (OCR/renormalized corpora) THEN chapter resolution SHALL succeed exactly as for primary anchors.
- WHEN a book has a single chapter THEN prev/next controls SHALL both be absent and percent math SHALL still be correct.
- WHEN the stored reading-position anchor no longer resolves (superseded corpus) THEN `/read` SHALL fall back to the first chapter without erroring, leaving the stored row untouched until the next successful write.
- WHEN total book word count is 0 THEN percent SHALL be 0 and minutes-left 0 (no division by zero).
- WHEN localStorage is unavailable (private mode) THEN the Aa popover SHALL still work for the session with in-memory settings.
- WHEN the section markdown contains text matching a highlight quote across a formatting boundary THEN a non-match is acceptable (AC P2-1.3: silent non-paint), never a mis-paint of the wrong range.

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| --- | --- | --- | --- |
| RD-01 | P1 Chapter-flow: chapter endpoint (shape + word counts + edges) | Design | Done |
| RD-02 | P1 Chapter-flow: ownership/404 semantics | Design | Done |
| RD-03 | P1 Chapter-flow: continuous article render + DOM ids | Design | Done |
| RD-04 | P1 Chapter-flow: `?anchor=` in-flow scroll + transient highlight | Design | Done |
| RD-05 | P1 Chapter-flow: sticky chapter boundary | Design | Done |
| RD-06 | P1 Chapter-flow: prev/next chapter nav | Design | Done |
| RD-07 | P1 Position: scroll-idle debounced write | Design | Done |
| RD-08 | P1 Position: upsert + server-computed percent | Design | Done |
| RD-09 | P1 Position: invalid anchor 404 | Design | Done |
| RD-10 | P1 Position: resume on open / first-chapter fallback | Design | Done |
| RD-11 | P1 Position: percent + minutes-left display | Design | Done |
| RD-12 | P1 Position: last-write-wins concurrency | Design | Done |
| RD-13 | P1 Position: silent-retry on write failure | Design | Done |
| RD-14 | P1 Word counts: build-time persistence | Design | Done |
| RD-15 | P1 Word counts: migration backfill | Design | Done |
| RD-16 | P1 Word counts: zero-word safety | Design | Done |
| RD-17 | P1 Aa: four controls present | Design | Done |
| RD-18 | P1 Aa: size/spacing via reader-scoped CSS vars | Design | Done |
| RD-19 | P1 Aa: Paper applies (light), chrome stays Iron Gall | Design | Done |
| RD-20 | P1 Aa: dark overrides appearance (AD-119) | Design | Done |
| RD-21 | P1 Aa: persistence + no-flash re-apply | Design | Done |
| RD-22 | P1 TOC: structure list + current position context | Design | Done |
| RD-23 | P1 TOC: click-to-navigate + URL update | Design | Done |
| RD-24 | P1 TOC: back-after-jump affordance | Design | Done |
| RD-25 | P1 TOC: narrow-viewport collapse | Design | Done |
| RD-26 | P1 Load path: parallel fetches | Design | Done |
| RD-27 | P1 Load path: 401 behavior preserved + skeleton | Design | Done |
| RD-28 | P2 Highlights: listing endpoint + ownership | Design | Done |
| RD-29 | P2 Highlights: active-only paint w/ disambiguation, silent non-match | Design | Done |
| RD-30 | P2 Ink-line: progress fill from tokens | Design | Done |
| RD-31 | P2 Chrome: recede/restore + reduced-motion | Design | Done |

**Coverage:** 31 total, 31 implemented and gated across Phases A–D, 0 outstanding.

## Success Criteria

- [ ] Resume-from-anywhere works: close mid-chapter, reopen, same passage on screen — the RFC dogfood loop's first leg.
- [ ] A full chapter of the largest fixture book renders and scrolls without perceptible jank (RFC assumption holds).
- [ ] Citation "Open in book" deep links land inside the chapter flow with highlight, unchanged externally.
- [ ] All existing suites stay green (frontend 256+, backend 793+ offline); new behavior covered by tests derived from these ACs.
