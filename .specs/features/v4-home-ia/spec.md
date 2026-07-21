# v4-home-ia Specification (RFC-004 Cycle E — Home + IA rewire)

## Problem Statement

The app has no home: authenticated users land on `/account` (a logout page) and navigate via a sidebar that lists every book. There is no "what should I do right now" surface, no visibility of study adherence (the Cycle F dogfood gate metric), and the public landing is a 9-line stub. Cycle E gives the product a two-card Home (continue reading + due cards), an adherence-framed streak/heatmap backed by a `study_days` rollup, and collapses the IA around it.

## Goals

- [ ] A signed-in user opening the app sees, in one screen, where to resume reading and whether cards are due — and can act on either in one click.
- [ ] Daily study activity (reviews and reading) is durably rolled up per user-local day; adherence ("Studied X of the last 14 days") and a heatmap render from it, computed at read time.
- [ ] Navigation collapses to Home / Bookshelf / Review / Notes; the landing page presents the product identity minimally.

## Out of Scope

| Feature | Reason |
| --- | --- |
| XP, coins, badges, popups, notifications, celebratory animations | RFC-004 gamification hard cap |
| Stored streak values or streak-freeze mechanics | RFC: streak computed at read time, never stored; adherence framing, not consecutive-count pressure |
| Backend per-user preferences table | AD-147 precedent: client persists toggles locally; hide-stats follows it |
| Marketing site / rich landing content | RFC out-of-scope; face-lift is minimal |
| Route renames (`/sources` → `/bookshelf`) | Display-level rename only; URL churn adds redirect risk with zero user value (D-6) |
| Windowing/virtualization, reader changes | Reader shipped in Cycles B–D; untouched |
| Daily digest email, spoiler-safe retrieval | RFC-004 explicit deferrals |

## Assumptions & Open Questions

