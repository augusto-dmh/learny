# v4-reader-core Context

**Gathered:** 2026-07-19 (auto-decision mode per learny-ship-cycle — recommended option chosen at each gray area, recorded here + STATE.md; escalation criteria checked at each: none met)
**Spec:** `.specs/features/v4-reader-core/spec.md`
**Status:** Ready for design

---

## Feature Boundary

RFC-004 Cycle B exactly: chapter-flow reader, reading position + progress (the one sanctioned backend addition plus its word-count prerequisite), Aa popover on the ADR-027 two-axis model, in-reader TOC with back-after-jump, load-path fix, inline rendering of existing highlights, ink-line signature + receding chrome. Nothing from Cycles C–F.

---

## Implementation Decisions

### D-1 · AD-121 — What is a "chapter"?

- **Chosen:** a depth-0 section plus all contiguous following sections of greater depth, ending before the next depth-0 section (by `corpus_sections.position`). Flat books (every section depth 0) yield one-section chapters.
- Why: matches the corpus ordering model (`position` + `depth`, normalization clamps depth jumps); zero schema change; alias resolution reuses existing anchor/alias lookup.
- Why not alternatives: a new `chapter_id` column (schema churn duplicating derivable structure); "EPUB spine item = chapter" (spine granularity is lost post-normalization and PDF corpora have no spine).

### D-2 · AD-122 — Chapter delivery

- **Chosen:** one new endpoint `GET /api/sources/{id}/chapter?anchor=` returning the full chapter (ordered sections with markdown + word_count, chapter title/index/count, prev/next chapter anchors, book-percent at chapter start), built as a `ReadChapter` use case beside `ReadSection`. `ReadSection` and its route stay untouched (citation popover still uses it).
- Why: one round-trip for the whole reading surface; ownership/404 semantics centralized in the application layer exactly like `ReadSection`; prev/next/percent computed where the data lives.
- Why not alternatives: client-composing N `?anchor=` section fetches (N round-trips, ownership checks per call, percent math scattered client-side); extending `/section` with a `mode=chapter` param (two response shapes behind one route muddies the contract).

### D-3 · AD-123 — Word counts

- **Chosen:** `word_count` column on `corpus_sections` (int, NOT NULL after backfill), computed at corpus build from the section's plain text; migration backfills existing rows in SQL/Python from stored markdown.
- Why: percent and minutes-left become simple SUM queries; ingestion already owns a normalization pass where the count is nearly free; backfill is one-time and bounded.
- Why not alternatives: computing per request (whole-book percent needs *all* sections' counts on every position write); a separate stats table (a join for one integer).

### D-4 · AD-124 — reading_position contract

- **Chosen:** table `reading_positions` PK `(user_id, source_id)`, columns `anchor`, `percent` (numeric), `updated_at`; FKs to `users` and `sources` **ON DELETE CASCADE** (product state, not a note — ADR-0026's inverse-cascade rule does not apply). API: `GET`/`PUT /api/sources/{id}/reading-position`; PUT body carries only `{anchor}`; server resolves the anchor (404 if unresolvable/not owned), computes whole-book percent from cumulative word counts, upserts, returns the view. Last-write-wins; no rate limit beyond auth+CSRF (client debounces on scroll-idle).
- Why: server-computed percent keeps Home's (Cycle E) number trustworthy; anchor-only payload means the client cannot forge progress; cascade delete prevents orphaned rows.
- Why not alternatives: client-computed percent in the payload (forgeable, drifts from corpus truth); event-log of positions (history is not a requirement; one row per (user, source) is the RFC shape); rate-limiting writes (foreign to every non-notes route; debounce already bounds volume).

### D-5 · AD-125 — Aa preferences storage & application

- **Chosen:** device-local persistence (one localStorage key, JSON, versioned), applied as reader-scoped CSS custom properties (size/spacing) plus `data-appearance` on the reader container; theme delegates to the existing `next-themes` control. Defaults = today's `.prose-reading` values. In-memory fallback when storage is unavailable.
- Why: RFC-004 sanctions only `reading_position` server-side; CSS-var application keeps `.prose-reading` the single source of typography truth; the Paper layer (AD-119) already keys off `data-appearance` under `html:not(.dark)`.
- Why not alternatives: backend prefs table (explicitly unsanctioned this cycle); per-control cookies (multiplies parsing for no cross-device win); setting `data-appearance` on `<html>` (widens Paper beyond the reader against ADR-027's reader-scope).

### D-6 · AD-126 — Minutes-left model

- **Chosen:** `220` wpm named constant; chapter minutes-left = ceil(unread chapter words / 220); shown with book percent in the reader chrome.
- Why: mid-range of adult silent-reading research; a constant is honest about being an estimate.
- Why not alternatives: per-user adaptive rate (needs reading-session telemetry that doesn't exist and isn't sanctioned); word counts at render time (rejected in D-3).

### D-7 · AD-127 — Inline highlight painting

- **Chosen:** new `GET /api/sources/{id}/highlights` (owner's anchors for the source: anchor, quotes, status, note id — mirror of the capture route, view reuses `NoteAnchorView` fields). Client paints `active` anchors only, by DOM-text search of `quote_exact` scoped to the anchored section's wrapper, disambiguated by `quote_prefix`/`quote_suffix`; unmatched or cross-boundary quotes silently don't paint. Marks use `--highlight-*` tokens.
- Why: read path mirrors the existing capture write path (same route family, same ownership rule); scoping search to the anchored section keeps it cheap and prevents wrong-section paints; silent non-match honors ADR-0026's "never guess" stance.
- Why not alternatives: server-side mark injection into markdown (couples corpus serving to notes, violating the no-FK boundary's spirit); offset-based painting (v3-E deliberately dropped offsets from the wire: client-side intermediate only); painting stale anchors dimmed (stale = text no longer matches; nothing truthful to paint).

### D-8 · AD-128 — Load-path fix shape

- **Chosen:** keep the reader a client component; fire `fetchAuthState()` and the chapter/position fetches concurrently (`Promise.all` semantics), render a reading-surface skeleton, preserve the existing 401→login behavior from the content response.
- Why: removes the full sequential round-trip (the named defect) with minimal blast radius; no RSC/cookie-forwarding rework mid-cycle.
- Why not alternatives: server-component prefetch (correct long-term but drags proxy/cookie forwarding and streaming into scope, and Cycle C rebuilds this surface again); optimistic content fetch with auth retry (equivalent latency win, more states).

### Agent's Discretion

- Exact skeleton composition, sticky-header styling, TOC collapse breakpoint, return-chip dismiss threshold, popover step values (size 17/19/21/23px; spacing 1.5/1.6/1.8) — within ADR-027 tokens and existing component idioms.

### Declined / Undiscussed Gray Areas → Assumptions

None declined (no user in the loop by design); every identified gray area is decided above and mirrored in the spec's Assumptions table.

---

## Specific References

- ADR-027 (two-axis appearance model; ink-line is functional; Paper is reader-scoped), AD-118 (WCAG vitest gate — extend for any new token pairs), AD-119 (guarded appearance selector), AD-113/ADR-0026 (highlight = note anchor; quote snapshot semantics), RFC-004 Cycle B bullet list (scope anchor).

## Deferred Ideas

- Per-user adaptive reading speed (needs telemetry; not sanctioned).
- RSC/streaming reader shell (revisit when Cycle C rebuilds the panel surface).
- Highlight management (edit/delete) in-reader — Cycle D's margin rail.
