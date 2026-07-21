# v4-home-ia — Decision Context

Gray areas auto-decided per the learny-ship-cycle auto-decision rule (no user in the loop except the merge gate). Each decision lists the options with why-recommend AND why-not. Durable rows: AD-150..AD-156 in `.specs/project/STATE.md`.

## D-1 — Home route and entry redirects

- **(a) New `(app)/home` route; brand link + post-login/post-register → `/home`** ← chosen
  - Why: keeps `/` as the public landing (it must stay anonymous-reachable for HOME-20); matches the existing route-group layout; post-login target is currently `/account` (a logout page) — strictly worse than any Home.
  - Why not: one more route to maintain; `/home` in the URL is mildly redundant.
- (b) Make Home the authenticated view of `/` (conditional render).
  - Why: prettiest URL.
  - Why not: mixes anonymous landing and authenticated shell in one route, breaking the `(auth)`/`(app)` layout split and middleware simplicity; highest regression risk for zero user-visible gain.

## D-2 — What counts as a study day

- **(a) Review submitted OR reading position saved; per-kind counters (`reviews_count`, `reading_updates`)** ← chosen
  - Why: RFC-004 is reading-first — a day spent only reading is a study day, and the Cycle F gate measures "real daily study", not reviews specifically; per-kind counters keep the gate free to re-weigh later without a migration.
  - Why not: a single scroll-triggered position save credits a day — the signal is generous. Mitigated: counters expose how thin a day was.
- (b) Reviews only.
  - Why: crisp, effortful signal.
  - Why not: contradicts reading-first framing; a user who reads two hours and reviews nothing would show a dead day — exactly the false negative an adherence UI must not produce.

## D-3 — Day boundary / timezone

- **(a) `X-Client-Timezone` IANA header on activity writes and stats reads; server validates via `zoneinfo`; silent UTC fallback** ← chosen
  - Why: the primary user is UTC-3 — evening study (21:00–24:00 local) lands on the wrong UTC day, visibly corrupting the heatmap and "today"; header keeps the API contract additive (no body changes) and the frontend sets it from `Intl.DateTimeFormat().resolvedOptions().timeZone`.
  - Why not: trusts the client's clock zone — acceptable, this is a personal adherence UI, not a security or billing surface.
- (b) UTC days everywhere.
  - Why: zero moving parts, fully deterministic.
  - Why not: demonstrably wrong for the actual dogfood user; the gate metric would misreport.
- (c) Per-user stored timezone setting.
  - Why: most correct long-term.
  - Why not: requires the preferences table AD-147 deliberately avoided; heavier than the need.

## D-4 — Rollup write transactionality

- **(a) Same transaction as the triggering write** ← chosen
  - Why: atomic — a recorded review and its study-day credit can't diverge; PostgreSQL-source-of-truth convention; the upsert is one trivial statement, so the added failure surface is negligible.
  - Why not: a rollup bug could fail a review write; accepted — the statement is small enough to test exhaustively.
- (b) Best-effort separate transaction / background task.
  - Why: review path isolated from rollup faults.
  - Why not: introduces silent-loss modes (review recorded, day missing) in the exact metric the dogfood gate reads; Celery for a one-row upsert is machinery without need.

## D-5 — Collapsed nav set

- **(a) Home / Bookshelf / Review / Notes** ← chosen
  - Why: RFC's "Home / Reader / Review" line predates the shipped Notes surfaces (v3-E/F flagship, PRs #31/#43) — orphaning Notes would regress a shipped flagship; "Reader" as a nav item is not directly enterable (needs a book), so the Bookshelf IS the reader entry; the real collapse is removing the per-source Library group from the sidebar.
  - Why not: four items, not the RFC's three — a letter-level deviation, recorded here deliberately.
- (b) Literal Home / Reader / Review (drop Notes; Reader → last-read book or bookshelf).
  - Why: letter-faithful to the RFC.
  - Why not: buries the v3 flagship behind no entry point; "Reader" with no open book still needs a bookshelf fallback, making it a worse-labeled Bookshelf.

## D-6 — Bookshelf rename depth

- **(a) Display-level rename + shelf presentation; route stays `/sources`** ← chosen
  - Why: users see "Bookshelf"; zero URL churn, zero redirect risk, deep links and tests keep working; RFC asks the Library to *become* the bookshelf, not for a URL.
  - Why not: route name and display name diverge — internal-only inconsistency.
- (b) Route rename to `/bookshelf` with redirect from `/sources`.
  - Why: full consistency.
  - Why not: redirect plumbing + sidebar/test churn for a URL nobody types.

## D-7 — Hide-stats persistence

- **(a) localStorage `learny.home.v1` (`showStats`, default true)** ← chosen
  - Why: exact precedent — reading settings (`learny.reading.v1`) and include-notes (`learny.include-notes.v1`) are device-local per AD-147's "no preferences table" stance.
  - Why not: not synced across devices; consistent with every other toggle in the product.
- (b) Backend settings table.
  - Why: cross-device.
  - Why not: contradicts AD-147; new table + endpoints for one boolean.

## D-8 — Heatmap window

- **(a) 84 days (12 weeks) default; `window` param min 7 / max 365** ← chosen
  - Why: 12 week columns render comfortably in a card at desktop and mobile widths; parameterized so the UI can tune without backend change; bounded to keep the query trivially cheap.
  - Why not: arbitrary-feeling constant; any constant is.
- (b) Fixed 365-day GitHub-style year.
  - Why: familiar idiom.
  - Why not: overflows the below-the-fold card on mobile; a year of mostly-empty cells at product age ~1 month reads as failure, not information.

## D-9 — Due-card data source

- **(a) Reuse `GET /api/reviews/due` (`total_due`)** ← chosen
  - Why: the endpoint already returns the exact number, user-scoped; `limit=1` keeps the payload tiny.
  - Why not: fetches one item's body needlessly; negligible.
- (b) New count-only endpoint.
  - Why: minimal payload.
  - Why not: duplicate query + view + tests for bytes.