All gray areas auto-decided per the ship-cycle rule; full rationale in `context.md`, durable rows AD-150..AD-156.

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| Home route | New `(app)/home`; brand link + post-login/post-register redirect → `/home` | D-1 | auto |
| What counts as a study day | A submitted review OR a saved reading position; per-kind counters kept | D-2 | auto |
| Day boundary | User-local day via `X-Client-Timezone` (IANA) header, validated server-side; fallback UTC | D-3 | auto |
| Rollup write transactionality | Same transaction as the triggering write (review insert / position upsert) | D-4 | auto |
| Nav set | Home / Bookshelf / Review / Notes (RFC's "Reader" entry = Bookshelf; Notes retained — shipped v3 flagship cannot be orphaned) | D-5 | auto |
| Bookshelf rename | Display-level only; route stays `/sources` | D-6 | auto |
| Hide-stats persistence | localStorage (`learny.home.v1`), default shown | D-7 | auto |
| Heatmap window | 84 days (12 weeks) default; endpoint `window` param min 7 / max 365 | D-8 | auto |
| Due data source | Existing `GET /api/reviews/due` `total_due`; no new endpoint | D-9 | auto |

**Open questions:** none — all resolved or logged above.

## User Stories

### P1: Continue-reading hero ⭐ MVP

**User Story**: As a reader, I want Home to show the book I'm in the middle of so that resuming takes one click.

**Acceptance Criteria**:

1. (HOME-01) WHEN `GET /api/reading/continue` is called by an authenticated user with at least one reading position THEN the system SHALL return the most recently updated position across all their sources: `source_id`, `source_title`, `chapter_title` (resolved from the stored anchor against the chapter index), `percent`, `updated_at`.
2. (HOME-02) WHEN the user has no reading positions THEN the endpoint SHALL return a null/empty shape (200), and the hero SHALL render an empty state linking to the bookshelf.
3. (HOME-03) WHEN the hero renders with data THEN it SHALL show book title, chapter title, and percent read, and its resume action SHALL navigate to `/sources/{id}/read` (the reader's existing resume path restores the stored position).
4. (HOME-04) WHEN the most recent position belongs to a source another user owns THEN it SHALL never be returned — the query is user-scoped.

**Independent Test**: Seed two users with positions; Home shows only the caller's latest book and resumes into it.

### P1: Due-cards card ⭐ MVP

**User Story**: As a student, I want Home to tell me whether cards are due so that I start (or skip) review without navigating.

**Acceptance Criteria**:

1. (HOME-05) WHEN cards are due (`total_due > 0` from `GET /api/reviews/due`) THEN the due card SHALL show the due count and a review CTA navigating to `/review`.
2. (HOME-06) WHEN `total_due == 0` THEN the card SHALL render a calm "done for today" state with no celebratory animation, badge, or popup.

**Independent Test**: With due cards seeded, Home shows the count; after reviewing all, it shows done-for-today.

### P1: `study_days` rollup ⭐ MVP

**User Story**: As a student, I want my daily study captured durably so that adherence stats reflect reality.

**Acceptance Criteria**:

1. (HOME-07) WHEN a review is submitted THEN the system SHALL upsert `study_days(user_id, day)` incrementing `reviews_count`, in the same transaction as the review-log insert.
2. (HOME-08) WHEN a reading position is saved THEN the system SHALL upsert `study_days(user_id, day)` incrementing `reading_updates`, in the same transaction as the position upsert.
3. (HOME-09) WHEN the request carries a valid IANA `X-Client-Timezone` header THEN `day` SHALL be the user-local date in that zone; WHEN the header is absent or invalid THEN `day` SHALL fall back to the UTC date — never an error.
4. (HOME-10) WHEN multiple qualifying events occur on the same user-local day (including concurrently) THEN exactly one row per `(user_id, day)` SHALL exist with counters equal to the event totals.

**Independent Test**: Submit 2 reviews + 1 position save in one local day → one row, `reviews_count=2`, `reading_updates=1`.

### P1: Streak + heatmap ⭐ MVP

**User Story**: As a student, I want to see "Studied X of the last 14 days" and a heatmap so that adherence is visible without gamification pressure.

**Acceptance Criteria**:

1. (HOME-11) WHEN `GET /api/study/days?window=N` is called THEN the system SHALL return the caller's study-day rows for the N-day window ending at the caller's local today (tz per HOME-09), plus `studied_last_14` computed at read time; `window` defaults to 84, bounds min 7 / max 365 (out-of-bounds → 422).
2. (HOME-12) WHEN the stats block renders THEN the streak line SHALL read "Studied X of the last 14 days" from the endpoint value; no consecutive-streak count SHALL be shown or stored.
3. (HOME-13) WHEN the heatmap renders THEN it SHALL show the window as a week-aligned grid where zero-activity days are plain empty cells (silent grace — no warnings or broken-streak messaging) and active days are shaded by activity count.
4. (HOME-14) WHEN the user toggles hide-stats THEN the streak+heatmap block SHALL hide, the choice SHALL persist across reloads via localStorage, and the default SHALL be visible.
5. (HOME-15) WHEN another user's study days exist THEN they SHALL never appear in the caller's response.

**Independent Test**: Seed 12 study days in the last 14 → line reads "Studied 12 of the last 14 days"; toggle hide → block gone after reload.

### P1: IA rewire ⭐ MVP

**User Story**: As a user, I want a small stable nav so that the app has three-and-a-half places, not a scrolling list of books.

**Acceptance Criteria**:

1. (HOME-16) WHEN the authenticated shell renders THEN the sidebar SHALL contain exactly Home, Bookshelf, Review, Notes as navigation items; the per-source Library group SHALL be removed; the brand link SHALL point to `/home`.
2. (HOME-17) WHEN a user logs in or registers THEN they SHALL land on `/home`.
3. (HOME-18) WHEN `/sources` renders THEN it SHALL present itself as the bookshelf (page title and shelf-like presentation of the user's books); the route SHALL remain `/sources`.
4. (HOME-19) WHEN existing deep links (`/sources/{id}/read`, `/review`, `/notes`, `/account`) are visited THEN they SHALL keep working unchanged; `/account` remains reachable from the header, not the sidebar.

**Independent Test**: Log in → land on `/home`; sidebar shows the four items; a book deep link still opens the reader.

### P2: Landing face-lift

**User Story**: As a visitor, I want the landing page to state what Learny is so that logging in isn't a leap of faith.

**Acceptance Criteria**:

1. (HOME-20) WHEN `/` renders for an anonymous visitor THEN it SHALL show the product name, a one-line value proposition, and Log in / Create account CTAs, styled with the Iron Gall identity tokens; no marketing sections.

**Independent Test**: Visit `/` logged out → identity-styled page with both CTAs.

## Edge Cases

- WHEN a brand-new user (no sources, no reviews) opens Home THEN hero shows the pick-a-book empty state, due card shows done-for-today, heatmap renders all-empty, streak reads "Studied 0 of the last 14 days".
- WHEN `X-Client-Timezone` is garbage (`"Mars/Olympus"`) THEN writes and reads fall back to UTC (HOME-09) with no 4xx/5xx.
- WHEN a source with the most recent position is deleted THEN `/api/reading/continue` returns the next most recent (or the empty shape) — never a dangling reference.
- WHEN two reviews for the same user commit concurrently at the same local day THEN no unique violation surfaces and counters total correctly (HOME-10).
- WHEN `window=6` or `window=400` THEN `/api/study/days` returns 422.

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| --- | --- | --- | --- |
| HOME-01..04 | P1 Continue-reading hero | Design | Pending |
| HOME-05..06 | P1 Due-cards card | Design | Pending |
| HOME-07..10 | P1 study_days rollup | Design | Pending |
| HOME-11..15 | P1 Streak + heatmap | Design | Pending |
| HOME-16..19 | P1 IA rewire | Design | Pending |
| HOME-20 | P2 Landing face-lift | Design | Pending |

## Implicit-Requirement Dimensions Sweep (Large)

| Dimension | Resolution |
| --- | --- |
| Input validation & bounds | `window` bounds (HOME-11); tz header validated with silent UTC fallback (HOME-09) |
| Failure / partial-failure | Rollup shares the triggering write's transaction — both commit or neither (HOME-07/08) |
| Idempotency / retry / duplicates | `(user_id, day)` PK + atomic upsert-increment (HOME-10) |
| Auth boundaries & rate limits | All new endpoints session-authenticated and user-scoped (HOME-04/15); read endpoints inherit existing default limits; no new rate-limit class |
| Concurrency / ordering | Concurrent same-day upserts resolved by ON CONFLICT increment (HOME-10) |
| Data lifecycle / expiry | `study_days.user_id` FK ON DELETE CASCADE; no TTL — the rollup IS the durable record |
| Observability | N/A beyond existing request logging — no new external calls or failure modes worth new instrumentation |
| External-dependency failure | N/A — cycle touches no AI providers, object storage, or queues |
| State-transition integrity | "Done for today" and streak are derived at read time, never stored — no transitions to guard |

## Success Criteria

- [ ] One screen answers "resume what?" and "review due?" with one-click actions.
- [ ] Adherence metric visible and correct against seeded fixtures; zero stored streak state.
- [ ] Nav shows exactly four items; all pre-existing deep links intact.
